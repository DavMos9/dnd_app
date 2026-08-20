"""
Export della scheda personaggio nel PDF ufficiale D&D 5e italiano.

Il template (`assets/character_sheet_template.pdf`, 3 pagine, 594×783pt) è un
PDF vettoriale piatto SENZA campi AcroForm — l'unico modo di "compilarlo" è
disegnare un overlay di testo con reportlab (origine BASSO-sinistra) pagina
per pagina e fonderlo con pypdf sopra lo sfondo originale.

Le coordinate usate qui derivano dalla ricognizione in
`docs/pdf_sheet_reference/` (README.md + raw_extraction.json + ispezione
visiva di grid-1/2/3.png, origine ALTO-sinistra come pdfplumber) — convertite
con `_y()`. Nessuna dipendenza da Flet: modulo puro, stessa convenzione di
`character_stats.py`/`weapon_calculator.py`.

Decisioni di design (confermate con Davide, vedi il README di ricognizione):
  1. Testo che eccede lo spazio della sua casella → font ridotto
     automaticamente (mai troncato, mai una pagina extra).
  2. Più di 3 armi equipaggiate → solo le prime 3 nella tabella Armi, le
     altre come elenco compresso nel box Equipaggiamento.
  3. Pagina 3 (incantesimi) presente solo se `character.spellcasting_ability`
     è valorizzata (copre anche le sottoclassi "in prestito dal Mago").
"""

from __future__ import annotations

import io
import logging
import os

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

from config.settings import char_prof_bonus
from core.character_stats import (
    ability_label,
    attack_roll,
    damage_roll,
    initiative_roll,
    save_roll,
    skill_roll,
    spell_attack_roll,
    spell_save_dc,
)
from data.game_data.game_data_loader import game_data
from data.repositories import character_repo

logger = logging.getLogger(__name__)

PAGE_W = 594.0
PAGE_H = 783.0

_ASSETS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets"
)
_TEMPLATE_PATH = os.path.join(_ASSETS_DIR, "character_sheet_template.pdf")


def _y(top: float) -> float:
    """Converte una coordinata Y "origine alto" (pdfplumber/griglia) in Y
    "origine basso" (reportlab)."""
    return PAGE_H - top


# ---------------------------------------------------------------------------
# Primitive di disegno — tutte in coordinate "origine alto" (convertite
# internamente), font Helvetica standard (nessun embedding necessario).
# ---------------------------------------------------------------------------


def _fit_size(c: canvas.Canvas, text: str, max_width: float, size: float,
              font: str, min_size: float = 5.0) -> float:
    """Riduce la dimensione del font finché il testo (una riga) non entra in
    `max_width`, senza mai troncarlo — si ferma a `min_size` anche se
    ancora troppo largo (meglio leggermente compresso che tagliato)."""
    while size > min_size and c.stringWidth(text, font, size) > max_width:
        size -= 0.5
    return size


def _value(c: canvas.Canvas, text: str, x: float, top: float, *,
           size: float = 11, font: str = "Helvetica-Bold",
           align: str = "left", max_width: float | None = None) -> None:
    """Disegna un valore su una riga sola, con auto-shrink opzionale se
    `max_width` è passato. `top` è trattato come baseline (approssimazione
    accettabile alla risoluzione di questa scheda)."""
    text = (text or "").strip()
    if not text:
        return
    use_size = size
    if max_width:
        use_size = _fit_size(c, text, max_width, size, font)
    c.setFont(font, use_size)
    y = _y(top)
    if align == "center":
        c.drawCentredString(x, y, text)
    elif align == "right":
        c.drawRightString(x, y, text)
    else:
        c.drawString(x, y, text)


def _wrap_lines(c: canvas.Canvas, text: str, font: str, size: float,
                 max_width: float) -> list[str]:
    lines: list[str] = []
    for para in text.split("\n"):
        words = para.split(" ")
        current = ""
        for w in words:
            candidate = f"{current} {w}".strip()
            if not current or c.stringWidth(candidate, font, size) <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = w
        lines.append(current)
    return lines


