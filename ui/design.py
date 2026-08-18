"""
Design system dell'app — token e primitive riusabili.

**Rifacimento radicale "Arcane Ledger"** (2026-08-20): palette e primitive
ricostruite da zero, nessun valore precedente riusato per continuità. Identità
visiva — grimorio illuminato, non dashboard: oro antico/bronzo come accento
primario (azioni, elementi hero), indaco/violetto (`magic`) come secondo
registro compositivo per contenuto arcano, rosso vero e isolato per
`danger` (prima coincideva con `primary` — separato qui perché nessun
prodotto di riferimento affianca mai i due). Tipografia invariata (Cinzel/
Inter/JetBrains Mono — nessuna alternativa valutata batte Cinzel per un'app
fantasy, resta l'asset già auto-ospitato).

Cosa c'è qui:
  1. **Token**: scale di spaziatura, raggi, elevazioni, durate, tipografia,
     breakpoint (allineati a `ft.ResponsiveRow`, vedi `Breakpoint`).
  2. **Palette doppia** (chiaro/scuro) con contrasti WCAG **calcolati**, non
     scelti a occhio (vedi i commenti sui singoli valori sotto).
  3. **Primitive**: `surface`, `card`, `section`, `hero_title`, `icon_badge`,
     `pill`, `chip`, `hp_bar`, `empty_state` — sostituiscono le card inline.

Regola per il futuro: **nessun colore o numero magico nelle view**. Se serve un
valore nuovo, si aggiunge un token qui.

Nota sul tema scuro: i token si leggono tramite `T()` (funzione, non costante),
così cambiare `set_mode()` e ricostruire la vista applica la nuova palette.
Questo funziona perché tutte le view del progetto si ricostruiscono già da zero
ad ogni refresh/navigazione.

Ogni API Flet usata qui è verificata per introspezione su `flet==0.86.5`:
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
    HERO = 40      # UN momento tipografico dominante per schermata (Arcane Ledger)
    DISPLAY = 32
    TITLE = 22
    SUBTITLE = 16
    BODY = 14
    BODY_SM = 13
    LABEL = 11
    MONO = 15


class Breakpoint:
    """
    Soglie di larghezza — allineate ai default reali di `ft.ResponsiveRow`
    (verificati per introspezione, `flet==0.86.5`: xs=0, sm=576, md=768,
    lg=992, xl=1200, xxl=1400 — valutati lato client, non `page.width` in
    Python). Non reinventare soglie parallele: ogni composizione multi-
    colonna (`asymmetric_row`, `col=` su `ResponsiveRow`) deve usare questi
    stessi nomi. `ui/app.py::_MOBILE_BP=600` (soglia del drill-down mobile,
    calcolata centralmente in `_on_page_resize()`) resta concettualmente
    allineata a `SM`.
    """
    SM = 576
    MD = 768
    LG = 992
    XL = 1200


# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Palette:
    """
    Token di colore semantici — palette "Arcane Ledger" (rifacimento radicale
    2026-08-20, nessun valore ereditato dalla palette precedente).

    Ogni valore è verificato per contrasto WCAG calcolato (script dedicato,
    non a occhio), contro il PEGGIORE dei due fondi su cui il token può
    comparire — `bg` per il tema chiaro (più scuro di `surface`, quindi più
    severo per un primo piano scuro), `surface_alt` per il tema scuro (più
    chiaro di `bg`, quindi più severo per un primo piano chiaro). Minimi:
      * `text` ≥ 7:1 (AAA) su ogni superficie
      * `text_2`/`text_3` ≥ 4.5:1
      * `on_primary`/`on_accent` ≥ 4.5:1 sul rispettivo accento pieno

    **Oro (`primary`) e rosso (`danger`) sono accenti DISTINTI**, non alias:
    in ogni palette di riferimento consultata il colore distruttivo non
    coincide mai col colore primario/brand — averli separati è il cambio
    strutturale principale di questo rifacimento.

    L'oro in tema chiaro ha la stessa tensione che il rosso aveva nella
    palette precedente (una tonalità chiara per natura non può essere insieme
    "oro pieno/saturo" e "leggibile da sola ≥4.5:1 su pergamena chiara"),
    quindi resta sdoppiato su tre livelli:
      * `primary`/`danger` ≥ 4.5:1 — testo scorrevole, paragrafi, etichette
      * `primary_icon`/`danger_icon` ≥ 3:1 — SOLO icone isolate e testo
        grande/bold ≥18pt (WCAG 1.4.11/1.4.3 "large text/graphical object")
      * `primary_fill`/`danger_fill` — SOLO riempimenti pieni (bottoni/
        badge/checkbox), sempre con `on_primary_fill` sopra. In tema scuro
        oro e rosso sono già abbastanza chiari da non avere questa tensione:
        `primary`==`primary_fill`==`primary_icon` (idem per danger).
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
    magic_bg: str        # riquadro a tema arcano (incantesimi, dadi)

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
    # Pergamena calda, più ricca/satura del semplice richiamo cartaceo di
    # prima — hue 38-40° (ambra), non un beige neutro.
    bg="#f0e8db", bg_alt="#eadecd",
    surface="#f8f6f1", surface_alt="#eee6d8", border="#d8cab6",
    # Inchiostro caldo (hue 28°), non nero puro — L=0.16, 11.7:1 su `bg`
    # (ben sopra il minimo AAA 7:1, non spinto oltre come non necessario).
    text="#37281b", text_2="#645240", text_3="#76614c",
    # Oro antico/bronzo — L calcolata al minimo che regge 4.5:1 su `bg`
    # (4.87:1) restando il più "oro" possibile: una tonalità più chiara
    # scende sotto soglia (vedi scan in fase di progettazione).
    primary="#815e18", on_primary="#ffffff",
    magic="#372e9e", success="#217347", warning="#8f4e14", alert="#a7401b",
    # Rosso vero, isolato da `primary` (vedi nota sulla Palette) — 5.6:1 su `bg`.
    danger="#ab2a21", on_accent="#ffffff",
    # `primary_fill` è un oro più saturo/ricco (funziona da bottone pieno con
    # `on_primary_fill` bianco, 5.55:1) — non lo stesso hex di `primary`
    # perché un oro abbastanza chiaro da leggersi bianco-su-oro a piena
    # saturazione scenderebbe sotto la soglia testo-su-pergamena di `primary`.
    primary_fill="#956c0f", on_primary_fill="#ffffff", danger_fill="#ab2a21",
    # Icone isolate/testo grande ≥18pt bold: soglia 3:1 (WCAG 1.4.11/1.4.3),
    # più chiare/vivide del testo normale restando conformi (margine minimo
    # voluto sopra 3.00, non sotto — stessa logica della vecchia palette).
    primary_icon="#a77a20", danger_icon="#dd554b",
    note_bg="#f7f1e3", info_bg="#e5ecf5", success_bg="#e3f2ea", magic_bg="#ebeaf6",
    parchment="#faf9f4", parchment_alt="#f4efe6",
    # Chrome di navigazione — cuoio scuro con accento oro, identico nei due
    # temi per scelta (non è una superficie, è cuoio).
    nav_bg="#1f160f", nav_bg_alt="#2d1f16", nav_border="#403126",
    nav_text="#ebe4d6", nav_muted="#a89c8a", nav_accent="#eab63e",
    shadow="#1f160f", shadow_opacity=(0.08, 0.12, 0.18),
)

