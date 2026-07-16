"""
Repository per le operazioni CRUD sui personaggi.
Tutta la logica di accesso al DB per i personaggi è qui.
"""

import json
import logging
from datetime import datetime
from typing import Optional

from data.database import get_connection
from data.game_data.game_data_loader import game_data
from data.models import Character, CharacterProficiency, Currency, SpellSlot, ClassResource, CreatureEntry

logger = logging.getLogger(__name__)

# Ultimo errore di create() — letto dalla UI per mostrare il dettaglio all'utente
_last_create_error: str = ""


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
        passive_perception_override=d.get("passive_perception_override", 0) or 0,
        carry_capacity_override=d.get("carry_capacity_override", 0) or 0,
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
                dragon_ancestry, fighting_style, totem_animal, land_terrain,
                pact_boon, initiative_bonus, max_prepared_spells_override,
                passive_perception_override, carry_capacity_override,
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
                :dragon_ancestry, :fighting_style, :totem_animal, :land_terrain,
                :pact_boon, :initiative_bonus, :max_prepared_spells_override,
                :passive_perception_override, :carry_capacity_override,
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
            "dragon_ancestry": _s(character.dragon_ancestry),
            "fighting_style": _s(character.fighting_style),
            "totem_animal": _s(character.totem_animal),
            "land_terrain": _s(character.land_terrain),
            "pact_boon": _s(character.pact_boon),
            "initiative_bonus": character.initiative_bonus,
            "max_prepared_spells_override": character.max_prepared_spells_override,
            "passive_perception_override": character.passive_perception_override,
            "carry_capacity_override": character.carry_capacity_override,
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
        global _last_create_error
        _last_create_error = f"{type(e).__name__}: {e}"
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
                max_prepared_spells_override=:max_prepared_spells_override,
                passive_perception_override=:passive_perception_override,
                carry_capacity_override=:carry_capacity_override,
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
            "max_prepared_spells_override": character.max_prepared_spells_override,
            "passive_perception_override": character.passive_perception_override,
            "carry_capacity_override": character.carry_capacity_override,
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


# Token bare per le competenze bonus di sottoclasse ("bonus_proficiencies"
# in classes/*.json), stessa convenzione già usata da "armor_proficiencies"/
# "weapon_proficiencies" a livello di classe (normalizzazione del
# 2026-07-10: "#armature_pesanti" -> "pesanti", ecc.). Aggiunte qui il
# 2026-07-16 insieme alla normalizzazione degli stessi tag rimasti rotti
# in chierico.json/bardo.json (vedi CLAUDE.md, TODO "bonus_proficiencies
# nelle sottoclassi di chierico.json/bardo.json").
_ARMOR_PROFICIENCY_TOKENS = {"leggere", "medie", "pesanti", "scudi"}
_WEAPON_PROFICIENCY_TOKENS = {"semplice", "semplice_mischia", "guerra", "guerra_mischia"}


def classify_bonus_proficiency_entries(entries: list) -> tuple[list[str], list[dict]]:
    """
    Divide una lista `bonus_proficiencies` (dal JSON di una sottoclasse) in:
    - fixed: stringhe pronte per il salvataggio diretto (token bare
      armatura/arma, o nome letterale di una competenza già specifica —
      es. uno strumento, come in ladro.json -> Assassino)
    - choices: dict `{"type":"choice","count":N,"from":[...]|"any_skill"}`
      che richiedono una scelta del giocatore prima di poter essere
      applicate (gestita dalla UI di creazione/level-up, vedi
      resolve_bonus_proficiency_choice_options())

    Voci di tipo non riconosciuto vengono ignorate silenziosamente (nessuna
    sottoclasse attuale ne contiene un formato diverso, ma la funzione non
    deve mai sollevare eccezioni su dati imprevisti).
    """
    fixed: list[str] = []
    choices: list[dict] = []
    for entry in entries or []:
        if isinstance(entry, dict) and entry.get("type") == "choice":
            choices.append(entry)
        elif isinstance(entry, str):
            fixed.append(entry)
    return fixed, choices


def resolve_bonus_proficiency_choice_options(entry: dict) -> list[str]:
    """
    Risolve il pool di opzioni selezionabili per una entry `{"type":
    "choice", "from": ...}`: "any_skill" -> tutte le 18 abilità PHB,
    altrimenti la lista letterale già presente nel JSON.
    """
    from config.settings import SKILLS
    src = entry.get("from")
    if src == "any_skill":
        return list(SKILLS.keys())
    if isinstance(src, list):
        return list(src)
    return []


