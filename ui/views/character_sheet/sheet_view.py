"""
Container principale della scheda personaggio.

Struttura:
    MiniStatBar  — 6 caratteristiche fisse in cima (cliccabili per modifica)
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
from ui.theme import show_error_dialog
import data.repositories.character_repo as character_repo

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
        self._page: ft.Page | None = None
        self._stat_bar_container: ft.Container | None = None
        self._header_container: ft.Container | None = None
        self._build()

    def did_mount(self):
        self._page = cast(ft.Page, self.page)

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self):
        self._stat_bar_container = self._build_stat_bar()
        self._header_container = self._build_header_and_tabs()
        self.content_container = ft.Container(
            expand=True,
            content=self._get_tab_content("profilo"),
        )

        self.controls = [
            self._stat_bar_container,
            self._header_container,
            self.content_container,
        ]

    # ------------------------------------------------------------------
    # Mini stat bar — cliccabile per editare le caratteristiche
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
                    on_click=lambda e: self._open_ability_score_dialog(),
                    ink=True,
                    tooltip="Clicca per modificare le caratteristiche",
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
        pb = char_prof_bonus(c)
        is_override = (c.proficiency_bonus_override or 0) > 0

        # Testo bonus competenza — cliccabile per override
        pb_label = ft.Text(
            f"+{pb} comp." + (" ✎" if is_override else ""),
            size=11,
            color=COLOR_ACCENT_BLUE if is_override else COLOR_TEXT_SECONDARY,
            weight=ft.FontWeight.BOLD if is_override else ft.FontWeight.NORMAL,
        )
        pb_btn = ft.Container(
            content=pb_label,
            on_click=lambda e: self._open_prof_bonus_dialog(),
            ink=True,
            border_radius=4,
            padding=ft.Padding.symmetric(horizontal=4, vertical=2),
            tooltip="Clicca per modificare il bonus competenza",
        )

        name_row = ft.Row(
            [
                ft.Text(c.name, size=15, weight=ft.FontWeight.BOLD,
                        color=COLOR_TEXT_TITLE, font_family=FONT_TITLE, expand=True),
                pb_btn,
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
        self._tab_buttons = {}
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
                size=11,
                color=COLOR_ACCENT_CRIMSON if is_active else COLOR_TEXT_SECONDARY,
                weight=ft.FontWeight.BOLD if is_active else ft.FontWeight.NORMAL,
                text_align=ft.TextAlign.CENTER,
                no_wrap=True,
            ),
            padding=ft.Padding.symmetric(horizontal=6, vertical=9),
            bgcolor=COLOR_BG_TAB_ACTIVE if is_active else COLOR_BG_TAB_INACTIVE,
            border=ft.Border.only(
                bottom=ft.BorderSide(2, COLOR_ACCENT_CRIMSON if is_active else "transparent")
            ),
            on_click=lambda e, k=key: self._switch_tab(k),
            ink=True,
            expand=True,
            alignment=ft.Alignment.CENTER,
        )

    # ------------------------------------------------------------------
    # Dialog — modifica caratteristiche
    # ------------------------------------------------------------------

    def _open_ability_score_dialog(self):
        page = self._page
        if page is None:
            return
        c = self.character

        fields: dict[str, ft.TextField] = {}
        for key, name, abbr in zip(ABILITY_KEYS, ABILITY_SCORES, ABILITY_ABBR):
            score = getattr(c, f"{key}_score", 10)
            fields[key] = ft.TextField(
                label=f"{name} ({abbr})",
                value=str(score),
                keyboard_type=ft.KeyboardType.NUMBER,
                text_style=ft.TextStyle(size=13, color=COLOR_TEXT_PRIMARY),
                border_color=COLOR_BORDER,
                focused_border_color=COLOR_ACCENT_BLUE,
                bgcolor=COLOR_BG_CARD,
                label_style=ft.TextStyle(color=COLOR_TEXT_SECONDARY),
                expand=True,
            )

        error_text = ft.Text("", size=11, color=COLOR_ACCENT_CRIMSON)

        def on_save(ev):
            if page is None:
                return
            new_vals: dict[str, int] = {}
            for key in ABILITY_KEYS:
                try:
                    val = int((fields[key].value or "").strip())
                    if not (1 <= val <= 30):
                        raise ValueError
                    new_vals[key] = val
                except ValueError:
                    idx = ABILITY_KEYS.index(key)
                    error_text.value = (
                        f"Valore non valido per {ABILITY_SCORES[idx]} "
                        f"({ABILITY_ABBR[idx]}) — inserire un numero tra 1 e 30"
                    )
                    error_text.update()
                    return
            for key, val in new_vals.items():
                setattr(c, f"{key}_score", val)
            if not character_repo.update(c):
                show_error_dialog(page)
                return
            page.pop_dialog()
            self._refresh_all()

        dlg = ft.AlertDialog(
            title=ft.Text("Modifica Caratteristiche", size=14,
                          weight=ft.FontWeight.BOLD, color=COLOR_TEXT_TITLE),
            content=ft.Column(
                [
                    ft.Text(
                        "Valori ammessi: 1–30  (house rules: nessun limite a 20)",
                        size=11, color=COLOR_TEXT_MUTED,
                    ),
                    ft.Container(height=4),
                    ft.Row([fields["str"], fields["dex"], fields["con"]], spacing=10),
                    ft.Row([fields["int"], fields["wis"], fields["cha"]], spacing=10),
                    error_text,
                ],
                spacing=10,
            ),
            actions=[
                ft.TextButton("Annulla",
                              on_click=lambda ev: page.pop_dialog() if page else None),
                ft.ElevatedButton(
                    "Salva",
                    on_click=on_save,
                    style=ft.ButtonStyle(
                        bgcolor=COLOR_ACCENT_CRIMSON, color="#ffffff",
                        shape=ft.RoundedRectangleBorder(radius=4),
                    ),
                ),
            ],
            bgcolor=COLOR_BG_CARD,
        )
        page.show_dialog(dlg)

    # ------------------------------------------------------------------
    # Dialog — override bonus competenza
    # ------------------------------------------------------------------

    def _open_prof_bonus_dialog(self):
        page = self._page
        if page is None:
            return
        c = self.character
        standard_pb = get_proficiency_bonus(c.level)
        current_override = c.proficiency_bonus_override or 0

        tf = ft.TextField(
            label="Bonus competenza personalizzato",
            value=str(current_override) if current_override > 0 else "",
            hint_text=f"Standard PHB: +{standard_pb}",
            keyboard_type=ft.KeyboardType.NUMBER,
            text_style=ft.TextStyle(size=13, color=COLOR_TEXT_PRIMARY),
            border_color=COLOR_BORDER,
            focused_border_color=COLOR_ACCENT_BLUE,
            bgcolor=COLOR_BG_CARD,
            label_style=ft.TextStyle(color=COLOR_TEXT_SECONDARY),
            width=280,
        )
        error_text = ft.Text("", size=11, color=COLOR_ACCENT_CRIMSON)

        def on_save(ev):
            if page is None:
                return
            raw = (tf.value or "").strip()
            if raw == "":
                # Reset a standard PHB
                c.proficiency_bonus_override = 0
            else:
                try:
                    val = int(raw)
                    if not (1 <= val <= 20):
                        raise ValueError
                    c.proficiency_bonus_override = val
                except ValueError:
                    error_text.value = "Inserire un numero tra 1 e 20 (o lasciare vuoto per standard PHB)"
                    error_text.update()
                    return
            if not character_repo.update(c):
                show_error_dialog(page)
                return
            page.pop_dialog()
            self._refresh_all()

        def on_reset_phb(ev):
            if page is None:
                return
            c.proficiency_bonus_override = 0
            if not character_repo.update(c):
                show_error_dialog(page)
                return
            page.pop_dialog()
            self._refresh_all()

        dlg = ft.AlertDialog(
            title=ft.Text("Bonus Competenza", size=14,
                          weight=ft.FontWeight.BOLD, color=COLOR_TEXT_TITLE),
            content=ft.Column(
                [
                    ft.Text(
                        f"Standard PHB per Lv.{c.level}: +{standard_pb}",
                        size=12, color=COLOR_TEXT_SECONDARY,
                    ),
                    ft.Text(
                        "Lascia vuoto per usare la tabella PHB standard. "
                        "Imposta un valore diverso per house rules.",
                        size=11, color=COLOR_TEXT_MUTED,
                    ),
                    ft.Container(height=4),
                    tf,
                    error_text,
                ],
                spacing=8,
            ),
            actions=[
                ft.TextButton("Annulla",
                              on_click=lambda ev: page.pop_dialog() if page else None),
                ft.TextButton(
                    "Reset PHB",
                    on_click=on_reset_phb,
                    style=ft.ButtonStyle(color=COLOR_TEXT_MUTED),
                ),
                ft.ElevatedButton(
                    "Salva",
                    on_click=on_save,
                    style=ft.ButtonStyle(
                        bgcolor=COLOR_ACCENT_CRIMSON, color="#ffffff",
                        shape=ft.RoundedRectangleBorder(radius=4),
                    ),
                ),
            ],
            bgcolor=COLOR_BG_CARD,
        )
        page.show_dialog(dlg)

    # ------------------------------------------------------------------
    # Refresh globale (dopo modifica caratteristiche o bonus competenza)
    # ------------------------------------------------------------------

    def _refresh_bar_and_header(self):
        """
        Ricarica il personaggio dal DB e aggiorna SOLO stat bar e header.
        Chiamato dai tab dopo il loro self-refresh, per tenere la top bar
        sincronizzata senza ricostruire il contenuto del tab.
        """
        updated = character_repo.get_by_id(self.character.id)
        if updated:
            self.character = updated
        self.proficiencies = character_repo.get_proficiencies(self.character.id)

        new_bar = self._build_stat_bar()
        new_hdr = self._build_header_and_tabs()
        self.controls[0] = new_bar
        self.controls[1] = new_hdr
        self._stat_bar_container = new_bar
        self._header_container = new_hdr

        try:
            self.update()
        except RuntimeError:
            pass

    def _refresh_all(self):
        """
        Ricarica il personaggio dal DB, aggiorna la stat bar, l'header
        e ricostruisce il tab corrente (che mostra valori derivati).
        Usato dai dialog interni a SheetView (modifica caratteristiche,
        bonus competenza).
        """
        self._refresh_bar_and_header()

        # Ricostruisce il tab corrente
        self.content_container.content = self._get_tab_content(self.active_tab)

        try:
            self.update()
        except RuntimeError:
            pass

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
        cb = self._refresh_bar_and_header
        if key == "profilo":
            from ui.views.character_sheet.profilo_tab import ProfiloTab
            return ProfiloTab(self.character, self.proficiencies, on_refresh=cb)
        if key == "combattimento":
            from ui.views.character_sheet.combattimento_tab import CombattimentoTab
            return CombattimentoTab(self.character, on_refresh=cb)
        if key == "esplorazione":
            from ui.views.character_sheet.esplorazione_tab import EsplorazioneTab
            return EsplorazioneTab(self.character, on_refresh=cb)
        if key == "inventario":
            from ui.views.character_sheet.inventario_tab import InventarioTab
            return InventarioTab(self.character, on_refresh=cb)
        if key == "diario":
            from ui.views.character_sheet.diario_tab import DiarioTab
            return DiarioTab(self.character, on_refresh=cb)
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
