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
al passo 4. **Dal passo 6** (Multiplayer §7) copre anche gli
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
from data.repositories import (
    character_export, character_repo, loot_repo, maps_repo, master_repo, world_repo,
)
from network import protocol

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Anti-spam lato client — stato di MODULO, non di istanza:
# `ui/app.py::_show_worlds_view()`/`_show_home()` creano un'istanza NUOVA
# di `WorldsView`/`HomeView` ad ogni navigazione — e anche ad ogni cambio
# tema, che passa dallo stesso `_rebuild_route` — quindi uno stato tenuto
# sull'istanza si azzererebbe ad ogni ricreazione, rendendo il limite
# aggirabile senza nemmeno volerlo. Un'istanza di modulo sopravvive per
# tutta la durata del processo, che è esattamente ciò che serve a un
# guardrail "non permettere all'utente di spammare".
#
# Costanti e aritmetica pura (`MASTER_ACTION_COOLDOWN_S`/
# `NETWORK_REQUEST_COOLDOWN_S`/`cooldown_remaining()`) vivono in
# `core.world_permissions`, non qui: servono anche lato HOST
# (`core.world_backend.LocalBackend`, `network.host_server.WorldHostServer`
# — difesa in profondità), e quel modulo è la base dipendenza-zero già
# condivisa da client e host. Qui vive SOLO lo stato lato client.
#
# Il timer del master (`MASTER_ACTION_COOLDOWN_S`, 3s) è PER PERSONAGGIO
# (`master_action_last_at: dict[character_id, float]`), non un solo timer
# globale sulla sezione: un'area che colpisce 4 PG non costringe il master
# ad aspettare 3s tra un personaggio e l'altro, il limite blocca solo il
# martellare ripetuto sullo STESSO personaggio.
# ---------------------------------------------------------------------------

@dataclass
class _ClientCooldownState:
    master_action_last_at: dict[str, float] = field(default_factory=dict)  # character_id -> float
    network_request_last_at: float = 0.0     # ingresso in un mondo (codice/LAN/QR) + retry
    instance_push_last_at: float = 0.0       # HomeView._push_instance_to_host
    #: hp.self_update — per personaggio come master_action,
    #: ma usato per DECIDERE quando è il momento di inviare (debounce in
    #: `CombattimentoTab`), mai per bloccare l'azione locale sulla scheda.
    hp_self_update_last_at: dict[str, float] = field(default_factory=dict)
    #: condition.self_apply/self_remove, estensione graduale di
    #: hp.self_update — per personaggio, usato solo per non martellare
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
    semplici", non categorie separate)."""
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
    QUESTO personaggio verso l'host (`CombattimentoTab`).
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
        # Eccezione: `CMD_HP_SELF_UPDATE` è per costruzione inviato SOLO dal
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
            # direttamente (upload): la replica non distingue le
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

        elif event.kind in (perm.CMD_LOOT_STASH_ADD, perm.CMD_LOOT_STASH_UPDATE):
            # Il payload porta già lo stato completo della voce (vedi
            # `_loot_stash_entry_payload` in `core/world_backend.py`) —
            # upsert diretto, nessuna interrogazione aggiuntiva necessaria.
            if payload.get("id"):
                loot_repo.replica_upsert_entry(payload)

        elif event.kind == perm.CMD_LOOT_STASH_MOVE:
            # Solo lo stato risultante "party" resta visibile alla replica:
            # una voce spostata verso l'archivio del Master (`"master"`)
            # deve sparire dalla vista locale, non restarci "fantasma" —
            # vedi il docstring di `_handle_loot_stash_move`.
            if payload.get("new_stash_kind") == "party" and payload.get("id"):
                loot_repo.replica_upsert_entry(payload)
            elif payload.get("id"):
                loot_repo.replica_delete_entry(str(payload["id"]))

        elif event.kind == perm.CMD_LOOT_STASH_DELETE:
            entry_id = str(payload.get("entry_id", ""))
            if entry_id:
                loot_repo.replica_delete_entry(entry_id)

        elif event.kind == perm.CMD_LOOT_STASH_CLAIM:
            # Il personaggio che ha preso la voce si rimaterializza già dal
            # ramo generico CHARACTER_MUTATING_COMMANDS sopra (evento
            # target_type="character") — qui serve solo far sparire la voce
            # dal deposito comune sulle repliche di TUTTI gli altri membri
            # del mondo, stessa identica forma di CMD_LOOT_STASH_DELETE.
            entry_id = str(payload.get("entry_id", ""))
            if entry_id:
                loot_repo.replica_delete_entry(entry_id)

        elif event.kind == perm.DEVICE_TRANSFER_REDEEM_KIND:
            # Un membro ha spostato il proprio personaggio su un altro
            # dispositivo (§11.9). Due letture completamente diverse dello
            # stesso evento, a seconda di chi lo riceve:
            #
            #  - Se il vecchio dispositivo sono IO, non è un aggiornamento
            #    dell'elenco membri: è la mia estromissione dal mondo. Va
            #    marcata subito, perché il mio token è già stato revocato
            #    dall'host e senza questo la replica proverebbe a
            #    riconnettersi in eterno.
            #  - Su un TERZO dispositivo non si riscrive nulla a mano:
            #    l'elenco membri si risana da sé al prossimo
            #    `sync_replica(refresh_members=True)`, che lo rilegge dallo
            #    snapshot. Il payload non porta il `display_name`, quindi
            #    ricostruire il membro da qui darebbe una riga peggiore di
            #    quella che arriva dallo snapshot.
            old_device_id = str(payload.get("old_device_id", ""))
            new_device_id = str(payload.get("new_device_id", ""))
            if old_device_id and new_device_id:
                if local_device_id is not None and local_device_id == old_device_id:
                    _mark_world_transferred_away(local_world_id)

        elif event.kind in (perm.CMD_DEVICE_TRANSFER_ISSUE, perm.CMD_DEVICE_TRANSFER_REVOKE):
            # Emissione/revoca di un codice: nessun effetto sulla replica. Il
            # codice non è mai nel payload (è un segreto per un solo membro,
            # vedi `_handle_device_transfer_issue`) e `world_device_transfers`
            # vive solo sull'host. L'evento serve al registro degli interventi.
            pass

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
    # `game_maps` escluse: le mappe personali non vengono mai inviate
    # all'host (mai condivise, per design), quindi lo snapshot dell'host
    # qui sopra non le contiene mai —
    # senza questa esclusione il DELETE CASCADE dentro
    # `import_replica_character()` le cancellerebbe ad ogni resync
    # innescato da un evento che non le riguarda affatto (danno HP, PE...).
    character_export.import_replica_character(
        data, character_id, world_seq=seq, skip_tables=frozenset({"game_maps"}),
    )


