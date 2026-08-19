"""
Geometria condivisa per le mappe disegnabili (`ui/views/maps_view.py`,
mappe locali, e `ui/views/world/world_view.py`, mappe condivise) — nessuna
dipendenza da Flet, solo aritmetica.

Bug corretto qui (2026-08-12, segnalato da Davide): i tratti venivano
salvati in pixel ASSOLUTI, cioè relativi alla dimensione che il riquadro di
disegno (`ft.GestureDetector`/`cv.Canvas`) aveva esattamente nell'istante
in cui l'utente disegnava. Flet non ridimensiona il contenuto di un canvas
in base al riquadro che lo contiene: se lo stesso tratto viene poi
visualizzato in un riquadro di dimensioni diverse (mappa locale: pannello
inline nella scheda vs. schermo intero — due `Stack` separati di
`MapsView`; mappa condivisa: la finestra del master che disegna può avere
una risoluzione diversa da quella del giocatore che guarda, anche se
entrambe sono "a schermo intero" sul rispettivo dispositivo), i punti
restano ancorati alle vecchie coordinate assolute — sembra che la mappa
"si sia rimpicciolita".

Soluzione: i punti si salvano come FRAZIONE (0.0-1.0) della dimensione del
riquadro nell'istante del disegno (`normalize_points`), e si riconvertono
in pixel assoluti rispetto al riquadro CORRENTE al momento del rendering
(`denormalize_points`) — letto tramite `ft.Container(on_size_change=...)`,
l'unico modo in questa versione di Flet (0.86.5, niente
`Container.on_resize`/`ContainerResizeEvent`) di conoscere la dimensione
effettiva dopo il layout di un controllo qualunque.

**Compatibilità con le annotazioni già esistenti** (disegnate prima di
questo fix, in pixel assoluti): nessuna migrazione — non è ricostruibile
la dimensione del riquadro con cui furono salvate. `looks_normalized()`
distingue i due formati per euristica: un tratto in frazioni ha SEMPRE
tutti i punti in [0, 1], un tratto in pixel assoluti quasi certamente no
(un riquadro di disegno largo meno di 1px non esiste). I tratti vecchi
restano quindi renderizzati "as-is" (stesso comportamento di prima, non
peggiore), quelli nuovi si allineano correttamente in qualunque riquadro.
"""

from __future__ import annotations

import json


def has_legacy_strokes(annotations_json: str) -> bool:
    """
    Vero se `annotations_json` (il campo `game_maps.annotations`, una lista
    JSON di tratti — vedi `data/repositories/maps_repo.py::apply_stroke_batch`)
    contiene almeno un tratto NON normalizzato (pixel assoluti pre-fix
    2026-08-12 — vedi il docstring del modulo). Usata dalla UI (2026-08-19)
    per mostrare un avviso una tantum: questi tratti restano renderizzati
    "as-is" (`denormalize_points` non li tocca) e possono quindi apparire
    disallineati su un dispositivo con un riquadro di disegno diverso da
    quello con cui furono disegnati — nessuna migrazione automatica è
    possibile (le dimensioni originali del riquadro non sono recuperabili),
    quindi l'unica azione sensata è darne conto all'utente, non nasconderla.

    `False` per JSON vuoto/non valido/nessun tratto — stesso principio
    "degrada, non solleva mai" già seguito da `apply_stroke_batch`.
    """
    try:
        strokes = json.loads(annotations_json or "[]")
    except (json.JSONDecodeError, TypeError):
        return False
    if not isinstance(strokes, list):
        return False
    for stroke in strokes:
        if not isinstance(stroke, dict):
            continue
        points = stroke.get("points", [])
        if points and not looks_normalized(points):
            return True
    return False


