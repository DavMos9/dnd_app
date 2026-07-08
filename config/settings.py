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

# Livelli di Indebolimento (Exhaustion) — PHB IT, condizione cumulativa.
# {livello: descrizione effetto}. Ogni livello include gli effetti di tutti
# i livelli precedenti (cumulativi). Il livello 6 è letale.
EXHAUSTION_LEVELS: dict[int, str] = {
    1: "Svantaggio alle prove di caratteristica",
    2: "Velocità dimezzata",
    3: "Svantaggio ai tiri per colpire e ai tiri salvezza",
    4: "Massimo dei punti ferita dimezzato",
    5: "Velocità ridotta a 0",
    6: "Morte",
}

# Modificatore da punteggio: (punteggio - 10) // 2
def get_modifier(score: int) -> int:
    return (score - 10) // 2

def get_modifier_str(score: int) -> str:
    mod = get_modifier(score)
    return f"+{mod}" if mod >= 0 else str(mod)

def get_proficiency_bonus(level: int) -> int:
    return LEVEL_PROGRESSION.get(level, (0, 2))[1]

def char_prof_bonus(character) -> int:
    """
    Restituisce il bonus competenza effettivo del personaggio.
    Se proficiency_bonus_override > 0 usa quello (house rules),
    altrimenti usa la tabella PHB standard.
    """
    override = getattr(character, "proficiency_bonus_override", 0) or 0
    if override > 0:
        return override
    return get_proficiency_bonus(character.level)

def get_xp_for_level(level: int) -> int:
    return LEVEL_PROGRESSION.get(level, (0, 2))[0]

def get_level_from_xp(xp: int) -> int:
    level = 1
    for lvl, (req_xp, _) in LEVEL_PROGRESSION.items():
        if xp >= req_xp:
            level = lvl
    return level


def get_class_resource_defaults(
    class_name: str,
    level: int,
    character=None,
) -> list[dict]:
    """
    Restituisce le risorse di classe per la classe e il livello indicati.

    Ogni voce:
        {
            "name":         str,
            "max_value":    int,
            "current_value":int,       # uguale a max_value alla creazione
            "reset_on":     "short_rest" | "long_rest",
            "display_type": "circles"  | "counter",
        }

    display_type:
        "circles"  → cerchietti cliccabili (pool piccoli ≤ 6)
        "counter"  → counter −/+ numerico  (pool grandi o HP)
    """
    resources: list[dict] = []

    def _cha_mod() -> int:
        if character:
            return max(1, get_modifier(getattr(character, "cha_score", 10)))
        return 1

    def _r(name: str, max_val: int, reset_on: str,
           display_type: str | None = None) -> dict:
        dt = display_type if display_type else ("circles" if max_val <= 6 else "counter")
        return {
            "name": name,
            "max_value": max_val,
            "current_value": max_val,
            "reset_on": reset_on,
            "display_type": dt,
        }

    if class_name == "Barbaro":
        rage = 2
        if level >= 17:   rage = 6
        elif level >= 12: rage = 5
        elif level >= 6:  rage = 4
        elif level >= 3:  rage = 3
        resources.append(_r("Furia", rage, "long_rest"))

    elif class_name == "Bardo":
        insp = _cha_mod()
        reset = "short_rest" if level >= 5 else "long_rest"
        resources.append(_r("Ispirazione Bardica", insp, reset))

    elif class_name == "Chierico":
        cd = 1
        if level >= 18:  cd = 3
        elif level >= 6: cd = 2
        resources.append(_r("Incanalare Divinità", cd, "short_rest"))

    elif class_name == "Druido":
        if level >= 2:
            resources.append(_r("Forma Selvatica", 2, "short_rest"))

    elif class_name == "Guerriero":
        resources.append(_r("Ripresa", 1, "short_rest"))
        ba = 2 if level >= 17 else 1
        resources.append(_r("Baldanza d'Azione", ba, "short_rest"))

    elif class_name == "Monaco":
        if level >= 2:
            resources.append(_r("Punti Ki", level, "short_rest", "counter"))

    elif class_name == "Paladino":
        if level >= 3:
            resources.append(_r("Incanalare Divinità", 1, "short_rest"))
        resources.append(_r("Imposizione delle Mani", level * 5, "long_rest", "counter"))

    elif class_name == "Stregone":
        if level >= 2:
            resources.append(_r("Punti Stregoneria", level, "long_rest", "counter"))

    elif class_name == "Warlock":
        if level >= 17:   n = 4
        elif level >= 11: n = 3
        elif level >= 2:  n = 2
        else:             n = 1
        resources.append(_r("Slot del Patto", n, "short_rest"))

    elif class_name == "Mago":
        resources.append(_r("Recupero Arcano", 1, "long_rest"))

    # Ranger e Ladro: nessuna risorsa di classe base

    return resources

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

