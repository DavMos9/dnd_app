"""
Design system dell'app — token e primitive riusabili.

Introdotto con la **Fase A del restyle** (revisione 2026-07-26, vedi
`dnd_app/docs/restyle_design.md`). Prima di questo modulo l'app non aveva un
sistema visivo utilizzabile: `ui/theme.py` offriva `fantasy_card()` ma era
chiamata da soli 2 file su 25, mentre le altre view costruivano **166 card a
mano** con `ft.Border(...)` e 153 `"#ffffff"` hardcoded. Conseguenza pratica:
cambiare un raggio o un colore significava toccare 25 file.

Cosa c'è qui:
  1. **Token**: scale di spaziatura, raggi, elevazioni, durate, tipografia.
  2. **Palette doppia** (chiaro/scuro) con contrasti WCAG **calcolati**, non
     scelti a occhio — vedi la tabella in `restyle_design.md`.
  3. **Primitive**: `surface`, `card`, `section`, `pill`, `chip`, `stat_tile`,
     `metric_bar`, `empty_state` — sostituiscono le card inline.

Regola per il futuro: **nessun colore o numero magico nelle view**. Se serve un
valore nuovo, si aggiunge un token qui.

Nota sul tema scuro: i token si leggono tramite `T()` (funzione, non costante),
così cambiare `set_mode()` e ricostruire la vista applica la nuova palette.
Questo funziona perché tutte le view del progetto si ricostruiscono già da zero
ad ogni refresh/navigazione. Le costanti `COLOR_*` di `config/settings.py`
restano valide e invariate: la migrazione delle view avviene per fasi
successive, una superficie alla volta.

Ogni API Flet usata qui è verificata per introspezione su `flet==0.85.3`:
`Container.shadow/gradient/animate/animate_scale/ink_color`, `ft.BoxShadow`
(`spread_radius, blur_radius, color, offset, blur_style`), `ft.LinearGradient`
(`colors, stops, begin, end, rotation, tile_mode`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal

import flet as ft

# ---------------------------------------------------------------------------
# Scale
# ---------------------------------------------------------------------------


class Space:
    """Scala di spaziatura (multipli di 4). Niente più numeri scelti a caso."""
    XS = 4
    SM = 8
    MD = 12
    LG = 16
    XL = 24
    XXL = 32


class Radius:
    """Scala dei raggi. Prima l'app usava 140× `radius=6` e 49× `radius=4`."""
    SM = 8
    MD = 12
    LG = 16
    XL = 20
    PILL = 999


class Duration:
    """Durate delle animazioni, in millisecondi."""
    FAST = 120
    BASE = 200
    SLOW = 320


CURVE = ft.AnimationCurve.EASE_OUT


class Font:
    """
    Famiglie tipografiche (Fase B.1 del restyle, 2026-07-30).

    I tre font sono self-hosted in `assets/fonts/` — nessuna richiesta di rete,
    coerente col vincolo offline-first del progetto. I nomi qui sono le chiavi
    di `FONT_FILES` registrate in `page.fonts` da `DnDApp._setup_page()`.

    Sono usate le versioni **variable** (un solo file per famiglia, asse
    `wght`): Cinzel 400-900, Inter 100-900, JetBrains Mono 100-800. Se Flutter
    non dovesse mappare `FontWeight` sull'asse `wght`, il fallback è il peso di
    default (400) con grassetto sintetico — mai un font mancante.
    """
    DISPLAY = "Cinzel"        # titoli, nomi personaggio — capitali romane
    BODY = "Inter"            # corpo e testo di regolamento
    MONO = "JetBrains Mono"   # valori numerici (cifre tabellari)


# Percorsi relativi ad `assets_dir` (= `dnd_app/assets/`, vedi
# `data/database.py → get_assets_path()` e `main.py`). Senza `assets_dir`
# impostata questi file non sarebbero raggiungibili: è il motivo per cui la
# Fase A ha dovuto collegarla prima di poter installare i font.
FONT_FILES: dict[str, str] = {
    Font.DISPLAY: "fonts/Cinzel-Variable.ttf",
    Font.BODY: "fonts/Inter-Variable.ttf",
    Font.MONO: "fonts/JetBrainsMono-Variable.ttf",
}


class Size:
    """Scala tipografica. Regola: nessun testo sotto 11px."""
    DISPLAY = 32
    TITLE = 22
    SUBTITLE = 16
    BODY = 14
    BODY_SM = 13
    LABEL = 11
    MONO = 15


# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Palette:
    """
    Token di colore semantici.

    I valori sono stati scelti calcolando il rapporto di contrasto WCAG di ogni
    combinazione testo/superficie, non a occhio. Riferimento completo in
    `docs/restyle_design.md`; i minimi rilevanti:
      * `text` ≥ 14:1 su ogni superficie (AAA)
      * `text_2` ≥ 6.4:1 (AA/AAA)
      * `text_3` ≥ 4.7:1 (AA anche per testo piccolo)
      * `on_primary`/`on_primary_fill` ≥ 4.5:1 sul rispettivo accento pieno

    Il rosso (`primary`/`danger`, alias tra loro) dal 2026-08-15 è su TRE
    livelli, non uno solo — usare quello sbagliato o rompe la leggibilità
    o resta più chiaro del necessario (dettaglio/storia in
    `docs/changelog_storico.md`, cerca "ottavo giro"):
      * `primary`/`danger` ≥ 4.5:1 — testo scorrevole, paragrafi, etichette
      * `primary_icon`/`danger_icon` ≥ 3:1 — SOLO icone isolate e testo
        grande/bold ≥18pt (WCAG 1.4.11/1.4.3 "large text/graphical
        object"), più scuro del testo normale
      * `primary_fill`/`danger_fill` — SOLO riempimenti pieni (bottoni/
        badge/checkbox), sempre con `on_primary_fill` sopra, nessun vincolo
        di contrasto proprio perché non compare mai da solo su `surface`/`bg`
    """
    name: str
    is_dark: bool

    bg: str
    bg_alt: str          # secondo gradino dello sfondo (gradiente pergamena)
    surface: str
    surface_alt: str
    border: str

    text: str
    text_2: str
    text_3: str

    primary: str
    on_primary: str      # testo/icone su `primary` pieno
    magic: str
    success: str
    warning: str
    alert: str           # gradino tra `warning` e `danger` (vedi difficulty_color)
    danger: str
    on_accent: str       # testo su success/warning/magic pieni

    # 2026-08-15 — SOLO per riempimenti pieni (bottoni/badge/checkbox), MAI
    # per testo/icona/bordo scritti direttamente su `surface`/`bg`: `primary`
    # deve restare leggibile da solo (usato così in 325 punti di `ui/`, audit
    # 2026-08-15), quindi in dark mode non può essere scuro quanto un vero
    # bordeaux. `primary_fill` invece ha sempre `on_primary_fill` sopra, può
    # essere scuro quanto serve. In light mode sono alias di `primary`/
    # `on_primary` — il rosso chiaro non ha questo problema.
    primary_fill: str
    on_primary_fill: str
    danger_fill: str     # come `primary_fill`, per i call site che riempiono con `danger`

    # 2026-08-15, ottavo giro — via di mezzo tra `primary` (testo scorrevole,
    # serve 4.5:1) e `primary_fill` (mai da solo, nessun vincolo): icone
    # isolate (IconButton "Elimina"/"Avvia scheda", ecc.) e testo grande/
    # bold (titolo "D&D", ≥18pt bold) ricadono nella soglia WCAG "large
    # text / graphical object" — 3:1, non 4.5:1 (1.4.11/1.4.3) — quindi
    # possono essere più scuri di `primary` restando comunque conformi.
    # MAI per paragrafi/etichette di testo normale: lì serve `primary`.
    # In light mode alias di `primary` (il rosso chiaro non ha soglie
    # diverse da rispettare).
    primary_icon: str
    danger_icon: str

    # Fondi tenui per i riquadri informativi (Fase B.2): prima erano 6 hex
    # diversi sparsi nelle view (#fef9ec, #e8eef8, #eef4ff, #dce8f8, #d4edda…),
    # tutti bianchissimi in tema scuro.
    note_bg: str         # riquadro nota / promemoria (crema)
    info_bg: str         # riquadro informativo (azzurrato)
    success_bg: str      # riquadro "completato / disponibile"

    # Pagina di lettura in stile pergamena (DiaryView, MasterNotesView).
    parchment: str
    parchment_alt: str   # pannello elenco a fianco della pagina

    # Chrome scura della navigazione: volutamente scura in ENTRAMBI i temi
    # (è cuoio, non una superficie), quindi i valori chiaro/scuro sono simili.
    nav_bg: str
    nav_bg_alt: str      # sfondo della voce selezionata
    nav_border: str
    nav_text: str
    nav_muted: str
    nav_accent: str      # accento LEGGIBILE sul fondo scuro della nav: `primary`
                         # su `nav_bg` dà solo 2.45:1, questo 4.55:1 (AA)

    shadow: str          # colore base delle ombre
    shadow_opacity: tuple[float, float, float]   # ELEV 1 / 2 / 3


LIGHT = Palette(
    name="light", is_dark=False,
    bg="#f4efe6", bg_alt="#efe8dc",
    surface="#fffdf9", surface_alt="#ece5d8", border="#d9d0bf",
    text="#1a1c24", text_2="#4a4f63", text_3="#5c6376",
    primary="#a4161a", on_primary="#ffffff",
    magic="#2f4b8f", success="#1f6b3a", warning="#a35a00", alert="#b8420a",
    danger="#a4161a", on_accent="#ffffff",
    primary_fill="#a4161a", on_primary_fill="#ffffff", danger_fill="#a4161a",
    primary_icon="#a4161a", danger_icon="#a4161a",
    note_bg="#fdf6e6", info_bg="#e9eff9", success_bg="#e2efe5",
    parchment="#fffef6", parchment_alt="#f7f2e8",
    nav_bg="#1a0d0d", nav_bg_alt="#3a1010", nav_border="#3a2828",
    nav_text="#f4ece4", nav_muted="#a89490", nav_accent="#d94a4e",
    shadow="#1a1c24", shadow_opacity=(0.08, 0.12, 0.18),
)

