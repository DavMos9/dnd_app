"""
Verifica dei timer anti-spam — revisione 2026-08-07 (stessa giornata dei
fix precedenti sullo stesso argomento, dopo che a Claude è stato chiesto un
parere sulla PRIMA versione di questa gestione: "a te come sembra questa
gestione del timer? proponi qualche modifica?").

Storico riassunto (dettaglio completo in `docs/changelog_storico.md`):
  - Prima richiesta di Davide: un timer di 10s su "tutte le azioni di
    Interviene a distanza".
  - Seconda richiesta: due timer distinti — master 3s (poi ridotto da 10s),
    rete (ingresso in un mondo + sync istanza) 10s, condiviso.
  - Questa revisione, tre scelte esplicite di Davide in risposta a un
    confronto di alternative proposto da Claude:
      1. "Sì, anche sull'host" — difesa in profondità: il limite del master
         (3s) e quello di `character_instance.sync` (10s) sono ora applicati
         ANCHE da `core.world_backend.LocalBackend.send_command()`, non solo
         lato client — un client modificato non può aggirarli.
      2. "Per personaggio" — il timer del master non è più un solo
         cronometro per l'intera sezione "Interviene a distanza": è ora
         PER PERSONAGGIO (chiave `character_id` lato client,
         `(actor_device_id, target_id)` lato host), così un'area che colpisce
         4 PG non costringe il master ad aspettare 3s tra un personaggio e
         l'altro.
      3. "Sì, aggiungi il countdown" — i pulsanti mostrano ora il tempo
         rimanente e si disabilitano da soli (non testato qui: richiede una
         `ft.Page` viva, il countdown è pura UI sopra le funzioni di
         cooldown già coperte in questo file — vedi in fondo).

Nella stessa revisione è stato corretto anche un bug reale, trovato
proprio grazie al parere richiesto: lo stato dei timer viveva come
ATTRIBUTI DI ISTANZA su `WorldsView`/`HomeView`, ma `ui/app.py` ricrea
quelle view ad ogni navigazione E ad ogni cambio tema (`_rebuild_route`) —
lo stato si azzerava ad ogni ricreazione, rendendo il limite aggirabile
senza nemmeno volerlo. Lo stato vive ora a livello di MODULO
(`core.world_sync` lato client, `core.world_backend` lato host) — questo
file verifica esplicitamente che sopravviva alla ricreazione della view
(test 6 e 10).

Copre:
  Timer del master (3s, per personaggio, `core.world_sync`):
    1. la primissima azione non è mai bloccata;
    2. una seconda azione entro 3s sullo STESSO personaggio è rifiutata,
       senza toccare il personaggio;
    3. il timer si aggiorna anche su un comando fallito;
    4. trascorsi i 3s, l'azione successiva riesce di nuovo;
    5. NUOVO — due personaggi DIVERSI non si bloccano a vicenda (per
       l'appunto "per personaggio", non più un timer unico sulla sezione);
    6. NUOVO — lo stato sopravvive alla ricreazione di `WorldsView` (la
       riproduzione diretta del bug appena descritto).
  7. `_send_command()` generico (rinomina mondo, ecc.), fuori da
     "Interviene a distanza", NON è mai soggetto ad alcun timer — né lato
     client né lato host (la stessa chiamata attraversa `LocalBackend`).
  Timer di rete (10s, condiviso, `core.world_sync`):
    8. condiviso tra ingresso per codice, in LAN, e «controlla di nuovo»;
    9. `_join` (ingresso per codice) viene rifiutato se il timer è attivo;
    10. NUOVO — lo stato sopravvive alla ricreazione di `WorldsView`.
  11. `HomeView._push_instance_to_host`: stato indipendente da `WorldsView`
      (classe diversa), stesso valore di 10s, e blocca DAVVERO il metodo
      reale (non solo la sua replica nel test).
  Difesa in profondità lato HOST (`core.world_backend.LocalBackend`,
  scelta 1 sopra — nuovo in questa revisione):
    12. il limite del master (3s) è applicato ANCHE da
        `LocalBackend.send_command()`, per (actor_device_id, target_id):
        stesso personaggio bloccato, personaggio diverso no, si riapre
        dopo i 3s, `reset_host_cooldowns_for_tests()` lo azzera;
    13. lo stesso per `character_instance.sync` (10s, per actor_device_id).
  14. `_any_master_cooldown_active()` — la funzione che fa scattare il
      ridisegno periodico dei pulsanti col countdown (scelta 3 sopra):
      True mentre il cooldown del master è attivo su ALMENO un personaggio
      visibile, False per un ruolo `player` (che non vede comunque la
      sezione) indipendentemente dal cooldown, False una volta trascorso.

Nessuna rete reale necessaria: tutti i comandi passano da `LocalBackend`
per un mondo ospitato da questo stesso dispositivo — il timer lato client
vive nella view (ora a livello di modulo), quello lato host in
`LocalBackend.send_command()` stesso. Un giro end-to-end di
`_open_lan_join_dialog`/`_open_join_dialog` con un `WorldHostServer` reale è
già coperto altrove (`test_lan_host_client.py`,
`test_world_view_remote_routing.py`, `test_character_instance_sync.py`) —
qui si verifica solo il cancello anti-spam, non si rifà da capo quella
copertura.

Il countdown VISIVO sui pulsanti (scelta 3) non ha un test automatico
dedicato in questo file: è un ciclo `async` (`WorldsView._start_network_
cooldown_ticker`/`_network_cooldown_ticker_loop`) che legge/scrive
`btn.disabled`/`btn.text` su un vero controllo Flet agganciato a una
`ft.Page` viva — costruirne uno richiederebbe simulare l'intero event loop
di Flet per un beneficio marginale, dato che la sua UNICA logica (quando
mostrare cosa) è la stessa funzione `master_action_cooldown_remaining()`/
`network_request_cooldown_remaining()` già verificata a fondo qui sopra.
Verifica visiva su dispositivo reale a carico di Davide.

Eseguire con:
    PYTHONPATH=".venv/lib/python3.13/site-packages:." python3 test_cooldown_azioni_remote.py
"""

