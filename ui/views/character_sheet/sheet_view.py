"""
Container principale della scheda personaggio.

Struttura:
    MiniStatBar  — 6 caratteristiche fisse in cima (cliccabili per modifica)
    TabBar       — Profilo | Combattimento | Esplorazione | Inventario | Diario
    Content area — contenuto del tab attivo

Input:  Character + list[CharacterProficiency]
Output: ft.Column che occupa tutta l'area disponibile
"""

import flet as ft
import logging
from typing import cast
from config.settings import *
from data.models import Character, CharacterProficiency
from ui.theme import show_error_dialog
import data.repositories.character_repo as character_repo
from ui import design
from ui.widgets import wrap_dialog_actions
import core.character_stats as cs
from ui.components.roll_panel import show_roll

logger = logging.getLogger(__name__)

SHEET_TABS = [
    {"key": "profilo",       "label": "Profilo",       "icon": ft.Icons.PERSON_OUTLINE},
    {"key": "combattimento", "label": "Combattimento", "icon": ft.Icons.SHIELD_OUTLINED},
    {"key": "esplorazione",  "label": "Esplorazione",  "icon": ft.Icons.EXPLORE_OUTLINED},
    {"key": "inventario",    "label": "Inventario",    "icon": ft.Icons.BACKPACK_OUTLINED},
    {"key": "diario",        "label": "Diario",        "icon": ft.Icons.MENU_BOOK_OUTLINED},
]


