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
import time
import urllib.parse
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Callable

from core import damage_rules
from core import world_permissions as perm
from data.models import WorldEvent
from data.repositories import (
    character_export, character_repo, loot_repo, maps_repo, master_repo, world_repo,
    world_transfer_repo,
)
from network import protocol

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Anti-spam lato HOST — difesa in profondità. Il client si limita da solo
# per UX (`core.world_sync`), ma un client modificato o con un bug potrebbe
# ignorare quel limite — qui lo STESSO limite viene applicato di nuovo,
# stavolta sui dati che l'host controlla davvero: mai fidarsi del client,
# stesso principio già seguito per i permessi in questo file (§5,
# "impossibile aggirarli da un client modificato").
#
# Stato a livello di MODULO, non su `LocalBackend`: quella classe viene
# istanziata spesso ad hoc in giro per il progetto (es. `WorldsView.
# __init__`, `HomeView._push_instance_to_host`, `WorldHostServer.__init__`
# di default) — uno stato sull'istanza si perderebbe silenziosamente ogni
# volta che una di queste ricrea `LocalBackend`.
#
# `master_action_last_at` è chiavato per (actor_device_id, character_id):
# stessa granularità per-personaggio del timer lato client (un'area su 4
# PG non blocca il master tra un personaggio e l'altro), E per-dispositivo
# (un co-master su un altro telefono non condivide il limite col master
# principale). `instance_sync_last_at` è chiavato solo per actor_device_id
# (come il timer di rete lato client, non per personaggio: un giocatore
# registra una sola istanza alla volta).
# ---------------------------------------------------------------------------

@dataclass
class _HostCooldownState:
    master_action_last_at: dict[tuple[str, str], float] = field(default_factory=dict)
    instance_sync_last_at: dict[str, float] = field(default_factory=dict)
    #: hp.self_update — chiavato (actor_device_id,
    #: target_id) come master_action_last_at: stessa granularità per
    #: personaggio, non un solo timer per l'intero dispositivo.
    hp_self_update_last_at: dict[tuple[str, str], float] = field(default_factory=dict)
    #: condition.self_apply/self_remove, estensione graduale —
    #: stessa chiave/granularità di hp_self_update_last_at, tracciato a
    #: parte perché usa CONDITION_SELF_UPDATE_COOLDOWN_S, non
    #: HP_SELF_UPDATE_COOLDOWN_S (valori oggi identici, ma concettualmente
    #: due limiti indipendenti — coerente con instance_sync_last_at, che è
    #: già un dict a sé pur condividendo NETWORK_REQUEST_COOLDOWN_S con
    #: altro).
    condition_self_update_last_at: dict[tuple[str, str], float] = field(default_factory=dict)


_host_cooldowns = _HostCooldownState()


def reset_host_cooldowns_for_tests() -> None:
    """SOLO per i test — vedi `core.world_sync.reset_client_cooldowns_for_tests()`
    per lo stesso principio lato client. Mai chiamato da codice applicativo."""
    global _host_cooldowns
    _host_cooldowns = _HostCooldownState()


def rewind_host_master_action_for_tests(actor_device_id: str, target_id: str,
                                         seconds_ago: float) -> None:
    """SOLO per i test — vedi `core.world_sync.rewind_master_action_for_tests()`
    per lo stesso principio lato client. Mai chiamato da codice applicativo."""
    _host_cooldowns.master_action_last_at[(actor_device_id, target_id)] = (
        time.monotonic() - seconds_ago
    )


def rewind_host_instance_sync_for_tests(actor_device_id: str, seconds_ago: float) -> None:
    """SOLO per i test — vedi `rewind_host_master_action_for_tests`."""
    _host_cooldowns.instance_sync_last_at[actor_device_id] = time.monotonic() - seconds_ago


def rewind_host_hp_self_update_for_tests(actor_device_id: str, target_id: str,
                                          seconds_ago: float) -> None:
    """SOLO per i test — vedi `rewind_host_master_action_for_tests`."""
    _host_cooldowns.hp_self_update_last_at[(actor_device_id, target_id)] = (
        time.monotonic() - seconds_ago
    )


def rewind_host_condition_self_update_for_tests(actor_device_id: str, target_id: str,
                                                 seconds_ago: float) -> None:
    """SOLO per i test — vedi `rewind_host_master_action_for_tests`."""
    _host_cooldowns.condition_self_update_last_at[(actor_device_id, target_id)] = (
        time.monotonic() - seconds_ago
    )


@dataclass
class CommandResult:
    """Esito dell'invio di un comando — mai un'eccezione verso il chiamante:
    la UI legge `success`/`error`, coerente con lo stile del resto del
    progetto (repository che non sollevano mai verso la UI)."""
    success: bool
    error: str = ""
    event: WorldEvent | None = None
    #: Dati di risposta destinati SOLO a chi ha inviato il comando
    #: (§11.9). Nasce dal codice di trasferimento: `event.payload`
    #: finisce nel giornale, e il giornale viene trasmesso a OGNI replica via
    #: `GET /events` — un segreto per un singolo membro non può passare da lì.
    #: Attraversa la rete in `WorldHostServer.handle_command` → il campo `data`
    #: della risposta JSON → `RemoteBackend.send_command`. Campo con valore
    #: predefinito in coda: tutte le costruzioni esistenti di `CommandResult`
    #: restano valide.
    data: dict | None = None


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

        rate_limit_error = self._check_rate_limit(actor_device_id, kind, target_id)
        if rate_limit_error is not None:
            return CommandResult(False, rate_limit_error)

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

    def _check_rate_limit(self, actor_device_id: str, kind: str, target_id: str) -> str | None:
        """
        Difesa in profondità — stesso limite già applicato
        lato client, riapplicato qui su dati che l'host controlla davvero.
        Ritorna un messaggio d'errore (in italiano, pronto per
        `CommandResult.error`) se il comando va rifiutato, `None` se può
        proseguire — in quel caso l'istante viene registrato SUBITO, PRIMA
        di chiamare l'handler: anche un comando che l'handler rifiuterà per
        un motivo suo (es. dati non validi) ha già impegnato un turno del
        limite, stesso principio del timer lato client ("non aggirabile
        martellando durante un errore").

        Fuori scope qui (nessun rate limit applicato): qualunque comando
        NON in `MASTER_REMOTE_ACTION_COMMANDS`/`CMD_CHARACTER_INSTANCE_SYNC`
        — coerente con la scelta già fatta lato client di non limitare
        `world.rename`/gestione membri/`change_request.respond`.
        """
        now = time.monotonic()
        if kind in perm.MASTER_REMOTE_ACTION_COMMANDS:
            key = (actor_device_id, target_id)
            remaining = perm.cooldown_remaining(
                _host_cooldowns.master_action_last_at.get(key, 0.0),
                perm.MASTER_ACTION_COOLDOWN_S,
            )
            if remaining > 0:
                return (
                    f"Troppe richieste ravvicinate su questo personaggio — "
                    f"aspetta {int(remaining) + 1} secondi."
                )
            _host_cooldowns.master_action_last_at[key] = now
            return None

        if kind == perm.CMD_CHARACTER_INSTANCE_SYNC:
            remaining = perm.cooldown_remaining(
                _host_cooldowns.instance_sync_last_at.get(actor_device_id, 0.0),
                perm.NETWORK_REQUEST_COOLDOWN_S,
            )
            if remaining > 0:
                return (
                    f"Troppe richieste di rete ravvicinate — "
                    f"aspetta {int(remaining) + 1} secondi."
                )
            _host_cooldowns.instance_sync_last_at[actor_device_id] = now
            return None

        if kind == perm.CMD_HP_SELF_UPDATE:
            # Stesso principio di difesa in profondità degli altri due rami:
            # il client si limita già da solo (debounce, `core.world_sync`),
            # questo è il backstop lato host contro un client modificato.
            key = (actor_device_id, target_id)
            remaining = perm.cooldown_remaining(
                _host_cooldowns.hp_self_update_last_at.get(key, 0.0),
                perm.HP_SELF_UPDATE_COOLDOWN_S,
            )
            if remaining > 0:
                return (
                    f"Troppi aggiornamenti PF ravvicinati — "
                    f"aspetta {int(remaining) + 1} secondi."
                )
            _host_cooldowns.hp_self_update_last_at[key] = now
            return None

        if kind in (perm.CMD_CONDITION_SELF_APPLY, perm.CMD_CONDITION_SELF_REMOVE):
            # Stesso principio di CMD_HP_SELF_UPDATE — backstop lato host
            # contro un client modificato (il client si limita già da solo).
            key = (actor_device_id, target_id)
            remaining = perm.cooldown_remaining(
                _host_cooldowns.condition_self_update_last_at.get(key, 0.0),
                perm.CONDITION_SELF_UPDATE_COOLDOWN_S,
            )
            if remaining > 0:
                return (
                    f"Troppi aggiornamenti di condizione ravvicinati — "
                    f"aspetta {int(remaining) + 1} secondi."
                )
            _host_cooldowns.condition_self_update_last_at[key] = now
            return None

        return None

    def fetch_events(self, world_id: str, since_seq: int = 0) -> list[WorldEvent]:
        return world_repo.get_events_since(world_id, since_seq)

    def connection_state(self) -> str:
        return "local"


# ---------------------------------------------------------------------------
# Handler dei comandi owner-only (§4) — gestione del mondo e dei membri
# (rinomina, rigenera codice, promuovi/retrocedi/espelli, trasferisci
# proprietà, elimina). Gli handler delle azioni master di §7 sulle istanze
# di personaggio (PE, danno, cura, condizioni, ...) vivono più sotto in
# questo stesso file, aggiunti dal passo 6.
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
    # Archivia (non elimina) le istanze possedute dal membro appena
    # espulso — vedi `character_repo.archive_world_instances()` per il
    # ragionamento completo, incluso su come si riattiva. `remove_member`
    # da solo toccava SOLO `world_members`, mai `characters`: senza questo
    # passo un'istanza restava per sempre visibile nella Sezione Master di
    # un mondo il cui proprietario non ne è più membro.
    archived_count = character_repo.archive_world_instances(ctx.world_id, device_id)
    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=perm.CMD_MEMBER_KICK, target_type="member", target_id=target.id,
        summary=(
            f"{ctx.actor_name} ha espulso {target.display_name} dal mondo"
            + (f" ({archived_count} personaggio/i archiviato/i)." if archived_count else ".")
        ),
        payload=json.dumps({"device_id": device_id, "archived_instances": archived_count}),
        before_state=json.dumps({"role": target.role, "display_name": target.display_name}),
    )
    return CommandResult(True, event=event)


@register_handler(perm.CMD_MEMBER_LEAVE)
def _handle_member_leave(ctx: HandlerContext) -> CommandResult:
    """
    Uscita volontaria dal mondo — controparte
    di `_handle_member_kick` sopra, stessa logica di rimozione/archiviazione,
    ma auto-diretta: nessun `device_id` nel payload, l'attore rimuove SOLO
    se stesso (`ctx.actor_device_id`), mai un altro membro — quello resta
    compito esclusivo di `CMD_MEMBER_KICK` (owner-only).
    """
    target = world_repo.get_member(ctx.world_id, ctx.actor_device_id)
    if target is None:
        return CommandResult(False, "Non sei membro di questo mondo.")
    if target.role == perm.ROLE_OWNER:
        return CommandResult(
            False, "Il proprietario non può uscire — trasferisci prima la proprietà.",
        )
    if not world_repo.remove_member(ctx.world_id, ctx.actor_device_id):
        return CommandResult(False, "Uscita fallita.")
    archived_count = character_repo.archive_world_instances(ctx.world_id, ctx.actor_device_id)
    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=perm.CMD_MEMBER_LEAVE, target_type="member", target_id=target.id,
        summary=(
            f"{ctx.actor_name} ha lasciato il mondo"
            + (f" ({archived_count} personaggio/i archiviato/i)." if archived_count else ".")
        ),
        payload=json.dumps({"device_id": ctx.actor_device_id, "archived_instances": archived_count}),
        before_state=json.dumps({"role": target.role, "display_name": target.display_name}),
    )
    return CommandResult(True, event=event)


@register_handler(perm.CMD_CHARACTER_INSTANCE_REMOVE)
def _handle_character_instance_remove(ctx: HandlerContext) -> CommandResult:
    """
    Rimuove UN personaggio dal mondo — a differenza di `CMD_MEMBER_KICK`,
    che espelle l'intero dispositivo e archivia TUTTE le sue istanze, qui il master
    sceglie UN personaggio mentre il suo giocatore resta membro (morte
    permanente, doppione, personaggio mai più usato). Stessa archiviazione
    non distruttiva del kick — vedi `character_repo.archive_world_instance`.
    """
    character = _resolve_world_character(ctx.world_id, ctx.target_id)
    if character is None:
        return CommandResult(False, "Personaggio non trovato in questo mondo.")
    if not character_repo.archive_world_instance(ctx.world_id, ctx.target_id):
        return CommandResult(False, "Rimozione del personaggio fallita.")
    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=perm.CMD_CHARACTER_INSTANCE_REMOVE, target_type="character",
        target_id=ctx.target_id,
        summary=f"{ctx.actor_name} ha rimosso {character.name} dal mondo",
        payload=json.dumps({"character_id": ctx.target_id, "name": character.name}),
    )
    return CommandResult(True, event=event)


_REJOIN_MODES = ("frozen", "refresh_from_local")


@register_handler(perm.CMD_CHARACTER_REJOIN_REQUEST)
def _handle_character_rejoin_request(ctx: HandlerContext) -> CommandResult:
    """
    Il proprietario di un'istanza ARCHIVIATA (espulsione o
    `CMD_CHARACTER_INSTANCE_REMOVE`) chiede al master di farla rientrare nel
    mondo — mai una riattivazione automatica: nessun altro punto del codice
    riporta `world_instance_archived` a 0.

    `mode`:
      - `"frozen"` (default): l'accettazione riprenderà l'istanza esattamente
        come fu archiviata, nessun altro dato coinvolto.
      - `"refresh_from_local"`: il giocatore vuole rientrare con lo stato
        ATTUALE della propria scheda locale di origine (può essere cambiata
        nel frattempo — livello, PF, inventario — mentre l'istanza restava
        congelata). Il client allega subito l'export integrale di quel
        personaggio locale (`ctx.payload["export"]`): uno snapshot preso ORA,
        applicato solo se e quando il master accetterà
        (`_handle_character_rejoin_respond` sotto), mai ricalcolato in quel
        momento — stesso principio già in uso per `change_request.propose`/
        `character_instance.sync`.
    """
    character = _resolve_world_character(ctx.world_id, ctx.target_id)
    if character is None:
        return CommandResult(False, "Personaggio non trovato in questo mondo.")
    if not character.world_instance_archived:
        return CommandResult(False, "Questo personaggio non è stato rimosso dal mondo.")
    if not perm.is_character_owner(ctx.actor_device_id, character.owner_device_id):
        return CommandResult(
            False, "Puoi richiedere il rientro solo di un tuo personaggio.",
        )

    if world_repo.get_pending_rejoin_request_for_character(character.id) is not None:
        return CommandResult(
            False, "Richiesta già inviata, in attesa di risposta del master.",
        )

    mode = str(ctx.payload.get("mode") or "frozen")
    if mode not in _REJOIN_MODES:
        return CommandResult(False, f"Modalità di rientro non valida: {mode!r}.")

    request_payload: dict = {"mode": mode}
    if mode == "refresh_from_local":
        export_data = ctx.payload.get("export")
        if not isinstance(export_data, dict):
            return CommandResult(
                False, "Dati della scheda locale mancanti o malformati.",
            )
        err = character_export.validate_export_data(export_data)
        if err:
            return CommandResult(False, f"Dati della scheda locale non validi: {err}")
        if export_data.get("character", {}).get("world_id"):
            return CommandResult(
                False, "Lo stato da usare per il rientro deve essere di un "
                       "personaggio locale, non di un'altra istanza di mondo.",
            )
        request_payload["export"] = export_data

    reason = str(ctx.payload.get("reason", ""))
    request = world_repo.create_rejoin_request(
        ctx.world_id, character.id, ctx.actor_device_id, ctx.actor_name,
        mode, json.dumps(request_payload), reason,
    )
    if request is None:
        return CommandResult(False, "Invio della richiesta di rientro fallito.")

    mode_label = "con lo stato attuale della scheda locale" if mode == "refresh_from_local" \
        else "con lo stato con cui era stato rimosso"
    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=perm.CMD_CHARACTER_REJOIN_REQUEST, target_type="character", target_id=character.id,
        summary=f"{ctx.actor_name} ha richiesto il rientro di «{character.name}» ({mode_label}).",
        payload=json.dumps({"request_id": request.id, "mode": mode}),
    )
    return CommandResult(True, event=event)


