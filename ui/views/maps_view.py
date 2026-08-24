"""
Sezione Mappe — sidebar key="maps".

Funzionalità:
  - Lista mappe con card/miniatura
  - Crea/modifica/elimina mappa
  - Dettaglio con layer di disegno freehand (flet.canvas)
  - Gomma "Tratto": elimina stroke intero al contatto
  - Gomma "Libera": cancella geometricamente i segmenti nel raggio
  - Slider per larghezza penna e dimensione gomma
  - Fullscreen overlay (page.overlay)
  - Annotazioni salvate come JSON in game_maps.annotations

Regole Flet 0.85.3:
  - ft.Image(src=data_uri), NON src_base64
  - page.show_dialog / page.pop_dialog
  - Selezione immagine: WebView locale su mobile (ui/mobile_webview_picker.py,
    ft.FilePicker abbandonato, confermato inutilizzabile su
    Android reale), subprocess nativo su desktop
  - expand=True su Column dentro Row dentro ListView → crash silenzioso → NON usare
  - ft.Paint / ft.PaintingStyle / ft.StrokeCap in flet principale, NON in flet.canvas
  - DragStartEvent / DragUpdateEvent usano local_position.x/.y (Offset object)
  - LISTVIEW: mai riassegnare self.controls, usare clear()+append()
"""

import base64
import json
import logging
import threading
from typing import Any, Optional, cast

import flet as ft

from core import world_sync
from core.world_backend import LocalBackend, RemoteBackend
from data.models import Character, GameMap
from data.repositories import maps_repo, world_repo
from ui.components.background_sync import BackgroundSyncLoop
from ui.components.map_drawing_canvas import MapDrawingCanvas, data_uri as _data_uri
from ui.device_identity import resolve_device_id
from ui.image_library import show_image_library_picker
from ui.mobile_webview_picker import pick_file_via_webview
from ui.native_image_picker import pick_image_native, ImagePickerUnavailable
from ui import design
from ui.widgets import ScrollMemoryListView, wrap_dialog_actions

logger = logging.getLogger(__name__)

#: Stesso intervallo già validato altrove (`sheet_view.py::_SHEET_SYNC_INTERVAL_S`).
#: Questa vista (sezione di primo livello, non un tab di `SheetView`) ha
#: bisogno di un proprio ciclo periodico per scaricare le mappe condivise,
#: altrimenti lo farebbe solo una volta al mount.
_MAPS_SYNC_INTERVAL_S = 2.0


# La geometria di disegno (gomma precisa, palette pennarello, data URI) e
# tutta la logica di canvas/toolbar/gesture vivono ora in
# `ui/components/map_drawing_canvas.py::MapDrawingCanvas` — condivise con
# `ui/views/world/world_view.py` (mappe condivise dal Master), invece di due
# copie divergenti. `_data_uri` resta importato con questo nome (alias di
# `map_drawing_canvas.data_uri`) per non toccare gli altri usi in questo file
# (miniature lista, anteprime nei dialog crea/modifica).

# La chrome dell'editor (barra strumenti scura sovrapposta alla mappa) vive in
# `ui/design.py → CHROME`: è volutamente scura in ENTRAMBI i temi.

# ── View principale ─────────────────────────────────────────────────────────

