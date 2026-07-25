"""
Vista "Modalità Master" — punto d'accesso indipendente dai personaggi
giocanti, per la gestione di NPC/mostri e incontri di combattimento da
parte del Dungeon Master. Vedi `dnd_app/docs/master_section_design.md`
per il design completo e `CLAUDE.md` (TODO "Sezione Master") per lo stato
di avanzamento.

Struttura: header (torna alla Home) + tab bar interna a 2 sezioni —
"Rubrica NPC" e "Incontri". Le viste reali (`MasterNpcListView`,
`MasterEncounterListView`/`MasterEncounterView`) sono innestate qui via
`_get_tab_content()`; finché non sono implementate (task successivi della
Sezione Master) questa vista mostra un placeholder "in costruzione" per
ciascuna tab, senza bloccare la navigazione.
"""

from typing import Any, cast

import flet as ft

from config.settings import (
    COLOR_BG_PRIMARY, COLOR_BG_SECONDARY, COLOR_BG_TAB_ACTIVE, COLOR_BG_TAB_INACTIVE,
    COLOR_BORDER, COLOR_ACCENT_CRIMSON, COLOR_TEXT_SECONDARY, COLOR_TEXT_MUTED,
)
from ui.theme import title_text, muted_text


_TABS: list[dict[str, Any]] = [
    {"key": "npcs", "label": "Rubrica NPC", "icon": ft.Icons.GROUPS_OUTLINED},
    {"key": "encounters", "label": "Incontri", "icon": ft.Icons.SHIELD_OUTLINED},
    {"key": "notes", "label": "Note di Campagna", "icon": ft.Icons.MENU_BOOK_OUTLINED},
    {"key": "magic_items", "label": "Oggetti Magici", "icon": ft.Icons.AUTO_AWESOME},
]