# ---------------------------------------------------------------------------
# Trasferimento del personaggio su un altro dispositivo (§11.9)
# ---------------------------------------------------------------------------
#
# Solo l'EMISSIONE e la REVOCA del codice passano da qui. Il riscatto no: vive
# in `WorldHostServer.handle_join`/`_approve_transfer`, perché per definizione
# lo esegue un dispositivo che non è ancora membro e quindi non ha un token né
# un ruolo — `LocalBackend.send_command` lo respingerebbe al primo controllo
# ("Il mittente non è membro di questo mondo").


def _can_issue_transfer_for(ctx: HandlerContext, member) -> str | None:
    """
    Verifica di proprietà per i due comandi sul codice di trasferimento.
    Restituisce un messaggio d'errore, oppure `None` se l'azione è consentita.

    Due strade legittime, entrambe volute:
    il GIOCATORE emette un codice per sé stesso (sta per cambiare telefono e ha
    ancora quello vecchio in mano), il MASTER lo emette per un giocatore il cui
    dispositivo è perso, rotto o venduto. Senza la seconda, il caso "telefono
    rotto" — quello che rende la funzione davvero utile — resterebbe scoperto.
    """
    if member is None:
        return "Membro non trovato in questo mondo."
    if member.role == perm.ROLE_OWNER:
        # L'owner ospita il mondo: il suo `device_id` è su `worlds.
        # owner_device_id` e la riassegnazione NON lo tocca (riscriverlo
        # sposterebbe la proprietà del mondo, che è un'altra operazione con un
        # altro comando). Per lui la via corretta esiste già ed è migliore:
        # esportare `.dndworld` e importarlo sul dispositivo nuovo, che rende
        # importatore = owner + host (§6.3/§11.4).
        return (
            "Il proprietario del mondo non si trasferisce con un codice: "
            "esporta il mondo in un file .dndworld e importalo sul nuovo "
            "dispositivo, che ne diventerà l'host."
        )
    if member.device_id == ctx.actor_device_id:
        return None
    if perm.role_at_least(ctx.actor_role, perm.ROLE_MASTER):
        return None
    return "Puoi generare un codice di trasferimento solo per il tuo dispositivo."


@register_handler(perm.CMD_DEVICE_TRANSFER_ISSUE)
def _handle_device_transfer_issue(ctx: HandlerContext) -> CommandResult:
    """
    Emette un codice monouso che permette a un ALTRO dispositivo di subentrare
    nell'appartenenza di un membro, portandosi via le sue istanze di personaggio.

    `payload`: `{"device_id": "<device del membro da sostituire>"}`.

    Il codice torna in `CommandResult.data`, **non** nel payload dell'evento: il
    giornale viene trasmesso a ogni replica via `GET /events`, quindi un segreto
    destinato a un solo membro non può passare da lì. L'evento resta comunque —
    serve al registro degli interventi (§5) e a far sapere al tavolo che un
    trasferimento è stato autorizzato — ma porta solo `device_id` e
    `transfer_id`.
    """
    device_id = str(ctx.payload.get("device_id", "")).strip()
    if not device_id:
        return CommandResult(False, "Dispositivo da trasferire non indicato.")

    member = world_repo.get_member(ctx.world_id, device_id)
    denial = _can_issue_transfer_for(ctx, member)
    if denial is not None:
        return CommandResult(False, denial)

    transfer = world_transfer_repo.issue_transfer(
        ctx.world_id, device_id, member.display_name, ctx.actor_device_id,
    )
    if transfer is None:
        return CommandResult(False, "Generazione del codice di trasferimento fallita.")

    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=perm.CMD_DEVICE_TRANSFER_ISSUE, target_type="member",
        target_id=member.id,
        summary=(
            f"{ctx.actor_name} ha generato un codice di trasferimento per "
            f"{member.display_name}."
        ),
        payload=json.dumps({"device_id": device_id, "transfer_id": transfer.id}),
    )
    return CommandResult(True, event=event, data={
        "transfer_id": transfer.id,
        "code": transfer.code,
        "expires_at": transfer.expires_at,
        "member_display_name": member.display_name,
    })


@register_handler(perm.CMD_DEVICE_TRANSFER_REVOKE)
def _handle_device_transfer_revoke(ctx: HandlerContext) -> CommandResult:
    """
    Annulla un codice non ancora riscattato — specchio dell'emissione, stessa
    verifica di proprietà. Serve quando il codice è stato letto ad alta voce per
    sbaglio, o quando il vecchio telefono riappare.
    """
    device_id = str(ctx.payload.get("device_id", "")).strip()
    if not device_id:
        return CommandResult(False, "Dispositivo da trasferire non indicato.")

    member = world_repo.get_member(ctx.world_id, device_id)
    denial = _can_issue_transfer_for(ctx, member)
    if denial is not None:
        return CommandResult(False, denial)

    transfer = world_transfer_repo.get_pending_transfer_for_member(ctx.world_id, device_id)
    if transfer is None:
        return CommandResult(False, "Nessun codice di trasferimento attivo per questo dispositivo.")
    if not world_transfer_repo.revoke_transfer(transfer.id):
        return CommandResult(False, "Revoca del codice fallita.")

    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=perm.CMD_DEVICE_TRANSFER_REVOKE, target_type="member",
        target_id=member.id,
        summary=(
            f"{ctx.actor_name} ha revocato il codice di trasferimento di "
            f"{member.display_name}."
        ),
        payload=json.dumps({"device_id": device_id, "transfer_id": transfer.id}),
    )
    return CommandResult(True, event=event)


@register_handler(perm.CMD_CHARACTER_REJOIN_RESPOND)
def _handle_character_rejoin_respond(ctx: HandlerContext) -> CommandResult:
    """
    Il master accetta o rifiuta una richiesta di rientro —
    unico punto del codice che toglie davvero l'archiviazione di
    un'istanza, in un modo o nell'altro a seconda di `request.mode`.
    """
    request_id = str(ctx.payload.get("request_id", ""))
    accept = bool(ctx.payload.get("accept", False))

    request = world_repo.get_rejoin_request(request_id)
    if request is None or request.world_id != ctx.world_id:
        return CommandResult(False, "Richiesta di rientro non trovata.")
    if request.status != "pending":
        return CommandResult(False, "Questa richiesta è già stata gestita.")

    character = _resolve_world_character(ctx.world_id, request.character_id)
    if character is None:
        return CommandResult(False, "Personaggio non trovato in questo mondo.")
    if not character.world_instance_archived:
        # Race (es. doppio accept da due dispositivi master): niente da
        # applicare di nuovo, ma la richiesta va comunque chiusa — non deve
        # restare "pending" per sempre.
        world_repo.resolve_rejoin_request(request_id, "accepted")
        return CommandResult(True)

    if accept:
        # Guardia: il richiedente potrebbe essere stato espulso dal mondo
        # DOPO l'invio della richiesta ma PRIMA della risposta del master —
        # riammettere un personaggio il cui proprietario non è più membro
        # produrrebbe uno stato incoerente (istanza attiva, nessun membro
        # proprietario).
        if world_repo.get_member(ctx.world_id, request.requested_by) is None:
            world_repo.resolve_rejoin_request(request_id, "expired")
            return CommandResult(
                False, "Il proprietario non è più membro di questo mondo — "
                       "la richiesta non è più valida.",
            )

        if request.mode == "refresh_from_local":
            try:
                payload = json.loads(request.payload or "{}")
            except (json.JSONDecodeError, TypeError):
                payload = {}
            export_data = payload.get("export")
            if not isinstance(export_data, dict):
                return CommandResult(False, "Dati della richiesta corrotti o mancanti.")
            result_id = character_export.import_character_data_as_world_refresh(
                export_data, character.id, world_id=ctx.world_id,
                origin_character_id=character.origin_character_id,
                owner_device_id=character.owner_device_id,
            )
            if result_id is None:
                return CommandResult(False, "Aggiornamento dell'istanza fallito.")
        else:
            if not character_repo.unarchive_world_instance(character.id):
                return CommandResult(False, "Riattivazione dell'istanza fallita.")

    if not world_repo.resolve_rejoin_request(request_id, "accepted" if accept else "rejected"):
        return CommandResult(False, "Aggiornamento dello stato della richiesta fallito.")

    verb = "accettato" if accept else "rifiutato"
    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=perm.CMD_CHARACTER_REJOIN_RESPOND, target_type="character", target_id=character.id,
        summary=f"{ctx.actor_name} ha {verb} il rientro di «{character.name}» nel mondo.",
        payload=json.dumps({"request_id": request_id, "accept": accept, "mode": request.mode}),
    )
    return CommandResult(True, event=event)


def _update_world_owner(world_id: str, new_owner_device_id: str) -> bool:
    """Aggiorna `worlds.owner_device_id` — non esposto in `world_repo` come
    CRUD pubblico perché è significativo SOLO nel contesto di un
    trasferimento di proprietà già validato qui, mai come scrittura diretta
    dalla UI."""
    from data.database import get_connection
    conn = None
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE worlds SET owner_device_id=?, updated_at=? WHERE id=?",
            (new_owner_device_id, datetime.now().isoformat(), world_id),
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error("Errore _update_world_owner: %s", e)
        return False
    finally:
        if conn is not None:
            conn.close()


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
# Handler dei comandi master/owner sulle istanze di personaggio — §7 del
# design doc, passo 6 del piano (`multiplayer_design.md` §13). Operativi da
# qui in poi: le istanze esistono dal passo 3, il trasporto di rete dal
# passo 4, questo passo aggiunge il pezzo che mancava — le AZIONI vere e
# proprie che risolvono "il problema di partenza" (§1: il master non ha
# modo di intervenire sulla scheda di un giocatore su un altro dispositivo).
#
# Ogni handler qui sotto:
#   1. risolve `ctx.target_id` a un personaggio che è DAVVERO un'istanza
#      di QUESTO mondo (`_resolve_world_character`) — fail-closed, altrimenti
#      un comando potrebbe toccare un personaggio di un mondo diverso;
#   2. applica l'effetto con le stesse funzioni di `character_repo.py` già
#      usate dalla scheda locale (nessuna logica duplicata: dove esisteva
#      già un algoritmo non banale — il danno/la cura — è stato spostato in
#      `core/damage_rules.py` ed è riusato qui, non riscritto);
#   3. scrive un evento con un `summary` leggibile — è il registro del
#      mondo (§5), non una tabella a parte.
#
# Fuori scope in questo passo (resta nella matrice dei permessi ma senza
# handler, esattamente come CMD_MAP_PUBLISH/CMD_MAP_DRAW lo erano prima del
# passo 8 — non ridiscutere chi può inviarlo, solo aggiungere l'handler
# quando arriva il suo passo): CMD_DICE_REQUEST (è una richiesta senza
# scrittura sul personaggio — richiede un meccanismo di notifica lato
# giocatore non ancora progettato, valutato a parte).
#
# CMD_LOOT_ASSIGN non è più fuori scope: ha il suo handler più sotto,
# subito dopo `_handle_xp_grant`, e passa da `_resolve_world_character()`
# come gli altri comandi di questo blocco.
#
# CMD_NOTE_SHARE (passo 7B, §6.2), CMD_ENCOUNTER_MANAGE/
# CMD_COMBAT_TOGGLE_VISIBILITY (passo 7C, §6.5) e CMD_MAP_PUBLISH/
# CMD_MAP_DRAW (passo 8, §6.4) hanno il loro handler più sotto, dopo
# `_handle_character_instance_sync` — non toccano `characters`, quindi non
# passano da `_resolve_world_character()`.
# ---------------------------------------------------------------------------

def _resolve_world_character(world_id: str, character_id: str):
    """
    Il personaggio bersaglio di un comando sulle istanze — deve esistere ed
    essere davvero un'istanza DI QUESTO mondo (`characters.world_id ==
    world_id`), altrimenti un comando (anche da un master legittimo di un
    ALTRO mondo, o un client che manda un id a caso) potrebbe toccare un
    personaggio che non gli compete. Fail-closed, nessun default permissivo
    — stesso principio di `can_perform()`.
    """
    if not character_id:
        return None
    character = character_repo.get_by_id(character_id)
    if character is None or character.world_id != world_id:
        return None
    return character


@register_handler(perm.CMD_XP_GRANT)
def _handle_xp_grant(ctx: HandlerContext) -> CommandResult:
    """Assegna PE — già esisteva come azione diretta same-device
    (`character_repo.add_xp()`, Fase 4); qui passa dal comando per
    ottenere permessi verificati e un evento nel registro anche quando il
    personaggio bersaglio è su un dispositivo remoto. Il livello NON viene
    toccato: sale il giocatore dalla propria scheda (invariato)."""
    character = _resolve_world_character(ctx.world_id, ctx.target_id)
    if character is None:
        return CommandResult(False, "Personaggio non trovato in questo mondo.")
    try:
        amount = int(ctx.payload.get("amount", 0))
    except (TypeError, ValueError):
        return CommandResult(False, "Quantità PE non valida.")
    if amount == 0:
        return CommandResult(False, "La quantità di PE non può essere zero.")

    old_xp = character.xp
    new_xp = character_repo.add_xp(character.id, amount)
    if new_xp is None:
        return CommandResult(False, "Assegnazione PE fallita.")

    verb = "assegnato" if amount > 0 else "tolto"
    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=perm.CMD_XP_GRANT, target_type="character", target_id=character.id,
        summary=f"{ctx.actor_name} ha {verb} {abs(amount)} PE a {character.name} "
                f"({old_xp} → {new_xp}).",
        payload=json.dumps({"amount": amount}),
        before_state=json.dumps({"xp": old_xp}),
    )
    return CommandResult(True, event=event)


