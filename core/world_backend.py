"""
L'astrazione WorldBackend e la sua implementazione locale — §9.1 e §5 di
`dnd_app/docs/multiplayer_design.md`.

I client non scrivono mai direttamente lo stato del mondo (§5): inviano un
comando, il backend valida i permessi del mittente contro
`core/world_permissions.py`, applica l'effetto al DB e scrive un evento nel
giornale (`world_repo.append_event`). Nessuna dipendenza da Flet, come tutto
`core/*.py`.

`LocalBackend` è l'unica implementazione di questo passo: scrive
direttamente sul DB di QUESTO dispositivo. È quella che userà chi ospita in
LAN (passo 4) e, già oggi, il deploy web — dove i client sono già sullo
stesso processo/DB, quindi questa implementazione basta a rendere il deploy
web "multi-utente vero" (ruoli, permessi, registro) prima ancora che esista
il trasporto di rete per il caso desktop/mobile. `RemoteBackend` (passo 4)
parlerà HTTP con un host e implementerà la stessa interfaccia, così la UI
non deve mai sapere quale delle due sta usando.
"""

from __future__ import annotations

import http.client
import json
import logging
import urllib.parse
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from core import world_permissions as perm
from data.models import WorldEvent
from data.repositories import world_repo
from network import protocol

logger = logging.getLogger(__name__)


@dataclass
class CommandResult:
    """Esito dell'invio di un comando — mai un'eccezione verso il chiamante:
    la UI legge `success`/`error`, coerente con lo stile del resto del
    progetto (repository che non sollevano mai verso la UI)."""
    success: bool
    error: str = ""
    event: WorldEvent | None = None


class WorldBackend(ABC):
    """Interfaccia comune a `LocalBackend` (questo passo) e `RemoteBackend`
    (passo 4, rete LAN)."""

    @abstractmethod
    def send_command(self, world_id: str, actor_device_id: str, kind: str,
                      payload: dict | None = None, target_type: str = "",
                      target_id: str = "") -> CommandResult:
        """Invia un comando a nome di `actor_device_id`. Il ruolo del
        mittente NON è un parametro: va sempre risolto dal backend a partire
        dalla propria tabella `world_members`, mai fidato da chi chiama —
        altrimenti un client compromesso potrebbe dichiararsi owner."""
        raise NotImplementedError

    @abstractmethod
    def fetch_events(self, world_id: str, since_seq: int = 0) -> list[WorldEvent]:
        """Eventi con `seq > since_seq`, in ordine — sincronizzazione
        incrementale (§5)."""
        raise NotImplementedError

    @abstractmethod
    def connection_state(self) -> str:
        """Stato della connessione al mondo — significativo solo per
        `RemoteBackend`; `LocalBackend` è sempre raggiungibile per
        definizione (parla con il proprio DB)."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Registro comandi — estendibile senza toccare LocalBackend (Open/Closed):
# i passi successivi del piano (istanze di personaggio, interventi del
# master, mappe condivise, ...) aggiungono un handler qui o in un modulo
# dedicato che lo registra, mai una modifica alla classe sotto.
# ---------------------------------------------------------------------------

@dataclass
class HandlerContext:
    world_id: str
    actor_device_id: str
    actor_name: str
    actor_role: str
    payload: dict
    target_type: str
    target_id: str


HandlerFunc = Callable[[HandlerContext], CommandResult]

_HANDLERS: dict[str, HandlerFunc] = {}


def register_handler(kind: str) -> Callable[[HandlerFunc], HandlerFunc]:
    """Decoratore per registrare l'handler di un comando. Se `kind` non
    esiste anche in `world_permissions` (`can_perform` sempre False per un
    comando sconosciuto), l'handler non verrà mai raggiunto — la matrice dei
    permessi resta l'unica fonte di verità su cosa è autorizzato."""
    def _decorator(fn: HandlerFunc) -> HandlerFunc:
        if kind in _HANDLERS:
            logger.warning("register_handler: sovrascrittura dell'handler per %r", kind)
        _HANDLERS[kind] = fn
        return fn
    return _decorator


