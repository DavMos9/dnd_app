"""
Dataclass models che rispecchiano lo schema del database.
Nessuna logica di business qui: solo struttura dati.
"""

from dataclasses import dataclass, field
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
    speed: float = 9.0            # in metri (velocità base terreno) — float: alcune razze hanno velocità frazionarie (Nano/Halfling 7,5 m, Elfo dei Boschi 10,5 m)
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
    movement_used: float = 0.0    # metri già usati nel turno — float per permettere step frazionari (0,5 m / 1,5 m)
    previous_turn_state: str = "" # JSON snapshot per undo

    # Magia
    spellcasting_ability: str = ""  # "int", "wis", "cha" o ""

    # Ispirazione
    inspiration: bool = False

    # CA temporanea (bonus da incantesimi, reazioni, ecc. — resettabile)
    ca_bonus: int = 0

    # Bonus permanente all'iniziativa (es. talento Allerta: +5)
    initiative_bonus: int = 0

    # Override manuale del bonus competenza (0 = usa tabella PHB standard)
    proficiency_bonus_override: int = 0

    # Override manuale del massimo incantesimi preparabili (0 = usa formula PHB)
    max_prepared_spells_override: int = 0

    # Override manuale della Percezione Passiva (0 = usa 10 + mod SAG + comp.)
    passive_perception_override: int = 0

    # Override manuale della capacità di trasporto massima in kg
    # (0 = usa FOR × 7,5 kg standard) — per talenti/razze/oggetti che la
    # alterano, es. "Corporatura Possente" (raddoppia il carico).
    carry_capacity_override: float = 0.0

    # Appunti di sessione (testo libero, per note al volo durante il gioco)
    session_notes: str = ""

    # Livello di Indebolimento (Exhaustion), 0-6, condizione cumulativa PHB.
    # Effetti testuali per livello in config/settings.py → EXHAUSTION_LEVELS.
    # Nessun effetto meccanico è applicato automaticamente (es. dimezzare la
    # velocità o gli HP massimi): il giocatore applica a mano leggendo la
    # sezione dedicata in Combattimento, coerente con l'approccio già usato
    # per "Abilità di Classe"/"Tratti di Razza" (testo di riferimento, non
    # enforcement automatico delle regole).
    exhaustion_level: int = 0

    # Barbaro, Cammino del Berserker — Frenesia (PHB IT): "Il barbaro può
    # entrare in frenesia quando entra in ira... Quando la sua ira termina,
    # il barbaro subisce un livello di indebolimento." L'Indebolimento è
    # condizionato all'aver dichiarato la Frenesia per QUELLA ira, non
    # automatico ad ogni uso di Furia — questo flag traccia se la frenesia è
    # stata dichiarata per l'ira in corso, in attesa che il giocatore segnali
    # la fine dell'ira (vedi combattimento_tab.py, sezione Risorse di Classe:
    # "Termina Ira" applica +1 Indebolimento in automatico e azzera il flag).
    frenzy_active: bool = False
    #: Incantesimo su cui il personaggio si sta concentrando (PHB p.203-204).
    #: Uno solo alla volta: "un incantatore non può concentrarsi su due
    #: incantesimi alla volta". Stringa vuota = nessuna concentrazione.
    concentrating_spell: str = ""
    #: Timestamp ISO di inizio, per mostrare "da quanto" — puramente informativo.
    concentrating_since: str = ""

    # Scelte di classe/razza che influenzano feature successive
    dragon_ancestry: str = ""       # Stregone Discendenza Draconica: tipo drago (es. "Rosso")
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

    # Mondi condivisi (2026-08-05, Multiplayer passo 2/3 — vedi
    # dnd_app/docs/multiplayer_design.md §8). '' / 0 su tutte e cinque =
    # personaggio locale: un personaggio creato da wizard/form manuale non
    # valorizza mai questi campi da solo, li imposta solo
    # core/character_instances.py quando nasce un'istanza di mondo.
    world_id: str = ""              # '' = personaggio locale
    origin_character_id: str = ""   # da quale personaggio locale nasce questa istanza
    owner_device_id: str = ""       # device_id di chi possiede questo personaggio/istanza
    is_replica: bool = False        # True = l'autorità sui dati è altrove (rete, passo 4)
    world_seq: int = 0              # ultimo evento del mondo applicato a questa scheda
    #: Espulsione dal mondo (2026-08-07): True = il proprietario è stato
    #: espulso, l'istanza è archiviata (esclusa dalla Sezione Master) invece
    #: di restare agganciata al mondo per sempre. Solo su un'istanza HOST
    #: (autoritativa), mai su un personaggio locale. Vedi `_add_column` in
    #: data/database.py per il ragionamento completo, incluso su come si
    #: riattiva.
    world_instance_archived: bool = False


