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

from core import damage_rules
from core import world_permissions as perm
from data.models import WorldEvent
from data.repositories import character_repo, world_repo
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
#   3. scrive un evento con un `summary` leggibile — è il registro
#      richiesto da Davide, non una tabella a parte (§5).
#
# Fuori scope in questo passo (restano nella matrice dei permessi ma senza
# handler, esattamente come CMD_MAP_PUBLISH/ecc. lo erano prima del passo
# 3/6 per le istanze — non ridiscutere chi può inviarli, solo aggiungere
# l'handler quando arriva il loro passo): CMD_LOOT_ASSIGN (il Bottino
# funziona già in locale, `loot_design.md` passo 6 — deposito lato
# giocatore — dipende da qui ma è un lavoro a sé), CMD_ENCOUNTER_MANAGE/
# CMD_COMBAT_TOGGLE_VISIBILITY (passo 7, §6.5), CMD_MAP_PUBLISH/
# CMD_MAP_DRAW (passo 8, §6.4), CMD_NOTE_SHARE (passo 7, §6.2), CMD_DICE_
# REQUEST (è una richiesta senza scrittura sul personaggio — richiede un
# meccanismo di notifica lato giocatore non ancora progettato, valutato a
# parte).
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


@register_handler(perm.CMD_HP_DAMAGE)
def _handle_hp_damage(ctx: HandlerContext) -> CommandResult:
    """Applica danno — stessa regola PHB della scheda locale
    (`core/damage_rules.apply_damage`, estratta il 2026-08-06 apposta per
    essere riusata qui senza duplicare l'algoritmo)."""
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
    damage_rules.apply_heal(character, amount)
    character_repo.update_hp(character.id, character.hp_current, character.hp_temp)

    event = world_repo.append_event(
        ctx.world_id, ctx.actor_device_id, ctx.actor_name,
        kind=perm.CMD_HP_HEAL, target_type="character", target_id=character.id,
        summary=f"{ctx.actor_name} ha curato {character.name} di {amount} PF "
                f"({before_hp} → {character.hp_current}).",
        payload=json.dumps({"amount": amount}),
        before_state=json.dumps({"hp_current": before_hp}),
    )
    return CommandResult(True, event=event)


@register_handler(perm.CMD_CONDITION_APPLY)
def _handle_condition_apply(ctx: HandlerContext) -> CommandResult:
    character = _resolve_world_character(ctx.world_id, ctx.target_id)
    if character is None:
        return CommandResult(False, "Personaggio non trovato in questo mondo.")
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
        kind=perm.CMD_CONDITION_APPLY, target_type="character", target_id=character.id,
        summary=f"{ctx.actor_name} ha imposto la condizione «{condition_name}» a {character.name}.",
        payload=json.dumps({"condition_key": condition_key, "source": source, "note": note}),
    )
    return CommandResult(True, event=event)


@register_handler(perm.CMD_CONDITION_REMOVE)
def _handle_condition_remove(ctx: HandlerContext) -> CommandResult:
    character = _resolve_world_character(ctx.world_id, ctx.target_id)
    if character is None:
        return CommandResult(False, "Personaggio non trovato in questo mondo.")
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
        kind=perm.CMD_CONDITION_REMOVE, target_type="character", target_id=character.id,
        summary=f"{ctx.actor_name} ha rimosso la condizione «{condition_name}» da {character.name}.",
        payload=json.dumps({"condition_id": condition_id}),
        before_state=json.dumps({"condition_key": condition.condition_key}),
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
        # Correttezza (2026-08-07): DES/COS/SAG entrano nella formula della CA
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
