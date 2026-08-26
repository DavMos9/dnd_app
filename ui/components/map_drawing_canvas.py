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

  4. **Zoom che si perde cambiando modalità + pizzico impossibile mentre si
     disegna** (2026-08-26, quarto giro — richiesta Davide dopo il fix del
     ritardo del tratto): la versione precedente smontava e rimontava un
     `ft.InteractiveViewer` DIVERSO ad ogni cambio Penna↔Sposta (necessario
     allora per togliere il suo `ScaleGestureRecognizer` dalla gesture arena
     — vedi punto sopra). Ma un `InteractiveViewer` appena creato riparte
     SEMPRE dalla trasformazione identità: la Matrix4 interna che Flutter
     mantiene per lo zoom/pan viveva nel vecchio widget, andava persa ad ogni
     smontaggio. Qui l'`InteractiveViewer` è UNICO per pannello, montato una
     sola volta e mai più sostituito per tutta la vita del pannello — lo
     zoom resta quindi sempre quello impostato, indipendentemente dalla
     modalità attiva. Il disegno NON usa più un secondo `ft.GestureDetector`
     con `on_pan_*` (che rimonterebbe un SECONDO widget con un SECONDO
     `GestureRecognizer` — esattamente la configurazione che il punto 2 ha
     già dimostrato causare 1-2s di ritardo): usa invece
     `on_interaction_start/update/end` — gli stessi identici eventi
     `onScaleStart/Update/End` che l'`InteractiveViewer` già cablava
     comunque incondizionatamente — letti DIRETTAMENTE dallo stesso widget,
     mai un secondo recognizer. Un tocco singolo (`pointer_count == 1`) in
     Penna/Gomma disegna/cancella; due o più tocchi pizzicano SEMPRE
     (`scale_enabled=True` in ogni modalità) per zoommare — vedi
     `_on_interaction_start()` per la logica completa e la derivazione
     matematica (verificata contro il sorgente reale di Flutter,
     `interactive_viewer.dart`, non per analogia).

  5. **"Pallini" lasciati sullo schermo durante un pizzico** (2026-08-26,
     quinto giro): il punto 4 riclassifica il gesto da disegno/gomma a
     "view" non appena arriva un secondo dito, ma solo IN `_on_interaction_
     update()` — nel frattempo il primo dito, da solo, aveva già dipinto
     qualcosa (il cursore della gomma all'istante del tocco, o un
     segmento cortissimo — che coi capi arrotondati sembra un puntino —
     dopo anche un solo fotogramma di trascinamento). Ripulire DOPO che è
     già stato disegnato lascia comunque un fotogramma visibile sul
     client reale (un giro websocket separato dalla ripulitura), tanto
     più percepibile quanto più la connessione è lenta — Davide l'ha
     confermato ancora presente dopo il fix del punto 4, con una diagnosi
     corretta ("dato che non metto le dita in simultanea... fa il puntino
     dove tocca prima il dito"). Qui il fix è strutturale, non più
     correttivo: `_on_interaction_start()`/`_on_interaction_update()` non
     dipingono più NULLA (né cursore gomma né tratto penna) finché non è
     trascorsa `_INTENT_CONFIRM_S` dall'inizio del gesto con un solo dito
     — se un secondo dito arriva prima (il caso normale di un pizzico),
     zero pennellate sono MAI arrivate al client, nulla da ripulire. I
     punti toccati durante l'attesa restano bufferizzati
     (`self._current_points` per la penna, `self._pending_erase_points`
     per la gomma) e vengono "recuperati" tutti insieme non appena la
     soglia scade o il gesto termina prima di allora (tocco singolo
     rapido) — nessun punto viene mai perso, solo il primo ridisegno
     visibile è ritardato di un tempo sotto la soglia di percezione umana
     del ritardo.

  6. **Il segno restava al sollevamento dell'ULTIMO dito, non più al primo
     tocco** (2026-08-26, sesto giro): il punto 5 elimina la pennellata
     prematura all'INIZIO di un pizzico, ma Davide ha segnalato che il
     segno si spostava alla FINE — "rimane il segno quando tolgo l'ultimo
     dito dallo schermo e non più quando metto il primo dito". Causa
     verificata sul sorgente reale di Flutter
     (`packages/flutter/lib/src/gestures/scale.dart::_reconfigure()`, non
     per analogia): il gesto "view" a due dita non finisce sempre in un
     colpo solo. Quando il PRIMO dei due si solleva, Flutter chiude quel
     gesto (`onEnd`, che qui arriva come `_on_interaction_end` con
     `kind == "view"`, innocuo) — ma se il dito RIMASTO si muove anche
     minimamente prima di sollevarsi a sua volta (fisiologico: raramente
     due dita si staccano in un istante perfettamente identico), Flutter
     RIAPRE un gesto nuovo per quel dito solo (`onStart`, un secondo
     `_on_interaction_start` con `pointer_count == 1`) — SENZA che l'utente
     abbia davvero staccato e ritoccato lo schermo. Prima di questo fix,
     `_on_interaction_start()` non aveva modo di distinguere questa "coda"
     fantasma da un tocco genuino: la classificava come disegno/gomma —
     in Gomma, `_on_interaction_end()` del punto 5 applica DELIBERATAMENTE
     la cancellazione bufferizzata anche su un gesto brevissimo (per non
     perdere un vero tap rapido), quindi cancellava qualcosa nel punto
     esatto in cui l'ultimo dito si è sollevato. Qui `_on_interaction_start()`
     tiene traccia di quando l'ULTIMO gesto "view" è terminato
     (`self._last_view_end_t`): un nuovo tocco a un dito solo entro
     `_VIEW_TAIL_GRACE_S` da quella fine viene trattato anch'esso come
     "view" (ignorato ai fini di disegno/gomma) invece che come un tocco
     nuovo — un vero tocco deliberato subito dopo un pizzico resta comunque
     reattivo, solo ritardato di una soglia sotto la percezione umana,
     stesso principio del punto 5.

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
import time
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

#: Limiti di zoom dell'`InteractiveViewer` — condivisi con lo specchio
#: `_view_scale`/`_view_offset` (vedi `__init__`) perché quello specchio
#: deve restare numericamente coerente con la trasformazione VERA che
#: Flutter applica al widget: se i limiti divergessero, un tratto disegnato
#: subito dopo uno zoom al limite finirebbe leggermente disallineato.
_MIN_SCALE = 1.0
_MAX_SCALE = 5.0

#: Finestra di conferma prima di dipingere QUALUNQUE segno visibile
#: (cursore gomma o linea penna) dal tocco di un dito solo — vedi il punto
#: 5 del docstring del modulo (BUG FIX 2026-08-26, "pallini" residui
#: durante il pizzico). Un dito genuino resta comunque reattivo: la soglia
#: è sotto la percezione umana di "ritardo" (~100ms).
_INTENT_CONFIRM_S = 0.08

#: Finestra di "diffidenza" dopo la fine di un gesto "view" (pizzico/pan) —
#: vedi il punto 6 del docstring del modulo (BUG FIX 2026-08-26, sesto
#: giro): il `ScaleGestureRecognizer` di Flutter (verificato sul sorgente
#: reale, `packages/flutter/lib/src/gestures/scale.dart::_reconfigure()`)
#: chiude il gesto corrente (`onEnd`) a OGNI cambio nel numero di dita —
#: anche quando un dito si solleva mentre l'altro resta giù, non solo
#: quando se ne aggiunge uno — e lo riapre (`onStart`) per le dita rimaste,
#: SENZA che l'utente abbia davvero staccato e ritoccato lo schermo. Un
#: `_on_interaction_start()` con un dito solo che arriva a meno di questa
#: soglia dalla fine dell'ultimo gesto "view" è quasi certamente questa
#: "coda" fantasma, non un tocco nuovo — vedi lì.
_VIEW_TAIL_GRACE_S = 0.15


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
        #: L'unico `ft.InteractiveViewer` del pannello — costruito una
        #: sola volta in `build_draw_area()` e MAI più sostituito (vedi
        #: punto 4 del docstring del modulo): la sua Matrix4 interna di
        #: zoom/pan sopravvive così a ogni cambio Penna/Gomma/Sposta.
        #: `_select_mode()` ne cambia solo `pan_enabled`, mai l'identità
        #: del widget.
        self._viewer: dict[bool, ft.InteractiveViewer | None] = {False: None, True: None}
        #: Specchio Python della trasformazione (scala + traslazione, in
        #: pixel del riquadro) che l'`InteractiveViewer` applica al suo
        #: `content` — Flet non espone la Matrix4 interna come proprietà
        #: leggibile, quindi va ricostruita qui dagli stessi eventi
        #: `on_interaction_*`, con la STESSA identica formula usata dal
        #: sorgente Flutter (`interactive_viewer.dart::_onScaleUpdate`,
        #: verificato leggendolo — non per analogia). Serve SOLO per
        #: convertire un tocco a un dito (disegno/gomma) da coordinate di
        #: schermo a coordinate del contenuto — vedi `_to_scene()` e
        #: `_on_interaction_start()`. Riparte da identità (1.0, [0,0]) ad
        #: ogni nuova costruzione dell'`InteractiveViewer` (vedi
        #: `build_draw_area()`), perché lì riparte anche la Matrix4 vera.
        self._view_scale: dict[bool, float] = {False: 1.0, True: 1.0}
        self._view_offset: dict[bool, list[float]] = {False: [0.0, 0.0], True: [0.0, 0.0]}
        #: Tipo del gesto in corso ("draw" | "erase" | "view" | `None`),
        #: deciso UNA SOLA VOLTA in `_on_interaction_start()` e mai
        #: rivalutato durante lo stesso gesto (stesso principio del
        #: `_gestureType` di Flutter) — vedi lì per il perché.
        self._gesture_kind: dict[bool, str | None] = {False: None, True: None}
        #: Punto focale iniziale del gesto corrente, già convertito in
        #: coordinate di contenuto (`_to_scene()`), e scala del pannello
        #: all'inizio del gesto — entrambi servono a `_on_interaction_update()`
        #: per ricalcolare `_view_scale`/`_view_offset` senza dover
        #: accumulare un delta per frame (stessa formula di Flutter: il
        #: punto di contenuto sotto il fuoco resta fisso per tutto il
        #: gesto).
        self._gesture_ref_focal: dict[bool, tuple[float, float] | None] = {False: None, True: None}
        self._gesture_scale_start: dict[bool, float] = {False: 1.0, True: 1.0}
        #: Istante (`time.monotonic()`) in cui il gesto CORRENTE è
        #: iniziato con un dito solo — vedi punto 5 del docstring del
        #: modulo. `_gesture_painted` diventa `True` la prima volta che
        #: il gesto ha DAVVERO dipinto qualcosa (dopo `_INTENT_CONFIRM_S`,
        #: o subito se già `True` in questo stesso gesto): finché resta
        #: `False`, niente è mai arrivato al client, quindi una eventuale
        #: riclassificazione a "view" non ha nulla da ripulire.
        self._gesture_start_t: dict[bool, float] = {False: 0.0, True: 0.0}
        self._gesture_painted: dict[bool, bool] = {False: False, True: False}
        #: Punti (coordinate di contenuto) toccati dalla gomma PRIMA che
        #: `_INTENT_CONFIRM_S` scada — rigiocati in ordine non appena la
        #: soglia scade (o al sollevamento del dito, se prima), così un
        #: tocco/trascinamento genuino non perde nulla di ciò che ha
        #: "cancellato" durante l'attesa. Il tratto penna non ha bisogno
        #: dell'equivalente: `self._current_points` bufferizza già tutto,
        #: `_redraw_live_stroke()` disegna l'intera polilinea in un colpo
        #: solo appena si comincia a dipingere.
        self._pending_erase_points: dict[bool, list[list[float]]] = {False: [], True: []}
        #: Istante in cui l'ULTIMO gesto "view" è terminato per questo
        #: pannello — vedi punto 6 del docstring del modulo. Parte
        #: volutamente lontanissimo nel passato: prima di qualunque gesto
        #: reale, `_on_interaction_start()` non deve MAI sospettare una
        #: "coda" fantasma.
        self._last_view_end_t: dict[bool, float] = {False: -1e9, True: -1e9}
        #: Dimensione CORRENTE (pixel) del riquadro — letta da
        #: `on_size_change`, MAI sincrona (Flet 0.86.5 non offre altro
        #: modo). Parte a [0,0]: un tratto completato prima del primo
        #: evento userebbe un riquadro sconosciuto — vedi `_box_ready`.
        self._box_size: dict[bool, list[float]] = {False: [0.0, 0.0], True: [0.0, 0.0]}
        #: `True` alla PRIMA `on_box_resize()` per quel pannello, mai più
        #: `False` dopo (il riquadro, una volta noto, resta valido per
        #: tutta la sessione). Finché è `False`, `_on_interaction_start()`
        #: tratta ogni gesto come "view" (mai disegno/gomma) — vedi punto 2
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
        """Immagine + canvas dentro un `ft.InteractiveViewer` UNICO per il
        pannello — montato una sola volta, mai più ricreato ai cambi
        modalità (vedi punto 4 del docstring del modulo: uno smontaggio
        avrebbe azzerato lo zoom). Il chiamante deve avvolgere il risultato
        in un `ft.Container(expand=True, on_size_change=lambda e:
        self._canvas.on_box_resize(is_fs, e))` — l'evento non può essere
        intercettato qui dentro (Flet non offre `on_resize` su un controllo
        qualunque, solo su un `Container` che lo racchiude).

        Nessun `ft.GestureDetector` separato per disegno/gomma: quegli
        eventi arrivano da `on_interaction_start/update/end`, GLI STESSI
        `onScaleStart/Update/End` che l'`InteractiveViewer` cabla comunque
        (vedi `_on_interaction_start()`) — un solo widget, un solo
        `GestureRecognizer`, per costruzione nessuna gara nell'arena
        possibile con nient'altro."""
        # Riparte da identità: un NUOVO `InteractiveViewer` (qui sotto)
        # riparte sempre con Matrix4 identità — lo specchio deve restare
        # coerente (vedi il commento su `self._view_scale` nell'`__init__`).
        self._view_scale[is_fs] = 1.0
        self._view_offset[is_fs] = [0.0, 0.0]
        self._gesture_kind[is_fs] = None

        # BUG FIX (2026-08-26, seguito a v0.3.11) — Davide: "quando seleziono
        # sposta fa un brutto effetto scatto... come se l'intera scheda si
        # ricaricasse, la mappa scompare e poi ricompare". Riprodotto dal
        # vivo (screenshot a raffica e video, non per ipotesi — vedi il
        # metodo usato nel changelog): l'immagine spariva per ~100ms SOLO
        # nelle transizioni che cambiano `pan_enabled` sull'`InteractiveViewer`
        # (Penna/Gomma → Sposta e viceversa) — MAI in Penna → Gomma (che non
        # lo tocca affatto), confermando che è proprio quel cambio a
        # innescarlo. Due tentativi PRECEDENTI, entrambi VERIFICATI E
        # SCARTATI (non solo per teoria — riprodotti dal vivo dopo ognuno):
        #   1. Una `key=` stabile su Image/Canvas/Stack, nell'ipotesi che
        #      Flutter perdesse la loro identità quando l'InteractiveViewer
        #      ricostruisce il suo `content` — non ha cambiato nulla.
        #   2. Raggruppare tutte le mutazioni di `_select_mode()` in un solo
        #      `page.update()` finale invece di più giri separati (vedi
        #      `_select_mode()`) — nemmeno questo ha eliminato il fotogramma
        #      vuoto da solo.
        # Causa REALE: `ft.Image` ha una proprietà dedicata a esattamente
        # questo sintomo — `gapless_playback` — la cui documentazione lo
        # descrive alla lettera: "Whether to continue showing the old image
        # (True), or briefly show nothing (False), when the image provider
        # changes." Il cambio di `pan_enabled` fa sì che Flutter tratti
        # l'`Image` come se il suo "image provider" fosse cambiato — senza
        # `gapless_playback=True` (il default è `False`), Flutter mostra
        # apposta un fotogramma vuoto durante la transizione, per design.
        # Le `key=` restano comunque (buona pratica di identità stabile,
        # anche se qui non erano la causa) e il batch di `page.update()`
        # resta come pulizia del codice — nessuno dei due va rimosso, ma
        # nessuno dei due basta da solo: è `gapless_playback=True`
        # sull'`Image` (poco sotto) il fix verificato.
        img_key = f"map-img-{id(self)}-{is_fs}"
        canvas_key = f"map-canvas-{id(self)}-{is_fs}"
        stack_key = f"map-stack-{id(self)}-{is_fs}"

        canvas = cv.Canvas(expand=True, key=canvas_key)
        self._canvas[is_fs] = canvas
        self._redraw_canvas(canvas, is_fs)

        if self.gm.image_data:
            img_layer: ft.Control = ft.Image(
                src=data_uri(self.gm.image_data), fit=ft.BoxFit.CONTAIN, expand=True,
                key=img_key, gapless_playback=True,
            )
        else:
            img_layer = ft.Container(
                expand=True,
                key=img_key,
                content=ft.Column(
                    [ft.Icon(ft.Icons.MAP_OUTLINED, size=64, color=design.T().border),
                     ft.Text("Nessuna immagine", size=13, color=design.T().text_3)],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
                bgcolor=design.T().surface_alt,
                shadow=design.elevation(1), border_radius=design.Radius.MD,
            )

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
        stack = ft.Stack([img_layer, canvas], expand=True, fit=ft.StackFit.EXPAND, key=stack_key)
        self._draw_stack[is_fs] = stack

        viewer = ft.InteractiveViewer(
            content=stack,
            pan_enabled=(not self.can_manage) or self._draw_mode == "move",
            scale_enabled=True,
            trackpad_scroll_causes_scale=True,
            min_scale=_MIN_SCALE, max_scale=_MAX_SCALE,
            # Come il `drag_interval=16` del vecchio `GestureDetector` di
            # disegno: senza questo, il default di 200ms renderebbe il
            # tratto in corso a scatti visibili durante il trascinamento.
            interaction_update_interval=16,
            on_interaction_start=lambda e, c=canvas: self._on_interaction_start(e, c),
            on_interaction_update=lambda e, c=canvas: self._on_interaction_update(e, c),
            on_interaction_end=lambda e, c=canvas: self._on_interaction_end(e, c),
        )
        self._viewer[is_fs] = viewer
        return viewer

    def on_box_resize(self, is_fs: bool, e: ft.LayoutSizeChangeEvent) -> None:
        box = self._box_size[is_fs]
        box[0], box[1] = e.width, e.height
        self._box_ready[is_fs] = True

        canvas = self._canvas[is_fs]
        if canvas is not None:
            self._redraw_canvas(canvas, is_fs)
            self._safe_update(canvas, f"on_box_resize is_fs={is_fs}")

    # ──────────────────────────────────────────────────────────────────────
    # Conversione schermo → contenuto (zoom/pan)
    # ──────────────────────────────────────────────────────────────────────

    def _to_scene(self, is_fs: bool, vx: float, vy: float) -> tuple[float, float]:
        """Converte un punto in coordinate di SCHERMO (quelle riportate da
        `local_focal_point`, relative al riquadro dell'`InteractiveViewer`,
        MAI trasformate dal suo zoom) in coordinate di CONTENUTO (quelle
        che usa tutta la matematica esistente di disegno/gomma/normalizzazione
        — identiche a `local_position` di prima di questo fix, quando
        l'`InteractiveViewer` non era mai montato mentre si disegnava).

        `viewportPoint = scala * contentPoint + traslazione` è la stessa
        relazione che Flutter mantiene nella sua Matrix4 interna — vedi
        `_on_interaction_update()` per la derivazione completa."""
        s = self._view_scale[is_fs]
        tx, ty = self._view_offset[is_fs]
        return (vx - tx) / s, (vy - ty) / s

    def _clamp_view_offset(self, is_fs: bool, s: float, tx: float, ty: float) -> tuple[float, float]:
        """Riproduce il vincolo che Flutter applica quando `boundary_margin`
        è zero (il valore che questo componente usa sempre): il contenuto
        (che a scala 1.0 riempie ESATTAMENTE il riquadro, perché `content`
        è uno `Stack(expand=True)` dentro un `InteractiveViewer(constrained=
        True)`, il default) non può mai scoprire spazio vuoto oltre i propri
        bordi. A scala `s`, il contenuto scalato misura `s * box`: la
        traslazione valida è quindi in `[box - s*box, 0]` su ogni asse —
        `[0, 0]` esatto quando `s == 1.0` (nessun pan possibile senza zoom,
        `min_scale` di questo componente è per l'appunto 1.0). Senza questo
        vincolo lo specchio Python divergerebbe dalla Matrix4 vera ogni
        volta che un pan reale tocca il bordo, disallineando il prossimo
        tratto disegnato — lo stesso tipo di bug silenzioso già visto nel
        punto 2 del docstring del modulo, qui per una causa diversa."""
        vw, vh = self._box_size[is_fs]
        min_tx, min_ty = vw - s * vw, vh - s * vh
        return min(0.0, max(min_tx, tx)), min(0.0, max(min_ty, ty))

    def _apply_view_update(self, is_fs: bool, e: ft.ScaleUpdateEvent) -> None:
        """Aggiorna `_view_scale`/`_view_offset` da un evento "view" —
        stessa formula di Flutter (`interactive_viewer.dart::
        _onScaleUpdate`, verificata sul sorgente reale — vedi il commento
        su `self._view_scale` nell'`__init__`): il punto di CONTENUTO che
        si trovava sotto il fuoco all'inizio del gesto (`_gesture_ref_focal`,
        già in coordinate di contenuto) resta sotto il fuoco ATTUALE per
        tutta la durata del gesto, sia che cambi solo la traslazione (un
        dito, modalità "Sposta") sia che cambi anche la scala (pizzico):
        entrambi i casi, in Flutter, si riducono alla STESSA equazione —
        non serve distinguerli qui. Chiamata sia dal ramo "view" normale di
        `_on_interaction_update()` sia dalla riclassificazione
        disegno/gomma → view (stesso evento, applicato subito invece di
        aspettare il fotogramma successivo)."""
        ref = self._gesture_ref_focal[is_fs]
        if ref is None:
            return
        s_new = max(_MIN_SCALE, min(_MAX_SCALE, self._gesture_scale_start[is_fs] * e.scale))
        fx, fy = e.local_focal_point.x, e.local_focal_point.y
        tx, ty = self._clamp_view_offset(is_fs, s_new, fx - s_new * ref[0], fy - s_new * ref[1])
        self._view_scale[is_fs] = s_new
        self._view_offset[is_fs] = [tx, ty]

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
        `_on_interaction_update()` in modalità Penna durante un trascinamento in
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

    def _on_interaction_start(self, e: ft.ScaleStartEvent, canvas: cv.Canvas) -> None:
        """Un solo `GestureRecognizer` per pannello (quello, sempre presente,
        dell'`InteractiveViewer` — vedi punto 4 del docstring del modulo):
        decide QUI se il gesto è disegno/gomma o zoom/pan, in base
        all'unica informazione disponibile in questo istante
        (`pointer_count`). Rivalutato UNA volta sola, in
        `_on_interaction_update()`, SOLO nel verso disegno/gomma → view
        (mai il contrario): un pizzico vero raramente tocca lo schermo con
        entrambe le dita nello stesso istante, quindi la prima dito arriva
        sempre da solo qui — vedi il commento nel ramo `pointer_count >= 2`
        di `_on_interaction_update()` per il perché (BUG FIX 2026-08-26,
        "pallino" lasciato dalla gomma durante un pizzico)."""
        is_fs = canvas is self._canvas[True]
        view = (
            self._draw_mode == "move"
            or not self.can_manage
            or not self._box_ready[is_fs]  # box ancora sconosciuto: vedi punto 2
            or e.pointer_count >= 2         # due o più dita: sempre zoom/pan
        )
        # Coda fantasma di un pizzico appena finito — vedi punto 6 del
        # docstring del modulo: Flutter può riaprire un gesto a un dito
        # solo per il dito rimasto quando il primo dei due si solleva,
        # senza che l'utente abbia davvero staccato e ritoccato lo
        # schermo. Trattarla come "view" (ignorata ai fini di
        # disegno/gomma) invece che come un tocco nuovo.
        view = view or (
            time.monotonic() - self._last_view_end_t[is_fs] < _VIEW_TAIL_GRACE_S
        )
        if view:
            self._gesture_kind[is_fs] = "view"
            self._gesture_scale_start[is_fs] = self._view_scale[is_fs]
            self._gesture_ref_focal[is_fs] = self._to_scene(
                is_fs, e.local_focal_point.x, e.local_focal_point.y)
            return

        x, y = self._to_scene(is_fs, e.local_focal_point.x, e.local_focal_point.y)
        # Nessuna pennellata QUI, in nessuno dei due rami — vedi punto 5 del
        # docstring del modulo: finché non è passata `_INTENT_CONFIRM_S`
        # (o il gesto non è già stato "confermato" da un fotogramma
        # precedente, impossibile al primissimo tocco), il tocco potrebbe
        # ancora rivelarsi il primo dito di un pizzico — dipingere subito
        # significherebbe dover ripulire un fotogramma già arrivato al
        # client reale.
        self._gesture_start_t[is_fs] = time.monotonic()
        self._gesture_painted[is_fs] = False
        if self._draw_mode == "eraser":
            self._gesture_kind[is_fs] = "erase"
            # Un solo snapshot per l'INTERO trascinamento della gomma (non
            # uno per ogni micro-cancellazione lungo il percorso): "Annulla"
            # deve ripristinare l'intera passata di gomma con un click solo,
            # non un frammento minuscolo di essa — vedi il commento su
            # `self._history` nell'`__init__`. Va bene prenderlo subito:
            # non dipinge nulla di suo, e se il gesto si rivela un pizzico
            # non viene mai consumato (nessuna cancellazione applicata).
            self._snapshot()
            self._eraser_cursor_pos = [x, y]
            self._pending_erase_points[is_fs] = [[x, y]]
            return
        self._gesture_kind[is_fs] = "draw"
        self._current_points.clear()
        self._current_points.append([x, y])

    def _on_interaction_update(self, e: ft.ScaleUpdateEvent, canvas: cv.Canvas) -> None:
        is_fs = canvas is self._canvas[True]
        kind = self._gesture_kind.get(is_fs)

        if kind == "view":
            self._apply_view_update(is_fs, e)
            return

        if e.pointer_count >= 2:
            # BUG FIX (2026-08-26, segnalato da Davide): un pizzico vero a
            # due dita quasi non tocca MAI lo schermo in modo perfettamente
            # simultaneo — il primo dito arriva con `pointer_count == 1`,
            # fa scattare `_on_interaction_start()` che lo classifica come
            # "draw"/"erase" (l'unica informazione disponibile in quel
            # momento), POI il secondo dito arriva qui come un
            # `on_interaction_update` con `pointer_count == 2`, non un
            # nuovo `_on_interaction_start()` (Flutter non lo rifà mai a
            # metà gesto). Senza questo ramo il gesto restava bloccato su
            # "erase"/"draw" per tutta la sua durata — in modalità Gomma il
            # cursore già disegnato al tocco del primo dito (vedi
            # `_on_interaction_start`) restava congelato lì fino al
            # sollevamento delle dita: il "pallino" segnalato. Qui si
            # riclassifica il gesto come "view" nel momento stesso in cui
            # arriva un secondo dito — stesso principio che Flutter applica
            # a se stesso in `_onScaleUpdate` (`_gestureType = _getGestureType
            # (details)` quando il gesto era ancora genericamente "pan"):
            # mai bloccarsi sulla prima informazione se il gesto la
            # smentisce quasi subito.
            self._gesture_kind[is_fs] = "view"
            # `_gesture_painted[is_fs]` distingue se c'è DAVVERO qualcosa da
            # ripulire sul client (punto 5 del docstring del modulo): nel
            # caso normale di un pizzico vero, il secondo dito arriva ben
            # prima di `_INTENT_CONFIRM_S` e non è mai stato dipinto
            # nulla — niente ridisegno/`_safe_update` da mandare, quindi
            # nessun fotogramma "pallino" può mai comparire sul client.
            if kind == "erase":
                self._eraser_cursor_pos = None
                self._pending_erase_points[is_fs] = []
                if self._gesture_painted[is_fs]:
                    self._redraw_canvas(canvas, is_fs)
                    self._safe_update(canvas, "on_interaction_update/erase-reclassified")
            elif kind == "draw":
                self._current_points.clear()
                if self._gesture_painted[is_fs]:
                    self._redraw_canvas(canvas, is_fs)
                    self._safe_update(canvas, "on_interaction_update/draw-reclassified")
            self._gesture_scale_start[is_fs] = self._view_scale[is_fs]
            self._gesture_ref_focal[is_fs] = self._to_scene(
                is_fs, e.local_focal_point.x, e.local_focal_point.y)
            # Applica SUBITO questo stesso evento come primo aggiornamento
            # "view" — non aspettare il prossimo fotogramma: `e.scale` è
            # già cumulativo rispetto al VERO inizio del gesto (il primo
            # dito, quando era ancora scale≈1.0), quindi riflette già
            # correttamente il pizzico fatto finora.
            self._apply_view_update(is_fs, e)
            return

        x, y = self._to_scene(is_fs, e.local_focal_point.x, e.local_focal_point.y)
        # Un dito solo confermato (pointer_count == 1 su questo evento, kind
        # già "erase"/"draw"): dipinge davvero solo se il gesto è già
        # "confermato" da un fotogramma precedente, oppure se è trascorsa
        # `_INTENT_CONFIRM_S` da quando ha toccato — vedi punto 5 del
        # docstring del modulo. Prima di allora bufferizza soltanto: se il
        # secondo dito arriva nel frattempo, il ramo `pointer_count >= 2`
        # sopra scarta il buffer senza che nulla sia mai stato disegnato.
        confirmed = self._gesture_painted[is_fs] or (
            time.monotonic() - self._gesture_start_t[is_fs] >= _INTENT_CONFIRM_S
        )
        if kind == "erase":
            self._eraser_cursor_pos = [x, y]
            if not confirmed:
                self._pending_erase_points[is_fs].append([x, y])
                return
            if not self._gesture_painted[is_fs]:
                # La soglia scade proprio ora: recupera in ordine tutti i
                # punti toccati durante l'attesa, così un trascinamento
                # rapido non perde il tratto iniziale di cancellazione.
                for px, py in self._pending_erase_points[is_fs]:
                    if self._eraser_sub == "stroke":
                        self._erase_strokes_at(px, py, canvas)
                    else:
                        self._erase_segments_at(px, py, canvas)
                self._pending_erase_points[is_fs] = []
                self._gesture_painted[is_fs] = True
            if self._eraser_sub == "stroke":
                self._erase_strokes_at(x, y, canvas)
            else:
                self._erase_segments_at(x, y, canvas)
            self._redraw_canvas(canvas, is_fs)
            self._safe_update(canvas, "on_interaction_update/eraser")
            return
        if kind == "draw":
            self._current_points.append([x, y])
            if not confirmed:
                return
            self._gesture_painted[is_fs] = True
            self._redraw_live_stroke(canvas, is_fs)
            self._safe_update(canvas, "on_interaction_update/pen")

    def _on_interaction_end(self, e: ft.ScaleEndEvent, canvas: cv.Canvas) -> None:
        is_fs = canvas is self._canvas[True]
        kind = self._gesture_kind.pop(is_fs, None)
        self._gesture_ref_focal[is_fs] = None
        if kind == "view":
            # Vedi punto 6 del docstring del modulo: se il dito rimasto si
            # muove prima di sollevarsi a sua volta, Flutter riapre un
            # gesto a un dito solo per lui — `_on_interaction_start()` usa
            # questo istante per riconoscerlo come coda fantasma, non un
            # tocco nuovo.
            self._last_view_end_t[is_fs] = time.monotonic()
            return
        if kind is None:
            return

        self._eraser_cursor_pos = None
        if kind == "erase":
            # Il gesto è finito prima che `_INTENT_CONFIRM_S` scadesse (tocco
            # rapido, non un pizzico — altrimenti `kind` sarebbe già "view",
            # vedi sopra): recupera ORA i punti bufferizzati, così una
            # cancellazione veloce non va persa — vedi punto 5 del docstring
            # del modulo.
            if not self._gesture_painted[is_fs]:
                for px, py in self._pending_erase_points[is_fs]:
                    if self._eraser_sub == "stroke":
                        self._erase_strokes_at(px, py, canvas)
                    else:
                        self._erase_segments_at(px, py, canvas)
                self._pending_erase_points[is_fs] = []
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
        self._safe_update(canvas, "on_interaction_end")

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
        """Il fix VERO del "brutto effetto scatto" segnalato da Davide è
        `gapless_playback=True` sull'`ft.Image` — vedi il commento su
        `img_key` in `build_draw_area()` per l'analisi completa e i due
        tentativi precedenti scartati dopo verifica dal vivo. Qui le
        mutazioni restano comunque raggruppate in un solo `page.update()`
        finale invece di un `.update()` per controllo — non è quello che
        elimina il fotogramma vuoto (verificato: da solo non bastava), ma
        resta una pulizia legittima (un solo giro sul socket invece di
        tre-quattro separati)."""
        self._draw_mode = key
        self._eraser_cursor_pos = None

        # L'`InteractiveViewer` di ogni pannello montato NON viene mai
        # sostituito (vedi punto 4 del docstring del modulo) — solo
        # `pan_enabled` cambia: un dito solo sposta la vista in "Sposta"
        # (o sempre, in sola lettura), altrimenti resta libero per
        # disegno/gomma. `scale_enabled` non cambia mai: il pizzico a due
        # dita zoomma in QUALSIASI modalità.
        for viewer in self._viewer.values():
            if viewer is None:
                continue
            viewer.pan_enabled = (not self.can_manage) or key == "move"

        for mode_list in self._mode_refs.values():
            for i, (k, _, _) in enumerate(_MODE_DEFS):
                if i >= len(mode_list):
                    break
                self._style_mode_btn(mode_list[i], k == key)

        # Aggiorna il body DI ENTRAMBI i pannelli — l'AnimatedSwitcher
        # anima solo l'opacità (mai la dimensione, il Container esterno ha
        # altezza fissa `_TOOLBAR_BODY_H`), lo stato logico è impostato
        # subito, sincrono.
        for panel_fs, switcher in self._toolbar_switcher.items():
            if switcher is None:
                continue
            switcher.content = self._build_toolbar_body(panel_fs, self._ersub_refs[panel_fs])

        if self._page is not None:
            try:
                self._page.update()
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
        self._viewer[True] = None
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