@dataclass
class CharacterProficiency:
    """Competenza del personaggio in un'abilità, tiro salvezza, strumento o linguaggio."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    character_id: str = ""
    proficiency_type: str = ""    # "skill" | "save" | "weapon" | "armor" | "tool" | "language"
    name: str = ""                # es. "Percezione", "Forza", "Spade Lunghe", "Comune"
    is_expert: bool = False       # doppio bonus competenza (es. Maestria del Ladro)


# ---------------------------------------------------------------------------
# Multiclasse (PHB IT cap.6, p.163-165 — vedi dnd_app/docs/multiclasse_design.md)
# ---------------------------------------------------------------------------

@dataclass
class CharacterClass:
    """
    Una classe posseduta dal personaggio, col suo livello. Character.
    class_name/subclass/level restano SEMPRE la classe primaria (1° livello)
    e il livello totale — mai derivati da qui, sempre la fonte di verità per
    la riga con is_primary=True.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    character_id: str = ""
    class_name: str = ""
    subclass: str = ""
    level: int = 1
    is_primary: bool = False
    order_index: int = 0


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
    # Proprietà "Versatile" (PHB p.149): dado danno quando impugnata a due
    # mani (es. "1d10" per una spada lunga il cui damage_dice a una mano è
    # "1d8"). Significativo solo se "Versatile" è tra le properties.
    versatile_damage_dice: str = ""
    # True se l'arma è attualmente impugnata a due mani — rilevante solo per
    # armi Versatile (le armi "Due Mani" sono sempre a due mani, non serve
    # un flag). Determina sia il dado danno effettivo (damage_dice vs
    # versatile_damage_dice) sia l'occupazione delle mani in
    # core/equipment_manager.py.
    grip_two_handed: bool = False

    # --- Calcolo automatico tiro per colpire (2026-07-17) ---------------
    # Categoria PHB dell'arma, usata per determinare la competenza per
    # confronto con character_proficiencies (proficiency_type="weapon"):
    # "semplice" | "guerra" | "" (sconosciuta — trattata come non competente
    # salvo proficiency_override). Sempre richiesta in creazione (autoriempita
    # dal catalogo se l'arma vi corrisponde, altrimenti scelta a mano — anche
    # un'arma homebrew "è comunque di un certo tipo", istruzione di Davide).
    weapon_category: str = ""
    # Competenza garantita da QUESTA specifica arma indipendentemente dalle
    # competenze generali del personaggio (es. arma magica che concede
    # automaticamente competenza a chi la impugna).
    proficiency_override: bool = False
    # Caratteristica usata per il tiro per colpire/danno: "" = automatico
    # (Forza in mischia, Destrezza a distanza, il più alto tra i due se
    # l'arma ha la proprietà Accurata) | "str" | "dex" — scelta esplicita
    # del giocatore, sempre disponibile ma pensata soprattutto per le armi
    # Accurate (dove il PHB lascia scegliere).
    finesse_ability: str = ""
    # Override manuale del TOTALE del tiro per colpire: se True, il totale
    # mostrato è attack_override_value invece del calcolo automatico
    # (mod. caratteristica + bonus competenza + attack_bonus).
    attack_total_override: bool = False
    attack_override_value: int = 0


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
    ca_value: int = 0
    #: Sintonia (DMG p.138). `requires_attunement` è salvato sull'oggetto e non
    #: dedotto dal catalogo, così vale anche per gli oggetti homebrew.
    requires_attunement: bool = False
    is_attuned: bool = False             # valore CA base (es. 14 per cotta di maglia)
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
    max_value_bonus: int = 0       # bonus permanente additivo (talento/oggetto magico),
                                    # sopravvive al ri-sync di init_class_resources()


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
    origin_unrestricted: bool = False  # Mistificatore Arcano/Cavaliere Mistico:
                                        # True se questo pick è "libero da vincolo
                                        # di scuola" (8°/14°/20° livello, +3° per il
                                        # Cavaliere Mistico) — usato per gestire
                                        # correttamente le sostituzioni future.
    is_bonus: bool = False             # Incantesimo bonus aggiunto manualmente dal
                                        # giocatore (es. concesso dal master) — sezione
                                        # dedicata "Incantesimi Bonus", rimovibile.
    always_prepared: bool = False      # Incantesimo sempre pronto da privilegio di
                                        # Dominio/Giuramento/Circolo — non conta nel
                                        # tetto di preparazione, non disattivabile.


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
# Abilità Speciali custom (2026-07-16)
# ---------------------------------------------------------------------------