def _classify_bonus_proficiency_type(entry_name: str) -> str:
    """
    Determina il proficiency_type corretto per una singola voce già
    risolta (token bare armatura/arma, nome di una delle 18 abilità PHB, o
    nome libero — strumento/altra competenza specifica).
    """
    from config.settings import SKILLS
    if entry_name in _ARMOR_PROFICIENCY_TOKENS:
        return "armor"
    if entry_name in _WEAPON_PROFICIENCY_TOKENS:
        return "weapon"
    if entry_name in SKILLS:
        return "skill"
    return "tool"


def apply_subclass_bonus_proficiencies(character_id: str, resolved_entries: list[str]) -> None:
    """
    Salva le competenze bonus di una sottoclasse (`bonus_proficiencies`,
    normalizzato in chierico.json/bardo.json il 2026-07-16 — generico per
    qualunque sottoclasse futura con lo stesso campo, es. ladro.json ->
    Assassino). `resolved_entries` è la lista FINALE di nomi già risolti:
    sia le voci fisse (token armatura/arma bare o nomi letterali) sia le
    scelte del giocatore per le entry "choice" (risolte dalla UI PRIMA di
    questa chiamata, tramite resolve_bonus_proficiency_choice_options()).

    Idempotente per contenuto: salta le voci già presenti per lo stesso
    (character_id, proficiency_type, name) — a differenza della normale
    _save_single_proficiency() (nessun vincolo UNIQUE sulla tabella, quindi
    duplicherebbe silenziosamente ad ogni chiamata), qui serve perché la
    scelta sottoclasse può essere riaperta o ripetuta (level-down e poi di
    nuovo level-up sulla stessa sottoclasse).
    """
    if not resolved_entries:
        return
    try:
        conn = get_connection()
        existing = {
            (row["proficiency_type"], row["name"])
            for row in conn.execute(
                "SELECT proficiency_type, name FROM character_proficiencies WHERE character_id=?",
                (character_id,),
            ).fetchall()
        }
        conn.close()
    except Exception as e:
        logger.error(f"Errore lettura competenze esistenti per bonus sottoclasse: {e}")
        existing = set()

    for entry_name in resolved_entries:
        if not entry_name:
            continue
        ptype = _classify_bonus_proficiency_type(entry_name)
        if (ptype, entry_name) in existing:
            continue
        _save_single_proficiency(character_id, ptype, entry_name)
        existing.add((ptype, entry_name))


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
#
# Spostata in data/game_data/spell_slot_progressions.json il 2026-07-10 —
# stesso principio già applicato a RACE_DATA/CLASSES/tags.json: i numeri
# erano già stati verificati contro il manuale in sessioni di audit
# precedenti, ma vivevano solo come dizionari Python invece che come dato
# JSON. GameDataLoader.get_caster_type()/get_spell_slot_table() sono
# l'unica fonte ora — nessun valore è cambiato in questa migrazione
# (confrontato con uno script di diff automatico prima della rimozione).
# ---------------------------------------------------------------------------


def auto_init_spell_slots(character_id: str, class_name: str, level: int) -> bool:
    """
    Aggiorna i totali slot incantesimo in base a classe e livello PHB.
    Sicuro da chiamare ad ogni level-up: aggiorna total e clamppa used al nuovo total.
    Per il Warlock (Patto della Magia) azzera i livelli non più attivi quando il
    livello degli slot aumenta (es. da Lv2 a Lv3: slot Lv1→0, slot Lv2→2).
    """
    caster_type = game_data.get_caster_type(class_name)
    if not caster_type:
        return False  # Classe non incantatore o non gestita
    table = game_data.get_spell_slot_table(caster_type)
    if not table:
        return False

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


def init_borrowed_caster_slots(
    character_id: str, class_name: str, subclass: str, level: int
) -> bool:
    """
    Aggiorna i totali slot incantesimo per Mistificatore Arcano (Ladro) e
    Cavaliere Mistico (Guerriero) — le uniche 2 sottoclassi PHB che
    concedono casting a una classe senza spellcasting_ability propria.

    Percorso completamente indipendente da auto_init_spell_slots() (che
    legge caster_type da game_data.get_caster_type(class_name), sempre
    vuoto per Ladro/Guerriero): nessun rischio per le 12 classi già
    funzionanti. Ritorna False (no-op) se la sottoclasse non è una delle
    2 gestite o se il personaggio non ha ancora raggiunto il 3° livello
    (subclass_choice_level) — in quel caso non tocca gli slot esistenti.

    Sicura da chiamare ad ogni level-up/level-down, stesso pattern di
    auto_init_spell_slots: aggiorna total e clamppa used al nuovo total.
    """
    row = game_data.get_borrowed_caster_progression_for_level(
        class_name, subclass, level
    )
    if row is None:
        return False
    slots = row.get("slots", {})
    if not slots:
        return False
    try:
        conn = get_connection()
        for slot_lv_str, total in slots.items():
            slot_lv = int(slot_lv_str)
            conn.execute(
                "UPDATE spell_slots SET total=?, used=MIN(used,?) "
                "WHERE character_id=? AND slot_level=?",
                (total, total, character_id, slot_lv),
            )
        conn.commit()
        conn.close()
        logger.info(
            "Slot borrowed-caster auto-init: %s/%s Lv%d → %s",
            class_name, subclass, level, slots,
        )
        return True
    except Exception as e:
        logger.error(f"Errore init_borrowed_caster_slots {character_id}: {e}")
        return False


