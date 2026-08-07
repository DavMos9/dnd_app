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

import time

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

#: Invio automatico (fix 2026-08-07, Multiplayer §7/step 7 "Condivisione" —
#: scelta esplicita di Davide dopo un confronto sui pro/contro: "sì, invio
#: automatico in tempo reale") dei PF che il giocatore stesso modifica sulla
#: propria scheda (danno subito, cura, riposo, tiri salvezza contro morte,
#: modifica manuale) — mai un'azione visibile, parte dal client con lo
#: stesso principio "best effort" di `CMD_CHARACTER_INSTANCE_SYNC`: se fallisce
#: (host irraggiungibile, cooldown) la scheda locale resta comunque corretta,
#: il prossimo invio porterà lo stato più recente (idempotente: valori
#: assoluti, mai un delta). Ruolo minimo `player`, proprietà verificata come
#: `CMD_CHANGE_REQUEST_RESPOND`/`CMD_CHARACTER_INSTANCE_SYNC` — un giocatore
#: può aggiornare via rete SOLO la propria istanza.
CMD_HP_SELF_UPDATE = "hp.self_update"

#: Registra sull'host l'istanza di personaggio appena creata/ripresa in
#: locale da `core/character_instances.py::create_or_resume_instance()`
#: (fix 2026-08-07: quella funzione, nata al passo 3 prima che esistesse la
#: rete, scrive SOLO sul DB del dispositivo che la chiama — su un
#: dispositivo che ha solo una replica del mondo, l'host non veniva mai
#: informato, e la Sezione Master non vedeva mai l'istanza). Ruolo minimo
#: `player` come `CMD_CHANGE_REQUEST_RESPOND`: chi invia questo comando può
#: farlo solo per il PROPRIO personaggio — qui non c'è ancora una riga
#: `characters` esistente sull'host da confrontare (è la prima scrittura),
#: quindi l'handler verifica la proprietà leggendo `owner_device_id` dal
#: payload esportato invece che da `_resolve_world_character()`.
CMD_CHARACTER_INSTANCE_SYNC = "character_instance.sync"

PLAYER_OWNED_COMMANDS: frozenset[str] = frozenset({
    CMD_CHANGE_REQUEST_RESPOND,
    CMD_CHARACTER_INSTANCE_SYNC,
    CMD_HP_SELF_UPDATE,
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
    # CMD_HP_SELF_UPDATE (fix 2026-08-07): anche questo evento deve far
    # rimaterializzare la replica su un TERZO dispositivo (es. un co-master
    # su un altro telefono, o il device del padrone stesso se un giorno
    # gira su più dispositivi) — stesso principio già commentato qui sotto
    # per CMD_CHARACTER_INSTANCE_SYNC.
    CMD_HP_SELF_UPDATE,
    # Anche questo comando (fix 2026-08-07) rientra qui: per un TERZO
    # dispositivo del mondo (non l'host, non il proprietario — es. un
    # co-master su un altro telefono) `core/world_sync.py` deve sapere di
    # richiamare la rimaterializzazione via `GET /character/<id>` quando
    # vede questo evento nel giornale, esattamente come per xp.grant e gli
    # altri. `_resync_character_from_host()` gestisce già correttamente il
    # caso "non sono il proprietario, l'host risponde 403" (nessuna
    # scrittura, non un errore) — nessuna logica nuova da aggiungere lì.
    CMD_CHARACTER_INSTANCE_SYNC,
})

# ---------------------------------------------------------------------------
# Anti-spam (fix 2026-08-07, esteso alla difesa in profondità lato host
# nella stessa sessione — Davide, dopo la revisione del primo fix
# "solo client": "sì, anche sull'host"). Solo le costanti e l'aritmetica
# pura vivono qui, coerente col resto di questo modulo (nessuna dipendenza,
# nessun accesso al DB): lo STATO — chi ha fatto cosa e quando — vive in
# ciascun attore che applica il limite, mai qui:
#   - `core.world_sync` — stato lato client/UI (`WorldsView`/`HomeView`),
#     a livello di MODULO (non di istanza: quelle view vengono ricreate ad
#     ogni navigazione/cambio tema in `ui/app.py`, uno stato tenuto
#     sull'istanza si azzererebbe ad ogni ricreazione — bug reale trovato
#     il 2026-08-07 in una prima versione di questo fix, corretto qui);
#   - `core.world_backend.LocalBackend` — stato lato host per i comandi
#     (`send_command()` è il choke point unico, sia per un mondo ospitato
#     da questo dispositivo sia per un comando arrivato via rete);
#   - `network.host_server.WorldHostServer` — stato lato host per i
#     tentativi di ingresso (`/join`), scoped correttamente per istanza:
#     un'istanza vive quanto la sessione di hosting, un nuovo `start()`
#     è già una nuova sessione con PIN nuovo (§9.4).
# ---------------------------------------------------------------------------