@dataclass
class CustomAbility:
    """
    Abilità speciale aggiunta manualmente (es. concessa dal master, o un
    tratto/feature che il giocatore vuole annotare senza modificare il testo
    ufficiale PHB già rappresentato altrove nella scheda). Puramente
    additiva: non sostituisce né modifica alcuna feature di classe/razza
    già presente nei JSON di gioco.

    category:
        "esplorazione"  → mostrata nella tab Esplorazione
        "combattimento" → mostrata nella tab Combattimento
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    character_id: str = ""
    category: str = "esplorazione"
    name: str = ""
    description: str = ""
    created_at: str = ""
    updated_at: str = ""


# ---------------------------------------------------------------------------
# Creature (Forme Selvatiche e Evocazioni)
# ---------------------------------------------------------------------------

@dataclass
class CreatureEntry:
    """
    Forma selvatica o evocazione legata a un personaggio.
    entry_type = "forma" (solo Druido) | "evocazione" (tutti)
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    character_id: str = ""

    # Tipo: "forma" = forma selvatica, "evocazione" = creatura evocata
    entry_type: str = "evocazione"

    # Identità della creatura (dal bestiary o inserita manualmente)
    name: str = ""
    creature_type: str = ""          # es. "Bestia", "Elementale", "Immondo"
    alignment: str = ""
    cr: str = ""                     # es. "1/4", "5", "—"

    # Difesa
    ac: int = 10
    ac_note: str = ""                # es. "armatura naturale"

    # Punti ferita
    hp_max: int = 1
    hp_formula: str = ""             # es. "3d8 + 6"
    hp_current: int = 1              # tracciato durante il combattimento

    # Movimento
    speed: str = ""                  # es. "9 m, nuotare 9 m"

    # Caratteristiche (punteggi grezzi)
    str_score: int = 10
    dex_score: int = 10
    con_score: int = 10
    int_score: int = 10
    wis_score: int = 10
    cha_score: int = 10

    # Bonus e competenze
    saving_throws: str = "{}"        # JSON: {"str": "+4", "dex": "+2"}
    skills: str = "{}"               # JSON: {"Percezione": "+3"}

    # Immunità e resistenze
    damage_vulnerabilities: str = ""
    damage_resistances: str = ""
    damage_immunities: str = ""
    condition_immunities: str = ""

    # Sensi e linguaggi
    senses: str = ""
    languages: str = ""

    # Feature narrative
    traits: str = "[]"              # JSON: [{"name":"...", "text":"..."}]
    actions: str = "[]"             # JSON: [{"name":"...", "text":"..."}]
    reactions: str = "[]"           # JSON: [{"name":"...", "text":"..."}]
    legendary_actions: str = "[]"   # JSON: [{"name":"...", "text":"..."}]

    # Azioni di Tana / Effetti Regionali — solo per i pochi mostri con una
    # tana propria (Kraken, Lich, Signore delle Mummie, Sfinge, Unicorno,
    # Vampiro, Demilich). Vuoti per tutti gli altri. "regional_effects_label"
    # è di norma "Effetti Regionali", ma per il Demilich il manuale usa
    # "Tratti della Tana" — stesso concetto, nome diverso, tenuto nel dato
    # per mostrare l'intestazione esatta del libro invece di una generica.
    lair_actions_intro: str = ""
    lair_actions: str = "[]"          # JSON: ["testo effetto 1", "testo effetto 2", ...]
    regional_effects_label: str = ""  # "Effetti Regionali" o "Tratti della Tana"
    regional_effects_intro: str = ""
    regional_effects: str = "[]"      # JSON: ["testo effetto 1", ...]

    # Varianti opzionali "sidebar" del manuale legate a questo mostro
    # specifico (es. "Arma su Asta del Diavolo d'Ossa", "Congreghe di
    # Megere") — sola consultazione, il master decide se applicarle.
    variant_rules: str = "[]"       # JSON: [{"name":"...", "description":"..."}]

    # Stato in-session
    is_active: bool = False          # True = attualmente in forma / evocata in campo

    # Note libere del giocatore
    notes: str = ""

    # Pagina di riferimento nel manuale (0 = non specificata)
    source_page: int = 0

    # Timestamp
    created_at: str = ""
    updated_at: str = ""


