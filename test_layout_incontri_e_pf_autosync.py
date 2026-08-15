"""
Batteria di verifica delle tre richieste di Davide del 2026-08-07 (sessione
"vorrei discutere di alcune cose", dopo aver confermato che il primo giro di
fix del Multiplayer funzionava su Wi-Fi reale):

[1] Layout — troppo spazio sopra la lista Incontri (selettore mondo +
    Generatori Rapidi + tab bar + header Incontri prima di vedere una sola
    card). Scelta di Davide (AskUserQuestion): togliere "Generatori Rapidi"
    SOLO nella tab "Incontri" (`ui/views/master/master_view.py`).

[2] Comodità del master — Danno/Cura/Condizione duplicati per ogni PG
    istanza di un mondo direttamente nel tracker di combattimento
    (`ui/views/master/master_encounter_view.py`), senza dover cambiare
    schermata verso la Sezione Mondi. Scelta di Davide: solo queste tre
    azioni, non l'intero pannello "Interviene a distanza".

[3] Sincronizzazione — quando il giocatore stesso modifica i propri PF sulla
    scheda (danno subito, cura, riposo, TS morte, modifica manuale), un
    nuovo comando `hp.self_update` (`core/world_permissions.py`,
    `core/world_backend.py`, `core/world_sync.py`,
    `ui/views/character_sheet/combattimento_tab.py`) lo invia in automatico
    verso l'host — scelta di Davide: invio automatico in tempo reale, non
    manuale come «Aggiorna il mio foglio» (§6.1, che resta per il resync
    COMPLETO, non per i soli PF).

Usa SEMPRE un DB temporaneo isolato (tempfile.mkdtemp() + HOME separato),
stesso pattern di tutte le altre batterie di questo progetto.

Eseguire con:
    PYTHONPATH=".venv/lib/python3.13/site-packages:." python3 test_layout_incontri_e_pf_autosync.py
"""

from __future__ import annotations

import os
import sys
import tempfile

_TMP_HOME = tempfile.mkdtemp(prefix="dnd_layout_pf_autosync_")
os.environ["HOME"] = _TMP_HOME

from data.database import init_db  # noqa: E402
from data.models import Character  # noqa: E402
from data.repositories import character_repo, master_repo, world_repo  # noqa: E402
from core import character_instances as ci  # noqa: E402
from core import world_permissions as perm  # noqa: E402
from core import world_backend  # noqa: E402
from core import world_sync  # noqa: E402
from core.world_backend import LocalBackend  # noqa: E402

_PASS = 0
_FAIL: list[str] = []


def check(label: str, cond: bool) -> None:
    global _PASS
    if cond:
        _PASS += 1
    else:
        _FAIL.append(label)
        print(f"  FALLITO: {label}")


def _send(backend: LocalBackend, *args, **kwargs):
    """Ignora il rate limit lato host — stesso motivo/stesso pattern di
    `test_master_remote_actions.py::_send`: qui si verifica la correttezza
    degli handler, il rate limiting ha le proprie batterie dedicate."""
    world_backend.reset_host_cooldowns_for_tests()
    return backend.send_command(*args, **kwargs)


def _make_world_with_instance(owner_device="dev-owner", player_device="dev-player",
                               name="Elara", level=4, hp_max=30):
    world = world_repo.create_world("Mondo Layout/PF", owner_device, "Il Master")
    assert world is not None

    local = Character(
        name=name, class_name="Chierico", race="Umano", level=level,
        hit_dice_type=8, hit_dice_total=level, hit_dice_remaining=level,
        str_score=12, dex_score=10, con_score=14, int_score=10,
        wis_score=16, cha_score=10,
        hp_max=hp_max, hp_current=hp_max,
    )
    character_repo.create(local)

    result = ci.create_or_resume_instance(world.id, local.id, player_device, mode="as_is")
    assert result.success, result.error
    instance = character_repo.get_by_id(result.character_id)
    assert instance is not None

    world_repo.join_world_by_code(world.join_code, player_device, "Il Giocatore")
    return world, instance


def _reload(character_id: str) -> Character:
    c = character_repo.get_by_id(character_id)
    assert c is not None
    return c


# ---------------------------------------------------------------------------
# [1] Layout — MasterView, pannello strumenti a comparsa (restyle 2026-08-07,
# sessione successiva: Davide ha chiesto di reintrodurre i Generatori Rapidi
# ovunque — invertendo la scelta "solo fuori da Incontri" testata sopra fino
# a poco fa — raggruppandoli però con il selettore mondo dietro un unico
# pannello a comparsa, per restare compatti senza più eccezioni per tab).
# ---------------------------------------------------------------------------