class LocalBackend(WorldBackend):
    """Implementazione senza rete del meccanismo comando -> validazione ->
    evento. Vedi il docstring del modulo."""

    def send_command(self, world_id: str, actor_device_id: str, kind: str,
                      payload: dict | None = None, target_type: str = "",
                      target_id: str = "") -> CommandResult:
        payload = payload or {}

        member = world_repo.get_member(world_id, actor_device_id)
        if member is None:
            return CommandResult(False, "Il mittente non è membro di questo mondo.")

        if not perm.can_perform(member.role, kind):
            return CommandResult(
                False,
                f"Il ruolo «{member.role}» non è autorizzato a eseguire «{kind}».",
            )

        handler = _HANDLERS.get(kind)
        if handler is None:
            return CommandResult(False, f"Comando sconosciuto: «{kind}».")

        ctx = HandlerContext(
            world_id=world_id, actor_device_id=actor_device_id,
            actor_name=member.display_name, actor_role=member.role,
            payload=payload, target_type=target_type, target_id=target_id,
        )
        try:
            return handler(ctx)
        except Exception as e:
            logger.error("Errore applicando il comando %r: %s", kind, e)
            return CommandResult(False, f"Errore interno applicando «{kind}».")

    def fetch_events(self, world_id: str, since_seq: int = 0) -> list[WorldEvent]:
        return world_repo.get_events_since(world_id, since_seq)

    def connection_state(self) -> str:
        return "local"


# ---------------------------------------------------------------------------
# Handler dei comandi owner-only (§4) — gli unici operativi in questo passo:
# non esistono ancora istanze di personaggio (passo 3) su cui applicare le
# azioni master di §7, quindi quei comandi restano registrati nella matrice
# dei permessi ma senza handler finché non arriva quel passo.
# ---------------------------------------------------------------------------

@register_handler(perm.CMD_WORLD_RENAME)
def _handle_world_rename(ctx: HandlerContext) -> CommandResult:
    new_name = str(ctx.payload.get("name", "")).strip()
    if not new_name:
        return CommandResult(False, "Il nuovo nome non può essere vuoto.")
    world = world_repo.get_world(ctx.world_id)
    if world is None:
        return CommandResult(False, "Mondo non trovato.")
    old_name = world.name
    if not world_repo.rename_world(ctx.world_id, new_name):
        return CommandResult(False, "Rinomina fallita.")
    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=perm.CMD_WORLD_RENAME, target_type="world", target_id=ctx.world_id,
        summary=f"{ctx.actor_name} ha rinominato il mondo da «{old_name}» a «{new_name}».",
        payload=json.dumps({"name": new_name}),
        before_state=json.dumps({"name": old_name}),
    )
    return CommandResult(True, event=event)


@register_handler(perm.CMD_WORLD_JOIN_CODE_REGENERATE)
def _handle_regenerate_join_code(ctx: HandlerContext) -> CommandResult:
    new_code = world_repo.regenerate_join_code(ctx.world_id)
    if new_code is None:
        return CommandResult(False, "Rigenerazione del codice fallita.")
    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=perm.CMD_WORLD_JOIN_CODE_REGENERATE, target_type="world",
        target_id=ctx.world_id,
        summary=f"{ctx.actor_name} ha rigenerato il codice d'ingresso del mondo.",
    )
    return CommandResult(True, event=event)


@register_handler(perm.CMD_MEMBER_PROMOTE)
def _handle_member_promote(ctx: HandlerContext) -> CommandResult:
    device_id = str(ctx.payload.get("device_id", ""))
    target = world_repo.get_member(ctx.world_id, device_id)
    if target is None:
        return CommandResult(False, "Membro non trovato.")
    if target.role != perm.ROLE_PLAYER:
        return CommandResult(False, "Solo un giocatore può essere promosso a co-master.")
    if not world_repo.update_member_role(ctx.world_id, device_id, perm.ROLE_MASTER):
        return CommandResult(False, "Promozione fallita.")
    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=perm.CMD_MEMBER_PROMOTE, target_type="member", target_id=target.id,
        summary=f"{ctx.actor_name} ha promosso {target.display_name} a co-master.",
        payload=json.dumps({"device_id": device_id, "role": perm.ROLE_MASTER}),
        before_state=json.dumps({"role": target.role}),
    )
    return CommandResult(True, event=event)