class MapsView(ft.Column):
    """
    Vista mappe. La logica di disegno (canvas/toolbar/gesture,
    Penna/Gomma/Sposta) vive in `self._canvas: MapDrawingCanvas | None` —
    vedi `ui/components/map_drawing_canvas.py`.
    """

    def __init__(self, character: Character):
        super().__init__(expand=True, spacing=0)
        self.character = character
        self._page: ft.Page | None = None
        self._maps: list[GameMap] = []
        # `ScrollMemoryListView`: `_refresh_shared_maps()` ricostruisce
        # questa lista ad ogni giro del ciclo di sync in background, un
        # `ft.ListView` semplice perderebbe lo scroll ogni volta.
        self._list_view = ScrollMemoryListView(expand=True, spacing=10, padding=16)

        # ── Stato disegno ──────────────────────────────────────────────
        #: `None` finché nessuna mappa è aperta in dettaglio — creato in
        #: `_open_detail()`, scartato in `_back_to_list()`. Un'unica
        #: istanza per l'intera apertura (pannello inline + eventuale
        #: schermo intero), vedi `ui/components/map_drawing_canvas.py`.
        self._canvas: MapDrawingCanvas | None = None
        self._current_gm: GameMap | None = None

        # Mappe condivise dal Master, mostrate qui SOLO se
        # `character.world_id` è valorizzato. Sola lettura qui (disegnare
        # resta compito del Master dalla Sezione Mondi): niente
        # GestureDetector nel viewer, solo immagine + annotazioni già
        # presenti. `backend`/`_remote_backends` servono solo per lo
        # scaricamento pigro dell'immagine (§6.4, stesso principio di
        # `WorldsView._open_shared_map`), mai per scrivere.
        self.device_id: str | None = None
        self.backend = LocalBackend()
        self._remote_backends: dict[str, RemoteBackend] = {}
        self._shared_maps: list[GameMap] = []
        self._sync_loop: BackgroundSyncLoop | None = None
        self._connection_state: str = "connected"

        # Nessun self._file_picker qui: ft.FilePicker non è utilizzabile su
        # Android reale (nessuna Activity nativa viene mai avviata). Su
        # Android/iOS la selezione passa da ui/mobile_webview_picker.py
        # (vedi _pick_mobile() sotto).

        self._build()

    def did_mount(self):
        self._page = cast(ft.Page, self.page)
        page = self.page
        if page is not None:
            page.run_task(self._init_world_sync)

    def will_unmount(self) -> None:
        self._stop_world_sync()

    async def _init_world_sync(self) -> None:
        if not self.character.world_id:
            return
        page = self.page
        if page is None:
            return
        self.device_id = await resolve_device_id(page)
        self._refresh_shared_maps()
        self._start_world_sync()

    def _start_world_sync(self) -> None:
        """Ciclo periodico (vedi `_MAPS_SYNC_INTERVAL_S`) —
        stesso pattern di `sheet_view.py::SheetView`/`spells_view.py::SpellsView`:
        finché la sezione Mappe resta aperta, scarica gli eventi nuovi
        dall'host (mappe condivise pubblicate/aggiornate dal master) e
        ridisegna, senza richiedere di uscire e rientrare nella sezione."""
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
                self._connection_state = "disconnected"

        def _signature() -> str | None:
            world = world_repo.get_world(world_id)
            seq = world.last_synced_seq if world is not None else 0
            return f"{self._connection_state}|{seq}"

        async def _redraw() -> None:
            self._refresh_shared_maps()

        loop = BackgroundSyncLoop(
            get_page=lambda: self.page,
            signature_fn=_signature,
            async_redraw_fn=_redraw,
            apply_fn=_apply,
            interval_s=_MAPS_SYNC_INTERVAL_S,
            thread_name=f"maps-sync-{self.character.id[:8]}",
        )
        self._sync_loop = loop
        loop.start()

    def _stop_world_sync(self) -> None:
        if self._sync_loop is not None:
            self._sync_loop.stop()
        self._sync_loop = None

    def _refresh_shared_maps(self) -> None:
        """Ricarica la lista mappe condivise visibili a questo giocatore e
        ridisegna — chiamata dal ciclo periodico di sync, dopo la
        risoluzione di `device_id`, e ad ogni chiusura del viewer di sola
        lettura."""
        if not self.character.world_id:
            return
        self._shared_maps = [
            m for m in maps_repo.get_shared_maps(self.character.world_id)
            if m.visible_to_players
        ]
        self._build()
        try:
            self.update()
        except RuntimeError:
            pass
        self._list_view.restore_scroll()

    # ------------------------------------------------------------------
    # Build root
    # ------------------------------------------------------------------

    def _build(self):
        # Mappe proprie + mappe condivise dal master, nella stessa lista
        # (con un chip che le distingue, vedi `_map_card`).
        # `self._shared_maps` è tenuta aggiornata dal
        # ciclo di sync in background (`_refresh_shared_maps`).
        self._maps = maps_repo.get_maps(self.character.id) + self._shared_maps
        self.controls.clear()
        self.controls.append(self._build_top_toolbar())
        self.controls.append(ft.Container(expand=True, content=self._build_list_panel()))

    def _open_shared_map_readonly(self, gm: GameMap) -> None:
        """
        Viewer di sola lettura per una mappa condivisa dal master —
        `MapDrawingCanvas(can_manage=False)`, stesso componente condiviso
        usato da `world_view.py::_open_shared_map(can_manage=False)`: niente
        `GestureDetector`/toolbar di disegno, solo immagine + annotazioni
        già presenti, riallineate col riquadro corrente per evitare
        disallineamenti cross-device.
        """
        page = self.page
        if page is None:
            return

        if not gm.image_data:
            world = world_repo.get_world(self.character.world_id)
            if world is not None and not world.is_local_host:
                backend = world_sync.resolve_backend_for_world(
                    world, self.device_id or "", self.backend, self._remote_backends,
                )
                if isinstance(backend, RemoteBackend):
                    raw = backend.fetch_map_image(gm.id)
                    if raw:
                        gm.image_data = base64.b64encode(raw).decode("ascii")
                        maps_repo.update_map(gm.id, image_data=gm.image_data)

        # Sola lettura: `on_batch=None` — `MapDrawingCanvas` non monta
        # alcun `GestureDetector`/toolbar in questo caso (vedi
        # `can_manage` nel suo `__init__`), esattamente come prima.
        ro_canvas = MapDrawingCanvas(gm, on_batch=None, can_manage=False)
        draw_stack = ro_canvas.build_draw_area(is_fs=True)

        overlay_list: list[ft.Control] = []

        def _close(e=None):
            if overlay_list and overlay_list[0] in page.overlay:
                page.overlay.remove(overlay_list[0])
            try:
                page.update()
            except RuntimeError:
                pass

        header = ft.Container(
            content=ft.Row(
                [
                    ft.Text(gm.name or "Mappa", size=16, color=design.CHROME.text,
                            weight=ft.FontWeight.BOLD, expand=True,
                            no_wrap=True, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                    design.chip("sola lettura", "neutral"),
                    ft.IconButton(ft.Icons.CLOSE, icon_color=design.CHROME.text, on_click=_close),
                ],
                spacing=design.Space.SM, vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=16, vertical=8),
            bgcolor=design.CHROME.backdrop,
        )
        overlay = ft.Container(
            expand=True, bgcolor=design.CHROME.canvas,
            content=ft.Column(
                [header, ft.Container(expand=True, content=draw_stack,
                                       on_size_change=lambda e: ro_canvas.on_box_resize(True, e))],
                spacing=0, expand=True,
            ),
        )
        overlay_list.append(overlay)
        page.overlay.append(overlay)
        try:
            page.update()
        except RuntimeError:
            pass

    def _build_top_toolbar(self) -> ft.Container:
        # Momento tipografico dominante della schermata (`hero_title()`,
        # Arcane Ledger) — prima un semplice `ft.Text` 16px, nessun titolo
        # della sezione risultava davvero "hero" rispetto al resto.
        return ft.Container(
            content=ft.Row(
                [
                    design.icon_badge(ft.Icons.MAP, tone="primary"),
                    ft.Container(width=design.Space.MD),
                    ft.Container(content=design.hero_title("Mappe"), expand=True),
                    ft.ElevatedButton(
                        "＋ Nuova Mappa", icon=ft.Icons.MAP,
                        on_click=lambda e: self._open_create_dialog(),
                        style=ft.ButtonStyle(
                            bgcolor=design.T().primary_fill, color=design.CHROME.text,
                        ),
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.only(left=16, right=16, top=16, bottom=16),
            bgcolor=design.T().surface_alt,
            border=ft.Border.only(bottom=ft.BorderSide(1, design.T().border)),
        )

    # ------------------------------------------------------------------
    # Lista mappe
    # ------------------------------------------------------------------

    def _build_list_panel(self) -> ft.Control:
        if not self._maps:
            return self._empty_state()
        self._list_view.controls.clear()
        for gm in self._maps:
            self._list_view.controls.append(self._map_card(gm))
        return self._list_view

    def _empty_state(self) -> ft.Container:
        return design.empty_state(
            ft.Icons.MAP_OUTLINED,
            "Nessuna mappa",
            "Carica la mappa della tua avventura e aggiungi annotazioni.",
            ft.ElevatedButton(
                "Carica prima mappa", icon=ft.Icons.ADD_PHOTO_ALTERNATE,
                on_click=lambda e: self._open_create_dialog(),
                style=ft.ButtonStyle(bgcolor=design.T().primary_fill,
                                     color=design.T().on_primary_fill),
            ),
        )

    def _map_card(self, gm: GameMap) -> ft.Container:
        # Mappa condivisa dal master, non posseduta da questo personaggio
        # (vedi `_build`): niente Modifica/Elimina (scrivere resta compito
        # del master), solo
        # apertura in sola lettura, con un chip a distinguerla.
        is_shared = gm.character_id != self.character.id
        if gm.image_data:
            thumb = ft.Container(
                content=ft.Image(src=_data_uri(gm.image_data), fit=ft.BoxFit.COVER),
                width=96, height=72, border_radius=design.Radius.MD,
                clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                shadow=design.elevation(1),
            )
        else:
            thumb = ft.Container(
                content=ft.Icon(ft.Icons.MAP_OUTLINED, size=28, color=design.T().text_3),
                width=96, height=72, border_radius=design.Radius.MD,
                bgcolor=design.T().surface_alt,
                shadow=design.elevation(1),
                alignment=ft.Alignment.CENTER,
            )

        n = len([s for s in json.loads(gm.annotations or "[]")
                 if s.get("type") == "stroke"])

        return design.card(
            ft.Row(
                [
                    thumb,
                    ft.Column(
                        [
                            ft.Text(gm.name or "Mappa senza nome", size=15,
                                    weight=ft.FontWeight.BOLD, color=design.T().text,
                                    font_family=design.Font.DISPLAY,
                                    no_wrap=True, max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS),
                            ft.Text((gm.notes or "—")[:80], size=design.Size.BODY_SM,
                                    color=design.T().text_3, max_lines=2),
                            ft.Row(
                                [
                                    ft.Container(
                                        content=design.chip(f"{n} annotazioni", "magic",
                                                            icon=ft.Icons.GESTURE),
                                        visible=bool(n),
                                    ),
                                    # Icona PUBLIC rimossa (audit anti-AI-slop): il testo
                                    # dice già esplicitamente lo stesso concetto — stesso
                                    # principio già applicato in
                                    # home_view.py::_section_label.
                                    ft.Container(
                                        content=design.chip("Condiviso dal Master", "primary"),
                                        visible=is_shared,
                                    ),
                                ],
                                spacing=6,
                            ),
                        ],
                        spacing=2, expand=True,
                    ),
                    ft.Column(
                        [
                            ft.IconButton(ft.Icons.OPEN_IN_FULL, icon_size=18,
                                          on_click=lambda e, m=gm: (
                                              self._open_shared_map_readonly(m) if is_shared
                                              else self._open_detail(m)
                                          ),
                                          icon_color=design.T().text_2),
                        ] + ([] if is_shared else [
                            ft.IconButton(ft.Icons.EDIT_OUTLINED, icon_size=18,
                                          on_click=lambda e, m=gm: self._open_edit_dialog(m),
                                          icon_color=design.T().text_2),
                            ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_size=18,
                                          on_click=lambda e, m=gm: self._confirm_delete(m),
                                          icon_color=design.T().danger_icon),
                        ]),
                        spacing=0,
                    ),
                ],
                spacing=12, vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            accent=design.T().primary,
            padding=design.Space.MD,
            on_click=lambda e, m=gm: (
                self._open_shared_map_readonly(m) if is_shared else self._open_detail(m)
            ),
        )

    # ------------------------------------------------------------------
    # Dettaglio mappa
    # ------------------------------------------------------------------

    def _open_detail(self, gm: GameMap):
        self._current_gm = gm
        # Mappa personale: qui la persistenza è sempre e solo locale —
        # a differenza del Master (`world_view.py::_open_shared_map`), il
        # giocatore non ha nulla da instradare verso un mondo per il
        # disegno sulla propria mappa.
        self._canvas = MapDrawingCanvas(
            gm, on_batch=lambda batch: maps_repo.apply_stroke_batch(gm.id, batch),
            can_manage=True,
        )
        self.controls[-1] = ft.Container(expand=True, content=self._build_detail_panel(gm))
        try:
            self.update()
        except RuntimeError:
            pass

    def _build_detail_panel(self, gm: GameMap) -> ft.Column:
        canvas = self._canvas
        assert canvas is not None
        draw_area = canvas.build_draw_area(is_fs=False)
        toolbar_row, toolbar_body = canvas.build_toolbar(is_fs=False)

        notes_tf = ft.TextField(
            value=gm.notes or "", multiline=True, min_lines=2, max_lines=6,
            hint_text="Note sulla mappa…",
            **design.field_style())

        def save_notes(ev):
            maps_repo.update_map(gm.id, notes=notes_tf.value or "")
            gm.notes = notes_tf.value or ""

        header_row = ft.Row(
            [
                ft.IconButton(ft.Icons.ARROW_BACK, tooltip="Lista mappe",
                              on_click=lambda e: self._back_to_list(),
                              icon_color=design.T().text_2),
                ft.Text(gm.name or "Mappa", size=16, weight=ft.FontWeight.BOLD,
                        color=design.T().text, font_family=design.Font.DISPLAY,
                        expand=True,
                        no_wrap=True, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                ft.IconButton(ft.Icons.FULLSCREEN, tooltip="Schermo intero",
                              on_click=lambda e: self._open_fullscreen(gm),
                              icon_color=design.T().text_2),
                ft.TextButton("✎ Modifica", on_click=lambda e: self._open_edit_dialog(gm),
                              style=ft.ButtonStyle(color=design.T().text_3)),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        legacy_banner = canvas.build_legacy_banner()
        return ft.Column(
            [
                ft.Container(
                    content=header_row, bgcolor=design.T().surface,
                    padding=ft.Padding.only(left=design.Space.SM, right=design.Space.SM,
                                            top=design.Space.SM, bottom=design.Space.SM),
                    shadow=design.elevation(1),
                ),
                *([legacy_banner] if legacy_banner is not None else []),
                # L'area di disegno è scura: fa risaltare la mappa e i tratti
                # chiari, e stacca l'immagine dal fondo pergamena della scheda.
                ft.Container(expand=True, content=draw_area,
                             bgcolor=design.CHROME.backdrop,
                             on_size_change=lambda e: canvas.on_box_resize(False, e)),
                # Barra strumenti: pannello scuro flottante, angoli superiori
                # arrotondati e ombra verso l'alto — "posata" sopra la mappa
                # invece di incollata al bordo con un filo da 1px.
                ft.Container(
                    content=ft.Column([toolbar_row, toolbar_body], spacing=0),
                    bgcolor=design.CHROME.bg,
                    border_radius=ft.BorderRadius.only(
                        top_left=design.Radius.LG, top_right=design.Radius.LG),
                    shadow=ft.BoxShadow(blur_radius=18, spread_radius=0,
                                        offset=ft.Offset(0, -4),
                                        color=ft.Colors.with_opacity(0.45, design.CHROME.canvas)),
                ),
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text("NOTE", size=9, color=design.T().text_3,
                                    weight=ft.FontWeight.BOLD,
                                    style=ft.TextStyle(letter_spacing=0.8)),
                            notes_tf,
                            ft.Row([ft.ElevatedButton(
                                "Salva note", on_click=save_notes,
                                style=ft.ButtonStyle(
                                    bgcolor=design.T().primary_fill, color=design.CHROME.text,
                                ),
                            )], alignment=ft.MainAxisAlignment.END),
                        ],
                        spacing=6,
                    ),
                    padding=12, bgcolor=design.T().surface,
                    border=ft.Border.only(top=ft.BorderSide(1, design.T().border)),
                ),
            ],
            expand=True, spacing=0,
        )

    def _back_to_list(self):
        self._canvas = None
        self._current_gm = None
        # BUG FIX (2026-08-20): mancava `+ self._shared_maps` (presente in
        # `_build()`, la formula corretta) — tornare alla lista dopo aver
        # aperto/creato una mappa PERSONALE faceva sparire dalla vista ogni
        # mappa CONDIVISA dal master, senza autoripararsi: il ciclo di sync
        # periodico (`_start_world_sync`) richiama `_refresh_shared_maps()`
        # (che l'avrebbe corretto) solo quando `_signature()` cambia, cioè
        # solo su un nuovo evento nel giornale del mondo — un'azione
        # puramente locale come caricare una mappa propria non ne genera
        # mai uno, quindi la mappa condivisa restava assente a tempo
        # indeterminato, non solo per un istante. Bug report Davide:
        # "carico manualmente una terza mappa, la mappa condivisa
        # sparisce e rimangono solo le 2 mappe locali".
        self._maps = maps_repo.get_maps(self.character.id) + self._shared_maps
        self.controls[-1] = ft.Container(expand=True, content=self._build_list_panel())
        try:
            self.update()
        except RuntimeError:
            pass

    # ------------------------------------------------------------------
    # Fullscreen overlay
    # ------------------------------------------------------------------

    def _open_fullscreen(self, gm: GameMap):
        page = self._page
        canvas = self._canvas
        if page is None or canvas is None:
            return

        fs_draw_area = canvas.build_draw_area(is_fs=True)
        fs_toolbar_row, fs_toolbar_body = canvas.build_toolbar(is_fs=True)

        overlay_list: list[ft.Control] = []

        def close_fs(e: Any = None):
            if overlay_list and overlay_list[0] in page.overlay:
                page.overlay.remove(overlay_list[0])
            canvas.teardown_fullscreen()
            page.update()

        header = ft.Container(
            content=ft.Row(
                [
                    ft.Text(gm.name or "Mappa", size=16, color=design.CHROME.text,
                            weight=ft.FontWeight.BOLD, expand=True,
                            no_wrap=True, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                    ft.IconButton(ft.Icons.FULLSCREEN_EXIT, icon_color=design.CHROME.text,
                                  on_click=close_fs),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=16, vertical=8),
            bgcolor=design.CHROME.backdrop,
        )

        fs_legacy_banner = canvas.build_legacy_banner()
        overlay = ft.Container(
            expand=True, bgcolor=design.CHROME.canvas,
            content=ft.Column(
                [
                    header,
                    *([fs_legacy_banner] if fs_legacy_banner is not None else []),
                    ft.Container(expand=True, content=fs_draw_area,
                                 on_size_change=lambda e: canvas.on_box_resize(True, e)),
                    ft.Container(
                        content=ft.Column(
                            [fs_toolbar_row, fs_toolbar_body], spacing=0),
                        bgcolor=design.CHROME.bg,
                        border_radius=ft.BorderRadius.only(
                            top_left=design.Radius.LG, top_right=design.Radius.LG),
                        shadow=ft.BoxShadow(blur_radius=18, spread_radius=0,
                                            offset=ft.Offset(0, -4),
                                            color=ft.Colors.with_opacity(0.45, design.CHROME.canvas)),
                    ),
                ],
                spacing=0, expand=True,
            ),
        )

        overlay_list.append(overlay)
        page.overlay.append(overlay)
        page.update()

    # ------------------------------------------------------------------
    # Dialog — Crea mappa
    # ------------------------------------------------------------------

    def _open_create_dialog(self):
        page = self._page
        if page is None:
            return

        name_tf = ft.TextField(
            label="Nome mappa",
            label_style=ft.TextStyle(color=design.T().text_2),
            **design.field_style())
        notes_tf = ft.TextField(
            label="Note (opzionale)", multiline=True, min_lines=2, max_lines=5,
            label_style=ft.TextStyle(color=design.T().text_2),
            **design.field_style())
        img_data: list[str] = [""]
        img_label  = ft.Text("Nessuna immagine", size=11, color=design.T().text_3)
        img_preview = ft.Container(
            content=ft.Icon(ft.Icons.IMAGE_OUTLINED, size=48, color=design.T().border),
            width=120, height=80, bgcolor=design.T().surface_alt,
            shadow=design.elevation(1), border_radius=design.Radius.MD,
            alignment=ft.Alignment.CENTER,
        )
        error_text = ft.Text("", size=11, color=design.T().danger)

        def pick_image(ev: Any):
            if page.web:
                _pick_from_library(self._page, img_data, img_label, img_preview)
            elif page.platform in (ft.PagePlatform.ANDROID, ft.PagePlatform.IOS):
                # _pick_mobile è async (vedi il suo
                # docstring): va schedulata, non chiamata direttamente da
                # un on_click sincrono.
                page.run_task(_pick_mobile, self._page, img_data, img_label, img_preview)
            else:
                import platform as _sys
                threading.Thread(
                    target=_pick_desktop,
                    args=(_sys.system(), img_data, img_label, img_preview, page),
                    daemon=True,
                ).start()

        def on_save(ev: Any):
            name = (name_tf.value or "").strip()
            if not name:
                error_text.value = "Il nome è obbligatorio"
                error_text.update()
                return
            gm = maps_repo.create_map(
                character_id=self.character.id, name=name,
                image_data=img_data[0], notes=(notes_tf.value or "").strip(),
            )
            if gm:
                page.pop_dialog()
                self._back_to_list()
            else:
                error_text.value = "Errore durante il salvataggio"
                error_text.update()

        page.show_dialog(ft.AlertDialog(
            title=design.dialog_title("Nuova Mappa", ft.Icons.ADD_LOCATION_ALT),
            content=ft.Column(
                [
                    name_tf, notes_tf, ft.Container(height=4),
                    ft.Row(
                        [
                            img_preview,
                            ft.Column([
                                ft.OutlinedButton(
                                    "Scegli immagine…",
                                    icon=ft.Icons.ADD_PHOTO_ALTERNATE,
                                    on_click=pick_image,
                                    style=ft.ButtonStyle(
                                        side=ft.BorderSide(1, design.T().border),
                                        color=design.T().text_2,
                                    ),
                                ),
                                img_label,
                            ], spacing=6),
                        ],
                        spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    error_text,
                ],
                spacing=10, scroll=ft.ScrollMode.AUTO,
            ),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda ev: page.pop_dialog()),
                ft.ElevatedButton("Salva", on_click=on_save,
                                  style=ft.ButtonStyle(
                                      bgcolor=design.T().primary_fill, color=design.CHROME.text)),
            ]),
        ))

    # ------------------------------------------------------------------
    # Dialog — Modifica mappa
    # ------------------------------------------------------------------

    def _open_edit_dialog(self, gm: GameMap):
        page = self._page
        if page is None:
            return

        name_tf = ft.TextField(
            label="Nome mappa", value=gm.name or "",
            label_style=ft.TextStyle(color=design.T().text_2),
            **design.field_style())
        notes_tf = ft.TextField(
            label="Note", value=gm.notes or "",
            multiline=True, min_lines=2, max_lines=5,
            label_style=ft.TextStyle(color=design.T().text_2),
            **design.field_style())
        img_data: list[str] = [gm.image_data or ""]
        img_label = ft.Text(
            "Immagine corrente" if gm.image_data else "Nessuna immagine",
            size=11, color=design.T().text_3,
        )
        if gm.image_data:
            img_preview: ft.Container = ft.Container(
                content=ft.Image(src=_data_uri(gm.image_data), fit=ft.BoxFit.COVER),
                width=120, height=80, border_radius=design.Radius.MD,
                clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                border=ft.Border.all(1, design.T().border),
            )
        else:
            img_preview = ft.Container(
                content=ft.Icon(ft.Icons.IMAGE_OUTLINED, size=48, color=design.T().border),
                width=120, height=80, bgcolor=design.T().surface_alt,
                shadow=design.elevation(1), border_radius=design.Radius.MD,
                alignment=ft.Alignment.CENTER,
            )
        error_text = ft.Text("", size=11, color=design.T().danger)

        def pick_image(ev: Any):
            if page.web:
                _pick_from_library(self._page, img_data, img_label, img_preview)
            elif page.platform in (ft.PagePlatform.ANDROID, ft.PagePlatform.IOS):
                # _pick_mobile è async (vedi il suo
                # docstring): va schedulata, non chiamata direttamente da
                # un on_click sincrono.
                page.run_task(_pick_mobile, self._page, img_data, img_label, img_preview)
            else:
                import platform as _sys
                threading.Thread(
                    target=_pick_desktop,
                    args=(_sys.system(), img_data, img_label, img_preview, page),
                    daemon=True,
                ).start()

        def on_save(ev: Any):
            name = (name_tf.value or "").strip()
            if not name:
                error_text.value = "Il nome è obbligatorio"
                error_text.update()
                return
            maps_repo.update_map(
                gm.id, name=name,
                image_data=img_data[0] if img_data[0] else None,
                notes=(notes_tf.value or "").strip(),
            )
            gm.name = name
            gm.notes = (notes_tf.value or "").strip()
            if img_data[0]:
                gm.image_data = img_data[0]
            page.pop_dialog()
            self._back_to_list()

        page.show_dialog(ft.AlertDialog(
            title=design.dialog_title("Modifica Mappa", ft.Icons.EDIT_LOCATION_ALT),
            content=ft.Column(
                [
                    name_tf, notes_tf, ft.Container(height=4),
                    ft.Row(
                        [
                            img_preview,
                            ft.Column([
                                ft.OutlinedButton(
                                    "Cambia immagine…",
                                    icon=ft.Icons.ADD_PHOTO_ALTERNATE,
                                    on_click=pick_image,
                                    style=ft.ButtonStyle(
                                        side=ft.BorderSide(1, design.T().border),
                                        color=design.T().text_2,
                                    ),
                                ),
                                img_label,
                            ], spacing=6),
                        ],
                        spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    error_text,
                ],
                spacing=10, scroll=ft.ScrollMode.AUTO,
            ),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda ev: page.pop_dialog()),
                ft.ElevatedButton("Salva", on_click=on_save,
                                  style=ft.ButtonStyle(
                                      bgcolor=design.T().primary_fill, color=design.CHROME.text)),
            ]),
        ))

    # ------------------------------------------------------------------
    # Dialog — Elimina mappa
    # ------------------------------------------------------------------

    def _confirm_delete(self, gm: GameMap):
        page = self._page
        if page is None:
            return

        def do_delete(ev: Any):
            maps_repo.delete_map(gm.id)
            page.pop_dialog()
            self._back_to_list()

        page.show_dialog(ft.AlertDialog(
            title=design.dialog_title("Elimina Mappa", ft.Icons.DELETE_FOREVER, tone="danger"),
            content=ft.Text(
                f'Eliminare "{gm.name}"?\nVerranno rimossi anche tutti i disegni.',
                size=13, color=design.T().text,
            ),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda ev: page.pop_dialog()),
                ft.ElevatedButton("Elimina", on_click=do_delete,
                                  style=ft.ButtonStyle(
                                      bgcolor=design.T().danger_fill, color=design.CHROME.text)),
            ]),
        ))


