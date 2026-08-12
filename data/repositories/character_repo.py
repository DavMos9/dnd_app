"""
Repository per le operazioni CRUD sui personaggi.
Tutta la logica di accesso al DB per i personaggi è qui.
"""

import json
import logging
from datetime import datetime
from typing import Any, Optional

from data.database import get_connection
from data.game_data.game_data_loader import game_data
from data.models import (Character, CharacterCondition, CharacterClass, CharacterProficiency,
                         Currency, SpellSlot, ClassResource, CreatureEntry)

logger = logging.getLogger(__name__)

# Ultimo errore di create() — letto dalla UI per mostrare il dettaglio all'utente
_last_create_error: str = ""


def _s(value) -> str:
    """Converte None in stringa vuota per i campi TEXT NOT NULL."""
    return value if value is not None else ""


def _col(row, name: str, default=0):
    """
    Legge una colonna da una `sqlite3.Row` tollerando che non esista.

    `sqlite3.Row` non ha `.get()` (nota già presente in CLAUDE.md) e solleva
    `IndexError` per una colonna assente: qui serve perché le colonne aggiunte
    da `_migrate()` potrebbero mancare se il DB non è ancora stato migrato in
    questa sessione.
    """
    try:
        value = row[name]
    except (IndexError, KeyError):
        return default
    return default if value is None else value


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
        exhaustion_level=d.get("exhaustion_level", 0) or 0,
        frenzy_active=bool(d.get("frenzy_active", 0) or 0),
        concentrating_spell=d.get("concentrating_spell", "") or "",
        concentrating_since=d.get("concentrating_since", "") or "",
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
        world_id=d.get("world_id", "") or "",
        origin_character_id=d.get("origin_character_id", "") or "",
        owner_device_id=d.get("owner_device_id", "") or "",
        is_replica=bool(d.get("is_replica", 0) or 0),
        world_seq=d.get("world_seq", 0) or 0,
        world_instance_archived=bool(d.get("world_instance_archived", 0) or 0),
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


def get_all_instances_of_world(world_id: str) -> list[Character]:
    """
    TUTTE le istanze di `world_id`, comprese quelle archiviate — a
    differenza di `get_master_visible_characters()` sotto, che filtra
    `world_instance_archived=0` per la Sezione Master (2026-08-12,
    "Esportazione del mondo" §6.3/§9D: un backup/trasferimento di campagna
    deve portare con sé anche le istanze rimosse, non solo quelle attive —
    altrimenti un'espulsione o una rimozione singola diventerebbe
    silenziosamente definitiva al primo export/import, contraddicendo la
    scelta esplicita di non cancellarle mai).
    """
    try:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM characters WHERE world_id = ? ORDER BY updated_at DESC",
            (world_id,),
        ).fetchall()
        conn.close()
        return [_row_to_character(r) for r in rows]
    except Exception as e:
        logger.error(f"Errore get_all_instances_of_world({world_id!r}): {e}")
        return []


def get_master_visible_characters(world_id: str = "") -> list[Character]:
    """
    Personaggi rilevanti per il contesto correntemente selezionato nella
    Modalità Master (2026-08-06) — fix di due bug segnalati da Davide con
    un'unica causa: i picker personaggi della Sezione Master (Tesoro,
    Oggetto Magico, Bottino, partecipanti a un Incontro) chiamavano
    `get_all()`, che non ha mai filtrato per mondo.

    A differenza di `get_all()` (usato da `HomeView`, che mostra insieme
    personaggi locali E istanze, partizionati in sezioni distinte), qui i due
    insiemi sono SEMPRE mutuamente esclusivi, in base al mondo che il Master
    sta correntemente gestendo:

    - `world_id == ""` ("Nessun mondo" / modalità locale, default): solo i
      personaggi locali (`characters.world_id == ''`). Le istanze di
      QUALSIASI mondo restano escluse — risolve "in Master escono i
      personaggi di ogni mondo mescolati".
    - `world_id` valorizzato: solo le istanze DI QUEL mondo
      (`characters.world_id == world_id`). L'originale locale da cui
      un'istanza è nata non compare mai accanto alla sua istanza — risolve
      "il player entrato in un mondo appare duplicato".
    """
    try:
        conn = get_connection()
        if world_id:
            # world_instance_archived (2026-08-07, §7): un'istanza il cui
            # proprietario è stato espulso dal mondo resta nel DB (non
            # distruttivo, riattivabile — vedi `archive_world_instances()`)
            # ma sparisce dalla Sezione Master, che è esattamente il
            # problema segnalato da Davide ("resta collegato per sempre").
            rows = conn.execute(
                "SELECT * FROM characters WHERE world_id = ? AND world_instance_archived = 0 "
                "ORDER BY updated_at DESC",
                (world_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM characters WHERE world_id = '' ORDER BY updated_at DESC"
            ).fetchall()
        conn.close()
        return [_row_to_character(r) for r in rows]
    except Exception as e:
        logger.error(f"Errore nel recupero personaggi (contesto Master, world_id={world_id!r}): {e}")
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
                exhaustion_level, frenzy_active,
                concentrating_spell, concentrating_since,
                age, height, weight, eyes, skin, hair,
                personality_traits, ideals, bonds, flaws,
                backstory, allies_organizations, additional_traits, appearance_notes,
                world_id, origin_character_id, owner_device_id, is_replica, world_seq,
                world_instance_archived,
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
                :exhaustion_level, :frenzy_active,
                :concentrating_spell, :concentrating_since,
                :age, :height, :weight, :eyes, :skin, :hair,
                :personality_traits, :ideals, :bonds, :flaws,
                :backstory, :allies_organizations, :additional_traits, :appearance_notes,
                :world_id, :origin_character_id, :owner_device_id, :is_replica, :world_seq,
                :world_instance_archived,
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
            "exhaustion_level": character.exhaustion_level,
            "frenzy_active": int(character.frenzy_active),
            "concentrating_spell": character.concentrating_spell or "",
            "concentrating_since": character.concentrating_since or "",
            # Mondi condivisi (2026-08-06 — bug reale trovato mentre si
            # verificava il fix della Modalità Master world-scoped: queste 5
            # colonne esistono su `Character` e sono già scritte da
            # `update()`, ma `create()` non le aveva MAI incluse nell'INSERT,
            # quindi passare un `Character` con `world_id` già valorizzato a
            # `create()` lo perdeva silenziosamente — invisibile finché
            # nessun chiamante lo faceva: l'unico punto di scrittura reale,
            # `core/character_instances.py._link_to_world()`, aggira il
            # problema con un UPDATE separato subito dopo il create(). Corretto
            # qui alla radice per coerenza con `update()` e per non lasciare
            # la trappola per il prossimo chiamante che si aspetti — a
            # ragione — che `create()` persista l'intero oggetto passato.
            "world_id": _s(character.world_id),
            "origin_character_id": _s(character.origin_character_id),
            "owner_device_id": _s(character.owner_device_id),
            "is_replica": int(character.is_replica),
            "world_seq": character.world_seq,
            "world_instance_archived": int(character.world_instance_archived),
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

        # Multiclasse (2026-08-12): riga primaria in character_classes, fonte
        # derivata da characters.class_name/subclass/level — mai il contrario.
        # Senza questo insert un personaggio appena creato in QUESTA sessione
        # (non backfillato da _migrate, che gira solo su characters già
        # esistenti al momento di init_db()) risulterebbe senza classi.
        import uuid as _uuid_mc
        conn.execute(
            """INSERT INTO character_classes
               (id, character_id, class_name, subclass, level, is_primary, order_index)
               VALUES (?, ?, ?, ?, ?, 1, 0)""",
            (str(_uuid_mc.uuid4()), character.id, _s(character.class_name),
             _s(character.subclass), character.level),
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
                exhaustion_level=:exhaustion_level,
                frenzy_active=:frenzy_active,
                concentrating_spell=:concentrating_spell,
                concentrating_since=:concentrating_since,
                world_id=:world_id,
                origin_character_id=:origin_character_id,
                owner_device_id=:owner_device_id,
                is_replica=:is_replica,
                world_seq=:world_seq,
                world_instance_archived=:world_instance_archived,
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
            "exhaustion_level": character.exhaustion_level,
            "frenzy_active": int(character.frenzy_active),
            "concentrating_spell": character.concentrating_spell or "",
            "concentrating_since": character.concentrating_since or "",
            "world_id": _s(character.world_id),
            "origin_character_id": _s(character.origin_character_id),
            "owner_device_id": _s(character.owner_device_id),
            "is_replica": int(character.is_replica),
            "world_seq": character.world_seq,
            "world_instance_archived": int(character.world_instance_archived),
            "updated_at": character.updated_at,
        })
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore nell'aggiornamento del personaggio {character.id}: {e}")
        return False


