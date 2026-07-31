"""
Motore di tiro dei dadi — modulo puro, nessuna dipendenza da Flet o dal DB.

Stesso principio di `weapon_calculator.py`/`level_manager.py`/`encounter_calculator.py`:
la logica di gioco vive in `core/`, la UI la consuma.

Introdotto con la **Fase 4, feature 1** (dadi collegati alla scheda, vedi
`docs/feature_design_2026_07_26.md`). Prima di questo modulo la logica di tiro
esisteva solo dentro `DiceView._roll()`, non riusabile da nessun'altra parte:
la scheda mostrava i modificatori ma non poteva tirarli, e il master doveva
digitare a mano l'iniziativa di ogni mostro.

Cosa gestisce:
  * formule a più termini — `"1d20+5"`, `"2d6"`, `"1d8+1d6+3"` (utile per i
    danni magici extra di un'arma, già modellati come dadi aggiuntivi), `"d20"`;
  * vantaggio/svantaggio sul d20, mostrando **quale dado è stato scartato**
    (al tavolo si vuole vedere entrambi i risultati, non solo quello tenuto);
  * critico (20 naturale) e fallimento critico (1 naturale).

Regola PHB applicata: vantaggio e svantaggio riguardano **solo i tiri di d20**
(PHB Cap. 7, "Vantaggio e Svantaggio") — su una formula di danno come `2d6`
vengono quindi ignorati invece di essere applicati a un dado qualsiasi.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from typing import Literal

Advantage = Literal["normal", "advantage", "disadvantage"]

ADVANTAGE_LABELS: dict[str, str] = {
    "normal": "Normale",
    "advantage": "Vantaggio",
    "disadvantage": "Svantaggio",
}

#: Un termine della formula: `NdM` (dado) oppure una costante.
#: `sign` è +1 o -1, `count`/`faces` valgono 0 per le costanti.
_TERM_RE = re.compile(r"([+-]?)\s*(?:(\d*)\s*[dD]\s*(\d+)|(\d+))")


@dataclass(frozen=True)
class DieGroup:
    """Un gruppo di dadi uguali all'interno di un tiro."""
    faces: int
    sign: int
    rolls: list[int]
    kept: list[int]
    dropped: list[int] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.sign * sum(self.kept)


@dataclass(frozen=True)
class RollResult:
    """Esito completo di un tiro, pronto sia per la UI sia per i test."""
    formula: str
    groups: list[DieGroup]
    constant: int
    modifier: int
    total: int
    advantage: Advantage
    is_crit: bool
    is_crit_fail: bool

    @property
    def all_rolls(self) -> list[int]:
        out: list[int] = []
        for g in self.groups:
            out.extend(g.rolls)
        return out

    def detail(self) -> str:
        """
        Riga di dettaglio leggibile: `"(14, 7 scartato) +3"`.

        Mostra sempre i dadi scartati da vantaggio/svantaggio: è la ragione per
        cui esiste il dettaglio, altrimenti basterebbe il totale.
        """
        parts: list[str] = []
        for g in self.groups:
            nums = ", ".join(str(r) for r in g.kept)
            if g.dropped:
                nums += ", " + ", ".join(f"{d} scartato" for d in g.dropped)
            sign = "" if g.sign > 0 or not parts else "− "
            parts.append(f"{sign}({nums})")
        extra = self.constant + self.modifier
        if extra:
            parts.append(f"{'+' if extra > 0 else '−'} {abs(extra)}")
        return " ".join(parts) if parts else str(self.total)


def parse_formula(formula: str) -> tuple[list[tuple[int, int, int]], int]:
    """
    Scompone una formula in `([(segno, quantità, facce), ...], costante)`.

    Solleva `ValueError` su una formula vuota o non interpretabile: è un errore
    di programmazione (una formula arriva sempre da un `RollSpec` o da un dato
    di gioco), non un input dell'utente da gestire con un fallback silenzioso.
    """
    text = (formula or "").strip().replace(" ", "")
    if not text:
        raise ValueError("Formula di tiro vuota.")

    dice: list[tuple[int, int, int]] = []
    constant = 0
    consumed = 0
    for m in _TERM_RE.finditer(text):
        if m.start() != consumed:
            raise ValueError(f"Formula di tiro non valida: {formula!r}")
        consumed = m.end()
        sign = -1 if m.group(1) == "-" else 1
        if m.group(3):                       # termine NdM
            count = int(m.group(2)) if m.group(2) else 1
            faces = int(m.group(3))
            if count <= 0 or faces <= 0:
                raise ValueError(f"Formula di tiro non valida: {formula!r}")
            dice.append((sign, count, faces))
        else:                                # costante
            constant += sign * int(m.group(4))
    if consumed != len(text):
        raise ValueError(f"Formula di tiro non valida: {formula!r}")
    if not dice and constant == 0:
        raise ValueError(f"Formula di tiro non valida: {formula!r}")
    return dice, constant


def roll(formula: str, advantage: Advantage = "normal", modifier: int = 0,
         rng: random.Random | None = None) -> RollResult:
    """
    Tira una formula. `modifier` si somma a quanto già contenuto nella formula
    (comodo per i `RollSpec`, che tengono formula e modificatore separati).

    `rng` permette di iniettare un generatore con seme fisso nei test senza
    toccare lo stato globale di `random`.
    """
    r = rng or random
    dice, constant = parse_formula(formula)

    groups: list[DieGroup] = []
    is_crit = False
    is_crit_fail = False
    adv_applied = False

    for sign, count, faces in dice:
        # Vantaggio/svantaggio: solo sul PRIMO 1d20 della formula (PHB Cap. 7).
        if (advantage != "normal" and not adv_applied
                and faces == 20 and count == 1 and sign > 0):
            a, b = r.randint(1, 20), r.randint(1, 20)
            keep = max(a, b) if advantage == "advantage" else min(a, b)
            drop = min(a, b) if advantage == "advantage" else max(a, b)
            groups.append(DieGroup(faces, sign, [a, b], [keep], [drop]))
            adv_applied = True
        else:
            rolls = [r.randint(1, faces) for _ in range(count)]
            groups.append(DieGroup(faces, sign, list(rolls), list(rolls)))

    # Critico: si guarda il d20 tenuto, quando ce n'è esattamente uno — è il
    # caso dei tiri per colpire e delle prove, mai di una formula di danno.
    d20_kept = [v for g in groups for v in g.kept if g.faces == 20 and g.sign > 0]
    if len(d20_kept) == 1:
        is_crit = d20_kept[0] == 20
        is_crit_fail = d20_kept[0] == 1

    total = sum(g.total for g in groups) + constant + modifier
    return RollResult(
        formula=formula, groups=groups, constant=constant, modifier=modifier,
        total=total, advantage=advantage, is_crit=is_crit, is_crit_fail=is_crit_fail,
    )


def roll_d20(modifier: int = 0, advantage: Advantage = "normal",
             rng: random.Random | None = None) -> RollResult:
    """Scorciatoia per il tiro più frequente: 1d20 + modificatore."""
    return roll("1d20", advantage=advantage, modifier=modifier, rng=rng)


def format_modifier(value: int) -> str:
    """`+3` / `−1` / `+0` — segno sempre esplicito, come sulla scheda."""
    return f"+{value}" if value >= 0 else f"−{abs(value)}"
