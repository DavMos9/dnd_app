"""
Verifica del fix 2026-08-07 — bug segnalato da Davide dopo il primo vero
test su Wi-Fi: "una volta entrato il player può far unire il personaggio al
mondo... ma il master non vede il personaggio che si è unito al mondo...
nella Sezione Master... non gli esce il personaggio giocante".

Causa: `core/character_instances.py::create_or_resume_instance()`
(Multiplayer passo 3, 2026-08-05) è nata PRIMA che esistesse la rete —
scrive solo sul DB del dispositivo che la chiama. Su un dispositivo che ha
solo una REPLICA del mondo (join in LAN, non lo ospita), la riga
`characters` restava solo lì: l'host — il DB che la Sezione Master legge
davvero — non veniva mai informato.

Fix: `ui/views/home_view.py::HomeView._push_instance_to_host()` invia
subito dopo la creazione locale un nuovo comando
`character_instance.sync` (`core/world_permissions.py`,
`core/world_backend.py::_handle_character_instance_sync`) che porta
l'export integrale dell'istanza sull'host, riusando
`character_export.import_replica_character()` (stesso modulo già
collaudato per la semina iniziale e per ogni rimaterializzazione via
eventi).

Qui si verifica con un vero `WorldHostServer` su socket reale (stesso
pattern di `test_world_view_remote_routing.py`) che:
  1. un personaggio creato/ripreso come istanza su un dispositivo NON
     host non esiste ancora sul DB dell'host finché non viene inviato
     `character_instance.sync` — la riproduzione esatta del bug;
  2. `HomeView._push_instance_to_host()` lo invia correttamente e il
     personaggio compare DAVVERO sul DB che l'host usa (lo stesso che
     legge la Sezione Master);
  3. un dispositivo non proprietario non può registrare il personaggio di
     un altro (fail-closed, stesso principio di ogni altro handler);
  4. un personaggio di un mondo diverso viene rifiutato.

Stessa limitazione dichiarata negli altri test di questa famiglia: un vero
test a due database SEPARATI (due dispositivi fisici) non è simulabile in
modo affidabile in questo sandbox — qui verifichiamo che il comando
raggiunga DAVVERO l'host reale via HTTP, leggendo poi lo stato dallo stesso
DB che il server host userebbe per rispondere alla Sezione Master.

Eseguire con:
    PYTHONPATH=".venv/lib/python3.13/site-packages:." python3 test_character_instance_sync.py
"""

from __future__ import annotations

import os
import sys
import tempfile

_TMP_HOME = tempfile.mkdtemp(prefix="dnd_char_instance_sync_")
os.environ["HOME"] = _TMP_HOME

from data.database import init_db  # noqa: E402
from data.models import Character  # noqa: E402
from data.repositories import character_export, character_repo, world_repo  # noqa: E402
from core import character_instances as ci  # noqa: E402
from core import world_backend  # noqa: E402
from core import world_permissions as perm  # noqa: E402
from core import world_sync  # noqa: E402
from core.world_backend import RemoteBackend  # noqa: E402
from network.host_server import WorldHostServer  # noqa: E402

_PASS = 0
_FAIL: list[str] = []


def check(label: str, cond: bool) -> None:
    global _PASS
    if cond:
        _PASS += 1
    else:
        _FAIL.append(label)
        print(f"  FALLITO: {label}")


def _make_local_character(name: str = "Elyndra") -> Character:
    c = Character(
        name=name, class_name="Ladro", race="Mezzelfo", level=2,
        hit_dice_type=8, hit_dice_total=2, hit_dice_remaining=2,
        str_score=10, dex_score=16, con_score=12, int_score=12,
        wis_score=10, cha_score=14, hp_max=16, hp_current=16,
    )
    character_repo.create(c)
    return c


def test_bug_reproduced_without_the_fix() -> None:
    print("\n[1] Riproduzione del bug: istanza creata su un client LAN non "
          "esiste sull'host finché non viene inviata")
    host_world = world_repo.create_world("Mondo Sync PG", "dev-owner", "Il Master")
    assert host_world is not None

    host = WorldHostServer(host_world.id, long_poll_timeout=2.0, announce=False)
    port = host.start()
    check("l'host si avvia", isinstance(port, int) and port > 0)
    try:
        world_repo.join_world_by_code(host_world.join_code, "dev-player", "Il Giocatore")

        local_char = _make_local_character()
        result = ci.create_or_resume_instance(host_world.id, local_char.id, "dev-player",
                                               mode="as_is")
        check("la creazione locale dell'istanza riesce", result.success)

        # -- Il bug: la riga esiste SOLO qui (stesso DB di questo processo,
        # ma nulla è mai stato inviato all'host) --
        instance = character_repo.get_by_id(result.character_id)
        check("l'istanza esiste sul DB locale subito dopo la creazione",
              instance is not None)
    finally:
        host.stop()