DARK = Palette(
    name="dark", is_dark=True,
    # 2026-08-15: bug report Davide, secondo giro — lo sfondo aveva ancora
    # una dominante blu/viola percepibile ("quasi blu invece lo voglio nero
    # opaco"). `bg`/`bg_alt`/`surface`/`surface_alt`/`border`/`nav_bg`/
    # `nav_border` erano tutti tinti verso l'azzurro-viola (tonalità ~250°)
    # fin dalla prima stesura del tema scuro: desaturati qui a tonalità
    # neutra (~0-2% di saturazione residua, impercettibile) mantenendo la
    # stessa luminosità di prima — un nero/grigio scuro davvero neutro, non
    # colorato. `note_bg`/`info_bg`/`success_bg` NON toccati: la loro tinta
    # (calda/blu/verde) è intenzionale, segnala la categoria del riquadro.
    bg="#161617", bg_alt="#1d1c1e",
    # Superficie riavvicinata a `bg` (1.10:1 → 1.02:1, quasi lo stesso salto
    # di prima) e accenti desaturati/scuriti — bug report Davide, primo giro:
    # pannelli troppo "accesi" e colori troppo fluo. `border` resta sullo
    # stesso scarto relativo di prima — è l'unico segnale rimasto per i
    # bordi delle card, ridurlo lo avrebbe reso invisibile.
    #
    # 2026-08-15, quinto giro — bug report Davide con screenshot reale: la
    # barra header (HomeView) e le card personaggio (entrambe su
    # `bgcolor=p.surface`, vedi `home_view.py`/`design.card()`) leggevano
    # ancora "troppo luminose" rispetto al corpo pagina, anche col rapporto
    # di contrasto surface/bg già sceso a 1.02:1 nel giro precedente: un
    # rapporto WCAG basso non garantisce che due riquadri PIENI affiancati
    # sembrino uguali all'occhio (simultaneous contrast) — la formula WCAG
    # misura leggibilità del testo, non l'uniformità percepita tra due
    # campiture. Portati a coincidere esattamente con `bg`/`bg_alt` per
    # eliminare del tutto la dominante di quel giro (blu/viola).
    #
    # 2026-08-15, settimo giro — Davide: la fusione totale andava bene ma
    # voleva un "leggero distacco" tra card/header e fondo pagina, con un
    # GRIGIO puro (0% saturazione — non una tinta, come lo erano tutti i
    # tentativi precedenti) invece di nessuna differenza. `surface`/
    # `surface_alt` ora sono grigio neutro puro, un gradino sopra `bg`/
    # `bg_alt` (1.08:1/1.11:1 — percettibile ma minimo, niente "glow"):
    # non derivano più da `bg` per costruzione, sono valori indipendenti
    # apposta per restare desaturati anche se `bg` cambiasse in futuro.
    surface="#1e1e1e", surface_alt="#242424", border="#3e3d41",
    text="#f0ece4", text_2="#c2bcae", text_3="#9c94a8",
    # 2026-08-15, quarto giro — bug report Davide: il rosso corallo non
    # piaceva (voleva un bordeaux vino, #8d2132 poi #761c2a — entrambi
    # ~2:1 di contrasto su `surface`, illeggibili nei 325 usi testo/icona/
    # bordo su 478 totali di `primary`/`danger` in `ui/`, vedi audit e
    # scelta "un solo token" nel changelog). Il primo tentativo di
    # schiarire in spazio HSL (`#d4596c`) è stato giudicato "non
    # corrisponde a quello visto online" — troppo tenue/rosato. Causa:
    # la saturazione HSL non è percettivamente uniforme, portare la
    # lightness da 0.34 (l'hex di Davide) a 0.59 per la leggibilità
    # smorza la resa visiva anche a saturazione HSL invariata. Ricalcolato
    # in OKLCH (croma percettivo, non HSL) sulla tonalità dei due hex di
    # Davide (H≈17° OKLCH) → `#e04f61`.
    #
    # 2026-08-15, settimo giro — dopo l'introduzione di `primary_fill` per
    # il bordeaux vero (sesto giro, sotto), Davide: i pulsanti vanno bene
    # così, ma anche il testo rosso resta troppo chiaro, va scurito. Stesso
    # vincolo tecnico di sempre (325 usi testo/icona/bordo, servono ≥4.5:1)
    # ma stavolta calcolato contro il **peggiore dei due** fondi su cui
    # questo testo può comparire — `surface` (ora più chiaro di `bg`, vedi
    # sopra) è il vincolo binante, non `bg` come nei giri precedenti: un
    # primo calcolo fatto solo contro `bg` (`#d35561`) risultava sotto
    # soglia su `surface` (4.16:1) e andava scartato. Ricalcolato in OKLCH
    # contro ENTRAMBI → `#da5b67`, croma 0.16 (contro 0.18 di `#e04f61`) —
    # percettibilmente più scuro/meno acceso, margine minimo ma sopra
    # soglia su entrambi (4.50 su surface, 4.89 su bg). Limite tecnico:
    # non si può scurire oltre restando sia "rosso" (non grigio-mauve) sia
    # leggibile da solo su entrambi i fondi.
    primary="#da5b67", on_primary="#241012",
    magic="#7897db", success="#4ec27f", warning="#bd8c32", alert="#d57d40",
    danger="#da5b67", on_accent="#161617",
    # 2026-08-15, sesto giro — Davide, dopo tre schiariture successive di
    # `primary` (tutte respinte, "non corrisponde a quello visto online"):
    # nessuna schiaritura di un bordeaux può bastare, perché la richiesta
    # ("bordeaux vino scuro") e il vincolo di leggibilità testo (≥4.5:1 su
    # `surface` quasi-nera) sono in conflitto diretto per costruzione — non
    # esiste una tinta che sia insieme "scura come il vino" e "chiara
    # abbastanza da leggersi da sola sul nero". Sdoppiato come preannunciato:
    # `primary_fill` è il bordeaux vero di Davide (ultimo hex indicato,
    # `#761c2a`), usato SOLO nei ~141 punti di riempimento (bottoni/badge/
    # checkbox) dove sopra c'è sempre `on_primary_fill` (bianco, 10.7:1 di
    # contrasto) — mai da solo su `surface`/`bg`. `primary` resta `#e04f61`
    # per i 325 punti testo/icona/bordo, invariato.
    primary_fill="#761c2a", on_primary_fill="#ffffff", danger_fill="#761c2a",
    # 2026-08-15, ottavo giro — Davide: anche icone isolate (bottoni
    # "Elimina scheda"/"Avvia scheda" in home_view.py, ecc.) e il titolo
    # "D&D" (48px bold) restano "troppo chiari", li vuole vicini al
    # bordeaux dei pulsanti. Non possono usare `primary_fill` (1.7:1 su
    # `surface`, illeggibile da soli) ma non serve nemmeno il 4.5:1 di
    # `primary`: WCAG 1.4.11/1.4.3 richiedono solo 3:1 per icone isolate e
    # testo grande/bold — via di mezzo calcolata in OKLCH sullo stesso hue
    # (H≈17°), croma 0.17, fino al minimo che regge 3:1 su ENTRAMBI i
    # fondi (3.08 su surface, 3.34 su bg — margine minimo voluto sopra il
    # pavimento esatto 3.00, non sotto).
    primary_icon="#bf384b", danger_icon="#bf384b",
    # I fondi tenui in dark non possono essere "chiari": sono la superficie
    # alternativa leggermente tinta verso l'accento corrispondente.
    note_bg="#1d1b14", info_bg="#1d2029", success_bg="#17201b",
    parchment="#1e1e1e", parchment_alt="#242424",
    nav_bg="#101010", nav_bg_alt="#2a1418", nav_border="#2c2c2e",
    nav_text="#f0ece4", nav_muted="#8e8799", nav_accent="#da5b67",
    shadow="#000000", shadow_opacity=(0.45, 0.55, 0.65),
)