@register_handler(perm.CMD_LOOT_ASSIGN)
def _handle_loot_assign(ctx: HandlerContext) -> CommandResult:
    """
    Assegna un lotto di oggetti/monete a uno o più personaggi di questo
    mondo. Ogni riga del payload risolve il proprio `target_character_id`
    in modo indipendente e fail-closed via
    `_resolve_world_character(ctx.world_id, ...)` — questo è precisamente
    ciò che impedisce a un master non-host su un ALTRO mondo di scrivere
    per errore in un personaggio che non gli compete. Righe con un id che
    non risolve a un personaggio DI QUESTO mondo vengono saltate (non
    abortiscono l'intero batch): il Master vede
    comunque applicato tutto ciò che era valido, coerente con la UI che
    ricalcola le ripartizioni prima di inviare (validazione già fatta lato
    client, questo è un controllo di sicurezza in profondità).

    UN EVENTO PER PERSONAGGIO EFFETTIVAMENTE COINVOLTO, non un solo evento
    per l'intero batch: `core.world_sync.apply_event_to_replica` rimaterializza
    la replica di un personaggio SOLO per un evento con
    `target_type=="character"` (vedi il suo `if event.kind in
    CHARACTER_MUTATING_COMMANDS and event.target_type == "character"`) — un
    unico evento con `target_type="world"` per un'assegnazione a più
    personaggi non farebbe MAI aggiornare le repliche di quei personaggi.
    """
    items = ctx.payload.get("items", [])
    coins = ctx.payload.get("coins", [])
    if not isinstance(items, list):
        items = []
    if not isinstance(coins, list):
        coins = []
    if not items and not coins:
        return CommandResult(False, "Nessuna voce da assegnare.")

    # Raggruppa per personaggio bersaglio così ognuno riceve un solo evento
    # (oggetti + monete insieme, se entrambi presenti), invece di un evento
    # per riga — più leggibile nel registro e meno rumore di resync.
    per_character: dict[str, dict] = {}

    def _bucket(character_id: str):
        character = _resolve_world_character(ctx.world_id, character_id)
        if character is None:
            return None
        return per_character.setdefault(
            character.id, {"character": character, "item_names": [], "coins_applied": False},
        )

    for it in items:
        if not isinstance(it, dict):
            continue
        name = str(it.get("name", "")).strip()
        if not name:
            continue
        bucket = _bucket(str(it.get("target_character_id", "")))
        if bucket is None:
            continue
        quantity = int(it.get("quantity", 1) or 1)
        # "weapon"/"armor" (2026-08-20, bug report Davide: le voci
        # arma/armatura devono avere le stesse caselle della scheda
        # giocatore) scrivono su tabelle diverse dall'`inventory_items`
        # generico — stessa logica di `_create_recipient_item()` in
        # `master_loot_assign_dialog.py` (duplicata qui perché gira
        # sull'host, non sul dispositivo del Master).
        if str(it.get("entry_kind", "")) == "weapon":
            ok = False
            for _ in range(max(1, quantity)):
                ok = character_repo.create_weapon(
                    bucket["character"].id, name,
                    damage_dice=str(it.get("weapon_damage_dice", "")),
                    damage_type=str(it.get("weapon_damage_type", "")),
                    attack_bonus=int(it.get("weapon_attack_bonus", 0) or 0),
                    damage_bonus=int(it.get("weapon_damage_bonus", 0) or 0),
                    properties=str(it.get("weapon_properties", "")),
                    weapon_category=str(it.get("weapon_category", "")),
                    magic_description=str(it.get("description", "")),
                    magic_damages=str(it.get("weapon_magic_damages", "[]") or "[]"),
                    is_magical=bool(it.get("requires_attunement"))
                    or bool(it.get("weapon_attack_bonus") or it.get("weapon_damage_bonus"))
                    or it.get("weapon_magic_damages", "[]") not in ("", "[]"),
                ) or ok
            created = name if ok else None
        elif str(it.get("entry_kind", "")) == "armor":
            created = character_repo.create_inventory_item(
                bucket["character"].id, name, quantity=quantity, category="armor",
                description=str(it.get("description", "")),
                ca_value=int(it.get("armor_ca_value", 0) or 0),
                armor_type=str(it.get("armor_type", "")),
                effects=str(it.get("armor_effects", "")),
                requires_attunement=bool(it.get("requires_attunement", False)),
            )
        else:
            created = character_repo.create_inventory_item(
                bucket["character"].id, name, quantity=quantity,
                description=str(it.get("description", "")),
                category=str(it.get("category", "misc")) or "misc",
                requires_attunement=bool(it.get("requires_attunement", False)),
                effects=str(it.get("effects", "")),
            )
        if created is not None:
            bucket["item_names"].append(name)

    for c in coins:
        if not isinstance(c, dict):
            continue
        bucket = _bucket(str(c.get("target_character_id", "")))
        if bucket is None:
            continue
        character = bucket["character"]
        existing = character_repo.get_currencies(character.id)
        ok = character_repo.update_currencies(
            character.id,
            (existing.copper if existing else 0) + int(c.get("copper", 0) or 0),
            (existing.silver if existing else 0) + int(c.get("silver", 0) or 0),
            (existing.electrum if existing else 0) + int(c.get("electrum", 0) or 0),
            (existing.gold if existing else 0) + int(c.get("gold", 0) or 0),
            (existing.platinum if existing else 0) + int(c.get("platinum", 0) or 0),
        )
        bucket["coins_applied"] = bucket["coins_applied"] or ok

    n_chars = 0
    last_event = None
    for bucket in per_character.values():
        if not bucket["item_names"] and not bucket["coins_applied"]:
            continue
        character = bucket["character"]
        bits = []
        if bucket["item_names"]:
            bits.append(", ".join(f"«{n}»" for n in bucket["item_names"]))
        if bucket["coins_applied"]:
            bits.append("monete")
        n_chars += 1
        last_event = world_repo.append_event(
            ctx.world_id, ctx.actor_device_id, ctx.actor_name,
            kind=perm.CMD_LOOT_ASSIGN, target_type="character", target_id=character.id,
            summary=f"{ctx.actor_name} ha assegnato a {character.name}: " + " e ".join(bits) + ".",
            payload=json.dumps({
                "item_names": bucket["item_names"], "coins_applied": bucket["coins_applied"],
            }),
        )

    if n_chars == 0 or last_event is None:
        return CommandResult(False, "Nessuna voce valida per questo mondo.")
    return CommandResult(True, event=last_event)


@register_handler(perm.CMD_HP_DAMAGE)
def _handle_hp_damage(ctx: HandlerContext) -> CommandResult:
    """Applica danno — stessa regola PHB della scheda locale
    (`core/damage_rules.apply_damage`, riusata qui senza duplicare
    l'algoritmo)."""
    character = _resolve_world_character(ctx.world_id, ctx.target_id)
    if character is None:
        return CommandResult(False, "Personaggio non trovato in questo mondo.")
    try:
        amount = int(ctx.payload.get("amount", 0))
    except (TypeError, ValueError):
        return CommandResult(False, "Quantità di danno non valida.")
    if amount <= 0:
        return CommandResult(False, "La quantità di danno deve essere positiva.")
    is_critical = bool(ctx.payload.get("is_critical", False))

    before = {"hp_current": character.hp_current, "hp_temp": character.hp_temp}
    outcome = damage_rules.apply_damage(character, amount, is_critical=is_critical)
    character_repo.update_hp(character.id, character.hp_current, character.hp_temp)
    if outcome.death_note:
        character_repo.update_death_saves(
            character.id, character.death_saves_success, character.death_saves_failure,
        )
    if outcome.concentration_broken:
        character_repo.clear_concentration(character.id)

    summary = (
        f"{ctx.actor_name} ha applicato {outcome.amount_requested} danni a "
        f"{character.name} ({before['hp_current']} → {character.hp_current} PF)."
    )
    if outcome.death_note:
        summary += " " + outcome.death_note.splitlines()[0]
    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=perm.CMD_HP_DAMAGE, target_type="character", target_id=character.id,
        summary=summary,
        payload=json.dumps({"amount": amount, "is_critical": is_critical}),
        before_state=json.dumps(before),
    )
    return CommandResult(True, event=event)


@register_handler(perm.CMD_HP_HEAL)
def _handle_hp_heal(ctx: HandlerContext) -> CommandResult:
    """Applica cura — `core/damage_rules.apply_heal`, stesso principio del
    danno."""
    character = _resolve_world_character(ctx.world_id, ctx.target_id)
    if character is None:
        return CommandResult(False, "Personaggio non trovato in questo mondo.")
    try:
        amount = int(ctx.payload.get("amount", 0))
    except (TypeError, ValueError):
        return CommandResult(False, "Quantità di cura non valida.")
    if amount <= 0:
        return CommandResult(False, "La quantità di cura deve essere positiva.")

    before_hp = character.hp_current
    outcome = damage_rules.apply_heal(character, amount)
    character_repo.update_hp(character.id, character.hp_current, character.hp_temp)
    if outcome.death_saves_reset:
        character_repo.update_death_saves(
            character.id, character.death_saves_success, character.death_saves_failure,
        )

    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=perm.CMD_HP_HEAL, target_type="character", target_id=character.id,
        summary=f"{ctx.actor_name} ha curato {character.name} di {amount} PF "
                f"({before_hp} → {character.hp_current}).",
        payload=json.dumps({"amount": amount}),
        before_state=json.dumps({"hp_current": before_hp}),
    )
    return CommandResult(True, event=event)


@register_handler(perm.CMD_HP_SELF_UPDATE)
def _handle_hp_self_update(ctx: HandlerContext) -> CommandResult:
    """
    Il giocatore stesso invia lo stato aggiornato dei propri PF/TS contro
    morte dopo averli già modificati sulla propria scheda — sincronizzazione
    automatica (§7), non più solo manuale come «Aggiorna il mio foglio»
    §6.1, che resta per il resync completo, non per i soli PF.

    Come `_handle_change_request_respond`: il ruolo da solo non basta,
    serve anche `perm.is_character_owner()` — altrimenti un giocatore
    potrebbe scrivere sui PF di un altro. A differenza degli altri
    handler qui sopra, NON passa da `core/damage_rules.py`: il calcolo
    (assorbimento HP temp, morte istantanea, tiri salvezza contro morte,
    concentrazione) è già stato applicato dal chiamante sulla PROPRIA
    copia locale — qui si scrive il risultato finale, a valori assoluti
    (mai un delta: un invio perso non lascia lo stato incoerente, il
    prossimo invio porta comunque il valore più recente, idempotente).
    """
    character = _resolve_world_character(ctx.world_id, ctx.target_id)
    if character is None:
        return CommandResult(False, "Personaggio non trovato in questo mondo.")
    if not perm.is_character_owner(ctx.actor_device_id, character.owner_device_id):
        return CommandResult(
            False, "Solo il proprietario del personaggio può aggiornarne i PF.",
        )

    try:
        hp_current = int(ctx.payload.get("hp_current", character.hp_current))
        hp_temp = int(ctx.payload.get("hp_temp", character.hp_temp))
        death_saves_success = int(ctx.payload.get("death_saves_success",
                                                    character.death_saves_success))
        death_saves_failure = int(ctx.payload.get("death_saves_failure",
                                                    character.death_saves_failure))
    except (TypeError, ValueError):
        return CommandResult(False, "Valori PF non validi.")

    hp_current = max(0, min(character.hp_max, hp_current)) if character.hp_max else max(0, hp_current)
    hp_temp = max(0, hp_temp)
    death_saves_success = max(0, min(3, death_saves_success))
    death_saves_failure = max(0, min(3, death_saves_failure))

    before = {
        "hp_current": character.hp_current, "hp_temp": character.hp_temp,
        "death_saves_success": character.death_saves_success,
        "death_saves_failure": character.death_saves_failure,
    }
    if not character_repo.update_hp(character.id, hp_current, hp_temp):
        return CommandResult(False, "Aggiornamento PF fallito.")
    character_repo.update_death_saves(character.id, death_saves_success, death_saves_failure)

    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=perm.CMD_HP_SELF_UPDATE, target_type="character", target_id=character.id,
        summary=f"{character.name}: {before['hp_current']} → {hp_current} PF "
                f"(aggiornamento dalla scheda).",
        payload=json.dumps({
            "hp_current": hp_current, "hp_temp": hp_temp,
            "death_saves_success": death_saves_success,
            "death_saves_failure": death_saves_failure,
        }),
        before_state=json.dumps(before),
    )
    return CommandResult(True, event=event)


@register_handler(perm.CMD_NOTES_SELF_UPDATE)
def _handle_notes_self_update(ctx: HandlerContext) -> CommandResult:
    """
    Il giocatore stesso invia il testo aggiornato delle proprie "Appunti di
    sessione" — estensione di `CMD_HP_SELF_UPDATE`, stesso principio:
    valore assoluto, mai un delta, idempotente come `hp.self_update`.
    """
    character = _resolve_world_character(ctx.world_id, ctx.target_id)
    if character is None:
        return CommandResult(False, "Personaggio non trovato in questo mondo.")
    if not perm.is_character_owner(ctx.actor_device_id, character.owner_device_id):
        return CommandResult(
            False, "Solo il proprietario del personaggio può aggiornarne le note.",
        )
    notes = str(ctx.payload.get("notes", ""))
    if not character_repo.update_session_notes(character.id, notes):
        return CommandResult(False, "Aggiornamento delle note fallito.")

    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=perm.CMD_NOTES_SELF_UPDATE, target_type="character", target_id=character.id,
        summary=f"{character.name} ha aggiornato le proprie note di sessione.",
        payload=json.dumps({"notes": notes}),
    )
    return CommandResult(True, event=event)


def _apply_condition_to_character(
    ctx: HandlerContext, character, *, kind: str, summary_verb: str = "ha imposto",
) -> CommandResult:
    """
    Nucleo comune a `_handle_condition_apply` (master/owner) e
    `_handle_condition_self_apply` (estensione graduale di
    hp.self_update): stessa identica scrittura, cambia solo CHI può
    invocarla — la verifica di permesso/proprietà resta nel chiamante,
    mai qui, per lo stesso principio di separazione già seguito altrove in
    questo file (un handler valida, poi applica).
    """
    condition_key = str(ctx.payload.get("condition_key", "")).strip()
    if not condition_key:
        return CommandResult(False, "Condizione mancante.")

    from data.game_data.game_data_loader import GameDataLoader
    condition_data = GameDataLoader().get_condition(condition_key)
    if condition_data is None:
        return CommandResult(False, f"Condizione sconosciuta: «{condition_key}».")

    source = str(ctx.payload.get("source", "")) or ctx.actor_name
    note = str(ctx.payload.get("note", ""))
    condition_id = character_repo.add_condition(character.id, condition_key, source, note)
    if condition_id is None:
        return CommandResult(False, "Applicazione della condizione fallita.")

    condition_name = condition_data.get("name", condition_key)
    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=kind, target_type="character", target_id=character.id,
        summary=f"{ctx.actor_name} {summary_verb} la condizione «{condition_name}» a {character.name}.",
        payload=json.dumps({"condition_key": condition_key, "source": source, "note": note}),
    )
    return CommandResult(True, event=event)


@register_handler(perm.CMD_CONDITION_APPLY)
def _handle_condition_apply(ctx: HandlerContext) -> CommandResult:
    character = _resolve_world_character(ctx.world_id, ctx.target_id)
    if character is None:
        return CommandResult(False, "Personaggio non trovato in questo mondo.")
    return _apply_condition_to_character(ctx, character, kind=perm.CMD_CONDITION_APPLY)


@register_handler(perm.CMD_CONDITION_SELF_APPLY)
def _handle_condition_self_apply(ctx: HandlerContext) -> CommandResult:
    """
    Il giocatore stesso applica una condizione dalla propria scheda
    (estensione graduale di hp.self_update — vedi il docstring
    di `perm.CMD_CONDITION_SELF_APPLY`). Come `_handle_hp_self_update`: il
    ruolo `player` da solo non basta, serve `perm.is_character_owner()`.
    """
    character = _resolve_world_character(ctx.world_id, ctx.target_id)
    if character is None:
        return CommandResult(False, "Personaggio non trovato in questo mondo.")
    if not perm.is_character_owner(ctx.actor_device_id, character.owner_device_id):
        return CommandResult(
            False, "Solo il proprietario del personaggio può applicarsi una condizione.",
        )
    return _apply_condition_to_character(
        ctx, character, kind=perm.CMD_CONDITION_SELF_APPLY, summary_verb="si è imposto/a",
    )


def _remove_condition_from_character(
    ctx: HandlerContext, character, *, kind: str,
) -> CommandResult:
    """Rimozione per `condition_id` — usata SOLO da `_handle_condition_remove`
    (master/owner, che agisce sulla riga autoritativa dell'host: l'id letto
    da lì è sempre corretto). `_handle_condition_self_remove` NON riusa
    questa funzione: identifica per `condition_key` invece, vedi il suo
    docstring per il perché (un id di replica non ha significato sull'host)."""
    condition_id = str(ctx.payload.get("condition_id", "")).strip()
    if not condition_id:
        return CommandResult(False, "Condizione da rimuovere non specificata.")

    existing = [c for c in character_repo.get_conditions(character.id) if c.id == condition_id]
    if not existing:
        return CommandResult(False, "Condizione non trovata su questo personaggio.")
    condition = existing[0]

    if not character_repo.remove_condition(condition_id):
        return CommandResult(False, "Rimozione della condizione fallita.")

    from data.game_data.game_data_loader import GameDataLoader
    condition_data = GameDataLoader().get_condition(condition.condition_key) or {}
    condition_name = condition_data.get("name", condition.condition_key)
    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=kind, target_type="character", target_id=character.id,
        summary=f"{ctx.actor_name} ha rimosso la condizione «{condition_name}» da {character.name}.",
        payload=json.dumps({"condition_id": condition_id}),
        before_state=json.dumps({"condition_key": condition.condition_key}),
    )
    return CommandResult(True, event=event)


@register_handler(perm.CMD_CONDITION_REMOVE)
def _handle_condition_remove(ctx: HandlerContext) -> CommandResult:
    character = _resolve_world_character(ctx.world_id, ctx.target_id)
    if character is None:
        return CommandResult(False, "Personaggio non trovato in questo mondo.")
    return _remove_condition_from_character(ctx, character, kind=perm.CMD_CONDITION_REMOVE)