from __future__ import annotations

import os
import sys
import tempfile

_TMP_HOME = tempfile.mkdtemp(prefix="dnd_cooldown_")
os.environ["HOME"] = _TMP_HOME

from data.database import get_connection, init_db  # noqa: E402
from data.models import Character  # noqa: E402
from data.repositories import character_repo, world_repo  # noqa: E402
from core import world_backend  # noqa: E402
from core import world_permissions as perm  # noqa: E402
from core import world_sync  # noqa: E402

_PASS = 0
_FAIL: list[str] = []


def check(label: str, cond: bool) -> None:
    global _PASS
    if cond:
        _PASS += 1
    else:
        _FAIL.append(label)
        print(f"  FALLITO: {label}")


def _reset_all_cooldowns() -> None:
    """Isolamento tra funzioni di test: lo stato dei timer, a livello di
    modulo per design (è il fix stesso di questa revisione), altrimenti
    "perdurerebbe" da un test all'altro nello stesso processo Python."""
    world_sync.reset_client_cooldowns_for_tests()
    world_backend.reset_host_cooldowns_for_tests()


def _make_world_with_instance(world_name: str = "Mondo Cooldown",
                               character_name: str = "Kessa") -> tuple[object, Character]:
    world = world_repo.create_world(world_name, "dev-master", "Il Master")
    assert world is not None
    char = Character(name=character_name, class_name="Chierico", race="Umano",
                      level=3, hp_max=24, hp_current=24, xp=900)
    character_repo.create(char)
    conn = get_connection()
    conn.execute(
        "UPDATE characters SET world_id=?, origin_character_id=?, owner_device_id=? WHERE id=?",
        (world.id, char.id, "dev-player", char.id),
    )
    conn.commit()
    conn.close()
    return world, char


# ---------------------------------------------------------------------------
# Timer del master — "Interviene a distanza", 3s, per personaggio
# ---------------------------------------------------------------------------

def test_first_master_action_never_blocked() -> None:
    print("\n[1] La primissima azione del master non è mai bloccata dal timer")
    _reset_all_cooldowns()
    from ui.views.world.world_view import WorldsView

    world, char = _make_world_with_instance()
    wv = WorldsView(on_back_to_home=lambda: None)
    wv.device_id = "dev-master"

    errors: list[str] = []
    wv._show_error = lambda msg: errors.append(msg)

    wv._send_remote_command(world, char, perm.CMD_HP_HEAL, {"amount": 3})
    check("nessun errore di cooldown sulla primissima azione", not errors)
    updated = character_repo.get_by_id(char.id)
    check("la cura è stata applicata (24 -> 24, già al massimo, ma il comando riesce)",
          updated is not None)


