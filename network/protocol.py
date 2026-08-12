"""
Formato di rete condiviso tra host e client — passo 4 di
`dnd_app/docs/multiplayer_design.md` (§9).

Un solo posto dove vivono la versione del protocollo (§11.6, controllata
all'ingresso per rifiutare con un messaggio chiaro invece di fallire a metà
partita), le porte di default (§9.2: "8765, con ripiego sulle successive") e
il timeout dell'attesa lunga (§9.2/§12.3 — 25 s è una stima, non un valore
misurato: se un router reale la taglia prima, si abbassa qui in un solo
punto). La (de)serializzazione JSON degli eventi/mondo/membri vive qui
perché sia `network/host_server.py` (lato host) sia `core/world_backend.py`
(`RemoteBackend`, lato client) sia `core/world_sync.py` (applicazione degli
eventi sulla replica) ne hanno bisogno — un solo formato, non tre copie che
potrebbero disallinearsi.
"""

from __future__ import annotations

from data.models import World, WorldChangeRequest, WorldEvent, WorldMember, WorldRejoinRequest

#: Incrementare ad ogni cambio non retrocompatibile del formato delle rotte
#: HTTP o del payload JSON. `GET /world` lo espone; il client lo confronta
#: PRIMA di mostrare il dialogo del PIN (§11.6).
PROTOCOL_VERSION = 1

#: §9.2 — porta di partenza per l'host, con ripiego sulle 5 successive se
#: occupata (es. da un'altra istanza dell'app, o da un mondo ospitato in
#: precedenza non ancora rilasciato dal sistema operativo).
DEFAULT_PORT_RANGE = range(8765, 8771)

#: §9.3/§13 (passo 5) — porta UDP dedicata all'annuncio broadcast della
#: scoperta automatica, distinta dalla porta TCP dell'host (che varia
#: nell'intervallo sopra): un client in ascolto deve sapere DOVE ascoltare
#: senza già conoscere la porta specifica scelta dall'host.
DISCOVERY_PORT = 8766

#: Intervallo tra due annunci broadcast successivi (§9.3: "ogni 2 s").
DISCOVERY_ANNOUNCE_INTERVAL_S = 2.0

#: Prefisso del payload broadcast — un client che riceve pacchetti UDP non
#: suoi su questa porta (rumore di rete, un'altra applicazione) li scarta
#: subito senza tentare `json.loads()` su dati non pertinenti.
DISCOVERY_MAGIC = "dnd_companion_world_v1"

#: §9.2/§12.3 — durata dell'attesa lunga di GET /events. Stima di partenza,
#: non un valore misurato su una rete reale: se un router chiude le
#: connessioni ferme prima, Davide lo scoprirà nel passo 4 e va abbassato
#: qui, in un solo punto (nessuna riprogettazione).
LONG_POLL_TIMEOUT_S = 25.0

#: Intervallo di ripolling interno del server durante l'attesa lunga: non è
#: una vera notifica push (nessuna dipendenza nuova, §3.2), è un controllo
#: periodico del giornale mentre la connessione HTTP resta aperta.
LONG_POLL_INTERVAL_S = 0.2


def event_to_dict(event: WorldEvent) -> dict:
    return {
        "seq": event.seq,
        "id": event.id,
        "world_id": event.world_id,
        "actor_device_id": event.actor_device_id,
        "actor_name": event.actor_name,
        "kind": event.kind,
        "target_type": event.target_type,
        "target_id": event.target_id,
        "summary": event.summary,
        "payload": event.payload,
        "before_state": event.before_state,
        "created_at": event.created_at,
    }


def event_from_dict(d: dict) -> WorldEvent:
    return WorldEvent(
        seq=int(d.get("seq") or 0),
        id=str(d.get("id", "")),
        world_id=str(d.get("world_id", "")),
        actor_device_id=str(d.get("actor_device_id", "")),
        actor_name=str(d.get("actor_name", "")),
        kind=str(d.get("kind", "")),
        target_type=str(d.get("target_type", "")),
        target_id=str(d.get("target_id", "")),
        summary=str(d.get("summary", "")),
        payload=str(d.get("payload", "{}")),
        before_state=str(d.get("before_state", "{}")),
        created_at=str(d.get("created_at", "")),
    )