def sync_borrowed_spellcasting_ability(character: "Character") -> bool:
    """
    Imposta/ricalcola character.spellcasting_ability per le sottoclassi che
    concedono casting a una classe altrimenti non incantatrice (Mistificatore
    Arcano/Ladro, Cavaliere Mistico/Guerriero — entrambe "int" per PHB,
    letto dal JSON di sottoclasse, mai hardcoded qui).

    No-op (ritorna False, non tocca nulla) se la classe base HA GIA' una
    propria spellcasting_ability nel JSON — questa funzione serve solo a
    "riempire il vuoto" per le classi che altrimenti non ne avrebbero
    nessuna, mai a sovrascrivere un incantatore vero.

    Sicura da richiamare ad ogni level-up/level-down/creazione: se il
    personaggio non ha (ancora) una delle 2 sottoclassi gestite, riporta
    spellcasting_ability a "" (nessun incantesimo) — difensivo contro lo
    stato residuo se in futuro venisse mai introdotto un modo di cambiare
    sottoclasse. Aggiorna sia l'oggetto Character in memoria sia la riga DB.
    """
    cls_data = game_data.get_class(character.class_name or "")
    if cls_data and (cls_data.get("spellcasting_ability") or ""):
        return False  # la classe base ha già una propria caratteristica da incantatore

    sc = game_data.get_borrowed_caster_data(character.class_name or "", character.subclass or "")
    new_ability = (sc.get("spellcasting_ability") or "") if sc else ""

    if character.spellcasting_ability == new_ability:
        return False  # già sincronizzato, nessuna scrittura necessaria

    try:
        conn = get_connection()
        conn.execute(
            "UPDATE characters SET spellcasting_ability=?, updated_at=? WHERE id=?",
            (new_ability, datetime.now().isoformat(), character.id),
        )
        conn.commit()
        conn.close()
        character.spellcasting_ability = new_ability
        return True
    except Exception as e:
        logger.error(f"Errore sync_borrowed_spellcasting_ability {character.id}: {e}")
        return False


