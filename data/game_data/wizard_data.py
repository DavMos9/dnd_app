"""
Dati statici per il wizard di creazione guidata.
Domande con pesi di scoring, backgrounds dal PHB italiano, mapping classe→stat.
"""

# ------------------------------------------------------------------
# DOMANDE DEL WIZARD
# ------------------------------------------------------------------
# Ogni opzione ha:
#   scores       → punteggi per le classi
#   scores_bg    → punteggi per i background (solo q. "background_style")
#   alignment_axis_ge / alignment_axis_lc → asse allineamento (q. allineamento)
# Il punteggio finale per ogni classe è la somma di tutti i contributi.

WIZARD_QUESTIONS = [
    {
        "id": "playstyle",
        "phase": "Stile di Gioco",
        "text": "Cosa ti piace di più fare in D&D?",
        "subtitle": "Puoi scegliere più risposte.",
        "multi": True,
        "options": [
            {
                "id": "combat",
                "text": "Combattere",
                "icon": "SPORTS_MARTIAL_ARTS",
                "desc": "Affrontare i nemici in mischia o a distanza",
                "scores": {"Barbaro": 3, "Guerriero": 3, "Paladino": 2, "Monaco": 2, "Ranger": 1, "Ladro": 1},
            },
            {
                "id": "explore",
                "text": "Esplorare",
                "icon": "EXPLORE",
                "desc": "Scoprire luoghi segreti e avventurarsi nel selvaggio",
                "scores": {"Ranger": 3, "Druido": 2, "Monaco": 1, "Ladro": 1},
            },
            {
                "id": "social",
                "text": "Interagire",
                "icon": "CHAT",
                "desc": "Parlare con i personaggi, negoziare, ingannare",
                "scores": {"Bardo": 3, "Warlock": 2, "Ladro": 1},
            },
            {
                "id": "support",
                "text": "Supportare",
                "icon": "FAVORITE",
                "desc": "Guarire e potenziare i compagni",
                "scores": {"Chierico": 3, "Bardo": 2, "Druido": 2, "Paladino": 1},
            },
            {
                "id": "puzzle",
                "text": "Enigmi e sfide",
                "icon": "PSYCHOLOGY",
                "desc": "Usare l'intelligenza per superare ostacoli",
                "scores": {"Mago": 3, "Bardo": 2, "Ladro": 1},
            },
        ],
    },
    {
        "id": "combat_style",
        "phase": "Combattimento",
        "text": "Come ti comporti in combattimento?",
        "subtitle": None,
        "multi": False,
        "options": [
            {
                "id": "melee_heavy",
                "text": "Entro in mischia e meno forte",
                "icon": "FITNESS_CENTER",
                "desc": "Armatura pesante, arma in mano, niente sottigliezze",
                "scores": {"Guerriero": 3, "Barbaro": 3, "Paladino": 2, "Monaco": 1},
            },
            {
                "id": "melee_agile",
                "text": "Combatto veloce e preciso",
                "icon": "SPEED",
                "desc": "Colpi rapidi, schivate, non mi fermo mai",
                "scores": {"Ladro": 3, "Monaco": 3, "Ranger": 1, "Guerriero": 1},
            },
            {
                "id": "ranged",
                "text": "Attacco a distanza",
                "icon": "GPS_FIXED",
                "desc": "Arco, balestra o incantesimi a distanza",
                "scores": {"Ranger": 3, "Guerriero": 2, "Mago": 1, "Bardo": 1},
            },
            {
                "id": "spellcaster",
                "text": "Lancio incantesimi potenti",
                "icon": "AUTO_AWESOME",
                "desc": "Magia offensiva devastante",
                "scores": {"Mago": 3, "Stregone": 3, "Warlock": 2, "Bardo": 1},
            },
            {
                "id": "support_healer",
                "text": "Supporto e guarigione",
                "icon": "HEALING",
                "desc": "Tengo in vita il gruppo e potenzione gli alleati",
                "scores": {"Chierico": 3, "Bardo": 2, "Druido": 2, "Paladino": 1},
            },
        ],
    },
    {
        "id": "magic_preference",
        "phase": "Magia",
        "text": "Vuoi usare la magia?",
        "subtitle": None,
        "multi": False,
        "options": [
            {
                "id": "full_caster",
                "text": "Sì, voglio essere un incantatore puro",
                "icon": "STARS",
                "desc": "La magia è il cuore del mio personaggio",
                "scores": {"Mago": 4, "Stregone": 4, "Warlock": 3, "Druido": 2, "Chierico": 2, "Bardo": 2},
            },
            {
                "id": "half_caster",
                "text": "Un po', come complemento al combattimento",
                "icon": "FLASH_ON",
                "desc": "Qualche incantesimo utile senza essere un mago puro",
                "scores": {"Paladino": 3, "Ranger": 3, "Bardo": 2},
            },
            {
                "id": "no_magic",
                "text": "No, preferisco il combattimento fisico",
                "icon": "SHIELD",
                "desc": "Forza, destrezza e addestramento, senza magia",
                "scores": {"Guerriero": 4, "Barbaro": 4, "Monaco": 3, "Ladro": 3, "Ranger": 1},
            },
        ],
    },
    {
        "id": "complexity",
        "phase": "Meccaniche",
        "text": "Ti piace gestire risorse e meccaniche complesse?",
        "subtitle": None,
        "multi": False,
        "options": [
            {
                "id": "love_complexity",
                "text": "Sì, mi piacciono le meccaniche profonde",
                "icon": "ACCOUNT_TREE",
                "desc": "Slot incantesimo, preparazione, tante opzioni",
                "scores": {"Mago": 3, "Druido": 2, "Chierico": 2, "Bardo": 1},
            },
            {
                "id": "medium",
                "text": "Un livello intermedio va bene",
                "icon": "TUNE",
                "desc": "Qualche risorsa, ma non troppo complicato",
                "scores": {"Bardo": 2, "Paladino": 2, "Ranger": 2, "Ladro": 2, "Warlock": 2},
            },
            {
                "id": "simple",
                "text": "No, voglio qualcosa di semplice",
                "icon": "BOLT",
                "desc": "Poche risorse, poche scelte, massima efficacia",
                "scores": {"Barbaro": 3, "Guerriero": 3, "Monaco": 2},
            },
        ],
    },
    {
        "id": "personality",
        "phase": "Personalità",
        "text": "Come descriveresti il tuo personaggio?",
        "subtitle": None,
        "multi": False,
        "options": [
            {
                "id": "brute",
                "text": "Potente e diretto",
                "icon": "SPORTS_MARTIAL_ARTS",
                "desc": "Parla poco, agisce tanto, è il più forte della stanza",
                "scores": {"Barbaro": 3, "Guerriero": 2},
            },
            {
                "id": "noble_pers",
                "text": "Nobile e giusto",
                "icon": "SHIELD",
                "desc": "Difende i deboli, crede nel bene, segue un codice",
                "scores": {"Paladino": 4, "Guerriero": 1, "Chierico": 1},
            },
            {
                "id": "cunning",
                "text": "Furbo e scaltro",
                "icon": "VISIBILITY",
                "desc": "Ottiene ciò che vuole con l'astuzia, non con la forza",
                "scores": {"Ladro": 3, "Bardo": 2, "Warlock": 1},
            },
            {
                "id": "wise",
                "text": "Saggio e spirituale",
                "icon": "SELF_IMPROVEMENT",
                "desc": "Cerca l'illuminazione, ascolta la natura o le divinità",
                "scores": {"Chierico": 3, "Druido": 3, "Monaco": 2},
            },
            {
                "id": "dark",
                "text": "Oscuro e misterioso",
                "icon": "NIGHTS_STAY",
                "desc": "Un passato tormentato, poteri oscuri, scopi enigmatici",
                "scores": {"Warlock": 3, "Stregone": 2, "Ladro": 1},
            },
            {
                "id": "intellectual",
                "text": "Intellettuale e curioso",
                "icon": "PSYCHOLOGY",
                "desc": "Ossessionato dalla conoscenza, studia tutto e tutti",
                "scores": {"Mago": 4, "Bardo": 1},
            },
            {
                "id": "wild",
                "text": "Libero e selvaggio",
                "icon": "PARK",
                "desc": "Figlio della natura, spirito indomabile",
                "scores": {"Druido": 3, "Barbaro": 2, "Ranger": 2},
            },
            {
                "id": "charismatic",
                "text": "Carismatico e artistico",
                "icon": "MUSIC_NOTE",
                "desc": "Ama il palcoscenico, le storie e le persone",
                "scores": {"Bardo": 4, "Warlock": 1},
            },
        ],
    },
    {
        "id": "power_source",
        "phase": "Fonte di Potere",
        "text": "Da dove viene il potere del tuo personaggio?",
        "subtitle": None,
        "multi": False,
        "options": [
            {
                "id": "physical",
                "text": "Allenamento fisico e disciplina",
                "icon": "FITNESS_CENTER",
                "desc": "Anni di addestramento hanno affinato corpo e mente",
                "scores": {"Guerriero": 3, "Monaco": 3, "Ladro": 2, "Ranger": 1},
            },
            {
                "id": "rage",
                "text": "Furia interiore e istinto primordiale",
                "icon": "WHATSHOT",
                "desc": "In battaglia si scatena qualcosa di selvaggio e potente",
                "scores": {"Barbaro": 5},
            },
            {
                "id": "pact",
                "text": "Un patto con un'entità potente",
                "icon": "HANDSHAKE",
                "desc": "Ha stretto un accordo con un essere ultraterreno",
                "scores": {"Warlock": 5},
            },
            {
                "id": "divine",
                "text": "Fede e devozione divina",
                "icon": "FLARE",
                "desc": "Un dio o una causa gli ha concesso poteri sacri",
                "scores": {"Chierico": 4, "Paladino": 3},
            },
            {
                "id": "innate",
                "text": "Magia innata nel sangue",
                "icon": "AUTO_AWESOME",
                "desc": "La magia è parte della sua natura, ereditata o mutata",
                "scores": {"Stregone": 5, "Druido": 1},
            },
            {
                "id": "study",
                "text": "Studio e dedizione alla magia",
                "icon": "MENU_BOOK",
                "desc": "Anni sui libri hanno sbloccato i segreti arcani",
                "scores": {"Mago": 5},
            },
            {
                "id": "nature",
                "text": "Connessione con la natura",
                "icon": "FOREST",
                "desc": "Il mondo naturale risponde alla sua chiamata",
                "scores": {"Druido": 4, "Ranger": 3},
            },
        ],
    },
    {
        "id": "background_style",
        "phase": "Background",
        "text": "Qual è il passato del tuo personaggio?",
        "subtitle": None,
        "multi": False,
        "options": [
            {
                "id": "bg_military",
                "text": "Militare o soldato",
                "icon": "MILITARY_TECH",
                "desc": "Ha servito in un esercito o in un ordine cavalleresco",
                "scores": {"Guerriero": 2, "Paladino": 2, "Barbaro": 1},
                "scores_bg": {"Soldato": 10, "Eroe Popolare": 3},
            },
            {
                "id": "bg_criminal",
                "text": "Criminale o ladro",
                "icon": "GAVEL",
                "desc": "Ha vissuto nell'ombra, tra truffe e furti",
                "scores": {"Ladro": 2, "Bardo": 1, "Warlock": 1},
                "scores_bg": {"Criminale": 10, "Monello": 5, "Ciarlatano": 4},
            },
            {
                "id": "bg_religious",
                "text": "Religioso o devoto",
                "icon": "CHURCH",
                "desc": "Ha servito una divinità o un ordine religioso",
                "scores": {"Chierico": 2, "Paladino": 2, "Druido": 1},
                "scores_bg": {"Accolito": 10, "Eremita": 4},
            },
            {
                "id": "bg_wild",
                "text": "Cresciuto nella natura selvaggia",
                "icon": "FOREST",
                "desc": "Ha vissuto lontano dalla civiltà",
                "scores": {"Ranger": 2, "Druido": 2, "Barbaro": 1},
                "scores_bg": {"Forestiero": 10, "Eremita": 4},
            },
            {
                "id": "bg_academic",
                "text": "Accademico o studioso",
                "icon": "SCHOOL",
                "desc": "Ha studiato in una biblioteca o un'università",
                "scores": {"Mago": 2, "Bardo": 1, "Chierico": 1},
                "scores_bg": {"Sapiente": 10, "Eremita": 3},
            },
            {
                "id": "bg_noble",
                "text": "Nobile o aristocratico",
                "icon": "WORKSPACE_PREMIUM",
                "desc": "Nato o cresciuto tra i privilegi dell'alta società",
                "scores": {"Paladino": 1, "Bardo": 1, "Warlock": 1},
                "scores_bg": {"Nobile": 10, "Artigiano di Gilda": 3},
            },
            {
                "id": "bg_artisan",
                "text": "Artigiano o mercante",
                "icon": "HARDWARE",
                "desc": "Lavorava con le mani o nel commercio",
                "scores": {"Guerriero": 1, "Ladro": 1},
                "scores_bg": {"Artigiano di Gilda": 10},
            },
            {
                "id": "bg_performer",
                "text": "Artista o intrattenitore",
                "icon": "THEATER_COMEDY",
                "desc": "Si esibiva per il pubblico, amava la scena",
                "scores": {"Bardo": 2, "Warlock": 1, "Ladro": 1},
                "scores_bg": {"Intrattenitore": 10, "Ciarlatano": 3},
            },
            {
                "id": "bg_common",
                "text": "Gente comune, un eroe inaspettato",
                "icon": "PEOPLE",
                "desc": "Un normale abitante che ha risposto alla chiamata",
                "scores": {"Guerriero": 1, "Chierico": 1, "Paladino": 1},
                "scores_bg": {"Eroe Popolare": 10, "Marinaio": 3, "Monello": 3},
            },
        ],
    },
    {
        "id": "alignment_ge",
        "phase": "Allineamento",
        "text": "Come si rapporta il tuo personaggio con la moralità?",
        "subtitle": None,
        "multi": False,
        "options": [
            {
                "id": "good",
                "text": "Si preoccupa per gli altri, cerca di fare del bene",
                "icon": "FAVORITE",
                "desc": "Aiuta chi è nel bisogno, anche a costo di sacrifici",
                "alignment_axis_ge": "Buono",
            },
            {
                "id": "neutral_ge",
                "text": "Pensa a se stesso, ma non è crudele",
                "icon": "BALANCE",
                "desc": "Non cerca di fare del male, ma non si sacrifica per gli altri",
                "alignment_axis_ge": "Neutrale",
            },
            {
                "id": "evil",
                "text": "Mette i propri interessi davanti a tutto",
                "icon": "DANGEROUS",
                "desc": "Non gli importa fare del male se serve ai suoi scopi",
                "alignment_axis_ge": "Malvagio",
            },
        ],
    },
    {
        "id": "alignment_lc",
        "phase": "Allineamento",
        "text": "Come si rapporta il tuo personaggio con le regole?",
        "subtitle": None,
        "multi": False,
        "options": [
            {
                "id": "lawful",
                "text": "Rispetta le regole e i codici",
                "icon": "GAVEL",
                "desc": "La legge e l'ordine sono importanti, le promesse vanno mantenute",
                "alignment_axis_lc": "Legale",
            },
            {
                "id": "neutral_lc",
                "text": "Segue la propria coscienza",
                "icon": "SELF_IMPROVEMENT",
                "desc": "Non è schiavo delle regole, ma non le ignora del tutto",
                "alignment_axis_lc": "Neutrale",
            },
            {
                "id": "chaotic",
                "text": "Libertà sopra tutto",
                "icon": "WHATSHOT",
                "desc": "Le regole sono catene; la libertà è l'unica vera legge",
                "alignment_axis_lc": "Caotico",
            },
        ],
    },
]