# ---------------------------------------------------------------------------
# Mappe
# ---------------------------------------------------------------------------

@dataclass
class GameMap:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    character_id: str = ""         # '' = nessun personaggio proprietario locale
                                    # (mappa condivisa non posseduta — Multiplayer passo 8)
    name: str = ""
    image_path: str = ""           # legacy — usare image_data
    image_data: str = ""           # immagine base64 (stessa convenzione di Character)
    annotations: str = "[]"        # JSON list di annotazioni testuali
    notes: str = ""                # testo libero associato alla mappa
    # Mappe condivise (Multiplayer passo 8, §6.4). '' = mappa locale, non
    # pubblicata in nessun mondo. `is_shared` conta solo se `world_id` è
    # valorizzato.
    world_id: str = ""
    is_shared: bool = False
    # Visibilità ai giocatori (2026-08-12) — distinta da `is_shared`: una
    # mappa condivisa resta nella sezione del master anche quando
    # `visible_to_players=False`, solo i giocatori smettono di vederla e
    # di poterne scaricare l'immagine (§6.4, CMD_MAP_VISIBILITY). Conta
    # solo se `is_shared` è vero.
    visible_to_players: bool = True
    created_at: str = ""
    updated_at: str = ""


# ---------------------------------------------------------------------------
# Sezione Master — NPC/mostri, incontri, membri d'incontro (2026-07-24)
#
# Deliberatamente indipendenti da `Character`/`CreatureEntry`: vedi
# dnd_app/docs/master_section_design.md per il ragionamento completo
# ("Perché NON riusare creature_entries"). Stesso principio "solo lettura
# dei PG": MasterEncounterMember non duplica mai gli HP di un personaggio
# giocante — hp_current/hp_max qui sono significativi solo per
# kind="npc"/"adhoc", per kind="character" si legge sempre live da
# `characters.hp_current`/`hp_max`.
# ---------------------------------------------------------------------------

@dataclass
class MasterNpc:
    """
    Voce di rubrica del Master: un NPC può essere puro ruolo (has_stat_block
    = False, solo name/role/notes/tags) oppure avere anche uno stat block
    completo (has_stat_block = True, stessa forma di CreatureEntry/i dict
    grezzi di monsters.json — risolvibile con `creature_entry_dict()` per il
    rendering condiviso via `ui/components/monster_picker.py`).
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    role: str = ""                    # es. "Alleato", "Antagonista", "Comune" — testo libero
    notes: str = ""                   # note di ruolo/backstory, sempre presenti
    tags: str = ""                    # CSV libero per filtro/ricerca nella rubrica
    has_stat_block: bool = False

    # Sezione Master world-scoped (2026-08-12) — "" = NPC locale/di nessun
    # mondo (comportamento di sempre), altrimenti l'id del mondo in cui è
    # stato creato. Stesso principio già in uso per Character/
    # MasterCampaignNote/LootStashEntry: filtro per UGUAGLIANZA esatta, mai
    # "mostra tutti" — un mondo è un container, non un filtro opzionale.
    world_id: str = ""

    # Razza PHB (2026-08-12, bug report Davide: "tipo creatura e taglia
    # devono corrispondere a quelle già create automaticamente") — una
    # delle 9 di `core.npc_generator.RACE_OPTIONS`, o testo libero se scelta
    # "Altro" nel form. "" per un NPC senza razza nota (es. un mostro puro
    # dal Bestiario). A differenza di `world_id`, MODIFICABILE dopo la
    # creazione (`update_npc()`) — un Master che scopre "in realtà è un
    # cambiaforma" deve poter correggerla e vederla persistere.
    race: str = ""

    # Campi stat block, stessa forma di CreatureEntry — tutti opzionali
    creature_type: str = ""
    size: str = ""
    alignment: str = ""
    ac: int = 10
    ac_note: str = ""
    hp_max: int = 1
    hp_formula: str = ""
    speed: str = ""
    str_score: int = 10
    dex_score: int = 10
    con_score: int = 10
    int_score: int = 10
    wis_score: int = 10
    cha_score: int = 10
    saving_throws: str = "{}"
    skills: str = "{}"
    damage_vulnerabilities: str = ""
    damage_resistances: str = ""
    damage_immunities: str = ""
    condition_immunities: str = ""
    senses: str = ""
    languages: str = ""
    cr: str = ""
    xp: int = 0                        # Punti Esperienza — per il Calcolatore Difficoltà Incontro (Sezione Master)
    traits: str = "[]"
    actions: str = "[]"
    reactions: str = "[]"
    legendary_actions: str = "[]"
    source_page: str = ""              # es. "da Bestiario: Goblin (p.167)" — testo libero, non un numero

    created_at: str = ""
    updated_at: str = ""


@dataclass
class MasterEncounter:
    """Un incontro (sessione di combattimento) gestito dal Master."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    notes: str = ""
    round_number: int = 1
    current_turn_index: int = 0
    is_archived: bool = False
    created_at: str = ""
    updated_at: str = ""

    # Tracker di combattimento condiviso (Multiplayer passo 7C, §6.5).
    # '' = incontro locale, non legato a nessun mondo. `visible_to_players`
    # conta solo se `world_id` è valorizzato — spento di default.
    world_id: str = ""
    visible_to_players: bool = False


