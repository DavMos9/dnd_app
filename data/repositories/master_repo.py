"""
Repository per la Sezione Master: rubrica NPC/mostri, incontri e membri
d'incontro. Tutta la logica di accesso al DB per queste 3 tabelle è qui.

Deliberatamente indipendente da `character_repo.py` — nessuna delle 3
tabelle (`master_npcs`, `master_encounters`, `master_encounter_members`) ha
una FK obbligatoria verso `characters` (vedi `data/database.py` e
`dnd_app/docs/master_section_design.md` per il ragionamento completo). Le
uniche letture di `characters` qui dentro sono in sola lettura, per
risolvere nome/CA/PF live di un membro d'incontro di tipo "character" — mai
una scrittura su quella tabella da questo modulo.
"""

import json
import logging
from datetime import datetime

from data.database import get_connection
from data.game_data.game_data_loader import parse_monster_xp
from data.models import MasterNpc, MasterEncounter, MasterEncounterMember, MasterCampaignNote

logger = logging.getLogger(__name__)


def _s(value) -> str:
    """Converte None in stringa vuota per i campi TEXT NOT NULL."""
    return value if value is not None else ""


# ---------------------------------------------------------------------------
# master_npcs
# ---------------------------------------------------------------------------

def _row_to_npc(row) -> MasterNpc:
    d = dict(row)
    return MasterNpc(
        id=d["id"],
        name=d.get("name", ""),
        role=d.get("role", ""),
        notes=d.get("notes", ""),
        tags=d.get("tags", ""),
        has_stat_block=bool(d.get("has_stat_block", 0)),
        creature_type=d.get("creature_type", ""),
        size=d.get("size", ""),
        alignment=d.get("alignment", ""),
        ac=d.get("ac", 10),
        ac_note=d.get("ac_note", ""),
        hp_max=d.get("hp_max", 1),
        hp_formula=d.get("hp_formula", ""),
        speed=d.get("speed", ""),
        str_score=d.get("str_score", 10),
        dex_score=d.get("dex_score", 10),
        con_score=d.get("con_score", 10),
        int_score=d.get("int_score", 10),
        wis_score=d.get("wis_score", 10),
        cha_score=d.get("cha_score", 10),
        saving_throws=d.get("saving_throws", "{}"),
        skills=d.get("skills", "{}"),
        damage_vulnerabilities=d.get("damage_vulnerabilities", ""),
        damage_resistances=d.get("damage_resistances", ""),
        damage_immunities=d.get("damage_immunities", ""),
        condition_immunities=d.get("condition_immunities", ""),
        senses=d.get("senses", ""),
        languages=d.get("languages", ""),
        cr=d.get("cr", ""),
        xp=d.get("xp", 0),
        traits=d.get("traits", "[]"),
        actions=d.get("actions", "[]"),
        reactions=d.get("reactions", "[]"),
        legendary_actions=d.get("legendary_actions", "[]"),
        source_page=d.get("source_page", ""),
        world_id=d.get("world_id", ""),
        created_at=d.get("created_at", ""),
        updated_at=d.get("updated_at", ""),
    )


def get_npcs(query: str = "", world_id: str = "") -> list[MasterNpc]:
    """
    Gli NPC di rubrica del mondo indicato, ordinati per nome. `query`
    (opzionale) filtra per sottostringa case-insensitive su nome/ruolo/tag.

    `world_id` (2026-08-12, bug report Davide: "in Master... npc... tutto
    deve essere dipendente dal mondo") — filtro per UGUAGLIANZA esatta,
    stesso principio già in uso per personaggi/note/bottino: `""` (default)
    ritorna solo gli NPC locali/di nessun mondo, un id di mondo ritorna
    solo i suoi. Mai un OR/"mostra tutti" — un mondo è un container.
    """
    try:
        conn = get_connection()
        if query.strip():
            q = f"%{query.strip().lower()}%"
            rows = conn.execute(
                """SELECT * FROM master_npcs
                   WHERE world_id=? AND (lower(name) LIKE ? OR lower(role) LIKE ? OR lower(tags) LIKE ?)
                   ORDER BY name""",
                (world_id, q, q, q),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM master_npcs WHERE world_id=? ORDER BY name",
                (world_id,),
            ).fetchall()
        conn.close()
        return [_row_to_npc(r) for r in rows]
    except Exception as e:
        logger.error(f"Errore get_npcs: {e}")
        return []


def get_npc_by_id(npc_id: str) -> MasterNpc | None:
    """
    Singolo NPC di rubrica per id — usato da `MasterEncounterView` per
    risolvere lo stat block completo di un membro `kind="npc"` (2026-08-03,
    richiesta di Davide: consultare la scheda/tirare i dadi di un NPC/mostro
    direttamente dal tracker di combattimento, senza dover tornare alla
    Rubrica NPC).
    """
    try:
        conn = get_connection()
        row = conn.execute("SELECT * FROM master_npcs WHERE id=?", (npc_id,)).fetchone()
        conn.close()
        return _row_to_npc(row) if row else None
    except Exception as e:
        logger.error(f"Errore get_npc_by_id: {e}")
        return None