def sync_bonus_domain_spells(character: "Character") -> None:
    """
    Sincronizza gli incantesimi "sempre pronti" concessi da un privilegio di
    Dominio (Chierico)/Giuramento (Paladino)/Circolo della Terra (Druido) —
    PHB: questi incantesimi si aggiungono alla lista di incantesimi preparati
    del chierico/paladino/druido e sono SEMPRE preparati, non contano nel
    numero di incantesimi che il personaggio può preparare.

    Dati letti (nessun nuovo audit manuale, stessi JSON già verificati):
      - chierico.json / paladino.json → subclasses[i].bonus_spells,
        dict {"livello_soglia": [nomi]} (es. Paladino Giuramento degli
        Antichi: {"3": ["Colpo Intrappolante", "Parlare con gli Animali"],
        "5": ["Bagliore Lunare", "Passo Velato"], ...}).
      - druido.json → subclasses[i].circle_spells (solo Circolo della
        Terra), dict {terreno: {"livello_soglia": [nomi]}} — filtrato per
        `character.land_terrain`.

    Self-healing: va richiamata ad ogni apertura di SpellsView e ad ogni
    level-up/level-down (stesso pattern di init_class_resources()) — così
    un cambio di sottoclasse/terreno o livello riallinea sempre lo stato
    corretto senza richiedere un'azione manuale del giocatore. Ogni
    incantesimo atteso viene scritto/aggiornato in known_spells con
    `always_prepared=True, is_prepared=True`; ogni riga `always_prepared=1`
    non più valida (sottoclasse/terreno cambiati, level-down sotto la
    soglia) viene ripulita — se quella stessa riga era ANCHE un incantesimo
    bonus scelto manualmente dal giocatore (`is_bonus=True`, task
    "Incantesimi bonus"), il flag `always_prepared` viene semplicemente
    rimosso invece di cancellare l'intera riga, per non perdere la scelta
    del giocatore.
    """
    cls_lower = (character.class_name or "").strip().lower()
    level = character.level
    subclass = character.subclass or ""

    expected: dict[tuple[str, int], dict] = {}

    def _collect(spells_by_level: dict, resolve_class: str) -> None:
        for lvl_str, names in (spells_by_level or {}).items():
            try:
                lvl_threshold = int(lvl_str)
            except (TypeError, ValueError):
                continue
            if level < lvl_threshold:
                continue
            for name in names:
                resolved = game_data.get_spell_by_name(name, resolve_class)
                key_level = resolved.get("level", 0) if resolved else 0
                expected[(name, key_level)] = resolved or {"name": name}

    if cls_lower in ("chierico", "paladino") and subclass:
        cls_data = game_data.get_class(cls_lower)
        sc_data = next(
            (sc for sc in (cls_data.get("subclasses", []) if cls_data else [])
             if sc.get("name") == subclass),
            None,
        )
        if sc_data:
            _collect(sc_data.get("bonus_spells", {}), cls_lower)
    elif cls_lower == "druido" and character.land_terrain:
        cls_data = game_data.get_class("druido")
        sc_data = next(
            (sc for sc in (cls_data.get("subclasses", []) if cls_data else [])
             if "circle_spells" in sc),
            None,
        )
        if sc_data:
            terrain_spells = sc_data.get("circle_spells", {}).get(character.land_terrain, {})
            _collect(terrain_spells, "druido")

    for (name, lvl), spell in expected.items():
        comps = spell.get("components", [])
        comp_str = ", ".join(comps) if isinstance(comps, list) else str(comps)
        if spell.get("material"):
            comp_str += f" ({spell['material']})"
        upsert_known_spell(
            character_id=character.id,
            name=spell.get("name", name),
            level=lvl,
            is_prepared=True,
            school=spell.get("school", ""),
            casting_time=spell.get("casting_time", ""),
            spell_range=spell.get("range", ""),
            components=comp_str,
            duration=spell.get("duration", ""),
            description=spell.get("description", ""),
            higher_levels=spell.get("higher_levels", "") or "",
            class_list=character.class_name or "",
            always_prepared=True,
        )

    expected_keys = set(expected.keys())
    try:
        conn = get_connection()
        rows = conn.execute(
            "SELECT name, spell_level, is_bonus FROM known_spells "
            "WHERE character_id=? AND always_prepared=1",
            (character.id,),
        ).fetchall()
        conn.close()
        for r in rows:
            key = (r["name"], r["spell_level"])
            if key in expected_keys:
                continue
            if r["is_bonus"]:
                _clear_always_prepared_flag(character.id, r["name"], r["spell_level"])
            else:
                remove_known_spell(character.id, r["name"], r["spell_level"])
    except Exception as e:
        logger.error(f"Errore sync_bonus_domain_spells (cleanup) {character.id}: {e}")