@dataclass
class MasterEncounterMember:
    """
    Un partecipante a un incontro: un personaggio giocante (kind="character",
    letto in sola lettura da `characters`), un NPC di rubrica (kind="npc",
    `npc_id` verso `master_npcs`), o un combattente estemporaneo creato al
    volo per quell'incontro (kind="adhoc", nessuna riga in nessun'altra
    tabella — solo display_name/ac/hp_max/hp_current qui).
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    encounter_id: str = ""
    kind: str = "adhoc"                # "character" | "npc" | "adhoc"
    character_id: str = ""             # valorizzato solo se kind="character"
    npc_id: str = ""                   # valorizzato solo se kind="npc"
    display_name: str = ""             # nome mostrato per adhoc; override opzionale per character/npc
    ac: int = 0                        # cache per npc/adhoc; per "character" si legge live da characters.ac
    hp_current: int = 0                # tracciato solo per npc/adhoc
    hp_max: int = 0
    xp: int = 0                        # PE del mostro/NPC (0 per kind="character") — Calcolatore Difficoltà
    initiative: int = 0
    #: Modificatore di Destrezza del combattente, catturato al momento
    #: dell'aggiunta (dallo stat block del mostro o dall'NPC di rubrica).
    #: Serve a "Tira iniziativa per tutti": il membro non conserva altrimenti
    #: alcuna traccia delle caratteristiche. Vale 0 per kind="character" — i
    #: PG non vengono mai tirati dal master (regola del progetto).
    dex_mod: int = 0
    order_index: int = 0               # per pareggi/riordino manuale
    is_active: bool = True              # False = rimosso dall'incontro senza cancellare la riga (storico)
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""


@dataclass
class MasterCampaignNote:
    """
    Nota di campagna del Master — stessa forma di `CampaignNote` (usata da
    `DiaryView`, per-personaggio) ma SENZA `character_id`: vive solo nella
    Sezione Master, indipendente da ogni scheda giocante. `category`:
    "npc" | "npc_todo" | "place" | "place_todo" | "quest" | "faction" |
    "event" | "secret" (le prime 6 condivise con CampaignNote, le ultime 2
    nuove). `linked_npc_id` collega opzionalmente la nota a una voce della
    Rubrica NPC (`master_npcs`) — puramente organizzativo, nessuna fonte
    DMG coinvolta.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    category: str = "npc"
    name: str = ""
    description: str = ""
    status: str = ""
    tags: str = ""
    linked_npc_id: str = ""
    created_at: str = ""
    updated_at: str = ""

    # Modalità Master world-scoped (2026-08-06). '' = nota locale/di nessun
    # mondo. `visibility` conta solo se `world_id` è valorizzato:
    # "private" (solo il Master) | "all" (tutti i membri del mondo) |
    # "selected" (solo i device_id elencati in `visible_to_device_ids`,
    # JSON list di stringhe). Non riassegnabile dopo la creazione (una nota
    # non "cambia mondo").
    world_id: str = ""
    visibility: str = "private"
    visible_to_device_ids: str = "[]"