def _update_replica_owner(world_id: str, new_owner_device_id: str) -> None:
    """`worlds.owner_device_id` non ha un setter pubblico in `world_repo`
    (stessa scelta di `core.world_backend._update_world_owner`, che lo
    scrive sull'host dopo la validazione): qui rispecchia un evento già
    validato altrove, stesso principio delle altre funzioni `save_replica_*`."""
    from datetime import datetime

    from data.database import get_connection
    conn = None
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE worlds SET owner_device_id=?, updated_at=? WHERE id=?",
            (new_owner_device_id, datetime.now().isoformat(), world_id),
        )
        conn.commit()
    except Exception as e:
        logger.error("Errore _update_replica_owner: %s", e)
    finally:
        if conn is not None:
            conn.close()


#: Prefisso della chiave `app_settings` che marca una replica come "trasferita
#: via" (§11.9). Una chiave per mondo, non una colonna nuova su `worlds`:
#: `app_settings` è già il registro degli stati per-installazione del progetto
#: (`device_id`, `display_name`) e questa informazione è esattamente di quel
#: tipo — vale per QUESTA installazione, non per il mondo, che sull'host è
#: perfettamente vivo.
_TRANSFERRED_AWAY_KEY_PREFIX = "world_transferred_away:"


def transferred_away_key(world_id: str) -> str:
    return f"{_TRANSFERRED_AWAY_KEY_PREFIX}{world_id}"


def is_world_transferred_away(world_id: str) -> bool:
    """
    True se il personaggio di questo dispositivo in questo mondo è stato
    spostato su un altro dispositivo (§11.9): la replica locale resta
    consultabile ma non può più inviare nulla al master.
    """
    from data.repositories import settings_repo
    return settings_repo.get_setting(transferred_away_key(world_id), "") == "1"


