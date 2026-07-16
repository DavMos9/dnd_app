"""
Tab Profilo della scheda personaggio.

Struttura (ListView scrollabile):
  - Header foto + XP + bottone Level Up
  - Anagrafica  (classe, razza, background, allineamento, XP, livello)
  - Tratti Razziali  (velocità, scurovisione, tratti speciali)
  - Dettagli Fisici  (età, altezza, peso, occhi, carnagione, capelli)
  - Personalità  (tratti, ideali, legami, difetti)
  - Storia  (background narrativo, alleanze, tratti extra)
  - Competenze  (tiri salvezza + tutte le 18 abilità con indicatore pieno/vuoto)

Usa ft.ListView (non Column scroll=AUTO) per evitare bug height in Flet 0.85.3.
"""

import base64
import threading
from typing import Any, Callable, cast
import flet as ft
import logging
from config.settings import *
from data.models import Character, CharacterProficiency
import data.repositories.character_repo as character_repo
from ui.image_library import show_image_library_picker
from ui.theme import section_header, muted_text, show_error_dialog
from ui.widgets import (
    dropdown_with_info, make_spell_describe, format_spell_body,
    make_feat_describe, make_invocation_describe, make_named_option_describe,
)
from data.game_data.game_data_loader import GameDataLoader
from core.level_manager import get_level_up_steps, estimate_hp_loss, StepType

_loader = GameDataLoader()

logger = logging.getLogger(__name__)


def _data_uri(b64: str) -> str:
    """
    Costruisce un data URI dal base64, rilevando il formato dai magic bytes.
    Usato per mostrare immagini con ft.Image(src=...) in Flet 0.85.3
    (src_base64 non è supportato in questa versione).
    """
    try:
        import base64 as _b64
        header = _b64.b64decode(b64[:16] + "==")
        if header[:3] == b"\xff\xd8\xff":
            mime = "image/jpeg"
        elif header[:8] == b"\x89PNG\r\n\x1a\n":
            mime = "image/png"
        elif header[:4] == b"GIF8":
            mime = "image/gif"
        elif header[:4] == b"RIFF" and len(header) >= 12 and header[8:12] == b"WEBP":
            mime = "image/webp"
        else:
            mime = "image/jpeg"
    except Exception:
        mime = "image/jpeg"
    return f"data:{mime};base64,{b64}"

def _is_asi_level(class_name: str, level: int) -> bool:
    """
    Livelli ASI per classe — letti da GameDataLoader.get_asi_levels(), che
    legge il campo "asi_levels" dal JSON di classe per le 2 eccezioni
    (Guerriero, Ladro) e la progressione standard PHB {4,8,12,16,19} per
    tutte le altre. Prima del 2026-07-10 questa era una copia locale
    duplicata di ASI_LEVELS/ASI_LEVELS_DEFAULT (config/settings.py) — stesso
    dato scritto a mano in due posti indipendenti, stesso tipo di rischio già
    eliminato altrove nel progetto (RACE_DATA, CLASS_FEATURES, ecc.).
    """
    return level in _loader.get_asi_levels(class_name)


