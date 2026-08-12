"""
Batteria di verifica del passo 7B di dnd_app/docs/multiplayer_design.md —
"Condivisione delle note" (§6.2).

Quattro parti:

[1] L'handler `CMD_NOTE_SHARE` (`core/world_backend.py`): validazione,
    creazione/aggiornamento tramite la pipeline comando → evento (mai una
    scrittura diretta), evento nel registro.

[2] Applicazione dell'evento sulla replica (`core/world_sync.py::
    apply_event_to_replica`) in isolamento puro — nessun server vivo,
    stesso principio di `test_lan_host_client.py` parte [2].

[3] Le note `private` non compaiono mai in `get_notes_visible_to()`, per
    nessun device.

[4] Guardia di regressione: un evento di kind sconosciuto non fa mai
    sollevare `apply_event_to_replica` (utile anche per i rami aggiunti nei
    prossimi passi, 7C/8/9).

[5] Il bug di correttezza trovato in fase di revisione del piano — una nota
    condivisa PRIMA che un giocatore entrasse nel mondo deve comunque
    arrivargli: `WorldHostServer.handle_snapshot()` la include, e
    `core.world_sync._finalize_join()` la materializza.

Un solo DB per processo (`LocalBackend` parla col proprio DB, come nel
deploy web e come fa l'host reale in LAN — stesso principio di
`test_master_remote_actions.py`).

Eseguire con:
    PYTHONPATH=".venv/lib/python3.13/site-packages:." python3 test_note_sharing.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

_TMP_HOME = tempfile.mkdtemp(prefix="dnd_note_sharing_")
os.environ["HOME"] = _TMP_HOME

from data.database import init_db  # noqa: E402
from data.models import WorldEvent  # noqa: E402
from data.repositories import master_repo, world_repo  # noqa: E402
from core import world_backend  # noqa: E402
from core import world_permissions as perm  # noqa: E402
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
    world_backend.reset_host_cooldowns_for_tests()
    return backend.send_command(*args, **kwargs)


def _make_world(owner="dev-owner", players=("dev-player-1", "dev-player-2")):
    world = world_repo.create_world("Mondo delle Note", owner, "Il Master")
    assert world is not None
    for i, device in enumerate(players):
        world_repo.join_world_by_code(world.join_code, device, f"Giocatore {i + 1}")
    return world


# ---------------------------------------------------------------------------
# [1] Handler CMD_NOTE_SHARE
# ---------------------------------------------------------------------------

def test_handler_note_share() -> None:
    print("\n[1] Handler CMD_NOTE_SHARE — validazione, creazione, evento")

    world = _make_world()
    backend = LocalBackend()

    result = _send(backend, world.id, "dev-owner", perm.CMD_NOTE_SHARE, {
        "category": "npc", "name": "Il Vecchio Saggio", "description": "Sa più di quanto dice.",
        "visibility": "non-valida",
    })
    check("visibilità non valida: rifiutato", not result.success)

    result = _send(backend, world.id, "dev-owner", perm.CMD_NOTE_SHARE, {
        "category": "secret", "name": "Il tradimento del duca",
        "description": "Solo il ladro lo sa, per ora.",
        "visibility": "selected", "visible_to_device_ids": ["dev-player-1"],
    })
    check("visibilità 'selected' valida: riuscito", result.success)
    check("produce un evento", result.event is not None)
    check("l'evento ha kind note.share", result.event.kind == perm.CMD_NOTE_SHARE)
    check("l'evento è target_type=note", result.event.target_type == "note")

    note_id = result.event.target_id
    note = master_repo.get_master_campaign_note_by_id(note_id)
    check("la nota esiste davvero sull'host", note is not None)
    check("con la visibilità corretta", note is not None and note.visibility == "selected")
    check("con world_id impostato", note is not None and note.world_id == world.id)

    # Player non autorizzato al comando (solo master/owner)
    result = _send(backend, world.id, "dev-player-1", perm.CMD_NOTE_SHARE, {
        "category": "npc", "name": "Tentativo non autorizzato", "visibility": "all",
    })
    check("un giocatore non può condividere una nota", not result.success)

    # Aggiornamento (note_id presente) — cambia visibilità a 'all'
    result = _send(backend, world.id, "dev-owner", perm.CMD_NOTE_SHARE, {
        "note_id": note_id, "category": "secret", "name": "Il tradimento del duca",
        "description": "Ormai lo sanno tutti.", "visibility": "all",
    })
    check("aggiornamento riuscito", result.success)
    note = master_repo.get_master_campaign_note_by_id(note_id)
    check("visibilità aggiornata ad 'all'", note is not None and note.visibility == "all")
    check("descrizione aggiornata", note is not None and "sanno tutti" in note.description)

    # Aggiornamento di una nota inesistente
    result = _send(backend, world.id, "dev-owner", perm.CMD_NOTE_SHARE, {
        "note_id": "id-inesistente", "name": "x", "visibility": "all",
    })
    check("aggiornare una nota inesistente fallisce", not result.success)


# ---------------------------------------------------------------------------
# [2] Applicazione sulla replica
# ---------------------------------------------------------------------------

def test_replica_materializza_nota() -> None:
    print("\n[2] apply_event_to_replica — materializza la nota sulla replica")

    world = _make_world(owner="dev-owner-2", players=("dev-player-a", "dev-player-b"))
    backend = LocalBackend()

    result = _send(backend, world.id, "dev-owner-2", perm.CMD_NOTE_SHARE, {
        "category": "quest", "name": "Il Sigillo Spezzato", "description": "Solo per pochi.",
        "visibility": "selected", "visible_to_device_ids": ["dev-player-a"],
    })
    check("condivisione riuscita", result.success)
    event = result.event
    assert event is not None

    # Simula l'applicazione sulla replica di un SECONDO device (stesso DB
    # in questo test, per lo stesso motivo di test_lan_host_client.py parte
    # [2] — apply_event_to_replica non fa mai I/O di rete, solo scritture
    # locali, quindi è legittimo isolarlo così).
    world_sync.apply_event_to_replica(world.id, event)

    visible_a = master_repo.get_notes_visible_to(world.id, "dev-player-a")
    visible_b = master_repo.get_notes_visible_to(world.id, "dev-player-b")
    check("il device incluso in visible_to_device_ids vede la nota",
          any(n.name == "Il Sigillo Spezzato" for n in visible_a))
    check("il device escluso NON la vede", not any(n.name == "Il Sigillo Spezzato" for n in visible_b))


def test_note_private_mai_visibile() -> None:
    print("\n[3] Le note 'private' non compaiono mai per nessun device")

    world = _make_world(owner="dev-owner-3", players=("dev-player-x",))
    backend = LocalBackend()

    result = _send(backend, world.id, "dev-owner-3", perm.CMD_NOTE_SHARE, {
        "category": "secret", "name": "Segreto del Master", "visibility": "private",
    })
    check("condivisione con visibility=private riuscita (l'handler non la vieta)", result.success)

    visible = master_repo.get_notes_visible_to(world.id, "dev-player-x")
    check("una nota private non torna mai da get_notes_visible_to",
          not any(n.name == "Segreto del Master" for n in visible))
    visible_owner = master_repo.get_notes_visible_to(world.id, "dev-owner-3")
    check("nemmeno per l'owner/master stesso (quella vista è solo per i giocatori — "
          "il master usa get_master_campaign_notes)",
          not any(n.name == "Segreto del Master" for n in visible_owner))


def test_evento_sconosciuto_non_solleva() -> None:
    print("\n[4] Un evento di kind sconosciuto non solleva mai eccezioni")

    world = _make_world(owner="dev-owner-4", players=())
    fake_event = WorldEvent(
        seq=999, id="fake-event", world_id=world.id,
        actor_device_id="dev-owner-4", actor_name="Il Master",
        kind="qualche.evento.futuro.sconosciuto", target_type="", target_id="",
        summary="", payload="{}", before_state="{}", created_at="2026-01-01T00:00:00",
    )
    try:
        world_sync.apply_event_to_replica(world.id, fake_event)
        check("nessuna eccezione propagata per un kind sconosciuto", True)
    except Exception as e:
        check(f"nessuna eccezione propagata per un kind sconosciuto (sollevata: {e})", False)


# ---------------------------------------------------------------------------
# [5] Bug di correttezza: nota condivisa PRIMA dell'ingresso di un giocatore
# ---------------------------------------------------------------------------

def test_nota_arriva_a_chi_entra_dopo() -> None:
    print("\n[5] Una nota condivisa prima dell'ingresso arriva comunque al nuovo membro")

    from network.host_server import WorldHostServer
    from core.world_backend import RemoteBackend

    world = world_repo.create_world("Mondo Tardivo", "dev-owner-5", "Il Master")
    assert world is not None
    backend = LocalBackend()

    # La nota viene condivisa PRIMA che il giocatore entri nel mondo.
    result = _send(backend, world.id, "dev-owner-5", perm.CMD_NOTE_SHARE, {
        "category": "place", "name": "La Torre Sommersa", "description": "Vista da lontano.",
        "visibility": "all",
    })
    check("condivisione (pre-ingresso) riuscita", result.success)

    host = WorldHostServer(world.id, backend=backend, long_poll_timeout=2.0, announce=False)
    port = host.start()
    try:
        client = RemoteBackend("127.0.0.1", port, "dev-player-tardivo", world_id=world.id)
        outcome = client.join(world.join_code, host.pin, "Arrivato Dopo")
        check("il nuovo giocatore entra (nuovo device: pending, poi va approvato)",
              outcome.status == "pending")
        req_id = outcome.request_id
        pending = host.list_pending()
        check("la richiesta è in coda", any(r.id == req_id for r in pending))
        host.approve(req_id)

        join_outcome = client.poll_join_status(req_id)
        check("dopo l'approvazione, lo stato è 'approved' con un token",
              join_outcome.status == "approved" and bool(client.token))

        finalize_result = world_sync._finalize_join(client, f"127.0.0.1:{port}")
        check("_finalize_join riesce", finalize_result.success)

        visible = master_repo.get_notes_visible_to(world.id, "dev-player-tardivo")
        check("la nota condivisa PRIMA dell'ingresso è comunque visibile dopo _finalize_join "
              "(bug di correttezza corretto nel passo 9/7B)",
              any(n.name == "La Torre Sommersa" for n in visible))
    finally:
        host.stop()


def main() -> int:
    print("=" * 62)
    print("PASSO 7B — Condivisione delle note (§6.2)")
    print(f"HOME di test: {_TMP_HOME}")
    print("=" * 62)
    init_db()
    test_handler_note_share()
    test_replica_materializza_nota()
    test_note_private_mai_visibile()
    test_evento_sconosciuto_non_solleva()
    test_nota_arriva_a_chi_entra_dopo()
    print("\n" + "=" * 62)
    print(f"Controlli passati: {_PASS} — falliti: {len(_FAIL)}")
    if _FAIL:
        for f in _FAIL:
            print(f"  - {f}")
        return 1
    print("Tutti i controlli passati.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