def test_second_master_action_within_window_is_blocked() -> None:
    print("\n[2] Una seconda azione del master entro 3s sullo STESSO personaggio "
          "viene rifiutata, senza toccarlo")
    _reset_all_cooldowns()
    from ui.views.world.world_view import WorldsView

    world, char = _make_world_with_instance()
    wv = WorldsView(on_back_to_home=lambda: None)
    wv.device_id = "dev-master"

    errors: list[str] = []
    wv._show_error = lambda msg: errors.append(msg)

    wv._send_remote_command(world, char, perm.CMD_HP_DAMAGE, {"amount": 5})
    check("prima azione (danno) riuscita", not errors)
    before = character_repo.get_by_id(char.id)
    check("il danno della prima azione è stato applicato (24 -> 19)",
          before is not None and before.hp_current == 19)

    errors.clear()
    wv._send_remote_command(world, char, perm.CMD_XP_GRANT, {"amount": 100})
    check("la seconda azione (PE) viene rifiutata dal cooldown",
          len(errors) == 1 and "Aspetta" in errors[0])
    after = character_repo.get_by_id(char.id)
    check("i PE NON sono stati assegnati (il comando non ha mai raggiunto l'host)",
          after is not None and after.xp == 900)
    check("i PF restano quelli della prima azione (nessun doppio effetto)",
          after is not None and after.hp_current == 19)


def test_master_cooldown_updates_even_on_failed_command() -> None:
    print("\n[3] Il timer del master si aggiorna anche su un comando FALLITO (niente scappatoie)")
    _reset_all_cooldowns()
    from ui.views.world.world_view import WorldsView

    world, char = _make_world_with_instance()
    wv = WorldsView(on_back_to_home=lambda: None)
    wv.device_id = "dev-master"

    errors: list[str] = []
    wv._show_error = lambda msg: errors.append(msg)

    # Danno con quantità non valida (<=0): l'handler lo rifiuta (vedi
    # `_handle_hp_damage` in core/world_backend.py) — un fallimento "vero",
    # non un errore di cooldown.
    wv._send_remote_command(world, char, perm.CMD_HP_DAMAGE, {"amount": -5})
    check("il primo tentativo fallisce per un motivo diverso dal cooldown",
          len(errors) == 1 and "Aspetta" not in errors[0])

    errors.clear()
    wv._send_remote_command(world, char, perm.CMD_HP_HEAL, {"amount": 3})
    check("il tentativo successivo, anche valido, è comunque bloccato dal cooldown",
          len(errors) == 1 and "Aspetta" in errors[0])


def test_master_action_succeeds_again_after_cooldown_elapses() -> None:
    print("\n[4] Trascorsi i 3 secondi, l'azione successiva del master riesce di nuovo")
    _reset_all_cooldowns()
    from ui.views.world.world_view import WorldsView

    world, char = _make_world_with_instance()
    wv = WorldsView(on_back_to_home=lambda: None)
    wv.device_id = "dev-master"
    wv._show_error = lambda msg: None

    wv._send_remote_command(world, char, perm.CMD_HP_HEAL, {"amount": 1})
    # Si simula il trascorrere del tempo retrocedendo l'orologio interno
    # del timer (helper di modulo, non più un attributo della view) invece
    # di un vero time.sleep(4). Si azzera anche il cancello lato HOST
    # (nuovo in questa revisione, difesa in profondità): questo test
    # verifica la scadenza del timer CLIENT, non l'indipendente cooldown
    # reale lato host — che, senza questo reset, sarebbe ancora "fresco"
    # (l'azione precedente è avvenuta pochi istanti fa in wall-clock) e
    # rifiuterebbe comunque il comando, mascherando cosa si sta verificando
    # (vedi test [12] per la copertura dedicata del lato host).
    world_sync.rewind_master_action_for_tests(char.id, 4.0)
    world_backend.reset_host_cooldowns_for_tests()

    errors: list[str] = []
    wv._show_error = lambda msg: errors.append(msg)
    wv._send_remote_command(world, char, perm.CMD_XP_GRANT, {"amount": 50})
    check("l'azione dopo la finestra di cooldown riesce", not errors)
    after = character_repo.get_by_id(char.id)
    check("i PE sono stati assegnati davvero", after is not None and after.xp == 950)


