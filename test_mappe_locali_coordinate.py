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


class _FakeDragEvent:
    def __init__(self, x: float, y: float):
        self.local_position = _FakeOffset(x, y)


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
    diretto, un `ft.InteractiveViewer`: non basta più cercare "un
    qualunque Container con on_size_change", dato che anche la barra
    pillole della toolbar (breakpoint responsive) ne monta uno per conto
    proprio."""
    c = _find(panel_root, lambda n: isinstance(n, ft.Container)
              and isinstance(getattr(n, "content", None), ft.InteractiveViewer)
              and getattr(n, "on_size_change", None))
    assert c is not None, "nessun Container(content=InteractiveViewer) con on_size_change trovato"
    return c


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

    gesture = _find(panel, lambda n: isinstance(n, ft.GestureDetector))
    assert gesture is not None
    gesture.on_pan_start(_FakeDragEvent(0, 0))
    gesture.on_pan_update(_FakeDragEvent(400, 300))
    gesture.on_pan_end(_FakeDragEvent(400, 300))

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
    gesture = _find(panel, lambda n: isinstance(n, ft.GestureDetector))
    gesture.on_pan_start(_FakeDragEvent(400, 0))
    gesture.on_pan_update(_FakeDragEvent(0, 300))
    gesture.on_pan_end(_FakeDragEvent(0, 300))

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
    gesture = _find(panel, lambda n: isinstance(n, ft.GestureDetector))
    assert gesture is not None
    gesture.on_pan_start(_FakeDragEvent(200, 100))
    gesture.on_pan_update(_FakeDragEvent(200, 200))
    gesture.on_pan_end(_FakeDragEvent(200, 200))
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
    gesture.on_pan_start(_FakeDragEvent(400, 200))
    gesture.on_pan_update(_FakeDragEvent(400, 200))
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
    gesture = _find(panel, lambda n: isinstance(n, ft.GestureDetector))
    assert gesture is not None
    gesture.on_pan_start(_FakeDragEvent(0, 150))
    for x in range(0, 401, 40):
        gesture.on_pan_update(_FakeDragEvent(x, 150))
    gesture.on_pan_end(_FakeDragEvent(400, 150))
    check("un tratto è stato salvato", len(mv._canvas._strokes) == 1)

    # Passa alla gomma libera, riquadro RADDOPPIATO (800x600): il tratto
    # ora attraversa (0,300)-(800,300). Cancella al centro (400,300).
    resize.on_size_change(_FakeSizeEvent(800, 600))
    mv._canvas._draw_mode = "eraser"
    mv._canvas._eraser_sub = "pixel"
    mv._canvas._eraser_size = 40.0

    gesture.on_pan_start(_FakeDragEvent(400, 300))
    gesture.on_pan_update(_FakeDragEvent(400, 300))

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

def test_move_mode_rimuove_gesture_detector() -> None:
    """
    Bug report Davide: "lo zoom funziona per pc ma non funziona per
    smartphone". Causa: il `GestureDetector` di disegno restava sempre
    montato, anche in modalità "Sposta" (dove i suoi handler `on_pan_*`
    fanno subito `return`, vedi `_on_pan_start`) — il suo recognizer di pan
    vince comunque la gesture arena di Flutter su un pinch a due dita
    PRIMA che l'`InteractiveViewer` padre possa riconoscerlo come zoom (un
    trackpad non lo nota mai, passa da un canale di eventi diverso).
    `_select_mode("move", ...)` ora ricostruisce il layer del canvas senza
    il `GestureDetector`, lasciando l'`InteractiveViewer` libero di gestire
    pan/zoom nativamente.
    """
    print("\n[5] Modalità «Sposta» — il GestureDetector di disegno sparisce, "
          "l'InteractiveViewer resta libero per pinch/pan (2026-08-20)")
    from ui.views.maps_view import MapsView

    character = _make_character()
    gm = maps_repo.create_map(character.id, "Mappa Zoom Mobile")
    assert gm is not None

    mv = MapsView(character)
    mv._page = _FakePage()
    mv._open_detail(gm)

    # BUG FIX 2026-08-24 (race di normalizzazione, vedi
    # `MapDrawingCanvas.on_box_resize`): il `GestureDetector` di
    # disegno/gomma NON è montato finché il riquadro non è noto — prima di
    # qualunque `on_size_change` il canvas resta nudo (stesso ramo di
    # "move"), per non rischiare di normalizzare un tratto contro un box
    # 0×0. Qui si simula il resize prima di verificare lo stato "pen".
    panel = mv.controls[-1]
    resize = _resize_container(panel)
    resize.on_size_change(_FakeSizeEvent(400, 300))

    check("modalità di default 'pen'", mv._canvas._draw_mode == "pen")
    stack = mv._canvas._draw_stack[False]
    assert stack is not None
    check("in modalità 'pen', a riquadro noto, il canvas è avvolto in un GestureDetector",
          isinstance(stack.controls[1], ft.GestureDetector))
    viewer = mv._canvas._interactive_viewer[False]
    assert viewer is not None
    check("in modalità 'pen' l'InteractiveViewer non pannerebbe comunque (pan_enabled=False)",
          viewer.pan_enabled is False)

    mv._canvas._select_mode("move", is_fs=False)
    check("il draw_mode è cambiato in 'move'", mv._canvas._draw_mode == "move")
    check("BUG FIX: in modalità 'move' il GestureDetector è sparito, "
          "il canvas è figlio diretto dello Stack",
          stack.controls[1] is mv._canvas._canvas[False])
    check("l'InteractiveViewer ora ha pan_enabled=True (nessun concorrente nella gesture arena)",
          viewer.pan_enabled is True)

    # Tornando a "pen" il GestureDetector di disegno deve ricomparire —
    # altrimenti si perderebbe la possibilità di disegnare.
    mv._canvas._select_mode("pen", is_fs=False)
    check("tornando a 'pen' il GestureDetector di disegno ricompare",
          isinstance(stack.controls[1], ft.GestureDetector))

    # Disegnare deve ancora funzionare dopo il giro di andata/ritorno.
    gesture = stack.controls[1]
    gesture.on_pan_start(_FakeDragEvent(0, 0))
    gesture.on_pan_update(_FakeDragEvent(50, 50))
    gesture.on_pan_end(_FakeDragEvent(50, 50))
    check("il disegno funziona ancora dopo un giro pen→move→pen",
          bool(json.loads(maps_repo.get_map(gm.id).annotations)))


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

    Fix: `MapDrawingCanvas` non monta il `GestureDetector` di
    disegno/gomma finché il riquadro non è noto — il canvas resta nudo
    (stesso ramo già usato per la modalità "move"), quindi nessun tratto
    può essere completato con un box sconosciuto, per costruzione. Questo
    test verifica che l'assenza del `GestureDetector` sia vera SUBITO dopo
    l'apertura (nessun `on_size_change` ancora arrivato), e che compaia
    solo dopo il primo resize.
    """
    print("\n[6] Nessun GestureDetector montato finché il riquadro non è noto "
          "(BUG FIX 2026-08-24, disallineamento su dati freschi)")
    from ui.views.maps_view import MapsView

    character = _make_character()
    gm = maps_repo.create_map(character.id, "Mappa Appena Aperta")
    assert gm is not None

    mv = MapsView(character)
    mv._page = _FakePage()
    mv._open_detail(gm)

    check("box del pannello inline non ancora noto subito dopo l'apertura",
          mv._canvas._box_ready[False] is False)
    stack = mv._canvas._draw_stack[False]
    assert stack is not None
    canvas = mv._canvas._canvas[False]
    check("BUG FIX: prima di qualunque on_size_change, il canvas è nudo "
          "(nessun GestureDetector che possa completare un tratto con box 0x0)",
          stack.controls[1] is canvas and not isinstance(stack.controls[1], ft.GestureDetector))

    panel = mv.controls[-1]
    resize = _resize_container(panel)
    resize.on_size_change(_FakeSizeEvent(400, 300))

    check("dopo il primo on_size_change il box è noto",
          mv._canvas._box_ready[False] is True)
    check("FIX: ora il GestureDetector è montato, il disegno può iniziare",
          isinstance(stack.controls[1], ft.GestureDetector))

    gesture = stack.controls[1]
    gesture.on_pan_start(_FakeDragEvent(100, 100))
    gesture.on_pan_update(_FakeDragEvent(300, 200))
    gesture.on_pan_end(_FakeDragEvent(300, 200))
    stored = json.loads(maps_repo.get_map(gm.id).annotations)[0]["points"]
    check("il tratto disegnato dopo il resize si salva come frazione [0,1], "
          "mai come pixel assoluti indistinguibili da dati legacy",
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
    gesture = _find(panel, lambda n: isinstance(n, ft.GestureDetector))
    assert gesture is not None

    # Due tratti distinti, ben separati nello spazio.
    gesture.on_pan_start(_FakeDragEvent(50, 50))
    gesture.on_pan_update(_FakeDragEvent(50, 100))
    gesture.on_pan_end(_FakeDragEvent(50, 100))
    gesture.on_pan_start(_FakeDragEvent(350, 250))
    gesture.on_pan_update(_FakeDragEvent(350, 280))
    gesture.on_pan_end(_FakeDragEvent(350, 280))
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
    gesture.on_pan_start(_FakeDragEvent(50, 50))
    gesture.on_pan_update(_FakeDragEvent(50, 50))
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
    test_move_mode_rimuove_gesture_detector()
    test_nessun_gesture_prima_del_box_noto()
    test_tolleranza_sconfinamento_letterbox()
    test_annulla_ripristina_ultima_azione_non_solo_ultimo_tratto()
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
