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
    ft.FilePicker abbandonato dal 2026-08-06, confermato inutilizzabile su
    Android reale), subprocess nativo su desktop
  - expand=True su Column dentro Row dentro ListView → crash silenzioso → NON usare
  - ft.Paint / ft.PaintingStyle / ft.StrokeCap in flet principale, NON in flet.canvas
  - DragStartEvent / DragUpdateEvent usano local_position.x/.y (Offset object)
  - LISTVIEW: mai riassegnare self.controls, usare clear()+append()
"""

import base64
import json
import logging
import math
import threading
from typing import Any, Optional, cast

import flet as ft
import flet.canvas as cv

from core import world_sync
from core.image_utils import sniff_mime
from core.world_backend import LocalBackend, RemoteBackend
from data.models import Character, GameMap
from data.repositories import maps_repo, world_repo
from ui import canvas_geometry as geo
from ui.components.background_sync import BackgroundSyncLoop
from ui.device_identity import resolve_device_id
from ui.image_library import show_image_library_picker
from ui.mobile_webview_picker import pick_file_via_webview
from ui.native_image_picker import pick_image_native, ImagePickerUnavailable
from ui import design
from ui.widgets import ScrollMemoryListView, wrap_dialog_actions

logger = logging.getLogger(__name__)

#: Stesso intervallo già validato altrove (`sheet_view.py::_SHEET_SYNC_INTERVAL_S`)
#: — bug segnalato da Davide (2026-08-16): "sincronizzazione mappa
#: condivisa non coerente, aggiornamento manuale per vederla". Questa vista
#: (sezione di primo livello, non un tab di `SheetView`) scaricava le
#: mappe condivise solo una volta al mount, mai in un ciclo periodico.
_MAPS_SYNC_INTERVAL_S = 2.0


# ── Geometria gomma precisa ────────────────────────────────────────────────

def _circle_segment_ts(px1: float, py1: float, px2: float, py2: float,
                        cx: float, cy: float, r: float) -> list[float]:
    """
    Parametri t ∈ [0,1] dove il segmento P1→P2 interseca il cerchio (cx,cy,r).
    Ritorna lista vuota se nessuna intersezione, [t] o [t1,t2] altrimenti.
    """
    dx, dy = px2 - px1, py2 - py1
    fx, fy = px1 - cx, py1 - cy
    a = dx * dx + dy * dy
    if a < 1e-12:
        return []
    b = 2.0 * (fx * dx + fy * dy)
    c = fx * fx + fy * fy - r * r
    disc = b * b - 4.0 * a * c
    if disc < 0.0:
        return []
    sq = math.sqrt(max(disc, 0.0))
    ts = [(-b - sq) / (2.0 * a), (-b + sq) / (2.0 * a)]
    return sorted(t for t in ts if 0.0 <= t <= 1.0)


def _split_stroke_by_circle(pts: list, cx: float, cy: float,
                              r: float) -> list[list[list[float]]]:
    """
    Divide una sequenza di punti in sub-sequenze esterne al cerchio (cx,cy,r).
    Ritorna [[pts]] invariato se nessuna modifica, altrimenti la lista di sub-stroke.
    Il taglio avviene esattamente all'intersezione geometrica (non per approssimazione).
    """
    result: list[list[list[float]]] = []
    current: list[list[float]] = []
    any_change = False

    def flush():
        if len(current) >= 2:
            result.append(current[:])
        current.clear()

    for i, p in enumerate(pts):
        p_in = math.hypot(p[0] - cx, p[1] - cy) <= r

        if i == 0:
            if not p_in:
                current.append(p)
            else:
                any_change = True
            continue

        prev = pts[i - 1]
        prev_in = math.hypot(prev[0] - cx, prev[1] - cy) <= r
        ts = _circle_segment_ts(prev[0], prev[1], p[0], p[1], cx, cy, r)
        dx, dy = p[0] - prev[0], p[1] - prev[1]

        if not prev_in and not p_in and not ts:
            # Segmento completamente fuori: accoda
            current.append(p)
        elif prev_in and p_in and not ts:
            # Segmento completamente dentro: scarta
            any_change = True
            flush()
        else:
            # Segmento misto: spezza agli eventi [0, ts..., 1]
            any_change = True
            events = [0.0] + ts + [1.0]
            for j in range(len(events) - 1):
                t0, t1 = events[j], events[j + 1]
                mid_t = (t0 + t1) * 0.5
                mid_in = math.hypot(prev[0] + mid_t*dx - cx,
                                     prev[1] + mid_t*dy - cy) <= r
                pt0 = [prev[0] + t0*dx, prev[1] + t0*dy]
                pt1 = [prev[0] + t1*dx, prev[1] + t1*dy]
                if mid_in:
                    # Sotto-segmento da cancellare
                    if current:
                        if current[-1] != pt0:
                            current.append(pt0)
                        flush()
                else:
                    # Sotto-segmento da tenere
                    if not current or current[-1] != pt0:
                        current.append(pt0)
                    current.append(pt1)

    flush()

    if not any_change:
        return [pts]
    return result


# ── Palette ────────────────────────────────────────────────────────────────
# ⚠️ Questi NON sono token di tema e non vanno migrati a `ui/design.py`
# (Fase B.2 del restyle, 2026-07-30): sono i colori del PENNARELLO scelti dal
# giocatore e vengono **persistiti** dentro `game_maps.annotations` come valore
# di ogni tratto. Cambiarli o renderli dipendenti dal tema romperebbe le
# annotazioni già salvate (un tratto rosso diventerebbe di un altro colore, o
# cambierebbe colore accendendo il tema scuro).
_PEN_COLORS = [
    "#e53935",  # rosso
    "#1e88e5",  # blu
    "#43a047",  # verde
    "#fb8c00",  # arancio
    "#9c27b0",  # viola
    "#ffffff",  # bianco
    "#212121",  # nero
]

# La chrome dell'editor (barra strumenti scura sovrapposta alla mappa) vive in
# `ui/design.py → CHROME`: è volutamente scura in ENTRAMBI i temi, ma non è più
# un dizionario di hex dentro questa view.

# ── Data URI helper ────────────────────────────────────────────────────────
def _data_uri(b64: str) -> str:
    try:
        mime = sniff_mime(base64.b64decode(b64[:16] + "=="))
    except Exception:
        mime = "image/jpeg"
    return f"data:{mime};base64,{b64}"


# ── View principale ─────────────────────────────────────────────────────────

class MapsView(ft.Column):
    """
    Vista mappe.
    Modalità disegno: pen | eraser
    Eraser sub-mode: stroke (cancella tratto intero) | pixel (gomma libera precisa)
    """

    _MODE_DEFS = [
        ("pen",    ft.Icons.EDIT,            "Penna"),
        ("eraser", ft.Icons.AUTO_FIX_NORMAL, "Gomma"),
        # "Sposta" (2026-08-19, zoom/pan — bug segnalato da Davide: "è
        # impossibile zoommare la mappa"): un trascinamento a un dito in
        # questa modalità sposta la vista invece di disegnare/cancellare —
        # vedi `_on_pan_start/_on_pan_update/_on_pan_end` (branch dedicato)
        # e `_select_mode` (toggle di `InteractiveViewer.pan_enabled`).
        ("move",   ft.Icons.OPEN_WITH,       "Sposta"),
    ]

    def __init__(self, character: Character):
        super().__init__(expand=True, spacing=0)
        self.character = character
        self._page: ft.Page | None = None
        self._maps: list[GameMap] = []
        # `ScrollMemoryListView` (2026-08-16, bug segnalato da Davide:
        # "flash a schermo e uno scattino che riporta la vista in cima"
        # durante la sincronizzazione) — `_refresh_shared_maps()` ricostruisce
        # questa lista ad ogni giro del ciclo di sync in background, un
        # `ft.ListView` semplice perdeva lo scroll ogni volta.
        self._list_view = ScrollMemoryListView(expand=True, spacing=10, padding=16)

        # ── Stato disegno ──────────────────────────────────────────────
        self._strokes: list[dict] = []
        self._current_points: list[list[float]] = []

        self._pen_color_idx: int = 0
        self._pen_width: float = 5.0
        self._eraser_size: float = 20.0
        self._draw_mode: str = "pen"        # pen | eraser
        self._eraser_sub: str = "stroke"    # stroke | pixel

        # Cursore gomma pixel
        self._eraser_cursor_pos: list[float] | None = None

        # ── Riferimenti canvas / stack ──────────────────────────────────
        self._detail_canvas: cv.Canvas | None = None
        self._fs_canvas: cv.Canvas | None = None
        self._detail_draw_stack: ft.Stack | None = None
        self._fs_draw_stack: ft.Stack | None = None
        #: `ft.InteractiveViewer` che avvolge ciascuno dei due stack sopra
        #: (2026-08-19, zoom/pan) — riferimenti tenuti per poterne
        #: mutare `pan_enabled` da `_select_mode()` quando si passa alla
        #: modalità "Sposta", stesso principio dei riferimenti canvas/stack.
        self._detail_interactive_viewer: ft.InteractiveViewer | None = None
        self._fs_interactive_viewer: ft.InteractiveViewer | None = None
        self._current_gm: GameMap | None = None

        # Dimensione CORRENTE (pixel) del riquadro di disegno inline e a
        # schermo intero — due box DISTINTI, letti da `on_size_change`
        # (2026-08-12, fix del bug "le annotazioni non si allineano se la
        # mappa non è a schermo intero": segnalato da Davide sulle mappe
        # condivise, confermato presente anche qui). I tratti si salvano
        # come frazione [0,1] del riquadro con cui si è disegnato
        # (`ui/canvas_geometry.py`) e si riconvertono in pixel assoluti
        # rispetto al riquadro CORRENTE ad ogni ridisegno — così lo stesso
        # tratto resta allineato sia nel pannello inline sia a schermo
        # intero, qualunque sia la dimensione di ciascuno.
        self._detail_box_size: list[float] = [0.0, 0.0]
        self._fs_box_size: list[float] = [0.0, 0.0]
        #: Dimensione NATIVA dell'immagine della mappa aperta (2026-08-16,
        #: fix disallineamento — vedi `geo.contain_rect()`): con
        #: `fit=ft.BoxFit.CONTAIN` l'immagine occupa solo una PARTE del box
        #: se l'aspect ratio non coincide, le coordinate normalizzate vanno
        #: prese rispetto a quella parte, non all'intero riquadro. Popolata
        #: in `_open_detail()`, azzerata in `_back_to_list()`.
        self._img_size: list[float] = [0.0, 0.0]

        # ── Toolbar refs ────────────────────────────────────────────────
        self._swatch_refs:     list[ft.Container] = []
        self._width_refs:      list[ft.Container] = []
        self._mode_refs:       list[ft.Container] = []
        self._ersub_refs:      list[ft.Container] = []
        self._toolbar_body:    ft.Container | None = None

        self._fs_swatch_refs:  list[ft.Container] = []
        self._fs_width_refs:   list[ft.Container] = []
        self._fs_mode_refs:    list[ft.Container] = []
        self._fs_ersub_refs:   list[ft.Container] = []
        self._fs_toolbar_body: ft.Container | None = None

        # Mappe condivise dal Master (2026-08-16, richiesta di Davide:
        # "voglio che... le mappe condivise vengano visualizzate... nella
        # sezione mappa già presente nella scheda giocatore") — SOLO se
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

        # NOTA (2026-08-06): non c'è più un self._file_picker qui.
        # ft.FilePicker è stato abbandonato per la selezione mobile —
        # confermato non funzionante su build Android reali (log adb
        # logcat: TimeoutException, nessuna Activity nativa mai avviata,
        # vedi _pick_mobile() sotto e dnd_app/docs/changelog_storico.md,
        # sezione FILE PICKER). Su Android/iOS la selezione ora passa da
        # ui/mobile_webview_picker.py.

        self._build()

    def did_mount(self):
        self._page = cast(ft.Page, self.page)
        page = self.page
        if page is not None:
            page.run_task(self._init_world_sync)

        # Storico (fino al 2026-08-06): questo blocco registrava
        # ft.FilePicker in page.overlay, con vari tentativi di timing
        # (subito al mount, solo su mobile, poi anche quello scartato dopo
        # un test su Android reale — vedi git blame per il dettaglio).
        # Rimosso perché non più rilevante: FilePicker non è più usato
        # affatto in questo file, sostituito da una WebView locale (vedi
        # _pick_mobile()) dopo la diagnosi definitiva del 2026-08-06 (log
        # adb logcat: nessuna Activity nativa Android viene mai avviata,
        # bug non risolvibile lato applicazione).

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
        """Ciclo periodico (2026-08-16, vedi `_MAPS_SYNC_INTERVAL_S`) —
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
        # Mappe proprie + mappe condivise dal master (2026-08-16, richiesta
        # di Davide: niente più un riquadro "condiviso" separato — vanno
        # nella stessa lista già esistente, con un chip che le distingue,
        # vedi `_map_card`). `self._shared_maps` è tenuta aggiornata dal
        # ciclo di sync in background (`_refresh_shared_maps`).
        self._maps = maps_repo.get_maps(self.character.id) + self._shared_maps
        self.controls.clear()
        self.controls.append(self._build_top_toolbar())
        self.controls.append(ft.Container(expand=True, content=self._build_list_panel()))

    def _open_shared_map_readonly(self, gm: GameMap) -> None:
        """
        Viewer di sola lettura per una mappa condivisa dal master
        (2026-08-16) — stesso principio di
        `WorldsView._open_shared_map(can_manage=False)`, ma auto-contenuto
        qui (questa vista non ha accesso a quella classe): niente
        `GestureDetector`/toolbar di disegno, solo immagine + annotazioni
        già presenti, riallineate con `geo.contain_rect()` esattamente come
        lato Sezione Mondi (stesso fix 2026-08-16 del disallineamento
        cross-device).
        """
        page = self.page
        if page is None:
            return
        p = design.T()

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

        try:
            strokes: list[dict] = json.loads(gm.annotations or "[]")
        except (json.JSONDecodeError, TypeError):
            strokes = []
        canvas = cv.Canvas(expand=True)
        box_size = [0.0, 0.0]
        img_size = [0.0, 0.0]
        if gm.image_data:
            try:
                from PIL import Image as PILImage
                import io
                with PILImage.open(io.BytesIO(base64.b64decode(gm.image_data))) as _img:
                    img_size[0], img_size[1] = float(_img.width), float(_img.height)
            except Exception as e:
                logger.debug("Lettura dimensioni immagine mappa condivisa fallita: %s", e)

        def _redraw():
            ox, oy, dw, dh = geo.contain_rect(box_size[0], box_size[1], img_size[0], img_size[1])
            shapes: list[cv.Shape] = []
            for stroke in strokes:
                if stroke.get("type") != "stroke":
                    continue
                pts = geo.denormalize_points(stroke.get("points", []), dw, dh, ox, oy)
                if len(pts) < 2:
                    continue
                elems: list = [cv.Path.MoveTo(pts[0][0], pts[0][1])]
                for x, y in pts[1:]:
                    elems.append(cv.Path.LineTo(x, y))
                shapes.append(cv.Path(
                    elements=elems,
                    paint=ft.Paint(
                        color=stroke.get("color", "#e63946"), stroke_width=stroke.get("width", 5.0),
                        style=ft.PaintingStyle.STROKE, stroke_cap=ft.StrokeCap.ROUND,
                    ),
                ))
            canvas.shapes = shapes

        def _on_box_resize(e: ft.LayoutSizeChangeEvent):
            box_size[0], box_size[1] = e.width, e.height
            _redraw()
            try:
                canvas.update()
            except RuntimeError:
                pass

        _redraw()

        if gm.image_data:
            img_layer: ft.Control = ft.Image(src=_data_uri(gm.image_data),
                                             fit=ft.BoxFit.CONTAIN, expand=True)
        else:
            img_layer = ft.Container(
                expand=True, bgcolor=p.surface_alt, alignment=ft.Alignment.CENTER,
                content=ft.Column(
                    [ft.Icon(ft.Icons.MAP_OUTLINED, size=48, color=p.border),
                     design.muted("Nessuna immagine per questa mappa")],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            )
        draw_stack = ft.Stack([img_layer, canvas], expand=True)

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
                [header, ft.Container(expand=True, content=draw_stack, on_size_change=_on_box_resize)],
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
        # (2026-08-16, fusione nella lista esistente — vedi `_build`):
        # niente Modifica/Elimina (scrivere resta compito del master), solo
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
        self._strokes.clear()
        self._strokes.extend(json.loads(gm.annotations or "[]"))
        self._current_points.clear()
        self._eraser_cursor_pos = None
        self._current_gm = gm
        self._img_size = [0.0, 0.0]
        if gm.image_data:
            try:
                from PIL import Image as PILImage
                import io
                with PILImage.open(io.BytesIO(base64.b64decode(gm.image_data))) as _img:
                    self._img_size[0], self._img_size[1] = float(_img.width), float(_img.height)
            except Exception as e:
                logger.debug("Lettura dimensioni immagine mappa fallita: %s", e)

        self.controls[-1] = ft.Container(expand=True, content=self._build_detail_panel(gm))
        try:
            self.update()
        except RuntimeError:
            pass

    def _build_detail_panel(self, gm: GameMap) -> ft.Column:
        self._detail_canvas = cv.Canvas(expand=True)
        self._redraw_canvas(self._detail_canvas)

        # `_build_draw_stack` imposta già `self._detail_draw_stack` (l'inner
        # Stack) e `self._detail_interactive_viewer` — `draw_stack` qui è
        # l'InteractiveViewer che li avvolge, usato solo per il layout sotto.
        draw_stack = self._build_draw_stack(gm, self._detail_canvas, is_fs=False)

        toolbar_row, toolbar_body = self._build_drawing_toolbar(
            gm=gm, is_fs=False,
        )
        self._toolbar_body = toolbar_body

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

        legacy_banner = self._legacy_banner(gm)
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
                ft.Container(expand=True, content=draw_stack,
                             bgcolor=design.CHROME.backdrop,
                             on_size_change=lambda e: self._on_box_resize(False, e)),
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

    def _build_draw_stack(self, gm: GameMap, canvas: cv.Canvas,
                          is_fs: bool) -> ft.InteractiveViewer:
        """Costruisce lo Stack (immagine + canvas + gesture) avvolto in un
        `ft.InteractiveViewer` per zoom/pan (2026-08-19). `pan_enabled`
        parte sempre `False`: un trascinamento a un dito deve disegnare
        finché l'utente non passa esplicitamente alla modalità "Sposta"
        (`_select_mode`) — `scale_enabled` resta invece sempre `True`, un
        pinch a due dita (o lo scroll del trackpad) non compete mai con il
        disegno a un dito, nessun interruttore necessario per lo zoom in
        sé, solo per il pan. Il tipo di ritorno cambia da `ft.Stack` a
        `ft.InteractiveViewer`: entrambi i chiamanti (`_build_detail_panel`/
        `_open_fullscreen`) lo usano solo come `content` di un Container,
        quindi il cambio è trasparente per loro."""
        if gm.image_data:
            img_layer: ft.Control = ft.Image(
                src=_data_uri(gm.image_data), fit=ft.BoxFit.CONTAIN, expand=True,
            )
        else:
            img_layer = ft.Container(
                expand=True,
                content=ft.Column(
                    [ft.Icon(ft.Icons.MAP_OUTLINED, size=64, color=design.T().border),
                     ft.Text("Nessuna immagine", size=13, color=design.T().text_3)],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
                bgcolor=design.T().surface_alt,
                shadow=design.elevation(1), border_radius=design.Radius.MD,
            )

        gesture = ft.GestureDetector(
            content=canvas,
            on_pan_start=lambda e: self._on_pan_start(e, canvas),
            on_pan_update=lambda e: self._on_pan_update(e, gm, canvas),
            on_pan_end=lambda e: self._on_pan_end(e, gm, canvas),
            drag_interval=16,
            expand=True,
        )

        stack = ft.Stack(
            [img_layer, gesture],
            expand=True,
        )
        interactive_viewer = ft.InteractiveViewer(
            content=stack, pan_enabled=False, scale_enabled=True,
            trackpad_scroll_causes_scale=True, min_scale=1.0, max_scale=5.0,
        )
        # `self._{detail,fs}_draw_stack` deve restare il vero `ft.Stack`
        # (non l'`InteractiveViewer` che lo avvolge): `_clear_all()` più
        # sotto manipola direttamente `stack.controls`, che l'InteractiveViewer
        # non ha (ha `content`, non `controls`) — da qui i due riferimenti
        # separati, uno per l'inner Stack (invariato) e uno per il wrapper.
        if is_fs:
            self._fs_draw_stack = stack
            self._fs_interactive_viewer = interactive_viewer
        else:
            self._detail_draw_stack = stack
            self._detail_interactive_viewer = interactive_viewer
        return interactive_viewer

    def _back_to_list(self):
        self._strokes.clear()
        self._current_points.clear()
        self._eraser_cursor_pos = None
        self._img_size = [0.0, 0.0]
        self._detail_canvas = None
        self._detail_draw_stack = None
        self._fs_draw_stack = None
        self._detail_interactive_viewer = None
        self._fs_interactive_viewer = None
        self._current_gm = None
        self._swatch_refs.clear()
        self._mode_refs.clear()
        self._ersub_refs.clear()
        self._maps = maps_repo.get_maps(self.character.id)
        self.controls[-1] = ft.Container(expand=True, content=self._build_list_panel())
        try:
            self.update()
        except RuntimeError:
            pass

    # ------------------------------------------------------------------
    # Canvas: render
    # ------------------------------------------------------------------

    def _box_size_for(self, canvas: cv.Canvas | None) -> tuple[float, float]:
        """Dimensione CORRENTE (pixel) del riquadro che contiene `canvas` —
        inline o schermo intero, letta da `on_size_change` (vedi il
        commento su `self._detail_box_size` in `__init__`)."""
        box = self._fs_box_size if canvas is self._fs_canvas else self._detail_box_size
        return box[0], box[1]

    def _draw_rect_for(self, canvas: cv.Canvas | None) -> tuple[float, float, float, float]:
        """Rettangolo (`offset_x, offset_y, draw_w, draw_h`) effettivamente
        occupato dall'immagine dentro il box di `canvas` dopo
        `BoxFit.CONTAIN` — vedi `geo.contain_rect()` e `self._img_size`."""
        box_w, box_h = self._box_size_for(canvas)
        return geo.contain_rect(box_w, box_h, self._img_size[0], self._img_size[1])

    def _on_box_resize(self, is_fs: bool, e: ft.LayoutSizeChangeEvent):
        box = self._fs_box_size if is_fs else self._detail_box_size
        box[0], box[1] = e.width, e.height
        canvas = self._fs_canvas if is_fs else self._detail_canvas
        if canvas is not None:
            self._redraw_canvas(canvas)
            try:
                canvas.update()
            except RuntimeError:
                pass

    def _redraw_canvas(self, canvas: cv.Canvas):
        """
        Ridisegna sul canvas: stroke penna + cursore gomma.
        NON usa BlendMode.CLEAR (non funziona su CustomPaint senza saveLayer).

        I tratti salvati in `self._strokes` sono frazioni [0,1] del
        riquadro con cui furono disegnati (2026-08-12) — si riconvertono
        in pixel assoluti rispetto al riquadro CORRENTE di `canvas`
        (`_box_size_for`) ad ogni chiamata, cosicché lo stesso tratto
        resti allineato sia nel pannello inline sia a schermo intero. Il
        tratto in corso (`self._current_points`) e il cursore della gomma
        restano invece in pixel assoluti as-is: si vedono solo sul canvas
        che sta ricevendo la gesture in questo istante, nello stesso
        riquadro in cui sono stati generati.
        """
        ox, oy, dw, dh = self._draw_rect_for(canvas)
        shapes: list[cv.Shape] = []

        for stroke in self._strokes:
            stype = stroke.get("type", "stroke")
            if stype != "stroke":
                continue

            pts = geo.denormalize_points(stroke.get("points", []), dw, dh, ox, oy)
            if len(pts) < 2:
                continue
            elems: list = [cv.Path.MoveTo(pts[0][0], pts[0][1])]
            for x, y in pts[1:]:
                elems.append(cv.Path.LineTo(x, y))
            shapes.append(cv.Path(
                elements=elems,
                paint=ft.Paint(
                    color=stroke.get("color", _PEN_COLORS[0]),
                    stroke_width=stroke.get("width", 5.0),
                    style=ft.PaintingStyle.STROKE,
                    stroke_cap=ft.StrokeCap.ROUND,
                ),
            ))

        # Penna in corso (feedback real-time)
        if len(self._current_points) >= 2 and self._draw_mode == "pen":
            pts = self._current_points
            elems = [cv.Path.MoveTo(pts[0][0], pts[0][1])]
            for x, y in pts[1:]:
                elems.append(cv.Path.LineTo(x, y))
            shapes.append(cv.Path(
                elements=elems,
                paint=ft.Paint(
                    color=_PEN_COLORS[self._pen_color_idx],
                    stroke_width=self._pen_width,
                    style=ft.PaintingStyle.STROKE,
                    stroke_cap=ft.StrokeCap.ROUND,
                ),
            ))

        # Cursore gomma (cerchio che mostra il raggio)
        if self._eraser_cursor_pos and self._draw_mode == "eraser":
            cx, cy = self._eraser_cursor_pos
            r = self._eraser_size / 2
            shapes.append(cv.Circle(
                cx, cy, r,
                paint=ft.Paint(
                    color=design.CHROME.overlay_text,
                    stroke_width=1.5,
                    style=ft.PaintingStyle.STROKE,
                ),
            ))
            # Cerchio interno di contrasto (visibile su sfondi chiari)
            shapes.append(cv.Circle(
                cx, cy, r,
                paint=ft.Paint(
                    color=design.CHROME.overlay_dim,
                    stroke_width=0.8,
                    style=ft.PaintingStyle.STROKE,
                ),
            ))

        canvas.shapes = shapes

    def _update_all_canvases(self):
        for c in [self._detail_canvas, self._fs_canvas]:
            if c is not None:
                self._redraw_canvas(c)
                try:
                    c.update()
                except RuntimeError:
                    pass

    # ------------------------------------------------------------------
    # Gesture handlers
    # ------------------------------------------------------------------

    def _on_pan_start(self, e: ft.DragStartEvent, canvas: cv.Canvas):
        # Modalità "Sposta" (2026-08-19, zoom/pan): il gesture detector del
        # disegno resta agganciato ma inerte — `InteractiveViewer.pan_enabled`
        # (attivato solo in questa modalità, vedi `_select_mode`) reclama il
        # trascinamento a un dito per spostare la vista invece.
        if self._draw_mode == "move":
            return
        x, y = e.local_position.x, e.local_position.y
        if self._draw_mode == "eraser":
            self._eraser_cursor_pos = [x, y]
            self._redraw_canvas(canvas)
            try:
                canvas.update()
            except RuntimeError:
                pass
            return
        # pen
        self._current_points.clear()
        self._current_points.append([x, y])

    def _on_pan_update(self, e: ft.DragUpdateEvent, gm: GameMap, canvas: cv.Canvas):
        if self._draw_mode == "move":
            return
        x, y = e.local_position.x, e.local_position.y
        if self._draw_mode == "eraser":
            self._eraser_cursor_pos = [x, y]
            if self._eraser_sub == "stroke":
                self._erase_strokes_at(x, y, gm, canvas)
            else:
                # Gomma libera: spezza i segmenti nel raggio, salva incrementalmente
                self._erase_segments_at(x, y, gm, canvas)
            # Aggiorna cursore su QUESTO canvas (update_all_canvases già chiamato
            # da erase_*_at se ci sono modifiche; qui gestiamo solo il cursore)
            self._redraw_canvas(canvas)
            try:
                canvas.update()
            except RuntimeError:
                pass
            return
        # pen
        self._current_points.append([x, y])
        self._redraw_canvas(canvas)
        try:
            canvas.update()
        except RuntimeError:
            pass

    def _on_pan_end(self, e: ft.DragEndEvent, gm: GameMap, canvas: cv.Canvas):
        if self._draw_mode == "move":
            return
        self._eraser_cursor_pos = None
        if self._draw_mode == "eraser":
            self._update_all_canvases()
            return
        # pen
        if len(self._current_points) >= 2:
            ox, oy, dw, dh = self._draw_rect_for(canvas)
            self._strokes.append({
                "type": "stroke",
                "color": _PEN_COLORS[self._pen_color_idx],
                "width": self._pen_width,
                "points": geo.normalize_points(self._current_points, dw, dh, ox, oy),
            })
            maps_repo.update_map(gm.id, annotations=json.dumps(self._strokes))
            gm.annotations = json.dumps(self._strokes)
        self._current_points.clear()
        self._redraw_canvas(canvas)
        try:
            canvas.update()
        except RuntimeError:
            pass

    # ------------------------------------------------------------------
    # Gomma "Tratto": rimuove stroke interi
    # ------------------------------------------------------------------

    def _erase_strokes_at(self, x: float, y: float, gm: GameMap, canvas: cv.Canvas):
        """`x`/`y` sono pixel assoluti del riquadro che ha generato la
        gesture (`canvas`) — i punti di ogni tratto (frazioni [0,1], vedi
        `_redraw_canvas`) si riconvertono in pixel assoluti dello STESSO
        riquadro prima del confronto di distanza, altrimenti la gomma
        cancellerebbe nel posto sbagliato ogni volta che il riquadro non ha
        la dimensione con cui il tratto fu disegnato."""
        ox, oy, dw, dh = self._draw_rect_for(canvas)
        radius = self._eraser_size / 2
        to_remove: list[int] = []
        for i, stroke in enumerate(self._strokes):
            if stroke.get("type") != "stroke":
                continue
            pts = geo.denormalize_points(stroke.get("points", []), dw, dh, ox, oy)
            for px, py in pts:
                if math.hypot(px - x, py - y) <= radius:
                    to_remove.append(i)
                    break

        if to_remove:
            for i in reversed(to_remove):
                self._strokes.pop(i)
            maps_repo.update_map(gm.id, annotations=json.dumps(self._strokes))
            gm.annotations = json.dumps(self._strokes)
            self._update_all_canvases()

    # ------------------------------------------------------------------
    # Gomma "Libera": taglio geometrico preciso al bordo del cerchio
    # ------------------------------------------------------------------

    def _erase_segments_at(self, x: float, y: float, gm: GameMap, canvas: cv.Canvas):
        """
        Gomma libera precisa: usa _split_stroke_by_circle() per tagliare ogni
        segmento esattamente all'intersezione con il cerchio della gomma.
        Il taglio avviene al bordo, non per approssimazione ai punti campionati.

        Stesso principio di `_erase_strokes_at`: la geometria (raggio in
        pixel, intersezioni di cerchio) lavora in pixel assoluti del
        riquadro corrente — i punti si denormalizzano prima del taglio e si
        rinormalizzano subito dopo, prima di salvare (`self._strokes` resta
        sempre in frazioni [0,1], mai un mix dei due formati)."""
        ox, oy, dw, dh = self._draw_rect_for(canvas)
        radius = self._eraser_size / 2
        new_strokes: list[dict] = []
        modified = False

        for stroke in self._strokes:
            if stroke.get("type") != "stroke":
                continue

            pts = geo.denormalize_points(stroke.get("points", []), dw, dh, ox, oy)
            color = stroke.get("color", _PEN_COLORS[0])
            width_s = stroke.get("width", 5.0)

            if not pts:
                continue

            sub_groups = _split_stroke_by_circle(pts, x, y, radius)

            if len(sub_groups) == 1 and sub_groups[0] is pts:
                # Nessuna modifica: mantieni lo stroke originale identico
                new_strokes.append(stroke)
            else:
                modified = True
                for sub_pts in sub_groups:
                    if len(sub_pts) >= 2:
                        new_strokes.append({
                            "type": "stroke",
                            "color": color,
                            "width": width_s,
                            "points": geo.normalize_points(sub_pts, dw, dh, ox, oy),
                        })

        if modified:
            self._strokes = new_strokes
            maps_repo.update_map(gm.id, annotations=json.dumps(self._strokes))
            gm.annotations = json.dumps(self._strokes)
            self._update_all_canvases()

    # ------------------------------------------------------------------
    # Undo / Clear
    # ------------------------------------------------------------------

    def _undo_stroke(self, gm: GameMap):
        if self._strokes:
            self._strokes.pop()
        maps_repo.update_map(gm.id, annotations=json.dumps(self._strokes))
        gm.annotations = json.dumps(self._strokes)
        self._update_all_canvases()

    def _clear_all(self, gm: GameMap):
        self._strokes.clear()
        maps_repo.update_map(gm.id, annotations="[]")
        gm.annotations = "[]"
        self._update_all_canvases()
        for stack, canvas in [
            (self._detail_draw_stack, self._detail_canvas),
            (self._fs_draw_stack, self._fs_canvas),
        ]:
            if stack is None or canvas is None:
                continue
            base = stack.controls[:2]
            stack.controls.clear()
            stack.controls.extend(base)
            try:
                stack.update()
            except RuntimeError:
                pass

    def _has_legacy_strokes(self) -> bool:
        """Vero se `self._strokes` contiene almeno un tratto in formato
        legacy (pre-2026-08-12, pixel assoluti) — vedi il docstring di
        `ui.canvas_geometry`. Controlla la lista già in memoria, non
        `gm.annotations` da disco: resta corretto anche a runtime dopo un
        disegno/una cancellazione, senza dover rileggere il DB."""
        return any(
            s.get("type") == "stroke" and s.get("points")
            and not geo.looks_normalized(s.get("points", []))
            for s in self._strokes
        )

    def _clear_legacy_strokes(self, gm: GameMap) -> None:
        """Rimuove SOLO i tratti in formato legacy, preservando quelli già
        corretti — l'utente può poi ridisegnarli allineati. Nessuna
        migrazione automatica è possibile (vedi `ui.canvas_geometry`)."""
        self._strokes[:] = [
            s for s in self._strokes
            if s.get("type") != "stroke" or geo.looks_normalized(s.get("points", []))
        ]
        maps_repo.update_map(gm.id, annotations=json.dumps(self._strokes))
        gm.annotations = json.dumps(self._strokes)
        self._update_all_canvases()

    def _legacy_banner(self, gm: GameMap) -> ft.Control | None:
        """Avviso una tantum + azione "Cancella tratti precedenti" — `None`
        se non ci sono tratti legacy da segnalare (nessun controllo
        aggiunto all'albero in quel caso)."""
        if not self._has_legacy_strokes():
            return None

        banner_ref: list[ft.Container] = []

        def _on_clear(e: Any) -> None:
            self._clear_legacy_strokes(gm)
            if banner_ref:
                banner_ref[0].visible = False
                try:
                    banner_ref[0].update()
                except RuntimeError:
                    pass

        banner = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, size=16, color=design.T().danger),
                    ft.Text(
                        "Alcuni tratti di questa mappa sono di un formato precedente e "
                        "potrebbero non allinearsi su schermi diversi.",
                        size=12, color=design.CHROME.text, expand=True,
                    ),
                    ft.TextButton(
                        "Cancella tratti precedenti", icon=ft.Icons.DELETE_OUTLINE,
                        on_click=_on_clear,
                        style=ft.ButtonStyle(color=design.T().danger),
                    ),
                ],
                spacing=design.Space.SM, vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=16, vertical=8),
            bgcolor=ft.Colors.with_opacity(0.12, design.T().danger),
        )
        banner_ref.append(banner)
        return banner

    # ------------------------------------------------------------------
    # Toolbar disegno
    # ------------------------------------------------------------------

    def _build_drawing_toolbar(self, gm: GameMap, is_fs: bool
                                ) -> tuple[ft.Row, ft.Container]:
        """
        Ritorna (toolbar_modes_row, toolbar_body_container).
        toolbar_body cambia contenuto in base alla modalità.
        """
        swatch_list = self._fs_swatch_refs if is_fs else self._swatch_refs
        mode_list   = self._fs_mode_refs   if is_fs else self._mode_refs
        ersub_list  = self._fs_ersub_refs  if is_fs else self._ersub_refs

        swatch_list.clear(); mode_list.clear(); ersub_list.clear()

        # ── Bottoni modalità ──────────────────────────────────────────
        def _mbtn(key: str, icon: Any, label: str) -> ft.Container:
            c = ft.Container(
                content=ft.Row(
                    [ft.Icon(icon, size=15),
                     ft.Text(label, size=design.Size.LABEL,
                             weight=ft.FontWeight.BOLD,
                             font_family=design.Font.BODY)],
                    spacing=6, tight=True,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=ft.Padding.symmetric(horizontal=design.Space.MD,
                                             vertical=design.Space.SM),
                border_radius=design.Radius.PILL,
                alignment=ft.Alignment.CENTER,
                on_click=lambda e, k=key, ml=mode_list, sl=swatch_list, el=ersub_list:
                    self._select_mode(k, ml, sl, el, gm, is_fs),
                ink=True,
                animate=ft.Animation(design.Duration.FAST, design.CURVE),
            )
            self._style_mode_btn(c, key == self._draw_mode)
            mode_list.append(c)
            return c

        # Segmento (pillole dentro un binario) invece di due riquadri squadrati
        mode_row = ft.Container(
            content=ft.Row([_mbtn(k, ic, lb) for k, ic, lb in self._MODE_DEFS],
                           spacing=design.Space.XS),
            bgcolor=design.CHROME.panel,
            border_radius=design.Radius.PILL,
            padding=design.Space.XS,
        )

        # ── Colori ───────────────────────────────────────────────────
        def _swatch(idx: int) -> ft.Container:
            c = ft.Container(
                content=ft.Container(bgcolor=_PEN_COLORS[idx],
                                     border_radius=design.Radius.PILL, expand=True),
                width=28, height=28, border_radius=design.Radius.PILL,
                padding=3,
                on_click=lambda e, i=idx, sl=swatch_list:
                    self._select_color(i, sl),
                ink=True,
                animate_scale=ft.Animation(design.Duration.FAST, design.CURVE),
                tooltip="Colore del pennarello",
            )
            self._style_swatch(c, idx == self._pen_color_idx)
            swatch_list.append(c)
            return c

        swatches = ft.Row([_swatch(i) for i in range(len(_PEN_COLORS))],
                          spacing=design.Space.XS)

        # ── Undo / Cancella tutto ───────────────────────────────────
        def _action_btn(icon: Any, label: str, bg: str, fg: str, fn: Any) -> ft.Container:
            return ft.Container(
                content=ft.Row(
                    [ft.Icon(icon, size=14, color=fg),
                     ft.Text(label, size=design.Size.LABEL, color=fg,
                             weight=ft.FontWeight.BOLD,
                             font_family=design.Font.BODY)],
                    spacing=5, tight=True,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=ft.Padding.symmetric(horizontal=design.Space.MD,
                                             vertical=design.Space.SM),
                border_radius=design.Radius.PILL,
                bgcolor=bg,
                on_click=fn, ink=True,
                animate_scale=ft.Animation(design.Duration.FAST, design.CURVE),
            )

        undo_btn     = _action_btn(ft.Icons.UNDO, "Annulla",
                                   design.CHROME.btn, design.CHROME.text,
                                   lambda e: self._undo_stroke(gm))
        clearall_btn = _action_btn(ft.Icons.DELETE_FOREVER_OUTLINED, "Cancella tutto",
                                   design.CHROME.danger, design.CHROME.text,
                                   lambda e: self._clear_all(gm))

        def _sep():
            return ft.Container(width=1, height=24,
                                bgcolor=ft.Colors.with_opacity(0.5, design.CHROME.border),
                                margin=ft.Margin.only(left=design.Space.SM,
                                                      right=design.Space.SM))

        # `wrap=True` invece di `scroll=ft.ScrollMode.AUTO` (2026-08-19, bug
        # segnalato da Davide: su smartphone "bisogna scorrere per vedere i
        # restanti colori e i pulsanti") — vedi `docs/regole_flet_api.md`,
        # sezione "TAB BAR / BARRE DI PILLOLE...": per una barra di
        # navigazione a striscia fissa lo scroll è la scelta corretta, ma
        # per un controllo come questa toolbar (dove il contenuto DEVE
        # restare tutto visibile senza un gesto nascosto — preferenza
        # esplicita del progetto, "no hidden UI actions") crescere in
        # altezza è accettabile, a differenza di una tab bar che deve
        # restare fissa. Nessun figlio qui sotto usa `expand=True`, quindi
        # nessun rischio del crash "wrap+expand sulla stessa Row" già
        # documentato lì.
        top_row = ft.Row(
            [mode_row, _sep(), swatches, _sep(), undo_btn, clearall_btn],
            spacing=design.Space.SM,
            run_spacing=design.Space.SM,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            wrap=True,
        )

        # ── Body dinamico (cambia con la modalità) ───────────────────
        body_content = self._build_toolbar_body(gm, is_fs, swatch_list, ersub_list)
        toolbar_body = ft.Container(
            content=body_content,
            padding=ft.Padding.symmetric(horizontal=design.Space.LG,
                                         vertical=design.Space.SM),
            bgcolor=design.CHROME.panel,
        )

        if is_fs:
            self._fs_toolbar_body = toolbar_body
        else:
            self._toolbar_body = toolbar_body

        return (top_row, toolbar_body)

    # ── Stile dei controlli della barra (condiviso build ↔ selezione) ──
    # Prima lo stile era scritto due volte: una in costruzione e una dentro
    # `_select_*`, con il rischio che restassero disallineati.

    @staticmethod
    def _style_mode_btn(btn: ft.Container, sel: bool) -> None:
        btn.bgcolor = design.T().primary_fill if sel else "transparent"
        fg = design.T().on_primary_fill if sel else design.CHROME.text_muted
        for c in getattr(btn.content, "controls", []):
            c.color = fg

    @staticmethod
    def _style_swatch(sw: ft.Container, sel: bool) -> None:
        # Anello di selezione attorno al colore, invece di un bordo più spesso
        sw.bgcolor = design.CHROME.text if sel else "transparent"
        sw.border = None if sel else ft.Border.all(
            1, ft.Colors.with_opacity(0.5, design.CHROME.border))
        sw.scale = 1.0 if sel else 0.9

    @staticmethod
    def _style_ersub_btn(btn: ft.Container, sel: bool) -> None:
        btn.bgcolor = design.T().primary_fill if sel else design.CHROME.btn
        btn.border = None
        if btn.content:
            cast(ft.Text, btn.content).color = (
                design.T().on_primary if sel else design.CHROME.text_muted)

    def _build_toolbar_body(self, gm: GameMap, is_fs: bool,
                             swatch_list: list, ersub_list: list) -> ft.Control:
        """Contenuto body toolbar in base alla modalità corrente."""
        mode = self._draw_mode

        def _value_badge(text: str) -> ft.Container:
            """Valore dello slider in un badge mono, invece di testo nudo."""
            return ft.Container(
                content=ft.Text(text, size=design.Size.LABEL,
                                color=design.CHROME.text,
                                font_family=design.Font.MONO,
                                weight=ft.FontWeight.BOLD,
                                text_align=ft.TextAlign.CENTER),
                bgcolor=design.CHROME.btn,
                border_radius=design.Radius.SM,
                padding=ft.Padding.symmetric(horizontal=design.Space.SM, vertical=2),
                width=48,
                alignment=ft.Alignment.CENTER,
            )

        def _slider_label(text: str) -> ft.Text:
            return ft.Text(text, size=design.Size.LABEL, color=design.CHROME.text_dim,
                           weight=ft.FontWeight.BOLD, font_family=design.Font.BODY,
                           style=ft.TextStyle(letter_spacing=0.8))

        if mode == "pen":
            return ft.Row(
                [
                    _slider_label("LARGHEZZA"),
                    ft.Slider(
                        min=1, max=30, value=self._pen_width, divisions=29,
                        active_color=design.T().primary_fill, thumb_color=design.CHROME.text,
                        inactive_color=design.CHROME.border, expand=True, height=32,
                        on_change=lambda e: self._on_pen_width_change(e, gm),
                    ),
                    _value_badge(f"{self._pen_width:.0f}px"),
                ],
                spacing=design.Space.MD, vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )

        if mode == "eraser":
            ersub_list.clear()

            def _esbtn(key: str, label: str) -> ft.Container:
                c = ft.Container(
                    content=ft.Text(label, size=design.Size.LABEL,
                                    weight=ft.FontWeight.BOLD,
                                    font_family=design.Font.BODY),
                    padding=ft.Padding.symmetric(horizontal=design.Space.MD,
                                                 vertical=design.Space.XS + 2),
                    border_radius=design.Radius.PILL,
                    on_click=lambda e, k=key, el=ersub_list:
                        self._select_eraser_sub(k, el, gm, is_fs),
                    ink=True,
                    animate=ft.Animation(design.Duration.FAST, design.CURVE),
                )
                self._style_ersub_btn(c, key == self._eraser_sub)
                ersub_list.append(c)
                return c

            return ft.Row(
                [
                    _esbtn("stroke", "Tratto"),
                    _esbtn("pixel", "Libera"),
                    ft.Container(width=design.Space.SM),
                    _slider_label("DIMENSIONE"),
                    ft.Slider(
                        min=5, max=60, value=self._eraser_size, divisions=55,
                        active_color=design.CHROME.text_muted, thumb_color=design.CHROME.text,
                        inactive_color=design.CHROME.border, expand=True, height=32,
                        on_change=lambda e: self._on_eraser_size_change(e, gm),
                    ),
                    _value_badge(f"{self._eraser_size:.0f}px"),
                ],
                spacing=design.Space.SM, vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )

        # fallback (non dovrebbe accadere)
        return ft.Container()

    # ── Slider callbacks ─────────────────────────────────────────────

    @staticmethod
    def _set_badge(ctrl: Any, text: str) -> None:
        """Aggiorna il valore dentro il badge dello slider (Container → Text)."""
        target = ctrl.content if isinstance(ctrl, ft.Container) else ctrl
        if isinstance(target, ft.Text):
            target.value = text
            try:
                target.update()
            except RuntimeError:
                pass

    def _on_pen_width_change(self, e: Any, gm: GameMap):
        self._pen_width = float(e.control.value)
        # Aggiorna il badge del valore (3° figlio del Row nel body)
        body = self._toolbar_body
        if body and body.content and hasattr(body.content, "controls"):
            ctrls = cast(list, cast(Any, body.content).controls)
            if len(ctrls) >= 3:
                self._set_badge(ctrls[2], f"{self._pen_width:.0f}px")

    def _on_eraser_size_change(self, e: Any, gm: GameMap):
        self._eraser_size = float(e.control.value)
        body = self._toolbar_body
        if body and body.content and hasattr(body.content, "controls"):
            ctrls = cast(list, cast(Any, body.content).controls)
            if len(ctrls) >= 6:
                self._set_badge(ctrls[5], f"{self._eraser_size:.0f}px")
                try:
                    pass
                except RuntimeError:
                    pass

    # ── Mode / color / eraser-sub selectors ─────────────────────────

    def _select_mode(self, key: str, mode_list: list, swatch_list: list,
                     ersub_list: list, gm: GameMap, is_fs: bool):
        self._draw_mode = key
        self._eraser_cursor_pos = None

        # Zoom/pan (2026-08-19): `self._draw_mode` è condiviso tra pannello
        # inline e schermo intero, quindi entrambi gli `InteractiveViewer`
        # (quello/i effettivamente montati in questo momento) vanno
        # aggiornati insieme — non solo quello del pannello che ha appena
        # cambiato modalità.
        for viewer in (self._detail_interactive_viewer, self._fs_interactive_viewer):
            if viewer is None:
                continue
            viewer.pan_enabled = key == "move"
            try:
                viewer.update()
            except RuntimeError:
                pass

        for i, (k, _, _) in enumerate(self._MODE_DEFS):
            if i >= len(mode_list):
                break
            self._style_mode_btn(mode_list[i], k == key)
            try:
                mode_list[i].update()
            except RuntimeError:
                pass

        # Aggiorna body toolbar
        body = self._fs_toolbar_body if is_fs else self._toolbar_body
        if body is not None:
            body.content = self._build_toolbar_body(gm, is_fs, swatch_list, ersub_list)
            try:
                body.update()
            except RuntimeError:
                pass

        # Sincronizza l'altra toolbar
        other_mode = self._mode_refs if is_fs else self._fs_mode_refs
        other_body = self._toolbar_body if is_fs else self._fs_toolbar_body
        other_sw   = self._swatch_refs if is_fs else self._fs_swatch_refs
        other_es   = self._ersub_refs  if is_fs else self._fs_ersub_refs
        if other_mode:
            for i, (k, _, _) in enumerate(self._MODE_DEFS):
                if i >= len(other_mode):
                    break
                self._style_mode_btn(other_mode[i], k == key)
                try:
                    other_mode[i].update()
                except RuntimeError:
                    pass
        if other_body is not None:
            other_body.content = self._build_toolbar_body(
                gm, not is_fs, other_sw, other_es)
            try:
                other_body.update()
            except RuntimeError:
                pass

    def _select_color(self, idx: int, swatch_list: list):
        self._pen_color_idx = idx
        for i, s in enumerate(swatch_list):
            self._style_swatch(s, i == idx)
            try:
                s.update()
            except RuntimeError:
                pass
        # Sincronizza altra toolbar
        other = self._swatch_refs if swatch_list is self._fs_swatch_refs else self._fs_swatch_refs
        for i, s in enumerate(other):
            self._style_swatch(s, i == idx)
            try:
                s.update()
            except RuntimeError:
                pass

    def _select_eraser_sub(self, key: str, ersub_list: list,
                            gm: GameMap, is_fs: bool):
        self._eraser_sub = key
        for i, btn in enumerate(ersub_list):
            sel = (i == 0 and key == "stroke") or (i == 1 and key == "pixel")
            self._style_ersub_btn(btn, sel)
            try:
                btn.update()
            except RuntimeError:
                pass

    # ------------------------------------------------------------------
    # Fullscreen overlay
    # ------------------------------------------------------------------

    def _open_fullscreen(self, gm: GameMap):
        page = self._page
        if page is None:
            return

        self._fs_canvas = cv.Canvas(expand=True)
        self._redraw_canvas(self._fs_canvas)

        # Stesso principio del pannello inline: `_build_draw_stack` imposta
        # già `self._fs_draw_stack`/`self._fs_interactive_viewer`.
        fs_draw_stack = self._build_draw_stack(gm, self._fs_canvas, is_fs=True)

        fs_toolbar_row, fs_toolbar_body = self._build_drawing_toolbar(gm, is_fs=True)

        overlay_list: list[ft.Control] = []

        def close_fs(e: Any = None):
            if overlay_list and overlay_list[0] in page.overlay:
                page.overlay.remove(overlay_list[0])
            self._fs_canvas = None
            self._fs_draw_stack = None
            self._fs_interactive_viewer = None
            self._fs_swatch_refs.clear()
            self._fs_mode_refs.clear()
            self._fs_ersub_refs.clear()
            if self._detail_canvas:
                self._redraw_canvas(self._detail_canvas)
                try:
                    self._detail_canvas.update()
                except RuntimeError:
                    pass
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

        fs_legacy_banner = self._legacy_banner(gm)
        overlay = ft.Container(
            expand=True, bgcolor=design.CHROME.canvas,
            content=ft.Column(
                [
                    header,
                    *([fs_legacy_banner] if fs_legacy_banner is not None else []),
                    ft.Container(expand=True, content=fs_draw_stack,
                                 on_size_change=lambda e: self._on_box_resize(True, e)),
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
                # _pick_mobile è async (fix 2026-08-06, vedi il suo
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
                # _pick_mobile è async (fix 2026-08-06, vedi il suo
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

    Estratto da _load_image_base64() il 2026-08-06 per essere condiviso
    anche dal flusso WebView (_pick_mobile()), che riceve i bytes
    dell'immagine direttamente (FileReader lato browser) invece di un
    percorso file locale da aprire.
    """
    try:
        from PIL import Image as PILImage  # type: ignore[import-untyped]
        from PIL import ImageOps  # type: ignore[import-untyped]
        import io
        with PILImage.open(io.BytesIO(raw)) as im:
            # Applica la rotazione EXIF prima di ri-salvare — stesso bug e
            # stesso fix di profilo_tab.py::_save_photo_bytes() (2026-08-06):
            # senza questo, immagini scattate in verticale da smartphone
            # vengono salvate ruotate perché il tag "Orientation" va perso
            # al salvataggio se non applicato esplicitamente prima.
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
    caricata a mano da Davide via SSH (vedi ui/image_library.py) invece di
    ft.FilePicker — che in modalità web è strutturalmente rotto e non
    risolvibile lato applicazione (bug upstream confermato, flet-dev/flet
    #6040/#6250/#6251 — vedi CLAUDE.md 2026-07-12 per il changelog dei tre
    tentativi precedenti). Selezionare un'immagine richiama la stessa
    identica logica già usata per il path locale su mobile nativo
    (_load_image_base64() + _update_preview()).

    Parametro `page` diretto (non più un `MapsView`, 2026-08-12): riusata
    anche da `ui/views/world/world_view.py` per il caricamento di una mappa
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
    `page` diretto (non più un `MapsView`, 2026-08-12) — vedi il docstring
    gemello su `_pick_from_library` per il perché.

    **Storico** (perché non `ft.FilePicker`, 2026-08-06, log `adb logcat`
    reale): un primo log aveva rivelato un vero bug Python (`await`
    mancante su `pick_files()`, corretto — stesso identico difetto di
    `profilo_tab.py::_pick_photo_mobile()`), ma un secondo log preso DOPO
    quel fix ha mostrato che il problema è più a fondo:
    `TimeoutException: Timeout waiting for invoke method listener` —
    nessuna Activity nativa Android viene mai avviata. `ft.FilePicker` non
    è utilizzabile su questa build. Vedi `dnd_app/docs/changelog_storico.md`.

    **Tentativo 1 (WebView + `<input type=file>`), anch'esso confermato
    morto**: `webview_flutter` su Android non implementa di default
    `WebChromeClient.onShowFileChooser` — nessun selettore nativo si apre
    mai. Vedi `regole_flet_api.md`.

    **Percorso attuale (2026-08-06)**: estensione Flet nativa scritta su
    misura (`ui/native_image_picker.py` ->
    `dnd_app/extensions/flet_image_picker/`). ⚠️ NON verificata end-to-end
    da questo sandbox — per questo il fallback WebView resta qui sotto,
    attivato automaticamente se l'estensione solleva
    `ImagePickerUnavailable`, non rimosso. Stesso identico pattern di
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