# Razze disponibili (lista piatta legacy — usata fuori dal wizard)
RACES = [
    "Elfo Alto", "Elfo dei Boschi", "Elfo Oscuro (Drow)",
    "Halfling Piedelesto", "Halfling Tozzo",
    "Nano delle Colline", "Nano della Montagna",
    "Umano",
    "Dragonide",
    "Gnomo delle Rocce", "Gnomo delle Foreste",
    "Mezzelfo",
    "Mezzorco",
    "Tiefling",
]

# Razze base (per wizard): race → lista sottorazze
# Dragonide usa DRACONIDE_ANCESTRIES, non subraces.
RACES_BASE: dict[str, list[str]] = {
    "Dragonide": [],
    "Elfo":      ["Elfo Alto", "Elfo dei Boschi", "Elfo Oscuro (Drow)"],
    "Gnomo":     ["Gnomo delle Foreste", "Gnomo delle Rocce"],
    "Halfling":  ["Halfling Piedelesto", "Halfling Tozzo"],
    "Mezzelfo":  [],
    "Mezzorco":  [],
    "Nano":      ["Nano della Montagna", "Nano delle Colline"],
    "Tiefling":  [],
    "Umano":     [],
}

# Discendenze del Dragonide (determina tipo soffio e resistenza)
# Riutilizzato anche per la Discendenza Draconiana dello Stregone
DRACONIDE_ANCESTRIES = [
    "Bianco", "Blu", "Verde", "Nero", "Rosso",
    "Oro", "Argento", "Rame", "Ottone", "Bronzo",
]

# Stili di combattimento PHB per classe (PHB p.72, p.84, p.91)
FIGHTING_STYLES: dict[str, list[str]] = {
    "guerriero": [
        "Tiro",
        "Combattere con Due Armi",
        "Difesa",
        "Duellare",
        "Combattere con Armi Possenti",
        "Protezione",
    ],
    "paladino": [
        "Difesa",
        "Duellare",
        "Combattere con Armi Possenti",
        "Protezione",
    ],
    "ranger": [
        "Tiro",
        "Combattere con Due Armi",
        "Difesa",
        "Duellare",
    ],
}

# Animali totem del Barbaro (Percorso del Totem Guerriero)
TOTEM_ANIMALS = ["Orso", "Aquila", "Lupo"]

# Terreni del Druido (Cerchio della Terra — Incantesimi del Cerchio)
LAND_TERRAINS = [
    "Artico", "Costa", "Deserto", "Foresta",
    "Montagna", "Piana", "Palude", "Sottosuolo",
]

# Trucchetti del Mago disponibili per l'Elfo Alto (PHB — lista completa)
MAGO_CANTRIPS = [
    "Amici", "Danno Acido", "Danza Delle Spade", "Fulmine Guida",
    "Getto di Veleno", "Illusione Minore", "Luce", "Mano del Mago",
    "Messaggio", "Occhio del Mago", "Prestidigitazione",
    "Raggio di Gelo", "Raggio di Fuoco", "Scossa Tonante",
    "Saggio Mano", "Tocco del Gelo",
]

