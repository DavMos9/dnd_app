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

Copriva SOLO gli eventi di gestione del mondo (rinomina, promuovi/
retrocedi/espelli, trasferimento di proprietà, ingresso di un membro) fino
al passo 4. **Dal passo 6** (2026-08-06, Multiplayer §7) copre anche gli
eventi che mutano un'istanza di personaggio (PE, danno, cura, condizioni,
risorse di classe, abilità custom, incantesimo bonus, voce di diario,
risposta a una richiesta di modifica) e le richieste di modifica stesse
(§7.1): per questi non basta applicare un campo alla volta come per gli
eventi di mondo — la scelta è **rimaterializzare l'intero personaggio**
scaricandolo di nuovo da `GET /character/<id>` e riscrivendolo con
`character_export.import_replica_character()`, riusando lo stesso modulo
già collaudato per `.dndchar` e per la copia di un'istanza (passo 3) invece
di duplicare, evento per evento, la logica di scrittura di ciascuna delle
12 tabelle figlio coinvolte — la stessa classe di bug (una tabella
dimenticata in un punto ma non nell'altro) che l'introspezione dello
schema in `character_export.py` esiste apposta per eliminare.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from core import world_permissions as perm
from data.models import World, WorldChangeRequest, WorldEvent
from data.repositories import character_export, world_repo
from network import protocol

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Applicazione di un evento alla replica
# ---------------------------------------------------------------------------

def apply_event_to_replica(local_world_id: str, event: WorldEvent, remote_backend=None) -> None:
    """
    Applica un singolo evento del giornale alla replica locale.

    `remote_backend` (Multiplayer passo 6, opzionale — `None` per
    compatibilità con i chiamanti del passo 4 che non lo passano):
    necessario SOLO per gli eventi che mutano un'istanza di personaggio
    (`core.world_permissions.CHARACTER_MUTATING_COMMANDS`) o una richiesta
    di modifica — per rimaterializzare il personaggio serve scaricarlo di
    nuovo dall'host (`RemoteBackend.get_character()`), non basta il
    payload dell'evento. Se `None` e serve, l'evento viene comunque
    registrato nel giornale locale dal chiamante (`sync_replica()`) ma il
    personaggio non si aggiorna finché non arriva una sincronizzazione con
    un backend valido — degradato, non un crash.

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
        # I due rami seguenti non sono mutuamente esclusivi:
        # change_request.respond è SIA in CHARACTER_MUTATING_COMMANDS (se
        # accettata, muta il personaggio — va rimaterializzato) SIA
        # l'evento che chiude la richiesta stessa (va segnata risolta) —
        # entrambe le scritture devono avvenire per quell'evento, quindi
        # niente `elif` tra i due.
        if event.kind in perm.CHARACTER_MUTATING_COMMANDS and event.target_type == "character":
            _resync_character_from_host(remote_backend, event.target_id, event.seq)

        if event.kind == perm.CMD_CHANGE_REQUEST_PROPOSE:
            # Il payload scritto da _handle_change_request_propose() porta
            # già request_id/changes/reason; il resto si ricostruisce dagli
            # altri campi dell'evento stesso (§7.1 non ha bisogno di altro
            # lato replica: la UI del giocatore la mostra e basta).
            request_id = str(payload.get("request_id", ""))
            if request_id:
                world_repo.save_replica_change_request(WorldChangeRequest(
                    id=request_id, world_id=local_world_id,
                    character_id=event.target_id, requested_by=event.actor_device_id,
                    payload=json.dumps(payload.get("changes", {})),
                    reason=str(payload.get("reason", "")),
                    status="pending", created_at=event.created_at,
                ))

        elif event.kind == perm.CMD_CHANGE_REQUEST_RESPOND:
            request_id = str(payload.get("request_id", ""))
            accept = bool(payload.get("accept", False))
            if request_id:
                world_repo.resolve_change_request(
                    request_id, "accepted" if accept else "rejected",
                )

        elif event.kind == "world.rename":
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

        elif event.kind in perm.CHARACTER_MUTATING_COMMANDS:
            # xp.grant/hp.damage/hp.heal/condition.*/resource.*/
            # custom_ability.grant/bonus_spell.grant/diary.add_entry: già
            # gestiti dal ramo di rimaterializzazione in cima alla funzione
            # (non un `elif` di quello, per il motivo spiegato lì sopra) —
            # questo ramo esiste solo per non farli cadere nell'`else`
            # "evento non gestito" qui sotto, che sarebbe un log fuorviante.
            pass

        else:
            logger.info(
                "apply_event_to_replica: evento %r (seq %s) non ancora gestito "
                "da questo passo, ignorato.", event.kind, event.seq,
            )
    except Exception as e:
        logger.error("Errore apply_event_to_replica su seq=%s kind=%r: %s",
                     event.seq, event.kind, e)


def _resync_character_from_host(remote_backend, character_id: str, seq: int) -> None:
    """
    Riscarica per intero un'istanza di personaggio dall'host
    (`RemoteBackend.get_character()`) e la rimaterializza sulla replica
    locale (`character_export.import_replica_character()`) — Multiplayer
    passo 6.

    Se `character_id` è vuoto, `remote_backend` è `None` (nessun trasporto
    disponibile — es. `apply_event_to_replica()` chiamato da un test in
    isolamento) o l'host risponde "non trovato"/"non tuo" (403/404, l'host
    filtra già per proprietario in `handle_get_character()`), la funzione
    non fa nulla: **non è un errore da sollevare**, è il caso normale per
    un evento su un personaggio di CUI QUESTO DISPOSITIVO NON È IL
    PROPRIETARIO (il giornale del mondo contiene gli eventi di TUTTI i
    personaggi, non solo del proprio — un giocatore vede comunque il
    `summary` leggibile dell'evento nel registro, ma non ha né deve avere
    una replica della scheda di un altro).
    """
    if not character_id or remote_backend is None:
        return
    data = remote_backend.get_character(character_id)
    if data is None:
        return
    character_export.import_replica_character(data, character_id, world_seq=seq)


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
        apply_event_to_replica(local_world_id, event, remote_backend=remote_backend)
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
    """
    Ingresso approvato: semina la replica locale con l'intero snapshot
    (mondo, membri, giornale) — così è leggibile offline fin dal primo
    momento, non solo dal prossimo evento in poi (§6).

    Dal passo 6 (Multiplayer, 2026-08-06) semina anche le istanze di
    personaggio DI CUI QUESTO DISPOSITIVO È PROPRIETARIO
    (`snapshot["characters"]`, già filtrate lato host —
    `WorldHostServer.handle_snapshot()`) e le richieste di modifica in
    sospeso che le riguardano (`snapshot["change_requests"]`): senza
    questo, un dispositivo appena entrato non avrebbe alcuna copia locale
    della propria scheda su cui applicare gli eventi successivi.
    """
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

    for char_data in snapshot.get("characters", []):
        char_row = char_data.get("character") or {}
        character_id = str(char_row.get("id") or "")
        if character_id:
            character_export.import_replica_character(char_data, character_id, world_seq=latest_seq)

    for req_data in snapshot.get("change_requests", []):
        request_id = str(req_data.get("id") or "")
        if request_id:
            world_repo.save_replica_change_request(protocol.change_request_from_dict(req_data))

    return LanJoinResult(True, world=world_repo.get_world(world.id), backend=backend)