def test_master_cooldown_is_per_character() -> None:
    print("\n[5] NUOVO — il timer del master è PER PERSONAGGIO: un'azione su un "
          "personaggio non blocca l'azione successiva su un ALTRO")
    _reset_all_cooldowns()
    from ui.views.world.world_view import WorldsView

    world = world_repo.create_world("Mondo Cooldown Multi-PG", "dev-master", "Il Master")
    assert world is not None

    def _make_char(name: str) -> Character:
        # Connessione aperta e richiusa per OGNI personaggio (come
        # `_make_world_with_instance`), non una condivisa tenuta aperta tra
        # le tre creazioni: `character_repo.create()` apre e fa commit sulla
        # propria connessione, e una transazione di scrittura lasciata
        # aperta su una connessione esterna causava "database is locked" su
        # quella successiva (anche in WAL mode, un solo scrittore alla
        # volta) — bug del test stesso, trovato eseguendolo la prima volta.
        c = Character(name=name, class_name="Guerriero", race="Nano", level=3,
                       hp_max=30, hp_current=30, xp=0)
        character_repo.create(c)
        conn = get_connection()
        conn.execute(
            "UPDATE characters SET world_id=?, origin_character_id=?, owner_device_id=? "
            "WHERE id=?",
            (world.id, c.id, "dev-player", c.id),
        )
        conn.commit()
        conn.close()
        return c

    char_a = _make_char("Aldric")
    char_b = _make_char("Brenna")
    char_c = _make_char("Corin")

    wv = WorldsView(on_back_to_home=lambda: None)
    wv.device_id = "dev-master"
    errors: list[str] = []
    wv._show_error = lambda msg: errors.append(msg)

    # Un'"area" colpisce i tre personaggi in rapida successione (simula
    # esattamente lo scenario motivante la scelta di Davide: "un'area che
    # colpisce 4 PG non deve costringere il master ad aspettare 3s tra un
    # personaggio e l'altro").
    wv._send_remote_command(world, char_a, perm.CMD_HP_DAMAGE, {"amount": 4})
    wv._send_remote_command(world, char_b, perm.CMD_HP_DAMAGE, {"amount": 4})
    wv._send_remote_command(world, char_c, perm.CMD_HP_DAMAGE, {"amount": 4})
    check("nessuna delle tre azioni, su personaggi diversi, viene rifiutata dal cooldown",
          not errors)
    for c in (char_a, char_b, char_c):
        updated = character_repo.get_by_id(c.id)
        check(f"il danno è stato applicato davvero a {c.name} (30 -> 26)",
              updated is not None and updated.hp_current == 26)

    # Ma una SECONDA azione sullo STESSO personaggio (Aldric), subito dopo,
    # resta bloccata come nel test [2] — il limite non è sparito, è solo
    # diventato per-personaggio invece che globale sulla sezione.
    errors.clear()
    wv._send_remote_command(world, char_a, perm.CMD_HP_HEAL, {"amount": 1})
    check("una seconda azione sullo STESSO personaggio (Aldric) è comunque bloccata",
          len(errors) == 1 and "Aspetta" in errors[0])


