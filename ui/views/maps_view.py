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
  - ft.FilePicker SOLO mobile; desktop → subprocess nativo
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
from typing import Any, cast

import flet as ft
import flet.canvas as cv

from config.settings import *
from data.models import Character, GameMap
from data.repositories import maps_repo

logger = logging.getLogger(__name__)


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
_PEN_COLORS = [
    "#e53935",  # rosso
    "#1e88e5",  # blu
    "#43a047",  # verde
    "#fb8c00",  # arancio
    "#9c27b0",  # viola
    "#ffffff",  # bianco
    "#212121",  # nero
]

# ── Data URI helper ────────────────────────────────────────────────────────
def _data_uri(b64: str) -> str:
    try:
        h = base64.b64decode(b64[:16] + "==")
        if h[:3] == b"\xff\xd8\xff":
            mime = "image/jpeg"
        elif h[:8] == b"\x89PNG\r\n\x1a\n":
            mime = "image/png"
        elif h[:4] == b"GIF8":
            mime = "image/gif"
        else:
            mime = "image/jpeg"
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
    ]

    def __init__(self, character: Character):
        super().__init__(expand=True, spacing=0)
        self.character = character
        self._page: ft.Page | None = None
        self._maps: list[GameMap] = []
        self._list_view = ft.ListView(expand=True, spacing=10, padding=16)

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
        self._current_gm: GameMap | None = None

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

        self._build()

    def did_mount(self):
        self._page = cast(ft.Page, self.page)

    # ------------------------------------------------------------------
    # Build root
    # ------------------------------------------------------------------

    def _build(self):
        self._maps = maps_repo.get_maps(self.character.id)
        self.controls.clear()
        self.controls.append(self._build_top_toolbar())
        self.controls.append(ft.Container(expand=True, content=self._build_list_panel()))

    def _build_top_toolbar(self) -> ft.Container:
        return ft.Container(
            content=ft.Row(
                [
                    ft.Text("Mappe", size=16, weight=ft.FontWeight.BOLD,
                            color=COLOR_TEXT_TITLE, expand=True),
                    ft.ElevatedButton(
                        "＋ Nuova Mappa", icon=ft.Icons.MAP,
                        on_click=lambda e: self._open_create_dialog(),
                        style=ft.ButtonStyle(
                            bgcolor=COLOR_ACCENT_CRIMSON, color="#ffffff",
                            shape=ft.RoundedRectangleBorder(radius=6),
                        ),
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.only(left=16, right=16, top=12, bottom=8),
            bgcolor=COLOR_BG_SECONDARY,
            border=ft.Border.only(bottom=ft.BorderSide(1, COLOR_BORDER)),
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
        return ft.Container(
            expand=True,
            content=ft.Column(
                [
                    ft.Icon(ft.Icons.MAP_OUTLINED, size=64, color=COLOR_BORDER),
                    ft.Container(height=16),
                    ft.Text("Nessuna mappa", size=18, color=COLOR_TEXT_MUTED,
                            weight=ft.FontWeight.BOLD),
                    ft.Container(height=8),
                    ft.Text("Carica la mappa della tua avventura\ne aggiungi annotazioni.",
                            size=13, color=COLOR_TEXT_MUTED,
                            text_align=ft.TextAlign.CENTER),
                    ft.Container(height=20),
                    ft.ElevatedButton(
                        "Carica prima mappa", icon=ft.Icons.ADD_PHOTO_ALTERNATE,
                        on_click=lambda e: self._open_create_dialog(),
                        style=ft.ButtonStyle(
                            bgcolor=COLOR_ACCENT_CRIMSON, color="#ffffff",
                            shape=ft.RoundedRectangleBorder(radius=6),
                        ),
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                expand=True,
            ),
        )

    def _map_card(self, gm: GameMap) -> ft.Container:
        if gm.image_data:
            thumb = ft.Container(
                content=ft.Image(src=_data_uri(gm.image_data), fit=ft.BoxFit.COVER),
                width=80, height=60, border_radius=4,
                clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                border=ft.Border.all(1, COLOR_BORDER),
            )
        else:
            thumb = ft.Container(
                content=ft.Icon(ft.Icons.MAP_OUTLINED, size=28, color=COLOR_TEXT_MUTED),
                width=80, height=60, border_radius=4,
                bgcolor=COLOR_BG_SECONDARY,
                border=ft.Border.all(1, COLOR_BORDER),
                alignment=ft.Alignment.CENTER,
            )

        n = len([s for s in json.loads(gm.annotations or "[]")
                 if s.get("type") == "stroke"])

        return ft.Container(
            content=ft.Row(
                [
                    thumb,
                    ft.Column(
                        [
                            ft.Text(gm.name or "Mappa senza nome", size=13,
                                    weight=ft.FontWeight.BOLD, color=COLOR_TEXT_TITLE),
                            ft.Text((gm.notes or "—")[:80], size=11,
                                    color=COLOR_TEXT_MUTED, max_lines=2),
                            ft.Text(f"✏ {n} annotazioni" if n else "",
                                    size=10, color=COLOR_ACCENT_BLUE),
                        ],
                        spacing=2, expand=True,
                    ),
                    ft.Column(
                        [
                            ft.IconButton(ft.Icons.OPEN_IN_FULL, icon_size=18,
                                          on_click=lambda e, m=gm: self._open_detail(m),
                                          icon_color=COLOR_TEXT_SECONDARY),
                            ft.IconButton(ft.Icons.EDIT_OUTLINED, icon_size=18,
                                          on_click=lambda e, m=gm: self._open_edit_dialog(m),
                                          icon_color=COLOR_TEXT_SECONDARY),
                            ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_size=18,
                                          on_click=lambda e, m=gm: self._confirm_delete(m),
                                          icon_color=COLOR_ACCENT_CRIMSON),
                        ],
                        spacing=0,
                    ),
                ],
                spacing=12, vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            bgcolor=COLOR_BG_CARD, padding=12,
            border=ft.Border(
                top=ft.BorderSide(3, COLOR_ACCENT_CRIMSON),
                left=ft.BorderSide(1, COLOR_BORDER),
                right=ft.BorderSide(1, COLOR_BORDER),
                bottom=ft.BorderSide(1, COLOR_BORDER),
            ),
            border_radius=6, on_click=lambda e, m=gm: self._open_detail(m), ink=True,
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

        self.controls[-1] = ft.Container(expand=True, content=self._build_detail_panel(gm))
        try:
            self.update()
        except RuntimeError:
            pass

    def _build_detail_panel(self, gm: GameMap) -> ft.Column:
        self._detail_canvas = cv.Canvas(expand=True)
        self._redraw_canvas(self._detail_canvas)

        draw_stack = self._build_draw_stack(gm, self._detail_canvas, is_fs=False)
        self._detail_draw_stack = draw_stack

        toolbar_row, toolbar_body = self._build_drawing_toolbar(
            gm=gm, is_fs=False,
        )
        self._toolbar_body = toolbar_body

        notes_tf = ft.TextField(
            value=gm.notes or "", multiline=True, min_lines=2, max_lines=6,
            hint_text="Note sulla mappa…",
            text_style=ft.TextStyle(size=13, color=COLOR_TEXT_PRIMARY),
            border_color=COLOR_BORDER, focused_border_color=COLOR_ACCENT_BLUE,
            bgcolor=COLOR_BG_CARD,
        )

        def save_notes(ev):
            maps_repo.update_map(gm.id, notes=notes_tf.value or "")
            gm.notes = notes_tf.value or ""

        header_row = ft.Row(
            [
                ft.IconButton(ft.Icons.ARROW_BACK, tooltip="Lista mappe",
                              on_click=lambda e: self._back_to_list(),
                              icon_color=COLOR_TEXT_SECONDARY),
                ft.Text(gm.name or "Mappa", size=15, weight=ft.FontWeight.BOLD,
                        color=COLOR_TEXT_TITLE, expand=True),
                ft.IconButton(ft.Icons.FULLSCREEN, tooltip="Schermo intero",
                              on_click=lambda e: self._open_fullscreen(gm),
                              icon_color=COLOR_TEXT_SECONDARY),
                ft.TextButton("✎ Modifica", on_click=lambda e: self._open_edit_dialog(gm),
                              style=ft.ButtonStyle(color=COLOR_TEXT_MUTED)),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        return ft.Column(
            [
                ft.Container(
                    content=header_row, bgcolor=COLOR_BG_SECONDARY,
                    padding=ft.Padding.only(left=8, right=8, top=4, bottom=4),
                    border=ft.Border.only(bottom=ft.BorderSide(1, COLOR_BORDER)),
                ),
                ft.Container(expand=True, content=draw_stack),
                ft.Container(
                    content=ft.Column([toolbar_row, toolbar_body], spacing=0),
                    bgcolor="#2a2a2a",
                    border=ft.Border.only(top=ft.BorderSide(1, "#444444")),
                ),
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text("NOTE", size=9, color=COLOR_TEXT_MUTED,
                                    weight=ft.FontWeight.BOLD,
                                    style=ft.TextStyle(letter_spacing=0.8)),
                            notes_tf,
                            ft.Row([ft.ElevatedButton(
                                "Salva note", on_click=save_notes,
                                style=ft.ButtonStyle(
                                    bgcolor=COLOR_ACCENT_CRIMSON, color="#ffffff",
                                    shape=ft.RoundedRectangleBorder(radius=4),
                                ),
                            )], alignment=ft.MainAxisAlignment.END),
                        ],
                        spacing=6,
                    ),
                    padding=12, bgcolor=COLOR_BG_CARD,
                    border=ft.Border.only(top=ft.BorderSide(1, COLOR_BORDER)),
                ),
            ],
            expand=True, spacing=0,
        )

    def _build_draw_stack(self, gm: GameMap, canvas: cv.Canvas,
                          is_fs: bool) -> ft.Stack:
        """Costruisce lo Stack: immagine + canvas + gesture + overlay testo."""
        if gm.image_data:
            img_layer: ft.Control = ft.Image(
                src=_data_uri(gm.image_data), fit=ft.BoxFit.CONTAIN, expand=True,
            )
        else:
            img_layer = ft.Container(
                expand=True,
                content=ft.Column(
                    [ft.Icon(ft.Icons.MAP_OUTLINED, size=64, color=COLOR_BORDER),
                     ft.Text("Nessuna immagine", size=13, color=COLOR_TEXT_MUTED)],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
                bgcolor=COLOR_BG_SECONDARY,
                border=ft.Border.all(1, COLOR_BORDER), border_radius=6,
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
        return stack

    def _back_to_list(self):
        self._strokes.clear()
        self._current_points.clear()
        self._eraser_cursor_pos = None
        self._detail_canvas = None
        self._detail_draw_stack = None
        self._fs_draw_stack = None
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

    def _redraw_canvas(self, canvas: cv.Canvas):
        """
        Ridisegna sul canvas: stroke penna + cursore gomma.
        NON usa BlendMode.CLEAR (non funziona su CustomPaint senza saveLayer).
        """
        shapes: list[cv.Shape] = []

        for stroke in self._strokes:
            stype = stroke.get("type", "stroke")
            if stype != "stroke":
                continue

            pts = stroke.get("points", [])
            if len(pts) < 2:
                continue
            elems: list = [cv.Path.MoveTo(pts[0][0], pts[0][1])]
            for x, y in pts[1:]:
                elems.append(cv.Path.LineTo(x, y))
            shapes.append(cv.Path(
                elements=elems,
                paint=ft.Paint(
                    color=stroke.get("color", "#e53935"),
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
                    color="#ffffffdd",
                    stroke_width=1.5,
                    style=ft.PaintingStyle.STROKE,
                ),
            ))
            # Cerchio interno di contrasto (visibile su sfondi chiari)
            shapes.append(cv.Circle(
                cx, cy, r,
                paint=ft.Paint(
                    color="#00000066",
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
        x, y = e.local_position.x, e.local_position.y
        if self._draw_mode == "eraser":
            self._eraser_cursor_pos = [x, y]
            if self._eraser_sub == "stroke":
                self._erase_strokes_at(x, y, gm)
            else:
                # Gomma libera: spezza i segmenti nel raggio, salva incrementalmente
                self._erase_segments_at(x, y, gm)
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
        self._eraser_cursor_pos = None
        if self._draw_mode == "eraser":
            self._update_all_canvases()
            return
        # pen
        if len(self._current_points) >= 2:
            self._strokes.append({
                "type": "stroke",
                "color": _PEN_COLORS[self._pen_color_idx],
                "width": self._pen_width,
                "points": [list(p) for p in self._current_points],
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

    def _erase_strokes_at(self, x: float, y: float, gm: GameMap):
        radius = self._eraser_size / 2
        to_remove: list[int] = []
        for i, stroke in enumerate(self._strokes):
            if stroke.get("type") != "stroke":
                continue
            pts = stroke.get("points", [])
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

    def _erase_segments_at(self, x: float, y: float, gm: GameMap):
        """
        Gomma libera precisa: usa _split_stroke_by_circle() per tagliare ogni
        segmento esattamente all'intersezione con il cerchio della gomma.
        Il taglio avviene al bordo, non per approssimazione ai punti campionati.
        """
        radius = self._eraser_size / 2
        new_strokes: list[dict] = []
        modified = False

        for stroke in self._strokes:
            if stroke.get("type") != "stroke":
                continue
                continue

            pts = stroke.get("points", [])
            color = stroke.get("color", "#e53935")
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
                            "points": sub_pts,
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
            sel = key == self._draw_mode
            c = ft.Container(
                content=ft.Column(
                    [ft.Icon(icon, size=14, color="#ffffff" if sel else "#bbbbbb"),
                     ft.Text(label, size=9, color="#ffffff" if sel else "#bbbbbb")],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=1,
                ),
                width=46, height=42, border_radius=6,
                bgcolor="#c0182c" if sel else "#3a3a3a",
                border=ft.Border.all(1, "#c0182c" if sel else "#555555"),
                alignment=ft.Alignment.CENTER,
                on_click=lambda e, k=key, ml=mode_list, sl=swatch_list, el=ersub_list:
                    self._select_mode(k, ml, sl, el, gm, is_fs),
                ink=True,
            )
            mode_list.append(c)
            return c

        mode_row = ft.Row(
            [_mbtn(k, ic, lb) for k, ic, lb in self._MODE_DEFS],
            spacing=4,
        )

        # ── Colori ───────────────────────────────────────────────────
        def _swatch(idx: int) -> ft.Container:
            sel = idx == self._pen_color_idx
            c = ft.Container(
                width=22, height=22, bgcolor=_PEN_COLORS[idx], border_radius=11,
                border=ft.Border.all(3 if sel else 1.5,
                                     "#ffffff" if sel else "#00000066"),
                on_click=lambda e, i=idx, sl=swatch_list:
                    self._select_color(i, sl),
                ink=True,
            )
            swatch_list.append(c)
            return c

        swatches = ft.Row([_swatch(i) for i in range(len(_PEN_COLORS))], spacing=4)

        # ── Undo / Cancella disegni / Cancella tutto ────────────────
        def _action_btn(icon: Any, label: str, color: str,
                        border: str, fn: Any) -> ft.Container:
            return ft.Container(
                content=ft.Row(
                    [ft.Icon(icon, size=13, color="#ffffff"),
                     ft.Text(label, size=10, color="#ffffff")],
                    spacing=3,
                ),
                padding=ft.Padding.symmetric(horizontal=8, vertical=5),
                border_radius=5, bgcolor=color,
                border=ft.Border.all(1, border),
                on_click=fn, ink=True,
            )

        undo_btn     = _action_btn(ft.Icons.UNDO, "Annulla", "#3a3a3a", "#777777",
                                   lambda e: self._undo_stroke(gm))
        clearall_btn = _action_btn(ft.Icons.DELETE_FOREVER_OUTLINED, "Cancella tutto",
                                   "#7b0000", "#c0182c",
                                   lambda e: self._clear_all(gm))

        def _sep():
            return ft.Container(width=1, height=30, bgcolor="#555555",
                                margin=ft.Margin.only(left=2, right=2))

        top_row = ft.Row(
            [mode_row, _sep(), swatches, _sep(), undo_btn, clearall_btn],
            spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER,
            scroll=ft.ScrollMode.AUTO,
        )

        # ── Body dinamico (cambia con la modalità) ───────────────────
        body_content = self._build_toolbar_body(gm, is_fs, swatch_list, ersub_list)
        toolbar_body = ft.Container(
            content=body_content,
            padding=ft.Padding.symmetric(horizontal=12, vertical=6),
            bgcolor="#222222",
        )

        if is_fs:
            self._fs_toolbar_body = toolbar_body
        else:
            self._toolbar_body = toolbar_body

        return (
            ft.Row(
                [top_row],
                scroll=ft.ScrollMode.AUTO,
            ),
            toolbar_body,
        )

    def _build_toolbar_body(self, gm: GameMap, is_fs: bool,
                             swatch_list: list, ersub_list: list) -> ft.Control:
        """Contenuto body toolbar in base alla modalità corrente."""
        mode = self._draw_mode

        if mode == "pen":
            return ft.Row(
                [
                    ft.Text("Larghezza:", size=10, color="#aaaaaa"),
                    ft.Slider(
                        min=1, max=30, value=self._pen_width, divisions=29,
                        active_color=COLOR_ACCENT_CRIMSON, thumb_color="#ffffff",
                        inactive_color="#555555", expand=True, height=32,
                        on_change=lambda e: self._on_pen_width_change(e, gm),
                    ),
                    ft.Text(f"{self._pen_width:.0f}px", size=10, color="#aaaaaa",
                            width=34),
                ],
                spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )

        if mode == "eraser":
            ersub_list.clear()

            def _esbtn(key: str, label: str) -> ft.Container:
                sel = key == self._eraser_sub
                c = ft.Container(
                    content=ft.Text(label, size=10,
                                    color="#111111" if sel else "#ffffff",
                                    weight=ft.FontWeight.W_600),
                    padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                    border_radius=4,
                    bgcolor="#ffffff" if sel else "#3a3a3a",
                    border=ft.Border.all(1, "#ffffff" if sel else "#666666"),
                    on_click=lambda e, k=key, el=ersub_list:
                        self._select_eraser_sub(k, el, gm, is_fs),
                    ink=True,
                )
                ersub_list.append(c)
                return c

            return ft.Row(
                [
                    _esbtn("stroke", "Tratto"),
                    _esbtn("pixel", "Libera"),
                    ft.Container(width=8),
                    ft.Text("Dimensione:", size=10, color="#aaaaaa"),
                    ft.Slider(
                        min=5, max=60, value=self._eraser_size, divisions=55,
                        active_color="#888888", thumb_color="#ffffff",
                        inactive_color="#444444", expand=True, height=32,
                        on_change=lambda e: self._on_eraser_size_change(e, gm),
                    ),
                    ft.Text(f"{self._eraser_size:.0f}px", size=10, color="#aaaaaa",
                            width=34),
                ],
                spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )

        # fallback (non dovrebbe accadere)
        return ft.Container()

    # ── Slider callbacks ─────────────────────────────────────────────

    def _on_pen_width_change(self, e: Any, gm: GameMap):
        self._pen_width = float(e.control.value)
        # Aggiorna etichetta (3° figlio del Row nel body)
        body = self._toolbar_body
        if body and body.content and hasattr(body.content, "controls"):
            ctrls = cast(list, cast(Any, body.content).controls)
            if len(ctrls) >= 3:
                cast(ft.Text, ctrls[2]).value = f"{self._pen_width:.0f}px"
                try:
                    ctrls[2].update()
                except RuntimeError:
                    pass

    def _on_eraser_size_change(self, e: Any, gm: GameMap):
        self._eraser_size = float(e.control.value)
        body = self._toolbar_body
        if body and body.content and hasattr(body.content, "controls"):
            ctrls = cast(list, cast(Any, body.content).controls)
            if len(ctrls) >= 6:
                cast(ft.Text, ctrls[5]).value = f"{self._eraser_size:.0f}px"
                try:
                    ctrls[5].update()
                except RuntimeError:
                    pass

    # ── Mode / color / eraser-sub selectors ─────────────────────────

    def _select_mode(self, key: str, mode_list: list, swatch_list: list,
                     ersub_list: list, gm: GameMap, is_fs: bool):
        self._draw_mode = key
        self._eraser_cursor_pos = None

        for i, (k, _, _) in enumerate(self._MODE_DEFS):
            if i >= len(mode_list):
                break
            sel = k == key
            mode_list[i].bgcolor = "#c0182c" if sel else "#3a3a3a"
            mode_list[i].border = ft.Border.all(1, "#c0182c" if sel else "#555555")
            ctrls = getattr(mode_list[i].content, "controls", [])
            if len(ctrls) >= 2:
                ctrls[0].color = "#ffffff" if sel else "#bbbbbb"
                ctrls[1].color = "#ffffff" if sel else "#bbbbbb"
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
                sel = k == key
                other_mode[i].bgcolor = "#c0182c" if sel else "#3a3a3a"
                other_mode[i].border = ft.Border.all(1, "#c0182c" if sel else "#555555")
                ctrls = getattr(other_mode[i].content, "controls", [])
                if len(ctrls) >= 2:
                    ctrls[0].color = "#ffffff" if sel else "#bbbbbb"
                    ctrls[1].color = "#ffffff" if sel else "#bbbbbb"
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
            sel = i == idx
            s.border = ft.Border.all(3 if sel else 1.5,
                                     "#ffffff" if sel else "#00000066")
            try:
                s.update()
            except RuntimeError:
                pass
        # Sincronizza altra toolbar
        other = self._swatch_refs if swatch_list is self._fs_swatch_refs else self._fs_swatch_refs
        for i, s in enumerate(other):
            sel = i == idx
            s.border = ft.Border.all(3 if sel else 1.5,
                                     "#ffffff" if sel else "#00000066")
            try:
                s.update()
            except RuntimeError:
                pass

    def _select_eraser_sub(self, key: str, ersub_list: list,
                            gm: GameMap, is_fs: bool):
        self._eraser_sub = key
        for i, btn in enumerate(ersub_list):
            sel = (i == 0 and key == "stroke") or (i == 1 and key == "pixel")
            btn.bgcolor = "#ffffff" if sel else "#3a3a3a"
            btn.border = ft.Border.all(1, "#ffffff" if sel else "#666666")
            if btn.content:
                cast(ft.Text, btn.content).color = "#111111" if sel else "#ffffff"
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

        fs_draw_stack = self._build_draw_stack(gm, self._fs_canvas, is_fs=True)
        self._fs_draw_stack = fs_draw_stack

        fs_toolbar_row, fs_toolbar_body = self._build_drawing_toolbar(gm, is_fs=True)

        overlay_list: list[ft.Control] = []

        def close_fs(e: Any = None):
            if overlay_list and overlay_list[0] in page.overlay:
                page.overlay.remove(overlay_list[0])
            self._fs_canvas = None
            self._fs_draw_stack = None
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
                    ft.Text(gm.name or "Mappa", size=16, color="#ffffff",
                            weight=ft.FontWeight.BOLD, expand=True),
                    ft.IconButton(ft.Icons.FULLSCREEN_EXIT, icon_color="#ffffff",
                                  on_click=close_fs),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=16, vertical=8),
            bgcolor="#111111",
        )

        overlay = ft.Container(
            expand=True, bgcolor="#000000",
            content=ft.Column(
                [
                    header,
                    ft.Container(expand=True, content=fs_draw_stack),
                    ft.Container(
                        content=ft.Column(
                            [fs_toolbar_row, fs_toolbar_body], spacing=0),
                        bgcolor="#2a2a2a",
                        border=ft.Border.only(top=ft.BorderSide(1, "#444444")),
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
            text_style=ft.TextStyle(size=13, color=COLOR_TEXT_PRIMARY),
            border_color=COLOR_BORDER, focused_border_color=COLOR_ACCENT_BLUE,
            bgcolor=COLOR_BG_CARD,
            label_style=ft.TextStyle(color=COLOR_TEXT_SECONDARY),
        )
        notes_tf = ft.TextField(
            label="Note (opzionale)", multiline=True, min_lines=2, max_lines=5,
            text_style=ft.TextStyle(size=13, color=COLOR_TEXT_PRIMARY),
            border_color=COLOR_BORDER, focused_border_color=COLOR_ACCENT_BLUE,
            bgcolor=COLOR_BG_CARD,
            label_style=ft.TextStyle(color=COLOR_TEXT_SECONDARY),
        )
        img_data: list[str] = [""]
        img_label  = ft.Text("Nessuna immagine", size=11, color=COLOR_TEXT_MUTED)
        img_preview = ft.Container(
            content=ft.Icon(ft.Icons.IMAGE_OUTLINED, size=48, color=COLOR_BORDER),
            width=120, height=80, bgcolor=COLOR_BG_SECONDARY,
            border=ft.Border.all(1, COLOR_BORDER), border_radius=6,
            alignment=ft.Alignment.CENTER,
        )
        error_text = ft.Text("", size=11, color=COLOR_ACCENT_CRIMSON)

        def pick_image(ev: Any):
            if page.platform in (ft.PagePlatform.ANDROID, ft.PagePlatform.IOS):
                _pick_mobile(page, img_data, img_label, img_preview)
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
            title=ft.Text("Nuova Mappa", size=14, weight=ft.FontWeight.BOLD,
                          color=COLOR_TEXT_TITLE),
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
                                        side=ft.BorderSide(1, COLOR_BORDER),
                                        color=COLOR_TEXT_SECONDARY,
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
            actions=[
                ft.TextButton("Annulla", on_click=lambda ev: page.pop_dialog()),
                ft.ElevatedButton("Salva", on_click=on_save,
                                  style=ft.ButtonStyle(
                                      bgcolor=COLOR_ACCENT_CRIMSON, color="#ffffff",
                                      shape=ft.RoundedRectangleBorder(radius=4))),
            ],
            bgcolor=COLOR_BG_CARD,
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
            text_style=ft.TextStyle(size=13, color=COLOR_TEXT_PRIMARY),
            border_color=COLOR_BORDER, focused_border_color=COLOR_ACCENT_BLUE,
            bgcolor=COLOR_BG_CARD,
            label_style=ft.TextStyle(color=COLOR_TEXT_SECONDARY),
        )
        notes_tf = ft.TextField(
            label="Note", value=gm.notes or "",
            multiline=True, min_lines=2, max_lines=5,
            text_style=ft.TextStyle(size=13, color=COLOR_TEXT_PRIMARY),
            border_color=COLOR_BORDER, focused_border_color=COLOR_ACCENT_BLUE,
            bgcolor=COLOR_BG_CARD,
            label_style=ft.TextStyle(color=COLOR_TEXT_SECONDARY),
        )
        img_data: list[str] = [gm.image_data or ""]
        img_label = ft.Text(
            "Immagine corrente" if gm.image_data else "Nessuna immagine",
            size=11, color=COLOR_TEXT_MUTED,
        )
        if gm.image_data:
            img_preview: ft.Container = ft.Container(
                content=ft.Image(src=_data_uri(gm.image_data), fit=ft.BoxFit.COVER),
                width=120, height=80, border_radius=6,
                clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                border=ft.Border.all(1, COLOR_BORDER),
            )
        else:
            img_preview = ft.Container(
                content=ft.Icon(ft.Icons.IMAGE_OUTLINED, size=48, color=COLOR_BORDER),
                width=120, height=80, bgcolor=COLOR_BG_SECONDARY,
                border=ft.Border.all(1, COLOR_BORDER), border_radius=6,
                alignment=ft.Alignment.CENTER,
            )
        error_text = ft.Text("", size=11, color=COLOR_ACCENT_CRIMSON)

        def pick_image(ev: Any):
            if page.platform in (ft.PagePlatform.ANDROID, ft.PagePlatform.IOS):
                _pick_mobile(page, img_data, img_label, img_preview)
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
            title=ft.Text("Modifica Mappa", size=14, weight=ft.FontWeight.BOLD,
                          color=COLOR_TEXT_TITLE),
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
                                        side=ft.BorderSide(1, COLOR_BORDER),
                                        color=COLOR_TEXT_SECONDARY,
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
            actions=[
                ft.TextButton("Annulla", on_click=lambda ev: page.pop_dialog()),
                ft.ElevatedButton("Salva", on_click=on_save,
                                  style=ft.ButtonStyle(
                                      bgcolor=COLOR_ACCENT_CRIMSON, color="#ffffff",
                                      shape=ft.RoundedRectangleBorder(radius=4))),
            ],
            bgcolor=COLOR_BG_CARD,
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
            title=ft.Text("Elimina Mappa", size=14, weight=ft.FontWeight.BOLD,
                          color=COLOR_TEXT_TITLE),
            content=ft.Text(
                f'Eliminare "{gm.name}"?\nVerranno rimossi anche tutti i disegni.',
                size=13, color=COLOR_TEXT_PRIMARY,
            ),
            actions=[
                ft.TextButton("Annulla", on_click=lambda ev: page.pop_dialog()),
                ft.ElevatedButton("Elimina", on_click=do_delete,
                                  style=ft.ButtonStyle(
                                      bgcolor=COLOR_ACCENT_CRIMSON, color="#ffffff",
                                      shape=ft.RoundedRectangleBorder(radius=4))),
            ],
            bgcolor=COLOR_BG_CARD,
        ))


# ── File picker helpers ────────────────────────────────────────────────────

def _load_image_base64(path: str) -> str:
    try:
        from PIL import Image as PILImage  # type: ignore[import-untyped]
        import io
        with PILImage.open(path) as im:
            if im.mode not in ("RGB", "L"):
                im = im.convert("RGB")
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=85)
            return base64.b64encode(buf.getvalue()).decode()
    except ImportError:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception as exc:
        logger.error("_load_image_base64(%s): %s", path, exc)
        return ""


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


def _pick_mobile(page: ft.Page, img_data: list[str],
                 label: ft.Text, preview: ft.Container):
    fp = ft.FilePicker()

    def on_result(ev: Any):  # ft.FilePickerResultEvent non in stubs 0.85.3
        if ev.files:
            b64 = _load_image_base64(ev.files[0].path)
            if b64:
                img_data[0] = b64
                _update_preview(b64, label, preview, page)

    cast(Any, fp).on_result = on_result
    page.overlay.append(fp)
    page.update()
    cast(Any, fp).pick_files(  # type: ignore[unused-coroutine]
        allowed_extensions=["jpg", "jpeg", "png", "gif", "webp"]
    )


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
