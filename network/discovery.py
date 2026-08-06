"""
Scoperta automatica dei mondi in LAN — passo 5 di
`dnd_app/docs/multiplayer_design.md` §13 ("Scoperta e comodità", §9.3:
"l'host manda un breve annuncio in broadcast UDP sulla porta 8766 ogni 2 s
(nome del mondo, indirizzo, se accetta ingressi); i client in ascolto lo
mostrano in un elenco").

Solo `socket` di stdlib (§3.2 del design doc: nessuna dipendenza nuova per
la rete, niente mDNS/zeroconf) — un annuncio broadcast periodico, non un
protocollo di scoperta vero e proprio. Per questo l'inserimento manuale di
indirizzo+codice+PIN (già implementato al passo 4) resta **sempre
disponibile e necessario come ripiego**: il broadcast UDP non attraversa
reti che lo bloccano (molti Wi-Fi pubblici con "isolamento client") né
funziona su iOS senza l'entitlement multicast (§3.5) — questo modulo non
prova mai a coprire quei casi, si limita a fallire silenziosamente (nessun
annuncio ricevuto = elenco vuoto), lasciando intatto il percorso manuale.

Due pezzi:
  - `LanAnnouncer`: lato host, un thread daemon che spedisce un annuncio
    ogni `protocol.DISCOVERY_ANNOUNCE_INTERVAL_S` finché `stop()` non viene
    chiamato. Gestito da `network/host_server.py` (stessa proprietà del
    ciclo di vita: si accende quando il master apre un mondo, si spegne
    alla chiusura — §9.4).
  - `discover_worlds()`: lato client, ascolta per una finestra di tempo
    limitata e ritorna gli annunci ricevuti, deduplicati per `world_id`
    (un host manda comunque un annuncio ogni 2 s: durante una finestra di
    qualche secondo lo stesso mondo compare più volte).
"""

from __future__ import annotations

import json
import logging
import socket
import threading
import time
from dataclasses import dataclass
from typing import Callable

from network import protocol

logger = logging.getLogger(__name__)


@dataclass
class DiscoveredWorld:
    """Un mondo trovato in ascolto sulla rete locale — dati sufficienti a
    precompilare il dialogo "Unisciti in LAN" già esistente (host/porta),
    senza far digitare nulla all'utente se lo sceglie dall'elenco."""
    world_id: str
    name: str
    host: str
    port: int
    protocol_version: int
    accepting: bool


def _build_announce_payload(world_id: str, name: str, port: int, accepting: bool) -> bytes:
    return json.dumps({
        "magic": protocol.DISCOVERY_MAGIC,
        "world_id": world_id,
        "name": name,
        "port": port,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "accepting": accepting,
    }).encode("utf-8")


class LanAnnouncer:
    """
    Manda un breve annuncio broadcast UDP a intervalli regolari finché è in
    esecuzione — lato host. `accepting_fn` è chiamata ad ogni invio invece
    di tenere un flag proprio: `WorldHostServer.accepting` resta l'UNICA
    fonte di verità su "questo mondo accetta ingressi ora" (letta anche da
    `world_info()`/`GET /world`), l'annunciatore la specchia senza doverla
    duplicare né tenerla sincronizzata a mano.
    """

    def __init__(self, world_id: str, world_name: str, port: int,
                 accepting_fn: Callable[[], bool] = lambda: True,
                 interval: float = protocol.DISCOVERY_ANNOUNCE_INTERVAL_S):
        self.world_id = world_id
        self.world_name = world_name
        self.port = port
        self.accepting_fn = accepting_fn
        self.interval = interval
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._sock: socket.socket | None = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self._thread is not None:
            return  # già in esecuzione — start() idempotente, non un errore
        self._stop_event.clear()
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        except OSError as e:
            # Alcune piattaforme/sandbox non concedono SO_BROADCAST — la
            # scoperta automatica diventa semplicemente non disponibile,
            # non un errore fatale per l'hosting (che resta comunque
            # raggiungibile con indirizzo+codice+PIN a mano).
            logger.warning("LanAnnouncer: impossibile aprire il socket broadcast (%s) — "
                            "la scoperta automatica non sarà disponibile per questo mondo.", e)
            self._sock = None
            return
        self._sock = sock
        self._thread = threading.Thread(
            target=self._run, name=f"lan-announce-{self.world_id[:8]}", daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=self.interval + 1.0)
            self._thread = None
        if self._sock is not None:
            self._sock.close()
            self._sock = None

    def _run(self) -> None:
        assert self._sock is not None
        while not self._stop_event.is_set():
            payload = _build_announce_payload(
                self.world_id, self.world_name, self.port, bool(self.accepting_fn()),
            )
            try:
                self._sock.sendto(payload, ("255.255.255.255", protocol.DISCOVERY_PORT))
            except OSError as e:
                # Rete assente/cambiata a metà (§11.7) — riprova al giro
                # successivo, non termina il thread per un singolo invio
                # fallito.
                logger.debug("LanAnnouncer: invio broadcast fallito (%s)", e)
            self._stop_event.wait(self.interval)


def discover_worlds(timeout: float = 3.0) -> list[DiscoveredWorld]:
    """
    Ascolta gli annunci broadcast per `timeout` secondi e ritorna i mondi
    trovati, deduplicati per `world_id` (tiene l'annuncio più recente di
    ciascuno). Bloccante — pensata per essere chiamata da un pulsante
    "Cerca partite nelle vicinanze" nella UI di ingresso, non da un ciclo
    automatico continuo (nessuna dipendenza da un event loop async: § 3.2,
    stessa stdlib-only del resto del trasporto).

    L'indirizzo IP del mittente (`addr[0]`, letto dal socket, mai dal
    payload) è usato come `host` del risultato — un client non deve fidarsi
    di un indirizzo dichiarato nel pacchetto stesso.
    """
    results: dict[str, DiscoveredWorld] = {}
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", protocol.DISCOVERY_PORT))
        sock.settimeout(0.5)
    except OSError as e:
        logger.warning("discover_worlds: impossibile ascoltare sulla porta di scoperta (%s) — "
                        "nessun mondo verrà trovato automaticamente.", e)
        return []

    deadline = time.monotonic() + max(0.0, timeout)
    try:
        while time.monotonic() < deadline:
            try:
                raw, addr = sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                data = json.loads(raw.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if not isinstance(data, dict) or data.get("magic") != protocol.DISCOVERY_MAGIC:
                continue  # pacchetto non nostro — rumore di rete, ignorato
            world_id = str(data.get("world_id", ""))
            if not world_id:
                continue
            results[world_id] = DiscoveredWorld(
                world_id=world_id,
                name=str(data.get("name", "")),
                host=addr[0],
                port=int(data.get("port", 0) or 0),
                protocol_version=int(data.get("protocol_version", 0) or 0),
                accepting=bool(data.get("accepting", False)),
            )
    finally:
        sock.close()

    return list(results.values())
