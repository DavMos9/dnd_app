"""
Host LAN di un Mondo — passo 4 di `dnd_app/docs/multiplayer_design.md`
(§9.2, "La rete, in concreto").

`WorldHostServer` fa da lato server del meccanismo comando -> validazione ->
evento (§5): riceve richieste HTTP da altri dispositivi sulla stessa rete e
le inoltra a un `core.world_backend.LocalBackend` già esistente — nessuna
logica di permessi o di applicazione qui, solo trasporto e sicurezza
(§9.4). Tutto sulla libreria standard (`http.server.ThreadingHTTPServer`,
`secrets`, `threading`): nessuna dipendenza nuova, vincolo verificato in
§3.2 del design doc (rischio serious-python sul build mobile).

Sicurezza proporzionata a una LAN domestica (§9.4), non un sistema di
autenticazione vero:
- **PIN a 6 cifre** generato ad ogni `start()`, mostrato dal master.
- **Token di sessione** (`secrets.token_urlsafe`) consegnato all'ingresso e
  ripresentato ad ogni chiamata autenticata (header `Authorization: Bearer`).
- **Il master approva ogni ingresso di un dispositivo non ancora membro**
  (`list_pending()`/`approve()`/`reject()`, chiamati direttamente dalla UI
  del master — gira nello stesso processo dell'host, non serve esporli via
  HTTP). Un dispositivo già membro del mondo rientra senza approvazione.
- Solo HTTP in chiaro, dichiarato (§9.4): accettabile in una LAN domestica,
  la UI deve dirlo esplicitamente.

Il server si accende solo quando il master apre l'hosting esplicitamente
(§9.4: "nessuna porta aperta di default") e si spegne SOLO con "Ferma
hosting" o alla vera chiusura del processo (thread `daemon=True`) — MAI
navigando via dalla Sezione Mondi verso un'altra schermata dell'app: legarne
il ciclo di vita a quello di una view farebbe perdere l'hosting al master
al primo cambio di schermata. Garantito da `HostServerSlot`, vedi il suo
docstring.
"""

from __future__ import annotations

import base64
import json
import logging
import secrets
import socket
import threading
import time
import urllib.parse
import uuid as _uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from core import world_permissions as perm
from core.image_utils import sniff_mime
from core.world_backend import LocalBackend
from data.repositories import character_repo, loot_repo, maps_repo, master_repo, world_repo
from data.repositories import character_export, world_transfer_repo
from network import protocol
from network.discovery import LanAnnouncer

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now().isoformat()


def local_ip_hint() -> str:
    """
    Indirizzo IP locale più probabile da mostrare al master come punto
    d'ingresso (§9.3: "l'host mostra 192.168.1.7:8765"). Non invia alcun
    pacchetto: aprire una connessione UDP verso un indirizzo pubblico serve
    solo a far scegliere al sistema operativo l'interfaccia di uscita
    corretta, da cui si legge l'IP locale — trucco standard, nessuna
    dipendenza nuova. Ripiega su "127.0.0.1" se non c'è alcuna rete attiva
    (utile comunque per un test sullo stesso dispositivo)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def _generate_pin() -> str:
    """PIN numerico a 6 cifre (§9.4) — distinto dal codice d'ingresso del
    mondo (6 caratteri alfabetici di `world_repo.generate_join_code()`):
    il codice identifica QUALE mondo, il PIN è un secondo fattore rigenerato
    ad ogni apertura dell'hosting."""
    return "".join(secrets.choice("0123456789") for _ in range(6))


@dataclass
class PendingJoinRequest:
    """Un dispositivo non ancora membro che chiede di entrare — resta qui
    finché il master non lo approva o rifiuta dalla propria UI (§9.4:
    «Marco vuole entrare»)."""
    id: str
    device_id: str
    display_name: str
    status: str = "pending"  # pending | approved | rejected
    token: str = ""
    role: str = ""
    created_at: str = field(default_factory=_now)
    #: Id del codice di trasferimento riscattato (§11.9). Vuoto per
    #: un ingresso normale. Quando è valorizzato, `approve()` NON crea un nuovo
    #: membro: riassegna quello esistente a questo dispositivo. Il master deve
    #: vedere la differenza — non è un giocatore nuovo che entra, è uno scambio
    #: di identità che farà smettere di funzionare il vecchio dispositivo.
    transfer_id: str = ""
    #: Nome del membro che si sta sostituendo, copiato dal codice: serve alla UI
    #: del master per scrivere «X vuole spostare il personaggio di Y».
    transfer_member_name: str = ""


class _WorldHTTPServer(ThreadingHTTPServer):
    """Un thread per connessione (§9.2: accettabile con 4-8 giocatori, un
    tavolo di D&D — non con 50). `daemon_threads` così un client bloccato
    in attesa lunga non impedisce lo spegnimento pulito del server."""
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address, handler_cls, host_server: "WorldHostServer"):
        self.host_server = host_server
        super().__init__(server_address, handler_cls)


