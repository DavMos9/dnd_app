"""
Dataclass models che rispecchiano lo schema del database.
Nessuna logica di business qui: solo struttura dati.
"""

from dataclasses import dataclass, field
from typing import Optional
import uuid


# ---------------------------------------------------------------------------
# Personaggio
# ---------------------------------------------------------------------------

@dataclass
class Character:
    # Identità
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    player_name: str = ""
    class_name: str = ""
    subclass: str = ""
    level: int = 1
    race: str = ""
    subrace: str = ""
    background: str = ""
    alignment: str = ""
    xp: int = 0
    image_path: str = ""          # percorso foto personaggio

    # Caratteristiche base (punteggi grezzi, modificatori calcolati runtime)
    str_score: int = 10
    dex_score: int = 10
    con_score: int = 10
    int_score: int = 10
    wis_score: int = 10
    cha_score: int = 10

    # Punti ferita
    hp_max: int = 0
    hp_current: int = 0
    hp_temp: int = 0

    # Combattimento
    ac: int = 10
    speed: int = 9                # in metri (velocità base terreno)
    hit_dice_type: int = 6        # d6, d8, d10, d12
    hit_dice_total: int = 1
    hit_dice_remaining: int = 1

    # Tiri salvezza contro morte
    death_saves_success: int = 0  # 0-3
    death_saves_failure: int = 0  # 0-3

    # Stato turno
    action_used: bool = False
    bonus_action_used: bool = False
    reaction_used: bool = False
    movement_used: int = 0        # metri già usati nel turno
    previous_turn_state: str = "" # JSON snapshot per undo

    # Magia
    spellcasting_ability: str = ""  # "int", "wis", "cha" o ""

    # Ispirazione
    inspiration: bool = False

    # Dettagli fisici
    age: str = ""
    height: str = ""
    weight: str = ""
    eyes: str = ""
    skin: str = ""
    hair: str = ""

    # Personalità
    personality_traits: str = ""
    ideals: str = ""
    bonds: str = ""
    flaws: str = ""
    backstory: str = ""
    allies_organizations: str = ""
    additional_traits: str = ""   # tratti & privilegi aggiuntivi
    appearance_notes: str = ""    # note aspetto

    # Timestamp
    created_at: str = ""
    updated_at: str = ""


@dataclass
class CharacterProficiency:
    """Competenza del personaggio in un'abilità, tiro salvezza, strumento o linguaggio."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    character_id: str = ""
    proficiency_type: str = ""    # "skill" | "save" | "weapon" | "armor" | "tool" | "language"
    name: str = ""                # es. "Percezione", "Forza", "Spade Lunghe", "Comune"
    is_expert: bool = False       # doppio bonus competenza (es. Maestria del Ladro)


# ---------------------------------------------------------------------------
# Armi
# ---------------------------------------------------------------------------

@dataclass
class Weapon:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    character_id: str = ""
    name: str = ""
    damage_dice: str = ""         # es. "1d8", "2d6"
    damage_type: str = ""         # es. "tagliente", "perforante", "contundente"
    attack_bonus: int = 0         # bonus totale al tiro per colpire
    damage_bonus: int = 0         # bonus ai danni
    properties: str = ""          # es. "versatile, da lancio" (CSV)
    is_magical: bool = False
    magic_description: str = ""   # descrizione potere se magica
    is_equipped: bool = False
    range_normal: int = 0         # gittata normale in metri (0 = mischia)
    range_max: int = 0            # gittata massima in metri


# ---------------------------------------------------------------------------
# Inventario
# ---------------------------------------------------------------------------

@dataclass
class InventoryItem:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    character_id: str = ""
    name: str = ""
    quantity: int = 1
    weight: float = 0.0           # kg per unità
    description: str = ""
    category: str = "misc"        # "armor" | "weapon" | "tool" | "magic" | "misc"
    is_equipped: bool = False


@dataclass
class Currency:
    character_id: str = ""
    copper: int = 0               # MR - Monete di Rame
    silver: int = 0               # MA - Monete d'Argento
    electrum: int = 0             # ME - Monete di Elettro
    gold: int = 0                 # MO - Monete d'Oro
    platinum: int = 0             # MP - Monete di Platino


# ---------------------------------------------------------------------------
# Magia
# ---------------------------------------------------------------------------

@dataclass
class SpellSlot:
    """Slot incantesimo per livello (1-9)."""
    character_id: str = ""
    slot_level: int = 1           # 1-9
    total: int = 0                # slot massimi a quel livello
    used: int = 0                 # slot già spesi


@dataclass
class KnownSpell:
    """Incantesimo conosciuto dal personaggio."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    character_id: str = ""
    name: str = ""
    spell_level: int = 0          # 0 = trucchetto
    is_prepared: bool = False
    school: str = ""              # es. "evocazione", "illusione"
    casting_time: str = ""        # es. "1 azione", "1 azione bonus"
    spell_range: str = ""         # es. "18 metri", "Tocco"
    components: str = ""          # es. "V, S, M (un granello di zolfo)"
    duration: str = ""            # es. "Istantanea", "Concentrazione, fino a 1 minuto"
    description: str = ""
    higher_levels: str = ""       # effetto ai livelli superiori
    class_list: str = ""          # classi che possono usarlo (CSV)


# ---------------------------------------------------------------------------
# Diario
# ---------------------------------------------------------------------------

@dataclass
class DiaryEntry:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    character_id: str = ""
    title: str = ""
    content: str = ""
    session_date: str = ""        # data della sessione di gioco (stringa libera)
    created_at: str = ""
    updated_at: str = ""


# ---------------------------------------------------------------------------
# Mappe
# ---------------------------------------------------------------------------

@dataclass
class GameMap:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    character_id: str = ""
    name: str = ""
    image_path: str = ""
    annotations: str = "[]"       # JSON list di annotazioni
    created_at: str = ""
    updated_at: str = ""