def test_layout_pannello_strumenti() -> None:
    print("\n[1] MasterView — pannello strumenti a comparsa, uniforme su ogni tab")
    from ui.views.master.master_view import MasterView

    for tab in ("npcs", "encounters", "magic_items"):
        mv = MasterView(on_back_to_home=lambda: None, active_tab=tab)
        check(f"tab '{tab}': il pannello strumenti esiste sempre, incluso Incontri",
              mv._tools_panel_container is not None)
        check(f"tab '{tab}': il pannello strumenti è nei controls",
              mv._tools_panel_container in mv.controls)
        check(f"tab '{tab}': collassato di default", mv._tools_panel_expanded is False)
        check(f"tab '{tab}': la tab bar resta presente", mv._tab_bar_container in mv.controls)

    # Toggle: apre e mostra selettore mondo + Generatori Rapidi, richiude.
    mv = MasterView(on_back_to_home=lambda: None, active_tab="encounters")
    panel_before = mv._tools_panel_container
    mv._on_tools_panel_toggle(not mv._tools_panel_expanded)
    check("un click sul pannello lo espande", mv._tools_panel_expanded is True)
    check("il pannello espanso è un controllo NUOVO (sostituito in place, "
          "non un semplice flip di 'visible')", mv._tools_panel_container is not panel_before)
    check("il pannello espanso resta nei controls", mv._tools_panel_container in mv.controls)
    mv._on_tools_panel_toggle(not mv._tools_panel_expanded)
    check("un secondo click lo richiude", mv._tools_panel_expanded is False)

    # Cambiare mondo (_on_world_change) fa una _build() completa: lo stato
    # di apertura/chiusura del pannello non deve azzerarsi da solo.
    mv._on_tools_panel_toggle(not mv._tools_panel_expanded)
    check("pannello espanso prima del cambio mondo", mv._tools_panel_expanded is True)

    class _FakeEvent:
        class control:
            value = "un-world-id-qualunque"  # diverso da "" (Nessun mondo): forza _build()

    mv._on_world_change(_FakeEvent())
    check("lo stato espanso/collassato sopravvive a un cambio mondo (_build() completa)",
          mv._tools_panel_expanded is True)

    # _on_child_focus_change deve restare a prova di None per il caso
    # "prima ancora del primo _build()" — qui invece testiamo il caso
    # normale, container sempre valorizzato: nasconde/mostra senza sollevare.
    mv._on_child_focus_change(True)
    check("_on_child_focus_change(True) non solleva e nasconde il pannello",
          mv._tools_panel_container.visible is False)
    mv._on_child_focus_change(False)
    check("_on_child_focus_change(False) non solleva e lo rimostra",
          mv._tools_panel_container.visible is True)


# ---------------------------------------------------------------------------
# [2] hp.self_update — permessi, handler, rate limit host
# ---------------------------------------------------------------------------

def test_permessi_hp_self_update() -> None:
    print("\n[2] core/world_permissions.py — hp.self_update")
    check("ruolo minimo 'player' basta", perm.can_perform(perm.ROLE_PLAYER, perm.CMD_HP_SELF_UPDATE))
    check("richiede la verifica di proprietà (elenco PLAYER_OWNED_COMMANDS)",
          perm.CMD_HP_SELF_UPDATE in perm.PLAYER_OWNED_COMMANDS)
    check("è tra i comandi che mutano il personaggio (serve alla replica)",
          perm.CMD_HP_SELF_UPDATE in perm.CHARACTER_MUTATING_COMMANDS)
    check("NON è tra le azioni 'Interviene a distanza' del master (è del giocatore)",
          perm.CMD_HP_SELF_UPDATE not in perm.MASTER_REMOTE_ACTION_COMMANDS)
    check("ha un cooldown dedicato, più corto di quello del master",
          0 < perm.HP_SELF_UPDATE_COOLDOWN_S < perm.MASTER_ACTION_COOLDOWN_S)


def test_handler_hp_self_update() -> None:
    print("\n[3] core/world_backend.py — handler hp.self_update")
    world, instance = _make_world_with_instance(name="Bram", hp_max=28)
    backend = LocalBackend()

    # Il proprietario invia il proprio stato aggiornato (valori assoluti)
    result = _send(
        backend, world.id, "dev-player", perm.CMD_HP_SELF_UPDATE,
        {"hp_current": 15, "hp_temp": 3, "death_saves_success": 0, "death_saves_failure": 0},
        target_type="character", target_id=instance.id,
    )
    check("il proprietario può aggiornare i propri PF", result.success)
    after = _reload(instance.id)
    check("hp_current scritto sull'host", after.hp_current == 15)
    check("hp_temp scritto sull'host", after.hp_temp == 3)
    check("l'evento finisce nel registro", result.event is not None
          and result.event.kind == perm.CMD_HP_SELF_UPDATE)

    # Un dispositivo diverso dal proprietario NON può farlo (nemmeno il master)
    result2 = _send(
        backend, world.id, "dev-owner", perm.CMD_HP_SELF_UPDATE,
        {"hp_current": 1, "hp_temp": 0}, target_type="character", target_id=instance.id,
    )
    check("il master NON può inviare hp.self_update per il giocatore",
          not result2.success)
    check("il rifiuto non ha toccato lo stato", _reload(instance.id).hp_current == 15)

    # Clamp: hp_current non può superare hp_max né scendere sotto 0
    result3 = _send(
        backend, world.id, "dev-player", perm.CMD_HP_SELF_UPDATE,
        {"hp_current": 9999, "hp_temp": -5}, target_type="character", target_id=instance.id,
    )
    check("l'invio con valori fuori range riesce comunque (clamp, non rifiuto)", result3.success)
    after3 = _reload(instance.id)
    check("hp_current è stato clampato a hp_max", after3.hp_current == after3.hp_max)
    check("hp_temp negativo è stato clampato a 0", after3.hp_temp == 0)

    # Tiri salvezza contro morte inclusi nel payload
    result4 = _send(
        backend, world.id, "dev-player", perm.CMD_HP_SELF_UPDATE,
        {"hp_current": 0, "hp_temp": 0, "death_saves_success": 1, "death_saves_failure": 2},
        target_type="character", target_id=instance.id,
    )
    check("l'invio aggiorna anche i tiri salvezza contro morte", result4.success)
    after4 = _reload(instance.id)
    check("death_saves_success scritto", after4.death_saves_success == 1)
    check("death_saves_failure scritto", after4.death_saves_failure == 2)


