"""
Generatore Tesori Casuali — logica pura (nessuna dipendenza Flet), stesso
principio architetturale di `wizard_engine.py`/`level_manager.py`/
`equipment_manager.py`/`weapon_calculator.py`/`encounter_calculator.py`:
nessuna scrittura su DB, solo funzioni che tirano dadi e restituiscono un
risultato calcolato a partire dai dati di `data/game_data/treasure_tables.json`
(esposti tramite `GameDataLoader`).

Fonte: "Guida del Dungeon Master" IT (DMG), Capitolo 7 "Tesori", p.133-149.
Tutte le tabelle sono state lette visivamente dalle pagine renderizzate del
PDF (`pdftoppm`, mai `pdftotext`/OCR per il contenuto) il 2026-07-24. Vedi
`treasure_tables.json → _source_note` per il changelog completo della
trascrizione.

Due sistemi distinti, entrambi implementati qui, esattamente come nel manuale:

- **Tesoro Singolo** (`generate_individual_treasure`): il bottino di UNA
  singola creatura/incontro minore — un solo tiro d100 su una delle 4 tabelle
  per fascia di CR, che restituisce solo monete (una o due valute insieme
  nelle fasce più alte).
- **Cumulo di Tesori** (`generate_hoard_treasure`): il tesoro di un'intera
  tana/covo — una formula di monete FISSA sempre assegnata per intero, più UN
  tiro d100 aggiuntivo che determina gemme/oggetti d'arte (con la propria
  fascia di valore, che alterna riga per riga — non è fissa per l'intera
  tabella) e/o oggetti magici (tirati su una o più delle 9 Tabelle A-I).

Le Tabelle degli Oggetti Magici A-I restituiscono SOLO il nome dell'oggetto
(nessuna descrizione completa — quella appartiene al Compendio Oggetti
Magici, punto 7 del design Master, deliberatamente rimandato a una sessione
futura dedicata, vedi CLAUDE.md).
"""

from __future__ import annotations

import random
import re
from typing import Any

from data.game_data.game_data_loader import game_data

_DICE_RE = re.compile(r"^\s*(\d*)\s*[dD]\s*(\d+)\s*$")


CURRENCY_LABELS = {
    "mr": "Monete di Rame",
    "ma": "Monete di Argento",
    "me": "Monete di Electrum",
    "mo": "Monete d'Oro",
    "mp": "Monete di Platino",
}


def roll_dice(formula: str) -> int:
    """
    Tira una formula di dadi tipo "3d6"/"1d4"/"d8" e ritorna la somma.
    Se `formula` è un numero puro (es. "1", nessuna "d"), ritorna quel
    valore fisso senza tirare nulla — usato per le entry "rolls": "1" delle
    tabelle Cumulo di Tesori (un singolo oggetto garantito, non un tiro).
    """
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


def _row_for_roll(rows: list[dict[str, Any]], roll: int) -> dict[str, Any] | None:
    for r in rows:
        lo, hi = r.get("range", [0, -1])
        if lo <= roll <= hi:
            return r
    return None


# ---------------------------------------------------------------------------
# Tesoro Singolo
# ---------------------------------------------------------------------------

def generate_individual_treasure(cr_band: str) -> dict[str, Any]:
    """
    Tira il Tesoro Singolo per la fascia di CR indicata
    ("0-4" | "5-10" | "11-16" | "17+").
    Ritorna {"cr_band", "roll", "coins": [{"currency","amount"}]}
    — "coins" può contenere più di una valuta (fasce 5-10/11-16/17+).
    Lista vuota se il tiro cade su una riga "niente" (fascia 0-4, 01-30 = MR
    puro comunque presente — verificato che nel manuale nessuna riga di
    Tesoro Singolo è realmente vuota, a differenza del Cumulo).
    """
    rows = game_data.get_individual_treasure_table(cr_band)
    roll = random.randint(1, 100)
    row = _row_for_roll(rows, roll)
    coins: list[dict[str, Any]] = []
    if row:
        for d in row.get("drops", []):
            amount = roll_dice(d["dice"]) * int(d.get("mult", 1) or 1)
            coins.append({"currency": d["currency"], "amount": amount})
    return {"cr_band": cr_band, "roll": roll, "coins": coins}


