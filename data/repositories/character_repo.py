"""
Repository per le operazioni CRUD sui personaggi.
Tutta la logica di accesso al DB per i personaggi è qui.
"""

import json
import logging
from datetime import datetime
from typing import Optional

from data.database import get_connection
from data.models import Character, CharacterProficiency, Currency

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
            INSERT INTO characters VALUES (
                :id, :name, :player_name, :class_name, :subclass, :level,
                :race, :subrace, :background, :alignment, :xp, :image_path,
                :str_score, :dex_score, :con_score, :int_score, :wis_score, :cha_score,
                :hp_max, :hp_current, :hp_temp,
                :ac, :speed, :hit_dice_type, :hit_dice_total, :hit_dice_remaining,
                :death_saves_success, :death_saves_failure,
                :action_used, :bonus_action_used, :reaction_used,
                :movement_used, :previous_turn_state,
                :spellcasting_ability, :inspiration,
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
) -> bool:
    """Inserisce una singola competenza (usata dal wizard)."""
    import uuid
    try:
        conn = get_connection()
        conn.execute(
            """INSERT OR IGNORE INTO character_proficiencies
               (id, character_id, proficiency_type, name, is_expert)
               VALUES (?, ?, ?, ?, ?)""",
            (str(uuid.uuid4()), character_id, proficiency_type, name, int(is_expert)),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore salvataggio competenza '{name}': {e}")
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


def update_hp(character_id: str, hp_current: int, hp_temp: int = None) -> bool:
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