# Opzioni di Metamagia dello Stregone (PHB p.102)
METAMAGIC_OPTIONS = [
    "Incantesimo Attento",      # Careful Spell  — 1 PS: alleati esclusi dall'area
    "Incantesimo Distante",     # Distant Spell  — 1 PS: raddoppia gittata
    "Potenziamento Incantesimo",# Empowered Spell — 1 PS: rilancia N dadi danno
    "Estensione Incantesimo",   # Extended Spell  — 1 PS: raddoppia durata
    "Intensificazione",         # Heightened Spell— 3 PS: bersaglio svantaggio al TS
    "Velocizzazione Incantesimo",# Quickened Spell — 2 PS: lanci come azione bonus
    "Occultamento Incantesimo", # Subtle Spell    — 1 PS: niente componenti V/S
    "Incantesimo Gemellato",    # Twinned Spell   — 1+ PS: colpisce 2 bersagli
]

# Doni del Patto del Warlock (PHB p.107)
PACT_BOONS = [
    "Patto della Catena",  # Famiglio potenziato
    "Patto della Lama",    # Arma del patto evocata
    "Patto del Tomo",      # Libro delle Ombre (3 trucchetti extra)
]

# Lingue D&D 5e (PHB)
LANGUAGES = [
    "Comune", "Nanico", "Elfico", "Gigante", "Gnomesco", "Goblin",
    "Halfling", "Orchesco", "Abissale", "Celeste", "Draconico",
    "Silvano", "Sottocomune", "Infernale", "Primordiale",
]

# Strumenti per categoria (mappati dai 'from' dei JSON background)
ARTISAN_TOOLS = [
    "Strumenti da Fabbro", "Strumenti da Birraio", "Strumenti da Muratore",
    "Strumenti da Calligrafo", "Strumenti da Falegname", "Strumenti da Calzolaio",
    "Strumenti da Cuoco", "Strumenti da Vetraio", "Strumenti da Gioielliere",
    "Strumenti da Conciatore", "Strumenti da Scalpellino", "Strumenti da Pittore",
    "Strumenti da Vasaio", "Strumenti da Fabbricante di Archi",
    "Strumenti da Sarto", "Strumenti da Calderaio", "Strumenti da Tessitore",
    "Strumenti da Armaolo",
]
MUSICAL_INSTRUMENTS = [
    "Cornamusa", "Batacchio", "Flauto", "Liuto",
    "Lira", "Corno", "Piffero", "Tamburello", "Tromba", "Viola",
]
GAMING_SETS = ["Carte da Gioco", "Dadi", "Scacchi dei Draghi", "Tre Draghi"]

# 'from' key nei JSON background → lista opzioni selezionabili
TOOL_CATEGORIES: dict[str, list[str]] = {
    "strumenti_artigiani":           ARTISAN_TOOLS,
    "strumenti_musicali":            MUSICAL_INSTRUMENTS,
    "strumenti_artigiani_o_musicali": ARTISAN_TOOLS + MUSICAL_INSTRUMENTS,  # Monaco PHB
    "gioco_carte":                   ["Carte da Gioco"],
    "gioco_dadi":                    ["Dadi"],
    "scacchi":                       ["Scacchi dei Draghi"],
    "gioco_tre_draghi":              ["Tre Draghi"],
    "altro_gioco":                   GAMING_SETS,
}

# Label singola per chiave categoria (usata quando 'from' è una lista di chiavi)
TOOL_CATEGORY_LABEL: dict[str, str] = {
    "gioco_carte":      "Carte da Gioco",
    "gioco_dadi":       "Dadi",
    "scacchi":          "Scacchi dei Draghi",
    "gioco_tre_draghi": "Tre Draghi",
    "altro_gioco":      "Altro gioco a scelta",
}

