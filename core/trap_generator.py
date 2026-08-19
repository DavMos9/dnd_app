"""
Generatore Trappole — logica pura (nessuna dipendenza Flet), stesso
principio architetturale di `wizard_engine.py`/`level_manager.py`/
`equipment_manager.py`/`weapon_calculator.py`/`encounter_calculator.py`/
`treasure_generator.py`: nessuna scrittura su DB, solo funzioni che
risolvono/tirano i valori suggeriti a partire dai dati di
`data/game_data/traps.json` (esposti tramite `GameDataLoader`).

Fonte: "Guida del Dungeon Master" IT (DMG), Capitolo 5 "Ambienti delle
Avventure", sezione "Trappole", p.120-124. Tutte le tabelle sono state
lette visivamente dalle pagine renderizzate del PDF (`pdftoppm`, mai
`pdftotext`/OCR per il contenuto). Vedi `traps.json → _source_note` per il
changelog completo della trascrizione.

Due funzionalità, esattamente come da design ("Generatore Trappole", punto
8 della Sezione Master):

- **Suggerisci** (`suggest_trap_stats`): dato il livello del gruppo di PG e
  la gravità desiderata (Imprevisto/Pericoloso/Letale), restituisce CD del
  tiro salvezza, bonus di attacco e dado danno suggeriti dalle 2 tabelle
  del manuale — utile per progettare al volo una trappola custom.
- **Sfoglia Esempi** (`GameDataLoader.get_example_traps()`/`get_example_trap()`,
  usati direttamente dalla UI): le 8 trappole nominate del manuale, con
  testo completo — nessuna logica di generazione necessaria qui, sono
  voci di consultazione statiche.
"""

from __future__ import annotations

import random
import re
from typing import Any

from data.game_data.game_data_loader import game_data

_DICE_RE = re.compile(r"^\s*(\d*)\s*[dD]\s*(\d+)\s*$")

SEVERITY_LABELS = {"imprevisto": "Imprevisto", "pericoloso": "Pericoloso", "letale": "Letale"}


def roll_dice(formula: str) -> int:
    """Tira una formula di dadi tipo "4d10" e ritorna la somma. Stesso
    helper già in uso in `core/treasure_generator.py` (duplicato qui per
    tenere il modulo autonomo, stesso principio di indipendenza già
    seguito dagli altri moduli `core/`)."""
    formula = (formula or "").strip()
    if not formula:
        return 0
    match = _DICE_RE.match(formula)
    if not match:
        try:
            return int(formula)
        except ValueError:
            return 0
    count = int(match.group(1)) if match.group(1) else 1
    sides = int(match.group(2))
    return sum(random.randint(1, sides) for _ in range(count))


def suggest_trap_stats(char_level: int, severity: str) -> dict[str, Any]:
    """
    Restituisce i valori suggeriti dalle 2 tabelle DMG per una trappola
    custom, dati il livello dei PG e la gravità desiderata:
    {"severity", "severity_label", "save_dc", "attack_bonus", "damage_dice",
    "char_level_range"} — ognuno stringa vuota/"?" se il dato non risolve
    (livello fuori range 1-20 o gravità non riconosciuta).
    """
    severity = (severity or "").strip().lower()
    label = SEVERITY_LABELS.get(severity, severity.capitalize())

    danger_row = next(
        (r for r in game_data.get_trap_danger_table() if r.get("level", "").lower() == severity),
        None,
    )
    save_dc = danger_row.get("save_dc", "?") if danger_row else "?"
    attack_bonus = danger_row.get("attack_bonus", "?") if danger_row else "?"

    damage_dice = ""
    char_level_range = ""
    for row in game_data.get_trap_damage_table():
        lo_str, _, hi_str = row.get("char_level_range", "").partition("-")
        try:
            lo, hi = int(lo_str), int(hi_str)
        except ValueError:
            continue
        if lo <= char_level <= hi:
            damage_dice = row.get(severity, "")
            char_level_range = row.get("char_level_range", "")
            break

    return {
        "severity": severity,
        "severity_label": label,
        "save_dc": save_dc,
        "attack_bonus": attack_bonus,
        "damage_dice": damage_dice or "?",
        "char_level_range": char_level_range,
    }


def roll_trap_damage(char_level: int, severity: str) -> int:
    """Tira effettivamente il danno suggerito per il livello/gravità
    indicati (comodo per un pulsante "Tira Danno" nella UI). 0 se il dado
    non risolve."""
    stats = suggest_trap_stats(char_level, severity)
    dice = stats.get("damage_dice", "")
    if not dice or dice == "?":
        return 0
    return roll_dice(dice)