class _RequestHandler(BaseHTTPRequestHandler):
    """Dispatcher per rotta — nessuna logica di dominio qui, solo
    marshaling JSON e delega a `WorldHostServer`. Vedi §9.2 per l'elenco
    delle rotte."""

    protocol_version = "HTTP/1.1"  # necessario per il keep-alive dell'attesa lunga

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        # BaseHTTPRequestHandler scrive di default su stderr ad ogni
        # richiesta: con l'attesa lunga (una ogni ~25s per client connesso)
        # sarebbe rumore costante nei log dell'app. Usiamo il logger del
        # progetto, a livello debug.
        logger.debug("HTTP %s - %s", self.address_string(), format % args)

    def _host(self) -> "WorldHostServer":
        return self.server.host_server  # type: ignore[attr-defined]

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass  # client disconnesso a metà risposta — non un errore del server

    def _send_binary(self, status: int, content_type: str, data: bytes) -> None:
        """Prima rotta non-JSON del progetto (§6.4, passo 8, `GET
        /map/<id>/image`) — stessa forma di `_send_json` ma senza
        serializzare: `data` è già la sequenza di byte da mandare in
        risposta (l'immagine decodificata da base64, mai il testo base64
        stesso)."""
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _read_json_body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
        except ValueError:
            length = 0
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    def _bearer_token(self) -> str:
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth[len("Bearer "):].strip()
        return ""

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)
        host = self._host()
        try:
            if path == "/world":
                self._send_json(200, host.world_info())
            elif path == "/join/status":
                request_id = (qs.get("request_id") or [""])[0]
                self._send_json(200, host.join_status(request_id))
            elif path == "/events":
                since = int((qs.get("since") or ["0"])[0])
                wait = float((qs.get("wait") or [str(host.long_poll_timeout)])[0])
                status, payload = host.handle_events(self._bearer_token(), since, wait)
                self._send_json(status, payload)
            elif path == "/snapshot":
                status, payload = host.handle_snapshot(self._bearer_token())
                self._send_json(status, payload)
            elif path.startswith("/character/"):
                character_id = path[len("/character/"):]
                status, payload = host.handle_get_character(self._bearer_token(), character_id)
                self._send_json(status, payload)
            elif path.startswith("/map/") and path.endswith("/image"):
                map_id = path[len("/map/"):-len("/image")]
                status, content_type, data = host.handle_map_image(self._bearer_token(), map_id)
                self._send_binary(status, content_type, data)
            elif path.startswith("/map/") and path.endswith("/annotations"):
                map_id = path[len("/map/"):-len("/annotations")].rstrip("/")
                status, payload = host.handle_map_annotations(self._bearer_token(), map_id)
                self._send_json(status, payload)
            else:
                self._send_json(404, {"error": "Rotta sconosciuta."})
        except Exception as e:
            logger.error("Errore GET %s: %s", path, e)
            self._send_json(500, {"error": "Errore interno del server."})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        body = self._read_json_body()
        host = self._host()
        try:
            if path == "/join":
                status, payload = host.handle_join(body)
                self._send_json(status, payload)
            elif path == "/join/cancel":
                status, payload = host.handle_join_cancel(body)
                self._send_json(status, payload)
            elif path == "/command":
                status, payload = host.handle_command(self._bearer_token(), body)
                self._send_json(status, payload)
            elif path == "/leave":
                status, payload = host.handle_leave(self._bearer_token())
                self._send_json(status, payload)
            else:
                self._send_json(404, {"error": "Rotta sconosciuta."})
        except Exception as e:
            logger.error("Errore POST %s: %s", path, e)
            self._send_json(500, {"error": "Errore interno del server."})


class HostServerSlot:
    """
    Contenitore mutabile per l'hosting LAN eventualmente attivo in questa
    sessione dell'app — tenuto da `ui/app.py::DnDApp` (che vive quanto il
    processo) e condiviso con ogni `ui.views.world.world_view.WorldsView`
    creata ad ogni navigazione nella Sezione Mondi
    (`DnDApp._show_worlds_view`).

    `WorldHostServer` non può vivere come attributo di ISTANZA su
    `WorldsView`, fermato in `will_unmount()`: `ui/app.py::_navigate()`
    azzera e ricostruisce l'intera pagina ad OGNI navigazione di primo
    livello (Home, Modalità Master, Mondi, cambio tema incluso, non solo un
    vero "esco dalla Sezione Mondi") — il ciclo di vita standard di Flet fa
    scattare `will_unmount()` sulla `WorldsView` precedente ad ogni singola
    di queste navigazioni, non solo quando l'utente lascia davvero la
    sezione Mondi per restarci fuori. Un master che semplicemente controlla
    un'altra schermata dell'app, mentre un tavolo di gioco è in corso, non
    deve MAI disconnettere tutti i giocatori collegati.

    Questo contenitore rompe quell'accoppiamento: l'hosting vive quanto
    la sessione dell'app (non quanto la singola `WorldsView` che l'ha
    avviato), e si ferma SOLO su un'azione esplicita del master ("Ferma
    hosting", `WorldsView._stop_hosting()`) — mai per un semplice cambio
    di schermata. Sopravvive comunque a una chiusura vera del processo
    senza bisogno di alcun cleanup qui: `WorldHostServer._thread` è
    `daemon=True` (§9.2), termina da solo con l'uscita del processo.
    """

    def __init__(self) -> None:
        self.server: WorldHostServer | None = None


