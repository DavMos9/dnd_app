"""
Configurazione globale dell'app: colori, font, costanti di gioco.
"""

APP_NAME = "D&D Companion"
APP_VERSION = "0.1.0"
DB_NAME = "dnd_companion.db"

# ---------------------------------------------------------------------------
# Palette Pergamena & Avventura — sfondo pergamena, rosso D&D + blu reale
# ---------------------------------------------------------------------------
COLOR_BG_PRIMARY       = "#f5f0e8"   # pergamena calda (sfondo principale)
COLOR_BG_SECONDARY     = "#ece5d8"   # pergamena leggermente più scura (stat bar, header)
COLOR_BG_CARD          = "#ffffff"   # bianco puro (card, pannelli)
COLOR_BG_TAB_ACTIVE    = "#ffffff"   # tab attivo: bianco puro
COLOR_BG_TAB_INACTIVE  = "#e8e1d4"   # tab inattivo: pergamena
COLOR_BG_SELECTED      = "#dce8f8"   # selezione attiva (blu tenue)

COLOR_ACCENT_CRIMSON   = "#c0182c"   # rosso D&D – accento principale
COLOR_ACCENT_GOLD      = "#1848a0"   # blu reale – accento secondario (nome legacy)
COLOR_ACCENT_AMBER     = "#b86800"   # ambra/oro per warning e HP
COLOR_ACCENT_BLUE      = "#1848a0"   # blu reale – magia, modificatori
COLOR_ACCENT_GREEN     = "#1a6b30"   # verde selvatico – valori positivi
COLOR_ACCENT_RED       = "#c0182c"   # alias rosso (= CRIMSON)

# Colori testo — scuri leggibili su sfondo chiaro
COLOR_TEXT_PRIMARY     = "#1c1e2c"   # inchiostro quasi nero – testo principale
COLOR_TEXT_SECONDARY   = "#3c4060"   # blu-ardesia scuro – label, sottotitoli (più visibile)
COLOR_TEXT_MUTED       = "#7880a0"   # grigio-blu – placeholder, info secondaria
COLOR_TEXT_TITLE       = "#0a0c1c"   # nero profondo – nomi e titoli

COLOR_BORDER           = "#c8c0b0"   # bordo pergamena dorata
COLOR_BORDER_ACCENT    = "#1848a0"   # bordo blu – evidenziato
COLOR_BORDER_STRONG    = "#c0182c"   # bordo rosso – elementi importanti

COLOR_HP_FULL          = "#186030"   # verde vitale scuro
COLOR_HP_MID           = "#b86800"   # ambra attenzione
COLOR_HP_LOW           = "#c0182c"   # rosso pericolo

COLOR_SLOT_FULL        = "#1848a0"   # slot incantesimo disponibile (blu)
COLOR_SLOT_USED        = "#e8e1d4"   # slot incantesimo usato

# Sidebar (nav rail) — scura per contrasto, stile cuoio scuro D&D
COLOR_NAV_BG           = "#1a0808"   # rosso-nero quasi nero (sidebar)
COLOR_NAV_TEXT         = "#f0e8e0"   # testo chiaro nella sidebar
COLOR_NAV_MUTED        = "#806878"   # testo secondario sidebar

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


# Livelli in cui si ottiene un ASI (Ability Score Improvement) per classe — PHB 5e
ASI_LEVELS: dict[str, set[int]] = {
    "Guerriero": {4, 6, 8, 12, 14, 16, 19},
    "Ladro":     {4, 8, 10, 12, 16, 19},
}
ASI_LEVELS_DEFAULT: set[int] = {4, 8, 12, 16, 19}

# Tiri salvezza competenti per classe — PHB 5e
CLASS_SAVING_THROWS: dict[str, list[str]] = {
    "Barbaro":   ["Forza", "Costituzione"],
    "Bardo":     ["Destrezza", "Carisma"],
    "Chierico":  ["Saggezza", "Carisma"],
    "Druido":    ["Intelligenza", "Saggezza"],
    "Guerriero": ["Forza", "Costituzione"],
    "Ladro":     ["Destrezza", "Intelligenza"],
    "Mago":      ["Intelligenza", "Saggezza"],
    "Monaco":    ["Forza", "Destrezza"],
    "Paladino":  ["Saggezza", "Carisma"],
    "Ranger":    ["Forza", "Destrezza"],
    "Stregone":  ["Costituzione", "Carisma"],
    "Warlock":   ["Saggezza", "Carisma"],
}

# Standard array D&D 5e
STANDARD_ARRAY = [15, 14, 13, 12, 10, 8]

# Point buy: costo per punteggio
POINT_BUY_COSTS = {8: 0, 9: 1, 10: 2, 11: 3, 12: 4, 13: 5, 14: 7, 15: 9}
POINT_BUY_BUDGET = 27

