"""
Batteria di verifica del passo 9 di dnd_app/docs/multiplayer_design.md —
"Robustezza": correzione di due bug reali trovati durante la revisione del
piano (non nel documento di progettazione originale) più la verifica lato
host della versione di protocollo (§11.6).

[1] `get_events_since(limit=None)` — nessun limite implicito, e
    `WorldHostServer.handle_snapshot()` lo usa: un mondo con più di 200
    eventi nella sua storia non produce più uno snapshot troncato per chi
    entra ora (prima, `limit=200` veniva ereditato in silenzio).

[2] Verifica lato HOST della versione di protocollo (§11.6) su `/join` e su
    `/command` — prima esisteva solo lato client
    (`core.world_sync.start_lan_join`), quindi un client che saltasse
    `GET /world` (o una versione modificata) poteva comunque entrare.

Stesso schema del resto del progetto: DB condiviso in un solo processo
(vedi il docstring di `test_lan_host_client.py` per il perché — scambiare
`HOME` a runtime per simulare due dispositivi introdurrebbe una corsa reale
tra il thread del server e quello di test).

Eseguire con:
    PYTHONPATH=".venv/lib/python3.13/site-packages:." python3 test_robustezza_rete.py
"""

from __future__ import annotations

import os
import sys
import tempfile

_TMP_HOME = tempfile.mkdtemp(prefix="dnd_robustezza_")
os.environ["HOME"] = _TMP_HOME

from data.database import init_db  # noqa: E402
from data.repositories import world_repo  # noqa: E402
from core.world_backend import RemoteBackend  # noqa: E402
from network import protocol  # noqa: E402
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


def test_snapshot_non_troncato() -> None:
    print("\n[1] Snapshot non più troncato oltre 200 eventi")

    world = world_repo.create_world("Mondo Grande", "dev-owner", "Il Master")
    assert world is not None

    # world.created conta già come evento #1 — ne servono altri 250+ per
    # superare il vecchio limite implicito di 200.
    for i in range(250):
        world_repo.append_event(
            world.id, "dev-owner", "Il Master", kind="xp.grant",
            target_type="character", target_id=f"fake-{i}",
            summary=f"Evento di prova {i}", payload="{}",
        )

    total_in_db = len(world_repo.get_events_since(world.id, 0, limit=None))
    check("il mondo ha davvero più di 200 eventi nella sua storia", total_in_db > 200)

    capped = world_repo.get_events_since(world.id, 0)  # default limit=200
    check("get_events_since senza limit esplicito resta a 200 (comportamento invariato per il polling incrementale)",
          len(capped) == 200)

    uncapped = world_repo.get_events_since(world.id, 0, limit=None)
    check("get_events_since(limit=None) ritorna TUTTI gli eventi",
          len(uncapped) == total_in_db)

    host = WorldHostServer(world.id, long_poll_timeout=2.0, announce=False)
    port = host.start()
    try:
        client = RemoteBackend("127.0.0.1", port, "dev-owner", world_id=world.id)
        outcome = client.join(world.join_code, host.pin, "Il Master")
        check("il master (già membro) entra subito, approvato", outcome.status == "approved")

        snapshot = client.get_snapshot()
        check("/snapshot risponde", snapshot is not None)
        events = snapshot.get("events", []) if snapshot else []
        check("/snapshot porta l'INTERO giornale, non troncato a 200",
              len(events) == total_in_db)
    finally:
        host.stop()


def test_versione_protocollo_join() -> None:
    print("\n[2] Verifica versione di protocollo lato host — /join")

    world = world_repo.create_world("Mondo Versioni", "dev-owner-2", "Master 2")
    assert world is not None
    host = WorldHostServer(world.id, long_poll_timeout=1.0, announce=False)
    port = host.start()
    try:
        # Corpo grezzo con versione sbagliata — bypassa RemoteBackend di
        # proposito, per verificare il controllo lato host indipendentemente
        # da cosa manda un client "onesto".
        status, data = host.handle_join({
            "join_code": world.join_code, "pin": host.pin,
            "device_id": "dev-player-vecchio", "display_name": "Vecchio",
            "protocol_version": protocol.PROTOCOL_VERSION - 1,
        })
        check("versione sbagliata: l'host rifiuta con un errore leggibile",
              status == 400 and "error" in data and "rotocollo" in data["error"])
        check("nessun membro creato per il tentativo rifiutato",
              world_repo.get_member(world.id, "dev-player-vecchio") is None)

        status, data = host.handle_join({
            "join_code": world.join_code, "pin": host.pin,
            "device_id": "dev-player-senza-versione", "display_name": "Senza versione",
        })
        check("versione assente: rifiutata allo stesso modo (fail-closed, non un default permissivo)",
              status == 400 and "error" in data)

        # Un client vero (RemoteBackend, patchato per mandare la versione)
        # entra regolarmente.
        client = RemoteBackend("127.0.0.1", port, "dev-player-nuovo", world_id=world.id)
        outcome = client.join(world.join_code, host.pin, "Nuovo")
        check("un client con la versione giusta (RemoteBackend reale) ottiene status pending/approved, non un rifiuto",
              outcome.status in ("pending", "approved"))
    finally:
        host.stop()


def test_versione_protocollo_command() -> None:
    print("\n[3] Verifica versione di protocollo lato host — /command (difesa in profondità)")

    world = world_repo.create_world("Mondo Versioni Comando", "dev-owner-3", "Master 3")
    assert world is not None
    host = WorldHostServer(world.id, long_poll_timeout=1.0, announce=False)
    port = host.start()
    try:
        client = RemoteBackend("127.0.0.1", port, "dev-owner-3", world_id=world.id)
        outcome = client.join(world.join_code, host.pin, "Master 3")
        check("il proprietario entra ed ottiene un token", outcome.status == "approved" and client.token)

        # Comando con la versione giusta (RemoteBackend reale) — deve
        # arrivare fino alla validazione del comando stesso (qui rifiutato
        # per un motivo di dominio, "kind" inventato — non per la versione).
        result = client.send_command(world.id, "dev-owner-3", "kind.inventato", {})
        check("con la versione giusta il rifiuto è di dominio (comando sconosciuto), non di protocollo",
              not result.success and "rotocollo" not in (result.error or ""))

        # Corpo grezzo con token valido ma versione sbagliata — bypassa
        # RemoteBackend apposta.
        status, data = host.handle_command(client.token, {
            "kind": "xp.grant", "payload": {}, "target_type": "", "target_id": "",
            "protocol_version": protocol.PROTOCOL_VERSION - 1,
        })
        check("un token valido con versione sbagliata viene comunque rifiutato",
              status == 400 and "rotocollo" in data.get("error", ""))
    finally:
        host.stop()


def main() -> int:
    print("=" * 62)
    print("PASSO 9 — Robustezza: snapshot completo + versione protocollo")
    print(f"HOME di test: {_TMP_HOME}")
    print("=" * 62)
    init_db()
    test_snapshot_non_troncato()
    test_versione_protocollo_join()
    test_versione_protocollo_command()
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