@register_handler(perm.CMD_CONDITION_SELF_REMOVE)
def _handle_condition_self_remove(ctx: HandlerContext) -> CommandResult:
    """
    Il giocatore stesso rimuove una condizione dalla propria scheda — vedi
    `_handle_condition_self_apply` per la verifica di proprietà.

    A DIFFERENZA di `_handle_condition_remove` (master, che identifica la
    riga da rimuovere per `condition_id`): quell'id è quello della replica
    LOCALE del giocatore su `character_conditions`, una tabella figlio che
    non condivide MAI gli id con la riga autoritativa dell'host — ogni
    rimaterializzazione della replica (`character_export.
    import_replica_character()`) rigenera un id nuovo per ogni riga figlio
    (`_insert_row`, `row_overrides["id"] = uuid4()`), quindi un id nato sul
    dispositivo del giocatore non identifica nulla sull'host. Qui si
    identifica per `condition_key` (cosa la condizione È, non quale riga
    opaca la rappresenta) — stesso principio di `hp.self_update`, che usa
    sempre valori assoluti/chiavi note, mai un id di replica.
    """
    character = _resolve_world_character(ctx.world_id, ctx.target_id)
    if character is None:
        return CommandResult(False, "Personaggio non trovato in questo mondo.")
    if not perm.is_character_owner(ctx.actor_device_id, character.owner_device_id):
        return CommandResult(
            False, "Solo il proprietario del personaggio può rimuoversi una condizione.",
        )
    condition_key = str(ctx.payload.get("condition_key", "")).strip()
    if not condition_key:
        return CommandResult(False, "Condizione da rimuovere non specificata.")

    matches = [c for c in character_repo.get_conditions(character.id)
               if c.condition_key == condition_key]
    if not matches:
        return CommandResult(False, "Condizione non trovata su questo personaggio.")
    for m in matches:
        character_repo.remove_condition(m.id)

    from data.game_data.game_data_loader import GameDataLoader
    condition_data = GameDataLoader().get_condition(condition_key) or {}
    condition_name = condition_data.get("name", condition_key)
    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=perm.CMD_CONDITION_SELF_REMOVE, target_type="character", target_id=character.id,
        summary=f"{character.name} si è tolto/a la condizione «{condition_name}».",
        payload=json.dumps({"condition_key": condition_key}),
        before_state=json.dumps({"removed_count": len(matches)}),
    )
    return CommandResult(True, event=event)


def _resource_max(resource) -> int:
    return int(resource.max_value or 0) + int(resource.max_value_bonus or 0)


@register_handler(perm.CMD_RESOURCE_CONSUME)
def _handle_resource_consume(ctx: HandlerContext) -> CommandResult:
    character = _resolve_world_character(ctx.world_id, ctx.target_id)
    if character is None:
        return CommandResult(False, "Personaggio non trovato in questo mondo.")
    resource_id = str(ctx.payload.get("resource_id", "")).strip()
    try:
        amount = int(ctx.payload.get("amount", 1))
    except (TypeError, ValueError):
        return CommandResult(False, "Quantità non valida.")
    if amount <= 0:
        return CommandResult(False, "La quantità deve essere positiva.")

    resources = [r for r in character_repo.get_class_resources(character.id) if r.id == resource_id]
    if not resources:
        return CommandResult(False, "Risorsa non trovata su questo personaggio.")
    resource = resources[0]

    old_value = resource.current_value
    new_value = max(0, old_value - amount)
    if not character_repo.update_class_resource(resource_id, new_value):
        return CommandResult(False, "Aggiornamento della risorsa fallito.")

    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=perm.CMD_RESOURCE_CONSUME, target_type="character", target_id=character.id,
        summary=f"{ctx.actor_name} ha consumato {old_value - new_value} «{resource.name}» "
                f"di {character.name} ({old_value} → {new_value}).",
        payload=json.dumps({"resource_id": resource_id, "amount": amount}),
        before_state=json.dumps({"current_value": old_value}),
    )
    return CommandResult(True, event=event)


@register_handler(perm.CMD_RESOURCE_RESTORE)
def _handle_resource_restore(ctx: HandlerContext) -> CommandResult:
    character = _resolve_world_character(ctx.world_id, ctx.target_id)
    if character is None:
        return CommandResult(False, "Personaggio non trovato in questo mondo.")
    resource_id = str(ctx.payload.get("resource_id", "")).strip()
    try:
        amount = int(ctx.payload.get("amount", 1))
    except (TypeError, ValueError):
        return CommandResult(False, "Quantità non valida.")
    if amount <= 0:
        return CommandResult(False, "La quantità deve essere positiva.")

    resources = [r for r in character_repo.get_class_resources(character.id) if r.id == resource_id]
    if not resources:
        return CommandResult(False, "Risorsa non trovata su questo personaggio.")
    resource = resources[0]

    old_value = resource.current_value
    new_value = min(_resource_max(resource), old_value + amount)
    if not character_repo.update_class_resource(resource_id, new_value):
        return CommandResult(False, "Aggiornamento della risorsa fallito.")

    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=perm.CMD_RESOURCE_RESTORE, target_type="character", target_id=character.id,
        summary=f"{ctx.actor_name} ha ripristinato {new_value - old_value} «{resource.name}» "
                f"di {character.name} ({old_value} → {new_value}).",
        payload=json.dumps({"resource_id": resource_id, "amount": amount}),
        before_state=json.dumps({"current_value": old_value}),
    )
    return CommandResult(True, event=event)


@register_handler(perm.CMD_CUSTOM_ABILITY_GRANT)
def _handle_custom_ability_grant(ctx: HandlerContext) -> CommandResult:
    character = _resolve_world_character(ctx.world_id, ctx.target_id)
    if character is None:
        return CommandResult(False, "Personaggio non trovato in questo mondo.")
    category = str(ctx.payload.get("category", "")).strip()
    name = str(ctx.payload.get("name", "")).strip()
    description = str(ctx.payload.get("description", ""))
    if category not in ("esplorazione", "combattimento"):
        return CommandResult(False, "Categoria non valida (esplorazione|combattimento).")
    if not name:
        return CommandResult(False, "Nome dell'abilità mancante.")

    ability_id = character_repo.create_custom_ability(character.id, category, name, description)
    if ability_id is None:
        return CommandResult(False, "Concessione dell'abilità fallita.")

    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=perm.CMD_CUSTOM_ABILITY_GRANT, target_type="character", target_id=character.id,
        summary=f"{ctx.actor_name} ha concesso a {character.name} l'abilità speciale «{name}».",
        payload=json.dumps({"category": category, "name": name, "description": description}),
    )
    return CommandResult(True, event=event)


@register_handler(perm.CMD_CUSTOM_ABILITY_SELF_CREATE)
def _handle_custom_ability_self_create(ctx: HandlerContext) -> CommandResult:
    """
    Il giocatore stesso crea una propria abilità personalizzata — estensione
    di `CMD_HP_SELF_UPDATE`; copre sia il tab Esplorazione che il tab
    Combattimento (`esplorazione_tab.py`/`combattimento_tab.py`, entrambi
    sulla stessa tabella `custom_abilities`). Come
    `_handle_hp_self_update`: il ruolo `player` da solo non basta, serve
    `perm.is_character_owner()`.
    """
    character = _resolve_world_character(ctx.world_id, ctx.target_id)
    if character is None:
        return CommandResult(False, "Personaggio non trovato in questo mondo.")
    if not perm.is_character_owner(ctx.actor_device_id, character.owner_device_id):
        return CommandResult(
            False, "Solo il proprietario del personaggio può creare una propria abilità.",
        )
    category = str(ctx.payload.get("category", "")).strip()
    name = str(ctx.payload.get("name", "")).strip()
    description = str(ctx.payload.get("description", ""))
    if category not in ("esplorazione", "combattimento"):
        return CommandResult(False, "Categoria non valida (esplorazione|combattimento).")
    if not name:
        return CommandResult(False, "Nome dell'abilità mancante.")

    ability_id = character_repo.create_custom_ability(character.id, category, name, description)
    if ability_id is None:
        return CommandResult(False, "Creazione dell'abilità fallita.")

    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=perm.CMD_CUSTOM_ABILITY_SELF_CREATE, target_type="character", target_id=character.id,
        summary=f"{character.name} ha creato l'abilità speciale «{name}».",
        payload=json.dumps({"category": category, "name": name, "description": description}),
    )
    return CommandResult(True, event=event)


@register_handler(perm.CMD_CUSTOM_ABILITY_SELF_UPDATE)
def _handle_custom_ability_self_update(ctx: HandlerContext) -> CommandResult:
    """
    Il giocatore modifica una propria abilità personalizzata già esistente
    sull'host — stesso ripiego su una creazione se `ability_id` è stale
    (un resync completo l'ha rigenerato) già usato in
    `_handle_diary_self_update_entry`, vedi il suo docstring per il perché.
    """
    character = _resolve_world_character(ctx.world_id, ctx.target_id)
    if character is None:
        return CommandResult(False, "Personaggio non trovato in questo mondo.")
    if not perm.is_character_owner(ctx.actor_device_id, character.owner_device_id):
        return CommandResult(
            False, "Solo il proprietario del personaggio può modificare una propria abilità.",
        )
    category = str(ctx.payload.get("category", "")).strip()
    name = str(ctx.payload.get("name", "")).strip()
    description = str(ctx.payload.get("description", ""))
    ability_id = str(ctx.payload.get("ability_id", ""))
    if category not in ("esplorazione", "combattimento"):
        return CommandResult(False, "Categoria non valida (esplorazione|combattimento).")
    if not name:
        return CommandResult(False, "Nome dell'abilità mancante.")

    if ability_id and character_repo.custom_ability_exists(ability_id, character.id):
        ok = character_repo.update_custom_ability(ability_id, name, description)
    else:
        ok = character_repo.create_custom_ability(
            character.id, category, name, description,
        ) is not None
    if not ok:
        return CommandResult(False, "Aggiornamento dell'abilità fallito.")

    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=perm.CMD_CUSTOM_ABILITY_SELF_UPDATE, target_type="character", target_id=character.id,
        summary=f"{character.name} ha modificato l'abilità speciale «{name}».",
        payload=json.dumps({"category": category, "name": name, "description": description}),
    )
    return CommandResult(True, event=event)


@register_handler(perm.CMD_BONUS_SPELL_GRANT)
def _handle_bonus_spell_grant(ctx: HandlerContext) -> CommandResult:
    character = _resolve_world_character(ctx.world_id, ctx.target_id)
    if character is None:
        return CommandResult(False, "Personaggio non trovato in questo mondo.")
    name = str(ctx.payload.get("name", "")).strip()
    try:
        level = int(ctx.payload.get("level", 0))
    except (TypeError, ValueError):
        return CommandResult(False, "Livello dell'incantesimo non valido.")
    if not name:
        return CommandResult(False, "Nome dell'incantesimo mancante.")
    if not (0 <= level <= 9):
        return CommandResult(False, "Livello dell'incantesimo fuori intervallo (0-9).")

    ok = character_repo.upsert_known_spell(
        character.id, name, level, is_prepared=True,
        school=str(ctx.payload.get("school", "")),
        casting_time=str(ctx.payload.get("casting_time", "")),
        spell_range=str(ctx.payload.get("spell_range", "")),
        components=str(ctx.payload.get("components", "")),
        duration=str(ctx.payload.get("duration", "")),
        description=str(ctx.payload.get("description", "")),
        higher_levels=str(ctx.payload.get("higher_levels", "")),
        class_list=str(ctx.payload.get("class_list", "")),
        is_bonus=True,
    )
    if not ok:
        return CommandResult(False, "Concessione dell'incantesimo fallita.")

    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=perm.CMD_BONUS_SPELL_GRANT, target_type="character", target_id=character.id,
        summary=f"{ctx.actor_name} ha concesso a {character.name} l'incantesimo bonus «{name}».",
        payload=json.dumps({"name": name, "level": level}),
    )
    return CommandResult(True, event=event)


@register_handler(perm.CMD_SPELL_SELF_UPSERT)
def _handle_spell_self_upsert(ctx: HandlerContext) -> CommandResult:
    """
    Il giocatore stesso crea/aggiorna un proprio incantesimo conosciuto
    (estensione di `CMD_HP_SELF_UPDATE`) — copre sia il toggle
    di preparazione sul catalogo di classe (`spells_view.py::_toggle_prepared`/
    `_toggle_prepared_mc`) sia l'aggiunta manuale di un incantesimo bonus
    (`spells_view.py`, dialog "Aggiungi incantesimo bonus") sia le scelte
    fatte in `profilo_tab.py` (creazione/level-up). Come
    `_handle_bonus_spell_grant`: `character_repo.upsert_known_spell`
    identifica già la riga per (character_id, name, level), quindi nessun
    problema di id stale dopo un resync (a differenza di diario/abilità).
    """
    character = _resolve_world_character(ctx.world_id, ctx.target_id)
    if character is None:
        return CommandResult(False, "Personaggio non trovato in questo mondo.")
    if not perm.is_character_owner(ctx.actor_device_id, character.owner_device_id):
        return CommandResult(
            False, "Solo il proprietario del personaggio può modificare i propri incantesimi.",
        )
    name = str(ctx.payload.get("name", "")).strip()
    try:
        level = int(ctx.payload.get("level", 0))
    except (TypeError, ValueError):
        return CommandResult(False, "Livello dell'incantesimo non valido.")
    if not name:
        return CommandResult(False, "Nome dell'incantesimo mancante.")
    if not (0 <= level <= 9):
        return CommandResult(False, "Livello dell'incantesimo fuori intervallo (0-9).")
    is_bonus = ctx.payload.get("is_bonus")
    if is_bonus is not None:
        is_bonus = bool(is_bonus)
    always_prepared = ctx.payload.get("always_prepared")
    if always_prepared is not None:
        always_prepared = bool(always_prepared)

    ok = character_repo.upsert_known_spell(
        character.id, name, level, is_prepared=bool(ctx.payload.get("is_prepared", True)),
        school=str(ctx.payload.get("school", "")),
        casting_time=str(ctx.payload.get("casting_time", "")),
        spell_range=str(ctx.payload.get("spell_range", "")),
        components=str(ctx.payload.get("components", "")),
        duration=str(ctx.payload.get("duration", "")),
        description=str(ctx.payload.get("description", "")),
        higher_levels=str(ctx.payload.get("higher_levels", "")),
        class_list=str(ctx.payload.get("class_list", "")),
        origin_unrestricted=bool(ctx.payload.get("origin_unrestricted", False)),
        is_bonus=is_bonus,
        always_prepared=always_prepared,
    )
    if not ok:
        return CommandResult(False, "Aggiornamento dell'incantesimo fallito.")

    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=perm.CMD_SPELL_SELF_UPSERT, target_type="character", target_id=character.id,
        summary=f"{character.name}: incantesimo «{name}» aggiornato.",
        payload=json.dumps({"name": name, "level": level}),
    )
    return CommandResult(True, event=event)


@register_handler(perm.CMD_SPELL_SELF_REMOVE)
def _handle_spell_self_remove(ctx: HandlerContext) -> CommandResult:
    """Il giocatore stesso rimuove un proprio incantesimo conosciuto —
    controparte di `_handle_spell_self_upsert`."""
    character = _resolve_world_character(ctx.world_id, ctx.target_id)
    if character is None:
        return CommandResult(False, "Personaggio non trovato in questo mondo.")
    if not perm.is_character_owner(ctx.actor_device_id, character.owner_device_id):
        return CommandResult(
            False, "Solo il proprietario del personaggio può rimuovere i propri incantesimi.",
        )
    name = str(ctx.payload.get("name", "")).strip()
    try:
        level = int(ctx.payload.get("level", 0))
    except (TypeError, ValueError):
        return CommandResult(False, "Livello dell'incantesimo non valido.")
    if not name:
        return CommandResult(False, "Nome dell'incantesimo mancante.")

    if not character_repo.remove_known_spell(character.id, name, level):
        return CommandResult(False, "Rimozione dell'incantesimo fallita.")

    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=perm.CMD_SPELL_SELF_REMOVE, target_type="character", target_id=character.id,
        summary=f"{character.name}: incantesimo «{name}» rimosso.",
        payload=json.dumps({"name": name, "level": level}),
    )
    return CommandResult(True, event=event)


