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
    image_path: str = ""          # percorso foto (legacy, usare image_data)
    image_data: str = ""          # foto codificata base64 (salvata nel DB)

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

    # CA temporanea (bonus da incantesimi, reazioni, ecc. — resettabile)
    ca_bonus: int = 0

    # Override manuale del bonus competenza (0 = usa tabella PHB standard)
    proficiency_bonus_override: int = 0

    # Override manuale del massimo incantesimi preparabili (0 = usa formula PHB)
    max_prepared_spells_override: int = 0

    # Appunti di sessione (testo libero, per note al volo durante il gioco)
    session_notes: str = ""

    # Scelte di classe/razza che influenzano feature successive
    dragon_ancestry: str = ""       # Stregone Discendenza Draconiana: tipo drago (es. "Rosso")
    fighting_style: str = ""        # Guerriero/Paladino/Ranger: stile di combattimento scelto
    totem_animal: str = ""          # Barbaro Percorso del Totem: animale (Orso/Aquila/Lupo)
    land_terrain: str = ""          # Druido Cerchio della Terra: terreno scelto
    pact_boon: str = ""             # Warlock Dono del Patto: "Patto della Catena/Lama/Tomo"

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
    properties: str = ""          # CSV proprietà PHB: "Leggera,Versatile,Da Lancio"
    is_magical: bool = False
    magic_description: str = ""   # descrizione effetti magici
    is_equipped: bool = False
    range_normal: int = 0         # gittata normale in metri (0 = mischia)
    range_max: int = 0            # gittata massima in metri
    # Danni magici aggiuntivi — JSON: [{"dice":"1d6","type":"Fuoco","note":""}]
    magic_damages: str = "[]"


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
    # Campi armatura/scudo (usati quando category="armor")
    ca_value: int = 0             # valore CA base (es. 14 per cotta di maglia)
    armor_type: str = ""          # "leggera" | "media" | "pesante" | "scudo" | ""
    # Effetti magici (per armature, scudi e qualsiasi item incantato)
    effects: str = ""


@dataclass
class Currency:
    character_id: str = ""
    copper: int = 0               # MR - Monete di Rame
    silver: int = 0               # MA - Monete d'Argento
    electrum: int = 0             # ME - Monete di Elettro
    gold: int = 0                 # MO - Monete d'Oro
    platinum: int = 0             # MP - Monete di Platino


# ---------------------------------------------------------------------------
# Risorse di classe (Furia, Ki, Incanalare Divinità, Slot del Patto, ecc.)
# ---------------------------------------------------------------------------

@dataclass
class ClassResource:
    """Risorsa di classe con pool tracciabile (si azzera su riposo breve o lungo)."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    character_id: str = ""
    name: str = ""                 # es. "Furia", "Punti Ki", "Incanalare Divinità"
    max_value: int = 0             # pool massimo
    current_value: int = 0         # pool attuale
    reset_on: str = "long_rest"    # "short_rest" | "long_rest"
    display_type: str = "circles"  # "circles" (≤6 cerchietti) | "counter" (−/+ numerico)


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
# Note di Campagna (PNG, Luoghi, Missioni, Fazioni)
# ---------------------------------------------------------------------------

@dataclass
class CampaignNote:
    """
    Voce generica del diario di campagna.

    category:
        "npc"        → PNG incontrati
        "npc_todo"   → PNG da cercare
        "place"      → luoghi visitati
        "place_todo" → luoghi da esplorare
        "quest"      → missioni
        "faction"    → fazioni

    status: stringa libera dipendente dalla categoria
        npc        → alleato | neutrale | ostile | sconosciuto
        npc_todo   → cercato | sentito nominare | leggenda
        place      → esplorato | parzialmente esplorato
        place_todo → da esplorare | sentito nominare | leggenda/rumor
        quest      → attiva | completata | fallita | in pausa
        faction    → alleata | neutrale | ostile | sconosciuta
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    character_id: str = ""
    category: str = ""
    name: str = ""
    description: str = ""
    status: str = ""
    tags: str = ""              # tag liberi separati da virgola
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
    image_path: str = ""           # legacy — usare image_data
    image_data: str = ""           # immagine base64 (stessa convenzione di Character)
    annotations: str = "[]"        # JSON list di annotazioni testuali
    notes: str = ""                # testo libero associato alla mappa
    created_at: str = ""
    updated_at: str = ""