def _mark_world_transferred_away(world_id: str) -> None:
    """
    Marca la replica come trasferita e azzera il token di sessione.

    Azzerare il token è la metà che conta: senza,
    `resolve_backend_for_world()` proverebbe a riconnettersi, si vedrebbe
    rifiutare il token e ritenterebbe da sé un ingresso completo col solo
    `join_code` — arrivando a mostrare all'utente un errore che parla di PIN.
    Con il token azzerato quella funzione esce subito con `None` e la replica
    resta una copia locale in sola lettura, che è il comportamento voluto.
    """
    from data.repositories import settings_repo

    settings_repo.set_setting(transferred_away_key(world_id), "1")
    world_repo.clear_session_token(world_id)
    logger.info(
        "Mondo %s marcato come trasferito su un altro dispositivo: replica "
        "locale in sola lettura.", world_id,
    )


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
    applied = 0
    if events:
        for event in events:
            apply_event_to_replica(local_world_id, event, remote_backend=remote_backend)
            world_repo.save_replica_event(event)
        latest_seq = max(e.seq for e in events)
        world_repo.update_last_synced_seq(local_world_id, latest_seq)
        applied = len(events)

    # Questo passo gira SEMPRE (quando `refresh_members=True`, il default),
    # a prescindere da `events`: se girasse solo dopo eventi incrementali
    # nuovi, un dispositivo che ha già raggiunto la punta del giornale (il
    # caso più comune durante una sessione tranquilla, o subito dopo un
    # ingresso) smetterebbe di ri-scaricare lo snapshot del tutto — se per
    # qualunque motivo una nota/mappa non fosse stata seminata correttamente
    # al primo ingresso (`_finalize_join`), nessun ciclo successivo avrebbe
    # più occasione di correggerlo. Costo di una sola chiamata di rete in
    # più ogni ciclo, già accettato per i soli membri, qui esteso a note e
    # mappe condivise (che riusano gli stessi identici scrittori di
    # `_finalize_join`, un solo punto di verità su "come si materializza lo
    # stato derivato dallo snapshot", mai due copie della stessa logica).
    if refresh_members:
        _refresh_snapshot_derived_state(remote_backend, local_world_id)

    return applied


def push_pending_instances(remote_backend, local_world_id: str, device_id: str) -> int:
    """
    Ritenta il push verso l'host delle istanze di QUESTO dispositivo rimaste
    con `host_sync_pending=1`: se `HomeView._push_instance_to_host()` fallisce
    perché l'host è offline nel momento della creazione, il personaggio
    resterebbe "nel mondo" solo in locale finché non si ripete l'operazione
    a mano con l'host online.

    Va chiamata dallo stesso loop periodico che già chiama `sync_replica()`
    (`ui/views/world/world_view.py`) — qui, non in `sync_replica()` stessa,
    perché è un comando in USCITA (stato locale → host), non uno stato
    scaricato dall'host. Rispetta lo stesso cooldown anti-spam di
    `HomeView._push_instance_to_host()` (`instance_push_cooldown_remaining`/
    `mark_instance_push`, stesso tracciato condiviso). Ritorna il numero di
    istanze registrate con successo in questo giro.
    """
    if instance_push_cooldown_remaining() > 0:
        return 0
    pending_ids = character_repo.list_pending_host_sync(local_world_id, device_id)
    if not pending_ids:
        return 0
    mark_instance_push()

    pushed = 0
    for character_id in pending_ids:
        export_data = character_export.export_character(character_id)
        if export_data is None:
            logger.error("push_pending_instances: export fallito per %s", character_id)
            continue
        result = remote_backend.send_command(
            local_world_id, device_id, perm.CMD_CHARACTER_INSTANCE_SYNC,
            {"export": export_data}, target_type="character", target_id=character_id,
        )
        if result.success:
            character_repo.set_host_sync_pending(character_id, False)
            pushed += 1
        else:
            logger.warning(
                "push_pending_instances: registrazione %s ancora rifiutata: %s",
                character_id, result.error,
            )
    return pushed


def push_pending_self_commands(remote_backend, local_world_id: str, device_id: str) -> int:
    """
    Ritenta i comandi `*.self_*` di QUESTO dispositivo rimasti in coda
    (`pending_self_commands`, BUG FIX 2026-08-20) — controparte generalizzata
    di `push_pending_instances` sopra: se `push_character_self_command()`
    fallisce perché l'host è irraggiungibile nel momento del salvataggio
    (nota, arma, oggetto, incantesimo, ecc.), il comando resterebbe SOLO
    locale finché non arriva un resync innescato da altro — che lo
    cancellerebbe, esattamente il bug appena corretto altrove nella stessa
    sessione. Vedi il docstring di `push_character_self_command` per il
    dettaglio completo.

    Va chiamata dallo stesso loop periodico che già chiama `sync_replica()`/
    `push_pending_instances()` (`ui/views/world/world_view.py`), stesso
    cooldown anti-spam condiviso. Ritorna il numero di comandi inviati con
    successo in questo giro — l'ordine FIFO (`list_pending_self_commands`,
    `ORDER BY created_at`) garantisce che, se più modifiche sullo stesso
    campo erano rimaste in coda, l'host le applichi nello stesso ordine in
    cui sono avvenute in locale.
    """
    if instance_push_cooldown_remaining() > 0:
        return 0
    pending = world_repo.list_pending_self_commands(local_world_id, device_id)
    if not pending:
        return 0
    mark_instance_push()

    pushed = 0
    for pending_id, character_id, kind, payload_json in pending:
        try:
            payload = json.loads(payload_json)
        except (json.JSONDecodeError, TypeError):
            logger.error(
                "push_pending_self_commands: payload illeggibile per %s (kind=%r), scartato",
                pending_id, kind,
            )
            world_repo.delete_pending_self_command(pending_id)
            continue
        result = remote_backend.send_command(
            local_world_id, device_id, kind, payload,
            target_type="character", target_id=character_id,
        )
        if result.success:
            world_repo.delete_pending_self_command(pending_id)
            pushed += 1
        else:
            # A differenza di `push_character_self_command()` (dove
            # un'eccezione di trasporto è già distinta da un rifiuto
            # applicativo prima di arrivare a questo punto), `RemoteBackend.
            # send_command()` non solleva mai — un host tornato di nuovo
            # irraggiungibile PROPRIO durante questo ritentativo produce lo
            # stesso `CommandResult(False, ...)` di un vero rifiuto
            # applicativo (proprietà non verificata, payload non valido).
            # Senza poterli distinguere qui, la scelta più sicura è NON
            # rimuovere mai dalla coda su un fallimento: un comando
            # legittimo riprova al giro successivo (costo: nessuno, stesso
            # cooldown di sempre); un payload davvero non valido — non
            # dovrebbe mai accadere, i payload sono costruiti dal codice
            # stesso, mai da input libero dell'utente — resterebbe in coda
            # ritentato invano, ma senza perdere né corrompere nulla.
            logger.warning(
                "push_pending_self_commands: %s (kind=%r) non riuscito, resta in coda: %s",
                pending_id, kind, result.error,
            )
    return pushed


