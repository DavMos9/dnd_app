"""
Vista "Modalità Master" — punto d'accesso indipendente dai personaggi
giocanti, per la gestione di NPC/mostri e incontri di combattimento da
parte del Dungeon Master. Vedi `dnd_app/docs/master_section_design.md`
per il design completo e `CLAUDE.md` (TODO "Sezione Master") per lo stato
di avanzamento.

Struttura: header (torna alla Home) + selettore "mondo da masterare" +
tab bar interna a 5 sezioni. Le viste reali (`MasterNpcListView`,
`MasterEncounterListView`/`MasterEncounterView`, ...) sono innestate qui via
`_get_tab_content()`; finché non sono implementate questa vista mostra un
placeholder "in costruzione" per ciascuna tab, senza bloccare la
navigazione.

**Selettore mondo (2026-08-06)** — fix di due bug segnalati da Davide
("il player entrato in un mondo appare duplicato nei picker" / "in Master
escono i personaggi di ogni mondo mescolati"): prima di questa modifica la
Modalità Master non aveva ALCUN concetto di mondo, e i picker personaggi
(Tesoro, Oggetto Magico, Bottino, partecipanti a un Incontro) leggevano
sempre `character_repo.get_all()` — ogni personaggio mai creato, locali e
istanze di ogni mondo mescolati. Ora il Master sceglie esplicitamente quale
mondo sta gestendo (o "Nessun mondo", il comportamento locale di sempre) da
un menu SEMPRE visibile nell'header — mai un menu nascosto dietro un'icona
aggiuntiva, stessa convenzione già stabilita per la barra "Generatori
Rapidi". La scelta vive SOLO per la sessione (decisione di Davide,
2026-08-06: si azzera ogni volta che si riapre la Modalità Master, per non
rischiare di restare per errore sul mondo sbagliato) ma sopravvive al
rebuild della vista causato dal cambio tema, con lo stesso meccanismo già
usato per `active_tab` (vedi `ui/app.py._show_master_view`).
"""

from typing import Any, cast

import flet as ft

from core.world_permissions import ROLE_MASTER, ROLE_OWNER
from data.models import World
from data.repositories import world_repo
from ui.device_identity import resolve_device_id
from ui.theme import title_text, muted_text
from ui import design


_TABS: list[dict[str, Any]] = [
    {"key": "npcs", "label": "Rubrica NPC", "icon": ft.Icons.GROUPS_OUTLINED},
    {"key": "encounters", "label": "Incontri", "icon": ft.Icons.SHIELD_OUTLINED},
    {"key": "notes", "label": "Note di Campagna", "icon": ft.Icons.MENU_BOOK_OUTLINED},
    {"key": "magic_items", "label": "Oggetti Magici", "icon": ft.Icons.AUTO_AWESOME},
    {"key": "loot", "label": "Bottino", "icon": ft.Icons.INVENTORY_2_OUTLINED},
]

#: Ruoli che abilitano un mondo a comparire nel selettore "mondo da
#: masterare" — un dispositivo che è solo `player` in un mondo non lo mastera.
_MASTERABLE_ROLES = (ROLE_OWNER, ROLE_MASTER)

#: Valore convenzionale per "Nessun mondo" nel Dropdown — non può coincidere
#: con un id di mondo reale (UUID), usato solo come chiave del controllo.
_NO_WORLD_KEY = ""