def _weapon_fields_from_payload(payload: dict) -> dict:
    """Estrae i campi arma comuni a create/update da un payload di
    `CMD_WEAPON_SELF_UPSERT` — un solo punto per i due rami dell'handler
    sotto, stesso principio di `_apply_condition_to_character` più sopra."""
    return dict(
        damage_dice=str(payload.get("damage_dice", "")),
        damage_type=str(payload.get("damage_type", "")),
        attack_bonus=int(payload.get("attack_bonus", 0) or 0),
        damage_bonus=int(payload.get("damage_bonus", 0) or 0),
        properties=str(payload.get("properties", "")),
        is_equipped=bool(payload.get("is_equipped", False)),
        is_magical=bool(payload.get("is_magical", False)),
        magic_description=str(payload.get("magic_description", "")),
        range_normal=int(payload.get("range_normal", 0) or 0),
        range_max=int(payload.get("range_max", 0) or 0),
        magic_damages=str(payload.get("magic_damages", "[]")),
        versatile_damage_dice=str(payload.get("versatile_damage_dice", "")),
        grip_two_handed=bool(payload.get("grip_two_handed", False)),
        weapon_category=str(payload.get("weapon_category", "")),
        proficiency_override=bool(payload.get("proficiency_override", False)),
        finesse_ability=str(payload.get("finesse_ability", "")),
        attack_total_override=bool(payload.get("attack_total_override", False)),
        attack_override_value=int(payload.get("attack_override_value", 0) or 0),
    )


@register_handler(perm.CMD_WEAPON_SELF_UPSERT)
def _handle_weapon_self_upsert(ctx: HandlerContext) -> CommandResult:
    """
    Il giocatore stesso crea/aggiorna una propria arma (`inventario_tab.py`,
    sezione Armi) — estensione di `CMD_HP_SELF_UPDATE`, stesso principio di
    `_handle_spell_self_upsert` ma senza una chiave naturale disponibile
    (due armi possono avere lo stesso nome): identifica la riga per
    `weapon_id`, generato lato client PRIMA della scrittura locale (vedi il
    docstring di `CMD_WEAPON_SELF_UPSERT` in `core/world_permissions.py`) —
    se non esiste ancora sull'host la crea con quello stesso id invece di
    generarne uno nuovo, così client e host restano sempre allineati sullo
    stesso id per questa riga.
    """
    character = _resolve_world_character(ctx.world_id, ctx.target_id)
    if character is None:
        return CommandResult(False, "Personaggio non trovato in questo mondo.")
    if not perm.is_character_owner(ctx.actor_device_id, character.owner_device_id):
        return CommandResult(
            False, "Solo il proprietario del personaggio può modificare le proprie armi.",
        )
    name = str(ctx.payload.get("name", "")).strip()
    if not name:
        return CommandResult(False, "Nome dell'arma mancante.")
    weapon_id = str(ctx.payload.get("weapon_id", "")).strip()
    fields = _weapon_fields_from_payload(ctx.payload)

    existing = character_repo.get_weapon_by_id(weapon_id) if weapon_id else None
    if existing is not None and existing.character_id == character.id:
        ok = character_repo.update_weapon(weapon_id, name, **fields)
    else:
        ok = character_repo.create_weapon(
            character.id, name, weapon_id=weapon_id or None, **fields,
        )
    if not ok:
        return CommandResult(False, "Scrittura dell'arma fallita.")

    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=perm.CMD_WEAPON_SELF_UPSERT, target_type="character", target_id=character.id,
        summary=f"{character.name}: arma «{name}» aggiornata.",
        payload=json.dumps({"weapon_id": weapon_id, "name": name}),
    )
    return CommandResult(True, event=event)


@register_handler(perm.CMD_WEAPON_SELF_REMOVE)
def _handle_weapon_self_remove(ctx: HandlerContext) -> CommandResult:
    """Il giocatore stesso elimina una propria arma — controparte di
    `_handle_weapon_self_upsert`."""
    character = _resolve_world_character(ctx.world_id, ctx.target_id)
    if character is None:
        return CommandResult(False, "Personaggio non trovato in questo mondo.")
    if not perm.is_character_owner(ctx.actor_device_id, character.owner_device_id):
        return CommandResult(
            False, "Solo il proprietario del personaggio può eliminare le proprie armi.",
        )
    weapon_id = str(ctx.payload.get("weapon_id", "")).strip()
    if not weapon_id:
        return CommandResult(False, "Id dell'arma mancante.")
    existing = character_repo.get_weapon_by_id(weapon_id)
    if existing is not None and existing.character_id != character.id:
        return CommandResult(False, "Questa arma non appartiene a questo personaggio.")
    if existing is None:
        # Già assente sull'host (mai arrivata, o già rimossa) — idempotente,
        # non un errore: stesso principio di CMD_LOOT_STASH_CLAIM su una
        # voce già presa.
        return CommandResult(True)
    if not character_repo.delete_weapon(weapon_id):
        return CommandResult(False, "Eliminazione dell'arma fallita.")

    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=perm.CMD_WEAPON_SELF_REMOVE, target_type="character", target_id=character.id,
        summary=f"{character.name}: arma «{existing.name}» eliminata.",
        payload=json.dumps({"weapon_id": weapon_id, "name": existing.name}),
    )
    return CommandResult(True, event=event)


def _inventory_fields_from_payload(payload: dict) -> dict:
    """Stesso ruolo di `_weapon_fields_from_payload` per
    `CMD_INVENTORY_SELF_UPSERT`."""
    return dict(
        quantity=int(payload.get("quantity", 1) or 1),
        weight=float(payload.get("weight", 0.0) or 0.0),
        description=str(payload.get("description", "")),
        category=str(payload.get("category", "misc") or "misc"),
        is_equipped=bool(payload.get("is_equipped", False)),
        ca_value=int(payload.get("ca_value", 0) or 0),
        armor_type=str(payload.get("armor_type", "")),
        effects=str(payload.get("effects", "")),
        requires_attunement=bool(payload.get("requires_attunement", False)),
    )


@register_handler(perm.CMD_INVENTORY_SELF_UPSERT)
def _handle_inventory_self_upsert(ctx: HandlerContext) -> CommandResult:
    """Il giocatore stesso crea/aggiorna un proprio oggetto d'inventario
    (`inventario_tab.py`, sezioni Armature/Oggetti) — stesso principio di
    `_handle_weapon_self_upsert`, `item_id` al posto di `weapon_id`. La
    sintonia (`is_attuned`) è scritta a parte con
    `character_repo.set_item_attunement()`, come fa già `inventario_tab.py`
    in locale (`_write_attunement`) — non è un parametro di
    `create_inventory_item`/`update_inventory_item`."""
    character = _resolve_world_character(ctx.world_id, ctx.target_id)
    if character is None:
        return CommandResult(False, "Personaggio non trovato in questo mondo.")
    if not perm.is_character_owner(ctx.actor_device_id, character.owner_device_id):
        return CommandResult(
            False, "Solo il proprietario del personaggio può modificare i propri oggetti.",
        )
    name = str(ctx.payload.get("name", "")).strip()
    if not name:
        return CommandResult(False, "Nome dell'oggetto mancante.")
    item_id = str(ctx.payload.get("item_id", "")).strip()
    fields = _inventory_fields_from_payload(ctx.payload)

    existing = character_repo.get_inventory_item_by_id(item_id) if item_id else None
    if existing is not None and existing.character_id == character.id:
        ok = character_repo.update_inventory_item(item_id, name, **fields)
        result_id = item_id
    else:
        result_id = character_repo.create_inventory_item(
            character.id, name, item_id=item_id or None, **fields,
        )
        ok = result_id is not None
    if ok and "is_attuned" in ctx.payload and result_id:
        character_repo.set_item_attunement(result_id, bool(ctx.payload.get("is_attuned")))
    if not ok:
        return CommandResult(False, "Scrittura dell'oggetto fallita.")

    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=perm.CMD_INVENTORY_SELF_UPSERT, target_type="character", target_id=character.id,
        summary=f"{character.name}: oggetto «{name}» aggiornato.",
        payload=json.dumps({"item_id": item_id, "name": name}),
    )
    return CommandResult(True, event=event)


@register_handler(perm.CMD_INVENTORY_SELF_REMOVE)
def _handle_inventory_self_remove(ctx: HandlerContext) -> CommandResult:
    """Il giocatore stesso elimina un proprio oggetto — controparte di
    `_handle_inventory_self_upsert`."""
    character = _resolve_world_character(ctx.world_id, ctx.target_id)
    if character is None:
        return CommandResult(False, "Personaggio non trovato in questo mondo.")
    if not perm.is_character_owner(ctx.actor_device_id, character.owner_device_id):
        return CommandResult(
            False, "Solo il proprietario del personaggio può eliminare i propri oggetti.",
        )
    item_id = str(ctx.payload.get("item_id", "")).strip()
    if not item_id:
        return CommandResult(False, "Id dell'oggetto mancante.")
    existing = character_repo.get_inventory_item_by_id(item_id)
    if existing is not None and existing.character_id != character.id:
        return CommandResult(False, "Questo oggetto non appartiene a questo personaggio.")
    if existing is None:
        return CommandResult(True)
    if not character_repo.delete_inventory_item(item_id):
        return CommandResult(False, "Eliminazione dell'oggetto fallita.")

    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=perm.CMD_INVENTORY_SELF_REMOVE, target_type="character", target_id=character.id,
        summary=f"{character.name}: oggetto «{existing.name}» eliminato.",
        payload=json.dumps({"item_id": item_id, "name": existing.name}),
    )
    return CommandResult(True, event=event)


@register_handler(perm.CMD_CURRENCY_SELF_UPDATE)
def _handle_currency_self_update(ctx: HandlerContext) -> CommandResult:
    """Il giocatore stesso aggiorna le proprie monete
    (`inventario_tab.py::_on_edit_currency`) — estensione di
    `CMD_HP_SELF_UPDATE`, valori assoluti come lì, idempotente."""
    character = _resolve_world_character(ctx.world_id, ctx.target_id)
    if character is None:
        return CommandResult(False, "Personaggio non trovato in questo mondo.")
    if not perm.is_character_owner(ctx.actor_device_id, character.owner_device_id):
        return CommandResult(
            False, "Solo il proprietario del personaggio può aggiornarne le monete.",
        )
    try:
        copper = int(ctx.payload.get("copper", 0) or 0)
        silver = int(ctx.payload.get("silver", 0) or 0)
        electrum = int(ctx.payload.get("electrum", 0) or 0)
        gold = int(ctx.payload.get("gold", 0) or 0)
        platinum = int(ctx.payload.get("platinum", 0) or 0)
    except (TypeError, ValueError):
        return CommandResult(False, "Valori delle monete non validi.")
    if not character_repo.update_currencies(
        character.id, copper, silver, electrum, gold, platinum,
    ):
        return CommandResult(False, "Aggiornamento delle monete fallito.")

    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=perm.CMD_CURRENCY_SELF_UPDATE, target_type="character", target_id=character.id,
        summary=f"{character.name} ha aggiornato le proprie monete.",
        payload=json.dumps({
            "copper": copper, "silver": silver, "electrum": electrum,
            "gold": gold, "platinum": platinum,
        }),
    )
    return CommandResult(True, event=event)


@register_handler(perm.CMD_CAMPAIGN_NOTE_SELF_CREATE)
def _handle_campaign_note_self_create(ctx: HandlerContext) -> CommandResult:
    """
    Il giocatore stesso crea una propria nota di campagna (NPC/luogo/
    missiva — `diary_view.py`, sezione "Diario" della barra laterale,
    DISTINTA dalle note condivise dal master su `master_campaign_notes`,
    vedi il docstring di `CMD_CAMPAIGN_NOTE_SELF_CREATE` in
    `core/world_permissions.py`). Stesso principio di
    `_handle_custom_ability_self_create`.
    """
    character = _resolve_world_character(ctx.world_id, ctx.target_id)
    if character is None:
        return CommandResult(False, "Personaggio non trovato in questo mondo.")
    if not perm.is_character_owner(ctx.actor_device_id, character.owner_device_id):
        return CommandResult(
            False, "Solo il proprietario del personaggio può creare una propria nota.",
        )
    category = str(ctx.payload.get("category", "")).strip()
    name = str(ctx.payload.get("name", "")).strip()
    description = str(ctx.payload.get("description", ""))
    status = str(ctx.payload.get("status", ""))
    tags = str(ctx.payload.get("tags", ""))
    if not name:
        return CommandResult(False, "Nome della nota mancante.")
    note_id = str(ctx.payload.get("note_id", "")).strip()

    result_id = character_repo.create_campaign_note(
        character.id, category, name, description, status, tags,
        note_id=note_id or None,
    )
    if result_id is None:
        return CommandResult(False, "Creazione della nota fallita.")

    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=perm.CMD_CAMPAIGN_NOTE_SELF_CREATE, target_type="character", target_id=character.id,
        summary=f"{character.name} ha creato la nota «{name}».",
        payload=json.dumps({"note_id": result_id, "category": category, "name": name}),
    )
    return CommandResult(True, event=event)


@register_handler(perm.CMD_CAMPAIGN_NOTE_SELF_UPDATE)
def _handle_campaign_note_self_update(ctx: HandlerContext) -> CommandResult:
    """Il giocatore modifica una propria nota di campagna già esistente
    sull'host — stesso ripiego su una creazione se `note_id` è stale (un
    resync completo l'ha rigenerato) già usato in
    `_handle_custom_ability_self_update`, vedi il suo docstring per il perché."""
    character = _resolve_world_character(ctx.world_id, ctx.target_id)
    if character is None:
        return CommandResult(False, "Personaggio non trovato in questo mondo.")
    if not perm.is_character_owner(ctx.actor_device_id, character.owner_device_id):
        return CommandResult(
            False, "Solo il proprietario del personaggio può modificare una propria nota.",
        )
    category = str(ctx.payload.get("category", "")).strip()
    name = str(ctx.payload.get("name", "")).strip()
    description = str(ctx.payload.get("description", ""))
    status = str(ctx.payload.get("status", ""))
    tags = str(ctx.payload.get("tags", ""))
    note_id = str(ctx.payload.get("note_id", "")).strip()
    if not name:
        return CommandResult(False, "Nome della nota mancante.")

    existing = character_repo.get_campaign_note_by_id(note_id) if note_id else None
    if existing is not None and existing.character_id == character.id:
        ok = character_repo.update_campaign_note(note_id, name, description, status, tags)
    else:
        ok = character_repo.create_campaign_note(
            character.id, category, name, description, status, tags,
            note_id=note_id or None,
        ) is not None
    if not ok:
        return CommandResult(False, "Aggiornamento della nota fallito.")

    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=perm.CMD_CAMPAIGN_NOTE_SELF_UPDATE, target_type="character", target_id=character.id,
        summary=f"{character.name} ha modificato la nota «{name}».",
        payload=json.dumps({"note_id": note_id, "category": category, "name": name}),
    )
    return CommandResult(True, event=event)


@register_handler(perm.CMD_CAMPAIGN_NOTE_SELF_DELETE)
def _handle_campaign_note_self_delete(ctx: HandlerContext) -> CommandResult:
    """Il giocatore elimina una propria nota di campagna — controparte di
    `_handle_campaign_note_self_create`."""
    character = _resolve_world_character(ctx.world_id, ctx.target_id)
    if character is None:
        return CommandResult(False, "Personaggio non trovato in questo mondo.")
    if not perm.is_character_owner(ctx.actor_device_id, character.owner_device_id):
        return CommandResult(
            False, "Solo il proprietario del personaggio può eliminare una propria nota.",
        )
    note_id = str(ctx.payload.get("note_id", "")).strip()
    if not note_id:
        return CommandResult(False, "Id della nota mancante.")
    existing = character_repo.get_campaign_note_by_id(note_id)
    if existing is not None and existing.character_id != character.id:
        return CommandResult(False, "Questa nota non appartiene a questo personaggio.")
    if existing is None:
        return CommandResult(True)
    if not character_repo.delete_campaign_note(note_id):
        return CommandResult(False, "Eliminazione della nota fallita.")

    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=perm.CMD_CAMPAIGN_NOTE_SELF_DELETE, target_type="character", target_id=character.id,
        summary=f"{character.name} ha eliminato la nota «{existing.name}».",
        payload=json.dumps({"note_id": note_id, "name": existing.name}),
    )
    return CommandResult(True, event=event)