# ── File picker helpers ────────────────────────────────────────────────────

def _normalize_image_bytes_to_base64(raw: bytes) -> str:
    """
    Normalizza bytes immagine in JPEG via PIL e li codifica in base64.

    Separata da _load_image_base64() per essere condivisa
    anche dal flusso WebView (_pick_mobile()), che riceve i bytes
    dell'immagine direttamente (FileReader lato browser) invece di un
    percorso file locale da aprire.
    """
    try:
        from PIL import Image as PILImage  # type: ignore[import-untyped]
        from PIL import ImageOps  # type: ignore[import-untyped]
        import io
        with PILImage.open(io.BytesIO(raw)) as im:
            # Applica la rotazione EXIF prima di ri-salvare — stesso fix di
            # profilo_tab.py::_save_photo_bytes(): senza questo, immagini
            # scattate in verticale da smartphone vengono salvate ruotate,
            # perché il tag "Orientation" va perso al salvataggio se non
            # applicato esplicitamente prima.
            im = ImageOps.exif_transpose(im)
            if im.mode not in ("RGB", "L"):
                im = im.convert("RGB")
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=85)
            return base64.b64encode(buf.getvalue()).decode()
    except ImportError:
        return base64.b64encode(raw).decode()
    except Exception as exc:
        logger.error("_normalize_image_bytes_to_base64: %s", exc)
        return ""


