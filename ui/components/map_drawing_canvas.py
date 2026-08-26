"""
Componente di disegno condiviso per le mappe — riquadro immagine + canvas +
toolbar Penna/Gomma/Sposta, usato sia dal giocatore (`ui/views/maps_view.py`,
mappe personali) sia dal Master (`ui/views/world/world_view.py`, mappe
condivise). Prima di questo modulo le due viste avevano ciascuna la propria
copia quasi identica di questa logica (~500 righe duplicate in
`world_view.py`, come closure dentro un unico metodo, con una gomma
semplificata e nessuna parità di toolbar) — refactor 2026-08-24, richiesta
Davide di riprogettare "disegno cancella e sposta" con la skill
`ui-ux-pro-max`, vedi il piano approvato per l'analisi completa dei bug
corretti qui:

  1. **Salto di layout ad ogni cambio strumento**: la vecchia
     `_build_toolbar_body()` in `maps_view.py` non gestiva affatto la
     modalità "move" (fallback `ft.Container()` vuoto) — l'area mappa,
     unico elemento `expand=True` della colonna, assorbiva la differenza di
     altezza. Qui il body della toolbar ha un'altezza fissa
     (`_TOOLBAR_BODY_H`) per TUTTE le modalità, "move" incluso, e la
     transizione tra contenuti usa un `ft.AnimatedSwitcher` (solo opacità,
     mai dimensione — nessun salto possibile per costruzione).
  2. **Disallineamento su dati freschi (non legacy)**: `self._detail_box_size`/
     `self._fs_box_size` partivano a `[0.0, 0.0]` e un tratto completato
     PRIMA del primo evento `on_size_change` (un giro websocket
     client→server, non istantaneo) veniva normalizzato con un riquadro
     0×0 — `geo.normalize_points()` ritorna i punti invariati (pixel
     assoluti) in quel caso, che poi `geo.denormalize_points()` giudica
     "legacy" per euristica e non riscala mai più. Qui il layer gesture
     (disegno/gomma) resta smontato — stesso canvas nudo già usato per la
     modalità "move" — finché il primo `on_size_change` non arriva per
     quel riquadro: nessuna scrittura può più avvenire con un box
     sconosciuto, per costruzione.
  3. **Barra pillole (`wrap=True`) che va a capo su finestra stretta**: un
     secondo salto verticale, indipendente dal cambio modalità. Qui sotto
     `_TOP_ROW_COMPACT_BP` px la riga passa a icone-sole con tooltip
     (nessun contenuto nascosto, solo più compatto), restando su una riga
     unica di altezza fissa.

Le due viste NON sono libere di divergere di nuovo: `MapDrawingCanvas` è
l'UNICO punto che sa costruire canvas/gesture/toolbar per una mappa
disegnabile — un chiamante che riscrivesse la propria copia invece di usare
questo modulo reintrodurrebbe esattamente i bug sopra.
"""

from __future__ import annotations

import base64
import json
import logging
import math
from typing import Any, Callable, cast

import flet as ft
import flet.canvas as cv

from core.image_utils import sniff_mime
from data.models import GameMap
from ui import canvas_geometry as geo
from ui import design

logger = logging.getLogger(__name__)

# ── Palette pennarello ───────────────────────────────────────────────────────
# ⚠️ NON sono token di tema (non vanno in `ui/design.py`): sono i colori del
# pennarello scelti dal giocatore/master e vengono PERSISTITI dentro
# `game_maps.annotations` come valore di ogni tratto. Cambiarli o renderli
# dipendenti dal tema romperebbe le annotazioni già salvate.
PEN_COLORS = [
    "#e53935",  # rosso
    "#1e88e5",  # blu
    "#43a047",  # verde
    "#fb8c00",  # arancio
    "#9c27b0",  # viola
    "#ffffff",  # bianco
    "#212121",  # nero
]

#: Altezza fissa del body dinamico della toolbar (slider penna/gomma o
#: suggerimento "Sposta") — stessa per tutte le modalità, derivata
#: dall'altezza reale di uno slider (`Slider(height=32)` + padding verticale
#: `Space.SM`×2). Vedi punto 1 del docstring del modulo.
_TOOLBAR_BODY_H = 48

#: Sotto questa larghezza (px) del riquadro toolbar, i pulsanti modalità e
#: annulla/cancella passano a icona-sola con tooltip invece di icona+testo —
#: mai `wrap=True` (andrebbe a capo, un salto verticale indipendente) né
#: scroll (nasconderebbe controlli, contro "no hidden UI actions" del
#: progetto). Riguarda SOLO la riga 1 (modalità/annulla/cancella, senza le
#: pastiglie colore — vedi `_TOP_ROW_STACK_BP`): sotto questa soglia la
#: riga 1 da sola non ci sta più con le etichette per esteso, verificato
#: dal vivo (screenshot reali, non stimato).
_TOP_ROW_COMPACT_BP = 650

#: Sotto questa larghezza (punti) del riquadro toolbar, le pastiglie
#: colore passano su una RIGA PROPRIA sotto modalità/annulla/cancella —
#: mai tutte sulla stessa riga di tutto il resto: bug report Davide
#: (2026-08-25) "ho dovuto allargare la scheda su pc per vedere cancella
#: tutto" — anche in modalità compatta (sola icona), 7 pastiglie da 40px
#: più modalità/separatori/annulla/cancella non entrano MAI su una riga
#: sola sotto ~950px, quindi su uno smartphone in verticale (tipicamente
#: 375-430pt) l'unica soluzione stabile è una seconda riga dedicata — MAI
#: un salto imprevedibile: la soglia si valuta una volta sola per
#: ridimensionamento, stesso identico meccanismo di `_TOP_ROW_COMPACT_BP`.
_TOP_ROW_STACK_BP = 950


def data_uri(b64: str) -> str:
    try:
        mime = sniff_mime(base64.b64decode(b64[:16] + "=="))
    except Exception:
        mime = "image/jpeg"
    return f"data:{mime};base64,{b64}"


# ── Geometria gomma precisa ("Libera") ──────────────────────────────────────

def _circle_segment_ts(px1: float, py1: float, px2: float, py2: float,
                        cx: float, cy: float, r: float) -> list[float]:
    """Parametri t ∈ [0,1] dove il segmento P1→P2 interseca il cerchio
    (cx,cy,r). Lista vuota se nessuna intersezione, [t] o [t1,t2] altrimenti."""
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
    """Divide una sequenza di punti in sub-sequenze esterne al cerchio
    (cx,cy,r). Ritorna [[pts]] invariato se nessuna modifica. Il taglio
    avviene esattamente all'intersezione geometrica, non per approssimazione."""
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
            current.append(p)
        elif prev_in and p_in and not ts:
            any_change = True
            flush()
        else:
            any_change = True
            events = [0.0] + ts + [1.0]
            for j in range(len(events) - 1):
                t0, t1 = events[j], events[j + 1]
                mid_t = (t0 + t1) * 0.5
                mid_in = math.hypot(prev[0] + mid_t * dx - cx,
                                     prev[1] + mid_t * dy - cy) <= r
                pt0 = [prev[0] + t0 * dx, prev[1] + t0 * dy]
                pt1 = [prev[0] + t1 * dx, prev[1] + t1 * dy]
                if mid_in:
                    if current:
                        if current[-1] != pt0:
                            current.append(pt0)
                        flush()
                else:
                    if not current or current[-1] != pt0:
                        current.append(pt0)
                    current.append(pt1)

    flush()

    if not any_change:
        return [pts]
    return result


