"""
Repository per le operazioni CRUD sui personaggi.
Tutta la logica di accesso al DB per i personaggi è qui.
"""

import json
import logging
from datetime import datetime
from typing import Optional

from data.database import get_connection
from data.models import Character, CharacterProficiency, Currency, SpellSlot, ClassResource, CreatureEntry

logger = logging.getLogger(__name__)


def _s(value) -> str:
    """Converte None in stringa vuota per i campi TEXT NOT NULL."""
    return value if value is not None else ""


def _row_to_character(row) -> Character:
    """Converte una riga SQLite in un oggetto Character."""
    d = dict(row)
    return Character(
        id=d["id"],
        name=d["name"],
        player_name=d["player_name"],
        class_name=d["class_name"],
        subclass=d["subclass"],
        level=d["level"],
        race=d["race"],
        subrace=d["subrace"],
        background=d["background"],
        alignment=d["alignment"],
        xp=d["xp"],
        image_path=d["image_path"],
        image_data=d.get("image_data", "") or "",
        str_score=d["str_score"],
        dex_score=d["dex_score"],
        con_score=d["con_score"],
        int_score=d["int_score"],
        wis_score=d["wis_score"],
        cha_score=d["cha_score"],
        hp_max=d["hp_max"],
        hp_current=d["hp_current"],
        hp_temp=d["hp_temp"],
        ac=d["ac"],
        speed=d["speed"],
        hit_dice_type=d["hit_dice_type"],
        hit_dice_total=d["hit_dice_total"],
        hit_dice_remaining=d["hit_dice_remaining"],
        death_saves_success=d["death_saves_success"],
        death_saves_failure=d["death_saves_failure"],
        action_used=bool(d["action_used"]),
        bonus_action_used=bool(d["bonus_action_used"]),
        reaction_used=bool(d["reaction_used"]),
        movement_used=d["movement_used"],
        previous_turn_state=d["previous_turn_state"],
        spellcasting_ability=d["spellcasting_ability"],
        inspiration=bool(d["inspiration"]),
        ca_bonus=d.get("ca_bonus", 0) or 0,
        proficiency_bonus_override=d.get("proficiency_bonus_override", 0) or 0,
        session_notes=d.get("session_notes", "") or "",
        max_prepared_spells_override=d.get("max_prepared_spells_override", 0) or 0,
        dragon_ancestry=d.get("dragon_ancestry", "") or "",
        fighting_style=d.get("fighting_style", "") or "",
        totem_animal=d.get("totem_animal", "") or "",
        land_terrain=d.get("land_terrain", "") or "",
        pact_boon=d.get("pact_boon", "") or "",
        initiative_bonus=d.get("initiative_bonus", 0) or 0,
        age=d["age"],
        height=d["height"],
        weight=d["weight"],
        eyes=d["eyes"],
        skin=d["skin"],
        hair=d["hair"],
        personality_traits=d["personality_traits"],
        ideals=d["ideals"],
        bonds=d["bonds"],
        flaws=d["flaws"],
        backstory=d["backstory"],
        allies_organizations=d["allies_organizations"],
        additional_traits=d["additional_traits"],
        appearance_notes=d["appearance_notes"],
        created_at=d["created_at"],
        updated_at=d["updated_at"],
    )


def get_all() -> list[Character]:
    """Restituisce tutti i personaggi ordinati per data di aggiornamento (più recente prima)."""
    try:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM characters ORDER BY updated_at DESC"
        ).fetchall()
        conn.close()
        return [_row_to_character(r) for r in rows]
    except Exception as e:
        logger.error(f"Errore nel recupero personaggi: {e}")
        return []


def get_by_id(character_id: str) -> Optional[Character]:
    """Restituisce un personaggio per ID, None se non trovato."""
    try:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM characters WHERE id = ?", (character_id,)
        ).fetchone()
        conn.close()
        return _row_to_character(row) if row else None
    except Exception as e:
        logger.error(f"Errore nel recupero personaggio {character_id}: {e}")
        return None


def create(character: Character) -> bool:
    """
    Inserisce un nuovo personaggio e inizializza le valute e gli slot incantesimo.
    Restituisce True in caso di successo.
    """
    now = datetime.now().isoformat()
    character.created_at = now
    character.updated_at = now

    try:
        conn = get_connection()
        conn.execute("""
            INSERT INTO characters (
                id, name, player_name, class_name, subclass, level,
                race, subrace, background, alignment, xp, image_path, image_data,
                str_score, dex_score, con_score, int_score, wis_score, cha_score,
                hp_max, hp_current, hp_temp,
                ac, speed, hit_dice_type, hit_dice_total, hit_dice_remaining,
                death_saves_success, death_saves_failure,
                action_used, bonus_action_used, reaction_used,
                movement_used, previous_turn_state,
                spellcasting_ability, inspiration,
                ca_bonus, proficiency_bonus_override, session_notes,
                age, height, weight, eyes, skin, hair,
                personality_traits, ideals, bonds, flaws,
                backstory, allies_organizations, additional_traits, appearance_notes,
                created_at, updated_at
            ) VALUES (
                :id, :name, :player_name, :class_name, :subclass, :level,
                :race, :subrace, :background, :alignment, :xp, :image_path, :image_data,
                :str_score, :dex_score, :con_score, :int_score, :wis_score, :cha_score,
                :hp_max, :hp_current, :hp_temp,
                :ac, :speed, :hit_dice_type, :hit_dice_total, :hit_dice_remaining,
                :death_saves_success, :death_saves_failure,
                :action_used, :bonus_action_used, :reaction_used,
                :movement_used, :previous_turn_state,
                :spellcasting_ability, :inspiration,
                :ca_bonus, :proficiency_bonus_override, :session_notes,
                :age, :height, :weight, :eyes, :skin, :hair,
                :personality_traits, :ideals, :bonds, :flaws,
                :backstory, :allies_organizations, :additional_traits, :appearance_notes,
                :created_at, :updated_at
            )
        """, {
            "id": character.id,
            "name": _s(character.name),
            "player_name": _s(character.player_name),
            "class_name": _s(character.class_name),
            "subclass": _s(character.subclass),
            "level": character.level,
            "race": _s(character.race),
            "subrace": _s(character.subrace),
            "background": _s(character.background),
            "alignment": _s(character.alignment),
            "xp": character.xp,
            "image_path": _s(character.image_path),
            "image_data": _s(character.image_data),
            "str_score": character.str_score,
            "dex_score": character.dex_score,
            "con_score": character.con_score,
            "int_score": character.int_score,
            "wis_score": character.wis_score,
            "cha_score": character.cha_score,
            "hp_max": character.hp_max,
            "hp_current": character.hp_current,
            "hp_temp": character.hp_temp,
            "ac": character.ac,
            "speed": character.speed,
            "hit_dice_type": character.hit_dice_type,
            "hit_dice_total": character.hit_dice_total,
            "hit_dice_remaining": character.hit_dice_remaining,
            "death_saves_success": character.death_saves_success,
            "death_saves_failure": character.death_saves_failure,
            "action_used": int(character.action_used),
            "bonus_action_used": int(character.bonus_action_used),
            "reaction_used": int(character.reaction_used),
            "movement_used": character.movement_used,
            "previous_turn_state": _s(character.previous_turn_state),
            "spellcasting_ability": _s(character.spellcasting_ability),
            "inspiration": int(character.inspiration),
            "age": _s(character.age),
            "height": _s(character.height),
            "weight": _s(character.weight),
            "eyes": _s(character.eyes),
            "skin": _s(character.skin),
            "hair": _s(character.hair),
            "personality_traits": _s(character.personality_traits),
            "ideals": _s(character.ideals),
            "bonds": _s(character.bonds),
            "flaws": _s(character.flaws),
            "backstory": _s(character.backstory),
            "allies_organizations": _s(character.allies_organizations),
            "additional_traits": _s(character.additional_traits),
            "appearance_notes": _s(character.appearance_notes),
            "ca_bonus": character.ca_bonus,
            "proficiency_bonus_override": character.proficiency_bonus_override,
            "session_notes": _s(character.session_notes),
            "created_at": character.created_at,
            "updated_at": character.updated_at,
        })

        # Inizializza valute a zero
        conn.execute(
            "INSERT INTO currencies (character_id) VALUES (?)",
            (character.id,)
        )

        # Inizializza slot incantesimo (livelli 1-9 tutti a 0)
        for level in range(1, 10):
            conn.execute(
                "INSERT INTO spell_slots (character_id, slot_level, total, used) VALUES (?, ?, 0, 0)",
                (character.id, level)
            )

        conn.commit()
        conn.close()
        logger.info(f"Personaggio creato: {character.name} ({character.id})")

        # Inizializza risorse di classe
        init_class_resources(character.id, character.class_name, character.level, character)

        return True

    except Exception as e:
        logger.error(f"Errore nella creazione del personaggio: {e}")
        return False


