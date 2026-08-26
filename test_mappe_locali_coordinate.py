"""
Verifica del fix 2026-08-12 sulla vista Mappe LOCALI
(`ui/views/maps_view.py::MapsView`) — Davide, dopo aver confermato il fix
sulle mappe condivise: "il problema del disallineamento esisteva già
anche solo per il giocatore [in locale], non me ne sono accorto prima, va
allineato anche quello".

Stesso identico bug delle mappe condivise (vedi `test_mappe_condivise_ui.py`
parte [3b] per il fix gemello lato mondo): i tratti si salvavano in pixel
ASSOLUTI del riquadro con cui si era disegnato — il pannello inline e lo
schermo intero sono DUE riquadri Flet distinti, quasi mai della stessa
dimensione, quindi lo stesso tratto appariva disallineato passando
dall'uno all'altro. Qui però la complicazione in più è la gomma: la sua
geometria (raggio, intersezioni di cerchio in `_split_stroke_by_circle`)
lavora in pixel assoluti — `_erase_strokes_at`/`_erase_segments_at` ora
denormalizzano i punti del riquadro CORRENTE prima del taglio e
rinormalizzano il risultato subito dopo.

Quattro parti:

[1] Un tratto disegnato nel pannello INLINE si salva come frazione [0,1]
    del suo riquadro, e si ridisegna correttamente scalato quando il
    riquadro cambia dimensione (stesso principio della mappa condivisa).

[2] Lo SCHERMO INTERO ha un riquadro indipendente da quello inline: lo
    stesso tratto (stessa lista `self._strokes`, condivisa dalle due
    viste) si ridisegna scalato alla dimensione DELLO SCHERMO INTERO, non
    a quella (diversa) del pannello inline — è esattamente lo scenario
    del bug segnalato.

[3] Gomma "Tratto" — cancella nel punto giusto anche quando il riquadro
    con cui si cancella ha una dimensione diversa da quello con cui si è
    disegnato.

[4] Gomma "Libera" — stessa cosa, verificando anche che il pezzo di
    tratto rimasto dopo il taglio resti allineato (rinormalizzato)
    correttamente.

Eseguire con:
    PYTHONPATH=".venv/lib/python3.13/site-packages:." python3 test_mappe_locali_coordinate.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

_TMP_HOME = tempfile.mkdtemp(prefix="dnd_mappe_locali_coord_")
os.environ["HOME"] = _TMP_HOME

import flet as ft  # noqa: E402
import flet.canvas as cv  # noqa: E402

from data.database import init_db  # noqa: E402
from data.models import Character  # noqa: E402
from data.repositories import character_repo, maps_repo  # noqa: E402
from ui import canvas_geometry as geo  # noqa: E402
from ui.components import map_drawing_canvas as mdc  # noqa: E402


class _FakeTimeModule:
    """Sostituisce l'attributo `time` dentro `map_drawing_canvas` (mai il
    vero modulo stdlib `time`, che resterebbe condiviso con tutto il resto
    del processo) — BUG FIX 2026-08-26, quinto giro: `_on_interaction_*`
    ora ritarda la prima pennellata di `_INTENT_CONFIRM_S` per non lasciare
    "pallini" durante un pizzico (vedi il punto 5 del docstring del
    modulo). Passo di default 1.0s: molto oltre `_INTENT_CONFIRM_S`,
    così ogni singolo `on_interaction_update` di un test esistente (che
    simula un trascinamento a un dito, non un pizzico) resta "confermato"
    subito, come un trascinamento reale che dura più di qualche decina di
    ms — nessuna modifica necessaria ai test che non riguardano
    specificamente la finestra di conferma."""

    def __init__(self, step: float = 1.0, start: float = 1_000_000.0):
        self._t = start
        self.step = step

    def monotonic(self) -> float:
        self._t += self.step
        return self._t


mdc.time = _FakeTimeModule()

_PASS = 0
_FAIL: list[str] = []


def check(label: str, cond: bool) -> None:
    global _PASS
    if cond:
        _PASS += 1
    else:
        _FAIL.append(label)
        print(f"  FALLITO: {label}")


def _iter_controls(root):
    stack = [root]
    while stack:
        node = stack.pop()
        if node is None:
            continue
        yield node
        content = getattr(node, "content", None)
        if content is not None:
            stack.append(content)
        controls = getattr(node, "controls", None)
        if controls:
            stack.extend(controls)


def _find(root, pred):
    for node in _iter_controls(root):
        if pred(node):
            return node
    return None


class _FakeOffset:
    def __init__(self, x: float, y: float):
        self.x = x
        self.y = y


class _FakeScaleStartEvent:
    """Imita `ft.ScaleStartEvent` — l'unico evento che
    `MapDrawingCanvas._on_interaction_start()` legge ora (BUG FIX
    2026-08-26, quarto giro: non più `on_pan_start`/`DragStartEvent`, un
    solo `ft.InteractiveViewer` gestisce sia disegno/gomma [1 dito] sia
    pan/zoom [2+ dita] — vedi il punto 4 del docstring del modulo di
    `map_drawing_canvas.py`)."""

    def __init__(self, x: float, y: float, pointer_count: int = 1):
        self.local_focal_point = _FakeOffset(x, y)
        self.pointer_count = pointer_count


class _FakeScaleUpdateEvent:
    def __init__(self, x: float, y: float, pointer_count: int = 1, scale: float = 1.0):
        self.local_focal_point = _FakeOffset(x, y)
        self.pointer_count = pointer_count
        self.scale = scale


class _FakeScaleEndEvent:
    def __init__(self, pointer_count: int = 1):
        self.pointer_count = pointer_count


class _FakeSizeEvent:
    def __init__(self, width: float, height: float):
        self.width = width
        self.height = height


class _FakePage:
    def __init__(self):
        self.overlay: list = []

    def update(self, *_a, **_k) -> None:
        pass


def _make_character() -> Character:
    c = Character(
        name="Locale", class_name="Guerriero", race="Umano", level=1,
        hit_dice_type=10, hit_dice_total=1, hit_dice_remaining=1,
        str_score=10, dex_score=10, con_score=10, int_score=10,
        wis_score=10, cha_score=10, hp_max=10, hp_current=10,
    )
    character_repo.create(c)
    return c


def _resize_container(panel_root) -> ft.Container:
    """Il Container che avvolge l'area di disegno (`on_size_change` verso
    `MapDrawingCanvas.on_box_resize`) — identificato dal suo contenuto
    diretto, l'`ft.InteractiveViewer` UNICO che `build_draw_area()`
    restituisce (BUG FIX 2026-08-26, quarto giro: non più uno "slot" il cui
    contenuto si scambia a seconda della modalità — un solo
    `InteractiveViewer`, mai sostituito, montato per tutta la vita del
    pannello — vedi il punto 4 del docstring del modulo di
    `map_drawing_canvas.py`): non basta cercare "un qualunque Container con
    on_size_change", dato che anche la barra pillole della toolbar
    (breakpoint responsive) ne monta uno per conto proprio, e quello ha
    come contenuto diretto una Row/Column, non un `InteractiveViewer`."""
    c = _find(panel_root, lambda n: isinstance(n, ft.Container)
              and isinstance(getattr(n, "content", None), ft.InteractiveViewer)
              and getattr(n, "on_size_change", None))
    assert c is not None, "nessun Container(content=InteractiveViewer) con on_size_change trovato"
    return c


def _viewer_of(panel_root) -> ft.InteractiveViewer:
    """L'`ft.InteractiveViewer` stesso (il `.content` di `_resize_container()`)
    — è lì che ora si chiamano `on_interaction_start/update/end` per
    simulare disegno/gomma/pan/zoom, non più un `ft.GestureDetector`
    separato (vedi il punto 4 del docstring del modulo)."""
    v = _find(panel_root, lambda n: isinstance(n, ft.InteractiveViewer))
    assert v is not None, "nessun InteractiveViewer trovato"
    return v


# ---------------------------------------------------------------------------
# [1] Pannello inline — normalizzazione base
# ---------------------------------------------------------------------------

def test_pannello_inline_normalizza() -> None:
    print("\n[1] Pannello inline — i punti si salvano come frazione del riquadro")
    from ui.views.maps_view import MapsView

    character = _make_character()
    gm = maps_repo.create_map(character.id, "Mappa Locale")
    assert gm is not None

    mv = MapsView(character)
    mv._page = _FakePage()
    mv._open_detail(gm)

    panel = mv.controls[-1]
    resize = _resize_container(panel)
    resize.on_size_change(_FakeSizeEvent(400, 300))

    viewer = _viewer_of(panel)
    viewer.on_interaction_start(_FakeScaleStartEvent(0, 0))
    viewer.on_interaction_update(_FakeScaleUpdateEvent(400, 300))
    viewer.on_interaction_end(_FakeScaleEndEvent())

    stored = json.loads(maps_repo.get_map(gm.id).annotations)[0]["points"]
    check("il punto (400,300) in un riquadro 400x300 si salva come (1.0, 1.0)",
          stored == [[0.0, 0.0], [1.0, 1.0]])

    canvas = mv._canvas._canvas[False]
    assert canvas is not None
    path = next(s for s in canvas.shapes if isinstance(s, cv.Path))
    end = path.elements[-1]
    check("nel riquadro 400x300 il tratto è disegnato fino a (400,300)",
          (end.x, end.y) == (400.0, 300.0))

    # Il riquadro cambia dimensione (es. la finestra viene ridimensionata,
    # o il pannello inline è più stretto su uno smartphone) — il tratto
    # deve seguire proporzionalmente.
    resize.on_size_change(_FakeSizeEvent(800, 600))
    path2 = next(s for s in canvas.shapes if isinstance(s, cv.Path))
    end2 = path2.elements[-1]
    check("nello stesso riquadro raddoppiato a 800x600, il tratto arriva a (800,600) — "
          "PRIMA del fix sarebbe rimasto fermo a (400,300)",
          (end2.x, end2.y) == (800.0, 600.0))


# ---------------------------------------------------------------------------
# [2] Schermo intero — riquadro indipendente da quello inline
# ---------------------------------------------------------------------------

def test_schermo_intero_riquadro_indipendente() -> None:
    print("\n[2] Schermo intero — riquadro indipendente, stesso tratto scalato correttamente")
    from ui.views.maps_view import MapsView

    character = _make_character()
    gm = maps_repo.create_map(character.id, "Mappa Locale 2")
    assert gm is not None

    mv = MapsView(character)
    mv._page = _FakePage()
    mv._open_detail(gm)

    # Disegna nel pannello inline, riquadro 400x300.
    panel = mv.controls[-1]
    _resize_container(panel).on_size_change(_FakeSizeEvent(400, 300))
    viewer = _viewer_of(panel)
    viewer.on_interaction_start(_FakeScaleStartEvent(400, 0))
    viewer.on_interaction_update(_FakeScaleUpdateEvent(0, 300))
    viewer.on_interaction_end(_FakeScaleEndEvent())

    # Apre lo schermo intero — riquadro DIVERSO (es. un vero schermo,
    # 1200x800), mai stato ridimensionato prima d'ora.
    mv._open_fullscreen(gm)
    check("l'overlay a schermo intero si apre", len(mv._page.overlay) == 1)
    fs_overlay = mv._page.overlay[0]
    fs_resize = _resize_container(fs_overlay)
    fs_resize.on_size_change(_FakeSizeEvent(1200, 800))

    fs_canvas = mv._canvas._canvas[True]
    assert fs_canvas is not None
    fs_path = next(s for s in fs_canvas.shapes if isinstance(s, cv.Path))
    start, end = fs_path.elements[0], fs_path.elements[-1]
    check("lo stesso tratto, a schermo intero 1200x800, parte da (1200,0) e arriva a (0,800) "
          "— proporzionale al riquadro inline 400x300 con cui fu disegnato, non ancorato "
          "ai suoi vecchi pixel assoluti",
          (start.x, start.y) == (1200.0, 0.0) and (end.x, end.y) == (0.0, 800.0))

    # Il pannello inline, riletto ORA, deve restare quello che era (i due
    # riquadri sono indipendenti, nessuno "vince" sull'altro).
    detail_canvas = mv._canvas._canvas[False]
    assert detail_canvas is not None
    detail_path = next(s for s in detail_canvas.shapes if isinstance(s, cv.Path))
    d_start, d_end = detail_path.elements[0], detail_path.elements[-1]
    check("il pannello inline resta scalato al SUO riquadro (400,300), non a quello "
          "dello schermo intero",
          (d_start.x, d_start.y) == (400.0, 0.0) and (d_end.x, d_end.y) == (0.0, 300.0))


# ---------------------------------------------------------------------------
# [3] Gomma "Tratto" — cancella nel punto giusto in un riquadro diverso
# ---------------------------------------------------------------------------

def test_gomma_tratto_riquadro_diverso() -> None:
    print("\n[3] Gomma \"Tratto\" — allineata anche in un riquadro di dimensione diversa")
    from ui.views.maps_view import MapsView

    character = _make_character()
    gm = maps_repo.create_map(character.id, "Mappa Locale 3")
    assert gm is not None

    mv = MapsView(character)
    mv._page = _FakePage()
    mv._open_detail(gm)
    panel = mv.controls[-1]
    resize = _resize_container(panel)

    # Disegna un tratto verticale al centro di un riquadro 400x300. Il
    # `GestureDetector` non esiste finché il box non è noto (BUG FIX
    # 2026-08-24) — va cercato DOPO il resize, non prima.
    resize.on_size_change(_FakeSizeEvent(400, 300))
    viewer = _viewer_of(panel)
    viewer.on_interaction_start(_FakeScaleStartEvent(200, 100))
    viewer.on_interaction_update(_FakeScaleUpdateEvent(200, 200))
    viewer.on_interaction_end(_FakeScaleEndEvent())
    check("un tratto è stato salvato", len(mv._canvas._strokes) == 1)

    # Ridimensiona a 800x600 (il doppio) e passa in modalità gomma.
    resize.on_size_change(_FakeSizeEvent(800, 600))
    mv._canvas._draw_mode = "eraser"
    mv._canvas._eraser_sub = "stroke"
    mv._canvas._eraser_size = 20.0

    # Il tratto ha solo 2 punti salvati (inizio/fine, un solo pan_update in
    # fase di disegno) — riscalati al nuovo riquadro sono (400,200) e
    # (400,400) (erano (200,100)/(200,200) nel riquadro originale). La
    # gomma "Tratto" confronta la distanza dai punti SALVATI di ogni
    # tratto: si cancella vicino a un endpoint riscalato, non al vecchio
    # valore assoluto (200,150) — quello sarebbe il punto SBAGLIATO se il
    # fix non funzionasse.
    viewer.on_interaction_start(_FakeScaleStartEvent(400, 200))
    viewer.on_interaction_update(_FakeScaleUpdateEvent(400, 200))
    check("la gomma \"Tratto\" cancella il tratto nel punto RISCALATO corretto "
          "(400,200 nel riquadro 800x600, non più 200,100 del riquadro originale)",
          len(mv._canvas._strokes) == 0)


# ---------------------------------------------------------------------------
# [4] Gomma "Libera" — taglio e rinormalizzazione
# ---------------------------------------------------------------------------

def test_gomma_libera_rinormalizza() -> None:
    print("\n[4] Gomma \"Libera\" — il pezzo di tratto rimasto resta allineato dopo il taglio")
    from ui.views.maps_view import MapsView

    character = _make_character()
    gm = maps_repo.create_map(character.id, "Mappa Locale 4")
    assert gm is not None

    mv = MapsView(character)
    mv._page = _FakePage()
    mv._open_detail(gm)
    panel = mv.controls[-1]
    resize = _resize_container(panel)

    # Tratto orizzontale lungo tutto un riquadro 400x300, a metà altezza.
    # Il `GestureDetector` non esiste finché il box non è noto (BUG FIX
    # 2026-08-24) — va cercato DOPO il resize, non prima.
    resize.on_size_change(_FakeSizeEvent(400, 300))
    viewer = _viewer_of(panel)
    viewer.on_interaction_start(_FakeScaleStartEvent(0, 150))
    for x in range(0, 401, 40):
        viewer.on_interaction_update(_FakeScaleUpdateEvent(x, 150))
    viewer.on_interaction_end(_FakeScaleEndEvent())
    check("un tratto è stato salvato", len(mv._canvas._strokes) == 1)

    # Passa alla gomma libera, riquadro RADDOPPIATO (800x600): il tratto
    # ora attraversa (0,300)-(800,300). Cancella al centro (400,300).
    resize.on_size_change(_FakeSizeEvent(800, 600))
    mv._canvas._draw_mode = "eraser"
    mv._canvas._eraser_sub = "pixel"
    mv._canvas._eraser_size = 40.0

    viewer.on_interaction_start(_FakeScaleStartEvent(400, 300))
    viewer.on_interaction_update(_FakeScaleUpdateEvent(400, 300))

    check("il tratto è stato spezzato in due pezzi dalla cancellazione centrale",
          len(mv._canvas._strokes) == 2)
    for stroke in mv._canvas._strokes:
        pts = stroke["points"]
        check("ogni pezzo rimasto è salvato come frazione [0,1] (rinormalizzato "
              "dopo il taglio in pixel assoluti)",
              all(0.0 <= px <= 1.0 and 0.0 <= py <= 1.0 for px, py in pts))

    # Ridisegnando allo stesso riquadro 800x600, i pezzi devono comparire
    # correttamente ai due lati del buco (non più intorno al centro).
    canvas = mv._canvas._canvas[False]
    assert canvas is not None
    xs = []
    for shape in canvas.shapes:
        if isinstance(shape, cv.Path):
            xs.extend(el.x for el in shape.elements)
    check("nessun punto disegnato ricade nel buco centrale appena tagliato (intorno a x=400)",
          all(x <= 380 or x >= 420 for x in xs))


# ---------------------------------------------------------------------------
# [5] BUG FIX (2026-08-20): zoom rotto su smartphone in modalità "move"
# ---------------------------------------------------------------------------

def test_zoom_persiste_e_pizzico_funziona_in_ogni_modalita() -> None:
    """
    Bug report Davide (2026-08-26, dopo il fix del ritardo del tratto):
    "se uso sposta e zoommo poi vado a penna e ricarica la foto non
    zoommata" + "vorrei che anche nella sezione penna si possa zoommare
    col pizzico e viceversa". Causa del primo problema: la versione
    precedente smontava/rimontava un `ft.InteractiveViewer` DIVERSO a ogni
    cambio Penna↔Sposta — un widget appena creato riparte sempre dalla
    Matrix4 identità, lo zoom si perdeva per costruzione. Fix (quarto
    giro): un solo `InteractiveViewer` per pannello, mai sostituito — vedi
    il punto 4 del docstring del modulo di `map_drawing_canvas.py`. Il
    disegno/gomma non passa più da un `ft.GestureDetector` separato ma da
    `on_interaction_start/update/end` sullo STESSO widget: un tocco singolo
    disegna, due o più dita pizzicano SEMPRE (anche in Penna/Gomma), decisi
    una volta sola all'inizio del gesto.
    """
    print("\n[5] Un solo InteractiveViewer per pannello: lo zoom sopravvive ai "
          "cambi modalità, il pizzico funziona anche in Penna (BUG FIX 2026-08-26, "
          "quarto giro)")
    from ui.views.maps_view import MapsView

    character = _make_character()
    gm = maps_repo.create_map(character.id, "Mappa Zoom Mobile")
    assert gm is not None

    mv = MapsView(character)
    mv._page = _FakePage()
    mv._open_detail(gm)

    panel = mv.controls[-1]
    resize = _resize_container(panel)
    resize.on_size_change(_FakeSizeEvent(400, 300))

    check("modalità di default 'pen'", mv._canvas._draw_mode == "pen")
    viewer = _viewer_of(panel)
    check("l'InteractiveViewer trovato nell'albero è lo stesso oggetto "
          "tenuto da MapDrawingCanvas (nessuna copia)",
          viewer is mv._canvas._viewer[False])
    check("in modalità 'pen' un dito solo NON sposta la vista "
          "(pan_enabled=False, resta libero per disegnare) — ma scale_enabled "
          "resta True: il pizzico funziona comunque",
          viewer.pan_enabled is False and viewer.scale_enabled is True)

    # Pizzico a DUE dita mentre si è ancora in modalità "pen" — messo a
    # fuoco al centro del riquadro (200,150), portato a scala 2x. Prima di
    # questo fix un `ft.GestureDetector` di disegno separato lo avrebbe
    # reso impossibile (o avrebbe rimesso in gioco il ritardo di 1-2s se
    # montato insieme all'InteractiveViewer) — qui è lo STESSO widget a
    # gestire entrambi, decidendo in base a `pointer_count`.
    viewer.on_interaction_start(_FakeScaleStartEvent(200, 150, pointer_count=2))
    viewer.on_interaction_update(_FakeScaleUpdateEvent(200, 150, pointer_count=2, scale=2.0))
    viewer.on_interaction_end(_FakeScaleEndEvent(pointer_count=2))
    check("il pizzico a due dita in modalità 'pen' ha zoomato la vista a 2x",
          mv._canvas._view_scale[False] == 2.0)
    check("il pizzico NON ha disegnato nulla (interpretato come zoom, non "
          "come tratto)",
          mv._canvas._strokes == [])

    mv._canvas._select_mode("move", is_fs=False)
    check("il draw_mode è cambiato in 'move'", mv._canvas._draw_mode == "move")
    check("passando a 'move' l'InteractiveViewer NON viene ricreato — "
          "stesso oggetto di prima, ora con pan_enabled=True",
          viewer is mv._canvas._viewer[False] and viewer.pan_enabled is True)

    mv._canvas._select_mode("pen", is_fs=False)
    check("BUG FIX: tornando a 'pen' lo zoom impostato in 'move' è ANCORA lì "
          "(2x) — prima di questo fix sarebbe tornato a 1x (widget ricreato)",
          mv._canvas._view_scale[False] == 2.0
          and viewer is mv._canvas._viewer[False]
          and viewer.pan_enabled is False)

    # Disegna con UN dito, a schermo zoomato 2x, spostamento (-200,-150) —
    # gli stessi valori che la formula di `_on_interaction_update()`
    # produce per quel pizzico (verificati sopra): un punto touch a
    # (300,200) e uno a (340,200) devono convertirsi in coordinate di
    # CONTENUTO (250,175) e (270,175), non restare (300,200)/(340,200)
    # (che sarebbe il comportamento SBAGLIATO, come se lo zoom non fosse
    # mai stato applicato).
    check("lo spostamento della vista calcolato dal pizzico è quello atteso "
          "dalla formula (stessa di Flutter: il punto sotto il fuoco resta fisso)",
          mv._canvas._view_offset[False] == [-200.0, -150.0])
    viewer.on_interaction_start(_FakeScaleStartEvent(300, 200))
    viewer.on_interaction_update(_FakeScaleUpdateEvent(340, 200))
    viewer.on_interaction_end(_FakeScaleEndEvent())
    stored = json.loads(maps_repo.get_map(gm.id).annotations)[0]["points"]
    check("il tratto disegnato a schermo zoomato si salva in coordinate di "
          "CONTENUTO corrette (250,175)→(270,175) su un riquadro 400x300, "
          "non nelle coordinate di schermo grezze (300,200)→(340,200)",
          stored == [[250.0 / 400.0, 175.0 / 300.0], [270.0 / 400.0, 175.0 / 300.0]])


# ---------------------------------------------------------------------------
# [6] BUG FIX (2026-08-24): race di normalizzazione — nessun disegno prima
#     che il riquadro sia noto
# ---------------------------------------------------------------------------

def test_nessun_gesture_prima_del_box_noto() -> None:
    """
    Bug report Davide (riprodotto su un personaggio nuovo, mappa caricata
    da zero — quindi NON dati "legacy"): il disegno non corrisponde alla
    mappa. Causa reale: `self._detail_box_size`/`self._fs_box_size`
    partono a `[0.0, 0.0]` e vengono aggiornati SOLO da `on_size_change`
    (un giro websocket client→server, non istantaneo) — un tratto
    completato PRIMA che quell'evento arrivi veniva normalizzato con un
    riquadro 0×0, che `geo.normalize_points()` (fallback documentato)
    ritorna INVARIATO (pixel assoluti) — poi `geo.denormalize_points()`
    giudica quei valori "legacy" per euristica e non li riscala mai più:
    disallineamento permanente su dati freschissimi.

    Fix (quarto giro, 2026-08-26: l'`InteractiveViewer` è sempre montato
    ora, non c'è più un `GestureDetector` separato da smontare — vedi il
    punto 4 del docstring del modulo): `_on_interaction_start()` tratta
    ogni gesto come "view" (mai disegno/gomma) finché `_box_ready[is_fs]`
    è `False`, per costruzione nessun tratto può essere completato con un
    box sconosciuto. Questo test verifica che un tentativo di disegno
    SUBITO dopo l'apertura (nessun `on_size_change` ancora arrivato) non
    salvi nulla, e che funzioni normalmente dopo il primo resize.
    """
    print("\n[6] Un tentativo di disegno prima che il riquadro sia noto viene "
          "ignorato, per costruzione (BUG FIX 2026-08-24, quarto giro 2026-08-26)")
    from ui.views.maps_view import MapsView

    character = _make_character()
    gm = maps_repo.create_map(character.id, "Mappa Appena Aperta")
    assert gm is not None

    mv = MapsView(character)
    mv._page = _FakePage()
    mv._open_detail(gm)

    check("box del pannello inline non ancora noto subito dopo l'apertura",
          mv._canvas._box_ready[False] is False)
    panel = mv.controls[-1]
    viewer = _viewer_of(panel)

    # Un dito solo, PRIMA di qualunque on_size_change: `_box_ready` è
    # ancora False, il gesto va trattato come "view" (nessun tratto).
    viewer.on_interaction_start(_FakeScaleStartEvent(100, 100))
    viewer.on_interaction_update(_FakeScaleUpdateEvent(300, 200))
    viewer.on_interaction_end(_FakeScaleEndEvent())
    check("BUG FIX: un tentativo di disegno prima che il box sia noto non "
          "salva nulla (nessun tratto corrotto contro un box 0x0)",
          mv._canvas._strokes == [])

    resize = _resize_container(panel)
    resize.on_size_change(_FakeSizeEvent(400, 300))
    check("dopo il primo on_size_change il box è noto",
          mv._canvas._box_ready[False] is True)

    viewer.on_interaction_start(_FakeScaleStartEvent(100, 100))
    viewer.on_interaction_update(_FakeScaleUpdateEvent(300, 200))
    viewer.on_interaction_end(_FakeScaleEndEvent())
    stored = json.loads(maps_repo.get_map(gm.id).annotations)[0]["points"]
    check("FIX: il tratto disegnato dopo il resize si salva come frazione "
          "[0,1], mai come pixel assoluti indistinguibili da dati legacy",
          all(0.0 <= px <= 1.0 and 0.0 <= py <= 1.0 for px, py in stored))


def test_tolleranza_sconfinamento_letterbox() -> None:
    """
    Bug report Davide (screenshot 2026-08-24): "il disegno a schermo pieno
    e a schermo ridotto non corrisponde" per lo STESSO tratto, mai
    ridisegnato. Trovato scavando nel DB reale (`dnd_companion.db`, mappa
    "Mappa del mondo"): un tratto fresco, con `x` fino a -0.239 — fuori da
    [0,1]. Causa: durante un trascinamento, `local_position` NON è mai
    vincolato al riquadro del `GestureDetector` — un utente che disegna
    vicino al bordo di un'immagine con `BoxFit.CONTAIN` può facilmente
    sconfinare nella banda di letterboxing (fuori dal contenuto
    dell'immagine, ma dentro il riquadro di disegno): quel punto
    normalizzato è una frazione realistica ma < 0 o > 1, NON un pixel
    assoluto. La vecchia euristica `looks_normalized()` (stretta a [0,1])
    scambiava questo tratto per "legacy" e smetteva per sempre di
    riscalarlo — disallineamento permanente su dati freschissimi, non
    "legacy" in alcun senso.

    Fix: `looks_normalized()` tollera un margine oltre [0,1]
    (`_NORM_MARGIN`) — largo abbastanza da coprire uno sconfinamento reale
    nella banda di letterboxing, ordini di grandezza sotto qualunque
    valore che un vero pixel assoluto (legacy) potrebbe assumere.
    """
    print("\n[7] Tolleranza per sconfinamento nella banda di letterboxing "
          "(BUG FIX 2026-08-24, prova diretta nel DB reale — mai più "
          "scambiato per dato legacy)")

    # Stessi valori osservati nel DB reale (mappa "Mappa del mondo").
    real_stroke_points = [[-0.239, 0.273], [-0.230, 0.278], [0.097, 0.650]]
    check("un tratto che sconfina leggermente oltre [0,1] è ANCORA "
          "giudicato normalizzato (non più scambiato per legacy)",
          geo.looks_normalized(real_stroke_points))

    box_w, box_h = 1800.0, 1000.0
    denorm = geo.denormalize_points(real_stroke_points, box_w, box_h)
    check("viene riscalato rispetto al riquadro CORRENTE, non lasciato "
          "invariato come farebbe con dati legacy",
          denorm[0] == [-0.239 * box_w, 0.273 * box_h])

    # Un vero tratto legacy (pixel assoluti, box tipicamente >> 3px) resta
    # correttamente riconosciuto come tale — il margine non lo confonde.
    legacy_points = [[340.5, 210.2], [512.0, 198.7]]
    check("un vero tratto legacy (pixel assoluti) resta fuori tolleranza, "
          "riconosciuto come non normalizzato",
          not geo.looks_normalized(legacy_points))


def test_annulla_ripristina_ultima_azione_non_solo_ultimo_tratto() -> None:
    """
    Bug report Davide: "Annulla annulla solo l'ultimo tratto, non l'ultima
    azione, per esempio se cancello per sbaglio con la gomma [non si può
    annullare]". Prima del fix, `undo()` faceva solo
    `self._strokes.pop()` — corretto se l'ultima azione ha AGGIUNTO un
    tratto, sbagliato se l'ultima azione lo ha RIMOSSO (la gomma): un pop
    successivo toglieva un altro tratto ancora, non ripristinava quello
    cancellato per errore. Fix: `self._history`, uno snapshot completo
    PRIMA di ogni azione distruttiva — `undo()` ripristina quello snapshot
    invece di limitarsi a togliere l'ultimo elemento della lista attuale.
    """
    print("\n[8] \"Annulla\" ripristina l'ultima AZIONE (anche una cancellazione "
          "con la gomma), non solo l'ultimo tratto disegnato (BUG FIX 2026-08-25)")
    from ui.views.maps_view import MapsView

    character = _make_character()
    gm = maps_repo.create_map(character.id, "Mappa Locale 8")
    assert gm is not None

    mv = MapsView(character)
    mv._page = _FakePage()
    mv._open_detail(gm)
    panel = mv.controls[-1]
    resize = _resize_container(panel)
    resize.on_size_change(_FakeSizeEvent(400, 300))
    viewer = _viewer_of(panel)

    # Due tratti distinti, ben separati nello spazio.
    viewer.on_interaction_start(_FakeScaleStartEvent(50, 50))
    viewer.on_interaction_update(_FakeScaleUpdateEvent(50, 100))
    viewer.on_interaction_end(_FakeScaleEndEvent())
    viewer.on_interaction_start(_FakeScaleStartEvent(350, 250))
    viewer.on_interaction_update(_FakeScaleUpdateEvent(350, 280))
    viewer.on_interaction_end(_FakeScaleEndEvent())
    check("due tratti disegnati", len(mv._canvas._strokes) == 2)

    # La gomma "Tratto" cancella per errore il PRIMO tratto (vicino a
    # 50,50..50,100) — nessun nuovo tratto viene aggiunto in fondo alla
    # lista: un `pop()` naive toglierebbe il tratto SBAGLIATO (l'unico
    # rimasto, quello vicino a 350,250).
    mv._canvas._draw_mode = "eraser"
    mv._canvas._eraser_sub = "stroke"
    mv._canvas._eraser_size = 20.0
    # `_erase_strokes_at` confronta la distanza dai PUNTI SALVATI del
    # tratto (qui solo i due estremi, 50,50 e 50,100) — il click deve
    # cadere entro il raggio (10) da uno di essi, non semplicemente "sulla
    # linea".
    viewer.on_interaction_start(_FakeScaleStartEvent(50, 50))
    viewer.on_interaction_update(_FakeScaleUpdateEvent(50, 50))
    check("la gomma ha cancellato il primo tratto per errore",
          len(mv._canvas._strokes) == 1)

    mv._canvas.undo()
    check("BUG FIX: \"Annulla\" ripristina ENTRAMBI i tratti (l'azione "
          "cancellata dalla gomma), non ne toglie un altro",
          len(mv._canvas._strokes) == 2)

    # Annullare ancora ripristina lo stato prima del SECONDO tratto disegnato
    # (un tratto solo) — la cronologia è multi-livello, non un solo passo.
    mv._canvas.undo()
    check("un secondo \"Annulla\" torna indietro di un altro passo (un solo "
          "tratto rimasto, quello disegnato per primo)",
          len(mv._canvas._strokes) == 1)

    # Un terzo "Annulla" consuma l'ultimo snapshot rimasto (lo stato PRIMA
    # del primo tratto mai disegnato: nessun tratto).
    mv._canvas.undo()
    check("un terzo \"Annulla\" torna allo stato iniziale (nessun tratto)",
          len(mv._canvas._strokes) == 0)

    # Cronologia esaurita: ulteriori "Annulla" sono no-op sicuri (nessun
    # crash, nessuna modifica ulteriore).
    mv._canvas.undo()
    mv._canvas.undo()
    check("\"Annulla\" senza più cronologia è un no-op sicuro (nessun crash, "
          "nessuna modifica ulteriore)",
          len(mv._canvas._strokes) == 0 and mv._canvas._history == [])


# ---------------------------------------------------------------------------
# [9] Cache dei tratti già salvati durante un trascinamento in corso
# ---------------------------------------------------------------------------

def test_cache_tratti_salvati_durante_trascinamento() -> None:
    """
    Bug report Davide (2026-08-26, dopo il fix `scale_enabled`): "il bug è
    ancora presente, solo per tratti piccoli/trascinamenti brevi". Causa
    trovata leggendo il codice: `_redraw_canvas()` ricalcolava da zero
    TUTTI i tratti già salvati (denormalizzazione + `cv.Path`) ad OGNI
    singolo `on_pan_update`, non solo il tratto in corso — costo O(punti
    totali sulla mappa) per ogni fotogramma di trascinamento. Fix:
    `_committed_shapes()` calcola quella lista una volta e la mette in
    cache; `_redraw_live_stroke()` (usato durante un trascinamento penna)
    la riusa senza ricalcolarla, `_redraw_canvas()` (usato altrove) la
    invalida sempre prima. Verificato qui per IDENTITÀ degli oggetti
    `cv.Path` (non solo per valore): le shape dei tratti già salvati
    devono restare lo STESSO oggetto Python tra un `on_pan_update` e il
    successivo durante lo stesso trascinamento — se venissero ricreate
    (anche con contenuto identico) la cache non starebbe funzionando.
    """
    print("\n[9] I tratti già salvati non vengono ricalcolati ad ogni fotogramma "
          "di un trascinamento penna in corso (BUG FIX 2026-08-26)")
    from ui.views.maps_view import MapsView

    character = _make_character()
    gm = maps_repo.create_map(character.id, "Mappa Locale 9")
    assert gm is not None

    mv = MapsView(character)
    mv._page = _FakePage()
    mv._open_detail(gm)
    panel = mv.controls[-1]
    resize = _resize_container(panel)
    resize.on_size_change(_FakeSizeEvent(400, 300))
    viewer = _viewer_of(panel)
    canvas = mv._canvas._canvas[False]
    assert canvas is not None

    # Due tratti già salvati sulla mappa.
    viewer.on_interaction_start(_FakeScaleStartEvent(10, 10))
    viewer.on_interaction_update(_FakeScaleUpdateEvent(10, 50))
    viewer.on_interaction_end(_FakeScaleEndEvent())
    viewer.on_interaction_start(_FakeScaleStartEvent(200, 200))
    viewer.on_interaction_update(_FakeScaleUpdateEvent(200, 250))
    viewer.on_interaction_end(_FakeScaleEndEvent())
    check("due tratti già salvati", len(mv._canvas._strokes) == 2)

    # Terzo tratto: inizia un nuovo trascinamento (non ancora committato).
    viewer.on_interaction_start(_FakeScaleStartEvent(100, 100))
    viewer.on_interaction_update(_FakeScaleUpdateEvent(100, 120))
    committed_paths = [s for s in canvas.shapes if isinstance(s, cv.Path)]
    check("dopo il primo on_pan_update del terzo tratto: 3 Path totali "
          "(2 già salvati + 1 in corso)", len(committed_paths) == 3)
    # Le shape dei DUE tratti già salvati, per identità di oggetto — sono
    # le prime nella lista (append order: prima i salvati, poi quello in
    # corso — vedi `_redraw_live_stroke`).
    saved_shapes_first_frame = committed_paths[:2]

    viewer.on_interaction_update(_FakeScaleUpdateEvent(100, 140))
    committed_paths_2 = [s for s in canvas.shapes if isinstance(s, cv.Path)]
    check("un secondo on_pan_update sullo stesso trascinamento: ancora 3 "
          "Path totali, non 4 o più", len(committed_paths_2) == 3)
    check("BUG FIX: le shape dei DUE tratti già salvati sono gli STESSI "
          "oggetti Python del fotogramma precedente (cache riusata, non "
          "ricalcolata) — solo il tratto in corso cambia",
          committed_paths_2[0] is saved_shapes_first_frame[0]
          and committed_paths_2[1] is saved_shapes_first_frame[1])

    # Fine del terzo tratto: ora committato, la cache DEVE invalidarsi e
    # includerlo (altrimenti sparirebbe dal disegno finale).
    viewer.on_interaction_end(_FakeScaleEndEvent())
    check("dopo il commit, 3 tratti salvati", len(mv._canvas._strokes) == 3)
    final_paths = [s for s in canvas.shapes if isinstance(s, cv.Path)]
    check("dopo il commit il ridisegno include tutti e 3 i tratti (nessuno "
          "perso per una cache non invalidata)", len(final_paths) == 3)

    # La gomma cancella un tratto: la cache deve invalidarsi anche qui.
    mv._canvas._draw_mode = "eraser"
    mv._canvas._eraser_sub = "stroke"
    mv._canvas._eraser_size = 20.0
    viewer.on_interaction_start(_FakeScaleStartEvent(10, 10))
    viewer.on_interaction_update(_FakeScaleUpdateEvent(10, 10))
    check("la gomma cancella un tratto e la cache lo riflette subito",
          len(mv._canvas._strokes) == 2
          and len([s for s in canvas.shapes if isinstance(s, cv.Path)]) == 2)


# ---------------------------------------------------------------------------
# [10] Un secondo dito che arriva IN RITARDO durante un pizzico non lascia
#      il cursore gomma congelato sullo schermo
# ---------------------------------------------------------------------------

def test_secondo_dito_in_ritardo_non_lascia_cursore_congelato() -> None:
    """
    Bug report Davide (2026-08-26, dopo v0.3.10): "quando pizzico con 2
    dita lascia 2 pallini dove ho messo le dita per pizzicare, per il
    resto è ok". Causa: un pizzico vero quasi non tocca MAI lo schermo con
    entrambe le dita nello stesso istante — Flutter fa scattare
    `onScaleStart` per il PRIMO dito da solo (`pointer_count == 1`),
    `_on_interaction_start()` lo classificava come disegno/gomma (l'unica
    informazione disponibile in quel momento) — poi il secondo dito arriva
    come un `on_interaction_update` con `pointer_count == 2`, MAI un nuovo
    `_on_interaction_start()` (Flutter non lo rifà mai a metà gesto).

    Il fix v0.3.11 (riclassificare a "view" e ripulire quando arriva il
    secondo dito) NON bastava: Davide l'ha confermato ancora presente,
    con la diagnosi corretta — il primo dito, da solo, dipingeva
    IMMEDIATAMENTE il cursore gomma (o un segmento cortissimo in Penna),
    quel fotogramma arrivava DAVVERO al client via un `_safe_update()`
    separato, e "ripulirlo" col fotogramma successivo non impedisce che
    l'occhio lo veda comparire per un istante. Fix v0.3.13 (qui): nessuna
    pennellata parte finché non è trascorsa `_INTENT_CONFIRM_S` — un vero
    pizzico ha il secondo dito ben dentro quella finestra, quindi qui sotto
    NON deve comparire NESSUNA `cv.Circle`/`cv.Path` in nessun momento,
    nemmeno subito dopo `on_interaction_start` — non solo "sparire dopo",
    ma "mai apparsa" — vedi il punto 5 del docstring del modulo.
    """
    print("\n[10] Un pizzico che inizia con un dito solo (fisiologico, mai "
          "perfettamente simultaneo) non dipinge MAI nulla sullo schermo, "
          "nemmeno per un fotogramma (BUG FIX 2026-08-26, quinto giro)")
    from ui.views.maps_view import MapsView

    character = _make_character()
    gm = maps_repo.create_map(character.id, "Mappa Pizzico Ritardato")
    assert gm is not None

    mv = MapsView(character)
    mv._page = _FakePage()
    mv._open_detail(gm)
    panel = mv.controls[-1]
    resize = _resize_container(panel)
    resize.on_size_change(_FakeSizeEvent(400, 300))
    viewer = _viewer_of(panel)
    canvas = mv._canvas._canvas[False]
    assert canvas is not None

    # -- Ramo Gomma: il primo dito (da solo) NON deve dipingere nulla —
    # a differenza del vecchio comportamento "dipingi subito, ripulisci
    # dopo", qui semplicemente non c'è ancora nulla da ripulire.
    mv._canvas._draw_mode = "eraser"
    viewer.on_interaction_start(_FakeScaleStartEvent(100, 100))
    check("BUG FIX: il primo dito da solo, in modalità Gomma, NON dipinge "
          "ancora il cursore (resta in attesa di conferma)",
          not any(isinstance(s, cv.Circle) for s in canvas.shapes))

    # Il secondo dito arriva SUBITO — stesso gesto, un on_interaction_update
    # con pointer_count=2, MAI un nuovo on_interaction_start, ben dentro la
    # finestra di conferma (il mock del clock qui non serve nemmeno: fra
    # start e questo update non passa nessuna chiamata a time.monotonic()
    # nel ramo "view", quindi non importa quanto sia "lento" il clock finto
    # — il punto è che non è MAI stato dipinto nulla).
    viewer.on_interaction_update(_FakeScaleUpdateEvent(120, 100, pointer_count=2, scale=1.3))
    check("dopo il secondo dito, ancora nessuna cv.Circle è mai comparsa "
          "sul canvas", not any(isinstance(s, cv.Circle) for s in canvas.shapes))
    check("il gesto è stato riclassificato a 'view'",
          mv._canvas._gesture_kind[False] == "view")
    check("il pizzico, una volta riclassificato, zoomma davvero (non resta "
          "ignorato)", mv._canvas._view_scale[False] == 1.3)

    viewer.on_interaction_end(_FakeScaleEndEvent(pointer_count=2))
    check("nessuna cancellazione è stata applicata (la gomma non ha mai "
          "avuto un secondo fotogramma valido)", mv._canvas._strokes == [])

    # -- Ramo Penna: stesso principio, un tratto non deve crearsi né deve
    # restare un punto singolo appeso in `_current_points`.
    mv._canvas._draw_mode = "pen"
    mv._canvas._view_scale[False] = 1.0
    mv._canvas._view_offset[False] = [0.0, 0.0]
    viewer.on_interaction_start(_FakeScaleStartEvent(50, 50))
    viewer.on_interaction_update(_FakeScaleUpdateEvent(60, 50, pointer_count=2, scale=1.5))
    check("in modalità Penna, il secondo dito in ritardo riclassifica il "
          "gesto a 'view' e zoomma anche qui",
          mv._canvas._gesture_kind[False] == "view"
          and mv._canvas._view_scale[False] == 1.5)
    viewer.on_interaction_end(_FakeScaleEndEvent(pointer_count=2))
    check("nessun tratto è stato salvato (il tocco iniziale a un dito solo "
          "non ha mai formato un vero trascinamento penna)",
          mv._canvas._strokes == [] and mv._canvas._current_points == [])


def test_dito_solo_genuino_dipinge_dopo_la_soglia_di_conferma() -> None:
    """
    Controparte di [10]: un tocco a un dito solo che resta a un dito solo
    (nessun pizzico) deve continuare a disegnare/cancellare normalmente —
    il fix di [10] ritarda la prima pennellata, non la impedisce. Verifica
    anche il "recupero": una gomma che tocca e stacca il dito PRIMA che la
    soglia scada (un tap rapido, non un trascinamento) non deve perdere la
    cancellazione — viene applicata comunque in `on_interaction_end()`.
    """
    print("\n[10b] Un dito solo genuino continua a disegnare/cancellare "
          "normalmente dopo la soglia di conferma (BUG FIX 2026-08-26, "
          "quinto giro)")
    from ui.views.maps_view import MapsView

    character = _make_character()
    gm = maps_repo.create_map(character.id, "Mappa Dito Solo")
    assert gm is not None

    mv = MapsView(character)
    mv._page = _FakePage()
    mv._open_detail(gm)
    panel = mv.controls[-1]
    resize = _resize_container(panel)
    resize.on_size_change(_FakeSizeEvent(400, 300))
    viewer = _viewer_of(panel)
    canvas = mv._canvas._canvas[False]
    assert canvas is not None

    # -- Penna: un trascinamento vero (più fotogrammi, clock finto di
    # default con passo 1.0s >> _INTENT_CONFIRM_S) deve produrre un tratto
    # visibile DURANTE il trascinamento, non solo al rilascio.
    mv._canvas._draw_mode = "pen"
    viewer.on_interaction_start(_FakeScaleStartEvent(50, 50))
    viewer.on_interaction_update(_FakeScaleUpdateEvent(80, 60))
    check("un trascinamento penna genuino disegna la linea in corso PRIMA "
          "del rilascio (non solo dopo la soglia iniziale)",
          any(isinstance(s, cv.Path) for s in canvas.shapes))
    viewer.on_interaction_end(_FakeScaleEndEvent())
    check("il tratto penna genuino viene salvato normalmente",
          len(mv._canvas._strokes) == 1)

    # -- Gomma: un tap rapido (start seguito subito da end, MAI un update
    # con pointer_count==1 nel mezzo) non deve perdere la cancellazione —
    # `on_interaction_end()` recupera i punti bufferizzati.
    mv._canvas._draw_mode = "eraser"
    x0, y0, dw0, dh0 = mv._canvas._draw_rect_for(canvas)
    stroke_x = x0 + dw0 * 0.5
    stroke_y = y0 + dh0 * 0.5
    mv._canvas._strokes = [{
        "type": "stroke", "color": "#ffffff", "width": 5.0,
        "points": geo.normalize_points([[stroke_x, stroke_y], [stroke_x + 10, stroke_y]],
                                        dw0, dh0, x0, y0),
    }]
    mv._canvas._static_shapes[False] = None
    viewer.on_interaction_start(_FakeScaleStartEvent(stroke_x, stroke_y))
    viewer.on_interaction_end(_FakeScaleEndEvent())
    check("BUG FIX: un tap-gomma rapido (nessun on_interaction_update nel "
          "mezzo) cancella comunque il tratto toccato, recuperato al "
          "rilascio", mv._canvas._strokes == [])


def main() -> int:
    print("=" * 62)
    print("Mappe locali — fix coordinate 2026-08-12 (inline/schermo intero/gomma)")
    print(f"HOME di test: {_TMP_HOME}")
    print("=" * 62)
    init_db()
    test_pannello_inline_normalizza()
    test_schermo_intero_riquadro_indipendente()
    test_gomma_tratto_riquadro_diverso()
    test_gomma_libera_rinormalizza()
    test_zoom_persiste_e_pizzico_funziona_in_ogni_modalita()
    test_nessun_gesture_prima_del_box_noto()
    test_tolleranza_sconfinamento_letterbox()
    test_annulla_ripristina_ultima_azione_non_solo_ultimo_tratto()
    test_cache_tratti_salvati_durante_trascinamento()
    test_secondo_dito_in_ritardo_non_lascia_cursore_congelato()
    test_dito_solo_genuino_dipinge_dopo_la_soglia_di_conferma()
    print("\n" + "=" * 62)
    print(f"Controlli passati: {_PASS} — falliti: {len(_FAIL)}")
    if _FAIL:
        for f in _FAIL:
            print(f"  - {f}")
        return 1
    print("Tutti i controlli passati.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