# ---------------------------------------------------------------------------
# Cumulo di Tesori
# ---------------------------------------------------------------------------

def _roll_gems_or_art(gems_art: dict[str, Any] | None) -> dict[str, Any] | None:
    """
    Risolve la entry "gems_art" di una riga del Cumulo (None se la riga non
    ne concede) in {"type","value","count","items":[nomi tirati]}.
    """
    if not gems_art:
        return None
    kind = gems_art["type"]
    value = gems_art["value"]
    count = roll_dice(gems_art["dice"])
    table = game_data.get_gems_by_value(value) if kind == "gems" else game_data.get_art_by_value(value)
    pool = table.get("items", [])
    items = [random.choice(pool) for _ in range(count)] if pool else []
    return {"type": kind, "value": value, "count": count, "items": items}


def _roll_magic_item_row(letter: str) -> str:
    """Un singolo tiro sulla Tabella degli Oggetti Magici indicata, con
    risoluzione automatica dell'eventuale sotto-tabella (es. G/I)."""
    rows = game_data.get_magic_item_table(letter)
    roll = random.randint(1, 100)
    row = _row_for_roll(rows, roll)
    if not row:
        return f"(tabella {letter} vuota o non trovata)"
    name = row.get("name", "?")
    sub = row.get("sub_table")
    if sub:
        items = sub.get("items", [])
        if items:
            sub_roll = roll_dice(sub["dice"])
            idx = max(0, min(len(items) - 1, sub_roll - 1))
            return f"{name} — {items[idx]}"
        return name
    return name


def _roll_magic_items(magic_entries: list[dict[str, Any]]) -> list[str]:
    """Risolve la lista "magic" di una riga del Cumulo — una o più tabelle,
    ciascuna tirata per il proprio numero di volte (es. "1d6 volte A")."""
    results: list[str] = []
    for entry in magic_entries or []:
        letter = entry["table"]
        count = roll_dice(entry["rolls"])
        for _ in range(count):
            results.append(_roll_magic_item_row(letter))
    return results


def generate_hoard_treasure(cr_band: str) -> dict[str, Any]:
    """
    Tira il Cumulo di Tesori per la fascia di CR indicata. Ritorna:
    {"cr_band", "coins": [{"currency","amount"}, ...] (formula fissa, sempre
    presente per intero), "roll": il tiro d100 sulla tabella aggiuntiva,
    "gems_or_art": None oppure {"type","value","count","items"},
    "magic_items": [nomi tirati, eventualmente da più tabelle]}.
    """
    hoard = game_data.get_hoard_treasure_table(cr_band)
    coins = [
        {"currency": d["currency"], "amount": roll_dice(d["dice"]) * int(d.get("mult", 1) or 1)}
        for d in hoard.get("coins", [])
    ]
    roll = random.randint(1, 100)
    row = _row_for_roll(hoard.get("rows", []), roll)
    gems_or_art = _roll_gems_or_art(row.get("gems_art")) if row else None
    magic_items = _roll_magic_items(row.get("magic", [])) if row else []
    return {
        "cr_band": cr_band,
        "coins": coins,
        "roll": roll,
        "gems_or_art": gems_or_art,
        "magic_items": magic_items,
    }


# ---------------------------------------------------------------------------
# Oggetti Insoliti ("Cimeli") — hook dedicato dentro il generatore tesori
# ---------------------------------------------------------------------------

def roll_trinket() -> tuple[int, str]:
    """
    Tira 1d100 sulla tabella "Oggetti Insoliti" (PHB IT p.160-161,
    equipment/trinkets.json) e ritorna (tiro, descrizione). Deciso con
    Davide il 2026-07-24: pulsante "+ Cimelio" dentro il dialog "Genera
    Tesoro", non una voce di navigazione a sé — un tiro 1d100 senza
    parametri non giustifica una schermata dedicata.
    """
    roll = random.randint(1, 100)
    description = game_data.get_trinket_by_roll(roll) or "(voce non trovata)"
    return roll, description


