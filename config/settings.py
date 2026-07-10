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
        if level >= 20:
            # Furia illimitata dal 20° livello — nessun pool da tracciare.
            resources.append({
                "name": "Furia",
                "max_value": -1,
                "current_value": -1,
                "reset_on": "long_rest",
                "display_type": "unlimited",
            })
        else:
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
        if level >= 2:
            cd = 1
            if level >= 18:  cd = 3
            elif level >= 6: cd = 2
            resources.append(_r("Incanalare Divinità", cd, "short_rest"))

    elif class_name == "Druido":
        if level >= 2:
            resources.append(_r("Forma Selvatica", 2, "short_rest"))

    elif class_name == "Guerriero":
        resources.append(_r("Recupera Energie", 1, "short_rest"))
        if level >= 2:
            ba = 2 if level >= 17 else 1
            resources.append(_r("Azione Impetuosa", ba, "short_rest"))

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

    elif class_name == "Mago":
        resources.append(_r("Recupero Arcano", 1, "long_rest"))

    # Warlock: gli slot del Patto della Magia sono già gestiti tramite la
    # tabella standard degli slot incantesimo (_WARLOCK_SLOTS in character_repo.py),
    # che li ripristina correttamente a riposo breve — nessuna risorsa duplicata qui.
    # Ranger e Ladro: nessuna risorsa di classe base.

    return resources


def get_permanent_class_hp_bonus(class_name: str, subclass: str, level: int) -> int:
    """
    Bonus permanente ai PF massimi concesso da capacità di classe/sottoclasse
    non temporanee (Categoria A dell'audit 2026-07-09), da sommare oltre al
    normale calcolo dado vita + modificatore Costituzione.

    Restituisce il TOTALE accumulato fino al livello indicato (non un delta):
    chi chiama deve calcolare la differenza tra il valore al nuovo livello e
    quello al vecchio livello per ottenere il PF da aggiungere/rimuovere.

    Casi gestiti:
      - Stregone, Discendenza Draconica → Resilienza Draconica:
        +1 PF massimo per ogni livello da stregone (PHB, cumulativo dal lv1).
    """
    if class_name == "Stregone" and subclass == "Discendenza Draconica":
        return max(0, level)
    return 0

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
# Riutilizzato anche per la Discendenza Draconica dello Stregone
DRACONIDE_ANCESTRIES = [
    "Bianco", "Blu", "Verde", "Nero", "Rosso",
    "Oro", "Argento", "Rame", "Ottone", "Bronzo",
]

# ---------------------------------------------------------------------------
# Dati di Classe (stili di combattimento, totem, terreni, metamagia, patti,
# trucchetti Mago) — RIMOSSI (2026-07-09), stesso refactor di RACE_DATA sopra.
#
# In precedenza qui vivevano FIGHTING_STYLES, TOTEM_ANIMALS, LAND_TERRAINS,
# MAGO_CANTRIPS, METAMAGIC_OPTIONS, PACT_BOONS: liste Python scritte a mano,
# duplicate rispetto ai dati già presenti (o aggiunti in questo stesso
# refactor) nei JSON di data/game_data/classes/. Motivazione identica a
# RACE_DATA: singola fonte di verità nei JSON, il codice deve solo leggerli.
#
# Sostituite da metodi su GameDataLoader (data/game_data/game_data_loader.py):
#   get_fighting_styles(class_name)   -> legge fighting_style_details
#                                         (guerriero.json) o le "options" della
#                                         feature "Stile di Combattimento"
#                                         (paladino.json / ranger.json)
#   get_totem_animals()               -> barbaro.json, feature "Spirito
#                                         Totemico" -> options
#   get_land_terrains()               -> druido.json, chiavi di circle_spells
#   get_mago_cantrips()               -> spells/incantesimi_mago.json
#                                         (livello 0), NON mago.json: gli
#                                         incantesimi/trucchetti vivono solo
#                                         nel loro file dedicato, mai duplicati
#                                         nel JSON di classe. I 16 nomi sono
#                                         già stati sostituiti con quelli
#                                         verificati in guerriero.json
#                                         Cavaliere Mistico / ladro.json
#                                         Mistificatore Arcano; le descrizioni
#                                         restano da aggiungere con l'audit
#                                         dedicato di incantesimi_mago.json
#   get_metamagic_options()           -> stregone.json, feature "Metamagia"
#   get_pact_boons()                  -> warlock.json, feature "Dono del
#                                         Patto" -> options
#
# Durante questo refactor sono stati corretti anche 2 problemi di dati:
# - LAND_TERRAINS aveva "Piana"/"Sottosuolo" mentre druido.json (già
#   auditato) usa "Prateria"/"Underdark" — nessun bug live (land_terrain è
#   solo testo salvato, mai usato per filtrare incantesimi), ma dato
#   comunque sbagliato, ora risolto leggendo direttamente da circle_spells.
# - MAGO_CANTRIPS conteneva nomi tradotti dall'inglese, solo 5/16 coerenti
#   con incantesimi_mago.json (che aveva 11 trucchetti con nomi sospetti,
#   vedi Checklist Revisione Dati PHB) — quei nomi sono stati sostituiti
#   direttamente in incantesimi_mago.json con i 16 già verificati in
#   guerriero.json/ladro.json (solo nome, descrizione rimandata all'audit
#   dedicato di quel file).
#
# Verificato via grep su tutto l'albero .py: zero riferimenti residui a
# nessuna delle 6 costanti fuori da questo file dopo il refactor.
# ---------------------------------------------------------------------------