def update(character: Character) -> bool:
    """Aggiorna tutti i campi di un personaggio esistente."""
    character.updated_at = datetime.now().isoformat()
    try:
        conn = get_connection()
        conn.execute("""
            UPDATE characters SET
                name=:name, player_name=:player_name,
                class_name=:class_name, subclass=:subclass, level=:level,
                race=:race, subrace=:subrace, background=:background,
                alignment=:alignment, xp=:xp, image_path=:image_path,
                str_score=:str_score, dex_score=:dex_score, con_score=:con_score,
                int_score=:int_score, wis_score=:wis_score, cha_score=:cha_score,
                hp_max=:hp_max, hp_current=:hp_current, hp_temp=:hp_temp,
                ac=:ac, speed=:speed,
                hit_dice_type=:hit_dice_type, hit_dice_total=:hit_dice_total,
                hit_dice_remaining=:hit_dice_remaining,
                death_saves_success=:death_saves_success,
                death_saves_failure=:death_saves_failure,
                action_used=:action_used, bonus_action_used=:bonus_action_used,
                reaction_used=:reaction_used, movement_used=:movement_used,
                previous_turn_state=:previous_turn_state,
                spellcasting_ability=:spellcasting_ability,
                inspiration=:inspiration,
                age=:age, height=:height, weight=:weight,
                eyes=:eyes, skin=:skin, hair=:hair,
                personality_traits=:personality_traits, ideals=:ideals,
                bonds=:bonds, flaws=:flaws, backstory=:backstory,
                allies_organizations=:allies_organizations,
                additional_traits=:additional_traits,
                appearance_notes=:appearance_notes,
                image_data=:image_data,
                ca_bonus=:ca_bonus,
                proficiency_bonus_override=:proficiency_bonus_override,
                session_notes=:session_notes,
                dragon_ancestry=:dragon_ancestry,
                fighting_style=:fighting_style,
                totem_animal=:totem_animal,
                land_terrain=:land_terrain,
                pact_boon=:pact_boon,
                initiative_bonus=:initiative_bonus,
                updated_at=:updated_at
            WHERE id=:id
        """, {
            "id": character.id,
            "name": _s(character.name),
            "player_name": _s(character.player_name),
            "class_name": _s(character.class_name),
            "subclass": _s(character.subclass),
            "level": character.level,
            "race": _s(character.race),
            "subrace": _s(character.subrace),
            "background": _s(character.background),
            "alignment": _s(character.alignment),
            "xp": character.xp,
            "image_path": _s(character.image_path),
            "str_score": character.str_score,
            "dex_score": character.dex_score,
            "con_score": character.con_score,
            "int_score": character.int_score,
            "wis_score": character.wis_score,
            "cha_score": character.cha_score,
            "hp_max": character.hp_max,
            "hp_current": character.hp_current,
            "hp_temp": character.hp_temp,
            "ac": character.ac,
            "speed": character.speed,
            "hit_dice_type": character.hit_dice_type,
            "hit_dice_total": character.hit_dice_total,
            "hit_dice_remaining": character.hit_dice_remaining,
            "death_saves_success": character.death_saves_success,
            "death_saves_failure": character.death_saves_failure,
            "action_used": int(character.action_used),
            "bonus_action_used": int(character.bonus_action_used),
            "reaction_used": int(character.reaction_used),
            "movement_used": character.movement_used,
            "previous_turn_state": _s(character.previous_turn_state),
            "spellcasting_ability": _s(character.spellcasting_ability),
            "inspiration": int(character.inspiration),
            "age": _s(character.age),
            "height": _s(character.height),
            "weight": _s(character.weight),
            "eyes": _s(character.eyes),
            "skin": _s(character.skin),
            "hair": _s(character.hair),
            "personality_traits": _s(character.personality_traits),
            "ideals": _s(character.ideals),
            "bonds": _s(character.bonds),
            "flaws": _s(character.flaws),
            "backstory": _s(character.backstory),
            "allies_organizations": _s(character.allies_organizations),
            "additional_traits": _s(character.additional_traits),
            "appearance_notes": _s(character.appearance_notes),
            "image_data": _s(character.image_data),
            "ca_bonus": character.ca_bonus,
            "proficiency_bonus_override": character.proficiency_bonus_override,
            "session_notes": _s(character.session_notes),
            "dragon_ancestry": _s(character.dragon_ancestry),
            "fighting_style": _s(character.fighting_style),
            "totem_animal": _s(character.totem_animal),
            "land_terrain": _s(character.land_terrain),
            "pact_boon": _s(character.pact_boon),
            "initiative_bonus": character.initiative_bonus,
            "updated_at": character.updated_at,
        })
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore nell'aggiornamento del personaggio {character.id}: {e}")
        return False


def delete(character_id: str) -> bool:
    """
    Elimina un personaggio e tutti i dati collegati (CASCADE).
    Restituisce True in caso di successo.
    """
    try:
        conn = get_connection()
        conn.execute("DELETE FROM characters WHERE id = ?", (character_id,))
        conn.commit()
        conn.close()
        logger.info(f"Personaggio eliminato: {character_id}")
        return True
    except Exception as e:
        logger.error(f"Errore nell'eliminazione del personaggio {character_id}: {e}")
        return False