@dataclass
class CharacterCondition:
    """
    Una condizione dell'Appendice A attiva su un personaggio (Fase 4, 2b).

    `condition_key` e' la chiave di `data/game_data/conditions.json`; nome e
    testo integrale vivono la' e non vengono duplicati qui.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    character_id: str = ""
    condition_key: str = ""
    source: str = ""      # da cosa e' stata imposta ("Incantesimo Spavento")
    note: str = ""
    created_at: str = ""


@dataclass
class LootStashEntry:
    """
    Una voce di bottino — vive nell'archivio privato del Master o nel
    deposito comune del gruppo (`dnd_app/docs/loot_design.md`).

    `stash_kind`: "master" (archivio privato, mai visibile ai giocatori) |
    "party" (deposito comune, visibile a tutti i membri del gruppo).

    `world_id`: "" per una voce locale/di nessun mondo, altrimenti l'id del
    mondo correntemente selezionato al momento della creazione — si applica
    a ENTRAMBI gli `stash_kind` (2026-08-12: prima l'archivio del Master
    restava sempre a "" per scelta di design, cambiato su bug report di
    Davide — un mondo è un container per tutta la Sezione Master, non solo
    per il deposito comune; resta comunque un asse indipendente dalla
    privacy di `stash_kind="master"`, mai sincronizzato/visibile ai
    giocatori indipendentemente da `world_id`).

    `entry_kind`: "item" (oggetto generico/mondano) | "magic_item" (dal
    Compendio A-Z o dal Generatore) | "artifact" | "poison" | "gem" |
    "art" (oggetto d'arte) | "coins" (voce puramente monetaria, usa solo i
    5 campi valuta sotto, `name`/`description` restano vuoti).

    `description` porta sempre il testo ufficiale COMPLETO quando la voce
    proviene da una fonte trascritta (mai un riassunto) — stessa regola
    gia' seguita per il Compendio Oggetti Magici e gli Artefatti.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    stash_kind: str = "master"
    world_id: str = ""
    entry_kind: str = "item"
    name: str = ""
    description: str = ""
    quantity: int = 1
    source_note: str = ""       # es. "Generatore Tesori", "Manuale (voce manuale)"
    copper: int = 0
    silver: int = 0
    electrum: int = 0
    gold: int = 0
    platinum: int = 0
    added_by_device_id: str = ""  # placeholder per il Multiplayer, vuoto oggi
    created_at: str = ""
    updated_at: str = ""


# ---------------------------------------------------------------------------
# Mondi condivisi / LAN party (2026-08-05)
#
# Vedi dnd_app/docs/multiplayer_design.md per il progetto completo. Queste
# quattro dataclass rispecchiano le tabelle omonime create in
# data/database.py — nessuna logica qui, solo struttura dati (stesso
# principio di tutto questo file).
# ---------------------------------------------------------------------------