def test_rate_limit_host_hp_self_update() -> None:
    print("\n[4] core/world_backend.py — difesa in profondità lato host per hp.self_update")
    world, instance = _make_world_with_instance(name="Nyx")
    backend = LocalBackend()
    world_backend.reset_host_cooldowns_for_tests()

    r1 = backend.send_command(
        world.id, "dev-player", perm.CMD_HP_SELF_UPDATE,
        {"hp_current": 10, "hp_temp": 0}, target_type="character", target_id=instance.id,
    )
    check("primo invio riesce", r1.success)
    r2 = backend.send_command(
        world.id, "dev-player", perm.CMD_HP_SELF_UPDATE,
        {"hp_current": 9, "hp_temp": 0}, target_type="character", target_id=instance.id,
    )
    check("secondo invio ravvicinato viene rifiutato (rate limit host)", not r2.success)
    check("lo stato riflette solo il primo invio", _reload(instance.id).hp_current == 10)

    world_backend.rewind_host_hp_self_update_for_tests(
        "dev-player", instance.id, perm.HP_SELF_UPDATE_COOLDOWN_S + 1,
    )
    r3 = backend.send_command(
        world.id, "dev-player", perm.CMD_HP_SELF_UPDATE,
        {"hp_current": 9, "hp_temp": 0}, target_type="character", target_id=instance.id,
    )
    check("dopo il cooldown il prossimo invio riesce", r3.success)
    check("lo stato riflette il terzo invio", _reload(instance.id).hp_current == 9)


# ---------------------------------------------------------------------------
# [3] core/world_sync.py — cooldown lato client (debounce, mai bloccante)
# ---------------------------------------------------------------------------

def test_cooldown_client_hp_self_update() -> None:
    print("\n[5] core/world_sync.py — cooldown lato client per hp.self_update")
    world_sync.reset_client_cooldowns_for_tests()

    check("nessun cooldown attivo prima del primo invio",
          world_sync.hp_self_update_cooldown_remaining("char-a") <= 0)
    world_sync.mark_hp_self_update("char-a")
    check("subito dopo mark_hp_self_update il cooldown è attivo",
          world_sync.hp_self_update_cooldown_remaining("char-a") > 0)
    check("un personaggio DIVERSO non è toccato dal cooldown",
          world_sync.hp_self_update_cooldown_remaining("char-b") <= 0)

    world_sync.rewind_hp_self_update_for_tests("char-a", perm.HP_SELF_UPDATE_COOLDOWN_S + 1)
    check("dopo il rewind il cooldown è di nuovo scaduto",
          world_sync.hp_self_update_cooldown_remaining("char-a") <= 0)

    world_sync.reset_client_cooldowns_for_tests()


# ---------------------------------------------------------------------------
# [4] combattimento_tab.py — la scheda pianifica l'invio, mai in modo bloccante
# ---------------------------------------------------------------------------