# ---------------------------------------------------------------------------
# Lista armi PHB 5e italiano (tabella p.149)
# ---------------------------------------------------------------------------
WEAPONS_SEMPLICI_MISCHIA = [
    "Ascia", "Bastone Ferrato", "Falcetto", "Giavellotto",
    "Lancia", "Martello Leggero", "Mazza", "Pugnale",
    "Randello", "Randello Pesante",
]
WEAPONS_SEMPLICI_DISTANZA = [
    "Arco Corto", "Balestra Leggera", "Dardo", "Fionda",
]
WEAPONS_GUERRA_MISCHIA = [
    "Alabarda", "Ascia Bipenne", "Ascia da Battaglia",
    "Falcione", "Frusta", "Lancia da Cavaliere", "Maglio",
    "Martello da Guerra", "Mazzafrusto", "Morning Star", "Picca",
    "Piccone da Guerra", "Scimitarra", "Spada Corta", "Spada Lunga",
    "Spadone", "Stocco", "Tridente",
]
WEAPONS_GUERRA_DISTANZA = [
    "Arco Lungo", "Balestra a Mano", "Balestra Pesante",
    "Cerbottana", "Rete",
]

# Categorie usate nel weapon picker (equipment JSON: "category")
WEAPONS_BY_CATEGORY: dict[str, list[str]] = {
    "semplice":         sorted(WEAPONS_SEMPLICI_MISCHIA + WEAPONS_SEMPLICI_DISTANZA),
    "semplice_mischia": sorted(WEAPONS_SEMPLICI_MISCHIA),
    "guerra":           sorted(WEAPONS_GUERRA_MISCHIA + WEAPONS_GUERRA_DISTANZA),
    "guerra_mischia":   sorted(WEAPONS_GUERRA_MISCHIA),
}

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
    "Nano della Montagna": {
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
    "Elfo Alto": {
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
    "Halfling Piedelesto": {
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
    "Halfling Tozzo": {
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


# ---------------------------------------------------------------------------
# Risorse razziali — tratti con usi limitati e resistenze
# ---------------------------------------------------------------------------

def get_race_resource_defaults(
    race_name: str,
    subrace: str,
    level: int,
) -> list[dict]:
    """
    Legge il JSON della razza e restituisce le risorse razziali attive
    al livello indicato (es. Soffio del Dragonide, Resistenza Implacabile).

    Ogni voce:
        {
            "name":         str,
            "max_value":    int,
            "current_value":int,
            "reset_on":     "short_rest" | "long_rest",
            "display_type": "circles" | "counter",
        }
    """
    import json as _json
    import os as _os

    races_dir = _os.path.join(
        _os.path.dirname(_os.path.dirname(__file__)),
        "data", "game_data", "races",
    )

    # Normalizza il nome razza → nome file
    race_key = race_name.lower().replace(" ", "").replace("'", "")
    candidate = _os.path.join(races_dir, f"{race_key}.json")
    if not _os.path.exists(candidate):
        return []

    try:
        with open(candidate, encoding="utf-8") as fh:
            data = _json.load(fh)
    except Exception:
        return []

    resources: list[dict] = []

    def _extract_resources(traits: list[dict]) -> None:
        for trait in traits:
            # Risorsa singola
            res = trait.get("resource")
            if res and level >= res.get("min_level", 1):
                resources.append({
                    "name":          res["name"],
                    "max_value":     res["max_value"],
                    "current_value": res["max_value"],
                    "reset_on":      res.get("reset_on", "long_rest"),
                    "display_type":  res.get("display_type", "circles"),
                })
            # Risorse multiple (es. Eredità Infernale, Magia Drow)
            for res in trait.get("resources", []):
                if level >= res.get("min_level", 1):
                    resources.append({
                        "name":          res["name"],
                        "max_value":     res["max_value"],
                        "current_value": res["max_value"],
                        "reset_on":      res.get("reset_on", "long_rest"),
                        "display_type":  res.get("display_type", "circles"),
                    })

    # Tratti base
    _extract_resources(data.get("traits", []))

    # Tratti della sottorazza selezionata
    subrace_norm = (subrace or "").lower().strip()
    if subrace_norm:
        for sr in data.get("subraces", []):
            if sr.get("name", "").lower() in subrace_norm or subrace_norm in sr.get("name", "").lower():
                _extract_resources(sr.get("traits", []))
                break

    return resources


def get_race_display_traits(
    race_name: str,
    subrace: str,
) -> dict:
    """
    Restituisce un dizionario con resistenze, vantaggi ai TS e tratti passivi
    rilevanti per la razza/sottorazza, da mostrare nel tab Combattimento.

    Ritorna:
        {
            "resistances":    list[str],   # es. ["Fuoco", "Veleno"]
            "advantage_saves":list[str],   # es. ["Veleno"]
            "passive_traits": list[str],   # es. ["Resistenza Implacabile (testo)"]
        }
    """
    import json as _json
    import os as _os

    races_dir = _os.path.join(
        _os.path.dirname(_os.path.dirname(__file__)),
        "data", "game_data", "races",
    )

    race_key = race_name.lower().replace(" ", "").replace("'", "")
    candidate = _os.path.join(races_dir, f"{race_key}.json")
    if not _os.path.exists(candidate):
        return {"resistances": [], "advantage_saves": [], "passive_traits": []}

    try:
        with open(candidate, encoding="utf-8") as fh:
            data = _json.load(fh)
    except Exception:
        return {"resistances": [], "advantage_saves": [], "passive_traits": []}

    # Mappa danno (usata per Dragonide)
    DRAGON_DAMAGE: dict[str, str] = {
        "bianco": "Freddo", "blu": "Fulmine", "ottone": "Fuoco",
        "bronzo": "Fulmine", "rame": "Acido", "oro": "Fuoco",
        "argento": "Freddo", "nero": "Acido", "verde": "Veleno",
        "rosso": "Fuoco",
    }

    resistances: list[str] = []
    advantage_saves: list[str] = []
    passive_traits: list[str] = []

    _DAMAGE_IT = {
        "fire": "Fuoco", "poison": "Veleno", "cold": "Freddo",
        "lightning": "Fulmine", "acid": "Acido", "necrotic": "Necrotico",
        "radiant": "Radiante", "thunder": "Tuono", "psychic": "Psichico",
        "force": "Forza", "bludgeoning": "Contundente",
        "piercing": "Perforante", "slashing": "Tagliante",
    }
    _SAVE_IT = {"poison": "Veleno", "charm": "Charme", "fear": "Paura"}

    def _scan(traits: list[dict]) -> None:
        for t in traits:
            for dmg in t.get("resistance", []):
                label = _DAMAGE_IT.get(str(dmg), str(dmg).capitalize())
                if label not in resistances:
                    resistances.append(label)
            if t.get("resistance_by_ancestry"):
                resistances.append("(vedi Discendenza Draconiana)")
            for sv in t.get("advantage_save", []):
                label = _SAVE_IT.get(str(sv), str(sv).capitalize())
                if label not in advantage_saves:
                    advantage_saves.append(label)

    _scan(data.get("traits", []))

    # Dragonide: aggiunge resistenza basata su sottorazza (tipo drago)
    if data.get("name", "").lower() == "dragonide" and subrace:
        sub_key = subrace.lower().strip()
        dmg = DRAGON_DAMAGE.get(sub_key)
        if dmg:
            # Sostituisce il placeholder generico
            if "(vedi Discendenza Draconiana)" in resistances:
                resistances.remove("(vedi Discendenza Draconiana)")
            if dmg not in resistances:
                resistances.append(dmg)

    # Sottorazza
    subrace_norm = (subrace or "").lower().strip()
    if subrace_norm:
        for sr in data.get("subraces", []):
            if sr.get("name", "").lower() in subrace_norm or subrace_norm in sr.get("name", "").lower():
                _scan(sr.get("traits", []))
                break

    return {
        "resistances":    resistances,
        "advantage_saves": advantage_saves,
        "passive_traits": passive_traits,
    }