def _draw_wrapped(c: canvas.Canvas, text: str, x0: float, top0: float,
                   x1: float, bottom0: float, *, font: str = "Helvetica",
                   max_size: float = 8.5, min_size: float = 4.0,
                   leading_mult: float = 1.2) -> None:
    """Testo multi-riga con word-wrap, font ridotto automaticamente finché
    tutte le righe non entrano nell'altezza del box — mai troncato: se anche
    a `min_size` non basta, le righe vengono comunque disegnate tutte (può
    sconfinare leggermente sotto il bordo, mai perdere contenuto)."""
    text = (text or "").strip()
    if not text:
        return
    width = x1 - x0
    height = bottom0 - top0
    size = max_size
    lines = _wrap_lines(c, text, font, size, width)
    while size > min_size and len(lines) * (size * leading_mult) > height:
        size -= 0.5
        lines = _wrap_lines(c, text, font, size, width)

    leading = size * leading_mult
    c.setFont(font, size)
    y = _y(top0) - size
    for line in lines:
        c.drawString(x0, y, line)
        y -= leading


def _circle(c: canvas.Canvas, cx: float, cy_top: float, r: float, *,
            fill: bool = False) -> None:
    c.circle(cx, _y(cy_top), r, stroke=1, fill=1 if fill else 0)


# ---------------------------------------------------------------------------
# Dati aggregati — un solo posto dove leggere tutto dal repository, così
# ciascuna funzione `_draw_pageN` riceve dati già pronti.
# ---------------------------------------------------------------------------


class _SheetData:
    def __init__(self, character_id: str):
        c = character_repo.get_by_id(character_id)
        if c is None:
            raise ValueError(f"personaggio non trovato: {character_id}")
        character_repo.sync_borrowed_spellcasting_ability(c)

        self.character = c
        self.profs = character_repo.get_proficiencies(character_id)
        self.weapons = character_repo.get_weapons(character_id, equipped_only=True)
        self.inventory = character_repo.get_inventory(character_id)
        self.currency = character_repo.get_currencies(character_id)
        self.spell_slots = {s.slot_level: s for s in character_repo.get_spell_slots(character_id)}
        self.known_spells = character_repo.get_known_spells(character_id)
        self.class_resources = character_repo.get_class_resources(character_id)
        self.custom_abilities = character_repo.get_custom_abilities(character_id)
        self.classes = character_repo.get_character_classes(character_id)
        self.class_display = character_repo.get_class_display_string(
            character_id, f"{c.class_name} {c.level}".strip()
        )


# ---------------------------------------------------------------------------
# PAGINA 1 — scheda principale
# ---------------------------------------------------------------------------

_ABILITY_BLOCKS = [
    ("str", 139.8), ("dex", 211.7), ("con", 282.9),
    ("int", 354.8), ("wis", 426.4), ("cha", 497.8),
]
_ABILITY_CX = 50.5

_SKILL_ROWS = [
    ("Acrobazia", 316.9), ("Addestrare Animali", 330.4), ("Arcano", 343.9),
    ("Atletica", 357.4), ("Furtività", 370.9), ("Indagare", 384.4),
    ("Inganno", 397.9), ("Intimidire", 411.4), ("Intrattenere", 424.9),
    ("Intuizione", 438.4), ("Medicina", 451.9), ("Natura", 465.4),
    ("Percezione", 478.9), ("Persuasione", 492.4), ("Rapidità di Mano", 505.9),
    ("Religione", 519.4), ("Sopravvivenza", 532.9), ("Storia", 546.4),
]
_SAVE_ROWS = [
    ("str", "Forza", 201.6), ("dex", "Destrezza", 215.1), ("con", "Costituzione", 228.6),
    ("int", "Intelligenza", 242.1), ("wis", "Saggezza", 255.6), ("cha", "Carisma", 269.1),
]

_WEAPON_ROWS = [393.2, 413.65, 434.3]