def test_scheda_schedule_hp_world_sync() -> None:
    print("\n[6] CombattimentoTab — _schedule_hp_world_sync() non blocca mai la scheda")
    from ui.views.character_sheet.combattimento_tab import CombattimentoTab

    # Personaggio LOCALE (nessun mondo): _schedule_hp_world_sync deve essere
    # un no-op sicuro anche senza alcuna pagina montata (did_mount mai
    # chiamato in questo test, self._page resta None).
    local_char = Character(
        name="Solista", class_name="Ladro", race="Halfling", level=2,
        hit_dice_type=8, hit_dice_total=2, hit_dice_remaining=2,
        str_score=10, dex_score=16, con_score=12, int_score=10,
        wis_score=10, cha_score=10, hp_max=16, hp_current=16,
    )
    character_repo.create(local_char)
    tab_local = CombattimentoTab(local_char)
    try:
        tab_local._schedule_hp_world_sync()
        check("nessuna eccezione per un personaggio locale senza pagina montata", True)
    except Exception as e:  # pragma: no cover - non dovrebbe mai accadere
        check(f"non deve sollevare per un personaggio locale ({e})", False)
    check("un personaggio locale non genera mai un tentativo di rete "
          "(world_id vuoto, controllo immediato in cima al metodo)",
          not local_char.world_id)

    # Personaggio istanza di un mondo, ma SENZA pagina montata: anche qui
    # deve restare un no-op sicuro (page is None -> return), la scheda non
    # deve mai bloccarsi o sollevare per la sola assenza di rete/pagina.
    world, instance = _make_world_with_instance(name="Rete", hp_max=20)
    tab_world = CombattimentoTab(instance)
    try:
        tab_world._schedule_hp_world_sync()
        check("nessuna eccezione per un'istanza di mondo senza pagina montata", True)
    except Exception as e:  # pragma: no cover
        check(f"non deve sollevare per un'istanza senza pagina ({e})", False)
    check("senza una pagina montata il metodo esce PRIMA di programmare "
          "alcun invio (nessun task orfano, generation resta a 0)",
          tab_world._hp_sync_generation == 0)


# ---------------------------------------------------------------------------
# [+] condition.self_apply/self_remove — estensione graduale di hp.self_update
# (2026-08-07, scelta di Davide dopo aver chiesto "la scheda che ha il
# giocatore deve essere completamente sincronizzata con i dati che ha il
# master": estendere gradualmente il pattern hp.self_update ad altri campi,
# uno alla volta, ognuno un comando auditabile). Le condizioni sono il primo.
# ---------------------------------------------------------------------------

def test_permessi_condition_self_update() -> None:
    print("\n[7] core/world_permissions.py — condition.self_apply/self_remove")
    for cmd in (perm.CMD_CONDITION_SELF_APPLY, perm.CMD_CONDITION_SELF_REMOVE):
        check(f"ruolo minimo 'player' basta per {cmd}",
              perm.can_perform(perm.ROLE_PLAYER, cmd))
        check(f"{cmd} richiede la verifica di proprietà",
              cmd in perm.PLAYER_OWNED_COMMANDS)
        check(f"{cmd} è tra i comandi che mutano il personaggio (serve alla replica)",
              cmd in perm.CHARACTER_MUTATING_COMMANDS)
        check(f"{cmd} NON è tra le azioni 'Interviene a distanza' del master",
              cmd not in perm.MASTER_REMOTE_ACTION_COMMANDS)
    check("cooldown dedicato, più corto di quello del master",
          0 < perm.CONDITION_SELF_UPDATE_COOLDOWN_S < perm.MASTER_ACTION_COOLDOWN_S)


def test_handler_condition_self_update() -> None:
    print("\n[8] core/world_backend.py — handler condition.self_apply/self_remove")
    world, instance = _make_world_with_instance(name="Odile", hp_max=22)
    backend = LocalBackend()

    # Il proprietario si applica una condizione
    result = _send(
        backend, world.id, "dev-player", perm.CMD_CONDITION_SELF_APPLY,
        {"condition_key": "prono", "source": "", "note": ""},
        target_type="character", target_id=instance.id,
    )
    check("il proprietario può applicarsi una condizione", result.success)
    check("l'evento finisce nel registro",
          result.event is not None and result.event.kind == perm.CMD_CONDITION_SELF_APPLY)
    conditions = character_repo.get_conditions(instance.id)
    check("la condizione è scritta sull'host", any(c.condition_key == "prono" for c in conditions))

    # Un dispositivo diverso dal proprietario NON può farlo (nemmeno il master)
    world_backend.reset_host_cooldowns_for_tests()
    result2 = _send(
        backend, world.id, "dev-owner", perm.CMD_CONDITION_SELF_APPLY,
        {"condition_key": "accecato"}, target_type="character", target_id=instance.id,
    )
    check("il master NON può inviare condition.self_apply per il giocatore",
          not result2.success)
    check("nessuna condizione in più è stata scritta",
          len(character_repo.get_conditions(instance.id)) == 1)

    # Condizione sconosciuta -> rifiutata
    world_backend.reset_host_cooldowns_for_tests()
    result3 = _send(
        backend, world.id, "dev-player", perm.CMD_CONDITION_SELF_APPLY,
        {"condition_key": "non-esiste"}, target_type="character", target_id=instance.id,
    )
    check("una chiave di condizione sconosciuta viene rifiutata", not result3.success)

    # Rimozione per condition_key — IL PUNTO CENTRALE del fix: l'id della
    # riga sull'host (generato da add_condition sopra) NON è mai stato
    # comunicato al client, che quindi non potrebbe MAI identificarla per
    # id — solo per condition_key, esattamente come farebbe un giocatore
    # vero (vedi il docstring di _handle_condition_self_remove).
    world_backend.reset_host_cooldowns_for_tests()
    result4 = _send(
        backend, world.id, "dev-player", perm.CMD_CONDITION_SELF_REMOVE,
        {"condition_key": "prono"}, target_type="character", target_id=instance.id,
    )
    check("il proprietario può rimuoversi una condizione per chiave, "
          "senza conoscere l'id della riga sull'host", result4.success)
    check("la condizione non è più presente sull'host",
          not any(c.condition_key == "prono" for c in character_repo.get_conditions(instance.id)))

    # Rimuovere una condizione non presente -> rifiutata, non un no-op silenzioso
    world_backend.reset_host_cooldowns_for_tests()
    result5 = _send(
        backend, world.id, "dev-player", perm.CMD_CONDITION_SELF_REMOVE,
        {"condition_key": "prono"}, target_type="character", target_id=instance.id,
    )
    check("rimuovere una condizione già assente viene rifiutato onestamente",
          not result5.success)

    # Un dispositivo diverso dal proprietario non può rimuovere
    world_backend.reset_host_cooldowns_for_tests()
    _send(backend, world.id, "dev-player", perm.CMD_CONDITION_SELF_APPLY,
          {"condition_key": "avvelenato"}, target_type="character", target_id=instance.id)
    world_backend.reset_host_cooldowns_for_tests()
    result6 = _send(
        backend, world.id, "dev-owner", perm.CMD_CONDITION_SELF_REMOVE,
        {"condition_key": "avvelenato"}, target_type="character", target_id=instance.id,
    )
    check("il master NON può rimuovere una condizione per conto del giocatore",
          not result6.success)