@dataclass
class World:
    """
    Una campagna condivisa. Vive nel DB di chi la ospita
    (`is_local_host=True`); sui dispositivi dei membri e' una replica
    aggiornata dal giornale eventi (`world_events`).
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    owner_device_id: str = ""       # device_id di chi ha creato il mondo
    join_code: str = ""             # 6 caratteri, significativo solo sull'host
    is_local_host: bool = False     # True = il mondo autoritativo vive su QUESTO dispositivo
    last_seen_host: str = ""        # "192.168.1.7:8765" — per la riconnessione (passo 4)
    session_token: str = ""         # token RemoteBackend (join()), solo lato replica — per
                                     # ricostruire la connessione senza richiedere codice+PIN
                                     # ad ogni apertura della sezione Mondi (fix 2026-08-07)
    last_synced_seq: int = 0        # ultimo world_events.seq applicato (solo lato replica)
    last_export_seq: int = 0        # world_events.seq al momento dell'ultimo export .dndworld
                                     # riuscito (2026-08-12, passo 9E — promemoria di backup)
    created_at: str = ""
    updated_at: str = ""


@dataclass
class WorldMember:
    """
    Un dispositivo dentro un mondo, con un ruolo (§4 del design doc).

    role: "owner" (uno solo, chi ospita) | "master" (co-master promossi
    dall'owner) | "player". Nessun ruolo spettatore — scelta di Davide.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    world_id: str = ""
    device_id: str = ""
    display_name: str = ""
    role: str = "player"
    is_connected: bool = False   # significativo solo dal passo 4 (rete) in poi
    last_seen_at: str = ""
    created_at: str = ""
    updated_at: str = ""


@dataclass
class WorldEvent:
    """
    Una riga del giornale del mondo — sincronizzazione E registro delle
    azioni insieme (§5). `seq` e' l'ordine totale assegnato dall'host
    (AUTOINCREMENT); `kind` identifica il tipo di evento (es. "world.renamed",
    "member.role_changed", "xp.grant" nei passi successivi del piano).

    `summary` e' gia' la riga leggibile per il registro mostrato al
    giocatore ("Il Master ha rinominato il mondo in 'La Costa di Smeraldo'");
    `payload` e `before_state` sono JSON per l'applicazione/l'eventuale undo,
    non per la visualizzazione diretta.
    """
    seq: int = 0
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    world_id: str = ""
    actor_device_id: str = ""
    actor_name: str = ""          # copiato al momento dell'evento: leggibile
                                   # anche dopo un'espulsione del membro
    kind: str = ""
    target_type: str = ""         # "world" | "member" | "character" | ...
    target_id: str = ""
    summary: str = ""
    payload: str = "{}"
    before_state: str = "{}"
    created_at: str = ""


@dataclass
class WorldChangeRequest:
    """
    Richiesta del master di modificare un campo altrimenti vietato (§7.1) —
    punteggi, competenze, talenti, livello, scelte di classe. Il giocatore
    accetta o rifiuta; non usata prima del passo 3 (non esistono ancora
    istanze di personaggio su cui applicarla), ma vive nello schema fin da
    ora insieme al resto del modello mondo.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    world_id: str = ""
    character_id: str = ""
    requested_by: str = ""        # device_id del master richiedente
    payload: str = "{}"           # JSON: {"campo": nuovo_valore, ...}
    reason: str = ""
    status: str = "pending"       # "pending" | "accepted" | "rejected" | "expired"
    created_at: str = ""
    resolved_at: str = ""


@dataclass
class WorldRejoinRequest:
    """
    Richiesta del GIOCATORE di far rientrare nel mondo un'istanza di
    personaggio archiviata (rimossa dal master via `member.kick` o
    `CMD_CHARACTER_INSTANCE_REMOVE`) — verso opposto di `WorldChangeRequest`
    sopra: qui propone il giocatore, risponde il master. Non usata prima
    del passo 6 (nessuna istanza archiviata prima che esistessero le
    istanze/gli interventi del master), vive nello schema fin da ora insieme
    al resto del modello mondo.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    world_id: str = ""
    character_id: str = ""
    requested_by: str = ""        # device_id del proprietario del personaggio
    requester_name: str = ""      # copiato: leggibile anche se il device cambia nome
    mode: str = "frozen"          # "frozen" | "refresh_from_local"
    payload: str = "{}"           # JSON: {"export": {...}} SOLO se mode="refresh_from_local"
    reason: str = ""
    status: str = "pending"       # "pending" | "accepted" | "rejected" | "expired"
    created_at: str = ""
    resolved_at: str = ""


@dataclass
class WorldDeviceTransfer:
    """
    Codice monouso che autorizza un ALTRO dispositivo a subentrare
    nell'appartenenza di un membro, portandosi via le sue istanze di
    personaggio (2026-08-17, §11.9 del design doc).

    Vive SOLO sul dispositivo che ospita il mondo: è stato dell'host come il PIN
    e i token, non viaggia nell'export `.dndworld` e non viene replicato ai
    client. `code` non compare MAI nel payload di un `world_event` — il giornale
    è trasmesso a tutte le repliche, il codice è un segreto per un solo membro:
    torna al chiamante in `CommandResult.data`.

    `member_display_name` è copiato alla creazione con lo stesso criterio di
    `WorldRejoinRequest.requester_name`: resta leggibile per il master anche se
    il dispositivo di origine non si collega mai più.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    world_id: str = ""
    code: str = ""                # 8 caratteri, alfabeto senza 0/O/1/I/L
    member_device_id: str = ""    # il dispositivo da sostituire
    member_display_name: str = ""
    issued_by_device_id: str = ""  # il membro stesso, oppure un master/owner
    status: str = "pending"       # "pending" | "redeemed" | "revoked" | "expired"
    new_device_id: str = ""       # valorizzato al riscatto
    expires_at: str = ""          # ISO; oltre questa data il codice non vale più
    created_at: str = ""
    resolved_at: str = ""