class WorldHostServer:
    """
    Ciclo di vita e stato dell'hosting di UN mondo su questo dispositivo.
    Un'istanza per mondo ospitato — la UI ne crea una quando il master
    preme "Ospita in LAN" e la ferma quando preme "Ferma hosting", non
    più legata al ciclo di vita di una singola view (vedi `HostServerSlot`).
    """

    def __init__(self, world_id: str, backend: LocalBackend | None = None,
                 port_range=protocol.DEFAULT_PORT_RANGE,
                 long_poll_timeout: float = protocol.LONG_POLL_TIMEOUT_S,
                 announce: bool = True):
        self.world_id = world_id
        self.backend = backend or LocalBackend()
        self.port_range = port_range
        self.long_poll_timeout = long_poll_timeout
        #: Multiplayer passo 5 (§9.3): manda l'annuncio broadcast UDP che
        #: alimenta `network.discovery.discover_worlds()` lato client.
        #: Disattivabile (`announce=False`) per i test che non vogliono
        #: aprire un socket broadcast reale — la scoperta automatica resta
        #: comunque solo un mattone di comodità, mai l'unico modo di
        #: entrare in un mondo (§9.3: il codice a 6 caratteri funziona
        #: sempre).
        self._announce_enabled = announce

        self.pin: str = ""
        self.accepting = False

        self._httpd: _WorldHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._port: int | None = None
        self._announcer: LanAnnouncer | None = None

        self._lock = threading.Lock()
        self._tokens: dict[str, str] = {}          # token -> device_id
        self._pending: dict[str, PendingJoinRequest] = {}
        #: Anti-spam su `/join` (completamento della difesa
        #: in profondità lasciata in sospeso quando `LocalBackend.
        #: send_command()` ha ricevuto lo stesso trattamento per `/command`:
        #: senza questo, nulla impediva di martellare `/join` per tentare
        #: PIN diversi in rapida successione — il PIN a 6 cifre (§9.4) è
        #: l'UNICA barriera per un dispositivo non ancora membro, quindi è
        #: proprio lì che un limite serve di più. A differenza dei
        #: `_host_cooldowns` di `core.world_backend` (stato di MODULO, un
        #: solo host per processo lato app) questo è stato di ISTANZA: un
        #: `WorldHostServer` vive quanto UNA sessione di hosting, e
        #: `stop()` lo azzera già esplicitamente insieme a token/pending —
        #: un nuovo `start()` è comunque una nuova sessione con PIN nuovo,
        #: niente da preservare tra l'una e l'altra. Chiave: `device_id`
        #: (10s, `perm.NETWORK_REQUEST_COOLDOWN_S`, stesso valore già usato
        #: lato client per "tutte le richieste di rete semplici" —
        #: coerente, anche se qui è un tracciato indipendente: un client
        #: che passa da qui non ha ancora un token, non può condividere
        #: stato con `LocalBackend`).
        self._join_attempts: dict[str, float] = {}

    # ------------------------------------------------------------------
    # Ciclo di vita
    # ------------------------------------------------------------------

    @property
    def port(self) -> int | None:
        return self._port

    @property
    def is_running(self) -> bool:
        return self._httpd is not None

    def start(self) -> int:
        """Avvia il server su una porta libera dell'intervallo (§9.2:
        8765, ripiego sulle successive). Ritorna la porta effettiva."""
        if self._httpd is not None:
            raise RuntimeError("Il server è già avviato per questo mondo.")

        self.pin = _generate_pin()
        last_error: Exception | None = None
        for candidate_port in self.port_range:
            try:
                httpd = _WorldHTTPServer(("0.0.0.0", candidate_port), _RequestHandler, self)
            except OSError as e:
                last_error = e
                continue
            self._httpd = httpd
            self._port = candidate_port
            break

        if self._httpd is None:
            raise RuntimeError(
                f"Nessuna porta libera nell'intervallo {self.port_range}: {last_error}"
            )

        self._thread = threading.Thread(
            target=self._httpd.serve_forever, name=f"world-host-{self.world_id[:8]}",
            daemon=True,
        )
        self._thread.start()
        self.accepting = True

        if self._announce_enabled:
            world = world_repo.get_world(self.world_id)
            self._announcer = LanAnnouncer(
                self.world_id, world.name if world else "", self._port,
                accepting_fn=lambda: self.accepting,
            )
            self._announcer.start()

        logger.info("WorldHostServer avviato su porta %d per il mondo %s",
                    self._port, self.world_id)
        return self._port

    def stop(self) -> None:
        """Ferma il server, l'annuncio broadcast e scarta PIN/token/
        richieste in sospeso — un prossimo `start()` è una nuova sessione
        di hosting a tutti gli effetti (§9.4: nuovo PIN ad ogni apertura)."""
        self.accepting = False
        if self._announcer is not None:
            self._announcer.stop()
            self._announcer = None
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None
        with self._lock:
            self._tokens.clear()
            self._pending.clear()
            self._join_attempts.clear()
        self.pin = ""
        self._port = None
        logger.info("WorldHostServer fermato per il mondo %s", self.world_id)

    # ------------------------------------------------------------------
    # Approvazione ingressi — chiamate dirette dalla UI del master, STESSO
    # processo dell'host: nessuna rotta HTTP dedicata, solo il proprietario
    # dell'hosting deve vederle.
    # ------------------------------------------------------------------

    def list_pending(self) -> list[PendingJoinRequest]:
        with self._lock:
            return [r for r in self._pending.values() if r.status == "pending"]

    def approve(self, request_id: str) -> bool:
        with self._lock:
            req = self._pending.get(request_id)
            if req is None or req.status != "pending":
                return False

        world = world_repo.get_world(self.world_id)
        if world is None:
            return False

        # Due esiti diversi per la stessa approvazione (§11.9): un
        # ingresso normale crea un membro nuovo, un trasferimento riassegna
        # quello esistente a un altro dispositivo.
        if req.transfer_id:
            member = self._approve_transfer(req)
            if member is None:
                return False
        else:
            joined = world_repo.join_world_by_code(
                world.join_code, req.device_id, req.display_name,
            )
            if joined is None:
                return False
            _world, member = joined

        token = self._issue_token(req.device_id)
        world_repo.set_member_connected(self.world_id, req.device_id, True)
        with self._lock:
            req.status = "approved"
            req.token = token
            req.role = member.role
        return True

    def _approve_transfer(self, req: PendingJoinRequest):
        """
        Riassegna un membro esistente al dispositivo di `req` e chiude il codice.
        Restituisce il `WorldMember` aggiornato, oppure `None` se qualcosa è
        andato storto — e in quel caso nulla è stato scritto (la riassegnazione è
        una singola transazione in `world_transfer_repo.rebind_device`).

        L'ordine conta: prima la riassegnazione, poi il codice segnato come
        usato, poi l'evento di giornale, infine la revoca dei token del vecchio
        dispositivo. Se il primo passo fallisce, il codice resta valido e il
        master può riprovare.
        """
        transfer = world_transfer_repo.get_transfer(req.transfer_id)
        if transfer is None or transfer.status != world_transfer_repo.STATUS_PENDING:
            logger.warning(
                "_approve_transfer: codice %s non più riscattabile", req.transfer_id,
            )
            return None

        old_device_id = transfer.member_device_id
        summary_data = world_transfer_repo.rebind_device(
            self.world_id, old_device_id, req.device_id,
        )
        if summary_data is None:
            return None

        if not world_transfer_repo.mark_redeemed(transfer.id, req.device_id):
            # `mark_redeemed` ha un `WHERE status='pending'`: un fallimento qui
            # significa che un altro riscatto ha vinto la corsa nel frattempo.
            # La riassegnazione è già avvenuta e non si annulla — si registra e
            # si prosegue, perché il membro ORA appartiene davvero a questo
            # dispositivo e negarglielo lo lascerebbe fuori da un mondo di cui è
            # già proprietario.
            logger.warning(
                "_approve_transfer: codice %s già chiuso da un altro riscatto "
                "(riassegnazione a %s comunque completata)",
                transfer.id, req.device_id,
            )

        display_name = summary_data.get("display_name") or req.display_name
        world_repo.append_event(
            self.world_id, req.device_id, display_name,
            kind=perm.DEVICE_TRANSFER_REDEEM_KIND, target_type="member",
            target_id=summary_data.get("member_id", ""),
            summary=(
                f"{display_name} ha spostato il personaggio su un nuovo dispositivo."
            ),
            payload=json.dumps({
                "old_device_id": old_device_id,
                "new_device_id": req.device_id,
                "transfer_id": transfer.id,
                "characters": summary_data.get("characters", 0),
                "notes_remapped": summary_data.get("notes_remapped", 0),
                "rejoin_requests": summary_data.get("rejoin_requests", 0),
            }),
            before_state=json.dumps({"device_id": old_device_id}),
        )

        # Il vecchio dispositivo non deve poter continuare a scrivere con un
        # token già emesso: la sua attesa lunga su `GET /events` torna 401 al
        # giro successivo (`handle_events` risolve il token e non lo trova più),
        # che è esattamente il segnale con cui scopre di essere stato sostituito.
        with self._lock:
            for tok, dev in list(self._tokens.items()):
                if dev == old_device_id:
                    del self._tokens[tok]

        return world_repo.get_member(self.world_id, req.device_id)

    def reject(self, request_id: str) -> bool:
        with self._lock:
            req = self._pending.get(request_id)
            if req is None or req.status != "pending":
                return False
            req.status = "rejected"
        return True

    def cancel_own_request(self, request_id: str, device_id: str) -> bool:
        """
        Annulla una richiesta di ingresso — a differenza di `reject()`
        sopra (il master rifiuta la richiesta di un ALTRO), qui è il
        richiedente stesso ad annullare la propria, così può inviarne
        subito una nuova invece di restare bloccato dietro quella in
        sospeso. Verifica che `device_id` corrisponda al proprietario della
        richiesta — nessun token esiste
        ancora a questo punto del flusso (il dispositivo non è membro),
        quindi questo confronto è l'unica autenticazione disponibile, come
        già per l'intero `handle_join()`.
        """
        with self._lock:
            req = self._pending.get(request_id)
            if req is None or req.status != "pending" or req.device_id != device_id:
                return False
            req.status = "cancelled"
        return True

    # ------------------------------------------------------------------
    # Rotte — chiamate dal dispatcher HTTP, ma testabili anche a diretto
    # (senza socket) passando token/body a mano: la logica di dominio non
    # dipende da `BaseHTTPRequestHandler`.
    # ------------------------------------------------------------------

    def world_info(self) -> dict:
        world = world_repo.get_world(self.world_id)
        return {
            "world_id": self.world_id,
            "name": world.name if world else "",
            "protocol_version": protocol.PROTOCOL_VERSION,
            "accepting": self.accepting,
            # Capacità opzionali dell'host (§11.9). Meccanismo
            # deliberatamente scelto INVECE di alzare `PROTOCOL_VERSION` a 2:
            # `_check_protocol_version` è un'uguaglianza stretta e rifiuta
            # l'ingresso con "Aggiorna l'app su entrambi i dispositivi", quindi
            # un bump romperebbe OGNI accoppiamento esistente per una
            # funzionalità che nessuno sta ancora usando. Un client che vuole
            # riscattare un codice di trasferimento controlla qui prima di
            # provarci, e con un host più vecchio (che non manda la chiave)
            # riceve un messaggio specifico invece di un "codice non valido"
            # fuorviante.
            "features": protocol.HOST_FEATURES,
        }

    def _check_protocol_version(self, body: dict) -> str | None:
        """
        Verifica lato HOST della versione di protocollo (§11.6) — finora il
        controllo esisteva solo lato client (`core.world_sync.start_lan_join`
        confronta `GET /world` prima di mostrare il dialogo del PIN), quindi
        un client che saltasse quel passo (o una versione modificata)
        potrebbe comunque entrare. Ritorna un messaggio d'errore leggibile
        se la versione manca o non combacia, `None` se va bene — chiamato
        da `handle_join`/`handle_command`, prima di qualunque scrittura.
        """
        client_version = body.get("protocol_version")
        if client_version != protocol.PROTOCOL_VERSION:
            return (
                f"Versione del protocollo non compatibile (host: "
                f"{protocol.PROTOCOL_VERSION}, dispositivo: {client_version!r}). "
                f"Aggiorna l'app su entrambi i dispositivi."
            )
        return None

    def handle_join(self, body: dict) -> tuple[int, dict]:
        version_error = self._check_protocol_version(body)
        if version_error is not None:
            return 400, {"error": version_error}

        join_code = str(body.get("join_code", "")).strip().upper()
        pin = str(body.get("pin", "")).strip()
        device_id = str(body.get("device_id", "")).strip()
        display_name = str(body.get("display_name", "")).strip() or "Giocatore"

        if not device_id:
            return 400, {"error": "device_id mancante."}

        rate_limit_error = self._check_join_rate_limit(device_id)
        if rate_limit_error is not None:
            return 429, {"error": rate_limit_error}

        world = world_repo.get_world(self.world_id)
        if world is None:
            return 404, {"error": "Mondo non trovato su questo host."}
        if world.join_code.upper() != join_code:
            return 403, {"error": "Codice del mondo errato."}

        # Terzo percorso d'ingresso (§11.9): un dispositivo NUOVO
        # che presenta un codice di trasferimento per subentrare a un membro
        # esistente, portandosi via le sue istanze di personaggio. Va valutato
        # PRIMA del ramo "dispositivo già noto": per definizione questo
        # dispositivo non è ancora membro, e il codice deve poter essere
        # riscattato una volta sola anche se il richiedente ritenta.
        #
        # Il codice SOSTITUISCE il PIN — è strettamente più forte (8 caratteri,
        # monouso, a scadenza, legato a un solo membro, emesso dall'host) — ma
        # NON sostituisce l'approvazione del master, che resta obbligatoria:
        # chi intercetta un codice non entra comunque senza che il master dica sì.
        transfer_code = str(body.get("transfer_code", "")).strip().upper()
        if transfer_code:
            return self._handle_transfer_join(transfer_code, device_id, display_name)

        member = world_repo.get_member(self.world_id, device_id)
        if member is not None:
            # Dispositivo già noto ("registrato" — §9.4: "I dispositivi già
            # noti rientrano senza chiedere"): rientra con il solo
            # join_code, NESSUN controllo PIN — un riavvio dell'hosting da
            # parte del master rigenera un PIN nuovo e svuota tutti i token
            # in memoria, `WorldHostServer.stop()`, ma NON tocca
            # `world_members`, persistito su DB — quindi l'appartenenza già
            # approvata resta valida indipendentemente dal PIN corrente. Un
            # dispositivo MAI approvato prima deve ancora passare dal PIN,
            # vedi ramo sotto — solo l'accesso di un dispositivo già vetted
            # non richiede più che il master condivida un PIN fresco ad
            # ogni riavvio.
            token = self._issue_token(device_id)
            world_repo.set_member_connected(self.world_id, device_id, True)
            return 200, {"status": "approved", "token": token, "role": member.role}

        # Questo dispositivo è stato SOSTITUITO da un altro (§11.9): dirglielo,
        # invece di lasciarlo cadere nel ramo del PIN qui sotto. Senza questo
        # controllo il percorso reale è: token non più valido →
        # `core.world_sync.resolve_backend_for_world` ritenta da sé un ingresso
        # completo con PIN vuoto → "PIN errato." — un messaggio che manda a
        # cercare il problema esattamente nel posto sbagliato. È il motivo per
        # cui le righe `redeemed` di `world_device_transfers` non si cancellano.
        transferred = world_transfer_repo.was_transferred_away(self.world_id, device_id)
        if transferred is not None:
            return 403, {
                "error": (
                    "Il personaggio di questo dispositivo è stato trasferito su "
                    "un altro dispositivo: questo non fa più parte del mondo."
                ),
                "reason": "transferred_away",
            }

        # Nuovo dispositivo: il PIN resta obbligatorio (un estraneo in LAN
        # non può entrare per la prima volta senza che il master lo
        # condivida esplicitamente), poi in coda per l'approvazione
        # esplicita del master (§9.4: «Marco vuole entrare»).
        if not self.pin or pin != self.pin:
            return 403, {"error": "PIN errato."}

        # Deduplica: un dispositivo con già una richiesta in sospeso la
        # riusa invece di accodarne una nuova ad ogni ritentativo — il
        # cooldown di 10s su `_check_join_rate_limit` da solo rallenta lo
        # spam ma non lo impedisce (basta aspettare tra un tentativo e
        # l'altro). `display_name` dell'ultimo tentativo aggiorna quello
        # già in coda (l'utente può aver corretto un refuso nel nome prima
        # di ritentare), il resto della riga (id, timestamp) resta quello
        # originale — il master vede comunque una sola richiesta.
        with self._lock:
            existing = next(
                (r for r in self._pending.values()
                 if r.device_id == device_id and r.status == "pending"),
                None,
            )
            if existing is not None:
                existing.display_name = display_name
                return 200, {"status": "pending", "request_id": existing.id}
            req = PendingJoinRequest(id=str(_uuid.uuid4()), device_id=device_id,
                                      display_name=display_name)
            self._pending[req.id] = req
        return 200, {"status": "pending", "request_id": req.id}

    def handle_join_cancel(self, body: dict) -> tuple[int, dict]:
        """`POST /join/cancel` — controparte di `handle_join`
        per l'annullamento lato richiedente, vedi `cancel_own_request()`."""
        request_id = str(body.get("request_id", "")).strip()
        device_id = str(body.get("device_id", "")).strip()
        if not request_id or not device_id:
            return 400, {"error": "request_id/device_id mancanti."}
        if not self.cancel_own_request(request_id, device_id):
            return 404, {"error": "Richiesta non trovata o già evasa."}
        return 200, {"ok": True}

    def _handle_transfer_join(self, transfer_code: str, device_id: str,
                               display_name: str) -> tuple[int, dict]:
        """
        Riscatto di un codice di trasferimento (§11.9) — accoda la richiesta,
        non riassegna nulla: la riassegnazione avviene solo se il master
        approva, in `_approve_transfer()`.

        Il rate limit su `device_id` è già stato applicato da `handle_join`
        prima di arrivare qui, quindi la barriera contro chi prova codici a
        raffica è quella (10 s per dispositivo, `perm.NETWORK_REQUEST_COOLDOWN_S`).
        """
        # Igiene, non sicurezza: `get_pending_transfer_by_code` scarta comunque i
        # codici scaduti da sé. Serve a non tenere righe morte nell'elenco che il
        # master vede.
        world_transfer_repo.expire_stale_transfers(self.world_id)

        transfer = world_transfer_repo.get_pending_transfer_by_code(
            self.world_id, transfer_code,
        )
        if transfer is None:
            # Messaggio IDENTICO per "inesistente", "scaduto", "revocato" e "già
            # usato": non rivelare quale dei quattro a chi sta provando codici —
            # lo stesso principio già applicato al PIN.
            return 403, {"error": "Codice di trasferimento non valido o scaduto."}

        if transfer.member_device_id == device_id:
            return 400, {
                "error": "Questo è già il dispositivo registrato per quel personaggio.",
            }

        if world_repo.get_member(self.world_id, device_id) is not None:
            # `UNIQUE (world_id, device_id)`: due appartenenze nello stesso
            # mondo non si possono fondere, e non è questa la sede per decidere
            # quale delle due tenere.
            return 409, {
                "error": (
                    "Questo dispositivo è già membro del mondo con un'altra "
                    "identità. Esci dal mondo prima di usare un codice di "
                    "trasferimento."
                ),
            }

        member = world_repo.get_member(self.world_id, transfer.member_device_id)
        if member is None:
            # Il membro è stato espulso dopo l'emissione del codice: non c'è più
            # nulla in cui subentrare.
            return 409, {
                "error": (
                    "Il membro a cui appartiene questo codice non fa più parte "
                    "del mondo."
                ),
            }

        req = PendingJoinRequest(
            id=str(_uuid.uuid4()), device_id=device_id,
            # Se il nuovo dispositivo non manda un nome, si eredita quello del
            # membro che sta sostituendo: cambiare telefono non è un rinomino.
            display_name=display_name or member.display_name,
            transfer_id=transfer.id,
            transfer_member_name=member.display_name,
        )
        with self._lock:
            self._pending[req.id] = req
        return 200, {"status": "pending", "request_id": req.id, "kind": "transfer"}

    def join_status(self, request_id: str) -> dict:
        with self._lock:
            req = self._pending.get(request_id)
        if req is None:
            return {"status": "unknown"}
        if req.status == "approved":
            return {"status": "approved", "token": req.token, "role": req.role}
        if req.status == "rejected":
            return {"status": "rejected"}
        if req.status == "cancelled":
            return {"status": "cancelled"}
        return {"status": "pending"}

    def handle_events(self, token: str, since: int, wait: float) -> tuple[int, dict]:
        device_id = self._resolve_device_by_token(token)
        if device_id is None:
            return 401, {"error": "Token non valido: riconnettersi al mondo."}

        wait = max(0.0, min(wait, self.long_poll_timeout))
        deadline = time.monotonic() + wait
        while True:
            events = world_repo.get_events_since(self.world_id, since)
            if events:
                return 200, {"events": [protocol.event_to_dict(e) for e in events]}
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return 200, {"events": []}
            time.sleep(min(protocol.LONG_POLL_INTERVAL_S, remaining))

    def handle_command(self, token: str, body: dict) -> tuple[int, dict]:
        device_id = self._resolve_device_by_token(token)
        if device_id is None:
            return 401, {"error": "Token non valido: riconnettersi al mondo."}

        # Difesa in profondità (§11.6): il varco principale è già
        # `handle_join` (un client con versione diversa non ottiene mai un
        # token), questo copre un token valido riusato da un client
        # aggiornato/downgradato dopo l'ingresso.
        version_error = self._check_protocol_version(body)
        if version_error is not None:
            return 400, {"error": version_error}

        kind = str(body.get("kind", ""))
        payload = body.get("payload") or {}
        if not isinstance(payload, dict):
            payload = {}
        target_type = str(body.get("target_type", ""))
        target_id = str(body.get("target_id", ""))

        result = self.backend.send_command(
            self.world_id, device_id, kind, payload, target_type, target_id,
        )
        return 200, {
            "success": result.success,
            "error": result.error,
            "event": protocol.event_to_dict(result.event) if result.event else None,
            # Dati destinati SOLO al mittente (§11.9): il codice di
            # trasferimento non può viaggiare in `event.payload`, che finisce nel
            # giornale trasmesso a tutte le repliche.
            "data": result.data,
        }

    def handle_snapshot(self, token: str) -> tuple[int, dict]:
        """
        Stato completo del mondo (§9.2) — mondo + membri + giornale, come
        nel passo 4, **più** (Multiplayer passo 6) l'export integrale delle
        istanze di personaggio di CUI IL CHIAMANTE È PROPRIETARIO in questo
        mondo (`characters.owner_device_id == device_id`, mai tutte le
        istanze: un giocatore vede solo la propria scheda, mai quella di un
        altro membro).

        Serve a seminare la replica locale al primo ingresso
        (`core.world_sync._finalize_join()`): senza questo, un dispositivo
        appena entrato in un mondo LAN non avrebbe alcuna copia locale
        della propria scheda su cui applicare gli eventi successivi (danno,
        PE, condizioni, ...) — il gap descritto in
        `dnd_app/docs/multiplayer_design.md` §6, colmato qui.
        """
        device_id = self._resolve_device_by_token(token)
        if device_id is None:
            return 401, {"error": "Token non valido: riconnettersi al mondo."}

        world = world_repo.get_world(self.world_id)
        if world is None:
            return 404, {"error": "Mondo non trovato."}
        members = world_repo.get_members(self.world_id)
        # limit=None: uno snapshot deve portare l'INTERO giornale, non i
        # 200 eventi più recenti (limite di default di get_events_since,
        # pensato per il polling incrementale) — altrimenti un mondo con
        # più di 200 eventi nella sua storia produce uno snapshot troncato
        # per chi entra ora.
        events = world_repo.get_events_since(self.world_id, 0, limit=None)
        own_characters = [
            c for c in character_repo.get_master_visible_characters(self.world_id)
            if c.owner_device_id == device_id
        ]
        exports = []
        for c in own_characters:
            data = character_export.export_character(c.id)
            if data is not None:
                exports.append(data)
        own_ids = {c.id for c in own_characters}
        change_requests = [
            protocol.change_request_to_dict(r)
            for r in world_repo.get_pending_change_requests(self.world_id)
            if r.character_id in own_ids
        ]
        # Richieste di rientro inviate DA questo device — a
        # differenza dei filtri sopra (che passano da `own_ids`, calcolato
        # su personaggi ATTIVI: `get_master_visible_characters` esclude
        # sempre quelli archiviati) qui basta confrontare `requested_by`,
        # già il device_id del richiedente sulla riga stessa — un'istanza
        # archiviata non compare mai in `own_ids` ma la sua eventuale
        # richiesta di rientro deve comunque raggiungere il device che
        # l'ha inviata al primo (ri)ingresso.
        rejoin_requests = [
            protocol.rejoin_request_to_dict(r)
            for r in world_repo.get_pending_rejoin_requests(self.world_id)
            if r.requested_by == device_id
        ]

        # Isolamento per sezione: un'eccezione in QUALUNQUE sezione sotto
        # (es. un incontro con dati residui da una sessione di test
        # precedente, un NPC collegato ormai cancellato) farebbe fallire
        # l'INTERA risposta con 500 — e poiché `sync_replica()`
        # (core/world_sync.py) richiama questo endpoint ad OGNI ciclo,
        # anche quando non ci sono eventi nuovi, un solo dato residuo rotto
        # bloccherebbe per sempre ogni sincronizzazione successiva su TUTTE
        # le sezioni, non solo quella incidentata — il dispositivo
        # resterebbe congelato allo stato dell'ultimo snapshot riuscito
        # (tipicamente quello del primo ingresso). Ogni sezione qui sotto
        # degrada quindi a "vuota" invece di far fallire tutto, con un log
        # per poterla poi correggere.

        # Note condivise visibili a questo device (§7B, chiude lo stesso gap
        # delle istanze sopra: senza questo, un giocatore che entra DOPO che
        # una nota è stata condivisa non la riceverebbe mai — gli eventi
        # storici vengono salvati ma non "applicati" da `_finalize_join()`).
        try:
            notes = [
                asdict(n) for n in master_repo.get_notes_visible_to(self.world_id, device_id)
            ]
        except Exception as e:
            logger.error("handle_snapshot: errore costruendo le note condivise: %s", e)
            notes = []

        # Incontro visibile ai giocatori, se c'è (§6.5, passo 7C) — stesso
        # gap delle note sopra: senza questo, un giocatore che entra mentre
        # un combattimento è già visibile non lo vedrebbe mai finché non
        # arriva un evento successivo (next_turn/toggle).
        try:
            visible_encounter = master_repo.get_visible_encounter_for_world(self.world_id)
            encounter_payload = None
            if visible_encounter is not None:
                encounter_payload = {
                    "encounter": asdict(visible_encounter),
                    "members": master_repo.resolved_members_to_dicts(
                        master_repo.get_encounter_members_resolved(visible_encounter.id),
                    ),
                }
        except Exception as e:
            logger.error("handle_snapshot: errore costruendo l'incontro visibile: %s", e)
            encounter_payload = None

        # Mappe pubblicate in questo mondo (§6.4, passo 8) — solo metadati
        # (id/nome), MAI `image_data`: resta sulla rotta dedicata
        # `GET /map/<id>/image`, scaricata lazy alla prima apertura. Stesso
        # gap delle note/dell'incontro sopra: senza questo, un giocatore che
        # entra dopo che una mappa è stata pubblicata non la vedrebbe mai.
        try:
            shared_maps = [
                {"id": m.id, "name": m.name}
                for m in maps_repo.get_shared_maps(self.world_id)
            ]
        except Exception as e:
            logger.error("handle_snapshot: errore costruendo le mappe condivise: %s", e)
            shared_maps = []

        # Deposito comune del gruppo — solo `stash_kind="party"`,
        # stesso gap delle sezioni sopra: senza questo, un giocatore/master
        # non-host che entra dopo che una voce è stata depositata non la
        # vedrebbe mai finché non arriva un evento successivo. L'archivio
        # privato del Master (`stash_kind="master"`) non entra MAI qui —
        # resta intenzionalmente locale, vedi `data/repositories/loot_repo.py`.
        try:
            loot_stash = [
                asdict(entry) for entry in loot_repo.get_entries("party", world_id=self.world_id)
            ]
        except Exception as e:
            logger.error("handle_snapshot: errore costruendo il deposito del gruppo: %s", e)
            loot_stash = []

        return 200, {
            "world": protocol.world_to_dict(world),
            "members": [protocol.member_to_dict(m) for m in members],
            "events": [protocol.event_to_dict(e) for e in events],
            "characters": exports,
            "change_requests": change_requests,
            "rejoin_requests": rejoin_requests,
            "notes": notes,
            "visible_encounter": encounter_payload,
            "shared_maps": shared_maps,
            "loot_stash": loot_stash,
        }

    def handle_get_character(self, token: str, character_id: str) -> tuple[int, dict]:
        """
        `GET /character/<id>` — Multiplayer passo 6: export integrale di
        UNA istanza, per rimaterializzare la replica locale dopo un evento
        che l'ha toccata (`core.world_sync.apply_event_to_replica`), senza
        dover riscaricare l'intero `/snapshot` (giornale compreso) per un
        singolo cambiamento.

        Permesso solo al PROPRIETARIO del personaggio (`owner_device_id`):
        stessa regola di `handle_snapshot`, un giocatore non può leggere la
        scheda di un altro tramite questa rotta. Il master/owner del mondo
        non ne ha bisogno: la sua copia è già quella autoritativa sul
        proprio DB.
        """
        device_id = self._resolve_device_by_token(token)
        if device_id is None:
            return 401, {"error": "Token non valido: riconnettersi al mondo."}
        if not character_id:
            return 400, {"error": "Id personaggio mancante."}

        character = character_repo.get_by_id(character_id)
        if character is None or character.world_id != self.world_id:
            return 404, {"error": "Personaggio non trovato in questo mondo."}
        if character.owner_device_id != device_id:
            return 403, {"error": "Non sei il proprietario di questo personaggio."}

        data = character_export.export_character(character_id)
        if data is None:
            return 500, {"error": "Esportazione del personaggio fallita."}
        return 200, {"character": data}

    def handle_map_image(self, token: str, map_id: str) -> tuple[int, str, bytes]:
        """
        `GET /map/<id>/image` (§6.4, passo 8) — l'immagine di una mappa
        condivisa, MAI trasportata via evento/snapshot (troppo grande per
        il giornale). Prima rotta non-JSON del progetto: ritorna sempre
        `(status, content_type, bytes)` — anche l'errore è servito come
        JSON con `content_type="application/json"`, cosicché il
        dispatcher HTTP possa restare uno solo per entrambi i casi (vedi
        `_RequestHandler._handle_map_image`).

        Permesso a chiunque sia membro del mondo della mappa (non solo il
        proprietario, a differenza di `handle_get_character`): una mappa
        condivisa è per definizione visibile a tutto il tavolo, non a un
        singolo giocatore. ECCEZIONE: una mappa nascosta ai
        giocatori (`visible_to_players=False`, distinto da `is_shared` —
        vedi `CMD_MAP_VISIBILITY`) nega l'immagine a chi non è master/owner,
        stesso principio fail-closed di `handle_get_character` — un
        giocatore non deve poter scaricare l'immagine anche conoscendone
        l'id per tentativi, non solo non vederla in lista.
        """
        def _error(status: int, message: str) -> tuple[int, str, bytes]:
            return status, "application/json", json.dumps({"error": message}).encode("utf-8")

        device_id = self._resolve_device_by_token(token)
        if device_id is None:
            return _error(401, "Token non valido: riconnettersi al mondo.")
        if not map_id:
            return _error(400, "Id mappa mancante.")

        game_map = maps_repo.get_map(map_id)
        if game_map is None or game_map.world_id != self.world_id or not game_map.is_shared:
            return _error(404, "Mappa non trovata in questo mondo.")
        member = world_repo.get_member(self.world_id, device_id)
        if member is None:
            return _error(403, "Non sei membro di questo mondo.")
        if not game_map.visible_to_players and member.role == perm.ROLE_PLAYER:
            return _error(404, "Mappa non trovata in questo mondo.")
        if not game_map.image_data:
            return _error(404, "Questa mappa non ha ancora un'immagine.")

        try:
            raw = base64.b64decode(game_map.image_data)
        except Exception:
            return _error(500, "Immagine della mappa non decodificabile.")
        return 200, sniff_mime(raw), raw

    def handle_map_annotations(self, token: str, map_id: str) -> tuple[int, dict]:
        """
        `GET /map/<id>/annotations` — backfill lazy delle
        annotazioni di una mappa condivisa, stesso principio di
        `handle_map_image` sopra ma per i tratti di disegno invece
        dell'immagine: entrambi restano fuori da `handle_snapshot`
        (§6.4, "solo metadati... MAI `image_data`"), qui perché anche un
        deposito di molti tratti disegnati nel tempo può crescere oltre
        quanto è ragionevole spedire ad OGNI ciclo di sync per OGNI
        membro — a differenza dell'immagine però questa resta una
        risposta JSON (niente byte grezzi), quindi passa dal normale
        dispatcher JSON invece che da quello dedicato di `handle_map_image`.

        Colma un gap del join: lo stub creato al join
        (`maps_repo.replica_create_map_stub`) inizializza sempre
        `annotations='[]'` e non viene mai aggiornato retroattivamente;
        solo i tratti disegnati DOPO l'ingresso arrivano via eventi
        `CMD_MAP_DRAW` — senza questa rotta, i tratti disegnati dal master
        prima che il giocatore entrasse nel mondo resterebbero invisibili.
        Stessa regola di visibilità di `handle_map_image`:
        chiunque sia membro del mondo, tranne un giocatore contro una
        mappa nascosta (`visible_to_players=False`).
        """
        device_id = self._resolve_device_by_token(token)
        if device_id is None:
            return 401, {"error": "Token non valido: riconnettersi al mondo."}
        if not map_id:
            return 400, {"error": "Id mappa mancante."}

        game_map = maps_repo.get_map(map_id)
        if game_map is None or game_map.world_id != self.world_id or not game_map.is_shared:
            return 404, {"error": "Mappa non trovata in questo mondo."}
        member = world_repo.get_member(self.world_id, device_id)
        if member is None:
            return 403, {"error": "Non sei membro di questo mondo."}
        if not game_map.visible_to_players and member.role == perm.ROLE_PLAYER:
            return 404, {"error": "Mappa non trovata in questo mondo."}

        return 200, {"annotations": game_map.annotations or "[]"}

    def handle_leave(self, token: str) -> tuple[int, dict]:
        device_id = self._resolve_device_by_token(token)
        if device_id is None:
            return 401, {"error": "Token non valido."}
        with self._lock:
            self._tokens.pop(token, None)
        world_repo.set_member_connected(self.world_id, device_id, False)
        return 200, {"ok": True}

    # ------------------------------------------------------------------
    # Anti-spam su /join — vedi il commento su `self._join_attempts` in
    # `__init__` per il motivo e le scelte di design.
    # ------------------------------------------------------------------

    def _check_join_rate_limit(self, device_id: str) -> str | None:
        """Ritorna un messaggio d'errore (pronto per il body della
        risposta HTTP) se `device_id` ha già tentato un ingresso negli
        ultimi `NETWORK_REQUEST_COOLDOWN_S` secondi, `None` se può
        procedere — nel qual caso l'istante viene registrato SUBITO, prima
        ancora di validare codice/PIN (stessa policy già in uso altrove:
        anche un tentativo respinto per credenziali errate ha già generato
        traffico, e proprio i tentativi con PIN sbagliato sono quelli da
        limitare di più)."""
        with self._lock:
            remaining = perm.cooldown_remaining(
                self._join_attempts.get(device_id, 0.0), perm.NETWORK_REQUEST_COOLDOWN_S,
            )
            if remaining > 0:
                return (
                    f"Troppi tentativi di ingresso ravvicinati — "
                    f"aspetta {int(remaining) + 1} secondi."
                )
            self._join_attempts[device_id] = time.monotonic()
        return None

    def reset_join_rate_limit_for_tests(self) -> None:
        """SOLO per i test — vedi `core.world_sync.reset_client_cooldowns_
        for_tests()`/`core.world_backend.reset_host_cooldowns_for_tests()`
        per lo stesso principio. Mai chiamato da codice applicativo: qui,
        a differenza di quei due (stato di MODULO), lo stato è già di
        ISTANZA — un test che vuole isolamento vero crea semplicemente un
        nuovo `WorldHostServer` per ogni batteria; questo helper serve
        solo a un test che deve inviare più tentativi ravvicinati DELLO
        STESSO device_id allo STESSO host per verificare aspetti diversi
        del comportamento (es. codice errato, poi PIN errato, poi
        successo), senza che il primo esaurisca il cancello anti-spam per
        i successivi."""
        with self._lock:
            self._join_attempts.clear()

    # ------------------------------------------------------------------
    # Token
    # ------------------------------------------------------------------

    def _issue_token(self, device_id: str) -> str:
        token = secrets.token_urlsafe(24)
        with self._lock:
            self._tokens[token] = device_id
        return token

    def _resolve_device_by_token(self, token: str) -> str | None:
        if not token:
            return None
        with self._lock:
            return self._tokens.get(token)