_MODE_DEFS = [
    ("pen",    ft.Icons.EDIT,            "Penna"),
    ("eraser", ft.Icons.AUTO_FIX_NORMAL, "Gomma"),
    # "Sposta" (zoom/pan): un trascinamento a un dito in questa modalità
    # sposta la vista invece di disegnare/cancellare.
    ("move",   ft.Icons.OPEN_WITH,       "Sposta"),
]


class MapDrawingCanvas:
    """
    Stato di disegno di UNA mappa aperta — un'istanza per apertura (creata da
    `_open_detail()`/equivalente, scartata alla chiusura), con riferimenti
    SEPARATI per il pannello inline e per lo schermo intero (`is_fs: bool`),
    così i due possono restare montati insieme e sincronizzati (stesso
    principio degli originali `self._detail_*`/`self._fs_*` in
    `maps_view.py`, qui riorganizzati come due voci di un dict invece di
    coppie di attributi separati).

    `on_batch`: astrazione della persistenza — `None` per un giocatore in
    sola lettura su una mappa condivisa (nessun `GestureDetector`/toolbar
    montati, `can_manage=False`); altrimenti una closure chiamata con la
    lista di operazioni da applicare (`[{"op": "add"|"clear"|"replace_all", ...}]`,
    stesso formato di `data/repositories/maps_repo.py::apply_stroke_batch`).
    Il chiamante decide se questo scrive solo in locale (giocatore, mappa
    personale) o instrada anche `CMD_MAP_DRAW` verso il mondo (Master,
    mappa condivisa).
    """

    def __init__(self, gm: GameMap, *,
                 on_batch: Callable[[list[dict]], None] | None,
                 can_manage: bool = True,
                 page: ft.Page | None = None):
        self.gm = gm
        self.can_manage = can_manage and on_batch is not None
        self._on_batch = on_batch
        #: Riferimento di riserva per `_safe_update()` — un controllo
        #: appena riassegnato (`canvas.shapes = ...` seguito da
        #: `canvas.update()`) può sollevare `RuntimeError` se il client
        #: non lo considera ancora "pronto" (osservato durante un
        #: ridimensionamento live della finestra: molti `on_size_change` in
        #: rapida successione, alcuni dei quali arrivano mentre il
        #: sottoalbero è ancora a metà ricostruzione) — finora quell'errore
        #: veniva insabbiato (`except RuntimeError: pass`), lasciando la
        #: `cv.Canvas` visivamente ferma alla forma calcolata PRIMA del
        #: resize finché un `page.update()` esterno non arrivava per
        #: caso — da qui "il tratto si sposta/non corrisponde" segnalato
        #: da Davide anche a parità di dati corretti (verificato a mano dai
        #: log diagnostici: la matematica di normalizzazione tornava
        #: giusta, mancava solo la conferma al client).
        self._page = page

        try:
            self._strokes: list[dict] = json.loads(gm.annotations or "[]")
        except (json.JSONDecodeError, TypeError):
            self._strokes = []
        #: Cronologia per `undo()` — uno snapshot JSON di `self._strokes`
        #: PRIMA di ogni azione distruttiva (tratto, gomma "Tratto"/"Libera",
        #: cancella tutto). BUG FIX (2026-08-25, richiesta Davide: "Annulla
        #: annulla solo l'ultimo tratto, non l'ultima azione, per esempio se
        #: cancello per sbaglio con la gomma [non si può annullare]"):
        #: `undo()` faceva solo `self._strokes.pop()` — corretto per un
        #: tratto appena disegnato, ma un'azione della gomma modifica o
        #: rimuove tratti ESISTENTI senza aggiungerne uno nuovo in fondo,
        #: quindi un pop successivo toglieva il tratto SBAGLIATO (l'ultimo
        #: rimasto) invece di ripristinare quello cancellato per errore.
        #: Limite a 20 voci: sufficiente per un "annulla" a più passi senza
        #: crescita di memoria illimitata in una sessione di disegno lunga.
        self._history: list[str] = []
        self._current_points: list[list[float]] = []
        self._eraser_cursor_pos: list[float] | None = None

        self._pen_color_idx: int = 0
        self._pen_width: float = 5.0
        self._eraser_size: float = 20.0
        self._draw_mode: str = "pen"
        self._eraser_sub: str = "stroke"

        #: Dimensione NATIVA dell'immagine (`geo.contain_rect()`): con
        #: `fit=ft.BoxFit.CONTAIN` l'immagine occupa solo una PARTE del
        #: riquadro se l'aspect ratio non coincide — le coordinate
        #: normalizzate vanno prese rispetto a quella parte.
        self._img_size: list[float] = [0.0, 0.0]
        if gm.image_data:
            try:
                from PIL import Image as PILImage
                import io
                with PILImage.open(io.BytesIO(base64.b64decode(gm.image_data))) as _img:
                    self._img_size[0], self._img_size[1] = float(_img.width), float(_img.height)
            except Exception as e:
                logger.debug("Lettura dimensioni immagine mappa fallita: %s", e)

        # ── Stato per-pannello (chiave: is_fs) ──────────────────────────
        self._canvas: dict[bool, cv.Canvas | None] = {False: None, True: None}
        self._draw_stack: dict[bool, ft.Stack | None] = {False: None, True: None}
        self._interactive_viewer: dict[bool, ft.InteractiveViewer | None] = {False: None, True: None}
        #: Dimensione CORRENTE (pixel) del riquadro — letta da
        #: `on_size_change`, MAI sincrona (Flet 0.86.5 non offre altro
        #: modo). Parte a [0,0]: un tratto completato prima del primo
        #: evento userebbe un riquadro sconosciuto — vedi `_box_ready`.
        self._box_size: dict[bool, list[float]] = {False: [0.0, 0.0], True: [0.0, 0.0]}
        #: `True` alla PRIMA `on_box_resize()` per quel pannello, mai più
        #: `False` dopo (il riquadro, una volta noto, resta valido per
        #: tutta la sessione). Finché è `False`, `_canvas_layer_for_mode()`
        #: non monta il `GestureDetector` di disegno/gomma — vedi punto 2
        #: del docstring del modulo.
        self._box_ready: dict[bool, bool] = {False: False, True: False}
        #: Cache delle shape dei tratti GIÀ SALVATI (`self._strokes`),
        #: `None` = da ricalcolare. BUG FIX (2026-08-26) — Davide ha
        #: segnalato che il ritardo prima che un tratto inizi a comparire
        #: (già "corretto" con `scale_enabled`, ma persiste per i
        #: trascinamenti BREVI) è più probabile in trascinamenti che
        #: durano poco: `_redraw_canvas()` ricalcolava TUTTI i tratti già
        #: salvati (denormalizzazione + oggetto `cv.Path`) ad OGNI singolo
        #: `on_pan_update`, non solo quello in corso — un costo O(punti
        #: totali sulla mappa) per ogni fotogramma di trascinamento, tanto
        #: più pesante quanti più tratti la mappa accumula, e più lento su
        #: hardware mobile che su un Mac da sviluppo. Un trascinamento
        #: BREVE può concludersi (il dito si solleva) prima che anche solo
        #: il primo ridisegno completo torni dal client — da cui "il primo
        #: pezzo del tratto non viene scritto" concentrato proprio sui
        #: trascinamenti più rapidi. `_committed_shapes()` calcola questa
        #: lista una volta sola e la riusa finché `self._strokes` non
        #: cambia DAVVERO (nuovo tratto, gomma, annulla, cancella tutto,
        #: resize) — vedi `_redraw_canvas()` (invalida sempre) vs
        #: `_redraw_live_stroke()` (la riusa, ricalcola solo il tratto in
        #: corso).
        self._static_shapes: dict[bool, list[cv.Shape] | None] = {False: None, True: None}

        # ── Riferimenti toolbar (per-pannello, per lo stile in-place) ───
        self._mode_refs: dict[bool, list[ft.Container]] = {False: [], True: []}
        self._swatch_refs: dict[bool, list[ft.Container]] = {False: [], True: []}
        self._ersub_refs: dict[bool, list[ft.Container]] = {False: [], True: []}
        self._toolbar_body: dict[bool, ft.Container | None] = {False: None, True: None}
        self._toolbar_switcher: dict[bool, ft.AnimatedSwitcher | None] = {False: None, True: None}
        self._top_row_box: dict[bool, ft.Container | None] = {False: None, True: None}
        self._top_row_compact: dict[bool, bool] = {False: False, True: False}
        #: `True` sotto `_TOP_ROW_STACK_BP` — le pastiglie colore passano
        #: su una riga propria (vedi `_TOP_ROW_STACK_BP`).
        self._top_row_stacked: dict[bool, bool] = {False: False, True: False}

    # ──────────────────────────────────────────────────────────────────────
    # Aggiornamento sicuro
    # ──────────────────────────────────────────────────────────────────────

    def _safe_update(self, ctrl: ft.BaseControl, what: str = "") -> None:
        """`ctrl.update()` con fallback a `self.page.update()` se il primo
        fallisce (vedi il commento su `self._page` nell'`__init__`): un
        `RuntimeError` su un controllo appena riassegnato (`.shapes = ...`
        seguito da `.update()`) veniva finora insabbiato, lasciando la
        `cv.Canvas` visivamente ferma alla forma calcolata PRIMA
        dell'ultimo evento — indistinguibile a occhio da un bug di
        allineamento, ma in realtà solo un repaint mai arrivato al
        client. Log a WARNING quando scatta il fallback: se questo non
        compare mai nei log durante un resize, la causa del disallineamento
        è altrove."""
        try:
            ctrl.update()
        except RuntimeError:
            logger.warning("DIAG map_draw: %s.update() ha sollevato RuntimeError "
                            "(%s) — fallback a page.update()", type(ctrl).__name__, what)
            if self._page is not None:
                try:
                    self._page.update()
                except RuntimeError:
                    pass

    # ──────────────────────────────────────────────────────────────────────
    # Persistenza
    # ──────────────────────────────────────────────────────────────────────

    def _push(self, batch: list[dict]) -> None:
        """Applica `batch` alla cache locale (`self.gm.annotations`, letta
        da chi mostra la card/lista mappe) e la inoltra al chiamante — mai
        una scrittura diretta qui: `self._on_batch` decide come/se
        persistere (locale, o anche verso il mondo)."""
        self.gm.annotations = json.dumps(self._strokes)
        if self._on_batch is not None:
            self._on_batch(batch)

    def _snapshot(self) -> None:
        """Salva lo stato ATTUALE di `self._strokes` nella cronologia,
        PRIMA di applicare una modifica — chiamare all'inizio di ogni
        azione distruttiva (tratto, gomma, cancella tutto/legacy), mai
        dopo. Vedi il commento su `self._history` nell'`__init__`."""
        self._history.append(json.dumps(self._strokes))
        if len(self._history) > 20:
            self._history.pop(0)

    # ──────────────────────────────────────────────────────────────────────
    # Area di disegno
    # ──────────────────────────────────────────────────────────────────────

    def build_draw_area(self, *, is_fs: bool) -> ft.InteractiveViewer:
        """Immagine + canvas (+ gesture se `can_manage`) avvolti in un
        `ft.InteractiveViewer` per zoom/pan. Il chiamante deve avvolgere il
        risultato in un `ft.Container(expand=True, on_size_change=lambda e:
        self._canvas.on_box_resize(is_fs, e))` — l'evento non può essere
        intercettato qui dentro (Flet non offre `on_resize` su un controllo
        qualunque, solo su un `Container` che lo racchiude)."""
        canvas = cv.Canvas(expand=True)
        self._canvas[is_fs] = canvas
        self._redraw_canvas(canvas, is_fs)

        if self.gm.image_data:
            img_layer: ft.Control = ft.Image(
                src=data_uri(self.gm.image_data), fit=ft.BoxFit.CONTAIN, expand=True,
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

        gesture_layer = self._canvas_layer_for_mode(self._draw_mode, is_fs, canvas)
        # BUG FIX (2026-08-25) — causa REALE del disallineamento (confermata
        # visivamente pixel per pixel, non più per ipotesi): `ft.Stack` ha
        # `fit=StackFit.LOOSE` di default, quindi i figli NON sono forzati a
        # riempire il riquadro nonostante il loro `expand=True` — Flutter
        # concede all'`ft.Image` vincoli "liberi" e la piazza in alto a
        # sinistra (allineamento di default dello `Stack`) invece di
        # centrarla con `BoxFit.CONTAIN`. `contain_rect()` (canvas_geometry)
        # calcola SEMPRE il rettangolo centrato corretto — ma finora quel
        # rettangolo non corrispondeva a dove l'immagine veniva DAVVERO
        # disegnata, da cui il disallineamento riprodotto ad ogni resize e
        # perfino tra riquadri di forma diversa (inline/schermo intero,
        # master/giocatore): l'offset di centratura calcolato in Python non
        # è mai stato applicato dal client. `fit=ft.StackFit.EXPAND` forza
        # ENTRAMBI i figli a riempire esattamente il riquadro, così
        # l'immagine si centra davvero e il rettangolo calcolato coincide
        # finalmente con quello renderizzato.
        stack = ft.Stack([img_layer, gesture_layer], expand=True, fit=ft.StackFit.EXPAND)
        self._draw_stack[is_fs] = stack

        interactive_viewer = ft.InteractiveViewer(
            content=stack,
            # Un giocatore in sola lettura non ha alcun GestureDetector di
            # disegno che reclami il trascinamento a un dito (vedi
            # `_canvas_layer_for_mode`), quindi può spostare/zoomare la vista
            # da subito — un utente che può disegnare parte invece con
            # `pan_enabled=False, scale_enabled=False`: un trascinamento a un
            # dito disegna finché non passa esplicitamente a "Sposta"
            # (`_select_mode`).
            #
            # BUG FIX (2026-08-26) — ritardo di 1-2s prima che il tratto
            # inizi a comparire su schermo touch reale (segnalato da Davide),
            # stessa causa del gemello già corretto il 2026-08-20 (pizzico
            # rotto in modalità "Sposta"), ma nella direzione opposta: qui
            # era `scale_enabled=True` FISSO, mai spento in modalità
            # Penna/Gomma. Il `GestureDetector` figlio (disegno) e lo
            # `ScaleGestureRecognizer` dell'`InteractiveViewer` restavano
            # entrambi iscritti nella gesture arena di Flutter per lo stesso
            # tocco: su un touchscreen reale l'arena deve stabilire se è un
            # trascinamento a un dito o l'inizio di un pizzico a due, e
            # quell'arbitraggio può ritardare sensibilmente la vittoria del
            # riconoscitore di pan — nel frattempo i punti toccati vengono
            # persi (il riconoscitore non può invocare `onPanStart` finché
            # non vince). Su mouse/trackpad il problema non si vede (nessun
            # secondo tocco possibile, l'arena si risolve subito). Fix: come
            # per `pan_enabled`, spegnere anche `scale_enabled` ogni volta
            # che si è in Penna/Gomma — nessun riconoscitore concorrente resta
            # nell'arena, il pizzico durante il disegno si ottiene passando a
            # "Sposta", esattamente come già succede per il pan.
            pan_enabled=self._draw_mode == "move" or not self.can_manage,
            scale_enabled=self._draw_mode == "move" or not self.can_manage,
            trackpad_scroll_causes_scale=True,
            min_scale=1.0, max_scale=5.0,
        )
        self._interactive_viewer[is_fs] = interactive_viewer
        return interactive_viewer

    def on_box_resize(self, is_fs: bool, e: ft.LayoutSizeChangeEvent) -> None:
        box = self._box_size[is_fs]
        box[0], box[1] = e.width, e.height
        was_ready = self._box_ready[is_fs]
        self._box_ready[is_fs] = True

        canvas = self._canvas[is_fs]
        if canvas is not None:
            self._redraw_canvas(canvas, is_fs)
            self._safe_update(canvas, f"on_box_resize is_fs={is_fs}")

        if not was_ready and self.can_manage:
            # Il riquadro era sconosciuto finora: il layer gesture era
            # rimasto smontato (canvas nudo) per non rischiare di
            # normalizzare un tratto contro un box 0×0 — vedi punto 2 del
            # docstring del modulo. Ora che è noto, lo si monta.
            stack = self._draw_stack[is_fs]
            if stack is not None and canvas is not None:
                stack.controls[1] = self._canvas_layer_for_mode(self._draw_mode, is_fs, canvas)
                self._safe_update(stack, f"on_box_resize/stack is_fs={is_fs}")

    def _canvas_layer_for_mode(self, mode: str, is_fs: bool, canvas: cv.Canvas) -> ft.Control:
        """Il secondo figlio dello Stack sotto l'`InteractiveViewer`: avvolge
        il canvas in un `GestureDetector` per disegnare/cancellare, o lo
        lascia nudo se non c'è nulla da disegnare in questo istante — tre
        casi possibili, tutti con lo stesso identico rimedio (BUG FIX
        2026-08-20 per il primo, esteso qui al terzo):
          - `not self.can_manage`: sola lettura, niente da disegnare mai.
          - `mode == "move"`: un `GestureDetector` con `on_pan_*` resta
            iscritto nella gesture arena di Flutter anche quando gli
            handler fanno subito `return` — il suo recognizer di pan vince
            comunque il pinch a due dita PRIMA che possa arrivare allo
            `ScaleGestureRecognizer` dell'`InteractiveViewer` padre (un
            dito reale su schermo touch lo nota, un mouse/trackpad no — da
            qui il bug originale "zoom funziona su pc, non su smartphone").
          - `not self._box_ready[is_fs]`: il riquadro non è ancora noto
            (nessun `on_size_change` ricevuto) — disegnare ora
            normalizzerebbe il tratto contro un box 0×0, corrompendolo
            silenziosamente per sempre (vedi punto 2 del docstring del
            modulo). Finestra reale di uno-due frame, richiusa da
            `on_box_resize()` appena il primo evento arriva.
        """
        if not self.can_manage or mode == "move" or not self._box_ready[is_fs]:
            return canvas
        return ft.GestureDetector(
            content=canvas,
            on_pan_start=lambda e: self._on_pan_start(e, canvas),
            on_pan_update=lambda e: self._on_pan_update(e, canvas),
            on_pan_end=lambda e: self._on_pan_end(e, canvas),
            drag_interval=16,
            expand=True,
        )

    # ──────────────────────────────────────────────────────────────────────
    # Render
    # ──────────────────────────────────────────────────────────────────────

    def _box_size_for(self, canvas: cv.Canvas | None) -> tuple[float, float]:
        is_fs = canvas is self._canvas[True]
        box = self._box_size[is_fs]
        return box[0], box[1]

    def _draw_rect_for(self, canvas: cv.Canvas | None) -> tuple[float, float, float, float]:
        box_w, box_h = self._box_size_for(canvas)
        return geo.contain_rect(box_w, box_h, self._img_size[0], self._img_size[1])

    def _committed_shapes(self, is_fs: bool) -> list[cv.Shape]:
        """Le shape dei tratti GIÀ SALVATI (`self._strokes`) — calcolate una
        volta e messe in cache (`self._static_shapes[is_fs]`) finché
        qualcosa non le invalida davvero (vedi `_redraw_canvas`, che
        invalida sempre prima di ricalcolare). NON include il tratto in
        corso né il cursore della gomma: quelli cambiano ad ogni
        fotogramma di un trascinamento e li aggiunge chi chiama (vedi
        `_redraw_canvas`/`_redraw_live_stroke`) — vedi il commento su
        `self._static_shapes` nell'`__init__` per il perché di questa
        separazione.

        I tratti salvati sono frazioni [0,1] del riquadro con cui furono
        disegnati — si riconvertono in pixel assoluti rispetto al riquadro
        CORRENTE ad ogni ricalcolo, cosicché lo stesso tratto resti allineato
        sia inline sia a schermo intero."""
        cached = self._static_shapes[is_fs]
        if cached is not None:
            return cached
        ox, oy, dw, dh = self._draw_rect_for(self._canvas[is_fs])
        shapes: list[cv.Shape] = []
        for stroke in self._strokes:
            if stroke.get("type", "stroke") != "stroke":
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
                    color=stroke.get("color", PEN_COLORS[0]),
                    stroke_width=stroke.get("width", 5.0),
                    style=ft.PaintingStyle.STROKE,
                    stroke_cap=ft.StrokeCap.ROUND,
                ),
            ))
        self._static_shapes[is_fs] = shapes
        return shapes

    def _redraw_canvas(self, canvas: cv.Canvas, is_fs: bool) -> None:
        """Ridisegna TUTTO: stroke salvati (ricalcolati da zero — vedi sotto)
        + tratto penna in corso + cursore gomma. NON usa `BlendMode.CLEAR`
        (non funziona su CustomPaint senza saveLayer) — la cancellazione
        muta `self._strokes` e ridisegna da zero.

        Invalida SEMPRE la cache di `_committed_shapes()` prima di
        ricalcolare: è la scelta giusta qui perché ogni chiamante di
        `_redraw_canvas()` lo fa esattamente quando i tratti salvati
        POSSONO essere cambiati (resize, cambio modalità, fine tratto,
        gomma, annulla, cancella tutto...) — mai durante il singolo
        fotogramma di un trascinamento penna in corso, per cui esiste
        invece `_redraw_live_stroke()` (riusa la cache, non la invalida)."""
        self._static_shapes[is_fs] = None
        shapes = list(self._committed_shapes(is_fs))

        if len(self._current_points) >= 2 and self._draw_mode == "pen":
            elems = [cv.Path.MoveTo(self._current_points[0][0], self._current_points[0][1])]
            for x, y in self._current_points[1:]:
                elems.append(cv.Path.LineTo(x, y))
            shapes.append(cv.Path(
                elements=elems,
                paint=ft.Paint(
                    color=PEN_COLORS[self._pen_color_idx],
                    stroke_width=self._pen_width,
                    style=ft.PaintingStyle.STROKE,
                    stroke_cap=ft.StrokeCap.ROUND,
                ),
            ))

        if self._eraser_cursor_pos is not None and self._draw_mode == "eraser":
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
            shapes.append(cv.Circle(
                cx, cy, r,
                paint=ft.Paint(
                    color=design.CHROME.overlay_dim,
                    stroke_width=0.8,
                    style=ft.PaintingStyle.STROKE,
                ),
            ))

        canvas.shapes = shapes

    def _redraw_live_stroke(self, canvas: cv.Canvas, is_fs: bool) -> None:
        """Variante leggera di `_redraw_canvas()`, usata SOLO da
        `_on_pan_update()` in modalità Penna durante un trascinamento in
        corso (BUG FIX 2026-08-26, vedi `self._static_shapes`
        nell'`__init__`): riusa `_committed_shapes()` dalla cache — i
        tratti già salvati non cambiano mentre si disegna un tratto nuovo
        — e ricalcola SOLO la Path del tratto in corso, invece di rifare
        da zero il lavoro per ogni singolo tratto già sulla mappa ad ogni
        fotogramma."""
        shapes = list(self._committed_shapes(is_fs))
        if len(self._current_points) >= 2:
            elems = [cv.Path.MoveTo(self._current_points[0][0], self._current_points[0][1])]
            for x, y in self._current_points[1:]:
                elems.append(cv.Path.LineTo(x, y))
            shapes.append(cv.Path(
                elements=elems,
                paint=ft.Paint(
                    color=PEN_COLORS[self._pen_color_idx],
                    stroke_width=self._pen_width,
                    style=ft.PaintingStyle.STROKE,
                    stroke_cap=ft.StrokeCap.ROUND,
                ),
            ))
        canvas.shapes = shapes

    def _update_all_canvases(self) -> None:
        for is_fs, canvas in self._canvas.items():
            if canvas is None:
                continue
            self._redraw_canvas(canvas, is_fs)
            self._safe_update(canvas, f"_update_all_canvases is_fs={is_fs}")

    # ──────────────────────────────────────────────────────────────────────
    # Gesture handlers
    # ──────────────────────────────────────────────────────────────────────

    def _on_pan_start(self, e: ft.DragStartEvent, canvas: cv.Canvas) -> None:
        is_fs = canvas is self._canvas[True]
        x, y = e.local_position.x, e.local_position.y
        if self._draw_mode == "eraser":
            # Un solo snapshot per l'INTERO trascinamento della gomma (non
            # uno per ogni micro-cancellazione lungo il percorso): "Annulla"
            # deve ripristinare l'intera passata di gomma con un click solo,
            # non un frammento minuscolo di essa — vedi il commento su
            # `self._history` nell'`__init__`.
            self._snapshot()
            self._eraser_cursor_pos = [x, y]
            self._redraw_canvas(canvas, is_fs)
            self._safe_update(canvas, "on_pan_start/eraser")
            return
        self._current_points.clear()
        self._current_points.append([x, y])

    def _on_pan_update(self, e: ft.DragUpdateEvent, canvas: cv.Canvas) -> None:
        is_fs = canvas is self._canvas[True]
        x, y = e.local_position.x, e.local_position.y
        if self._draw_mode == "eraser":
            self._eraser_cursor_pos = [x, y]
            if self._eraser_sub == "stroke":
                self._erase_strokes_at(x, y, canvas)
            else:
                self._erase_segments_at(x, y, canvas)
            self._redraw_canvas(canvas, is_fs)
            self._safe_update(canvas, "on_pan_update/eraser")
            return
        self._current_points.append([x, y])
        self._redraw_live_stroke(canvas, is_fs)
        self._safe_update(canvas, "on_pan_update/pen")

    def _on_pan_end(self, e: ft.DragEndEvent, canvas: cv.Canvas) -> None:
        is_fs = canvas is self._canvas[True]
        self._eraser_cursor_pos = None
        if self._draw_mode == "eraser":
            self._update_all_canvases()
            return
        if len(self._current_points) >= 2:
            ox, oy, dw, dh = self._draw_rect_for(canvas)
            stroke = {
                "type": "stroke",
                "color": PEN_COLORS[self._pen_color_idx],
                "width": self._pen_width,
                "points": geo.normalize_points(self._current_points, dw, dh, ox, oy),
            }
            self._snapshot()
            self._strokes.append(stroke)
            self._push([{"op": "add", **stroke}])
        self._current_points.clear()
        self._redraw_canvas(canvas, is_fs)
        self._safe_update(canvas, "on_pan_end")

    # ──────────────────────────────────────────────────────────────────────
    # Gomma "Tratto": rimuove stroke interi
    # ──────────────────────────────────────────────────────────────────────

    def _erase_strokes_at(self, x: float, y: float, canvas: cv.Canvas) -> None:
        """`x`/`y` sono pixel assoluti del riquadro che ha generato la
        gesture — i punti di ogni tratto si riconvertono in pixel assoluti
        dello STESSO riquadro prima del confronto, altrimenti la gomma
        cancellerebbe nel posto sbagliato."""
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
            self._push([{"op": "replace_all", "strokes": self._strokes}])
            self._update_all_canvases()

    # ──────────────────────────────────────────────────────────────────────
    # Gomma "Libera": taglio geometrico preciso al bordo del cerchio
    # ──────────────────────────────────────────────────────────────────────

    def _erase_segments_at(self, x: float, y: float, canvas: cv.Canvas) -> None:
        """Usa `_split_stroke_by_circle()` per tagliare ogni segmento
        esattamente all'intersezione col cerchio della gomma — il taglio
        avviene al bordo, non per approssimazione ai punti campionati.
        Stesso principio di `_erase_strokes_at`: i punti si denormalizzano
        prima del taglio e si rinormalizzano subito dopo, `self._strokes`
        resta sempre in frazioni [0,1]."""
        ox, oy, dw, dh = self._draw_rect_for(canvas)
        radius = self._eraser_size / 2
        new_strokes: list[dict] = []
        modified = False

        for stroke in self._strokes:
            if stroke.get("type") != "stroke":
                continue
            pts = geo.denormalize_points(stroke.get("points", []), dw, dh, ox, oy)
            color = stroke.get("color", PEN_COLORS[0])
            width_s = stroke.get("width", 5.0)
            if not pts:
                continue

            sub_groups = _split_stroke_by_circle(pts, x, y, radius)
            if len(sub_groups) == 1 and sub_groups[0] is pts:
                new_strokes.append(stroke)
            else:
                modified = True
                for sub_pts in sub_groups:
                    if len(sub_pts) >= 2:
                        new_strokes.append({
                            "type": "stroke", "color": color, "width": width_s,
                            "points": geo.normalize_points(sub_pts, dw, dh, ox, oy),
                        })

        if modified:
            self._strokes = new_strokes
            self._push([{"op": "replace_all", "strokes": self._strokes}])
            self._update_all_canvases()

    # ──────────────────────────────────────────────────────────────────────
    # Undo / Clear
    # ──────────────────────────────────────────────────────────────────────

    def undo(self) -> None:
        """Ripristina lo stato PRIMA dell'ultima azione (tratto, gomma,
        cancella tutto/legacy) — non semplicemente "l'ultimo tratto": vedi
        `self._history`/`_snapshot()`. Nessun effetto se non c'è ancora
        nulla da annullare."""
        if not self._history:
            return
        self._strokes = json.loads(self._history.pop())
        self._push([{"op": "replace_all", "strokes": self._strokes}])
        self._update_all_canvases()

    def clear_all(self) -> None:
        self._snapshot()
        self._strokes.clear()
        self._push([{"op": "clear"}])
        self._update_all_canvases()

    # ──────────────────────────────────────────────────────────────────────
    # Tratti legacy (pixel assoluti, pre-normalizzazione)
    # ──────────────────────────────────────────────────────────────────────

    def has_legacy_strokes(self) -> bool:
        """Controlla `self._strokes` già in memoria, non `gm.annotations` su
        disco: resta corretto a runtime dopo un disegno/una cancellazione,
        senza dover rileggere il DB."""
        return any(
            s.get("type") == "stroke" and s.get("points")
            and not geo.looks_normalized(s.get("points", []))
            for s in self._strokes
        )

    def _clear_legacy_strokes(self) -> None:
        """Rimuove SOLO i tratti in formato legacy, preservando quelli già
        corretti — l'utente può poi ridisegnarli allineati. Nessuna
        migrazione automatica è possibile (vedi `ui.canvas_geometry`)."""
        self._snapshot()
        self._strokes[:] = [
            s for s in self._strokes
            if s.get("type") != "stroke" or geo.looks_normalized(s.get("points", []))
        ]
        self._push([{"op": "replace_all", "strokes": self._strokes}])
        self._update_all_canvases()

    def build_legacy_banner(self) -> ft.Control | None:
        """Avviso una tantum + azione "Cancella tratti precedenti" — `None`
        se non ci sono tratti legacy da segnalare."""
        if not self.can_manage or not self.has_legacy_strokes():
            return None

        banner_ref: list[ft.Container] = []

        def _on_clear(e: Any) -> None:
            self._clear_legacy_strokes()
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

    # ──────────────────────────────────────────────────────────────────────
    # Toolbar
    # ──────────────────────────────────────────────────────────────────────

    def build_toolbar(self, *, is_fs: bool) -> tuple[ft.Control, ft.Container]:
        """Ritorna `(top_row, toolbar_body)` — il chiamante li impila in una
        `ft.Column` dentro il proprio Container "chrome" (bordi
        arrotondati/ombra, invariato: è decorazione della vista, non del
        componente). `None` per entrambi i riferimenti equivale a "niente
        toolbar" — il chiamante non deve invocare questo metodo affatto se
        `not self.can_manage`."""
        mode_list: list[ft.Container] = []
        swatch_list: list[ft.Container] = []
        ersub_list: list[ft.Container] = []
        self._mode_refs[is_fs] = mode_list
        self._swatch_refs[is_fs] = swatch_list
        self._ersub_refs[is_fs] = ersub_list

        top_row_box = self._build_top_row(is_fs, mode_list, swatch_list)
        self._top_row_box[is_fs] = top_row_box

        body_content = self._build_toolbar_body(is_fs, ersub_list)
        switcher = ft.AnimatedSwitcher(
            content=body_content,
            duration=design.Duration.BASE,
            switch_in_curve=design.CURVE,
            switch_out_curve=design.CURVE,
            transition=ft.AnimatedSwitcherTransition.FADE,
        )
        self._toolbar_switcher[is_fs] = switcher

        toolbar_body = ft.Container(
            content=switcher,
            height=_TOOLBAR_BODY_H,
            padding=ft.Padding.symmetric(horizontal=design.Space.LG, vertical=design.Space.SM),
            bgcolor=design.CHROME.panel,
            alignment=ft.Alignment.CENTER,
        )
        self._toolbar_body[is_fs] = toolbar_body

        return top_row_box, toolbar_body

    def _build_top_row(self, is_fs: bool, mode_list: list, swatch_list: list) -> ft.Container:
        """Riga pillole modalità + swatch colore + annulla/cancella, in un
        Container che sorveglia la propria larghezza (`on_size_change`) per
        passare a icona-sola sotto `_TOP_ROW_COMPACT_BP` e/o le pastiglie
        colore su una riga propria sotto `_TOP_ROW_STACK_BP` — mai
        `wrap=True` (andrebbe a capo in modo imprevedibile, un salto
        verticale indipendente dal cambio modalità) né scroll (nasconderebbe
        controlli): entrambe le soglie si valutano una volta sola per
        ridimensionamento, il layout risultante è sempre stabile."""
        content = self._build_top_row_content(
            is_fs, mode_list, swatch_list,
            compact=self._top_row_compact[is_fs], stacked=self._top_row_stacked[is_fs])

        def _on_resize(e: ft.LayoutSizeChangeEvent) -> None:
            compact = e.width < _TOP_ROW_COMPACT_BP
            stacked = e.width < _TOP_ROW_STACK_BP
            if (compact == self._top_row_compact[is_fs]
                    and stacked == self._top_row_stacked[is_fs]):
                return
            self._top_row_compact[is_fs] = compact
            self._top_row_stacked[is_fs] = stacked
            box = self._top_row_box[is_fs]
            if box is None:
                return
            mode_list.clear()
            swatch_list.clear()
            box.content = self._build_top_row_content(
                is_fs, mode_list, swatch_list, compact=compact, stacked=stacked)
            try:
                box.update()
            except RuntimeError:
                pass

        return ft.Container(content=content, on_size_change=_on_resize)

    def _build_top_row_content(self, is_fs: bool, mode_list: list, swatch_list: list,
                                *, compact: bool, stacked: bool) -> ft.Control:
        def _mbtn(key: str, icon: Any, label: str) -> ft.Container:
            # BUG FIX (2026-08-25) — causa REALE del testo illeggibile nei
            # pulsanti modalità (confermato con un confronto diretto:
            # "Annulla"/"Cancella tutto", stesso identico Container con
            # `ink=True`+Row[Icon,Text], si leggono perfettamente — l'unica
            # differenza è che il LORO `ft.Text` riceve `color=` già al
            # costruttore, mentre qui il colore veniva impostato DOPO, con
            # `_style_mode_btn()` che muta `.color` su un `ft.Text` già
            # costruito ma mai ancora montato. Quella mutazione post-hoc
            # lascia lo stile del testo in uno stato che Flutter renderizza
            # mostrando solo la metà inferiore delle lettere minuscole
            # (le maiuscole, come "LARGHEZZA", non ne risentivano) — colore
            # impostato al costruttore, come già faceva `_action_btn`,
            # risolve.
            sel = key == self._draw_mode
            fg = design.T().on_primary_fill if sel else design.CHROME.text_muted
            row_children: list[ft.Control] = [ft.Icon(icon, size=15, color=fg)]
            if not compact:
                row_children.append(
                    ft.Text(label, size=design.Size.LABEL, weight=ft.FontWeight.BOLD,
                            font_family=design.Font.BODY, no_wrap=True, color=fg),
                )
            c = ft.Container(
                content=ft.Row(row_children, spacing=6, tight=True,
                               vertical_alignment=ft.CrossAxisAlignment.CENTER),
                # NIENTE `width` esplicito qui (né in modalità compatta né
                # estesa): un Container con `animate=` che passa da una
                # larghezza numerica a `None` (o viceversa) chiede a Flutter
                # di interpolare un `AnimatedContainer` verso una larghezza
                # non vincolata — animazione mal definita. La larghezza
                # resta SEMPRE intrinseca al contenuto (icona sola in
                # compatto, icona+testo altrimenti) — l'area di tocco
                # minima (40px) è garantita dal solo `padding`, mai da
                # `width`.
                height=40,
                padding=(ft.Padding.all(12) if compact else
                         ft.Padding.symmetric(horizontal=design.Space.MD, vertical=design.Space.SM)),
                border_radius=design.Radius.PILL,
                bgcolor=design.T().primary_fill if sel else "transparent",
                alignment=ft.Alignment.CENTER,
                tooltip=label if compact else None,
                on_click=lambda e, k=key: self._select_mode(k, is_fs),
                ink=True,
                animate_scale=ft.Animation(design.Duration.FAST, design.CURVE),
            )
            mode_list.append(c)
            return c

        mode_row = ft.Row([_mbtn(k, ic, lb) for k, ic, lb in _MODE_DEFS],
                           spacing=design.Space.XS)

        def _swatch(idx: int) -> ft.Container:
            c = ft.Container(
                content=ft.Container(bgcolor=PEN_COLORS[idx], border_radius=design.Radius.PILL,
                                     expand=True),
                width=40, height=40, border_radius=design.Radius.PILL,
                # Il pallino visivo resta piccolo (~24px, via padding
                # generoso): solo l'AREA di tocco cresce a 40px.
                padding=8,
                on_click=lambda e, i=idx: self._select_color(i),
                ink=True,
                animate_scale=ft.Animation(design.Duration.FAST, design.CURVE),
                tooltip="Colore del pennarello",
            )
            self._style_swatch(c, idx == self._pen_color_idx)
            swatch_list.append(c)
            return c

        swatches = ft.Row([_swatch(i) for i in range(len(PEN_COLORS))], spacing=design.Space.XS)

        def _action_btn(icon: Any, label: str, bg: str, fg: str, fn: Any) -> ft.Container:
            row_children: list[ft.Control] = [ft.Icon(icon, size=14, color=fg)]
            if not compact:
                row_children.append(
                    ft.Text(label, size=design.Size.LABEL, color=fg, weight=ft.FontWeight.BOLD,
                            font_family=design.Font.BODY, no_wrap=True),
                )
            return ft.Container(
                content=ft.Row(row_children, spacing=5, tight=True,
                               vertical_alignment=ft.CrossAxisAlignment.CENTER),
                # Vedi commento in `_mbtn`: mai `width` numerico↔`None` sotto
                # `animate`/`animate_scale` — stessa causa dello stesso bug.
                height=40,
                padding=(ft.Padding.all(12) if compact else
                         ft.Padding.symmetric(horizontal=design.Space.MD, vertical=design.Space.SM)),
                border_radius=design.Radius.PILL,
                bgcolor=bg,
                alignment=ft.Alignment.CENTER,
                tooltip=label if compact else None,
                on_click=fn, ink=True,
                animate_scale=ft.Animation(design.Duration.FAST, design.CURVE),
            )

        undo_btn = _action_btn(ft.Icons.UNDO, "Annulla",
                               design.CHROME.btn, design.CHROME.text,
                               lambda e: self.undo())
        clearall_btn = _action_btn(ft.Icons.DELETE_FOREVER_OUTLINED, "Cancella tutto",
                                   design.CHROME.danger, design.CHROME.text,
                                   lambda e: self.clear_all())

        def _sep() -> ft.Container:
            return ft.Container(width=1, height=24,
                                bgcolor=ft.Colors.with_opacity(0.5, design.CHROME.border),
                                margin=ft.Margin.only(left=design.Space.SM, right=design.Space.SM))

        if stacked:
            # BUG FIX (2026-08-25, richiesta Davide: "ho dovuto allargare la
            # scheda su pc per vedere cancella tutto") — sotto
            # `_TOP_ROW_STACK_BP` le 7 pastiglie colore non entrano MAI
            # insieme al resto sulla stessa riga (nemmeno in modalità
            # compatta): qui vanno su una riga propria, sotto
            # modalità/annulla/cancella. Layout stabile — deciso una volta
            # sola per ridimensionamento da `_on_resize`, mai un salto
            # imprevedibile come lo era il vecchio `wrap=True`.
            return ft.Column(
                [
                    ft.Row([mode_row, _sep(), undo_btn, clearall_btn],
                           spacing=design.Space.SM, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    swatches,
                ],
                spacing=design.Space.SM,
            )

        return ft.Row(
            [mode_row, _sep(), swatches, _sep(), undo_btn, clearall_btn],
            spacing=design.Space.SM, run_spacing=design.Space.SM,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    # ── Body dinamico (cambia con la modalità, altezza sempre fissa) ────

    def _build_toolbar_body(self, is_fs: bool, ersub_list: list) -> ft.Control:
        mode = self._draw_mode

        def _value_badge(text: str) -> ft.Container:
            return ft.Container(
                content=ft.Text(text, size=design.Size.LABEL, color=design.CHROME.text,
                                font_family=design.Font.MONO, weight=ft.FontWeight.BOLD,
                                text_align=ft.TextAlign.CENTER),
                bgcolor=design.CHROME.btn, border_radius=design.Radius.SM,
                padding=ft.Padding.symmetric(horizontal=design.Space.SM, vertical=2),
                width=48, alignment=ft.Alignment.CENTER,
            )

        def _slider_label(text: str) -> ft.Text:
            return ft.Text(text, size=design.Size.LABEL, color=design.CHROME.text_dim,
                           weight=ft.FontWeight.BOLD, font_family=design.Font.BODY,
                           style=ft.TextStyle(letter_spacing=0.8))

        if mode == "pen":
            content: ft.Control = ft.Row(
                [
                    _slider_label("LARGHEZZA"),
                    ft.Slider(
                        min=1, max=30, value=self._pen_width, divisions=29,
                        active_color=design.T().primary_fill, thumb_color=design.CHROME.text,
                        inactive_color=design.CHROME.border, expand=True, height=32,
                        on_change=lambda e: self._on_pen_width_change(e, is_fs),
                    ),
                    _value_badge(f"{self._pen_width:.0f}px"),
                ],
                spacing=design.Space.MD, vertical_alignment=ft.CrossAxisAlignment.CENTER,
                key="pen",
            )
        elif mode == "eraser":
            ersub_list.clear()

            def _esbtn(key: str, label: str) -> ft.Container:
                # BUG FIX (2026-08-25): stessa causa e stesso rimedio di
                # `_mbtn` — `animate=` (AnimatedContainer) tagliava le
                # lettere minuscole di "Tratto"/"Libera"; `animate_scale=`
                # no. Colore impostato al costruttore invece che mutato
                # dopo con `_style_ersub_btn` (chiamata comunque, serve per
                # gli aggiornamenti live da `_select_eraser_sub`).
                sel = key == self._eraser_sub
                c = ft.Container(
                    content=ft.Text(label, size=design.Size.LABEL, weight=ft.FontWeight.BOLD,
                                    font_family=design.Font.BODY, no_wrap=True,
                                    color=design.T().on_primary if sel else design.CHROME.text_muted),
                    padding=ft.Padding.symmetric(horizontal=design.Space.MD,
                                                 vertical=design.Space.XS + 2),
                    border_radius=design.Radius.PILL,
                    bgcolor=design.T().primary_fill if sel else design.CHROME.btn,
                    on_click=lambda e, k=key: self._select_eraser_sub(k, is_fs),
                    ink=True,
                    animate_scale=ft.Animation(design.Duration.FAST, design.CURVE),
                )
                ersub_list.append(c)
                return c

            content = ft.Row(
                [
                    _esbtn("stroke", "Tratto"),
                    _esbtn("pixel", "Libera"),
                    ft.Container(width=design.Space.SM),
                    _slider_label("DIMENSIONE"),
                    ft.Slider(
                        min=5, max=60, value=self._eraser_size, divisions=55,
                        active_color=design.CHROME.text_muted, thumb_color=design.CHROME.text,
                        inactive_color=design.CHROME.border, expand=True, height=32,
                        on_change=lambda e: self._on_eraser_size_change(e, is_fs),
                    ),
                    _value_badge(f"{self._eraser_size:.0f}px"),
                ],
                spacing=design.Space.SM, vertical_alignment=ft.CrossAxisAlignment.CENTER,
                key="eraser",
            )
        else:
            # "move" — MAI il fallback vuoto dell'implementazione originale
            # (vedi punto 1 del docstring del modulo): un suggerimento
            # testuale della stessa altezza di uno slider, non un buco nel
            # layout.
            content = ft.Row(
                [
                    ft.Icon(ft.Icons.OPEN_WITH, size=14, color=design.CHROME.text_dim),
                    ft.Text(
                        "Trascina per spostare la vista  ·  pizzica per zoom",
                        size=design.Size.LABEL, color=design.CHROME.text_dim,
                        weight=ft.FontWeight.BOLD, font_family=design.Font.BODY,
                    ),
                ],
                spacing=design.Space.SM, alignment=ft.MainAxisAlignment.CENTER,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                key="move",
            )

        return content

    # ── Stile dei controlli (condiviso build ↔ selezione) ────────────────

    @staticmethod
    def _style_mode_btn(btn: ft.Container, sel: bool) -> None:
        btn.bgcolor = design.T().primary_fill if sel else "transparent"
        fg = design.T().on_primary_fill if sel else design.CHROME.text_muted
        for c in getattr(btn.content, "controls", []):
            if isinstance(c, (ft.Icon, ft.Text)):
                c.color = fg

    @staticmethod
    def _style_swatch(sw: ft.Container, sel: bool) -> None:
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

    # ── Slider callbacks ─────────────────────────────────────────────────

    @staticmethod
    def _set_badge(ctrl: Any, text: str) -> None:
        target = ctrl.content if isinstance(ctrl, ft.Container) else ctrl
        if isinstance(target, ft.Text):
            target.value = text
            try:
                target.update()
            except RuntimeError:
                pass

    def _on_pen_width_change(self, e: Any, is_fs: bool) -> None:
        self._pen_width = float(e.control.value)
        body = self._toolbar_switcher[is_fs]
        if body and body.content and hasattr(body.content, "controls"):
            ctrls = cast(list, cast(Any, body.content).controls)
            if len(ctrls) >= 3:
                self._set_badge(ctrls[2], f"{self._pen_width:.0f}px")

    def _on_eraser_size_change(self, e: Any, is_fs: bool) -> None:
        self._eraser_size = float(e.control.value)
        body = self._toolbar_switcher[is_fs]
        if body and body.content and hasattr(body.content, "controls"):
            ctrls = cast(list, cast(Any, body.content).controls)
            if len(ctrls) >= 6:
                self._set_badge(ctrls[5], f"{self._eraser_size:.0f}px")

    # ── Mode / color / eraser-sub selectors ──────────────────────────────

    def _select_mode(self, key: str, is_fs: bool) -> None:
        self._draw_mode = key
        self._eraser_cursor_pos = None

        for panel_fs, viewer in self._interactive_viewer.items():
            if viewer is None:
                continue
            # `scale_enabled` segue `pan_enabled` — vedi il commento in
            # `build_draw_area` (BUG FIX 2026-08-26): se restasse acceso da
            # solo in Penna/Gomma, il suo `ScaleGestureRecognizer` resterebbe
            # comunque nella gesture arena e ritarderebbe l'inizio del
            # tratto su schermo touch reale.
            allow_viewer_gestures = (key == "move") or not self.can_manage
            viewer.pan_enabled = allow_viewer_gestures
            viewer.scale_enabled = allow_viewer_gestures
            try:
                viewer.update()
            except RuntimeError:
                pass

        # Ricostruisce il layer gesture di OGNI pannello montato (inline e
        # schermo intero condividono `self._draw_mode`) — stesso principio
        # del BUG FIX 2026-08-20 (zoom rotto su smartphone).
        for panel_fs, stack in self._draw_stack.items():
            canvas = self._canvas[panel_fs]
            if stack is None or canvas is None:
                continue
            stack.controls[1] = self._canvas_layer_for_mode(key, panel_fs, canvas)
            self._safe_update(stack, f"_select_mode/stack panel_fs={panel_fs}")

        for panel_fs, mode_list in self._mode_refs.items():
            for i, (k, _, _) in enumerate(_MODE_DEFS):
                if i >= len(mode_list):
                    break
                self._style_mode_btn(mode_list[i], k == key)
                try:
                    mode_list[i].update()
                except RuntimeError:
                    pass

        # Aggiorna il body DI ENTRAMBI i pannelli — l'AnimatedSwitcher
        # anima solo l'opacità (mai la dimensione, il Container esterno ha
        # altezza fissa `_TOOLBAR_BODY_H`), lo stato logico è impostato
        # subito, sincrono.
        for panel_fs, switcher in self._toolbar_switcher.items():
            if switcher is None:
                continue
            switcher.content = self._build_toolbar_body(panel_fs, self._ersub_refs[panel_fs])
            try:
                switcher.update()
            except RuntimeError:
                pass

    def _select_color(self, idx: int) -> None:
        self._pen_color_idx = idx
        for swatch_list in self._swatch_refs.values():
            for i, s in enumerate(swatch_list):
                self._style_swatch(s, i == idx)
                try:
                    s.update()
                except RuntimeError:
                    pass

    def _select_eraser_sub(self, key: str, is_fs: bool) -> None:
        self._eraser_sub = key
        for ersub_list in self._ersub_refs.values():
            for i, btn in enumerate(ersub_list):
                sel = (i == 0 and key == "stroke") or (i == 1 and key == "pixel")
                self._style_ersub_btn(btn, sel)
                try:
                    btn.update()
                except RuntimeError:
                    pass

    def refresh_strokes(self, strokes: list[dict]) -> None:
        """Sostituisce `self._strokes` con una lista arrivata da FUORI
        (es. un evento remoto applicato sulla replica di un giocatore in
        sola lettura, che non passa mai da `on_batch`/`_push` di questa
        stessa istanza) e ridisegna — no-op se `strokes` è identica a
        quella già in memoria (evita un ridisegno ad ogni giro del ciclo
        di polling quando nulla è realmente cambiato). Usata da
        `world_view.py::_open_shared_map` per un giocatore che guarda una
        mappa condivisa senza poterla modificare."""
        if strokes == self._strokes:
            return
        self._strokes = strokes
        self.gm.annotations = json.dumps(strokes)
        self._update_all_canvases()

    # ──────────────────────────────────────────────────────────────────────
    # Ciclo di vita
    # ──────────────────────────────────────────────────────────────────────

    def teardown_fullscreen(self) -> None:
        """Da chiamare alla chiusura dell'overlay a schermo intero — azzera
        SOLO i riferimenti del pannello fullscreen (canvas/stack/viewer/
        toolbar), il pannello inline (se ancora aperto) e lo stato di
        disegno condiviso (`self._strokes`/modalità/colore) restano
        invariati."""
        self._canvas[True] = None
        self._draw_stack[True] = None
        self._interactive_viewer[True] = None
        self._mode_refs[True] = []
        self._swatch_refs[True] = []
        self._ersub_refs[True] = []
        self._toolbar_body[True] = None
        self._toolbar_switcher[True] = None
        self._top_row_box[True] = None
        canvas = self._canvas[False]
        if canvas is not None:
            self._redraw_canvas(canvas, False)
            self._safe_update(canvas, "teardown_fullscreen")