def archive_world_instances(world_id: str, owner_device_id: str) -> int:
    """
    Archivia (2026-08-07, §7 — vedi `_add_column` in `data/database.py` per
    il ragionamento completo) tutte le istanze di `world_id` possedute da
    `owner_device_id` — chiamata da `core.world_backend._handle_member_kick`
    subito dopo l'espulsione del membro, sull'HOST (autoritativo): NON
    tocca personaggi locali (`world_id == ''` non può mai comparire nel
    filtro) né istanze di altri proprietari.

    Ritorna il numero di righe realmente archiviate (0 se il membro
    espulso non possedeva alcuna istanza in questo mondo, il caso più
    comune — un giocatore "solo spettatore" o il cui personaggio non è
    ancora mai stato creato in quel mondo).

    Riattivabile SOLO tramite una richiesta di rientro approvata dal master
    (2026-08-12, `unarchive_world_instance()` sotto — chiamata unicamente da
    `core/world_backend.py::_handle_character_rejoin_respond`) — MAI in
    automatico al resync: un commento precedente di questa funzione
    affermava il contrario, ma nessun punto del codice lo ha mai
    implementato davvero (verificato con grep sull'intero repo).
    """
    try:
        conn = get_connection()
        cur = conn.execute(
            """UPDATE characters SET world_instance_archived=1, updated_at=?
               WHERE world_id=? AND owner_device_id=? AND world_instance_archived=0""",
            (datetime.now().isoformat(), world_id, owner_device_id),
        )
        conn.commit()
        conn.close()
        return cur.rowcount
    except Exception as e:
        logger.error(f"Errore archive_world_instances: {e}")
        return 0


def archive_world_instance(world_id: str, character_id: str) -> bool:
    """
    Archivia UNA singola istanza di personaggio in un mondo (2026-08-12,
    `CMD_CHARACTER_INSTANCE_REMOVE`) — a differenza di
    `archive_world_instances` sopra (tutte le istanze di un dispositivo,
    chiamata dopo l'espulsione del membro), questa la usa il master per
    rimuovere UN personaggio dal mondo mentre il suo giocatore resta
    membro (es. morte permanente, doppione). Stessa non-distruttività
    già decisa con Davide per l'espulsione: mai `character_repo.delete()`,
    la riga resta nel DB — riattivabile SOLO tramite una richiesta di
    rientro approvata dal master (2026-08-12, vedi `unarchive_world_instance()`
    sotto), esattamente come un'istanza archiviata da un kick, mai in
    automatico.

    Ritorna False se il personaggio non esiste o non appartiene a questo
    mondo (fail-closed, stesso principio dell'handler che la chiama).
    """
    character = get_by_id(character_id)
    if character is None or character.world_id != world_id:
        return False
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE characters SET world_instance_archived=1, updated_at=? WHERE id=?",
            (datetime.now().isoformat(), character_id),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore archive_world_instance({character_id}): {e}")
        return False


def unarchive_world_instance(character_id: str) -> bool:
    """
    Toglie l'archiviazione di UN'istanza (2026-08-12, "Richiesta di
    rientro") — controparte di `archive_world_instance()` sopra. Unico
    punto del codice che scrive `world_instance_archived=0`: chiamato
    SOLO da `core/world_backend.py::_handle_character_rejoin_respond`
    quando il master accetta con `mode="frozen"` (per `mode=
    "refresh_from_local"` la riattivazione è parte della stessa scrittura
    di `character_export.import_character_data_as_world_refresh`, mai qui).

    Nessuna verifica di appartenenza al mondo qui dentro (il chiamante l'ha
    già fatta risolvendo `request.character_id` a un personaggio di questo
    mondo) — stessa scelta di `archive_world_instance`.
    """
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE characters SET world_instance_archived=0, updated_at=? WHERE id=?",
            (datetime.now().isoformat(), character_id),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore unarchive_world_instance({character_id}): {e}")
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
    # Nome di arma specifica (es. "Stocco", "Bastone Ferrato") invece di una
    # categoria — usato da armor_proficiencies/weapon_proficiencies a
    # livello di CLASSE BASE (es. mago.json: Pugnale/Dardo/Fionda/Bastone
    # Ferrato/Balestra Leggera), mai da bonus_proficiencies di sottoclasse
    # finora. Verificato che tutti i nomi usati in questo campo nei 12 file
    # classe risolvono esattamente in equipment/weapons.json (2026-07-16).
    if game_data.get_weapon(entry_name):
        return "weapon"
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


def apply_class_base_proficiencies(character_id: str, class_name: str) -> None:
    """
    Applica le competenze di armatura/arma della CLASSE BASE
    (`armor_proficiencies`/`weapon_proficiencies` in classes/*.json) —
    gap segnalato in CLAUDE.md ("Competenze armatura/armi base-classe mai
    applicate"): questi due campi esistono in tutti e 12 i file classe fin
    dalla prima trascrizione JSON, ma nessun codice li aveva mai letti né
    salvati come `character_proficiencies` — non vanno confusi con
    `bonus_proficiencies` di SOTTOCLASSE (già applicato da
    apply_subclass_bonus_proficiencies(), es. armatura pesante dal Dominio
    della Vita del Chierico), che è un campo diverso a un livello diverso
    del JSON.

    Riusa la stessa infrastruttura già scritta per le sottoclassi
    (classify_bonus_proficiency_entries per separare eventuali entry
    "choice" da quelle fisse, apply_subclass_bonus_proficiencies per il
    salvataggio deduplicato) invece di reimplementare la stessa logica —
    verificato che nei 12 file classe attuali armor_proficiencies/
    weapon_proficiencies sono SEMPRE liste piatte di stringhe (nessuna
    entry "choice" a questo livello, a differenza di tool_proficiencies
    che la usa già ed è gestito a parte da _class_tool_choices() nella UI
    di creazione) — se in futuro un file classe ne introducesse una,
    viene ignorata con un warning invece di far fallire la creazione del
    personaggio su un dato imprevisto.

    Idempotente (via apply_subclass_bonus_proficiencies): sicura da
    richiamare anche come self-healing ad ogni apertura di scheda, per
    backfillare i personaggi creati prima di questo fix (2026-07-16).
    """
    cls_data = game_data.get_class(class_name or "")
    if not cls_data:
        return
    raw_entries = list(cls_data.get("armor_proficiencies", []) or []) + \
                  list(cls_data.get("weapon_proficiencies", []) or [])
    fixed, choices = classify_bonus_proficiency_entries(raw_entries)
    if choices:
        logger.warning(
            "apply_class_base_proficiencies: entry 'choice' inattesa in "
            f"armor/weapon_proficiencies di '{class_name}', ignorata: {choices}"
        )
    apply_subclass_bonus_proficiencies(character_id, fixed)