_MODE: Literal["light", "dark"] = "light"


def set_mode(mode: Literal["light", "dark"]) -> None:
    """Imposta il tema attivo. Le view vanno ricostruite dopo la chiamata."""
    global _MODE
    _MODE = mode


def mode() -> str:
    return _MODE


def T() -> Palette:
    """Token attivi. Funzione e non costante: serve al tema scuro."""
    return DARK if _MODE == "dark" else LIGHT


# ---------------------------------------------------------------------------
# Elevazione
# ---------------------------------------------------------------------------


def _rgba(hex_color: str, opacity: float) -> str:
    """'#rrggbb' + opacità → stringa colore accettata da Flet."""
    return ft.Colors.with_opacity(opacity, hex_color)


def elevation(level: int = 1) -> ft.BoxShadow | None:
    """
    Ombra morbida a 3 livelli (0 = nessuna). In tema scuro le ombre sono più
    diffuse e più opache, altrimenti scompaiono sullo sfondo.
    """
    if level <= 0:
        return None
    p = T()
    level = min(level, 3)
    blur, dy = {1: (8, 2), 2: (16, 4), 3: (32, 8)}[level]
    if p.is_dark:
        blur = {1: 12, 2: 20, 3: 40}[level]
    return ft.BoxShadow(
        blur_radius=blur,
        spread_radius=0,
        offset=ft.Offset(0, dy),
        color=_rgba(p.shadow, p.shadow_opacity[level - 1]),
    )


def page_gradient() -> ft.LinearGradient:
    """
    Sfondo pagina: gradiente a contrasto minimo (≈2% di luminosità) che dà la
    sensazione della pergamena senza usare immagini — peso zero, funziona
    identico in tema scuro.
    """
    p = T()
    return ft.LinearGradient(
        begin=ft.Alignment.TOP_CENTER,
        end=ft.Alignment.BOTTOM_CENTER,
        colors=[p.bg, p.bg_alt],
    )