@register_handler(perm.CMD_MEMBER_DEMOTE)
def _handle_member_demote(ctx: HandlerContext) -> CommandResult:
    device_id = str(ctx.payload.get("device_id", ""))
    target = world_repo.get_member(ctx.world_id, device_id)
    if target is None:
        return CommandResult(False, "Membro non trovato.")
    if target.role != perm.ROLE_MASTER:
        return CommandResult(False, "Solo un co-master può essere retrocesso a giocatore.")
    if not world_repo.update_member_role(ctx.world_id, device_id, perm.ROLE_PLAYER):
        return CommandResult(False, "Retrocessione fallita.")
    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=perm.CMD_MEMBER_DEMOTE, target_type="member", target_id=target.id,
        summary=f"{ctx.actor_name} ha retrocesso {target.display_name} a giocatore.",
        payload=json.dumps({"device_id": device_id, "role": perm.ROLE_PLAYER}),
        before_state=json.dumps({"role": target.role}),
    )
    return CommandResult(True, event=event)


@register_handler(perm.CMD_MEMBER_KICK)
def _handle_member_kick(ctx: HandlerContext) -> CommandResult:
    device_id = str(ctx.payload.get("device_id", ""))
    target = world_repo.get_member(ctx.world_id, device_id)
    if target is None:
        return CommandResult(False, "Membro non trovato.")
    if target.role == perm.ROLE_OWNER:
        return CommandResult(False,
                              "L'owner non può essere espulso — trasferisci prima la proprietà.")
    if not world_repo.remove_member(ctx.world_id, device_id):
        return CommandResult(False, "Espulsione fallita.")
    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=perm.CMD_MEMBER_KICK, target_type="member", target_id=target.id,
        summary=f"{ctx.actor_name} ha espulso {target.display_name} dal mondo.",
        payload=json.dumps({"device_id": device_id}),
        before_state=json.dumps({"role": target.role, "display_name": target.display_name}),
    )
    return CommandResult(True, event=event)


def _update_world_owner(world_id: str, new_owner_device_id: str) -> bool:
    """Aggiorna `worlds.owner_device_id` — non esposto in `world_repo` come
    CRUD pubblico perché è significativo SOLO nel contesto di un
    trasferimento di proprietà già validato qui, mai come scrittura diretta
    dalla UI."""
    from data.database import get_connection
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE worlds SET owner_device_id=?, updated_at=? WHERE id=?",
            (new_owner_device_id, datetime.now().isoformat(), world_id),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error("Errore _update_world_owner: %s", e)
        return False


@register_handler(perm.CMD_WORLD_TRANSFER_OWNERSHIP)
def _handle_transfer_ownership(ctx: HandlerContext) -> CommandResult:
    device_id = str(ctx.payload.get("device_id", ""))
    if device_id == ctx.actor_device_id:
        return CommandResult(False, "Sei già l'owner di questo mondo.")
    target = world_repo.get_member(ctx.world_id, device_id)
    if target is None:
        return CommandResult(False, "Membro non trovato.")
    if not world_repo.update_member_role(ctx.world_id, device_id, perm.ROLE_OWNER):
        return CommandResult(False, "Trasferimento fallito.")
    world_repo.update_member_role(ctx.world_id, ctx.actor_device_id, perm.ROLE_MASTER)
    if not _update_world_owner(ctx.world_id, device_id):
        return CommandResult(False, "worlds.owner_device_id non aggiornato.")
    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=perm.CMD_WORLD_TRANSFER_OWNERSHIP, target_type="member", target_id=target.id,
        summary=f"{ctx.actor_name} ha trasferito la proprietà del mondo a {target.display_name}.",
        payload=json.dumps({"new_owner_device_id": device_id}),
    )
    return CommandResult(True, event=event)


@register_handler(perm.CMD_WORLD_DELETE)
def _handle_world_delete(ctx: HandlerContext) -> CommandResult:
    """
    Nessun evento scritto: `world_events` ha `ON DELETE CASCADE` verso
    `worlds`, quindi il giornale stesso sparisce insieme al mondo — non
    esiste un posto dove "mondo eliminato" possa sopravvivere alla
    cancellazione a cui si riferisce.
    """
    if not world_repo.delete_world(ctx.world_id):
        return CommandResult(False, "Eliminazione fallita.")
    return CommandResult(True)


# ---------------------------------------------------------------------------
# RemoteBackend — passo 4: host + client in LAN (§9 del design doc).
# ---------------------------------------------------------------------------