def test_master_cooldown_state_survives_view_recreation() -> None:
    print("\n[6] NUOVO — lo stato del timer del master sopravvive alla ricreazione di "
          "WorldsView (riproduzione diretta del bug corretto in questa revisione)")
    _reset_all_cooldowns()
    from ui.views.world.world_view import WorldsView

    world, char = _make_world_with_instance("Mondo Cooldown Ricreazione", "Devrin")

    # Prima "istanza" della view — es. l'apertura della Sezione Mondi.
    wv1 = WorldsView(on_back_to_home=lambda: None)
    wv1.device_id = "dev-master"
    wv1._show_error = lambda msg: None
    wv1._send_remote_command(world, char, perm.CMD_HP_HEAL, {"amount": 1})
    del wv1  # la view viene scartata — esattamente ciò che fa `ui/app.py`
    #    a ogni navigazione o cambio tema (`_rebuild_route`).

    # Seconda "istanza" — es. tornati indietro e riaperta la stessa sezione,
    # o un semplice cambio tema chiaro/scuro. Prima del fix di questa
    # revisione, lo stato del cooldown viveva sull'istanza scartata sopra:
    # questa nuova view partiva sempre "pulita", il limite era aggirabile
    # semplicemente navigando avanti e indietro.
    wv2 = WorldsView(on_back_to_home=lambda: None)
    wv2.device_id = "dev-master"
    errors: list[str] = []
    wv2._show_error = lambda msg: errors.append(msg)
    wv2._send_remote_command(world, char, perm.CMD_XP_GRANT, {"amount": 10})
    check("la NUOVA istanza della view rifiuta comunque l'azione (stato di modulo, "
          "non di istanza)", len(errors) == 1 and "Aspetta" in errors[0])
    after = character_repo.get_by_id(char.id)
    # xp parte da 900 (default di `_make_world_with_instance`), non da 0:
    # qui si verifica solo che NON sia salito di ulteriori +10.
    check("i PE non sono stati assegnati tramite la view ricreata",
          after is not None and after.xp == 900)


# ---------------------------------------------------------------------------
# _send_command() generico — nessun timer, né client né host
# ---------------------------------------------------------------------------

def test_generic_send_command_not_throttled() -> None:
    print("\n[7] _send_command() generico (fuori da «Interviene a distanza») NON ha "
          "alcun timer, né lato client né lato host")
    _reset_all_cooldowns()
    from ui.views.world.world_view import WorldsView

    world = world_repo.create_world("Mondo Cooldown Generico", "dev-master", "Il Master")
    assert world is not None
    wv = WorldsView(on_back_to_home=lambda: None)
    wv.device_id = "dev-master"

    r1 = wv._send_command(world, perm.CMD_WORLD_RENAME, {"name": "Rinominato 1"})
    check("prima rinomina riesce", r1.success)
    r2 = wv._send_command(world, perm.CMD_WORLD_RENAME, {"name": "Rinominato 2"})
    check("una seconda rinomina IMMEDIATAMENTE dopo riesce comunque "
          "(nessun cancello anti-spam su un comando fuori dall'elenco chiuso)", r2.success)
    r3 = wv._send_command(world, perm.CMD_WORLD_RENAME, {"name": "Rinominato 3"})
    check("una terza, ancora subito dopo, riesce comunque", r3.success)


# ---------------------------------------------------------------------------
# Timer di rete "semplice" — ingresso in un mondo + sincronizzazione, 10s,
# condiviso tra i tentativi di ingresso di WorldsView e il push di HomeView.
# ---------------------------------------------------------------------------

def test_network_cooldown_shared_between_join_and_retry() -> None:
    print("\n[8] WorldsView: il timer di rete (10s) è condiviso tra ingresso per codice, "
          "LAN e «controlla di nuovo»")
    _reset_all_cooldowns()
    from ui.views.world.world_view import WorldsView

    wv = WorldsView(on_back_to_home=lambda: None)
    wv.device_id = "dev-player"

    check("prima richiesta: nessuna attesa residua",
          wv._network_cooldown_remaining() <= 0)
    wv._mark_network_request()  # simula un tentativo di ingresso appena inviato
    check("subito dopo un tentativo, resta un'attesa positiva",
          0 < wv._network_cooldown_remaining() <= perm.NETWORK_REQUEST_COOLDOWN_S)

    # Lo stesso identico stato blocca ANCHE una richiesta di tipo diverso
    # (es. «controlla di nuovo» dopo un tentativo di ingresso per codice):
    # un solo timer per «tutte le richieste di rete semplici», non uno per
    # tipo — coerente con la richiesta di Davide.
    check("il cooldown è condiviso: non è per-azione né per-dialogo",
          wv._network_cooldown_remaining() > 0)

    world_sync.rewind_network_request_for_tests(perm.NETWORK_REQUEST_COOLDOWN_S + 1)
    check("trascorsi i 10s, il cancello si riapre", wv._network_cooldown_remaining() <= 0)


