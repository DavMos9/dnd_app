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
                 active_world_id: str = "", is_mobile: bool = False):
        """
        `on_toggle_theme` (Fase D del restyle, 2026-07-30): se assente la
        pillola del tema non compare — stesso comportamento "nascosto se
        assente" già usato per `on_open_master` in `HomeView`, così una
        costruzione legacy senza questo argomento resta valida.

        `active_tab` permette a `DnDApp` di riaprire la Sezione Master sulla
        stessa tab dopo un cambio di tema, che ricostruisce la vista da zero.

        `active_world_id` (2026-08-06): stesso principio di `active_tab`, ma
        per il mondo correntemente selezionato — vedi il docstring del modulo.

        `is_mobile` (2026-08-06): decide lo stile della tab bar (icona+testo
        o solo icona) — vedi il docstring di `_build_tab_bar()`. Passato da
        `DnDApp` con lo stesso breakpoint (`_MOBILE_BP = 600`, `ui/app.py`)
        già usato per sidebar/bottom-nav. Diversamente da `active_tab`, NON
        si aggiorna da solo se la finestra viene ridimensionata mentre la
        Sezione Master è aperta (`MasterView` non vive dentro il layout con
        sidebar/content_area che risponde a `page.on_resize` — sostituisce
        l'intera pagina via `_navigate()`): resta fissato al valore letto
        all'apertura o all'ultimo rebuild (es. cambio tema). Limite noto,
        accettabile: nessuna sessione finora ha segnalato di ridimensionare
        la finestra a metà mentre è in Modalità Master.
        """
        super().__init__(expand=True, spacing=0)
        self.on_back_to_home = on_back_to_home
        self.on_toggle_theme = on_toggle_theme
        self.theme_preference = theme_preference
        self._compact_tabs = is_mobile
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
        #: Pannello a comparsa (2026-08-07, restyle su richiesta di Davide —
        #: vedi `_build_tools_panel()`): selettore mondo + Generatori Rapidi
        #: raggruppati sotto un'unica intestazione sempre visibile, aperta o
        #: chiusa a scelta. Sostituisce il precedente "nascondi Generatori
        #: Rapidi SOLO nella tab Incontri" (Davide, sessione successiva: li
        #: voleva di nuovo visibili ovunque, ma la parte superiore doveva
        #: restare compatta) — collassato di default su OGNI tab, incluso
        #: Incontri, mai più un'eccezione per una singola tab.
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

        title = title_text("Modalità Master", size=20)
        # `no_wrap` + `overflow=ELLIPSIS` + `max_lines=1`: senza questi tre,
        # un `ft.Text` dentro un `Container(expand=True)` va semplicemente a
        # capo quando lo spazio disponibile si stringe — su uno smartphone
        # stretto lo spazio può ridursi al punto che ogni parola (persino
        # ogni lettera) finisce sulla propria riga, producendo un titolo
        # verticale illeggibile (bug reale segnalato da Davide con
        # screenshot, 2026-08-06 — il commento precedente qui affermava
        # erroneamente che `expand=True` da solo bastasse a troncare il
        # titolo: falso, `design.title()`/`ft.Text` non ha mai impostato
        # queste tre proprietà di default).
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
                    ft.Icon(ft.Icons.CASTLE_OUTLINED, color=design.T().primary, size=22),
                    ft.Container(width=8),
                    ft.Container(content=title, expand=True),
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
        # Pannello strumenti (selettore mondo + Generatori Rapidi) su una
        # riga a sé, SOTTO l'header (2026-08-06, fix di una regressione
        # precedente: infilarlo nella Row dell'header ne contendeva lo
        # spazio col titolo). Uniforme su OGNI tab, incluso Incontri — vedi
        # il docstring di `_tools_panel_expanded` nel costruttore.
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

        **Perché esiste** (bug report di Davide, 2026-08-06, screenshot da
        smartphone): `MasterEncounterView` è documentata come "tracker di
        combattimento a schermo intero", ma prima di questo fix veniva
        comunque renderizzata SOTTO l'header di `MasterView`, il selettore
        mondo, la barra Generatori Rapidi e la tab bar — tutta chrome
        persistente e sempre visibile per costruzione. Su desktop restava
        leggibile per lo spazio abbondante; su uno smartphone quella chrome
        da sola occupa gran parte dell'altezza disponibile, lasciando alla
        lista combattenti "un piccolo rettangolo" con scroll (parole di
        Davide) invece dello schermo intero promesso dal modulo. Non è un
        problema specifico del solo mobile: è un'incoerenza reale tra
        l'intento dichiarato del componente e come viene effettivamente
        composto in `MasterView` — corretto per ogni dimensione di finestra,
        non dietro un controllo `is_mobile`.

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
        Master è già aperta (2026-08-06, bug report Davide: "se cambio
        dimensione [la scheda Note di Campagna] taglia il testo" — prima di
        questo metodo `_compact_tabs` restava fissato al valore letto
        all'apertura o all'ultimo cambio tema, perché `MasterView`
        sostituisce l'intera pagina via `_navigate()` e non viveva dentro
        il layout con `content_area` che risponde a `page.on_resize` (vedi
        il vecchio docstring del costruttore, ora superato — il limite
        "nessuna sessione ha segnalato di ridimensionare a metà" non è più
        vero). Chiamato da `DnDApp._on_page_resize()`.

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
        per quella tab specifica: un limite onesto, non peggiore del
        comportamento di prima di questo fix.
        """
        if is_mobile == self._compact_tabs:
            return
        self._compact_tabs = is_mobile
        new_tab_bar = self._build_tab_bar()
        if self._tab_bar_container is not None and self._tab_bar_container in self.controls:
            idx = self.controls.index(self._tab_bar_container)
            self.controls[idx] = new_tab_bar
        self._tab_bar_container = new_tab_bar
        content = self._content_area.content
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

    def _toggle_tools_panel(self, e: Any = None) -> None:
        """Apre/chiude il pannello strumenti SENZA una `_build()` completa
        (stesso principio di `set_mobile()`/`_on_child_focus_change()`: non
        deve mai perdere lo stato "incontro aperto" di una eventuale
        `MasterEncounterListView` nell'area contenuto) — ricostruisce solo
        `self._tools_panel_container` e lo sostituisce in place."""
        self._tools_panel_expanded = not self._tools_panel_expanded
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

    def _build_tools_panel(self) -> ft.Container:
        """
        Pannello a comparsa (2026-08-07, restyle su richiesta di Davide):
        selettore mondo + Generatori Rapidi raggruppati sotto un'unica
        intestazione sempre visibile e cliccabile — MAI un menu nascosto
        (convenzione del progetto): l'intestazione stessa mostra sempre il
        mondo correntemente selezionato, così l'informazione più importante
        resta leggibile anche a pannello chiuso, e un solo tap la apre.

        Sostituisce due controlli distinti (`_world_selector_row()` +
        `_build_tools_row()`, prima quest'ultima nascosta SOLO nella tab
        Incontri): Davide ha chiesto di reintrodurre i Generatori Rapidi
        ovunque, ma di rendere comunque la parte superiore più compatta — un
        pannello collassabile uniforme su ogni tab risolve entrambe le cose
        insieme, senza più eccezioni per tab specifiche.

        Collassato di default (`self._tools_panel_expanded`, un attributo di
        istanza che sopravvive a `_build()`, azzerato solo alla ricreazione
        di `MasterView` come qualunque altro stato di questa vista).
        """
        p = design.T()
        header = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.TUNE, size=16, color=p.text_3),
                    ft.Container(width=8),
                    ft.Column(
                        [
                            ft.Text("STRUMENTI MASTER", size=11, weight=ft.FontWeight.BOLD,
                                    color=p.text_3, font_family=design.Font.BODY),
                            ft.Text(self._current_world_label(), size=12, color=p.text_2,
                                    no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS),
                        ],
                        spacing=1, expand=True,
                    ),
                    ft.Icon(
                        ft.Icons.EXPAND_LESS if self._tools_panel_expanded else ft.Icons.EXPAND_MORE,
                        size=20, color=p.text_3,
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=design.Space.LG, vertical=design.Space.SM),
            on_click=self._toggle_tools_panel,
            ink=True,
        )
        if not self._tools_panel_expanded:
            return ft.Container(
                content=header,
                bgcolor=p.surface_alt,
            )

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

        # "GENERATORI RAPIDI" (2026-08-03, segnalazione di Davide: senza un
        # titolo sopra le pillole si confondevano con la tab bar
        # sottostante). `wrap=True` sulla Row: su schermi stretti le pillole
        # vanno a capo invece di traboccare.
        pills = [
            self._tool_pill(ft.Icons.DIAMOND_OUTLINED, "Tesoro", self._open_treasure_dialog),
            self._tool_pill(ft.Icons.AUTO_AWESOME, "Oggetto Magico", self._open_magic_item_generator_dialog),
            self._tool_pill(ft.Icons.WARNING_AMBER_OUTLINED, "Trappola", self._open_traps_dialog),
            self._tool_pill(ft.Icons.SICK_OUTLINED, "Veleni", self._open_health_hazards_dialog),
            self._tool_pill(ft.Icons.FOREST_OUTLINED, "Ambiente", self._open_forest_encounters_dialog),
            self._tool_pill(ft.Icons.DIAMOND, "Artefatti", self._open_artifacts_dialog),
        ]

        return ft.Container(
            bgcolor=p.surface_alt,
            content=ft.Column(
                [
                    header,
                    ft.Container(
                        padding=ft.Padding.only(left=design.Space.LG, right=design.Space.LG,
                                                bottom=design.Space.SM),
                        content=world_dropdown,
                    ),
                    ft.Container(
                        padding=ft.Padding.only(left=design.Space.LG, right=design.Space.LG,
                                                bottom=design.Space.MD),
                        content=ft.Column(
                            [
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
                        ),
                    ),
                ],
                spacing=0,
            ),
        )

    @staticmethod
    def _tool_pill(icon, label: str, on_click) -> ft.Control:
        """Pillola dalla primitiva condivisa `design.pill()` — stessa forma di
        quelle di Home ed Encounter, un solo posto da cambiare."""
        return design.pill(icon, label, on_click=lambda e: on_click())

    def _build_tab_bar(self) -> ft.Container:
        """Controllo segmentato: stesso linguaggio della tab bar della scheda.

        STORIA:
        1) Primo fix (2026-08-06) — `wrap=True` sulla Row esterna + pillole
           NON `expand`, per il bug segnalato da Davide con screenshot (5
           pillole — "Rubrica NPC", "Note di Campagna", "Oggetti Magici"
           comprese — con `expand=True` forzavano una sola riga su
           smartphone stretto, l'ellissi tagliava il testo a una sola
           lettera, illeggibile). Risolveva il crash/troncamento ma
           produceva lo stesso identico difetto visivo poi trovato nella
           tab bar gemella della scheda personaggio: le pillole in eccesso
           finivano su una riga in più a piena larghezza, allungando
           verticalmente la barra ("si prende tutto lo schermo").
        2) Secondo fix, stesso giorno — `wrap=True` sostituito con `scroll=
           ft.ScrollMode.AUTO` sulla Row, dentro un Container con
           `bgcolor=surface_alt` (la "pista" beige dietro le pillole).
           Risolveva l'altezza, ma un nuovo screenshot di Davide ha
           mostrato quella pista allungarsi ben oltre le pillole vere,
           quasi fino al bordo della finestra ("quel alone allungato").
           Causa: un `SingleChildScrollView` orizzontale (quello che Flet
           genera per `scroll=...`) non si restringe MAI al contenuto
           lungo l'asse di scroll — prende sempre la larghezza massima
           concessa dal genitore, comportamento noto di Flutter, non un
           errore di configurazione. Il `Container` che gli dava lo sfondo
           beige, senza una larghezza propria, ereditava quella stessa
           larghezza "gonfiata" e la disegnava visibilmente anche dove non
           c'era nessuna pillola.
        3) Terzo fix, stesso giorno: tolto lo sfondo/bordo dall'involucro
           esterno — resta una Row scorrevole "nuda", nessun contenitore
           colorato che possa allargarsi in modo visibile. Ogni pillola
           porta il proprio sfondo quando attiva (`bgcolor=p.surface`,
           invariato: contrasta già bene con lo sfondo della pagina, non
           serviva cambiarlo qui — diverso da `SheetView`, il cui header è
           già `p.surface` e ha richiesto `p.surface_alt` per non sparire).
           Stesso principio di "Generatori Rapidi" (`design.pill()`): ogni
           pillola ha il proprio bordo/sfondo, MAI un contenitore che le
           racchiude tutte.
        4) FIX DEFINITIVO, sempre lo stesso giorno: lo scroll di per
           sé restava sbagliato — Davide ha fatto notare che, restringendo
           la finestra, le pillole "vengono tagliate o scompaiono", in
           contrasto con la preferenza già nota di questo progetto per
           un'interfaccia sempre visibile, mai azioni nascoste dietro uno
           scroll non scoperto. Sotto il breakpoint mobile dell'app
           (`self._compact_tabs`, passato da `DnDApp` con lo stesso
           `_MOBILE_BP = 600` di `ui/app.py`), ogni pillola mostra SOLO
           l'icona (tooltip con l'etichetta completa) — 5 pillole
           icona-sola stanno comodamente su una riga anche a 360-375px.
           Sopra il breakpoint, icona + etichetta come prima.
        5) FIX 2026-08-06 (sessione successiva) — `scroll=ft.ScrollMode.AUTO`
           sostituito da `wrap=True`: a schermo intero desktop la lista di 5
           etichette italiane di questa vista ("Rubrica NPC", "Incontri",
           "Note di Campagna", "Oggetti Magici", "Bottino") è più lunga di
           quella gemella della scheda personaggio, e lo scroll nascondeva
           silenziosamente le ultime pillole già a finestre desktop di
           larghezza moderata (non solo su smartphone) — bug reale
           segnalato da Davide con screenshot ("vengono tagliate le tab"),
           esattamente la stessa violazione di "nessuna azione nascosta"
           già corretta al punto 4 per il caso mobile, qui riemersa in un
           caso che quel fix non copriva. `wrap=True` non nasconde mai
           nulla: se le pillole non entrano su una riga, quelle in eccesso
           vanno sulla riga sotto — e lo fa in modo nativamente reattivo al
           ridimensionamento della finestra (è Flutter stesso a
           ricalcolare dove andare a capo ad ogni resize, nessun codice
           Python coinvolto), risolvendo anche il ridimensionamento dal
           vivo senza bisogno di ricostruire la vista. Il contenitore che
           avvolge questa Row è un figlio diretto della Column esterna
           (`self`, `MasterView(ft.Column, expand=True)`), quindi riceve
           già una larghezza vincolata dalla pagina — verificato
           empiricamente dal comportamento del vecchio bug "alone
           allungato" del punto 2 (uno `SingleChildScrollView` che si
           allarga fino al bordo della finestra lo fa SOLO se il genitore
           gli offre un vincolo di larghezza finito, non infinito): non è
           il caso strutturale già corretto in `profilo_tab.py` lo stesso
           giorno (`wrap=True` annidato dentro una Row non-expand, che dà
           larghezza illimitata). La modalità icona-sola sotto i 600px
           resta invariata (evita che 5 pillole con etichetta si
           impilino su altrettante righe su un telefono stretto): il wrap
           qui entra in gioco solo per la modalità con etichetta, sopra il
           breakpoint, quando la finestra desktop è comunque troppo stretta
           per contenerle tutte su una riga.
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