class SheetView(ft.Column):
    """
    Vista principale della scheda personaggio.
    Gestisce la mini stat bar fissa e il routing tra i 5 tab.
    """

    def __init__(self, character: Character, proficiencies: list[CharacterProficiency],
                 is_mobile: bool = False):
        """
        `is_mobile` (2026-08-06): decide lo stile della tab bar — vedi il
        docstring di `_build_header_and_tabs()`. Passato da `DnDApp` con lo
        stesso breakpoint (`_MOBILE_BP = 600`, `ui/app.py`) già usato per
        scegliere tra sidebar e bottom nav — nessun nuovo concetto di
        "mobile", si riusa quello che l'app ha già. Default `False` per
        restare compatibile con i costruttori esistenti (test, chiamate
        legacy) che non lo passano.
        """
        super().__init__(expand=True, spacing=0)
        self.character = character
        self.proficiencies = proficiencies
        self.active_tab = "profilo"
        self._tab_buttons: dict[str, ft.Container] = {}
        self._compact_tabs = is_mobile
        self._page: ft.Page | None = None
        self._stat_bar_container: ft.Container | None = None
        self._header_container: ft.Container | None = None
        self._build()

    def did_mount(self):
        self._page = cast(ft.Page, self.page)

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self):
        self._stat_bar_container = self._build_stat_bar()
        self._header_container = self._build_header_and_tabs()
        self.content_container = ft.Container(
            expand=True,
            content=self._get_tab_content("profilo"),
        )

        self.controls = [
            self._stat_bar_container,
            self._header_container,
            self.content_container,
        ]

    # ------------------------------------------------------------------
    # Mini stat bar — cliccabile per editare le caratteristiche
    # ------------------------------------------------------------------

    def _build_stat_bar(self) -> ft.Container:
        """
        Barra flottante delle caratteristiche (Fase E.4 del restyle).

        Prima: sei riquadri bianchi identici con l'etichetta piccola e il
        modificatore come semplice testo blu. Ora la barra è un pannello elevato
        con i riquadri incassati (`surface_alt`), il punteggio in cifre
        tabellari e il modificatore in un chip d'accento — quello che il
        giocatore legge più spesso è anche l'elemento con più peso visivo.
        """
        p = design.T()
        boxes = []
        for abbr, key in zip(ABILITY_ABBR, ABILITY_KEYS):
            score = getattr(self.character, f"{key}_score")
            mod = get_modifier(score)
            mod_str = f"+{mod}" if mod >= 0 else str(mod)
            boxes.append(
                ft.Container(
                    content=ft.Column(
                        [
                            # Icona matita (2026-07-24, fix affordance "nulla di
                            # nascosto": prima solo tooltip+bordo, nessuna icona
                            # visibile a colpo d'occhio come le altre sezioni
                            # editabili dell'app — stessa convenzione "✎" già
                            # usata ovunque)
                            ft.Row(
                                [
                                    ft.Text(abbr, size=design.Size.LABEL,
                                            color=p.text_3,
                                            weight=ft.FontWeight.BOLD,
                                            font_family=design.Font.BODY,
                                            style=ft.TextStyle(letter_spacing=0.8)),
                                    ft.Icon(ft.Icons.EDIT, size=9, color=p.text_3),
                                ],
                                spacing=2, tight=True,
                                alignment=ft.MainAxisAlignment.CENTER,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            ft.Text(str(score), size=20, color=p.text,
                                    weight=ft.FontWeight.BOLD,
                                    text_align=ft.TextAlign.CENTER,
                                    font_family=design.Font.MONO),
                            # Il chip del modificatore è il pulsante di tiro
                            # (Fase 4, feature 1): due affordance distinte nello
                            # stesso riquadro — la matita in alto modifica il
                            # punteggio, il chip qui sotto tira la prova di
                            # caratteristica. L'icona del dado lo rende esplicito.
                            ft.Container(
                                content=ft.Row(
                                    [
                                        ft.Text(mod_str, size=design.Size.LABEL,
                                                color=p.magic,
                                                weight=ft.FontWeight.BOLD,
                                                font_family=design.Font.MONO,
                                                text_align=ft.TextAlign.CENTER),
                                        ft.Icon(ft.Icons.CASINO_OUTLINED, size=10,
                                                color=p.magic),
                                    ],
                                    spacing=3, tight=True,
                                    alignment=ft.MainAxisAlignment.CENTER,
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                ),
                                bgcolor=ft.Colors.with_opacity(0.12, p.magic),
                                border_radius=design.Radius.PILL,
                                padding=ft.Padding.symmetric(horizontal=8, vertical=1),
                                on_click=(lambda e, k=key: show_roll(
                                    self._page,
                                    cs.ability_check_roll(self.character, k))),
                                ink=True,
                                tooltip=f"Tira una prova di {cs.ability_label(key)}",
                            ),
                        ],
                        spacing=2,
                        tight=True,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.Padding.symmetric(vertical=design.Space.SM, horizontal=6),
                    bgcolor=p.surface_alt,
                    border_radius=design.Radius.MD,
                    expand=True,
                    on_click=lambda e: self._open_ability_score_dialog(),
                    ink=True,
                    animate_scale=ft.Animation(design.Duration.FAST, design.CURVE),
                    tooltip="Clicca per modificare le caratteristiche",
                )
            )

        return ft.Container(
            content=ft.Row(boxes, spacing=design.Space.SM, expand=True),
            padding=ft.Padding.symmetric(horizontal=design.Space.MD,
                                         vertical=design.Space.MD),
            bgcolor=p.surface,
            shadow=design.elevation(2),
            border_radius=ft.BorderRadius.only(bottom_left=design.Radius.LG,
                                               bottom_right=design.Radius.LG),
        )

    # ------------------------------------------------------------------
    # Header personaggio + tab bar
    # ------------------------------------------------------------------

    def _build_header_and_tabs(self) -> ft.Container:
        c = self.character
        pb = char_prof_bonus(c)
        is_override = (c.proficiency_bonus_override or 0) > 0

        # Testo bonus competenza — cliccabile per override
        # Icona matita sempre presente (2026-07-24, fix affordance "nulla di
        # nascosto"): prima l'unico indizio che fosse cliccabile era il
        # tooltip (visibile solo passandoci sopra) più il "✎" mostrato SOLO
        # quando già in override — un personaggio senza override non aveva
        # alcun indizio visivo.
        pb_label = ft.Row(
            [
                ft.Text(
                    f"+{pb} comp.",
                    size=11,
                    color=design.T().magic if is_override else design.T().text_2,
                    weight=ft.FontWeight.BOLD if is_override else ft.FontWeight.NORMAL,
                ),
                ft.Icon(
                    ft.Icons.EDIT, size=10,
                    color=design.T().magic if is_override else design.T().text_3,
                ),
            ],
            spacing=3, tight=True,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        pb_btn = ft.Container(
            content=pb_label,
            on_click=lambda e: self._open_prof_bonus_dialog(),
            ink=True,
            border_radius=design.Radius.SM,
            padding=ft.Padding.symmetric(horizontal=4, vertical=2),
            tooltip="Clicca per modificare il bonus competenza",
        )

        name_row = ft.Row(
            [
                ft.Text(c.name, size=18, weight=ft.FontWeight.BOLD,
                        color=design.T().text, font_family=design.Font.DISPLAY,
                        no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS, expand=True),
                pb_btn,
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        # Chip invece di una riga di testo con i "•": stesso linguaggio visivo
        # delle card della Home, e i tre dati si distinguono a colpo d'occhio.
        chips: list[ft.Control] = [
            design.chip(f"Lv. {c.level}", "primary"),
            design.chip(c.class_name + (f" · {c.subclass}" if c.subclass else ""), "magic"),
            design.chip(c.race + (f" · {c.subrace}" if c.subrace else ""), "neutral"),
        ]
        subtitle = ft.Row(chips, spacing=design.Space.XS, wrap=True)

        # Tab buttons
        tab_row = []
        self._tab_buttons = {}
        for tab in SHEET_TABS:
            btn = self._make_tab_button(tab["key"], tab["label"], tab["icon"])
            self._tab_buttons[tab["key"]] = btn
            tab_row.append(btn)

        p = design.T()
        return ft.Container(
            content=ft.Column(
                [
                    ft.Container(
                        content=ft.Column([name_row, subtitle],
                                          spacing=design.Space.SM),
                        padding=ft.Padding.only(left=design.Space.LG,
                                                right=design.Space.LG,
                                                top=design.Space.MD,
                                                bottom=design.Space.MD),
                    ),
                    # Controllo segmentato (pillole) invece dei tab sottolineati.
                    #
                    # STORIA (per chi legge il changelog — tre round nella
                    # stessa giornata, 2026-08-06):
                    # 1) `wrap=True` + pillole senza `expand`: le pillole in
                    #    eccesso finivano su una riga in più a piena
                    #    larghezza ("si prende tutto lo schermo").
                    # 2) `scroll=ft.ScrollMode.AUTO` al posto di `wrap=True`:
                    #    altezza fissa, ma lo sfondo `surface_alt` che dava
                    #    l'aspetto di "pista" si allargava ben oltre le
                    #    pillole vere (un `SingleChildScrollView` orizzontale
                    #    non si restringe mai al contenuto — comportamento
                    #    noto di Flutter). Tolto lo sfondo dall'involucro,
                    #    lasciato solo sulla singola pillola attiva.
                    # 3) Lo scroll di per sé restava comunque sbagliato:
                    #    Davide ha fatto notare che, restringendo la
                    #    finestra, le pillole "vengono tagliate o
                    #    scompaiono" — in contrasto con la preferenza già
                    #    nota di questo progetto per un'interfaccia sempre
                    #    visibile, mai azioni nascoste dietro uno scroll non
                    #    scoperto. FIX DEFINITIVO (qui): niente più scroll
                    #    NÉ wrap multi-riga — la barra ora è DAVVERO
                    #    responsive, non solo "meno peggio". Sotto il
                    #    breakpoint mobile dell'app (`is_mobile`, passato da
                    #    `DnDApp` con lo stesso `_MOBILE_BP = 600` di
                    #    `ui/app.py`), ogni pillola mostra SOLO l'icona
                    #    (tooltip con l'etichetta completa, sempre
                    #    raggiungibile) — 5 pillole icona-sola stanno
                    #    comodamente su una riga anche a 360-375px, la
                    #    larghezza minima comune di uno smartphone. Sopra il
                    #    breakpoint, icona + etichetta come prima. `scroll=
                    #    ft.ScrollMode.AUTO` resta solo come rete di
                    #    sicurezza per casi patologici (font di sistema
                    #    enormi, finestra sotto i 360px), non più come
                    #    meccanismo primario.
                    ft.Container(
                        content=ft.Row(tab_row, spacing=design.Space.XS,
                                       scroll=ft.ScrollMode.AUTO),
                        margin=ft.Margin.only(left=design.Space.MD,
                                              right=design.Space.MD,
                                              bottom=design.Space.MD),
                    ),
                ],
                spacing=0,
            ),
            bgcolor=p.surface,
            shadow=design.elevation(1),
        )

    def _style_tab_button(self, btn: ft.Container, active: bool) -> None:
        """Stile della pillola di tab — usato sia in costruzione sia al cambio tab.

        `p.surface_alt` per la pillola attiva, NON `p.surface` (2026-08-06,
        fix dell'"alone allungato"): l'header che contiene questa barra ha
        già `bgcolor=p.surface` (vedi `_build_header_and_tabs()`) — da
        quando l'involucro esterno beige è stato tolto, una pillola attiva
        con `bgcolor=p.surface` sarebbe risultata invisibile (bianco su
        bianco). `surface_alt` è lo stesso colore che prima dava lo sfondo
        all'intera barra: qui identifica solo la pillola selezionata,
        risultato visivo pressoché identico a prima ma senza il contenitore
        che si allargava oltre il contenuto.

        `btn.data` porta i riferimenti a icona/testo (impostati in
        `_make_tab_button()`) invece di leggere `btn.content` direttamente
        — necessario da quando la pillola può contenere solo un'icona
        (modalità compatta, `self._compact_tabs`), non più sempre un
        `ft.Text` isolato.
        """
        p = design.T()
        refs = cast(dict, btn.data)
        icon_ctrl = cast(ft.Icon, refs["icon"])
        text_ctrl = cast("ft.Text | None", refs["text"])
        color = p.primary if active else p.text_2
        icon_ctrl.color = color
        if text_ctrl is not None:
            text_ctrl.color = color
            text_ctrl.weight = ft.FontWeight.BOLD if active else ft.FontWeight.W_500
        btn.bgcolor = p.surface_alt if active else "transparent"
        btn.shadow = design.elevation(1) if active else None

    def _make_tab_button(self, key: str, label: str, icon: ft.IconData) -> ft.Container:
        """
        Pillola di tab — icona sempre presente, etichetta testuale SOLO se
        `self._compact_tabs` è `False` (2026-08-06, fix definitivo della
        tab bar — vedi lo storico nel commento di `_build_header_and_tabs()`).
        In modalità compatta l'etichetta completa resta comunque
        raggiungibile via `tooltip`, non è mai persa, solo non sempre
        visibile a colpo d'occhio: nessuna voce viene nascosta o rimossa
        dal controllo, tutte e 5 restano cliccabili sulla stessa riga.

        Niente `expand=True`: il Container si dimensiona sul contenuto,
        com'è già `design.pill()` — il genitore è una Row (con `scroll=
        ft.ScrollMode.AUTO` come sola rete di sicurezza, vedi sopra): ogni
        pillola deve restare larga quanto il proprio contenuto.
        """
        icon_ctrl = ft.Icon(icon, size=15)
        row_children: list[ft.Control] = [icon_ctrl]
        text_ctrl: ft.Text | None = None
        if not self._compact_tabs:
            text_ctrl = ft.Text(
                label,
                size=design.Size.LABEL + 1,
                text_align=ft.TextAlign.CENTER,
                font_family=design.Font.BODY,
                no_wrap=True,
                overflow=ft.TextOverflow.ELLIPSIS,
            )
            row_children.append(ft.Container(width=6))
            row_children.append(text_ctrl)

        btn = ft.Container(
            content=ft.Row(
                row_children, spacing=0, tight=True,
                alignment=ft.MainAxisAlignment.CENTER,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(
                horizontal=design.Space.SM if self._compact_tabs else design.Space.MD,
                vertical=design.Space.SM,
            ),
            border_radius=design.Radius.PILL,
            on_click=lambda e, k=key: self._switch_tab(k),
            ink=True,
            alignment=ft.Alignment.CENTER,
            animate=ft.Animation(design.Duration.BASE, design.CURVE),
            tooltip=label if self._compact_tabs else None,
        )
        btn.data = {"icon": icon_ctrl, "text": text_ctrl}
        self._style_tab_button(btn, key == self.active_tab)
        return btn

    # ------------------------------------------------------------------
    # Dialog — modifica caratteristiche
    # ------------------------------------------------------------------

    def _open_ability_score_dialog(self):
        page = self._page
        if page is None:
            return
        c = self.character

        fields: dict[str, ft.TextField] = {}
        for key, name, abbr in zip(ABILITY_KEYS, ABILITY_SCORES, ABILITY_ABBR):
            score = getattr(c, f"{key}_score", 10)
            fields[key] = ft.TextField(
                label=f"{name} ({abbr})",
                value=str(score),
                keyboard_type=ft.KeyboardType.NUMBER,
                text_style=ft.TextStyle(size=13, color=design.T().text),
                border_color=design.T().border,
                focused_border_color=design.T().magic,
                bgcolor=design.T().surface,
                label_style=ft.TextStyle(color=design.T().text_2),
                expand=True,
                border_radius=design.field_style()['border_radius'])

        error_text = ft.Text("", size=11, color=design.T().primary)

        def on_save(ev):
            if page is None:
                return
            new_vals: dict[str, int] = {}
            for key in ABILITY_KEYS:
                try:
                    val = int((fields[key].value or "").strip())
                    if not (1 <= val <= 30):
                        raise ValueError
                    new_vals[key] = val
                except ValueError:
                    idx = ABILITY_KEYS.index(key)
                    error_text.value = (
                        f"Valore non valido per {ABILITY_SCORES[idx]} "
                        f"({ABILITY_ABBR[idx]}) — inserire un numero tra 1 e 30"
                    )
                    error_text.update()
                    return
            for key, val in new_vals.items():
                setattr(c, f"{key}_score", val)
            if not character_repo.update(c):
                show_error_dialog(page)
                return
            page.pop_dialog()
            self._refresh_all()

        dlg = ft.AlertDialog(
            title=design.dialog_title("Modifica Caratteristiche"),
            content=ft.Column(
                [
                    ft.Text(
                        "Valori ammessi: 1–30  (house rules: nessun limite a 20)",
                        size=11, color=design.T().text_3,
                    ),
                    ft.Container(height=4),
                    ft.Row([fields["str"], fields["dex"], fields["con"]], spacing=10),
                    ft.Row([fields["int"], fields["wis"], fields["cha"]], spacing=10),
                    error_text,
                ],
                spacing=10,
            ),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla",
                              on_click=lambda ev: page.pop_dialog() if page else None),
                ft.ElevatedButton(
                    "Salva",
                    on_click=on_save,
                    style=ft.ButtonStyle(
                        bgcolor=design.T().primary, color=design.T().on_primary,
                    ),
                ),
            ]),
        )
        page.show_dialog(dlg)

    # ------------------------------------------------------------------
    # Dialog — override bonus competenza
    # ------------------------------------------------------------------

    def _open_prof_bonus_dialog(self):
        page = self._page
        if page is None:
            return
        c = self.character
        standard_pb = get_proficiency_bonus(c.level)
        current_override = c.proficiency_bonus_override or 0

        tf = ft.TextField(
            label="Bonus competenza personalizzato",
            value=str(current_override) if current_override > 0 else "",
            hint_text=f"Standard PHB: +{standard_pb}",
            keyboard_type=ft.KeyboardType.NUMBER,
            text_style=ft.TextStyle(size=13, color=design.T().text),
            border_color=design.T().border,
            focused_border_color=design.T().magic,
            bgcolor=design.T().surface,
            label_style=ft.TextStyle(color=design.T().text_2),
            width=280,
            border_radius=design.field_style()['border_radius'])
        error_text = ft.Text("", size=11, color=design.T().primary)

        def on_save(ev):
            if page is None:
                return
            raw = (tf.value or "").strip()
            if raw == "":
                # Reset a standard PHB
                c.proficiency_bonus_override = 0
            else:
                try:
                    val = int(raw)
                    if not (1 <= val <= 20):
                        raise ValueError
                    c.proficiency_bonus_override = val
                except ValueError:
                    error_text.value = "Inserire un numero tra 1 e 20 (o lasciare vuoto per standard PHB)"
                    error_text.update()
                    return
            if not character_repo.update(c):
                show_error_dialog(page)
                return
            page.pop_dialog()
            self._refresh_all()

        def on_reset_phb(ev):
            if page is None:
                return
            c.proficiency_bonus_override = 0
            if not character_repo.update(c):
                show_error_dialog(page)
                return
            page.pop_dialog()
            self._refresh_all()

        dlg = ft.AlertDialog(
            title=design.dialog_title("Bonus Competenza"),
            content=ft.Column(
                [
                    ft.Text(
                        f"Standard PHB per Lv.{c.level}: +{standard_pb}",
                        size=12, color=design.T().text_2,
                    ),
                    ft.Text(
                        "Lascia vuoto per usare la tabella PHB standard. "
                        "Imposta un valore diverso per house rules.",
                        size=11, color=design.T().text_3,
                    ),
                    ft.Container(height=4),
                    tf,
                    error_text,
                ],
                spacing=8,
            ),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla",
                              on_click=lambda ev: page.pop_dialog() if page else None),
                ft.TextButton(
                    "Reset PHB",
                    on_click=on_reset_phb,
                    style=ft.ButtonStyle(color=design.T().text_3),
                ),
                ft.ElevatedButton(
                    "Salva",
                    on_click=on_save,
                    style=ft.ButtonStyle(
                        bgcolor=design.T().primary, color=design.T().on_primary,
                    ),
                ),
            ]),
        )
        page.show_dialog(dlg)

    # ------------------------------------------------------------------
    # Refresh globale (dopo modifica caratteristiche o bonus competenza)
    # ------------------------------------------------------------------

    def _refresh_bar_and_header(self):
        """
        Ricarica il personaggio dal DB e aggiorna SOLO stat bar e header.
        Chiamato dai tab dopo il loro self-refresh, per tenere la top bar
        sincronizzata senza ricostruire il contenuto del tab.
        """
        updated = character_repo.get_by_id(self.character.id)
        if updated:
            self.character = updated
        self.proficiencies = character_repo.get_proficiencies(self.character.id)

        new_bar = self._build_stat_bar()
        new_hdr = self._build_header_and_tabs()
        self.controls[0] = new_bar
        self.controls[1] = new_hdr
        self._stat_bar_container = new_bar
        self._header_container = new_hdr

        try:
            self.update()
        except RuntimeError:
            pass

    def _refresh_all(self):
        """
        Ricarica il personaggio dal DB, aggiorna la stat bar, l'header
        e ricostruisce il tab corrente (che mostra valori derivati).
        Usato dai dialog interni a SheetView (modifica caratteristiche,
        bonus competenza).
        """
        self._refresh_bar_and_header()

        # Ricostruisce il tab corrente
        self.content_container.content = self._get_tab_content(self.active_tab)

        try:
            self.update()
        except RuntimeError:
            pass

    # ------------------------------------------------------------------
    # Navigazione tra tab
    # ------------------------------------------------------------------

    def _switch_tab(self, key: str):
        if key == self.active_tab:
            return
        self.active_tab = key

        # Aggiorna stile bottoni
        for k, btn in self._tab_buttons.items():
            self._style_tab_button(btn, k == key)

        self.content_container.content = self._get_tab_content(key)
        self.update()

    # ------------------------------------------------------------------
    # Contenuto tab
    # ------------------------------------------------------------------

    def _get_tab_content(self, key: str) -> ft.Control:
        cb = self._refresh_bar_and_header
        if key == "profilo":
            from ui.views.character_sheet.profilo_tab import ProfiloTab
            return ProfiloTab(self.character, self.proficiencies, on_refresh=cb)
        if key == "combattimento":
            from ui.views.character_sheet.combattimento_tab import CombattimentoTab
            return CombattimentoTab(self.character, on_refresh=cb)
        if key == "esplorazione":
            from ui.views.character_sheet.esplorazione_tab import EsplorazioneTab
            return EsplorazioneTab(self.character, on_refresh=cb)
        if key == "inventario":
            from ui.views.character_sheet.inventario_tab import InventarioTab
            return InventarioTab(self.character, on_refresh=cb)
        if key == "diario":
            from ui.views.character_sheet.diario_tab import DiarioTab
            return DiarioTab(self.character, on_refresh=cb)
        return self._placeholder_tab(key)

    def _placeholder_tab(self, key: str) -> ft.Container:
        labels = {
            "combattimento": ("Combattimento", ft.Icons.SHIELD),
            "esplorazione":  ("Esplorazione",  ft.Icons.EXPLORE),
            "inventario":    ("Inventario",     ft.Icons.BACKPACK),
            "diario":        ("Diario",         ft.Icons.MENU_BOOK),
        }
        label, icon = labels.get(key, (key, ft.Icons.BUILD))
        return ft.Container(
            expand=True,
            content=ft.Column(
                [
                    ft.Icon(icon, size=52, color=design.T().border),
                    ft.Container(height=12),
                    ft.Text(label, size=20, color=design.T().text_3),
                    ft.Container(height=8),
                    ft.Text("In sviluppo...", size=13, color=design.T().text_3),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                expand=True,
            ),
        )