# ---------------------------------------------------------------------------
# Chrome degli overlay (editor mappe)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Chrome:
    """
    Palette dei pannelli sovrapposti a un'immagine (oggi: l'editor di mappe).

    È **scura in entrambi i temi** per scelta, non per dimenticanza: una barra
    strumenti chiara sopra una mappa competerebbe con l'immagine e renderebbe
    illeggibili i tratti chiari. Vive qui e non come dizionario di hex dentro
    `maps_view.py` così anche questa superficie rispetta la regola "nessun
    colore magico nelle view".
    """
    bg: str            # barra strumenti
    panel: str         # pannello secondario (slider)
    btn: str           # bottone non selezionato
    border: str
    text: str
    text_muted: str
    text_dim: str
    on_light: str      # testo su swatch/bottone chiaro selezionato
    danger: str        # "Cancella tutto"
    backdrop: str      # sfondo del fullscreen
    canvas: str        # area di disegno
    overlay_text: str  # etichette scritte sopra la mappa
    overlay_dim: str   # loro alone/ombra


CHROME = Chrome(
    bg="#24222b", panel="#1a181f", btn="#322e3c", border="#423d4f",
    text="#f5f2ee", text_muted="#b8b2c2", text_dim="#9c96a8",
    on_light="#17151c", danger="#6d1b1f",
    backdrop="#100f14", canvas="#000000",
    overlay_text="#ffffffdd", overlay_dim="#00000066",
)


# ---------------------------------------------------------------------------
# Colori semantici di dominio
# ---------------------------------------------------------------------------

# Colori delle monete: sono i colori dei METALLI, non della UI — restano
# identici nei due temi (il rame è rame anche di notte) e funzionano su fondo
# sia chiaro sia scuro. Prima vivevano come 5 hex inline in `inventario_tab.py`.
CURRENCY_COLORS: dict[str, str] = {
    "MR": "#b87333",   # rame
    "MA": "#a0a0b0",   # argento
    "ME": "#6a9060",   # electrum
    "MO": "#c8a000",   # oro
    "MP": "#a0c8d0",   # platino
}

# Scala di difficoltà degli incontri (DMG). Prima era un dizionario di hex
# duplicato **identico** in `master_encounter_view.py` e
# `master_encounter_generator_dialog.py`: qui è una sola mappa
# difficoltà → token semantico, così segue anche il tema scuro.
_DIFFICULTY_TONES: dict[str, str] = {
    "trascurabile": "text_3",
    "facile": "success",
    "medio": "warning",
    "difficile": "alert",
    "letale": "danger",
    "indeterminato": "text_3",
}


def difficulty_color(key: str) -> str:
    """Colore per una categoria di difficoltà d'incontro (default: neutro)."""
    p = T()
    return getattr(p, _DIFFICULTY_TONES.get((key or "").lower(), "text_3"))


# ---------------------------------------------------------------------------
# Tipografia
# ---------------------------------------------------------------------------


def title(text: str, size: int = Size.TITLE, color: str | None = None) -> ft.Text:
    return ft.Text(text, size=size, weight=ft.FontWeight.BOLD,
                   color=color or T().text, font_family=Font.DISPLAY)


def subtitle(text: str, color: str | None = None) -> ft.Text:
    return ft.Text(text, size=Size.SUBTITLE, weight=ft.FontWeight.W_600,
                   color=color or T().text, font_family=Font.BODY)


def body(text: str, size: int = Size.BODY, color: str | None = None,
         weight: ft.FontWeight | None = None) -> ft.Text:
    return ft.Text(text, size=size, color=color or T().text,
                   font_family=Font.BODY, weight=weight)


def muted(text: str, size: int = Size.BODY_SM, color: str | None = None) -> ft.Text:
    return ft.Text(text, size=size, color=color or T().text_3, font_family=Font.BODY)


def label(text: str, color: str | None = None) -> ft.Text:
    return ft.Text(text.upper(), size=Size.LABEL, weight=ft.FontWeight.BOLD,
                   color=color or T().text_3, font_family=Font.BODY,
                   style=ft.TextStyle(letter_spacing=1))


# ---------------------------------------------------------------------------
# Primitive
# ---------------------------------------------------------------------------


def surface(content: ft.Control, *, level: int = 1, padding: int = Space.LG,
            radius: int = Radius.MD, alt: bool = False,
            expand: bool | None = None) -> ft.Container:
    """Superficie elevata generica — sostituisce i `Container(bgcolor=..., border=...)`."""
    p = T()
    return ft.Container(
        content=content,
        bgcolor=p.surface_alt if alt else p.surface,
        padding=padding,
        border_radius=radius,
        shadow=elevation(level),
        expand=expand,
    )


def card(content: ft.Control, *, accent: str | None = None, level: int = 1,
         padding: int = Space.LG, on_click: Callable[[Any], None] | None = None,
         tooltip: str | None = None, expand: bool | None = None) -> ft.Container:
    """
    Card standard. L'accento è una **barra sottile a sinistra**, non un filetto
    in cima: è il singolo cambiamento che sposta più percezione di modernità
    rispetto al vecchio `fantasy_card()`.

    Se `on_click` è passato, la card diventa interattiva (ink + animazione).
    """
    p = T()
    c = ft.Container(
        content=content,
        bgcolor=p.surface,
        padding=padding,
        border_radius=Radius.MD,
        shadow=elevation(level),
        border=(ft.Border.only(left=ft.BorderSide(3, accent)) if accent else None),
        on_click=on_click,
        tooltip=tooltip,
        ink=bool(on_click),
        animate=ft.Animation(Duration.BASE, CURVE),
        animate_scale=ft.Animation(Duration.FAST, CURVE),
        expand=expand,
    )
    return c