def _save_single_proficiency(
    character_id: str,
    proficiency_type: str,
    name: str,
    is_expert: bool = False,
    bonus_data: str | None = None,
    level_obtained: int = 0,
) -> bool:
    """Inserisce una singola competenza (usata dal wizard e dal level-up).

    bonus_data     — JSON opzionale con i bonus applicati, es.:
                     '{"ability": {"cha": 1}, "other": {"initiative": 5}}'
    level_obtained — livello al quale la competenza/talento è stato acquisito.
                     0 = sconosciuto (wizard, house rules). Usato da undo_level.
    """
    import uuid
    try:
        conn = get_connection()
        conn.execute(
            """INSERT OR IGNORE INTO character_proficiencies
               (id, character_id, proficiency_type, name, is_expert, bonus_data, level_obtained)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (str(uuid.uuid4()), character_id, proficiency_type, name,
             int(is_expert), bonus_data, level_obtained),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore salvataggio competenza '{name}': {e}")
        return False


def undo_level(character_id: str, level_removed: int) -> bool:
    """
    Inverte tutti i bonus (feat e ASI) acquisiti al livello `level_removed`.

    Legge le righe con level_obtained == level_removed e proficiency_type in
    ('feat', 'asi_record'), quindi:
    - per ogni riga con bonus_data: applica l'inverso su characters
    - elimina le righe

    Usato da _on_level_down_click PRIMA di decrementare c.level.
    """
    try:
        conn = get_connection()

        rows = conn.execute(
            """SELECT proficiency_type, name, bonus_data
               FROM character_proficiencies
               WHERE character_id=? AND level_obtained=?
                 AND proficiency_type IN ('feat', 'asi_record')""",
            (character_id, level_removed),
        ).fetchall()

        set_parts: list[str] = []
        params: list = []

        _other_col_map = {"initiative": "initiative_bonus", "speed": "speed"}

        for row in rows:
            if not row["bonus_data"]:
                continue
            try:
                stored = json.loads(row["bonus_data"])
            except (json.JSONDecodeError, TypeError):
                continue

            for stat, val in stored.get("ability", {}).items():
                set_parts.append(f"{stat}_score = MAX(1, {stat}_score - ?)")
                params.append(val)

            for key, val in stored.get("other", {}).items():
                col = _other_col_map.get(key)
                if col:
                    floor = 1 if col == "speed" else 0
                    set_parts.append(f"{col} = MAX({floor}, {col} - ?)")
                    params.append(val)

        if set_parts:
            params.append(character_id)
            conn.execute(
                f"UPDATE characters SET {', '.join(set_parts)} WHERE id=?",
                params,
            )

        # Rimuove feat e asi_record del livello
        conn.execute(
            """DELETE FROM character_proficiencies
               WHERE character_id=? AND level_obtained=?
                 AND proficiency_type IN ('feat', 'asi_record')""",
            (character_id, level_removed),
        )

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore undo_level({level_removed}) per {character_id}: {e}")
        return False


def remove_feat_with_bonuses(character_id: str, feat_name: str) -> bool:
    """
    Rimuove un talento da character_proficiencies e inverte tutti i bonus
    registrati in bonus_data al momento del salvataggio.

    Struttura bonus_data attesa:
        {"ability": {"str": 1, "cha": 1}, "other": {"initiative": 5, "speed": 3}}

    Chiavi 'other' supportate:
        "initiative" → characters.initiative_bonus
        "speed"      → characters.speed
    """
    try:
        conn = get_connection()

        # Legge la ricevuta del talento
        row = conn.execute(
            "SELECT bonus_data FROM character_proficiencies "
            "WHERE character_id=? AND proficiency_type='feat' AND name=?",
            (character_id, feat_name),
        ).fetchone()

        if row and row["bonus_data"]:
            try:
                stored = json.loads(row["bonus_data"])
            except (json.JSONDecodeError, TypeError):
                stored = {}

            ability_changes: dict = stored.get("ability", {})
            other_changes: dict  = stored.get("other", {})

            if ability_changes or other_changes:
                # Costruisce le colonne da aggiornare
                set_parts = []
                params: list = []

                for stat, val in ability_changes.items():
                    col = f"{stat}_score"
                    set_parts.append(f"{col} = MAX(1, {col} - ?)")
                    params.append(val)

                _other_col_map = {"initiative": "initiative_bonus", "speed": "speed"}
                for key, val in other_changes.items():
                    col = _other_col_map.get(key)
                    if col:
                        if col == "speed":
                            set_parts.append(f"{col} = MAX(1, {col} - ?)")
                        else:
                            set_parts.append(f"{col} = MAX(0, {col} - ?)")
                        params.append(val)

                if set_parts:
                    params.append(character_id)
                    conn.execute(
                        f"UPDATE characters SET {', '.join(set_parts)} WHERE id=?",
                        params,
                    )

        # Elimina il talento
        conn.execute(
            "DELETE FROM character_proficiencies "
            "WHERE character_id=? AND proficiency_type='feat' AND name=?",
            (character_id, feat_name),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore rimozione talento '{feat_name}': {e}")
        return False


def replace_proficiencies_by_types(
    character_id: str,
    proficiency_type: str,
    entries: list[tuple[str, bool]],
) -> bool:
    """
    Sostituisce in una transazione tutte le competenze di un tipo specifico
    (es. "save" oppure "skill") con il nuovo set fornito.
    Usato dalla dialog di modifica manuale competenze in ProfiloTab.
    """
    import uuid
    try:
        conn = get_connection()
        conn.execute(
            "DELETE FROM character_proficiencies WHERE character_id=? AND proficiency_type=?",
            (character_id, proficiency_type),
        )
        for name, is_expert in entries:
            conn.execute(
                """INSERT INTO character_proficiencies
                   (id, character_id, proficiency_type, name, is_expert)
                   VALUES (?, ?, ?, ?, ?)""",
                (str(uuid.uuid4()), character_id, proficiency_type, name, int(is_expert)),
            )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore replace_proficiencies_by_types ({proficiency_type}): {e}")
        return False


def set_expertise(character_id: str, skill_names: list[str]) -> bool:
    """
    Imposta is_expert=True sulle competenze di tipo 'skill' o 'tool'
    il cui name è in skill_names. Non rimuove expertise esistenti.
    """
    if not skill_names:
        return True
    try:
        conn = get_connection()
        for name in skill_names:
            conn.execute(
                """UPDATE character_proficiencies
                   SET is_expert = 1
                   WHERE character_id = ? AND name = ?
                     AND proficiency_type IN ('skill', 'tool')""",
                (character_id, name),
            )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore set_expertise {character_id}: {e}")
        return False


def get_proficiencies(character_id: str) -> list[CharacterProficiency]:
    """Restituisce tutte le competenze di un personaggio."""
    try:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM character_proficiencies WHERE character_id = ?",
            (character_id,)
        ).fetchall()
        conn.close()
        return [
            CharacterProficiency(
                id=r["id"],
                character_id=r["character_id"],
                proficiency_type=r["proficiency_type"],
                name=r["name"],
                is_expert=bool(r["is_expert"]),
            )
            for r in rows
        ]
    except Exception as e:
        logger.error(f"Errore nel recupero competenze {character_id}: {e}")
        return []


def update_hp(character_id: str, hp_current: int, hp_temp: int | None = None) -> bool:
    """Aggiornamento rapido degli HP senza ricaricare tutto il personaggio."""
    try:
        conn = get_connection()
        if hp_temp is not None:
            conn.execute(
                "UPDATE characters SET hp_current=?, hp_temp=?, updated_at=? WHERE id=?",
                (hp_current, hp_temp, datetime.now().isoformat(), character_id)
            )
        else:
            conn.execute(
                "UPDATE characters SET hp_current=?, updated_at=? WHERE id=?",
                (hp_current, datetime.now().isoformat(), character_id)
            )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore aggiornamento HP: {e}")
        return False


def get_spell_slots(character_id: str) -> list[SpellSlot]:
    """Restituisce i 9 slot incantesimo del personaggio (livelli 1-9)."""
    try:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM spell_slots WHERE character_id = ? ORDER BY slot_level",
            (character_id,)
        ).fetchall()
        conn.close()
        return [
            SpellSlot(
                character_id=r["character_id"],
                slot_level=r["slot_level"],
                total=r["total"],
                used=r["used"],
            )
            for r in rows
        ]
    except Exception as e:
        logger.error(f"Errore recupero slot incantesimo {character_id}: {e}")
        return []


def reset_all_spell_slots(character_id: str) -> bool:
    """
    Ripristina tutti gli slot incantesimo (used=0).
    Usato dal riposo lungo (tutte le classi) e dal riposo breve (Warlock — Patto della Magia PHB p.107).
    """
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE spell_slots SET used=0 WHERE character_id=?",
            (character_id,)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore reset slot per {character_id}: {e}")
        return False


def update_spell_slot(character_id: str, slot_level: int, used: int) -> bool:
    """Aggiorna il contatore 'used' di uno slot incantesimo."""
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE spell_slots SET used=? WHERE character_id=? AND slot_level=?",
            (used, character_id, slot_level)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore aggiornamento slot Lv.{slot_level}: {e}")
        return False


# ---------------------------------------------------------------------------
# Tabella PHB slot incantesimo per livello di personaggio
# Indice 0 = Lv 1, indice 19 = Lv 20. Ogni lista: [1°,2°,3°,...,9°]
# ---------------------------------------------------------------------------
_FULL_CASTER_SLOTS = [
    [2,0,0,0,0,0,0,0,0], [3,0,0,0,0,0,0,0,0], [4,2,0,0,0,0,0,0,0],
    [4,3,0,0,0,0,0,0,0], [4,3,2,0,0,0,0,0,0], [4,3,3,0,0,0,0,0,0],
    [4,3,3,1,0,0,0,0,0], [4,3,3,2,0,0,0,0,0], [4,3,3,3,1,0,0,0,0],
    [4,3,3,3,2,0,0,0,0], [4,3,3,3,2,1,0,0,0], [4,3,3,3,2,1,0,0,0],
    [4,3,3,3,2,1,1,0,0], [4,3,3,3,2,1,1,0,0], [4,3,3,3,2,1,1,1,0],
    [4,3,3,3,2,1,1,1,0], [4,3,3,3,2,1,1,1,1], [4,3,3,3,3,1,1,1,1],
    [4,3,3,3,3,2,1,1,1], [4,3,3,3,3,2,2,1,1],
]
_HALF_CASTER_SLOTS = [
    [0,0,0,0,0,0,0,0,0], [2,0,0,0,0,0,0,0,0], [3,0,0,0,0,0,0,0,0],
    [3,0,0,0,0,0,0,0,0], [4,2,0,0,0,0,0,0,0], [4,2,0,0,0,0,0,0,0],
    [4,3,0,0,0,0,0,0,0], [4,3,0,0,0,0,0,0,0], [4,3,2,0,0,0,0,0,0],
    [4,3,2,0,0,0,0,0,0], [4,3,3,0,0,0,0,0,0], [4,3,3,0,0,0,0,0,0],
    [4,3,3,1,0,0,0,0,0], [4,3,3,1,0,0,0,0,0], [4,3,3,2,0,0,0,0,0],
    [4,3,3,2,0,0,0,0,0], [4,3,3,3,1,0,0,0,0], [4,3,3,3,1,0,0,0,0],
    [4,3,3,3,2,0,0,0,0], [4,3,3,3,2,0,0,0,0],
]
# Warlock — Magia del Patto (PHB p.107): tutti gli slot allo stesso livello,
# ripristinati a riposo breve O lungo. Formato: [Lv1, Lv2, Lv3, Lv4, Lv5, 0,0,0,0]
# (gli altri livelli sono sempre 0 per il warlock)
_WARLOCK_SLOTS = [
    [1,0,0,0,0,0,0,0,0],  # Lv 1:  1 slot Lv1
    [2,0,0,0,0,0,0,0,0],  # Lv 2:  2 slot Lv1
    [0,2,0,0,0,0,0,0,0],  # Lv 3:  2 slot Lv2
    [0,2,0,0,0,0,0,0,0],  # Lv 4:  2 slot Lv2
    [0,0,2,0,0,0,0,0,0],  # Lv 5:  2 slot Lv3
    [0,0,2,0,0,0,0,0,0],  # Lv 6:  2 slot Lv3
    [0,0,0,2,0,0,0,0,0],  # Lv 7:  2 slot Lv4
    [0,0,0,2,0,0,0,0,0],  # Lv 8:  2 slot Lv4
    [0,0,0,0,2,0,0,0,0],  # Lv 9:  2 slot Lv5
    [0,0,0,0,2,0,0,0,0],  # Lv10:  2 slot Lv5
    [0,0,0,0,3,0,0,0,0],  # Lv11:  3 slot Lv5
    [0,0,0,0,3,0,0,0,0],  # Lv12:  3 slot Lv5
    [0,0,0,0,3,0,0,0,0],  # Lv13:  3 slot Lv5
    [0,0,0,0,3,0,0,0,0],  # Lv14:  3 slot Lv5
    [0,0,0,0,3,0,0,0,0],  # Lv15:  3 slot Lv5
    [0,0,0,0,3,0,0,0,0],  # Lv16:  3 slot Lv5
    [0,0,0,0,4,0,0,0,0],  # Lv17:  4 slot Lv5
    [0,0,0,0,4,0,0,0,0],  # Lv18:  4 slot Lv5
    [0,0,0,0,4,0,0,0,0],  # Lv19:  4 slot Lv5
    [0,0,0,0,4,0,0,0,0],  # Lv20:  4 slot Lv5
]
_FULL_CASTERS   = {"bardo","chierico","druido","mago","stregone"}
_HALF_CASTERS   = {"paladino","ranger"}
_PACT_CASTERS   = {"warlock"}


def auto_init_spell_slots(character_id: str, class_name: str, level: int) -> bool:
    """
    Aggiorna i totali slot incantesimo in base a classe e livello PHB.
    Sicuro da chiamare ad ogni level-up: aggiorna total e clamppa used al nuovo total.
    Per il Warlock (Patto della Magia) azzera i livelli non più attivi quando il
    livello degli slot aumenta (es. da Lv2 a Lv3: slot Lv1→0, slot Lv2→2).
    """
    key = class_name.strip().lower()
    if key in _FULL_CASTERS:
        table = _FULL_CASTER_SLOTS
    elif key in _HALF_CASTERS:
        table = _HALF_CASTER_SLOTS
    elif key in _PACT_CASTERS:
        table = _WARLOCK_SLOTS
    else:
        return False  # Classe non incantatore o non gestita

    lv_idx = max(0, min(level - 1, 19))
    slots = table[lv_idx]
    try:
        conn = get_connection()
        for slot_lv, total in enumerate(slots, start=1):
            conn.execute(
                "UPDATE spell_slots SET total=?, used=MIN(used,?) "
                "WHERE character_id=? AND slot_level=?",
                (total, total, character_id, slot_lv),
            )
        conn.commit()
        conn.close()
        logger.info("Slot auto-init: %s Lv%d → %s", class_name, level, slots)
        return True
    except Exception as e:
        logger.error(f"Errore auto_init_spell_slots {character_id}: {e}")
        return False


def update_spell_slot_total(character_id: str, slot_level: int, total: int) -> bool:
    """
    Aggiorna il totale massimo di uno slot incantesimo.
    Se il nuovo totale è inferiore all'usato corrente, riduce anche 'used'.
    """
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE spell_slots SET total=?, used=MIN(used, ?) WHERE character_id=? AND slot_level=?",
            (total, total, character_id, slot_level)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore aggiornamento totale slot Lv.{slot_level}: {e}")
        return False


def update_death_saves(character_id: str, success: int, failure: int) -> bool:
    """Aggiorna i tiri salvezza contro morte."""
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE characters SET death_saves_success=?, death_saves_failure=?, updated_at=? WHERE id=?",
            (success, failure, datetime.now().isoformat(), character_id)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore aggiornamento death saves: {e}")
        return False


def update_hit_dice(character_id: str, remaining: int) -> bool:
    """Aggiorna il contatore di dadi vita rimanenti."""
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE characters SET hit_dice_remaining=?, updated_at=? WHERE id=?",
            (remaining, datetime.now().isoformat(), character_id)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore aggiornamento dadi vita: {e}")
        return False


def get_weapons(character_id: str, equipped_only: bool = True) -> list:
    """Restituisce le armi del personaggio (di default solo quelle equipaggiate)."""
    from data.models import Weapon
    try:
        conn = get_connection()
        q = "SELECT * FROM weapons WHERE character_id=?"
        params: tuple = (character_id,)
        if equipped_only:
            q += " AND is_equipped=1"
        q += " ORDER BY rowid"
        rows = conn.execute(q, params).fetchall()
        conn.close()
        return [
            Weapon(
                id=r["id"],
                character_id=r["character_id"],
                name=r["name"],
                damage_dice=r["damage_dice"],
                damage_type=r["damage_type"],
                attack_bonus=r["attack_bonus"],
                damage_bonus=r["damage_bonus"],
                properties=r["properties"],
                is_magical=bool(r["is_magical"]),
                magic_description=r["magic_description"] or "",
                is_equipped=bool(r["is_equipped"]),
                range_normal=r["range_normal"] or 0,
                range_max=r["range_max"] or 0,
                magic_damages=r["magic_damages"] or "[]",
            )
            for r in rows
        ]
    except Exception as e:
        logger.error(f"Errore recupero armi {character_id}: {e}")
        return []


def get_prepared_spells(character_id: str) -> list:
    """Restituisce gli incantesimi preparati (is_prepared=True), ordinati per livello."""
    from data.models import KnownSpell
    try:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM known_spells WHERE character_id=? AND is_prepared=1 ORDER BY spell_level, name",
            (character_id,)
        ).fetchall()
        conn.close()
        return [
            KnownSpell(
                id=r["id"],
                character_id=r["character_id"],
                name=r["name"],
                spell_level=r["spell_level"],
                is_prepared=True,
                school=r["school"] or "",
                casting_time=r["casting_time"] or "",
                spell_range=r["spell_range"] or "",
                components=r["components"] or "",
                duration=r["duration"] or "",
                description=r["description"] or "",
                higher_levels=r["higher_levels"] or "",
                class_list=r["class_list"] or "",
            )
            for r in rows
        ]
    except Exception as e:
        logger.error(f"Errore recupero incantesimi preparati {character_id}: {e}")
        return []


def get_known_spells(character_id: str) -> list:
    """Restituisce tutti gli incantesimi in known_spells (preparati e non)."""
    from data.models import KnownSpell
    try:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM known_spells WHERE character_id=? ORDER BY spell_level, name",
            (character_id,)
        ).fetchall()
        conn.close()
        return [
            KnownSpell(
                id=r["id"], character_id=r["character_id"], name=r["name"],
                spell_level=r["spell_level"], is_prepared=bool(r["is_prepared"]),
                school=r["school"] or "", casting_time=r["casting_time"] or "",
                spell_range=r["spell_range"] or "", components=r["components"] or "",
                duration=r["duration"] or "", description=r["description"] or "",
                higher_levels=r["higher_levels"] or "", class_list=r["class_list"] or "",
            )
            for r in rows
        ]
    except Exception as e:
        logger.error(f"Errore get_known_spells {character_id}: {e}")
        return []


def upsert_known_spell(
    character_id: str,
    name: str,
    level: int,
    is_prepared: bool,
    school: str = "",
    casting_time: str = "",
    spell_range: str = "",
    components: str = "",
    duration: str = "",
    description: str = "",
    higher_levels: str = "",
    class_list: str = "",
) -> bool:
    """
    Inserisce o aggiorna un incantesimo in known_spells.
    Identifica la riga per (character_id, name, spell_level).
    """
    import uuid as _uuid
    try:
        conn = get_connection()
        existing = conn.execute(
            "SELECT id FROM known_spells WHERE character_id=? AND name=? AND spell_level=?",
            (character_id, name, level),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE known_spells SET is_prepared=?, school=?, casting_time=?, "
                "spell_range=?, components=?, duration=?, description=?, higher_levels=?, "
                "class_list=? WHERE id=?",
                (int(is_prepared), school, casting_time, spell_range, components,
                 duration, description, higher_levels, class_list, existing["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO known_spells (id, character_id, name, spell_level, is_prepared, "
                "school, casting_time, spell_range, components, duration, description, "
                "higher_levels, class_list) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (str(_uuid.uuid4()), character_id, name, level, int(is_prepared),
                 school, casting_time, spell_range, components, duration, description,
                 higher_levels, class_list),
            )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore upsert_known_spell {character_id}/{name}: {e}")
        return False


def remove_known_spell(character_id: str, name: str, level: int) -> bool:
    """Rimuove un incantesimo dalla tabella known_spells."""
    try:
        conn = get_connection()
        conn.execute(
            "DELETE FROM known_spells WHERE character_id=? AND name=? AND spell_level=?",
            (character_id, name, level),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore remove_known_spell {character_id}/{name}: {e}")
        return False


def get_inventory(character_id: str) -> list:
    """Restituisce tutti gli oggetti in inventario del personaggio."""
    from data.models import InventoryItem
    try:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM inventory_items WHERE character_id=? ORDER BY rowid",
            (character_id,)
        ).fetchall()
        conn.close()
        return [
            InventoryItem(
                id=r["id"],
                character_id=r["character_id"],
                name=r["name"],
                quantity=r["quantity"],
                weight=r["weight"],
                description=r["description"] or "",
                category=r["category"] or "misc",
                is_equipped=bool(r["is_equipped"]),
                ca_value=r["ca_value"] or 0,
                armor_type=r["armor_type"] or "",
                effects=r["effects"] or "",
            )
            for r in rows
        ]
    except Exception as e:
        logger.error(f"Errore recupero inventario {character_id}: {e}")
        return []


def create_weapon(character_id: str, name: str, damage_dice: str = "",
                  damage_type: str = "", attack_bonus: int = 0,
                  damage_bonus: int = 0, properties: str = "",
                  is_equipped: bool = True, is_magical: bool = False,
                  magic_description: str = "", range_normal: int = 0,
                  range_max: int = 0, magic_damages: str = "[]") -> bool:
    """Crea una nuova arma per il personaggio."""
    import uuid as _uuid
    try:
        conn = get_connection()
        conn.execute(
            """INSERT INTO weapons
               (id, character_id, name, damage_dice, damage_type, attack_bonus,
                damage_bonus, properties, is_magical, magic_description,
                is_equipped, range_normal, range_max, magic_damages)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (str(_uuid.uuid4()), character_id, name, damage_dice, damage_type,
             attack_bonus, damage_bonus, properties, int(is_magical),
             magic_description, int(is_equipped), range_normal, range_max, magic_damages)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore creazione arma: {e}")
        return False


def update_weapon(weapon_id: str, name: str, damage_dice: str, damage_type: str,
                  attack_bonus: int, damage_bonus: int, properties: str,
                  is_equipped: bool, is_magical: bool, magic_description: str,
                  range_normal: int, range_max: int,
                  magic_damages: str = "[]") -> bool:
    """Aggiorna un'arma esistente."""
    try:
        conn = get_connection()
        conn.execute(
            """UPDATE weapons SET name=?, damage_dice=?, damage_type=?,
               attack_bonus=?, damage_bonus=?, properties=?, is_equipped=?,
               is_magical=?, magic_description=?, range_normal=?, range_max=?,
               magic_damages=?
               WHERE id=?""",
            (name, damage_dice, damage_type, attack_bonus, damage_bonus,
             properties, int(is_equipped), int(is_magical), magic_description,
             range_normal, range_max, magic_damages, weapon_id)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore aggiornamento arma {weapon_id}: {e}")
        return False


def delete_weapon(weapon_id: str) -> bool:
    """Elimina un'arma."""
    try:
        conn = get_connection()
        conn.execute("DELETE FROM weapons WHERE id=?", (weapon_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore eliminazione arma {weapon_id}: {e}")
        return False


def create_inventory_item(character_id: str, name: str, quantity: int = 1,
                          weight: float = 0.0, description: str = "",
                          category: str = "misc", is_equipped: bool = False,
                          ca_value: int = 0, armor_type: str = "",
                          effects: str = "") -> bool:
    """Crea un nuovo oggetto nell'inventario."""
    import uuid as _uuid
    try:
        conn = get_connection()
        conn.execute(
            """INSERT INTO inventory_items
               (id, character_id, name, quantity, weight, description,
                category, is_equipped, ca_value, armor_type, effects)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (str(_uuid.uuid4()), character_id, name, quantity, weight,
             description, category, int(is_equipped), ca_value, armor_type, effects)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore creazione oggetto inventario: {e}")
        return False


def update_inventory_item(item_id: str, name: str, quantity: int, weight: float,
                          description: str, category: str, is_equipped: bool,
                          ca_value: int = 0, armor_type: str = "",
                          effects: str = "") -> bool:
    """Aggiorna un oggetto dell'inventario."""
    try:
        conn = get_connection()
        conn.execute(
            """UPDATE inventory_items SET name=?, quantity=?, weight=?,
               description=?, category=?, is_equipped=?,
               ca_value=?, armor_type=?, effects=? WHERE id=?""",
            (name, quantity, weight, description, category, int(is_equipped),
             ca_value, armor_type, effects, item_id)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore aggiornamento oggetto {item_id}: {e}")
        return False


def delete_inventory_item(item_id: str) -> bool:
    """Elimina un oggetto dall'inventario."""
    try:
        conn = get_connection()
        conn.execute("DELETE FROM inventory_items WHERE id=?", (item_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore eliminazione oggetto {item_id}: {e}")
        return False


def get_currencies(character_id: str) -> "Currency | None":
    """Restituisce le monete del personaggio, None se non trovate."""
    from data.models import Currency
    try:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM currencies WHERE character_id=?", (character_id,)
        ).fetchone()
        conn.close()
        if row:
            return Currency(
                character_id=row["character_id"],
                copper=row["copper"],
                silver=row["silver"],
                electrum=row["electrum"],
                gold=row["gold"],
                platinum=row["platinum"],
            )
        return None
    except Exception as e:
        logger.error(f"Errore recupero valute {character_id}: {e}")
        return None


def update_currencies(character_id: str, copper: int, silver: int,
                      electrum: int, gold: int, platinum: int) -> bool:
    """Aggiorna le monete del personaggio."""
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE currencies SET copper=?, silver=?, electrum=?, gold=?, platinum=? WHERE character_id=?",
            (copper, silver, electrum, gold, platinum, character_id)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore aggiornamento valute {character_id}: {e}")
        return False


def get_diary_entries(character_id: str) -> list:
    """Restituisce le voci di diario ordinate per data di creazione (più recente prima)."""
    from data.models import DiaryEntry
    try:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM diary_entries WHERE character_id=? ORDER BY created_at DESC",
            (character_id,)
        ).fetchall()
        conn.close()
        return [
            DiaryEntry(
                id=r["id"],
                character_id=r["character_id"],
                title=r["title"] or "",
                content=r["content"] or "",
                session_date=r["session_date"] or "",
                created_at=r["created_at"] or "",
                updated_at=r["updated_at"] or "",
            )
            for r in rows
        ]
    except Exception as e:
        logger.error(f"Errore recupero diario {character_id}: {e}")
        return []


def create_diary_entry(character_id: str, title: str, content: str,
                       session_date: str = "") -> bool:
    """Crea una nuova voce di diario."""
    import uuid as _uuid
    now = datetime.now().isoformat()
    try:
        conn = get_connection()
        conn.execute(
            """INSERT INTO diary_entries
               (id, character_id, title, content, session_date, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (str(_uuid.uuid4()), character_id, title, content, session_date, now, now)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore creazione voce diario: {e}")
        return False


def update_diary_entry(entry_id: str, title: str, content: str,
                       session_date: str = "") -> bool:
    """Aggiorna una voce di diario esistente."""
    now = datetime.now().isoformat()
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE diary_entries SET title=?, content=?, session_date=?, updated_at=? WHERE id=?",
            (title, content, session_date, now, entry_id)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore aggiornamento voce diario: {e}")
        return False


def delete_diary_entry(entry_id: str) -> bool:
    """Elimina una voce di diario."""
    try:
        conn = get_connection()
        conn.execute("DELETE FROM diary_entries WHERE id=?", (entry_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore eliminazione voce diario: {e}")
        return False


# ---------------------------------------------------------------------------
# Note di Campagna (PNG, Luoghi, Missioni, Fazioni)
# ---------------------------------------------------------------------------

def get_campaign_notes(character_id: str,
                       category: str | None = None) -> list:
    """
    Restituisce le note di campagna del personaggio.
    Se category è specificato, filtra per categoria.
    Ordine: created_at ASC (cronologico).
    """
    from data.models import CampaignNote
    try:
        conn = get_connection()
        if category:
            rows = conn.execute(
                "SELECT * FROM campaign_notes WHERE character_id=? AND category=?"
                " ORDER BY created_at ASC",
                (character_id, category)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM campaign_notes WHERE character_id=?"
                " ORDER BY category, created_at ASC",
                (character_id,)
            ).fetchall()
        conn.close()
        return [
            CampaignNote(
                id=r["id"],
                character_id=r["character_id"],
                category=r["category"],
                name=r["name"],
                description=r["description"] or "",
                status=r["status"] or "",
                tags=r["tags"] or "",
                created_at=r["created_at"] or "",
                updated_at=r["updated_at"] or "",
            )
            for r in rows
        ]
    except Exception as e:
        logger.error(f"Errore recupero campaign_notes {character_id}: {e}")
        return []


def create_campaign_note(character_id: str, category: str, name: str,
                          description: str = "", status: str = "",
                          tags: str = "") -> bool:
    """Crea una nuova nota di campagna."""
    import uuid as _uuid
    now = datetime.now().isoformat()
    try:
        conn = get_connection()
        conn.execute(
            """INSERT INTO campaign_notes
               (id, character_id, category, name, description, status, tags,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (str(_uuid.uuid4()), character_id, category, name,
             description, status, tags, now, now)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore creazione campaign_note: {e}")
        return False


def update_campaign_note(note_id: str, name: str, description: str,
                          status: str, tags: str) -> bool:
    """Aggiorna una nota di campagna esistente."""
    now = datetime.now().isoformat()
    try:
        conn = get_connection()
        conn.execute(
            """UPDATE campaign_notes
               SET name=?, description=?, status=?, tags=?, updated_at=?
               WHERE id=?""",
            (name, description, status, tags, now, note_id)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore aggiornamento campaign_note {note_id}: {e}")
        return False


def delete_campaign_note(note_id: str) -> bool:
    """Elimina una nota di campagna."""
    try:
        conn = get_connection()
        conn.execute("DELETE FROM campaign_notes WHERE id=?", (note_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore eliminazione campaign_note {note_id}: {e}")
        return False


def update_ca_bonus(character_id: str, ca_bonus: int) -> bool:
    """Aggiorna il bonus CA temporaneo (da incantesimi, reazioni, ecc.)."""
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE characters SET ca_bonus=?, updated_at=? WHERE id=?",
            (ca_bonus, datetime.now().isoformat(), character_id)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore aggiornamento CA bonus: {e}")
        return False


def update_max_prepared_override(character_id: str, value: int) -> bool:
    """Salva l'override manuale del massimo incantesimi preparabili (0 = usa formula PHB)."""
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE characters SET max_prepared_spells_override=?, updated_at=? WHERE id=?",
            (value, datetime.now().isoformat(), character_id),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore update_max_prepared_override: {e}")
        return False


def update_session_notes(character_id: str, notes: str) -> bool:
    """Aggiorna gli appunti di sessione del personaggio."""
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE characters SET session_notes=?, updated_at=? WHERE id=?",
            (notes, datetime.now().isoformat(), character_id)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore aggiornamento note sessione: {e}")
        return False


def calculate_and_update_ca(character_id: str) -> int:
    """
    Ricalcola la CA del personaggio in base all'armatura e agli scudi equipaggiati.

    Logica PHB:
      - Nessuna armatura  → 10 + mod DES
      - Armatura leggera  → ca_value + mod DES
      - Armatura media    → ca_value + min(mod DES, 2)
      - Armatura pesante  → ca_value  (DES ignorato)
      - Scudo             → somma i ca_value di tutti gli scudi equipaggiati

    Aggiorna il campo `ac` nel DB e restituisce il nuovo valore.
    """
    from config.settings import get_modifier
    try:
        char = get_by_id(character_id)
        if not char:
            return 10
        dex_mod = get_modifier(char.dex_score)

        items = get_inventory(character_id)
        equipped_armor = [i for i in items
                          if i.is_equipped and i.category == "armor"
                          and i.armor_type in ("leggera", "media", "pesante")]
        equipped_shields = [i for i in items
                            if i.is_equipped and i.category == "armor"
                            and i.armor_type == "scudo"]

        if equipped_armor:
            armor = equipped_armor[0]  # si indossa una sola armatura alla volta
            if armor.armor_type == "leggera":
                base_ca = armor.ca_value + dex_mod
            elif armor.armor_type == "media":
                base_ca = armor.ca_value + min(dex_mod, 2)
            else:  # pesante
                base_ca = armor.ca_value
        else:
            base_ca = 10 + dex_mod  # senza armatura

        shield_ca = sum(s.ca_value for s in equipped_shields)
        new_ca = base_ca + shield_ca

        conn = get_connection()
        conn.execute(
            "UPDATE characters SET ac=?, updated_at=? WHERE id=?",
            (new_ca, datetime.now().isoformat(), character_id)
        )
        conn.commit()
        conn.close()
        logger.info(f"CA aggiornata: {new_ca} (armatura={base_ca}, scudo={shield_ca})")
        return new_ca
    except Exception as e:
        logger.error(f"Errore calcolo CA: {e}")
        return 10


# ---------------------------------------------------------------------------
# Risorse di classe
# ---------------------------------------------------------------------------

def get_class_resources(character_id: str) -> list[ClassResource]:
    """Restituisce tutte le risorse di classe del personaggio."""
    try:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM class_resources WHERE character_id=? ORDER BY rowid",
            (character_id,)
        ).fetchall()
        conn.close()
        return [
            ClassResource(
                id=r["id"],
                character_id=r["character_id"],
                name=r["name"],
                max_value=r["max_value"],
                current_value=r["current_value"],
                reset_on=r["reset_on"],
                display_type=r["display_type"],
            )
            for r in rows
        ]
    except Exception as e:
        logger.error(f"Errore recupero risorse di classe {character_id}: {e}")
        return []


def update_class_resource(resource_id: str, current_value: int) -> bool:
    """Aggiorna il valore corrente di una risorsa di classe."""
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE class_resources SET current_value=? WHERE id=?",
            (current_value, resource_id)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore aggiornamento risorsa {resource_id}: {e}")
        return False


def reset_class_resources(character_id: str, reset_on: str) -> bool:
    """
    Ripristina current_value = max_value per tutte le risorse con il reset_on indicato.
    Usato da riposo breve (reset_on='short_rest') e riposo lungo (chiamare due volte).
    """
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE class_resources SET current_value=max_value WHERE character_id=? AND reset_on=?",
            (character_id, reset_on)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore reset risorse {reset_on} per {character_id}: {e}")
        return False


def init_class_resources(
    character_id: str,
    class_name: str,
    level: int,
    character=None,
) -> bool:
    """
    Inizializza o aggiorna le risorse di classe E razziali dopo creazione o level-up.

    Strategia merge:
      - Risorse presenti in defaults ma non nel DB → create con current=max.
      - Risorse presenti nel DB e in defaults → max_value aggiornato;
        current_value = min(current_value, nuovo_max).
      - Risorse nel DB ma non più nei defaults → eliminate.
    """
    import uuid as _uuid
    from config.settings import get_class_resource_defaults, get_race_resource_defaults
    try:
        # Risorse di classe
        defaults = get_class_resource_defaults(class_name, level, character)

        # Risorse razziali (aggiunte allo stesso pool)
        race_name  = getattr(character, "race",    "") or "" if character else ""
        subrace    = getattr(character, "subrace", "") or "" if character else ""
        race_defaults = get_race_resource_defaults(race_name, subrace, level)
        defaults = defaults + race_defaults

        existing = {r.name: r for r in get_class_resources(character_id)}
        default_names = {d["name"] for d in defaults}

        conn = get_connection()

        # Rimuovi risorse non più applicabili
        for name, res in existing.items():
            if name not in default_names:
                conn.execute("DELETE FROM class_resources WHERE id=?", (res.id,))
                logger.info(f"Rimossa risorsa obsoleta '{name}' per {character_id}")

        # Crea o aggiorna
        for d in defaults:
            if d["name"] in existing:
                ex = existing[d["name"]]
                new_current = min(ex.current_value, d["max_value"])
                conn.execute(
                    """UPDATE class_resources
                       SET max_value=?, current_value=?, reset_on=?, display_type=?
                       WHERE id=?""",
                    (d["max_value"], new_current, d["reset_on"], d["display_type"], ex.id)
                )
            else:
                conn.execute(
                    """INSERT INTO class_resources
                       (id, character_id, name, max_value, current_value, reset_on, display_type)
                       VALUES (?,?,?,?,?,?,?)""",
                    (str(_uuid.uuid4()), character_id,
                     d["name"], d["max_value"], d["current_value"],
                     d["reset_on"], d["display_type"])
                )

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore init_class_resources ({class_name} lv{level}): {e}")
        return False


# ---------------------------------------------------------------------------
# Creature Entries (Forme Selvatiche e Evocazioni)
# ---------------------------------------------------------------------------

def _row_to_creature(row) -> CreatureEntry:
    """Converte una riga SQLite in CreatureEntry."""
    from data.models import CreatureEntry
    d = dict(row)
    return CreatureEntry(
        id=d["id"],
        character_id=d["character_id"],
        entry_type=d["entry_type"],
        name=d["name"],
        creature_type=d.get("creature_type", ""),
        alignment=d.get("alignment", ""),
        cr=d.get("cr", ""),
        ac=d.get("ac", 10),
        ac_note=d.get("ac_note", ""),
        hp_max=d.get("hp_max", 1),
        hp_formula=d.get("hp_formula", ""),
        hp_current=d.get("hp_current", 1),
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
        traits=d.get("traits", "[]"),
        actions=d.get("actions", "[]"),
        legendary_actions=d.get("legendary_actions", "[]"),
        is_active=bool(d.get("is_active", 0)),
        notes=d.get("notes", ""),
        source_page=d.get("source_page", 0),
        created_at=d.get("created_at", ""),
        updated_at=d.get("updated_at", ""),
    )


def get_creature_entries(
    character_id: str,
    entry_type: str | None = None,
    active_only: bool = False,
) -> list[CreatureEntry]:
    """
    Restituisce le creature del personaggio.
    entry_type = "forma" | "evocazione" | None (tutte).
    active_only = True → solo quelle is_active=1.
    """
    try:
        conn = get_connection()
        clauses = ["character_id=?"]
        params: list = [character_id]
        if entry_type:
            clauses.append("entry_type=?")
            params.append(entry_type)
        if active_only:
            clauses.append("is_active=1")
        rows = conn.execute(
            f"SELECT * FROM creature_entries WHERE {' AND '.join(clauses)} ORDER BY name",
            params,
        ).fetchall()
        conn.close()
        return [_row_to_creature(r) for r in rows]
    except Exception as e:
        logger.error(f"Errore get_creature_entries: {e}")
        return []


def create_creature_entry(
    character_id: str,
    entry_type: str,
    name: str,
    creature_type: str = "",
    alignment: str = "",
    cr: str = "",
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
    traits: str = "[]",
    actions: str = "[]",
    legendary_actions: str = "[]",
    notes: str = "",
    source_page: int = 0,
) -> CreatureEntry | None:
    """
    Crea una nuova voce bestiary per il personaggio.
    Ritorna la `CreatureEntry` creata, o None in caso di errore.
    """
    import uuid as _uuid
    entry_id = str(_uuid.uuid4())
    now = datetime.now().isoformat()
    try:
        conn = get_connection()
        conn.execute("""
            INSERT INTO creature_entries (
                id, character_id, entry_type, name, creature_type, alignment, cr,
                ac, ac_note, hp_max, hp_formula, hp_current, speed,
                str_score, dex_score, con_score, int_score, wis_score, cha_score,
                saving_throws, skills,
                damage_vulnerabilities, damage_resistances, damage_immunities, condition_immunities,
                senses, languages, traits, actions, legendary_actions,
                is_active, notes, source_page, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            entry_id, character_id, entry_type, name, creature_type, alignment, cr,
            ac, ac_note, hp_max, hp_formula, hp_max,  # hp_current = hp_max inizialmente
            speed, str_score, dex_score, con_score, int_score, wis_score, cha_score,
            saving_throws, skills,
            damage_vulnerabilities, damage_resistances, damage_immunities, condition_immunities,
            senses, languages, traits, actions, legendary_actions,
            0, notes, source_page, now, now,
        ))
        conn.commit()
        row = conn.execute("SELECT * FROM creature_entries WHERE id=?", (entry_id,)).fetchone()
        conn.close()
        return _row_to_creature(row) if row else None
    except Exception as e:
        logger.error(f"Errore create_creature_entry: {e}")
        return None


def update_creature_hp(creature_id: str, hp_current: int) -> bool:
    """Aggiorna hp_current di una creatura durante il combattimento."""
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE creature_entries SET hp_current=?, updated_at=? WHERE id=?",
            (max(0, hp_current), datetime.now().isoformat(), creature_id),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore update_creature_hp: {e}")
        return False


def set_creature_active(creature_id: str, is_active: bool, reset_hp: bool = False) -> bool:
    """
    Segna la creatura come attiva (in-campo) o inattiva.
    reset_hp=True → ripristina hp_current = hp_max (utile a fine combattimento).
    """
    try:
        conn = get_connection()
        if reset_hp:
            conn.execute(
                """UPDATE creature_entries
                   SET is_active=?, hp_current=hp_max, updated_at=?
                   WHERE id=?""",
                (int(is_active), datetime.now().isoformat(), creature_id),
            )
        else:
            conn.execute(
                "UPDATE creature_entries SET is_active=?, updated_at=? WHERE id=?",
                (int(is_active), datetime.now().isoformat(), creature_id),
            )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore set_creature_active: {e}")
        return False


def deactivate_all_creatures(character_id: str, entry_type: str | None = None) -> bool:
    """
    Disattiva tutte le creature del personaggio (fine combattimento / fine turno).
    entry_type = "forma" | "evocazione" | None (tutte).
    """
    try:
        conn = get_connection()
        if entry_type:
            conn.execute(
                """UPDATE creature_entries SET is_active=0, hp_current=hp_max, updated_at=?
                   WHERE character_id=? AND entry_type=?""",
                (datetime.now().isoformat(), character_id, entry_type),
            )
        else:
            conn.execute(
                """UPDATE creature_entries SET is_active=0, hp_current=hp_max, updated_at=?
                   WHERE character_id=?""",
                (datetime.now().isoformat(), character_id),
            )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore deactivate_all_creatures: {e}")
        return False


def update_creature_notes(creature_id: str, notes: str) -> bool:
    """Aggiorna le note libere di una voce bestiary."""
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE creature_entries SET notes=?, updated_at=? WHERE id=?",
            (notes, datetime.now().isoformat(), creature_id),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore update_creature_notes: {e}")
        return False


def delete_creature_entry(creature_id: str) -> bool:
    """Elimina definitivamente una voce dal bestiary personale."""
    try:
        conn = get_connection()
        conn.execute("DELETE FROM creature_entries WHERE id=?", (creature_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore delete_creature_entry: {e}")
        return False


# ---------------------------------------------------------------------------

def update_turn_state(character_id: str, action: bool, bonus: bool,
                      reaction: bool, movement: int, prev_state: str) -> bool:
    """Aggiornamento rapido dello stato turno."""
    try:
        conn = get_connection()
        conn.execute("""
            UPDATE characters SET
                action_used=?, bonus_action_used=?, reaction_used=?,
                movement_used=?, previous_turn_state=?, updated_at=?
            WHERE id=?
        """, (int(action), int(bonus), int(reaction), movement,
              prev_state, datetime.now().isoformat(), character_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore aggiornamento stato turno: {e}")
        return False