def resolve_feat_proficiency_choice_pool(proficiency_type: str) -> list[str]:
    """
    Pool di opzioni selezionabili per una entry `{"type":"choice",
    "proficiency_type": ...}` di `proficiency_grants` in feats.json:

    - "skill"         -> le 18 abilità PHB (config.settings.SKILLS)
    - "tool"          -> tutti gli strumenti PHB (equipment/tools.json)
    - "skill_or_tool" -> unione delle due liste sopra (es. Abile — "una
      qualsiasi combinazione di abilità O strumenti")
    - "weapon"        -> tutte le armi PHB (equipment/weapons.json,
      qualunque categoria — "un'arma semplice o un'arma da guerra" del
      PHB copre già l'intero catalogo)
    - "language"      -> tutte le lingue PHB (config.settings.LANGUAGES)

    Ritorna lista vuota per un proficiency_type non riconosciuto, mai
    un'eccezione.
    """
    from config.settings import SKILLS, LANGUAGES
    if proficiency_type == "skill":
        return list(SKILLS.keys())
    if proficiency_type == "tool":
        return game_data.get_all_tool_names()
    if proficiency_type == "skill_or_tool":
        return list(SKILLS.keys()) + game_data.get_all_tool_names()
    if proficiency_type == "weapon":
        return game_data.get_weapon_names()
    if proficiency_type == "language":
        return list(LANGUAGES)
    return []


def apply_feat_proficiency_grants(
    character_id: str,
    feat_name: str,
    choice_values: list[str] | None = None,
    save_ability_key: str = "",
) -> list[dict]:
    """
    Applica le competenze concesse da un talento (`proficiency_grants` in
    feats.json) — sia fisse (armor/weapon con nome esplicito, es. Corazze
    Leggere/Lottatore da Taverna) sia a scelta del giocatore (skill/tool/
    weapon/language/skill_or_tool: `choice_values` contiene i valori già
    scelti dalla UI, nello stesso ordine e stesso conteggio complessivo
    delle entry "choice" del talento).

    Applica anche la competenza nel tiro salvezza se il talento ha
    `ability_bonus.grants_save_proficiency` (es. Resiliente) —
    `save_ability_key` è la chiave caratteristica scelta/fissa ("str".."cha"),
    già risolta dal chiamante.

    Idempotente: non duplica competenze già possedute dal personaggio
    (stesso controllo (proficiency_type, name) già usato da
    apply_subclass_bonus_proficiencies()).

    Ritorna la lista delle competenze EFFETTIVAMENTE aggiunte in questa
    chiamata, come [{"type": proficiency_type, "name": nome}, ...] — da
    salvare in bonus_data["granted_proficiencies"] del talento, così una
    futura rimozione (remove_feat_with_bonuses()/undo_level()) sa
    esattamente quali righe eliminare senza toccare una competenza
    identica posseduta per un'altra ragione (es. già data dalla classe).
    """
    fd = game_data.get_feat(feat_name) or {}
    grants = fd.get("proficiency_grants", []) or []
    choice_values = list(choice_values or [])

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
        logger.error(f"Errore lettura competenze esistenti per talento '{feat_name}': {e}")
        existing = set()

    granted: list[dict] = []
    choice_idx = 0

    def _add(ptype: str, name: str) -> None:
        if not name or (ptype, name) in existing:
            return
        if _save_single_proficiency(character_id, ptype, name):
            granted.append({"type": ptype, "name": name})
            existing.add((ptype, name))

    from config.settings import SKILLS

    for grant in grants:
        gtype = grant.get("proficiency_type", "")
        if grant.get("type") == "fixed":
            _add(gtype, grant.get("name", ""))
        elif grant.get("type") == "choice":
            count = int(grant.get("count", 0) or 0)
            for _ in range(count):
                if choice_idx >= len(choice_values):
                    break
                value = choice_values[choice_idx]
                choice_idx += 1
                if not value:
                    continue
                ptype = ("skill" if value in SKILLS else "tool") if gtype == "skill_or_tool" else gtype
                _add(ptype, value)

    if save_ability_key:
        from config.settings import ABILITY_SCORES, ABILITY_KEYS
        try:
            save_name = ABILITY_SCORES[ABILITY_KEYS.index(save_ability_key)]
        except (ValueError, IndexError):
            save_name = save_ability_key
        _add("save", save_name)

    return granted


def get_feat_names_at_level(character_id: str, level: int) -> list[str]:
    """
    Nomi dei talenti (proficiency_type='feat') acquisiti esattamente al
    livello indicato (level_obtained == level) — usato per calcolare il
    delta PF di talenti con hp_bonus_per_level (es. Robusto) quando si
    rimuove un livello (do_level_down), PRIMA di chiamare undo_level()
    (che elimina la riga) — stesso pattern già in uso per il bonus PF di
    classe (get_permanent_class_hp_bonus), calcolato in profilo_tab.py
    nello scope che racchiude do_level_down, non dentro undo_level stesso.
    """
    try:
        conn = get_connection()
        rows = conn.execute(
            "SELECT name FROM character_proficiencies "
            "WHERE character_id=? AND proficiency_type='feat' AND level_obtained=?",
            (character_id, level),
        ).fetchall()
        conn.close()
        return [r["name"] for r in rows]
    except Exception as e:
        logger.error(f"Errore get_feat_names_at_level({level}) per {character_id}: {e}")
        return []