def section(title_text: str, content: ft.Control, *,
            accent: str | None = None, trailing: ft.Control | None = None,
            level: int = 1) -> ft.Container:
    """Sezione con intestazione — sostituisce `section_header()` + Column manuale."""
    p = T()
    head: list[ft.Control] = [
        ft.Container(width=3, height=14, bgcolor=accent or p.primary_fill,
                     border_radius=Radius.SM),
        ft.Container(width=Space.SM),
        ft.Text(title_text.upper(), size=Size.LABEL, weight=ft.FontWeight.BOLD,
                color=p.text_2, font_family=Font.BODY,
                style=ft.TextStyle(letter_spacing=1.5)),
    ]
    if trailing is not None:
        head.append(ft.Container(expand=True))
        head.append(trailing)
    return surface(
        ft.Column(
            [
                ft.Row(head, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Container(height=Space.MD),
                content,
            ],
            spacing=0, tight=True,
        ),
        level=level,
    )


def collapsible_section(
    title_text: str,
    content_builder: Callable[[], ft.Control],
    *,
    expanded: bool = False,
    accent: str | None = None,
    level: int = 1,
    header_subtitle: str | None = None,
    on_toggle: Callable[[bool], None] | None = None,
    alt: bool = False,
) -> ft.Control:
    """
    Sezione con intestazione cliccabile che mostra/nasconde il contenuto —
    generalizza il pannello "STRUMENTI MASTER" di `master_view.py`
    (`_build_tools_panel()`), mai estratto come primitiva pur essendo
    pianificato (`docs/restyle_design.md`: `section(collapsible=...)`).
    Pensata per descrizioni lunghe (es. le sezioni di una scheda mostro) da
    tenere chiuse finché non servono, riducendo lo spazio occupato.

    Nessuno stato interno: Flet ricostruisce le view da zero ad ogni
    `_build()`/navigazione, quindi lo stato aperto/chiuso non può vivere
    qui — resta un attributo di istanza nel chiamante (stesso principio già
    in uso per `_tools_panel_expanded`/`set_mobile`), passato con
    `expanded=` e restituito via `on_toggle(new_state)`: il chiamante
    decide se sostituire l'intero controllo in place (`self.controls[idx] =
    ...`) o rigenerare solo un `ft.Ref` locale.

    `content_builder` è una funzione, non un controllo già costruito: se la
    sezione parte chiusa, il contenuto (potenzialmente pesante — liste di
    azioni di un mostro, dropdown, ecc.) non viene costruito finché l'utente
    non apre.
    """
    p = T()
    header_children: list[ft.Control] = [
        ft.Container(width=3, height=14, bgcolor=accent or p.primary_fill,
                     border_radius=Radius.SM),
        ft.Container(width=Space.SM),
    ]
    label_col: list[ft.Control] = [
        ft.Text(title_text.upper(), size=Size.LABEL, weight=ft.FontWeight.BOLD,
                color=p.text_2, font_family=Font.BODY,
                style=ft.TextStyle(letter_spacing=1.5)),
    ]
    if header_subtitle:
        label_col.append(ft.Text(header_subtitle, size=Size.BODY_SM, color=p.text_2,
                                 no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS))
    header_children.append(ft.Column(label_col, spacing=1, expand=True))
    header_children.append(ft.Icon(
        ft.Icons.EXPAND_LESS if expanded else ft.Icons.EXPAND_MORE,
        size=20, color=p.text_3,
    ))

    def _on_header_click(e: Any) -> None:
        if on_toggle is not None:
            on_toggle(not expanded)

    header = ft.Container(
        content=ft.Row(header_children, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        padding=ft.Padding.symmetric(horizontal=Space.LG, vertical=Space.SM),
        on_click=_on_header_click,
        ink=True,
    )

    if not expanded:
        return surface(header, level=level, padding=0, alt=alt)

    return surface(
        ft.Column(
            [
                header,
                ft.Container(
                    content=content_builder(),
                    padding=ft.Padding.only(left=Space.LG, right=Space.LG, bottom=Space.MD),
                    animate=ft.Animation(Duration.BASE, CURVE),
                ),
            ],
            spacing=0, tight=True,
        ),
        level=level, padding=0, alt=alt,
    )


def pill(icon: ft.IconData | None, text: str, *,
         color: str | None = None, on_click: Callable[[Any], None] | None = None,
         filled: bool = False, tooltip: str | None = None) -> ft.Container:
    """
    Pillola azione — unifica le 3 copie di `_tool_pill`/`_action_pill`/
    `_header_actions` che vivevano in master_view / master_encounter_view /
    home_view.
    """
    p = T()
    col = color or p.primary
    kids: list[ft.Control] = []
    if icon is not None:
        kids.append(ft.Icon(icon, size=15, color=p.on_primary if filled else col))
    if icon is not None and text:
        kids.append(ft.Container(width=6))
    if text:
        kids.append(ft.Text(text, size=12, weight=ft.FontWeight.BOLD,
                            color=p.on_primary if filled else col,
                            font_family=Font.BODY))
    return ft.Container(
        content=ft.Row(kids, spacing=0, tight=True,
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
        padding=ft.Padding.symmetric(horizontal=Space.MD, vertical=Space.SM),
        bgcolor=col if filled else p.surface,
        border=None if filled else ft.Border.all(1, col),
        border_radius=Radius.PILL,
        on_click=on_click,
        tooltip=tooltip,
        ink=bool(on_click),
        animate_scale=ft.Animation(Duration.FAST, CURVE),
    )


Tone = Literal["neutral", "primary", "magic", "success", "warning", "danger"]


def tone_color(tone: Tone) -> str:
    p = T()
    return {
        "neutral": p.text_3, "primary": p.primary, "magic": p.magic,
        "success": p.success, "warning": p.warning, "danger": p.danger,
    }[tone]


def chip(text: str, tone: Tone = "neutral", *, icon: ft.IconData | None = None,
         filled: bool = False) -> ft.Container:
    """Chip informativo compatto (rarità, livello incantesimo, stato, tag…)."""
    p = T()
    col = tone_color(tone)
    kids: list[ft.Control] = []
    if icon is not None:
        kids.append(ft.Icon(icon, size=12, color=p.on_accent if filled else col))
        kids.append(ft.Container(width=4))
    kids.append(ft.Text(text, size=Size.LABEL, weight=ft.FontWeight.BOLD,
                        color=p.on_accent if filled else col, font_family=Font.BODY))
    return ft.Container(
        content=ft.Row(kids, spacing=0, tight=True,
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
        padding=ft.Padding.symmetric(horizontal=Space.SM, vertical=3),
        bgcolor=col if filled else ft.Colors.with_opacity(0.12, col),
        border_radius=Radius.PILL,
    )


#: Stati di `RemoteBackend.connection_state()` (`core/world_backend.py`)
#: considerati "online" — solo `"connected"` mostra il LED verde, ogni altro
#: valore (`disconnected|pending|rejected|error`) mostra rosso: un giocatore
#: deve poter fidarsi del verde senza dover distinguere le sfumature del
#: perché non è connesso.
_CONNECTION_OK_STATES = {"connected"}


def connection_led(state: str, *, tooltip: str | None = None) -> ft.Container:
    """
    Pallino di stato connessione (richiesta di Davide, 2026-08-16: "il
    player sa sempre se è sincronizzato o se l'hosting si è interrotto",
    senza dover aprire la Sezione Mondi) — verde/rosso, riusato identico in
    Home (`home_view.py`, un LED per gruppo-mondo remoto), sulla scheda
    personaggio (`sheet_view.py`, header, solo lato giocatore/replica) e nel
    dettaglio Sezione Mondi (`world_view.py`, accanto al pulsante
    "Riconnettiti").
    """
    p = T()
    online = state in _CONNECTION_OK_STATES
    col = p.success if online else p.danger
    return ft.Container(
        width=9, height=9, border_radius=Radius.PILL, bgcolor=col,
        tooltip=tooltip or ("Sincronizzato" if online else "Non connesso all'host"),
    )


def hp_tone(current: float, maximum: float) -> Tone:
    """Verde sopra metà, ambra sopra un quarto, rosso sotto — soglie di sempre."""
    if maximum <= 0:
        return "neutral"
    r = current / maximum
    return "success" if r > 0.5 else ("warning" if r > 0.25 else "danger")


def hp_bar(current: int, maximum: int, temp: int = 0, *, height: int = 14) -> ft.Container:
    """
    Barra dei punti ferita a segmenti (Fase E.4 del restyle).

    Prima era una `ProgressBar` piatta che ignorava del tutto i PF temporanei.
    Qui i segmenti sono Container con peso `expand`, quindi le proporzioni sono
    esatte e i PF temporanei hanno una loro fascia in colore `magic` — si vede a
    colpo d'occhio quanta parte della barra è "presa in prestito".
    """
    p = T()
    cur = max(0, current)
    tmp = max(0, temp)
    total = max(maximum, cur + tmp, 1)
    tone = hp_tone(cur, maximum)
    segs: list[ft.Control] = []
    if cur:
        segs.append(ft.Container(bgcolor=tone_color(tone), expand=cur))
    if tmp:
        segs.append(ft.Container(bgcolor=p.magic, expand=tmp))
    rest = total - cur - tmp
    if rest > 0:
        segs.append(ft.Container(bgcolor=ft.Colors.with_opacity(0.5, p.border), expand=rest))
    return ft.Container(
        content=ft.Row(segs, spacing=0),
        height=height,
        border_radius=Radius.PILL,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        bgcolor=ft.Colors.with_opacity(0.5, p.border),
        animate=ft.Animation(Duration.BASE, CURVE),
    )


def slot_dots(total: int, used: int, *, tone: Tone = "magic", size: int = 16,
              max_shown: int = 12) -> ft.Row:
    """
    Pallini degli slot incantesimo / risorse di classe (Fase E.4).

    Pieno = disponibile, anello vuoto = speso. Prima erano cerchi con bordo 1px
    e riempimento pieno/grigio: l'anello rende la differenza leggibile anche a
    colpo d'occhio e in tema scuro.
    """
    p = T()
    col = tone_color(tone)
    avail = max(0, total - max(0, used))
    dots: list[ft.Control] = []
    shown = min(total, max_shown)
    for i in range(shown):
        is_avail = i < avail
        dots.append(ft.Container(
            width=size, height=size, border_radius=size // 2,
            bgcolor=col if is_avail else "transparent",
            border=None if is_avail else ft.Border.all(2, ft.Colors.with_opacity(0.45, col)),
            animate=ft.Animation(Duration.FAST, CURVE),
        ))
    if total > max_shown:
        dots.append(ft.Text(f"+{total - max_shown}", size=Size.LABEL,
                            color=p.text_3, font_family=Font.MONO))
    return ft.Row(dots, spacing=Space.XS, wrap=True)


def dot_button(filled: bool, *, tone: Tone = "magic", size: int = 18,
               on_click: Callable[[Any], None] | None = None,
               tooltip: str | None = None, dim: bool = False) -> ft.Container:
    """
    Pallino CLICCABILE (slot incantesimo, risorse di classe, TS contro morte).

    Stessa resa di `slot_dots` — pieno = disponibile, anello = speso — ma con
    tap-target adeguato: il pallino disegnato è `size`, l'area cliccabile ha 4px
    di padding attorno, così resta comodo anche col dito su tablet.
    """
    col = tone_color(tone)
    inner = ft.Container(
        width=size, height=size, border_radius=size // 2,
        bgcolor=col if filled else "transparent",
        border=None if filled else ft.Border.all(
            2, ft.Colors.with_opacity(0.20 if dim else 0.45, col)),
        animate=ft.Animation(Duration.FAST, CURVE),
    )
    return ft.Container(
        content=inner,
        padding=ft.Padding.all(Space.XS),
        border_radius=Radius.PILL,
        on_click=on_click,
        tooltip=tooltip,
        ink=bool(on_click),
        animate_scale=ft.Animation(Duration.FAST, CURVE),
    )


def dialog_title(text: str, icon: ft.IconData | None = None,
                 tone: Tone = "primary") -> ft.Control:
    """
    Intestazione standard dei dialog: icona in un cerchietto tinto + titolo nel
    font display. Prima ogni dialog costruiva il proprio `ft.Text` con
    dimensione, peso e colore scelti caso per caso (101 varianti).
    """
    p = T()
    col = tone_color(tone)
    kids: list[ft.Control] = []
    if icon is not None:
        kids.append(ft.Container(
            content=ft.Icon(icon, size=18, color=col),
            width=36, height=36, alignment=ft.Alignment.CENTER,
            bgcolor=ft.Colors.with_opacity(0.12, col),
            border_radius=Radius.PILL,
        ))
        kids.append(ft.Container(width=Space.MD))
    kids.append(ft.Text(text, size=Size.SUBTITLE, weight=ft.FontWeight.BOLD,
                        color=p.text, font_family=Font.DISPLAY,
                        expand=True, no_wrap=False))
    return ft.Row(kids, tight=True, vertical_alignment=ft.CrossAxisAlignment.CENTER)


def field_style() -> dict[str, Any]:
    """
    Stile condiviso di `TextField`/`Dropdown`.

    Flet 0.85.3 **non ha** `input_decoration_theme` in `ft.Theme` (verificato per
    introspezione), quindi i campi non si possono uniformare dal tema: questi
    kwarg vengono applicati a ogni campo dell'app.
    """
    p = T()
    return dict(
        border_radius=Radius.SM,
        border_color=p.border,
        focused_border_color=p.magic,
        bgcolor=p.surface,
        text_style=ft.TextStyle(size=Size.BODY_SM, color=p.text,
                                font_family=Font.BODY),
    )


def empty_state(icon: ft.IconData, title_text: str, hint: str = "",
                action: ft.Control | None = None) -> ft.Container:
    """Stato vuoto uniforme — l'app ne aveva ~12 scritti a mano tutti diversi."""
    p = T()
    kids: list[ft.Control] = [
        ft.Icon(icon, size=48, color=p.text_3),
        ft.Container(height=Space.MD),
        ft.Text(title_text, size=Size.SUBTITLE, weight=ft.FontWeight.W_600,
                color=p.text_2, font_family=Font.BODY,
                text_align=ft.TextAlign.CENTER),
    ]
    if hint:
        kids += [ft.Container(height=Space.XS),
                 ft.Text(hint, size=Size.BODY_SM, color=p.text_3,
                         font_family=Font.BODY, text_align=ft.TextAlign.CENTER)]
    if action is not None:
        kids += [ft.Container(height=Space.LG), action]
    return ft.Container(
        content=ft.Column(kids, spacing=0, tight=True,
                          horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        padding=Space.XXL,
        alignment=ft.Alignment.CENTER,
    )
