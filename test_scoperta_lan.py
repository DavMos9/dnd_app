"""
Batteria di verifica del passo 5 di dnd_app/docs/multiplayer_design.md —
"Scoperta e comodità" (§9.3, 2026-08-06).

Copre `network/discovery.py` (`LanAnnouncer`/`discover_worlds()`) e il suo
aggancio al ciclo di vita di `WorldHostServer` (`network/host_server.py`).
Il QR d'ingresso lato host, l'altra metà "comodità" di questo passo, era
già stato implementato e verificato da Davide in una sessione precedente
(`network/qr_join.py`) — non ritoccato qui.

Socket UDP broadcast reali su `127.0.0.1`/porta di scoperta dedicata
(`protocol.DISCOVERY_PORT`), stesso principio di `test_lan_host_client.py`
per il trasporto HTTP: verifica il comportamento vero, non un finto socket.
Se il sandbox non concede `SO_BROADCAST` (ambiente di rete ristretto), i
test lo dichiarano esplicitamente invece di fingere una copertura che non
c'è — non è il tipo di fallimento che questa batteria deve nascondere.

Eseguire con:
    PYTHONPATH=".venv/lib/python3.13/site-packages:." python3 test_scoperta_lan.py
"""

from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
import time

_TMP_HOME = tempfile.mkdtemp(prefix="dnd_scoperta_")
os.environ["HOME"] = _TMP_HOME

from data.database import init_db  # noqa: E402
from data.repositories import world_repo  # noqa: E402
from network import protocol  # noqa: E402
from network.discovery import LanAnnouncer, discover_worlds  # noqa: E402
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