class MasterView(ft.Column):
    """Shell di navigazione della Sezione Master: header + tab bar + contenuto."""

    def __init__(self, on_back_to_home):
        super().__init__(expand=True, spacing=0)
        self.on_back_to_home = on_back_to_home
        self.active_tab: str = "npcs"
        self._content_area = ft.Container(expand=True, bgcolor=COLOR_BG_PRIMARY)
        self._build()

    # ------------------------------------------------------------------
    # Build layout
    # ------------------------------------------------------------------

    def _build(self):
        self.controls.clear()

        header = ft.Container(
            content=ft.Row(
                [
                    ft.IconButton(
                        icon=ft.Icons.ARROW_BACK,
                        icon_color=COLOR_TEXT_SECONDARY,
                        tooltip="Torna alla Home",
                        on_click=lambda e: self.on_back_to_home(),
                    ),
                    ft.Icon(ft.Icons.CASTLE_OUTLINED, color=COLOR_ACCENT_CRIMSON, size=22),
                    ft.Container(width=8),
                    # expand=True + no_wrap: il titolo si tronca con "..." invece di
                    # spingere il resto dell'header fuori dalla finestra su schermi
                    # stretti (smartphone).
                    ft.Container(
                        content=title_text("Modalità Master", size=20),
                        expand=True,
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=16, vertical=12),
            bgcolor=COLOR_BG_SECONDARY,
            border=ft.Border.only(bottom=ft.BorderSide(1, COLOR_BORDER)),
        )

        self._content_area.content = self._get_tab_content(self.active_tab)

        self.controls.append(header)
        self.controls.append(self._build_tools_row())
        self.controls.append(self._build_tab_bar())
        self.controls.append(self._content_area)

    def _build_tools_row(self) -> ft.Container:
        """Barra di pillole sempre visibili per i 4 generatori/riferimenti del
        Master (2026-07-24, redesign su richiesta di Davide: il menu a tre
        puntini/"Strumenti" nascondeva le azioni dietro un click in più — qui
        sono tutte visibili subito). `wrap=True` sulla Row: su schermi stretti
        (smartphone) le pillole vanno semplicemente a capo su più righe invece
        di traboccare o restare irraggiungibili."""
        pills = [
            self._tool_pill(ft.Icons.DIAMOND_OUTLINED, "Tesoro", self._open_treasure_dialog),
            self._tool_pill(ft.Icons.AUTO_AWESOME, "Oggetto Magico", self._open_magic_item_generator_dialog),
            self._tool_pill(ft.Icons.WARNING_AMBER_OUTLINED, "Trappola", self._open_traps_dialog),
            self._tool_pill(ft.Icons.SICK_OUTLINED, "Veleni", self._open_health_hazards_dialog),
            self._tool_pill(ft.Icons.FOREST_OUTLINED, "Ambiente", self._open_forest_encounters_dialog),
        ]
        return ft.Container(
            content=ft.Row(cast(list[ft.Control], pills), spacing=8, wrap=True),
            padding=ft.Padding.symmetric(horizontal=16, vertical=10),
            bgcolor=COLOR_BG_PRIMARY,
            border=ft.Border.only(bottom=ft.BorderSide(1, COLOR_BORDER)),
        )

    @staticmethod
    def _tool_pill(icon, label: str, on_click) -> ft.Control:
        return ft.Container(
            content=ft.Row(
                [
                    ft.Icon(icon, size=15, color=COLOR_ACCENT_CRIMSON),
                    ft.Container(width=6),
                    ft.Text(label, size=12, weight=ft.FontWeight.BOLD, color=COLOR_ACCENT_CRIMSON),
                ],
                tight=True,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=12, vertical=7),
            bgcolor=COLOR_BG_TAB_ACTIVE,
            border=ft.Border.all(1, COLOR_ACCENT_CRIMSON),
            border_radius=16,
            on_click=lambda e: on_click(),
            ink=True,
        )

    def _build_tab_bar(self) -> ft.Container:
        items = []
        for t in _TABS:
            is_sel = t["key"] == self.active_tab
            items.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(
                                t["icon"], size=16,
                                color=COLOR_ACCENT_CRIMSON if is_sel else COLOR_TEXT_MUTED,
                            ),
                            ft.Container(width=6),
                            ft.Text(
                                t["label"].upper(), size=12,
                                weight=ft.FontWeight.BOLD if is_sel else ft.FontWeight.NORMAL,
                                color=COLOR_ACCENT_CRIMSON if is_sel else COLOR_TEXT_SECONDARY,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                    padding=ft.Padding.symmetric(horizontal=16, vertical=12),
                    bgcolor=COLOR_BG_TAB_ACTIVE if is_sel else COLOR_BG_TAB_INACTIVE,
                    border=ft.Border.only(
                        bottom=ft.BorderSide(3, COLOR_ACCENT_CRIMSON if is_sel else "transparent")
                    ),
                    on_click=lambda e, k=t["key"]: self._on_tab_click(k),
                    ink=True,
                    expand=True,
                )
            )
        return ft.Container(content=ft.Row(items, spacing=0), bgcolor=COLOR_BG_TAB_INACTIVE)

    def _open_treasure_dialog(self) -> None:
        page = self.page
        if page is None:
            return
        from ui.views.master.master_treasure_dialog import show_treasure_generator_dialog
        show_treasure_generator_dialog(cast(ft.Page, page))

    def _open_magic_item_generator_dialog(self) -> None:
        page = self.page
        if page is None:
            return
        from ui.views.master.master_magic_item_generator_dialog import show_magic_item_generator_dialog
        show_magic_item_generator_dialog(cast(ft.Page, page))

    def _open_traps_dialog(self) -> None:
        page = self.page
        if page is None:
            return
        from ui.views.master.master_traps_dialog import show_traps_dialog
        show_traps_dialog(cast(ft.Page, page))

    def _open_health_hazards_dialog(self) -> None:
        page = self.page
        if page is None:
            return
        from ui.views.master.master_health_hazards_dialog import show_health_hazards_dialog
        show_health_hazards_dialog(cast(ft.Page, page))

    def _open_forest_encounters_dialog(self) -> None:
        page = self.page
        if page is None:
            return
        from ui.views.master.master_forest_encounters_dialog import show_forest_encounters_dialog
        show_forest_encounters_dialog(cast(ft.Page, page))

    def _on_tab_click(self, key: str):
        if key == self.active_tab:
            return
        self.active_tab = key
        self._build()
        try:
            self.update()
        except RuntimeError:
            pass

    # ------------------------------------------------------------------
    # Contenuto tab
    # ------------------------------------------------------------------

    def _get_tab_content(self, key: str) -> ft.Control:
        if key == "npcs":
            try:
                from ui.views.master.master_npc_list_view import MasterNpcListView
                return MasterNpcListView()
            except ImportError:
                return self._placeholder(
                    ft.Icons.GROUPS_OUTLINED, "Rubrica NPC",
                    "In costruzione — presto potrai creare e consultare qui i tuoi NPC.",
                )
        elif key == "encounters":
            try:
                from ui.views.master.master_encounter_list_view import MasterEncounterListView
                return MasterEncounterListView()
            except ImportError:
                return self._placeholder(
                    ft.Icons.SHIELD_OUTLINED, "Incontri",
                    "In costruzione — presto potrai gestire qui i tracker di combattimento.",
                )
        elif key == "notes":
            try:
                from ui.views.master.master_notes_view import MasterNotesView
                return MasterNotesView()
            except ImportError:
                return self._placeholder(
                    ft.Icons.MENU_BOOK_OUTLINED, "Note di Campagna",
                    "In costruzione — presto potrai tenere qui gli appunti della campagna.",
                )
        elif key == "magic_items":
            try:
                from ui.views.master.master_magic_items_view import MasterMagicItemsView
                return MasterMagicItemsView()
            except ImportError:
                return self._placeholder(
                    ft.Icons.AUTO_AWESOME, "Oggetti Magici",
                    "In costruzione — presto potrai consultare qui il compendio.",
                )
        return ft.Container()

    def _placeholder(self, icon, title: str, subtitle: str) -> ft.Control:
        return ft.Container(
            expand=True,
            content=ft.Column(
                [
                    ft.Icon(icon, size=64, color=COLOR_BORDER),
                    ft.Container(height=16),
                    title_text(title, size=22),
                    ft.Container(height=8),
                    muted_text(subtitle, size=13, text_align=ft.TextAlign.CENTER),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                expand=True,
            ),
        )