# ---------------------------------------------------------------------------
# Dati Razziali — PHB 5e italiano
# ability_bonuses: dict {stat_key: bonus} applicati ai punteggi base
# ability_bonuses_flex: N slot da +1 a scelta del giocatore (es. Mezzelfo)
# speed: velocità in metri
# darkvision: distanza scurovisione in metri (None = nessuna)
# traits: lista di tratti speciali della razza
# ---------------------------------------------------------------------------
RACE_DATA: dict[str, dict] = {
    "Nano delle Colline": {
        "ability_bonuses": {"con": 2, "wis": 1},
        "ability_bonuses_flex": 0,
        "speed": 7.5,
        "darkvision": 18,
        "traits": [
            "Resistenza Nanica — vantaggio ai tiri salvezza vs veleni, resistenza al danno da veleno",
            "Competenza in armi — ascia da guerra, ascia leggera, martello leggero, martello da guerra",
            "Formazione in attrezzi — scegli tra strumenti da ferraro, birraio o falegname",
            "Scaltrezza della pietra — vantaggio alle prove di Storia su architettura, pietra e oggetti di pietra",
            "Tenacia dei Colli — punti ferita massimi aumentano di 1 per ogni livello",
        ],
    },
    "Nano delle Montagne": {
        "ability_bonuses": {"con": 2, "str": 2},
        "ability_bonuses_flex": 0,
        "speed": 7.5,
        "darkvision": 18,
        "traits": [
            "Resistenza Nanica — vantaggio ai tiri salvezza vs veleni, resistenza al danno da veleno",
            "Competenza in armi — ascia da guerra, ascia leggera, martello leggero, martello da guerra",
            "Addestramento con armature — competenza nelle armature leggere e medie",
            "Scaltrezza della pietra — vantaggio alle prove di Storia su architettura e pietra",
        ],
    },
    "Elfo (Alto)": {
        "ability_bonuses": {"dex": 2, "int": 1},
        "ability_bonuses_flex": 0,
        "speed": 9,
        "darkvision": 18,
        "traits": [
            "Sensi affinati — competenza nell'abilità Percezione",
            "Discendenza fatata — vantaggio ai tiri salvezza vs incantesimi e altri effetti magici",
            "Transe — non hai bisogno di dormire; il riposo lungo richiede 4 ore di meditazione",
            "Competenza in armi elfici — spada corta, spada lunga, arco corto, arco lungo",
            "Trucchetto da Mago — conosci un trucchetto a scelta dall'elenco del Mago (INT)",
            "Lingua aggiuntiva — una lingua a scelta",
        ],
    },
    "Elfo dei Boschi": {
        "ability_bonuses": {"dex": 2, "wis": 1},
        "ability_bonuses_flex": 0,
        "speed": 10.5,
        "darkvision": 18,
        "traits": [
            "Sensi affinati — competenza nell'abilità Percezione",
            "Discendenza fatata — vantaggio ai tiri salvezza vs incantesimi e altri effetti magici",
            "Transe — non hai bisogno di dormire; il riposo lungo richiede 4 ore di meditazione",
            "Competenza in armi elfici — spada corta, spada lunga, arco corto, arco lungo",
            "Passo del bosco — ignori il terreno difficile nei boschi; puoi muoverti silenziosamente",
            "Mascheramento naturale — puoi tentare di nasconderti in terreno naturale (vegetazione, pioggia, neve)",
        ],
    },
    "Elfo Oscuro (Drow)": {
        "ability_bonuses": {"dex": 2, "cha": 1},
        "ability_bonuses_flex": 0,
        "speed": 9,
        "darkvision": 36,
        "traits": [
            "Scurovisione superiore — 36 metri (vista nella luce fioca come se fosse luminosa, buio come luce fioca)",
            "Sensibilità alla luce solare — svantaggio ai tiri per colpire e alle prove di Percezione basate sulla vista se tu, il bersaglio o ciò che cerchi di vedere è in luce solare diretta",
            "Discendenza fatata — vantaggio ai tiri salvezza vs incantesimi",
            "Competenza in armi Drow — rapier, balestra a mano, spada corta",
            "Magia Drow — Luce danzante (trucco), Fata Fuoco 1/riposo lungo (SAG), Oscurità 1/riposo lungo (SAG)",
        ],
    },
    "Halfling (Piedelesto)": {
        "ability_bonuses": {"dex": 2, "cha": 1},
        "ability_bonuses_flex": 0,
        "speed": 7.5,
        "darkvision": None,
        "traits": [
            "Fortuna — quando ottieni un 1 naturale su un tiro per colpire, prova di caratteristica o tiro salvezza, puoi ritirare il dado e devi usare il nuovo risultato",
            "Coraggioso — vantaggio ai tiri salvezza contro la condizione di spavento",
            "Agilità Halfling — puoi muoverti attraverso lo spazio di qualsiasi creatura di taglia superiore alla tua",
            "Nascondersi agevolmente — puoi tentare di nasconderti dietro creature di taglia Media o più grande",
        ],
    },
    "Halfling (Tozzo)": {
        "ability_bonuses": {"dex": 2, "con": 1},
        "ability_bonuses_flex": 0,
        "speed": 7.5,
        "darkvision": None,
        "traits": [
            "Fortuna — quando ottieni un 1 naturale, puoi ritirare il dado",
            "Coraggioso — vantaggio ai tiri salvezza contro la condizione di spavento",
            "Agilità Halfling — puoi muoverti attraverso lo spazio di creature più grandi di te",
            "Resistenza Halfling — vantaggio ai tiri salvezza vs veleni; resistenza al danno da veleno",
        ],
    },
    "Umano": {
        "ability_bonuses": {"str": 1, "dex": 1, "con": 1, "int": 1, "wis": 1, "cha": 1},
        "ability_bonuses_flex": 0,
        "speed": 9,
        "darkvision": None,
        "traits": [
            "+1 a tutte e sei le caratteristiche — incredibile versatilità e adattabilità",
            "Competenza aggiuntiva — competenza in una lingua aggiuntiva a scelta",
        ],
    },
    "Dragonide": {
        "ability_bonuses": {"str": 2, "cha": 1},
        "ability_bonuses_flex": 0,
        "speed": 9,
        "darkvision": None,
        "traits": [
            "Lignaggio Draconico — scegli l'antenato draconico: determina tipo di danno e resistenza",
            "Arma Soffio — azione: CA 8 + bonus competenza + mod DES (area cono o linea, danni da 2d6 a Lv.1/5°→3d6/11°→4d6/17°→5d6). 1 uso per riposo breve/lungo",
            "Resistenza ai Danni — resistenza al tipo di danno del tuo antenato draconico",
        ],
    },
    "Gnomo delle Rocce": {
        "ability_bonuses": {"int": 2, "con": 1},
        "ability_bonuses_flex": 0,
        "speed": 7.5,
        "darkvision": 18,
        "traits": [
            "Scaltrezza Gnoma — vantaggio ai tiri salvezza di Intelligenza, Saggezza e Carisma contro la magia",
            "Conoscenza Artificiere — ogni volta che effettui una prova di Intelligenza (Storia) relativa a oggetti magici, oggetti alchemici o congegni tecnologici, puoi aggiungere il doppio del bonus competenza",
            "Illusione Artificiere — trucchetto Illusione Minore modificato: puoi creare suoni e immagini (INT)",
            "Comunicare con costrutti — puoi comunicare concetti semplici a creature meccaniche/costrutti entro 30 m",
        ],
    },
    "Gnomo delle Foreste": {
        "ability_bonuses": {"int": 2, "dex": 1},
        "ability_bonuses_flex": 0,
        "speed": 7.5,
        "darkvision": 18,
        "traits": [
            "Scaltrezza Gnoma — vantaggio ai tiri salvezza di INT, SAG e CAR contro la magia",
            "Illusione Naturale — conosci il trucchetto Illusione Minore (INT)",
            "Parlare con gli Animali Piccoli — puoi comunicare con bestie di taglia Piccola o più piccola",
        ],
    },
    "Mezzelfo": {
        "ability_bonuses": {"cha": 2},
        "ability_bonuses_flex": 2,  # +1 a 2 caratteristiche a scelta (non CAR)
        "speed": 9,
        "darkvision": 18,
        "traits": [
            "+1 a due caratteristiche a scelta (escluso Carisma) — grande flessibilità",
            "Discendenza fatata — vantaggio ai tiri salvezza vs incantesimi e altri effetti magici",
            "Transe — non hai bisogno di dormire; il riposo lungo richiede 4 ore di meditazione",
            "Versatilità — competenza in due abilità a scelta",
        ],
    },
    "Mezzorco": {
        "ability_bonuses": {"str": 2, "con": 1},
        "ability_bonuses_flex": 0,
        "speed": 9,
        "darkvision": 18,
        "traits": [
            "Minaccioso — competenza nell'abilità Intimidire",
            "Resistenza Implacabile — quando scendi a 0 PF per la prima volta in uno scontro, rimani invece a 1 PF (1 uso, ripristinato dopo riposo lungo)",
            "Attacchi Feroci — quando ottieni un colpo critico con un attacco in mischia, tira uno dei dadi danno dell'arma una volta aggiuntiva e somma al danno extra",
        ],
    },
    "Tiefling": {
        "ability_bonuses": {"int": 1, "cha": 2},
        "ability_bonuses_flex": 0,
        "speed": 9,
        "darkvision": 18,
        "traits": [
            "Resistenza Infernale — resistenza al danno da fuoco",
            "Eredità Infernale — Thaumaturgy (trucco, CAR); Hellish Rebuke come incantesimo di 2° livello 1/riposo lungo (CAR); Darkness come incantesimo di 2° livello 1/riposo lungo (CAR)",
        ],
    },
}
