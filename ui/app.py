"""
Root dell'applicazione Flet.
Gestisce la navigazione principale tra le sezioni e lo stato globale.

Flusso:
    Avvio → Home (selezione personaggi)
        ├─► Seleziona personaggio → MainLayout (navbar + sezioni)
        ├─► Crea wizard          → [TODO] WizardView → MainLayout
        └─► Crea manuale         → ManualCreationForm → MainLayout
"""

import flet as ft
import logging
from config.settings import *
from ui.theme import get_theme, title_text, muted_text

logger = logging.getLogger(__name__)

SECTIONS = [
    {"key": "sheet",     "label": "Scheda",      "icon_off": ft.Icons.PERSON_OUTLINE,       "icon_on": ft.Icons.PERSON},
    {"key": "spells",    "label": "Incantesimi", "icon_off": ft.Icons.AUTO_AWESOME_OUTLINED, "icon_on": ft.Icons.AUTO_AWESOME},
    {"key": "diary",     "label": "Diario",      "icon_off": ft.Icons.MENU_BOOK_OUTLINED,    "icon_on": ft.Icons.MENU_BOOK},
    {"key": "maps",      "label": "Mappe",       "icon_off": ft.Icons.MAP_OUTLINED,          "icon_on": ft.Icons.MAP},
    {"key": "dice",      "label": "Dadi",        "icon_off": ft.Icons.CASINO_OUTLINED,       "icon_on": ft.Icons.CASINO},
]


class DnDApp:
    """Controller principale: gestisce routing tra Home, form e scheda."""

    def __init__(self, page: ft.Page):
        self.page = page
        self.current_character_id: str | None = None
        self.active_section: str = "sheet"

        self._setup_page()
        self._show_home()

    # ------------------------------------------------------------------
    # Setup pagina
    # ------------------------------------------------------------------

    def _setup_page(self):
        self.page.title = APP_NAME
        self.page.theme = get_theme()
        self.page.bgcolor = COLOR_BG_PRIMARY
        self.page.padding = 0

    # ------------------------------------------------------------------
    # Routing di primo livello
    # ------------------------------------------------------------------

    def _show_home(self):
        """Mostra la schermata di selezione/creazione personaggi."""
        from ui.views.home_view import HomeView
        self.page.controls.clear()
        home = HomeView(
            on_select=self._on_character_selected,
            on_create_wizard=self._show_wizard,
            on_create_manual=self._show_manual_form,
        )
        self.page.add(home)
        self.page.update()

    def _show_manual_form(self):
        """Mostra il form di creazione manuale."""
        from ui.views.creation_wizard.manual_form import ManualCreationForm
        self.page.controls.clear()
        form = ManualCreationForm(
            on_complete=self._on_character_selected,
            on_cancel=self._show_home,
        )
        self.page.add(form)
        self.page.update()

    def _show_wizard(self):
        """Avvia il wizard guidato."""
        from ui.views.creation_wizard.wizard_view import WizardView
        self.page.controls.clear()
        wizard = WizardView(
            on_complete=self._on_character_selected,
            on_cancel=self._show_home,
        )
        self.page.add(wizard)
        self.page.update()

    def _on_character_selected(self, character_id: str):
        """Carica la scheda del personaggio selezionato."""
        self.current_character_id = character_id
        self._show_main_layout()

    # ------------------------------------------------------------------
    # Layout principale (navbar + sezioni)
    # ------------------------------------------------------------------

    def _show_main_layout(self):
        """Mostra il layout con navbar laterale e area contenuto."""
        self.page.controls.clear()

        self.nav_rail = self._build_nav_rail()
        self.content_area = ft.Container(
            expand=True,
            bgcolor=COLOR_BG_PRIMARY,
            content=self._get_section_view(self.active_section),
        )

        self.page.add(
            ft.Row(
                controls=[
                    self.nav_rail,
                    ft.VerticalDivider(width=1, color=COLOR_BORDER),
                    self.content_area,
                ],
                expand=True,
                spacing=0,
                vertical_alignment=ft.CrossAxisAlignment.STRETCH,
            )
        )
        self.page.update()

    def _build_nav_rail(self) -> ft.NavigationRail:
        destinations = [
            ft.NavigationRailDestination(
                icon=s["icon_off"],
                selected_icon=s["icon_on"],
                label=s["label"],
            )
            for s in SECTIONS
        ]

        # Tasto "Cambia personaggio" nel footer della navbar
        switch_btn = ft.Container(
            content=ft.Column(
                [
                    ft.Container(height=8),
                    ft.IconButton(
                        icon=ft.Icons.SWAP_HORIZ,
                        icon_color=COLOR_TEXT_SECONDARY,
                        tooltip="Cambia personaggio",
                        on_click=lambda e: self._show_home(),
                    ),
                    ft.Text(
                        "Cambia",
                        size=10,
                        color=COLOR_TEXT_MUTED,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.Container(height=8),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=2,
            ),
        )

        return ft.NavigationRail(
            selected_index=list(s["key"] for s in SECTIONS).index(self.active_section),
            destinations=destinations,
            on_change=self._on_nav_change,
            bgcolor=COLOR_BG_SECONDARY,
            indicator_color=COLOR_ACCENT_GOLD,
            indicator_shape=ft.RoundedRectangleBorder(radius=4),
            label_type=ft.NavigationRailLabelType.ALL,
            leading=ft.Container(
                content=ft.Column(
                    [
                        ft.Container(height=8),
                        ft.Icon(ft.Icons.SHIELD, color=COLOR_ACCENT_GOLD, size=32),
                        ft.Text(
                            "D&D",
                            size=11,
                            weight=ft.FontWeight.BOLD,
                            color=COLOR_ACCENT_GOLD,
                            text_align=ft.TextAlign.CENTER,
                        ),
                        ft.Container(height=8),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=2,
                ),
            ),
            trailing=switch_btn,
        )

    def _on_nav_change(self, e):
        index = e.control.selected_index
        self.active_section = SECTIONS[index]["key"]
        self.content_area.content = self._get_section_view(self.active_section)
        self.page.update()

    # ------------------------------------------------------------------
    # Routing sezioni interne
    # ------------------------------------------------------------------

    def _get_section_view(self, key: str) -> ft.Control:
        if key == "sheet":
            return self._placeholder_view("Scheda Personaggio", ft.Icons.PERSON, "In sviluppo...")
        elif key == "spells":
            return self._placeholder_view("Incantesimi", ft.Icons.AUTO_AWESOME, "In sviluppo...")
        elif key == "diary":
            return self._placeholder_view("Diario", ft.Icons.MENU_BOOK, "In sviluppo...")
        elif key == "maps":
            return self._placeholder_view("Mappe", ft.Icons.MAP, "In sviluppo...")
        elif key == "dice":
            return self._placeholder_view("Dadi", ft.Icons.CASINO, "In sviluppo...")
        return ft.Container()

    def _placeholder_view(self, title: str, icon, subtitle: str) -> ft.Container:
        return ft.Container(
            expand=True,
            bgcolor=COLOR_BG_PRIMARY,
            content=ft.Column(
                [
                    ft.Icon(icon, size=64, color=COLOR_BORDER),
                    ft.Container(height=16),
                    title_text(title, size=24),
                    ft.Container(height=8),
                    muted_text(subtitle, size=14),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                expand=True,
            ),
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_app(page: ft.Page):
    DnDApp(page)