def _backfill_map_annotations_if_empty(remote_backend, map_id: str) -> None:
    """
    Recupera una volta sola i tratti di disegno di una mappa condivisa
    quando la replica locale non li ha ancora — `replica_create_map_stub`
    inizializza sempre `annotations='[]'` e non le aggiorna più su un
    UPDATE (righe già presenti), quindi senza questo backfill un
    dispositivo che si unisce dopo che il master ha già disegnato non
    vedrebbe mai quei tratti, solo quelli disegnati dopo (via evento
    `CMD_MAP_DRAW`). Stessa semantica "una tantum, mai ad ogni apertura"
    di `fetch_map_image` — se la mappa risulta già annotata localmente
    (fetch precedente riuscito, o tratti arrivati nel frattempo via
    evento) non richiede nulla alla rete.

    No-op silenzioso se `remote_backend` non è un `RemoteBackend` (questo
    dispositivo ospita il mondo: la propria copia È già quella
    autoritativa) o se il fetch fallisce — riproverà al prossimo giro di
    `_refresh_snapshot_derived_state`.
    """
    from core.world_backend import RemoteBackend
    if not isinstance(remote_backend, RemoteBackend):
        return
    local_map = maps_repo.get_map(map_id)
    if local_map is None or (local_map.annotations or "[]").strip() not in ("", "[]"):
        return
    annotations = remote_backend.fetch_map_annotations(map_id)
    if annotations and annotations != "[]":
        maps_repo.update_map(map_id, annotations=annotations)


