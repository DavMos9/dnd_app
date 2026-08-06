"""
Matrice dei permessi del Mondo condiviso — §7 di
`dnd_app/docs/multiplayer_design.md`.

Modulo puro: nessuna dipendenza da Flet (`core/*.py` non ne ha mai), nessun
accesso al DB. Riceve un ruolo e un "kind" di comando (la stessa stringa che
finirà su `world_events.kind`) e risponde se è permesso — unico punto di
verità per "chi può fare cosa", richiamato sia da `core/world_backend.py`
(validazione comandi, l'unico punto che conta davvero: §5, "impossibile
aggirarli da un client modificato") sia dalla UI (per mostrare/nascondere le
azioni non permesse, comodità dell'utente, non sicurezza).

I comandi elencati qui sotto non hanno ancora tutti un handler in
`world_backend.py`: molti diventano operativi solo dal passo 3 (istanze di
personaggio) o dal passo 6 (interventi del master) del piano. La matrice
nasce comunque completa ora, seguendo l'elenco chiuso di §7: registrare un
nuovo comando nei passi successivi significa aggiungere un handler, non
ridiscutere chi può inviarlo.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Ruoli (§4) — in scala di privilegio. Nessuno spettatore, scelta di Davide.
# ---------------------------------------------------------------------------

ROLE_PLAYER = "player"
ROLE_MASTER = "master"
ROLE_OWNER = "owner"

_ROLE_RANK: dict[str, int] = {ROLE_PLAYER: 0, ROLE_MASTER: 1, ROLE_OWNER: 2}


def is_valid_role(role: str) -> bool:
    return role in _ROLE_RANK


# ---------------------------------------------------------------------------
# Comandi riservati all'owner — gestione del mondo e dei membri (§4).
# ---------------------------------------------------------------------------

CMD_WORLD_RENAME = "world.rename"
CMD_WORLD_DELETE = "world.delete"
CMD_WORLD_JOIN_CODE_REGENERATE = "world.join_code.regenerate"
CMD_WORLD_TRANSFER_OWNERSHIP = "world.transfer_ownership"
CMD_MEMBER_PROMOTE = "member.promote"
CMD_MEMBER_DEMOTE = "member.demote"
CMD_MEMBER_KICK = "member.kick"

OWNER_ONLY_COMMANDS: frozenset[str] = frozenset({
    CMD_WORLD_RENAME, CMD_WORLD_DELETE, CMD_WORLD_JOIN_CODE_REGENERATE,
    CMD_WORLD_TRANSFER_OWNERSHIP, CMD_MEMBER_PROMOTE, CMD_MEMBER_DEMOTE,
    CMD_MEMBER_KICK,
})

# ---------------------------------------------------------------------------
# Comandi consentiti a master E owner — elenco chiuso di §7 (tabella
# "Consentito ai ruoli master e owner"). Operativi dal passo 3/6 in poi.
# ---------------------------------------------------------------------------

CMD_XP_GRANT = "xp.grant"
CMD_LOOT_ASSIGN = "loot.assign"
CMD_HP_DAMAGE = "hp.damage"
CMD_HP_HEAL = "hp.heal"
CMD_CONDITION_APPLY = "condition.apply"
CMD_CONDITION_REMOVE = "condition.remove"
CMD_RESOURCE_CONSUME = "resource.consume"
CMD_RESOURCE_RESTORE = "resource.restore"
CMD_CUSTOM_ABILITY_GRANT = "custom_ability.grant"
CMD_BONUS_SPELL_GRANT = "bonus_spell.grant"
CMD_DIARY_ADD_ENTRY = "diary.add_entry"
CMD_DICE_REQUEST = "dice.request"
CMD_ENCOUNTER_MANAGE = "encounter.manage"
CMD_MAP_PUBLISH = "map.publish"
CMD_MAP_DRAW = "map.draw"
CMD_NOTE_SHARE = "note.share"
CMD_COMBAT_TOGGLE_VISIBILITY = "combat.toggle_visibility"
CMD_CHANGE_REQUEST_PROPOSE = "change_request.propose"

MASTER_AND_OWNER_COMMANDS: frozenset[str] = frozenset({
    CMD_XP_GRANT, CMD_LOOT_ASSIGN, CMD_HP_DAMAGE, CMD_HP_HEAL,
    CMD_CONDITION_APPLY, CMD_CONDITION_REMOVE, CMD_RESOURCE_CONSUME,
    CMD_RESOURCE_RESTORE, CMD_CUSTOM_ABILITY_GRANT, CMD_BONUS_SPELL_GRANT,
    CMD_DIARY_ADD_ENTRY, CMD_DICE_REQUEST, CMD_ENCOUNTER_MANAGE,
    CMD_MAP_PUBLISH, CMD_MAP_DRAW, CMD_NOTE_SHARE,
    CMD_COMBAT_TOGGLE_VISIBILITY, CMD_CHANGE_REQUEST_PROPOSE,
})

# ---------------------------------------------------------------------------
# Comandi che un giocatore invia sulla PROPRIA istanza — §6.1 e §7.1. Il
# ruolo minimo è `player` (chiunque nel mondo può inviarli), ma il ruolo da
# solo non basta: l'handler in `core/world_backend.py` deve SEMPRE
# verificare in aggiunta che `actor_device_id` sia il proprietario del
# personaggio bersaglio (`characters.owner_device_id`), altrimenti un
# giocatore potrebbe rispondere alla richiesta di modifica di un altro. La
# stessa regola di "riservato al proprietario, mai al master" già decisa
# per «Aggiorna il mio foglio» (§6.1) — qui codificata come comando invece
# che come azione locale perché deve poter essere inviata da remoto.
# ---------------------------------------------------------------------------

CMD_CHANGE_REQUEST_RESPOND = "change_request.respond"

PLAYER_OWNED_COMMANDS: frozenset[str] = frozenset({
    CMD_CHANGE_REQUEST_RESPOND,
})

#: Ogni comando conosciuto -> ruolo minimo richiesto per inviarlo.
_MIN_ROLE_FOR_COMMAND: dict[str, str] = {
    **{k: ROLE_OWNER for k in OWNER_ONLY_COMMANDS},
    **{k: ROLE_MASTER for k in MASTER_AND_OWNER_COMMANDS},
    **{k: ROLE_PLAYER for k in PLAYER_OWNED_COMMANDS},
}


# ---------------------------------------------------------------------------
# Sottoinsieme dei comandi sopra che MUTA davvero un'istanza di personaggio
# (a differenza di, es., `world.rename` o — tra quelli sulle istanze —
# `change_request.propose`, che crea solo una richiesta in sospeso senza
# ancora applicare nulla). `core/world_sync.py` lo usa per decidere quando
# rimaterializzare la replica locale di un personaggio dopo un evento
# (Multiplayer passo 6): un solo punto di verità, non una lista duplicata
# nel modulo di sincronizzazione.
# ---------------------------------------------------------------------------

CHARACTER_MUTATING_COMMANDS: frozenset[str] = frozenset({
    CMD_XP_GRANT, CMD_HP_DAMAGE, CMD_HP_HEAL, CMD_CONDITION_APPLY, CMD_CONDITION_REMOVE,
    CMD_RESOURCE_CONSUME, CMD_RESOURCE_RESTORE, CMD_CUSTOM_ABILITY_GRANT,
    CMD_BONUS_SPELL_GRANT, CMD_DIARY_ADD_ENTRY, CMD_CHANGE_REQUEST_RESPOND,
})


def requires_character_ownership(command_kind: str) -> bool:
    """True se, oltre al ruolo, l'handler deve anche verificare che
    l'autore del comando sia il proprietario del personaggio bersaglio
    (§6.1/§7.1) — un controllo che questo modulo non può fare da solo
    perché non tocca mai il DB (`characters.owner_device_id` va letto dal
    chiamante)."""
    return command_kind in PLAYER_OWNED_COMMANDS


def is_character_owner(actor_device_id: str, character_owner_device_id: str) -> bool:
    """Confronto puro, nessun accesso al DB: il chiamante (l'handler in
    `core/world_backend.py`) ha già letto `characters.owner_device_id`."""
    return bool(actor_device_id) and actor_device_id == character_owner_device_id


def can_perform(role: str, command_kind: str) -> bool:
    """
    True se `role` può inviare un comando di tipo `command_kind`.

    Fail-closed: un comando non registrato in nessuna delle due liste sopra
    è rifiutato per chiunque, owner incluso — coerente con "nessun percorso
    di comando arbitrario" (§9.4). Un nuovo comando va sempre aggiunto
    esplicitamente qui prima di poter essere autorizzato: non esiste un
    default permissivo.
    """
    if not is_valid_role(role):
        return False
    required = _MIN_ROLE_FOR_COMMAND.get(command_kind)
    if required is None:
        return False
    return _ROLE_RANK[role] >= _ROLE_RANK[required]


# ---------------------------------------------------------------------------
# Campi di `characters` vietati a chiunque non sia il giocatore stesso (§7,
# tabella "Vietato a chiunque tranne il giocatore"). Nessun comando può
# scriverli direttamente, nemmeno l'owner: l'unica via è la richiesta di
# modifica approvata dal giocatore (§7.1, CMD_CHANGE_REQUEST_PROPOSE).
#
# Competenze e talenti non compaiono come nomi di campo perché non sono
# colonne di `characters` (vivono in `character_proficiencies`): sono
# comunque coperti dal divieto, rappresentati nel `payload` della richiesta
# di modifica con la propria struttura invece che come override di colonna.
# ---------------------------------------------------------------------------

FORBIDDEN_CHARACTER_FIELDS: frozenset[str] = frozenset({
    "name", "race", "subrace", "class_name", "subclass", "background",
    "alignment", "image_path", "image_data",
    "str_score", "dex_score", "con_score", "int_score", "wis_score", "cha_score",
    "level",
    "fighting_style", "totem_animal", "land_terrain", "pact_boon", "dragon_ancestry",
})

#: Sottoinsieme dei campi vietati che UNA richiesta di modifica può proporre
#: (§7.1: "riguarda solo i campi altrimenti vietati: punteggi, competenze,
#: talenti, livello, e le scelte di classe"). Esclude deliberatamente
#: l'identità pura del personaggio (nome/razza/sottorazza/classe/
#: sottoclasse/background/allineamento/ritratto): quella non si negozia
#: nemmeno con l'approvazione del giocatore, è la definizione stessa del
#: personaggio, non una house rule numerica.
CHANGE_REQUEST_ALLOWED_FIELDS: frozenset[str] = frozenset({
    "str_score", "dex_score", "con_score", "int_score", "wis_score", "cha_score",
    "level",
    "fighting_style", "totem_animal", "land_terrain", "pact_boon", "dragon_ancestry",
})


def is_forbidden_character_field(field_name: str) -> bool:
    return field_name in FORBIDDEN_CHARACTER_FIELDS


def is_change_request_field_allowed(field_name: str) -> bool:
    return field_name in CHANGE_REQUEST_ALLOWED_FIELDS