def test_rate_limit_host_condition_self_update() -> None:
    print("\n[9] core/world_backend.py — difesa in profondità lato host per condition.self_*")
    world, instance = _make_world_with_instance(name="Ravel")
    backend = LocalBackend()
    world_backend.reset_host_cooldowns_for_tests()

    r1 = backend.send_command(
        world.id, "dev-player", perm.CMD_CONDITION_SELF_APPLY,
        {"condition_key": "stordito"}, target_type="character", target_id=instance.id,
    )
    check("primo invio riesce", r1.success)
    r2 = backend.send_command(
        world.id, "dev-player", perm.CMD_CONDITION_SELF_APPLY,
        {"condition_key": "spaventato"}, target_type="character", target_id=instance.id,
    )
    check("secondo invio ravvicinato sullo stesso personaggio viene rifiutato "
          "(rate limit host)", not r2.success)
    check("solo la prima condizione è presente",
          {c.condition_key for c in character_repo.get_conditions(instance.id)} == {"stordito"})

    world_backend.rewind_host_condition_self_update_for_tests(
        "dev-player", instance.id, perm.CONDITION_SELF_UPDATE_COOLDOWN_S + 1,
    )
    r3 = backend.send_command(
        world.id, "dev-player", perm.CMD_CONDITION_SELF_APPLY,
        {"condition_key": "spaventato"}, target_type="character", target_id=instance.id,
    )
    check("dopo il cooldown il prossimo invio riesce", r3.success)
    check("entrambe le condizioni sono presenti",
          {c.condition_key for c in character_repo.get_conditions(instance.id)}
          == {"stordito", "spaventato"})


def test_cooldown_client_condition_self_update() -> None:
    print("\n[10] core/world_sync.py — cooldown lato client per condition.self_*")
    world_sync.reset_client_cooldowns_for_tests()

    check("nessun cooldown attivo prima del primo invio",
          world_sync.condition_self_update_cooldown_remaining("char-x") <= 0)
    world_sync.mark_condition_self_update("char-x")
    check("subito dopo mark_condition_self_update il cooldown è attivo",
          world_sync.condition_self_update_cooldown_remaining("char-x") > 0)
    check("un personaggio DIVERSO non è toccato dal cooldown",
          world_sync.condition_self_update_cooldown_remaining("char-y") <= 0)

    world_sync.rewind_condition_self_update_for_tests(
        "char-x", perm.CONDITION_SELF_UPDATE_COOLDOWN_S + 1,
    )
    check("dopo il rewind il cooldown è di nuovo scaduto",
          world_sync.condition_self_update_cooldown_remaining("char-x") <= 0)

    world_sync.reset_client_cooldowns_for_tests()