def _refresh_snapshot_derived_state(remote_backend, local_world_id: str) -> None:
    """
    Ri-materializza sulla replica locale lo stato che uno `GET /snapshot`
    porta ma che il giornale incrementale (`fetch_events`) da solo non
    garantisce sempre di riportare — membri, note condivise, mappe
    condivise (§9.2/§7B/§6.4). Chiamata ad ogni giro di `sync_replica`
    (vedi il commento lì sopra), non solo al primo ingresso: un
    "auto-guarigione" periodico, indipendente dalla causa esatta per cui
    qualcosa non fosse arrivato prima.
    """
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

    # Un elemento non processa mai gli altri: un `try` per riga, non uno
    # per l'intero ciclo — un singolo dato malformato (es. residuo di una
    # sessione di test precedente) non deve impedire agli ALTRI elementi,
    # per il resto sani, di arrivare sulla replica.
    # NPC collegati a una nota visibile (2026-08-20) — PRIMA delle note
    # sotto: `master_repo.save_replica_note()` azzera `linked_npc_id` se
    # l'NPC non esiste ancora in locale al momento in cui la nota viene
    # scritta, quindi l'NPC deve arrivare per primo nello stesso giro.
    # Vedi `master_repo.replica_upsert_npc()` per il perché di questa
    # sezione (bug report Davide: dossier PNG collegato a una nota
    # condivisa).
    for npc_data in snapshot.get("shared_npcs", []):
        if npc_data.get("id"):
            try:
                master_repo.replica_upsert_npc(npc_data)
            except Exception as e:
                logger.error("_refresh_snapshot_derived_state: NPC %r scartato: %s",
                             npc_data.get("id"), e)

    for note_data in snapshot.get("notes", []):
        if note_data.get("id"):
            try:
                master_repo.save_replica_note(note_data)
            except Exception as e:
                logger.error("_refresh_snapshot_derived_state: nota %r scartata: %s",
                             note_data.get("id"), e)

    for map_data in snapshot.get("shared_maps", []):
        if map_data.get("id"):
            try:
                maps_repo.replica_create_map_stub(
                    map_data["id"], local_world_id, str(map_data.get("name", "")),
                )
                _backfill_map_annotations_if_empty(remote_backend, str(map_data["id"]))
            except Exception as e:
                logger.error("_refresh_snapshot_derived_state: mappa %r scartata: %s",
                             map_data.get("id"), e)

    # Deposito comune del gruppo — solo `stash_kind="party"`,
    # mai "master" (l'archivio del Master non è mai incluso nello snapshot,
    # vedi `network/host_server.py::handle_snapshot`). A differenza di
    # note/mappe sopra (solo aggiunte) il deposito supporta anche la
    # cancellazione/spostamento fuori dal mondo — serve quindi la stessa
    # riconciliazione per rimozione già usata per i membri sopra: le righe
    # locali "party" di questo mondo non più presenti nello snapshot
    # vengono rimosse (spostate altrove o cancellate sull'host).
    incoming_stash_ids: set[str] = set()
    for entry_data in snapshot.get("loot_stash", []):
        if entry_data.get("id"):
            incoming_stash_ids.add(str(entry_data["id"]))
            try:
                loot_repo.replica_upsert_entry(entry_data)
            except Exception as e:
                logger.error("_refresh_snapshot_derived_state: voce di bottino %r scartata: %s",
                             entry_data.get("id"), e)
    for local_entry in loot_repo.get_entries("party", world_id=local_world_id):
        if local_entry.id not in incoming_stash_ids:
            loot_repo.replica_delete_entry(local_entry.id)


# ---------------------------------------------------------------------------
# Risoluzione del backend di un mondo
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
    perché la stessa identica logica serve anche a `ui/views/home_view.py`
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

    # Questa replica è già stata dichiarata trasferita su un altro dispositivo
    # (§11.9): non esiste più un backend raggiungibile per essa, e insistere
    # porterebbe al ritentativo automatico qui sotto e quindi a un messaggio
    # sbagliato sul PIN.
    if is_world_transferred_away(world.id):
        remote_cache.pop(world.id, None)
        return None

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
        # token in memoria e `start()` rigenera il PIN (§9.4). Senza un
        # ritentativo automatico, un giocatore già membro resterebbe
        # bloccato con l'errore "host non connesso o PIN cambiato" finché
        # non reinserisce codice+PIN a mano.
        #
        # Un dispositivo già presente
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
            # Percorso REALE del vecchio dispositivo dopo un trasferimento
            # (§11.9): quasi sempre era spento o fuori portata nel
            # momento in cui il master ha approvato, quindi non ha mai visto
            # l'evento `device_transfer.redeem` e non si è marcato da sé. Lo
            # scopre qui, dalla risposta dell'host al primo ritentativo. Senza
            # questo, ogni avvio dell'app rifarebbe lo stesso giro inutile e la
            # UI non potrebbe spiegare perché il mondo non risponde più.
            if retry.reason == "transferred_away":
                _mark_world_transferred_away(world.id)
                return None
            # §11.7: `host`/`port` qui sopra vengono SEMPRE
            # da `world.last_seen_host`, che diventa stale non appena l'host
            # cambia rete (nuovo IP LAN — es. il master ospita da un'altra
            # casa la settimana dopo) — senza questo ritentativo "Riconnetti"
            # funzionerebbe solo sulla stessa rete dell'ultimo ingresso.
            # Prima di arrendersi, ripete lo
            # stesso identico ritentativo con un indirizzo fresco trovato
            # via scoperta broadcast — l'host lo manda comunque
            # (`network/discovery.py`), quindi non serve QR né digitare
            # nulla.
            rediscovered = _retry_with_rediscovery(world, device_id)
            if rediscovered is None:
                return None
            remote_cache[world.id] = rediscovered
            return rediscovered
        remote_cache[world.id] = retry.backend
        return retry.backend
    remote_cache[world.id] = remote
    return remote


