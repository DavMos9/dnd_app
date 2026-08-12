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


def looks_normalized(points: list) -> bool:
    """Euristica: un tratto salvato in frazioni ha ogni coordinata in
    [0, 1]. Lista vuota: nessun punto da giudicare, tratta come "già
    normalizzato" (nessun effetto su `denormalize_points`, che con lista
    vuota non fa comunque nulla)."""
    return all(0.0 <= x <= 1.0 and 0.0 <= y <= 1.0 for x, y in points)


def normalize_points(points: list, box_w: float, box_h: float) -> list[list[float]]:
    """Pixel assoluti (relativi al riquadro di dimensione `box_w`x`box_h`)
    -> frazioni [0,1]. Ritorna i punti invariati se la dimensione del
    riquadro non è ancora nota (`on_size_change` non è ancora arrivato,
    caso raro: il primo evento di norma precede qualunque gesture reale)."""
    if not box_w or not box_h:
        return [[float(x), float(y)] for x, y in points]
    return [[x / box_w, y / box_h] for x, y in points]


def denormalize_points(points: list, box_w: float, box_h: float) -> list[list[float]]:
    """Frazioni [0,1] -> pixel assoluti nel riquadro CORRENTE (`box_w`x
    `box_h`) — usata ad ogni ridisegno del canvas, mai una sola volta al
    salvataggio: è così che lo stesso tratto si allinea correttamente in
    riquadri di dimensioni diverse. Un tratto che NON sembra normalizzato
    (`looks_normalized()` falso — dati pre-fix) passa invariato: era già
    in pixel assoluti, ririscalarlo lo romperebbe invece di ripararlo."""
    if not points:
        return []
    if not looks_normalized(points):
        return [[float(x), float(y)] for x, y in points]
    if not box_w or not box_h:
        return [[float(x), float(y)] for x, y in points]
    return [[x * box_w, y * box_h] for x, y in points]