def world_to_dict(world: World) -> dict:
    """
    Solo i campi significativi per un client remoto: `is_local_host`/
    `last_seen_host`/`last_synced_seq` sono locali a CIASCUN dispositivo
    (chi ospita ha `is_local_host=True` per definizione, un client lo
    imposta a False per sé al momento del salvataggio della replica) e non
    hanno senso "trasmessi" da un dispositivo all'altro.
    """
    return {
        "id": world.id,
        "name": world.name,
        "description": world.description,
        "owner_device_id": world.owner_device_id,
        "join_code": world.join_code,
    }


def member_to_dict(member: WorldMember) -> dict:
    return {
        "id": member.id,
        "world_id": member.world_id,
        "device_id": member.device_id,
        "display_name": member.display_name,
        "role": member.role,
        "is_connected": member.is_connected,
        "last_seen_at": member.last_seen_at,
        "created_at": member.created_at,
    }


def member_from_dict(d: dict) -> WorldMember:
    return WorldMember(
        id=str(d.get("id", "")),
        world_id=str(d.get("world_id", "")),
        device_id=str(d.get("device_id", "")),
        display_name=str(d.get("display_name", "")),
        role=str(d.get("role", "player")),
        is_connected=bool(d.get("is_connected", False)),
        last_seen_at=str(d.get("last_seen_at", "")),
    )


def change_request_to_dict(request: WorldChangeRequest) -> dict:
    """Multiplayer passo 6 — trasmette una richiesta di modifica (§7.1) al
    giocatore proprietario del personaggio bersaglio via `GET /snapshot`."""
    return {
        "id": request.id,
        "world_id": request.world_id,
        "character_id": request.character_id,
        "requested_by": request.requested_by,
        "payload": request.payload,
        "reason": request.reason,
        "status": request.status,
        "created_at": request.created_at,
        "resolved_at": request.resolved_at,
    }


def change_request_from_dict(d: dict) -> WorldChangeRequest:
    return WorldChangeRequest(
        id=str(d.get("id", "")),
        world_id=str(d.get("world_id", "")),
        character_id=str(d.get("character_id", "")),
        requested_by=str(d.get("requested_by", "")),
        payload=str(d.get("payload", "{}")),
        reason=str(d.get("reason", "")),
        status=str(d.get("status", "pending")),
        created_at=str(d.get("created_at", "")),
        resolved_at=str(d.get("resolved_at", "")),
    )


def rejoin_request_to_dict(request: WorldRejoinRequest) -> dict:
    """"Richiesta di rientro" (2026-08-12) — trasmette la richiesta del
    proprietario di far rientrare un'istanza archiviata al mondo via
    `GET /snapshot`, stesso principio di `change_request_to_dict` sopra ma
    verso opposto (qui il master è il destinatario, non il proprietario)."""
    return {
        "id": request.id,
        "world_id": request.world_id,
        "character_id": request.character_id,
        "requested_by": request.requested_by,
        "requester_name": request.requester_name,
        "mode": request.mode,
        "payload": request.payload,
        "reason": request.reason,
        "status": request.status,
        "created_at": request.created_at,
        "resolved_at": request.resolved_at,
    }


def rejoin_request_from_dict(d: dict) -> WorldRejoinRequest:
    return WorldRejoinRequest(
        id=str(d.get("id", "")),
        world_id=str(d.get("world_id", "")),
        character_id=str(d.get("character_id", "")),
        requested_by=str(d.get("requested_by", "")),
        requester_name=str(d.get("requester_name", "")),
        mode=str(d.get("mode", "frozen")),
        payload=str(d.get("payload", "{}")),
        reason=str(d.get("reason", "")),
        status=str(d.get("status", "pending")),
        created_at=str(d.get("created_at", "")),
        resolved_at=str(d.get("resolved_at", "")),
    )