def _retry_with_rediscovery(world: World, device_id: str) -> object | None:
    """Ripiego di `resolve_backend_for_world()` quando `world.last_seen_host`
    non risponde più: ascolta l'annuncio broadcast UDP che l'host manda
    comunque ogni pochi secondi (`network/discovery.py::discover_worlds()`)
    per trovare il suo indirizzo ATTUALE, poi ripete l'ingresso con
    `world.join_code`. Se trovato, `start_lan_join()` → `_finalize_join()`
    salva il nuovo indirizzo su `last_seen_host` come parte del normale
    ingresso — nessun aggiornamento separato necessario qui.

    Nessun ritentativo se il broadcast è bloccato dalla rete (Wi-Fi
    pubblico con isolamento client, §3.2 di `discovery.py`): in quel caso
    `discover_worlds()` ritorna una lista vuota e l'utente resta comunque
    con il percorso manuale (reinserire codice+PIN o riscansionare il QR)."""
    if not world.join_code:
        return None
    from network.discovery import discover_worlds
    found = next((w for w in discover_worlds() if w.world_id == world.id), None)
    if found is None:
        return None
    retry = start_lan_join(found.host, found.port, world.join_code, "", device_id or "", "")
    if not retry.success or retry.backend is None:
        return None
    return retry.backend


# ---------------------------------------------------------------------------
# Push self-service best-effort verso l'host
# ---------------------------------------------------------------------------

async def push_character_self_command(page, character, device_id_cache: dict, kind: str,
                                       payload: dict) -> None:
    """
    Invia un comando self-service (diario, note di sessione, abilità
    personalizzate, incantesimi, armi/oggetti/monete/note di campagna)
    verso l'host per `character`, best effort — stessa forma di
    `_push_hp_to_world`/`_push_condition_to_world`
    (`ui/views/character_sheet/combattimento_tab.py`), estratta qui perché
    ora serve identica a più tab (diario, esplorazione, incantesimi,
    inventario) invece di essere duplicata in ognuno.

    Nessun retry SINCRONO né debounce con "generation": a differenza dei PF
    (un flusso continuo di piccoli cambiamenti mentre l'utente tocca la
    scheda) queste sono azioni discrete e deliberate (un pulsante "Salva"),
    un invio per azione — stesso principio di `_push_condition_to_world`.
    C'è però un retry ASINCRONO (BUG FIX 2026-08-20, bug report Davide
    "cosa succede se il giocatore inserisce una nota mentre il mondo non è
    hostato?"): se l'host non è raggiungibile ORA, il comando viene messo
    in coda (`world_repo.enqueue_pending_self_command`, tabella
    `pending_self_commands`) e ritentato dal prossimo giro di
    `push_pending_self_commands()` — stesso principio già in uso per
    `CMD_CHARACTER_INSTANCE_SYNC`/`host_sync_pending`, qui generalizzato a
    qualunque comando self. Senza questo, la scrittura locale (già avvenuta
    dal chiamante prima di invocare questa funzione, e che resta comunque
    corretta) non arrivava MAI sull'host se non tornava a essere ripetuta a
    mano — e nel frattempo un resync innescato da un evento non correlato
    la cancellava, lo stesso identico bug appena corretto altrove.

    Un rifiuto ESPLICITO dell'host (`result.success is False`, es.
    proprietà non verificata) non entra in coda: non è un problema di
    raggiungibilità, ritentarlo all'infinito non lo farebbe mai riuscire.

    `device_id_cache` è un dict tenuto dal chiamante (es. `self._device_id_cache
    = {}` sul tab) per evitare di richiedere `resolve_device_id()` ad ogni
    invio — stesso ruolo di `self._device_id` sui tab che già usano questo
    pattern, ma passato esplicitamente perché questa funzione non ha una
    propria istanza su cui tenerlo.
    """
    if not character.world_id or page is None:
        return

    device_id = device_id_cache.get("id")
    if device_id is None:
        from ui.device_identity import resolve_device_id
        device_id = await resolve_device_id(page)
        device_id_cache["id"] = device_id
    if not device_id:
        return

    from core.world_backend import LocalBackend
    from data.repositories import world_repo
    world = world_repo.get_world(character.world_id)
    if world is None:
        return
    backend = resolve_backend_for_world(world, device_id, LocalBackend(), {})
    if backend is None:
        # Host irraggiungibile ORA: in coda per il prossimo giro utile,
        # non silenziosamente perso — vedi il docstring sopra.
        world_repo.enqueue_pending_self_command(
            character.id, world.id, device_id, kind, json.dumps(payload),
        )
        return

    try:
        result = backend.send_command(
            world.id, device_id, kind, payload,
            target_type="character", target_id=character.id,
        )
        if not result.success:
            logger.warning("Invio %s rifiutato per %s: %s", kind, character.id, result.error)
    except Exception as e:
        # Errore di trasporto (non un rifiuto esplicito): stesso principio
        # del ramo `backend is None` sopra, va ritentato.
        logger.warning("Invio %s fallito per %s: %s", kind, character.id, e)
        world_repo.enqueue_pending_self_command(
            character.id, world.id, device_id, kind, json.dumps(payload),
        )


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
    #: `"join"` o `"transfer"` (§11.9) — la UI usa un testo di attesa diverso
    #: per il trasferimento di un personaggio su un altro dispositivo.
    kind: str = "join"
    #: Motivo strutturato del rifiuto quando l'host ne dà uno; oggi solo
    #: `"transferred_away"`.
    reason: str = ""


