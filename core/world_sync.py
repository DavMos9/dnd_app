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
import time
from dataclasses import dataclass, field

from core import world_permissions as perm
from data.models import World, WorldChangeRequest, WorldEvent, WorldRejoinRequest
from data.repositories import character_export, maps_repo, master_repo, world_repo
from network import protocol

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Anti-spam lato client — stato di MODULO, fix 2026-08-07 (rivisto due
# volte nella stessa giornata).
#
# Prima versione: timer tenuti come attributi di istanza su `WorldsView`/
# `HomeView`. Bug trovato chiedendo un parere su questa stessa
# implementazione: `ui/app.py::_show_worlds_view()`/`_show_home()` creano
# un'istanza NUOVA della view ad ogni navigazione — e anche ad ogni cambio
# tema, che passa dallo stesso `_rebuild_route` — quindi uno stato
# sull'istanza si azzerava ad ogni ricreazione, rendendo il limite
# aggirabile senza nemmeno volerlo. Un'istanza di modulo sopravvive per
# tutta la durata del processo, che è esattamente ciò che serve a un
# guardrail "non permettere all'utente di spammare" (Davide).
#
# Costanti e aritmetica pura (`MASTER_ACTION_COOLDOWN_S`/
# `NETWORK_REQUEST_COOLDOWN_S`/`cooldown_remaining()`) vivono in
# `core.world_permissions`, non qui: servono anche lato HOST
# (`core.world_backend.LocalBackend`, `network.host_server.WorldHostServer`
# — difesa in profondità, stessa richiesta di Davide), e quel modulo è la
# base dipendenza-zero già condivisa da client e host. Qui vive SOLO lo
# stato lato client.
#
# Il timer del master (`MASTER_ACTION_COOLDOWN_S`, 3s) è ora PER
# PERSONAGGIO (`master_action_last_at: dict[character_id, float]`), non un
# solo timer globale sulla sezione: un'area che colpisce 4 PG non
# costringe il master ad aspettare 3s tra un personaggio e l'altro, il
# limite blocca solo il martellare ripetuto sullo STESSO personaggio
# (revisione richiesta da Davide dopo un parere sulla prima versione, che
# era un timer unico su tutta la sezione).
# ---------------------------------------------------------------------------

@dataclass
class _ClientCooldownState:
    master_action_last_at: dict[str, float] = field(default_factory=dict)  # character_id -> float
    network_request_last_at: float = 0.0     # ingresso in un mondo (codice/LAN/QR) + retry
    instance_push_last_at: float = 0.0       # HomeView._push_instance_to_host
    #: hp.self_update (fix 2026-08-07) — per personaggio come master_action,
    #: ma usato per DECIDERE quando è il momento di inviare (debounce in
    #: `CombattimentoTab`), mai per bloccare l'azione locale sulla scheda.
    hp_self_update_last_at: dict[str, float] = field(default_factory=dict)
    #: condition.self_apply/self_remove (2026-08-07, estensione graduale di
    #: hp.self_update) — per personaggio, usato solo per non martellare
    #: l'host con click ripetuti ravvicinati: l'azione locale (aggiungi/
    #: rimuovi condizione sulla propria scheda) non è mai bloccata da
    #: questo cooldown.
    condition_self_update_last_at: dict[str, float] = field(default_factory=dict)


_client_cooldowns = _ClientCooldownState()


def master_action_cooldown_remaining(character_id: str) -> float:
    """Secondi rimanenti prima che il master possa agire di nuovo su
    QUESTO personaggio (PE/danno/cura/condizione/abilità/incantesimo/
    diario/proponi modifica — vedi `_remote_character_row`)."""
    last_at = _client_cooldowns.master_action_last_at.get(character_id, 0.0)
    return perm.cooldown_remaining(last_at, perm.MASTER_ACTION_COOLDOWN_S)


def mark_master_action(character_id: str) -> None:
    _client_cooldowns.master_action_last_at[character_id] = time.monotonic()


def network_request_cooldown_remaining() -> float:
    """Secondi rimanenti prima del prossimo tentativo di ingresso in un
    mondo o controllo di una richiesta in sospeso — un solo tracciato
    condiviso tra `_join`/`_attempt`/`_retry` (tutte "richieste di rete
    semplici" per Davide, non categorie separate)."""
    return perm.cooldown_remaining(
        _client_cooldowns.network_request_last_at, perm.NETWORK_REQUEST_COOLDOWN_S,
    )


def mark_network_request() -> None:
    _client_cooldowns.network_request_last_at = time.monotonic()


def instance_push_cooldown_remaining() -> float:
    """Secondi rimanenti prima del prossimo invio di
    `HomeView._push_instance_to_host()` — tracciato indipendente da quello
    sopra (classe/istanza diversa, stesso valore di 10s)."""
    return perm.cooldown_remaining(
        _client_cooldowns.instance_push_last_at, perm.NETWORK_REQUEST_COOLDOWN_S,
    )


def mark_instance_push() -> None:
    _client_cooldowns.instance_push_last_at = time.monotonic()


def hp_self_update_cooldown_remaining(character_id: str) -> float:
    """Secondi rimanenti prima del prossimo invio automatico dei PF di
    QUESTO personaggio verso l'host (`CombattimentoTab`, fix 2026-08-07).
    Usato solo per decidere quando spedire (debounce), mai per bloccare
    l'azione locale del giocatore sulla propria scheda."""
    last_at = _client_cooldowns.hp_self_update_last_at.get(character_id, 0.0)
    return perm.cooldown_remaining(last_at, perm.HP_SELF_UPDATE_COOLDOWN_S)


def mark_hp_self_update(character_id: str) -> None:
    _client_cooldowns.hp_self_update_last_at[character_id] = time.monotonic()


def condition_self_update_cooldown_remaining(character_id: str) -> float:
    """Secondi rimanenti prima del prossimo invio di
    condition.self_apply/self_remove per QUESTO personaggio."""
    last_at = _client_cooldowns.condition_self_update_last_at.get(character_id, 0.0)
    return perm.cooldown_remaining(last_at, perm.CONDITION_SELF_UPDATE_COOLDOWN_S)


def mark_condition_self_update(character_id: str) -> None:
    _client_cooldowns.condition_self_update_last_at[character_id] = time.monotonic()


def reset_client_cooldowns_for_tests() -> None:
    """SOLO per i test: azzera lo stato condiviso a livello di processo,
    che altrimenti "perdurerebbe" da una funzione di test all'altra nello
    stesso processo Python — in produzione è proprio l'effetto voluto
    (sopravvive alla ricreazione della view), nei test invece ogni
    funzione vuole partire da uno stato pulito. Mai chiamato da codice
    applicativo."""
    global _client_cooldowns
    _client_cooldowns = _ClientCooldownState()


def rewind_master_action_for_tests(character_id: str, seconds_ago: float) -> None:
    """SOLO per i test: simula "l'ultima azione del master su questo
    personaggio è avvenuta N secondi fa", per verificare che il cancello
    si riapra dopo `MASTER_ACTION_COOLDOWN_S` senza un vero
    `time.sleep()`. Mai chiamato da codice applicativo."""
    _client_cooldowns.master_action_last_at[character_id] = time.monotonic() - seconds_ago


def rewind_network_request_for_tests(seconds_ago: float) -> None:
    """SOLO per i test — vedi `rewind_master_action_for_tests`."""
    _client_cooldowns.network_request_last_at = time.monotonic() - seconds_ago


def rewind_instance_push_for_tests(seconds_ago: float) -> None:
    """SOLO per i test — vedi `rewind_master_action_for_tests`."""
    _client_cooldowns.instance_push_last_at = time.monotonic() - seconds_ago


def rewind_hp_self_update_for_tests(character_id: str, seconds_ago: float) -> None:
    """SOLO per i test — vedi `rewind_master_action_for_tests`."""
    _client_cooldowns.hp_self_update_last_at[character_id] = time.monotonic() - seconds_ago


def rewind_condition_self_update_for_tests(character_id: str, seconds_ago: float) -> None:
    """SOLO per i test — vedi `rewind_master_action_for_tests`."""
    _client_cooldowns.condition_self_update_last_at[character_id] = time.monotonic() - seconds_ago


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
        #
        # Eccezione (2026-08-16, bug segnalato da Davide: "il tiro salvezza
        # segnato manualmente scompare, oppure riappare in ritardo"):
        # `CMD_HP_SELF_UPDATE` è per costruzione inviato SOLO dal
        # proprietario del personaggio (`perm.is_character_owner` in
        # `world_backend.py::_handle_hp_self_update`), che scrive la
        # propria replica locale PRIMA di spedire il comando
        # (`combattimento_tab.py::_push_hp_to_world`, valori assoluti,
        # debounce con generation token). Quando l'eco di quello stesso
        # invio torna indietro su QUESTO dispositivo, un reimport completo
        # non porta mai informazione più fresca — solo il rischio di
        # sovrascrivere con uno stato meno recente un click successivo già
        # scritto in locale ma non ancora spedito (debounce ancora in
        # corso). Va quindi saltato SOLO quando l'attore coincide con
        # questo stesso dispositivo — un hp.self_update di un ALTRO device
        # (impossibile oggi, ma il controllo resta per chiarezza) o
        # qualunque altro comando mutante deve continuare a rimaterializzare
        # normalmente.
        local_device_id = getattr(remote_backend, "device_id", None)
        is_own_hp_self_update_echo = (
            event.kind == perm.CMD_HP_SELF_UPDATE
            and local_device_id is not None
            and event.actor_device_id == local_device_id
        )
        if (
            event.kind in perm.CHARACTER_MUTATING_COMMANDS
            and event.target_type == "character"
            and not is_own_hp_self_update_echo
        ):
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

        elif event.kind == perm.CMD_CHARACTER_REJOIN_REQUEST:
            # Stesso principio di CMD_CHANGE_REQUEST_PROPOSE sopra: il
            # payload scritto da _handle_character_rejoin_request() porta
            # già request_id/mode/export (se presente), il resto si
            # ricostruisce dagli altri campi dell'evento.
            request_id = str(payload.get("request_id", ""))
            mode = str(payload.get("mode", "frozen"))
            if request_id:
                world_repo.save_replica_rejoin_request(WorldRejoinRequest(
                    id=request_id, world_id=local_world_id,
                    character_id=event.target_id, requested_by=event.actor_device_id,
                    requester_name=event.actor_name, mode=mode,
                    payload=json.dumps({"mode": mode}),
                    status="pending", created_at=event.created_at,
                ))

        elif event.kind == perm.CMD_CHARACTER_REJOIN_RESPOND:
            # La rimaterializzazione del personaggio (se accettata) è già
            # coperta dal ramo generico CHARACTER_MUTATING_COMMANDS sopra —
            # qui si chiude solo la richiesta.
            request_id = str(payload.get("request_id", ""))
            accept = bool(payload.get("accept", False))
            if request_id:
                world_repo.resolve_rejoin_request(
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

        elif event.kind == perm.CMD_NOTE_SHARE:
            # Il payload porta l'intero contenuto della nota (§7B) — mai
            # solo l'id: è testo, piccolo, e questo evita un secondo giro
            # di rete per materializzarla sulla replica (a differenza delle
            # immagini mappa del passo 8, troppo grandi per il giornale).
            if payload.get("note_id"):
                master_repo.save_replica_note({**payload, "world_id": local_world_id,
                                                "updated_at": event.created_at})

        elif event.kind in (perm.CMD_ENCOUNTER_MANAGE, perm.CMD_COMBAT_TOGGLE_VISIBILITY):
            # Il payload porta lo stato risolto dell'incontro (§7C) — la
            # replica non fa mai un secondo giro di rete per ricostruirlo.
            encounter_data = payload.get("encounter")
            if isinstance(encounter_data, dict) and encounter_data.get("id"):
                master_repo.replica_upsert_encounter_snapshot(
                    local_world_id, encounter_data, payload.get("members", []),
                )

        elif event.kind in (perm.CMD_MAP_PUBLISH, perm.CMD_MAP_UPLOAD):
            # L'immagine non viaggia mai qui (§6.4) — solo lo stub, scaricata
            # lazy via GET /map/<id>/image la prima volta che la mappa si apre.
            # Stesso identico stub per una mappa clonata (publish) o caricata
            # direttamente (upload, 2026-08-12): la replica non distingue le
            # due origini, entrambe producono una riga senza personaggio
            # proprietario (`character_id` NULL).
            maps_repo.replica_create_map_stub(
                event.target_id, local_world_id, str(payload.get("name", "")),
                visible_to_players=bool(payload.get("visible_to_players", True)),
            )

        elif event.kind == perm.CMD_MAP_VISIBILITY:
            maps_repo.set_map_visibility(
                event.target_id, bool(payload.get("visible_to_players", True)),
            )

        elif event.kind == perm.CMD_MAP_DELETE:
            maps_repo.delete_map(event.target_id)

        elif event.kind == perm.CMD_MAP_DRAW:
            strokes = payload.get("strokes", [])
            if isinstance(strokes, list) and strokes:
                maps_repo.apply_stroke_batch(event.target_id, strokes)

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
# Risoluzione del backend di un mondo — fix 2026-08-07
# ---------------------------------------------------------------------------

def resolve_backend_for_world(world: World, device_id: str, local_backend,
                               remote_cache: dict) -> object | None:
    """
    Risolve il backend giusto per `world` su QUESTO dispositivo:
    `local_backend` (tipicamente `LocalBackend()`) se lo ospita, altrimenti
    un `RemoteBackend` connesso all'host, riusando `world.session_token`
    (§9.4 — mai richiede di nuovo codice+PIN). Ritorna `None` se non è
    stato possibile stabilire una connessione valida.

    Estratto da `ui/views/world/world_view.py::WorldsView._backend_for()`
    (dove nasce lo stesso giorno, per il fix del routing dei comandi) perché
    la stessa identica logica serve ora anche a `ui/views/home_view.py`
    (`CMD_CHARACTER_INSTANCE_SYNC`: registrare sull'host un'istanza appena
    creata) — un solo punto di verità su "come si raggiunge l'host di un
    mondo da questo dispositivo", mai due copie destinate a divergere.

    `remote_cache` è tenuto dal chiamante (es. `self._remote_backends` su
    una view che vive più a lungo di una singola chiamata): ogni chiamante
    mantiene la propria cache di connessioni, non condivisa tra view
    indipendenti — passare un dict vuoto va benissimo per un uso "una
    tantum" (una sola chiamata, nessun riuso atteso).

    Tipizzato `object | None` invece di `WorldBackend | None` per evitare
    un import a livello di modulo di `core.world_backend` (che a sua volta
    non importa mai `core.world_sync`, ma un ciclo tra i due resterebbe
    comunque fragile da mantenere nel tempo) — lo stesso compromesso già
    accettato per `LanJoinResult.backend` qui sopra.
    """
    from core.world_backend import RemoteBackend

    if world.is_local_host:
        return local_backend

    cached = remote_cache.get(world.id)
    if cached is not None and cached.connection_state() == "connected":
        return cached

    if not world.last_seen_host or not world.session_token:
        return None
    host, sep, port_text = world.last_seen_host.rpartition(":")
    if not sep:
        return None
    try:
        port = int(port_text)
    except ValueError:
        return None

    remote = RemoteBackend(host, port, device_id or "", world_id=world.id)
    if not remote.reconnect_with_token(world.session_token):
        # Token non più valido — quasi sempre perché il master ha fermato e
        # riavviato l'hosting: `WorldHostServer.stop()` svuota TUTTI i
        # token in memoria e `start()` rigenera il PIN (§9.4). Prima del
        # 2026-08-16 questo era un vicolo cieco ("mai un ritentativo
        # automatico con credenziali scadute") — bug segnalato da Davide:
        # un giocatore già membro restava bloccato con l'errore "host non
        # connesso o PIN cambiato" finché non reinseriva codice+PIN a mano.
        #
        # Fix ("implementare registrazione"): un dispositivo già presente
        # in `world_members` (persistito su DB dall'host, sopravvive al
        # riavvio) rientra con il solo `join_code` — MAI col PIN, vedi
        # `network/host_server.py::handle_join`. Se questa replica ricorda
        # un `join_code` (sempre vero dopo il primo ingresso,
        # `_finalize_join` sotto), ritentare subito un ingresso completo:
        # se l'host è raggiungibile e questo dispositivo è ancora membro,
        # va a buon fine in silenzio, senza alcuna azione dell'utente.
        remote_cache.pop(world.id, None)
        if not world.join_code:
            return None
        retry = start_lan_join(host, port, world.join_code, "", device_id or "", "")
        if not retry.success or retry.backend is None:
            return None
        remote_cache[world.id] = retry.backend
        return retry.backend
    remote_cache[world.id] = remote
    return remote


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
        session_token=backend.token or "",
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

    for req_data in snapshot.get("rejoin_requests", []):
        request_id = str(req_data.get("id") or "")
        if request_id:
            world_repo.save_replica_rejoin_request(protocol.rejoin_request_from_dict(req_data))

    # Note condivise (§7B) visibili a questo device — stesso motivo dei due
    # loop sopra: gli `events` salvati qui sopra sono solo storia (mai
    # "applicati" da `apply_event_to_replica`), quindi senza questo un
    # giocatore che entra DOPO che una nota è stata condivisa non la
    # vedrebbe mai. Riusa lo stesso scrittore del ramo `note.share` in
    # `apply_event_to_replica` — un solo punto che sa scrivere una nota
    # sulla replica.
    for note_data in snapshot.get("notes", []):
        if note_data.get("id"):
            master_repo.save_replica_note(note_data)

    # Incontro visibile ai giocatori (§7C), se c'è — stesso motivo del loop
    # sopra: riusa lo stesso scrittore del ramo evento in
    # `apply_event_to_replica`, un solo punto che sa scrivere lo specchio.
    visible_encounter = snapshot.get("visible_encounter")
    if isinstance(visible_encounter, dict) and isinstance(visible_encounter.get("encounter"), dict):
        master_repo.replica_upsert_encounter_snapshot(
            world.id, visible_encounter["encounter"], visible_encounter.get("members", []),
        )

    # Mappe pubblicate (§8) — solo lo stub (id/nome): l'immagine si scarica
    # lazy alla prima apertura, mai qui. Stesso scrittore del ramo evento
    # `map.publish` in `apply_event_to_replica`.
    for map_data in snapshot.get("shared_maps", []):
        if map_data.get("id"):
            maps_repo.replica_create_map_stub(
                map_data["id"], world.id, str(map_data.get("name", "")),
            )

    return LanJoinResult(True, world=world_repo.get_world(world.id), backend=backend)