def _draw_page1(c: canvas.Canvas, d: _SheetData) -> None:
    ch = d.character

    # --- Header (Classe&Livello / Background / Nome Giocatore // Razza /
    # Allineamento / Punti Esperienza) — valore sopra l'etichetta, colonne a
    # x≈264/377/474.
    _value(c, d.class_display, 264, 50, size=11, max_width=105)
    _value(c, ch.background, 377, 50, size=11, max_width=90)
    _value(c, ch.player_name, 474, 50, size=11, max_width=90)
    race_label = (ch.race or "") + (f" ({ch.subrace})" if ch.subrace else "")
    _value(c, race_label, 264, 76, size=11, max_width=105)
    _value(c, ch.alignment, 377, 76, size=11, max_width=90)
    _value(c, str(ch.xp or 0), 474, 76, size=11, max_width=90)

    # --- Nome personaggio, sul nastro decorativo.
    _value(c, ch.name, 150, 70, size=16, font="Helvetica-Bold",
           align="center", max_width=175)

    # --- Ispirazione (quadrato) / Bonus di Competenza (cerchio).
    if ch.inspiration:
        _value(c, "X", 100.6, 137, size=14, align="center")
    _value(c, f"+{char_prof_bonus(ch)}", 102, 175, size=14, align="center")

    # --- CA / Iniziativa / Velocità.
    _value(c, str(ch.ac or 10), 240.7, 152, size=18, align="center")
    init_mod = initiative_roll(ch).modifier
    _value(c, f"{init_mod:+d}", 296.9, 152, size=16, align="center")
    speed = character_repo.get_effective_speed(ch)
    _value(c, f"{speed:g} m", 355.55, 152, size=13, align="center", max_width=48)

    # --- 6 caratteristiche: modificatore sopra, punteggio nell'ovale sotto.
    for key, label_top in _ABILITY_BLOCKS:
        score = int(getattr(ch, f"{key}_score", 10) or 10)
        mod = (score - 10) // 2
        _value(c, f"{mod:+d}", _ABILITY_CX, label_top + 30, size=17,
               align="center")
        _value(c, str(score), _ABILITY_CX, label_top + 51, size=12,
               align="center", font="Helvetica")

    # --- Tiri Salvezza (6) e Abilità (18): pallino competenza + modificatore
    # sulla riga vuota fra pallino e nome.
    for key, _name, row_top in _SAVE_ROWS:
        roll = _save_roll_for(ch, d, key)
        _draw_prof_row(c, row_top, roll["proficient"], roll["expert"], roll["modifier"])
    for skill_name, row_top in _SKILL_ROWS:
        roll = skill_roll(ch, d.profs, skill_name)
        _draw_prof_row(c, row_top, roll.proficient, roll.expert, roll.modifier)

    # --- Percezione Passiva.
    perc_mod = skill_roll(ch, d.profs, "Percezione").modifier
    passive = ch.passive_perception_override or (10 + perc_mod)
    _value(c, str(passive), 109.8, 586, size=15, align="center")

    # --- PF massimo / attuali / temporanei, Dadi Vita, TS contro morte.
    _value(c, str(ch.hp_max or 0), 310, 201, size=11, align="left")
    _value(c, str(ch.hp_current or 0), 299, 226, size=20, align="center")
    _value(c, str(ch.hp_temp or 0), 299, 280, size=20, align="center")
    _value(c, f"{ch.hit_dice_remaining or 0}/{ch.hit_dice_total or 0} d{ch.hit_dice_type or 6}",
           245, 322, size=10, align="left")
    for i, x in enumerate((343.7, 356.55, 369.4)):
        _circle(c, x, 320, 3.8, fill=i < (ch.death_saves_success or 0))
        _circle(c, x, 335, 3.8, fill=i < (ch.death_saves_failure or 0))

    # --- Tabella Armi: solo le prime 3 equipaggiate (decisione presa con
    # Davide — le altre finiscono nell'elenco compresso di Equipaggiamento).
    for i, weapon in enumerate(d.weapons[:3]):
        row_y = _WEAPON_ROWS[i]
        _value(c, weapon.name, 220, row_y, size=9, align="left", max_width=57)
        atk = attack_roll(ch, weapon, d.profs).modifier
        _value(c, f"{atk:+d}", 300.1, row_y, size=9, align="center")
        dmg = damage_roll(ch, weapon)
        dmg_text = f"{dmg.formula}{dmg.modifier:+d} {dmg.damage_type}".strip()
        _value(c, dmg_text, 351.25, row_y, size=8, align="center", max_width=60)

    # --- Monete.
    for label_top, amount in (
        (598.7, d.currency.copper if d.currency else 0),
        (624.4, d.currency.silver if d.currency else 0),
        (650.4, d.currency.electrum if d.currency else 0),
        (676.5, d.currency.gold if d.currency else 0),
        (702.2, d.currency.platinum if d.currency else 0),
    ):
        _value(c, str(amount or 0), 241, label_top + 10, size=11, align="center")

    # --- Box di solo testo, tutti con auto-shrink.
    _draw_wrapped(c, ch.personality_traits, 408, 130, 568, 180)
    _draw_wrapped(c, ch.ideals, 408, 200, 568, 235)
    _draw_wrapped(c, ch.bonds, 408, 256, 568, 291)
    _draw_wrapped(c, ch.flaws, 408, 311, 568, 346)

    _draw_wrapped(c, _competencies_text(d), 22, 618, 198, 748, max_size=8)
    # x0=266 (non 211, il bordo reale del box): le 5 caselle moneta occupano
    # x≈215-259 nella stessa fascia verticale, sovrapposte al bordo sinistro
    # del box Equipaggiamento nel template originale — il testo deve iniziare
    # dopo di loro per non finirci sopra.
    _draw_wrapped(c, _equipment_text(d), 266, 584, 387, 748, max_size=8)
    _draw_wrapped(c, _privileges_text(d), 401, 378, 575, 748, max_size=7.5)