def start_lan_join(host: str, port: int, join_code: str, pin: str,
                    device_id: str, display_name: str,
                    transfer_code: str = "") -> LanJoinResult:
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

    `transfer_code` (§11.9): riscatta un codice di trasferimento per
    subentrare a un membro esistente e riprendersi i suoi personaggi, invece di
    entrare come dispositivo nuovo. Sostituisce il PIN, non l'approvazione del
    master. La capacità dell'host viene verificata al passo 1, sullo stesso
    `GET /world` già in uso: con un host più vecchio si esce con un messaggio
    specifico invece di mandargli una richiesta che interpreterebbe come un
    ingresso normale con PIN vuoto (→ "PIN errato", fuorviante).
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

    if transfer_code:
        features = info.get("features") or []
        if protocol.FEATURE_DEVICE_TRANSFER not in features:
            return LanJoinResult(
                False,
                kind="transfer",
                error=(
                    "L'app sul dispositivo del master è troppo vecchia per il "
                    "trasferimento del personaggio. Chiedi al master di "
                    "aggiornarla."
                ),
            )

    backend.world_id = str(info.get("world_id", ""))

    outcome = backend.join(join_code, pin, display_name, transfer_code=transfer_code)
    if outcome.status == "error":
        return LanJoinResult(
            False, error=outcome.error, reason=outcome.reason,
            kind="transfer" if transfer_code else "join",
        )
    if outcome.status == "pending":
        attesa = (
            "In attesa che il master approvi il trasferimento."
            if outcome.kind == "transfer"
            else "In attesa dell'approvazione del master."
        )
        return LanJoinResult(
            False, backend=backend, pending_request_id=outcome.request_id,
            kind=outcome.kind, error=attesa,
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
    if outcome.status == "cancelled":
        # La richiesta è stata annullata (tipicamente da questo
        # stesso dispositivo, `RemoteBackend.cancel_join_request()`) — stato
        # TERMINALE come il rifiuto, mai più "in attesa": senza questo ramo
        # cadrebbe nel fallback sotto e resterebbe "in attesa" per sempre
        # anche dopo l'annullamento.
        return LanJoinResult(False, error="Richiesta di ingresso annullata.")
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

    Dal passo 6 (Multiplayer) semina anche le istanze di
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

    # Senza isolamento per elemento, un'eccezione qui risalirebbe fino al
    # chiamante — e nessuno dei due chiamanti la intercetta
    # (`_poll_pending_join_loop` è una coroutine: l'eccezione ucciderebbe il
    # task in silenzio e il dialogo del giocatore resterebbe fermo su
    # "In attesa dell'approvazione del master…" per sempre, mentre il mondo
    # risulterebbe comunque registrato al riavvio perché
    # `save_replica_world()` sopra ha già scritto). Per questo anche questi
    # due loop degradano a "salta questo elemento".
    for m in snapshot.get("members", []):
        try:
            world_repo.save_replica_member(protocol.member_from_dict(m))
        except Exception as e:
            logger.error("_finalize_join: membro %r scartato: %s", m.get("device_id"), e)

    # Gli eventi, a differenza di tutto il resto, sono una SEQUENZA: sono la
    # fonte di verità del giornale e `last_synced_seq` dichiara "ho tutto
    # fino a qui". Saltarne uno nel mezzo e lasciare comunque
    # `last_synced_seq = max(seq)` (come faceva il calcolo qui sopra)
    # lascerebbe un buco permanente: il prossimo `sync_replica()` chiederebbe
    # solo gli eventi successivi e quello scartato non tornerebbe mai più.
    # Quindi qui si tiene il seq più alto CONSECUTIVAMENTE salvato: al primo
    # errore la sequenza si tronca lì, e il giro di sincronizzazione
    # successivo riparte da quel punto e ritenta da sé gli eventi rimanenti.
    safe_seq = 0
    truncated = False
    for event in sorted(events, key=lambda e: e.seq):
        if truncated:
            break
        try:
            world_repo.save_replica_event(event)
            safe_seq = event.seq
        except Exception as e:
            logger.error(
                "_finalize_join: evento seq=%s scartato (%s) — giornale troncato qui, "
                "il prossimo sync riprenderà da questo punto.", event.seq, e,
            )
            truncated = True
    if truncated and safe_seq < latest_seq:
        world_repo.update_last_synced_seq(world.id, safe_seq)

    # Isolamento per elemento (stesso principio di
    # `_refresh_snapshot_derived_state` più sotto e di `handle_snapshot()`
    # lato host): senza, un'eccezione su UNA scheda/nota/mappa (es. dati
    # residui di una sessione di test precedente) farebbe fallire l'INTERA
    # `_finalize_join()` con un'eccezione non gestita, DOPO che
    # `world_repo.save_replica_world(world)` sopra ha già scritto la riga
    # del mondo sulla replica locale — risultato: l'app del giocatore non
    # mostrerebbe alcun esito (l'eccezione risalirebbe silenziosa fino al
    # gestore del pulsante "Controlla di nuovo" o al ciclo di polling
    # automatico, nessuno dei due la intercetta), ma il mondo risulterebbe
    # comunque "registrato" al riavvio dell'app, perché quella riga era già
    # stata salvata prima del crash. Ogni voce qui sotto degrada quindi a
    # "salta questo singolo elemento" invece di far fallire l'intero
    # ingresso, con un log per poterla poi correggere.
    for char_data in snapshot.get("characters", []):
        char_row = char_data.get("character") or {}
        character_id = str(char_row.get("id") or "")
        if character_id:
            try:
                # `game_maps` escluse — stesso motivo di
                # `_resync_character_from_host()` sopra: le mappe personali
                # non arrivano mai nell'export dell'host.
                character_export.import_replica_character(
                    char_data, character_id, world_seq=latest_seq,
                    skip_tables=frozenset({"game_maps"}),
                )
            except Exception as e:
                logger.error("_finalize_join: personaggio %r scartato: %s", character_id, e)

    for req_data in snapshot.get("change_requests", []):
        request_id = str(req_data.get("id") or "")
        if request_id:
            try:
                world_repo.save_replica_change_request(protocol.change_request_from_dict(req_data))
            except Exception as e:
                logger.error("_finalize_join: richiesta di modifica %r scartata: %s", request_id, e)

    for req_data in snapshot.get("rejoin_requests", []):
        request_id = str(req_data.get("id") or "")
        if request_id:
            try:
                world_repo.save_replica_rejoin_request(protocol.rejoin_request_from_dict(req_data))
            except Exception as e:
                logger.error("_finalize_join: richiesta di rientro %r scartata: %s", request_id, e)

    # Note condivise (§7B) visibili a questo device — stesso motivo dei due
    # loop sopra: gli `events` salvati qui sopra sono solo storia (mai
    # "applicati" da `apply_event_to_replica`), quindi senza questo un
    # giocatore che entra DOPO che una nota è stata condivisa non la
    # vedrebbe mai. Riusa lo stesso scrittore del ramo `note.share` in
    # `apply_event_to_replica` — un solo punto che sa scrivere una nota
    # sulla replica.
    # NPC collegati a una nota visibile (2026-08-20) — PRIMA delle note
    # sotto, stesso motivo di `_refresh_snapshot_derived_state` (evita che
    # `save_replica_note()` azzeri `linked_npc_id` per un NPC arrivato un
    # istante dopo).
    for npc_data in snapshot.get("shared_npcs", []):
        if npc_data.get("id"):
            try:
                master_repo.replica_upsert_npc(npc_data)
            except Exception as e:
                logger.error("_finalize_join: NPC %r scartato: %s", npc_data.get("id"), e)

    for note_data in snapshot.get("notes", []):
        if note_data.get("id"):
            try:
                master_repo.save_replica_note(note_data)
            except Exception as e:
                logger.error("_finalize_join: nota %r scartata: %s", note_data.get("id"), e)

    # Incontro visibile ai giocatori (§7C), se c'è — stesso motivo del loop
    # sopra: riusa lo stesso scrittore del ramo evento in
    # `apply_event_to_replica`, un solo punto che sa scrivere lo specchio.
    try:
        visible_encounter = snapshot.get("visible_encounter")
        if isinstance(visible_encounter, dict) and isinstance(visible_encounter.get("encounter"), dict):
            master_repo.replica_upsert_encounter_snapshot(
                world.id, visible_encounter["encounter"], visible_encounter.get("members", []),
            )
    except Exception as e:
        logger.error("_finalize_join: incontro visibile scartato: %s", e)

    # Mappe pubblicate (§8) — solo lo stub (id/nome): l'immagine si scarica
    # lazy alla prima apertura, mai qui. Stesso scrittore del ramo evento
    # `map.publish` in `apply_event_to_replica`.
    for map_data in snapshot.get("shared_maps", []):
        if map_data.get("id"):
            try:
                maps_repo.replica_create_map_stub(
                    map_data["id"], world.id, str(map_data.get("name", "")),
                )
                _backfill_map_annotations_if_empty(backend, str(map_data["id"]))
            except Exception as e:
                logger.error("_finalize_join: mappa %r scartata: %s", map_data.get("id"), e)

    return LanJoinResult(True, world=world_repo.get_world(world.id), backend=backend)