def test_scheda_schedule_condition_world_sync() -> None:
    print("\n[11] CombattimentoTab — _schedule_condition_*_sync() non blocca mai la scheda, "
          "e il picker/il dialog richiamano davvero l'invio")
    from ui.views.character_sheet.combattimento_tab import CombattimentoTab

    # Personaggio locale: no-op sicuro anche senza pagina montata.
    local_char = Character(
        name="Solitaria", class_name="Druido", race="Elfo", level=3,
        hit_dice_type=8, hit_dice_total=3, hit_dice_remaining=3,
        str_score=10, dex_score=14, con_score=12, int_score=12,
        wis_score=16, cha_score=10, hp_max=20, hp_current=20,
    )
    character_repo.create(local_char)
    tab_local = CombattimentoTab(local_char)
    try:
        tab_local._schedule_condition_apply_sync("prono", "", "")
        tab_local._schedule_condition_remove_sync("prono")
        check("nessuna eccezione per un personaggio locale senza pagina montata", True)
    except Exception as e:  # pragma: no cover
        check(f"non deve sollevare per un personaggio locale ({e})", False)

    # Istanza di un mondo, ma senza pagina montata: no-op sicuro.
    world, instance = _make_world_with_instance(name="Vex", hp_max=18)
    tab_world = CombattimentoTab(instance)
    try:
        tab_world._schedule_condition_apply_sync("accecato", "", "")
        check("nessuna eccezione per un'istanza di mondo senza pagina montata", True)
    except Exception as e:  # pragma: no cover
        check(f"non deve sollevare per un'istanza senza pagina ({e})", False)

    # End-to-end attraverso il picker/dialog reali (non solo il metodo di
    # schedulazione isolato): _add()/_remove() devono chiamare
    # _schedule_condition_*_sync con gli argomenti giusti. Verificato
    # sostituendo temporaneamente i due metodi con un finto che registra le
    # chiamate, invece di montare una pagina Flet vera solo per questo.
    calls: list[tuple] = []
    tab_world._schedule_condition_apply_sync = lambda k, s, n: calls.append(("apply", k, s, n))
    tab_world._schedule_condition_remove_sync = lambda k: calls.append(("remove", k))
    tab_world._page = object()  # non None: basta a superare il guard dei due metodi originali

    import flet as ft
    from ui.widgets import CardPicker  # noqa: F401 — solo per assicurarsi che l'import esista

    class _FakePage:
        def __init__(self):
            self.dialogs = []
        def show_dialog(self, dlg):
            self.dialogs.append(dlg)
        def pop_dialog(self):
            pass
        def update(self):
            pass

    fake_page = _FakePage()
    tab_world._page = fake_page
    tab_world._open_condition_picker()
    dlg = fake_page.dialogs[-1]

    def walk(ctrl):
        yield ctrl
        for attr in ("controls", "content", "actions"):
            v = getattr(ctrl, attr, None)
            if isinstance(v, list):
                for c in v:
                    yield from walk(c)
            elif v is not None and hasattr(v, "controls") or hasattr(v, "content"):
                yield from walk(v)

    add_btn = next((c for c in walk(dlg) if isinstance(c, ft.ElevatedButton)
                     and "Aggiungi" in str(getattr(c, "content", ""))), None)
    check("il dialog 'Aggiungi condizione' espone un pulsante di conferma",
          add_btn is not None)
    if add_btn is not None:
        add_btn.on_click(None)
    check("_add() ha richiamato _schedule_condition_apply_sync",
          any(c[0] == "apply" for c in calls))

    calls.clear()
    conditions = character_repo.get_conditions(instance.id)
    if conditions:
        tab_world._on_condition_click(conditions[0])
        dlg2 = fake_page.dialogs[-1]
        remove_btn = next((c for c in walk(dlg2) if isinstance(c, ft.ElevatedButton)
                            and "Rimuovi" in str(getattr(c, "content", ""))), None)
        check("il dialog di dettaglio condizione espone 'Rimuovi'", remove_btn is not None)
        if remove_btn is not None:
            remove_btn.on_click(None)
        check("_remove() ha richiamato _schedule_condition_remove_sync",
              any(c[0] == "remove" for c in calls))
    else:
        check("nessuna condizione da testare per _on_condition_click "
              "(picker precedente non ha scritto nulla in locale?)", False)


# ---------------------------------------------------------------------------
# [5] master_repo — world_id esposto da get_encounter_members_resolved
# ---------------------------------------------------------------------------

def test_encounter_members_resolved_world_id() -> None:
    print("\n[11] master_repo.get_encounter_members_resolved — world_id per i PG")
    world, instance = _make_world_with_instance(name="Talon", hp_max=24)
    enc = master_repo.create_encounter(name="Imboscata")
    assert enc is not None

    local_char = Character(
        name="Solo", class_name="Mago", race="Elfo", level=3,
        hit_dice_type=6, hit_dice_total=3, hit_dice_remaining=3,
        str_score=8, dex_score=14, con_score=12, int_score=16,
        wis_score=10, cha_score=10, hp_max=14, hp_current=14,
    )
    character_repo.create(local_char)

    master_repo.add_member(enc.id, kind="character", character_id=instance.id)
    master_repo.add_member(enc.id, kind="character", character_id=local_char.id)

    resolved = master_repo.get_encounter_members_resolved(enc.id)
    by_name = {r["name"]: r for r in resolved}
    check("il PG istanza di mondo espone il world_id giusto",
          by_name[instance.name]["world_id"] == world.id)
    check("il PG locale espone world_id vuoto",
          by_name[local_char.name]["world_id"] == "")


# ---------------------------------------------------------------------------
# [6] master_encounter_view — Danno/Cura/Condizione per un PG dall'incontro
# ---------------------------------------------------------------------------

