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
from data.repositories import world_repo
from ui import design
from ui.widgets import wrap_dialog_actions
import core.character_stats as cs
from ui.components.roll_panel import show_roll
from core import world_sync
from core.world_backend import LocalBackend, RemoteBackend
from ui.components.background_sync import BackgroundSyncLoop
from ui.device_identity import resolve_device_id

logger = logging.getLogger(__name__)

#: Stesso intervallo già validato in `WorldsView`/`HomeView`
#: (`ui/views/world/world_view.py::_DETAIL_SYNC_INTERVAL_S`). Senza un
#: `BackgroundSyncLoop` qui, la scheda personaggio resterebbe l'unica vista
#: multiplayer priva di sincronizzazione: un giocatore che tiene la scheda
#: aperta non vedrebbe MAI un intervento del master (PF, condizioni,
#: risorse) finché non torna alla Home e ci rientra — o chiude e riapre la
#: scheda a mano.
_SHEET_SYNC_INTERVAL_S = 2.0

SHEET_TABS = [
    {"key": "profilo",       "label": "Profilo",       "icon": ft.Icons.PERSON_OUTLINE},
    {"key": "combattimento", "label": "Combattimento", "icon": ft.Icons.SHIELD_OUTLINED},
    {"key": "esplorazione",  "label": "Esplorazione",  "icon": ft.Icons.EXPLORE_OUTLINED},
    {"key": "inventario",    "label": "Inventario",    "icon": ft.Icons.BACKPACK_OUTLINED},
    {"key": "diario",        "label": "Diario",        "icon": ft.Icons.MENU_BOOK_OUTLINED},
]


