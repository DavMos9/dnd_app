"""
Root dell'applicazione Flet.
Gestisce la navigazione principale tra le sezioni e lo stato globale.

Flusso:
    Avvio → Home (selezione personaggi)
        ├─► Seleziona personaggio → MainLayout (navbar + sezioni)
        ├─► Crea wizard          → WizardView → MainLayout
        └─► Crea manuale         → ManualCreationForm → MainLayout
"""

import flet as ft
import logging
import threading
from typing import Any, Callable
from config.settings import *
from data.repositories import settings_repo
from network.host_server import HostServerSlot
from ui import design
from ui.theme import get_theme, get_dark_theme, title_text, muted_text
from ui.widgets import theme_toggle_look, theme_toggle_tooltip

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
        # Preferenza di tema ("light"/"dark"/"system"), letta dal DB in
        # `_setup_page()`. Vedi la sezione "Tema" più sotto.
        self._theme_pref: str = settings_repo.DEFAULT_THEME_PREFERENCE
        # Come ricostruire la schermata attualmente a video dopo un cambio di
        # tema. `None` = schermata non ricostruibile senza perdere stato
        # (wizard/form di creazione), vedi `_rebuild_current()`.
        self._rebuild_route: Callable[[], None] | None = None
        self._master_view: Any = None
        self._worlds_view: Any = None
        #: Contenitore condiviso dell'hosting LAN eventualmente attivo —
        #: creato UNA VOLTA per l'intera sessione dell'app: se vivesse
        #: sull'istanza di `WorldsView`, che `_navigate()` ricrea ad ogni
        #: cambio di schermata, si fermerebbe da solo ad ogni navigazione —
        #: vedi il docstring di `HostServerSlot` in `network/host_server.py`
        #: per il dettaglio completo. Passato a ogni `WorldsView` creata in
        #: `_show_worlds_view()`.
        self._host_server_slot = HostServerSlot()
        # Vista di primo livello corrente in grado di aggiornarsi "in place"
        # su un resize dal vivo tramite un proprio `set_mobile(bool)` (oggi:
        # `MasterView`) — `None` quando siamo su Home/form/wizard/layout
        # principale, che non ne hanno bisogno o si gestiscono da soli.
        # `_on_main_layout` distingue il caso speciale del layout principale
        # (sidebar/bottom-nav), l'unico che richiede un rebuild completo
        # invece di un aggiornamento in place — vedi `_on_page_resize()`.
        self._active_top_view: Any = None
        self._on_main_layout: bool = False

        self._setup_page()
        self._show_home()
        # Prima l'esito dell'aggiornamento PRECEDENTE (lettura locale, immediata),
        # poi il controllo di quello nuovo (che parte con 3 s di ritardo su un
        # thread): così "Aggiornamento completato" appare subito all'avvio e non
        # rischia di sovrapporsi al dialogo di un nuovo aggiornamento.
        self._check_update_completion()
        self._start_update_check()

    def _is_mobile(self) -> bool:
        return (self.page.width or 0) < self._MOBILE_BP

    def _navigate(self, control: ft.Control) -> None:
        """
        Punto unico di navigazione di primo livello: azzera la pagina e monta
        `control` avvolto in `ft.SafeArea`, così header e barre superiori non
        finiscono mai sotto la tacca o la barra di stato su un telefono con
        notch. Centralizzare qui evita di doverlo ricordare ad ogni nuova
        vista di primo livello.

        `ft.SafeArea` è un no-op su desktop/web, dove `MediaQuery` non
        riporta intrusioni di sistema — nessun rischio di padding indesiderato.
        """
        self.page.controls.clear()
        self.page.add(ft.SafeArea(content=control, expand=True))
        self.page.update()

    # ------------------------------------------------------------------
    # Setup pagina
    # ------------------------------------------------------------------

    def _setup_page(self):
        self.page.title = APP_NAME
        # Font custom self-hosted. Va impostato PRIMA del tema: `get_theme()`
        # referenzia già le famiglie `d.Font.*`, che senza questa
        # registrazione non esisterebbero e ricadrebbero silenziosamente sul
        # font di sistema. I file vivono in `assets/fonts/`, raggiungibili
        # perché `assets_dir` è collegato su tutte le piattaforme (vedi main.py).
        self.page.fonts = dict(design.FONT_FILES)
        # Entrambi i temi sono registrati fin da subito; la scelta
        # dell'utente e la sua persistenza sono gestite sotto.
        self.page.theme = get_theme()
        self.page.dark_theme = get_dark_theme()
        self.page.padding = 0

        self._theme_pref = settings_repo.get_theme_preference()
        self._apply_theme_mode()
        # Con la preferenza "Sistema" il tema segue il SO anche mentre l'app è
        # aperta (es. la pianificazione automatica di macOS al tramonto).
        self.page.on_platform_brightness_change = self._on_system_brightness_change
        # `page.on_resize` è assegnato UNA SOLA VOLTA qui e resta attivo per
        # TUTTA la sessione, non solo mentre si guarda la scheda personaggio,
        # perché propaga il resize anche a `MasterView`/`WorldsView` tramite
        # `_active_top_view` — vedi `_on_page_resize()`. È di proprietà
        # esclusiva di questo unico punto: nessun'altra vista deve mai
        # assegnarlo, romperebbe questo meccanismo in modo silenzioso — vedi
        # `regole_flet_api.md`.
        self.page.on_resize = self._on_page_resize

    # ------------------------------------------------------------------
    # Tema
    # ------------------------------------------------------------------

    def _resolve_theme_mode(self) -> str:
        """
        Traduce la preferenza dell'utente nella modalità concreta da applicare.

        "system" viene risolta leggendo `page.platform_brightness`
        (`ft.Brightness.LIGHT`/`DARK`, verificato per introspezione su
        `flet==0.85.3`). Se il valore non è ancora disponibile — può essere
        `None` prima del primo layout — si ricade sul tema chiaro, che è anche
        quello con cui l'app è nata.
        """
        if self._theme_pref in ("light", "dark"):
            return self._theme_pref
        return "dark" if self.page.platform_brightness == ft.Brightness.DARK else "light"

    def _apply_theme_mode(self) -> bool:
        """
        Applica la modalità risolta. Ritorna `True` se è cambiata davvero.

        `page.theme_mode` riceve sempre un valore CONCRETO (LIGHT o DARK), mai
        `ft.ThemeMode.SYSTEM`, anche quando la preferenza è "Sistema": i colori
        delle nostre view vengono da `design.T()`, che conosce solo due
        palette. Lasciare a Flutter la risoluzione di SYSTEM significherebbe
        poter avere i controlli Material scuri e le nostre superfici chiare.
        La risoluzione la facciamo qui, una volta sola, per entrambi.
        """
        new_mode = self._resolve_theme_mode()
        changed = new_mode != design.mode()
        design.set_mode(new_mode)
        self.page.theme_mode = ft.ThemeMode.DARK if new_mode == "dark" else ft.ThemeMode.LIGHT
        self.page.bgcolor = design.T().bg
        return changed

    def _on_system_brightness_change(self, e: Any):
        """Il SO ha cambiato tema: rilevante solo se la preferenza è "Sistema"."""
        if self._theme_pref != "system":
            return
        if self._apply_theme_mode():
            self._rebuild_current()

    def _cycle_theme(self, e: Any = None):
        """Chiaro → Scuro → Sistema → Chiaro. Salva e ricostruisce la vista."""
        self._theme_pref = settings_repo.next_theme_preference(self._theme_pref)
        settings_repo.set_theme_preference(self._theme_pref)
        self._apply_theme_mode()
        # Sempre, anche quando la modalità risolta non cambia (es. da "Chiaro"
        # a "Sistema" con il SO già chiaro): l'etichetta del pulsante è
        # cambiata e va ridisegnata.
        self._rebuild_current()

    def _rebuild_current(self):
        """
        Ricostruisce la schermata a video con la nuova palette.

        Serve un rebuild completo perché i colori delle view sono letti da
        `design.T()` al momento della costruzione dei controlli: cambiare la
        palette non ridisegna da solo un albero già costruito.

        Se `_rebuild_route` è `None` siamo nel wizard o nel form di creazione,
        dove ricostruire vorrebbe dire perdere le scelte fatte a metà: si
        applica il solo tema Material (già fatto da `_apply_theme_mode`) e le
        superfici custom si allineano alla schermata successiva. È un caso che
        oggi può capitare solo con la preferenza "Sistema" e un cambio di tema
        del SO durante la creazione, dato che lì il pulsante non compare.
        """
        route = self._rebuild_route
        if route is None:
            self.page.update()
            return
        route()

    def _nav_theme_item(self, width: int | None = None, label_size: int = 10) -> ft.Container:
        """
        Voce "cambia tema" per la sidebar e la bottom nav.

        Non usa `theme_toggle_pill()`: su fondo scuro della navigazione la
        forma giusta è quella delle altre voci (icona sopra etichetta), non una
        pillola. Icona ed etichetta vengono comunque dalla stessa fonte
        condivisa `theme_toggle_look()`, così i tre punti non divergono.
        """
        p = design.T()
        icon, label = theme_toggle_look(self._theme_pref)
        return ft.Container(
            content=ft.Column(
                [
                    ft.Icon(icon, color=p.nav_muted, size=22),
                    ft.Text(label, size=label_size, color=p.nav_muted,
                            text_align=ft.TextAlign.CENTER),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=3 if width else 2,
            ),
            padding=ft.Padding.symmetric(horizontal=6 if width else 4,
                                         vertical=10 if width else 8),
            border_radius=8 if width else None,
            width=width or 68,
            tooltip=theme_toggle_tooltip(self._theme_pref),
            on_click=self._cycle_theme,
            ink=True,
        )

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
        home = HomeView(
            on_select=self._on_character_selected,
            on_create_wizard=self._show_wizard,
            on_create_manual=self._show_manual_form,
            on_open_master=self._show_master_view,
            on_toggle_theme=self._cycle_theme,
            theme_preference=self._theme_pref,
            on_open_worlds=self._show_worlds_view,
        )
        self._home_view = home
        self._rebuild_route = self._show_home
        self._active_top_view = None
        self._on_main_layout = False
        self._navigate(home)

    def _show_master_view(self, active_tab: str | None = None, active_world_id: str | None = None):
        """Mostra la Modalità Master — indipendente da ogni personaggio giocante.

        `active_world_id=None`: nessuna richiesta esplicita — `MasterView`
        rilegge da sola l'ultimo mondo masterato salvato (vedi il docstring
        del modulo). `""` è invece una richiesta esplicita di "Nessun mondo"
        (usata dal rebuild per cambio tema sotto), semanticamente diversa da
        "nessuna richiesta".
        """
        from ui.views.master.master_view import MasterView
        self._stop_home_polling()
        master = MasterView(
            on_back_to_home=self._show_home,
            on_toggle_theme=self._cycle_theme,
            theme_preference=self._theme_pref,
            active_tab=active_tab or "npcs",
            active_world_id=active_world_id,
            is_mobile=self._is_mobile(),
            on_open_world=self._show_worlds_view,
        )
        self._master_view = master
        # Il rebuild legge la tab/il mondo attivi al momento del cambio tema,
        # non ora. Nota onesta: solo questi due valori vengono preservati, non
        # lo stato interno di una sotto-vista (es. un incontro aperto torna
        # alla lista incontri).
        self._rebuild_route = lambda: self._show_master_view(
            getattr(self._master_view, "active_tab", "npcs"),
            getattr(self._master_view, "_active_world_id", ""),
        )
        self._active_top_view = master
        self._on_main_layout = False
        self._navigate(master)

    def _show_worlds_view(self, world_id: str | None = None):
        """Mostra la Sezione Mondi (Multiplayer, passo 2) — indipendente da
        ogni personaggio, stesso trattamento di `_show_master_view`.

        `world_id`: se passato, apre direttamente il dettaglio di quel mondo
        — vedi `WorldsView.__init__` (`initial_world_id`).
        """
        from ui.views.world.world_view import WorldsView
        self._stop_home_polling()
        worlds = WorldsView(
            on_back_to_home=self._show_home,
            on_toggle_theme=self._cycle_theme,
            theme_preference=self._theme_pref,
            host_server_slot=self._host_server_slot,
            initial_world_id=world_id,
            on_open_master=lambda wid: self._show_master_view(active_world_id=wid),
            on_open_character=self._on_character_selected,
        )
        self._worlds_view = worlds
        self._rebuild_route = self._show_worlds_view
        # `WorldsView` non espone ancora un proprio `set_mobile()`: tenerla
        # comunque come `_active_top_view` non cambia nulla oggi (vedi
        # `_on_page_resize()`, che chiama `set_mobile` solo se esiste) e
        # rende il futuro aggiornamento a costo zero se questa vista
        # svilupperà una propria esigenza di layout mobile/desktop.
        self._active_top_view = worlds
        self._on_main_layout = False
        self._navigate(worlds)

    def _show_manual_form(self):
        """Mostra il form di creazione manuale."""
        from ui.views.creation_wizard.manual_form import ManualCreationForm
        self._stop_home_polling()
        # Ricostruire il form a metà compilazione perderebbe le scelte fatte.
        self._rebuild_route = None
        form = ManualCreationForm(
            on_complete=self._on_character_selected,
            on_cancel=self._show_home,
        )
        self._active_top_view = None
        self._on_main_layout = False
        self._navigate(form)

    def _show_wizard(self):
        """Avvia il wizard guidato."""
        from ui.views.creation_wizard.wizard_view import WizardView
        self._stop_home_polling()
        # Come per il form manuale: nessun rebuild a metà creazione.
        self._rebuild_route = None
        wizard = WizardView(
            on_complete=self._on_character_selected,
            on_cancel=self._show_home,
        )
        self._active_top_view = None
        self._on_main_layout = False
        self._navigate(wizard)

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
        self._mobile = self._is_mobile()
        self._rebuild_route = self._show_main_layout

        self.content_area = ft.Container(
            expand=True,
            bgcolor=design.T().bg,
            content=self._get_section_view(self.active_section),
        )

        if self._mobile:
            self.bottom_nav = self._build_bottom_nav()
            layout: ft.Control = ft.Column(
                [self.content_area, self.bottom_nav],
                expand=True,
                spacing=0,
            )
        else:
            self.nav_rail = self._build_nav_rail()
            layout = ft.Row(
                controls=[
                    self.nav_rail,
                    ft.VerticalDivider(width=1, color=design.T().border),
                    self.content_area,
                ],
                expand=True,
                spacing=0,
                vertical_alignment=ft.CrossAxisAlignment.STRETCH,
            )

        # `page.on_resize` è assegnato una sola volta in `_setup_page()`, così
        # resta attivo anche fuori dal layout principale — vedi
        # `_on_page_resize()` sotto.
        self._active_top_view = None
        self._on_main_layout = True
        self._navigate(layout)

    def _on_page_resize(self, e: Any):
        """
        Reagisce al ridimensionamento della finestra, per QUALUNQUE vista
        di primo livello attualmente a video — non solo il layout
        principale.

        Due rami distinti:
        - Layout principale (scheda personaggio): richiede un rebuild
          completo quando si attraversa il breakpoint, perché sidebar e
          bottom-nav sono due alberi di widget strutturalmente diversi, non
          un semplice riflusso — `_show_main_layout()` se ne occupa già.
        - Qualunque altra vista di primo livello con un proprio
          `set_mobile(bool)` (oggi solo `MasterView`): aggiornamento "in
          place", chiamato ad OGNI resize (non solo quando si attraversa il
          breakpoint — `set_mobile()` verifica da sé se c'è davvero
          qualcosa da cambiare ed è quindi economico chiamarlo sempre).
        """
        now_mobile = self._is_mobile()
        if self._on_main_layout:
            if now_mobile != self._mobile:
                self._show_main_layout()
            return
        if self._active_top_view is not None:
            set_mobile = getattr(self._active_top_view, "set_mobile", None)
            if set_mobile is not None:
                set_mobile(now_mobile)

    def _build_char_avatar(self) -> ft.Control:
        """Icona del personaggio corrente per la sidebar."""
        from data.repositories import character_repo
        p = design.T()
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
                border=ft.Border.all(2, design.T().primary),
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
                color=p.nav_text, text_align=ft.TextAlign.CENTER,
            ),
            width=56, height=56,
            bgcolor=p.nav_bg_alt,
            border=ft.Border.all(2, p.nav_accent),
            border_radius=28,
            alignment=ft.Alignment.CENTER,
        )

    def _build_nav_rail(self) -> ft.Container:
        """
        Sidebar custom (Column) invece di NavigationRail — controllo totale sui colori.

        La chrome della navigazione è volutamente scura in ENTRAMBI i temi (è
        cuoio, non una superficie): usa i token `nav_*` di `ui/design.py`, non
        `surface`/`text`. L'accento delle voci non selezionate passa da
        `primary` a `nav_accent` perché `primary` su `nav_bg` dà solo 2.45:1.
        """
        p = design.T()

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
                                color=p.on_primary if is_sel else p.nav_muted,
                                size=22,
                            ),
                            ft.Text(
                                s["label"], size=10,
                                color=p.on_primary if is_sel else p.nav_muted,
                                text_align=ft.TextAlign.CENTER,
                                weight=ft.FontWeight.BOLD if is_sel else ft.FontWeight.NORMAL,
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=3,
                    ),
                    padding=ft.Padding.symmetric(horizontal=6, vertical=10),
                    bgcolor=p.primary_fill if is_sel else "transparent",
                    border_radius=8,
                    width=80,
                    on_click=lambda e, k=s["key"]: self._on_nav_click(k),
                    ink=True,
                )
            )

        switch_btn = ft.Container(
            content=ft.Column(
                [
                    ft.Icon(ft.Icons.SWAP_HORIZ, color=p.nav_muted, size=22),
                    ft.Text("Cambia", size=10, color=p.nav_muted,
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
                ft.Divider(color=p.nav_border, height=1),
                ft.Container(height=4),
                *nav_items,
                ft.Container(expand=True),   # spazio flessibile
                ft.Divider(color=p.nav_border, height=1),
                self._nav_theme_item(width=80),
                switch_btn,
                ft.Container(height=8),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=2,
            expand=True,
        )

        return ft.Container(
            content=sidebar_col,
            bgcolor=p.nav_bg,
            width=82,
        )

    def _build_bottom_nav(self) -> ft.Container:
        """Bottom navigation bar per schermi mobili (<600px)."""
        p = design.T()
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
                                color=p.nav_accent if is_sel else p.nav_muted,
                                size=22,
                            ),
                            ft.Text(
                                s["label"], size=9,
                                color=p.nav_accent if is_sel else p.nav_muted,
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
                    # Larghezza fissa invece di `expand`: con 9 voci su un
                    # telefono da 375px la ripartizione a fisarmonica
                    # scenderebbe a ~41px, sotto i 48dp minimi consigliati per
                    # un tap-target. Con una larghezza garantita la barra
                    # scorre orizzontalmente quando non ci stanno tutte.
                    width=68,
                )
            )

        # Ottava voce: cambio tema. A 375px di viewport le voci scendono a
        # ~47px di larghezza, appena sotto i 48dp minimi consigliati per la
        # larghezza del tap-target — ma l'altezza della barra è 64px, quindi
        # l'area effettiva resta ben oltre 48×48. La voce è qui e non solo in
        # Home perché deve essere "raggiungibile da tutte le schermate".
        items.append(self._nav_theme_item(label_size=9))

        return ft.Container(
            content=ft.Row(items, spacing=0, scroll=ft.ScrollMode.AUTO),
            bgcolor=p.nav_bg,
            height=64,
            border=ft.Border.only(top=ft.BorderSide(1, p.nav_border)),
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
                return SheetView(char, profs, is_mobile=self._mobile,
                                  on_open_world=self._show_worlds_view)
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

    def _check_update_completion(self):
        """
        Mostra "Aggiornamento completato" al primo avvio dopo un aggiornamento.

        Non può essere mostrato dal processo che ha avviato l'aggiornamento: su
        Android quel processo viene ucciso dall'installer di sistema, e su
        desktop l'utente deve comunque chiudere l'app per sostituire i file. La
        conferma viaggia quindi in un segnalibro su `app_settings`, scritto prima
        della consegna all'installer e letto qui. La decisione su cosa mostrare è
        una funzione pura in `core.update_state`, testata a parte.
        """
        if self.page.web:
            return
        try:
            from core import update_downloader, update_state
            from data.database import get_updates_path
            from ui.update_dialogs import show_completion_dialog
            from version import APP_VERSION

            pending, started_at = update_state.read_pending_update()
            outcome = update_state.classify_pending_update(
                APP_VERSION, pending, started_at,
            )
            if outcome == "none":
                return
            if outcome == "stale":
                # Un tentativo abbandonato settimane fa non deve infastidire per
                # sempre: si dimentica in silenzio.
                update_state.clear_pending_update()
                return
            if outcome == "completed":
                update_state.clear_pending_update()
                # Il pacchetto ha fatto il suo lavoro: liberare decine di MB.
                update_downloader.cleanup_old_downloads(
                    get_updates_path(), keep_version=APP_VERSION,
                )
            else:
                # "failed": l'utente non ha completato l'installazione. Il
                # segnalibro si cancella comunque, così l'avviso non si ripete a
                # ogni avvio; il pacchetto resta su disco per un nuovo tentativo.
                update_state.clear_pending_update()
            show_completion_dialog(self.page, APP_VERSION, pending, outcome)
        except Exception as e:
            logger.debug(f"Verifica dell'esito dell'aggiornamento fallita: {e}")

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
                has_update, info = check_for_updates()
                if not has_update or info is None:
                    logger.info("Nessun aggiornamento disponibile.")
                    return
                # Il dialog NON va aperto da questo thread: mutare l'albero dei
                # controlli fuori dal thread della UI è una race. `page.run_task`
                # usa asyncio.run_coroutine_threadsafe sul loop della sessione,
                # quindi è il modo corretto di rientrare nel thread della UI.
                try:
                    self.page.run_task(self._show_update_dialog_async, info)
                except Exception as e:
                    logger.debug(f"Impossibile pianificare il dialog aggiornamento: {e}")
            except Exception as e:
                logger.debug(f"Update check fallito: {e}")

        t = threading.Thread(target=_check, daemon=True, name="update-check")
        t.start()

    async def _show_update_dialog_async(self, info):
        """Wrapper coroutine: esegue `_show_update_dialog` sul loop della UI."""
        self._show_update_dialog(info)

    def _show_update_dialog(self, info):
        """
        Instrada verso il dialogo giusto — questa classe decide QUALE, il come
        vive in `ui/update_dialogs.py`.

        Due casi, non uno:

        - `info.requires_reinstall`: l'aggiornamento attraversa la migrazione
          alla firma di rilascio, la sola che obbliga a disinstallare perdendo il
          database. Serve il flusso guidato col backup, e il pacchetto deve
          scaricarlo il browser — non noi, perché la nostra cartella di staging
          viene cancellata dalla disinstallazione stessa.
        - altrimenti: download in-app con barra di avanzamento, poi consegna
          all'installer di sistema (Android) o al file manager (desktop).
        """
        try:
            from ui.update_dialogs import show_download_dialog, show_migration_dialog

            if info.requires_reinstall:
                show_migration_dialog(self.page, info)
            else:
                show_download_dialog(self.page, info)
            logger.info(
                "Dialog aggiornamento mostrato per la versione %s "
                "(reinstallazione necessaria: %s)",
                info.latest_version, info.requires_reinstall,
            )
        except Exception as e:
            logger.warning(f"Impossibile mostrare dialog aggiornamento: {e}")

    def _placeholder_view(self, title: str, icon, subtitle: str) -> ft.Container:
        return ft.Container(
            expand=True,
            bgcolor=design.T().bg,
            content=ft.Column(
                [
                    ft.Icon(icon, size=64, color=design.T().border),
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