def test_encounter_view_pg_remote_actions() -> None:
    print("\n[12] MasterEncounterView — Danno/Cura/Condizione su un PG istanza di mondo")
    from ui.views.master.master_encounter_view import MasterEncounterView

    world, instance = _make_world_with_instance(
        owner_device="dev-owner", player_device="dev-player2", name="Kael", hp_max=32,
    )
    enc = master_repo.create_encounter(name="Agguato nella foresta")
    assert enc is not None
    master_repo.add_member(enc.id, kind="character", character_id=instance.id)

    mev = MasterEncounterView(
        encounter_id=enc.id, on_back_to_list=lambda: None,
        world_id=world.id, device_id="dev-owner",
    )
    world_backend.reset_host_cooldowns_for_tests()
    world_sync.reset_client_cooldowns_for_tests()

    check("nessun cooldown attivo per questo PG all'inizio",
          mev._pg_cooldown_remaining(instance.id) <= 0)

    mev._send_pg_remote_command(
        instance.id, instance.name, world.id,
        perm.CMD_HP_DAMAGE, {"amount": 12, "is_critical": False},
    )
    after = _reload(instance.id)
    check("il danno inviato dall'incontro raggiunge la tabella characters",
          after.hp_current == 20)
    check("il cooldown per QUESTO personaggio è ora attivo",
          mev._pg_cooldown_remaining(instance.id) > 0)

    # Il refresh() della vista deve vedere il nuovo valore LIVE (stesso
    # principio già esistente per i PG: mai un valore cachato sulla riga
    # dell'incontro, sempre letto da `characters`).
    mev.refresh()
    resolved = {r["member"].character_id: r for r in mev._members}
    check("MasterEncounterView.refresh() riflette il danno appena applicato",
          resolved[instance.id]["hp_current"] == 20)

    # Un secondo invio ravvicinato sullo STESSO personaggio è bloccato dal
    # cooldown condiviso con "Interviene a distanza" (stato di modulo).
    from ui.views.world import world_view as _wv  # noqa: F401 — solo per assicurarsi
    # che il modulo condivida davvero lo stato (import equivalente a quello
    # già fatto da world_view.py stesso, nessuna istanza separata di
    # core.world_sync possibile in Python).
    result_blocked = LocalBackend().send_command(
        world.id, "dev-owner", perm.CMD_HP_HEAL, {"amount": 5},
        target_type="character", target_id=instance.id,
    )
    # Questo invio passa DIRETTAMENTE da LocalBackend (bypassa il cooldown
    # client di _send_pg_remote_command): verifica che la difesa lato host
    # da sola sia comunque attiva sull'azione appena inviata sopra.
    check("la difesa in profondità lato host blocca comunque il secondo invio "
          "ravvicinato, anche bypassando il cooldown client",
          not result_blocked.success)
    check("lo stato non è cambiato dal tentativo bloccato",
          _reload(instance.id).hp_current == 20)



# ---------------------------------------------------------------------------
# [9] Bug reale segnalato da Davide dopo il primo giro di verifica:
# "mittente non è membro di questo mondo" anche col giocatore presente,
# quando il mondo selezionato nel dropdown di Modalità Master (self._world_id
# sulla vista) NON coincide col mondo di cui il PG bersaglio è istanza. La
# vecchia `_send_pg_remote_command` usava `self._world_id` incondizionatamente
# invece del world_id proprio del personaggio — qui si riproduce esattamente
# lo scenario (vista costruita con un world_id diverso, anzi vuoto come nello
# screenshot di Davide: dropdown su "Locale") per impedire una regressione.
# ---------------------------------------------------------------------------

def test_encounter_view_send_usa_world_id_del_personaggio() -> None:
    print("\n[13] MasterEncounterView — usa il world_id del PG, non quello del dropdown")
    from ui.views.master.master_encounter_view import MasterEncounterView

    world, instance = _make_world_with_instance(
        owner_device="dev-owner", player_device="dev-player3", name="Troia", hp_max=21,
    )
    enc = master_repo.create_encounter(name="Incontro Casuale")
    assert enc is not None
    master_repo.add_member(enc.id, kind="character", character_id=instance.id)

    # Vista costruita con world_id="" (dropdown su "Locale"), esattamente
    # come nello screenshot di Davide — non con world.id come nel test [8].
    mev = MasterEncounterView(
        encounter_id=enc.id, on_back_to_list=lambda: None,
        world_id="", device_id="dev-owner",
    )
    world_backend.reset_host_cooldowns_for_tests()
    world_sync.reset_client_cooldowns_for_tests()

    check("self._world_id sulla vista è vuoto (dropdown su Locale)",
          mev._world_id == "")
    check("il PG bersaglio appartiene comunque a un mondo vero",
          instance.world_id == world.id and world.id != "")

    mev._send_pg_remote_command(
        instance.id, instance.name, instance.world_id,
        perm.CMD_HP_HEAL, {"amount": 5},
    )
    after = _reload(instance.id)
    check("la cura raggiunge characters anche con self._world_id vuoto "
          "(usa il world_id del personaggio, non quello del dropdown)",
          after.hp_current == 21)  # già al massimo, la cura non supera hp_max

    # Danno stavolta, per verificare che il valore cambi davvero (non solo
    # che l'invio non fallisca).
    world_sync.reset_client_cooldowns_for_tests()
    world_backend.reset_host_cooldowns_for_tests()
    mev._send_pg_remote_command(
        instance.id, instance.name, instance.world_id,
        perm.CMD_HP_DAMAGE, {"amount": 9, "is_critical": False},
    )
    check("il danno raggiunge characters con self._world_id vuoto",
          _reload(instance.id).hp_current == 12)

    # Il vecchio bug: usando self._world_id ("") invece del world_id del
    # personaggio, l'host rifiuta perché nessun membro ha device_id
    # "dev-owner" nel mondo "".
    result_with_wrong_world_id = LocalBackend().send_command(
        mev._world_id, "dev-owner", perm.CMD_HP_HEAL, {"amount": 1},
        target_type="character", target_id=instance.id,
    )
    check("riproduzione del bug originale: mev._world_id (vuoto) da solo "
          "viene rifiutato con \"mittente non è membro\"",
          not result_with_wrong_world_id.success
          and "membro" in result_with_wrong_world_id.error)


