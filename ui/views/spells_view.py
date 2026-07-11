"""
SpellsView — Gestione incantesimi del personaggio.

Struttura:
  - Header: caratteristica/CD/bonus attacco + banner "X/Y preparati"
  - Lista slot per livello (read-only — modifica in Combattimento)
  - Lista incantesimi da JSON classe, raggruppati per livello
    · Toggle preparazione (cerchietto) — scrive in known_spells
    · Click sul nome → dialog con descrizione completa

Regole PHB preparazione:
  - I trucchetti (livello 0) sono sempre disponibili, non contano nel limite.
  - Full caster (Chierico, Druido, Mago): mod_car + livello classe (min 1)
  - Half caster (Paladino, Ranger): mod_car + metà livello arrotondato giù (min 1)
  - Classi "know" (Bardo, Stregone, Warlock): nessun limite (sezione "Incantesimi Conosciuti")
  - Override manuale del giocatore: sovrascrive la formula se ≥ 1.
"""

import flet as ft
import logging
from typing import Any, cast
from config.settings import *
from config.settings import get_modifier, char_prof_bonus
from data.models import Character, KnownSpell, SpellSlot
import data.repositories.character_repo as character_repo
from data.game_data.game_data_loader import GameDataLoader
from ui.theme import section_header

logger = logging.getLogger(__name__)

_loader = GameDataLoader()

_SLOT_NAMES = ["1°", "2°", "3°", "4°", "5°", "6°", "7°", "8°", "9°"]

# Classi con sistema "prepara dalla lista"
_PREP_FULL: set[str] = {"chierico", "druido", "mago"}
_PREP_HALF: set[str] = {"paladino", "ranger"}
# Classi "know" (nessun limite di preparazione)
_KNOW_CLASSES: set[str] = {"bardo", "stregone", "warlock"}


