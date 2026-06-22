"""
Container principale della scheda personaggio.

Struttura:
    MiniStatBar  — 6 caratteristiche fisse in cima, sempre visibili
    TabBar       — Profilo | Combattimento | Esplorazione | Inventario | Diario
    Content area — contenuto del tab attivo

Input:  Character + list[CharacterProficiency]
Output: ft.Column che occupa tutta l'area disponibile
"""

import flet as ft
import logging
from typing import cast
from config.settings import *
from data.models import Character, CharacterProficiency
from ui.theme import title_text, muted_text

logger = logging.getLogger(__name__)

SHEET_TABS = [
    {"key": "profilo",       "label": "Profilo"},
    {"key": "combattimento", "label": "Combattimento"},
    {"key": "esplorazione",  "label": "Esplorazione"},
    {"key": "inventario",    "label": "Inventario"},
    {"key": "diario",        "label": "Diario"},
]


class SheetView(ft.Column):
    """
    Vista principale della scheda personaggio.
    Gestisce la mini stat bar fissa e il routing tra i 5 tab.
    """

    def __init__(self, character: Character, proficiencies: list[CharacterProficiency]):
        super().__init__(expand=True, spacing=0)
        self.character = character
        self.proficiencies = proficiencies
        self.active_tab = "profilo"
        self._tab_buttons: dict[str, ft.Container] = {}
        self._build()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self):
        self.content_container = ft.Container(
            expand=True,
            content=self._get_tab_content("profilo"),
        )

        self.controls = [
            self._build_stat_bar(),
            self._build_header_and_tabs(),
            self.content_container,
        ]

    # ------------------------------------------------------------------
    # Mini stat bar
    # ------------------------------------------------------------------

    def _build_stat_bar(self) -> ft.Container:
        boxes = []
        for abbr, key in zip(ABILITY_ABBR, ABILITY_KEYS):
            score = getattr(self.character, f"{key}_score")
            mod = get_modifier(score)
            mod_str = f"+{mod}" if mod >= 0 else str(mod)
            boxes.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text(abbr, size=9, color=COLOR_TEXT_SECONDARY,
                                    weight=ft.FontWeight.BOLD,
                                    text_align=ft.TextAlign.CENTER),
                            ft.Text(str(score), size=17, color=COLOR_TEXT_PRIMARY,
                                    weight=ft.FontWeight.BOLD,
                                    text_align=ft.TextAlign.CENTER,
                                    font_family=FONT_MONO),
                            ft.Text(mod_str, size=11, color=COLOR_ACCENT_GOLD,
                                    weight=ft.FontWeight.BOLD,
                                    text_align=ft.TextAlign.CENTER),
                        ],
                        spacing=1,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.Padding.symmetric(vertical=6, horizontal=10),
                    bgcolor=COLOR_BG_CARD,
                    border=ft.Border.all(1, COLOR_BORDER),
                    border_radius=4,
                    expand=True,
                )
            )

        return ft.Container(
            content=ft.Row(boxes, spacing=6, expand=True),
            padding=ft.Padding.symmetric(horizontal=12, vertical=8),
            bgcolor=COLOR_BG_SECONDARY,
            border=ft.Border.only(bottom=ft.BorderSide(1, COLOR_BORDER)),
        )

    # ------------------------------------------------------------------
    # Header personaggio + tab bar
    # ------------------------------------------------------------------

    def _build_header_and_tabs(self) -> ft.Container:
        c = self.character
        prof_bonus = get_proficiency_bonus(c.level)

        name_row = ft.Row(
            [
                ft.Text(c.name, size=15, weight=ft.FontWeight.BOLD,
                        color=COLOR_TEXT_TITLE, font_family=FONT_TITLE, expand=True),
                ft.Text(f"+{prof_bonus} comp.", size=11, color=COLOR_TEXT_SECONDARY),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        subtitle = ft.Text(
            f"Lv.{c.level} {c.class_name}"
            + (f" ({c.subclass})" if c.subclass else "")
            + f"  •  {c.race}"
            + (f" ({c.subrace})" if c.subrace else ""),
            size=11,
            color=COLOR_TEXT_SECONDARY,
        )

        # Tab buttons
        tab_row = []
        for tab in SHEET_TABS:
            btn = self._make_tab_button(tab["key"], tab["label"])
            self._tab_buttons[tab["key"]] = btn
            tab_row.append(btn)

        return ft.Container(
            content=ft.Column(
                [
                    ft.Container(
                        content=ft.Column([name_row, subtitle], spacing=2),
                        padding=ft.Padding.only(left=16, right=16, top=8, bottom=6),
                    ),
                    ft.Container(
                        content=ft.Row(tab_row, spacing=0),
                        border=ft.Border.only(top=ft.BorderSide(1, COLOR_BORDER)),
                    ),
                ],
                spacing=0,
            ),
            bgcolor=COLOR_BG_SECONDARY,
            border=ft.Border.only(bottom=ft.BorderSide(1, COLOR_BORDER_ACCENT)),
        )

    def _make_tab_button(self, key: str, label: str) -> ft.Container:
        is_active = key == self.active_tab
        return ft.Container(
            content=ft.Text(
                label,
                size=12,
                color=COLOR_ACCENT_CRIMSON if is_active else COLOR_TEXT_SECONDARY,
                weight=ft.FontWeight.BOLD if is_active else ft.FontWeight.NORMAL,
                text_align=ft.TextAlign.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=14, vertical=9),
            bgcolor=COLOR_BG_TAB_ACTIVE if is_active else COLOR_BG_TAB_INACTIVE,
            border=ft.Border.only(
                bottom=ft.BorderSide(2, COLOR_ACCENT_CRIMSON if is_active else "transparent")
            ),
            on_click=lambda e, k=key: self._switch_tab(k),
            ink=True,
        )

    # ------------------------------------------------------------------
    # Navigazione tra tab
    # ------------------------------------------------------------------

    def _switch_tab(self, key: str):
        if key == self.active_tab:
            return
        self.active_tab = key

        # Aggiorna stile bottoni
        for k, btn in self._tab_buttons.items():
            active = k == key
            label = cast(ft.Text, btn.content)
            label.color = COLOR_ACCENT_CRIMSON if active else COLOR_TEXT_SECONDARY
            label.weight = ft.FontWeight.BOLD if active else ft.FontWeight.NORMAL
            btn.bgcolor = COLOR_BG_TAB_ACTIVE if active else COLOR_BG_TAB_INACTIVE
            btn.border = ft.Border.only(
                bottom=ft.BorderSide(2, COLOR_ACCENT_CRIMSON if active else "transparent")
            )

        self.content_container.content = self._get_tab_content(key)
        self.update()

    # ------------------------------------------------------------------
    # Contenuto tab
    # ------------------------------------------------------------------

    def _get_tab_content(self, key: str) -> ft.Control:
        if key == "profilo":
            from ui.views.character_sheet.profilo_tab import ProfiloTab
            return ProfiloTab(self.character, self.proficiencies)
        if key == "combattimento":
            from ui.views.character_sheet.combattimento_tab import CombattimentoTab
            return CombattimentoTab(self.character)
        if key == "esplorazione":
            from ui.views.character_sheet.esplorazione_tab import EsplorazioneTab
            return EsplorazioneTab(self.character)
        if key == "inventario":
            from ui.views.character_sheet.inventario_tab import InventarioTab
            return InventarioTab(self.character)
        if key == "diario":
            from ui.views.character_sheet.diario_tab import DiarioTab
            return DiarioTab(self.character)
        return self._placeholder_tab(key)

    def _placeholder_tab(self, key: str) -> ft.Container:
        labels = {
            "combattimento": ("Combattimento", ft.Icons.SHIELD),
            "esplorazione":  ("Esplorazione",  ft.Icons.EXPLORE),
            "inventario":    ("Inventario",     ft.Icons.BACKPACK),
            "diario":        ("Diario",         ft.Icons.MENU_BOOK),
        }
        label, icon = labels.get(key, (key, ft.Icons.BUILD))
        return ft.Container(
            expand=True,
            content=ft.Column(
                [
                    ft.Icon(icon, size=52, color=COLOR_BORDER),
                    ft.Container(height=12),
                    ft.Text(label, size=20, color=COLOR_TEXT_MUTED),
                    ft.Container(height=8),
                    ft.Text("In sviluppo...", size=13, color=COLOR_TEXT_MUTED),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                expand=True,
            ),
        )
