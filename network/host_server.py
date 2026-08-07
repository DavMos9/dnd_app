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

Il server si accende solo quando il master apre l'hosting e si spegne alla
chiusura (§9.4: "nessuna porta aperta di default").
"""

from __future__ import annotations

import json
import logging
import secrets
import socket
import threading
import time
import urllib.parse
import uuid as _uuid
from dataclasses import dataclass, field
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from core import world_permissions as perm
from core.world_backend import LocalBackend
from data.repositories import character_repo, world_repo
from data.repositories import character_export
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


class WorldHostServer:
    """
    Ciclo di vita e stato dell'hosting di UN mondo su questo dispositivo.
    Un'istanza per mondo ospitato — la UI ne crea una quando il master
    preme "Ospita in LAN" e la ferma alla chiusura (§9.4).
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
        #: Anti-spam su `/join` (fix 2026-08-07, completamento della difesa
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
        joined = world_repo.join_world_by_code(world.join_code, req.device_id, req.display_name)
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

    def reject(self, request_id: str) -> bool:
        with self._lock:
            req = self._pending.get(request_id)
            if req is None or req.status != "pending":
                return False
            req.status = "rejected"
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
        }

    def handle_join(self, body: dict) -> tuple[int, dict]:
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
        if not self.pin or pin != self.pin:
            return 403, {"error": "PIN errato."}

        member = world_repo.get_member(self.world_id, device_id)
        if member is not None:
            # Dispositivo già noto: rientra senza approvazione del master
            # (§9.4: "I dispositivi già noti rientrano senza chiedere").
            token = self._issue_token(device_id)
            world_repo.set_member_connected(self.world_id, device_id, True)
            return 200, {"status": "approved", "token": token, "role": member.role}

        # Nuovo dispositivo: in coda per l'approvazione esplicita del
        # master (§9.4: «Marco vuole entrare»).
        req = PendingJoinRequest(id=str(_uuid.uuid4()), device_id=device_id,
                                  display_name=display_name)
        with self._lock:
            self._pending[req.id] = req
        return 200, {"status": "pending", "request_id": req.id}

    def join_status(self, request_id: str) -> dict:
        with self._lock:
            req = self._pending.get(request_id)
        if req is None:
            return {"status": "unknown"}
        if req.status == "approved":
            return {"status": "approved", "token": req.token, "role": req.role}
        if req.status == "rejected":
            return {"status": "rejected"}
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
        events = world_repo.get_events_since(self.world_id, 0)
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
        return 200, {
            "world": protocol.world_to_dict(world),
            "members": [protocol.member_to_dict(m) for m in members],
            "events": [protocol.event_to_dict(e) for e in events],
            "characters": exports,
            "change_requests": change_requests,
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