def undo_level(character_id: str, level_removed: int) -> bool:
    """
    Inverte tutti i bonus (feat e ASI) acquisiti al livello `level_removed`.

    Legge le righe con level_obtained == level_removed e proficiency_type in
    ('feat', 'asi_record'), quindi:
    - per ogni riga con bonus_data: applica l'inverso su characters
    - rimuove le competenze concesse dal talento (bonus_data["granted_proficiencies"],
      es. Abile/Corazze Leggere/Maestro d'Armi — 2026-07-16)
    - elimina le righe

    Il bonus PF permanente per-livello di eventuali talenti con
    hp_bonus_per_level (es. Robusto) NON è gestito qui — va calcolato dal
    chiamante (profilo_tab.py -> do_level_down) PRIMA di questa chiamata,
    tramite get_feat_names_at_level()+get_feats_permanent_hp_bonus(), stesso
    identico pattern già in uso per il bonus PF di classe (calcolato nello
    scope che racchiude do_level_down, non dentro undo_level).

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

            # Rimuove le competenze concesse dal talento (proficiency_grants),
            # es. le 3 abilità/strumenti di Abile o le 4 armi di Maestro d'Armi.
            for g in stored.get("granted_proficiencies", []) or []:
                gtype, gname = g.get("type"), g.get("name")
                if gtype and gname:
                    conn.execute(
                        "DELETE FROM character_proficiencies "
                        "WHERE character_id=? AND proficiency_type=? AND name=?",
                        (character_id, gtype, gname),
                    )

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
        {"ability": {"str": 1, "cha": 1}, "other": {"initiative": 5, "speed": 3},
         "granted_proficiencies": [{"type": "armor", "name": "leggere"}, ...]}

    Chiavi 'other' supportate:
        "initiative" → characters.initiative_bonus
        "speed"      → characters.speed

    Oltre alla ricevuta ability/other/granted_proficiencies (2026-07-16,
    stesso schema già in uso per i talenti scelti all'ASI), rimuove anche il
    bonus PF permanente per-livello di talenti con hp_bonus_per_level (es.
    Robusto: 2×livello) — a differenza di undo_level() (dove questo delta è
    calcolato dal chiamante in profilo_tab.py, perché lì serve confrontare
    due LIVELLI diversi), qui il livello non cambia: la funzione legge da
    sola characters.level/hp_max/hp_current e ricalcola il delta tra "prima"
    (talento posseduto) e "dopo" (rimosso) allo stesso livello, dato che è
    l'unico punto che tocca già la tabella characters per la reversione
    ability/other.
    """
    try:
        conn = get_connection()

        # Legge la ricevuta del talento
        row = conn.execute(
            "SELECT bonus_data FROM character_proficiencies "
            "WHERE character_id=? AND proficiency_type='feat' AND name=?",
            (character_id, feat_name),
        ).fetchone()

        granted_profs: list[dict] = []
        if row and row["bonus_data"]:
            try:
                stored = json.loads(row["bonus_data"])
            except (json.JSONDecodeError, TypeError):
                stored = {}

            ability_changes: dict = stored.get("ability", {})
            other_changes: dict  = stored.get("other", {})
            granted_profs = stored.get("granted_proficiencies", []) or []

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

        # Rimuove le competenze concesse dal talento (proficiency_grants)
        for g in granted_profs:
            gtype, gname = g.get("type"), g.get("name")
            if gtype and gname:
                conn.execute(
                    "DELETE FROM character_proficiencies "
                    "WHERE character_id=? AND proficiency_type=? AND name=?",
                    (character_id, gtype, gname),
                )

        # Bonus PF permanente per-livello (es. Robusto) — ricalcola il delta
        # usando i talenti posseduti PRIMA e DOPO la rimozione, allo stesso
        # livello attuale del personaggio (il livello non cambia qui).
        char_row = conn.execute(
            "SELECT level, hp_max, hp_current FROM characters WHERE id=?",
            (character_id,),
        ).fetchone()
        if char_row:
            lvl = char_row["level"]
            feats_before = [
                r["name"] for r in conn.execute(
                    "SELECT name FROM character_proficiencies "
                    "WHERE character_id=? AND proficiency_type='feat'",
                    (character_id,),
                ).fetchall()
            ]
            feats_after = [n for n in feats_before if n != feat_name]
            from config.settings import get_feats_permanent_hp_bonus
            hp_delta = (
                get_feats_permanent_hp_bonus(feats_after, lvl)
                - get_feats_permanent_hp_bonus(feats_before, lvl)
            )
            if hp_delta:
                new_hp_max = max(1, char_row["hp_max"] + hp_delta)
                new_hp_current = max(0, min(char_row["hp_current"], new_hp_max))
                conn.execute(
                    "UPDATE characters SET hp_max=?, hp_current=? WHERE id=?",
                    (new_hp_max, new_hp_current, character_id),
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
# Multiclasse (PHB IT cap.6, p.163-165 — vedi dnd_app/docs/multiclasse_design.md)
#
# characters.class_name/subclass/level restano SEMPRE la classe primaria (1°
# livello) e il livello TOTALE del personaggio — mai una stringa composita,
# mai derivati da qui. Questa tabella è puramente ADDITIVA: un personaggio a
# classe singola ha esattamente una riga qui (is_primary=1, backfillata dalla
# migrazione in data/database.py per ogni personaggio pre-esistente) e si
# comporta byte-per-byte come prima di questa feature.
# ---------------------------------------------------------------------------

def get_character_classes(character_id: str) -> list[CharacterClass]:
    """Tutte le classi del personaggio, ordinate per order_index (ordine di acquisizione)."""
    try:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM character_classes WHERE character_id=? ORDER BY order_index ASC",
            (character_id,),
        ).fetchall()
        conn.close()
    except Exception as e:
        logger.error(f"Errore lettura character_classes per {character_id}: {e}")
        return []
    return [
        CharacterClass(
            id=row["id"], character_id=row["character_id"],
            class_name=row["class_name"], subclass=row["subclass"] or "",
            level=row["level"], is_primary=bool(row["is_primary"]),
            order_index=row["order_index"],
        )
        for row in rows
    ]


def get_primary_character_class(character_id: str) -> CharacterClass | None:
    """La classe primaria (1° livello) del personaggio, o None se non ancora migrato."""
    for cc in get_character_classes(character_id):
        if cc.is_primary:
            return cc
    return None


def character_has_class(character_id: str, class_name: str) -> bool:
    """True se il personaggio ha almeno un livello nella classe indicata (case-insensitive)."""
    target = (class_name or "").strip().lower()
    if not target:
        return False
    return any(
        cc.class_name.strip().lower() == target
        for cc in get_character_classes(character_id)
    )


def get_class_display_string(character_id: str, fallback_class_name: str = "") -> str:
    """
    Stringa composita per la UI, es. "Guerriero 3 / Ladro 2" — calcolata
    SEMPRE a runtime da character_classes, mai salvata su characters.
    class_name resta un'etichetta singola. Ordine: order_index (acquisizione).
    Se il personaggio ha una sola classe, ritorna "NomeClasse Livello" (stessa
    forma di sempre, nessuna barra). fallback_class_name copre il caso limite
    di un personaggio non ancora migrato (nessuna riga): usa direttamente
    characters.class_name/level passati dal chiamante.
    """
    classes = get_character_classes(character_id)
    if not classes:
        return fallback_class_name or ""
    return " / ".join(f"{cc.class_name} {cc.level}" for cc in classes)