@dataclass
class JoinOutcome:
    """Esito di un tentativo di ingresso in un mondo remoto (§9.4)."""
    status: str  # "approved" | "pending" | "rejected" | "error"
    request_id: str = ""
    error: str = ""


class RemoteBackend(WorldBackend):
    """
    Implementazione di rete di `WorldBackend`: parla HTTP con l'host di un
    mondo (`network/host_server.py`) invece di scrivere sul proprio DB.
    Stessa interfaccia di `LocalBackend` (§9.1) — la UI usa `send_command`/
    `fetch_events`/`connection_state` senza sapere quale delle due sta
    parlando davvero con la rete.

    A differenza di `LocalBackend`, un'istanza è legata a UNA connessione
    verso UN host specifico: `host`/`port` sono l'indirizzo del dispositivo
    che ospita, `token` è consegnato da `join()` e va ripresentato ad ogni
    chiamata autenticata (§9.4). Nessuna dipendenza nuova: solo
    `http.client` della libreria standard (§3.2 del design doc).
    """

    def __init__(self, host: str, port: int, device_id: str, world_id: str = "",
                 timeout: float = 8.0):
        self.host = host
        self.port = port
        self.device_id = device_id
        self.world_id = world_id
        self.timeout = timeout
        self.token: str | None = None
        self._state = "disconnected"  # disconnected|pending|connected|rejected|error

    # -- trasporto --------------------------------------------------------

    def _request(self, method: str, path: str, body: dict | None = None,
                 authed: bool = False, timeout: float | None = None) -> tuple[int, dict]:
        conn = http.client.HTTPConnection(self.host, self.port, timeout=timeout or self.timeout)
        try:
            headers = {"Content-Type": "application/json"}
            if authed and self.token:
                headers["Authorization"] = f"Bearer {self.token}"
            payload = json.dumps(body).encode("utf-8") if body is not None else None
            conn.request(method, path, body=payload, headers=headers)
            resp = conn.getresponse()
            raw = resp.read()
            try:
                data = json.loads(raw.decode("utf-8")) if raw else {}
                if not isinstance(data, dict):
                    data = {}
            except (json.JSONDecodeError, UnicodeDecodeError):
                data = {"error": "Risposta del server non valida (non JSON)."}
            return resp.status, data
        finally:
            conn.close()

    # -- ingresso -----------------------------------------------------------

    def check_world(self) -> dict | None:
        """
        `GET /world` — biglietto da visita, incluso il numero di versione
        del protocollo (§11.6): la UI lo chiama PRIMA di mostrare il
        dialogo del PIN, per rifiutare con un messaggio chiaro
        («aggiorna l'app») se le versioni non combaciano, invece di
        scoprirlo a metà di un tentativo di ingresso. Ritorna None se
        l'host non è raggiungibile — indirizzo/porta sbagliati, o il
        master non sta ospitando in questo momento.
        """
        try:
            status, data = self._request("GET", "/world")
        except (OSError, http.client.HTTPException):
            return None
        if status != 200:
            return None
        return data

    def join(self, join_code: str, pin: str, display_name: str) -> JoinOutcome:
        """Primo passo dell'ingresso (§9.4). Un dispositivo già membro del
        mondo ottiene subito `status="approved"`; un dispositivo nuovo
        ottiene `status="pending"` e un `request_id` da interrogare con
        `poll_join_status()` finché il master non decide."""
        try:
            status, data = self._request("POST", "/join", {
                "join_code": join_code, "pin": pin,
                "device_id": self.device_id, "display_name": display_name,
            })
        except (OSError, http.client.HTTPException) as e:
            self._state = "error"
            return JoinOutcome("error", error=f"Host non raggiungibile: {e}")

        if status != 200:
            self._state = "error"
            return JoinOutcome("error", error=data.get("error", "Ingresso rifiutato."))

        result_status = data.get("status")
        if result_status == "approved":
            self.token = str(data.get("token", ""))
            self._state = "connected"
            return JoinOutcome("approved")
        if result_status == "pending":
            self._state = "pending"
            return JoinOutcome("pending", request_id=str(data.get("request_id", "")))
        self._state = "error"
        return JoinOutcome("error", error="Risposta di ingresso inattesa dall'host.")

    def poll_join_status(self, request_id: str) -> JoinOutcome:
        """Da richiamare mentre `join()` ha ritornato `"pending"` — tipico
        uso: un pulsante «Controlla di nuovo» nella UI, non un ciclo
        automatico (l'attesa dell'approvazione può durare quanto vuole il
        master)."""
        try:
            status, data = self._request(
                "GET", f"/join/status?request_id={urllib.parse.quote(request_id, safe='')}",
            )
        except (OSError, http.client.HTTPException) as e:
            return JoinOutcome("error", error=f"Host non raggiungibile: {e}")
        if status != 200:
            return JoinOutcome("error", error=data.get("error", "Errore di rete."))

        result_status = data.get("status", "unknown")
        if result_status == "approved":
            self.token = str(data.get("token", ""))
            self._state = "connected"
        elif result_status == "rejected":
            self._state = "rejected"
        return JoinOutcome(result_status)

    def reconnect_with_token(self, token: str) -> bool:
        """
        Riconnessione rapida (§11.1/§11.7): riusa un token ottenuto in una
        chiamata precedente invece di rifare l'ingresso con codice+PIN.
        Funziona solo se l'host è ancora lo stesso processo (i token vivono
        in memoria su `WorldHostServer`, azzerati ad ogni `stop()`/riavvio
        — §9.4, nuovo PIN ad ogni apertura): se il token non è più valido,
        torna `False` e la UI deve chiedere di nuovo codice+PIN, non deve
        insistere in automatico con le stesse credenziali scadute.
        """
        self.token = token
        try:
            status, _data = self._request("GET", "/snapshot", authed=True)
        except (OSError, http.client.HTTPException):
            self.token = None
            self._state = "error"
            return False
        if status == 200:
            self._state = "connected"
            return True
        self.token = None
        self._state = "disconnected"
        return False

    def leave(self) -> None:
        if self.token:
            try:
                self._request("POST", "/leave", authed=True)
            except (OSError, http.client.HTTPException):
                pass  # uscita "best effort": l'host scopre comunque la disconnessione
        self.token = None
        self._state = "disconnected"

    def get_snapshot(self) -> dict | None:
        """`GET /snapshot` — stato completo del mondo (§9.2: "per il primo
        ingresso o dopo una lunga assenza"). In questo passo copre mondo +
        membri + giornale eventi: non esistono ancora comandi sulle
        istanze di personaggio da sincronizzare (passo 6)."""
        if self.token is None:
            return None
        try:
            status, data = self._request("GET", "/snapshot", authed=True)
        except (OSError, http.client.HTTPException):
            return None
        if status != 200:
            return None
        return data

    # -- WorldBackend -------------------------------------------------------

    def send_command(self, world_id: str, actor_device_id: str, kind: str,
                      payload: dict | None = None, target_type: str = "",
                      target_id: str = "") -> CommandResult:
        if self.token is None:
            return CommandResult(False, "Non connesso al mondo — entra di nuovo.")
        try:
            status, data = self._request("POST", "/command", {
                "kind": kind, "payload": payload or {},
                "target_type": target_type, "target_id": target_id,
            }, authed=True)
        except (OSError, http.client.HTTPException) as e:
            self._state = "error"
            return CommandResult(False, f"Host non raggiungibile: {e}")

        if status == 401:
            self._state = "disconnected"
            self.token = None
            return CommandResult(False, "Sessione scaduta: entra di nuovo nel mondo.")
        if status != 200:
            return CommandResult(False, data.get("error", "Comando rifiutato dall'host."))

        event = protocol.event_from_dict(data["event"]) if data.get("event") else None
        return CommandResult(bool(data.get("success")), str(data.get("error", "")), event)

    def fetch_events(self, world_id: str, since_seq: int = 0) -> list[WorldEvent]:
        """Interroga senza attesa lunga (`wait=0`): la sincronizzazione
        periodica vera e propria (`core.world_sync.sync_replica`) decide
        essa stessa quanto aspettare, questo metodo resta un mattone
        semplice e non bloccante di default."""
        if self.token is None:
            return []
        try:
            status, data = self._request(
                "GET", f"/events?since={int(since_seq)}&wait=0", authed=True,
            )
        except (OSError, http.client.HTTPException):
            self._state = "error"
            return []
        if status == 401:
            self._state = "disconnected"
            self.token = None
            return []
        if status != 200:
            return []
        return [protocol.event_from_dict(e) for e in data.get("events", [])]

    def connection_state(self) -> str:
        return self._state