def _clear_always_prepared_flag(character_id: str, name: str, level: int) -> None:
    """Rimuove SOLO il flag always_prepared, senza toccare il resto della riga."""
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE known_spells SET always_prepared=0 "
            "WHERE character_id=? AND name=? AND spell_level=?",
            (character_id, name, level),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Errore _clear_always_prepared_flag {character_id}/{name}: {e}")


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
                versatile_damage_dice=r["versatile_damage_dice"] or "",
                grip_two_handed=bool(r["grip_two_handed"]),
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
                origin_unrestricted=bool(r["origin_unrestricted"])
                if "origin_unrestricted" in r.keys() else False,
                is_bonus=bool(r["is_bonus"]) if "is_bonus" in r.keys() else False,
                always_prepared=bool(r["always_prepared"])
                if "always_prepared" in r.keys() else False,
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
    origin_unrestricted: bool = False,
    is_bonus: bool | None = None,
    always_prepared: bool | None = None,
) -> bool:
    """
    Inserisce o aggiorna un incantesimo in known_spells.
    Identifica la riga per (character_id, name, spell_level).

    origin_unrestricted: solo per Mistificatore Arcano/Cavaliere Mistico —
    True se questo pick è "libero da vincolo di scuola" (vedi KnownSpell in
    data/models.py). Ignorato/sempre False per tutte le altre classi.

    is_bonus/always_prepared: usano `None` come sentinel "non specificato"
    (2026-07-16, task incantesimi bonus/sempre pronti) — a differenza degli
    altri parametri con default `False`/`""`, qui serve distinguere "il
    chiamante non sa/non vuole toccare questo flag" da "il chiamante vuole
    esplicitamente False". Motivo: molti punti del codice (toggle
    preparazione normale, SPELL_LEARN, Segreti Magici, ecc.) chiamano questa
    funzione su un incantesimo che potrebbe già esistere come bonus o
    sempre-pronto — se questi due flag avessero un default `False` fisso,
    ogni chiamata "innocente" li azzererebbe silenziosamente. Se `None`, il
    valore esistente sulla riga (o `False` per una riga nuova) viene
    preservato.
    """
    import uuid as _uuid
    try:
        conn = get_connection()
        existing = conn.execute(
            "SELECT id, is_bonus, always_prepared FROM known_spells "
            "WHERE character_id=? AND name=? AND spell_level=?",
            (character_id, name, level),
        ).fetchone()
        if existing:
            final_bonus = is_bonus if is_bonus is not None else bool(existing["is_bonus"])
            final_always = (
                always_prepared if always_prepared is not None
                else bool(existing["always_prepared"])
            )
            conn.execute(
                "UPDATE known_spells SET is_prepared=?, school=?, casting_time=?, "
                "spell_range=?, components=?, duration=?, description=?, higher_levels=?, "
                "class_list=?, origin_unrestricted=?, is_bonus=?, always_prepared=? WHERE id=?",
                (int(is_prepared), school, casting_time, spell_range, components,
                 duration, description, higher_levels, class_list,
                 int(origin_unrestricted), int(final_bonus), int(final_always),
                 existing["id"]),
            )
        else:
            final_bonus = bool(is_bonus)
            final_always = bool(always_prepared)
            conn.execute(
                "INSERT INTO known_spells (id, character_id, name, spell_level, is_prepared, "
                "school, casting_time, spell_range, components, duration, description, "
                "higher_levels, class_list, origin_unrestricted, is_bonus, always_prepared) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (str(_uuid.uuid4()), character_id, name, level, int(is_prepared),
                 school, casting_time, spell_range, components, duration, description,
                 higher_levels, class_list, int(origin_unrestricted),
                 int(final_bonus), int(final_always)),
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
                  range_max: int = 0, magic_damages: str = "[]",
                  versatile_damage_dice: str = "",
                  grip_two_handed: bool = False) -> bool:
    """Crea una nuova arma per il personaggio.

    versatile_damage_dice/grip_two_handed: dado danno a due mani e stato
    dell'impugnatura per le armi con proprietà "Versatile" (PHB p.149) —
    vedi il docstring di core/equipment_manager.py per i dettagli meccanici.
    """
    import uuid as _uuid
    try:
        conn = get_connection()
        conn.execute(
            """INSERT INTO weapons
               (id, character_id, name, damage_dice, damage_type, attack_bonus,
                damage_bonus, properties, is_magical, magic_description,
                is_equipped, range_normal, range_max, magic_damages,
                versatile_damage_dice, grip_two_handed)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (str(_uuid.uuid4()), character_id, name, damage_dice, damage_type,
             attack_bonus, damage_bonus, properties, int(is_magical),
             magic_description, int(is_equipped), range_normal, range_max, magic_damages,
             versatile_damage_dice, int(grip_two_handed))
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
                  magic_damages: str = "[]",
                  versatile_damage_dice: str = "",
                  grip_two_handed: bool = False) -> bool:
    """Aggiorna un'arma esistente."""
    try:
        conn = get_connection()
        conn.execute(
            """UPDATE weapons SET name=?, damage_dice=?, damage_type=?,
               attack_bonus=?, damage_bonus=?, properties=?, is_equipped=?,
               is_magical=?, magic_description=?, range_normal=?, range_max=?,
               magic_damages=?, versatile_damage_dice=?, grip_two_handed=?
               WHERE id=?""",
            (name, damage_dice, damage_type, attack_bonus, damage_bonus,
             properties, int(is_equipped), int(is_magical), magic_description,
             range_normal, range_max, magic_damages,
             versatile_damage_dice, int(grip_two_handed), weapon_id)
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
                          effects: str = "") -> str | None:
    """Crea un nuovo oggetto nell'inventario.

    Ritorna l'id generato in caso di successo, None in caso di errore —
    il valore resta "truthy" per i chiamanti preesistenti che facevano
    `if not create_inventory_item(...): show_error_dialog(...)` (un id
    UUID non è mai stringa vuota), ma i nuovi chiamanti possono usare
    l'id per operazioni successive sullo stesso oggetto appena creato
    (es. risoluzione dei conflitti di equipaggiamento in
    core/equipment_manager.py, che ha bisogno dell'id per essere incluso
    nel calcolo — vedi inventario_tab.py → _open_item_dialog).
    """
    import uuid as _uuid
    new_id = str(_uuid.uuid4())
    try:
        conn = get_connection()
        conn.execute(
            """INSERT INTO inventory_items
               (id, character_id, name, quantity, weight, description,
                category, is_equipped, ca_value, armor_type, effects)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (new_id, character_id, name, quantity, weight,
             description, category, int(is_equipped), ca_value, armor_type, effects)
        )
        conn.commit()
        conn.close()
        return new_id
    except Exception as e:
        logger.error(f"Errore creazione oggetto inventario: {e}")
        return None


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


# ---------------------------------------------------------------------------
# Abilità Speciali custom (2026-07-16)
# ---------------------------------------------------------------------------

def get_custom_abilities(character_id: str, category: str | None = None) -> list:
    """
    Restituisce le abilità speciali custom del personaggio (es. concesse dal
    master), opzionalmente filtrate per categoria ("esplorazione" |
    "combattimento"). Ordine: created_at ASC (cronologico).
    """
    from data.models import CustomAbility
    try:
        conn = get_connection()
        if category:
            rows = conn.execute(
                "SELECT * FROM custom_abilities WHERE character_id=? AND category=?"
                " ORDER BY created_at ASC",
                (character_id, category)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM custom_abilities WHERE character_id=?"
                " ORDER BY category, created_at ASC",
                (character_id,)
            ).fetchall()
        conn.close()
        return [
            CustomAbility(
                id=r["id"],
                character_id=r["character_id"],
                category=r["category"],
                name=r["name"],
                description=r["description"] or "",
                created_at=r["created_at"] or "",
                updated_at=r["updated_at"] or "",
            )
            for r in rows
        ]
    except Exception as e:
        logger.error(f"Errore lettura custom_abilities per {character_id}: {e}")
        return []


def create_custom_ability(character_id: str, category: str, name: str,
                           description: str = "") -> str | None:
    """Crea una nuova abilità speciale custom. Ritorna l'id creato o None."""
    import uuid as _uuid
    now = datetime.now().isoformat()
    new_id = str(_uuid.uuid4())
    try:
        conn = get_connection()
        conn.execute(
            """INSERT INTO custom_abilities
               (id, character_id, category, name, description, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (new_id, character_id, category, name, description, now, now)
        )
        conn.commit()
        conn.close()
        return new_id
    except Exception as e:
        logger.error(f"Errore creazione custom_ability: {e}")
        return None


def update_custom_ability(ability_id: str, name: str, description: str) -> bool:
    """Aggiorna nome/descrizione di un'abilità speciale custom esistente."""
    now = datetime.now().isoformat()
    try:
        conn = get_connection()
        conn.execute(
            """UPDATE custom_abilities
               SET name=?, description=?, updated_at=?
               WHERE id=?""",
            (name, description, now, ability_id)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore aggiornamento custom_ability {ability_id}: {e}")
        return False


def delete_custom_ability(ability_id: str) -> bool:
    """Elimina un'abilità speciale custom."""
    try:
        conn = get_connection()
        conn.execute("DELETE FROM custom_abilities WHERE id=?", (ability_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore eliminazione custom_ability {ability_id}: {e}")
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


def update_passive_perception_override(character_id: str, value: int) -> bool:
    """
    Salva l'override manuale della Percezione Passiva (0 = usa la formula PHB
    10 + mod SAG + eventuale bonus competenza/maestria). Aggiunto 2026-07-16
    su richiesta di Davide ("rendiamo modificabili... percezione passiva"),
    stesso pattern di update_max_prepared_override/proficiency_bonus_override.
    """
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE characters SET passive_perception_override=?, updated_at=? WHERE id=?",
            (value, datetime.now().isoformat(), character_id),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore update_passive_perception_override: {e}")
        return False


def update_carry_capacity_override(character_id: str, value: float) -> bool:
    """
    Salva l'override manuale della capacità di trasporto massima in kg
    (0 = usa la formula standard FOR × 7,5 kg). Aggiunto 2026-07-16 su
    richiesta di Davide ("rendiamo modificabili... il peso in Inventario")
    — permette di riflettere talenti/tratti che alterano il carico
    (es. "Corporatura Possente" raddoppia il carico) senza toccare la
    formula base né inventare un talento non ancora nei dati PHB.
    """
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE characters SET carry_capacity_override=?, updated_at=? WHERE id=?",
            (value, datetime.now().isoformat(), character_id),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore update_carry_capacity_override: {e}")
        return False


def update_speed(character_id: str, speed: float) -> bool:
    """
    Aggiorna solo la velocità base a piedi del personaggio (senza toccare la
    CA, a differenza del dialog combinato "Modifica CA/Velocità" già
    esistente in combattimento_tab.py) — usata dal punto di modifica rapida
    aggiunto in Esplorazione (2026-07-16, richiesta Davide: "rendiamo
    modificabili... velocità").
    """
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE characters SET speed=?, updated_at=? WHERE id=?",
            (speed, datetime.now().isoformat(), character_id),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore update_speed: {e}")
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
    Ricalcola la CA del personaggio in base all'armatura e agli scudi equipaggiati,
    e alle capacità di classe che modificano la formula di base (Categoria B
    dell'audit 2026-07-09 — bonus condizionati all'equipaggiamento attuale, quindi
    ricalcolati da zero ad ogni chiamata anziché salvati come "ricevuta" fissa).

    Logica PHB, senza armatura equipaggiata:
      - Monaco (Difesa Senza Armatura, e nessuno scudo) → 10 + mod DES + mod SAG
      - Barbaro (Difesa Senza Armatura, scudo permesso) → 10 + mod DES + mod COS
      - Stregone con Discendenza Draconica (Resilienza Draconica) → 13 + mod DES
      - Altrimenti → 10 + mod DES

    Logica PHB, con armatura equipaggiata:
      - Armatura leggera  → ca_value + mod DES
      - Armatura media    → ca_value + min(mod DES, 2)
      - Armatura pesante  → ca_value  (DES ignorato)
      - Stile di Combattimento "Difesa" (Guerriero/Paladino/Ranger) → +1 alla CA

    Scudo → somma i ca_value di tutti gli scudi equipaggiati (sempre, salvo
    l'eccezione Monaco sopra, che perde la Difesa Senza Armatura se ne indossa uno).

    Aggiorna il campo `ac` nel DB e restituisce il nuovo valore.

    NOTA (2026-07-11): questa funzione presuppone che al massimo UN'armatura
    corporea e UN solo scudo risultino equipaggiati alla volta — invariante
    ora garantita a monte da `core/equipment_manager.py → resolve_armor_equip()`,
    applicata da `inventario_tab.py` ad ogni equip di armatura/scudo (esclude
    automaticamente l'altra armatura/scudo già indossato). Prima di questo
    fix, equipaggiarne una seconda senza disequipaggiare la prima lasciava
    `equipped_armor[0]` legato per sempre al primo item creato: la CA
    sembrava "non aggiornarsi più" nonostante l'equipaggiamento cambiasse.
    Questa funzione resta comunque difensiva (prende sempre e solo il primo
    risultato) nel caso l'invariante venga violata da un percorso di codice
    futuro che non passi da resolve_armor_equip().
    """
    from config.settings import get_modifier
    try:
        char = get_by_id(character_id)
        if not char:
            return 10
        dex_mod = get_modifier(char.dex_score)
        class_name = (char.class_name or "").strip()
        subclass = (char.subclass or "").strip()

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
            # Stile di Combattimento "Difesa" — PHB: +1 CA finché indossa
            # un'armatura (fighting_style_details in guerriero.json)
            if (char.fighting_style or "") == "Difesa":
                base_ca += 1
        elif class_name == "Monaco" and not equipped_shields:
            # Difesa Senza Armatura (Monaco): richiede nessuna armatura E nessuno scudo
            base_ca = 10 + dex_mod + get_modifier(char.wis_score)
        elif class_name == "Barbaro":
            # Difesa Senza Armatura (Barbaro): lo scudo è permesso
            base_ca = 10 + dex_mod + get_modifier(char.con_score)
        elif class_name == "Stregone" and subclass == "Discendenza Draconica":
            # Resilienza Draconica
            base_ca = 13 + dex_mod
        else:
            base_ca = 10 + dex_mod  # senza armatura, nessuna formula di classe

        shield_ca = sum(s.ca_value for s in equipped_shields)
        new_ca = base_ca + shield_ca

        conn = get_connection()
        conn.execute(
            "UPDATE characters SET ac=?, updated_at=? WHERE id=?",
            (new_ca, datetime.now().isoformat(), character_id)
        )
        conn.commit()
        conn.close()
        logger.info(f"CA aggiornata: {new_ca} (base={base_ca}, scudo={shield_ca})")
        return new_ca
    except Exception as e:
        logger.error(f"Errore calcolo CA: {e}")
        return 10


def get_effective_speed(character: Character) -> float:
    """
    Calcola la velocità di movimento a piedi EFFETTIVA del personaggio,
    sommando alla velocità base (`character.speed` — già comprensiva di
    eventuali override manuali del giocatore e del bonus fisso del
    Talento Mobile, applicato come ricevuta diretta su `speed`) il bonus
    dinamico concesso da alcune capacità di classe condizionate
    all'equipaggiamento attualmente indossato (Categoria B dell'audit
    2026-07-09, parte Velocità).

    Decisione architetturale (confermata da Davide 2026-07-09): a differenza
    della CA, `speed` ha già due meccanismi consolidati (override manuale in
    Combattimento, bonus Talento Mobile) che scriverebbero un valore assoluto
    in conflitto con un ricalcolo automatico persistito. Questa funzione
    quindi NON scrive mai sul DB: il bonus di classe viene ricalcolato al
    volo ad ogni chiamata e va sommato dal chiamante solo dove serve
    mostrare/usare la velocità effettiva. `character.speed` in DB resta
    sempre il valore "base" (razza + override manuale + Talento Mobile),
    intatto e mai sovrascritto da questa funzione.

    Casi gestiti (PHB, testo confermato nei file classe già auditati ✅):
      - Monaco, "Movimento Senza Armatura" (dal 2° livello): +3 m, se non
        indossa armatura né scudo. Il bonus non è cumulativo: sale a +4,5 m
        al 6°, +6 m al 10°, +7,5 m al 14°, +9 m al 18° (sostituisce, non si
        somma ai livelli precedenti).
      - Barbaro, "Movimento Veloce" (dal 5° livello): +3 m, se non indossa
        un'armatura pesante (armatura leggera/media e scudo non ostacolano).

    Scelta di scope deliberata: il bonus si applica solo alla velocità a
    piedi (Camminata). Le velocità speciali mostrate in Esplorazione (Nuoto,
    Scalata, Volo, quando presenti come tratto razziale) restano al valore
    base — il testo PHB di entrambe le capacità parla esplicitamente della
    "velocità" del personaggio nel senso di velocità di movimento a piedi,
    non delle velocità speciali derivate dalla razza.
    """
    base = character.speed or 0
    class_name = (character.class_name or "").strip()
    level = character.level or 1

    if class_name not in ("Monaco", "Barbaro"):
        return base

    try:
        items = get_inventory(character.id)
    except Exception as e:
        logger.error(f"Errore lettura inventario per calcolo velocità effettiva: {e}")
        return base

    has_armor = any(i.is_equipped and i.category == "armor"
                     and i.armor_type in ("leggera", "media", "pesante") for i in items)
    has_heavy_armor = any(i.is_equipped and i.category == "armor"
                          and i.armor_type == "pesante" for i in items)
    has_shield = any(i.is_equipped and i.category == "armor"
                     and i.armor_type == "scudo" for i in items)

    bonus = 0.0
    if class_name == "Monaco" and level >= 2 and not has_armor and not has_shield:
        if level >= 18:
            bonus = 9.0
        elif level >= 14:
            bonus = 7.5
        elif level >= 10:
            bonus = 6.0
        elif level >= 6:
            bonus = 4.5
        else:
            bonus = 3.0
    elif class_name == "Barbaro" and level >= 5 and not has_heavy_armor:
        bonus = 3.0

    return base if bonus == 0 else base + bonus


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
            (lambda d: ClassResource(
                id=d["id"],
                character_id=d["character_id"],
                name=d["name"],
                max_value=d["max_value"],
                current_value=d["current_value"],
                reset_on=d["reset_on"],
                display_type=d["display_type"],
                max_value_bonus=d.get("max_value_bonus", 0) or 0,
            ))(dict(r))
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


def update_class_resource_bonus(resource_id: str, max_value_bonus: int) -> bool:
    """
    Imposta il bonus permanente additivo al massimo di una risorsa di classe
    (2026-07-16, richiesta Davide: "rendiamo modificabili... Risorse di
    classe"). Non tocca max_value/current_value direttamente: il chiamante
    deve far seguire un `init_class_resources()` per ricalcolare max_value
    = default PHB + bonus (stesso pattern già usato per sincronizzare le
    risorse dopo un level-up), altrimenti il bonus resterebbe salvato ma
    non ancora riflesso nel pool visibile.
    """
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE class_resources SET max_value_bonus=? WHERE id=?",
            (max_value_bonus, resource_id)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore aggiornamento bonus risorsa {resource_id}: {e}")
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
                base_max = d["max_value"]
                if base_max < 0:
                    # Pool illimitato (es. Furia del Barbaro al 20° livello):
                    # il sentinel -1 non è un numero di usi reale, il bonus
                    # additivo non si applica (non esiste "infinito+N").
                    new_max = -1
                else:
                    # Bonus permanente additivo (2026-07-16, talenti/oggetti
                    # magici che concedono usi extra a una risorsa) — deve
                    # sopravvivere a questo stesso ri-sync, che altrimenti
                    # sovrascriverebbe max_value col solo valore PHB.
                    new_max = base_max + (ex.max_value_bonus or 0)
                if new_max < 0:
                    new_current = -1
                elif ex.current_value < 0:
                    # Pool ERA illimitato (sentinel -1) e torna finito — tipicamente
                    # un level-down dal 20° livello. Non c'è un "usato" reale da
                    # riportare indietro: il min(-1, new_max) darebbe sempre -1
                    # (bug), quindi si riparte a piena carica sul nuovo massimo.
                    new_current = new_max
                else:
                    new_current = min(ex.current_value, new_max)
                conn.execute(
                    """UPDATE class_resources
                       SET max_value=?, current_value=?, reset_on=?, display_type=?
                       WHERE id=?""",
                    (new_max, new_current, d["reset_on"], d["display_type"], ex.id)
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
                      reaction: bool, movement: float, prev_state: str) -> bool:
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