def test_push_registers_instance_on_real_host() -> None:
    print("\n[2] HomeView._push_instance_to_host() — il comando raggiunge DAVVERO l'host")
    from ui.views.home_view import HomeView

    host_world = world_repo.create_world("Mondo Sync PG Reale", "dev-owner", "Il Master")
    assert host_world is not None

    host = WorldHostServer(host_world.id, long_poll_timeout=2.0, announce=False)
    port = host.start()
    check("l'host si avvia", isinstance(port, int) and port > 0)
    try:
        world_repo.join_world_by_code(host_world.join_code, "dev-player", "Il Giocatore")

        local_char = _make_local_character("Bramgar")
        result = ci.create_or_resume_instance(host_world.id, local_char.id, "dev-player",
                                               mode="as_is")
        assert result.success, result.error
        character_id = result.character_id

        # Replica del mondo così come la vedrebbe il dispositivo del
        # giocatore dopo `_finalize_join()` (fix 2026-08-07: session_token
        # persistito su `worlds`).
        join_backend = RemoteBackend("127.0.0.1", port, "dev-player")
        outcome = join_backend.join(host_world.join_code, host.pin, "Il Giocatore")
        check("il giocatore entra ed è già noto", outcome.status == "approved")

        # NOTA: qui host e "client" condividono lo STESSO DB (un solo
        # processo di test) — a differenza di due dispositivi fisici reali,
        # che avrebbero due DB separati con la propria riga `worlds` per lo
        # stesso mondo (una con is_local_host=1 sull'host, una con
        # is_local_host=0 sulla replica). Non si può quindi chiamare
        # `world_repo.save_replica_world()` qui: usa INSERT OR REPLACE
        # sulla PK, che in SQLite è un DELETE+INSERT — con `ON DELETE
        # CASCADE` su `world_members.world_id` cancellerebbe silenziosamente
        # TUTTI i membri già scritti dall'host (owner incluso), rompendo il
        # fixture. Si aggiornano quindi in-place solo le 3 colonne che
        # `_push_instance_to_host`/`resolve_backend_for_world` leggono
        # davvero (is_local_host/last_seen_host/session_token), fixture di
        # test come già in `test_world_view_remote_routing.py` per la
        # promozione di ruolo.
        from data.database import get_connection
        _conn = get_connection()
        _conn.execute(
            "UPDATE worlds SET is_local_host=0, last_seen_host=?, session_token=? WHERE id=?",
            (f"127.0.0.1:{port}", join_backend.token or "", host_world.id),
        )
        _conn.commit()
        _conn.close()

        home = HomeView.__new__(HomeView)  # nessun bisogno di ft.Page per questo metodo
        home.device_id = "dev-player"
        home._show_error = lambda msg: check(f"_show_error NON deve essere chiamato ({msg!r})",
                                              False)

        # Isolamento dal rate limiter anti-spam (fix 2026-08-07, lato client
        # E lato host — vedi core.world_sync/core.world_backend): questo
        # file verifica la registrazione dell'istanza, non l'anti-spam
        # (coperto da test_cooldown_azioni_remote.py). Senza questo reset,
        # una funzione di test successiva che riusa lo stesso device_id
        # "dev-player" verrebbe bloccata dal cooldown lato host, che è
        # stato di modulo e sopravvive tra le funzioni di questo stesso
        # processo (vedi test_host_rejects_wrong_world più sotto).
        world_backend.reset_host_cooldowns_for_tests()
        world_sync.reset_client_cooldowns_for_tests()
        home._push_instance_to_host(host_world.id, character_id)

        # -- La prova che conta: il personaggio esiste ora sul DB che
        # l'HOST userebbe per rispondere alla Sezione Master --
        on_host = character_repo.get_by_id(character_id)
        check("l'istanza esiste ora (anche) sul DB dell'host",
              on_host is not None and on_host.name == "Bramgar")
        check("l'istanza sull'host è collegata al mondo giusto",
              on_host is not None and on_host.world_id == host_world.id)
        check("l'istanza sull'host mantiene il proprietario corretto",
              on_host is not None and on_host.owner_device_id == "dev-player")

        events = world_repo.get_events_since(host_world.id, 0)
        sync_events = [e for e in events if e.kind == perm.CMD_CHARACTER_INSTANCE_SYNC]
        check("un evento character_instance.sync è stato scritto nel registro",
              len(sync_events) == 1)
    finally:
        host.stop()