MASTER_ACTION_COOLDOWN_S = 3.0
NETWORK_REQUEST_COOLDOWN_S = 10.0

#: Cooldown DEDICATO a `CMD_HP_SELF_UPDATE` (fix 2026-08-07) — deliberatamente
#: separato da `MASTER_ACTION_COOLDOWN_S`: quello protegge un'azione con
#: conferma esplicita dell'utente (una pillola, un dialog), qui invece
#: l'invio è automatico e silenzioso ad ogni modifica dei PF sulla propria
#: scheda (danno/cura/riposo/TS morte/modifica manuale — potenzialmente
#: diversi tocchi ravvicinati durante un combattimento). Il lato client non
#: BLOCCA mai l'azione locale per questo cooldown (la scheda del giocatore
#: deve restare sempre reattiva): la usa solo per decidere quando è il
#: momento di inviare il valore più recente (debounce in `core.world_sync`),
#: mai per mostrare un errore. Il valore, più corto di
#: `MASTER_ACTION_COOLDOWN_S`, riflette che qui non c'è alcuna attesa
#: percepita dall'utente da minimizzare (è tutto in background).
HP_SELF_UPDATE_COOLDOWN_S = 1.5

#: Le azioni di "Interviene a distanza" (§7) mostrate come pillole in
#: `ui/views/world/world_view.py::_remote_character_row` — un sottoinsieme
#: esplicito di `MASTER_AND_OWNER_COMMANDS`, che include anche comandi
#: (mappe, incontri, note condivise, dadi) non gestiti da quella sezione
#: della UI o non ancora operativi. Elenco chiuso: se una nuova pillola
#: viene aggiunta lì, va aggiunta anche qui per restare protetta dal
#: limite sia lato client sia lato host.
MASTER_REMOTE_ACTION_COMMANDS: frozenset[str] = frozenset({
    CMD_XP_GRANT, CMD_HP_DAMAGE, CMD_HP_HEAL, CMD_CONDITION_APPLY, CMD_CONDITION_REMOVE,
    CMD_CUSTOM_ABILITY_GRANT, CMD_BONUS_SPELL_GRANT, CMD_DIARY_ADD_ENTRY,
    CMD_CHANGE_REQUEST_PROPOSE,
})


def cooldown_remaining(last_action_at: float, cooldown_s: float) -> float:
    """
    Secondi ancora da aspettare prima che una nuova azione sia permessa
    (<=0 se è già permessa adesso). Funzione pura, nessuno stato qui dentro
    — lo stato (l'istante dell'ultima azione) resta sempre al chiamante.

    `time.monotonic()` come riferimento (mai `time.time()`/`datetime.now()`):
    insensibile a un eventuale cambio dell'orologio di sistema durante la
    sessione, conta solo il tempo trascorso davvero.
    """
    return cooldown_s - (time.monotonic() - last_action_at)


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
# modifica approvata dal giocatore (§7.1, CMD_CHANGE_REQUEST_PROPOSE). La
# protezione reale è STRUTTURALE (nessun handler in `world_backend.py`
# scrive questi campi al di fuori del sottoinsieme allow-listato in
# `CHANGE_REQUEST_ALLOWED_FIELDS` sotto), non un controllo a runtime su
# questa lista — pulizia 2026-08-07: rimosso `is_forbidden_character_field()`,
# mai chiamato da nessun handler. La costante resta: documenta §7 in una
# forma verificabile dal codice (non solo in prosa nel design doc), ed è il
# riferimento esplicito di `CHANGE_REQUEST_ALLOWED_FIELDS` qui sotto.
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


def is_change_request_field_allowed(field_name: str) -> bool:
    return field_name in CHANGE_REQUEST_ALLOWED_FIELDS