@register_handler(perm.CMD_DIARY_ADD_ENTRY)
def _handle_diary_add_entry(ctx: HandlerContext) -> CommandResult:
    """
    Scrive una voce sul diario del personaggio (§6.2: "il master può anche
    scrivere una voce sul diario di un personaggio... scrive, non guarda").
    Deliberatamente nessun comando di LETTURA del diario è mai stato
    aggiunto alla matrice dei permessi: questo handler chiama solo
    `create_diary_entry()` (INSERT), mai una funzione che elenchi le voci
    esistenti — l'asimmetria "scrive, non guarda" è garantita dalla forma
    stessa del comando, non da un controllo a parte.
    """
    character = _resolve_world_character(ctx.world_id, ctx.target_id)
    if character is None:
        return CommandResult(False, "Personaggio non trovato in questo mondo.")
    title = str(ctx.payload.get("title", "")).strip()
    content = str(ctx.payload.get("content", "")).strip()
    if not title or not content:
        return CommandResult(False, "Titolo e testo della voce di diario sono obbligatori.")
    session_date = str(ctx.payload.get("session_date", ""))

    if not character_repo.create_diary_entry(character.id, title, content, session_date):
        return CommandResult(False, "Scrittura della voce di diario fallita.")

    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=perm.CMD_DIARY_ADD_ENTRY, target_type="character", target_id=character.id,
        summary=f"{ctx.actor_name} ha scritto una voce sul diario di {character.name}: «{title}».",
        payload=json.dumps({"title": title}),
    )
    return CommandResult(True, event=event)


@register_handler(perm.CMD_DIARY_SELF_ADD_ENTRY)
def _handle_diary_self_add_entry(ctx: HandlerContext) -> CommandResult:
    """
    Il giocatore stesso scrive una voce sul proprio diario — estensione di
    `CMD_HP_SELF_UPDATE`. Come `_handle_hp_self_update`: il ruolo `player`
    da solo non basta, serve `perm.is_character_owner()`.
    """
    character = _resolve_world_character(ctx.world_id, ctx.target_id)
    if character is None:
        return CommandResult(False, "Personaggio non trovato in questo mondo.")
    if not perm.is_character_owner(ctx.actor_device_id, character.owner_device_id):
        return CommandResult(
            False, "Solo il proprietario del personaggio può scrivere sul proprio diario.",
        )
    title = str(ctx.payload.get("title", "")).strip()
    content = str(ctx.payload.get("content", "")).strip()
    if not title or not content:
        return CommandResult(False, "Titolo e testo della voce di diario sono obbligatori.")
    session_date = str(ctx.payload.get("session_date", ""))

    if not character_repo.create_diary_entry(character.id, title, content, session_date):
        return CommandResult(False, "Scrittura della voce di diario fallita.")

    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=perm.CMD_DIARY_SELF_ADD_ENTRY, target_type="character", target_id=character.id,
        summary=f"{character.name} ha scritto una voce sul proprio diario: «{title}».",
        payload=json.dumps({"title": title}),
    )
    return CommandResult(True, event=event)


@register_handler(perm.CMD_DIARY_SELF_UPDATE_ENTRY)
def _handle_diary_self_update_entry(ctx: HandlerContext) -> CommandResult:
    """
    Il giocatore modifica una propria voce di diario già esistente
    sull'host. `entry_id` nel payload è quello della replica locale del
    giocatore — può essere stale se un resync completo è avvenuto tra
    l'apertura del dialog di modifica e il salvataggio (una voce diario
    riceve un nuovo id ad ogni resync, vedi
    `character_repo.diary_entry_exists`): in quel caso si ripiega su una
    CREAZIONE invece di un aggiornamento, così la modifica non va
    silenziosamente persa — meglio una voce duplicata occasionale (rara,
    l'utente se ne accorge e può cancellarla) che una modifica scomparsa.
    """
    character = _resolve_world_character(ctx.world_id, ctx.target_id)
    if character is None:
        return CommandResult(False, "Personaggio non trovato in questo mondo.")
    if not perm.is_character_owner(ctx.actor_device_id, character.owner_device_id):
        return CommandResult(
            False, "Solo il proprietario del personaggio può modificare il proprio diario.",
        )
    title = str(ctx.payload.get("title", "")).strip()
    content = str(ctx.payload.get("content", "")).strip()
    if not title or not content:
        return CommandResult(False, "Titolo e testo della voce di diario sono obbligatori.")
    session_date = str(ctx.payload.get("session_date", ""))
    entry_id = str(ctx.payload.get("entry_id", ""))

    if entry_id and character_repo.diary_entry_exists(entry_id, character.id):
        ok = character_repo.update_diary_entry(entry_id, title, content, session_date)
    else:
        ok = character_repo.create_diary_entry(character.id, title, content, session_date)
    if not ok:
        return CommandResult(False, "Aggiornamento della voce di diario fallito.")

    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=perm.CMD_DIARY_SELF_UPDATE_ENTRY, target_type="character", target_id=character.id,
        summary=f"{character.name} ha modificato una voce sul proprio diario: «{title}».",
        payload=json.dumps({"title": title}),
    )
    return CommandResult(True, event=event)


@register_handler(perm.CMD_CHANGE_REQUEST_PROPOSE)
def _handle_change_request_propose(ctx: HandlerContext) -> CommandResult:
    """
    Propone una richiesta di modifica (§7.1) — NON applica nulla: scrive
    solo la riga `pending` che il giocatore dovrà accettare o rifiutare con
    `change_request.respond`. Riguarda solo i campi altrimenti vietati
    (`CHANGE_REQUEST_ALLOWED_FIELDS`); qualunque altro campo nel payload
    viene rifiutato in blocco — nessuna scrittura parziale su una richiesta
    parzialmente valida.
    """
    character = _resolve_world_character(ctx.world_id, ctx.target_id)
    if character is None:
        return CommandResult(False, "Personaggio non trovato in questo mondo.")
    changes = ctx.payload.get("changes")
    if not isinstance(changes, dict) or not changes:
        return CommandResult(False, "Nessuna modifica proposta.")
    reason = str(ctx.payload.get("reason", "")).strip()
    if not reason:
        return CommandResult(False, "La richiesta di modifica deve avere una motivazione.")

    invalid = [f for f in changes if not perm.is_change_request_field_allowed(f)]
    if invalid:
        return CommandResult(
            False, f"Campi non proponibili in una richiesta di modifica: {', '.join(invalid)}.",
        )

    request = world_repo.create_change_request(
        ctx.world_id, character.id, ctx.actor_device_id,
        payload=json.dumps(changes), reason=reason,
    )
    if request is None:
        return CommandResult(False, "Creazione della richiesta fallita.")

    fields_desc = ", ".join(f"{k}: {v}" for k, v in changes.items())
    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=perm.CMD_CHANGE_REQUEST_PROPOSE, target_type="character", target_id=character.id,
        summary=f"{ctx.actor_name} ha proposto una modifica a {character.name} ({fields_desc}): «{reason}».",
        payload=json.dumps({"request_id": request.id, "changes": changes, "reason": reason}),
    )
    return CommandResult(True, event=event)


@register_handler(perm.CMD_CHANGE_REQUEST_RESPOND)
def _handle_change_request_respond(ctx: HandlerContext) -> CommandResult:
    """
    Il giocatore accetta o rifiuta una richiesta di modifica (§7.1) —
    l'UNICO comando di questo modulo dove il ruolo da solo NON basta:
    `can_perform()` autorizza qualunque membro del mondo (ruolo minimo
    `player`), ma qui si verifica IN PIÙ che chi risponde sia il
    proprietario del personaggio bersaglio (`perm.is_character_owner()`) —
    altrimenti un giocatore potrebbe accettare/rifiutare una richiesta
    diretta a un altro. Stesso principio di «Aggiorna il mio foglio» (§6.1):
    riservato al proprietario, mai al master né a un altro giocatore.
    """
    request_id = str(ctx.payload.get("request_id", "")).strip()
    accept = bool(ctx.payload.get("accept", False))
    if not request_id:
        return CommandResult(False, "Richiesta non specificata.")

    request = world_repo.get_change_request(request_id)
    if request is None or request.world_id != ctx.world_id:
        return CommandResult(False, "Richiesta di modifica non trovata in questo mondo.")
    if request.status != "pending":
        return CommandResult(False, f"Questa richiesta è già stata risolta ({request.status}).")

    character = _resolve_world_character(ctx.world_id, request.character_id)
    if character is None:
        return CommandResult(False, "Il personaggio di questa richiesta non esiste più.")
    if not perm.is_character_owner(ctx.actor_device_id, character.owner_device_id):
        return CommandResult(
            False, "Solo il proprietario del personaggio può rispondere a questa richiesta.",
        )

    try:
        changes: dict = json.loads(request.payload or "{}")
    except (json.JSONDecodeError, TypeError):
        changes = {}
    invalid = [f for f in changes if not perm.is_change_request_field_allowed(f)]
    if invalid:
        # Difesa in profondità: anche se create_change_request() ha già
        # filtrato i campi al momento della proposta, non fidarsi di dati
        # scritti in precedenza da una versione diversa dell'app.
        return CommandResult(
            False, f"Richiesta non applicabile: campi non validi ({', '.join(invalid)}).",
        )

    if accept and changes:
        for field_name, value in changes.items():
            setattr(character, field_name, value)
        if not character_repo.update(character):
            return CommandResult(False, "Applicazione della modifica fallita.")
        # Correttezza: DES/COS/SAG entrano nella formula della CA
        # senza armatura (Monaco: DES+SAG, Barbaro: DES+COS, Stregone
        # Discendenza Draconica: DES) e DES anche con armatura leggera/media
        # — esattamente come ogni altro punto dell'app che tocca queste
        # caratteristiche richiama sempre `calculate_and_update_ca()` subito
        # dopo (vedi profilo_tab.py, riga 1326 e 3968). Senza questa chiamata
        # una richiesta di modifica accettata su una di queste tre
        # caratteristiche lascerebbe la CA visualizzata non aggiornata finché
        # qualcos'altro non la ricalcola.
        if {"dex_score", "con_score", "wis_score"} & changes.keys():
            character_repo.calculate_and_update_ca(character.id)

    new_status = "accepted" if accept else "rejected"
    if not world_repo.resolve_change_request(request_id, new_status):
        return CommandResult(False, "Aggiornamento dello stato della richiesta fallito.")

    verb = "accettato" if accept else "rifiutato"
    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=perm.CMD_CHANGE_REQUEST_RESPOND, target_type="character", target_id=character.id,
        summary=f"{ctx.actor_name} ha {verb} la richiesta di modifica «{request.reason}».",
        payload=json.dumps({"request_id": request_id, "accept": accept}),
    )
    return CommandResult(True, event=event)


@register_handler(perm.CMD_CHARACTER_INSTANCE_SYNC)
def _handle_character_instance_sync(ctx: HandlerContext) -> CommandResult:
    """
    Registra sull'host l'export integrale di un'istanza di personaggio —
    vedi il docstring di `perm.CMD_CHARACTER_INSTANCE_SYNC` per il motivo:
    senza questo, un'istanza creata su un dispositivo che non ospita il
    mondo non esisterebbe mai sul DB dell'host, e la Sezione Master
    risulterebbe vuota anche a ingresso riuscito.

    A differenza di ogni altro handler sopra, qui NON si passa da
    `_resolve_world_character()`: quella funzione presuppone che il
    personaggio esista già sull'host (è così per xp.grant/hp.damage/...,
    comandi su un'istanza che l'host ha già), ma qui è esattamente il
    contrario — questa PUÒ essere la primissima volta che l'host vede
    questo personaggio. La verifica di proprietà si fa quindi sul
    `payload` esportato (`owner_device_id`), non su una riga DB esistente.

    Riusa `character_export.import_replica_character()` — lo stesso
    modulo, collaudato, già usato per la semina iniziale
    (`core/world_sync.py::_finalize_join()`) e per ogni rimaterializzazione
    successiva (`_resync_character_from_host()`): nessuna logica di
    scrittura delle 12 tabelle figlio duplicata qui.
    """
    export_data = ctx.payload.get("export")
    if not isinstance(export_data, dict):
        return CommandResult(False, "Dati del personaggio mancanti o malformati.")

    err = character_export.validate_export_data(export_data)
    if err:
        return CommandResult(False, f"Dati del personaggio non validi: {err}")

    char_row = export_data.get("character", {})
    character_id = str(char_row.get("id") or "")
    if not character_id:
        return CommandResult(False, "Id del personaggio mancante nell'export.")
    if character_id != ctx.target_id:
        return CommandResult(False, "Id del personaggio non corrisponde al bersaglio del comando.")
    if str(char_row.get("world_id") or "") != ctx.world_id:
        return CommandResult(False, "Il personaggio esportato non appartiene a questo mondo.")
    if not perm.is_character_owner(ctx.actor_device_id, str(char_row.get("owner_device_id") or "")):
        return CommandResult(
            False, "Puoi registrare sull'host solo un'istanza di cui sei il proprietario.",
        )

    result_id = character_export.import_replica_character(
        export_data, character_id, world_seq=0,
    )
    if result_id is None:
        return CommandResult(False, "Scrittura dell'istanza sull'host fallita.")

    character_name = str(char_row.get("name") or "un personaggio")
    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=perm.CMD_CHARACTER_INSTANCE_SYNC, target_type="character", target_id=character_id,
        summary=f"{ctx.actor_name} ha aggiunto «{character_name}» al mondo.",
        payload=json.dumps({"character_id": character_id, "name": character_name}),
    )
    return CommandResult(True, event=event)


# ---------------------------------------------------------------------------
# Handler del passo 7 — "Condivisione" (§6.2 note, §6.5 combattimento). Non
# toccano `characters`, quindi non passano da `_resolve_world_character()`:
# ognuno valida il proprio bersaglio (una nota, un incontro) e verifica
# esplicitamente che appartenga a `ctx.world_id`. Il payload dell'evento
# porta lo stato risolto (contenuto della nota, round/turno/membri
# dell'incontro) invece del solo id — la replica non deve mai fare un
# secondo giro di rete per materializzarlo, stesso principio già seguito
# sopra per gli eventi sui personaggi.
# ---------------------------------------------------------------------------

@register_handler(perm.CMD_NOTE_SHARE)
def _handle_note_share(ctx: HandlerContext) -> CommandResult:
    """
    Condivide (o aggiorna la condivisione di) una nota di campagna del
    Master (§6.2). A differenza delle altre note del Master, questa passa
    dalla pipeline comando → evento invece che da una scrittura diretta:
    è l'unica via per cui (a) "cambiare la visibilità è un'azione
    registrata" (§6.2, richiesto esplicitamente) e (b) un master che gioca
    da un dispositivo che non ospita il mondo riesce comunque a condividere
    una nota (altrimenti scriverebbe solo sulla propria replica, mai
    raggiungendo l'host — stesso bug già corretto una volta per le azioni
    a distanza sui personaggi).
    """
    visibility = ctx.payload.get("visibility", "private")
    if visibility not in ("private", "all", "selected"):
        return CommandResult(False, "Visibilità non valida.")
    visible_ids_json = json.dumps(ctx.payload.get("visible_to_device_ids", []))
    name = str(ctx.payload.get("name", ""))
    description = str(ctx.payload.get("description", ""))
    status = str(ctx.payload.get("status", ""))
    tags = str(ctx.payload.get("tags", ""))
    linked_npc_id = str(ctx.payload.get("linked_npc_id", ""))

    note_id = str(ctx.payload.get("note_id") or "")
    if note_id:
        existing = master_repo.get_master_campaign_note_by_id(note_id)
        if existing is None or existing.world_id != ctx.world_id:
            return CommandResult(False, "Nota non trovata in questo mondo.")
        ok = master_repo.update_master_campaign_note(
            note_id, name, description, status, tags, linked_npc_id,
            visibility, visible_ids_json,
        )
        if not ok:
            return CommandResult(False, "Aggiornamento della nota fallito.")
    else:
        category = str(ctx.payload.get("category", "npc"))
        note = master_repo.create_master_campaign_note(
            category, name, description, status, tags, linked_npc_id,
            ctx.world_id, visibility, visible_ids_json,
        )
        if note is None:
            return CommandResult(False, "Creazione della nota fallita.")
        note_id = note.id

    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=perm.CMD_NOTE_SHARE, target_type="note", target_id=note_id,
        summary=f"{ctx.actor_name} ha condiviso una nota: {name or 'senza nome'}",
        payload=json.dumps({
            "note_id": note_id, "category": ctx.payload.get("category", "npc"),
            "name": name, "description": description, "status": status,
            "tags": tags, "linked_npc_id": linked_npc_id,
            "visibility": visibility,
            "visible_to_device_ids": ctx.payload.get("visible_to_device_ids", []),
        }),
    )
    return CommandResult(True, event=event)