# Lingue D&D 5e (PHB)
LANGUAGES = [
    "Comune", "Nanico", "Elfico", "Gigante", "Gnomesco", "Goblin",
    "Halfling", "Orchesco", "Abissale", "Celeste", "Draconico",
    "Silvano", "Sottocomune", "Infernale", "Primordiale",
]

# ---------------------------------------------------------------------------
# ARTISAN_TOOLS, MUSICAL_INSTRUMENTS, GAMING_SETS, TOOL_CATEGORIES,
# TOOL_CATEGORY_LABEL — RIMOSSE IL 2026-07-10 (stesso refactor già applicato
# a RACE_DATA e alle 7 costanti di classe: eliminare dati duplicati a mano in
# Python quando esiste già un JSON che dovrebbe essere l'unica fonte).
#
# Il 2026-07-10 queste liste erano state prima CORRETTE sul posto (nomi
# allineati al manuale, vedi equipment.json) invece di essere eliminate —
# Davide ha fatto notare che questo era lo stesso errore di duplicazione già
# risolto altrove: avevamo appena creato data/game_data/equipment/equipment.json
# apposta come fonte unica, quindi tenere ANCHE le liste Python (per quanto
# corrette) ricreava lo stesso rischio di disallineamento futuro.
#
# Sostituite da metodi GameDataLoader che leggono equipment.json → tools.items
# (ogni voce ha un campo "category": "strumenti_artigiano" | "strumenti_musicali"
# | "giochi" | "strumenti_vari"):
#   get_tool_names(category)      -> list[str], sostituisce le 3 costanti
#   get_tool_categories()         -> dict, sostituisce TOOL_CATEGORIES
#   get_tool_category_label(key)  -> str,  sostituisce TOOL_CATEGORY_LABEL
#
# Verificato via grep su tutto l'albero .py: zero riferimenti residui a
# nessuna delle 5 costanti fuori da questo commento dopo il refactor.
# ---------------------------------------------------------------------------

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

# Classi disponibili con dado vita e caratteristica da incantatore —
# RIMOSSO (2026-07-10). `CLASSES` duplicava hit_die/spellcasting_ability
# già presenti in ogni data/game_data/classes/*.json (verificato: nessuna
# discrepanza al momento della rimozione, ma stesso rischio architetturale
# già risolto per RACE_DATA e le altre costanti classe). Sostituito da
# `GameDataLoader.get_class(name)` (dict completo, incluso hit_die e
# spellcasting_ability) e `GameDataLoader.get_class_names()` (elenco nomi,
# per i dropdown "Classe").

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

# Tiri salvezza competenti per classe — RIMOSSO (2026-07-09), vedi il blocco
# di commento sopra ("Dati di Classe... RIMOSSI"). Sostituito da
# GameDataLoader.get_class_saving_throws(class_name), che legge il campo
# "saving_throws" (chiavi brevi "str"/"dex"/... convertite in etichette
# italiane) direttamente da ogni JSON in data/game_data/classes/.

# Standard array D&D 5e
STANDARD_ARRAY = [15, 14, 13, 12, 10, 8]

# Point buy: costo per punteggio
POINT_BUY_COSTS = {8: 0, 9: 1, 10: 2, 11: 3, 12: 4, 13: 5, 14: 7, 15: 9}
POINT_BUY_BUDGET = 27

# ---------------------------------------------------------------------------
# Dati Razziali — RIMOSSI (2026-07-09).
#
# In precedenza qui viveva `RACE_DATA`, un dizionario scritto a mano con
# bonus caratteristica/velocità/scurovisione/tratti per le 14 combinazioni
# razza-sottorazza, usato da wizard_engine.py (creazione personaggio),
# manual_form.py (anteprima bonus + velocità) ed esplorazione_tab.py/
# profilo_tab.py (visualizzazione tratti razziali).
#
# Era un secondo dataset indipendente dai JSON in data/game_data/races/,
# con i suoi propri errori (nomi tratti sbagliati, un tratto del Gnomo delle
# Rocce completamente inventato, ecc. — vedi CLAUDE.md, sezione razze,
# 2026-07-09) e un bug reale: il confronto `race == "Mezzelf"` in
# wizard_view.py/manual_form.py non corrispondeva mai a "Mezzelfo" (il nome
# usato ovunque nel resto dell'app), quindi i Mezzelfo creati non ricevevano
# mai il bonus flessibile +1/+1 né le 2 abilità di Versatilità.
#
# Sostituito da `GameDataLoader.get_resolved_race(race_name, subrace_name)`
# (in data/game_data/game_data_loader.py), che legge esclusivamente dai JSON
# e somma bonus base+sottorazza. Questo rende i JSON l'unica fonte dato per
# le razze: aggiungere o modificare una razza (anche di un'altra edizione)
# richiede solo di toccare/aggiungere un file JSON, mai il codice Python.
# ---------------------------------------------------------------------------


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
                resistances.append("(vedi Discendenza Draconica)")
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
            if "(vedi Discendenza Draconica)" in resistances:
                resistances.remove("(vedi Discendenza Draconica)")
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