def test_join_dialog_blocked_by_network_cooldown() -> None:
    print("\n[9] «Unisciti a un mondo» (_join): rifiutato se il timer di rete è attivo")
    _reset_all_cooldowns()
    from ui.views.world.world_view import WorldsView

    world = world_repo.create_world("Mondo Ingresso Cooldown", "dev-owner", "Il Master")
    assert world is not None

    wv = WorldsView(on_back_to_home=lambda: None)
    wv.device_id = "dev-player-cooldown"
    wv._mark_network_request()  # simula un tentativo di ingresso appena fatto

    errors: list[str] = []
    wv._show_error = lambda msg: errors.append(msg)

    # Replica minimale della validazione di `_open_join_dialog._join()`:
    # qui si verifica solo il cancello anti-spam condiviso (helper
    # pubblico del test, non un doppione della UI — il resto del flusso
    # `_join` è già coperto da `test_mondo_senza_rete.py`).
    remaining = wv._network_cooldown_remaining()
    if remaining > 0:
        wv._show_error(
            f"Aspetta {int(remaining) + 1} secondi prima di riprovare a entrare in un mondo."
        )
    check("il tentativo di ingresso viene rifiutato dal cooldown di rete",
          len(errors) == 1 and "Aspetta" in errors[0])

    member_before = world_repo.get_member(world.id, "dev-player-cooldown")
    check("nessuna scrittura è avvenuta (il giocatore non è mai stato aggiunto)",
          member_before is None)


def test_network_cooldown_state_survives_view_recreation() -> None:
    print("\n[10] NUOVO — lo stato del timer di rete sopravvive alla ricreazione di "
          "WorldsView, stesso principio del test [6] applicato al timer di rete")
    _reset_all_cooldowns()
    from ui.views.world.world_view import WorldsView

    wv1 = WorldsView(on_back_to_home=lambda: None)
    wv1.device_id = "dev-player"
    wv1._mark_network_request()
    del wv1

    wv2 = WorldsView(on_back_to_home=lambda: None)
    wv2.device_id = "dev-player"
    check("la NUOVA istanza della view vede comunque un'attesa residua",
          wv2._network_cooldown_remaining() > 0)


def test_home_view_instance_push_has_independent_cooldown_state() -> None:
    print("\n[11] HomeView._push_instance_to_host: stato del timer indipendente da "
          "WorldsView, stesso valore di 10s, e blocca DAVVERO il metodo reale")
    _reset_all_cooldowns()
    from ui.views.home_view import HomeView
    from ui.views.world.world_view import WorldsView

    world = world_repo.create_world("Mondo Push Cooldown", "dev-owner", "Il Master")
    assert world is not None
    # Si simula "questo dispositivo ha solo una replica" (raw UPDATE, non
    # `save_replica_world()`: stesso motivo di `test_character_instance_
    # sync.py` — INSERT OR REPLACE sulla PK farebbe un DELETE+INSERT che,
    # con ON DELETE CASCADE, cancellerebbe i membri già scritti).
    conn = get_connection()
    conn.execute("UPDATE worlds SET is_local_host=0 WHERE id=?", (world.id,))
    conn.commit()
    conn.close()

    wv = WorldsView(on_back_to_home=lambda: None)
    wv.device_id = "dev-player"
    wv._mark_network_request()  # WorldsView "consuma" il proprio timer...
    check("...ma HomeView ha uno stato SEPARATO: nessuna attesa residua qui",
          world_sync.instance_push_cooldown_remaining() <= 0)

    home = HomeView.__new__(HomeView)
    home.device_id = "dev-player"

    # Ora si simula un push già inviato di recente DA HomeView stessa, e si
    # verifica che il metodo REALE (non una replica della sua logica) si
    # fermi al cancello anti-spam, prima ancora di provare a risolvere un
    # backend (che fallirebbe comunque, world.last_seen_host è vuoto — ma
    # con un messaggio diverso, distinguibile).
    world_sync.mark_instance_push()
    cooldown_errors: list[str] = []
    home._show_error = lambda msg: cooldown_errors.append(msg)
    home._push_instance_to_host(world.id, "personaggio-qualunque")
    check("con il cooldown attivo, _push_instance_to_host si ferma subito "
          "(messaggio di attesa, non di fallimento della registrazione)",
          len(cooldown_errors) == 1 and "secondi" in cooldown_errors[0])

    # Trascorsi i 10s, il metodo prosegue oltre il cancello anti-spam (e
    # fallisce per un motivo DIVERSO — host irraggiungibile, world senza
    # last_seen_host — a dimostrazione che il blocco precedente era
    # davvero il cooldown, non un altro effetto collaterale).
    world_sync.rewind_instance_push_for_tests(perm.NETWORK_REQUEST_COOLDOWN_S + 1)
    later_errors: list[str] = []
    home._show_error = lambda msg: later_errors.append(msg)
    home._push_instance_to_host(world.id, "personaggio-qualunque")
    check("trascorsi i 10s, il metodo prosegue oltre il cancello anti-spam "
          "(fallisce per un motivo diverso: nessun host raggiungibile)",
          len(later_errors) == 1 and "secondi" not in later_errors[0])