# ------------------------------------------------------------------
# BACKGROUND DATA — rimosso il 2026-07-10, vedi CLAUDE.md "Note Importanti"
# Prima conteneva un secondo dataset dei 13 background PHB (skills, traits,
# ideals, bonds, flaws) scritto a mano, in parallelo a data/game_data/backgrounds/*.json
# — stesso tipo di duplicazione gia' eliminata per RACE_DATA e le costanti di classe.
# L'audit riga-per-riga contro il manuale (pagine 127-141) ha confermato che questo
# dataset Python aveva contenuto DIVERGENTE (non solo differente formattazione) da
# backgrounds/*.json, ed era esso stesso non allineato al manuale in piu' punti
# (es. chiave "Saggio" invece di "Sapiente" — bug reale: la domanda del wizard che
# assegnava punti al background "Sapiente" non aveva mai effetto, perche' quella
# chiave non esisteva in questo dizionario). Tutti i 13 file JSON sono stati
# verificati e corretti contro il PHB IT (pdftoppm + lettura visiva delle pagine,
# non pdftotext) e sono ora l'unica fonte. Vedi GameDataLoader.get_background(name) /
# get_background_names() / get_all_backgrounds().
# ------------------------------------------------------------------

# ------------------------------------------------------------------
# MAPPING CLASSI → CARATTERISTICHE PRIMARIE
# (usato per suggerire la distribuzione dello standard array)
# ------------------------------------------------------------------
CLASS_PRIMARY_STATS = {
    "Barbaro":   ["str", "con"],
    "Bardo":     ["cha", "dex"],
    "Chierico":  ["wis", "con"],
    "Druido":    ["wis", "con"],
    "Guerriero": ["str", "con"],
    "Monaco":    ["dex", "wis"],
    "Paladino":  ["str", "cha"],
    "Ranger":    ["dex", "wis"],
    "Ladro":     ["dex", "int"],
    "Stregone":  ["cha", "con"],
    "Warlock":   ["cha", "con"],
    "Mago":      ["int", "dex"],
}

