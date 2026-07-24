"""
Calcolatore Difficoltà Incontro — logica pura (nessuna dipendenza Flet), stesso
principio architetturale di `wizard_engine.py`/`level_manager.py`/
`equipment_manager.py`/`weapon_calculator.py`: nessuna scrittura su DB, solo
funzioni che prendono dati e restituiscono un risultato calcolato.

Fonte: "Guida del Dungeon Master" IT (DMG), Cap.3 "Creare le Avventure",
p.82-83 — sezioni "Soglie di PE per Livello del Personaggio", "Moltiplicatori
degli Incontri" e "Dimensioni del Gruppo". Tutti i valori sono stati letti
visivamente dalle pagine renderizzate del PDF (`pdftoppm`, non `pdftotext`/
OCR — il dump testuale automatico di queste due tabelle presenta corruzione
OCR su diverse cifre, es. "l.100" al posto di "1.100", "so" al posto di "50")
il 2026-07-24. Nessun dato indovinato, tradotto da un'altra edizione/lingua o
preso dal web.

La tabella "Punti Esperienza per Grado di Sfida" (PE-per-GS, Cap.9 del DMG)
NON serve trascriverla qui: `data/game_data/monsters.json` (444 mostri, già
interamente auditato) ha già un campo "xp" valorizzato per ogni mostro — il
calcolatore somma direttamente quei valori (o quello inserito a mano su un
NPC "Nuovo Manuale"/una Creazione Rapida), senza bisogno di una conversione
GS→PE separata.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Soglie di PE per Livello del Personaggio — DMG IT p.82, tabella completa,
# verificata visivamente (pdftoppm) il 2026-07-24. Nessun livello oltre il
# 20° esiste nel manuale.
# ---------------------------------------------------------------------------
PE_THRESHOLDS_BY_LEVEL: dict[int, dict[str, int]] = {
    1:  {"facile": 25,   "medio": 50,   "difficile": 75,   "letale": 100},
    2:  {"facile": 50,   "medio": 100,  "difficile": 150,  "letale": 200},
    3:  {"facile": 75,   "medio": 150,  "difficile": 225,  "letale": 400},
    4:  {"facile": 125,  "medio": 250,  "difficile": 375,  "letale": 500},
    5:  {"facile": 250,  "medio": 500,  "difficile": 750,  "letale": 1100},
    6:  {"facile": 300,  "medio": 600,  "difficile": 900,  "letale": 1400},
    7:  {"facile": 350,  "medio": 750,  "difficile": 1100, "letale": 1700},
    8:  {"facile": 450,  "medio": 900,  "difficile": 1400, "letale": 2100},
    9:  {"facile": 550,  "medio": 1100, "difficile": 1600, "letale": 2400},
    10: {"facile": 600,  "medio": 1200, "difficile": 1900, "letale": 2800},
    11: {"facile": 800,  "medio": 1600, "difficile": 2400, "letale": 3600},
    12: {"facile": 1000, "medio": 2000, "difficile": 3000, "letale": 4500},
    13: {"facile": 1100, "medio": 2200, "difficile": 3400, "letale": 5100},
    14: {"facile": 1250, "medio": 2500, "difficile": 3800, "letale": 5700},
    15: {"facile": 1400, "medio": 2800, "difficile": 4300, "letale": 6400},
    16: {"facile": 1600, "medio": 3200, "difficile": 4800, "letale": 7200},
    17: {"facile": 2000, "medio": 3900, "difficile": 5900, "letale": 8800},
    18: {"facile": 2100, "medio": 4200, "difficile": 6300, "letale": 9500},
    19: {"facile": 2400, "medio": 4900, "difficile": 7300, "letale": 10900},
    20: {"facile": 2800, "medio": 5700, "difficile": 8500, "letale": 12700},
}

DIFFICULTY_ORDER = ["facile", "medio", "difficile", "letale"]
DIFFICULTY_LABELS = {
    "trascurabile": "Trascurabile",
    "facile": "Facile",
    "medio": "Medio",
    "difficile": "Difficile",
    "letale": "Letale",
    "indeterminato": "Indeterminato",
}

# Moltiplicatori degli Incontri — DMG IT p.82, tabella pulita (nessuna
# corruzione OCR). Indice di riga: 0=1 mostro, 1=2, 2=3-6, 3=7-10, 4=11-14, 5=15+.
_BASE_MULTIPLIERS: list[float] = [1.0, 1.5, 2.0, 2.5, 3.0, 4.0]


def get_pe_threshold(level: int, difficulty: str) -> int:
    """Soglia PE per un singolo personaggio di questo livello/categoria.
    Livelli fuori 1-20 vengono clampati (nessun dato oltre il 20° nel DMG)."""
    lvl = max(1, min(20, int(level or 1)))
    return PE_THRESHOLDS_BY_LEVEL[lvl].get(difficulty, 0)


def _row_index_for_monster_count(count: int) -> int:
    if count <= 1:
        return 0
    if count == 2:
        return 1
    if 3 <= count <= 6:
        return 2
    if 7 <= count <= 10:
        return 3
    if 11 <= count <= 14:
        return 4
    return 5  # 15 o più


def encounter_multiplier(monster_count: int, party_size: int) -> float:
    """
    Moltiplicatore PE per il numero di mostri, con la rettifica per
    dimensione del gruppo (DMG IT p.82-83, "Dimensioni del Gruppo",
    verificata visivamente — testo esatto: "Se il gruppo contiene meno di tre
    personaggi, si applica il modificatore immediatamente più alto... Se il
    gruppo contiene sei o più personaggi, si usa il moltiplicatore
    immediatamente successivo della tabella", con i due valori limite dati
    per esempio nel testo stesso — ×5 per 15+ mostri con gruppo <3 PG (un
    valore SOPRA il ×4 di base, non presente nella tabella "Moltiplicatori
    degli Incontri"), ×0,5 per un singolo mostro con gruppo ≥6 PG (un valore
    SOTTO l'×1 di base): entrambi i valori estremi combaciano esattamente con
    gli esempi riportati nel manuale, non sono un'estrapolazione).
    """
    if monster_count <= 0:
        return 0.0
    idx = _row_index_for_monster_count(monster_count)
    if party_size < 3:
        if idx == len(_BASE_MULTIPLIERS) - 1:
            return 5.0
        idx += 1
    elif party_size >= 6:
        if idx == 0:
            return 0.5
        idx -= 1
    return _BASE_MULTIPLIERS[idx]


def calculate_difficulty(monster_xp_list: list[int], party_levels: list[int]) -> dict:
    """
    Calcola la difficoltà di un incontro secondo il metodo in 5 passi del DMG
    (p.81-82): soglie PE individuali → soglie di gruppo → somma PE mostri →
    PE modificato per moltiplicatore → confronto con le soglie di gruppo (si
    usa la soglia più vicina e inferiore al valore modificato di PE).

    `monster_xp_list`: PE di ciascun mostro/NPC attivo nell'incontro (non i
    personaggi giocanti — quelli contribuiscono solo tramite `party_levels`).
    `party_levels`: livello di ciascun personaggio del gruppo (reali già
    presenti nell'incontro e/o "PG fantasma" solo-livello per pianificare
    prima di sapere chi sarà al tavolo).

    Ritorna un dict con `monster_xp_total`, `monster_count`, `multiplier`,
    `adjusted_xp`, `party_size`, `thresholds` (dict per le 4 categorie) e
    `difficulty` (una delle chiavi di `DIFFICULTY_LABELS`).
    """
    party_size = len(party_levels)
    monster_count = len(monster_xp_list)
    monster_xp_total = sum(int(x or 0) for x in monster_xp_list)

    if party_size == 0:
        return {
            "monster_xp_total": monster_xp_total,
            "monster_count": monster_count,
            "multiplier": 0.0,
            "adjusted_xp": 0,
            "party_size": 0,
            "thresholds": {d: 0 for d in DIFFICULTY_ORDER},
            "difficulty": "indeterminato",
        }

    multiplier = encounter_multiplier(monster_count, party_size) if monster_count else 0.0
    adjusted_xp = int(round(monster_xp_total * multiplier))

    thresholds = {
        diff: sum(get_pe_threshold(lvl, diff) for lvl in party_levels)
        for diff in DIFFICULTY_ORDER
    }

    if monster_count == 0 or adjusted_xp < thresholds["facile"]:
        difficulty = "trascurabile"
    elif adjusted_xp < thresholds["medio"]:
        difficulty = "facile"
    elif adjusted_xp < thresholds["difficile"]:
        difficulty = "medio"
    elif adjusted_xp < thresholds["letale"]:
        difficulty = "difficile"
    else:
        difficulty = "letale"

    return {
        "monster_xp_total": monster_xp_total,
        "monster_count": monster_count,
        "multiplier": multiplier,
        "adjusted_xp": adjusted_xp,
        "party_size": party_size,
        "thresholds": thresholds,
        "difficulty": difficulty,
    }