def _resolve_world_encounter(world_id: str, encounter_id: str):
    """Fail-closed come `_resolve_world_character()` sopra — un incontro
    bersaglio di un comando deve DAVVERO appartenere a `world_id`."""
    if not encounter_id:
        return None
    encounter = master_repo.get_encounter_by_id(encounter_id)
    if encounter is None or encounter.world_id != world_id:
        return None
    return encounter


@register_handler(perm.CMD_ENCOUNTER_MANAGE)
def _handle_encounter_manage(ctx: HandlerContext) -> CommandResult:
    """
    Avanza il turno o termina un incontro condiviso (§6.5). Il payload
    dell'evento porta lo stato risolto (round/turno/membri), non solo
    l'azione — la replica non deve mai fare un secondo giro di rete per
    materializzarlo, stesso principio già seguito per `note.share`.
    """
    encounter = _resolve_world_encounter(ctx.world_id, str(ctx.payload.get("encounter_id", "")))
    if encounter is None:
        return CommandResult(False, "Scontro non trovato in questo mondo.")
    action = ctx.payload.get("action")
    if action == "next_turn":
        master_repo.advance_turn(encounter.id)
    elif action == "end_combat":
        master_repo.archive_encounter(encounter.id, True)
    else:
        return CommandResult(False, "Azione non riconosciuta.")

    updated = master_repo.get_encounter_by_id(encounter.id)
    members = master_repo.resolved_members_to_dicts(
        master_repo.get_encounter_members_resolved(encounter.id),
    )
    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=perm.CMD_ENCOUNTER_MANAGE, target_type="encounter", target_id=encounter.id,
        summary=f"{ctx.actor_name}: {'turno successivo' if action == 'next_turn' else 'combattimento terminato'}",
        payload=json.dumps({
            "action": action,
            "encounter": asdict(updated) if updated else asdict(encounter),
            "members": members,
        }),
    )
    return CommandResult(True, event=event)


@register_handler(perm.CMD_COMBAT_TOGGLE_VISIBILITY)
def _handle_combat_toggle_visibility(ctx: HandlerContext) -> CommandResult:
    """Mostra/nasconde ai giocatori un incontro condiviso (§6.5) — spento
    di default, così il master può prepararlo senza rivelarlo prima del
    tempo."""
    encounter = _resolve_world_encounter(ctx.world_id, str(ctx.payload.get("encounter_id", "")))
    if encounter is None:
        return CommandResult(False, "Scontro non trovato in questo mondo.")
    visible = bool(ctx.payload.get("visible", False))
    master_repo.set_encounter_visibility(encounter.id, visible)

    updated = master_repo.get_encounter_by_id(encounter.id)
    members = master_repo.resolved_members_to_dicts(
        master_repo.get_encounter_members_resolved(encounter.id),
    ) if visible else []
    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=perm.CMD_COMBAT_TOGGLE_VISIBILITY, target_type="encounter", target_id=encounter.id,
        summary=(f"{ctx.actor_name} ha reso visibile il combattimento ai giocatori" if visible
                 else f"{ctx.actor_name} ha nascosto il combattimento ai giocatori"),
        payload=json.dumps({
            "visible": visible,
            "encounter": asdict(updated) if updated else asdict(encounter),
            "members": members,
        }),
    )
    return CommandResult(True, event=event)


@register_handler(perm.CMD_MAP_PUBLISH)
def _handle_map_publish(ctx: HandlerContext) -> CommandResult:
    """
    Pubblica una mappa PERSONALE nel mondo CLONANDOLA (§6.4, passo 8):
    riusare la stessa riga (`world_id`/`is_shared` impostati sulla mappa
    del personaggio) farebbe sì che disegnarci sopra modifichi anche la
    mappa personale di un personaggio che magari non fa nemmeno parte di
    questo mondo. `maps_repo.clone_map_for_sharing()` crea invece una riga
    NUOVA, senza personaggio proprietario, annotazioni vuote — il
    personale non viene mai più toccato da qui in poi. L'immagine NON
    viaggia nell'evento — troppo grande per il giornale/lo snapshot: le
    repliche la scaricano lazy via `GET /map/<id>/image`
    (`network/host_server.py::handle_map_image`).
    """
    source_id = str(ctx.payload.get("map_id", ""))
    source = maps_repo.get_map(source_id)
    if source is None:
        return CommandResult(False, "Mappa non trovata.")
    clone = maps_repo.clone_map_for_sharing(source_id, ctx.world_id)
    if clone is None:
        return CommandResult(False, "Pubblicazione della mappa fallita.")
    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=perm.CMD_MAP_PUBLISH, target_type="map", target_id=clone.id,
        summary=f"{ctx.actor_name} ha condiviso la mappa: {clone.name}",
        payload=json.dumps({"name": clone.name, "visible_to_players": True}),
    )
    return CommandResult(True, event=event)


@register_handler(perm.CMD_MAP_UPLOAD)
def _handle_map_upload(ctx: HandlerContext) -> CommandResult:
    """
    Carica una mappa NUOVA direttamente nel mondo — stesso
    risultato di `CMD_MAP_PUBLISH` (una riga condivisa senza personaggio
    proprietario), ma senza una mappa personale di origine: il master
    sceglie un'immagine dal proprio dispositivo e la condivide subito.
    """
    name = str(ctx.payload.get("name", "")).strip() or "Mappa senza nome"
    image_data = str(ctx.payload.get("image_data", ""))
    visible = bool(ctx.payload.get("visible_to_players", True))
    gm = maps_repo.create_shared_map(ctx.world_id, name, image_data, visible)
    if gm is None:
        return CommandResult(False, "Caricamento della mappa fallito.")
    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=perm.CMD_MAP_UPLOAD, target_type="map", target_id=gm.id,
        summary=f"{ctx.actor_name} ha caricato la mappa: {gm.name}",
        payload=json.dumps({"name": gm.name, "visible_to_players": visible}),
    )
    return CommandResult(True, event=event)


@register_handler(perm.CMD_MAP_VISIBILITY)
def _handle_map_visibility(ctx: HandlerContext) -> CommandResult:
    """
    Mostra/nasconde ai giocatori una mappa già condivisa — DISTINTO
    dall'eliminazione: la mappa resta nell'elenco del master in entrambi i
    casi (§6.4).
    """
    game_map = maps_repo.get_map(str(ctx.payload.get("map_id", "")))
    if game_map is None or game_map.world_id != ctx.world_id or not game_map.is_shared:
        return CommandResult(False, "Mappa non trovata in questo mondo.")
    visible = bool(ctx.payload.get("visible_to_players", True))
    if not maps_repo.set_map_visibility(game_map.id, visible):
        return CommandResult(False, "Operazione sulla mappa fallita.")
    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=perm.CMD_MAP_VISIBILITY, target_type="map", target_id=game_map.id,
        summary=(f"{ctx.actor_name} ha reso visibile ai giocatori la mappa: {game_map.name}"
                 if visible else
                 f"{ctx.actor_name} ha nascosto ai giocatori la mappa: {game_map.name}"),
        payload=json.dumps({"visible_to_players": visible, "name": game_map.name}),
    )
    return CommandResult(True, event=event)


@register_handler(perm.CMD_MAP_DELETE)
def _handle_map_delete(ctx: HandlerContext) -> CommandResult:
    """
    Elimina definitivamente una mappa condivisa — l'unico modo per farla
    sparire anche dall'elenco del master (§6.4). La mappa personale di
    origine, se pubblicata per clonazione, non è mai toccata: questa
    elimina solo il clone/la riga condivisa.
    """
    game_map = maps_repo.get_map(str(ctx.payload.get("map_id", "")))
    if game_map is None or game_map.world_id != ctx.world_id or not game_map.is_shared:
        return CommandResult(False, "Mappa non trovata in questo mondo.")
    if not maps_repo.delete_map(game_map.id):
        return CommandResult(False, "Eliminazione della mappa fallita.")
    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=perm.CMD_MAP_DELETE, target_type="map", target_id=game_map.id,
        summary=f"{ctx.actor_name} ha eliminato la mappa condivisa: {game_map.name}",
        payload=json.dumps({"name": game_map.name}),
    )
    return CommandResult(True, event=event)


@register_handler(perm.CMD_MAP_DRAW)
def _handle_map_draw(ctx: HandlerContext) -> CommandResult:
    """
    Applica un pacchetto di tratti/gomma a una mappa condivisa (§6.4). Il
    master invia i punti raggruppati ogni ~200ms mentre disegna, non un
    evento per punto — vedi `maps_repo.apply_stroke_batch()` per la forma
    esatta del pacchetto, la stessa funzione usata anche dal ramo replica.
    """
    game_map = maps_repo.get_map(str(ctx.payload.get("map_id", "")))
    if game_map is None or game_map.world_id != ctx.world_id or not game_map.is_shared:
        return CommandResult(False, "Mappa non trovata in questo mondo.")
    batch = ctx.payload.get("strokes", [])
    if not batch or not isinstance(batch, list):
        return CommandResult(False, "Nessun tratto da applicare.")
    if not maps_repo.apply_stroke_batch(game_map.id, batch):
        return CommandResult(False, "Applicazione del disegno fallita.")
    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=perm.CMD_MAP_DRAW, target_type="map", target_id=game_map.id,
        summary="Disegno aggiornato sulla mappa",
        payload=json.dumps({"strokes": batch}),
    )
    return CommandResult(True, event=event)


# ---------------------------------------------------------------------------
# Deposito comune del gruppo — sincronizzazione. Solo
# `stash_kind="party"` passa da qui: il deposito privato del Master
# (`stash_kind="master"`) resta intenzionalmente locale-solo, mai
# condiviso, vedi il docstring di `data/repositories/loot_repo.py` e di
# `LootStashEntry` in `data/models.py`. Non toccano `characters`, stesso
# motivo per cui CMD_MAP_PUBLISH/CMD_MAP_DRAW non passano da
# `_resolve_world_character()`.
# ---------------------------------------------------------------------------

def _loot_stash_entry_payload(entry) -> dict:
    """Stato completo di una voce, incluso nell'evento — così le repliche
    possono materializzarla (`loot_repo.replica_upsert_entry`) senza
    un'altra interrogazione, stesso principio di `_handle_map_draw`."""
    return {
        "id": entry.id, "stash_kind": entry.stash_kind, "world_id": entry.world_id,
        "entry_kind": entry.entry_kind, "name": entry.name,
        "description": entry.description, "quantity": entry.quantity,
        "source_note": entry.source_note,
        "copper": entry.copper, "silver": entry.silver, "electrum": entry.electrum,
        "gold": entry.gold, "platinum": entry.platinum,
        "added_by_device_id": entry.added_by_device_id,
        "weapon_damage_dice": entry.weapon_damage_dice,
        "weapon_damage_type": entry.weapon_damage_type,
        "weapon_category": entry.weapon_category,
        "weapon_properties": entry.weapon_properties,
        "weapon_attack_bonus": entry.weapon_attack_bonus,
        "weapon_damage_bonus": entry.weapon_damage_bonus,
        "weapon_magic_damages": entry.weapon_magic_damages,
        "armor_ca_value": entry.armor_ca_value,
        "armor_type": entry.armor_type,
        "armor_effects": entry.armor_effects,
        "created_at": entry.created_at, "updated_at": entry.updated_at,
    }


@register_handler(perm.CMD_LOOT_STASH_ADD)
def _handle_loot_stash_add(ctx: HandlerContext) -> CommandResult:
    """Aggiunge una voce al deposito comune del gruppo di questo mondo."""
    entry_kind = str(ctx.payload.get("entry_kind", "item")).strip() or "item"
    name = str(ctx.payload.get("name", ""))
    if entry_kind != "coins" and not name.strip():
        return CommandResult(False, "Nome della voce mancante.")
    entry = loot_repo.create_entry(
        "party", entry_kind, name=name, description=str(ctx.payload.get("description", "")),
        quantity=int(ctx.payload.get("quantity", 1) or 0),
        source_note=str(ctx.payload.get("source_note", "")), world_id=ctx.world_id,
        copper=int(ctx.payload.get("copper", 0) or 0), silver=int(ctx.payload.get("silver", 0) or 0),
        electrum=int(ctx.payload.get("electrum", 0) or 0), gold=int(ctx.payload.get("gold", 0) or 0),
        platinum=int(ctx.payload.get("platinum", 0) or 0), added_by_device_id=ctx.actor_device_id,
        weapon_damage_dice=str(ctx.payload.get("weapon_damage_dice", "")),
        weapon_damage_type=str(ctx.payload.get("weapon_damage_type", "")),
        weapon_category=str(ctx.payload.get("weapon_category", "")),
        weapon_properties=str(ctx.payload.get("weapon_properties", "")),
        weapon_attack_bonus=int(ctx.payload.get("weapon_attack_bonus", 0) or 0),
        weapon_damage_bonus=int(ctx.payload.get("weapon_damage_bonus", 0) or 0),
        weapon_magic_damages=str(ctx.payload.get("weapon_magic_damages", "[]") or "[]"),
        armor_ca_value=int(ctx.payload.get("armor_ca_value", 0) or 0),
        armor_type=str(ctx.payload.get("armor_type", "")),
        armor_effects=str(ctx.payload.get("armor_effects", "")),
    )
    if entry is None:
        return CommandResult(False, "Aggiunta al deposito del gruppo fallita.")
    label = "monete" if entry_kind == "coins" else f"«{name}»"
    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=perm.CMD_LOOT_STASH_ADD, target_type="loot_stash", target_id=entry.id,
        summary=f"{ctx.actor_name} ha aggiunto {label} al deposito del gruppo.",
        payload=json.dumps(_loot_stash_entry_payload(entry)),
    )
    return CommandResult(True, event=event)


@register_handler(perm.CMD_LOOT_STASH_UPDATE)
def _handle_loot_stash_update(ctx: HandlerContext) -> CommandResult:
    """Aggiorna i campi testuali/quantità di una voce del deposito comune
    già esistente (mai le colonne valuta — stessa convenzione di
    `loot_repo.update_entry`, la UI ricorre a elimina+ricrea per le
    monete, vedi `master_loot_view.py::_open_edit_dialog`)."""
    entry_id = str(ctx.payload.get("entry_id", ""))
    entry = loot_repo.get_entry(entry_id) if entry_id else None
    if entry is None or entry.stash_kind != "party" or entry.world_id != ctx.world_id:
        return CommandResult(False, "Voce non trovata nel deposito del gruppo di questo mondo.")
    if not loot_repo.update_entry(
        entry_id, name=str(ctx.payload.get("name", "")),
        description=str(ctx.payload.get("description", "")),
        quantity=int(ctx.payload.get("quantity", entry.quantity) or 0),
        source_note=str(ctx.payload.get("source_note", "")),
        weapon_damage_dice=str(ctx.payload.get("weapon_damage_dice", entry.weapon_damage_dice)),
        weapon_damage_type=str(ctx.payload.get("weapon_damage_type", entry.weapon_damage_type)),
        weapon_category=str(ctx.payload.get("weapon_category", entry.weapon_category)),
        weapon_properties=str(ctx.payload.get("weapon_properties", entry.weapon_properties)),
        weapon_attack_bonus=int(ctx.payload.get("weapon_attack_bonus", entry.weapon_attack_bonus) or 0),
        weapon_damage_bonus=int(ctx.payload.get("weapon_damage_bonus", entry.weapon_damage_bonus) or 0),
        weapon_magic_damages=str(ctx.payload.get("weapon_magic_damages", entry.weapon_magic_damages) or "[]"),
        armor_ca_value=int(ctx.payload.get("armor_ca_value", entry.armor_ca_value) or 0),
        armor_type=str(ctx.payload.get("armor_type", entry.armor_type)),
        armor_effects=str(ctx.payload.get("armor_effects", entry.armor_effects)),
        entry_kind=str(ctx.payload.get("entry_kind", "")),
    ):
        return CommandResult(False, "Aggiornamento della voce fallito.")
    updated = loot_repo.get_entry(entry_id)
    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=perm.CMD_LOOT_STASH_UPDATE, target_type="loot_stash", target_id=entry_id,
        summary=f"{ctx.actor_name} ha modificato una voce del deposito del gruppo.",
        payload=json.dumps(_loot_stash_entry_payload(updated)),
    )
    return CommandResult(True, event=event)


