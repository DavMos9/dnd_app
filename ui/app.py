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
import threading
import webbrowser
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
    {"key": "sheet",     "label": "Scheda",      "icon_off": ft.Icons.PERSON_OUTLINE,        "icon_on": ft.Icons.PERSON},
    {"key": "spells",    "label": "Incantesimi", "icon_off": ft.Icons.AUTO_AWESOME_OUTLINED,  "icon_on": ft.Icons.AUTO_AWESOME},
    {"key": "diary",     "label": "Diario",      "icon_off": ft.Icons.MENU_BOOK_OUTLINED,     "icon_on": ft.Icons.MENU_BOOK},
    {"key": "maps",      "label": "Mappe",       "icon_off": ft.Icons.MAP_OUTLINED,           "icon_on": ft.Icons.MAP},
    {"key": "feats",     "label": "Talenti",     "icon_off": ft.Icons.MILITARY_TECH_OUTLINED, "icon_on": ft.Icons.MILITARY_TECH},
    {"key": "dice",      "label": "Dadi",        "icon_off": ft.Icons.CASINO_OUTLINED,        "icon_on": ft.Icons.CASINO},
]


class DnDApp:
    """Controller principale: gestisce routing tra Home, form e scheda."""

    _MOBILE_BP = 600   # px sotto cui si usa la bottom navigation

    def __init__(self, page: ft.Page):
        self.page = page
        self.current_character_id: str | None = None
        self.active_section: str = "sheet"
        self._mobile: bool = False

        self._setup_page()
        self._show_home()
        self._start_update_check()

    def _is_mobile(self) -> bool:
        return (self.page.width or 0) < self._MOBILE_BP

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

    def _stop_home_polling(self):
        """Ferma il polling della HomeView se attivo."""
        hv = getattr(self, "_home_view", None)
        if hv is not None:
            hv.stop_polling()
            self._home_view = None

    def _show_home(self):
        """Mostra la schermata di selezione/creazione personaggi."""
        from ui.views.home_view import HomeView
        self._stop_home_polling()
        self.page.controls.clear()
        home = HomeView(
            on_select=self._on_character_selected,
            on_create_wizard=self._show_wizard,
            on_create_manual=self._show_manual_form,
        )
        self._home_view = home
        self.page.add(home)
        self.page.update()

    def _show_manual_form(self):
        """Mostra il form di creazione manuale."""
        from ui.views.creation_wizard.manual_form import ManualCreationForm
        self._stop_home_polling()
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
        self._stop_home_polling()
        self.page.controls.clear()
        wizard = WizardView(
            on_complete=self._on_character_selected,
            on_cancel=self._show_home,
        )
        self.page.add(wizard)
        self.page.update()

    def _on_character_selected(self, character_id: str):
        """Carica la scheda del personaggio selezionato."""
        self._stop_home_polling()
        self.current_character_id = character_id
        self._show_main_layout()

    # ------------------------------------------------------------------
    # Layout principale (navbar + sezioni)
    # ------------------------------------------------------------------

    def _show_main_layout(self):
        """Mostra il layout con navbar laterale (desktop) o bottom nav (mobile)."""
        self.page.controls.clear()
        self._mobile = self._is_mobile()

        self.content_area = ft.Container(
            expand=True,
            bgcolor=COLOR_BG_PRIMARY,
            content=self._get_section_view(self.active_section),
        )

        if self._mobile:
            self.bottom_nav = self._build_bottom_nav()
            self.page.add(
                ft.Column(
                    [self.content_area, self.bottom_nav],
                    expand=True,
                    spacing=0,
                )
            )
        else:
            self.nav_rail = self._build_nav_rail()
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

        self.page.on_resize = self._on_page_resize
        self.page.update()

    def _on_page_resize(self, e: Any):
        """Ricostruisce il layout se si supera il breakpoint mobile/desktop."""
        now_mobile = self._is_mobile()
        if now_mobile != self._mobile:
            self._show_main_layout()

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

    def _build_bottom_nav(self) -> ft.Container:
        """Bottom navigation bar per schermi mobili (<600px)."""
        switch = {
            "key": "__home__",
            "label": "Cambia",
            "icon_off": ft.Icons.SWAP_HORIZ,
            "icon_on": ft.Icons.SWAP_HORIZ,
        }
        items = []
        for s in SECTIONS + [switch]:
            is_sel = s["key"] == self.active_section

            def _tap(e: Any, k: str = s["key"]):
                if k == "__home__":
                    self._show_home()
                else:
                    self._on_nav_click(k)

            items.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Icon(
                                s["icon_on"] if is_sel else s["icon_off"],
                                color=COLOR_ACCENT_CRIMSON if is_sel else "#9a8888",
                                size=22,
                            ),
                            ft.Text(
                                s["label"], size=9,
                                color=COLOR_ACCENT_CRIMSON if is_sel else "#9a8888",
                                text_align=ft.TextAlign.CENTER,
                                weight=ft.FontWeight.BOLD if is_sel else ft.FontWeight.NORMAL,
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=2,
                    ),
                    padding=ft.Padding.symmetric(horizontal=4, vertical=8),
                    on_click=_tap,
                    ink=True,
                    expand=True,
                )
            )

        return ft.Container(
            content=ft.Row(items, spacing=0),
            bgcolor=COLOR_NAV_BG,
            height=64,
            border=ft.Border.only(top=ft.BorderSide(1, "#3a2828")),
        )

    def _on_nav_click(self, key: str):
        if key == self.active_section:
            return
        self.active_section = key
        if self._mobile:
            self.bottom_nav.content = self._build_bottom_nav().content
        else:
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
            from data.repositories import character_repo
            from ui.views.spells_view import SpellsView
            if not self.current_character_id:
                return self._placeholder_view("Incantesimi", ft.Icons.AUTO_AWESOME, "")
            char = character_repo.get_by_id(self.current_character_id)
            if char:
                return SpellsView(char)
            return self._placeholder_view("Incantesimi", ft.Icons.AUTO_AWESOME, "")
        elif key == "diary":
            from data.repositories import character_repo
            from ui.views.diary_view import DiaryView
            if not self.current_character_id:
                return self._placeholder_view("Diario", ft.Icons.MENU_BOOK, "")
            char = character_repo.get_by_id(self.current_character_id)
            if char:
                return DiaryView(char)
            return self._placeholder_view("Diario", ft.Icons.MENU_BOOK, "")
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
        elif key == "feats":
            from ui.views.feats_view import FeatsView
            return FeatsView()
        return ft.Container()

    # ------------------------------------------------------------------
    # Update checker
    # ------------------------------------------------------------------

    def _start_update_check(self):
        """Avvia il check aggiornamenti in background (non blocca la UI).
        Disabilitato in modalità web: il deploy è gestito dal server."""
        if self.page.web:
            return
        import time

        def _check():
            time.sleep(3)  # attende che la pagina sia completamente montata
            try:
                from core.update_checker import check_for_updates
                has_update, version, url = check_for_updates()
                if has_update:
                    self._show_update_banner(version, url)
                else:
                    logger.info("Nessun aggiornamento disponibile.")
            except Exception as e:
                logger.debug(f"Update check fallito: {e}")

        t = threading.Thread(target=_check, daemon=True, name="update-check")
        t.start()

    def _show_update_banner(self, version: str, url: str):
        """Mostra dialog di aggiornamento disponibile."""
        def _open(e):
            webbrowser.open(url)
            self.page.pop_dialog()

        try:
            dlg = ft.AlertDialog(
                title=ft.Row([
                    ft.Icon(ft.Icons.SYSTEM_UPDATE, color=COLOR_ACCENT_BLUE, size=20),
                    ft.Container(width=8),
                    ft.Text("Aggiornamento disponibile", size=15,
                            weight=ft.FontWeight.BOLD, color=COLOR_TEXT_TITLE),
                ]),
                content=ft.Text(
                    f"È disponibile la versione {version}.\nVuoi scaricarla?",
                    size=13, color=COLOR_TEXT_PRIMARY,
                ),
                actions=[
                    ft.TextButton("Più tardi", on_click=lambda e: self.page.pop_dialog()),
                    ft.ElevatedButton(
                        "Scarica", icon=ft.Icons.DOWNLOAD,
                        on_click=_open,
                        bgcolor=COLOR_ACCENT_BLUE, color="#ffffff",
                    ),
                ],
                bgcolor=COLOR_BG_CARD,
            )
            self.page.show_dialog(dlg)
            logger.info(f"Dialog aggiornamento mostrato per versione {version}")
        except Exception as e:
            logger.warning(f"Impossibile mostrare dialog aggiornamento: {e}")

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