def contain_rect(box_w: float, box_h: float, img_w: float, img_h: float) -> tuple[float, float, float, float]:
    """
    Rettangolo (`offset_x, offset_y, draw_w, draw_h`) effettivamente
    occupato da un'immagine dentro un riquadro `box_w`x`box_h` con
    `ft.BoxFit.CONTAIN` — stessa logica di Flutter: l'immagine mantiene il
    proprio aspect ratio ed è centrata, con bande vuote (letterboxing) sui
    lati la cui proporzione eccede quella del box.

    Bug corretto qui (2026-08-16, segnalato da Davide dopo il primo giro di
    test su Wi-Fi reale — "il disegno del master su PC non corrisponde sulla
    mappa vista dal giocatore su smartphone"): `normalize_points`/
    `denormalize_points` convertivano le coordinate rispetto all'INTERO
    riquadro di disegno, non rispetto al rettangolo che l'immagine occupa
    davvero dopo `BoxFit.CONTAIN`. Un desktop (tipicamente landscape largo)
    e uno smartphone (tipicamente portrait stretto) producono letterboxing
    di entità/posizione diversa per la STESSA immagine — solo il centro
    esatto restava coincidente tra i due, ogni punto più lontano dal centro
    finiva disallineato, nei casi peggiori nella banda vuota, fuori
    dall'immagine vera sullo schermo del giocatore. Il fix del 2026-08-12
    (frazioni [0,1] invece di pixel assoluti) risolveva la differenza di
    dimensione ASSOLUTA del box tra dispositivi, ma non la differenza di
    RAPPORTO D'ASPETTO combinata con CONTAIN — un caso distinto.

    Fallback: se una qualunque dimensione non è nota/nulla (`on_size_change`
    non ancora arrivato, immagine non ancora caricata), ritorna l'intero box
    — stesso comportamento di prima, mai peggiore.
    """
    if not box_w or not box_h or not img_w or not img_h:
        return 0.0, 0.0, box_w, box_h
    box_ratio = box_w / box_h
    img_ratio = img_w / img_h
    if img_ratio > box_ratio:
        # Immagine più "larga" del box: occupa tutta la larghezza,
        # letterboxing sopra/sotto.
        draw_w = box_w
        draw_h = box_w / img_ratio
        return 0.0, (box_h - draw_h) / 2, draw_w, draw_h
    # Immagine più "alta" (o pari) del box: occupa tutta l'altezza,
    # letterboxing ai lati.
    draw_h = box_h
    draw_w = box_h * img_ratio
    return (box_w - draw_w) / 2, 0.0, draw_w, draw_h


def looks_normalized(points: list) -> bool:
    """Euristica: un tratto salvato in frazioni ha ogni coordinata in
    [0, 1]. Lista vuota: nessun punto da giudicare, tratta come "già
    normalizzato" (nessun effetto su `denormalize_points`, che con lista
    vuota non fa comunque nulla)."""
    return all(0.0 <= x <= 1.0 and 0.0 <= y <= 1.0 for x, y in points)


def normalize_points(points: list, box_w: float, box_h: float,
                      offset_x: float = 0.0, offset_y: float = 0.0) -> list[list[float]]:
    """Pixel assoluti (relativi al riquadro di disegno intero) -> frazioni
    [0,1] rispetto al rettangolo `box_w`x`box_h` che parte da
    (`offset_x`, `offset_y`) — per una mappa condivisa questo è il
    rettangolo effettivo dell'immagine dopo `BoxFit.CONTAIN`
    (`contain_rect()`), non l'intero riquadro di disegno: vedi il docstring
    di `contain_rect()` per il bug che questo risolve. Con `offset_x=
    offset_y=0.0` (default, compatibile con l'uso precedente) si comporta
    come prima. Ritorna i punti invariati se la dimensione non è ancora
    nota (`on_size_change` non è ancora arrivato, caso raro: il primo
    evento di norma precede qualunque gesture reale)."""
    if not box_w or not box_h:
        return [[float(x), float(y)] for x, y in points]
    return [[(x - offset_x) / box_w, (y - offset_y) / box_h] for x, y in points]


def denormalize_points(points: list, box_w: float, box_h: float,
                        offset_x: float = 0.0, offset_y: float = 0.0) -> list[list[float]]:
    """Frazioni [0,1] -> pixel assoluti nel rettangolo CORRENTE `box_w`x
    `box_h` a partire da (`offset_x`, `offset_y`) — usata ad ogni ridisegno
    del canvas, mai una sola volta al salvataggio: è così che lo stesso
    tratto si allinea correttamente in riquadri di dimensioni diverse. Un
    tratto che NON sembra normalizzato (`looks_normalized()` falso — dati
    pre-fix) passa invariato: era già in pixel assoluti, ririscalarlo lo
    romperebbe invece di ripararlo."""
    if not points:
        return []
    if not looks_normalized(points):
        return [[float(x), float(y)] for x, y in points]
    if not box_w or not box_h:
        return [[float(x), float(y)] for x, y in points]
    return [[x * box_w + offset_x, y * box_h + offset_y] for x, y in points]
