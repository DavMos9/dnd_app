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

from ui.theme import title_text, muted_text
from ui import design


_TABS: list[dict[str, Any]] = [
    {"key": "npcs", "label": "Rubrica NPC", "icon": ft.Icons.GROUPS_OUTLINED},
    {"key": "encounters", "label": "Incontri", "icon": ft.Icons.SHIELD_OUTLINED},
    {"key": "notes", "label": "Note di Campagna", "icon": ft.Icons.MENU_BOOK_OUTLINED},
    {"key": "magic_items", "label": "Oggetti Magici", "icon": ft.Icons.AUTO_AWESOME},
    {"key": "loot", "label": "Bottino", "icon": ft.Icons.INVENTORY_2_OUTLINED},
]


class MasterView(ft.Column):
    """Shell di navigazione della Sezione Master: header + tab bar + contenuto."""

    def __init__(self, on_back_to_home, on_toggle_theme=None,
                 theme_preference: str = "system", active_tab: str = "npcs"):
        """
        `on_toggle_theme` (Fase D del restyle, 2026-07-30): se assente la
        pillola del tema non compare — stesso comportamento "nascosto se
        assente" già usato per `on_open_master` in `HomeView`, così una
        costruzione legacy senza questo argomento resta valida.

        `active_tab` permette a `DnDApp` di riaprire la Sezione Master sulla
        stessa tab dopo un cambio di tema, che ricostruisce la vista da zero.
        """
        super().__init__(expand=True, spacing=0)
        self.on_back_to_home = on_back_to_home
        self.on_toggle_theme = on_toggle_theme
        self.theme_preference = theme_preference
        valid = {t["key"] for t in _TABS}
        self.active_tab: str = active_tab if active_tab in valid else "npcs"
        self._content_area = ft.Container(expand=True, bgcolor=design.T().bg)
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
                        icon_color=design.T().text_2,
                        tooltip="Torna alla Home",
                        on_click=lambda e: self.on_back_to_home(),
                    ),
                    ft.Icon(ft.Icons.CASTLE_OUTLINED, color=design.T().primary, size=22),
                    ft.Container(width=8),
                    # expand=True + no_wrap: il titolo si tronca con "..." invece di
                    # spingere il resto dell'header fuori dalla finestra su schermi
                    # stretti (smartphone).
                    ft.Container(
                        content=title_text("Modalità Master", size=20),
                        expand=True,
                    ),
                    *self._theme_action(),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=design.Space.LG,
                                         vertical=design.Space.MD),
            bgcolor=design.T().surface,
            shadow=design.elevation(1),
        )

        self._content_area.content = self._get_tab_content(self.active_tab)

        self.controls.append(header)
        self.controls.append(self._build_tools_row())
        self.controls.append(self._build_tab_bar())
        self.controls.append(self._content_area)

    def _theme_action(self) -> list[ft.Control]:
        """Pillola di cambio tema nell'header, o lista vuota se non collegata."""
        if self.on_toggle_theme is None:
            return []
        from ui.widgets import theme_toggle_pill
        return [theme_toggle_pill(self.theme_preference, self.on_toggle_theme)]

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
            self._tool_pill(ft.Icons.DIAMOND, "Artefatti", self._open_artifacts_dialog),
        ]
        return ft.Container(
            content=ft.Row(cast(list[ft.Control], pills), spacing=8, wrap=True),
            padding=ft.Padding.symmetric(horizontal=design.Space.LG,
                                         vertical=design.Space.MD),
        )

    @staticmethod
    def _tool_pill(icon, label: str, on_click) -> ft.Control:
        """Pillola dalla primitiva condivisa `design.pill()` — stessa forma di
        quelle di Home ed Encounter, un solo posto da cambiare."""
        return design.pill(icon, label, on_click=lambda e: on_click())

    def _build_tab_bar(self) -> ft.Container:
        """Controllo segmentato: stesso linguaggio della tab bar della scheda."""
        p = design.T()
        items: list[ft.Control] = []
        for t in _TABS:
            is_sel = t["key"] == self.active_tab
            items.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(t["icon"], size=15,
                                    color=p.primary if is_sel else p.text_3),
                            ft.Container(width=6),
                            ft.Text(
                                t["label"], size=design.Size.LABEL + 1,
                                weight=ft.FontWeight.BOLD if is_sel else ft.FontWeight.W_500,
                                color=p.primary if is_sel else p.text_2,
                                font_family=design.Font.BODY,
                                no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                        tight=True,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.Padding.symmetric(horizontal=design.Space.MD,
                                                 vertical=design.Space.SM),
                    border_radius=design.Radius.PILL,
                    bgcolor=p.surface if is_sel else "transparent",
                    shadow=design.elevation(1) if is_sel else None,
                    on_click=lambda e, k=t["key"]: self._on_tab_click(k),
                    ink=True,
                    expand=True,
                    animate=ft.Animation(design.Duration.BASE, design.CURVE),
                )
            )
        return ft.Container(
            content=ft.Row(items, spacing=design.Space.XS),
            bgcolor=design.T().surface_alt,
            border_radius=design.Radius.PILL,
            padding=design.Space.XS,
            margin=ft.Margin.only(left=design.Space.LG, right=design.Space.LG,
                                  bottom=design.Space.MD),
        )

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

    def _open_artifacts_dialog(self) -> None:
        page = self.page
        if page is None:
            return
        from ui.views.master.master_artifacts_dialog import show_artifacts_dialog
        show_artifacts_dialog(cast(ft.Page, page))

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
        elif key == "loot":
            try:
                from ui.views.master.master_loot_view import MasterLootView
                return MasterLootView()
            except ImportError:
                return self._placeholder(
                    ft.Icons.INVENTORY_2_OUTLINED, "Bottino",
                    "In costruzione — presto potrai gestire qui l'archivio e il deposito del gruppo.",
                )
        return ft.Container()

    def _placeholder(self, icon, title: str, subtitle: str) -> ft.Control:
        return ft.Container(
            expand=True,
            content=ft.Column(
                [
                    ft.Icon(icon, size=64, color=design.T().border),
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