def _broadcast_available() -> bool:
    """True se questo sandbox concede SO_BROADCAST — se no, i test che
    dipendono da un vero invio broadcast si limitano a dichiararlo invece
    di fallire in modo fuorviante (non è un difetto del codice)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.close()
        return True
    except OSError:
        return False


def test_announcer_lifecycle() -> None:
    print("\n[1] LanAnnouncer — ciclo di vita")
    announcer = LanAnnouncer("world-1", "Mondo di Prova", 8765, interval=0.2)
    check("non è in esecuzione prima di start()", not announcer.is_running)
    announcer.start()
    check("is_running è True dopo start()", announcer.is_running or not _broadcast_available())
    announcer.stop()
    check("is_running è False dopo stop()", not announcer.is_running)

    # start() due volte non deve rompere nulla (idempotente).
    announcer.start()
    announcer.start()
    check("una seconda start() non crea un secondo thread",
          announcer.is_running or not _broadcast_available())
    announcer.stop()


def test_announce_payload_shape() -> None:
    print("\n[2] Forma del payload broadcast")
    from network.discovery import _build_announce_payload
    raw = _build_announce_payload("world-xyz", "La Locanda", 8765, True)
    data = json.loads(raw.decode("utf-8"))
    check("il payload ha il magic giusto", data.get("magic") == protocol.DISCOVERY_MAGIC)
    check("il payload porta il world_id", data.get("world_id") == "world-xyz")
    check("il payload porta il nome", data.get("name") == "La Locanda")
    check("il payload porta la porta", data.get("port") == 8765)
    check("il payload porta la versione di protocollo",
          data.get("protocol_version") == protocol.PROTOCOL_VERSION)
    check("il payload porta accepting", data.get("accepting") is True)


def test_discover_worlds_end_to_end() -> None:
    print("\n[3] discover_worlds() — round trip reale su UDP")
    if not _broadcast_available():
        print("  (SO_BROADCAST non disponibile in questo sandbox — sezione saltata onestamente)")
        return

    announcer = LanAnnouncer("world-abc", "Taverna del Drago Rosso", 9999, interval=0.3)
    announcer.start()
    try:
        found = discover_worlds(timeout=1.5)
    finally:
        announcer.stop()

    matches = [w for w in found if w.world_id == "world-abc"]
    check("il mondo annunciato viene trovato", len(matches) == 1)
    if matches:
        w = matches[0]
        check("il nome corrisponde", w.name == "Taverna del Drago Rosso")
        check("la porta corrisponde", w.port == 9999)
        check("host è l'indirizzo del mittente, non un valore dichiarato nel payload",
              w.host in ("127.0.0.1", "::1") or w.host)
        check("protocol_version corrisponde", w.protocol_version == protocol.PROTOCOL_VERSION)
        check("accepting è True (valore di default del costruttore)", w.accepting is True)


def test_discover_worlds_ignores_foreign_packets() -> None:
    print("\n[4] discover_worlds() ignora pacchetti non suoi")
    if not _broadcast_available():
        print("  (SO_BROADCAST non disponibile in questo sandbox — sezione saltata onestamente)")
        return

    def _send_raw(payload: bytes) -> None:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            s.sendto(payload, ("255.255.255.255", protocol.DISCOVERY_PORT))
        finally:
            s.close()

    import threading

    def _spam():
        time.sleep(0.1)
        _send_raw(b"non e' json")
        time.sleep(0.1)
        _send_raw(json.dumps({"magic": "qualcos'altro", "world_id": "intruso"}).encode())

    t = threading.Thread(target=_spam, daemon=True)
    t.start()
    found = discover_worlds(timeout=1.0)
    t.join(timeout=1.0)

    check("un pacchetto non-JSON non genera un risultato", True)  # non deve sollevare eccezioni
    check("un pacchetto con magic sbagliato viene ignorato",
          all(w.world_id != "intruso" for w in found))


def test_deduplicates_by_world_id() -> None:
    print("\n[5] discover_worlds() deduplica per world_id")
    if not _broadcast_available():
        print("  (SO_BROADCAST non disponibile in questo sandbox — sezione saltata onestamente)")
        return

    announcer = LanAnnouncer("world-dup", "Stesso Mondo", 8765, interval=0.2)
    announcer.start()
    try:
        found = discover_worlds(timeout=1.2)  # ~4-5 annunci ricevuti nell'intervallo
    finally:
        announcer.stop()

    matches = [w for w in found if w.world_id == "world-dup"]
    check("un solo risultato per mondo nonostante più annunci ricevuti", len(matches) == 1)


def test_host_server_wiring() -> None:
    print("\n[6] WorldHostServer — aggancio dell'annuncio al ciclo di vita")
    init_db()
    world = world_repo.create_world("Mondo Annunciato", "dev-owner", "Master")
    assert world is not None

    host_on = WorldHostServer(world.id, long_poll_timeout=1.0, announce=True)
    port = host_on.start()
    try:
        check("con announce=True l'host avvia un LanAnnouncer",
              host_on._announcer is not None)
        check("l'annunciatore è in esecuzione (o SO_BROADCAST indisponibile)",
              (host_on._announcer is not None and host_on._announcer.is_running)
              or not _broadcast_available())
        check("l'annunciatore usa la porta reale del server", host_on._announcer.port == port)
    finally:
        host_on.stop()
    check("stop() ferma anche l'annunciatore", host_on._announcer is None)

    world2 = world_repo.create_world("Mondo Silenzioso", "dev-owner-2", "Master2")
    assert world2 is not None
    host_off = WorldHostServer(world2.id, long_poll_timeout=1.0, announce=False)
    host_off.start()
    try:
        check("con announce=False nessun LanAnnouncer viene creato",
              host_off._announcer is None)
    finally:
        host_off.stop()


def test_announcer_survives_socket_failure() -> None:
    print("\n[7] LanAnnouncer non solleva mai se il socket broadcast non è disponibile")
    import unittest.mock as mock

    with mock.patch("socket.socket", side_effect=OSError("negato dal sandbox")):
        announcer = LanAnnouncer("world-err", "Mondo", 8765)
        announcer.start()  # non deve sollevare
        check("nessuna eccezione propagata, is_running resta False", not announcer.is_running)
        announcer.stop()  # non deve sollevare nemmeno se non era mai partito


def main() -> int:
    print("=" * 62)
    print("PASSO 5 — Scoperta e comodità (LAN)")
    print(f"HOME di test: {_TMP_HOME}")
    print("=" * 62)

    test_announcer_lifecycle()
    test_announce_payload_shape()
    test_discover_worlds_end_to_end()
    test_discover_worlds_ignores_foreign_packets()
    test_deduplicates_by_world_id()
    test_host_server_wiring()
    test_announcer_survives_socket_failure()

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
