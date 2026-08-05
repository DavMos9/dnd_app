"""
Sincronizzazione della replica locale di un mondo remoto — passo 4 di
`dnd_app/docs/multiplayer_design.md` (§4, §9).

Un dispositivo che entra in un mondo ospitato altrove tiene una copia
locale di `worlds`/`world_members`/`world_events` (§4: "sul dispositivo del
giocatore sono repliche, aggiornate dagli eventi" — e §6: "un'istanza di
cui hai una replica resta leggibile offline"). Questo modulo è l'unico
punto che orchestra `core.world_backend.RemoteBackend` (trasporto) insieme
a `data.repositories.world_repo` (scrittura della replica): la UI non
applica mai un evento da sola.

Copre SOLO gli eventi già esistenti in questo passo (gestione del mondo:
rinomina, promuovi/retrocedi/espelli, trasferimento di proprietà, ingresso
di un membro). Gli eventi sulle istanze di personaggio (assegna PE, applica
danno, ...) arriveranno dal passo 6 insieme ai loro handler in
`core/world_backend.py`: quando esisteranno, basterà un ramo in più in
`apply_event_to_replica()`, questo modulo non va riprogettato.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from data.models import World, WorldEvent
from data.repositories import world_repo
from network import protocol

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Applicazione di un evento alla replica
# ---------------------------------------------------------------------------

def apply_event_to_replica(local_world_id: str, event: WorldEvent) -> None:
    """
    Applica un singolo evento del giornale alla replica locale.

    Non solleva mai verso il chiamante: un evento di un tipo non ancora
    gestito qui viene ignorato con un log, non blocca l'applicazione degli
    altri — un client con una versione più vecchia dell'app non deve
    bloccarsi su un `kind` che ancora non conosce (il caso più grave, un
    protocollo davvero incompatibile, è già intercettato a monte dal
    controllo versione di `RemoteBackend.check_world()`, §11.6).
    """
    try:
        payload = json.loads(event.payload or "{}")
    except (json.JSONDecodeError, TypeError):
        payload = {}

    try:
        if event.kind == "world.rename":
            new_name = payload.get("name")
            if new_name:
                world_repo.rename_world(local_world_id, new_name)

        elif event.kind in ("member.promote", "member.demote"):
            device_id = payload.get("device_id", "")
            new_role = payload.get("role", "")
            if device_id and new_role:
                world_repo.update_member_role(local_world_id, device_id, new_role)

        elif event.kind == "member.kick":
            device_id = payload.get("device_id", "")
            if device_id:
                world_repo.remove_replica_member(local_world_id, device_id)

        elif event.kind == "world.transfer_ownership":
            new_owner = payload.get("new_owner_device_id", "")
            if new_owner:
                world_repo.update_member_role(local_world_id, new_owner, "owner")
                world_repo.update_member_role(local_world_id, event.actor_device_id, "master")
                _update_replica_owner(local_world_id, new_owner)

        elif event.kind in ("world.created", "world.join_code.regenerate", "member.joined"):
            # "world.created": già applicato dal join iniziale (snapshot).
            # "world.join_code.regenerate": il nuovo codice non viaggia nel
            #   payload (l'handler in world_backend.py non lo scrive) — è
            #   rilevante solo per l'owner, che lo legge dalla propria UI
            #   di hosting, non dalla replica. Nessuna azione è corretta.
            # "member.joined": il payload non porta i dati del nuovo
            #   membro; `sync_replica()` li recupera con lo snapshot dei
            #   membri invece che da questo evento.
            pass

        else:
            logger.info(
                "apply_event_to_replica: evento %r (seq %s) non ancora gestito "
                "da questo passo, ignorato.", event.kind, event.seq,
            )
    except Exception as e:
        logger.error("Errore apply_event_to_replica su seq=%s kind=%r: %s",
                     event.seq, event.kind, e)


def _update_replica_owner(world_id: str, new_owner_device_id: str) -> None:
    """`worlds.owner_device_id` non ha un setter pubblico in `world_repo`
    (stessa scelta di `core.world_backend._update_world_owner`, che lo
    scrive sull'host dopo la validazione): qui rispecchia un evento già
    validato altrove, stesso principio delle altre funzioni `save_replica_*`."""
    from datetime import datetime

    from data.database import get_connection
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE worlds SET owner_device_id=?, updated_at=? WHERE id=?",
            (new_owner_device_id, datetime.now().isoformat(), world_id),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error("Errore _update_replica_owner: %s", e)


def sync_replica(remote_backend, local_world_id: str, refresh_members: bool = True) -> int:
    """
    Ciclo di sincronizzazione incrementale: recupera gli eventi con
    `seq > last_synced_seq`, li applica in ordine, ne salva una copia
    locale (così il giornale resta leggibile offline, §6), e aggiorna
    `last_synced_seq`. Ritorna il numero di eventi applicati.

    `refresh_members=True` (default) rilegge anche l'elenco membri intero
    da `GET /snapshot` invece di fidarsi solo degli eventi applicati: più
    robusto per un client tornato online dopo un evento di tipo ancora
    sconosciuto a questa versione dell'app (il ramo "else" sopra), al
    costo di una chiamata di rete in più — accettabile alla frequenza di
    polling già in uso nel progetto (§14.4, stesso ordine di grandezza del
    polling di `home_view.py`).
    """
    world = world_repo.get_world(local_world_id)
    if world is None:
        logger.warning("sync_replica: mondo locale %r non trovato", local_world_id)
        return 0

    events = remote_backend.fetch_events(local_world_id, since_seq=world.last_synced_seq)
    if not events:
        return 0

    for event in events:
        apply_event_to_replica(local_world_id, event)
        world_repo.save_replica_event(event)

    latest_seq = max(e.seq for e in events)
    world_repo.update_last_synced_seq(local_world_id, latest_seq)

    if refresh_members:
        _refresh_members_from_snapshot(remote_backend, local_world_id)

    return len(events)


def _refresh_members_from_snapshot(remote_backend, local_world_id: str) -> None:
    snapshot = remote_backend.get_snapshot()
    if snapshot is None:
        return
    incoming_members = snapshot.get("members", [])
    for m in incoming_members:
        world_repo.save_replica_member(protocol.member_from_dict(m))
    still_present = {m.get("device_id") for m in incoming_members}
    for local_member in world_repo.get_members(local_world_id):
        if local_member.device_id not in still_present:
            world_repo.remove_replica_member(local_world_id, local_member.device_id)


# ---------------------------------------------------------------------------
# Ingresso in un mondo LAN — orchestrazione lato client
# ---------------------------------------------------------------------------

@dataclass
class LanJoinResult:
    """Esito di un tentativo di ingresso in un mondo ospitato in LAN,
    pensato per essere consumato direttamente dalla UI (§9.4)."""
    success: bool
    world: World | None = None
    backend: object | None = None       # RemoteBackend — tipizzato `object` per
                                         # evitare un import circolare con core.world_backend
    pending_request_id: str = ""
    error: str = ""


def start_lan_join(host: str, port: int, join_code: str, pin: str,
                    device_id: str, display_name: str) -> LanJoinResult:
    """
    Primo passo dell'ingresso in un mondo in LAN (§9.3/§9.4):
    1. `GET /world` — verifica che l'host risponda e che la versione del
       protocollo combaci (§11.6), PRIMA di spendere il tentativo di join.
    2. `POST /join` — codice + PIN + identità.

    Se il dispositivo è già membro noto del mondo, l'ingresso è
    immediato e questa funzione ritorna già con `success=True`. Se è
    nuovo, ritorna con `pending_request_id` valorizzato: la UI deve
    richiamare `finish_pending_join()` (tipicamente con un pulsante
    «Controlla di nuovo») finché il master non approva o rifiuta.
    """
    from core.world_backend import RemoteBackend

    backend = RemoteBackend(host, port, device_id)
    info = backend.check_world()
    if info is None:
        return LanJoinResult(False, error="Host non raggiungibile: verifica indirizzo e porta.")

    host_version = info.get("protocol_version")
    if host_version != protocol.PROTOCOL_VERSION:
        return LanJoinResult(
            False,
            error=(
                f"Versione del protocollo non compatibile (host: {host_version}, "
                f"questa app: {protocol.PROTOCOL_VERSION}). Aggiorna l'app su "
                f"entrambi i dispositivi."
            ),
        )
    if not info.get("accepting", False):
        return LanJoinResult(False, error="Il master non sta accettando ingressi in questo momento.")

    backend.world_id = str(info.get("world_id", ""))

    outcome = backend.join(join_code, pin, display_name)
    if outcome.status == "error":
        return LanJoinResult(False, error=outcome.error)
    if outcome.status == "pending":
        return LanJoinResult(
            False, backend=backend, pending_request_id=outcome.request_id,
            error="In attesa dell'approvazione del master.",
        )
    return _finalize_join(backend, f"{host}:{port}")


def finish_pending_join(backend, request_id: str, host_port: str) -> LanJoinResult:
    """Da richiamare a intervalli (azione manuale della UI, non un ciclo
    automatico) finché lo stato resta `"pending"`."""
    outcome = backend.poll_join_status(request_id)
    if outcome.status == "approved":
        return _finalize_join(backend, host_port)
    if outcome.status == "rejected":
        return LanJoinResult(False, error="Il master ha rifiutato la richiesta di ingresso.")
    if outcome.status == "error":
        return LanJoinResult(False, backend=backend, pending_request_id=request_id,
                              error=outcome.error)
    return LanJoinResult(False, backend=backend, pending_request_id=request_id,
                          error="In attesa dell'approvazione del master.")


def _finalize_join(backend, host_port: str) -> LanJoinResult:
    """Ingresso approvato: semina la replica locale con l'intero snapshot
    (mondo, membri, giornale) — così è leggibile offline fin dal primo
    momento, non solo dal prossimo evento in poi (§6)."""
    snapshot = backend.get_snapshot()
    if snapshot is None:
        return LanJoinResult(False, backend=backend,
                              error="Ingresso riuscito ma lo scaricamento dello stato del "
                                    "mondo è fallito. Riprova.")

    world_data = snapshot.get("world", {})
    events = [protocol.event_from_dict(e) for e in snapshot.get("events", [])]
    latest_seq = max((e.seq for e in events), default=0)

    world = World(
        id=world_data.get("id", backend.world_id),
        name=world_data.get("name", ""),
        description=world_data.get("description", ""),
        owner_device_id=world_data.get("owner_device_id", ""),
        join_code=world_data.get("join_code", ""),
        is_local_host=False,
        last_seen_host=host_port,
        last_synced_seq=latest_seq,
    )
    if not world_repo.save_replica_world(world):
        return LanJoinResult(False, backend=backend,
                              error="Salvataggio della replica del mondo fallito.")

    for m in snapshot.get("members", []):
        world_repo.save_replica_member(protocol.member_from_dict(m))
    for event in events:
        world_repo.save_replica_event(event)

    return LanJoinResult(True, world=world_repo.get_world(world.id), backend=backend)