class SheetView(ft.Column):
    """
    Vista principale della scheda personaggio.
    Gestisce la mini stat bar fissa e il routing tra i 5 tab.
    """

    def __init__(self, character: Character, proficiencies: list[CharacterProficiency],
                 is_mobile: bool = False, on_open_world=None):
        """
        `is_mobile` decide lo stile della tab bar — vedi il
        docstring di `_build_header_and_tabs()`. Passato da `DnDApp` con lo
        stesso breakpoint (`_MOBILE_BP = 600`, `ui/app.py`) già usato per
        scegliere tra sidebar e bottom nav — nessun nuovo concetto di
        "mobile", si riusa quello che l'app ha già. Default `False` per
        restare compatibile con i costruttori esistenti (test, chiamate
        legacy) che non lo passano.

        `on_open_world` (navigazione rapida): callback
        `(world_id) -> None` verso `DnDApp._show_worlds_view`, propagato
        dal pulsante "Vai al Mondo" nell'header — mostrato SOLO se
        `character.world_id` non è vuoto. `None` (default) nasconde il
        pulsante, stesso principio già usato per `on_toggle_theme` altrove.
        """
        super().__init__(expand=True, spacing=0)
        self.character = character
        self.proficiencies = proficiencies
        self.on_open_world = on_open_world
        self.active_tab = "profilo"
        self._tab_buttons: dict[str, ft.Container] = {}
        self._compact_tabs = is_mobile
        self._page: ft.Page | None = None
        self._stat_bar_container: ft.Container | None = None
        self._header_container: ft.Container | None = None

        # Sincronizzazione in background (vedi commento su
        # `_SHEET_SYNC_INTERVAL_S`) — stesso stato persistente (device_id,
        # cache backend remoti) già usato da `WorldsView`/`HomeView`, qui
        # scoped al SOLO mondo di questo personaggio (`character.world_id`).
        self.device_id: str | None = None
        self.backend = LocalBackend()
        self._remote_backends: dict[str, RemoteBackend] = {}
        self._sync_loop: BackgroundSyncLoop | None = None
        self._connection_state: str = "connected"

        self._build()

    def did_mount(self):
        self._page = cast(ft.Page, self.page)
        page = self.page
        if page is not None:
            page.run_task(self._init_world_sync)

    def will_unmount(self):
        self._stop_world_sync()

    async def _init_world_sync(self):
        """Risolve `device_id` e avvia la sincronizzazione in background —
        SOLO se questo personaggio appartiene a un mondo condiviso
        (`character.world_id` non vuoto). Un personaggio locale non ha
        nulla da sincronizzare."""
        if not self.character.world_id:
            return
        page = self.page
        if page is None:
            return
        self.device_id = await resolve_device_id(page)
        self._start_world_sync()

    # ------------------------------------------------------------------
    # Sincronizzazione automatica in background — stesso
    # pattern di `WorldsView._start_detail_sync`/`_stop_detail_sync`
    # (`ui/views/world/world_view.py`), qui scoped al mondo di QUESTO
    # personaggio: finché la scheda resta aperta, un thread dedicato scarica
    # gli eventi nuovi dall'host (interventi del master: PF, condizioni,
    # risorse) e li applica alla replica locale, senza richiedere al
    # giocatore di chiudere/riaprire la scheda o tornare alla Home.
    # ------------------------------------------------------------------

    def _start_world_sync(self):
        if self._sync_loop is not None or not self.character.world_id:
            return
        world_id = self.character.world_id

        def _apply() -> None:
            world = world_repo.get_world(world_id)
            if world is None or world.is_local_host:
                return
            backend = world_sync.resolve_backend_for_world(
                world, self.device_id or "", self.backend, self._remote_backends,
            )
            if backend is not None and isinstance(backend, RemoteBackend):
                self._connection_state = backend.connection_state()
                # BUG FIX (2026-08-24): va PRIMA di `sync_replica()` — vedi
                # il docstring identico in `diary_view.py::_start_world_sync`
                # per il bug che risolve (una scrittura self-service fatta
                # offline, ancora in coda, che un resync innescato da un
                # evento non correlato cancellerebbe).
                if self.device_id:
                    world_sync.push_pending_self_commands(backend, world_id, self.device_id)
                world_sync.sync_replica(backend, world_id)
            else:
                # Nessun backend risolvibile (host irraggiungibile, token
                # scaduto): senza aggiornare qui lo stato resterebbe
                # congelato sull'ultimo valore noto (LED verde stantio).
                # Stessa logica in `home_view.py`/`world_view.py`.
                self._connection_state = "disconnected"

        def _signature() -> str | None:
            updated = character_repo.get_by_id(self.character.id)
            if updated is None:
                return None
            conditions = character_repo.get_conditions(updated.id)
            cond_sig = "|".join(sorted(c.condition_key for c in conditions))
            # `last_synced_seq` invece di enumerare a mano ogni
            # campo che può cambiare via evento remoto — qualunque nuovo
            # evento applicato (incantesimo/abilità bonus, nota condivisa,
            # ecc.) incrementa questo numero, garantendo il ridisegno anche
            # per campi non coperti esplicitamente qui sopra.
            world = world_repo.get_world(self.character.world_id)
            seq = world.last_synced_seq if world is not None else 0
            return f"{updated.updated_at}|{self._connection_state}|{cond_sig}|{seq}"

        async def _redraw() -> None:
            self._soft_refresh()

        loop = BackgroundSyncLoop(
            get_page=lambda: self.page,
            signature_fn=_signature,
            async_redraw_fn=_redraw,
            apply_fn=_apply,
            interval_s=_SHEET_SYNC_INTERVAL_S,
            thread_name=f"sheet-sync-{self.character.id[:8]}",
        )
        self._sync_loop = loop
        loop.start()

    def _stop_world_sync(self):
        if self._sync_loop is not None:
            self._sync_loop.stop()
        self._sync_loop = None

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
        """
        Barra flottante delle caratteristiche: pannello elevato con i
        riquadri incassati (`surface_alt`), il punteggio in cifre tabellari
        e il modificatore in un chip d'accento — quello che il giocatore
        legge più spesso è anche l'elemento con più peso visivo.
        """
        p = design.T()
        # Il punteggio più alto ha un accento visivo: è in pratica quello
        # che il giocatore consulta/tira più spesso (caratteristica
        # principale della classe). Il primo punteggio più alto in ordine
        # FOR→CAR "vince" in caso di parità — scelta deterministica, non
        # serve altro criterio per un solo accento visivo in più su 6 celle.
        top_key = max(ABILITY_KEYS, key=lambda k: getattr(self.character, f"{k}_score"))
        boxes = []
        for abbr, key in zip(ABILITY_ABBR, ABILITY_KEYS):
            score = getattr(self.character, f"{key}_score")
            mod = get_modifier(score)
            mod_str = f"+{mod}" if mod >= 0 else str(mod)
            is_top = key == top_key
            boxes.append(
                ft.Container(
                    content=ft.Column(
                        [
                            # Icona matita: senza, nessun indizio visibile a
                            # colpo d'occhio che la cella sia editabile —
                            # stessa convenzione "✎" usata ovunque nell'app.
                            ft.Row(
                                [
                                    ft.Text(abbr, size=design.Size.LABEL,
                                            color=p.text_3,
                                            weight=ft.FontWeight.BOLD,
                                            font_family=design.Font.BODY,
                                            style=ft.TextStyle(letter_spacing=0.8)),
                                    ft.Icon(ft.Icons.EDIT, size=9, color=p.text_3),
                                ],
                                spacing=2, tight=True,
                                alignment=ft.MainAxisAlignment.CENTER,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            ft.Text(str(score), size=20, color=p.text,
                                    weight=ft.FontWeight.BOLD,
                                    text_align=ft.TextAlign.CENTER,
                                    font_family=design.Font.MONO),
                            # Il chip del modificatore è il pulsante di tiro
                            # (Fase 4, feature 1): due affordance distinte nello
                            # stesso riquadro — la matita in alto modifica il
                            # punteggio, il chip qui sotto tira la prova di
                            # caratteristica. L'icona del dado lo rende esplicito.
                            ft.Container(
                                content=ft.Row(
                                    [
                                        ft.Text(mod_str, size=design.Size.LABEL,
                                                color=p.magic,
                                                weight=ft.FontWeight.BOLD,
                                                font_family=design.Font.MONO,
                                                text_align=ft.TextAlign.CENTER),
                                        ft.Icon(ft.Icons.CASINO_OUTLINED, size=10,
                                                color=p.magic),
                                    ],
                                    spacing=3, tight=True,
                                    alignment=ft.MainAxisAlignment.CENTER,
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                ),
                                bgcolor=ft.Colors.with_opacity(0.12, p.magic),
                                border_radius=design.Radius.PILL,
                                padding=ft.Padding.symmetric(horizontal=8, vertical=1),
                                on_click=(lambda e, k=key: show_roll(
                                    self._page,
                                    cs.ability_check_roll(self.character, k))),
                                ink=True,
                                tooltip=f"Tira una prova di {cs.ability_label(key)}",
                            ),
                        ],
                        spacing=2,
                        tight=True,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.Padding.symmetric(vertical=design.Space.SM, horizontal=6),
                    # Cella del punteggio più alto leggermente sollevata
                    # rispetto alle altre 5 (bordo colorato + alone in
                    # scuro) invece che identica — vedi commento sopra.
                    # `bgcolor` resta SEMPRE `surface_alt` per tutte le 6
                    # celle: `surface` è più chiaro di `surface_alt` in
                    # tema chiaro ma più SCURO in tema scuro (verificato per
                    # luminanza relativa — DARK.surface=0.013,
                    # DARK.surface_alt=0.018), quindi uno swap `surface`/
                    # `surface_alt` per "sollevare" la cella avrebbe fatto
                    # l'opposto in scuro (cella evidenziata più scura, non
                    # più chiara). Bordo + `accent_glow()` non hanno questo
                    # problema: leggibili in entrambi i temi allo stesso
                    # modo. `primary_icon` perché è un bordo isolato su una
                    # superficie piccola, non testo scorrevole (soglia
                    # WCAG 3:1, non 4.5:1 — vedi Palette in ui/design.py).
                    bgcolor=p.surface_alt,
                    border=ft.Border.all(1, p.primary_icon) if is_top else None,
                    shadow=design.accent_glow(p.primary_icon, 2) if is_top else None,
                    border_radius=design.Radius.MD,
                    expand=True,
                    on_click=lambda e: self._open_ability_score_dialog(),
                    ink=True,
                    animate_scale=ft.Animation(design.Duration.FAST, design.CURVE),
                    tooltip="Clicca per modificare le caratteristiche",
                )
            )

        return ft.Container(
            content=ft.Row(boxes, spacing=design.Space.SM, expand=True),
            padding=ft.Padding.symmetric(horizontal=design.Space.MD,
                                         vertical=design.Space.MD),
            bgcolor=p.surface,
            shadow=design.elevation(2),
            border_radius=ft.BorderRadius.only(bottom_left=design.Radius.LG,
                                               bottom_right=design.Radius.LG),
        )

    # ------------------------------------------------------------------
    # Header personaggio + tab bar
    # ------------------------------------------------------------------

    def _build_header_and_tabs(self) -> ft.Container:
        c = self.character
        pb = char_prof_bonus(c)
        is_override = (c.proficiency_bonus_override or 0) > 0

        # Testo bonus competenza — cliccabile per override.
        # Icona matita sempre presente: senza di essa l'unico indizio che
        # sia cliccabile sarebbe il tooltip (visibile solo al passaggio del
        # mouse). `design.pill()` (Arcane Ledger) usa lo stesso linguaggio
        # visivo delle pillole "Lv./classe/razza" sotto, invece di un
        # Text+Icon nudo senza contorno.
        pb_btn = design.pill(
            ft.Icons.EDIT,
            f"+{pb} comp.",
            color=design.T().magic if is_override else design.T().text_2,
            on_click=lambda e: self._open_prof_bonus_dialog(),
            tooltip="Clicca per modificare il bonus competenza",
        )

        # LED di stato connessione — SOLO per un personaggio
        # che è la replica locale di un mondo ospitato da un ALTRO
        # dispositivo (`world_id` valorizzato e non ospitato qui): un
        # personaggio locale o ospitato da questo stesso dispositivo non ha
        # una "connessione" da monitorare. Colore aggiornato ad ogni giro
        # del loop avviato in `_start_world_sync` (vedi `self._connection_state`).
        name_row_children: list[ft.Control] = [
            ft.Text(c.name, size=18, weight=ft.FontWeight.BOLD,
                    color=design.T().text, font_family=design.Font.DISPLAY,
                    no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS, expand=True),
            pb_btn,
        ]
        if c.world_id:
            world = world_repo.get_world(c.world_id)
            if world is not None and not world.is_local_host:
                name_row_children.append(design.connection_led(self._connection_state))
            if self.on_open_world is not None:
                # Navigazione rapida: un tasto che porti velocemente alla
                # sezione mondo.
                name_row_children.append(ft.IconButton(
                    ft.Icons.PUBLIC, icon_size=18, icon_color=design.T().magic,
                    tooltip="Vai al Mondo",
                    on_click=lambda e: self.on_open_world(c.world_id),
                ))
        name_row = ft.Row(
            name_row_children,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        # Chip invece di una riga di testo con i "•": stesso linguaggio visivo
        # delle card della Home, e i tre dati si distinguono a colpo d'occhio.
        chips: list[ft.Control] = [
            design.chip(f"Lv. {c.level}", "primary"),
            design.chip(c.class_name + (f" · {c.subclass}" if c.subclass else ""), "magic"),
            design.chip(c.race + (f" · {c.subrace}" if c.subrace else ""), "neutral"),
        ]
        subtitle = ft.Row(chips, spacing=design.Space.XS, wrap=True)

        # Tab buttons
        tab_row = []
        self._tab_buttons = {}
        for tab in SHEET_TABS:
            btn = self._make_tab_button(tab["key"], tab["label"], tab["icon"])
            self._tab_buttons[tab["key"]] = btn
            tab_row.append(btn)

        p = design.T()
        return ft.Container(
            content=ft.Column(
                [
                    ft.Container(
                        content=ft.Column([name_row, subtitle],
                                          spacing=design.Space.SM),
                        padding=ft.Padding.only(left=design.Space.LG,
                                                right=design.Space.LG,
                                                top=design.Space.MD,
                                                bottom=design.Space.MD),
                    ),
                    # Controllo segmentato (pillole) invece dei tab sottolineati.
                    #
                    # `wrap=True` non va usato qui: le pillole in eccesso
                    # finirebbero su una riga in più a piena larghezza. Sotto
                    # il breakpoint mobile dell'app (`is_mobile`, stesso
                    # `_MOBILE_BP = 600` di `ui/app.py`), ogni pillola mostra
                    # SOLO l'icona (tooltip con l'etichetta completa) — 5
                    # pillole icona-sola stanno comodamente su una riga anche
                    # a 360-375px, la larghezza minima comune di uno
                    # smartphone. Sopra il breakpoint, icona + etichetta.
                    # `scroll=ft.ScrollMode.AUTO` resta come rete di
                    # sicurezza per casi patologici (font di sistema enormi,
                    # finestra sotto i 360px), non come meccanismo primario.
                    #
                    # Il fix con `wrap=True` resta solo in `MasterView`
                    # (`ui/views/master/master_view.py::_build_tab_bar()`,
                    # che ha etichette più lunghe) — NON applicarlo a questa
                    # Row: qui il comportamento voluto è quello sopra.
                    ft.Container(
                        content=ft.Row(tab_row, spacing=design.Space.XS,
                                       scroll=ft.ScrollMode.AUTO),
                        margin=ft.Margin.only(left=design.Space.MD,
                                              right=design.Space.MD,
                                              bottom=design.Space.MD),
                    ),
                ],
                spacing=0,
            ),
            bgcolor=p.surface,
            shadow=design.elevation(1),
        )

    def _style_tab_button(self, btn: ft.Container, active: bool) -> None:
        """Stile della pillola di tab — usato sia in costruzione sia al cambio tab.

        `p.surface_alt` per la pillola attiva, NON `p.surface`: l'header che
        contiene questa barra ha già `bgcolor=p.surface` (vedi
        `_build_header_and_tabs()`) — da
        quando l'involucro esterno beige è stato tolto, una pillola attiva
        con `bgcolor=p.surface` sarebbe risultata invisibile (bianco su
        bianco). `surface_alt` è lo stesso colore che prima dava lo sfondo
        all'intera barra: qui identifica solo la pillola selezionata,
        risultato visivo pressoché identico a prima ma senza il contenitore
        che si allargava oltre il contenuto.

        `btn.data` porta i riferimenti a icona/testo (impostati in
        `_make_tab_button()`) invece di leggere `btn.content` direttamente
        — necessario da quando la pillola può contenere solo un'icona
        (modalità compatta, `self._compact_tabs`), non più sempre un
        `ft.Text` isolato.
        """
        p = design.T()
        refs = cast(dict, btn.data)
        icon_ctrl = cast(ft.Icon, refs["icon"])
        text_ctrl = cast("ft.Text | None", refs["text"])
        color = p.primary if active else p.text_2
        icon_ctrl.color = color
        if text_ctrl is not None:
            text_ctrl.color = color
            text_ctrl.weight = ft.FontWeight.BOLD if active else ft.FontWeight.W_500
        btn.bgcolor = p.surface_alt if active else "transparent"
        btn.shadow = design.elevation(1) if active else None

    def _make_tab_button(self, key: str, label: str, icon: ft.IconData) -> ft.Container:
        """
        Pillola di tab — icona sempre presente, etichetta testuale SOLO se
        `self._compact_tabs` è `False` (vedi il commento su `wrap=True` in
        `_build_header_and_tabs()`).
        In modalità compatta l'etichetta completa resta comunque
        raggiungibile via `tooltip`, non è mai persa, solo non sempre
        visibile a colpo d'occhio: nessuna voce viene nascosta o rimossa
        dal controllo, tutte e 5 restano cliccabili sulla stessa riga.

        Niente `expand=True`: il Container si dimensiona sul contenuto,
        com'è già `design.pill()` — il genitore è una Row (con `scroll=
        ft.ScrollMode.AUTO` come sola rete di sicurezza, vedi sopra): ogni
        pillola deve restare larga quanto il proprio contenuto.
        """
        icon_ctrl = ft.Icon(icon, size=15)
        row_children: list[ft.Control] = [icon_ctrl]
        text_ctrl: ft.Text | None = None
        if not self._compact_tabs:
            text_ctrl = ft.Text(
                label,
                size=design.Size.LABEL + 1,
                text_align=ft.TextAlign.CENTER,
                font_family=design.Font.BODY,
                no_wrap=True,
                overflow=ft.TextOverflow.ELLIPSIS,
            )
            row_children.append(ft.Container(width=6))
            row_children.append(text_ctrl)

        btn = ft.Container(
            content=ft.Row(
                row_children, spacing=0, tight=True,
                alignment=ft.MainAxisAlignment.CENTER,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(
                horizontal=design.Space.SM if self._compact_tabs else design.Space.MD,
                vertical=design.Space.SM,
            ),
            border_radius=design.Radius.PILL,
            on_click=lambda e, k=key: self._switch_tab(k),
            ink=True,
            alignment=ft.Alignment.CENTER,
            animate=ft.Animation(design.Duration.BASE, design.CURVE),
            tooltip=label if self._compact_tabs else None,
        )
        btn.data = {"icon": icon_ctrl, "text": text_ctrl}
        self._style_tab_button(btn, key == self.active_tab)
        return btn

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
                text_style=ft.TextStyle(size=13, color=design.T().text),
                border_color=design.T().border,
                focused_border_color=design.T().magic,
                bgcolor=design.T().surface,
                label_style=ft.TextStyle(color=design.T().text_2),
                expand=True,
                border_radius=design.field_style()['border_radius'])

        error_text = ft.Text("", size=11, color=design.T().danger)

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
            title=design.dialog_title("Modifica Caratteristiche", ft.Icons.TUNE),
            content=ft.Column(
                [
                    ft.Text(
                        "Valori ammessi: 1–30  (house rules: nessun limite a 20)",
                        size=11, color=design.T().text_3,
                    ),
                    ft.Container(height=4),
                    ft.Row([fields["str"], fields["dex"], fields["con"]], spacing=10),
                    ft.Row([fields["int"], fields["wis"], fields["cha"]], spacing=10),
                    error_text,
                ],
                spacing=10,
            ),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla",
                              on_click=lambda ev: page.pop_dialog() if page else None),
                ft.ElevatedButton(
                    "Salva",
                    on_click=on_save,
                    style=ft.ButtonStyle(
                        bgcolor=design.T().primary_fill, color=design.T().on_primary_fill,
                    ),
                ),
            ]),
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
            text_style=ft.TextStyle(size=13, color=design.T().text),
            border_color=design.T().border,
            focused_border_color=design.T().magic,
            bgcolor=design.T().surface,
            label_style=ft.TextStyle(color=design.T().text_2),
            width=280,
            border_radius=design.field_style()['border_radius'])
        error_text = ft.Text("", size=11, color=design.T().danger)

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
            title=design.dialog_title("Bonus Competenza", ft.Icons.WORKSPACE_PREMIUM),
            content=ft.Column(
                [
                    ft.Text(
                        f"Standard PHB per Lv.{c.level}: +{standard_pb}",
                        size=12, color=design.T().text_2,
                    ),
                    ft.Text(
                        "Lascia vuoto per usare la tabella PHB standard. "
                        "Imposta un valore diverso per house rules.",
                        size=11, color=design.T().text_3,
                    ),
                    ft.Container(height=4),
                    tf,
                    error_text,
                ],
                spacing=8,
            ),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla",
                              on_click=lambda ev: page.pop_dialog() if page else None),
                ft.TextButton(
                    "Reset PHB",
                    on_click=on_reset_phb,
                    style=ft.ButtonStyle(color=design.T().text_3),
                ),
                ft.ElevatedButton(
                    "Salva",
                    on_click=on_save,
                    style=ft.ButtonStyle(
                        bgcolor=design.T().primary_fill, color=design.T().on_primary_fill,
                    ),
                ),
            ]),
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

    def _soft_refresh(self) -> None:
        """
        Refresh NON distruttivo, usato dal ciclo di sync in background: un
        refresh distruttivo qui produrrebbe un flash a schermo e riporterebbe
        la vista in cima ad ogni sincronizzazione. A differenza di
        `_refresh_all()` (usato dai
        dialog interni, azione rara e deliberata dell'utente), qui il tab
        corrente NON viene mai ricreato da zero: tutti e 5 i tab
        (`ProfiloTab`/`CombattimentoTab`/`EsplorazioneTab`/`InventarioTab`/
        `DiarioTab`) sono `ScrollMemoryListView` e già espongono un proprio
        `_refresh()` che ricarica i dati, ricostruisce SULLA STESSA istanza
        e chiude con `restore_scroll()` — richiamarlo invece di sostituire
        l'intero controllo evita che lo scroll dell'utente salti in cima
        solo perché è arrivato un evento remoto irrilevante per il tab
        aperto in quel momento.
        """
        self._refresh_bar_and_header()
        content = self.content_container.content
        tab_refresh = getattr(content, "_refresh", None)
        if callable(tab_refresh):
            tab_refresh()
            return
        # Tab placeholder senza un proprio _refresh() (non dovrebbe più
        # capitare: tutti e 5 i tab reali ce l'hanno) — fallback sicuro.
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
            self._style_tab_button(btn, k == key)

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
                    ft.Icon(icon, size=52, color=design.T().border),
                    ft.Container(height=12),
                    ft.Text(label, size=20, color=design.T().text_3),
                    ft.Container(height=8),
                    ft.Text("Sezione non disponibile.", size=13, color=design.T().text_3),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                expand=True,
            ),
        )