@register_handler(perm.CMD_LOOT_STASH_MOVE)
def _handle_loot_stash_move(ctx: HandlerContext) -> CommandResult:
    """
    Sposta una voce tra il deposito del gruppo e l'archivio privato del
    Master (in entrambe le direzioni: la stessa voce può iniziare in uno
    dei due contenitori). Solo lo stato risultante "party" è mai visibile
    alle repliche — vedi `core.world_sync.apply_event_to_replica`, che
    applica questo evento come upsert se `new_stash_kind=="party"` o come
    rimozione locale se `"master"` (una voce spostata fuori dal deposito
    comune deve sparire dalla vista delle repliche, non restarci "fantasma").
    """
    entry_id = str(ctx.payload.get("entry_id", ""))
    new_kind = str(ctx.payload.get("new_stash_kind", "")).strip()
    if new_kind not in ("master", "party"):
        return CommandResult(False, "Contenitore di destinazione non valido.")
    entry = loot_repo.get_entry(entry_id) if entry_id else None
    if entry is None or entry.world_id != ctx.world_id:
        return CommandResult(False, "Voce non trovata in questo mondo.")
    # BUG FIX (2026-08-20, report Davide "sposta nell'archivio... archivio
    # risulta sempre vuoto"): `world_id` resta lo stesso mondo in ENTRAMBE
    # le direzioni — l'archivio del Master è privato/mai sincronizzato, ma
    # resta comunque world-scoped come il deposito (vedi il docstring di
    # `loot_repo.py`, "world-scoped su ENTRAMBI gli stash_kind"). Azzerarlo
    # qui per `new_kind == "master"` faceva sparire la voce dalla vista
    # Archivio, che filtra per il mondo correntemente selezionato.
    if not loot_repo.move_entry(entry_id, new_kind, new_world_id=ctx.world_id):
        return CommandResult(False, "Spostamento della voce fallito.")
    updated = loot_repo.get_entry(entry_id)
    dest_label = "deposito del gruppo" if new_kind == "party" else "archivio privato"
    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=perm.CMD_LOOT_STASH_MOVE, target_type="loot_stash", target_id=entry_id,
        summary=f"{ctx.actor_name} ha spostato una voce di bottino nel {dest_label}.",
        payload=json.dumps({"new_stash_kind": new_kind, **_loot_stash_entry_payload(updated)}),
    )
    return CommandResult(True, event=event)


@register_handler(perm.CMD_LOOT_STASH_DELETE)
def _handle_loot_stash_delete(ctx: HandlerContext) -> CommandResult:
    """Elimina definitivamente una voce del deposito comune del gruppo."""
    entry_id = str(ctx.payload.get("entry_id", ""))
    entry = loot_repo.get_entry(entry_id) if entry_id else None
    if entry is None or entry.stash_kind != "party" or entry.world_id != ctx.world_id:
        return CommandResult(False, "Voce non trovata nel deposito del gruppo di questo mondo.")
    if not loot_repo.delete_entry(entry_id):
        return CommandResult(False, "Eliminazione della voce fallita.")
    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=perm.CMD_LOOT_STASH_DELETE, target_type="loot_stash", target_id=entry_id,
        summary=f"{ctx.actor_name} ha eliminato una voce dal deposito del gruppo.",
        payload=json.dumps({"entry_id": entry_id}),
    )
    return CommandResult(True, event=event)


@register_handler(perm.CMD_LOOT_STASH_CLAIM)
def _handle_loot_stash_claim(ctx: HandlerContext) -> CommandResult:
    """
    Un giocatore prende DA SOLO una voce dal deposito comune (decisione di
    design 2026-08-20 — vedi il docstring di `perm.CMD_LOOT_STASH_CLAIM`).
    `ctx.target_id` è il personaggio che riceve la voce: come
    `_handle_hp_self_update`, il ruolo da solo non basta, serve anche
    `perm.is_character_owner()` — un giocatore non può far "prendere" una
    voce al personaggio di un altro.

    A differenza di `_handle_loot_assign` (che lascia alla UI chiamante il
    compito di eliminare la voce d'origine con un secondo comando
    `CMD_LOOT_STASH_DELETE`, vedi `master_loot_assign_dialog.py::_on_confirm`),
    qui applicazione + rimozione della voce avvengono nello STESSO handler:
    un solo comando dal client, un solo giro di rete, e nessuna finestra in
    cui la voce risulti sia ancora nel deposito sia già nell'inventario se
    il secondo comando andasse perso.

    La voce viene presa PER INTERO (mai una quota) — coerente con §3 di
    `loot_design.md`, "tutte le voci non-coins sono indivisibili"; per le
    monete, prendere per intero è la semplificazione scelta per l'auto-
    servizio del giocatore (una ripartizione in percentuale resta
    un'operazione del Master, vedi `show_loot_assign_dialog`/§5).
    """
    character = _resolve_world_character(ctx.world_id, ctx.target_id)
    if character is None:
        return CommandResult(False, "Personaggio non trovato in questo mondo.")
    if not perm.is_character_owner(ctx.actor_device_id, character.owner_device_id):
        return CommandResult(False, "Solo il proprietario del personaggio può prenderne il bottino.")

    entry_id = str(ctx.payload.get("entry_id", ""))
    entry = loot_repo.get_entry(entry_id) if entry_id else None
    if entry is None or entry.stash_kind != "party" or entry.world_id != ctx.world_id:
        return CommandResult(False, "Voce non trovata nel deposito del gruppo di questo mondo — "
                                     "qualcun altro potrebbe averla già presa.")

    if entry.entry_kind == "coins":
        existing = character_repo.get_currencies(character.id)
        ok = character_repo.update_currencies(
            character.id,
            (existing.copper if existing else 0) + entry.copper,
            (existing.silver if existing else 0) + entry.silver,
            (existing.electrum if existing else 0) + entry.electrum,
            (existing.gold if existing else 0) + entry.gold,
            (existing.platinum if existing else 0) + entry.platinum,
        )
        if not ok:
            return CommandResult(False, "Aggiunta delle monete fallita.")
        label = "monete"
    else:
        heuristic_attunement = "sintonia" in (entry.description + " " + entry.source_note).lower()
        # "weapon"/"armor" scrivono su tabelle diverse da `inventory_items`
        # generico — stessa logica di `_handle_loot_assign` sopra.
        if entry.entry_kind == "weapon":
            ok = True
            for _ in range(max(1, entry.quantity)):
                ok = character_repo.create_weapon(
                    character.id, entry.name,
                    damage_dice=entry.weapon_damage_dice, damage_type=entry.weapon_damage_type,
                    attack_bonus=entry.weapon_attack_bonus, damage_bonus=entry.weapon_damage_bonus,
                    properties=entry.weapon_properties, weapon_category=entry.weapon_category,
                    magic_description=entry.description,
                    magic_damages=entry.weapon_magic_damages or "[]",
                    is_magical=heuristic_attunement
                    or bool(entry.weapon_attack_bonus or entry.weapon_damage_bonus)
                    or entry.weapon_magic_damages not in ("", "[]"),
                ) and ok
            created = entry.name if ok else None
        elif entry.entry_kind == "armor":
            created = character_repo.create_inventory_item(
                character.id, entry.name, quantity=entry.quantity, category="armor",
                description=entry.description, ca_value=entry.armor_ca_value,
                armor_type=entry.armor_type, effects=entry.armor_effects,
                requires_attunement=heuristic_attunement,
            )
        else:
            created = character_repo.create_inventory_item(
                character.id, entry.name, quantity=entry.quantity,
                description=entry.description, category="misc",
                requires_attunement=heuristic_attunement,
            )
        if created is None:
            return CommandResult(False, "Aggiunta dell'oggetto fallita.")
        label = f"«{entry.name}»"

    if not loot_repo.delete_entry(entry.id):
        return CommandResult(False, "Rimozione della voce dal deposito fallita.")

    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=perm.CMD_LOOT_STASH_CLAIM, target_type="character", target_id=character.id,
        summary=f"{character.name} ha preso {label} dal deposito del gruppo.",
        payload=json.dumps({"entry_id": entry.id}),
    )
    return CommandResult(True, event=event)


# ---------------------------------------------------------------------------
# RemoteBackend — passo 4: host + client in LAN (§9 del design doc).
# ---------------------------------------------------------------------------

@dataclass
class JoinOutcome:
    """Esito di un tentativo di ingresso in un mondo remoto (§9.4)."""
    status: str  # "approved" | "pending" | "rejected" | "error"
    request_id: str = ""
    error: str = ""
    #: `"join"` (ingresso normale) oppure `"transfer"` (riscatto di un codice di
    #: trasferimento, §11.9): serve alla UI per scrivere "In attesa che il master
    #: approvi il TRASFERIMENTO" invece di "l'ingresso". Lo dichiara l'host nella
    #: risposta; un host più vecchio non manda la chiave e resta `"join"`.
    kind: str = "join"
    #: Motivo strutturato del rifiuto, quando l'host ne fornisce uno
    #: (`"transferred_away"`: questo dispositivo è stato sostituito da un altro).
    #: La UI può reagire in modo diverso da un errore generico.
    reason: str = ""


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

    def join(self, join_code: str, pin: str, display_name: str,
              transfer_code: str = "") -> JoinOutcome:
        """Primo passo dell'ingresso (§9.4). Un dispositivo già membro del
        mondo ottiene subito `status="approved"`; un dispositivo nuovo
        ottiene `status="pending"` e un `request_id` da interrogare con
        `poll_join_status()` finché il master non decide.

        `transfer_code` (§11.9): se valorizzato, questo dispositivo
        chiede di SUBENTRARE a un membro esistente invece di entrare come nuovo.
        Sostituisce il PIN (che l'host in quel caso non guarda) ma non
        l'approvazione del master. Campo aggiunto in coda alla richiesta JSON:
        un host più vecchio ignora la chiave sconosciuta, per questo
        `PROTOCOL_VERSION` non cambia — chi chiama deve però verificare prima la
        capacità `device_transfer` in `check_world()`, altrimenti l'host vecchio
        interpreterebbe la richiesta come un ingresso normale con PIN vuoto e
        risponderebbe "PIN errato"."""
        body = {
            "join_code": join_code, "pin": pin,
            "device_id": self.device_id, "display_name": display_name,
            "protocol_version": protocol.PROTOCOL_VERSION,
        }
        if transfer_code:
            body["transfer_code"] = transfer_code
        try:
            status, data = self._request("POST", "/join", body)
        except (OSError, http.client.HTTPException) as e:
            self._state = "error"
            return JoinOutcome("error", error=f"Host non raggiungibile: {e}")

        if status != 200:
            self._state = "error"
            return JoinOutcome(
                "error", error=data.get("error", "Ingresso rifiutato."),
                reason=str(data.get("reason", "")),
            )

        result_status = data.get("status")
        if result_status == "approved":
            self.token = str(data.get("token", ""))
            self._state = "connected"
            return JoinOutcome("approved")
        if result_status == "pending":
            self._state = "pending"
            return JoinOutcome(
                "pending", request_id=str(data.get("request_id", "")),
                kind=str(data.get("kind", "join")),
            )
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

    def cancel_join_request(self, request_id: str) -> bool:
        """`POST /join/cancel` — annulla una propria richiesta di ingresso
        ancora in sospeso, necessario per poterne inviare una nuova.
        `True` solo se l'host conferma l'annullamento — un errore
        di rete o una richiesta già evasa (approvata/rifiutata nel
        frattempo) ritornano `False`, il chiamante decide come reagire
        (tipicamente: prova comunque a inviarne una nuova)."""
        try:
            status, _data = self._request(
                "POST", "/join/cancel",
                {"request_id": request_id, "device_id": self.device_id},
            )
        except (OSError, http.client.HTTPException):
            return False
        return status == 200

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
        ingresso o dopo una lunga assenza"): mondo + membri + giornale
        eventi, più (vedi `network.host_server.WorldHostServer.handle_snapshot`)
        l'export delle istanze di personaggio di cui il chiamante è
        proprietario e le richieste di modifica pendenti che le
        riguardano."""
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
                "protocol_version": protocol.PROTOCOL_VERSION,
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
        # `data` (§11.9): dati di risposta destinati solo al
        # mittente, che NON possono viaggiare nel payload dell'evento perché il
        # giornale è trasmesso a tutte le repliche. Un host più vecchio non
        # manda la chiave: `.get` la rende assente, non un errore.
        extra = data.get("data")
        return CommandResult(
            bool(data.get("success")), str(data.get("error", "")), event,
            data=extra if isinstance(extra, dict) else None,
        )

    def get_character(self, character_id: str) -> dict | None:
        """`GET /character/<id>` (Multiplayer passo 6) — export integrale
        di UNA istanza di cui questo dispositivo è proprietario, usato da
        `core.world_sync` per rimaterializzare la replica locale dopo un
        evento che l'ha toccata, senza riscaricare l'intero `/snapshot`.
        Ritorna `None` se non connesso, non raggiungibile, o se il
        personaggio non è (più) di proprietà di questo dispositivo (403/404
        dell'host — vedi `WorldHostServer.handle_get_character`)."""
        if self.token is None or not character_id:
            return None
        try:
            status, data = self._request(
                "GET", f"/character/{urllib.parse.quote(character_id, safe='')}", authed=True,
            )
        except (OSError, http.client.HTTPException):
            return None
        if status != 200:
            return None
        return data.get("character")

    def fetch_map_image(self, map_id: str) -> bytes | None:
        """
        `GET /map/<id>/image` (§6.4, passo 8) — bytes grezzi dell'immagine
        di una mappa condivisa, MAI base64/JSON: prima rotta non-JSON del
        progetto, quindi non passa da `_request()` (che presuppone sempre
        un corpo JSON in risposta). `None` se non connesso, non
        raggiungibile, o l'host risponde un errore (mappa non trovata/non
        condivisa/non membro — vedi `WorldHostServer.handle_map_image`).
        Il chiamante (`ui/views/maps_view.py`) la scarica una volta sola e
        la mette in cache locale (`maps_repo.update_map(..., image_data=...)`),
        mai un fetch ad ogni apertura.
        """
        if self.token is None or not map_id:
            return None
        conn = http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)
        try:
            conn.request(
                "GET", f"/map/{urllib.parse.quote(map_id, safe='')}/image",
                headers={"Authorization": f"Bearer {self.token}"},
            )
            resp = conn.getresponse()
            raw = resp.read()
            if resp.status != 200:
                return None
            return raw
        except (OSError, http.client.HTTPException):
            return None
        finally:
            conn.close()

    def fetch_map_annotations(self, map_id: str) -> str | None:
        """
        `GET /map/<id>/annotations` — backfill lazy dei tratti
        di disegno di una mappa condivisa per un dispositivo che non li ha
        mai visti (tipicamente un giocatore entrato DOPO che il master
        aveva già disegnato — vedi `WorldHostServer.handle_map_annotations`).
        A differenza di `fetch_map_image`
        sopra, questa risposta È JSON (una stringa `annotations`, lo stesso
        formato di `game_maps.annotations`), quindi passa dal normale
        `_request()` invece di un client HTTP manuale. `None` se non
        connesso/non raggiungibile/l'host risponde un errore — il chiamante
        (`core/world_sync.py`) tratta `None` come "riprova al prossimo
        giro", mai un'eccezione.
        """
        if self.token is None or not map_id:
            return None
        try:
            status, data = self._request(
                "GET", f"/map/{urllib.parse.quote(map_id, safe='')}/annotations", authed=True,
            )
        except (OSError, http.client.HTTPException):
            return None
        if status != 200:
            return None
        return str(data.get("annotations", "[]"))

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