def _load_image_base64(path: str) -> str:
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except Exception as exc:
        logger.error("_load_image_base64(%s): %s", path, exc)
        return ""
    return _normalize_image_bytes_to_base64(raw)


def _update_preview(b64: str, label: ft.Text,
                    preview: ft.Container, page: ft.Page):
    if not b64:
        return
    try:
        label.value = "Immagine caricata ✓"
        preview.content = ft.Image(src=_data_uri(b64), fit=ft.BoxFit.COVER)
        preview.clip_behavior = ft.ClipBehavior.ANTI_ALIAS
        page.update()
    except Exception as exc:
        logger.error("_update_preview: %s", exc)


def _pick_from_library(page: ft.Page | None, img_data: list[str],
                       label: ft.Text, preview: ft.Container):
    """
    Ramo web (page.web == True): mostra il picker sulla libreria immagini
    caricata manualmente (vedi ui/image_library.py) invece di
    `ft.FilePicker` — che in modalità web è strutturalmente rotto e non
    risolvibile lato applicazione (bug upstream confermato, flet-dev/flet
    #6040/#6250/#6251 — vedi `dnd_app/docs/changelog_storico.md` per il
    dettaglio). Selezionare un'immagine richiama la stessa identica logica
    già usata per il path locale su mobile nativo (_load_image_base64() +
    _update_preview()).

    Parametro `page` diretto (non un `MapsView`): riusata anche da
    `ui/views/world/world_view.py` per il caricamento di una mappa
    condivisa nuova, che non ha un `MapsView` a disposizione — l'unica cosa
    che questa funzione usava della view era `view._page`.
    """
    if page is None:
        return

    def on_select(path: str):
        b64 = _load_image_base64(path)
        if b64:
            img_data[0] = b64
            _update_preview(b64, label, preview, page)

    show_image_library_picker(page, on_select=on_select)