# ------------------------------------------------------------------
# RAZZE CONSIGLIATE PER CLASSE
# ------------------------------------------------------------------
CLASS_SUGGESTED_RACES = {
    "Barbaro":   ["Mezzorco", "Nano della Montagna", "Umano", "Dragonide"],
    "Bardo":     ["Mezzelfo", "Tiefling", "Umano", "Elfo Alto"],
    "Chierico":  ["Nano delle Colline", "Umano", "Mezzelfo"],
    "Druido":    ["Elfo dei Boschi", "Umano", "Halfling Piedelesto"],
    "Guerriero": ["Umano", "Nano della Montagna", "Mezzorco", "Dragonide"],
    "Monaco":    ["Umano", "Elfo Alto", "Halfling Piedelesto"],
    "Paladino":  ["Umano", "Dragonide", "Mezzelfo", "Nano delle Colline"],
    "Ranger":    ["Elfo dei Boschi", "Halfling Piedelesto", "Umano"],
    "Ladro":     ["Elfo Alto", "Halfling Piedelesto", "Umano", "Mezzorco"],
    "Stregone":  ["Dragonide", "Tiefling", "Umano"],
    "Warlock":   ["Tiefling", "Mezzelfo", "Umano"],
    "Mago":      ["Elfo Alto", "Gnomo delle Rocce", "Umano", "Tiefling"],
}