def create_npc(
    name: str,
    role: str = "",
    notes: str = "",
    tags: str = "",
    has_stat_block: bool = False,
    creature_type: str = "",
    size: str = "",
    alignment: str = "",
    ac: int = 10,
    ac_note: str = "",
    hp_max: int = 1,
    hp_formula: str = "",
    speed: str = "",
    str_score: int = 10,
    dex_score: int = 10,
    con_score: int = 10,
    int_score: int = 10,
    wis_score: int = 10,
    cha_score: int = 10,
    saving_throws: str = "{}",
    skills: str = "{}",
    damage_vulnerabilities: str = "",
    damage_resistances: str = "",
    damage_immunities: str = "",
    condition_immunities: str = "",
    senses: str = "",
    languages: str = "",
    cr: str = "",
    xp: int = 0,
    traits: str = "[]",
    actions: str = "[]",
    reactions: str = "[]",
    legendary_actions: str = "[]",
    source_page: str = "",
    world_id: str = "",
) -> MasterNpc | None:
    """
    Crea un nuovo NPC di rubrica. Ritorna l'NPC creato, o None in caso di
    errore. `world_id` (2026-08-12): il mondo correntemente selezionato in
    Modalità Master — `""` per un NPC locale/di nessun mondo.
    """
    import uuid as _uuid
    npc_id = str(_uuid.uuid4())
    now = datetime.now().isoformat()
    try:
        conn = get_connection()
        conn.execute(
            """
            INSERT INTO master_npcs (
                id, name, role, notes, tags, has_stat_block,
                creature_type, size, alignment, ac, ac_note, hp_max, hp_formula, speed,
                str_score, dex_score, con_score, int_score, wis_score, cha_score,
                saving_throws, skills,
                damage_vulnerabilities, damage_resistances, damage_immunities, condition_immunities,
                senses, languages, cr, xp, traits, actions, reactions, legendary_actions,
                source_page, world_id, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                npc_id, _s(name), _s(role), _s(notes), _s(tags), int(has_stat_block),
                _s(creature_type), _s(size), _s(alignment), ac, _s(ac_note), hp_max, _s(hp_formula), _s(speed),
                str_score, dex_score, con_score, int_score, wis_score, cha_score,
                _s(saving_throws) or "{}", _s(skills) or "{}",
                _s(damage_vulnerabilities), _s(damage_resistances), _s(damage_immunities), _s(condition_immunities),
                _s(senses), _s(languages), _s(cr), int(xp or 0), _s(traits) or "[]", _s(actions) or "[]",
                _s(reactions) or "[]", _s(legendary_actions) or "[]",
                _s(source_page), _s(world_id), now, now,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM master_npcs WHERE id=?", (npc_id,)).fetchone()
        conn.close()
        return _row_to_npc(row) if row else None
    except Exception as e:
        logger.error(f"Errore create_npc: {e}")
        return None


def create_npc_from_monster(
    monster: dict,
    name_override: str = "",
    role: str = "",
    notes: str = "",
    tags: str = "",
    world_id: str = "",
) -> MasterNpc | None:
    """
    Convenienza per il percorso "Nuovo dal Bestiario" (Sezione Master):
    precompila tutti i campi stat block da un dict grezzo di `monsters.json`
    (stessa forma già usata da `_save_creature()` in `combattimento_tab.py`),
    con `has_stat_block=True` e `source_page` valorizzato come citazione
    leggibile invece di un numero grezzo. `world_id` (2026-08-12): vedi
    `create_npc()`.
    """
    src_page = monster.get("source_page")
    source_page = f"da Bestiario: {monster.get('name', '')} (p.{src_page})" if src_page else f"da Bestiario: {monster.get('name', '')}"
    return create_npc(
        name=name_override or monster.get("name", ""),
        role=role,
        notes=notes,
        tags=tags,
        world_id=world_id,
        has_stat_block=True,
        creature_type=monster.get("type", monster.get("creature_type", "")),
        size=monster.get("size", ""),
        alignment=monster.get("alignment", ""),
        ac=int(monster.get("ac", 10)),
        ac_note=monster.get("ac_note", ""),
        hp_max=int(monster.get("hp_max", 1)),
        hp_formula=monster.get("hp_formula", ""),
        speed=monster.get("speed", ""),
        str_score=int(monster.get("str_score", 10)),
        dex_score=int(monster.get("dex_score", 10)),
        con_score=int(monster.get("con_score", 10)),
        int_score=int(monster.get("int_score", 10)),
        wis_score=int(monster.get("wis_score", 10)),
        cha_score=int(monster.get("cha_score", 10)),
        saving_throws=json.dumps(monster.get("saving_throws", {})),
        skills=json.dumps(monster.get("skills", {})),
        damage_vulnerabilities=monster.get("damage_vulnerabilities", ""),
        damage_resistances=monster.get("damage_resistances", ""),
        damage_immunities=monster.get("damage_immunities", ""),
        condition_immunities=monster.get("condition_immunities", ""),
        senses=monster.get("senses", ""),
        languages=monster.get("languages", ""),
        cr=str(monster.get("cr", "")),
        xp=parse_monster_xp(monster.get("xp", 0)),
        traits=json.dumps(monster.get("traits", [])),
        actions=json.dumps(monster.get("actions", [])),
        reactions=json.dumps(monster.get("reactions", [])),
        legendary_actions=json.dumps(monster.get("legendary_actions", [])),
        source_page=source_page,
    )


def update_npc(npc: MasterNpc) -> bool:
    """Aggiornamento completo di un NPC esistente (tutti i campi)."""
    try:
        conn = get_connection()
        conn.execute(
            """
            UPDATE master_npcs SET
                name=?, role=?, notes=?, tags=?, has_stat_block=?,
                creature_type=?, size=?, alignment=?, ac=?, ac_note=?, hp_max=?, hp_formula=?, speed=?,
                str_score=?, dex_score=?, con_score=?, int_score=?, wis_score=?, cha_score=?,
                saving_throws=?, skills=?,
                damage_vulnerabilities=?, damage_resistances=?, damage_immunities=?, condition_immunities=?,
                senses=?, languages=?, cr=?, xp=?, traits=?, actions=?, reactions=?, legendary_actions=?,
                source_page=?, updated_at=?
            WHERE id=?
            """,
            (
                _s(npc.name), _s(npc.role), _s(npc.notes), _s(npc.tags), int(npc.has_stat_block),
                _s(npc.creature_type), _s(npc.size), _s(npc.alignment), npc.ac, _s(npc.ac_note),
                npc.hp_max, _s(npc.hp_formula), _s(npc.speed),
                npc.str_score, npc.dex_score, npc.con_score, npc.int_score, npc.wis_score, npc.cha_score,
                _s(npc.saving_throws) or "{}", _s(npc.skills) or "{}",
                _s(npc.damage_vulnerabilities), _s(npc.damage_resistances),
                _s(npc.damage_immunities), _s(npc.condition_immunities),
                _s(npc.senses), _s(npc.languages), _s(npc.cr), int(npc.xp or 0),
                _s(npc.traits) or "[]", _s(npc.actions) or "[]",
                _s(npc.reactions) or "[]", _s(npc.legendary_actions) or "[]",
                _s(npc.source_page), datetime.now().isoformat(), npc.id,
            ),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore update_npc: {e}")
        return False


def delete_npc(npc_id: str) -> bool:
    """
    Elimina un NPC dalla rubrica. Non tocca eventuali `master_encounter_members`
    già collegati a questo NPC (FK ON DELETE SET NULL — vedi schema): restano
    nello storico dell'incontro con i valori già cachati al momento
    dell'aggiunta (display_name/ac/hp_*), invece di sparire.
    """
    try:
        conn = get_connection()
        conn.execute("DELETE FROM master_npcs WHERE id=?", (npc_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore delete_npc: {e}")
        return False


# ---------------------------------------------------------------------------
# master_encounters
# ---------------------------------------------------------------------------

def _row_to_encounter(row) -> MasterEncounter:
    d = dict(row)
    return MasterEncounter(
        id=d["id"],
        name=d.get("name", ""),
        notes=d.get("notes", ""),
        round_number=d.get("round_number", 1),
        current_turn_index=d.get("current_turn_index", 0),
        is_archived=bool(d.get("is_archived", 0)),
        created_at=d.get("created_at", ""),
        updated_at=d.get("updated_at", ""),
        world_id=d.get("world_id", ""),
        visible_to_players=bool(d.get("visible_to_players", 0)),
    )


def get_encounters(include_archived: bool = False, world_id: str = "") -> list[MasterEncounter]:
    """
    Incontri del mondo indicato, ordinati per ultima modifica (più recenti
    prima). `world_id` (2026-08-12, bug report Davide: "in Master...
    incontri... tutto deve essere dipendente dal mondo") — filtro per
    UGUAGLIANZA esatta come per NPC/personaggi/note/bottino: `""`
    (default) ritorna solo gli incontri locali/di nessun mondo. La colonna
    esisteva già (Tracker condiviso §6.5) ma prima serviva solo al flag
    "visibile ai giocatori", mai a filtrare questa lista.
    """
    try:
        conn = get_connection()
        if include_archived:
            rows = conn.execute(
                "SELECT * FROM master_encounters WHERE world_id=? ORDER BY updated_at DESC",
                (world_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM master_encounters WHERE is_archived=0 AND world_id=? ORDER BY updated_at DESC",
                (world_id,),
            ).fetchall()
        conn.close()
        return [_row_to_encounter(r) for r in rows]
    except Exception as e:
        logger.error(f"Errore get_encounters: {e}")
        return []


def get_encounter_by_id(encounter_id: str) -> MasterEncounter | None:
    try:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM master_encounters WHERE id=?", (encounter_id,)
        ).fetchone()
        conn.close()
        return _row_to_encounter(row) if row else None
    except Exception as e:
        logger.error(f"Errore get_encounter_by_id: {e}")
        return None


def create_encounter(name: str, notes: str = "", world_id: str = "") -> MasterEncounter | None:
    """
    `world_id` (2026-08-12): il mondo correntemente selezionato in Modalità
    Master al momento della creazione — `""` per un incontro locale/di
    nessun mondo. Distinto da `visible_to_players` (§6.5, sempre spento
    alla creazione): un incontro può appartenere a un mondo senza essere
    ancora rivelato ai giocatori.
    """
    import uuid as _uuid
    enc_id = str(_uuid.uuid4())
    now = datetime.now().isoformat()
    try:
        conn = get_connection()
        conn.execute(
            """INSERT INTO master_encounters
               (id, name, notes, round_number, current_turn_index, is_archived, world_id, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (enc_id, _s(name), _s(notes), 1, 0, 0, _s(world_id), now, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM master_encounters WHERE id=?", (enc_id,)).fetchone()
        conn.close()
        return _row_to_encounter(row) if row else None
    except Exception as e:
        logger.error(f"Errore create_encounter: {e}")
        return None


def archive_encounter(encounter_id: str, archived: bool = True) -> bool:
    """"Termina Incontro" — archivia (o ripristina se archived=False, house rule)."""
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE master_encounters SET is_archived=?, updated_at=? WHERE id=?",
            (int(archived), datetime.now().isoformat(), encounter_id),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore archive_encounter: {e}")
        return False


def delete_encounter(encounter_id: str) -> bool:
    """Elimina l'incontro e, via CASCADE, tutti i suoi membri."""
    try:
        conn = get_connection()
        conn.execute("DELETE FROM master_encounters WHERE id=?", (encounter_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore delete_encounter: {e}")
        return False


def advance_turn(encounter_id: str) -> MasterEncounter | None:
    """
    Avanza al turno successivo tra i membri attivi (is_active=1), ordinati
    per iniziativa decrescente poi order_index — stesso ordine usato da
    `get_encounter_members_resolved()`. A fine giro (ultimo membro attivo
    raggiunto) torna al primo e incrementa `round_number`. Ritorna
    l'incontro aggiornato, o None se l'incontro non esiste o non ha membri
    attivi (in quel caso non modifica nulla).
    """
    try:
        conn = get_connection()
        enc_row = conn.execute(
            "SELECT * FROM master_encounters WHERE id=?", (encounter_id,)
        ).fetchone()
        if not enc_row:
            conn.close()
            return None
        members = conn.execute(
            """SELECT id FROM master_encounter_members
               WHERE encounter_id=? AND is_active=1
               ORDER BY initiative DESC, order_index ASC""",
            (encounter_id,),
        ).fetchall()
        n = len(members)
        if n == 0:
            conn.close()
            return _row_to_encounter(enc_row)

        current_idx = dict(enc_row).get("current_turn_index", 0)
        round_number = dict(enc_row).get("round_number", 1)
        next_idx = current_idx + 1
        if next_idx >= n:
            next_idx = 0
            round_number += 1

        conn.execute(
            "UPDATE master_encounters SET current_turn_index=?, round_number=?, updated_at=? WHERE id=?",
            (next_idx, round_number, datetime.now().isoformat(), encounter_id),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM master_encounters WHERE id=?", (encounter_id,)).fetchone()
        conn.close()
        return _row_to_encounter(row) if row else None
    except Exception as e:
        logger.error(f"Errore advance_turn: {e}")
        return None


def set_encounter_world(encounter_id: str, world_id: str) -> bool:
    """Collega un incontro a un mondo (Multiplayer passo 7C) — chiamata
    quando `MasterEncounterView` riceve un `world_id` non vuoto e
    l'incontro non ce l'ha ancora impostato."""
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE master_encounters SET world_id=?, updated_at=? WHERE id=?",
            (_s(world_id), datetime.now().isoformat(), encounter_id),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore set_encounter_world: {e}")
        return False


def set_encounter_visibility(encounter_id: str, visible: bool) -> bool:
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE master_encounters SET visible_to_players=?, updated_at=? WHERE id=?",
            (int(visible), datetime.now().isoformat(), encounter_id),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore set_encounter_visibility: {e}")
        return False


def get_visible_encounter_for_world(world_id: str) -> MasterEncounter | None:
    """
    L'incontro (se c'è) che il Master ha reso visibile ai giocatori in
    questo mondo (§6.5) — query di scoperta lato giocatore. Funziona
    identica sull'host (dove `master_encounters` è la tabella autoritativa)
    e su una replica (dove la stessa tabella ospita lo specchio scritto da
    `replica_upsert_encounter_snapshot`) — un solo schema, come ogni altra
    tabella del Multiplayer.
    """
    try:
        conn = get_connection()
        row = conn.execute(
            """SELECT * FROM master_encounters
               WHERE world_id=? AND visible_to_players=1 AND is_archived=0
               ORDER BY updated_at DESC LIMIT 1""",
            (world_id,),
        ).fetchone()
        conn.close()
        return _row_to_encounter(row) if row else None
    except Exception as e:
        logger.error(f"Errore get_visible_encounter_for_world: {e}")
        return None


def resolved_members_to_dicts(resolved: list[dict]) -> list[dict]:
    """
    Versione JSON-serializzabile di `get_encounter_members_resolved()` —
    sostituisce la chiave `"member"` (un `MasterEncounterMember`, non
    serializzabile) con i soli campi scalari che servono al trasporto:
    id, character_id, initiative, is_active. Usata per costruire il
    payload di `CMD_ENCOUNTER_MANAGE`/`CMD_COMBAT_TOGGLE_VISIBILITY` (§7C)
    — un solo punto che sa "appiattire" questa struttura, riusato sia
    dall'handler sia da `handle_snapshot()`.
    """
    out = []
    for r in resolved:
        m = r["member"]
        out.append({
            "id": m.id, "character_id": m.character_id, "initiative": m.initiative,
            "is_active": m.is_active, "name": r["name"], "ac": r["ac"],
            "hp_current": r["hp_current"], "hp_max": r["hp_max"], "xp": r.get("xp", 0),
            "source": r["source"], "world_id": r.get("world_id", ""),
        })
    return out


def replica_upsert_encounter_snapshot(world_id: str, encounter_data: dict, members: list[dict]) -> bool:
    """
    Scrive (o aggiorna) sulla replica locale lo specchio di un incontro
    condiviso — unico scrittore usato sia da
    `core.world_sync.apply_event_to_replica` (nuovo evento
    `encounter.manage`/`combat.toggle_visibility`) sia da
    `core.world_sync._finalize_join` (semina iniziale dallo snapshot),
    stesso principio di `save_replica_note`. `encounter_data` è il dict
    prodotto da `dataclasses.asdict(MasterEncounter)`; `members` è già
    nella forma di `resolved_members_to_dicts()`.

    UPDATE-se-esiste-altrimenti-INSERT, MAI `INSERT OR REPLACE`: su SQLite
    quest'ultimo è un DELETE+INSERT anche a parità di id, e
    `master_encounter_members.encounter_id` ha `ON DELETE CASCADE` — su
    questa stessa tabella riusata identica da host e replica (§7C), un
    riavvio a `INSERT OR REPLACE` cancellerebbe silenziosamente i membri
    reali se mai chiamata su un id che sull'HOST è invece la riga
    autoritativa (bug trovato scrivendo la batteria di test dedicata,
    `test_combat_tracker_condiviso.py`).
    """
    encounter_id = str(encounter_data.get("id") or "")
    if not encounter_id:
        return False
    now = datetime.now().isoformat()
    try:
        conn = get_connection()
        existing = conn.execute(
            "SELECT created_at FROM master_encounters WHERE id=?", (encounter_id,)
        ).fetchone()
        params = (
            _s(encounter_data.get("name")), _s(encounter_data.get("notes")),
            int(encounter_data.get("round_number", 1) or 1),
            int(encounter_data.get("current_turn_index", 0) or 0),
            int(bool(encounter_data.get("is_archived", False))),
            _s(world_id or encounter_data.get("world_id")),
            int(bool(encounter_data.get("visible_to_players", False))),
            json.dumps(members), now,
        )
        if existing:
            conn.execute(
                """UPDATE master_encounters
                   SET name=?, notes=?, round_number=?, current_turn_index=?, is_archived=?,
                       world_id=?, visible_to_players=?, replica_members_json=?, updated_at=?
                   WHERE id=?""",
                (*params, encounter_id),
            )
        else:
            conn.execute(
                """INSERT INTO master_encounters
                   (name, notes, round_number, current_turn_index, is_archived,
                    world_id, visible_to_players, replica_members_json, updated_at,
                    id, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (*params, encounter_id, now),
            )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore replica_upsert_encounter_snapshot: {e}")
        return False


def get_replica_encounter_members(encounter_id: str) -> list[dict]:
    """Membri (già risolti, JSON-safe) di un incontro condiviso letti dallo
    specchio di replica — vedi `replica_upsert_encounter_snapshot()`. Sul
    dispositivo che OSPITA il mondo questa colonna resta vuota (l'host
    legge sempre `get_encounter_members_resolved()` dal vivo): il chiamante
    lato UI decide quale delle due usare in base a chi ospita."""
    try:
        conn = get_connection()
        row = conn.execute(
            "SELECT replica_members_json FROM master_encounters WHERE id=?", (encounter_id,)
        ).fetchone()
        conn.close()
        if not row:
            return []
        return json.loads(row["replica_members_json"] or "[]")
    except Exception as e:
        logger.error(f"Errore get_replica_encounter_members: {e}")
        return []


# ---------------------------------------------------------------------------
# master_encounter_members
# ---------------------------------------------------------------------------

def _row_to_member(row) -> MasterEncounterMember:
    d = dict(row)
    return MasterEncounterMember(
        id=d["id"],
        encounter_id=d.get("encounter_id", ""),
        kind=d.get("kind", "adhoc"),
        character_id=d.get("character_id") or "",
        npc_id=d.get("npc_id") or "",
        display_name=d.get("display_name", ""),
        ac=d.get("ac", 0),
        hp_current=d.get("hp_current", 0),
        hp_max=d.get("hp_max", 0),
        xp=d.get("xp", 0),
        initiative=d.get("initiative", 0),
        dex_mod=d.get("dex_mod", 0) or 0,
        order_index=d.get("order_index", 0),
        is_active=bool(d.get("is_active", 1)),
        notes=d.get("notes", ""),
        created_at=d.get("created_at", ""),
        updated_at=d.get("updated_at", ""),
    )


def get_encounter_members(encounter_id: str, active_only: bool = False) -> list[MasterEncounterMember]:
    """Membri grezzi (senza risoluzione nome/CA/PF) — vedi `get_encounter_members_resolved`
    per la versione pronta per la UI, con i dati di `characters`/`master_npcs` già uniti."""
    try:
        conn = get_connection()
        if active_only:
            rows = conn.execute(
                """SELECT * FROM master_encounter_members
                   WHERE encounter_id=? AND is_active=1
                   ORDER BY initiative DESC, order_index ASC""",
                (encounter_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM master_encounter_members
                   WHERE encounter_id=?
                   ORDER BY initiative DESC, order_index ASC""",
                (encounter_id,),
            ).fetchall()
        conn.close()
        return [_row_to_member(r) for r in rows]
    except Exception as e:
        logger.error(f"Errore get_encounter_members: {e}")
        return []


def get_encounter_members_resolved(encounter_id: str, active_only: bool = True) -> list[dict]:
    """
    Membri pronti per la UI: un dict per membro con `member` (il
    `MasterEncounterMember` grezzo) più `name`/`ac`/`hp_current`/`hp_max`
    risolti — per kind="character" letti LIVE da `characters` (mai
    duplicati, characters resta l'unica fonte di verità per i PG); per
    kind="npc"/"adhoc" letti dai valori già cachati sulla riga membro.
    Ordinati per iniziativa decrescente poi order_index.
    """
    members = get_encounter_members(encounter_id, active_only=active_only)
    if not members:
        return []
    try:
        conn = get_connection()
        out: list[dict] = []
        for m in members:
            if m.kind == "character" and m.character_id:
                crow = conn.execute(
                    "SELECT name, ac, hp_current, hp_max, world_id FROM characters WHERE id=?",
                    (m.character_id,),
                ).fetchone()
                if crow:
                    cd = dict(crow)
                    out.append({
                        "member": m,
                        "name": m.display_name or cd.get("name", "?"),
                        "ac": cd.get("ac", 10),
                        "hp_current": cd.get("hp_current", 0),
                        "hp_max": cd.get("hp_max", 0),
                        "xp": 0,  # i PG non contano mai come PE mostro
                        "source": "character",
                        # world_id (fix 2026-08-07, azioni master in Incontro):
                        # "" per un PG locale, altrimenti l'id del mondo di cui
                        # questo PG è istanza — usato dalla UI per decidere se
                        # mostrare le pillole Danno/Cura/Condizione al posto
                        # del solo chip di sola lettura.
                        "world_id": cd.get("world_id", "") or "",
                    })
                    continue
                # Personaggio cancellato nel frattempo — mostra comunque la riga
                out.append({
                    "member": m,
                    "name": m.display_name or "(Personaggio non trovato)",
                    "ac": m.ac, "hp_current": m.hp_current, "hp_max": m.hp_max,
                    "xp": 0,
                    "source": "character",
                    "world_id": "",
                })
            elif m.kind == "npc" and m.npc_id:
                nrow = conn.execute(
                    "SELECT name, ac, hp_max FROM master_npcs WHERE id=?", (m.npc_id,)
                ).fetchone()
                if nrow:
                    nd = dict(nrow)
                    out.append({
                        "member": m,
                        "name": m.display_name or nd.get("name", "?"),
                        "ac": m.ac or nd.get("ac", 10),
                        "hp_current": m.hp_current,
                        "hp_max": m.hp_max or nd.get("hp_max", 1),
                        "xp": m.xp,
                        "source": "npc",
                    })
                    continue
                # NPC cancellato dalla rubrica — ON DELETE SET NULL, restano i cache
                out.append({
                    "member": m,
                    "name": m.display_name or "(NPC rimosso dalla rubrica)",
                    "ac": m.ac, "hp_current": m.hp_current, "hp_max": m.hp_max,
                    "xp": m.xp,
                    "source": "npc",
                })
            else:
                out.append({
                    "member": m,
                    "name": m.display_name or "?",
                    "ac": m.ac, "hp_current": m.hp_current, "hp_max": m.hp_max,
                    "xp": m.xp,
                    "source": "adhoc",
                })
        conn.close()
        return out
    except Exception as e:
        logger.error(f"Errore get_encounter_members_resolved: {e}")
        return []


def add_member(
    encounter_id: str,
    kind: str,
    character_id: str = "",
    npc_id: str = "",
    display_name: str = "",
    ac: int = 0,
    hp_current: int = 0,
    hp_max: int = 0,
    xp: int = 0,
    initiative: int = 0,
    order_index: int = 0,
    dex_mod: int = 0,
) -> MasterEncounterMember | None:
    """
    Aggiunge un combattente all'incontro. `kind`:
      "character" → `character_id` valorizzato, ac/hp_*/xp ignorati (letti live,
                    e non contano mai come PE mostro nel Calcolatore Difficoltà)
      "npc"       → `npc_id` valorizzato, ac/hp_max/xp precompilabili dall'NPC
                    (il chiamante li passa già risolti, questo repo non fa
                    lookup impliciti per restare esplicito su cosa viene salvato)
      "adhoc"     → solo display_name/ac/hp_max/xp, nessun'altra tabella coinvolta
    """
    import uuid as _uuid
    member_id = str(_uuid.uuid4())
    now = datetime.now().isoformat()
    try:
        conn = get_connection()
        conn.execute(
            """INSERT INTO master_encounter_members (
                   id, encounter_id, kind, character_id, npc_id, display_name,
                   ac, hp_current, hp_max, xp, initiative, dex_mod, order_index,
                   is_active, notes, created_at, updated_at
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                member_id, encounter_id, kind,
                character_id or None, npc_id or None, _s(display_name),
                ac, hp_current, hp_max, int(xp or 0), initiative, int(dex_mod or 0),
                order_index, 1, "", now, now,
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM master_encounter_members WHERE id=?", (member_id,)
        ).fetchone()
        conn.close()
        return _row_to_member(row) if row else None
    except Exception as e:
        logger.error(f"Errore add_member: {e}")
        return None


def update_member_hp(member_id: str, hp_current: int) -> bool:
    """Aggiorna i PF correnti di un membro npc/adhoc (per kind="character"
    la UI non deve mai chiamare questa funzione — gli HP restano gestiti
    solo dal giocatore sulla propria scheda)."""
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE master_encounter_members SET hp_current=?, updated_at=? WHERE id=?",
            (max(0, hp_current), datetime.now().isoformat(), member_id),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore update_member_hp: {e}")
        return False


def update_member_initiative(member_id: str, initiative: int) -> bool:
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE master_encounter_members SET initiative=?, updated_at=? WHERE id=?",
            (initiative, datetime.now().isoformat(), member_id),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore update_member_initiative: {e}")
        return False


def remove_member(member_id: str) -> bool:
    """Rimozione soft (is_active=0) — il membro resta nello storico
    dell'incontro invece di sparire, coerente con `is_archived` sull'incontro
    stesso e con la nota di design "storico" già usata per `creature_entries`."""
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE master_encounter_members SET is_active=0, updated_at=? WHERE id=?",
            (datetime.now().isoformat(), member_id),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore remove_member: {e}")
        return False


# ---------------------------------------------------------------------------
# master_campaign_notes
# ---------------------------------------------------------------------------

def _row_to_campaign_note(row) -> MasterCampaignNote:
    d = dict(row)
    return MasterCampaignNote(
        id=d["id"],
        category=d.get("category", "npc"),
        name=d.get("name", ""),
        description=d.get("description", ""),
        status=d.get("status", ""),
        tags=d.get("tags", ""),
        linked_npc_id=d.get("linked_npc_id") or "",
        created_at=d.get("created_at", ""),
        updated_at=d.get("updated_at", ""),
        world_id=d.get("world_id", ""),
        visibility=d.get("visibility") or "private",
        visible_to_device_ids=d.get("visible_to_device_ids") or "[]",
    )


def get_master_campaign_notes(category: str = "", world_id: str | None = None) -> list[MasterCampaignNote]:
    """
    Note di campagna del Master. `category` (opzionale) filtra per categoria
    esatta; senza filtro, ordina prima per categoria poi per data di
    creazione (stesso pattern di `character_repo.get_campaign_notes`).

    `world_id` (2026-08-06, Modalità Master world-scoped): `None` (default)
    non filtra per mondo — compatibilità con eventuali chiamate future che
    vogliono l'elenco completo. `""` restituisce solo le note locali/di
    nessun mondo; un id valorizzato restituisce solo le note di quel mondo —
    stessa convenzione già stabilita per
    `character_repo.get_master_visible_characters()`.
    """
    try:
        conn = get_connection()
        clauses: list[str] = []
        params: list[str] = []
        if category:
            clauses.append("category=?")
            params.append(category)
        if world_id is not None:
            clauses.append("world_id=?")
            params.append(world_id)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = conn.execute(
            f"SELECT * FROM master_campaign_notes{where} ORDER BY category, created_at ASC",
            params,
        ).fetchall()
        conn.close()
        return [_row_to_campaign_note(r) for r in rows]
    except Exception as e:
        logger.error(f"Errore get_master_campaign_notes: {e}")
        return []


def get_master_campaign_note_by_id(note_id: str) -> MasterCampaignNote | None:
    try:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM master_campaign_notes WHERE id=?", (note_id,)
        ).fetchone()
        conn.close()
        return _row_to_campaign_note(row) if row else None
    except Exception as e:
        logger.error(f"Errore get_master_campaign_note_by_id: {e}")
        return None


def get_notes_visible_to(world_id: str, device_id: str) -> list[MasterCampaignNote]:
    """
    Note di campagna condivise, viste da un GIOCATORE (§6.2) — mai le note
    `private` (quelle restano visibili solo dal Master tramite
    `get_master_campaign_notes`, che non applica questo filtro). `visibility`
    "all" → tutti i membri del mondo; "selected" → solo se `device_id` è
    nella lista JSON `visible_to_device_ids` (colonna non indicizzabile in
    SQL, filtro fatto in Python dopo aver ristretto a "selected" via SQL).
    """
    try:
        conn = get_connection()
        rows = conn.execute(
            """SELECT * FROM master_campaign_notes
               WHERE world_id=? AND visibility IN ('all', 'selected')
               ORDER BY category, created_at ASC""",
            (world_id,),
        ).fetchall()
        conn.close()
        notes = [_row_to_campaign_note(r) for r in rows]
        visible = []
        for note in notes:
            if note.visibility == "all":
                visible.append(note)
                continue
            try:
                ids = json.loads(note.visible_to_device_ids or "[]")
            except (json.JSONDecodeError, TypeError):
                ids = []
            if device_id in ids:
                visible.append(note)
        return visible
    except Exception as e:
        logger.error(f"Errore get_notes_visible_to: {e}")
        return []


def save_replica_note(note_data: dict) -> bool:
    """
    Scrive (o aggiorna) sulla replica locale una nota condivisa — stesso
    principio di `world_repo.save_replica_member`/`save_replica_event`:
    `INSERT OR REPLACE` per id, un solo scrittore usato sia da
    `core.world_sync.apply_event_to_replica` (nuovo evento `note.share`)
    sia da `core.world_sync._finalize_join` (semina iniziale dallo
    snapshot) — mai due copie della stessa logica di scrittura.
    """
    note_id = str(note_data.get("note_id") or note_data.get("id") or "")
    if not note_id:
        return False
    visible_ids = note_data.get("visible_to_device_ids", [])
    if not isinstance(visible_ids, str):
        visible_ids = json.dumps(visible_ids)
    now = datetime.now().isoformat()
    try:
        conn = get_connection()
        existing = conn.execute(
            "SELECT created_at FROM master_campaign_notes WHERE id=?", (note_id,)
        ).fetchone()
        created_at = existing["created_at"] if existing else now
        conn.execute(
            """INSERT OR REPLACE INTO master_campaign_notes
               (id, category, name, description, status, tags, linked_npc_id,
                world_id, visibility, visible_to_device_ids, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (note_id, _s(note_data.get("category")) or "npc", _s(note_data.get("name")),
             _s(note_data.get("description")), _s(note_data.get("status")),
             _s(note_data.get("tags")), note_data.get("linked_npc_id") or None,
             _s(note_data.get("world_id")), _s(note_data.get("visibility")) or "private",
             _s(visible_ids) or "[]", created_at, note_data.get("updated_at") or now),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore save_replica_note: {e}")
        return False


def create_master_campaign_note(
    category: str,
    name: str,
    description: str = "",
    status: str = "",
    tags: str = "",
    linked_npc_id: str = "",
    world_id: str = "",
    visibility: str = "private",
    visible_to_device_ids: str = "[]",
) -> MasterCampaignNote | None:
    import uuid as _uuid
    note_id = str(_uuid.uuid4())
    now = datetime.now().isoformat()
    try:
        conn = get_connection()
        conn.execute(
            """INSERT INTO master_campaign_notes
               (id, category, name, description, status, tags, linked_npc_id,
                world_id, visibility, visible_to_device_ids, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (note_id, _s(category) or "npc", _s(name), _s(description), _s(status),
             _s(tags), linked_npc_id or None, _s(world_id),
             _s(visibility) or "private", _s(visible_to_device_ids) or "[]", now, now),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM master_campaign_notes WHERE id=?", (note_id,)
        ).fetchone()
        conn.close()
        return _row_to_campaign_note(row) if row else None
    except Exception as e:
        logger.error(f"Errore create_master_campaign_note: {e}")
        return None


def update_master_campaign_note(
    note_id: str,
    name: str,
    description: str = "",
    status: str = "",
    tags: str = "",
    linked_npc_id: str = "",
    visibility: str = "private",
    visible_to_device_ids: str = "[]",
) -> bool:
    """`world_id` non è tra i parametri modificabili: una nota non cambia
    mondo dopo la creazione (stessa scelta di design già fatta per
    `origin_character_id` sulle istanze di personaggio — l'appartenenza a un
    mondo è decisa alla nascita, non un campo editabile in un secondo
    momento)."""
    try:
        conn = get_connection()
        conn.execute(
            """UPDATE master_campaign_notes
               SET name=?, description=?, status=?, tags=?, linked_npc_id=?,
                   visibility=?, visible_to_device_ids=?, updated_at=?
               WHERE id=?""",
            (_s(name), _s(description), _s(status), _s(tags), linked_npc_id or None,
             _s(visibility) or "private", _s(visible_to_device_ids) or "[]",
             datetime.now().isoformat(), note_id),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore update_master_campaign_note: {e}")
        return False


def delete_master_campaign_note(note_id: str) -> bool:
    try:
        conn = get_connection()
        conn.execute("DELETE FROM master_campaign_notes WHERE id=?", (note_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore delete_master_campaign_note: {e}")
        return False
