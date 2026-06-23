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
from typing import Any
from config.settings import *
from ui.theme import get_theme, title_text, muted_text

logger = logging.getLogger(__name__)


def _data_uri(b64: str) -> str:
    """Data URI da base64 con rilevamento formato (Flet 0.85.3 non ha src_base64)."""
    try:
        import base64 as _b64
        h = _b64.b64decode(b64[:16] + "==")
        if h[:3] == b"\xff\xd8\xff":
            mime = "image/jpeg"
        elif h[:8] == b"\x89PNG\r\n\x1a\n":
            mime = "image/png"
        else:
            mime = "image/jpeg"
    except Exception:
        mime = "image/jpeg"
    return f"data:{mime};base64,{b64}"


SECTIONS: list[dict[str, Any]] = [
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
        self.page.theme_mode = ft.ThemeMode.LIGHT   # tema marmo chiaro
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

    def _build_char_avatar(self) -> ft.Control:
        """Icona del personaggio corrente per la sidebar."""
        from data.repositories import character_repo
        char = character_repo.get_by_id(self.current_character_id) if self.current_character_id else None

        if char and char.image_data:
            return ft.Container(
                content=ft.Image(
                    src=_data_uri(char.image_data),
                    width=56, height=56,
                    fit=ft.BoxFit.COVER,
                ),
                width=56, height=56,
                border_radius=28,
                clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                border=ft.Border.all(2, COLOR_ACCENT_CRIMSON),
            )

        # Placeholder: scudo con iniziali
        initials = ""
        if char and char.name:
            parts = char.name.strip().split()
            initials = (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper()
        if not initials:
            initials = "?"

        return ft.Container(
            content=ft.Text(
                initials, size=18, weight=ft.FontWeight.BOLD,
                color="#ffffff", text_align=ft.TextAlign.CENTER,
            ),
            width=56, height=56,
            bgcolor="#3a1010",
            border=ft.Border.all(2, COLOR_ACCENT_CRIMSON),
            border_radius=28,
            alignment=ft.Alignment.CENTER,
        )

    def _build_nav_rail(self) -> ft.Container:
        """
        Sidebar custom (Column) invece di NavigationRail — controllo totale sui colori.
        Sfondo scuro COLOR_NAV_BG, icone e testo bianchi/grigi.
        """

        char_avatar = self._build_char_avatar()

        nav_items = []
        for s in SECTIONS:
            is_sel = s["key"] == self.active_section
            nav_items.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Icon(
                                s["icon_on"] if is_sel else s["icon_off"],
                                color="#ffffff" if is_sel else "#9a8888",
                                size=22,
                            ),
                            ft.Text(
                                s["label"], size=10,
                                color="#ffffff" if is_sel else "#9a8888",
                                text_align=ft.TextAlign.CENTER,
                                weight=ft.FontWeight.BOLD if is_sel else ft.FontWeight.NORMAL,
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=3,
                    ),
                    padding=ft.Padding.symmetric(horizontal=6, vertical=10),
                    bgcolor=COLOR_ACCENT_CRIMSON if is_sel else "transparent",
                    border_radius=8,
                    width=80,
                    on_click=lambda e, k=s["key"]: self._on_nav_click(k),
                    ink=True,
                )
            )

        switch_btn = ft.Container(
            content=ft.Column(
                [
                    ft.Icon(ft.Icons.SWAP_HORIZ, color="#9a8888", size=22),
                    ft.Text("Cambia", size=10, color="#9a8888",
                            text_align=ft.TextAlign.CENTER),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=3,
            ),
            padding=ft.Padding.symmetric(horizontal=6, vertical=10),
            border_radius=8,
            width=80,
            on_click=lambda e: self._show_home(),
            ink=True,
        )

        sidebar_col = ft.Column(
            [
                ft.Container(height=14),
                char_avatar,
                ft.Container(height=10),
                ft.Divider(color="#3a2828", height=1),
                ft.Container(height=4),
                *nav_items,
                ft.Container(expand=True),   # spazio flessibile
                ft.Divider(color="#3a2828", height=1),
                switch_btn,
                ft.Container(height=8),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=2,
            expand=True,
        )

        return ft.Container(
            content=sidebar_col,
            bgcolor=COLOR_NAV_BG,
            width=82,
        )

    def _on_nav_click(self, key: str):
        if key == self.active_section:
            return
        self.active_section = key
        # Ricostruisce il contenuto della sidebar per aggiornare lo stile selezionato
        self.nav_rail.content = self._build_nav_rail().content
        self.content_area.content = self._get_section_view(key)
        self.page.update()

    # ------------------------------------------------------------------
    # Routing sezioni interne
    # ------------------------------------------------------------------

    def _get_section_view(self, key: str) -> ft.Control:
        if key == "sheet":
            from data.repositories import character_repo
            from ui.views.character_sheet.sheet_view import SheetView
            if not self.current_character_id:
                return self._placeholder_view("Personaggio non trovato", ft.Icons.ERROR_OUTLINE, "")
            char = character_repo.get_by_id(self.current_character_id)
            profs = character_repo.get_proficiencies(self.current_character_id)
            if char:
                return SheetView(char, profs)
            return self._placeholder_view("Personaggio non trovato", ft.Icons.ERROR_OUTLINE, "")
        elif key == "spells":
            return self._placeholder_view("Incantesimi", ft.Icons.AUTO_AWESOME, "In sviluppo...")
        elif key == "diary":
            return self._placeholder_view("Diario", ft.Icons.MENU_BOOK, "In sviluppo...")
        elif key == "maps":
            from data.repositories import character_repo
            from ui.views.maps_view import MapsView
            if not self.current_character_id:
                return self._placeholder_view("Mappe", ft.Icons.MAP, "")
            char = character_repo.get_by_id(self.current_character_id)
            if char:
                return MapsView(char)
            return self._placeholder_view("Mappe", ft.Icons.MAP, "")
        elif key == "dice":
            from ui.views.dice_view import DiceView
            return DiceView()
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