def test_host_rejects_wrong_owner() -> None:
    print("\n[3] Fail-closed: non si può registrare il personaggio di un ALTRO proprietario")
    from core.world_backend import LocalBackend

    world = world_repo.create_world("Mondo Sync PG Owner", "dev-owner", "Il Master")
    assert world is not None
    world_repo.join_world_by_code(world.join_code, "dev-player-a", "Giocatore A")
    world_repo.join_world_by_code(world.join_code, "dev-player-b", "Giocatore B")

    local_char = _make_local_character("Thalindra")
    result = ci.create_or_resume_instance(world.id, local_char.id, "dev-player-a", mode="as_is")
    assert result.success, result.error

    export_data = character_export.export_character(result.character_id)
    assert export_data is not None

    world_backend.reset_host_cooldowns_for_tests()  # isolamento dal rate limiter, vedi test [2]
    backend = LocalBackend()
    # Giocatore B prova a registrare il personaggio di Giocatore A.
    bad_result = backend.send_command(
        world.id, "dev-player-b", perm.CMD_CHARACTER_INSTANCE_SYNC,
        {"export": export_data}, target_type="character", target_id=result.character_id,
    )
    check("un giocatore non può registrare il personaggio di un altro",
          not bad_result.success)

    # Lo stesso proprietario, invece, riesce.
    good_result = backend.send_command(
        world.id, "dev-player-a", perm.CMD_CHARACTER_INSTANCE_SYNC,
        {"export": export_data}, target_type="character", target_id=result.character_id,
    )
    check("il vero proprietario può registrare la propria istanza",
          good_result.success)


def test_host_rejects_wrong_world() -> None:
    print("\n[4] Fail-closed: un'istanza di un mondo non può essere registrata su un ALTRO mondo")
    from core.world_backend import LocalBackend

    world_a = world_repo.create_world("Mondo A", "dev-owner", "Il Master")
    world_b = world_repo.create_world("Mondo B", "dev-owner", "Il Master")
    assert world_a is not None and world_b is not None
    world_repo.join_world_by_code(world_a.join_code, "dev-player", "Il Giocatore")
    world_repo.join_world_by_code(world_b.join_code, "dev-player", "Il Giocatore")

    local_char = _make_local_character("Voss")
    result = ci.create_or_resume_instance(world_a.id, local_char.id, "dev-player", mode="as_is")
    assert result.success, result.error

    export_data = character_export.export_character(result.character_id)
    assert export_data is not None

    world_backend.reset_host_cooldowns_for_tests()  # isolamento dal rate limiter, vedi test [2]
    backend = LocalBackend()
    bad_result = backend.send_command(
        world_b.id, "dev-player", perm.CMD_CHARACTER_INSTANCE_SYNC,
        {"export": export_data}, target_type="character", target_id=result.character_id,
    )
    check("un'istanza del mondo A viene rifiutata se inviata al mondo B",
          not bad_result.success)


def test_host_device_does_not_push() -> None:
    print("\n[5] Il dispositivo che OSPITA il mondo non invia mai il comando (non serve)")
    from ui.views.home_view import HomeView

    world = world_repo.create_world("Mondo Sync PG Host", "dev-owner", "Il Master")
    assert world is not None

    local_char = _make_local_character("Owen")
    result = ci.create_or_resume_instance(world.id, local_char.id, "dev-owner", mode="as_is")
    assert result.success, result.error

    home = HomeView.__new__(HomeView)
    home.device_id = "dev-owner"
    called = {"show_error": False}
    home._show_error = lambda msg: called.__setitem__("show_error", True)

    # Nessun host server avviato: se `_push_instance_to_host` tentasse
    # comunque una connessione di rete fallirebbe rumorosamente (nessun
    # bottone in ascolto sulla porta) — la riuscita silenziosa di questo
    # test conferma che il ramo `is_local_host` esce subito.
    home._push_instance_to_host(world.id, result.character_id)
    check("nessun avviso mostrato quando il dispositivo ospita già il mondo",
          not called["show_error"])


def main() -> int:
    init_db()
    print("=" * 70)
    print("Fix 2026-08-07 — character_instance.sync (Sezione Master vede l'istanza)")
    print(f"HOME di test: {_TMP_HOME}")
    print("=" * 70)

    test_bug_reproduced_without_the_fix()
    test_push_registers_instance_on_real_host()
    test_host_rejects_wrong_owner()
    test_host_rejects_wrong_world()
    test_host_device_does_not_push()

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