def add_character_class(
    character_id: str, class_name: str, subclass: str = "",
    level: int = 1, is_primary: bool = False,
) -> str:
    """
    Aggiunge una nuova classe al personaggio (prima volta che prende un
    livello in `class_name`). Non tocca characters.class_name/subclass/level:
    quelli restano quelli della classe primaria, aggiornati a parte da chi
    orchestrata il level-up. Ritorna l'id della nuova riga.
    """
    import uuid
    new_id = str(uuid.uuid4())
    existing = get_character_classes(character_id)
    order_index = len(existing)
    try:
        conn = get_connection()
        conn.execute(
            """INSERT INTO character_classes
               (id, character_id, class_name, subclass, level, is_primary, order_index)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (new_id, character_id, class_name, subclass or "", level,
             1 if is_primary else 0, order_index),
        )
        conn.commit()
        conn.close()
        logger.info(f"Nuova classe multiclasse: {class_name} Lv{level} su {character_id}")
    except Exception as e:
        logger.error(f"Errore add_character_class {character_id}/{class_name}: {e}")
    return new_id


def set_character_class_level(character_classes_id: str, new_level: int) -> bool:
    """Aggiorna il livello di UNA riga character_classes (level-up/level-down su quella classe)."""
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE character_classes SET level=?, updated_at=datetime('now') WHERE id=?",
            (new_level, character_classes_id),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore set_character_class_level {character_classes_id}: {e}")
        return False


def set_character_class_subclass(character_classes_id: str, subclass: str) -> bool:
    """
    Aggiorna la sottoclasse di UNA riga character_classes — controparte di
    `set_character_class_level()` per il selettore "quale classe sale?" del
    level-up (2026-08-12): una classe SECONDARIA che sceglie la sottoclasse
    in questo level-up la salva qui, mai su `characters.subclass` (che resta
    sempre quella della classe primaria, vedi `CharacterClass` in
    data/models.py).
    """
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE character_classes SET subclass=?, updated_at=datetime('now') WHERE id=?",
            (subclass or "", character_classes_id),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore set_character_class_subclass {character_classes_id}: {e}")
        return False


def sync_character_total_level(character_id: str) -> int:
    """
    Riallinea characters.level alla SOMMA dei livelli in character_classes
    (PHB IT p.163: "i livelli in tutte le sue classi, sommati assieme,
    determinano il suo livello di personaggio"). Va richiamata dopo ogni
    level-up/level-down/aggiunta/rimozione di una classe, PRIMA di
    ricalcolare bonus competenza/CA/altro che dipendono dal livello totale
    (già tutti corretti perché leggono characters.level, vedi
    multiclasse_design.md §3 punto 2). Ritorna il nuovo livello totale, 0 se
    il personaggio non ha ancora classi (non dovrebbe mai succedere).
    """
    total = sum(cc.level for cc in get_character_classes(character_id))
    if total <= 0:
        return 0
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE characters SET level=?, updated_at=datetime('now') WHERE id=?",
            (total, character_id),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Errore sync_character_total_level {character_id}: {e}")
    return total


def remove_character_class(character_classes_id: str) -> bool:
    """
    Rimuove del tutto una riga character_classes (level-down che azzera i
    livelli di quella classe). Non chiamare mai sulla classe primaria mentre
    è l'unica rimasta: la UI deve impedirlo (un personaggio ha sempre almeno
    una classe).
    """
    try:
        conn = get_connection()
        conn.execute("DELETE FROM character_classes WHERE id=?", (character_classes_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore remove_character_class {character_classes_id}: {e}")
        return False


_ABILITY_SCORE_FIELDS = {
    "forza": "str_score", "destrezza": "dex_score", "costituzione": "con_score",
    "intelligenza": "int_score", "saggezza": "wis_score", "carisma": "cha_score",
}


def check_multiclass_prerequisites(
    character: "Character", new_class_name: str
) -> tuple[bool, list[str]]:
    """
    Verifica i prerequisiti di caratteristica per prendere `new_class_name`
    in multiclasse (PHB IT p.163): il personaggio deve soddisfarli sia per
    OGNI classe che possiede già, sia per quella nuova. Ogni classe elenca le
    sue opzioni in OR (es. Guerriero: Forza 13 OPPURE Destrezza 13) — vedi
    game_data.get_multiclass_prerequisites().

    Ritorna (True, []) se tutti i requisiti sono soddisfatti, altrimenti
    (False, [descrizioni leggibili di ogni requisito NON soddisfatto]) — solo
    ADVISORY: nessuna funzione di questo progetto blocca un'azione di gioco
    per un valore PHB non soddisfatto (stesso principio degli altri override
    in `characters`, es. proficiency_bonus_override); la UI mostra
    l'avviso e lascia decidere al tavolo se procedere comunque (house rule).
    """
    classes_to_check = [cc.class_name for cc in get_character_classes(character.id)]
    if new_class_name not in classes_to_check:
        classes_to_check.append(new_class_name)

    failures: list[str] = []
    for class_name in classes_to_check:
        options = game_data.get_multiclass_prerequisites(class_name)
        if not options:
            continue
        satisfied = False
        for option in options:
            if all(
                getattr(character, _ABILITY_SCORE_FIELDS.get(ability, ""), 0) >= minimum
                for ability, minimum in option
            ):
                satisfied = True
                break
        if not satisfied:
            option_descriptions = " OPPURE ".join(
                " e ".join(f"{ability.capitalize()} {minimum}" for ability, minimum in option)
                for option in options
            )
            failures.append(f"{class_name}: richiede {option_descriptions}")
    return (len(failures) == 0, failures)


def apply_multiclass_proficiencies(character_id: str, class_name: str) -> None:
    """
    Applica le competenze RIDOTTE ottenute prendendo `class_name` in
    multiclasse (PHB IT p.164, tabella "Competenze dei Multiclasse") — MAI
    quelle complete di apply_class_base_proficiencies() (quella resta solo
    per la classe primaria, presa a creazione). Le entry "choice" (skill/
    strumento a scelta) vanno risolte dalla UI PRIMA di questa chiamata
    (stesso pattern di apply_subclass_bonus_proficiencies): `choice_values`
    è la lista dei valori scelti, nello stesso ordine delle entry "choice"
    restituite da game_data.get_multiclass_proficiency_entries().
    """
    entries = game_data.get_multiclass_proficiency_entries(class_name)
    fixed, _choices = classify_bonus_proficiency_entries(entries)
    apply_subclass_bonus_proficiencies(character_id, fixed)


def resolve_multiclass_choice_options(entry: dict, class_name: str) -> list[str]:
    """
    Risolve il pool di opzioni per una entry "choice" di
    get_multiclass_proficiency_entries(): "any_skill" -> le 18 abilità PHB
    (riusa resolve_bonus_proficiency_choice_options), "own_class_skill_list"
    -> la lista di abilità della classe STESSA presa in multiclasse (letta da
    classes/*.json skill_choices.options, mai duplicata nel dato multiclasse
    per non rischiare disallineamento), "strumenti_musicali"/altra categoria
    tool -> game_data.get_tool_names(categoria).
    """
    src = entry.get("from")
    if src == "any_skill":
        return resolve_bonus_proficiency_choice_options({"from": "any_skill"})
    if src == "own_class_skill_list":
        cls_data = game_data.get_class(class_name) or {}
        return list((cls_data.get("skill_choices") or {}).get("options") or [])
    if isinstance(src, str) and src:
        return game_data.get_tool_names(src)
    return []


def apply_multiclass_proficiency_choices(
    character_id: str, class_name: str, choice_values: list[str]
) -> None:
    """
    Applica le entry "choice" già risolte dalla UI (abilità/strumento scelti
    dal giocatore prendendo `class_name` in multiclasse) — controparte di
    apply_multiclass_proficiencies() per le entry fisse. `choice_values` deve
    avere la stessa lunghezza/ordine delle entry "choice" restituite da
    get_multiclass_proficiency_entries(class_name).
    """
    if not choice_values:
        return
    apply_subclass_bonus_proficiencies(character_id, [v for v in choice_values if v])


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


def sync_multiclass_spell_slots(character_id: str) -> bool:
    """
    Aggiorna gli slot incantesimo "Incantesimi" condivisi (PHB IT p.164) per
    un personaggio con PIÙ DI UNA classe — chiamare questa, non
    auto_init_spell_slots(), quando get_character_classes(character_id) ha
    più di una riga (l'orchestrazione del level-up decide quale delle due
    chiamare, vedi multiclasse_design.md §1).

    Somma i livelli in TUTTE le classi da incantatore "full" (Bardo,
    Chierico, Druido, Mago, Stregone) e metà (arrotondati per difetto) dei
    livelli nelle classi "half" (Paladino, Ranger) — PHB IT p.164, "Slot
    Incantesimo" — poi guarda la tabella "Incantatore Multiclasse"
    (identica a full_caster, vedi get_multiclass_spell_slot_table()).

    LIMITE NOTO E DOCUMENTATO (non un bug dimenticato): il Warlock è
    escluso da questa somma (i suoi slot del Patto sono SEMPRE separati dal
    pool condiviso, PHB IT p.164 "Magia del Patto") — ma lo schema attuale
    di `spell_slots` ha UNA sola riga per (character_id, slot_level), senza
    una colonna per distinguere i due pool. Per un personaggio che ha SIA
    Warlock SIA un'altra classe da incantatore, questa funzione scrive solo
    il pool condiviso (corretto) ma NON scrive più i suoi slot del Patto
    separati (che restano a 0) — richiederebbe un secondo pool nello
    schema/UI, esplicitamente fuori scope in questo giro (vedi
    multiclasse_design.md §3 punto 5). Un Warlock a classe SINGOLA non è
    toccato da questa funzione (auto_init_spell_slots() resta il percorso
    per un personaggio con una sola classe, invariato).

    Non tocca gli slot terzo-incantatore di Mistificatore Arcano/Cavaliere
    Mistico (init_borrowed_caster_slots(), percorso indipendente) — la loro
    somma nel pool multiclasse è un altro limite noto della stessa origine,
    stesso motivo (§3 punto 4 del design doc).
    """
    classes = get_character_classes(character_id)
    caster_level = 0.0
    has_warlock = False
    for cc in classes:
        caster_type = game_data.get_caster_type(cc.class_name)
        if caster_type == "full":
            caster_level += cc.level
        elif caster_type == "half":
            caster_level += cc.level / 2
        elif caster_type == "pact":
            has_warlock = True

    table = game_data.get_multiclass_spell_slot_table()
    lv_idx = max(0, min(int(caster_level) - 1, 19)) if caster_level >= 1 else -1
    slots = table[lv_idx] if lv_idx >= 0 and table else [0] * 9

    if has_warlock and int(caster_level) > 0:
        logger.warning(
            "sync_multiclass_spell_slots: %s ha Warlock + un'altra classe da "
            "incantatore — pool condiviso aggiornato (%s), slot del Patto "
            "NON tracciati separatamente in questa versione (limite noto, "
            "vedi multiclasse_design.md §3 punto 5)", character_id, slots,
        )

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
        logger.info("Slot multiclasse auto-init: %s livello incantatore %s → %s",
                     character_id, caster_level, slots)
        return True
    except Exception as e:
        logger.error(f"Errore sync_multiclass_spell_slots {character_id}: {e}")
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
                weapon_category=r["weapon_category"] or "" if "weapon_category" in r.keys() else "",
                proficiency_override=bool(r["proficiency_override"]) if "proficiency_override" in r.keys() else False,
                finesse_ability=r["finesse_ability"] or "" if "finesse_ability" in r.keys() else "",
                attack_total_override=bool(r["attack_total_override"]) if "attack_total_override" in r.keys() else False,
                attack_override_value=r["attack_override_value"] or 0 if "attack_override_value" in r.keys() else 0,
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
                requires_attunement=bool(_col(r, "requires_attunement")),
                is_attuned=bool(_col(r, "is_attuned")),
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
                  grip_two_handed: bool = False,
                  weapon_category: str = "",
                  proficiency_override: bool = False,
                  finesse_ability: str = "",
                  attack_total_override: bool = False,
                  attack_override_value: int = 0) -> bool:
    """Crea una nuova arma per il personaggio.

    versatile_damage_dice/grip_two_handed: dado danno a due mani e stato
    dell'impugnatura per le armi con proprietà "Versatile" (PHB p.149) —
    vedi il docstring di core/equipment_manager.py per i dettagli meccanici.

    weapon_category/proficiency_override/finesse_ability/
    attack_total_override/attack_override_value: calcolo automatico del
    tiro per colpire (2026-07-17) — vedi core/weapon_calculator.py e
    CLAUDE.md.
    """
    import uuid as _uuid
    try:
        conn = get_connection()
        conn.execute(
            """INSERT INTO weapons
               (id, character_id, name, damage_dice, damage_type, attack_bonus,
                damage_bonus, properties, is_magical, magic_description,
                is_equipped, range_normal, range_max, magic_damages,
                versatile_damage_dice, grip_two_handed, weapon_category,
                proficiency_override, finesse_ability, attack_total_override,
                attack_override_value)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (str(_uuid.uuid4()), character_id, name, damage_dice, damage_type,
             attack_bonus, damage_bonus, properties, int(is_magical),
             magic_description, int(is_equipped), range_normal, range_max, magic_damages,
             versatile_damage_dice, int(grip_two_handed), weapon_category,
             int(proficiency_override), finesse_ability, int(attack_total_override),
             attack_override_value)
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
                  grip_two_handed: bool = False,
                  weapon_category: str = "",
                  proficiency_override: bool = False,
                  finesse_ability: str = "",
                  attack_total_override: bool = False,
                  attack_override_value: int = 0) -> bool:
    """Aggiorna un'arma esistente."""
    try:
        conn = get_connection()
        conn.execute(
            """UPDATE weapons SET name=?, damage_dice=?, damage_type=?,
               attack_bonus=?, damage_bonus=?, properties=?, is_equipped=?,
               is_magical=?, magic_description=?, range_normal=?, range_max=?,
               magic_damages=?, versatile_damage_dice=?, grip_two_handed=?,
               weapon_category=?, proficiency_override=?, finesse_ability=?,
               attack_total_override=?, attack_override_value=?
               WHERE id=?""",
            (name, damage_dice, damage_type, attack_bonus, damage_bonus,
             properties, int(is_equipped), int(is_magical), magic_description,
             range_normal, range_max, magic_damages,
             versatile_damage_dice, int(grip_two_handed), weapon_category,
             int(proficiency_override), finesse_ability, int(attack_total_override),
             attack_override_value, weapon_id)
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
                          effects: str = "",
                          requires_attunement: bool = False) -> str | None:
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
                category, is_equipped, ca_value, armor_type, effects,
                requires_attunement, is_attuned)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (new_id, character_id, name, quantity, weight,
             description, category, int(is_equipped), ca_value, armor_type, effects,
             int(requires_attunement), 0)
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
                          effects: str = "",
                          requires_attunement: bool | None = None) -> bool:
    """
    Aggiorna un oggetto dell'inventario.

    `requires_attunement=None` lascia il valore invariato: i chiamanti storici
    non lo passano e non devono azzerarlo senza volerlo.
    """
    try:
        conn = get_connection()
        conn.execute(
            """UPDATE inventory_items SET name=?, quantity=?, weight=?,
               description=?, category=?, is_equipped=?,
               ca_value=?, armor_type=?, effects=?,
               requires_attunement=COALESCE(?, requires_attunement)
               WHERE id=?""",
            (name, quantity, weight, description, category, int(is_equipped),
             ca_value, armor_type, effects,
             None if requires_attunement is None else int(requires_attunement),
             item_id)
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


def update_exhaustion_level(character_id: str, value: int) -> bool:
    """
    Salva il livello di Indebolimento (Exhaustion), 0-6, PHB IT — condizione
    cumulativa (vedi config/settings.py → EXHAUSTION_LEVELS per gli effetti
    testuali di ciascun livello). Clampato qui, non solo lato UI, per
    proteggere anche eventuali futuri chiamanti non-UI (stesso principio già
    applicato altrove nel repository, es. update_death_saves).
    """
    value = max(0, min(6, value))
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE characters SET exhaustion_level=?, updated_at=? WHERE id=?",
            (value, datetime.now().isoformat(), character_id),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore update_exhaustion_level: {e}")
        return False


def update_frenzy_state(character_id: str, active: bool) -> bool:
    """
    Dichiara (o annulla) la Frenesia per l'ira in corso (Barbaro, Cammino del
    Berserker) — non applica di per sé alcun effetto: solo la fine dell'ira
    frenetica infligge Indebolimento (vedi end_frenzy_rage() sotto). Usata sia
    per "Dichiara Frenesia" (active=True) sia per "Annulla dichiarazione"
    (active=False, es. per correggere un click accidentale senza subire il
    livello di Indebolimento).
    """
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE characters SET frenzy_active=?, updated_at=? WHERE id=?",
            (int(active), datetime.now().isoformat(), character_id),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore update_frenzy_state: {e}")
        return False


def end_frenzy_rage(character_id: str, current_exhaustion: int) -> int | None:
    """
    Termina un'ira in Frenesia (Barbaro, Cammino del Berserker): azzera il
    flag frenzy_active e applica automaticamente +1 Indebolimento (clampato a
    6), PHB IT — "Quando la sua ira termina, il barbaro subisce un livello
    di indebolimento." Operazione atomica (unica connessione/commit): un
    fallimento a metà lascerebbe il personaggio con la frenesia già "chiusa"
    ma senza il livello di Indebolimento corrispondente, o viceversa.
    Restituisce il nuovo livello di Indebolimento, o None in caso di errore
    (nessuna scrittura viene applicata).
    """
    new_level = max(0, min(6, current_exhaustion + 1))
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE characters SET frenzy_active=0, exhaustion_level=?, updated_at=? WHERE id=?",
            (new_level, datetime.now().isoformat(), character_id),
        )
        conn.commit()
        conn.close()
        return new_level
    except Exception as e:
        logger.error(f"Errore end_frenzy_rage: {e}")
        return None


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

    Multiclasse (2026-08-12): le risorse di classe non si fondono MAI tra
    classi diverse (Rage del Barbaro e Ki del Monaco restano due pool
    distinti anche sullo stesso personaggio) — ma la strategia di rimozione
    sopra è un "replace totale" per nome, quindi chiamarla una volta per
    classe cancellerebbe le risorse delle altre classi ad ogni ri-sync. Se
    il personaggio ha righe in `character_classes`, i default si calcolano
    come UNIONE su TUTTE le sue classi (ciascuna col proprio livello, non
    il totale — get_class_resource_defaults già lo richiede), non solo su
    `class_name`/`level` passati. Fallback ai parametri passati se non c'è
    ancora nessuna riga (caso limite: replica non ancora sincronizzata via
    character_classes, mai dovrebbe succedere dopo create()/migrazione, ma
    non deve mai sollevare un'eccezione su questo).
    """
    import uuid as _uuid
    from config.settings import get_class_resource_defaults, get_race_resource_defaults
    try:
        # Risorse di classe — unione su tutte le classi possedute (multiclasse)
        owned_classes = get_character_classes(character_id)
        if owned_classes:
            defaults = []
            for cc in owned_classes:
                defaults += get_class_resource_defaults(cc.class_name, cc.level, character)
        else:
            defaults = get_class_resource_defaults(class_name, level, character)

        # Risorse razziali (aggiunte allo stesso pool) — sul livello TOTALE,
        # mai su quello di una singola classe (nessuna feature razziale PHB
        # dipende dal livello di classe).
        race_name  = getattr(character, "race",    "") or "" if character else ""
        subrace    = getattr(character, "subrace", "") or "" if character else ""
        race_defaults = get_race_resource_defaults(race_name, subrace, level)
        defaults = defaults + race_defaults

        # Multiclasse: due classi possono concedere una risorsa OMONIMA
        # (es. Incanalare Divinità di Chierico e Paladino — PHB IT p.164:
        # "non ottiene un utilizzo aggiuntivo", il pool resta UNO). Tiene il
        # conteggio più alto tra le classi che la concedono, non l'ultimo
        # della lista — approssimazione onesta e documentata: il PHB non è
        # semplicemente "il massimo dei due", ma un pool unico crescente per
        # soglie di classe che nessuna delle 12 classi PHB fa scattare in un
        # ordine ambiguo abbastanza da giustificare la complessità di una
        # tabella dedicata per questo solo incrocio Chierico/Paladino.
        if len(defaults) > len(set(d["name"] for d in defaults)):
            by_name: dict[str, dict] = {}
            for d in defaults:
                prev = by_name.get(d["name"])
                if prev is None or d["max_value"] > prev["max_value"]:
                    by_name[d["name"]] = d
            defaults = list(by_name.values())

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
        reactions=d.get("reactions", "[]"),
        legendary_actions=d.get("legendary_actions", "[]"),
        lair_actions_intro=d.get("lair_actions_intro", ""),
        lair_actions=d.get("lair_actions", "[]"),
        regional_effects_label=d.get("regional_effects_label", ""),
        regional_effects_intro=d.get("regional_effects_intro", ""),
        regional_effects=d.get("regional_effects", "[]"),
        variant_rules=d.get("variant_rules", "[]"),
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
    reactions: str = "[]",
    legendary_actions: str = "[]",
    lair_actions_intro: str = "",
    lair_actions: str = "[]",
    regional_effects_label: str = "",
    regional_effects_intro: str = "",
    regional_effects: str = "[]",
    variant_rules: str = "[]",
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
                senses, languages, traits, actions, reactions, legendary_actions,
                lair_actions_intro, lair_actions,
                regional_effects_label, regional_effects_intro, regional_effects,
                variant_rules,
                is_active, notes, source_page, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            entry_id, character_id, entry_type, name, creature_type, alignment, cr,
            ac, ac_note, hp_max, hp_formula, hp_max,  # hp_current = hp_max inizialmente
            speed, str_score, dex_score, con_score, int_score, wis_score, cha_score,
            saving_throws, skills,
            damage_vulnerabilities, damage_resistances, damage_immunities, condition_immunities,
            senses, languages, traits, actions, reactions, legendary_actions,
            lair_actions_intro, lair_actions,
            regional_effects_label, regional_effects_intro, regional_effects,
            variant_rules,
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


# ---------------------------------------------------------------------------
# Concentrazione (Fase 4, feature 2a — PHB p.203-204)
# ---------------------------------------------------------------------------


def set_concentration(character_id: str, spell_name: str) -> bool:
    """
    Attiva la concentrazione su un incantesimo, sostituendo quella eventuale.

    PHB p.203: "L'incantatore perde la concentrazione su un incantesimo se
    lancia un altro incantesimo che richiede concentrazione. Un incantatore non
    può concentrarsi su due incantesimi alla volta." — per questo la scrittura
    sovrascrive sempre, senza controllare cosa c'era prima: è l'avviso in UI a
    dire al giocatore che la prima si interrompe.
    """
    try:
        now = datetime.now().isoformat()
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE characters SET concentrating_spell=?, concentrating_since=?, "
                "updated_at=? WHERE id=?",
                (spell_name or "", now if spell_name else "", now, character_id),
            )
            conn.commit()
        finally:
            conn.close()
        return True
    except Exception as e:
        logger.error(f"Impossibile impostare la concentrazione: {e}")
        return False


def clear_concentration(character_id: str) -> bool:
    """Interrompe la concentrazione (volontariamente o per una delle cause PHB)."""
    return set_concentration(character_id, "")


def add_xp(character_id: str, delta: int) -> int | None:
    """
    Somma punti esperienza a un personaggio e ritorna il nuovo totale.

    Nata come l'assegnazione PE lato master (Fase 4, feature 4b, autorizzata
    esplicitamente da Davide il 2026-07-30), sempre preceduta da un dialog di
    conferma che mostra chi riceve quanto. Dal passo 6 del Multiplayer
    (2026-08-06) è anche la funzione applicata da
    `core/world_backend._handle_xp_grant` quando il bersaglio è un'istanza di
    un mondo condiviso: non più l'unica scrittura del master su un personaggio
    giocante (vedi gli altri handler in quel modulo per danno/cura/
    condizioni/risorse/abilità/incantesimi bonus/diario), ma resta l'unico
    punto che tocca `characters.xp` — nessuna logica duplicata altrove.

    Il livello NON viene toccato: sale il giocatore dalla propria scheda, dove
    sceglie HP/ASI/incantesimi. L'app mostra solo il badge "Sali di Livello"
    che già esiste.
    """
    try:
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT xp FROM characters WHERE id=?", (character_id,)
            ).fetchone()
            if row is None:
                logger.error(f"Personaggio inesistente per l'assegnazione PE: {character_id}")
                return None
            new_xp = max(0, int(row["xp"] or 0) + int(delta))
            conn.execute(
                "UPDATE characters SET xp=?, updated_at=? WHERE id=?",
                (new_xp, datetime.now().isoformat(), character_id),
            )
            conn.commit()
        finally:
            conn.close()
        return new_xp
    except Exception as e:
        logger.error(f"Assegnazione PE fallita: {e}")
        return None


def set_item_attunement(item_id: str, attuned: bool) -> bool:
    """
    Entra o esce dalla sintonia con un oggetto (DMG p.138).

    I limiti del manuale (massimo 3 oggetti, mai due copie dello stesso) sono
    verificati a monte da `core/equipment_manager.can_attune()`: qui si scrive
    e basta, come per ogni altro setter di questo repository.
    """
    try:
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE inventory_items SET is_attuned=? WHERE id=?",
                (int(attuned), item_id),
            )
            conn.commit()
        finally:
            conn.close()
        return True
    except Exception as e:
        logger.error(f"Aggiornamento sintonia fallito per {item_id}: {e}")
        return False


# ---------------------------------------------------------------------------
# Condizioni (Fase 4, feature 2b — Appendice A del PHB)
# ---------------------------------------------------------------------------


def get_conditions(character_id: str) -> list[CharacterCondition]:
    """Condizioni attive sul personaggio, nell'ordine in cui sono state imposte."""
    try:
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM character_conditions WHERE character_id=? "
                "ORDER BY created_at, rowid",
                (character_id,),
            ).fetchall()
        finally:
            conn.close()
        return [
            CharacterCondition(
                id=r["id"], character_id=r["character_id"],
                condition_key=r["condition_key"],
                source=r["source"] or "", note=r["note"] or "",
                created_at=r["created_at"] or "",
            )
            for r in rows
        ]
    except Exception as e:
        logger.error(f"Errore lettura condizioni di {character_id}: {e}")
        return []


def add_condition(character_id: str, condition_key: str,
                  source: str = "", note: str = "") -> str | None:
    """
    Impone una condizione. Ritorna l'id creato, o `None` in caso di errore.

    PHB Appendice A: "Se più effetti impongono la stessa condizione su una
    creatura, ogni istanza di quella condizione ha una sua durata, ma gli
    effetti della condizione non peggiorano." — quindi imporre due volte la
    stessa condizione è legittimo (fonti diverse), ma sarebbe rumore mostrarne
    due chip identici: se la fonte è la stessa non si duplica.
    """
    import uuid as _uuid
    try:
        existing = get_conditions(character_id)
        for c in existing:
            if (c.condition_key == condition_key
                    and c.source.strip().lower() == (source or "").strip().lower()):
                return c.id
        new_id = str(_uuid.uuid4())
        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO character_conditions "
                "(id, character_id, condition_key, source, note, created_at) "
                "VALUES (?,?,?,?,?,?)",
                (new_id, character_id, condition_key, source or "", note or "",
                 datetime.now().isoformat()),
            )
            conn.commit()
        finally:
            conn.close()
        return new_id
    except Exception as e:
        logger.error(f"Errore aggiunta condizione {condition_key}: {e}")
        return None


def remove_condition(condition_id: str) -> bool:
    try:
        conn = get_connection()
        try:
            conn.execute("DELETE FROM character_conditions WHERE id=?", (condition_id,))
            conn.commit()
        finally:
            conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore rimozione condizione {condition_id}: {e}")
        return False


def clear_conditions(character_id: str) -> bool:
    """Rimuove tutte le condizioni (usata dal riposo lungo)."""
    try:
        conn = get_connection()
        try:
            conn.execute("DELETE FROM character_conditions WHERE character_id=?",
                         (character_id,))
            conn.commit()
        finally:
            conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore azzeramento condizioni di {character_id}: {e}")
        return False


def condition_effects(character_id: str) -> dict[str, Any]:
    """
    Unione degli effetti meccanici delle condizioni attive.

    Usata SOLO per i promemoria contestuali in sola lettura (scelta di Davide,
    2026-07-30): l'app segnala "svantaggio" accanto ai tiri, non lo applica.
    """
    from data.game_data.game_data_loader import game_data as _gd

    merged: dict[str, Any] = {}
    sources: dict[str, list[str]] = {}
    for c in get_conditions(character_id):
        data = _gd.get_condition(c.condition_key) or {}
        for key, value in (data.get("effects") or {}).items():
            if isinstance(value, list):
                merged.setdefault(key, [])
                for v in value:
                    if v not in merged[key]:
                        merged[key].append(v)
            else:
                merged[key] = bool(merged.get(key)) or bool(value)
            sources.setdefault(key, []).append(data.get("name", c.condition_key))
    merged["_sources"] = sources
    return merged