def _calc_max_prepared(c: Character) -> int | None:
    """
    Calcola il massimo di incantesimi preparabili secondo le regole PHB.
    Restituisce None per le classi "know" (nessun limite).
    Tiene conto dell'override manuale del giocatore (max_prepared_spells_override > 0).
    """
    if c.max_prepared_spells_override > 0:
        return c.max_prepared_spells_override

    key = (c.class_name or "").strip().lower()
    scores = {
        "str": c.str_score, "dex": c.dex_score, "con": c.con_score,
        "int": c.int_score, "wis": c.wis_score, "cha": c.cha_score,
    }
    sp_key = c.spellcasting_ability or ""
    sp_mod = get_modifier(scores.get(sp_key, 10))

    if key in _PREP_FULL:
        return max(1, sp_mod + c.level)
    if key in _PREP_HALF:
        return max(1, sp_mod + max(1, c.level // 2))
    if key in _KNOW_CLASSES:
        return None  # nessun limite — "known spells"
    # Sottoclasse incantatore (es. Guerriero Arcano, Ladro Mistificatore):
    # segnaliamo nessun limite perché la formula varia troppo
    return None


class SpellsView(ft.ListView):
    """Vista incantesimi: preparazione e consultazione."""

    def __init__(self, character: Character) -> None:
        super().__init__(expand=True, spacing=12, padding=16)
        self.character = character
        self._page: ft.Page | None = None
        self._slots: list[SpellSlot] = character_repo.get_spell_slots(character.id)
        self._known: dict[tuple[str, int], KnownSpell] = {}
        self._reload_known()
        self._class_spells: list[dict[str, Any]] = _loader.get_spells(
            character.class_name or ""
        )
        self._build()

    def did_mount(self) -> None:
        self._page = cast(ft.Page, self.page)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _reload_known(self) -> None:
        self._known = {
            (s.name, s.spell_level): s
            for s in character_repo.get_known_spells(self.character.id)
        }

    def _is_prepared(self, name: str, level: int) -> bool:
        ks = self._known.get((name, level))
        return ks is not None and ks.is_prepared

    def _prepared_count(self) -> int:
        """Conta solo gli incantesimi preparati di livello ≥ 1 (trucchetti esclusi)."""
        return sum(
            1 for (_, lv), ks in self._known.items()
            if ks.is_prepared and lv > 0
        )

    def _toggle_prepared(self, spell: dict[str, Any]) -> None:
        name  = spell.get("name", "")
        level = spell.get("level", 0)
        was_prepared = self._is_prepared(name, level)

        # I trucchetti (level 0) non hanno limite — sempre togglabili
        if not was_prepared and level > 0:
            max_prep = _calc_max_prepared(self.character)
            if max_prep is not None and self._prepared_count() >= max_prep:
                # Limite raggiunto: mostra snackbar e blocca
                if self._page:
                    self._page.show_dialog(ft.AlertDialog(
                        title=ft.Text("Limite raggiunto", size=14,
                                      weight=ft.FontWeight.BOLD,
                                      color=COLOR_ACCENT_CRIMSON),
                        content=ft.Text(
                            f"Hai già preparato {max_prep} incantesimi, "
                            f"il massimo per il tuo livello.\n\n"
                            f"Deprepara un incantesimo oppure aumenta il limite "
                            f"manualmente con il tasto ✎.",
                            size=13, color=COLOR_TEXT_PRIMARY,
                        ),
                        actions=[
                            ft.TextButton(
                                "OK",
                                on_click=lambda e: self._page.pop_dialog()
                                if self._page else None,
                            )
                        ],
                        bgcolor=COLOR_BG_CARD,
                    ))
                return

        if was_prepared:
            character_repo.remove_known_spell(self.character.id, name, level)
        else:
            comps = spell.get("components", [])
            comp_str = ", ".join(comps) if isinstance(comps, list) else str(comps)
            if spell.get("material"):
                comp_str += f" ({spell['material']})"
            character_repo.upsert_known_spell(
                character_id=self.character.id,
                name=name, level=level, is_prepared=True,
                school=spell.get("school", ""),
                casting_time=spell.get("casting_time", ""),
                spell_range=spell.get("range", ""),
                components=comp_str,
                duration=spell.get("duration", ""),
                description=spell.get("description", ""),
                higher_levels=spell.get("higher_levels", "") or "",
                class_list=self.character.class_name or "",
            )

        self._reload_known()
        self._refresh()

    def _open_override_dialog(self) -> None:
        """Dialog per modificare manualmente il limite di preparazione."""
        if not self._page:
            return
        page = self._page
        c = self.character
        # Calcola il valore formula escludendo l'override corrente
        tmp_override = c.max_prepared_spells_override
        c.max_prepared_spells_override = 0
        formula_val  = _calc_max_prepared(c)
        c.max_prepared_spells_override = tmp_override

        formula_desc = (
            f"Formula PHB: {formula_val}"
            if formula_val is not None
            else "Classe senza limite di preparazione"
        )

        f_val = ft.TextField(
            label="Massimo incantesimi preparabili",
            value=str(c.max_prepared_spells_override or ""),
            hint_text="Lascia vuoto o 0 per usare la formula PHB",
            keyboard_type=ft.KeyboardType.NUMBER,
            text_style=ft.TextStyle(size=14, color=COLOR_TEXT_PRIMARY,
                                    font_family=FONT_MONO),
            border_color=COLOR_BORDER,
            focused_border_color=COLOR_ACCENT_BLUE,
            bgcolor=COLOR_BG_CARD,
            autofocus=True,
        )

        def save(ev):
            if page is None:
                return
            try:
                val = int(f_val.value or 0)
            except ValueError:
                val = 0
            val = max(0, val)
            character_repo.update_max_prepared_override(c.id, val)
            c.max_prepared_spells_override = val
            page.pop_dialog()
            self._refresh()

        def reset(ev):
            if page is None:
                return
            character_repo.update_max_prepared_override(c.id, 0)
            c.max_prepared_spells_override = 0
            page.pop_dialog()
            self._refresh()

        page.show_dialog(ft.AlertDialog(
            title=ft.Text("Limite Preparazione", size=14,
                          weight=ft.FontWeight.BOLD, color=COLOR_TEXT_TITLE),
            content=ft.Column([
                ft.Text(formula_desc, size=12, color=COLOR_TEXT_MUTED, italic=True),
                ft.Container(height=4),
                f_val,
                ft.Text(
                    "Imposta 0 per tornare al calcolo automatico PHB.",
                    size=11, color=COLOR_TEXT_MUTED,
                ),
            ], spacing=8),
            actions=[
                ft.TextButton("Annulla",
                              on_click=lambda ev: page.pop_dialog() if page else None),
                ft.TextButton("Reset PHB", on_click=reset,
                              style=ft.ButtonStyle(color=COLOR_TEXT_MUTED)),
                ft.ElevatedButton(
                    "Salva", on_click=save,
                    style=ft.ButtonStyle(
                        bgcolor=COLOR_ACCENT_BLUE, color="#ffffff",
                        shape=ft.RoundedRectangleBorder(radius=4),
                    ),
                ),
            ],
            bgcolor=COLOR_BG_CARD,
        ))

    def _open_spell_dialog(self, spell: dict[str, Any]) -> None:
        if not self._page:
            return
        page = self._page
        name   = spell.get("name", "")
        level  = spell.get("level", 0)
        school = spell.get("school", "")
        comps  = spell.get("components", [])
        comp_str = ", ".join(comps) if isinstance(comps, list) else str(comps)
        if spell.get("material"):
            comp_str += f" ({spell['material']})"

        conc_icon   = "◉ Concentrazione  " if spell.get("concentration") else ""
        ritual_icon = "☽ Rituale"          if spell.get("ritual")        else ""
        level_label = "Trucchetto" if level == 0 else f"{_SLOT_NAMES[level - 1]} livello"
        header_line = f"{level_label}  ·  {school}" if school else level_label

        def _info_row(label: str, value: str) -> ft.Row:
            return ft.Row([
                ft.Text(label, size=11, color=COLOR_TEXT_MUTED,
                        weight=ft.FontWeight.BOLD, width=100),
                ft.Text(value, size=12, color=COLOR_TEXT_PRIMARY, expand=True),
            ], spacing=4)

        rows: list[ft.Control] = [
            ft.Text(header_line, size=11, color=COLOR_TEXT_MUTED, italic=True),
            ft.Container(height=4),
        ]
        for label, key in [
            ("Tempo:", "casting_time"), ("Gittata:", "range"),
            ("Durata:", "duration"),
        ]:
            if spell.get(key):
                rows.append(_info_row(label, spell[key]))
        if comp_str:
            rows.append(_info_row("Componenti:", comp_str))
        if conc_icon or ritual_icon:
            rows.append(ft.Text(f"{conc_icon}{ritual_icon}",
                                size=11, color=COLOR_ACCENT_AMBER))
        rows.append(ft.Divider(color=COLOR_BORDER))
        rows.append(ft.Text(
            spell.get("description", "Nessuna descrizione."),
            size=13, color=COLOR_TEXT_PRIMARY, selectable=True,
        ))
        if spell.get("higher_levels"):
            rows += [
                ft.Container(height=6),
                ft.Text("Ai livelli superiori:", size=11, color=COLOR_TEXT_MUTED,
                        weight=ft.FontWeight.BOLD),
                ft.Text(spell["higher_levels"], size=12, color=COLOR_TEXT_SECONDARY),
            ]

        page.show_dialog(ft.AlertDialog(
            title=ft.Row([
                ft.Container(
                    content=ft.Text(
                        f"Lv{level}" if level > 0 else "0",
                        size=10, color="#ffffff", weight=ft.FontWeight.BOLD,
                    ),
                    bgcolor=COLOR_ACCENT_BLUE if level == 0 else COLOR_ACCENT_CRIMSON,
                    padding=ft.Padding.symmetric(horizontal=6, vertical=3),
                    border_radius=4,
                ),
                ft.Container(width=8),
                ft.Text(name, size=14, weight=ft.FontWeight.BOLD,
                        color=COLOR_TEXT_TITLE, expand=True),
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            content=ft.Column(rows, spacing=6, scroll=ft.ScrollMode.AUTO),
            actions=[
                ft.TextButton("Chiudi",
                              on_click=lambda e: page.pop_dialog() if page else None),
            ],
            bgcolor=COLOR_BG_CARD,
        ))

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self) -> None:
        c = self.character
        controls: list[ft.Control] = []

        if c.spellcasting_ability:
            controls += [section_header("Magia"), self._section_magic_header(c)]

        active_slots = [s for s in self._slots if s.total > 0]
        if active_slots:
            controls += [
                section_header("Slot Incantesimo"),
                self._section_slots_summary(active_slots),
            ]

        if not self._class_spells:
            controls.append(ft.Container(
                content=ft.Column([
                    ft.Icon(ft.Icons.AUTO_AWESOME, size=48, color=COLOR_BORDER),
                    ft.Container(height=8),
                    ft.Text(
                        f"Nessun incantesimo per {c.class_name}.",
                        size=14, color=COLOR_TEXT_MUTED,
                        text_align=ft.TextAlign.CENTER,
                    ),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                   alignment=ft.MainAxisAlignment.CENTER),
                padding=40,
            ))
        else:
            by_level: dict[int, list[dict]] = {}
            for sp in self._class_spells:
                by_level.setdefault(sp.get("level", 0), []).append(sp)

            controls += [
                section_header("Incantesimi"),
                self._section_prep_banner(c),
            ]
            for lv in sorted(by_level.keys()):
                label = "Trucchetti (0°)" if lv == 0 else f"Livello {_SLOT_NAMES[lv - 1]}"
                controls += [
                    section_header(label),
                    self._section_spell_list(by_level[lv]),
                ]

        # Incantesimi "extra" — conosciuti dal DB ma non nella lista JSON della classe
        # (Segreti Magici, Mistificatore, Eldritch Knight, etc.)
        class_spell_names: set[str] = {s.get("name", "") for s in self._class_spells}
        extra_known: list[KnownSpell] = [
            ks for ks in self._known.values()
            if ks.name not in class_spell_names and ks.is_prepared
        ]
        if extra_known:
            extra_by_level: dict[int, list[KnownSpell]] = {}
            for ks in extra_known:
                extra_by_level.setdefault(ks.spell_level, []).append(ks)

            section_label = (
                "Segreti Magici"
                if (c.class_name or "").lower() == "bardo"
                else "Incantesimi Extra"
            )
            controls.append(section_header(section_label))
            for lv in sorted(extra_by_level.keys()):
                lv_label = "Trucchetti (0°)" if lv == 0 else f"Livello {_SLOT_NAMES[lv - 1]}"
                controls += [
                    section_header(lv_label),
                    self._section_extra_spell_list(extra_by_level[lv]),
                ]

        self.controls.clear()
        for ctrl in controls:
            self.controls.append(ctrl)

    # ------------------------------------------------------------------
    # Sezioni UI
    # ------------------------------------------------------------------

    def _section_magic_header(self, c: Character) -> ft.Container:
        _KEY_TO_NAME = dict(zip(ABILITY_KEYS, ABILITY_SCORES))
        _KEY_TO_ABBR = dict(zip(ABILITY_KEYS, ABILITY_ABBR))
        _KEY_TO_SCORE = {
            "str": c.str_score, "dex": c.dex_score, "con": c.con_score,
            "int": c.int_score, "wis": c.wis_score, "cha": c.cha_score,
        }
        pb      = char_prof_bonus(c)
        sp_key  = c.spellcasting_ability or ""
        sp_mod  = get_modifier(_KEY_TO_SCORE.get(sp_key, 10))
        save_dc = 8 + pb + sp_mod
        atk_bon = pb + sp_mod
        atk_str = f"+{atk_bon}" if atk_bon >= 0 else str(atk_bon)
        sp_name = _KEY_TO_NAME.get(sp_key, sp_key)
        sp_abbr = _KEY_TO_ABBR.get(sp_key, sp_key.upper())

        def _box(label: str, value: str) -> ft.Container:
            return ft.Container(
                content=ft.Column([
                    ft.Text(label, size=9, color=COLOR_TEXT_MUTED,
                            weight=ft.FontWeight.BOLD,
                            text_align=ft.TextAlign.CENTER),
                    ft.Text(value, size=18, color=COLOR_ACCENT_BLUE,
                            weight=ft.FontWeight.BOLD,
                            text_align=ft.TextAlign.CENTER,
                            font_family=FONT_MONO),
                ], spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                bgcolor=COLOR_BG_SECONDARY,
                padding=ft.Padding.symmetric(horizontal=10, vertical=8),
                border_radius=6, expand=True,
            )

        return ft.Container(
            content=ft.Row([
                _box(f"CARATTERISTICA\n({sp_abbr})", sp_name),
                _box("CD TIRO SALV.", str(save_dc)),
                _box("BONUS ATTACCO", atk_str),
            ], spacing=8),
            bgcolor=COLOR_BG_CARD,
            padding=14,
            border=ft.Border(
                top=ft.BorderSide(3, COLOR_ACCENT_BLUE),
                left=ft.BorderSide(1, COLOR_BORDER),
                right=ft.BorderSide(1, COLOR_BORDER),
                bottom=ft.BorderSide(1, COLOR_BORDER),
            ),
            border_radius=6,
        )

    def _section_prep_banner(self, c: Character) -> ft.Container:
        """
        Banner "X / Y preparati ✎" — mostra il limite e permette l'override.
        I trucchetti non contano nel limite (PHB).
        """
        max_prep = _calc_max_prepared(c)
        count    = self._prepared_count()

        if max_prep is None:
            # Classi "know": nessun limite
            label_text = f"{count} incantesimi conosciuti"
            color = COLOR_TEXT_MUTED
            ratio = 0.0
        else:
            label_text = f"{count} / {max_prep} preparati"
            at_limit   = count >= max_prep
            color      = COLOR_ACCENT_CRIMSON if at_limit else COLOR_ACCENT_BLUE
            ratio      = min(1.0, count / max_prep) if max_prep > 0 else 0.0

        note = (
            "I trucchetti (0°) non contano nel limite  ·  ✎ per modificare manuale"
            if max_prep is not None
            else "Tocca ◉ per segnare un incantesimo come conosciuto"
        )

        rows: list[ft.Control] = [
            ft.Row([
                ft.Text(
                    label_text, size=18, color=color,
                    weight=ft.FontWeight.BOLD, font_family=FONT_MONO,
                    expand=True,
                ),
                ft.TextButton(
                    "✎",
                    on_click=lambda e: self._open_override_dialog(),
                    style=ft.ButtonStyle(color=COLOR_TEXT_MUTED),
                    tooltip="Modifica limite manualmente",
                ),
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=4),
        ]
        if max_prep is not None:
            rows.append(ft.Row([ft.ProgressBar(
                value=ratio,
                color=color,
                bgcolor=COLOR_BG_SECONDARY,
                height=8, border_radius=4, expand=True,
            )]))
        rows.append(ft.Text(note, size=10, color=COLOR_TEXT_MUTED, italic=True))

        return ft.Container(
            content=ft.Column(rows, spacing=6),
            bgcolor=COLOR_BG_CARD,
            padding=14,
            border=ft.Border(
                top=ft.BorderSide(3, color),
                left=ft.BorderSide(1, COLOR_BORDER),
                right=ft.BorderSide(1, COLOR_BORDER),
                bottom=ft.BorderSide(1, COLOR_BORDER),
            ),
            border_radius=6,
        )

    def _section_slots_summary(self, slots: list[SpellSlot]) -> ft.Container:
        rows: list[ft.Control] = []
        for slot in sorted(slots, key=lambda s: s.slot_level):
            avail = slot.total - slot.used
            circles = [
                ft.Text(
                    "●" if i < avail else "○",
                    size=20,
                    color=COLOR_SLOT_FULL if i < avail else COLOR_TEXT_MUTED,
                )
                for i in range(slot.total)
            ]
            rows.append(ft.Row(cast(list[ft.Control], [
                ft.Container(
                    content=ft.Text(_SLOT_NAMES[slot.slot_level - 1], size=12,
                                    color=COLOR_TEXT_SECONDARY,
                                    weight=ft.FontWeight.W_600),
                    width=28,
                ),
                ft.Row(cast(list[ft.Control], circles), spacing=2),
                ft.Container(expand=True),
                ft.Text(f"{avail}/{slot.total}", size=11,
                        color=COLOR_TEXT_MUTED, font_family=FONT_MONO),
            ]), vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=4))
        rows.append(ft.Text(
            "Usa / recupera slot nel tab Combattimento.",
            size=10, color=COLOR_TEXT_MUTED, italic=True,
        ))
        return ft.Container(
            content=ft.Column(rows, spacing=8),
            bgcolor=COLOR_BG_CARD,
            padding=14,
            border=ft.Border(
                top=ft.BorderSide(3, COLOR_ACCENT_BLUE),
                left=ft.BorderSide(1, COLOR_BORDER),
                right=ft.BorderSide(1, COLOR_BORDER),
                bottom=ft.BorderSide(1, COLOR_BORDER),
            ),
            border_radius=6,
        )

    def _section_spell_list(self, spells: list[dict]) -> ft.Container:
        """Lista incantesimi con toggle preparazione e link al dettaglio."""
        max_prep  = _calc_max_prepared(self.character)
        count     = self._prepared_count()
        at_limit  = (max_prep is not None) and (count >= max_prep)

        rows: list[ft.Control] = []
        sorted_spells = sorted(spells, key=lambda s: s.get("name", ""))
        for i, sp in enumerate(sorted_spells):
            name     = sp.get("name", "")
            level    = sp.get("level", 0)
            prepared = self._is_prepared(name, level)
            conc     = "◉" if sp.get("concentration") else ""
            ritual   = "☽" if sp.get("ritual") else ""
            tags     = f"  {conc}{ritual}".rstrip() if (conc or ritual) else ""

            # Blocca il toggle solo per incantesimi non preparati di lv ≥ 1 quando al limite
            blocked = at_limit and not prepared and level > 0

            toggle_icon  = "◉" if prepared else ("✕" if blocked else "○")
            toggle_color = (
                COLOR_ACCENT_CRIMSON if prepared
                else (COLOR_BORDER if blocked else COLOR_TEXT_MUTED)
            )

            row = ft.Container(
                content=ft.Row([
                    ft.Container(
                        content=ft.Text(toggle_icon, size=22, color=toggle_color),
                        on_click=(lambda e, s=sp: self._toggle_prepared(s))
                        if not blocked else None,
                        tooltip=(
                            "Rimuovi dalla preparazione" if prepared
                            else ("Limite raggiunto" if blocked else "Prepara")
                        ),
                        border_radius=14,
                        ink=not blocked,
                        padding=ft.Padding.all(2),
                        width=32,
                    ),
                    ft.Container(width=6),
                    ft.Container(
                        content=ft.Row([
                            ft.Text(
                                name, size=13, expand=True,
                                color=(
                                    COLOR_TEXT_PRIMARY if prepared
                                    else (COLOR_TEXT_MUTED if blocked
                                          else COLOR_TEXT_SECONDARY)
                                ),
                                weight=(
                                    ft.FontWeight.W_600 if prepared
                                    else ft.FontWeight.NORMAL
                                ),
                            ),
                            ft.Text(tags, size=11, color=COLOR_ACCENT_AMBER)
                            if tags else ft.Container(width=0),
                            ft.Icon(ft.Icons.CHEVRON_RIGHT, size=14,
                                    color=COLOR_TEXT_MUTED),
                        ], spacing=4,
                           vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        on_click=lambda e, s=sp: self._open_spell_dialog(s),
                        expand=True, ink=True, border_radius=4,
                        padding=ft.Padding.symmetric(vertical=6, horizontal=4),
                        tooltip="Dettagli",
                    ),
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=0),
                border=ft.Border(
                    bottom=ft.BorderSide(1, COLOR_BORDER)
                    if i < len(sorted_spells) - 1
                    else ft.BorderSide(0, "transparent"),
                ),
            )
            rows.append(row)

        return ft.Container(
            content=ft.Column(rows, spacing=0),
            bgcolor=COLOR_BG_CARD,
            padding=ft.Padding.symmetric(horizontal=14, vertical=8),
            border=ft.Border(
                top=ft.BorderSide(3, COLOR_ACCENT_CRIMSON),
                left=ft.BorderSide(1, COLOR_BORDER),
                right=ft.BorderSide(1, COLOR_BORDER),
                bottom=ft.BorderSide(1, COLOR_BORDER),
            ),
            border_radius=6,
        )

    def _section_extra_spell_list(self, spells: list[KnownSpell]) -> ft.Container:
        """
        Lista di incantesimi "extra" (Segreti Magici, Mistificatore, etc.)
        letti dal DB — mostra dettagli già salvati, permette apertura dialog.
        Non ha toggle preparazione: sono sempre "conosciuti".
        """
        rows: list[ft.Control] = []
        sorted_spells = sorted(spells, key=lambda s: s.name)
        for i, ks in enumerate(sorted_spells):
            origin_badge = ft.Container(
                content=ft.Text(
                    (ks.class_list or "?")[:4], size=9,
                    color="#ffffff", weight=ft.FontWeight.BOLD,
                ),
                bgcolor=COLOR_ACCENT_AMBER,
                padding=ft.Padding.symmetric(horizontal=5, vertical=2),
                border_radius=4,
                tooltip=f"Da: {ks.class_list or '—'}",
            )

            def _open(e, _ks: KnownSpell = ks) -> None:
                if not self._page:
                    return
                page = self._page
                rows_d: list[ft.Control] = [
                    ft.Text(
                        f"Lv{_ks.spell_level}  ·  {_ks.school or '—'}",
                        size=11, color=COLOR_TEXT_MUTED, italic=True,
                    ),
                    ft.Container(height=4),
                ]
                for label, val in [
                    ("Tempo:", _ks.casting_time),
                    ("Gittata:", _ks.spell_range),
                    ("Durata:", _ks.duration),
                    ("Componenti:", _ks.components),
                ]:
                    if val:
                        rows_d.append(ft.Row([
                            ft.Text(label, size=11, color=COLOR_TEXT_MUTED,
                                    weight=ft.FontWeight.BOLD, width=100),
                            ft.Text(val, size=12, color=COLOR_TEXT_PRIMARY, expand=True),
                        ], spacing=4))
                rows_d += [
                    ft.Divider(color=COLOR_BORDER),
                    ft.Text(
                        _ks.description or "Nessuna descrizione.",
                        size=13, color=COLOR_TEXT_PRIMARY, selectable=True,
                    ),
                ]
                if _ks.higher_levels:
                    rows_d += [
                        ft.Container(height=6),
                        ft.Text("Ai livelli superiori:", size=11,
                                color=COLOR_TEXT_MUTED, weight=ft.FontWeight.BOLD),
                        ft.Text(_ks.higher_levels, size=12, color=COLOR_TEXT_SECONDARY),
                    ]
                page.show_dialog(ft.AlertDialog(
                    title=ft.Row([
                        origin_badge,
                        ft.Container(width=8),
                        ft.Text(_ks.name, size=14, weight=ft.FontWeight.BOLD,
                                color=COLOR_TEXT_TITLE, expand=True),
                    ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    content=ft.Column(
                        rows_d, spacing=6, scroll=ft.ScrollMode.AUTO
                    ),
                    actions=[
                        ft.TextButton(
                            "Chiudi",
                            on_click=lambda e: page.pop_dialog() if page else None,
                        )
                    ],
                    bgcolor=COLOR_BG_CARD,
                ))

            rows.append(ft.Container(
                content=ft.Row([
                    ft.Text("★", size=18, color=COLOR_ACCENT_AMBER),
                    ft.Container(width=6),
                    ft.Container(
                        content=ft.Row([
                            ft.Text(
                                ks.name, size=13, expand=True,
                                color=COLOR_TEXT_PRIMARY,
                                weight=ft.FontWeight.W_600,
                            ),
                            origin_badge,
                            ft.Icon(ft.Icons.CHEVRON_RIGHT, size=14,
                                    color=COLOR_TEXT_MUTED),
                        ], spacing=6,
                           vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        on_click=_open,
                        expand=True, ink=True, border_radius=4,
                        padding=ft.Padding.symmetric(vertical=6, horizontal=4),
                    ),
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=0),
                border=ft.Border(
                    bottom=ft.BorderSide(1, COLOR_BORDER)
                    if i < len(sorted_spells) - 1
                    else ft.BorderSide(0, "transparent"),
                ),
            ))

        return ft.Container(
            content=ft.Column(rows, spacing=0),
            bgcolor=COLOR_BG_CARD,
            padding=ft.Padding.symmetric(horizontal=14, vertical=8),
            border=ft.Border(
                top=ft.BorderSide(3, COLOR_ACCENT_AMBER),
                left=ft.BorderSide(1, COLOR_BORDER),
                right=ft.BorderSide(1, COLOR_BORDER),
                bottom=ft.BorderSide(1, COLOR_BORDER),
            ),
            border_radius=6,
        )

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    def _refresh(self) -> None:
        refreshed = character_repo.get_by_id(self.character.id)
        if refreshed:
            self.character = refreshed
        self._slots = character_repo.get_spell_slots(self.character.id)
        self._reload_known()
        self._build()
        try:
            self.update()
        except RuntimeError:
            pass