# ------------------------------------------------------------------
# DESCRIZIONI CLASSI (per la schermata di raccomandazione)
# ------------------------------------------------------------------
CLASS_DESCRIPTIONS = {
    "Barbaro":   "Un guerriero primitivo che si affida alla furia per combattere. Resistente, potente, temibile.",
    "Bardo":     "Un artista versatile che usa la magia della musica. Supporto, incantesimi e fascino.",
    "Chierico":  "Un devoto servitore degli dèi. Guarisce, protegge e punisce con potere divino.",
    "Druido":    "Un guardiano della natura. Si trasforma in bestie e comanda le forze naturali.",
    "Guerriero": "Il maestro del combattimento. Eccelle con qualsiasi arma e armatura.",
    "Monaco":    "Un artista marziale che incanalizza la forza interiore. Veloce e letale a mani nude.",
    "Paladino":  "Un campione divino. Unisce potere martiale e magia sacra in nome di una causa.",
    "Ranger":    "Un cacciatore e esploratore. Combatte con arco e astuzia, padrone della natura selvaggia.",
    "Ladro":     "Un maestro della furtività e dell'astuzia. Colpisce dove fa più male e scompare.",
    "Stregone":  "Un incantatore dalla magia innata. Pochi incantesimi ma devastanti, forgiati nel sangue.",
    "Warlock":   "Un signore di oscuri patti. Ottiene potere soprannaturale in cambio di un prezzo.",
    "Mago":      "Il maestro dell'arte arcana. Lo spettro più ampio di incantesimi, ma fragile in combattimento.",
}