async def _pick_mobile(page: ft.Page | None, img_data: list[str],
                       label: ft.Text, preview: ft.Container) -> None:
    """
    Apre il selettore immagine su Android/iOS. Chiamata SOLO dal ramo
    mobile nativo di pick_image() nei due dialog crea/modifica mappa — il
    ramo web non arriva mai qui, vedi _pick_from_library(). Parametro
    `page` diretto (non un `MapsView`) — vedi il docstring gemello su
    `_pick_from_library` per il perché.

    Prova prima l'estensione Flet nativa scritta su misura
    (`ui/native_image_picker.py` -> `dnd_app/extensions/flet_image_picker/`;
    ⚠️ non verificata end-to-end, nessun toolchain Flutter/Dart disponibile
    per compilarla qui — vedi il docstring del modulo). Se solleva
    `ImagePickerUnavailable`, ricade sul fallback WebView (vedi
    `ui/mobile_webview_picker.py` per il perché non `ft.FilePicker` e per
    come funziona questo fallback). Stesso identico pattern di
    `profilo_tab.py::_pick_photo_mobile()`, mantenuto qui in un file
    diverso perché `_pick_mobile()` è una funzione modulo-level (non un
    metodo di `MapsView`), condivisa dai due dialog crea/modifica mappa.
    """
    if page is None:
        return

    raw: Optional[bytes] = None
    try:
        raw = await pick_image_native(page)
    except ImagePickerUnavailable as ex:
        logger.warning(
            "_pick_mobile: ImagePicker nativo non disponibile (%s); "
            "ricado sul fallback WebView.", ex,
        )
        result = await pick_file_via_webview(
            page, accept="image/*", title="Scegli immagine mappa",
        )
        if result is None:
            return  # utente ha annullato, o errore già loggato nel modulo
        _name, b64_content = result
        try:
            raw = base64.b64decode(b64_content)
        except Exception as exc:
            logger.error("_pick_mobile: base64 non decodificabile: %s", exc)
            return

    if raw is None:
        return  # utente ha annullato la selezione nativa
    b64 = _normalize_image_bytes_to_base64(raw)
    if b64:
        img_data[0] = b64
        _update_preview(b64, label, preview, page)


