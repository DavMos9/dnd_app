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

**Selettore mondo** — la Modalità Master richiede una scelta esplicita di
quale mondo si sta gestendo (o "Nessun mondo", il comportamento locale di
sempre): senza, i picker personaggi (Tesoro, Oggetto Magico, Bottino,
partecipanti a un Incontro) leggerebbero sempre `character_repo.get_all()`
— ogni personaggio mai creato, locali e istanze di ogni mondo mescolati.
La scelta avviene da un menu SEMPRE visibile nell'header — mai un menu
nascosto dietro un'icona aggiuntiva, stessa convenzione già stabilita per
la barra "Generatori Rapidi".

**Persistenza della scelta** — la scelta è salvata in `app_settings`
(`data/repositories/settings_repo.py`, chiave `LAST_MASTER_WORLD_KEY`) ad
ogni cambio dal menu (`_on_world_change`), e riletta in `_init_identity()`
SOLO quando questa view viene aperta senza un `active_world_id` esplicito
(cioè non durante un rebuild per cambio tema/tab, che passa già lo stato
corrente — vedi `ui/app.py._show_master_view`): se il mondo salvato non è
più tra quelli masterabili da questo dispositivo, si torna a "Nessun
mondo".
"""

from typing import Any, cast

import flet as ft

from core.world_permissions import ROLE_MASTER, ROLE_OWNER
from data.models import World
from data.repositories import settings_repo, world_repo
from ui.device_identity import resolve_device_id
from ui import design

#: Chiave `app_settings` per l'ultimo mondo masterato — vedi il docstring
#: del modulo, "Persistenza della scelta".
LAST_MASTER_WORLD_KEY = "last_master_world_id"


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
                 active_world_id: str | None = None, is_mobile: bool = False,
                 on_open_world=None):
        """
        `on_open_world` (navigazione rapida): callback
        `(world_id) -> None` verso `DnDApp._show_worlds_view`, propagato dal
        pulsante accanto al selettore mondo — mostrato solo se un mondo è
        selezionato. `None` (default) nasconde il pulsante.

        `on_toggle_theme`: se assente la pillola del tema non compare —
        stesso comportamento "nascosto se assente" già usato per
        `on_open_master` in `HomeView`, così una costruzione legacy senza
        questo argomento resta valida.

        `active_tab` permette a `DnDApp` di riaprire la Sezione Master sulla
        stessa tab dopo un cambio di tema, che ricostruisce la vista da zero.

        `active_world_id`: stesso principio di `active_tab` — MA `None`
        (non passato) ha un significato diverso da `""`: `None` significa
        "nessuna richiesta esplicita", e fa rileggere l'ultimo mondo
        masterato da `app_settings` in `_init_identity()`; `""` (o
        qualunque world_id) è una richiesta esplicita del chiamante
        (rebuild per cambio tema, o un futuro arco di navigazione diretto
        verso questo mondo) e non consulta mai le preferenze salvate —
        vedi il docstring del modulo.

        `is_mobile`: valore iniziale dello stile della tab bar (icona+testo
        o solo icona) — vedi il docstring di `_build_tab_bar()`. Passato da
        `DnDApp` con lo stesso breakpoint (`_MOBILE_BP = 600`, `ui/app.py`)
        già usato per sidebar/bottom-nav. Se la finestra viene
        ridimensionata mentre la Sezione Master è già aperta, `set_mobile()`
        aggiorna la tab bar e la vista corrente in place — vedi il suo
        docstring.
        """
        super().__init__(expand=True, spacing=0)
        self.on_back_to_home = on_back_to_home
        self.on_toggle_theme = on_toggle_theme
        self.theme_preference = theme_preference
        self.on_open_world = on_open_world
        self._compact_tabs = is_mobile
        valid = {t["key"] for t in _TABS}
        self.active_tab: str = active_tab if active_tab in valid else "npcs"

        # Selettore mondo — vedi docstring del modulo. `device_id` è risolto
        # in modo asincrono in did_mount() (stesso pattern di HomeView):
        # finché è None il selettore mostra solo "Nessun mondo", nessun
        # blocco dell'apertura della Modalità Master in attesa della rete/
        # del servizio di storage.
        #: `True` solo se il chiamante NON ha passato `active_world_id`
        #: esplicitamente (`None`) — unico caso in cui `_init_identity()`
        #: rilegge l'ultimo mondo masterato da `app_settings`.
        self._world_id_from_settings = active_world_id is None
        self._active_world_id: str = active_world_id or _NO_WORLD_KEY
        self.device_id: str | None = None
        self._masterable_worlds: list[World] = []

        # `_content_switcher` avvolge SOLO il contenuto del tab in un
        # AnimatedSwitcher (fade ~200ms) — stesso principio di
        # `ui/app.py::_section_switcher`, vedi il piano "Fluidità
        # transizioni e animazioni": ora che `_on_tab_click()` non fa più
        # `_build()` pieno (Fase 1 del piano), il cambio tab è l'unico punto
        # in cui l'albero del contenuto cambia davvero — il caso d'uso
        # corretto per uno switcher. `set_mobile()` legge/scrive
        # `self._content_switcher.content` (non `_content_area.content`,
        # che ora è sempre lo switcher stesso) per propagare la modalità
        # mobile alla vista figlia corrente.
        self._content_switcher = ft.AnimatedSwitcher(
            content=ft.Container(),  # placeholder — _build() lo sostituisce subito sotto
            duration=design.Duration.INSTANT,
            switch_in_curve=design.CURVE,
            switch_out_curve=design.CURVE,
            transition=ft.AnimatedSwitcherTransition.FADE,
        )
        self._content_area = ft.Container(expand=True, bgcolor=design.T().bg,
                                          content=self._content_switcher)
        #: Riferimenti ai due controlli di chrome persistente (pannello
        #: strumenti — selettore mondo + Generatori Rapidi, tab bar) —
        #: salvati per poterne nascondere/mostrare la visibilità SENZA
        #: richiamare `_build()`. Vedi `_on_child_focus_change()` per il
        #: motivo: un `_build()` ricostruirebbe anche `_content_area.content`
        #: da zero (nuova istanza di `MasterEncounterListView` via
        #: `_get_tab_content()`), perdendo lo stato interno "incontro aperto"
        #: — chiuderebbe da solo l'incontro appena aperto dal Master.
        self._tools_panel_container: ft.Control | None = None
        self._tab_bar_container: ft.Control | None = None
        #: Pannello a comparsa (vedi `_build_tools_panel()`): selettore
        #: mondo + Generatori Rapidi raggruppati sotto un'unica
        #: intestazione sempre visibile, aperta o chiusa a scelta —
        #: collassato di default su OGNI tab, incluso Incontri, senza
        #: eccezioni per singola tab.
        self._tools_panel_expanded: bool = False
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
        # Nessuna richiesta esplicita del chiamante (vedi
        # `_world_id_from_settings` in `__init__`): rilegge l'ultimo mondo
        # masterato salvato in `app_settings`, invece di tornare a "Nessun
        # mondo" ad ogni apertura.
        if self._world_id_from_settings:
            self._active_world_id = settings_repo.get_setting(
                LAST_MASTER_WORLD_KEY, _NO_WORLD_KEY)
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

        title = design.title("Modalità Master", size=20)
        # `no_wrap` + `overflow=ELLIPSIS` + `max_lines=1`: senza questi tre,
        # un `ft.Text` dentro un `Container(expand=True)` va semplicemente a
        # capo quando lo spazio disponibile si stringe — su uno smartphone
        # stretto lo spazio può ridursi al punto che ogni parola (persino
        # ogni lettera) finisce sulla propria riga, producendo un titolo
        # verticale illeggibile. `expand=True` da solo non basta a troncare
        # il titolo: `design.title()`/`ft.Text` non imposta queste tre
        # proprietà di default.
        title.no_wrap = True
        title.overflow = ft.TextOverflow.ELLIPSIS
        title.max_lines = 1

        header = ft.Container(
            content=ft.Row(
                [
                    ft.IconButton(
                        icon=ft.Icons.ARROW_BACK,
                        icon_color=design.T().text_2,
                        tooltip="Torna alla Home",
                        on_click=lambda e: self.on_back_to_home(),
                    ),
                    design.icon_badge(ft.Icons.CASTLE_OUTLINED, tone="primary", size=32),
                    ft.Container(width=8),
                    ft.Container(content=title, expand=True),
                    *self._world_quick_nav_action(),
                    *self._theme_action(),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=design.Space.LG,
                                         vertical=design.Space.MD),
            bgcolor=design.T().surface,
            shadow=design.elevation(1),
        )

        self._content_switcher.content = self._get_tab_content(self.active_tab)

        self.controls.append(header)
        # Pannello strumenti (selettore mondo + Generatori Rapidi) su una
        # riga a sé, SOTTO l'header: infilarlo nella Row dell'header ne
        # contenderebbe lo spazio col titolo. Uniforme su OGNI tab, incluso
        # Incontri — vedi il docstring di `_tools_panel_expanded` nel
        # costruttore.
        self._tools_panel_container = self._build_tools_panel()
        self._tab_bar_container = self._build_tab_bar()
        self.controls.append(self._tools_panel_container)
        self.controls.append(self._tab_bar_container)
        self.controls.append(self._content_area)

    def _on_child_focus_change(self, focused: bool) -> None:
        """
        Nasconde/mostra selettore mondo + Generatori Rapidi + tab bar quando
        una vista figlia (oggi: `MasterEncounterListView`, quando un incontro
        è aperto) passa a schermo intero.

        **Perché esiste**: `MasterEncounterView` è documentata come
        "tracker di combattimento a schermo intero", ma senza questo
        nascondimento verrebbe comunque renderizzata SOTTO l'header di
        `MasterView`, il selettore mondo, la barra Generatori Rapidi e la
        tab bar — tutta chrome persistente e sempre visibile per
        costruzione. Su desktop resta leggibile per lo spazio abbondante;
        su uno smartphone quella chrome da sola occupa gran parte
        dell'altezza disponibile, lasciando alla lista combattenti un
        piccolo rettangolo con scroll invece dello schermo intero promesso
        dal modulo. Non è un problema specifico del solo mobile: è
        un'incoerenza reale tra l'intento dichiarato del componente e come
        viene effettivamente composto in `MasterView` — corretta per ogni
        dimensione di finestra, non dietro un controllo `is_mobile`.

        Nascondere questi tre controlli quando si è "dentro" un incontro non
        viola la convenzione "nessuna azione nascosta" di questo progetto:
        quella regola riguarda azioni interattive di cui l'utente potrebbe
        aver bisogno subito (pulsanti, tab) infilate dietro un tap in più —
        qui invece la vista figlia ha già il proprio pulsante "← torna alla
        lista" ben visibile, e mondo/tab restano semplicemente non pertinenti
        finché si è concentrati sul combattimento in corso, esattamente come
        un normale drill-down a schermo intero.

        Aggiorna solo la proprietà `visible` dei due controlli già costruiti
        — MAI una chiamata a `_build()`/`_get_tab_content()` qui: quella
        ricreerebbe una `MasterEncounterListView` nuova di zecca, perdendo lo
        stato "incontro aperto" che questa stessa vista figlia sta segnalando
        di avere appena impostato (richiuderebbe l'incontro da solo).
        """
        for ctrl in (self._tools_panel_container, self._tab_bar_container):
            if ctrl is not None:
                ctrl.visible = not focused
        try:
            self.update()
        except RuntimeError:
            pass

    def set_mobile(self, is_mobile: bool) -> None:
        """
        Aggiorna la modalità mobile "in place", senza ricostruire l'intera
        vista, quando la finestra viene ridimensionata MENTRE la Modalità
        Master è già aperta: senza questo metodo `_compact_tabs` resterebbe
        fissato al valore letto all'apertura o all'ultimo cambio tema,
        perché `MasterView` sostituisce l'intera pagina via `_navigate()` e
        non vive dentro il layout con `content_area` che risponde a
        `page.on_resize`. Chiamato da `DnDApp._on_page_resize()`.

        La tab bar (che ora usa `wrap=True`, non più `scroll`) in realtà
        NON ha bisogno di questo metodo per il solo effetto "le pillole
        vanno a capo quando non entrano": quello lo fa già Flutter da solo
        ad ogni resize. Questo metodo serve per il passaggio TRA modalità
        icona-sola e icona+etichetta (sotto/sopra i 600px), e soprattutto
        per propagare la modalità mobile alla vista attualmente mostrata
        nel tab attivo, così che layout strutturalmente diversi (es. il
        drill-down a un pannello di `MasterNotesView` sotto i 600px, contro
        i due pannelli fissi fianco a fianco sopra) si aggiornino anche
        loro dal vivo — cosa che il solo `wrap=True` di Flutter non può
        fare, perché lì la struttura dei widget stessa deve cambiare, non
        solo il loro posizionamento.

        Aggiorna solo la tab bar (rebuild mirato, non l'intero `_build()`:
        non tocca header/selettore mondo/riga strumenti) e propaga la
        nuova modalità alla vista corrente nell'area contenuto SE quella
        vista sa aggiornarsi da sola (espone un proprio `set_mobile()`,
        oggi solo `MasterNotesView`). Le viste che non lo supportano ancora
        (es. `MasterEncounterListView`) restano come sono state costruite
        l'ultima volta — nessun crash, solo nessun aggiornamento dal vivo
        per quella tab specifica: un limite onesto.
        """
        if is_mobile == self._compact_tabs:
            return
        self._compact_tabs = is_mobile
        new_tab_bar = self._build_tab_bar()
        if self._tab_bar_container is not None and self._tab_bar_container in self.controls:
            idx = self.controls.index(self._tab_bar_container)
            self.controls[idx] = new_tab_bar
        self._tab_bar_container = new_tab_bar
        content = self._content_switcher.content
        content_set_mobile = getattr(content, "set_mobile", None)
        if content_set_mobile is not None:
            content_set_mobile(is_mobile)
        try:
            self.update()
        except RuntimeError:
            pass

    def _current_world_label(self) -> str:
        """Nome del mondo attualmente selezionato per masterare, o l'etichetta
        della modalità locale — usato sia dal dropdown sia dalla riga di
        riepilogo del pannello strumenti quando è chiuso."""
        for w in self._masterable_worlds:
            if w.id == self._active_world_id:
                return w.name
        return "Nessun mondo (locale)"

    def _on_tools_panel_toggle(self, new_state: bool) -> None:
        """Apre/chiude il pannello strumenti SENZA una `_build()` completa
        (stesso principio di `set_mobile()`/`_on_child_focus_change()`: non
        deve mai perdere lo stato "incontro aperto" di una eventuale
        `MasterEncounterListView` nell'area contenuto) — ricostruisce solo
        `self._tools_panel_container` e lo sostituisce in place. Chiamato da
        `design.collapsible_section()` come `on_toggle` (la primitiva è
        stateless, lo stato aperto/chiuso resta qui)."""
        self._tools_panel_expanded = new_state
        new_panel = self._build_tools_panel()
        if self._tools_panel_container is not None and self._tools_panel_container in self.controls:
            idx = self.controls.index(self._tools_panel_container)
            self.controls[idx] = new_panel
        self._tools_panel_container = new_panel
        try:
            self.update()
        except RuntimeError:
            pass

    def _on_world_change(self, e: Any) -> None:
        new_world_id = e.control.value or _NO_WORLD_KEY
        if new_world_id == self._active_world_id:
            return
        self._active_world_id = new_world_id
        settings_repo.set_setting(LAST_MASTER_WORLD_KEY, new_world_id)
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

    def _world_quick_nav_action(self) -> list[ft.Control]:
        """Pulsante "Vai alla Sezione Mondo" nell'header, accanto al tema —
        sempre visibile qualunque tab/pannello sia attivo, a differenza del
        pannello "STRUMENTI MASTER" che richiede di essere aperto. Lista
        vuota se non è selezionato un mondo o il callback non è stato
        passato."""
        if self.on_open_world is None or self._active_world_id == _NO_WORLD_KEY:
            return []
        return [ft.IconButton(
            ft.Icons.PUBLIC, icon_color=design.T().primary_icon,
            tooltip="Vai alla Sezione Mondo",
            on_click=lambda e: self.on_open_world(self._active_world_id),
        )]

    def _build_tools_panel(self) -> ft.Control:
        """
        Pannello a comparsa: selettore mondo + Generatori Rapidi
        raggruppati sotto un'unica intestazione sempre visibile e
        cliccabile — MAI un menu nascosto (convenzione del progetto):
        l'intestazione stessa mostra sempre il mondo correntemente
        selezionato, così l'informazione più importante resta leggibile
        anche a pannello chiuso, e un solo tap la apre. Uniforme su ogni
        tab, senza eccezioni.

        Collassato di default (`self._tools_panel_expanded`, un attributo di
        istanza che sopravvive a `_build()`, azzerato solo alla ricreazione
        di `MasterView` come qualunque altro stato di questa vista).

        Usa `design.collapsible_section()` — un solo posto dove mantenere
        il pattern "intestazione cliccabile + chevron".
        """
        p = design.T()

        def _build_content() -> ft.Control:
            options = [ft.DropdownOption(key=_NO_WORLD_KEY, text="Nessun mondo (locale)")]
            options += [ft.DropdownOption(key=w.id, text=w.name) for w in self._masterable_worlds]
            current = self._active_world_id if any(
                w.id == self._active_world_id for w in self._masterable_worlds
            ) else _NO_WORLD_KEY
            world_dropdown = ft.Dropdown(
                label="Mondo da masterare",
                value=current,
                options=options,
                dense=True,
                expand=True,
                leading_icon=ft.Icons.PUBLIC,
                border_color=p.border, focused_border_color=p.primary,
                bgcolor=p.surface, label_style=ft.TextStyle(color=p.text_3, size=11),
                border_radius=design.field_style()['border_radius'],
                text_style=design.field_style()['text_style'],
                on_select=self._on_world_change,
            )

            # "GENERATORI RAPIDI": titolo sopra le pillole, altrimenti si
            # confonderebbero con la tab bar sottostante. `wrap=True` sulla
            # Row: su schermi stretti le pillole vanno a capo invece di
            # traboccare.
            pills = [
                self._tool_pill(ft.Icons.DIAMOND_OUTLINED, "Tesoro", self._open_treasure_dialog),
                self._tool_pill(ft.Icons.AUTO_AWESOME, "Oggetto Magico", self._open_magic_item_generator_dialog),
                self._tool_pill(ft.Icons.WARNING_AMBER_OUTLINED, "Trappola", self._open_traps_dialog),
                self._tool_pill(ft.Icons.SICK_OUTLINED, "Veleni", self._open_health_hazards_dialog),
                self._tool_pill(ft.Icons.FOREST_OUTLINED, "Ambiente", self._open_forest_encounters_dialog),
                self._tool_pill(ft.Icons.DIAMOND, "Artefatti", self._open_artifacts_dialog),
            ]

            return ft.Column(
                [
                    ft.Container(
                        padding=ft.Padding.only(bottom=design.Space.SM),
                        content=world_dropdown,
                    ),
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.CASINO_OUTLINED, size=13, color=p.text_3),
                            ft.Container(width=6),
                            ft.Text(
                                "GENERATORI RAPIDI", size=11, weight=ft.FontWeight.BOLD,
                                color=p.text_3, font_family=design.Font.BODY,
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Container(height=4),
                    ft.Row(cast(list[ft.Control], pills), spacing=8, wrap=True),
                ],
                spacing=0,
            )

        return design.collapsible_section(
            "STRUMENTI MASTER",
            _build_content,
            expanded=self._tools_panel_expanded,
            header_subtitle=self._current_world_label(),
            on_toggle=self._on_tools_panel_toggle,
            alt=True,
        )

    @staticmethod
    def _tool_pill(icon, label: str, on_click) -> ft.Control:
        """Pillola dalla primitiva condivisa `design.pill()` — stessa forma di
        quelle di Home ed Encounter, un solo posto da cambiare."""
        return design.pill(icon, label, on_click=lambda e: on_click())

    def _build_tab_bar(self) -> ft.Container:
        """Controllo segmentato: stesso linguaggio della tab bar della scheda.

        Sotto il breakpoint mobile dell'app (`self._compact_tabs`, passato
        da `DnDApp` con lo stesso `_MOBILE_BP = 600` di `ui/app.py`), ogni
        pillola mostra SOLO l'icona (tooltip con l'etichetta completa) —
        evita che le 5 pillole con etichetta si impilino su altrettante
        righe su un telefono stretto. Sopra il breakpoint, icona +
        etichetta, in una Row con `wrap=True`: se le pillole non entrano su
        una riga, quelle in eccesso vanno sulla riga sotto, in modo
        nativamente reattivo al ridimensionamento della finestra (Flutter
        ricalcola il wrap ad ogni resize, nessun codice Python coinvolto)
        — mai uno scroll che nasconde silenziosamente le ultime pillole,
        coerente con la convenzione del progetto di non nascondere mai
        azioni dietro un controllo aggiuntivo. Il contenitore che avvolge
        questa Row è un figlio diretto della Column esterna (`self`,
        `MasterView(ft.Column, expand=True)`), quindi riceve una larghezza
        vincolata dalla pagina — necessario perché `wrap=True` va a capo
        correttamente solo con un vincolo di larghezza finito, non
        infinito. Ogni pillola porta il proprio bordo/sfondo quando
        attiva, MAI un contenitore che le racchiude tutte.
        """
        p = design.T()
        items: list[ft.Control] = []
        for t in _TABS:
            is_sel = t["key"] == self.active_tab
            row_children: list[ft.Control] = [
                ft.Icon(t["icon"], size=15,
                        color=p.primary if is_sel else p.text_3),
            ]
            if not self._compact_tabs:
                row_children.append(ft.Container(width=6))
                row_children.append(
                    ft.Text(
                        t["label"], size=design.Size.LABEL + 1,
                        weight=ft.FontWeight.BOLD if is_sel else ft.FontWeight.W_500,
                        color=p.primary if is_sel else p.text_2,
                        font_family=design.Font.BODY,
                        no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS,
                    )
                )
            items.append(
                ft.Container(
                    content=ft.Row(
                        row_children,
                        alignment=ft.MainAxisAlignment.CENTER,
                        tight=True,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.Padding.symmetric(
                        horizontal=design.Space.SM if self._compact_tabs else design.Space.MD,
                        vertical=design.Space.SM,
                    ),
                    border_radius=design.Radius.PILL,
                    bgcolor=p.surface if is_sel else "transparent",
                    shadow=design.elevation(1) if is_sel else None,
                    on_click=lambda e, k=t["key"]: self._on_tab_click(k),
                    ink=True,
                    animate=ft.Animation(design.Duration.BASE, design.CURVE),
                    tooltip=t["label"] if self._compact_tabs else None,
                )
            )
        return ft.Container(
            content=ft.Row(items, spacing=design.Space.XS,
                           run_spacing=design.Space.XS, wrap=True),
            margin=ft.Margin.only(left=design.Space.LG, right=design.Space.LG,
                                  bottom=design.Space.MD),
        )

    def _open_treasure_dialog(self) -> None:
        page = self.page
        if page is None:
            return
        from ui.views.master.master_treasure_dialog import show_treasure_generator_dialog
        show_treasure_generator_dialog(
            cast(ft.Page, page), world_id=self._active_world_id, device_id=self.device_id or "",
        )

    def _open_magic_item_generator_dialog(self) -> None:
        page = self.page
        if page is None:
            return
        from ui.views.master.master_magic_item_generator_dialog import show_magic_item_generator_dialog
        show_magic_item_generator_dialog(
            cast(ft.Page, page), world_id=self._active_world_id, device_id=self.device_id or "",
        )

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
        show_health_hazards_dialog(
            cast(ft.Page, page), world_id=self._active_world_id, device_id=self.device_id or "",
        )

    def _open_forest_encounters_dialog(self) -> None:
        page = self.page
        if page is None:
            return
        from ui.views.master.master_forest_encounters_dialog import show_forest_encounters_dialog
        show_forest_encounters_dialog(cast(ft.Page, page), world_id=self._active_world_id)

    def _open_artifacts_dialog(self) -> None:
        page = self.page
        if page is None:
            return
        from ui.views.master.master_artifacts_dialog import show_artifacts_dialog
        show_artifacts_dialog(
            cast(ft.Page, page), world_id=self._active_world_id, device_id=self.device_id or "",
        )

    def _on_tab_click(self, key: str):
        """
        Cambio tab: aggiorna solo la tab bar (nuova pillola evidenziata) e
        il contenuto — MAI `_build()` pieno, che ricostruirebbe anche
        header/pannello strumenti (invarianti rispetto al tab attivo) e
        vanificherebbe l'`animate=` già presente sulle pillole
        (`_build_tab_bar()`, riga 540) — stesso principio già applicato da
        `set_mobile()`/`_on_tools_panel_toggle()` in questo stesso file.
        """
        if key == self.active_tab:
            return
        self.active_tab = key
        new_tab_bar = self._build_tab_bar()
        if self._tab_bar_container is not None and self._tab_bar_container in self.controls:
            idx = self.controls.index(self._tab_bar_container)
            self.controls[idx] = new_tab_bar
        self._tab_bar_container = new_tab_bar
        self._content_switcher.content = self._get_tab_content(self.active_tab)
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
                return MasterNpcListView(world_id=self._active_world_id)
            except ImportError:
                return self._placeholder(
                    ft.Icons.GROUPS_OUTLINED, "Rubrica NPC",
                    "In costruzione — presto potrai creare e consultare qui i tuoi NPC.",
                )
        elif key == "encounters":
            try:
                from ui.views.master.master_encounter_list_view import MasterEncounterListView
                return MasterEncounterListView(
                    world_id=self._active_world_id,
                    device_id=self.device_id or "",
                    on_focus_change=self._on_child_focus_change,
                )
            except ImportError:
                return self._placeholder(
                    ft.Icons.SHIELD_OUTLINED, "Incontri",
                    "In costruzione — presto potrai gestire qui i tracker di combattimento.",
                )
        elif key == "notes":
            try:
                from ui.views.master.master_notes_view import MasterNotesView
                return MasterNotesView(
                    world_id=self._active_world_id,
                    is_mobile=self._compact_tabs,
                    device_id=self.device_id or "",
                )
            except ImportError:
                return self._placeholder(
                    ft.Icons.MENU_BOOK_OUTLINED, "Note di Campagna",
                    "In costruzione — presto potrai tenere qui gli appunti della campagna.",
                )
        elif key == "magic_items":
            try:
                from ui.views.master.master_magic_items_view import MasterMagicItemsView
                return MasterMagicItemsView(
                    world_id=self._active_world_id, device_id=self.device_id or "",
                )
            except ImportError:
                return self._placeholder(
                    ft.Icons.AUTO_AWESOME, "Oggetti Magici",
                    "In costruzione — presto potrai consultare qui il compendio.",
                )
        elif key == "loot":
            try:
                from ui.views.master.master_loot_view import MasterLootView
                return MasterLootView(
                    world_id=self._active_world_id, device_id=self.device_id or "",
                )
            except ImportError:
                return self._placeholder(
                    ft.Icons.INVENTORY_2_OUTLINED, "Bottino",
                    "In costruzione — presto potrai gestire qui l'archivio e il deposito del gruppo.",
                )
        return ft.Container()

    def _placeholder(self, icon, title: str, subtitle: str) -> ft.Control:
        # Audit anti-AI-slop: riusa la primitiva condivisa `design.empty_state()`
        # invece della Column scritta a mano che duplicava esattamente lo stesso
        # pattern icona+titolo+sottotitolo centrati — l'outer Container(expand=
        # True, alignment=CENTER) resta qui per mantenere lo stesso centraggio
        # verticale a piena altezza dentro `_content_area` (`empty_state()` da
        # sola centra solo se il genitore le lascia spazio, non essendo lei
        # stessa `expand`).
        return ft.Container(
            expand=True,
            alignment=ft.Alignment.CENTER,
            content=design.empty_state(icon, title, subtitle),
        )