def _save_roll_for(ch, d: _SheetData, key: str) -> dict:
    r = save_roll(ch, d.profs, key)
    return {"proficient": r.proficient, "expert": False, "modifier": r.modifier}


def _draw_prof_row(c: canvas.Canvas, row_top: float, proficient: bool,
                    expert: bool, modifier: int) -> None:
    # Il template ha già un pallino stampato per ogni riga (misurato su
    # raw_extraction.json, curve_boxes: centro x≈96.5, raggio≈3.3, offset Y
    # dal row_top del rigo ≈2.9 — costante su tutte le 24 righe controllate,
    # tiri salvezza e abilità). Il vecchio x=92/cy=row_top+3.5 non coincideva
    # (era stato stimato senza calibrazione, README "da rifinire a vista") e
    # disegnava un secondo pallino leggermente sfalsato sopra quello del
    # template — effetto "doppio cerchio" trovato con un render di verifica.
    cx, cy, r = 96.5, row_top + 2.9, 3.3
    if proficient:
        _circle(c, cx, cy, r, fill=True)
    if expert:
        _circle(c, cx, cy, r + 1.6, fill=False)
    _value(c, f"{modifier:+d}", 118, row_top + 7, size=9, align="right")


def _competencies_text(d: _SheetData) -> str:
    by_type: dict[str, list[str]] = {}
    for p in d.profs:
        if p.proficiency_type in ("skill", "save", "saving_throw"):
            continue
        by_type.setdefault(p.proficiency_type, []).append(p.name)
    labels = {"armor": "Armature", "weapon": "Armi", "tool": "Strumenti", "language": "Linguaggi"}
    lines = []
    for key in ("armor", "weapon", "tool", "language"):
        names = by_type.get(key, [])
        if names:
            lines.append(f"{labels[key]}: {', '.join(sorted(set(names)))}")
    return "\n".join(lines)