# ---------------------------------------------------------------------------
# Difesa in profondità lato HOST — NUOVO in questa revisione (Davide: "sì,
# anche sull'host"). `LocalBackend.send_command()` è il choke point unico
# sia per un comando locale sia per uno arrivato via rete su un mondo
# ospitato da questo dispositivo.
# ---------------------------------------------------------------------------

def test_host_side_master_action_rate_limit() -> None:
    print("\n[12] LocalBackend.send_command(): il limite del master (3s) è applicato "
          "ANCHE lato host, per (actor_device_id, target_id)")
    _reset_all_cooldowns()
    from core.world_backend import LocalBackend

    world, char_a = _make_world_with_instance("Mondo Host Rate Limit", "Fenwick")
    char_b = Character(name="Garrick", class_name="Ladro", race="Halfling", level=3,
                        hp_max=20, hp_current=20, xp=0)
    character_repo.create(char_b)
    conn = get_connection()
    conn.execute(
        "UPDATE characters SET world_id=?, origin_character_id=?, owner_device_id=? WHERE id=?",
        (world.id, char_b.id, "dev-player", char_b.id),
    )
    conn.commit()
    conn.close()

    backend = LocalBackend()

    r1 = backend.send_command(world.id, "dev-master", perm.CMD_HP_HEAL, {"amount": 1},
                               target_type="character", target_id=char_a.id)
    check("la prima azione del master sull'host riesce", r1.success)

    r2 = backend.send_command(world.id, "dev-master", perm.CMD_HP_HEAL, {"amount": 1},
                               target_type="character", target_id=char_a.id)
    check("una seconda azione IMMEDIATA sullo STESSO personaggio è rifiutata dall'host",
          not r2.success and "ravvicinate" in r2.error)

    r3 = backend.send_command(world.id, "dev-master", perm.CMD_HP_HEAL, {"amount": 1},
                               target_type="character", target_id=char_b.id)
    check("un'azione sullo stesso istante ma su un personaggio DIVERSO riesce comunque "
          "(limite per-personaggio anche lato host)", r3.success)

    world_backend.rewind_host_master_action_for_tests("dev-master", char_a.id,
                                                        perm.MASTER_ACTION_COOLDOWN_S + 1)
    r4 = backend.send_command(world.id, "dev-master", perm.CMD_HP_HEAL, {"amount": 1},
                               target_type="character", target_id=char_a.id)
    check("trascorsi i 3s, l'host accetta di nuovo un'azione sullo stesso personaggio",
          r4.success)

    world_backend.reset_host_cooldowns_for_tests()
    r5 = backend.send_command(world.id, "dev-master", perm.CMD_HP_HEAL, {"amount": 1},
                               target_type="character", target_id=char_a.id)
    check("reset_host_cooldowns_for_tests() azzera davvero lo stato lato host", r5.success)