class MasterView(ft.Column):
    """Shell di navigazione della Sezione Master: header + tab bar + contenuto."""

    def __init__(self, on_back_to_home, on_toggle_theme=None,
                 theme_preference: str = "system", active_tab: str = "npcs",
                 active_world_id: str = ""):
        """
        `on_toggle_theme` (Fase D del restyle, 2026-07-30): se assente la
        pillola del tema non compare — stesso comportamento "nascosto se
        assente" già usato per `on_open_master` in `HomeView`, così una
        costruzione legacy senza questo argomento resta valida.

        `active_tab` permette a `DnDApp` di riaprire la Sezione Master sulla
        stessa tab dopo un cambio di tema, che ricostruisce la vista da zero.

        `active_world_id` (2026-08-06): stesso principio di `active_tab`, ma
        per il mondo correntemente selezionato — vedi il docstring del modulo.
        """
        super().__init__(expand=True, spacing=0)
        self.on_back_to_home = on_back_to_home
        self.on_toggle_theme = on_toggle_theme
        self.theme_preference = theme_preference
        valid = {t["key"] for t in _TABS}
        self.active_tab: str = active_tab if active_tab in valid else "npcs"

        # Selettore mondo — vedi docstring del modulo. `device_id` è risolto
        # in modo asincrono in did_mount() (stesso pattern di HomeView):
        # finché è None il selettore mostra solo "Nessun mondo", nessun
        # blocco dell'apertura della Modalità Master in attesa della rete/
        # del servizio di storage.
        self._active_world_id: str = active_world_id
        self.device_id: str | None = None
        self._masterable_worlds: list[World] = []

        self._content_area = ft.Container(expand=True, bgcolor=design.T().bg)
        self._build()

    def did_mount(self) -> None:
        page = self.page
        if page is not None:
            page.run_task(self._init_identity)

    async def _init_identity(self) -> None:
        """Risolve `device_id` e carica i mondi che questo dispositivo può
        masterare (ruolo owner/master) — vedi `ui/device_identity.py` per il
        motivo per cui questa risoluzione è asincrona."""
        page = self.page
        if page is None:
            return
        self.device_id = await resolve_device_id(page)
        self._masterable_worlds = world_repo.get_worlds_for_device(
            self.device_id, roles=_MASTERABLE_ROLES,
        )
        # Se il mondo selezionato in precedenza non è (più) tra quelli
        # masterabili da questo dispositivo (mondo eliminato, espulsione,
        # degradazione di ruolo), torna a "Nessun mondo" invece di restare
        # silenziosamente su un world_id ormai invalido.
        if self._active_world_id and not any(
            w.id == self._active_world_id for w in self._masterable_worlds
        ):
            self._active_world_id = _NO_WORLD_KEY
        self._build()
        try:
            self.update()
        except RuntimeError:
            pass

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
                    self._world_selector(),
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

    def _world_selector(self) -> ft.Control:
        """
        Menu SEMPRE visibile (mai dietro un'icona aggiuntiva) per scegliere
        quale mondo il Master sta gestendo — vedi docstring del modulo.
        Mostra sempre "Nessun mondo" come prima opzione anche quando la
        lista dei mondi masterabili è ancora vuota (identità non risolta, o
        semplicemente nessun mondo posseduto): nessuna sorpresa per chi non
        usa il Multiplayer.
        """
        options = [ft.DropdownOption(key=_NO_WORLD_KEY, text="Nessun mondo (locale)")]
        options += [ft.DropdownOption(key=w.id, text=w.name) for w in self._masterable_worlds]
        current = self._active_world_id if any(
            w.id == self._active_world_id for w in self._masterable_worlds
        ) else _NO_WORLD_KEY
        return ft.Container(
            width=220,
            content=ft.Dropdown(
                value=current,
                options=options,
                dense=True,
                prefix_icon=ft.Icons.PUBLIC,
                border_color=design.T().border, focused_border_color=design.T().primary,
                bgcolor=design.T().surface_alt, label_style=ft.TextStyle(color=design.T().text_3, size=11),
                border_radius=design.field_style()['border_radius'],
                text_style=design.field_style()['text_style'],
                on_select=self._on_world_change,
            ),
        )

    def _on_world_change(self, e: Any) -> None:
        new_world_id = e.control.value or _NO_WORLD_KEY
        if new_world_id == self._active_world_id:
            return
        self._active_world_id = new_world_id
        self._build()
        try:
            self.update()
        except RuntimeError:
            pass

    def _theme_action(self) -> list[ft.Control]:
        """Pillola di cambio tema nell'header, o lista vuota se non collegata."""
        if self.on_toggle_theme is None:
            return []
        from ui.widgets import theme_toggle_pill
        return [theme_toggle_pill(self.theme_preference, self.on_toggle_theme)]

    def _build_tools_row(self) -> ft.Container:
        """Barra di pillole sempre visibili per i 6 generatori/riferimenti del
        Master (2026-07-24, redesign su richiesta di Davide: il menu a tre
        puntini/"Strumenti" nascondeva le azioni dietro un click in più — qui
        sono tutte visibili subito). `wrap=True` sulla Row: su schermi stretti
        (smartphone) le pillole vanno semplicemente a capo su più righe invece
        di traboccare o restare irraggiungibili.

        **Etichetta "Generatori Rapidi" (2026-08-03, segnalazione di Davide)**:
        senza un titolo sopra, le pillole si confondevano con la tab bar
        sottostante e non era chiaro a cosa servissero. L'icona
        `CASINO_OUTLINED` (dado) rinforza il significato "genera qualcosa a
        caso", coerente con le icone già usate per i tiri di dado altrove
        nell'app."""
        pills = [
            self._tool_pill(ft.Icons.DIAMOND_OUTLINED, "Tesoro", self._open_treasure_dialog),
            self._tool_pill(ft.Icons.AUTO_AWESOME, "Oggetto Magico", self._open_magic_item_generator_dialog),
            self._tool_pill(ft.Icons.WARNING_AMBER_OUTLINED, "Trappola", self._open_traps_dialog),
            self._tool_pill(ft.Icons.SICK_OUTLINED, "Veleni", self._open_health_hazards_dialog),
            self._tool_pill(ft.Icons.FOREST_OUTLINED, "Ambiente", self._open_forest_encounters_dialog),
            self._tool_pill(ft.Icons.DIAMOND, "Artefatti", self._open_artifacts_dialog),
        ]
        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.CASINO_OUTLINED, size=13, color=design.T().text_3),
                            ft.Container(width=6),
                            ft.Text(
                                "GENERATORI RAPIDI", size=11, weight=ft.FontWeight.BOLD,
                                color=design.T().text_3, font_family=design.Font.BODY,
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Container(height=4),
                    ft.Row(cast(list[ft.Control], pills), spacing=8, wrap=True),
                ],
                spacing=0,
            ),
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
        show_treasure_generator_dialog(cast(ft.Page, page), world_id=self._active_world_id)

    def _open_magic_item_generator_dialog(self) -> None:
        page = self.page
        if page is None:
            return
        from ui.views.master.master_magic_item_generator_dialog import show_magic_item_generator_dialog
        show_magic_item_generator_dialog(cast(ft.Page, page), world_id=self._active_world_id)

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
        show_health_hazards_dialog(cast(ft.Page, page), world_id=self._active_world_id)

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
        show_artifacts_dialog(cast(ft.Page, page), world_id=self._active_world_id)

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
                return MasterEncounterListView(world_id=self._active_world_id)
            except ImportError:
                return self._placeholder(
                    ft.Icons.SHIELD_OUTLINED, "Incontri",
                    "In costruzione — presto potrai gestire qui i tracker di combattimento.",
                )
        elif key == "notes":
            try:
                from ui.views.master.master_notes_view import MasterNotesView
                return MasterNotesView(world_id=self._active_world_id)
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
                return MasterLootView(world_id=self._active_world_id)
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