def _equipment_text(d: _SheetData) -> str:
    lines = []
    extra_weapons = d.weapons[3:]
    if extra_weapons:
        parts = []
        for w in extra_weapons:
            atk = attack_roll(d.character, w, d.profs).modifier
            dmg = damage_roll(d.character, w)
            parts.append(f"{w.name} ({atk:+d}, {dmg.formula}{dmg.modifier:+d} {dmg.damage_type})")
        lines.append("Altre armi: " + "; ".join(parts))
    for item in d.inventory:
        qty = f" x{item.quantity}" if item.quantity and item.quantity != 1 else ""
        lines.append(f"{item.name}{qty}")
    return "\n".join(lines)


def _privileges_text(d: _SheetData) -> str:
    """
    Elenco compatto (solo nomi, non le descrizioni integrali — lo spazio del
    box ufficiale non è pensato per il testo PHB completo di ogni privilegio,
    e il giocatore la usa comunque insieme al manuale): feature di
    classe/sottoclasse filtrate per livello raggiunto, tratti razziali, e
    abilità custom. Stessa fonte dati di `combattimento_tab._load_class_features`
    (`GameDataLoader.get_class()`), riletta qui invece di essere duplicata
    manualmente.
    """
    ch = d.character
    lines: list[str] = []

    classes = d.classes or []
    if not classes and ch.class_name:
        from data.models import CharacterClass
        classes = [CharacterClass(class_name=ch.class_name, subclass=ch.subclass or "", level=ch.level)]

    for cc in classes:
        cls_data = game_data.get_class(cc.class_name)
        if not cls_data:
            continue
        for feat in cls_data.get("features", []):
            if feat.get("level", 1) <= cc.level:
                lines.append(f"{feat['name']} (Lv.{feat['level']}, {cc.class_name})")
        subclass_name = (cc.subclass or "").strip()
        if subclass_name:
            for sc in cls_data.get("subclasses", []):
                if sc.get("name", "").lower() == subclass_name.lower():
                    for feat in sc.get("features", []):
                        if feat.get("level", 1) <= cc.level:
                            lines.append(f"{feat['name']} (Lv.{feat['level']}, {subclass_name})")
                    break

    race_info = game_data.get_resolved_race(ch.race or "", ch.subrace or "")
    for trait in race_info.get("traits", []):
        name = trait.get("name", "")
        if name:
            lines.append(f"{name} (razza)")

    for ability in d.custom_abilities:
        lines.append(f"{ability.name} (custom)")

    return "; ".join(lines)


# ---------------------------------------------------------------------------
# PAGINA 2 — retro / background
# ---------------------------------------------------------------------------


def _draw_page2(c: canvas.Canvas, d: _SheetData) -> None:
    ch = d.character

    _value(c, ch.age, 256, 50, size=10, max_width=100)
    _value(c, ch.height, 369, 50, size=10, max_width=90)
    _value(c, ch.weight, 466, 50, size=10, max_width=90)
    _value(c, ch.eyes, 256, 77, size=10, max_width=100)
    _value(c, ch.skin, 369, 77, size=10, max_width=90)
    _value(c, ch.hair, 466, 77, size=10, max_width=90)
    _value(c, ch.name, 150, 71, size=14, font="Helvetica-Bold",
           align="center", max_width=175)

    _draw_wrapped(c, ch.appearance_notes, 23, 118, 191, 344, max_size=8)
    # La porzione destra del box "Alleati & Organizzazioni" ospita il
    # riquadro decorativo Nome/Simbolo del template (x≈408-557) — il
    # personaggio non ha un campo divinità/simbolo dedicato nel modello dati,
    # quindi il testo resta confinato alla metà sinistra per non sovrapporsi.
    _draw_wrapped(c, ch.allies_organizations, 212, 118, 400, 344, max_size=8)
    _draw_wrapped(c, ch.additional_traits, 212, 363, 569, 580, max_size=8)
    _draw_wrapped(c, ch.backstory, 23, 373, 191, 756, max_size=8)
    _draw_wrapped(c, _treasure_text(d), 212, 591, 569, 756, max_size=8)