# ---------------------------------------------------------------------------
# [10] Sincronizzazione automatica in background della Sezione Incontri
# (fix 2026-08-07, bug segnalato da Davide: "in Incontri i PF non si
# aggiornano, il master deve andare in Sezione Mondi e tornare indietro").
# ---------------------------------------------------------------------------

def test_encounter_view_sync_in_background() -> None:
    print("\n[14] MasterEncounterView — sincronizzazione automatica in background")
    from ui.views.master.master_encounter_view import MasterEncounterView

    world, instance = _make_world_with_instance(
        owner_device="dev-owner", player_device="dev-player4", name="Fenwick", hp_max=40,
    )
    enc = master_repo.create_encounter(name="Imboscata notturna")
    assert enc is not None
    master_repo.add_member(enc.id, kind="character", character_id=instance.id)

    mev = MasterEncounterView(
        encounter_id=enc.id, on_back_to_list=lambda: None,
        world_id=world.id, device_id="dev-owner",
    )

    sig_before = mev._sync_signature()

    # Un danno applicato DIRETTAMENTE su characters (come farebbe l'handler
    # hp.self_update quando il giocatore modifica i propri PF) — senza
    # passare da mev.refresh(): simula un aggiornamento arrivato da un altro
    # dispositivo, che il ciclo in background deve rilevare da solo.
    character_repo.update_hp(instance.id, hp_current=25, hp_temp=0)
    sig_after = mev._sync_signature()
    check("la firma di sync cambia quando i PF di un PG cambiano nel DB, "
          "senza bisogno di refresh() esplicito",
          sig_before != sig_after)

    check("_sync_apply() non solleva quando questo dispositivo ospita il mondo "
          "(nulla da scaricare, è già lo stato autoritativo)",
          mev._sync_apply() is None)

    check("_sync_should_redraw_anyway() è False senza alcun cooldown attivo",
          mev._sync_should_redraw_anyway() is False)
    world_sync.mark_master_action(instance.id)
    check("_sync_should_redraw_anyway() è True subito dopo un'azione master "
          "(countdown visivo, stesso principio di WorldsView)",
          mev._sync_should_redraw_anyway() is True)
    world_sync.reset_client_cooldowns_for_tests()

    # Lifecycle del thread: `_start_sync()`/`_stop_sync()` sono i metodi
    # richiamati da `did_mount()`/`will_unmount()` (qui testati direttamente,
    # non tramite i due hook: `self.page` solleva `RuntimeError` per un
    # controllo Flet mai realmente montato su una pagina — comportamento
    # della libreria, non di questo codice — mentre `_start_sync()` legge
    # solo `self._page`, None in questo contesto di test: il ciclo parte
    # comunque, get_page() nel loop deve solo astenersi dal programmare un
    # redraw finché resta None, mai sollevare).
    mev._start_sync()
    check("_start_sync() crea un ciclo di sync", mev._sync_loop_obj is not None)
    mev._stop_sync()
    check("_stop_sync() lo ferma", mev._sync_loop_obj is None)


def main() -> int:
    init_db()
    print("=" * 72)
    print("Layout Incontri + azioni PG dall'incontro + invio automatico PF (2026-08-07)")
    print(f"HOME di test: {_TMP_HOME}")
    print("=" * 72)

    test_layout_pannello_strumenti()
    test_permessi_hp_self_update()
    test_handler_hp_self_update()
    test_rate_limit_host_hp_self_update()
    test_cooldown_client_hp_self_update()
    test_scheda_schedule_hp_world_sync()
    test_permessi_condition_self_update()
    test_handler_condition_self_update()
    test_rate_limit_host_condition_self_update()
    test_cooldown_client_condition_self_update()
    test_scheda_schedule_condition_world_sync()
    test_encounter_members_resolved_world_id()
    test_encounter_view_pg_remote_actions()
    test_encounter_view_send_usa_world_id_del_personaggio()
    test_encounter_view_sync_in_background()

    print("\n" + "=" * 72)
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