DARK = Palette(
    name="dark", is_dark=True,
    # Nero-inchiostro CALDO (hue 28°, non blu-slate neutro da dashboard SaaS
    # generica) — un grimorio di notte, non un pannello di controllo.
    # `surface`/`surface_alt` un gradino sopra `bg` (1.14:1), percettibile
    # ma minimo.
    bg="#17130f", bg_alt="#1f1914",
    surface="#261f1a", surface_alt="#2f2720", border="#473d33",
    # Testo crema calda a 9.3:1/7.4:1 su bg/surface_alt (AAA, con margine ma
    # deliberatamente NON portato oltre ~9:1: un contrasto testo-quasi-
    # bianco-su-nero-quasi-puro è causa nota di affaticamento/"halation"
    # nella lettura prolungata — la stessa lezione della palette precedente,
    # applicata qui fin dall'inizio invece che corretta in un secondo giro).
    text="#c6b795", text_2="#a99d89", text_3="#9c9281",
    # Oro che "brilla" contro il nero — nessuna delle tensioni della
    # controparte chiara: il fondo è già scuro, quindi lo stesso oro serve
    # sia da testo/icona sia da riempimento pieno (con testo scuro sopra).
    primary="#e4b744", on_primary="#1c150f",
    magic="#9790df", success="#5cbc89", warning="#d49c54", alert="#d8805a",
    danger="#de7873", on_accent="#1c150f",
    primary_fill="#e4b744", on_primary_fill="#1c150f", danger_fill="#de7873",
    primary_icon="#e4b744", danger_icon="#de7873",
    # Fondi tenui: superficie alternativa leggermente tinta verso l'accento,
    # mai "chiara" — sarebbe fuori registro su un fondo quasi nero.
    note_bg="#282215", info_bg="#18202a", success_bg="#15231c", magic_bg="#1c192e",
    parchment="#261f1a", parchment_alt="#2f2720",
    # Cuoio ancora più scuro che in tema chiaro (recede ulteriormente di
    # notte) — valore deliberatamente distinto da `LIGHT.nav_bg`, non solo
    # concettualmente "scuro in entrambi i temi".
    nav_bg="#16100b", nav_bg_alt="#221811", nav_border="#362a21",
    nav_text="#ebe4d6", nav_muted="#a89c8a", nav_accent="#eab63e",
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


def accent_glow(accent: str | None, level: int) -> ft.BoxShadow | None:
    """
    Alone colorato attorno a una card "hero" (level≥2), SOLO in tema scuro
    e SOLO se ha un accento esplicito. `elevation()` da sola non basta: un'ombra
    nera è quasi invisibile contro uno sfondo già scuro (`DARK.shadow="#000000"`)
    — qui invece l'oro/l'indaco devono "brillare" come una fonte di luce nel
    grimorio, non limitarsi a essere leggermente più elevati.

    **Perché un'ombra colorata e non uno sfondo più chiaro**: schiarire
    `bgcolor` per "livello" rimetterebbe in discussione ogni contrasto
    testo/icona già calcolato contro `surface`/`surface_alt` invariati.
    Un'ombra colorata non tocca `bgcolor`: il segnale visivo è aggiuntivo,
    non sostitutivo. In tema chiaro l'equivalente è il bordo pieno di
    `card(hero=True)` — un alone dorato su pergamena chiara leggerebbe
    stonato/posterizzato, la silhouette basta.
    """
    p = T()
    if not p.is_dark or level < 2 or not accent:
        return None
    opacity, blur = {2: (0.22, 24), 3: (0.32, 36)}[min(level, 3)]
    return ft.BoxShadow(blur_radius=blur, spread_radius=0,
                         offset=ft.Offset(0, 0), color=_rgba(accent, opacity))


def layered_shadow(level: int, accent: str | None) -> ft.BoxShadow | list[ft.BoxShadow] | None:
    """Combina l'ombra standard con l'eventuale alone colorato — `Container.shadow`
    accetta sia un `BoxShadow` singolo sia una lista (verificato per introspezione,
    `flet==0.86.5`)."""
    base = elevation(level)
    glow = accent_glow(accent, level)
    if glow is None:
        return base
    return [glow, base] if base is not None else [glow]


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


def hero_title(text: str, subtitle_text: str = "", *, color: str | None = None,
               is_mobile: bool = False) -> ft.Control:
    """
    Momento tipografico dominante — UN solo uso per schermata (nome
    personaggio, nome mondo, titolo app). `Size.HERO` (40px) è la taglia più
    grande della scala: prima la scala si fermava a `DISPLAY` (32px) e nessun
    titolo risultava davvero "hero" rispetto al resto.

    `is_mobile` riduce la taglia a `Size.DISPLAY` sotto la soglia mobile —
    va calcolato centralmente (`ui/app.py::_on_page_resize()`) e passato in
    giù, mai un controllo diretto su `page.width` qui (vedi gotcha
    `docs/regole_flet_api.md`: `page.width` è spesso `None` prima del mount).
    """
    p = T()
    kids: list[ft.Control] = [
        ft.Text(text, size=Size.DISPLAY if is_mobile else Size.HERO,
                weight=ft.FontWeight.BOLD, color=color or p.text,
                font_family=Font.DISPLAY),
    ]
    if subtitle_text:
        kids.append(muted(subtitle_text, size=Size.BODY_SM))
    return ft.Column(kids, spacing=Space.XS, tight=True)


# ---------------------------------------------------------------------------
# Primitive
# ---------------------------------------------------------------------------


def _resolve_hero(level: int | None, padding: int | None, radius: int | None,
                   *, hero: bool, density: Literal["relaxed", "dense"]) -> tuple[int, int, int]:
    """Risolve level/padding/radius con i default `hero`/`density` — un
    valore esplicito del chiamante vince sempre sul default derivato."""
    lvl = level if level is not None else (2 if hero else 1)
    pad = padding if padding is not None else (
        Space.XL if hero else (Space.MD if density == "dense" else Space.LG))
    rad = radius if radius is not None else (Radius.LG if hero else Radius.MD)
    return lvl, pad, rad


def surface(content: ft.Control, *, level: int | None = None, padding: int | None = None,
            radius: int | None = None, alt: bool = False,
            expand: bool | None = None, accent: str | None = None,
            hero: bool = False, density: Literal["relaxed", "dense"] = "relaxed") -> ft.Container:
    """Superficie elevata generica — sostituisce i `Container(bgcolor=..., border=...)`.
    `accent` (opzionale) serve solo per l'alone colorato di `accent_glow()` a
    `level>=2` in tema scuro — `bgcolor` resta sempre `surface`/`surface_alt`
    invariati, vedi `accent_glow()` per il perché. `hero=True` è una
    scorciatoia per `level=2, radius=Radius.LG, padding=Space.XL` (l'elemento
    più consultato della schermata — MAX uno per schermata, vedi `card()`).
    `density="dense"` riduce il padding di default (`Space.MD`) per le tab
    dati-intensive; ignorato se `padding`/`hero` sono espliciti."""
    p = T()
    lvl, pad, rad = _resolve_hero(level, padding, radius, hero=hero, density=density)
    return ft.Container(
        content=content,
        bgcolor=p.surface_alt if alt else p.surface,
        padding=pad,
        border_radius=rad,
        shadow=layered_shadow(lvl, accent),
        expand=expand,
    )


def card(content: ft.Control, *, accent: str | None = None, level: int | None = None,
         padding: int | None = None, on_click: Callable[[Any], None] | None = None,
         tooltip: str | None = None, expand: bool | None = None,
         hero: bool = False, density: Literal["relaxed", "dense"] = "relaxed") -> ft.Container:
    """
    Card standard. L'accento è una **barra sottile a sinistra**, non un filetto
    in cima: è il singolo cambiamento che sposta più percezione di modernità
    rispetto al vecchio `fantasy_card()`.

    `hero=True` (MAX una per schermata — l'elemento più consultato, es. HP in
    `combattimento_tab.py`) alza radius/livello/padding e sostituisce la
    barra sinistra con un **bordo pieno** nell'accento: la silhouette da sola
    comunica "questo è diverso" prima ancora di ombra o colore.

    Se `on_click` è passato, la card diventa interattiva (ink + animazione).
    """
    p = T()
    lvl, pad, rad = _resolve_hero(level, padding, None, hero=hero, density=density)
    if hero and accent:
        border = ft.Border.all(1.5, ft.Colors.with_opacity(0.55, accent))
    elif accent:
        border = ft.Border.only(left=ft.BorderSide(3, accent))
    else:
        border = None
    c = ft.Container(
        content=content,
        bgcolor=p.surface,
        padding=pad,
        border_radius=rad,
        shadow=layered_shadow(lvl, accent),
        border=border,
        on_click=on_click,
        tooltip=tooltip,
        ink=bool(on_click),
        animate=ft.Animation(Duration.BASE, CURVE),
        animate_scale=ft.Animation(Duration.FAST, CURVE),
        expand=expand,
    )
    return c


def header_row(title_text: str, accent: str | None = None, *,
               hero: bool = False, trailing: ft.Control | None = None) -> ft.Row:
    """
    Barretta d'accento + etichetta maiuscola spaziata — l'intestazione
    condivisa da `section()` e da `ui/theme.py::section_header()` (68+ call
    site legacy). Un solo posto per cambiare lo stile di TUTTE le
    intestazioni di sezione dell'app, migrate o no a `design.py`.
    """
    p = T()
    bar_w, bar_h = (4, 18) if hero else (3, 14)
    head: list[ft.Control] = [
        ft.Container(width=bar_w, height=bar_h, bgcolor=accent or p.primary_fill,
                     border_radius=Radius.SM),
        ft.Container(width=Space.SM),
        ft.Text(title_text.upper(), size=Size.LABEL, weight=ft.FontWeight.BOLD,
                color=p.text_2, font_family=Font.BODY,
                style=ft.TextStyle(letter_spacing=1.5)),
    ]
    if trailing is not None:
        head.append(ft.Container(expand=True))
        head.append(trailing)
    return ft.Row(head, vertical_alignment=ft.CrossAxisAlignment.CENTER)


def section(title_text: str, content: ft.Control, *,
            accent: str | None = None, trailing: ft.Control | None = None,
            level: int | None = None, hero: bool = False,
            density: Literal["relaxed", "dense"] = "relaxed") -> ft.Container:
    """Sezione con intestazione — sostituisce `section_header()` + Column manuale.
    `hero`/`density`: vedi `surface()`/`card()`."""
    return surface(
        ft.Column(
            [
                header_row(title_text, accent, hero=hero, trailing=trailing),
                ft.Container(height=Space.MD),
                content,
            ],
            spacing=0, tight=True,
        ),
        level=level,
        accent=accent,
        hero=hero,
        density=density,
    )


def asymmetric_row(major: ft.Control, minor: ft.Control, *,
                    ratio: tuple[int, int] = (7, 5),
                    breakpoint: Literal["sm", "md", "lg"] = "md",
                    spacing: int = Space.MD) -> ft.ResponsiveRow:
    """
    Riga a due colonne di peso diverso (audit anti-AI-slop, 2026-08-18) —
    rompe la colonna singola meccanica nei punti dove un contenuto è
    chiaramente primario e l'altro secondario (es. HP grande a sinistra +
    statistiche compresse a destra in `combattimento_tab.py`).

    Usa `ft.ResponsiveRow`/`col=` (valutato lato client), MAI `expand=` su
    una `ft.Row` semplice: dentro un `ft.ListView` (le tab della scheda
    personaggio ereditano da `ScrollMemoryListView`, sottoclasse di
    `ft.ListView`), `expand=True` su un Column figlio di una Row causa un
    crash silenzioso di Flutter (vedi `docs/regole_flet_api.md`, voce
    "EXPAND=True su Column dentro Row dentro ListView"). `ResponsiveRow` usa
    un meccanismo di layout diverso e non è soggetto allo stesso problema —
    già collaudato in questo stesso contesto (tab-in-ListView) da
    `esplorazione_tab.py::_section_skills()`. Sotto la soglia `breakpoint`
    le due colonne tornano impilate a piena larghezza (mobile-safe di
    default, nessuna plumbing `is_mobile` necessaria).
    """
    total = 12
    a, b = ratio
    return ft.ResponsiveRow(
        [
            ft.Container(content=major, col={"xs": total, breakpoint: a}),
            ft.Container(content=minor, col={"xs": total, breakpoint: b}),
        ],
        columns=total, spacing=spacing, run_spacing=spacing,
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


def icon_badge(icon: ft.IconData, *, tone: Tone = "primary", size: int = 36) -> ft.Container:
    """
    Icona in un cerchietto tinto — la "forma-firma" ricorrente del rifacimento
    Arcane Ledger. Nata in `dialog_title()` (unico punto d'uso finora, 101
    varianti prima di questa primitiva) ed estratta qui perché `section()`,
    `empty_state()` e le righe di lista la riusano allo stesso modo:
    trasforma un'icona Material generica in un linguaggio visivo coerente
    senza introdurre una nuova libreria di icone.
    """
    col = tone_color(tone)
    return ft.Container(
        content=ft.Icon(icon, size=round(size * 0.5), color=col),
        width=size, height=size, alignment=ft.Alignment.CENTER,
        bgcolor=ft.Colors.with_opacity(0.12, col),
        border_radius=Radius.PILL,
    )


def dialog_title(text: str, icon: ft.IconData | None = None,
                 tone: Tone = "primary") -> ft.Control:
    """
    Intestazione standard dei dialog: icona in un cerchietto tinto + titolo nel
    font display. Prima ogni dialog costruiva il proprio `ft.Text` con
    dimensione, peso e colore scelti caso per caso (101 varianti).
    """
    p = T()
    kids: list[ft.Control] = []
    if icon is not None:
        kids.append(icon_badge(icon, tone=tone))
        kids.append(ft.Container(width=Space.MD))
    kids.append(ft.Text(text, size=Size.SUBTITLE, weight=ft.FontWeight.BOLD,
                        color=p.text, font_family=Font.DISPLAY,
                        expand=True, no_wrap=False))
    return ft.Row(kids, tight=True, vertical_alignment=ft.CrossAxisAlignment.CENTER)


def generator_dialog_shell(
    title: str,
    icon: ft.IconData | None,
    form: ft.Control,
    result: ft.Control | None,
    actions: list[ft.Control],
    *,
    tone: Tone = "primary",
) -> ft.Control:
    """
    Scheletro condiviso dei dialog "generatore" della Sezione Master (Genera
    Tesoro, Genera NPC, Generatore Trappole, Genera Incontro [Casuale/per
    Ambiente], Genera Oggetto Magico, Artefatti, Malattie e Veleni…): prima
    ognuno ricostruiva a mano la stessa sequenza intestazione → form
    parametri → `ft.Divider` → `card(result_col, accent=T().primary,
    level=2, padding=Space.XL)` → eventuale riga di azioni secondarie
    (Assegna…/Salva nell'archivio/Aggiungi all'inventario) — qui è UN solo
    punto per cambiare la "sensazione di rivelazione" del risultato in tutti
    i generatori insieme (audit anti-AI-slop, rifacimento Arcane Ledger).

    `form` è avvolto in `section("Parametri", form, density="dense")`
    (stessa intestazione a barretta+etichetta di ogni altra sezione
    dell'app, non più un blocco di controlli nudo).

    `result=None` finché il chiamante preferisce non mostrare ancora la card
    "risultato" (es. un dialog a schede dove la scheda generatore non è
    quella attiva). La maggior parte dei generatori esistenti passa invece
    SEMPRE un control con dentro un placeholder testuale iniziale ("Premi
    «Genera»…", mai `None`) proprio per evitare che la card "salti dentro"
    al primo tiro — comportamento preservato passando qui lo stesso
    control, che i generatori continuano ad aggiornare in place
    (`.update()`) esattamente come già fanno.

    `actions` sono le azioni RIGA secondarie sotto il risultato (Assegna…/
    Salva nell'archivio/Aggiungi all'inventario) — NON i pulsanti di
    `AlertDialog.actions` (Chiudi/Annulla), che restano invariati a carico
    del chiamante. Vengono avvolte con lo stesso schema di
    `ui/widgets.py::wrap_dialog_actions()` (import differito qui sotto per
    evitare un'importazione circolare: `ui/widgets.py` importa già
    `ui.design` a livello di modulo, quindi `design.py` non può importare
    `ui.widgets` allo stesso livello) — una fila di 2-3 pulsanti va a capo
    su un dialog stretto invece di uscire dal bordo.

    Non imposta `width`/`height`/`scroll`: restano a carico del chiamante,
    che avvolge il control restituito in un `ft.Column(scroll=ft.ScrollMode.
    AUTO, width=responsive_dialog_width(page, N), height=H, tight=True)` —
    questa funzione non riceve `page`, quindi non può calcolare la
    larghezza responsive da sola (vedi `ui/widgets.py::
    responsive_dialog_width()`).
    """
    p = T()
    accent = tone_color(tone)
    kids: list[ft.Control] = [
        dialog_title(title, icon, tone),
        ft.Container(height=Space.SM),
        section("Parametri", form, density="dense"),
    ]
    if result is not None:
        kids.append(ft.Divider(height=1, color=p.border))
        kids.append(card(result, accent=accent, level=2, padding=Space.XL))
    if actions:
        from ui.widgets import wrap_dialog_actions  # import differito, vedi docstring

        kids.append(ft.Divider(height=1, color=p.border))
        kids.extend(wrap_dialog_actions(actions))
    return ft.Column(kids, spacing=Space.MD, tight=True)


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
                action: ft.Control | None = None, *, tone: Tone = "neutral") -> ft.Container:
    """Stato vuoto uniforme — l'app ne aveva ~12 scritti a mano tutti diversi."""
    p = T()
    kids: list[ft.Control] = [
        icon_badge(icon, tone=tone, size=64),
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