def _treasure_text(d: _SheetData) -> str:
    """
    Nessun campo "tesoro" dedicato nel modello dati: il box viene composto
    dalla stessa fonte di verità delle monete (pagina 1, qui ripetuta per
    intero visto lo spazio) più gli oggetti di categoria "magic"
    dall'inventario — la lettura più vicina a "tesoro" (oggetti magici e
    ricchezza) che i dati esistenti permettono senza inventare un campo.
    """
    lines = []
    cur = d.currency
    if cur:
        lines.append(
            f"MR {cur.copper or 0}  MA {cur.silver or 0}  ME {cur.electrum or 0}  "
            f"MO {cur.gold or 0}  MP {cur.platinum or 0}"
        )
    magic_items = [i for i in d.inventory if i.category == "magic"]
    for item in magic_items:
        lines.append(item.name)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# PAGINA 3 — incantesimi
# ---------------------------------------------------------------------------

# (top del marcatore esagonale di livello, colonna) — da raw_extraction.json.
_SPELL_COLUMNS = [
    (24.3, {0: 144.8, 1: 312.5, 2: 541.1}),
    (221.7, {3: 144.8, 4: 370.4, 5: 596.9}),
    (408.9, {6: 144.8, 7: 314.5, 8: 484.3, 9: 625.1}),
]
# Offset dal top del marcatore esagonale alla riga (rigo stampato) del primo
# incantesimo — misurato su raw_extraction.json (pagina 3, `lines`): i livelli
# 1+ hanno la barra "SLOT TOTALI/SLOT SPESI" sopra le righe (offset ≈35-36),
# il livello 0 (Trucchetti) no (offset ≈33) — valori diversi per lo stesso
# motivo, non un'incoerenza.
_ROW_START_OFFSET = 35.0
_ROW_START_OFFSET_LVL0 = 33.0
_ROW_HEIGHT = 14.0
_COL_BOTTOM = 758.0


def _draw_page3(c: canvas.Canvas, d: _SheetData) -> None:
    ch = d.character
    key = (ch.spellcasting_ability or "").strip().lower()

    class_label = ch.class_name or ""
    _value(c, class_label, 150, 80, size=13, font="Helvetica-Bold",
           align="center", max_width=175)

    if key:
        _value(c, ability_label(key), 309, 68, size=12, align="center", max_width=78)
    dc = spell_save_dc(ch)
    if dc is not None:
        _value(c, str(dc), 407, 68, size=14, align="center")
    atk = spell_attack_roll(ch)
    if atk is not None:
        _value(c, f"{atk.modifier:+d}", 522, 68, size=14, align="center")

    by_level: dict[int, list] = {}
    for spell in d.known_spells:
        by_level.setdefault(spell.spell_level, []).append(spell)

    for col_x0, levels in _SPELL_COLUMNS:
        level_list = sorted(levels.items())
        for idx, (level, marker_top) in enumerate(level_list):
            next_top = (level_list[idx + 1][1] if idx + 1 < len(level_list)
                        else _COL_BOTTOM)
            _draw_spell_level(c, d, col_x0, level, marker_top, next_top)