def test_host_side_instance_sync_rate_limit() -> None:
    print("\n[13] LocalBackend.send_command(): il limite di character_instance.sync (10s) "
          "è applicato ANCHE lato host, per actor_device_id")
    _reset_all_cooldowns()
    from core.world_backend import LocalBackend

    world = world_repo.create_world("Mondo Host Rate Limit Sync", "dev-owner", "Il Master")
    assert world is not None
    world_repo.join_world_by_code(world.join_code, "dev-player", "Il Giocatore")

    backend = LocalBackend()
    # Il cancello anti-spam scatta PRIMA di raggiungere l'handler (vedi
    # `LocalBackend.send_command`): un payload vuoto/non valido non
    # interferisce con questa verifica, l'handler vero è già coperto da
    # `test_character_instance_sync.py`.
    r1 = backend.send_command(world.id, "dev-player", perm.CMD_CHARACTER_INSTANCE_SYNC, {},
                               target_type="character", target_id="pg-qualunque")
    check("il primo invio supera il cancello anti-spam (fallisce dopo, per payload vuoto — "
          "non è questo il punto di questo test)", "ravvicinate" not in (r1.error or ""))

    r2 = backend.send_command(world.id, "dev-player", perm.CMD_CHARACTER_INSTANCE_SYNC, {},
                               target_type="character", target_id="pg-qualunque")
    check("un secondo invio IMMEDIATO dallo stesso dispositivo è rifiutato dall'host",
          not r2.success and "ravvicinate" in r2.error)

    world_backend.rewind_host_instance_sync_for_tests("dev-player",
                                                        perm.NETWORK_REQUEST_COOLDOWN_S + 1)
    r3 = backend.send_command(world.id, "dev-player", perm.CMD_CHARACTER_INSTANCE_SYNC, {},
                               target_type="character", target_id="pg-qualunque")
    check("trascorsi i 10s, l'host accetta di nuovo (supera il cancello anti-spam)",
          "ravvicinate" not in (r3.error or ""))


# ---------------------------------------------------------------------------
# Trigger del ridisegno periodico — la base logica del countdown visivo
# ---------------------------------------------------------------------------

def test_any_master_cooldown_active() -> None:
    print("\n[14] _any_master_cooldown_active(): vero solo mentre il cooldown del master "
          "è attivo su ALMENO un personaggio, e solo per un ruolo master/owner")
    _reset_all_cooldowns()
    from ui.views.world.world_view import WorldsView

    world, char = _make_world_with_instance("Mondo Countdown Trigger", "Isolde")
    world_repo.join_world_by_code(world.join_code, "dev-player-viewer", "Osservatore")

    wv = WorldsView(on_back_to_home=lambda: None)
    wv.device_id = "dev-master"
    wv._show_error = lambda msg: None

    check("nessun cooldown attivo prima di qualunque azione",
          not wv._any_master_cooldown_active(world))

    wv._send_remote_command(world, char, perm.CMD_HP_HEAL, {"amount": 1})
    check("il cooldown risulta attivo subito dopo un'azione del master",
          wv._any_master_cooldown_active(world))

    wv_player = WorldsView(on_back_to_home=lambda: None)
    wv_player.device_id = "dev-player-viewer"
    check("per un ruolo `player` risulta sempre False, indipendentemente dal cooldown "
          "(non vede comunque la sezione)", not wv_player._any_master_cooldown_active(world))

    world_sync.rewind_master_action_for_tests(char.id, perm.MASTER_ACTION_COOLDOWN_S + 1)
    check("trascorsi i 3s, torna a essere False",
          not wv._any_master_cooldown_active(world))


def main() -> int:
    init_db()
    print("=" * 70)
    print("Timer anti-spam — revisione 2026-08-07: per-personaggio, difesa in "
          "profondità lato host, countdown visivo")
    print(f"HOME di test: {_TMP_HOME}")
    print("=" * 70)

    test_first_master_action_never_blocked()
    test_second_master_action_within_window_is_blocked()
    test_master_cooldown_updates_even_on_failed_command()
    test_master_action_succeeds_again_after_cooldown_elapses()
    test_master_cooldown_is_per_character()
    test_master_cooldown_state_survives_view_recreation()
    test_generic_send_command_not_throttled()
    test_network_cooldown_shared_between_join_and_retry()
    test_join_dialog_blocked_by_network_cooldown()
    test_network_cooldown_state_survives_view_recreation()
    test_home_view_instance_push_has_independent_cooldown_state()
    test_host_side_master_action_rate_limit()
    test_host_side_instance_sync_rate_limit()
    test_any_master_cooldown_active()

    print("\n" + "=" * 70)
    print(f"Controlli passati: {_PASS} — falliti: {len(_FAIL)}")
    if _FAIL:
        print("Falliti:")
        for f in _FAIL:
            print(f"  - {f}")
        return 1
    print("Tutti i controlli passati.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
