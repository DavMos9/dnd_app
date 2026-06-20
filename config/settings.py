"""
Configurazione globale dell'app: colori, font, costanti di gioco.
"""

APP_NAME = "D&D Companion"
APP_VERSION = "0.1.0"
DB_NAME = "dnd_companion.db"

# ---------------------------------------------------------------------------
# Palette fantasy
# ---------------------------------------------------------------------------
COLOR_BG_PRIMARY       = "#1a1209"   # sfondo principale (quasi nero, caldo)
COLOR_BG_SECONDARY     = "#251a0e"   # sfondo secondario
COLOR_BG_CARD          = "#2e1f0f"   # sfondo card / pannelli
COLOR_BG_TAB_ACTIVE    = "#3d2a12"   # tab attivo
COLOR_BG_TAB_INACTIVE  = "#1f1508"   # tab inattivo

COLOR_ACCENT_GOLD      = "#c9a84c"   # oro – titoli, bordi, accenti
COLOR_ACCENT_RED       = "#8b1a1a"   # rosso sangue – HP, pericolo
COLOR_ACCENT_BLUE      = "#2a4a7f"   # blu arcano – magia, slot
COLOR_ACCENT_GREEN     = "#2d5a27"   # verde – valori positivi

COLOR_TEXT_PRIMARY     = "#e8d5b0"   # testo principale (panna calda)
COLOR_TEXT_SECONDARY   = "#a08c6e"   # testo secondario (grigio dorato)
COLOR_TEXT_MUTED       = "#6b5940"   # testo disabilitato / placeholder
COLOR_TEXT_TITLE       = "#c9a84c"   # titoli in oro

COLOR_BORDER           = "#5a3e1b"   # bordi pannelli
COLOR_BORDER_ACCENT    = "#c9a84c"   # bordi evidenziati in oro

COLOR_HP_FULL          = "#2d8a27"   # HP piena – verde
COLOR_HP_MID           = "#c9a84c"   # HP metà – oro
COLOR_HP_LOW           = "#8b1a1a"   # HP bassa – rosso

COLOR_SLOT_FULL        = "#2a4a7f"   # slot incantesimo disponibile
COLOR_SLOT_USED        = "#1a1209"   # slot incantesimo usato

# ---------------------------------------------------------------------------
# Font
# ---------------------------------------------------------------------------
FONT_TITLE  = "Georgia"    # titoli e intestazioni
FONT_BODY   = "Arial"      # corpo testo
FONT_MONO   = "Courier New" # valori numerici

# ---------------------------------------------------------------------------
# Costanti D&D 5e
# ---------------------------------------------------------------------------

# Progressione livelli: {livello: (PE_richiesti, bonus_competenza)}
LEVEL_PROGRESSION = {
    1:  (0,       2),
    2:  (300,     2),
    3:  (900,     2),
    4:  (2700,    2),
    5:  (6500,    3),
    6:  (14000,   3),
    7:  (23000,   3),
    8:  (34000,   3),
    9:  (48000,   4),
    10: (64000,   4),
    11: (85000,   4),
    12: (100000,  4),
    13: (120000,  5),
    14: (140000,  5),
    15: (165000,  5),
    16: (195000,  5),
    17: (225000,  6),
    18: (265000,  6),
    19: (305000,  6),
    20: (355000,  6),
}

# Modificatore da punteggio: (punteggio - 10) // 2
def get_modifier(score: int) -> int:
    return (score - 10) // 2

def get_modifier_str(score: int) -> str:
    mod = get_modifier(score)
    return f"+{mod}" if mod >= 0 else str(mod)

def get_proficiency_bonus(level: int) -> int:
    return LEVEL_PROGRESSION.get(level, (0, 2))[1]

def get_xp_for_level(level: int) -> int:
    return LEVEL_PROGRESSION.get(level, (0, 2))[0]

def get_level_from_xp(xp: int) -> int:
    level = 1
    for lvl, (req_xp, _) in LEVEL_PROGRESSION.items():
        if xp >= req_xp:
            level = lvl
    return level

# Statistiche base
ABILITY_SCORES = ["Forza", "Destrezza", "Costituzione", "Intelligenza", "Saggezza", "Carisma"]
ABILITY_ABBR   = ["FOR",   "DES",       "COS",          "INT",          "SAG",      "CAR"]
ABILITY_KEYS   = ["str",   "dex",       "con",          "int",          "wis",      "cha"]

# Abilità → caratteristica
SKILLS = {
    "Acrobazia":         "dex",
    "Addestrare Animali":"wis",
    "Arcano":            "int",
    "Atletica":          "str",
    "Furtività":         "dex",
    "Indagare":          "int",
    "Inganno":           "cha",
    "Intimidire":        "cha",
    "Intrattenere":      "cha",
    "Intuizione":        "wis",
    "Medicina":          "wis",
    "Natura":            "int",
    "Percezione":        "wis",
    "Persuasione":       "cha",
    "Rapidità di Mano":  "dex",
    "Religione":         "int",
    "Sopravvivenza":     "wis",
    "Storia":            "int",
}

# Allineamenti
ALIGNMENTS = [
    "Legale Buono", "Neutrale Buono", "Caotico Buono",
    "Legale Neutrale", "Neutrale", "Caotico Neutrale",
    "Legale Malvagio", "Neutrale Malvagio", "Caotico Malvagio",
]

# Razze disponibili
RACES = [
    "Elfo (Alto)", "Elfo dei Boschi", "Elfo Oscuro (Drow)",
    "Halfling (Piedelesto)", "Halfling (Tozzo)",
    "Nano delle Colline", "Nano delle Montagne",
    "Umano",
    "Dragonide",
    "Gnomo delle Rocce", "Gnomo delle Foreste",
    "Mezzelfo",
    "Mezzorco",
    "Tiefling",
]

# Classi disponibili con dado vita e caratteristica da incantatore
CLASSES = {
    "Barbaro":  {"hit_die": 12, "spellcasting_ability": None},
    "Bardo":    {"hit_die": 8,  "spellcasting_ability": "cha"},
    "Chierico": {"hit_die": 8,  "spellcasting_ability": "wis"},
    "Druido":   {"hit_die": 8,  "spellcasting_ability": "wis"},
    "Guerriero":{"hit_die": 10, "spellcasting_ability": None},
    "Ladro":    {"hit_die": 8,  "spellcasting_ability": None},
    "Mago":     {"hit_die": 6,  "spellcasting_ability": "int"},
    "Monaco":   {"hit_die": 8,  "spellcasting_ability": None},
    "Paladino": {"hit_die": 10, "spellcasting_ability": "cha"},
    "Ranger":   {"hit_die": 10, "spellcasting_ability": "wis"},
    "Stregone": {"hit_die": 6,  "spellcasting_ability": "cha"},
    "Warlock":  {"hit_die": 8,  "spellcasting_ability": "cha"},
}

# Valute (ordine crescente di valore)
CURRENCIES = ["MR", "MA", "ME", "MO", "MP"]
CURRENCY_NAMES = {
    "MR": "Monete di Rame",
    "MA": "Monete d'Argento",
    "ME": "Monete di Elettro",
    "MO": "Monete d'Oro",
    "MP": "Monete di Platino",
}

# Standard array D&D 5e
STANDARD_ARRAY = [15, 14, 13, 12, 10, 8]

# Point buy: costo per punteggio
POINT_BUY_COSTS = {8: 0, 9: 1, 10: 2, 11: 3, 12: 4, 13: 5, 14: 7, 15: 9}
POINT_BUY_BUDGET = 27