def _draw_spell_level(c: canvas.Canvas, d: _SheetData, col_x0: float,
                       level: int, marker_top: float, next_top: float) -> None:
    pill_x0 = col_x0 + 8.2
    pill_x1 = col_x0 + 173.2

    if level > 0:
        slot = d.spell_slots.get(level)
        total = slot.total if slot else 0
        used = slot.used if slot else 0
        if total:
            left_cx = col_x0 + 8.2 + 29.6
            right_cx = col_x0 + 8.2 + 92.8
            pill_cy = marker_top + 13.7
            _value(c, str(total), left_cx, pill_cy, size=11, align="center")
            _value(c, str(used), right_cx, pill_cy, size=11, align="center")

    spells = sorted(
        (s for s in d.known_spells if s.spell_level == level),
        key=lambda s: s.name,
    )
    if not spells:
        return

    rows_top = marker_top + (_ROW_START_OFFSET_LVL0 if level == 0 else _ROW_START_OFFSET)
    if level == 1 and col_x0 == _SPELL_COLUMNS[0][0]:
        # Livello 1, colonna 1: le didascalie "PREPARATI"/"NOME INCANTESIMO"
        # (uniche nell'intero foglio, README §pagina 3) occupano lo spazio
        # del primo rigo — la prima riga scrivibile è la successiva, un
        # _ROW_HEIGHT più in basso (un rigo di capienza in meno solo qui).
        rows_top += _ROW_HEIGHT
    available = next_top - rows_top
    rows_at_normal = max(1, int(available // _ROW_HEIGHT))
    row_h = _ROW_HEIGHT if len(spells) <= rows_at_normal else max(
        available / len(spells), 6.5
    )

    checkbox_x = col_x0 + 3.4
    text_x = col_x0 + 9.5
    text_w = pill_x1 - text_x

    for i, spell in enumerate(spells):
        # `row_top` è la Y (origine alto) del rigo stampato stesso (misurata,
        # vedi _ROW_START_OFFSET*) — il testo va SOPRA quel rigo, non sotto:
        # baseline a `row_top - 2.5`, mai `row_top + qualcosa` (avrebbe
        # scritto il nome sopra il rigo SUCCESSIVO, un pieno row_h più in
        # basso — bug reale trovato con un render di verifica).
        row_top = rows_top + i * row_h
        baseline = row_top - 2.5
        if spell.is_prepared or level == 0:
            _circle(c, checkbox_x, baseline - 1.0, 2.6, fill=True)
        else:
            _circle(c, checkbox_x, baseline - 1.0, 2.6, fill=False)
        size = min(8.5, row_h * 0.65)
        _value(c, spell.name, text_x, baseline, size=size,
               font="Helvetica", align="left", max_width=text_w)


# ---------------------------------------------------------------------------
# Entry point pubblico
# ---------------------------------------------------------------------------


def _render_overlay(draw_fn, d: _SheetData):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(PAGE_W, PAGE_H))
    draw_fn(c, d)
    c.save()
    buf.seek(0)
    return PdfReader(buf).pages[0]


def suggested_pdf_filename(character_id: str) -> str:
    """Nome file suggerito per l'export PDF — stessa convenzione (slug del
    nome + livello + timestamp) di character_export.suggested_export_filename(),
    solo estensione diversa: nessuna duplicazione della logica di slug."""
    from data.repositories.character_export import suggested_export_filename
    return os.path.splitext(suggested_export_filename(character_id))[0] + ".pdf"


def export_character_pdf(character_id: str, output_path: str) -> bool:
    """
    Genera la scheda PDF compilata per `character_id` e la scrive in
    `output_path`. Ritorna `False` (mai un'eccezione) se il personaggio non
    esiste o se qualcosa va storto durante la generazione — il chiamante
    (wiring UI, non incluso in questo modulo) mostra un errore all'utente.
    """
    try:
        d = _SheetData(character_id)
    except Exception as e:
        logger.error(f"Errore caricamento dati per export PDF {character_id}: {e}")
        return False

    try:
        reader = PdfReader(_TEMPLATE_PATH)
        writer = PdfWriter()

        base1 = reader.pages[0]
        base1.merge_page(_render_overlay(_draw_page1, d))
        writer.add_page(base1)

        base2 = reader.pages[1]
        base2.merge_page(_render_overlay(_draw_page2, d))
        writer.add_page(base2)

        include_page3 = bool((d.character.spellcasting_ability or "").strip())
        if include_page3:
            base3 = reader.pages[2]
            base3.merge_page(_render_overlay(_draw_page3, d))
            writer.add_page(base3)

        with open(output_path, "wb") as f:
            writer.write(f)
        return True
    except Exception as e:
        logger.error(f"Errore generazione PDF scheda {character_id}: {e}")
        return False
