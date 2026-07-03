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
from ui.theme import section_header, muted_text
from data.game_data.wizard_data import BACKGROUNDS
from data.game_data.game_data_loader import GameDataLoader
from core.level_manager import get_level_up_steps, estimate_hp_loss, StepType
import re as _re

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

# Livelli ASI per classe — PHB 5e
_ASI_LEVELS: dict[str, set[int]] = {
    "Guerriero": {4, 6, 8, 12, 14, 16, 19},
    "Ladro":     {4, 8, 10, 12, 16, 19},
}
_ASI_DEFAULT: set[int] = {4, 8, 12, 16, 19}


def _is_asi_level(class_name: str, level: int) -> bool:
    return level in _ASI_LEVELS.get(class_name, _ASI_DEFAULT)


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
        self._level_up_btn: ft.IconButton | None = None
        self._level_down_btn: ft.IconButton | None = None

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

        self.controls = [
            self._build_photo_header(c),
            section_header("Anagrafica"),
            self._build_anagrafica(c),
            section_header("Tratti Razziali"),
            self._build_razza(c),
            section_header("Dettagli Fisici"),
            self._build_fisico(c),
            section_header("Personalità"),
            self._build_personalita(c),
            section_header("Storia"),
            self._build_storia(c),
            section_header("Competenze"),
            self._build_competenze(c, prof_bonus, skill_map, save_map),
            section_header("Talenti"),
            self._build_talenti(c),
        ]

    def did_mount(self):
        self._page = cast(ft.Page, self.page)

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

        self._level_up_btn = ft.IconButton(
            icon=ft.Icons.ARROW_DROP_UP,
            icon_size=22,
            tooltip=f"Sali a Lv.{c.level + 1}",
            on_click=self._on_level_up_click,
            disabled=(c.level >= 20),
            icon_color=COLOR_ACCENT_CRIMSON,
            style=ft.ButtonStyle(padding=ft.Padding.all(0)),
        )
        self._level_down_btn = ft.IconButton(
            icon=ft.Icons.ARROW_DROP_DOWN,
            icon_size=22,
            tooltip=f"Scendi a Lv.{c.level - 1}",
            on_click=self._on_level_down_click,
            disabled=(c.level <= 1),
            icon_color=COLOR_TEXT_MUTED,
            style=ft.ButtonStyle(padding=ft.Padding.all(0)),
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
                                    self._level_up_btn,
                                    self._level_down_btn,
                                ],
                                spacing=0,
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
        race_info = RACE_DATA.get(c.race, {})
        speed = race_info.get("speed", c.speed or 9)
        darkvision = race_info.get("darkvision", 0)
        traits = race_info.get("traits", [])

        rows: list[ft.Control] = [
            self._info_row("Velocità", f"{speed} m"),
            self._info_row("Scurovisione", f"{darkvision} m" if darkvision else "Nessuna"),
        ]
        if traits:
            rows.append(ft.Container(height=4))
            rows.append(ft.Text("Tratti Speciali", size=9, color=COLOR_TEXT_MUTED,
                                 weight=ft.FontWeight.BOLD,
                                 style=ft.TextStyle(letter_spacing=0.8)))
            for t in traits:
                # t è una stringa "Nome — descrizione"
                if " — " in t:
                    name, desc = t.split(" — ", 1)
                else:
                    name, desc = t, ""
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
                    "Nessuna metamagia — disponibile dal Lv.2.",
                    size=12, color=COLOR_TEXT_MUTED, italic=True,
                ))

        # --- Invocazioni Occulte + Patto (solo se Warlock) ---
        if (c.class_name or "").lower() == "warlock":
            # Patto
            rows.append(ft.Divider(color=COLOR_BORDER, height=16))
            rows.append(ft.Text(
                "Dono del Patto", size=13, weight=ft.FontWeight.BOLD,
                color=COLOR_ACCENT_CRIMSON,
            ))
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

        # --- Invocazioni Occulte (solo se Warlock) ---
        if (c.class_name or "").lower() == "warlock":
            rows.append(ft.Divider(color=COLOR_BORDER, height=16))
            rows.append(ft.Text(
                "Invocazioni Occulte",
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
                    "Nessuna invocazione ancora — verranno mostrate dal Lv.2.",
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
        character_repo.update(self.character)

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
        steps = get_level_up_steps(c.class_name or "", new_level, old_pb, new_pb)

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

        def on_asi_type_change(ev):
            val = ev.control.value
            stat_dd1.visible = val in ("two_one", "one_one")
            stat_dd2.visible = val == "one_one"
            feat_dd.visible  = val == "feat"
            # nasconde anche la bonus_dd se si cambia modalità
            if val != "feat":
                feat_bonus_dd.visible = False
            try:
                stat_dd1.update()
                stat_dd2.update()
                feat_dd.update()
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

        # Abilità/strumenti su cui il personaggio è già competente (candidati Perizia)
        _all_profs = character_repo.get_proficiencies(c.id)
        _expertise_candidates = [
            p.name for p in _all_profs
            if p.proficiency_type in ("skill", "tool") and not p.is_expert
        ]

        # Lista di riferimenti ai Checkbox di Perizia per raccogliere le scelte
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

        has_asi = False
        subclass_dd_ref: list[ft.Dropdown] = []  # [0] = dropdown sottoclasse, se presente
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
                    feat_dd,
                    feat_bonus_dd,
                ]

            elif step.step_type == StepType.PACT_CHOICE:
                if not c.pact_boon:
                    pact_rg = ft.RadioGroup(
                        content=ft.Column([
                            ft.Radio(value=b, label=b)
                            for b in PACT_BOONS
                        ], spacing=4),
                        value=PACT_BOONS[0],
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
                available_mm = [o for o in METAMAGIC_OPTIONS if o not in known_mm]
                to_add_mm = min(count, len(available_mm))

                if available_mm:
                    mm_cbs: list[ft.Checkbox] = []
                    metamagic_cb_groups.append((to_add_mm, mm_cbs))

                    def _make_mm_cb(name: str, cbs_ref: list, limit: int) -> ft.Checkbox:
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
                        return cb

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

                    def _make_inv_cb(name: str, cbs_ref: list, limit: int) -> ft.Checkbox:
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
                        return cb

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
                                    f"Invocazioni Occulte — scegli {to_add} nuov{'a' if to_add == 1 else 'e'}",
                                    size=13, weight=ft.FontWeight.BOLD,
                                    color=COLOR_ACCENT_CRIMSON),
                            ], spacing=6),
                            muted_text(
                                f"Totale invocazioni a Lv.{new_level}: {total_inv} "
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
                            ft.Text(f"Perizia — scegli {count} abilità da portare a Maestria",
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
                    eligible_spells = [
                        s for s in _loader.get_spells(c.class_name or "")
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
                        dlg_rows.append(dd)
                    spell_learn_refs.append((step.data, dds))

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
        sc_lower  = (c.subclass   or "").strip().lower()

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
            styles = FIGHTING_STYLES.get(cls_lower, [])
            if styles and new_level == 2 and cls_lower in ("paladino", "ranger"):
                fs_dd = _make_choice_dd("Stile di Combattimento", styles, "")
                fighting_style_dd_ref.append(fs_dd)
                dlg_rows += [
                    ft.Divider(color=COLOR_BORDER),
                    ft.Row([
                        ft.Icon(ft.Icons.SHIELD, size=14, color=COLOR_ACCENT_BLUE),
                        ft.Text("Scegli il tuo Stile di Combattimento",
                                size=13, weight=ft.FontWeight.BOLD, color=COLOR_ACCENT_BLUE),
                    ], spacing=6),
                    fs_dd,
                ]

        # Animale Totem — Barbaro Percorso del Totem Guerriero, Lv3
        if (not c.totem_animal and cls_lower == "barbaro"
                and "totem" in sc_lower and new_level == 3):
            ta_dd = _make_choice_dd("Spirito del Totem", TOTEM_ANIMALS, "")
            totem_animal_dd_ref.append(ta_dd)
            dlg_rows += [
                ft.Divider(color=COLOR_BORDER),
                ft.Row([
                    ft.Icon(ft.Icons.PETS, size=14, color=COLOR_ACCENT_AMBER),
                    ft.Text("Scegli il tuo Spirito Totem",
                            size=13, weight=ft.FontWeight.BOLD, color=COLOR_ACCENT_AMBER),
                ], spacing=6),
                muted_text("L'animale scelto a Lv.3 determina tutte le feature future del Percorso.", size=11),
                ta_dd,
            ]

        # Terreno — Druido Cerchio della Terra, Lv2
        if (not c.land_terrain and cls_lower == "druido"
                and "terra" in sc_lower and new_level == 2):
            lt_dd = _make_choice_dd("Terreno del Cerchio", LAND_TERRAINS, "")
            land_terrain_dd_ref.append(lt_dd)
            dlg_rows += [
                ft.Divider(color=COLOR_BORDER),
                ft.Row([
                    ft.Icon(ft.Icons.LANDSCAPE, size=14, color="#4caf50"),
                    ft.Text("Scegli il Terreno del Cerchio della Terra",
                            size=13, weight=ft.FontWeight.BOLD, color="#4caf50"),
                ], spacing=6),
                muted_text("Il terreno determina gli Incantesimi del Cerchio per ogni livello.", size=11),
                lt_dd,
            ]

        def _save_known_spell(
            spell_name: str, class_name: str, char: Character
        ) -> None:
            """Recupera i dettagli dello spell dal JSON e lo salva come conosciuto."""
            all_spells = _loader.get_spells(class_name)
            spell = next((s for s in all_spells if s.get("name") == spell_name), None)
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

            # Invocazioni Occulte: deve scegliere esattamente il numero richiesto
            # (solo se i checkbox sono stati mostrati, cioè invocations.json non è vuoto)
            for _inv_count, _inv_cbs in invocation_cb_groups:
                if _inv_cbs:
                    _sel_inv = sum(1 for cb in _inv_cbs if cb.value)
                    if _sel_inv < _inv_count:
                        _errors.append(
                            f"Scegli {_inv_count} invocazion"
                            f"{'e' if _inv_count == 1 else 'i'} occulte "
                            f"({_sel_inv}/{_inv_count})"
                        )

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

            c.level = new_level
            c.hp_max += gained
            c.hp_current = min(c.hp_current + gained, c.hp_max)
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

            # Expertise (Perizia)
            for cb_group in expertise_cb_groups:
                chosen = [
                    str(cb.label) for cb in cb_group if cb.value and cb.label
                ]
                if chosen:
                    character_repo.set_expertise(c.id, chosen)

            # Scelte extra: stile di combattimento, animale totem, terreno
            if fighting_style_dd_ref and fighting_style_dd_ref[0].value:
                c.fighting_style = fighting_style_dd_ref[0].value
            if totem_animal_dd_ref and totem_animal_dd_ref[0].value:
                c.totem_animal = totem_animal_dd_ref[0].value
            if land_terrain_dd_ref and land_terrain_dd_ref[0].value:
                c.land_terrain = land_terrain_dd_ref[0].value

            # Incantesimi conosciuti (classi "know")
            for _step_data, dds in spell_learn_refs:
                for dd in dds:
                    if dd.value:
                        _save_known_spell(dd.value, c.class_name or "", c)

            # Segreti Magici (qualsiasi classe)
            for _step_data, choices in magical_secrets_refs:
                for spell_name, class_name in choices:
                    _save_known_spell(spell_name, class_name, c)

            character_repo.update(c)
            # Aggiorna slot incantesimo PHB per il nuovo livello
            character_repo.auto_init_spell_slots(c.id, c.class_name, new_level)
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
            character_repo.update(self.character)
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
            fields["class_name"]  = dd("Classe", list(CLASSES.keys()), c.class_name or "")
            fields["race"]        = dd("Razza", RACES, c.race or "")
            fields["background"]  = dd("Background", list(BACKGROUNDS.keys()), c.background or "")
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
            character_repo.update(c)
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
        - Mobile (Android/iOS): ft.FilePicker nativo — funziona su Flet mobile
        - Desktop (macOS/Windows/Linux): dialogo nativo del SO via subprocess
          (ft.FilePicker è broken su Flet 0.85.3 desktop)
        """
        if self._page is None:
            return
        platform = self._page.platform
        if self._page.web or platform in (ft.PagePlatform.ANDROID, ft.PagePlatform.IOS):
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
        Funziona su Flet mobile; NON usare su desktop (causa "Unknown control").
        """
        page = self._page
        if page is None:
            return
        picker = ft.FilePicker()
        picker.on_result = self._on_mobile_file_picked  # type: ignore[assignment]
        page.overlay.append(picker)
        page.update()  # type: ignore[unused-coroutine]
        picker.pick_files(  # type: ignore[unused-coroutine]
            allow_multiple=False,
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["png", "jpg", "jpeg", "gif", "webp", "bmp"],
        )

    def _on_mobile_file_picked(self, e):
        """Callback del FilePicker mobile — legge il path e carica la foto."""
        page = self._page
        if page is None:
            return
        # Rimuovi il picker dall'overlay
        if e.control in page.overlay:
            page.overlay.remove(e.control)
            page.update()  # type: ignore[unused-coroutine]
        if e.files and len(e.files) > 0:
            path = e.files[0].path
            if path:
                self._load_photo(path)

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
        character_repo.update(self.character)
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
