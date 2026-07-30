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
        created_at=d.get("created_at", ""),
        updated_at=d.get("updated_at", ""),
    )


def get_npcs(query: str = "") -> list[MasterNpc]:
    """
    Tutti gli NPC di rubrica, ordinati per nome. `query` (opzionale) filtra
    per sottostringa case-insensitive su nome/ruolo/tag.
    """
    try:
        conn = get_connection()
        if query.strip():
            q = f"%{query.strip().lower()}%"
            rows = conn.execute(
                """SELECT * FROM master_npcs
                   WHERE lower(name) LIKE ? OR lower(role) LIKE ? OR lower(tags) LIKE ?
                   ORDER BY name""",
                (q, q, q),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM master_npcs ORDER BY name").fetchall()
        conn.close()
        return [_row_to_npc(r) for r in rows]
    except Exception as e:
        logger.error(f"Errore get_npcs: {e}")
        return []


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
) -> MasterNpc | None:
    """Crea un nuovo NPC di rubrica. Ritorna l'NPC creato, o None in caso di errore."""
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
                source_page, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                npc_id, _s(name), _s(role), _s(notes), _s(tags), int(has_stat_block),
                _s(creature_type), _s(size), _s(alignment), ac, _s(ac_note), hp_max, _s(hp_formula), _s(speed),
                str_score, dex_score, con_score, int_score, wis_score, cha_score,
                _s(saving_throws) or "{}", _s(skills) or "{}",
                _s(damage_vulnerabilities), _s(damage_resistances), _s(damage_immunities), _s(condition_immunities),
                _s(senses), _s(languages), _s(cr), int(xp or 0), _s(traits) or "[]", _s(actions) or "[]",
                _s(reactions) or "[]", _s(legendary_actions) or "[]",
                _s(source_page), now, now,
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
) -> MasterNpc | None:
    """
    Convenienza per il percorso "Nuovo dal Bestiario" (Sezione Master):
    precompila tutti i campi stat block da un dict grezzo di `monsters.json`
    (stessa forma già usata da `_save_creature()` in `combattimento_tab.py`),
    con `has_stat_block=True` e `source_page` valorizzato come citazione
    leggibile invece di un numero grezzo.
    """
    src_page = monster.get("source_page")
    source_page = f"da Bestiario: {monster.get('name', '')} (p.{src_page})" if src_page else f"da Bestiario: {monster.get('name', '')}"
    return create_npc(
        name=name_override or monster.get("name", ""),
        role=role,
        notes=notes,
        tags=tags,
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
    )


def get_encounters(include_archived: bool = False) -> list[MasterEncounter]:
    """Incontri ordinati per ultima modifica (più recenti prima)."""
    try:
        conn = get_connection()
        if include_archived:
            rows = conn.execute(
                "SELECT * FROM master_encounters ORDER BY updated_at DESC"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM master_encounters WHERE is_archived=0 ORDER BY updated_at DESC"
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


def create_encounter(name: str, notes: str = "") -> MasterEncounter | None:
    import uuid as _uuid
    enc_id = str(_uuid.uuid4())
    now = datetime.now().isoformat()
    try:
        conn = get_connection()
        conn.execute(
            """INSERT INTO master_encounters
               (id, name, notes, round_number, current_turn_index, is_archived, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (enc_id, _s(name), _s(notes), 1, 0, 0, now, now),
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
                    "SELECT name, ac, hp_current, hp_max FROM characters WHERE id=?",
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
                    })
                    continue
                # Personaggio cancellato nel frattempo — mostra comunque la riga
                out.append({
                    "member": m,
                    "name": m.display_name or "(Personaggio non trovato)",
                    "ac": m.ac, "hp_current": m.hp_current, "hp_max": m.hp_max,
                    "xp": 0,
                    "source": "character",
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
                   ac, hp_current, hp_max, xp, initiative, order_index, is_active,
                   notes, created_at, updated_at
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                member_id, encounter_id, kind,
                character_id or None, npc_id or None, _s(display_name),
                ac, hp_current, hp_max, int(xp or 0), initiative, order_index, 1,
                "", now, now,
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
    )


def get_master_campaign_notes(category: str = "") -> list[MasterCampaignNote]:
    """
    Note di campagna del Master. `category` (opzionale) filtra per categoria
    esatta; senza filtro, ordina prima per categoria poi per data di
    creazione (stesso pattern di `character_repo.get_campaign_notes`).
    """
    try:
        conn = get_connection()
        if category:
            rows = conn.execute(
                "SELECT * FROM master_campaign_notes WHERE category=? ORDER BY created_at ASC",
                (category,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM master_campaign_notes ORDER BY category, created_at ASC"
            ).fetchall()
        conn.close()
        return [_row_to_campaign_note(r) for r in rows]
    except Exception as e:
        logger.error(f"Errore get_master_campaign_notes: {e}")
        return []


def create_master_campaign_note(
    category: str,
    name: str,
    description: str = "",
    status: str = "",
    tags: str = "",
    linked_npc_id: str = "",
) -> MasterCampaignNote | None:
    import uuid as _uuid
    note_id = str(_uuid.uuid4())
    now = datetime.now().isoformat()
    try:
        conn = get_connection()
        conn.execute(
            """INSERT INTO master_campaign_notes
               (id, category, name, description, status, tags, linked_npc_id, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (note_id, _s(category) or "npc", _s(name), _s(description), _s(status),
             _s(tags), linked_npc_id or None, now, now),
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
) -> bool:
    try:
        conn = get_connection()
        conn.execute(
            """UPDATE master_campaign_notes
               SET name=?, description=?, status=?, tags=?, linked_npc_id=?, updated_at=?
               WHERE id=?""",
            (_s(name), _s(description), _s(status), _s(tags), linked_npc_id or None,
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