def _pick_desktop(system: str, img_data: list[str],
                  label: ft.Text, preview: ft.Container, page: ft.Page):
    import subprocess
    path: str | None = None
    try:
        if system == "Darwin":
            r = subprocess.run(
                ["osascript", "-e",
                 'tell application "System Events"\nactivate\n'
                 'set f to choose file with prompt "Seleziona immagine mappa" '
                 'of type {"public.image"}\nreturn POSIX path of f\nend tell'],
                capture_output=True, text=True, timeout=60,
            )
            if r.returncode == 0:
                path = r.stdout.strip()
        elif system == "Windows":
            ps = (
                "Add-Type -AssemblyName System.Windows.Forms; "
                "$d = New-Object System.Windows.Forms.OpenFileDialog; "
                "$d.Filter = 'Immagini|*.jpg;*.jpeg;*.png;*.gif;*.webp'; "
                "if ($d.ShowDialog() -eq 'OK') { Write-Output $d.FileName }"
            )
            r = subprocess.run(["powershell", "-Command", ps],
                               capture_output=True, text=True, timeout=60)
            if r.returncode == 0 and r.stdout.strip():
                path = r.stdout.strip()
        else:
            for cmd in (
                ["zenity", "--file-selection", "--title=Seleziona immagine mappa",
                 "--file-filter=*.jpg *.jpeg *.png *.gif *.webp"],
                ["kdialog", "--getopenfilename", ".", "*.jpg *.jpeg *.png"],
            ):
                try:
                    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                    if r.returncode == 0 and r.stdout.strip():
                        path = r.stdout.strip()
                        break
                except FileNotFoundError:
                    continue
    except Exception as exc:
        logger.error("_pick_desktop: %s", exc)

    if path:
        b64 = _load_image_base64(path)
        if b64:
            img_data[0] = b64
            _update_preview(b64, label, preview, page)