class ProfiloTab(ft.ListView):
    """
    Tab profilo: lista scrollabile di sezioni con edit inline.
    Eredita da ft.ListView per garantire scroll corretto in Flet 0.85.3.
    """

    def __init__(
        self,
        character: Character,
        proficiencies: list[CharacterProficiency],
        on_refresh: "Callable[[], None] | None" = None,
    ):
        super().__init__(expand=True, spacing=12, padding=16)
        self.character = character
        self.proficiencies = proficiencies
        self._on_refresh = on_refresh
        self._page: ft.Page | None = None

        self._xp_field: ft.TextField | None = None
        self._level_up_btn: ft.Control | None = None
        self._level_down_btn: ft.Control | None = None

        # FilePicker persistente (foto profilo) — vedi did_mount() e
        # _pick_photo_mobile() per il motivo per cui NON viene più creato
        # al volo dentro il click handler.
        self._file_picker: ft.FilePicker | None = None

        self._build()

    # ------------------------------------------------------------------
    # Build principale
    # ------------------------------------------------------------------

    def _build(self):
        c = self.character
        prof_bonus = char_prof_bonus(c)

        skill_map: dict[str, bool] = {}
        save_map: dict[str, bool] = {}
        for p in self.proficiencies:
            if p.proficiency_type == "skill":
                skill_map[p.name] = p.is_expert
            elif p.proficiency_type == "save":
                save_map[p.name] = p.is_expert

        # IMPORTANTE: modificare self.controls IN-PLACE (mai self.controls = [...]).
        # In Flet 0.85.3 la riassegnazione diretta rimpiazza la ControlsList interna
        # che Flutter usa per il rendering → schermata bianca (vedi CLAUDE.md).
        self.controls.clear()
        self.controls.append(self._build_photo_header(c))
        self.controls.append(section_header("Anagrafica"))
        self.controls.append(self._build_anagrafica(c))
        self.controls.append(section_header("Tratti Razziali"))
        self.controls.append(self._build_razza(c))
        self.controls.append(section_header("Dettagli Fisici"))
        self.controls.append(self._build_fisico(c))
        self.controls.append(section_header("Personalità"))
        self.controls.append(self._build_personalita(c))
        self.controls.append(section_header("Storia"))
        self.controls.append(self._build_storia(c))
        self.controls.append(section_header("Competenze"))
        self.controls.append(self._build_competenze(c, prof_bonus, skill_map, save_map))
        self.controls.append(section_header("Talenti"))
        self.controls.append(self._build_talenti(c))

    def did_mount(self):
        self._page = cast(ft.Page, self.page)

        # Registra il FilePicker SUBITO al mount, non al click — MA SOLO su
        # mobile (Android/iOS). Storia del fix, in quattro tempi, tutti
        # confermati con Davide:
        # 1) Teoria iniziale (poi confermata insufficiente): puro problema
        #    di timing/handshake lato client (bug "noto" upstream
        #    flet-dev/flet#6250/#6251) — fix tentato: registrare prima.
        # 2) Davide ha segnalato che l'errore compariva "all'istante senza
        #    nemmeno cliccare sull'immagine" — sintomo incompatibile con una
        #    race di timing. Nuova ipotesi: serviva il vero upload
        #    client→server (page.get_upload_url() + FilePicker.upload()),
        #    implementato di conseguenza.
        # 3) Ricerca diretta sulla issue tracker upstream di Flet (confermata
        #    con Davide) ha rivelato che il problema NON è affatto risolvibile
        #    lato applicazione in modalità WEB: flet-dev/flet#6040/#6250/#6251
        #    documentano che, a partire da Flet ^0.80.1 (versione attuale del
        #    progetto: 0.85.3), i controlli "Service" come FilePicker in
        #    modalità web (server-side rendering, es. Docker) sono
        #    strutturalmente rotti — il solo AGGIUNGERE FilePicker a
        #    page.overlay, indipendentemente da QUANDO lo si fa, produce
        #    "Unknown control" o TimeoutException. Fix applicato allora:
        #    `not self._page.web` — registra ovunque TRANNE che sul web.
        # 4) (2026-07-16) Davide ha segnalato lo STESSO identico banner rosso
        #    "Unknown control: FilePicker" avviando l'app nativa da terminale
        #    (desktop macOS, non web) — la condizione `not self._page.web`
        #    del punto 3 è insufficiente: include anche il desktop, che
        #    secondo la primissima regola scritta in cima a questo stesso
        #    CLAUDE.md ("ft.FilePicker su DESKTOP Flet 0.85.3 → 'Unknown
        #    control: FilePicker' — NON usare") non supporta il controllo
        #    ESATTAMENTE come il web, per lo stesso motivo pratico (il solo
        #    registrarlo in page.overlay basta a far comparire il banner,
        #    prima ancora di qualunque click) — semplicemente non era mai
        #    stato notato prima perché nessuno aveva ancora testato un lancio
        #    nativo da terminale dopo l'introduzione di questo did_mount().
        #    Il resto del codice (_pick_photo() sotto, `_pick_photo_desktop()`)
        #    già instrada correttamente il desktop su un subprocess nativo
        #    (osascript/PowerShell/zenity) e non ha MAI avuto bisogno di
        #    FilePicker — solo did_mount() lo registrava comunque, senza
        #    motivo, introducendo il bug. Fix definitivo: restringere la
        #    registrazione ai soli platform Android/iOS (stessa condizione
        #    già usata da _pick_photo() per instradare la UI), mai su
        #    desktop o web.
        if (
            self._file_picker is None
            and self._page is not None
            and self._page.platform in (ft.PagePlatform.ANDROID, ft.PagePlatform.IOS)
        ):
            self._file_picker = ft.FilePicker()
            self._file_picker.on_result = self._on_mobile_file_picked  # type: ignore[assignment]
            self._page.overlay.append(self._file_picker)
            try:
                self._page.update()  # type: ignore[unused-coroutine]
            except RuntimeError:
                pass

    # ------------------------------------------------------------------
    # Header foto + XP + Level Up
    # ------------------------------------------------------------------

    def _build_photo_header(self, c: Character) -> ft.Container:
        # Mostra image_data (base64 dal DB) oppure image_path (legacy) oppure placeholder
        if c.image_data:
            avatar_content = ft.Image(src=_data_uri(c.image_data), fit=ft.BoxFit.COVER)
        elif c.image_path:
            avatar_content = ft.Image(src=c.image_path, fit=ft.BoxFit.COVER)
        else:
            avatar_content = ft.Icon(ft.Icons.PERSON, size=38, color=COLOR_NAV_MUTED)

        avatar = ft.Container(
            content=avatar_content,
            width=80, height=80,
            border_radius=40,
            bgcolor=COLOR_NAV_BG if not (c.image_data or c.image_path) else None,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            alignment=ft.Alignment.CENTER,
            on_click=lambda e: self._pick_photo(),
            tooltip="Clicca per cambiare foto",
        )

        pb = get_proficiency_bonus(c.level)

        self._xp_field = ft.TextField(
            value=str(c.xp or 0),
            width=80,
            height=32,
            text_align=ft.TextAlign.CENTER,
            text_style=ft.TextStyle(size=13, color=COLOR_TEXT_PRIMARY),
            border_color=COLOR_BORDER,
            focused_border_color=COLOR_ACCENT_BLUE,
            bgcolor=COLOR_BG_CARD,
            content_padding=ft.Padding.symmetric(horizontal=6, vertical=4),
            keyboard_type=ft.KeyboardType.NUMBER,
        )

        # Pulsanti Livello Su/Giù — dimensionati tre volte lo stesso giorno
        # su feedback diretto di Davide (2026-07-16):
        # 1) Prima erano due IconButton da 22px (sole frecce monocolore,
        #    senza testo), infilati nella riga "Lv.N/Comp.+N" — facili da
        #    perdere. Fix tentato: pulsanti pieni con etichetta lunga
        #    ("▲ Sali a Lv.9"), riga dedicata, colore pieno — troppo
        #    ingombranti ("i tasti level up e down li volevo più visibili
        #    ma così è troppo").
        # 2) Via di mezzo (icone circolari 30px, nessun testo): tornato
        #    troppo minimale — task successivo "testo + dimensione media"
        #    chiede esplicitamente sia un'etichetta testuale sia una taglia
        #    intermedia, non solo un'icona colorata.
        # 3) Versione attuale: due ElevatedButton/OutlinedButton compatti con
        #    icona + etichetta breve fissa ("Su"/"Giù", non il numero di
        #    livello dinamico che aveva reso ingombrante il tentativo #1),
        #    altezza 30px, font 12px — via di mezzo reale tra le due
        #    estremità già provate. Tooltip mantiene il dettaglio testuale
        #    completo ("Sali a Lv.9") per chi passa sopra col mouse.
        self._level_up_btn = ft.ElevatedButton(
            content=ft.Row([
                ft.Icon(ft.Icons.ARROW_UPWARD, size=14, color="#ffffff"),
                ft.Text("Level up", size=12, weight=ft.FontWeight.BOLD, color="#ffffff"),
            ], spacing=3, tight=True),
            tooltip=f"Sali a Lv.{c.level + 1}" if c.level < 20 else "Livello massimo",
            on_click=self._on_level_up_click,
            disabled=(c.level >= 20),
            style=ft.ButtonStyle(
                bgcolor=COLOR_ACCENT_CRIMSON,
                shape=ft.RoundedRectangleBorder(radius=6),
                padding=ft.Padding.symmetric(horizontal=10, vertical=0),
            ),
            height=30,
        )
        self._level_down_btn = ft.OutlinedButton(
            content=ft.Row([
                ft.Icon(ft.Icons.ARROW_DOWNWARD, size=14, color=COLOR_TEXT_SECONDARY),
                ft.Text("Level down", size=12, weight=ft.FontWeight.BOLD, color=COLOR_TEXT_SECONDARY),
            ], spacing=3, tight=True),
            tooltip=f"Scendi a Lv.{c.level - 1}" if c.level > 1 else "Livello minimo",
            on_click=self._on_level_down_click,
            disabled=(c.level <= 1),
            style=ft.ButtonStyle(
                side=ft.BorderSide(1, COLOR_BORDER),
                shape=ft.RoundedRectangleBorder(radius=6),
                padding=ft.Padding.symmetric(horizontal=10, vertical=0),
            ),
            height=30,
        )

        return ft.Container(
            content=ft.Row(
                [
                    avatar,
                    ft.Container(width=14),
                    ft.Column(
                        [
                            ft.Text(c.name or "—", size=18, weight=ft.FontWeight.BOLD,
                                    color=COLOR_TEXT_TITLE, font_family=FONT_TITLE),
                            ft.Row(
                                [
                                    ft.Text(f"Lv.{c.level}", size=11, color=COLOR_ACCENT_CRIMSON,
                                            weight=ft.FontWeight.BOLD),
                                    ft.Text(f"  Comp. +{pb}", size=11, color=COLOR_TEXT_SECONDARY),
                                    ft.Container(width=10),
                                    self._level_up_btn,
                                    self._level_down_btn,
                                ],
                                spacing=8,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            ft.Text(
                                (c.class_name or "—")
                                + (f" ({c.subclass})" if c.subclass else "")
                                + f"  •  {c.race or '—'}",
                                size=12, color=COLOR_TEXT_SECONDARY,
                            ),
                            ft.Row(
                                [
                                    ft.Text("XP:", size=12, color=COLOR_TEXT_SECONDARY),
                                    self._xp_field,
                                    ft.TextButton(
                                        "Salva",
                                        on_click=self._on_save_xp,
                                        style=ft.ButtonStyle(color=COLOR_ACCENT_BLUE),
                                    ),
                                ],
                                spacing=6,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                        ],
                        spacing=3,
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            bgcolor=COLOR_BG_CARD,
            padding=16,
            border=ft.Border.all(1, COLOR_BORDER),
            border_radius=8,
        )

    # ------------------------------------------------------------------
    # Card editabile generica
    # ------------------------------------------------------------------

    def _editable_card(self, controls: list[ft.Control], section_key: str) -> ft.Container:
        """Card con bordo rosso superiore e bottone Modifica in fondo a destra."""
        edit_btn = ft.TextButton(
            "✎ Modifica",
            on_click=lambda e, s=section_key: self._open_edit_dialog(s),
            style=ft.ButtonStyle(color=COLOR_TEXT_MUTED),
        )
        return ft.Container(
            content=ft.Column(
                controls + [
                    ft.Container(height=4),
                    ft.Row([edit_btn], alignment=ft.MainAxisAlignment.END),
                ],
                spacing=6,
            ),
            bgcolor=COLOR_BG_CARD,
            padding=16,
            border=ft.Border(
                top=ft.BorderSide(3, COLOR_ACCENT_CRIMSON),
                left=ft.BorderSide(1, COLOR_BORDER),
                right=ft.BorderSide(1, COLOR_BORDER),
                bottom=ft.BorderSide(1, COLOR_BORDER),
            ),
            border_radius=6,
        )

    # ------------------------------------------------------------------
    # Dialog modifica competenze (tiri salvezza + abilità)
    # ------------------------------------------------------------------

    def _on_edit_competenze(self):
        """
        Dialog interattivo per toggle competenza/maestria su
        tiri salvezza e abilità. Clicca una riga per ciclare: ○ → ● → ★ → ○.
        """
        page = self._page
        if page is None:
            return
        c = self.character

        # Stato iniziale dal DB: 0=nessuna, 1=competente, 2=maestria
        states: dict[str, int] = {}
        for p in self.proficiencies:
            if p.proficiency_type in ("save", "skill"):
                states[p.name] = 2 if p.is_expert else 1

        _DOTS  = ["○", "●", "★"]
        _CLRS  = [COLOR_TEXT_MUTED, COLOR_ACCENT_CRIMSON, COLOR_ACCENT_BLUE]

        def make_row(name: str, extra: str = "") -> ft.Container:
            s = states.get(name, 0)
            dot = ft.Text(_DOTS[s], size=13, color=_CLRS[s])

            def cycle(ev, n=name, d=dot):
                states[n] = (states.get(n, 0) + 1) % 3
                d.value = _DOTS[states[n]]
                d.color = _CLRS[states[n]]
                d.update()

            return ft.Container(
                content=ft.Row(
                    [
                        dot,
                        ft.Text(name, size=12, expand=True, color=COLOR_TEXT_PRIMARY),
                        ft.Text(extra, size=10, color=COLOR_TEXT_MUTED),
                    ],
                    spacing=6,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=ft.Padding.only(left=4, top=3, bottom=3, right=4),
                border_radius=4,
                on_click=cycle,
                ink=True,
            )

        save_rows: list[ft.Control] = []
        for stat_name, key in zip(ABILITY_SCORES, ABILITY_KEYS):
            abbr = ABILITY_ABBR[ABILITY_KEYS.index(key)]
            save_rows.append(make_row(stat_name, abbr))

        skill_rows: list[ft.Control] = []
        for skill_name, ability_key in SKILLS.items():
            abbr = ABILITY_ABBR[ABILITY_KEYS.index(ability_key)]
            skill_rows.append(make_row(skill_name, f"({abbr})"))

        def on_save(ev):
            if page is None:
                return
            save_entries: list[tuple[str, bool]] = [
                (n, states[n] == 2) for n in ABILITY_SCORES if states.get(n, 0) > 0
            ]
            skill_entries: list[tuple[str, bool]] = [
                (n, states[n] == 2) for n in SKILLS if states.get(n, 0) > 0
            ]
            character_repo.replace_proficiencies_by_types(c.id, "save", save_entries)
            character_repo.replace_proficiencies_by_types(c.id, "skill", skill_entries)
            self.proficiencies = character_repo.get_proficiencies(c.id)
            page.pop_dialog()
            self._refresh()

        dlg = ft.AlertDialog(
            title=ft.Text("Modifica Competenze", size=14,
                          weight=ft.FontWeight.BOLD, color=COLOR_TEXT_TITLE),
            content=ft.Column(
                [
                    ft.Text(
                        "Tocca una riga per ciclare: ○ nessuna  ●  competente  ★ maestria",
                        size=11, color=COLOR_TEXT_MUTED,
                    ),
                    ft.Container(height=4),
                    ft.Text("TIRI SALVEZZA", size=9, color=COLOR_TEXT_MUTED,
                            weight=ft.FontWeight.BOLD,
                            style=ft.TextStyle(letter_spacing=0.8)),
                    ft.Container(
                        content=ft.Column(save_rows, spacing=2),
                        bgcolor=COLOR_BG_SECONDARY,
                        padding=8,
                        border_radius=4,
                        border=ft.Border.all(1, COLOR_BORDER),
                    ),
                    ft.Container(height=6),
                    ft.Text("ABILITÀ", size=9, color=COLOR_TEXT_MUTED,
                            weight=ft.FontWeight.BOLD,
                            style=ft.TextStyle(letter_spacing=0.8)),
                    ft.Container(
                        content=ft.Column(skill_rows, spacing=2),
                        bgcolor=COLOR_BG_SECONDARY,
                        padding=8,
                        border_radius=4,
                        border=ft.Border.all(1, COLOR_BORDER),
                    ),
                ],
                spacing=6,
                scroll=ft.ScrollMode.AUTO,
                height=480,
            ),
            actions=[
                ft.TextButton("Annulla",
                              on_click=lambda ev: page.pop_dialog() if page else None),
                ft.ElevatedButton(
                    "Salva",
                    on_click=on_save,
                    style=ft.ButtonStyle(
                        bgcolor=COLOR_ACCENT_CRIMSON, color="#ffffff",
                        shape=ft.RoundedRectangleBorder(radius=4),
                    ),
                ),
            ],
            bgcolor=COLOR_BG_CARD,
        )
        page.show_dialog(dlg)

    def _info_row(self, label: str, value: str) -> ft.Row:
        return ft.Row(
            [
                ft.Container(
                    content=ft.Text(label, size=11, color=COLOR_TEXT_SECONDARY,
                                    weight=ft.FontWeight.W_600),
                    width=130,
                ),
                ft.Text(value or "—", size=13, color=COLOR_TEXT_PRIMARY,
                        weight=ft.FontWeight.W_500),
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )

    def _text_block(self, text: str) -> ft.Container:
        return ft.Container(
            content=ft.Text(text or "—", size=13,
                            color=COLOR_TEXT_PRIMARY if text else COLOR_TEXT_MUTED),
            bgcolor=COLOR_BG_SECONDARY,
            padding=10,
            border_radius=4,
            border=ft.Border.all(1, COLOR_BORDER),
        )

    # ------------------------------------------------------------------
    # Sezioni specifiche
    # ------------------------------------------------------------------

    def _build_anagrafica(self, c: Character) -> ft.Container:
        return self._editable_card([
            self._info_row("Giocatore", c.player_name),
            self._info_row("Classe", (c.class_name or "") + (f" · {c.subclass}" if c.subclass else "")),
            self._info_row("Razza", (c.race or "") + (f" ({c.subrace})" if c.subrace else "")),
            self._info_row("Background", c.background),
            self._info_row("Allineamento", c.alignment),
            self._info_row("Livello", str(c.level)),
            self._info_row("XP", str(c.xp or 0)),
        ], "anagrafica")

    def _build_razza(self, c: Character) -> ft.Container:
        race_info = _loader.get_resolved_race(c.race, c.subrace)
        speed = race_info.get("speed", c.speed or 9)
        darkvision = race_info.get("darkvision", 0)
        traits = race_info.get("traits", [])

        rows: list[ft.Control] = [
            self._info_row("Velocità", f"{speed:g} m"),
            self._info_row("Scurovisione", f"{darkvision} m" if darkvision else "Nessuna"),
        ]
        if traits:
            rows.append(ft.Container(height=4))
            rows.append(ft.Text("Tratti Speciali", size=9, color=COLOR_TEXT_MUTED,
                                 weight=ft.FontWeight.BOLD,
                                 style=ft.TextStyle(letter_spacing=0.8)))
            for t in traits:
                # t è un dict {"name": ..., "description": ...} dal JSON razza
                name = t.get("name", "")
                desc = t.get("description", "")
                rows.append(ft.Container(
                    content=ft.Column([
                        ft.Text(name.strip(), size=12, weight=ft.FontWeight.BOLD,
                                color=COLOR_ACCENT_CRIMSON),
                        *(
                            [ft.Text(desc.strip(), size=12, color=COLOR_TEXT_SECONDARY)]
                            if desc else []
                        ),
                    ], spacing=2),
                    padding=ft.Padding.only(left=8, top=2),
                ))
        return self._editable_card(rows, "razza")

    def _build_fisico(self, c: Character) -> ft.Container:
        return self._editable_card([
            self._info_row("Età", str(c.age) if c.age else ""),
            self._info_row("Altezza", c.height),
            self._info_row("Peso", c.weight),
            self._info_row("Occhi", c.eyes),
            self._info_row("Carnagione", c.skin),
            self._info_row("Capelli", c.hair),
        ], "fisico")

    def _build_personalita(self, c: Character) -> ft.Container:
        return self._editable_card([
            ft.Text("Tratti", size=10, color=COLOR_TEXT_MUTED, weight=ft.FontWeight.BOLD),
            self._text_block(c.personality_traits),
            ft.Text("Ideali", size=10, color=COLOR_TEXT_MUTED, weight=ft.FontWeight.BOLD),
            self._text_block(c.ideals),
            ft.Text("Legami", size=10, color=COLOR_TEXT_MUTED, weight=ft.FontWeight.BOLD),
            self._text_block(c.bonds),
            ft.Text("Difetti", size=10, color=COLOR_TEXT_MUTED, weight=ft.FontWeight.BOLD),
            self._text_block(c.flaws),
        ], "personalita")

    def _build_storia(self, c: Character) -> ft.Container:
        return self._editable_card([
            ft.Text("Storia", size=10, color=COLOR_TEXT_MUTED, weight=ft.FontWeight.BOLD),
            self._text_block(c.backstory),
            ft.Text("Alleanze e Organizzazioni", size=10, color=COLOR_TEXT_MUTED,
                    weight=ft.FontWeight.BOLD),
            self._text_block(c.allies_organizations),
            ft.Text("Tratti Aggiuntivi", size=10, color=COLOR_TEXT_MUTED,
                    weight=ft.FontWeight.BOLD),
            self._text_block(c.additional_traits),
        ], "storia")

    # ------------------------------------------------------------------
    # Competenze — tutte 18 abilità + 6 tiri salvezza
    # ------------------------------------------------------------------

    def _build_competenze(
        self, c: Character, prof_bonus: int,
        skill_map: dict, save_map: dict,
    ) -> ft.Container:

        def _dot_row(name: str, mod_str: str, is_prof: bool, is_expert: bool,
                     extra: str = "") -> ft.Row:
            if is_expert:
                dot = ft.Text("★", size=13, color=COLOR_ACCENT_BLUE)
                mod_color = COLOR_ACCENT_BLUE
            elif is_prof:
                dot = ft.Text("●", size=13, color=COLOR_ACCENT_CRIMSON)
                mod_color = COLOR_ACCENT_CRIMSON
            else:
                dot = ft.Text("○", size=13, color=COLOR_TEXT_MUTED)
                mod_color = COLOR_TEXT_SECONDARY

            return ft.Row(
                [
                    dot,
                    ft.Container(
                        content=ft.Text(
                            mod_str, size=12, font_family=FONT_MONO,
                            color=mod_color,
                            weight=ft.FontWeight.BOLD if is_prof else ft.FontWeight.NORMAL,
                        ),
                        width=30,
                    ),
                    ft.Text(
                        name, size=12, expand=True,
                        color=COLOR_TEXT_PRIMARY,
                        weight=ft.FontWeight.BOLD if is_prof else ft.FontWeight.NORMAL,
                    ),
                    ft.Text(extra, size=10, color=COLOR_TEXT_MUTED),
                ],
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )

        # --- Tiri salvezza ---
        save_rows = []
        for stat_name, key in zip(ABILITY_SCORES, ABILITY_KEYS):
            score = getattr(c, f"{key}_score", 10)
            base_mod = get_modifier(score)
            is_prof = stat_name in save_map
            total = base_mod + (prof_bonus if is_prof else 0)
            mod_str = f"+{total}" if total >= 0 else str(total)
            save_rows.append(_dot_row(stat_name, mod_str, is_prof, False,
                                      ABILITY_ABBR[ABILITY_KEYS.index(key)]))

        # --- Abilità (tutte e 18) ---
        skill_rows = []
        for skill_name, ability_key in SKILLS.items():
            score = getattr(c, f"{ability_key}_score", 10)
            base_mod = get_modifier(score)
            is_prof = skill_name in skill_map
            is_expert = bool(skill_map.get(skill_name)) if is_prof else False
            if is_expert:
                total = base_mod + prof_bonus * 2
            elif is_prof:
                total = base_mod + prof_bonus
            else:
                total = base_mod
            mod_str = f"+{total}" if total >= 0 else str(total)
            abbr = ABILITY_ABBR[ABILITY_KEYS.index(ability_key)]
            skill_rows.append(_dot_row(skill_name, mod_str, is_prof, is_expert, f"({abbr})"))

        # Due colonne per le abilità
        mid = (len(skill_rows) + 1) // 2
        col_a = ft.Column(skill_rows[:mid], spacing=3)
        col_b = ft.Column(skill_rows[mid:], spacing=3)

        edit_btn = ft.TextButton(
            "✎ Modifica",
            on_click=lambda e: self._on_edit_competenze(),
            style=ft.ButtonStyle(color=COLOR_TEXT_MUTED),
        )

        return ft.Container(
            content=ft.Column(
                [
                    ft.Text("TIRI SALVEZZA", size=9, color=COLOR_TEXT_MUTED,
                            weight=ft.FontWeight.BOLD,
                            style=ft.TextStyle(letter_spacing=0.8)),
                    ft.Container(
                        content=ft.Column(save_rows, spacing=3),
                        bgcolor=COLOR_BG_SECONDARY,
                        padding=10,
                        border_radius=4,
                        border=ft.Border.all(1, COLOR_BORDER),
                    ),
                    ft.Container(height=8),
                    ft.Row([
                        ft.Text("ABILITÀ", size=9, color=COLOR_TEXT_MUTED,
                                weight=ft.FontWeight.BOLD,
                                style=ft.TextStyle(letter_spacing=0.8)),
                        ft.Text(" ● competente   ★ maestria", size=9, color=COLOR_TEXT_MUTED),
                    ], spacing=16),
                    ft.Row(
                        [col_a, ft.VerticalDivider(width=1, color=COLOR_BORDER), col_b],
                        spacing=12,
                        vertical_alignment=ft.CrossAxisAlignment.START,
                    ),
                    ft.Container(height=4),
                    ft.Row([edit_btn], alignment=ft.MainAxisAlignment.END),
                ],
                spacing=6,
            ),
            bgcolor=COLOR_BG_CARD,
            padding=16,
            border=ft.Border(
                top=ft.BorderSide(3, COLOR_ACCENT_CRIMSON),
                left=ft.BorderSide(1, COLOR_BORDER),
                right=ft.BorderSide(1, COLOR_BORDER),
                bottom=ft.BorderSide(1, COLOR_BORDER),
            ),
            border_radius=6,
        )

    # ------------------------------------------------------------------
    # Talenti scelti
    # ------------------------------------------------------------------

    def _build_talenti(self, c: Character) -> ft.Container:
        """Mostra talenti (feat) e invocazioni occulte (Warlock) acquisiti."""
        all_profs = character_repo.get_proficiencies(c.id)
        feats = [p for p in all_profs if p.proficiency_type == "feat"]
        invocations = [p for p in all_profs if p.proficiency_type == "invocation"]

        rows: list[ft.Control] = []

        # --- Bottone modifica talenti posseduti ---
        def _open_feat_edit(ev: Any) -> None:
            page = self._page
            if page is None:
                return
            all_feats = _loader.get_feats()
            owned_names = {p.name for p in feats}
            feat_cbs: list[ft.Checkbox] = []

            for fd in sorted(all_feats, key=lambda f: f.get("name", "")):
                fn = fd.get("name", "")
                cb = ft.Checkbox(
                    label=fn,
                    value=(fn in owned_names),
                    active_color=COLOR_ACCENT_AMBER,
                )
                feat_cbs.append(cb)

            def _save_feats(ev_inner: Any) -> None:
                selected = {
                    str(cb.label) for cb in feat_cbs
                    if cb.value and cb.label
                }
                # Rimuove i talenti deselezionati (invertendo i bonus registrati)
                for name in owned_names - selected:
                    character_repo.remove_feat_with_bonuses(c.id, name)
                # Aggiunge i talenti appena spuntati (senza bonus: house rules, no UI choose_one)
                for name in selected - owned_names:
                    character_repo._save_single_proficiency(c.id, "feat", name)
                page.pop_dialog()
                self._refresh()

            page.show_dialog(ft.AlertDialog(
                title=ft.Row([
                    ft.Icon(ft.Icons.MILITARY_TECH, color=COLOR_ACCENT_AMBER, size=16),
                    ft.Container(width=6),
                    ft.Text("Modifica Talenti", size=13, weight=ft.FontWeight.BOLD,
                            color=COLOR_TEXT_TITLE),
                ]),
                content=ft.Column(
                    cast(list[ft.Control], feat_cbs),
                    scroll=ft.ScrollMode.AUTO,
                    spacing=2,
                    height=320,
                ),
                actions=[
                    ft.TextButton(
                        "Annulla",
                        on_click=lambda ev_inner: page.pop_dialog(),
                    ),
                    ft.ElevatedButton(
                        "Salva",
                        on_click=_save_feats,
                        style=ft.ButtonStyle(
                            bgcolor=COLOR_ACCENT_CRIMSON, color="#ffffff",
                            shape=ft.RoundedRectangleBorder(radius=4),
                        ),
                    ),
                ],
                bgcolor=COLOR_BG_CARD,
            ))

        rows.append(ft.Row(
            [ft.TextButton(
                "✎ Modifica talenti",
                on_click=_open_feat_edit,
                style=ft.ButtonStyle(color=COLOR_TEXT_MUTED),
            )],
            alignment=ft.MainAxisAlignment.END,
        ))

        # --- Talenti ---
        if feats:
            for prof in feats:
                feat_data = _loader.get_feat(prof.name)
                desc   = feat_data.get("description", "") if feat_data else ""
                prereq = feat_data.get("prerequisite", "") if feat_data else ""
                rows.append(ft.Container(
                    content=ft.Column([
                        ft.Row([
                            ft.Icon(ft.Icons.STAR, size=14, color=COLOR_ACCENT_AMBER),
                            ft.Text(prof.name, size=13, weight=ft.FontWeight.BOLD,
                                    color=COLOR_TEXT_TITLE),
                        ], spacing=6),
                        ft.Text(f"Prerequisito: {prereq}", size=11, color=COLOR_TEXT_MUTED,
                                visible=bool(prereq)),
                        ft.Text(desc, size=12, color=COLOR_TEXT_PRIMARY, visible=bool(desc)),
                    ], spacing=4),
                    bgcolor=COLOR_BG_CARD,
                    border=ft.Border.all(1, COLOR_BORDER),
                    border_radius=6,
                    padding=ft.Padding.all(10),
                ))
        else:
            rows.append(ft.Text(
                "Nessun talento acquisito. Scegli 'Talento' al prossimo ASI.",
                size=12, color=COLOR_TEXT_MUTED, italic=True,
            ))

        # --- Scelte di Classe (Stile di Combattimento, Totem, Terreno, Discendenza) ---
        # Questi campi vengono chiesti durante il level-up ma altrimenti non
        # comparirebbero mai più da nessuna parte nella scheda (a differenza del
        # Dono del Patto del Warlock, mostrato più sotto).
        class_choices: list[tuple[str, str, str]] = []  # (etichetta, valore, dettaglio)

        if c.fighting_style:
            style_detail = ""
            guerriero_data = _loader.get_class("Guerriero") or {}
            for fs in guerriero_data.get("fighting_style_details", []):
                if fs.get("name") == c.fighting_style:
                    style_detail = fs.get("description", "")
                    break
            class_choices.append(("Stile di Combattimento", c.fighting_style, style_detail))

        if c.totem_animal:
            class_choices.append(("Animale Totem (Combattente Totemico)", c.totem_animal, ""))

        if c.land_terrain:
            class_choices.append(("Terreno (Circolo della Terra)", c.land_terrain, ""))

        if c.dragon_ancestry:
            dmg_type = ""
            stregone_data = _loader.get_class("Stregone") or {}
            for sub in stregone_data.get("subclasses", []):
                if sub.get("name") == "Discendenza Draconica":
                    for row in sub.get("dragon_damage_types", []):
                        if row.get("dragon") == c.dragon_ancestry:
                            dmg_type = row.get("damage_type", "")
                            break
                    break
            detail = f"Tipo di danno associato: {dmg_type}" if dmg_type else ""
            class_choices.append(("Antenato Draconico", c.dragon_ancestry, detail))

        # --- Modifica Scelte di Classe (2026-07-16, richiesta Davide:
        # "rendiamo modificabili anche i campi che non si possono
        # modificare attualmente, come le scelte di classe in profilo") ---
        # Permette di CAMBIARE una scelta già fatta (non di anticiparne una
        # non ancora guadagnata: il dropdown compare solo per i campi già
        # valorizzati, esattamente come class_choices sopra) — stesse
        # opzioni PHB già usate nel dialog di level-up, mai valori inventati.
        def _open_class_choices_edit(ev: Any) -> None:
            page = self._page
            if page is None:
                return
            cls_lower_edit = (c.class_name or "").strip().lower()
            dd_refs: dict[str, ft.Dropdown] = {}
            dlg_content: list[ft.Control] = []

            if c.fighting_style:
                styles = _loader.get_fighting_styles(cls_lower_edit)
                if styles:
                    dd = ft.Dropdown(
                        label="Stile di Combattimento",
                        value=c.fighting_style if c.fighting_style in styles else styles[0],
                        options=[ft.DropdownOption(key=o, text=o) for o in styles],
                        bgcolor=COLOR_BG_CARD, color=COLOR_TEXT_PRIMARY,
                        label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=12),
                        border_color=COLOR_BORDER, focused_border_color=COLOR_ACCENT_CRIMSON,
                    )
                    dd_refs["fighting_style"] = dd
                    dlg_content.append(dd)

            if c.totem_animal:
                totems = _loader.get_totem_animals()
                dd = ft.Dropdown(
                    label="Animale Totem",
                    value=c.totem_animal if c.totem_animal in totems else totems[0],
                    options=[ft.DropdownOption(key=o, text=o) for o in totems],
                    bgcolor=COLOR_BG_CARD, color=COLOR_TEXT_PRIMARY,
                    label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=12),
                    border_color=COLOR_BORDER, focused_border_color=COLOR_ACCENT_CRIMSON,
                )
                dd_refs["totem_animal"] = dd
                dlg_content.append(dd)

            if c.land_terrain:
                terrains = _loader.get_land_terrains()
                dd = ft.Dropdown(
                    label="Terreno del Cerchio",
                    value=c.land_terrain if c.land_terrain in terrains else terrains[0],
                    options=[ft.DropdownOption(key=o, text=o) for o in terrains],
                    bgcolor=COLOR_BG_CARD, color=COLOR_TEXT_PRIMARY,
                    label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=12),
                    border_color=COLOR_BORDER, focused_border_color=COLOR_ACCENT_CRIMSON,
                )
                dd_refs["land_terrain"] = dd
                dlg_content.append(dd)

            if c.dragon_ancestry:
                dd = ft.Dropdown(
                    label="Antenato Draconico",
                    value=c.dragon_ancestry if c.dragon_ancestry in DRACONIDE_ANCESTRIES else DRACONIDE_ANCESTRIES[0],
                    options=[ft.DropdownOption(key=o, text=o) for o in DRACONIDE_ANCESTRIES],
                    bgcolor=COLOR_BG_CARD, color=COLOR_TEXT_PRIMARY,
                    label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=12),
                    border_color=COLOR_BORDER, focused_border_color=COLOR_ACCENT_CRIMSON,
                )
                dd_refs["dragon_ancestry"] = dd
                dlg_content.append(dd)

            if not dd_refs:
                return

            def _save(ev_inner: Any) -> None:
                if "fighting_style" in dd_refs:
                    c.fighting_style = dd_refs["fighting_style"].value or c.fighting_style
                if "totem_animal" in dd_refs:
                    c.totem_animal = dd_refs["totem_animal"].value or c.totem_animal
                if "land_terrain" in dd_refs:
                    c.land_terrain = dd_refs["land_terrain"].value or c.land_terrain
                if "dragon_ancestry" in dd_refs:
                    c.dragon_ancestry = dd_refs["dragon_ancestry"].value or c.dragon_ancestry
                if not character_repo.update(c):
                    show_error_dialog(page, "Impossibile salvare le scelte di classe.")
                    return
                # Lo Stile "Difesa" (Guerriero/Paladino/Ranger) dà +1 CA solo
                # se indossata un'armatura — cambiare stile può quindi
                # alterare la CA, stesso ricalcolo già fatto al level-up.
                character_repo.calculate_and_update_ca(c.id)
                page.pop_dialog()
                self._refresh()

            page.show_dialog(ft.AlertDialog(
                title=ft.Row([
                    ft.Icon(ft.Icons.AUTO_AWESOME, color=COLOR_ACCENT_CRIMSON, size=16),
                    ft.Container(width=6),
                    ft.Text("Modifica Scelte di Classe", size=13, weight=ft.FontWeight.BOLD,
                            color=COLOR_TEXT_TITLE),
                ]),
                content=ft.Column(dlg_content, spacing=12, width=320),
                actions=[
                    ft.TextButton("Annulla", on_click=lambda ev_inner: page.pop_dialog()),
                    ft.ElevatedButton(
                        "Salva", on_click=_save,
                        style=ft.ButtonStyle(bgcolor=COLOR_ACCENT_CRIMSON, color="#ffffff",
                                              shape=ft.RoundedRectangleBorder(radius=4)),
                    ),
                ],
                bgcolor=COLOR_BG_CARD,
            ))

        if class_choices:
            rows.append(ft.Divider(color=COLOR_BORDER, height=16))
            rows.append(ft.Row([
                ft.Text(
                    "Scelte di Classe", size=13, weight=ft.FontWeight.BOLD,
                    color=COLOR_ACCENT_CRIMSON, expand=True,
                ),
                ft.TextButton(
                    "✎ Modifica", on_click=_open_class_choices_edit,
                    style=ft.ButtonStyle(color=COLOR_TEXT_MUTED),
                ),
            ]))
            for label, value, detail in class_choices:
                rows.append(ft.Container(
                    content=ft.Column([
                        ft.Row([
                            ft.Icon(ft.Icons.AUTO_AWESOME, size=14, color=COLOR_ACCENT_CRIMSON),
                            ft.Text(label, size=11, color=COLOR_TEXT_MUTED,
                                    weight=ft.FontWeight.BOLD),
                        ], spacing=6),
                        ft.Text(value, size=13, weight=ft.FontWeight.BOLD,
                                color=COLOR_TEXT_TITLE),
                        ft.Text(detail, size=12, color=COLOR_TEXT_PRIMARY,
                                visible=bool(detail)),
                    ], spacing=2),
                    bgcolor=COLOR_BG_CARD,
                    border=ft.Border.all(1, COLOR_BORDER),
                    border_radius=6,
                    padding=ft.Padding.all(10),
                ))

        # --- Metamagia (solo se Stregone) ---
        if (c.class_name or "").lower() == "stregone":
            metamagic = [p for p in all_profs if p.proficiency_type == "metamagic"]
            rows.append(ft.Divider(color=COLOR_BORDER, height=16))
            rows.append(ft.Text(
                "Metamagia", size=13, weight=ft.FontWeight.BOLD, color="#7b1fa2",
            ))
            if metamagic:
                for mm in metamagic:
                    rows.append(ft.Container(
                        content=ft.Row([
                            ft.Icon(ft.Icons.BOLT, size=14, color="#7b1fa2"),
                            ft.Text(mm.name, size=12, color=COLOR_TEXT_PRIMARY),
                        ], spacing=6),
                        bgcolor=COLOR_BG_CARD,
                        border=ft.Border.all(1, COLOR_BORDER),
                        border_radius=6,
                        padding=ft.Padding.symmetric(horizontal=10, vertical=6),
                    ))
            else:
                rows.append(ft.Text(
                    "Nessuna metamagia — disponibile dal Lv.3.",
                    size=12, color=COLOR_TEXT_MUTED, italic=True,
                ))

        # --- Discipline Elementali (solo se Monaco, Via dei Quattro Elementi) ---
        # Aggiunto 2026-07-16 insieme al picker Lv.3/6/11/17 in
        # _on_level_up_click — prima non c'era alcuna sezione per vedere le
        # discipline conosciute, stesso principio del Dono del Patto/
        # Metamagia già mostrati qui.
        if (c.class_name or "").lower() == "monaco" and (c.subclass or "") == "Via dei Quattro Elementi":
            disciplines_known = [p for p in all_profs if p.proficiency_type == "monk_discipline"]
            _mk_all_data = _loader.get_subclass_data("Monaco", "Via dei Quattro Elementi") or {}
            _mk_by_name = {d.get("name", ""): d for d in _mk_all_data.get("disciplines", [])}
            rows.append(ft.Divider(color=COLOR_BORDER, height=16))
            rows.append(ft.Text(
                "Discipline Elementali", size=13, weight=ft.FontWeight.BOLD, color="#00838f",
            ))
            if disciplines_known:
                for disc in disciplines_known:
                    disc_data = _mk_by_name.get(disc.name, {})
                    ki_cost = disc_data.get("ki_cost", 0)
                    ki_label = "Gratuita" if not ki_cost else f"{ki_cost} ki"

                    def _open_discipline_detail(ev: Any, _name: str = disc.name,
                                                 _desc: str = disc_data.get("description", ""),
                                                 _ki: str = ki_label) -> None:
                        page = self._page
                        if page is None:
                            return
                        page.show_dialog(ft.AlertDialog(
                            title=ft.Text(_name, size=14, weight=ft.FontWeight.BOLD,
                                          color=COLOR_TEXT_TITLE),
                            content=ft.Column([
                                ft.Text(f"Costo: {_ki}", size=12, color=COLOR_TEXT_MUTED),
                                ft.Text(_desc, size=13, color=COLOR_TEXT_PRIMARY),
                            ], spacing=8, scroll=ft.ScrollMode.AUTO, width=340, height=220),
                            actions=[ft.TextButton("Chiudi", on_click=lambda ev2: page.pop_dialog())],
                            bgcolor=COLOR_BG_CARD,
                        ))

                    rows.append(ft.Container(
                        content=ft.Row([
                            ft.Icon(ft.Icons.SELF_IMPROVEMENT, size=14, color="#00838f"),
                            ft.Text(disc.name, size=12, color=COLOR_TEXT_PRIMARY, expand=True),
                            ft.Text(ki_label, size=11, color=COLOR_TEXT_MUTED),
                        ], spacing=6),
                        bgcolor=COLOR_BG_CARD,
                        border=ft.Border.all(1, COLOR_BORDER),
                        border_radius=6,
                        padding=ft.Padding.symmetric(horizontal=10, vertical=6),
                        on_click=_open_discipline_detail,
                        ink=True,
                    ))
            else:
                rows.append(ft.Text(
                    "Nessuna disciplina conosciuta — disponibile dal Lv.3.",
                    size=12, color=COLOR_TEXT_MUTED, italic=True,
                ))

        # --- Invocazioni Occulte + Patto (solo se Warlock) ---
        if (c.class_name or "").lower() == "warlock":
            # Patto — stessa richiesta di editabilità delle Scelte di
            # Classe sopra (2026-07-16), qui a parte perché il Dono del
            # Patto vive nella propria sezione dedicata invece che in
            # class_choices (Warlock Lv3+).
            def _open_pact_boon_edit(ev: Any) -> None:
                page = self._page
                if page is None or not c.pact_boon:
                    return
                boons = _loader.get_pact_boons()
                dd = ft.Dropdown(
                    label="Dono del Patto",
                    value=c.pact_boon if c.pact_boon in boons else boons[0],
                    options=[ft.DropdownOption(key=o, text=o) for o in boons],
                    bgcolor=COLOR_BG_CARD, color=COLOR_TEXT_PRIMARY,
                    label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=12),
                    border_color=COLOR_BORDER, focused_border_color=COLOR_ACCENT_CRIMSON,
                )

                def _save(ev_inner: Any) -> None:
                    c.pact_boon = dd.value or c.pact_boon
                    if not character_repo.update(c):
                        show_error_dialog(page, "Impossibile salvare il Dono del Patto.")
                        return
                    page.pop_dialog()
                    self._refresh()

                page.show_dialog(ft.AlertDialog(
                    title=ft.Text("Modifica Dono del Patto", size=13,
                                  weight=ft.FontWeight.BOLD, color=COLOR_TEXT_TITLE),
                    content=ft.Column([dd], spacing=8, width=280),
                    actions=[
                        ft.TextButton("Annulla", on_click=lambda ev_inner: page.pop_dialog()),
                        ft.ElevatedButton(
                            "Salva", on_click=_save,
                            style=ft.ButtonStyle(bgcolor=COLOR_ACCENT_CRIMSON, color="#ffffff",
                                                  shape=ft.RoundedRectangleBorder(radius=4)),
                        ),
                    ],
                    bgcolor=COLOR_BG_CARD,
                ))

            # Patto
            rows.append(ft.Divider(color=COLOR_BORDER, height=16))
            rows.append(ft.Row([
                ft.Text(
                    "Dono del Patto", size=13, weight=ft.FontWeight.BOLD,
                    color=COLOR_ACCENT_CRIMSON, expand=True,
                ),
                ft.TextButton(
                    "✎ Modifica", on_click=_open_pact_boon_edit,
                    style=ft.ButtonStyle(color=COLOR_TEXT_MUTED),
                ) if c.pact_boon else ft.Container(width=0),
            ]))
            if c.pact_boon:
                rows.append(ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.BOOK, size=14, color=COLOR_ACCENT_CRIMSON),
                        ft.Text(c.pact_boon, size=12, color=COLOR_TEXT_PRIMARY),
                    ], spacing=6),
                    bgcolor=COLOR_BG_CARD,
                    border=ft.Border.all(1, COLOR_BORDER),
                    border_radius=6,
                    padding=ft.Padding.symmetric(horizontal=10, vertical=6),
                ))
            else:
                rows.append(ft.Text(
                    "Nessun patto ancora — sceglierai al Lv.3.",
                    size=12, color=COLOR_TEXT_MUTED, italic=True,
                ))

        # --- Suppliche Occulte (solo se Warlock) ---
        if (c.class_name or "").lower() == "warlock":
            rows.append(ft.Divider(color=COLOR_BORDER, height=16))
            rows.append(ft.Text(
                "Suppliche Occulte",
                size=13, weight=ft.FontWeight.BOLD, color=COLOR_ACCENT_CRIMSON,
            ))
            if invocations:
                for inv in invocations:
                    inv_data = next(
                        (i for i in _loader.get_invocations()
                         if i.get("name") == inv.name), None
                    )
                    desc = inv_data.get("description", "") if inv_data else ""
                    prereq_lv = inv_data.get("prerequisite_level", 0) if inv_data else 0
                    rows.append(ft.Container(
                        content=ft.Column([
                            ft.Row([
                                ft.Icon(ft.Icons.AUTO_FIX_HIGH, size=14,
                                        color=COLOR_ACCENT_CRIMSON),
                                ft.Text(inv.name, size=13, weight=ft.FontWeight.BOLD,
                                        color=COLOR_TEXT_TITLE),
                                ft.Text(f"  Lv.{prereq_lv}+", size=11,
                                        color=COLOR_TEXT_MUTED,
                                        visible=bool(prereq_lv)),
                            ], spacing=4),
                            ft.Text(desc, size=12, color=COLOR_TEXT_PRIMARY,
                                    visible=bool(desc)),
                        ], spacing=4),
                        bgcolor=COLOR_BG_CARD,
                        border=ft.Border.all(1, COLOR_BORDER),
                        border_radius=6,
                        padding=ft.Padding.all(10),
                    ))
            else:
                rows.append(ft.Text(
                    "Nessuna supplica ancora — verranno mostrate dal Lv.2.",
                    size=12, color=COLOR_TEXT_MUTED, italic=True,
                ))

        return ft.Container(
            content=ft.Column(rows, spacing=8),
            padding=ft.Padding.symmetric(horizontal=16, vertical=8),
        )

    # ------------------------------------------------------------------
    # XP
    # ------------------------------------------------------------------

    def _can_level_up(self, c: Character) -> bool:
        if c.level >= 20:
            return False
        next_xp = LEVEL_PROGRESSION.get(c.level + 1, (999999, 0))[0]
        return (c.xp or 0) >= next_xp

    def _on_save_xp(self, e):
        if self._xp_field is None:
            return
        try:
            xp = int((self._xp_field.value or "0").strip())
        except ValueError:
            return
        self.character.xp = xp
        if not character_repo.update(self.character):
            show_error_dialog(self._page)

    # ------------------------------------------------------------------
    # Level Up guidato
    # ------------------------------------------------------------------

    def _on_level_up_click(self, e):
        c = self.character
        new_level = c.level + 1
        if new_level > 20:
            return

        old_pb = get_proficiency_bonus(c.level)
        new_pb = get_proficiency_bonus(new_level)
        steps = get_level_up_steps(c.class_name or "", new_level, old_pb, new_pb, c.subclass or "")

        hit_die = c.hit_dice_type or 8
        con_mod = get_modifier(c.con_score)
        hp_max_gain = hit_die
        hp_avg_gain = max(1, hit_die // 2 + 1)

        # --- Widget HP ---
        hp_choice = ft.RadioGroup(
            content=ft.Column([
                ft.Radio(value="max",
                         label=f"Massimo ({hp_max_gain} + {con_mod:+d} CON = {hp_max_gain + con_mod})"),
                ft.Radio(value="avg",
                         label=f"Media ({hp_avg_gain} + {con_mod:+d} CON = {hp_avg_gain + con_mod})"),
                ft.Radio(value="manual", label=f"Inserisci il risultato del dado (d{hit_die})"),
            ], spacing=4),
            value="avg",
        )
        manual_roll = ft.TextField(
            label=f"Risultato dado d{hit_die} (1–{hit_die})",
            width=200, keyboard_type=ft.KeyboardType.NUMBER, visible=False,
            text_style=ft.TextStyle(size=13, color=COLOR_TEXT_PRIMARY),
            border_color=COLOR_BORDER, focused_border_color=COLOR_ACCENT_BLUE,
            bgcolor=COLOR_BG_CARD,
        )

        def on_hp_choice_change(ev):
            manual_roll.visible = ev.control.value == "manual"
            try:
                manual_roll.update()
            except RuntimeError:
                pass

        hp_choice.on_change = on_hp_choice_change

        # --- Widget ASI ---
        stat_options = [
            ft.DropdownOption(key=k, text=f"{n} (attuale: {getattr(c, k + '_score')})")
            for k, n in zip(ABILITY_KEYS, ABILITY_SCORES)
        ]
        feat_names = _loader.get_feat_names()
        feat_options = [ft.DropdownOption(key=f, text=f) for f in feat_names]

        asi_type = ft.RadioGroup(
            content=ft.Column([
                ft.Radio(value="two_one", label="+2 a una caratteristica"),
                ft.Radio(value="one_one", label="+1 a due caratteristiche diverse"),
                ft.Radio(value="feat",    label="Talento"),
            ], spacing=4),
            value="two_one",
        )
        stat_dd1 = ft.Dropdown(label="Caratteristica", options=stat_options, width=280)
        stat_dd2 = ft.Dropdown(label="Seconda caratteristica (+1)", options=stat_options,
                               width=280, visible=False)
        feat_dd  = ft.Dropdown(
            label="Scegli talento",
            options=feat_options if feat_options else [ft.DropdownOption(key="__none__", text="— nessun talento disponibile —")],
            width=280,
            visible=False,
            bgcolor=COLOR_BG_CARD,
            color=COLOR_TEXT_PRIMARY,
            label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=12),
            border_color=COLOR_BORDER,
            focused_border_color=COLOR_ACCENT_BLUE,
        )

        # Dropdown bonus stat per talenti con choose_one — appare dinamicamente
        feat_bonus_dd = ft.Dropdown(
            label="Scegli la caratteristica da aumentare (+1)",
            options=[],
            width=280,
            visible=False,
            bgcolor=COLOR_BG_CARD,
            color=COLOR_TEXT_PRIMARY,
            label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=12),
            border_color=COLOR_BORDER,
            focused_border_color=COLOR_ACCENT_BLUE,
        )

        _stat_name_map = dict(zip(ABILITY_KEYS, ABILITY_SCORES))  # es. "str" → "Forza"

        def _make_info_icon(
            describe: Callable[[str], tuple[str, str] | None], value: str
        ) -> ft.IconButton:
            """
            Icona ⓘ standalone per opzioni non-Dropdown (RadioGroup/Checkbox) —
            stessa presentazione di `dropdown_with_info()` ma per un singolo
            valore fisso invece di leggere `dropdown.value` dal vivo (task #24,
            2026-07-16: Dono del Patto/Metamagia/Suppliche Occulte usano
            RadioGroup/Checkbox, non Dropdown).
            """
            def _on_click(ev: Any) -> None:
                page = self._page
                if page is None:
                    return
                result = describe(value)
                if result is None:
                    return
                title, body = result
                page.show_dialog(ft.AlertDialog(
                    title=ft.Text(title, size=14, weight=ft.FontWeight.BOLD, color=COLOR_TEXT_TITLE),
                    content=ft.Container(
                        content=ft.Column(
                            [ft.Text(body, size=13, color=COLOR_TEXT_PRIMARY, selectable=True)],
                            scroll=ft.ScrollMode.AUTO),
                        width=360, height=320),
                    actions=[ft.TextButton("Chiudi", on_click=lambda e2: page.pop_dialog())],
                    bgcolor=COLOR_BG_CARD,
                ))
            return ft.IconButton(
                ft.Icons.INFO_OUTLINE, icon_size=18, icon_color=COLOR_ACCENT_BLUE,
                tooltip="Mostra descrizione", on_click=_on_click, padding=ft.Padding.all(2),
            )

        def on_feat_select(ev: Any) -> None:
            """Mostra feat_bonus_dd se il talento ha choose_one, altrimenti la nasconde."""
            name = feat_dd.value
            if not name or name == "__none__":
                feat_bonus_dd.visible = False
                try:
                    feat_bonus_dd.update()
                except RuntimeError:
                    pass
                return
            fd = _loader.get_feat(name)
            ab = fd.get("ability_bonus") if fd else None
            if ab and ab.get("choose_one"):
                opts = ab.get("options", [])
                feat_bonus_dd.options = [
                    ft.DropdownOption(key=k, text=_stat_name_map.get(k, k))
                    for k in opts
                ]
                feat_bonus_dd.value = None
                feat_bonus_dd.visible = True
            else:
                feat_bonus_dd.visible = False
            try:
                feat_bonus_dd.update()
            except RuntimeError:
                pass

        feat_dd.on_select = on_feat_select

        # Widget ⓘ per la descrizione del talento selezionato (task #24) —
        # `feat_dd_row` (non `feat_dd` da solo) va nascosto/mostrato insieme,
        # altrimenti l'icona ⓘ resterebbe visibile anche a dropdown nascosto.
        feat_dd_row = dropdown_with_info(lambda: self._page, feat_dd, make_feat_describe(_loader))
        feat_dd_row.visible = False

        def on_asi_type_change(ev):
            val = ev.control.value
            stat_dd1.visible = val in ("two_one", "one_one")
            stat_dd2.visible = val == "one_one"
            feat_dd.visible  = val == "feat"
            feat_dd_row.visible = val == "feat"
            # nasconde anche la bonus_dd se si cambia modalità
            if val != "feat":
                feat_bonus_dd.visible = False
            try:
                stat_dd1.update()
                stat_dd2.update()
                feat_dd.update()
                feat_dd_row.update()
                feat_bonus_dd.update()
            except RuntimeError:
                pass

        asi_type.on_change = on_asi_type_change

        # --- Costruzione dialog da steps ---
        dlg_rows: list[ft.Control] = [
            ft.Text(f"Avanzamento a Livello {new_level}",
                    size=15, weight=ft.FontWeight.BOLD, color=COLOR_TEXT_TITLE),
            ft.Text(f"{c.class_name or '—'}  •  {c.race or '—'}",
                    size=12, color=COLOR_TEXT_SECONDARY),
            ft.Divider(color=COLOR_BORDER),
        ]

        # Abilità/strumenti su cui il personaggio è già competente (candidati Maestria)
        _all_profs = character_repo.get_proficiencies(c.id)
        _expertise_candidates = [
            p.name for p in _all_profs
            if p.proficiency_type in ("skill", "tool") and not p.is_expert
        ]

        # Lista di riferimenti ai Checkbox di Maestria per raccogliere le scelte
        expertise_cb_groups: list[list[ft.Checkbox]] = []

        # Invocazioni: (count_to_add, list[Checkbox])
        invocation_cb_groups: list[tuple[int, list[ft.Checkbox]]] = []

        # Metamagia: (count, list[Checkbox])
        metamagic_cb_groups: list[tuple[int, list[ft.Checkbox]]] = []

        # Patto del Warlock
        pact_rg_ref: list[ft.RadioGroup] = []

        # Incantesimi conosciuti (classi "know"): [(step_data, [dd, ...]), ...]
        spell_learn_refs: list[tuple[dict, list[ft.Dropdown]]] = []

        # Segreti Magici (qualsiasi classe): [(step_data, [(spell_name, class_name), ...]), ...]
        magical_secrets_refs: list[tuple[dict, list[tuple[str, str]]]] = []

        # Sostituzione incantesimo conosciuto (opzionale, classi "know"):
        # [(enable_checkbox, dd_remove, dd_add), ...]
        spell_swap_refs: list[tuple[ft.Checkbox, ft.Dropdown, ft.Dropdown]] = []

        # Nuovo trucchetto conosciuto (lv.4/10, 6 classi incantatrici): [dd, ...]
        cantrip_learn_refs: list[ft.Dropdown] = []

        # Arcanum Mistico (Warlock, lv.11/13/15/17): [dd, ...] — un solo
        # dropdown per level-up, livello incantesimo ESATTO (non "fino a").
        arcanum_spell_refs: list[ft.Dropdown] = []

        # Discipline Elementali (Monaco, Via dei Quattro Elementi, lv.6/11/17
        # — crescita successiva alla scelta iniziale di Lv.3, gestita invece
        # nel blocco SUBCLASS_CHOICE più sotto): [dd, ...]
        monk_discipline_refs: list[ft.Dropdown] = []

        # Mistificatore Arcano (Ladro)/Cavaliere Mistico (Guerriero) — casting
        # "preso in prestito dal Mago". Apprendimento INIZIALE al 3° livello
        # (stesso livello di SUBCLASS_CHOICE, gestito con reattività live sul
        # valore scelto — vedi blocco SUBCLASS_CHOICE più sotto):
        borrowed_initial_cantrip_refs: list[ft.Dropdown] = []
        # [(dropdown, origin_unrestricted), ...] — 2 vincolati per scuola +
        # 1 libero (libero da vincolo per lo scambio futuro solo se il 3°
        # livello è tra gli unrestricted_origin_levels della sottoclasse,
        # vedi CLAUDE.md 2026-07-15 — asimmetria reale Ladro/Guerriero)
        borrowed_initial_spell_refs: list[tuple[ft.Dropdown, bool]] = []
        # Container la cui visibilità segue il valore del dropdown sottoclasse
        borrowed_initial_container_ref: list[ft.Container] = []
        borrowed_subclass_name_ref: list[str] = []  # [0] = nome sottoclasse borrowed-caster, se applicabile

        # Monaco, Via dei Quattro Elementi: scelta INIZIALE di Lv.3 (Sintonia
        # Elementale automatica + 1 disciplina a scelta) — stesso motivo/
        # pattern del blocco Mistificatore Arcano/Cavaliere Mistico sopra,
        # gestita con reattività live sul dropdown sottoclasse (vedi blocco
        # SUBCLASS_CHOICE più sotto). Aggiunto 2026-07-16.
        monk_initial_discipline_refs: list[ft.Dropdown] = []

        # Crescita dal 4° livello in poi (BORROWED_CANTRIP/BORROWED_SPELL_LEARN):
        borrowed_cantrip_dd_refs: list[ft.Dropdown] = []
        # [(dropdown, origin_unrestricted), ...]
        borrowed_spell_learn_refs: list[tuple[ft.Dropdown, bool]] = []
        # Sostituzione opzionale: (checkbox, dd_remove, dd_add, restricted_schools)
        borrowed_spell_swap_refs: list[tuple[ft.Checkbox, ft.Dropdown, ft.Dropdown, list[str]]] = []

        def _borrowed_eligible_mago_spells(
            max_level: int, restricted_schools: list[str], unrestricted: bool,
            exclude: set[str],
        ) -> list[dict]:
            """
            Incantesimi da Mago eleggibili per Mistificatore Arcano/Cavaliere
            Mistico: livello 1..max_level, esclusi quelli già scelti/
            conosciuti, e se non `unrestricted` limitati a `restricted_schools`.
            """
            pool = _loader.get_spells("Mago")
            return sorted(
                (
                    s for s in pool
                    if 0 < s.get("level", 0) <= max_level
                    and s.get("name") not in exclude
                    and (unrestricted or s.get("school", "") in restricted_schools)
                ),
                key=lambda s: (s.get("level", 0), s.get("name", "")),
            )

        has_asi = False
        subclass_dd_ref: list[ft.Dropdown] = []  # [0] = dropdown sottoclasse, se presente
        # Inizializzato qui (non solo dentro il ramo SUBCLASS_CHOICE) così è
        # sempre garantito bound anche nei level-up senza scelta sottoclasse
        # — a runtime `subclasses` viene letta più avanti (riga ~3074) solo
        # sotto `if live_subclass_dd is not None`, che è già correlato a
        # `subclass_dd_ref` non vuoto, ma l'analisi statica di Pylance non
        # riesce a legare i due `if` a distanza: fix difensivo, nessun
        # comportamento cambiato.
        subclasses: list[str] = []
        for step in steps:
            if step.step_type == StepType.HP_GAIN:
                dlg_rows += [
                    ft.Text("Punti Ferita", size=13, weight=ft.FontWeight.BOLD,
                            color=COLOR_ACCENT_CRIMSON),
                    ft.Text(f"Dado vita: d{hit_die}  |  Mod. CON: {con_mod:+d}",
                            size=12, color=COLOR_TEXT_SECONDARY),
                    hp_choice,
                    manual_roll,
                ]

            elif step.step_type == StepType.FEATURE_AUTO:
                dlg_rows.append(ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.AUTO_AWESOME, size=14, color=COLOR_ACCENT_BLUE),
                        ft.Text(step.label, size=12, color=COLOR_TEXT_PRIMARY, expand=True),
                    ], spacing=6),
                    bgcolor=COLOR_BG_SECONDARY,
                    padding=ft.Padding.symmetric(horizontal=10, vertical=6),
                    border_radius=4,
                    border=ft.Border.all(1, COLOR_BORDER),
                ))

            elif step.step_type == StepType.SUBCLASS_CHOICE:
                # Carica sottoclassi dalla classe del personaggio
                cls_data = _loader.get_class(c.class_name or "")
                subclasses = []
                subclass_label_name = "Sottoclasse"
                if cls_data:
                    subclasses = [sc.get("name", "") for sc in cls_data.get("subclasses", [])]
                    subclass_label_name = cls_data.get("subclass_label", "Sottoclasse")

                if subclasses:
                    _sc_dd = ft.Dropdown(
                        label=subclass_label_name,
                        value=c.subclass if c.subclass in subclasses else subclasses[0],
                        options=[ft.DropdownOption(key=s, text=s) for s in subclasses],
                        bgcolor=COLOR_BG_CARD,
                        color=COLOR_TEXT_PRIMARY,
                        label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=12),
                        border_color=COLOR_BORDER,
                        focused_border_color=COLOR_ACCENT_BLUE,
                        expand=True,
                    )
                    subclass_dd_ref.append(_sc_dd)
                    dlg_rows += [
                        ft.Divider(color=COLOR_BORDER),
                        ft.Row([
                            ft.Icon(ft.Icons.STAR, size=14, color=COLOR_ACCENT_AMBER),
                            ft.Text(step.label, size=13, weight=ft.FontWeight.BOLD,
                                    color=COLOR_ACCENT_BLUE, expand=True),
                        ], spacing=6),
                        _sc_dd,
                    ]

                    # ------------------------------------------------------
                    # Mistificatore Arcano (Ladro)/Cavaliere Mistico
                    # (Guerriero): apprendimento INIZIALE di trucchetti e
                    # incantesimi "presi in prestito dal Mago", mostrato solo
                    # se la sottoclasse scelta nel dropdown sopra è quella
                    # che concede casting — a differenza di stile di
                    # combattimento/totem/terreno (che riusano c.subclass
                    # GIA' persistito, quindi appaiono solo al level-up
                    # successivo), qui serve reattività live sul valore del
                    # dropdown perché la scelta va fatta nello STESSO
                    # level-up in cui si sceglie la sottoclasse. Aggiunto
                    # 2026-07-15, fix Mistificatore Arcano/Cavaliere Mistico.
                    _borrowed_name = _loader.get_borrowed_caster_subclass_name(c.class_name or "")
                    if _borrowed_name:
                        borrowed_subclass_name_ref.append(_borrowed_name)
                        _bc_data = _loader.get_borrowed_caster_data(c.class_name or "", _borrowed_name) or {}
                        _bc_prog3 = next(
                            (r for r in _bc_data.get("spell_progression", []) if r.get("level") == 3),
                            {},
                        )
                        _fixed_cantrip = _bc_data.get("fixed_cantrip") or ""
                        _cantrips_lv3 = _bc_prog3.get("cantrips_known", 0)
                        _choosable_cantrip_count = max(0, _cantrips_lv3 - (1 if _fixed_cantrip else 0))
                        _cantrip_pool = [
                            n for n in _bc_data.get("cantrip_options", [])
                            if n != _fixed_cantrip
                        ]
                        _restricted_schools = _bc_data.get("restricted_schools", [])
                        _unrestricted_levels = _bc_data.get("unrestricted_origin_levels", [])
                        _lv3_is_unrestricted = 3 in _unrestricted_levels

                        _bi_cantrip_dds: list[ft.Dropdown] = []
                        _bi_spell_dds: list[ft.Dropdown] = []

                        def _refresh_borrowed_initial_options(ev: Any = None) -> None:
                            chosen_cantrips = {dd.value for dd in _bi_cantrip_dds if dd.value}
                            for dd in _bi_cantrip_dds:
                                excl = chosen_cantrips - ({dd.value} if dd.value else set())
                                dd.options = [
                                    ft.DropdownOption(key=n, text=n)
                                    for n in _cantrip_pool if n not in excl
                                ]
                                try:
                                    dd.update()
                                except RuntimeError:
                                    pass
                            chosen_spells = {dd.value for dd in _bi_spell_dds if dd.value}
                            for i, dd in enumerate(_bi_spell_dds):
                                is_free = (i == len(_bi_spell_dds) - 1)  # ultimo dropdown = pick libero
                                excl = chosen_spells - ({dd.value} if dd.value else set())
                                eligible = _borrowed_eligible_mago_spells(
                                    1, _restricted_schools,
                                    unrestricted=is_free, exclude=excl,
                                )
                                dd.options = [
                                    ft.DropdownOption(key=s["name"], text=s["name"])
                                    for s in eligible
                                ]
                                if dd.value not in {o.key for o in dd.options}:
                                    dd.value = None
                                try:
                                    dd.update()
                                except RuntimeError:
                                    pass

                        for i in range(_choosable_cantrip_count):
                            dd = ft.Dropdown(
                                label=f"Trucchetto {i + 1}/{_choosable_cantrip_count}",
                                options=[ft.DropdownOption(key=n, text=n) for n in _cantrip_pool],
                                bgcolor=COLOR_BG_CARD, color=COLOR_TEXT_PRIMARY,
                                label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=12),
                                border_color=COLOR_BORDER,
                                focused_border_color=COLOR_ACCENT_BLUE,
                                on_select=_refresh_borrowed_initial_options,
                                expand=True,
                            )
                            _bi_cantrip_dds.append(dd)
                            borrowed_initial_cantrip_refs.append(dd)

                        _restricted_label = "/".join(_restricted_schools)
                        for i in range(2):
                            dd = ft.Dropdown(
                                label=f"Incantesimo {i + 1}/3 ({_restricted_label})",
                                options=[],
                                bgcolor=COLOR_BG_CARD, color=COLOR_TEXT_PRIMARY,
                                label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=12),
                                border_color=COLOR_BORDER,
                                focused_border_color=COLOR_ACCENT_BLUE,
                                on_select=_refresh_borrowed_initial_options,
                                expand=True,
                            )
                            _bi_spell_dds.append(dd)
                            borrowed_initial_spell_refs.append((dd, False))
                        _dd_free = ft.Dropdown(
                            label="Incantesimo 3/3 (qualsiasi scuola)",
                            options=[],
                            bgcolor=COLOR_BG_CARD, color=COLOR_TEXT_PRIMARY,
                            label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=12),
                            border_color=COLOR_BORDER,
                            focused_border_color=COLOR_ACCENT_BLUE,
                            on_select=_refresh_borrowed_initial_options,
                            expand=True,
                        )
                        _bi_spell_dds.append(_dd_free)
                        borrowed_initial_spell_refs.append((_dd_free, _lv3_is_unrestricted))
                        _refresh_borrowed_initial_options()

                        _bi_rows: list[ft.Control] = [
                            ft.Divider(color=COLOR_BORDER),
                            ft.Row([
                                ft.Icon(ft.Icons.AUTO_AWESOME, size=14, color=COLOR_ACCENT_BLUE),
                                ft.Text("Incantesimi da Mago (Lv.3)", size=13,
                                        weight=ft.FontWeight.BOLD, color=COLOR_ACCENT_BLUE,
                                        expand=True),
                            ], spacing=6),
                        ]
                        if _fixed_cantrip:
                            _bi_rows.append(muted_text(
                                f"Trucchetto fisso: {_fixed_cantrip} (automatico)", size=11,
                            ))
                        describe_bi_cantrip = make_spell_describe([
                            s for s in _loader.get_spells_by_level("Mago", 0)
                            if s.get("name") in _cantrip_pool
                        ])
                        describe_bi_spell = make_spell_describe(_loader.get_spells_by_level("Mago", 1))
                        _bi_rows += [
                            dropdown_with_info(lambda: self._page, dd, describe_bi_cantrip)
                            for dd in _bi_cantrip_dds
                        ]
                        _bi_rows.append(muted_text(
                            "2 incantesimi di 1° livello vincolati per scuola + 1 libero.",
                            size=11,
                        ))
                        _bi_rows += [
                            dropdown_with_info(lambda: self._page, dd, describe_bi_spell)
                            for dd in _bi_spell_dds
                        ]

                        _bi_container = ft.Container(
                            content=ft.Column(_bi_rows, spacing=8),
                            visible=(_sc_dd.value == _borrowed_name),
                        )
                        borrowed_initial_container_ref.append(_bi_container)
                        dlg_rows.append(_bi_container)

                        def _on_sc_select(ev: Any, _cont: ft.Container = _bi_container,
                                          _name: str = _borrowed_name, _dd: ft.Dropdown = _sc_dd) -> None:
                            _cont.visible = (_dd.value == _name)
                            try:
                                _cont.update()
                            except RuntimeError:
                                pass

                        _sc_dd.on_select = _on_sc_select

                    # ------------------------------------------------------
                    # Monaco, Via dei Quattro Elementi: scelta INIZIALE di
                    # Lv.3 — Sintonia Elementale automatica (sempre inclusa,
                    # gratuita) + 1 disciplina elementale aggiuntiva a scelta
                    # (PHB IT p.93, "Discepolo degli Elementi": "Il monaco
                    # conosce la disciplina Sintonia Elementale e un'altra
                    # disciplina elementale a sua scelta"). Stesso motivo del
                    # blocco Mistificatore Arcano/Cavaliere Mistico sopra: la
                    # scelta va fatta nello STESSO level-up in cui si sceglie
                    # la sottoclasse, quindi la visibilità segue dal vivo il
                    # valore del dropdown sottoclasse. Monaco non è mai una
                    # classe "borrowed caster" (get_borrowed_caster_subclass_
                    # name("Monaco") == ""), quindi _sc_dd.on_select non è
                    # ancora stato impostato da nessun altro blocco a questo
                    # punto — assegnazione diretta, nessuna composizione
                    # necessaria. Aggiunto 2026-07-16.
                    # ------------------------------------------------------
                    _MK3_SUBCLASS = "Via dei Quattro Elementi"
                    if c.class_name == "Monaco" and _MK3_SUBCLASS in subclasses:
                        _mk3_data = _loader.get_subclass_data("Monaco", _MK3_SUBCLASS) or {}
                        _mk3_all = _mk3_data.get("disciplines", [])
                        _mk3_fixed = "Sintonia Elementale"
                        _mk3_pool = sorted(
                            (d for d in _mk3_all
                             if d.get("level") is None and d.get("name") != _mk3_fixed),
                            key=lambda d: d.get("name", ""),
                        )
                        mk3_dd = ft.Dropdown(
                            label="Disciplina Elementale aggiuntiva",
                            options=[ft.DropdownOption(key=d["name"], text=d["name"])
                                     for d in _mk3_pool],
                            bgcolor=COLOR_BG_CARD, color=COLOR_TEXT_PRIMARY,
                            label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=12),
                            border_color=COLOR_BORDER,
                            focused_border_color=COLOR_ACCENT_AMBER,
                            expand=True,
                        )
                        describe_mk3 = make_named_option_describe(_mk3_all)
                        _mk3_container = ft.Container(
                            content=ft.Column([
                                ft.Divider(color=COLOR_BORDER),
                                ft.Row([
                                    ft.Icon(ft.Icons.SELF_IMPROVEMENT, size=14, color=COLOR_ACCENT_AMBER),
                                    ft.Text("Discepolo degli Elementi (Lv.3)", size=13,
                                            weight=ft.FontWeight.BOLD, color=COLOR_ACCENT_AMBER,
                                            expand=True),
                                ], spacing=6),
                                muted_text(f"Disciplina fissa: {_mk3_fixed} (automatica).", size=11),
                                dropdown_with_info(lambda: self._page, mk3_dd, describe_mk3),
                            ], spacing=8),
                            visible=(_sc_dd.value == _MK3_SUBCLASS),
                        )
                        dlg_rows.append(_mk3_container)
                        monk_initial_discipline_refs.append(mk3_dd)

                        def _on_sc_select_monk(ev: Any, _cont: ft.Container = _mk3_container,
                                                _dd: ft.Dropdown = _sc_dd) -> None:
                            _cont.visible = (_dd.value == _MK3_SUBCLASS)
                            try:
                                _cont.update()
                            except RuntimeError:
                                pass

                        _sc_dd.on_select = _on_sc_select_monk
                else:
                    dlg_rows.append(ft.Container(
                        content=ft.Row([
                            ft.Icon(ft.Icons.STAR, size=14, color=COLOR_ACCENT_AMBER),
                            ft.Text(step.label, size=12, color=COLOR_TEXT_PRIMARY, expand=True),
                        ], spacing=6),
                        bgcolor="#fef9ec",
                        padding=ft.Padding.symmetric(horizontal=10, vertical=6),
                        border_radius=4,
                        border=ft.Border.all(1, COLOR_ACCENT_AMBER),
                    ))

            elif step.step_type == StepType.ASI:
                has_asi = True
                dlg_rows += [
                    ft.Divider(color=COLOR_BORDER),
                    ft.Text(f"Miglioramento Caratteristiche — Lv.{new_level}",
                            size=13, weight=ft.FontWeight.BOLD, color=COLOR_ACCENT_BLUE),
                    ft.Text("Scegli come distribuire i 2 punti, oppure prendi un Talento.",
                            size=12, color=COLOR_TEXT_SECONDARY),
                    asi_type,
                    stat_dd1,
                    stat_dd2,
                    feat_dd_row,
                    feat_bonus_dd,
                ]

            elif step.step_type == StepType.PACT_CHOICE:
                if not c.pact_boon:
                    pact_boons = _loader.get_pact_boons()
                    describe_pact = make_named_option_describe(_loader.get_pact_boon_data())
                    pact_rg = ft.RadioGroup(
                        content=ft.Column([
                            ft.Row(
                                [ft.Radio(value=b, label=b), _make_info_icon(describe_pact, b)],
                                spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            )
                            for b in pact_boons
                        ], spacing=4),
                        value=pact_boons[0] if pact_boons else "",
                    )
                    pact_rg_ref.append(pact_rg)
                    dlg_rows += [
                        ft.Divider(color=COLOR_BORDER),
                        ft.Row([
                            ft.Icon(ft.Icons.BOOK, size=14, color=COLOR_ACCENT_CRIMSON),
                            ft.Text("Dono del Patto — scegli il tuo patto",
                                    size=13, weight=ft.FontWeight.BOLD,
                                    color=COLOR_ACCENT_CRIMSON),
                        ], spacing=6),
                        muted_text("Determina il tipo di patto con il tuo Patrono.", size=11),
                        pact_rg,
                    ]
                else:
                    dlg_rows.append(ft.Container(
                        content=ft.Row([
                            ft.Icon(ft.Icons.BOOK, size=14, color=COLOR_ACCENT_CRIMSON),
                            ft.Text(f"Dono del Patto: {c.pact_boon} (già scelto)",
                                    size=12, color=COLOR_TEXT_PRIMARY, expand=True),
                        ], spacing=6),
                        bgcolor=COLOR_BG_SECONDARY, padding=8, border_radius=4,
                        border=ft.Border.all(1, COLOR_BORDER),
                    ))

            elif step.step_type == StepType.METAMAGIC:
                count = step.data.get("count", 2)
                known_mm = {
                    p.name for p in _all_profs
                    if p.proficiency_type == "metamagic"
                }
                available_mm = [o for o in _loader.get_metamagic_options() if o not in known_mm]
                to_add_mm = min(count, len(available_mm))

                if available_mm:
                    mm_cbs: list[ft.Checkbox] = []
                    metamagic_cb_groups.append((to_add_mm, mm_cbs))
                    describe_mm = make_named_option_describe(_loader.get_metamagic_option_data())

                    def _make_mm_cb(name: str, cbs_ref: list, limit: int) -> ft.Control:
                        def on_toggle(ev):
                            if len([cb for cb in cbs_ref if cb.value]) > limit:
                                ev.control.value = False
                                try: ev.control.update()
                                except RuntimeError: pass
                        cb = ft.Checkbox(
                            label=name, value=False,
                            active_color="#7b1fa2",
                            on_change=on_toggle,
                        )
                        cbs_ref.append(cb)
                        return ft.Row([cb, _make_info_icon(describe_mm, name)],
                                      spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER)

                    mm_cb_widgets = [
                        _make_mm_cb(name, mm_cbs, to_add_mm)
                        for name in available_mm
                    ]
                    dlg_rows += [
                        ft.Divider(color=COLOR_BORDER),
                        ft.Row([
                            ft.Icon(ft.Icons.BOLT, size=14, color="#7b1fa2"),
                            ft.Text(f"Metamagia — scegli {to_add_mm} opzion{'e' if to_add_mm == 1 else 'i'}",
                                    size=13, weight=ft.FontWeight.BOLD, color="#7b1fa2"),
                        ], spacing=6),
                        muted_text(
                            f"Già note: {', '.join(known_mm) or 'nessuna'}." if known_mm
                            else "Prima scelta di Metamagia.", size=11),
                        ft.Column(cast(list[ft.Control], mm_cb_widgets), spacing=2),
                    ]
                else:
                    dlg_rows.append(ft.Container(
                        content=ft.Row([
                            ft.Icon(ft.Icons.BOLT, size=14, color="#7b1fa2"),
                            ft.Text(f"{step.label} — tutte le opzioni già note",
                                    size=12, color=COLOR_TEXT_PRIMARY, expand=True),
                        ], spacing=6),
                        bgcolor=COLOR_BG_SECONDARY, padding=8, border_radius=4,
                        border=ft.Border.all(1, COLOR_BORDER),
                    ))

            elif step.step_type == StepType.INVOCATION:
                total_inv = step.data.get("total", 0)
                # Conta invocazioni già note
                known_inv = {
                    p.name for p in _all_profs
                    if p.proficiency_type == "invocation"
                }
                to_add = max(0, total_inv - len(known_inv))
                # Invocazioni disponibili filtrate per livello
                available_inv = [
                    n for n in _loader.get_invocation_names(new_level)
                    if n not in known_inv
                ]

                if to_add > 0:
                    inv_cbs: list[ft.Checkbox] = []
                    invocation_cb_groups.append((to_add, inv_cbs))
                    describe_inv = make_invocation_describe(_loader.get_invocations(new_level))

                    def _make_inv_cb(name: str, cbs_ref: list, limit: int) -> ft.Control:
                        def on_toggle(ev):
                            selected = [cb for cb in cbs_ref if cb.value]
                            if len(selected) > limit:
                                ev.control.value = False
                                try: ev.control.update()
                                except RuntimeError: pass
                        cb = ft.Checkbox(
                            label=name, value=False,
                            active_color=COLOR_ACCENT_CRIMSON,
                            on_change=on_toggle,
                        )
                        cbs_ref.append(cb)

                        def _show_inv_info(ev, _name=name):
                            page = self._page
                            if page is None:
                                return
                            result = describe_inv(_name)
                            if result is None:
                                return
                            title, body = result
                            page.show_dialog(ft.AlertDialog(
                                title=ft.Text(title, size=14, weight=ft.FontWeight.BOLD,
                                              color=COLOR_TEXT_TITLE),
                                content=ft.Container(
                                    content=ft.Column(
                                        [ft.Text(body, size=13, color=COLOR_TEXT_PRIMARY,
                                                 selectable=True)],
                                        scroll=ft.ScrollMode.AUTO),
                                    width=360, height=320),
                                actions=[ft.TextButton("Chiudi", on_click=lambda ev2: page.pop_dialog())],
                                bgcolor=COLOR_BG_CARD,
                            ))

                        info_btn = ft.IconButton(
                            ft.Icons.INFO_OUTLINE, icon_size=18,
                            icon_color=COLOR_ACCENT_BLUE,
                            tooltip="Mostra descrizione",
                            on_click=_show_inv_info,
                            padding=ft.Padding.all(2),
                        )
                        return ft.Row([cb, info_btn], spacing=0,
                                       vertical_alignment=ft.CrossAxisAlignment.CENTER)

                    if available_inv:
                        inv_cb_widgets = [
                            _make_inv_cb(name, inv_cbs, to_add)
                            for name in available_inv
                        ]
                        dlg_rows += [
                            ft.Divider(color=COLOR_BORDER),
                            ft.Row([
                                ft.Icon(ft.Icons.AUTO_FIX_HIGH, size=14,
                                        color=COLOR_ACCENT_CRIMSON),
                                ft.Text(
                                    f"Suppliche Occulte — scegli {to_add} nuov{'a' if to_add == 1 else 'e'}",
                                    size=13, weight=ft.FontWeight.BOLD,
                                    color=COLOR_ACCENT_CRIMSON),
                            ], spacing=6),
                            muted_text(
                                f"Totale suppliche a Lv.{new_level}: {total_inv} "
                                f"(già note: {len(known_inv)}).",
                                size=11),
                            ft.Column(cast(list[ft.Control], inv_cb_widgets), spacing=2),
                        ]
                    else:
                        # JSON ancora vuoto — info generica
                        dlg_rows += [
                            ft.Divider(color=COLOR_BORDER),
                            ft.Container(
                                content=ft.Row([
                                    ft.Icon(ft.Icons.AUTO_FIX_HIGH, size=14,
                                            color=COLOR_ACCENT_CRIMSON),
                                    ft.Text(
                                        f"{step.label} (+{to_add} — scegli manualmente per ora)",
                                        size=12, color=COLOR_TEXT_PRIMARY, expand=True),
                                ], spacing=6),
                                bgcolor=COLOR_BG_SECONDARY,
                                padding=ft.Padding.symmetric(horizontal=10, vertical=6),
                                border_radius=4,
                                border=ft.Border.all(1, COLOR_BORDER),
                            ),
                        ]
                else:
                    # Nessuna nuova da scegliere (caso edge: downgrade/undo)
                    dlg_rows.append(ft.Container(
                        content=ft.Row([
                            ft.Icon(ft.Icons.AUTO_FIX_HIGH, size=14, color=COLOR_ACCENT_CRIMSON),
                            ft.Text(step.label, size=12, color=COLOR_TEXT_PRIMARY, expand=True),
                        ], spacing=6),
                        bgcolor=COLOR_BG_SECONDARY,
                        padding=ft.Padding.symmetric(horizontal=10, vertical=6),
                        border_radius=4,
                        border=ft.Border.all(1, COLOR_BORDER),
                    ))

            elif step.step_type == StepType.EXPERTISE:
                count = step.data.get("count", 2)
                if _expertise_candidates:
                    cbs: list[ft.Checkbox] = []
                    expertise_cb_groups.append(cbs)

                    def _make_expertise_cb(name: str, cbs_ref: list) -> ft.Checkbox:
                        def on_toggle(ev):
                            # Limita la selezione a `count`
                            selected = [cb for cb in cbs_ref if cb.value]
                            if len(selected) > count:
                                ev.control.value = False
                                try: ev.control.update()
                                except RuntimeError: pass
                        cb = ft.Checkbox(
                            label=name, value=False,
                            active_color=COLOR_ACCENT_BLUE,
                            on_change=on_toggle,
                        )
                        cbs_ref.append(cb)
                        return cb

                    cb_widgets = [
                        _make_expertise_cb(name, cbs)
                        for name in _expertise_candidates
                    ]
                    dlg_rows += [
                        ft.Divider(color=COLOR_BORDER),
                        ft.Row([
                            ft.Icon(ft.Icons.STAR_HALF, size=14, color=COLOR_ACCENT_AMBER),
                            ft.Text(f"Maestria — scegli {count} abilità aggiuntive",
                                    size=13, weight=ft.FontWeight.BOLD,
                                    color=COLOR_ACCENT_AMBER),
                        ], spacing=6),
                        muted_text("Raddoppia il bonus competenza su queste abilità.", size=11),
                        ft.Column(cast(list[ft.Control], cb_widgets), spacing=2),
                    ]
                else:
                    # Nessuna competenza senza maestria — mostro solo info
                    dlg_rows.append(ft.Container(
                        content=ft.Row([
                            ft.Icon(ft.Icons.STAR_HALF, size=14, color=COLOR_ACCENT_AMBER),
                            ft.Text(step.label, size=12, color=COLOR_TEXT_PRIMARY, expand=True),
                        ], spacing=6),
                        bgcolor=COLOR_BG_SECONDARY,
                        padding=ft.Padding.symmetric(horizontal=10, vertical=6),
                        border_radius=4,
                        border=ft.Border.all(1, COLOR_BORDER),
                    ))

            elif step.step_type == StepType.SPELL_LEARN:
                any_class = step.data.get("any_class", False)
                count     = step.data.get("count", 1)
                max_lv    = step.data.get("max_level", 9)

                dlg_rows += [
                    ft.Divider(color=COLOR_BORDER),
                    ft.Row([
                        ft.Icon(ft.Icons.AUTO_AWESOME, size=14, color=COLOR_ACCENT_BLUE),
                        ft.Text(step.label, size=13, weight=ft.FontWeight.BOLD,
                                color=COLOR_ACCENT_BLUE, expand=True),
                    ], spacing=6),
                ]

                if any_class:
                    # Segreti Magici: dialog interattivo con chip-classi + lista
                    _known_ms: set[str] = {
                        ks.name for ks in character_repo.get_known_spells(c.id)
                    }
                    _ms_choices: list[tuple[str, str]] = []  # [(spell_name, class_name)]
                    _ALL_SPELL_CLASSES = [
                        "Bardo","Chierico","Druido","Mago",
                        "Paladino","Ranger","Stregone","Warlock",
                    ]

                    status_text = ft.Text(
                        f"0/{count} incantesimi scelti",
                        size=12, color=COLOR_TEXT_MUTED, italic=True,
                    )
                    badges_row = ft.Row([], spacing=6, wrap=True)

                    def _open_ms_picker(
                        ev,
                        _cnt: int = count,
                        _ml: int = max_lv,
                        _lbl: str = step.label,
                        _kn: set = _known_ms,
                        _choices: list = _ms_choices,
                        _st: ft.Text = status_text,
                        _br: ft.Row = badges_row,
                    ) -> None:
                        if not self._page:
                            return
                        _pg = self._page
                        _active_cls: list[str] = [_ALL_SPELL_CLASSES[0]]
                        _chosen: list[tuple[str, str]] = list(_choices)

                        counter_txt = ft.Text(
                            f"{len(_chosen)}/{_cnt}",
                            size=13, weight=ft.FontWeight.BOLD,
                            color=COLOR_ACCENT_BLUE if len(_chosen) == _cnt
                            else COLOR_TEXT_MUTED,
                        )
                        confirm_btn_ref: list[ft.ElevatedButton] = []
                        chip_refs: dict[str, ft.Container] = {}
                        spell_col = ft.Column(
                            [], spacing=0, scroll=ft.ScrollMode.AUTO,
                        )
                        spell_area = ft.Container(
                            content=spell_col, height=220,
                        )

                        def _rebuild_spell_list() -> None:
                            cls = _active_cls[0]
                            chosen_names = {n for n, _ in _chosen}
                            spells_for_cls = sorted(
                                [s for s in _loader.get_spells(cls)
                                 if 0 < s.get("level", 0) <= _ml
                                 and s.get("name") not in _kn],
                                key=lambda s: (s.get("level", 0), s.get("name", "")),
                            )
                            rows: list[ft.Control] = []
                            cur_lv = -1
                            for sp in spells_for_cls:
                                lv = sp.get("level", 0)
                                nm = sp.get("name", "")
                                is_chosen = nm in chosen_names
                                at_limit = (len(_chosen) >= _cnt) and not is_chosen

                                if lv != cur_lv:
                                    cur_lv = lv
                                    rows.append(ft.Container(
                                        content=ft.Text(
                                            f"Livello {lv}",
                                            size=10, color=COLOR_TEXT_MUTED,
                                            weight=ft.FontWeight.BOLD,
                                        ),
                                        padding=ft.Padding.only(
                                            top=8, bottom=2, left=4
                                        ),
                                    ))

                                def _toggle(ev, spell=sp, cls_nm=cls):
                                    sn = spell["name"]
                                    idx = next(
                                        (i for i, (n, _) in enumerate(_chosen) if n == sn),
                                        None,
                                    )
                                    if idx is not None:
                                        _chosen.pop(idx)
                                    elif len(_chosen) < _cnt:
                                        _chosen.append((sn, cls_nm))
                                    _refresh_picker()

                                def _show_spell_info(ev, spell=sp) -> None:
                                    # ⓘ — mostra la descrizione completa dell'incantesimo
                                    # PRIMA che il giocatore lo scelga (2026-07-16,
                                    # richiesta Davide). Icona separata dal resto della
                                    # riga: il tap non attiva anche _toggle.
                                    if not _pg:
                                        return
                                    _pg.show_dialog(ft.AlertDialog(
                                        title=ft.Text(spell.get("name", ""), size=14,
                                                      weight=ft.FontWeight.BOLD,
                                                      color=COLOR_TEXT_TITLE),
                                        content=ft.Container(
                                            content=ft.Column(
                                                [ft.Text(format_spell_body(spell), size=13,
                                                        color=COLOR_TEXT_PRIMARY, selectable=True)],
                                                scroll=ft.ScrollMode.AUTO,
                                            ),
                                            width=340, height=300,
                                        ),
                                        actions=[ft.TextButton(
                                            "Chiudi", on_click=lambda e: _pg.pop_dialog(),
                                        )],
                                        bgcolor=COLOR_BG_CARD,
                                    ))

                                rows.append(ft.Container(
                                    content=ft.Row([
                                        ft.Text(
                                            "●" if is_chosen else ("—" if at_limit else "○"),
                                            size=20,
                                            color=(
                                                COLOR_ACCENT_CRIMSON if is_chosen
                                                else (COLOR_BORDER if at_limit
                                                      else COLOR_TEXT_MUTED)
                                            ),
                                        ),
                                        ft.Container(width=6),
                                        ft.Column([
                                            ft.Text(
                                                nm, size=13, expand=True,
                                                color=(COLOR_TEXT_MUTED if at_limit
                                                       else COLOR_TEXT_PRIMARY),
                                                weight=(ft.FontWeight.W_600 if is_chosen
                                                        else ft.FontWeight.NORMAL),
                                            ),
                                            ft.Text(
                                                f"Lv{lv}  ·  {sp.get('school', '')}",
                                                size=10, color=COLOR_TEXT_MUTED,
                                            ),
                                        ], spacing=1, expand=True),
                                        ft.IconButton(
                                            ft.Icons.INFO_OUTLINE, icon_size=16,
                                            icon_color=COLOR_ACCENT_BLUE,
                                            tooltip="Mostra descrizione",
                                            on_click=_show_spell_info,
                                            padding=ft.Padding.all(2),
                                        ),
                                    ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                                    on_click=None if at_limit else _toggle,
                                    ink=not at_limit,
                                    border=ft.Border(
                                        bottom=ft.BorderSide(1, COLOR_BORDER)
                                    ),
                                    padding=ft.Padding.symmetric(
                                        vertical=6, horizontal=4
                                    ),
                                ))

                            if not rows:
                                rows.append(ft.Container(
                                    content=ft.Text(
                                        "Nessun incantesimo disponibile.",
                                        size=12, color=COLOR_TEXT_MUTED, italic=True,
                                    ),
                                    padding=20,
                                ))

                            spell_col.controls.clear()
                            for r in rows:
                                spell_col.controls.append(r)
                            try:
                                spell_area.update()
                            except RuntimeError:
                                pass

                        def _refresh_picker() -> None:
                            n = len(_chosen)
                            counter_txt.value = f"{n}/{_cnt}"
                            counter_txt.color = (
                                COLOR_ACCENT_BLUE if n == _cnt else COLOR_TEXT_MUTED
                            )
                            if confirm_btn_ref:
                                confirm_btn_ref[0].disabled = (n != _cnt)
                            # Chip: evidenzia attivo + badge verde se ha scelte
                            cls_counts: dict[str, int] = {}
                            for _, cn in _chosen:
                                cls_counts[cn] = cls_counts.get(cn, 0) + 1
                            for cls_name, chip in chip_refs.items():
                                is_active = cls_name == _active_cls[0]
                                has_picks = cls_counts.get(cls_name, 0) > 0
                                chip.bgcolor = (
                                    COLOR_ACCENT_BLUE if is_active
                                    else ("#d4edda" if has_picks else COLOR_BG_SECONDARY)
                                )
                                chip.border = ft.Border.all(
                                    2 if has_picks else 1,
                                    COLOR_ACCENT_BLUE if is_active
                                    else ("#2e7d32" if has_picks else COLOR_BORDER),
                                )
                            _rebuild_spell_list()
                            try:
                                counter_txt.update()
                                if confirm_btn_ref:
                                    confirm_btn_ref[0].update()
                                for chip in chip_refs.values():
                                    chip.update()
                            except RuntimeError:
                                pass

                        def _on_chip_click(ev, cls: str) -> None:
                            _active_cls[0] = cls
                            _refresh_picker()

                        # Build class chips
                        chip_controls: list[ft.Control] = []
                        for cls_n in _ALL_SPELL_CLASSES:
                            is_active = cls_n == _active_cls[0]
                            chip = ft.Container(
                                content=ft.Text(
                                    cls_n, size=11,
                                    color="#ffffff" if is_active else COLOR_TEXT_SECONDARY,
                                    weight=ft.FontWeight.BOLD,
                                    text_align=ft.TextAlign.CENTER,
                                ),
                                bgcolor=COLOR_ACCENT_BLUE if is_active else COLOR_BG_SECONDARY,
                                padding=ft.Padding.symmetric(horizontal=10, vertical=5),
                                border_radius=14,
                                border=ft.Border.all(
                                    1, COLOR_ACCENT_BLUE if is_active else COLOR_BORDER
                                ),
                                on_click=lambda ev, c=cls_n: _on_chip_click(ev, c),
                                ink=True,
                            )
                            chip_refs[cls_n] = chip
                            chip_controls.append(chip)

                        _rebuild_spell_list()

                        def _confirm(ev):
                            _choices.clear()
                            _choices.extend(_chosen)
                            n = len(_chosen)
                            _st.value = f"{n}/{_cnt} incantesimi scelti"
                            _st.color = (
                                COLOR_ACCENT_BLUE if n == _cnt else COLOR_TEXT_MUTED
                            )
                            _br.controls.clear()
                            for sn, cn in _chosen:
                                _br.controls.append(ft.Container(
                                    content=ft.Row([
                                        ft.Text(sn, size=11, color="#ffffff", expand=True),
                                        ft.Text(f"({cn[:4]})", size=10, color="#aaccff"),
                                    ], spacing=4),
                                    bgcolor=COLOR_ACCENT_BLUE,
                                    padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                                    border_radius=12,
                                ))
                            try:
                                _st.update()
                                _br.update()
                            except RuntimeError:
                                pass
                            _pg.pop_dialog()

                        confirm_btn = ft.ElevatedButton(
                            "Conferma",
                            disabled=len(_chosen) != _cnt,
                            on_click=_confirm,
                            style=ft.ButtonStyle(
                                bgcolor=COLOR_ACCENT_BLUE, color="#ffffff",
                                shape=ft.RoundedRectangleBorder(radius=4),
                            ),
                        )
                        confirm_btn_ref.append(confirm_btn)

                        _pg.show_dialog(ft.AlertDialog(
                            title=ft.Row([
                                ft.Icon(ft.Icons.AUTO_AWESOME, color=COLOR_ACCENT_BLUE, size=16),
                                ft.Container(width=6),
                                ft.Text(
                                    _lbl, size=13, weight=ft.FontWeight.BOLD,
                                    color=COLOR_TEXT_TITLE, expand=True,
                                ),
                            ]),
                            content=ft.Column([
                                ft.Text(
                                    f"Scegli {_cnt} incantesimi  ·  max livello {_ml}°",
                                    size=11, color=COLOR_TEXT_MUTED, italic=True,
                                ),
                                ft.Container(height=4),
                                ft.Row(chip_controls, wrap=True, spacing=6, run_spacing=6),
                                ft.Divider(color=COLOR_BORDER),
                                spell_area,
                                ft.Divider(color=COLOR_BORDER),
                                ft.Row([
                                    ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE,
                                            size=14, color=COLOR_TEXT_MUTED),
                                    ft.Container(width=4),
                                    counter_txt,
                                ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                            ], spacing=6),
                            actions=[
                                ft.TextButton(
                                    "Annulla",
                                    on_click=lambda ev: _pg.pop_dialog() if _pg else None,
                                ),
                                confirm_btn,
                            ],
                            bgcolor=COLOR_BG_CARD,
                        ))

                    dlg_rows += [
                        ft.OutlinedButton(
                            f"✨  Scegli {count} incantesimi — qualsiasi lista",
                            on_click=_open_ms_picker,
                            style=ft.ButtonStyle(
                                color=COLOR_ACCENT_BLUE,
                                side=ft.BorderSide(1, COLOR_ACCENT_BLUE),
                                shape=ft.RoundedRectangleBorder(radius=6),
                            ),
                        ),
                        status_text,
                        badges_row,
                    ]
                    magical_secrets_refs.append((step.data, _ms_choices))

                else:
                    # Classe "know" normale: scegli dalla lista della classe
                    _known_set: set[str] = {
                        ks.name for ks in character_repo.get_known_spells(c.id)
                    }
                    # Lista Incantesimi Ampliata (Warlock, task #25, 2026-07-16)
                    # — aggiunge al pool i nomi patrono-specifici (es. Il
                    # Signore Fatato → Luminescenza/Sonno/...), MAI incantesimi
                    # gratuiti: il giocatore deve comunque scegliere di
                    # "spenderci" uno slot conosciuto, esattamente come per un
                    # incantesimo della lista base. No-op per qualunque altra
                    # classe/sottoclasse (get_expanded_spells ritorna []).
                    _expanded = _loader.get_expanded_spells(c.class_name or "", c.subclass or "")
                    _base_names = {s.get("name") for s in _loader.get_spells(c.class_name or "")}
                    eligible_spells = [
                        s for s in _loader.get_spells(c.class_name or "") + [
                            s for s in _expanded if s.get("name") not in _base_names
                        ]
                        if 0 < s.get("level", 0) <= max_lv
                        and s.get("name") not in _known_set
                    ]
                    eligible_spells.sort(
                        key=lambda s: (s.get("level", 0), s.get("name", ""))
                    )
                    spell_opts = [
                        ft.DropdownOption(
                            key=s["name"],
                            text=f"[Lv{s['level']}] {s['name']}",
                        )
                        for s in eligible_spells
                    ]
                    describe_learn = make_spell_describe(eligible_spells)
                    dds: list[ft.Dropdown] = []
                    for i in range(count):
                        dd = ft.Dropdown(
                            label=f"Incantesimo {i + 1}/{count}",
                            hint_text="Scegli dalla lista...",
                            options=spell_opts,
                            bgcolor=COLOR_BG_CARD, color=COLOR_TEXT_PRIMARY,
                            label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=12),
                            border_color=COLOR_BORDER,
                            focused_border_color=COLOR_ACCENT_BLUE,
                            expand=True,
                        )
                        dds.append(dd)
                        dlg_rows.append(dropdown_with_info(lambda: self._page, dd, describe_learn))
                    spell_learn_refs.append((step.data, dds))

            elif step.step_type == StepType.ARCANUM_SPELL:
                # Warlock, Arcanum Mistico (lv.11/13/15/17): un incantesimo di
                # livello ESATTO (non "fino a", a differenza di SPELL_LEARN),
                # lanciabile senza slot 1/riposo lungo. Stesso pattern del
                # ramo "else" di SPELL_LEARN sopra, filtro sul livello esatto.
                _arcanum_lv = step.data.get("spell_level", 6)
                _known_arcanum: set[str] = {
                    ks.name for ks in character_repo.get_known_spells(c.id)
                }
                eligible_arcanum = sorted(
                    (s for s in _loader.get_spells("Warlock")
                     if s.get("level", 0) == _arcanum_lv
                     and s.get("name") not in _known_arcanum),
                    key=lambda s: s.get("name", ""),
                )
                arcanum_dd = ft.Dropdown(
                    label=f"Arcanum Mistico ({_arcanum_lv}° livello)",
                    hint_text="Scegli dalla lista...",
                    options=[ft.DropdownOption(key=s["name"], text=s["name"])
                             for s in eligible_arcanum],
                    bgcolor=COLOR_BG_CARD, color=COLOR_TEXT_PRIMARY,
                    label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=12),
                    border_color=COLOR_BORDER,
                    focused_border_color=COLOR_ACCENT_BLUE,
                    expand=True,
                )
                describe_arcanum = make_spell_describe(eligible_arcanum)
                dlg_rows += [
                    ft.Divider(color=COLOR_BORDER),
                    ft.Row([
                        ft.Icon(ft.Icons.AUTO_AWESOME, size=14, color=COLOR_ACCENT_BLUE),
                        ft.Text(step.label, size=13, weight=ft.FontWeight.BOLD,
                                color=COLOR_ACCENT_BLUE, expand=True),
                    ], spacing=6),
                    dropdown_with_info(lambda: self._page, arcanum_dd, describe_arcanum),
                ]
                arcanum_spell_refs.append(arcanum_dd)

            elif step.step_type == StepType.MONK_DISCIPLINE:
                # Monaco, Via dei Quattro Elementi (lv.6/11/17): 1 disciplina
                # elementale aggiuntiva dal pool sbloccato a questo livello
                # (monaco.json → subclasses["Via dei Quattro Elementi"].
                # disciplines, campo "level": null = sempre disponibile da
                # Lv.3, altrimenti soglia minima). Esclude quelle già
                # conosciute (character_proficiencies "monk_discipline").
                _unlock_lv = step.data.get("unlock_level", new_level)
                _mk_subclass_data = _loader.get_subclass_data("Monaco", "Via dei Quattro Elementi") or {}
                _mk_all_disciplines = _mk_subclass_data.get("disciplines", [])
                _mk_known: set[str] = {
                    p.name for p in character_repo.get_proficiencies(c.id)
                    if p.proficiency_type == "monk_discipline"
                }
                _mk_eligible = sorted(
                    (d for d in _mk_all_disciplines
                     if (d.get("level") is None or d.get("level", 0) <= _unlock_lv)
                     and d.get("name") not in _mk_known),
                    key=lambda d: d.get("name", ""),
                )
                mk_dd = ft.Dropdown(
                    label="Nuova Disciplina Elementale",
                    hint_text="Scegli dalla lista...",
                    options=[ft.DropdownOption(key=d["name"], text=d["name"])
                             for d in _mk_eligible],
                    bgcolor=COLOR_BG_CARD, color=COLOR_TEXT_PRIMARY,
                    label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=12),
                    border_color=COLOR_BORDER,
                    focused_border_color=COLOR_ACCENT_AMBER,
                    expand=True,
                )
                describe_mk = make_named_option_describe(_mk_eligible)
                dlg_rows += [
                    ft.Divider(color=COLOR_BORDER),
                    ft.Row([
                        ft.Icon(ft.Icons.SELF_IMPROVEMENT, size=14, color=COLOR_ACCENT_AMBER),
                        ft.Text(step.label, size=13, weight=ft.FontWeight.BOLD,
                                color=COLOR_ACCENT_AMBER, expand=True),
                    ], spacing=6),
                    dropdown_with_info(lambda: self._page, mk_dd, describe_mk),
                ]
                monk_discipline_refs.append(mk_dd)

            elif step.step_type == StepType.SPELL_SWAP:
                # Sostituzione OPZIONALE di un incantesimo conosciuto — PHB IT,
                # stesso testo confermato per Bardo/Ranger/Stregone/Warlock:
                # "quando [la classe] acquisisce un livello, può scegliere un
                # incantesimo che conosce e sostituirlo con un altro". A
                # differenza di SPELL_LEARN non è mai obbligatoria: il
                # giocatore può lasciare la checkbox spenta e non succede
                # nulla. Il pool "da sostituire" è filtrato solo sugli
                # incantesimi che appartengono davvero alla lista della
                # classe (esclude i trucchetti, che non hanno slot, ed
                # esclude eventuali incantesimi noti tramite Segreti Magici
                # del Bardo — "da qualsiasi classe", non "da bardo").
                max_lv = step.data.get("max_level", 9)
                # Lista Incantesimi Ampliata (Warlock, task #25, 2026-07-16) —
                # un incantesimo appreso in precedenza da questa lista (via
                # SPELL_LEARN, vedi sopra) deve poter essere sostituito qui
                # come un qualunque altro incantesimo "da warlock" — PHB:
                # "questi incantesimi sono considerati incantesimi da warlock
                # per [il patrono]". No-op per qualunque altra classe.
                _swap_expanded = _loader.get_expanded_spells(c.class_name or "", c.subclass or "")
                class_spell_names = {
                    s.get("name", "") for s in _loader.get_spells(c.class_name or "") + _swap_expanded
                }
                known_class_spells = sorted(
                    (
                        ks for ks in character_repo.get_known_spells(c.id)
                        if ks.spell_level > 0 and ks.name in class_spell_names
                    ),
                    key=lambda k: (k.spell_level, k.name),
                )
                known_names_all = {k.name for k in known_class_spells}

                swap_enable_cb = ft.Checkbox(
                    label="Sostituisci un incantesimo conosciuto",
                    value=False,
                )
                dd_remove = ft.Dropdown(
                    label="Incantesimo da sostituire",
                    options=[
                        ft.DropdownOption(key=k.name, text=f"[Lv{k.spell_level}] {k.name}")
                        for k in known_class_spells
                    ],
                    disabled=True,
                    bgcolor=COLOR_BG_CARD, color=COLOR_TEXT_PRIMARY,
                    label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=12),
                    border_color=COLOR_BORDER,
                    focused_border_color=COLOR_ACCENT_BLUE,
                    expand=True,
                )
                dd_add = ft.Dropdown(
                    label="Nuovo incantesimo",
                    options=[],
                    disabled=True,
                    bgcolor=COLOR_BG_CARD, color=COLOR_TEXT_PRIMARY,
                    label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=12),
                    border_color=COLOR_BORDER,
                    focused_border_color=COLOR_ACCENT_BLUE,
                    expand=True,
                )

                def _refresh_swap_add_options(
                    ev: Any = None, _rm: ft.Dropdown = dd_remove,
                    _add: ft.Dropdown = dd_add, _cls: str = c.class_name or "",
                    _ml: int = max_lv, _known: set = known_names_all,
                    _expanded: list = _swap_expanded,
                ) -> None:
                    excluded = set(_known)
                    excluded.discard(_rm.value or "")
                    _base_names_swap = {s.get("name") for s in _loader.get_spells(_cls)}
                    _pool_swap = _loader.get_spells(_cls) + [
                        s for s in _expanded if s.get("name") not in _base_names_swap
                    ]
                    eligible = sorted(
                        (s for s in _pool_swap
                         if 0 < s.get("level", 0) <= _ml
                         and s.get("name") not in excluded),
                        key=lambda s: (s.get("level", 0), s.get("name", "")),
                    )
                    _add.options = [
                        ft.DropdownOption(key=s["name"], text=f"[Lv{s['level']}] {s['name']}")
                        for s in eligible
                    ]
                    if _add.value not in {o.key for o in _add.options}:
                        _add.value = None
                    try:
                        _add.update()
                    except RuntimeError:
                        pass

                def _on_swap_toggle(
                    ev: Any, _cb: ft.Checkbox = swap_enable_cb,
                    _rm: ft.Dropdown = dd_remove, _add: ft.Dropdown = dd_add,
                ) -> None:
                    enabled = bool(_cb.value)
                    _rm.disabled = not enabled
                    _add.disabled = not enabled
                    if not enabled:
                        _rm.value = None
                        _add.value = None
                    _refresh_swap_add_options()
                    try:
                        _rm.update()
                        _add.update()
                    except RuntimeError:
                        pass

                def _on_swap_remove_select(ev: Any) -> None:
                    _refresh_swap_add_options()

                swap_enable_cb.on_change = _on_swap_toggle
                dd_remove.on_select = _on_swap_remove_select
                _refresh_swap_add_options()

                if not known_class_spells:
                    swap_enable_cb.disabled = True
                    swap_enable_cb.label = "Sostituisci un incantesimo conosciuto (nessuno disponibile)"

                describe_swap_remove = make_spell_describe([
                    _loader.get_spell_by_name(k.name, c.class_name) or
                    {"name": k.name, "level": k.spell_level}
                    for k in known_class_spells
                ])
                describe_swap_add = make_spell_describe([
                    s for s in _loader.get_spells(c.class_name or "")
                    if 0 < s.get("level", 0) <= max_lv
                ])

                dlg_rows += [
                    ft.Divider(color=COLOR_BORDER),
                    ft.Row([
                        ft.Icon(ft.Icons.AUTO_AWESOME, size=14, color=COLOR_ACCENT_BLUE),
                        ft.Text(step.label, size=13, weight=ft.FontWeight.BOLD,
                                color=COLOR_ACCENT_BLUE, expand=True),
                    ], spacing=6),
                    swap_enable_cb,
                    dropdown_with_info(lambda: self._page, dd_remove, describe_swap_remove),
                    dropdown_with_info(lambda: self._page, dd_add, describe_swap_add),
                ]
                spell_swap_refs.append((swap_enable_cb, dd_remove, dd_add))

            elif step.step_type == StepType.CANTRIP_LEARN:
                # Nuovo trucchetto conosciuto ai lv.4/10 (Bardo/Chierico/
                # Druido/Mago/Stregone/Warlock — colonna "Trucchetti
                # Conosciuti" delle tabelle di classe PHB, vedi
                # core/level_manager.py). Stesso pattern minimale di
                # SPELL_LEARN ma filtrato su spell_level == 0 (trucchetti,
                # niente slot/livello massimo) ed escludendo i trucchetti
                # già conosciuti dal personaggio.
                _known_cantrips: set[str] = {
                    ks.name for ks in character_repo.get_known_spells(c.id)
                    if ks.spell_level == 0
                }
                _eligible_cantrips = sorted(
                    (s for s in _loader.get_spells(c.class_name or "")
                     if s.get("level", 0) == 0 and s.get("name") not in _known_cantrips),
                    key=lambda s: s.get("name", ""),
                )
                cantrip_dd = ft.Dropdown(
                    label="Nuovo trucchetto",
                    hint_text="Scegli dalla lista...",
                    options=[
                        ft.DropdownOption(key=s["name"], text=s["name"])
                        for s in _eligible_cantrips
                    ],
                    bgcolor=COLOR_BG_CARD, color=COLOR_TEXT_PRIMARY,
                    label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=12),
                    border_color=COLOR_BORDER,
                    focused_border_color=COLOR_ACCENT_BLUE,
                    expand=True,
                )
                dlg_rows += [
                    ft.Divider(color=COLOR_BORDER),
                    ft.Row([
                        ft.Icon(ft.Icons.AUTO_AWESOME, size=14, color=COLOR_ACCENT_BLUE),
                        ft.Text(step.label, size=13, weight=ft.FontWeight.BOLD,
                                color=COLOR_ACCENT_BLUE, expand=True),
                    ], spacing=6),
                    dropdown_with_info(
                        lambda: self._page, cantrip_dd, make_spell_describe(_eligible_cantrips)
                    ),
                ]
                cantrip_learn_refs.append(cantrip_dd)

            elif step.step_type == StepType.BORROWED_CANTRIP:
                # Nuovo trucchetto da mago (Mistificatore Arcano/Cavaliere
                # Mistico, lv.10) — stesso pattern minimale di CANTRIP_LEARN,
                # ma il pool è cantrip_options della sottoclasse (16 nomi
                # condivisi Ladro/Guerriero), non la lista propria di classe
                # (che per Ladro/Guerriero è sempre vuota).
                _bc_data_cl = _loader.get_borrowed_caster_data(c.class_name or "", c.subclass or "") or {}
                _bc_fixed = _bc_data_cl.get("fixed_cantrip") or ""
                _bc_pool_cl = [n for n in _bc_data_cl.get("cantrip_options", []) if n != _bc_fixed]
                _known_borrowed_cantrips: set[str] = {
                    ks.name for ks in character_repo.get_known_spells(c.id) if ks.spell_level == 0
                }
                _eligible_bc = [n for n in _bc_pool_cl if n not in _known_borrowed_cantrips]
                bc_cantrip_dd = ft.Dropdown(
                    label="Nuovo trucchetto da mago",
                    hint_text="Scegli dalla lista...",
                    options=[ft.DropdownOption(key=n, text=n) for n in _eligible_bc],
                    bgcolor=COLOR_BG_CARD, color=COLOR_TEXT_PRIMARY,
                    label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=12),
                    border_color=COLOR_BORDER,
                    focused_border_color=COLOR_ACCENT_BLUE,
                    expand=True,
                )
                dlg_rows += [
                    ft.Divider(color=COLOR_BORDER),
                    ft.Row([
                        ft.Icon(ft.Icons.AUTO_AWESOME, size=14, color=COLOR_ACCENT_BLUE),
                        ft.Text(step.label, size=13, weight=ft.FontWeight.BOLD,
                                color=COLOR_ACCENT_BLUE, expand=True),
                    ], spacing=6),
                    dropdown_with_info(
                        lambda: self._page, bc_cantrip_dd,
                        make_spell_describe(_loader.get_spells_by_level("Mago", 0)),
                    ),
                ]
                borrowed_cantrip_dd_refs.append(bc_cantrip_dd)

            elif step.step_type == StepType.BORROWED_SPELL_LEARN:
                # Nuovo incantesimo da mago (Mistificatore Arcano/Cavaliere
                # Mistico) — vincolato per scuola tranne agli
                # unrestricted_origin_levels (8°/14°/20°, +3° per il
                # Cavaliere Mistico, gestito separatamente al lv3).
                _count_bsl      = step.data.get("count", 1)
                _max_lv_bsl     = step.data.get("max_level", 1)
                _restricted_bsl = step.data.get("restricted_schools", [])
                _unrestr_bsl    = step.data.get("unrestricted", False)
                _known_bsl: set[str] = {
                    ks.name for ks in character_repo.get_known_spells(c.id) if ks.spell_level > 0
                }
                _eligible_bsl = _borrowed_eligible_mago_spells(
                    _max_lv_bsl, _restricted_bsl, _unrestr_bsl, _known_bsl,
                )
                _opts_bsl = [
                    ft.DropdownOption(key=s["name"], text=f"[Lv{s['level']}] {s['name']}")
                    for s in _eligible_bsl
                ]
                dlg_rows += [
                    ft.Divider(color=COLOR_BORDER),
                    ft.Row([
                        ft.Icon(ft.Icons.AUTO_AWESOME, size=14, color=COLOR_ACCENT_BLUE),
                        ft.Text(step.label, size=13, weight=ft.FontWeight.BOLD,
                                color=COLOR_ACCENT_BLUE, expand=True),
                    ], spacing=6),
                ]
                describe_bsl = make_spell_describe(_eligible_bsl)
                for i in range(_count_bsl):
                    bsl_dd = ft.Dropdown(
                        label=f"Incantesimo da mago {i + 1}/{_count_bsl}",
                        hint_text="Scegli dalla lista...",
                        options=_opts_bsl,
                        bgcolor=COLOR_BG_CARD, color=COLOR_TEXT_PRIMARY,
                        label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=12),
                        border_color=COLOR_BORDER,
                        focused_border_color=COLOR_ACCENT_BLUE,
                        expand=True,
                    )
                    dlg_rows.append(dropdown_with_info(lambda: self._page, bsl_dd, describe_bsl))
                    borrowed_spell_learn_refs.append((bsl_dd, _unrestr_bsl))

            elif step.step_type == StepType.BORROWED_SPELL_SWAP:
                # Sostituzione OPZIONALE di un incantesimo da mago conosciuto
                # — stesso pattern di SPELL_SWAP, ma il rimpiazzo può essere
                # di qualsiasi scuola SOLO se l'incantesimo sostituito era
                # esso stesso un pick "libero" (origin_unrestricted=True in
                # known_spells) — altrimenti resta vincolato alle 2 scuole
                # della sottoclasse. Il flag si propaga sul nuovo incantesimo
                # (la "postazione" resta libera anche in futuro).
                _max_lv_swap = step.data.get("max_level", 1)
                _bc_data_swap = _loader.get_borrowed_caster_data(c.class_name or "", c.subclass or "") or {}
                _restricted_swap = _bc_data_swap.get("restricted_schools", [])
                _mago_names = {s.get("name", "") for s in _loader.get_spells("Mago")}
                _known_borrowed_spells = sorted(
                    (
                        ks for ks in character_repo.get_known_spells(c.id)
                        if ks.spell_level > 0 and ks.name in _mago_names
                    ),
                    key=lambda k: (k.spell_level, k.name),
                )
                _known_borrowed_names = {k.name for k in _known_borrowed_spells}
                _origin_by_name = {k.name: k.origin_unrestricted for k in _known_borrowed_spells}

                bsw_enable_cb = ft.Checkbox(
                    label="Sostituisci un incantesimo da mago conosciuto",
                    value=False,
                )
                bsw_dd_remove = ft.Dropdown(
                    label="Incantesimo da sostituire",
                    options=[
                        ft.DropdownOption(
                            key=k.name,
                            text=f"[Lv{k.spell_level}] {k.name}"
                            + ("  (libero da scuola)" if k.origin_unrestricted else ""),
                        )
                        for k in _known_borrowed_spells
                    ],
                    disabled=True,
                    bgcolor=COLOR_BG_CARD, color=COLOR_TEXT_PRIMARY,
                    label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=12),
                    border_color=COLOR_BORDER,
                    focused_border_color=COLOR_ACCENT_BLUE,
                    expand=True,
                )
                bsw_dd_add = ft.Dropdown(
                    label="Nuovo incantesimo da mago",
                    options=[],
                    disabled=True,
                    bgcolor=COLOR_BG_CARD, color=COLOR_TEXT_PRIMARY,
                    label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=12),
                    border_color=COLOR_BORDER,
                    focused_border_color=COLOR_ACCENT_BLUE,
                    expand=True,
                )

                def _refresh_bsw_add_options(
                    ev: Any = None, _rm: ft.Dropdown = bsw_dd_remove,
                    _add: ft.Dropdown = bsw_dd_add, _ml: int = _max_lv_swap,
                    _restricted: list = _restricted_swap,
                    _known: set = _known_borrowed_names,
                    _origin: dict = _origin_by_name,
                ) -> None:
                    excluded = set(_known)
                    excluded.discard(_rm.value or "")
                    # Il rimpiazzo è libero da vincolo di scuola solo se
                    # l'incantesimo sostituito lo era già.
                    replaced_unrestricted = _origin.get(_rm.value or "", False)
                    eligible = _borrowed_eligible_mago_spells(
                        _ml, _restricted, replaced_unrestricted, excluded,
                    )
                    _add.options = [
                        ft.DropdownOption(key=s["name"], text=f"[Lv{s['level']}] {s['name']}")
                        for s in eligible
                    ]
                    if _add.value not in {o.key for o in _add.options}:
                        _add.value = None
                    try:
                        _add.update()
                    except RuntimeError:
                        pass

                def _on_bsw_toggle(
                    ev: Any, _cb: ft.Checkbox = bsw_enable_cb,
                    _rm: ft.Dropdown = bsw_dd_remove, _add: ft.Dropdown = bsw_dd_add,
                ) -> None:
                    enabled = bool(_cb.value)
                    _rm.disabled = not enabled
                    _add.disabled = not enabled
                    if not enabled:
                        _rm.value = None
                        _add.value = None
                    _refresh_bsw_add_options()
                    try:
                        _rm.update()
                        _add.update()
                    except RuntimeError:
                        pass

                def _on_bsw_remove_select(ev: Any) -> None:
                    _refresh_bsw_add_options()

                bsw_enable_cb.on_change = _on_bsw_toggle
                bsw_dd_remove.on_select = _on_bsw_remove_select
                _refresh_bsw_add_options()

                if not _known_borrowed_spells:
                    bsw_enable_cb.disabled = True
                    bsw_enable_cb.label = "Sostituisci un incantesimo da mago conosciuto (nessuno disponibile)"

                describe_bsw_remove = make_spell_describe([
                    _loader.get_spell_by_name(k.name, "Mago") or
                    {"name": k.name, "level": k.spell_level}
                    for k in _known_borrowed_spells
                ])
                describe_bsw_add = make_spell_describe([
                    s for s in _loader.get_spells("Mago")
                    if 0 < s.get("level", 0) <= _max_lv_swap
                ])

                dlg_rows += [
                    ft.Divider(color=COLOR_BORDER),
                    ft.Row([
                        ft.Icon(ft.Icons.AUTO_AWESOME, size=14, color=COLOR_ACCENT_BLUE),
                        ft.Text(step.label, size=13, weight=ft.FontWeight.BOLD,
                                color=COLOR_ACCENT_BLUE, expand=True),
                    ], spacing=6),
                    bsw_enable_cb,
                    dropdown_with_info(lambda: self._page, bsw_dd_remove, describe_bsw_remove),
                    dropdown_with_info(lambda: self._page, bsw_dd_add, describe_bsw_add),
                ]
                borrowed_spell_swap_refs.append((bsw_enable_cb, bsw_dd_remove, bsw_dd_add, _restricted_swap))

            elif step.step_type == StepType.PROFICIENCY_BONUS_UP:
                dlg_rows.append(ft.Container(
                    content=ft.Text(f"⬆ {step.label}", size=12,
                                    color=COLOR_ACCENT_BLUE, weight=ft.FontWeight.BOLD),
                    bgcolor="#e8eef8", padding=8, border_radius=4,
                    border=ft.Border.all(1, COLOR_ACCENT_BLUE),
                ))

        # ------------------------------------------------------------------
        # Scelte extra specifiche per classe/sottoclasse
        # ------------------------------------------------------------------
        cls_lower = (c.class_name or "").strip().lower()

        fighting_style_dd_ref: list[ft.Dropdown] = []
        totem_animal_dd_ref:   list[ft.Dropdown] = []
        land_terrain_dd_ref:   list[ft.Dropdown] = []

        def _make_choice_dd(label: str, opts: list[str], current: str) -> ft.Dropdown:
            return ft.Dropdown(
                label=label,
                value=current if current in opts else opts[0],
                options=[ft.DropdownOption(key=o, text=o) for o in opts],
                bgcolor=COLOR_BG_CARD,
                color=COLOR_TEXT_PRIMARY,
                label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=12),
                border_color=COLOR_BORDER,
                focused_border_color=COLOR_ACCENT_BLUE,
                expand=True,
            )

        # Stile di Combattimento — Paladino Lv2 / Ranger Lv2
        if not c.fighting_style:
            styles = _loader.get_fighting_styles(cls_lower)
            if styles and new_level == 2 and cls_lower in ("paladino", "ranger"):
                fs_dd = _make_choice_dd("Stile di Combattimento", styles, "")
                fighting_style_dd_ref.append(fs_dd)
                describe_fs = make_named_option_describe(_loader.get_fighting_style_data(cls_lower))
                dlg_rows += [
                    ft.Divider(color=COLOR_BORDER),
                    ft.Row([
                        ft.Icon(ft.Icons.SHIELD, size=14, color=COLOR_ACCENT_BLUE),
                        ft.Text("Scegli il tuo Stile di Combattimento",
                                size=13, weight=ft.FontWeight.BOLD, color=COLOR_ACCENT_BLUE),
                    ], spacing=6),
                    dropdown_with_info(lambda: self._page, fs_dd, describe_fs),
                ]

        # ------------------------------------------------------------------
        # Animale Totem (Barbaro, Lv3) / Terreno (Druido, Lv2) — dipendono
        # dalla sottoclasse. Se questo stesso level-up include anche lo step
        # SUBCLASS_CHOICE (subclass_dd_ref popolato dal blocco sopra),
        # c.subclass è ancora vuota in questo momento: la visibilità va
        # agganciata dal vivo al valore corrente del dropdown sottoclasse
        # (on_select), non al campo persistito — altrimenti la condizione
        # "totem" in sc_lower/"terra" in sc_lower non è mai vera nello stesso
        # level-up in cui si sceglie la sottoclasse, e al level-up
        # successivo new_level non coincide più con la soglia richiesta.
        # Bug latente segnalato in CLAUDE.md (2026-07-15), fix 2026-07-16.
        # ------------------------------------------------------------------
        live_subclass_dd = subclass_dd_ref[0] if subclass_dd_ref else None

        def _compose_on_select(dd: ft.Dropdown, handler: Any) -> None:
            """Aggiunge `handler` a on_select senza sovrascrivere uno già presente."""
            prev = dd.on_select
            if prev is None:
                dd.on_select = handler
            else:
                def _combined(ev: Any, _prev: Any = prev, _new: Any = handler) -> None:
                    _prev(ev)
                    _new(ev)
                dd.on_select = _combined

        # Animale Totem — Barbaro Percorso del Totem Guerriero, Lv3
        if not c.totem_animal and cls_lower == "barbaro" and new_level == 3:
            initial_sc = ((live_subclass_dd.value if live_subclass_dd else c.subclass) or "").strip().lower()
            if live_subclass_dd is not None or "totem" in initial_sc:
                ta_dd = _make_choice_dd("Spirito del Totem", _loader.get_totem_animals(), "")
                totem_animal_dd_ref.append(ta_dd)
                ta_container = ft.Container(
                    content=ft.Column([
                        ft.Divider(color=COLOR_BORDER),
                        ft.Row([
                            ft.Icon(ft.Icons.PETS, size=14, color=COLOR_ACCENT_AMBER),
                            ft.Text("Scegli il tuo Spirito Totem",
                                    size=13, weight=ft.FontWeight.BOLD, color=COLOR_ACCENT_AMBER),
                        ], spacing=6),
                        muted_text("L'animale scelto a Lv.3 determina tutte le feature future del Percorso.", size=11),
                        ta_dd,
                    ], spacing=8),
                    visible=("totem" in initial_sc),
                )
                dlg_rows.append(ta_container)
                if live_subclass_dd is not None:
                    def _on_sc_select_totem(ev: Any, _cont: ft.Container = ta_container,
                                             _dd: ft.Dropdown = live_subclass_dd) -> None:
                        _cont.visible = "totem" in (_dd.value or "").strip().lower()
                        try:
                            _cont.update()
                        except RuntimeError:
                            pass
                    _compose_on_select(live_subclass_dd, _on_sc_select_totem)

        # Terreno — Druido Cerchio della Terra, Lv2
        if not c.land_terrain and cls_lower == "druido" and new_level == 2:
            initial_sc = ((live_subclass_dd.value if live_subclass_dd else c.subclass) or "").strip().lower()
            if live_subclass_dd is not None or "terra" in initial_sc:
                lt_dd = _make_choice_dd("Terreno del Cerchio", _loader.get_land_terrains(), "")
                land_terrain_dd_ref.append(lt_dd)
                lt_container = ft.Container(
                    content=ft.Column([
                        ft.Divider(color=COLOR_BORDER),
                        ft.Row([
                            ft.Icon(ft.Icons.LANDSCAPE, size=14, color="#4caf50"),
                            ft.Text("Scegli il Terreno del Cerchio della Terra",
                                    size=13, weight=ft.FontWeight.BOLD, color="#4caf50"),
                        ], spacing=6),
                        muted_text("Il terreno determina gli Incantesimi del Cerchio per ogni livello.", size=11),
                        lt_dd,
                    ], spacing=8),
                    visible=("terra" in initial_sc),
                )
                dlg_rows.append(lt_container)
                if live_subclass_dd is not None:
                    def _on_sc_select_terrain(ev: Any, _cont: ft.Container = lt_container,
                                               _dd: ft.Dropdown = live_subclass_dd) -> None:
                        _cont.visible = "terra" in (_dd.value or "").strip().lower()
                        try:
                            _cont.update()
                        except RuntimeError:
                            pass
                    _compose_on_select(live_subclass_dd, _on_sc_select_terrain)

        # ------------------------------------------------------------------
        # Competenze bonus di sottoclasse (task #20, 2026-07-16) — es. Bardo
        # Collegio della Conoscenza (3 abilità a scelta)/Collegio del Valore
        # (armatura media+scudi+armi da guerra fisse), Ladro Assassino (2
        # strumenti fissi). Stesso dato/stessa logica di wizard_view.py/
        # manual_form.py (bonus_proficiencies in classes/*.json — vedi
        # character_repo.classify_bonus_proficiency_entries()/
        # apply_subclass_bonus_proficiencies()), applicata qui al level-up
        # per le sottoclassi con subclass_choice_level != 1 (Chierico è
        # l'unica lv1, gestita solo in creazione — vedi CLAUDE.md). A
        # differenza di Totem/Terreno, il numero di dropdown varia per
        # sottoclasse, quindi qui l'intero blocco (non solo la visibilità)
        # va ricostruito ad ogni cambio del dropdown sottoclasse.
        # ------------------------------------------------------------------
        subclass_bonus_dd_refs: list[ft.Dropdown] = []
        subclass_bonus_choice_values: list[str] = []
        if live_subclass_dd is not None and subclasses:
            _scb_owned_skills = {p.name for p in _all_profs if p.proficiency_type == "skill"}
            _SCB_TOKEN_LABELS = {
                "leggere": "Armature Leggere", "medie": "Armature Medie",
                "pesanti": "Armature Pesanti", "scudi": "Scudi",
                "semplice": "Armi Semplici", "semplice_mischia": "Armi Semplici da Mischia",
                "guerra": "Armi da Guerra", "guerra_mischia": "Armi da Guerra da Mischia",
            }
            _scb_container = ft.Container(visible=False)

            def _rebuild_scb_container(_dd: ft.Dropdown = live_subclass_dd) -> None:
                subclass_bonus_dd_refs.clear()
                sc_name = _dd.value or ""
                entries = _loader.get_subclass_bonus_proficiencies(c.class_name or "", sc_name)
                fixed, choices = character_repo.classify_bonus_proficiency_entries(entries)
                total_slots = sum(int(ch.get("count", 0)) for ch in choices)

                while len(subclass_bonus_choice_values) < total_slots:
                    subclass_bonus_choice_values.append("")
                del subclass_bonus_choice_values[total_slots:]

                if not fixed and total_slots == 0:
                    _scb_container.visible = False
                    _scb_container.content = None
                    try:
                        _scb_container.update()
                    except RuntimeError:
                        pass
                    return

                rows: list[ft.Control] = [
                    ft.Divider(color=COLOR_BORDER),
                    ft.Row([
                        ft.Icon(ft.Icons.SHIELD_MOON, size=14, color=COLOR_ACCENT_BLUE),
                        ft.Text("Competenze Bonus di Sottoclasse", size=13,
                                weight=ft.FontWeight.BOLD, color=COLOR_ACCENT_BLUE, expand=True),
                    ], spacing=6),
                ]
                if fixed:
                    labels = ", ".join(_SCB_TOKEN_LABELS.get(f, f) for f in fixed)
                    rows.append(muted_text(f"Competenze bonus automatiche: {labels}", size=11))

                if total_slots > 0:
                    already = _scb_owned_skills
                    dds: list[ft.Dropdown] = []

                    def _refresh_scb_options() -> None:
                        for i, dd in enumerate(dds):
                            siblings = {
                                subclass_bonus_choice_values[j]
                                for j in range(len(dds)) if j != i
                            }
                            dd.options = [
                                ft.DropdownOption(key=p, text=p) for p in _scb_pool
                                if p not in siblings
                            ]
                            try:
                                dd.update()
                            except RuntimeError:
                                pass

                    for choice_entry in choices:
                        count = int(choice_entry.get("count", 0))
                        _scb_pool = [
                            p for p in character_repo.resolve_bonus_proficiency_choice_options(choice_entry)
                            if p not in already
                        ]
                        for i in range(count):
                            siblings = {
                                subclass_bonus_choice_values[j]
                                for j in range(count) if j != i
                            }
                            opts = [p for p in _scb_pool if p not in siblings]
                            curr = subclass_bonus_choice_values[i] if i < len(subclass_bonus_choice_values) else ""
                            if curr not in opts:
                                curr = opts[0] if opts else ""
                                subclass_bonus_choice_values[i] = curr

                            def _make_scb_handler(slot_idx: int = i) -> Any:
                                def _handler(ev: Any) -> None:
                                    subclass_bonus_choice_values[slot_idx] = ev.control.value or ""
                                    _refresh_scb_options()
                                return _handler

                            dd = ft.Dropdown(
                                label=(f"Competenza bonus (scelta {i + 1})" if count > 1
                                       else "Competenza bonus (scelta sottoclasse)"),
                                value=curr,
                                options=[ft.DropdownOption(key=p, text=p) for p in opts],
                                on_select=_make_scb_handler(),
                                bgcolor=COLOR_BG_CARD, color=COLOR_TEXT_PRIMARY,
                                label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=12),
                                border_color=COLOR_BORDER, focused_border_color=COLOR_ACCENT_BLUE,
                                expand=True,
                            )
                            dds.append(dd)
                            subclass_bonus_dd_refs.append(dd)
                    rows.append(ft.Row(list(dds), spacing=12, wrap=True))

                _scb_container.content = ft.Column(rows, spacing=8)
                _scb_container.visible = True
                try:
                    _scb_container.update()
                except RuntimeError:
                    pass

            dlg_rows.append(_scb_container)
            _rebuild_scb_container()

            def _on_sc_select_scb(ev: Any) -> None:
                _rebuild_scb_container()
            _compose_on_select(live_subclass_dd, _on_sc_select_scb)

        def _save_known_spell(
            spell_name: str, class_name: str, char: Character,
            origin_unrestricted: bool = False,
        ) -> None:
            """
            Recupera i dettagli dello spell dal JSON e lo salva come conosciuto.

            origin_unrestricted: solo per Mistificatore Arcano/Cavaliere
            Mistico (class_name="Mago" in quel caso) — True se questo pick è
            "libero da vincolo di scuola" (8°/14°/20° livello, +3° per il
            Cavaliere Mistico — vedi CLAUDE.md 2026-07-15). Ignorato/sempre
            False per tutte le altre chiamate esistenti.
            """
            all_spells = _loader.get_spells(class_name)
            spell = next((s for s in all_spells if s.get("name") == spell_name), None)
            if spell is None:
                # Lista Incantesimi Ampliata (Warlock, task #25, 2026-07-16) —
                # un nome scelto dal pool "ampliato" (es. Il Signore Fatato →
                # Luminescenza) non è nella lista base della classe, va
                # risolto qui. No-op per qualunque altra classe/sottoclasse.
                spell = next(
                    (s for s in _loader.get_expanded_spells(class_name, char.subclass or "")
                     if s.get("name") == spell_name),
                    None,
                )
            if spell is None:
                logger.warning("Spell '%s' non trovato per classe '%s'", spell_name, class_name)
                return
            comps = spell.get("components", [])
            comp_str = ", ".join(comps) if isinstance(comps, list) else str(comps)
            if spell.get("material"):
                comp_str += f" ({spell['material']})"
            character_repo.upsert_known_spell(
                character_id=char.id,
                name=spell_name,
                level=spell.get("level", 0),
                is_prepared=True,
                school=spell.get("school", ""),
                casting_time=spell.get("casting_time", ""),
                spell_range=spell.get("range", ""),
                components=comp_str,
                duration=spell.get("duration", ""),
                description=spell.get("description", ""),
                higher_levels=spell.get("higher_levels", "") or "",
                class_list=class_name,
                origin_unrestricted=origin_unrestricted,
            )

        def do_level_up(ev):
            if page is None:
                return

            # ----------------------------------------------------------------
            # Validazione — blocca il salvataggio se campi obbligatori mancanti
            # ----------------------------------------------------------------
            _errors: list[str] = []

            # HP manuale: valore deve essere un intero nel range del dado
            if hp_choice.value == "manual":
                try:
                    _roll = int((manual_roll.value or "").strip())
                    if _roll < 1 or _roll > hit_die:
                        _errors.append(f"Risultato dado non valido (deve essere 1–{hit_die})")
                except ValueError:
                    _errors.append(f"Inserisci il risultato del dado d{hit_die} (1–{hit_die})")

            # ASI: selezione obbligatoria di caratteristica o talento
            if has_asi:
                if asi_type.value == "two_one" and not stat_dd1.value:
                    _errors.append("Scegli la caratteristica da aumentare (+2)")
                elif asi_type.value == "one_one":
                    if not stat_dd1.value:
                        _errors.append("Scegli la prima caratteristica (+1)")
                    if not stat_dd2.value:
                        _errors.append("Scegli la seconda caratteristica (+1)")
                    elif stat_dd2.value == stat_dd1.value:
                        _errors.append("Le due caratteristiche devono essere diverse")
                elif asi_type.value == "feat":
                    if not feat_dd.value or feat_dd.value == "__none__":
                        _errors.append("Scegli un talento per l'ASI")
                    else:
                        _fd = _loader.get_feat(feat_dd.value)
                        _ab = _fd.get("ability_bonus") if _fd else None
                        if _ab and _ab.get("choose_one") and not feat_bonus_dd.value:
                            _errors.append("Scegli la caratteristica da aumentare con il talento")

            # Incantesimi conosciuti (classi "know"): tutti i dropdown devono avere un valore
            for _sd, _dds in spell_learn_refs:
                for _i, _dd in enumerate(_dds):
                    if not _dd.value:
                        _errors.append(f"Scegli l'incantesimo {_i + 1}/{len(_dds)}")

            # Nuovo trucchetto conosciuto (lv.4/10) — sempre obbligatorio,
            # stesso trattamento di SPELL_LEARN (non è opzionale come SPELL_SWAP).
            for _cantrip_dd in cantrip_learn_refs:
                if not _cantrip_dd.value:
                    _errors.append("Scegli il nuovo trucchetto")

            # Arcanum Mistico (Warlock) — sempre obbligatorio
            for _arcanum_dd in arcanum_spell_refs:
                if not _arcanum_dd.value:
                    _errors.append("Scegli l'incantesimo per l'Arcanum Mistico")

            # Discipline Elementali (Monaco) — sempre obbligatorio
            for _mk_dd in monk_discipline_refs:
                if not _mk_dd.value:
                    _errors.append("Scegli la nuova Disciplina Elementale")

            # Sostituzione incantesimo conosciuto — OPZIONALE: se la checkbox
            # non è attiva, nessuna validazione. Se attiva, entrambi i
            # dropdown devono essere compilati (il pool di `dd_add` già
            # esclude `dd_remove.value` a monte, quindi non serve controllare
            # che siano diversi).
            for _swap_cb, _swap_rm, _swap_add in spell_swap_refs:
                if _swap_cb.value:
                    if not _swap_rm.value:
                        _errors.append("Scegli quale incantesimo sostituire")
                    if not _swap_add.value:
                        _errors.append("Scegli il nuovo incantesimo")

            # Segreti Magici: deve aver aperto il picker e scelto tutti gli incantesimi
            for _sd, _choices in magical_secrets_refs:
                _needed = _sd.get("count", 2)
                if len(_choices) < _needed:
                    _errors.append(
                        f"Segreti Magici: scegli {_needed} incantesimi "
                        f"({len(_choices)}/{_needed} scelti)"
                    )

            # Metamagia: deve scegliere esattamente il numero richiesto
            for _mm_count, _mm_cbs in metamagic_cb_groups:
                if _mm_cbs:  # solo se i checkbox sono stati mostrati
                    _sel_mm = sum(1 for cb in _mm_cbs if cb.value)
                    if _sel_mm < _mm_count:
                        _errors.append(
                            f"Scegli {_mm_count} opzion"
                            f"{'e' if _mm_count == 1 else 'i'} di Metamagia "
                            f"({_sel_mm}/{_mm_count})"
                        )

            # Suppliche Occulte: deve scegliere esattamente il numero richiesto
            # (solo se i checkbox sono stati mostrati, cioè invocations.json non è vuoto)
            for _inv_count, _inv_cbs in invocation_cb_groups:
                if _inv_cbs:
                    _sel_inv = sum(1 for cb in _inv_cbs if cb.value)
                    if _sel_inv < _inv_count:
                        _errors.append(
                            f"Scegli {_inv_count} supplic"
                            f"{'a' if _inv_count == 1 else 'he'} occult"
                            f"{'a' if _inv_count == 1 else 'e'} "
                            f"({_sel_inv}/{_inv_count})"
                        )

            # Mistificatore Arcano/Cavaliere Mistico — validazione solo se la
            # sottoclasse FINALE scelta nel dropdown è quella borrowed-caster
            # (i widget restano nel DOM anche se nascosti, ma non vanno
            # validati/salvati se il giocatore ha scelto un'altra sottoclasse).
            _final_subclass = (subclass_dd_ref[0].value if subclass_dd_ref else (c.subclass or "")) or ""
            _is_borrowed_choice = bool(
                borrowed_subclass_name_ref and _final_subclass == borrowed_subclass_name_ref[0]
            )
            if _is_borrowed_choice:
                for _i, _dd in enumerate(borrowed_initial_cantrip_refs):
                    if not _dd.value:
                        _errors.append(f"Scegli il trucchetto da mago {_i + 1}/{len(borrowed_initial_cantrip_refs)}")
                for _i, (_dd, _) in enumerate(borrowed_initial_spell_refs):
                    if not _dd.value:
                        _errors.append(f"Scegli l'incantesimo da mago {_i + 1}/{len(borrowed_initial_spell_refs)}")

            for _dd in borrowed_cantrip_dd_refs:
                if not _dd.value:
                    _errors.append("Scegli il nuovo trucchetto da mago")

            for _dd, _ in borrowed_spell_learn_refs:
                if not _dd.value:
                    _errors.append("Scegli il nuovo incantesimo da mago")

            for _bsw_cb, _bsw_rm, _bsw_add, _ in borrowed_spell_swap_refs:
                if _bsw_cb.value:
                    if not _bsw_rm.value:
                        _errors.append("Scegli quale incantesimo da mago sostituire")
                    if not _bsw_add.value:
                        _errors.append("Scegli il nuovo incantesimo da mago")

            # Monaco, Via dei Quattro Elementi — scelta iniziale di Lv.3
            # (Sintonia Elementale automatica + 1 disciplina a scelta):
            # stesso principio del Mistificatore Arcano/Cavaliere Mistico —
            # il dropdown resta nel DOM anche se nascosto, va validato solo
            # se la sottoclasse FINALE scelta è davvero questa.
            _is_monk_discipline_choice = (
                c.class_name == "Monaco" and _final_subclass == "Via dei Quattro Elementi"
            )
            if _is_monk_discipline_choice:
                for _dd in monk_initial_discipline_refs:
                    if not _dd.value:
                        _errors.append("Scegli la disciplina elementale aggiuntiva (Lv.3)")

            # Competenze bonus di sottoclasse (task #20, 2026-07-16) —
            # validate contro la sottoclasse FINALE scelta, non contro il
            # numero di dropdown attualmente costruiti (già tenuti in sync
            # da _rebuild_scb_container ad ogni cambio del dropdown, ma un
            # doppio controllo qui evita falsi negativi se in futuro il
            # rebuild venisse rimosso o modificato).
            if live_subclass_dd is not None:
                _scb_entries_final = _loader.get_subclass_bonus_proficiencies(c.class_name or "", _final_subclass)
                _scb_fixed_final, _scb_choices_final = character_repo.classify_bonus_proficiency_entries(_scb_entries_final)
                _scb_total_final = sum(int(ch.get("count", 0)) for ch in _scb_choices_final)
                if _scb_total_final > 0:
                    _scb_filled = [v for v in subclass_bonus_choice_values if v]
                    if len(_scb_filled) != _scb_total_final or len(set(_scb_filled)) != len(_scb_filled):
                        _errors.append("Completa la scelta delle competenze bonus di sottoclasse (nessun duplicato ammesso)")

            if _errors:
                def _close_err_dlg(ev_inner: Any) -> None:
                    page.pop_dialog()  # type: ignore[union-attr]

                err_dlg = ft.AlertDialog(
                    title=ft.Row([
                        ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED,
                                color=COLOR_ACCENT_AMBER, size=18),
                        ft.Container(width=6),
                        ft.Text("Completa tutte le scelte", size=13,
                                weight=ft.FontWeight.BOLD, color=COLOR_TEXT_TITLE),
                    ]),
                    content=ft.Column(
                        [ft.Text(f"• {err}", size=12, color=COLOR_TEXT_PRIMARY)
                         for err in _errors],
                        spacing=6,
                    ),
                    actions=[ft.TextButton("OK", on_click=_close_err_dlg)],
                    bgcolor=COLOR_BG_CARD,
                )
                page.show_dialog(err_dlg)  # type: ignore[union-attr]
                return

            # HP
            choice = hp_choice.value
            if choice == "max":
                gained = hp_max_gain + con_mod
            elif choice == "manual":
                try:
                    roll = max(1, min(hit_die, int(manual_roll.value or 1)))
                except ValueError:
                    roll = 1
                gained = roll + con_mod
            else:
                gained = hp_avg_gain + con_mod
            gained = max(1, gained)

            # Bonus PF permanente da capacità di sottoclasse (es. Resilienza
            # Draconica dello Stregone: +1 PF/livello) — delta tra il totale
            # al nuovo livello e quello al livello precedente.
            hp_class_bonus = (
                get_permanent_class_hp_bonus(c.class_name, c.subclass, new_level)
                - get_permanent_class_hp_bonus(c.class_name, c.subclass, c.level)
            )

            c.level = new_level
            c.hp_max += gained + hp_class_bonus
            c.hp_current = min(c.hp_current + gained + hp_class_bonus, c.hp_max)
            # Dadi vita: +1 per ogni livello acquisito (PHB p.12)
            c.hit_dice_total += 1
            c.hit_dice_remaining = min(c.hit_dice_remaining + 1, c.hit_dice_total)

            # ASI
            if has_asi:
                if asi_type.value == "two_one" and stat_dd1.value:
                    k = stat_dd1.value
                    setattr(c, f"{k}_score", min(20, getattr(c, f"{k}_score") + 2))
                    # Traccia l'ASI per il level-down
                    import json as _json2
                    character_repo._save_single_proficiency(
                        c.id, "asi_record", f"+2 {k}",
                        bonus_data=_json2.dumps({"ability": {k: 2}}),
                        level_obtained=new_level,
                    )
                elif asi_type.value == "one_one":
                    _asi_applied: dict[str, int] = {}
                    if stat_dd1.value:
                        setattr(c, f"{stat_dd1.value}_score",
                                min(20, getattr(c, f"{stat_dd1.value}_score") + 1))
                        _asi_applied[stat_dd1.value] = 1
                    if stat_dd2.value and stat_dd2.value != stat_dd1.value:
                        setattr(c, f"{stat_dd2.value}_score",
                                min(20, getattr(c, f"{stat_dd2.value}_score") + 1))
                        _asi_applied[stat_dd2.value] = 1
                    if _asi_applied:
                        import json as _json2
                        character_repo._save_single_proficiency(
                            c.id, "asi_record",
                            "+1 " + "+1 ".join(_asi_applied.keys()),
                            bonus_data=_json2.dumps({"ability": _asi_applied}),
                            level_obtained=new_level,
                        )
                elif asi_type.value == "feat" and feat_dd.value and feat_dd.value != "__none__":
                    _fd = _loader.get_feat(feat_dd.value)
                    _ab = (_fd.get("ability_bonus") if _fd else None) or {}
                    _ob = (_fd.get("other_bonuses") if _fd else None) or {}

                    # Calcola i bonus effettivi applicati (per bonus_data)
                    applied_ability: dict[str, int] = {}
                    applied_other:   dict[str, int] = {}

                    # ability_bonus: fisso o choose_one
                    if _ab:
                        if _ab.get("choose_one"):
                            if feat_bonus_dd.value:
                                stat = feat_bonus_dd.value
                                _cur = getattr(c, f"{stat}_score", 10)
                                setattr(c, f"{stat}_score", min(20, _cur + 1))
                                applied_ability[stat] = 1
                        else:
                            for _stat, _val in _ab.items():
                                if _stat in ABILITY_KEYS and isinstance(_val, int):
                                    _cur = getattr(c, f"{_stat}_score", 10)
                                    setattr(c, f"{_stat}_score", min(20, _cur + _val))
                                    applied_ability[_stat] = _val

                    # other_bonuses: initiative, speed, ecc.
                    if _ob:
                        if "initiative" in _ob:
                            c.initiative_bonus = (c.initiative_bonus or 0) + _ob["initiative"]
                            applied_other["initiative"] = _ob["initiative"]
                        if "speed" in _ob:
                            c.speed = (c.speed or 9) + _ob["speed"]
                            applied_other["speed"] = _ob["speed"]

                    # Costruisce la ricevuta da salvare
                    _bonus_data: dict = {}
                    if applied_ability:
                        _bonus_data["ability"] = applied_ability
                    if applied_other:
                        _bonus_data["other"] = applied_other

                    # Salva talento con ricevuta e livello di acquisizione
                    import json as _json
                    character_repo._save_single_proficiency(
                        c.id, "feat", feat_dd.value,
                        bonus_data=_json.dumps(_bonus_data) if _bonus_data else None,
                        level_obtained=new_level,
                    )

            # Sottoclasse scelta al level-up
            if subclass_dd_ref and subclass_dd_ref[0].value:
                c.subclass = subclass_dd_ref[0].value

            # Competenze bonus di sottoclasse (task #20, 2026-07-16) — es.
            # Bardo Collegio della Conoscenza/Valore, Ladro Assassino. Va
            # applicata alla sottoclasse FINALE appena scritta su c.subclass
            # (non a subclass_bonus_choice_values "as-is" se il giocatore ha
            # cambiato sottoclasse più volte senza che l'ultimo rebuild sia
            # coerente — si ricalcolano fixed/choices da c.subclass per
            # sicurezza, stesso principio già usato per Totem/Terreno sopra).
            if live_subclass_dd is not None:
                _scb_entries_apply = _loader.get_subclass_bonus_proficiencies(c.class_name or "", c.subclass or "")
                _scb_fixed_apply, _scb_choices_apply = character_repo.classify_bonus_proficiency_entries(_scb_entries_apply)
                _scb_resolved_apply = list(_scb_fixed_apply) + [v for v in subclass_bonus_choice_values if v]
                character_repo.apply_subclass_bonus_proficiencies(c.id, _scb_resolved_apply)

            # Patto del Warlock
            if pact_rg_ref and pact_rg_ref[0].value:
                c.pact_boon = pact_rg_ref[0].value

            # Metamagia
            for _mm_count, mm_cbs in metamagic_cb_groups:
                for cb in mm_cbs:
                    if cb.value and cb.label:
                        character_repo._save_single_proficiency(
                            c.id, "metamagic", str(cb.label)
                        )

            # Invocazioni Occulte
            for _to_add, inv_cbs in invocation_cb_groups:
                for cb in inv_cbs:
                    if cb.value and cb.label:
                        character_repo._save_single_proficiency(
                            c.id, "invocation", str(cb.label)
                        )

            # Expertise (Maestria)
            for cb_group in expertise_cb_groups:
                chosen = [
                    str(cb.label) for cb in cb_group if cb.value and cb.label
                ]
                if chosen:
                    character_repo.set_expertise(c.id, chosen)

            # Scelte extra: stile di combattimento, animale totem, terreno.
            # Totem/Terreno: il dropdown viene costruito (nascosto) anche per
            # sottoclassi che non lo richiedono quando la sottoclasse è
            # scelta in questo stesso level-up (vedi live_subclass_dd sopra)
            # — va salvato solo se la sottoclasse FINALE scelta corrisponde
            # davvero, altrimenti si salverebbe sempre il primo valore di
            # default (es. "Orso") anche per un Barbaro Berserker.
            if fighting_style_dd_ref and fighting_style_dd_ref[0].value:
                c.fighting_style = fighting_style_dd_ref[0].value
            _final_subclass_lower = ((live_subclass_dd.value if live_subclass_dd else c.subclass) or "").strip().lower()
            if (totem_animal_dd_ref and totem_animal_dd_ref[0].value
                    and "totem" in _final_subclass_lower):
                c.totem_animal = totem_animal_dd_ref[0].value
            if (land_terrain_dd_ref and land_terrain_dd_ref[0].value
                    and "terra" in _final_subclass_lower):
                c.land_terrain = land_terrain_dd_ref[0].value

            # Incantesimi conosciuti (classi "know")
            for _step_data, dds in spell_learn_refs:
                for dd in dds:
                    if dd.value:
                        _save_known_spell(dd.value, c.class_name or "", c)

            # Nuovo trucchetto conosciuto (lv.4/10) — salvato come known_spell
            # is_prepared=True, stessa convenzione dei trucchetti iniziali
            # (task #74) e di SPELL_LEARN sopra.
            for _cantrip_dd in cantrip_learn_refs:
                if _cantrip_dd.value:
                    _save_known_spell(_cantrip_dd.value, c.class_name or "", c)

            # Arcanum Mistico (Warlock, lv.11/13/15/17) — salvato come
            # known_spell (is_prepared=True), stesso pattern di SPELL_LEARN/
            # CANTRIP_LEARN. Il fatto che sia lanciabile senza slot 1/riposo
            # lungo non è tracciato a parte in questo progetto, coerente con
            # la semplificazione già adottata per tutti gli incantesimi
            # conosciuti (nessun sistema di "usi speciali" per singolo spell).
            for _arcanum_dd in arcanum_spell_refs:
                if _arcanum_dd.value:
                    _save_known_spell(_arcanum_dd.value, c.class_name or "", c)

            # Discipline Elementali (Monaco, Via dei Quattro Elementi,
            # lv.6/11/17) — salvate come proficiency dedicata "monk_discipline".
            for _mk_dd in monk_discipline_refs:
                if _mk_dd.value:
                    character_repo._save_single_proficiency(
                        c.id, "monk_discipline", _mk_dd.value, level_obtained=new_level,
                    )

            # Sostituzione incantesimo conosciuto (opzionale) — rimuove il
            # vecchio incantesimo da known_spells e salva il nuovo con lo
            # stesso pattern di _save_known_spell già usato sopra. Il livello
            # del vecchio incantesimo viene riletto dal DB (non dal JSON) per
            # essere certi di cancellare la riga esatta.
            for _swap_cb, _swap_rm, _swap_add in spell_swap_refs:
                if _swap_cb.value and _swap_rm.value and _swap_add.value:
                    _old_name = _swap_rm.value
                    _old_row = next(
                        (ks for ks in character_repo.get_known_spells(c.id)
                         if ks.name == _old_name),
                        None,
                    )
                    if _old_row is not None:
                        character_repo.remove_known_spell(c.id, _old_name, _old_row.spell_level)
                    _save_known_spell(_swap_add.value, c.class_name or "", c)

            # Segreti Magici (qualsiasi classe)
            for _step_data, choices in magical_secrets_refs:
                for spell_name, class_name in choices:
                    _save_known_spell(spell_name, class_name, c)

            # Mistificatore Arcano/Cavaliere Mistico — apprendimento INIZIALE
            # (3° livello), solo se la sottoclasse finale scelta è quella
            # borrowed-caster (c.subclass è già stato aggiornato sopra).
            if _is_borrowed_choice:
                # Il trucchetto fisso (es. Mano Magica del Ladro) va comunque
                # salvato come known_spell — è un trucchetto reale che il
                # personaggio conosce e può lanciare, solo non è una scelta
                # del giocatore. Senza questo salvataggio non comparirebbe
                # affatto nella tab Incantesimi. Assente per il Cavaliere
                # Mistico (fixed_cantrip="" in guerriero.json).
                _bc_data_save = _loader.get_borrowed_caster_data(c.class_name or "", c.subclass or "") or {}
                _fixed_cantrip_save = _bc_data_save.get("fixed_cantrip") or ""
                if _fixed_cantrip_save:
                    _save_known_spell(_fixed_cantrip_save, "Mago", c)
                for _dd in borrowed_initial_cantrip_refs:
                    if _dd.value:
                        _save_known_spell(_dd.value, "Mago", c)
                for _dd, _origin_unr in borrowed_initial_spell_refs:
                    if _dd.value:
                        _save_known_spell(_dd.value, "Mago", c, origin_unrestricted=_origin_unr)

            # Monaco, Via dei Quattro Elementi — scelta iniziale di Lv.3:
            # Sintonia Elementale (automatica, sempre inclusa) + la disciplina
            # scelta nel dropdown, solo se la sottoclasse finale è questa.
            if _is_monk_discipline_choice:
                character_repo._save_single_proficiency(
                    c.id, "monk_discipline", "Sintonia Elementale", level_obtained=new_level,
                )
                for _dd in monk_initial_discipline_refs:
                    if _dd.value:
                        character_repo._save_single_proficiency(
                            c.id, "monk_discipline", _dd.value, level_obtained=new_level,
                        )

            # Mistificatore Arcano/Cavaliere Mistico — crescita dal 4° livello
            # in poi (nuovo trucchetto/incantesimo da mago).
            for _dd in borrowed_cantrip_dd_refs:
                if _dd.value:
                    _save_known_spell(_dd.value, "Mago", c)
            for _dd, _origin_unr in borrowed_spell_learn_refs:
                if _dd.value:
                    _save_known_spell(_dd.value, "Mago", c, origin_unrestricted=_origin_unr)

            # Mistificatore Arcano/Cavaliere Mistico — sostituzione opzionale.
            # Il flag origin_unrestricted del vecchio incantesimo si propaga
            # sul nuovo (la "postazione" resta libera da vincolo anche in
            # futuro se lo era già — vedi CLAUDE.md 2026-07-15).
            for _bsw_cb, _bsw_rm, _bsw_add, _ in borrowed_spell_swap_refs:
                if _bsw_cb.value and _bsw_rm.value and _bsw_add.value:
                    _old_name_bsw = _bsw_rm.value
                    _old_row_bsw = next(
                        (ks for ks in character_repo.get_known_spells(c.id)
                         if ks.name == _old_name_bsw),
                        None,
                    )
                    _was_unrestricted = _old_row_bsw.origin_unrestricted if _old_row_bsw else False
                    if _old_row_bsw is not None:
                        character_repo.remove_known_spell(c.id, _old_name_bsw, _old_row_bsw.spell_level)
                    _save_known_spell(_bsw_add.value, "Mago", c, origin_unrestricted=_was_unrestricted)

            if not character_repo.update(c):
                show_error_dialog(page)
                return
            # Aggiorna slot incantesimo PHB per il nuovo livello
            character_repo.auto_init_spell_slots(c.id, c.class_name, new_level)
            # Aggiorna risorse di classe (Furia, Ki, Incanalare Divinità, ecc.)
            # per il nuovo livello — senza questa chiamata i pool restavano
            # congelati al valore calcolato alla creazione del personaggio.
            character_repo.init_class_resources(c.id, c.class_name, new_level, c)
            # Mistificatore Arcano/Cavaliere Mistico — spellcasting_ability e
            # slot incantesimo "presi in prestito dal Mago". No-op per
            # qualunque altra classe/sottoclasse (vedi character_repo.py).
            character_repo.sync_borrowed_spellcasting_ability(c)
            character_repo.init_borrowed_caster_slots(c.id, c.class_name or "", c.subclass or "", new_level)
            # Incantesimi sempre pronti da Dominio/Giuramento/Circolo della
            # Terra (es. Paladino Giuramento degli Antichi) — un level-up può
            # sbloccare una nuova soglia (Lv.3/5/9/13/17) o, se questo
            # level-up ha assegnato la sottoclasse, la primissima soglia.
            character_repo.sync_bonus_domain_spells(c)
            # Ricalcola la CA — copre i casi in cui questo level-up ha assegnato
            # una sottoclasse (es. Discendenza Draconica), uno Stile di
            # Combattimento (es. Difesa) o un ASI su DES/COS/SAG.
            character_repo.calculate_and_update_ca(c.id)
            page.pop_dialog()
            self._refresh()

        page = self._page
        if page is None:
            return
        dlg = ft.AlertDialog(
            content=ft.Column(dlg_rows, spacing=8, scroll=ft.ScrollMode.AUTO),
            actions=[
                ft.TextButton("Annulla", on_click=lambda ev: page.pop_dialog() if page else None),
                ft.ElevatedButton(
                    f"Sali a Lv.{new_level}",
                    on_click=do_level_up,
                    style=ft.ButtonStyle(
                        bgcolor=COLOR_ACCENT_CRIMSON, color="#ffffff",
                        shape=ft.RoundedRectangleBorder(radius=4),
                    ),
                ),
            ],
            bgcolor=COLOR_BG_CARD,
        )
        page.show_dialog(dlg)

    def _on_level_down_click(self, e):
        page = self._page
        if page is None:
            return
        c = self.character
        if c.level <= 1:
            return

        new_level = c.level - 1
        hit_die = c.hit_dice_type or 8
        con_mod = get_modifier(c.con_score)
        hp_loss = estimate_hp_loss(hit_die, con_mod)
        # Simmetrico al bonus applicato al level-up (es. Resilienza Draconica)
        hp_loss += (
            get_permanent_class_hp_bonus(c.class_name, c.subclass, c.level)
            - get_permanent_class_hp_bonus(c.class_name, c.subclass, new_level)
        )

        def do_level_down(ev):
            if page is None:
                return
            # Inverte ASI e talenti acquisiti al livello che si sta rimuovendo
            character_repo.undo_level(c.id, c.level)
            # Ricarica dal DB per avere i valori aggiornati (stat invertite da undo_level)
            refreshed = character_repo.get_by_id(c.id)
            if refreshed:
                self.character = refreshed
            # Applica la riduzione di livello su self.character (aggiornato o originale)
            self.character.level = new_level
            self.character.hp_max = max(1, self.character.hp_max - hp_loss)
            self.character.hp_current = min(self.character.hp_current, self.character.hp_max)
            if not character_repo.update(self.character):
                show_error_dialog(page)
                return
            # Ricalcola slot incantesimo e risorse di classe per il livello ridotto
            # (altrimenti restano al valore del livello precedente più alto)
            character_repo.auto_init_spell_slots(self.character.id, self.character.class_name, new_level)
            character_repo.init_class_resources(self.character.id, self.character.class_name, new_level, self.character)
            # Mistificatore Arcano/Cavaliere Mistico — ricalcola spellcasting_
            # ability e slot "presi in prestito dal Mago" anche in level-down
            # (no-op per qualunque altra classe/sottoclasse).
            character_repo.sync_borrowed_spellcasting_ability(self.character)
            character_repo.init_borrowed_caster_slots(
                self.character.id, self.character.class_name or "",
                self.character.subclass or "", new_level,
            )
            # Incantesimi sempre pronti da Dominio/Giuramento/Circolo della
            # Terra — un level-down può scendere sotto una soglia (Lv.3/5/
            # 9/13/17), la funzione ripulisce le righe non più valide.
            character_repo.sync_bonus_domain_spells(self.character)
            # Ricalcola la CA — coerente con il ricalcolo fatto al level-up
            # (es. perdita di una sottoclasse/ASI che influenzava la CA senza armatura)
            character_repo.calculate_and_update_ca(self.character.id)
            page.pop_dialog()
            self._refresh()

        dlg = ft.AlertDialog(
            title=ft.Text("Scendi di Livello", size=14,
                          weight=ft.FontWeight.BOLD, color=COLOR_TEXT_TITLE),
            content=ft.Column([
                ft.Text(f"Il personaggio scenderà a Livello {new_level}.",
                        size=13, color=COLOR_TEXT_PRIMARY),
                ft.Container(height=4),
                ft.Text(
                    f"HP max verrà ridotto di ~{hp_loss} PF "
                    f"(stima media: d{hit_die} + {con_mod:+d} CON).",
                    size=12, color=COLOR_TEXT_SECONDARY,
                ),
                ft.Container(height=4),
                ft.Container(
                    content=ft.Text(
                        "✓ Talenti e ASI acquisiti a Lv."
                        f"{c.level} verranno invertiti automaticamente.\n"
                        "⚠ Le feature di classe ottenute a quel livello "
                        "non vengono ripristinate automaticamente.",
                        size=11, color=COLOR_ACCENT_AMBER,
                    ),
                    bgcolor="#fef9ec", padding=8, border_radius=4,
                    border=ft.Border.all(1, COLOR_ACCENT_AMBER),
                ),
            ], spacing=4),
            actions=[
                ft.TextButton("Annulla", on_click=lambda ev: page.pop_dialog() if page else None),
                ft.ElevatedButton(
                    f"Scendi a Lv.{new_level}",
                    on_click=do_level_down,
                    style=ft.ButtonStyle(
                        bgcolor=COLOR_ACCENT_AMBER, color="#ffffff",
                        shape=ft.RoundedRectangleBorder(radius=4),
                    ),
                ),
            ],
            bgcolor=COLOR_BG_CARD,
        )
        page.show_dialog(dlg)

    # ------------------------------------------------------------------
    # Dialog modifica sezione
    # ------------------------------------------------------------------

    def _open_edit_dialog(self, section: str):
        page = self._page
        if page is None:
            return
        c = self.character
        # Mappa attr → TextField o Dropdown (entrambi hanno .value)
        fields: dict[str, ft.TextField | ft.Dropdown] = {}

        def f(label: str, value: str, multiline: bool = False, min_lines: int = 1) -> ft.TextField:
            return ft.TextField(
                label=label,
                value=value or "",
                multiline=multiline,
                min_lines=min_lines,
                max_lines=8 if multiline else 1,
                text_style=ft.TextStyle(size=13, color=COLOR_TEXT_PRIMARY),
                border_color=COLOR_BORDER,
                focused_border_color=COLOR_ACCENT_BLUE,
                bgcolor=COLOR_BG_CARD,
                label_style=ft.TextStyle(color=COLOR_TEXT_SECONDARY),
                expand=not multiline,
            )

        def dd(label: str, options: list[str], value: str) -> ft.Dropdown:
            """Dropdown stilizzato coerente con il tema."""
            return ft.Dropdown(
                label=label,
                value=value or None,
                options=[ft.DropdownOption(key=o, text=o) for o in options],
                text_style=ft.TextStyle(size=13, color=COLOR_TEXT_PRIMARY),
                border_color=COLOR_BORDER,
                focused_border_color=COLOR_ACCENT_BLUE,
                bgcolor=COLOR_BG_CARD,
                label_style=ft.TextStyle(color=COLOR_TEXT_SECONDARY),
            )

        if section == "anagrafica":
            fields["player_name"] = f("Giocatore", c.player_name)
            fields["class_name"]  = dd("Classe", _loader.get_class_names(), c.class_name or "")
            fields["race"]        = dd("Razza", RACES, c.race or "")
            fields["background"]  = dd("Background", _loader.get_background_names(), c.background or "")
            fields["alignment"]   = dd("Allineamento", ALIGNMENTS, c.alignment or "")
        elif section == "fisico":
            fields["age"]    = f("Età", str(c.age) if c.age else "")
            fields["height"] = f("Altezza", c.height)
            fields["weight"] = f("Peso", c.weight)
            fields["eyes"]   = f("Occhi", c.eyes)
            fields["skin"]   = f("Carnagione", c.skin)
            fields["hair"]   = f("Capelli", c.hair)
        elif section == "personalita":
            fields["personality_traits"] = f("Tratti", c.personality_traits,
                                              multiline=True, min_lines=2)
            fields["ideals"]  = f("Ideali", c.ideals, multiline=True, min_lines=2)
            fields["bonds"]   = f("Legami", c.bonds, multiline=True, min_lines=2)
            fields["flaws"]   = f("Difetti", c.flaws, multiline=True, min_lines=2)
        elif section == "storia":
            fields["backstory"]            = f("Storia", c.backstory,
                                                multiline=True, min_lines=3)
            fields["allies_organizations"] = f("Alleanze", c.allies_organizations,
                                                multiline=True, min_lines=2)
            fields["additional_traits"]    = f("Tratti Aggiuntivi", c.additional_traits,
                                                multiline=True, min_lines=2)
        elif section == "razza":
            # Solo cambio razza — i tratti razziali si aggiornano automaticamente al refresh
            fields["race"] = dd("Razza", RACES, c.race or "")
        else:
            return

        def on_save(ev):
            if page is None:
                return
            for attr, ctrl in fields.items():
                val = (ctrl.value or "").strip()
                if attr == "age":
                    try:
                        setattr(c, attr, int(val))
                    except ValueError:
                        setattr(c, attr, None)
                else:
                    setattr(c, attr, val)
            if not character_repo.update(c):
                show_error_dialog(page)
                return
            page.pop_dialog()
            self._refresh()

        titles = {
            "anagrafica": "Modifica Anagrafica",
            "fisico":     "Modifica Dettagli Fisici",
            "personalita":"Modifica Personalità",
            "storia":     "Modifica Storia",
            "razza":      "Cambia Razza",
        }
        dlg = ft.AlertDialog(
            title=ft.Text(titles.get(section, "Modifica"), size=14,
                          weight=ft.FontWeight.BOLD, color=COLOR_TEXT_TITLE),
            content=ft.Column(
                list(fields.values()),  # mix di TextField e Dropdown — entrambi hanno .value
                spacing=10,
                scroll=ft.ScrollMode.AUTO,
            ),
            actions=[
                ft.TextButton("Annulla", on_click=lambda ev: page.pop_dialog() if page else None),
                ft.ElevatedButton(
                    "Salva",
                    on_click=on_save,
                    style=ft.ButtonStyle(
                        bgcolor=COLOR_ACCENT_CRIMSON,
                        color="#ffffff",
                        shape=ft.RoundedRectangleBorder(radius=4),
                    ),
                ),
            ],
            bgcolor=COLOR_BG_CARD,
        )
        page.show_dialog(dlg)

    # ------------------------------------------------------------------
    # Selezione foto — cross-platform
    # Desktop: dialogo nativo (macOS/Windows/Linux)
    # Mobile / fallback: dialog con TextField per incollare il percorso
    # Salvataggio come base64 nel DB — la foto non dipende dal percorso file
    # ------------------------------------------------------------------

    def _pick_photo(self):
        """
        Entry point: sceglie la strategia giusta per la piattaforma.
        - Mobile (Android/iOS, build nativa): ft.FilePicker, path locale
          letto direttamente (client e server sono lo stesso dispositivo)
        - Web (browser, deploy Docker): NIENTE ft.FilePicker (bug upstream
          Flet confermato, non risolvibile lato applicazione — vedi
          CLAUDE.md 2026-07-12). Al suo posto, un picker sulla libreria
          immagini caricata a mano da Davide via SSH (vedi
          ui/image_library.py, data/database.py -> get_image_library_path())
        - Desktop (macOS/Windows/Linux, app locale): dialogo nativo del SO
          via subprocess (ft.FilePicker e' broken su Flet 0.85.3 desktop)
        """
        if self._page is None:
            return
        if self._page.web:
            show_image_library_picker(self._page, on_select=self._load_photo)
            return
        platform = self._page.platform
        if platform in (ft.PagePlatform.ANDROID, ft.PagePlatform.IOS):
            self._pick_photo_mobile()
        else:
            import platform as sys_platform
            system = sys_platform.system()
            threading.Thread(
                target=self._pick_photo_desktop, args=(system,), daemon=True
            ).start()

    def _pick_photo_desktop(self, system: str):
        """Apre il dialogo file nativo del SO. Chiamato in un thread separato."""
        import subprocess
        path = None
        try:
            if system == "Darwin":
                script = (
                    'tell application "System Events"\n'
                    '  activate\n'
                    '  set f to choose file with prompt "Seleziona immagine personaggio" '
                    'of type {"public.image"}\n'
                    '  return POSIX path of f\n'
                    'end tell'
                )
                r = subprocess.run(["osascript", "-e", script],
                                   capture_output=True, text=True, timeout=60)
                if r.returncode == 0:
                    path = r.stdout.strip()

            elif system == "Windows":
                ps = (
                    "Add-Type -AssemblyName System.Windows.Forms; "
                    "$d = New-Object System.Windows.Forms.OpenFileDialog; "
                    "$d.Title = 'Seleziona immagine personaggio'; "
                    "$d.Filter = 'Immagini|*.png;*.jpg;*.jpeg;*.bmp;*.gif;*.webp'; "
                    "if ($d.ShowDialog() -eq 'OK') { $d.FileName }"
                )
                r = subprocess.run(["powershell", "-Command", ps],
                                   capture_output=True, text=True, timeout=60)
                if r.returncode == 0:
                    path = r.stdout.strip()

            elif system == "Linux":
                # Prova zenity (GNOME), poi kdialog (KDE)
                for cmd in [
                    ["zenity", "--file-selection", "--title=Seleziona immagine",
                     "--file-filter=Immagini | *.png *.jpg *.jpeg *.bmp *.gif *.webp"],
                    ["kdialog", "--getopenfilename", ".", "*.png *.jpg *.jpeg *.bmp *.gif *.webp"],
                ]:
                    try:
                        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                        if r.returncode == 0 and r.stdout.strip():
                            path = r.stdout.strip()
                            break
                    except FileNotFoundError:
                        continue

        except Exception as ex:
            logger.warning(f"Dialogo file nativo non disponibile ({system}): {ex}")

        if path:
            self._load_photo(path)
        elif not path and system == "Linux":
            # Nessun gestore dialogo trovato: fallback testo
            self._show_path_input_dialog()

    def _pick_photo_mobile(self):
        """
        Apre il file picker nativo Android/iOS tramite ft.FilePicker.
        Funziona su Flet mobile nativo; NON usare su desktop nativo (causa
        "Unknown control") né in web mode (stesso errore, bug upstream
        confermato — vedi _pick_photo(), che intercetta page.web PRIMA di
        arrivare qui e usa show_image_library_picker() al suo posto).

        Riusa SEMPRE self._file_picker, già registrato in did_mount().
        Fallback difensivo: se per qualche motivo did_mount() non l'ha
        ancora creato (page non pronta), lo crea qui al volo — sicuro solo
        perché questo metodo è raggiungibile esclusivamente dal ramo mobile
        nativo di _pick_photo().
        """
        page = self._page
        if page is None:
            return
        if self._file_picker is None:
            self._file_picker = ft.FilePicker()
            self._file_picker.on_result = self._on_mobile_file_picked  # type: ignore[assignment]
            page.overlay.append(self._file_picker)
            page.update()  # type: ignore[unused-coroutine]
        self._file_picker.pick_files(  # type: ignore[unused-coroutine]
            allow_multiple=False,
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["png", "jpg", "jpeg", "gif", "webp", "bmp"],
        )

    def _on_mobile_file_picked(self, e):
        """
        Callback di pick_files() — chiamata SOLO dal ramo mobile nativo
        (Android/iOS) di _pick_photo(); il ramo web non arriva mai qui,
        vedi _pick_photo() (usa show_image_library_picker() invece).

        Mobile nativo (Android/iOS, build "flet build apk/ipa"): Python
        gira SULLO STESSO dispositivo del client, quindi e.files[0].path
        e' gia' leggibile direttamente da questo processo.

        Il picker NON viene rimosso dall'overlay dopo l'uso: resta
        registrato per essere riutilizzato alla prossima modifica foto.
        """
        if not e.files:
            return
        f = e.files[0]
        if f.path:
            self._load_photo(f.path)

    def _show_path_input_dialog(self):
        """
        Fallback universale: dialog con TextField dove l'utente
        incolla o digita il percorso dell'immagine.
        Usato su mobile e su Linux senza zenity/kdialog.
        """
        page = self._page
        if page is None:
            return

        path_field = ft.TextField(
            label="Percorso immagine",
            hint_text="/percorso/immagine.png",
            expand=True,
            autofocus=True,
            bgcolor=COLOR_BG_SECONDARY,
            border_color=COLOR_BORDER,
            focused_border_color=COLOR_ACCENT_CRIMSON,
        )

        def _confirm(e):
            if page is None:
                return
            p = (path_field.value or "").strip()
            page.pop_dialog()
            if p:
                self._load_photo(p)

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Percorso immagine", color=COLOR_TEXT_TITLE,
                          weight=ft.FontWeight.BOLD),
            bgcolor=COLOR_BG_CARD,
            content=ft.Column([
                ft.Text("Incolla o digita il percorso del file immagine:",
                        color=COLOR_TEXT_SECONDARY, size=13),
                ft.Container(height=8),
                path_field,
            ], tight=True, spacing=0),
            actions=[
                ft.TextButton("Annulla",
                              on_click=lambda e: page.pop_dialog() if page else None,
                              style=ft.ButtonStyle(color=COLOR_TEXT_SECONDARY)),
                ft.ElevatedButton("Carica",
                                  icon=ft.Icons.UPLOAD,
                                  on_click=_confirm,
                                  style=ft.ButtonStyle(
                                      bgcolor=COLOR_ACCENT_CRIMSON,
                                      color="#ffffff",
                                      shape=ft.RoundedRectangleBorder(radius=6),
                                  )),
            ],
        )
        page.show_dialog(dlg)

    def _load_photo(self, path: str):
        """
        Legge il file immagine, lo normalizza in JPEG via PIL e lo salva
        come base64 nel DB. La conversione JPEG garantisce un formato uniforme
        compatibile con il data URI usato da ft.Image(src=...) in Flet 0.85.3.
        """
        try:
            import io
            from PIL import Image as PILImage  # type: ignore[import-untyped]
            with PILImage.open(path) as img:
                img = img.convert("RGB")          # rimuovi alpha per JPEG
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=85)
                raw = buf.getvalue()
        except ImportError:
            # PIL non disponibile: usa i bytes raw
            with open(path, "rb") as f:
                raw = f.read()
        except Exception as ex:
            logger.error(f"Errore nel caricamento foto: {ex}")
            return

        encoded = base64.b64encode(raw).decode("utf-8")
        self.character.image_data = encoded
        if not character_repo.update(self.character):
            show_error_dialog(self._page, "Errore nel salvataggio della foto. Riprova.")
            return
        logger.info(f"Foto salvata nel DB ({len(raw)} bytes) per {self.character.name}")
        self._refresh()

    # ------------------------------------------------------------------
    # Refresh — ricarica dal DB e ricostruisce
    # ------------------------------------------------------------------

    def _refresh(self):
        refreshed = character_repo.get_by_id(self.character.id)
        if refreshed:
            self.character = refreshed
        self.proficiencies = character_repo.get_proficiencies(self.character.id)
        self.controls.clear()
        self._build()
        try:
            self.update()
        except RuntimeError:
            pass
        if self._on_refresh:
            self._on_refresh()
