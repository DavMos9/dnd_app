"""
Form di creazione manuale del personaggio — riscrittura completa.

Flusso in 5 fasi:
    1. Identità     — nome, classe, razza, background, allineamento
    2. Punteggi     — Standard Array pre-assegnato per classe, modificabile
    3. Scelte       — sottorazza, sottoclasse lv1, abilità, lingue/strumenti, extra razziali
    4. Equipaggiamento — oggetti fissi + scelte A/B
    5. Conferma     — riepilogo valori derivati + salvataggio

Il personaggio viene sempre creato a Lv.1.
Per livelli superiori il giocatore usa il level-up nella scheda personaggio.
"""

import copy
import logging
from typing import Any, cast

import flet as ft

from config.settings import (
    COLOR_ACCENT_BLUE, COLOR_ACCENT_CRIMSON, COLOR_ACCENT_GOLD, COLOR_ACCENT_RED,
    COLOR_BG_CARD, COLOR_BG_PRIMARY, COLOR_BG_SECONDARY, COLOR_BG_SELECTED,
    COLOR_BORDER,
    COLOR_TEXT_MUTED, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY, COLOR_TEXT_TITLE,
    ABILITY_KEYS, ABILITY_SCORES, ALIGNMENTS, DRACONIDE_ANCESTRIES,
    LANGUAGES, RACES_BASE,
    SKILLS, STANDARD_ARRAY,
    WEAPONS_BY_CATEGORY,
    get_modifier, get_modifier_str, get_permanent_class_hp_bonus,
)
from core.wizard_engine import WizardEngine
from data.game_data.game_data_loader import GameDataLoader
from data.repositories import character_repo
from ui.theme import (
    body_text, fantasy_card, ghost_button, label_text, muted_text,
    primary_button, section_header, title_text,
)

logger = logging.getLogger(__name__)
_loader = GameDataLoader()
# Solo per get_suggested_stat_assignment — non registra risposte al quiz.
_stat_engine = WizardEngine()


# ---------------------------------------------------------------------------
# Costanti di fase
# ---------------------------------------------------------------------------

_PHASES = ["identity", "stats", "choices", "equipment", "confirm"]
_PROGRESS = {"identity": 0.2, "stats": 0.4, "choices": 0.6, "equipment": 0.8, "confirm": 1.0}


class ManualCreationForm(ft.Column):
    """
    Form di creazione manuale in 5 fasi.

    Callback:
        on_complete(character_id: str)  → personaggio salvato
        on_cancel()                     → torna alla Home
    """

    def __init__(self, on_complete, on_cancel):
        super().__init__(expand=True, spacing=0)
        self.on_complete = on_complete
        self.on_cancel   = on_cancel

        # ---- State fase 1 ----
        self._name:         str = ""
        self._player_name:  str = ""

        # ---- State condiviso fasi 2-5 ----
        _first_class = _loader.get_class_names()[0]
        _first_race  = list(RACES_BASE.keys())[0]
        _bg_names    = _loader.get_background_names()
        _first_bg    = _bg_names[0] if _bg_names else ""

        self._review_class:    str       = _first_class
        self._review_race:     str       = _first_race
        self._review_subrace:  str       = ""
        self._review_subclass: str       = ""
        self._review_bg:       str       = _first_bg
        self._review_align:    str       = ALIGNMENTS[0]
        self._review_stats:    dict      = {}
        self._review_skills:   list[str] = []
        self._review_languages:list[str] = []
        self._review_tools:    list[str] = []
        self._review_dragon_ancestry: str       = ""
        self._review_fighting_style:  str       = ""
        self._review_mezzelf_flex:    list[str] = []
        self._review_mezzelf_skills:  list[str] = []
        self._review_elf_cantrip:     str       = ""
        self._review_umano_language:  str       = ""
        self._review_expertise:       list[str] = []

        # ---- State fase 4 ----
        self._equip_fixed:   list[dict[str, Any]] = []
        self._equip_choices: list[dict[str, Any]] = []
        self._gold_mode:   bool = False
        self._gold_amount: str  = ""

        # ---- Shell UI ----
        self._phase        = "identity"
        self._content      = ft.Container(expand=True, bgcolor=COLOR_BG_PRIMARY)
        self._progress_bar = ft.ProgressBar(
            value=0.2, color=COLOR_ACCENT_CRIMSON, bgcolor=COLOR_BORDER, height=4,
        )
        self._build_shell()
        self._render_identity()

    # -----------------------------------------------------------------------
    # Shell
    # -----------------------------------------------------------------------

    def _build_shell(self) -> None:
        header = ft.Container(
            content=ft.Row(
                [
                    ft.IconButton(
                        icon=ft.Icons.ARROW_BACK,
                        icon_color=COLOR_TEXT_SECONDARY,
                        on_click=self._on_back,
                        tooltip="Indietro",
                    ),
                    ft.Column(
                        [
                            title_text("Creazione Manuale", size=20),
                            muted_text("Inserisci i dati del tuo personaggio", size=12),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=8,
            ),
            padding=ft.Padding.symmetric(horizontal=24, vertical=14),
            bgcolor=COLOR_BG_SECONDARY,
            border=ft.Border.only(bottom=ft.BorderSide(1, COLOR_BORDER)),
        )
        self.controls = [header, self._progress_bar, self._content]

    def _update_progress(self) -> None:
        self._progress_bar.value = _PROGRESS.get(self._phase, 0.0)
        try:
            self._progress_bar.update()
        except RuntimeError:
            pass

    def _set_content(self, control: ft.Control) -> None:
        self._content.content = control
        try:
            self._content.update()
        except RuntimeError:
            pass

    def _on_back(self, e=None) -> None:
        idx = _PHASES.index(self._phase)
        if idx == 0:
            self.on_cancel()
        else:
            prev = _PHASES[idx - 1]
            self._phase = prev
            self._update_progress()
            getattr(self, f"_render_{prev}")()

    # -----------------------------------------------------------------------
    # Helpers — dati background / classe
    # -----------------------------------------------------------------------

    def _bg_skill_proficiencies(self) -> list[str]:
        bg_data = _loader.get_background(self._review_bg)
        return bg_data.get("skill_proficiencies", []) if bg_data else []

    def _class_skill_options(self) -> tuple[int, list[str]]:
        cls_data = _loader.get_class(self._review_class)
        if not cls_data:
            return 0, []
        sc    = cls_data.get("skill_choices", {})
        count = sc.get("count", 0)
        opts  = sc.get("options", [])
        if opts == "any":
            opts = list(SKILLS.keys())
        return count, [o for o in opts if o not in self._bg_skill_proficiencies()]

    def _bg_language_choices(self) -> tuple[int, str]:
        bg_data = _loader.get_background(self._review_bg)
        if not bg_data:
            return 0, ""
        for entry in bg_data.get("languages", []):
            if isinstance(entry, dict) and entry.get("type") == "choice":
                return entry.get("count", 1), entry.get("from", "any")
        return 0, ""

    def _bg_tool_choices(self) -> list[tuple[int, list[str]]]:
        bg_data = _loader.get_background(self._review_bg)
        if not bg_data:
            return []
        result: list[tuple[int, list[str]]] = []
        for entry in bg_data.get("tool_proficiencies", []):
            if isinstance(entry, dict) and entry.get("type") == "choice":
                frm   = entry.get("from", "")
                count = entry.get("count", 1)
                tool_categories = _loader.get_tool_categories()
                if isinstance(frm, list):
                    seen_labels: set[str] = set()
                    opts = []
                    for k in frm:
                        lbl = _loader.get_tool_category_label(k) or tool_categories.get(k, [k])[0]
                        if lbl not in seen_labels:
                            opts.append(lbl)
                            seen_labels.add(lbl)
                else:
                    opts = tool_categories.get(frm, [])
                result.append((count, opts))
        return result

    # -----------------------------------------------------------------------
    # Helper — factory dropdown
    # -----------------------------------------------------------------------

    @staticmethod
    def _dd(label: str, options: list[str], value: str | None, on_select) -> ft.Dropdown:
        return ft.Dropdown(
            label=label,
            value=value,
            options=[ft.DropdownOption(key=o, text=o) for o in options],
            on_select=on_select,
            bgcolor=COLOR_BG_CARD,
            color=COLOR_TEXT_PRIMARY,
            label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=12),
            border_color=COLOR_BORDER,
            focused_border_color=COLOR_ACCENT_GOLD,
            expand=True,
        )

    # -----------------------------------------------------------------------
    # FASE 1 — Identità
    # -----------------------------------------------------------------------

    def _render_identity(self) -> None:
        self._phase = "identity"
        self._update_progress()

        name_tf = ft.TextField(
            label="Nome Personaggio *",
            value=self._name,
            autofocus=True,
            bgcolor=COLOR_BG_CARD, color=COLOR_TEXT_PRIMARY,
            label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=12),
            border_color=COLOR_BORDER, focused_border_color=COLOR_ACCENT_GOLD,
            cursor_color=COLOR_ACCENT_GOLD,
            on_change=lambda e: setattr(self, "_name", e.control.value or ""),
            expand=True,
        )
        player_tf = ft.TextField(
            label="Nome Giocatore (opzionale)",
            value=self._player_name,
            bgcolor=COLOR_BG_CARD, color=COLOR_TEXT_PRIMARY,
            label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=12),
            border_color=COLOR_BORDER, focused_border_color=COLOR_ACCENT_GOLD,
            cursor_color=COLOR_ACCENT_GOLD,
            on_change=lambda e: setattr(self, "_player_name", e.control.value or ""),
            expand=True,
        )

        _class_names = _loader.get_class_names()
        _bg_names    = _loader.get_background_names()
        class_val = self._review_class if self._review_class in _class_names else _class_names[0]
        race_val  = self._review_race  if self._review_race  in RACES_BASE else list(RACES_BASE.keys())[0]
        bg_val    = self._review_bg    if self._review_bg    in _bg_names  else (_bg_names[0] if _bg_names else None)
        align_val = self._review_align if self._review_align in ALIGNMENTS else ALIGNMENTS[0]

        def _on_class_change(val: str) -> None:
            self._review_class        = val
            self._review_subclass     = ""
            self._review_dragon_ancestry = ""
            self._review_fighting_style  = ""
            self._review_skills       = []
            self._review_expertise    = []

        def _on_race_change(val: str) -> None:
            self._review_race         = val
            self._review_subrace      = ""
            self._review_mezzelf_flex = []
            self._review_mezzelf_skills = []
            self._review_elf_cantrip  = ""
            self._review_umano_language = ""

        def _on_bg_change(val: str) -> None:
            self._review_bg        = val
            self._review_skills    = []
            self._review_languages = []
            self._review_tools     = []
            self._review_expertise = []

        class_dd = self._dd("Classe *", _class_names, class_val,
                            lambda e: _on_class_change(e.control.value or ""))
        race_dd  = self._dd("Razza *",  list(RACES_BASE.keys()), race_val,
                            lambda e: _on_race_change(e.control.value or ""))
        bg_dd    = self._dd("Background *", _bg_names, bg_val,
                            lambda e: _on_bg_change(e.control.value or ""))
        align_dd = self._dd("Allineamento", ALIGNMENTS, align_val,
                            lambda e: setattr(self, "_review_align", e.control.value or ALIGNMENTS[0]))

        error_text = ft.Text("", color=COLOR_ACCENT_RED, size=13, visible=False)

        def _on_continue(e) -> None:
            nm = (name_tf.value or "").strip()
            if not nm:
                error_text.value   = "Il nome del personaggio è obbligatorio."
                error_text.visible = True
                try:
                    error_text.update()
                except RuntimeError:
                    pass
                return
            self._name        = nm
            self._player_name = (player_tf.value or "").strip()
            if not self._review_bg:
                _bg_names_fallback = _loader.get_background_names()
                if _bg_names_fallback:
                    self._review_bg = _bg_names_fallback[0]
            # Inizializza Standard Array ottimale per la classe scelta
            self._review_stats = _stat_engine.get_suggested_stat_assignment(self._review_class)
            self._phase = "stats"
            self._update_progress()
            self._render_stats()

        content = ft.Column(
            [
                ft.Text("Chi è il tuo personaggio?", size=22,
                        weight=ft.FontWeight.BOLD, color=COLOR_TEXT_TITLE),
                ft.Container(height=4),
                muted_text("Inserisci i dati base. HP, CA e velocità verranno derivati automaticamente.", size=13),
                ft.Container(height=20),
                fantasy_card(ft.Column([
                    section_header("Nome e Giocatore"),
                    name_tf,
                    player_tf,
                ], spacing=12), padding=16),
                ft.Container(height=16),
                fantasy_card(ft.Column([
                    section_header("Classe, Razza e Background"),
                    class_dd,
                    race_dd,
                    bg_dd,
                    align_dd,
                ], spacing=12), padding=16),
                ft.Container(height=8),
                error_text,
                ft.Container(height=16),
                ft.Row(
                    [
                        ghost_button("Annulla", on_click=lambda e: self.on_cancel()),
                        primary_button("Continua", on_click=_on_continue, icon=ft.Icons.ARROW_FORWARD),
                    ],
                    alignment=ft.MainAxisAlignment.END,
                    spacing=12,
                ),
            ],
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )
        self._set_content(
            ft.Container(content=content, expand=True,
                         padding=ft.Padding.symmetric(horizontal=16, vertical=20))
        )

    # -----------------------------------------------------------------------
    # FASE 2 — Punteggi
    # -----------------------------------------------------------------------

    def _render_stats(self) -> None:
        self._phase = "stats"
        self._update_progress()

        stat_dropdowns: dict[str, ft.Dropdown] = {}

        def _make_stat_row(key: str, label: str) -> ft.Row:
            val     = self._review_stats.get(key, 10)
            mod_str = get_modifier_str(val)
            mod     = get_modifier(val)
            dd = ft.Dropdown(
                value=str(val),
                options=[ft.DropdownOption(key=str(v), text=str(v))
                         for v in sorted(STANDARD_ARRAY, reverse=True)],
                on_select=lambda e, k=key: _on_stat_change(k, int(e.control.value or 10)),
                bgcolor=COLOR_BG_CARD, color=COLOR_TEXT_PRIMARY,
                border_color=COLOR_BORDER, focused_border_color=COLOR_ACCENT_GOLD,
                width=110,
            )
            stat_dropdowns[key] = dd
            badge = ft.Container(
                content=ft.Text(mod_str, size=13, weight=ft.FontWeight.BOLD,
                                color=COLOR_ACCENT_BLUE if mod >= 0 else COLOR_ACCENT_RED),
                width=40,
                alignment=ft.Alignment.CENTER,
            )
            return ft.Row(
                [ft.Text(label, size=13, color=COLOR_TEXT_PRIMARY, expand=True), dd, badge],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=8,
            )

        def _on_stat_change(key: str, new_val: int) -> None:
            self._review_stats[key] = new_val
            for k, dd_ctrl in stat_dropdowns.items():
                v   = self._review_stats.get(k, 10)
                row = dd_ctrl.parent
                if row and len(cast(ft.Row, row).controls) >= 3:
                    badge = cast(ft.Container, cast(ft.Row, row).controls[2])
                    cast(ft.Text, badge.content).value = get_modifier_str(v)
                    cast(ft.Text, badge.content).color = (
                        COLOR_ACCENT_GOLD if get_modifier(v) >= 0 else COLOR_ACCENT_RED
                    )
                    badge.update()
            hp_note.value = _hp_note()
            try:
                hp_note.update()
            except RuntimeError:
                pass

        def _hp_note() -> str:
            hd      = (_loader.get_class(self._review_class) or {}).get("hit_die", 8)
            con_mod = get_modifier(self._review_stats.get("con", 10))
            hp      = max(1, hd + con_mod)
            sign    = "+" if con_mod >= 0 else ""
            return f"HP al Lv.1: d{hd}{sign}{con_mod} = {hp}  (cambia COS. per aggiornare)"

        stat_rows = ft.Column(
            [_make_stat_row(k, lbl) for k, lbl in zip(ABILITY_KEYS, ABILITY_SCORES)],
            spacing=8,
        )
        hp_note = ft.Text(_hp_note(), size=11, color=COLOR_TEXT_MUTED, italic=True)

        # Anteprima bonus razziali (solo info, vengono applicati al salvataggio)
        # get_resolved_race() somma già base+sottorazza leggendo solo dal JSON.
        race_info = _loader.get_resolved_race(self._review_race, self._review_subrace)
        bonuses   = race_info.get("ability_bonuses", {})
        bonus_lines: list[ft.Control] = []
        if bonuses:
            stat_abbr = dict(zip(ABILITY_KEYS, ABILITY_SCORES))
            parts = [
                f"{stat_abbr.get(k, k.upper())} +{v}" if v > 0 else f"{stat_abbr.get(k, k.upper())} {v}"
                for k, v in bonuses.items()
            ]
            bonus_lines.append(
                muted_text(f"Bonus razziali applicati al salvataggio: {', '.join(parts)}", size=11)
            )

        content = ft.Column(
            [
                ft.Text("Assegna i punteggi", size=22,
                        weight=ft.FontWeight.BOLD, color=COLOR_TEXT_TITLE),
                ft.Container(height=4),
                muted_text(
                    f"Standard Array [{', '.join(str(v) for v in sorted(STANDARD_ARRAY, reverse=True))}] "
                    f"pre-assegnato in base alla classe {self._review_class}. Puoi spostare i valori liberamente.",
                    size=13,
                ),
                ft.Container(height=20),
                fantasy_card(ft.Column([
                    section_header("Caratteristiche"),
                    stat_rows,
                    ft.Container(height=6),
                    hp_note,
                    *bonus_lines,
                ], spacing=8), padding=20),
                ft.Container(height=20),
                ft.Row(
                    [
                        ghost_button("Indietro", on_click=self._on_back),
                        primary_button("Continua", on_click=lambda e: self._goto_choices(),
                                       icon=ft.Icons.ARROW_FORWARD),
                    ],
                    alignment=ft.MainAxisAlignment.END,
                    spacing=12,
                ),
            ],
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )
        self._set_content(
            ft.Container(content=content, expand=True,
                         padding=ft.Padding.symmetric(horizontal=16, vertical=20))
        )

    # -----------------------------------------------------------------------
    # FASE 3 — Scelte (sottorazza, sottoclasse, abilità, lingue, strumenti, extra)
    # -----------------------------------------------------------------------

    def _goto_choices(self) -> None:
        self._phase = "choices"
        self._update_progress()
        self._render_choices()

    def _render_choices(self) -> None:
        self._phase = "choices"
        self._update_progress()

        # ---- Sottorazza / Discendenza draconica ----
        subrace_col = ft.Column([], spacing=8, visible=False)

        def _rebuild_subrace_col() -> None:
            subrace_col.controls.clear()
            subraces = RACES_BASE.get(self._review_race, [])
            if self._review_race == "Dragonide":
                val = self._review_subrace or DRACONIDE_ANCESTRIES[0]
                if not self._review_subrace:
                    self._review_subrace = val
                subrace_col.controls.append(ft.Dropdown(
                    label="Discendenza Draconica",
                    value=val,
                    options=[ft.DropdownOption(key=a, text=a) for a in DRACONIDE_ANCESTRIES],
                    on_select=lambda e: setattr(self, "_review_subrace", e.control.value or ""),
                    bgcolor=COLOR_BG_CARD, color=COLOR_TEXT_PRIMARY,
                    label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=12),
                    border_color=COLOR_BORDER, focused_border_color=COLOR_ACCENT_GOLD,
                    expand=True,
                ))
                subrace_col.visible = True
            elif subraces:
                val = self._review_subrace if self._review_subrace in subraces else subraces[0]
                self._review_subrace = val
                subrace_col.controls.append(ft.Dropdown(
                    label="Sottorazza",
                    value=val,
                    options=[ft.DropdownOption(key=s, text=s) for s in subraces],
                    on_select=lambda e: [
                        setattr(self, "_review_subrace", e.control.value or ""),
                        _rebuild_race_extras_col(),
                        _update_extra_card(),
                    ],
                    bgcolor=COLOR_BG_CARD, color=COLOR_TEXT_PRIMARY,
                    label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=12),
                    border_color=COLOR_BORDER, focused_border_color=COLOR_ACCENT_GOLD,
                    expand=True,
                ))
                subrace_col.visible = True
            else:
                self._review_subrace = ""
                subrace_col.visible = False
            try:
                subrace_col.update()
            except RuntimeError:
                pass

        # ---- Sottoclasse lv1 ----
        subclass_col = ft.Column([], spacing=8, visible=False)

        def _rebuild_subclass_col() -> None:
            subclass_col.controls.clear()
            cls_data = _loader.get_class(self._review_class)
            if not cls_data or cls_data.get("subclass_choice_level", 99) != 1:
                self._review_subclass = ""
                subclass_col.visible  = False
                try:
                    subclass_col.update()
                except RuntimeError:
                    pass
                return
            subclasses  = [sc.get("name", "") for sc in cls_data.get("subclasses", [])]
            label_name  = cls_data.get("subclass_label", "Sottoclasse")
            val         = self._review_subclass if self._review_subclass in subclasses else (subclasses[0] if subclasses else "")
            self._review_subclass = val
            subclass_col.controls.append(ft.Dropdown(
                label=label_name,
                value=val,
                options=[ft.DropdownOption(key=s, text=s) for s in subclasses],
                on_select=lambda e: [
                    setattr(self, "_review_subclass", e.control.value or ""),
                    _rebuild_dragon_col(),
                    _update_extra_card(),
                ],
                bgcolor=COLOR_BG_CARD, color=COLOR_TEXT_PRIMARY,
                label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=12),
                border_color=COLOR_BORDER, focused_border_color=COLOR_ACCENT_GOLD,
                expand=True,
            ))
            subclass_col.visible = bool(subclasses)
            try:
                subclass_col.update()
            except RuntimeError:
                pass

        # ---- Tipo drago antenato (Stregone + Discendenza Draconica) ----
        dragon_col = ft.Column([], spacing=8, visible=False)

        def _rebuild_dragon_col() -> None:
            dragon_col.controls.clear()
            if self._review_subclass == "Discendenza Draconica":
                if not self._review_dragon_ancestry:
                    self._review_dragon_ancestry = DRACONIDE_ANCESTRIES[0]
                curr = self._review_dragon_ancestry if self._review_dragon_ancestry in DRACONIDE_ANCESTRIES else DRACONIDE_ANCESTRIES[0]
                self._review_dragon_ancestry = curr
                dragon_col.controls.append(ft.Dropdown(
                    label="Tipo di Drago Antenato",
                    value=curr,
                    options=[ft.DropdownOption(key=a, text=a) for a in DRACONIDE_ANCESTRIES],
                    on_select=lambda e: setattr(self, "_review_dragon_ancestry", e.control.value or ""),
                    bgcolor=COLOR_BG_CARD, color=COLOR_TEXT_PRIMARY,
                    label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=12),
                    border_color=COLOR_BORDER, focused_border_color=COLOR_ACCENT_GOLD,
                    expand=True,
                ))
                dragon_col.visible = True
            else:
                self._review_dragon_ancestry = ""
                dragon_col.visible           = False
            try:
                dragon_col.update()
            except RuntimeError:
                pass

        # ---- Stile di combattimento ----
        fighting_style_col = ft.Column([], spacing=8, visible=False)

        def _rebuild_fighting_style_col() -> None:
            fighting_style_col.controls.clear()
            styles = _loader.get_fighting_styles((self._review_class or "").strip())
            if styles:
                if not self._review_fighting_style or self._review_fighting_style not in styles:
                    self._review_fighting_style = styles[0]
                fighting_style_col.controls.append(ft.Dropdown(
                    label="Stile di Combattimento",
                    value=self._review_fighting_style,
                    options=[ft.DropdownOption(key=s, text=s) for s in styles],
                    on_select=lambda e: setattr(self, "_review_fighting_style", e.control.value or ""),
                    bgcolor=COLOR_BG_CARD, color=COLOR_TEXT_PRIMARY,
                    label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=12),
                    border_color=COLOR_BORDER, focused_border_color=COLOR_ACCENT_GOLD,
                    expand=True,
                ))
                fighting_style_col.visible = True
            else:
                self._review_fighting_style = ""
                fighting_style_col.visible  = False
            try:
                fighting_style_col.update()
            except RuntimeError:
                pass

        # ---- Extra razziali: Mezzelf / Alto Elfo / Umano ----
        race_extras_col = ft.Column([], spacing=10, visible=False)

        def _rebuild_race_extras_col() -> None:
            race_extras_col.controls.clear()
            has_content = False
            race    = (self._review_race   or "").strip()
            subrace = (self._review_subrace or "").strip()

            # Mezzelfo: +1 a 2 stat (escluso CHA già +2)
            if race == "Mezzelfo":
                has_content   = True
                all_stat_keys = [k for k in ABILITY_KEYS if k != "cha"]
                stat_labels   = {k: ABILITY_SCORES[i] for i, k in enumerate(ABILITY_KEYS)}
                self._review_mezzelf_flex = [k for k in self._review_mezzelf_flex if k in all_stat_keys]
                while len(self._review_mezzelf_flex) < 2:
                    for k in all_stat_keys:
                        if k not in self._review_mezzelf_flex:
                            self._review_mezzelf_flex.append(k)
                            break

                race_extras_col.controls.append(
                    ft.Text("Versatilità Mezzelf — assegna +1 a due caratteristiche (escluso Carisma)",
                            size=13, color=COLOR_TEXT_PRIMARY, weight=ft.FontWeight.W_600)
                )
                flex_dds: list[ft.Control] = []
                for slot in range(2):
                    curr_key = self._review_mezzelf_flex[slot] if slot < len(self._review_mezzelf_flex) else all_stat_keys[slot]

                    def _make_flex_handler(slot_idx: int):
                        def _handler(e: Any) -> None:
                            while len(self._review_mezzelf_flex) <= slot_idx:
                                self._review_mezzelf_flex.append("")
                            self._review_mezzelf_flex[slot_idx] = e.control.value or ""
                        return _handler

                    flex_dds.append(ft.Dropdown(
                        label=f"+1 a (scelta {slot + 1})",
                        value=curr_key,
                        options=[ft.DropdownOption(key=k, text=stat_labels.get(k, k)) for k in all_stat_keys],
                        on_select=_make_flex_handler(slot),
                        bgcolor=COLOR_BG_CARD, color=COLOR_TEXT_PRIMARY,
                        label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=12),
                        border_color=COLOR_BORDER, focused_border_color=COLOR_ACCENT_GOLD,
                        expand=True,
                    ))
                race_extras_col.controls.append(ft.Row(flex_dds, spacing=12))

                # Mezzelf: 2 abilità a scelta (Versatilità nelle Abilità)
                all_skills = list(SKILLS.keys())
                self._review_mezzelf_skills = [s for s in self._review_mezzelf_skills if s in all_skills]
                mez_count   = 2
                mez_counter = ft.Text(f"({len(self._review_mezzelf_skills)}/{mez_count})",
                                      size=11, color=COLOR_TEXT_MUTED)
                mez_label_row = ft.Row([
                    ft.Text(f"Scegli {mez_count} abilità (tratto razziale)",
                            size=13, color=COLOR_TEXT_PRIMARY, weight=ft.FontWeight.W_600),
                    ft.Container(expand=True),
                    mez_counter,
                ])
                race_extras_col.controls.append(mez_label_row)
                mez_checks: dict[str, ft.Checkbox] = {}

                def _on_mez_skill(skill: str, val: bool) -> None:
                    if val:
                        if len(self._review_mezzelf_skills) < mez_count:
                            if skill not in self._review_mezzelf_skills:
                                self._review_mezzelf_skills.append(skill)
                        else:
                            cb = mez_checks.get(skill)
                            if cb:
                                cb.value = False
                                try:
                                    cb.update()
                                except RuntimeError:
                                    pass
                            return
                    else:
                        if skill in self._review_mezzelf_skills:
                            self._review_mezzelf_skills.remove(skill)
                    mez_counter.value = f"({len(self._review_mezzelf_skills)}/{mez_count})"
                    try:
                        mez_counter.update()
                    except RuntimeError:
                        pass

                left_m: list[ft.Control] = []
                right_m: list[ft.Control] = []
                for i, sk in enumerate(all_skills):
                    cb = ft.Checkbox(
                        label=sk, value=sk in self._review_mezzelf_skills,
                        fill_color=COLOR_ACCENT_GOLD, check_color="#ffffff",
                        label_style=ft.TextStyle(size=12, color=COLOR_TEXT_PRIMARY),
                        on_change=lambda e, s=sk: _on_mez_skill(s, bool(e.control.value)),
                    )
                    mez_checks[sk] = cb
                    (left_m if i % 2 == 0 else right_m).append(cb)
                race_extras_col.controls.append(ft.Row(
                    [ft.Column(left_m, spacing=4, expand=True),
                     ft.Column(right_m, spacing=4, expand=True)],
                    spacing=8,
                ))

            # Alto Elfo: trucchetto del Mago
            if race == "Elfo" and subrace == "Elfo Alto":
                has_content = True
                mago_cantrips = _loader.get_mago_cantrips()
                if not self._review_elf_cantrip or self._review_elf_cantrip not in mago_cantrips:
                    self._review_elf_cantrip = mago_cantrips[0] if mago_cantrips else ""
                race_extras_col.controls.append(ft.Dropdown(
                    label="Trucchetto del Mago (tratto Elfo Alto)",
                    value=self._review_elf_cantrip,
                    options=[ft.DropdownOption(key=c, text=c) for c in mago_cantrips],
                    on_select=lambda e: setattr(self, "_review_elf_cantrip", e.control.value or ""),
                    bgcolor=COLOR_BG_CARD, color=COLOR_TEXT_PRIMARY,
                    label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=12),
                    border_color=COLOR_BORDER, focused_border_color=COLOR_ACCENT_GOLD,
                    expand=True,
                ))
            elif race != "Elfo":
                self._review_elf_cantrip = ""

            # Umano: lingua aggiuntiva
            if race == "Umano":
                has_content = True
                avail = [l for l in LANGUAGES if l != "Comune"]
                if not self._review_umano_language or self._review_umano_language not in avail:
                    self._review_umano_language = avail[0] if avail else ""
                race_extras_col.controls.append(ft.Dropdown(
                    label="Lingua aggiuntiva (tratto Umano)",
                    value=self._review_umano_language,
                    options=[ft.DropdownOption(key=l, text=l) for l in avail],
                    on_select=lambda e: setattr(self, "_review_umano_language", e.control.value or ""),
                    bgcolor=COLOR_BG_CARD, color=COLOR_TEXT_PRIMARY,
                    label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=12),
                    border_color=COLOR_BORDER, focused_border_color=COLOR_ACCENT_GOLD,
                    expand=True,
                ))
            else:
                self._review_umano_language = ""

            race_extras_col.visible = has_content
            try:
                race_extras_col.update()
            except RuntimeError:
                pass

        # ---- Abilità di classe ----
        skills_col    = ft.Column([], spacing=6, visible=False)
        skill_checks: dict[str, ft.Checkbox] = {}

        def _rebuild_skills_col() -> None:
            skills_col.controls.clear()
            skill_checks.clear()
            count, opts = self._class_skill_options()
            if count == 0 or not opts:
                skills_col.visible = False
                try:
                    skills_col.update()
                except RuntimeError:
                    pass
                return
            self._review_skills = [s for s in self._review_skills if s in opts]
            counter_text = ft.Text(f"({len(self._review_skills)}/{count} selezionate)",
                                   size=11, color=COLOR_TEXT_MUTED)
            label_row = ft.Row([
                ft.Text(f"Scegli {count} abilità dalla lista", size=13,
                        color=COLOR_TEXT_PRIMARY, weight=ft.FontWeight.W_600),
                ft.Container(expand=True),
                counter_text,
            ])
            skills_col.controls.append(label_row)

            def _on_skill_toggle(skill: str, val: bool) -> None:
                if val:
                    if len(self._review_skills) < count:
                        if skill not in self._review_skills:
                            self._review_skills.append(skill)
                    else:
                        cb = skill_checks.get(skill)
                        if cb:
                            cb.value = False
                            try:
                                cb.update()
                            except RuntimeError:
                                pass
                        return
                else:
                    if skill in self._review_skills:
                        self._review_skills.remove(skill)
                counter_text.value = f"({len(self._review_skills)}/{count} selezionate)"
                try:
                    counter_text.update()
                except RuntimeError:
                    pass
                _rebuild_expertise_col()

            left_col: list[ft.Control] = []
            right_col: list[ft.Control] = []
            for i, skill in enumerate(opts):
                cb = ft.Checkbox(
                    label=skill, value=skill in self._review_skills,
                    fill_color=COLOR_ACCENT_CRIMSON, check_color="#ffffff",
                    label_style=ft.TextStyle(size=12, color=COLOR_TEXT_PRIMARY),
                    on_change=lambda e, s=skill: _on_skill_toggle(s, bool(e.control.value)),
                )
                skill_checks[skill] = cb
                (left_col if i % 2 == 0 else right_col).append(cb)

            skills_col.controls.append(ft.Row(
                [ft.Column(left_col, spacing=4, expand=True),
                 ft.Column(right_col, spacing=4, expand=True)],
                spacing=8,
            ))
            bg_skills = self._bg_skill_proficiencies()
            if bg_skills:
                skills_col.controls.append(
                    muted_text(f"Background concede già: {', '.join(bg_skills)}", size=11)
                )
            skills_col.visible = True
            try:
                skills_col.update()
            except RuntimeError:
                pass

        # ---- Perizia Ladro Lv1 ----
        expertise_col    = ft.Column([], spacing=6, visible=False)
        expertise_checks: dict[str, ft.Checkbox] = {}

        def _rebuild_expertise_col() -> None:
            expertise_col.controls.clear()
            expertise_checks.clear()
            if self._review_class.lower() != "ladro":
                self._review_expertise = []
                expertise_col.visible  = False
                try:
                    expertise_col.update()
                except RuntimeError:
                    pass
                return
            bg_skills = self._bg_skill_proficiencies()
            pool      = list(dict.fromkeys(bg_skills + self._review_skills))
            if not pool:
                expertise_col.visible = False
                try:
                    expertise_col.update()
                except RuntimeError:
                    pass
                return
            self._review_expertise = [s for s in self._review_expertise if s in pool]
            exp_counter = ft.Text(f"({len(self._review_expertise)}/2 selezionate)",
                                  size=11, color=COLOR_TEXT_MUTED)
            expertise_col.controls.append(ft.Row([
                ft.Text("Scegli 2 abilità per la Perizia (Lv.1)",
                        size=13, color=COLOR_TEXT_PRIMARY, weight=ft.FontWeight.W_600),
                ft.Container(expand=True),
                exp_counter,
            ]))

            def _on_expertise_toggle(skill: str, val: bool) -> None:
                if val:
                    if len(self._review_expertise) < 2:
                        if skill not in self._review_expertise:
                            self._review_expertise.append(skill)
                    else:
                        cb = expertise_checks.get(skill)
                        if cb:
                            cb.value = False
                            try:
                                cb.update()
                            except RuntimeError:
                                pass
                        return
                else:
                    if skill in self._review_expertise:
                        self._review_expertise.remove(skill)
                exp_counter.value = f"({len(self._review_expertise)}/2 selezionate)"
                try:
                    exp_counter.update()
                except RuntimeError:
                    pass

            left_exp: list[ft.Control] = []
            right_exp: list[ft.Control] = []
            for i, skill in enumerate(pool):
                cb = ft.Checkbox(
                    label=skill, value=skill in self._review_expertise,
                    fill_color=COLOR_ACCENT_BLUE, check_color="#ffffff",
                    label_style=ft.TextStyle(size=12, color=COLOR_TEXT_PRIMARY),
                    on_change=lambda e, s=skill: _on_expertise_toggle(s, bool(e.control.value)),
                )
                expertise_checks[skill] = cb
                (left_exp if i % 2 == 0 else right_exp).append(cb)

            expertise_col.controls.append(ft.Row(
                [ft.Column(left_exp, spacing=4, expand=True),
                 ft.Column(right_exp, spacing=4, expand=True)],
                spacing=8,
            ))
            expertise_col.controls.append(
                muted_text("La Perizia raddoppia il bonus di competenza per le abilità scelte.", size=11)
            )
            expertise_col.visible = True
            try:
                expertise_col.update()
            except RuntimeError:
                pass

        # ---- Lingue + strumenti background ----
        lang_tool_col = ft.Column([], spacing=8, visible=False)

        def _rebuild_lang_tool_col() -> None:
            lang_tool_col.controls.clear()
            has_content = False

            lang_count, _ = self._bg_language_choices()
            if lang_count > 0:
                has_content = True
                avail_langs = LANGUAGES
                self._review_languages = [l for l in self._review_languages if l in avail_langs]
                lang_counter = ft.Text(f"({len(self._review_languages)}/{lang_count})",
                                       size=11, color=COLOR_TEXT_MUTED)
                lang_tool_col.controls.append(ft.Row([
                    ft.Text(f"Scegli {lang_count} lingua{'e' if lang_count > 1 else ''}",
                            size=13, color=COLOR_TEXT_PRIMARY, weight=ft.FontWeight.W_600),
                    ft.Container(expand=True),
                    lang_counter,
                ]))
                lang_checks: dict[str, ft.Checkbox] = {}

                def _on_lang_toggle(lang: str, val: bool) -> None:
                    if val:
                        if len(self._review_languages) < lang_count:
                            if lang not in self._review_languages:
                                self._review_languages.append(lang)
                        else:
                            cb = lang_checks.get(lang)
                            if cb:
                                cb.value = False
                                try:
                                    cb.update()
                                except RuntimeError:
                                    pass
                            return
                    else:
                        if lang in self._review_languages:
                            self._review_languages.remove(lang)
                    lang_counter.value = f"({len(self._review_languages)}/{lang_count})"
                    try:
                        lang_counter.update()
                    except RuntimeError:
                        pass

                ll: list[ft.Control] = []
                rl: list[ft.Control] = []
                for i, lang in enumerate(avail_langs):
                    cb = ft.Checkbox(
                        label=lang, value=lang in self._review_languages,
                        fill_color=COLOR_ACCENT_GOLD, check_color="#ffffff",
                        label_style=ft.TextStyle(size=12, color=COLOR_TEXT_PRIMARY),
                        on_change=lambda e, lg=lang: _on_lang_toggle(lg, bool(e.control.value)),
                    )
                    lang_checks[lang] = cb
                    (ll if i % 2 == 0 else rl).append(cb)
                lang_tool_col.controls.append(ft.Row(
                    [ft.Column(ll, spacing=4, expand=True),
                     ft.Column(rl, spacing=4, expand=True)],
                    spacing=8,
                ))

            for tc_idx, (tc_count, tc_opts) in enumerate(self._bg_tool_choices()):
                if not tc_opts:
                    continue
                has_content = True
                if len(self._review_tools) <= tc_idx:
                    self._review_tools.append("")
                curr_tool = self._review_tools[tc_idx] if tc_idx < len(self._review_tools) else ""
                if curr_tool not in tc_opts:
                    curr_tool = tc_opts[0]
                    if tc_idx < len(self._review_tools):
                        self._review_tools[tc_idx] = curr_tool
                    else:
                        self._review_tools.append(curr_tool)
                lang_tool_col.controls.append(ft.Dropdown(
                    label="Strumento a scelta",
                    value=curr_tool,
                    options=[ft.DropdownOption(key=t, text=t) for t in tc_opts],
                    on_select=lambda e, idx=tc_idx: _set_tool(idx, e.control.value or ""),
                    bgcolor=COLOR_BG_CARD, color=COLOR_TEXT_PRIMARY,
                    label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=12),
                    border_color=COLOR_BORDER, focused_border_color=COLOR_ACCENT_GOLD,
                    expand=True,
                ))
            lang_tool_col.visible = has_content
            try:
                lang_tool_col.update()
            except RuntimeError:
                pass

        def _set_tool(idx: int, val: str) -> None:
            while len(self._review_tools) <= idx:
                self._review_tools.append("")
            self._review_tools[idx] = val

        # Inizializzazione
        _rebuild_subrace_col()
        _rebuild_subclass_col()
        _rebuild_dragon_col()
        _rebuild_fighting_style_col()
        _rebuild_race_extras_col()
        _rebuild_skills_col()
        _rebuild_expertise_col()
        _rebuild_lang_tool_col()

        # ---- Visibilità sezioni ----
        sec_razza_classe   = ft.Container(content=section_header("Razza e Classe"),     visible=False)
        sec_extra_razziali = ft.Container(content=section_header("Extra Razziali"),      visible=False)
        sec_abilita        = ft.Container(content=section_header("Abilità di Classe"),   visible=False)
        sec_perizia        = ft.Container(content=section_header("Perizia (Ladro Lv.1)"), visible=False)
        sec_lang_tool      = ft.Container(content=section_header("Lingue e Strumenti"),  visible=False)

        extra_card_content = ft.Column([
            sec_razza_classe,
            subrace_col,
            subclass_col,
            dragon_col,
            fighting_style_col,
            sec_extra_razziali,
            race_extras_col,
            sec_abilita,
            skills_col,
            sec_perizia,
            expertise_col,
            sec_lang_tool,
            lang_tool_col,
        ], spacing=12)

        no_choices_text = ft.Text(
            "Nessuna scelta richiesta per questa combinazione classe/razza/background.",
            size=13, color=COLOR_TEXT_MUTED, italic=True,
        )

        extra_card = ft.Container(
            content=extra_card_content,
            bgcolor=COLOR_BG_CARD,
            border=ft.Border.only(top=ft.BorderSide(3, COLOR_ACCENT_CRIMSON)),
            border_radius=ft.BorderRadius.all(8),
            padding=20,
        )

        def _update_extra_card() -> None:
            has_rc = subrace_col.visible or subclass_col.visible or dragon_col.visible or fighting_style_col.visible
            sec_razza_classe.visible   = has_rc
            sec_extra_razziali.visible = race_extras_col.visible
            sec_abilita.visible        = skills_col.visible
            sec_perizia.visible        = expertise_col.visible
            sec_lang_tool.visible      = lang_tool_col.visible
            any_visible = (
                has_rc or race_extras_col.visible or skills_col.visible
                or expertise_col.visible or lang_tool_col.visible
            )
            extra_card.content   = extra_card_content if any_visible else no_choices_text
            try:
                extra_card.update()
            except RuntimeError:
                pass

        _update_extra_card()

        content = ft.Column(
            [
                ft.Text("Scelte di classe e razza", size=22,
                        weight=ft.FontWeight.BOLD, color=COLOR_TEXT_TITLE),
                ft.Container(height=4),
                muted_text(f"Seleziona le opzioni disponibili per {self._review_class} / {self._review_race}.", size=13),
                ft.Container(height=20),
                extra_card,
                ft.Container(height=20),
                ft.Row(
                    [
                        ghost_button("Indietro", on_click=self._on_back),
                        primary_button("Continua", on_click=lambda e: self._goto_equipment(),
                                       icon=ft.Icons.ARROW_FORWARD),
                    ],
                    alignment=ft.MainAxisAlignment.END,
                    spacing=12,
                ),
            ],
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )
        self._set_content(
            ft.Container(content=content, expand=True,
                         padding=ft.Padding.symmetric(horizontal=16, vertical=20))
        )

    # -----------------------------------------------------------------------
    # FASE 4 — Equipaggiamento
    # -----------------------------------------------------------------------

    @staticmethod
    def _init_weapon_choice(item: dict) -> dict:
        if item.get("item_type") == "weapon_choice":
            cat = item.get("category", "semplice")
            weapons = WEAPONS_BY_CATEGORY.get(cat, [])
            count = item.get("count", 1)
            if count > 1:
                item["chosen_weapons"] = [weapons[0]] * count if weapons else []
            else:
                item["chosen_weapon"] = weapons[0] if weapons else ""
        return item

    def _goto_equipment(self) -> None:
        self._phase = "equipment"
        # Reset stato monete iniziali
        self._gold_mode   = False
        self._gold_amount = ""
        cls_data          = _loader.get_class(self._review_class)
        self._equip_fixed   = []
        self._equip_choices = []
        if cls_data:
            for entry in cls_data.get("starting_equipment", []):
                if entry.get("type") == "fixed":
                    for item in entry.get("items", []):
                        new_item = {**item, "selected": True}
                        self._init_weapon_choice(new_item)
                        self._equip_fixed.append(new_item)
                elif entry.get("type") == "choice":
                    opts = copy.deepcopy(entry.get("options", []))
                    for opt_list in opts:
                        for item in opt_list:
                            self._init_weapon_choice(item)
                    self._equip_choices.append({
                        "options": opts,
                        "chosen_idx": 0,
                    })
        self._update_progress()
        self._render_equipment()

    def _render_equipment(self) -> None:
        self._phase = "equipment"
        self._update_progress()

        rows: list[ft.Control] = [
            ft.Text("Equipaggiamento iniziale", size=22,
                    weight=ft.FontWeight.BOLD, color=COLOR_TEXT_TITLE),
            ft.Container(height=4),
            muted_text("Seleziona l'equipaggiamento di partenza della tua classe.", size=13),
            ft.Container(height=20),
        ]

        if self._equip_fixed:
            fixed_checks: list[ft.Control] = []
            for item in self._equip_fixed:
                if item.get("item_type") == "weapon_choice":
                    cat = item.get("category", "semplice")
                    weapons = WEAPONS_BY_CATEGORY.get(cat, [])
                    count = item.get("count", 1)
                    if count > 1:
                        chosen = item.setdefault("chosen_weapons", [weapons[0]] * count if weapons else [])
                        fixed_checks.append(label_text(f"Scegli {count} armi ({cat.replace('_', ' ')}):", size=12))
                        for wi in range(count):
                            def _on_wsel(e: Any, it=item, idx=wi) -> None:
                                it["chosen_weapons"][idx] = e.control.value or ""
                            fixed_checks.append(ft.Dropdown(
                                value=chosen[wi] if wi < len(chosen) else (weapons[0] if weapons else ""),
                                options=[ft.DropdownOption(key=w, text=w) for w in weapons],
                                width=220, text_size=13, on_select=_on_wsel,
                            ))
                    else:
                        chosen_w = item.setdefault("chosen_weapon", weapons[0] if weapons else "")
                        fixed_checks.append(ft.Row([
                            label_text(f"Arma ({cat.replace('_', ' ')}):", size=12),
                            ft.Dropdown(
                                value=chosen_w,
                                options=[ft.DropdownOption(key=w, text=w) for w in weapons],
                                width=220, text_size=13,
                                on_select=lambda e, it=item: it.update({"chosen_weapon": e.control.value or ""}),
                            ),
                        ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER))
                else:
                    qty   = item.get("quantity", 1)
                    label = item["name"] + (f" ×{qty}" if qty > 1 else "")
                    fixed_checks.append(ft.Row([
                        ft.Icon(ft.Icons.CHECK_BOX, color=COLOR_ACCENT_CRIMSON, size=20),
                        ft.Text(label, size=13, color=COLOR_TEXT_PRIMARY),
                    ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER))
            rows.append(fantasy_card(ft.Column([
                section_header("Oggetti garantiti"),
                ft.Column(fixed_checks, spacing=6),
            ], spacing=12), padding=20))
            rows.append(ft.Container(height=16))

        for ci, choice in enumerate(self._equip_choices):
            opts = choice["options"]
            if not opts:
                continue

            def _fmt(pkg: list[dict]) -> str:
                parts = []
                for it in pkg:
                    if it.get("item_type") == "weapon_choice":
                        cat = it.get("category", "semplice").replace("_", " ")
                        cnt = it.get("count", 1)
                        parts.append(f"Qualsiasi arma {cat}" + (f" ×{cnt}" if cnt > 1 else ""))
                    else:
                        qty = it.get("quantity", 1)
                        parts.append(it["name"] + (f" ×{qty}" if qty > 1 else ""))
                return "  +  ".join(parts)

            def _make_radio_change(c: dict) -> Any:
                def _on_change(e: Any) -> None:
                    c["chosen_idx"] = int(e.control.value or 0)
                    self._render_equipment()
                return _on_change

            radio_group = ft.RadioGroup(
                content=ft.Column(
                    [ft.Radio(value=str(i), label=_fmt(opts[i])) for i in range(len(opts))],
                    spacing=4,
                ),
                value=str(choice["chosen_idx"]),
                on_change=_make_radio_change(choice),
            )

            chosen_opt = opts[choice["chosen_idx"]] if 0 <= choice["chosen_idx"] < len(opts) else []
            weapon_pickers: list[ft.Control] = []
            for item in chosen_opt:
                if item.get("item_type") == "weapon_choice":
                    cat = item.get("category", "semplice")
                    weapons = WEAPONS_BY_CATEGORY.get(cat, [])
                    count = item.get("count", 1)
                    if count > 1:
                        chosen_ws = item.setdefault("chosen_weapons", [weapons[0]] * count if weapons else [])
                        weapon_pickers.append(label_text(f"Scegli {count} armi ({cat.replace('_', ' ')}):", size=12))
                        for wi in range(count):
                            def _on_wc(e: Any, it=item, idx=wi) -> None:
                                it["chosen_weapons"][idx] = e.control.value or ""
                            weapon_pickers.append(ft.Dropdown(
                                value=chosen_ws[wi] if wi < len(chosen_ws) else (weapons[0] if weapons else ""),
                                options=[ft.DropdownOption(key=w, text=w) for w in weapons],
                                width=220, text_size=13, on_select=_on_wc,
                            ))
                    else:
                        chosen_w = item.setdefault("chosen_weapon", weapons[0] if weapons else "")
                        weapon_pickers.append(ft.Row([
                            label_text(f"Arma ({cat.replace('_', ' ')}):", size=12),
                            ft.Dropdown(
                                value=chosen_w,
                                options=[ft.DropdownOption(key=w, text=w) for w in weapons],
                                width=220, text_size=13,
                                on_select=lambda e, it=item: it.update({"chosen_weapon": e.control.value or ""}),
                            ),
                        ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER))

            card_children: list[ft.Control] = [
                section_header(f"Scelta {ci + 1}"),
                radio_group,
            ]
            if weapon_pickers:
                card_children.append(ft.Container(height=8))
                card_children.extend(weapon_pickers)

            rows.append(fantasy_card(ft.Column(card_children, spacing=8), padding=20))
            rows.append(ft.Container(height=16))

        bg_data = _loader.get_background(self._review_bg)
        if bg_data:
            bg_equip = bg_data.get("equipment", [])
            if bg_equip:
                bg_text = "\n".join(
                    f"• {it['name']}" if isinstance(it, dict) else f"• {it}"
                    for it in bg_equip
                )
                rows.append(fantasy_card(ft.Column([
                    section_header("Equipaggiamento background"),
                    muted_text("Aggiunto automaticamente all'inventario.", size=11),
                    ft.Container(height=4),
                    ft.Text(bg_text, size=13, color=COLOR_TEXT_PRIMARY),
                ], spacing=8), padding=20))
                rows.append(ft.Container(height=16))

        # --- Sezione Monete iniziali (alternativa all'equipaggiamento di classe) ---
        cls_data_gold = _loader.get_class(self._review_class)
        if cls_data_gold:
            gold_alt = cls_data_gold.get("starting_gold_alternative", {})
            dice_str = gold_alt.get("dice", "")
            mult     = gold_alt.get("multiplier", 1)
            if dice_str:
                formula = f"{dice_str} × {mult} mo" if mult > 1 else f"{dice_str} mo"

                def _on_mode_change(ev: Any) -> None:
                    self._gold_mode = (getattr(ev.control, "value", "") == "gold")
                    self._render_equipment()

                gold_field = ft.TextField(
                    label=f"Somma ottenuta ({formula})",
                    value=self._gold_amount,
                    visible=self._gold_mode,
                    keyboard_type=ft.KeyboardType.NUMBER,
                    hint_text="Inserisci il risultato del tiro",
                    on_change=lambda ev: setattr(
                        self, "_gold_amount",
                        ev.control.value if ev.control.value else ""
                    ),
                    text_style=ft.TextStyle(size=14, color=COLOR_TEXT_PRIMARY),
                    border_color=COLOR_BORDER,
                    focused_border_color=COLOR_ACCENT_GOLD,
                    bgcolor=COLOR_BG_CARD,
                )

                rg_gold = ft.RadioGroup(
                    value="gold" if self._gold_mode else "equip",
                    content=ft.Column([
                        ft.Radio(value="equip", label="Equipaggiamento standard"),
                        ft.Radio(value="gold",  label=f"Oro iniziale — tira {formula}"),
                    ], spacing=4),
                    on_change=_on_mode_change,
                )

                rows.append(fantasy_card(ft.Column([
                    section_header("Monete iniziali"),
                    muted_text(
                        "In alternativa all'equipaggiamento, puoi iniziare con "
                        "dell'oro e acquistare ciò che vuoi.",
                        size=11,
                    ),
                    ft.Container(height=4),
                    rg_gold,
                    gold_field,
                ], spacing=8), padding=20))
                rows.append(ft.Container(height=16))

        rows.append(ft.Row(
            [
                ghost_button("Indietro", on_click=self._on_back),
                primary_button("Continua", on_click=lambda e: self._goto_confirm(),
                               icon=ft.Icons.ARROW_FORWARD),
            ],
            alignment=ft.MainAxisAlignment.END,
            spacing=12,
        ))

        content = ft.Column(rows, scroll=ft.ScrollMode.AUTO, expand=True)
        self._set_content(
            ft.Container(content=content, expand=True,
                         padding=ft.Padding.symmetric(horizontal=16, vertical=20))
        )

    # -----------------------------------------------------------------------
    # FASE 5 — Conferma e salvataggio
    # -----------------------------------------------------------------------

    def _goto_confirm(self) -> None:
        self._phase = "confirm"
        self._update_progress()
        self._render_confirm()

    def _render_confirm(self) -> None:
        self._phase = "confirm"
        self._update_progress()

        # Calcola valori derivati per il riepilogo
        hd      = (_loader.get_class(self._review_class) or {}).get("hit_die", 8)
        con_mod = get_modifier(self._review_stats.get("con", 10))
        dex_mod = get_modifier(self._review_stats.get("dex", 10))
        hp_val  = max(1, hd + con_mod)
        ac_val  = 10 + dex_mod
        speed   = _loader.get_resolved_race(self._review_race, self._review_subrace).get("speed", 9)

        error_text = ft.Text("", color=COLOR_ACCENT_RED, size=13, visible=False)

        def _stat_chip(label: str, val: Any) -> ft.Container:
            return ft.Container(
                content=ft.Column(
                    [
                        label_text(label, size=9),
                        ft.Text(str(val), size=14, weight=ft.FontWeight.BOLD,
                                color=COLOR_ACCENT_GOLD),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=2,
                ),
                padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                bgcolor=COLOR_BG_SECONDARY,
                border=ft.Border.all(1, COLOR_BORDER),
                border_radius=6,
            )

        summary = ft.Column(
            [
                ft.Row(
                    [
                        ft.Column([label_text("Nome",        11), body_text(self._name,           16, weight=ft.FontWeight.BOLD)], spacing=2),
                        ft.Column([label_text("Classe",      11), body_text(self._review_class,   16)], spacing=2),
                        ft.Column([label_text("Razza",       11), body_text(self._review_race,    16)], spacing=2),
                        ft.Column([label_text("Background",  11), body_text(self._review_bg,      16)], spacing=2),
                        ft.Column([label_text("Allineamento",11), body_text(self._review_align,   16)], spacing=2),
                    ],
                    spacing=24,
                    wrap=True,
                ),
                ft.Container(height=12),
                ft.Row(
                    [
                        _stat_chip("HP",  hp_val),
                        _stat_chip("CA",  ac_val),
                        _stat_chip("VEL", f"{speed} m"),
                        *[_stat_chip(lbl[:3].upper(), self._review_stats.get(k, 10))
                          for k, lbl in zip(ABILITY_KEYS, ABILITY_SCORES)],
                    ],
                    spacing=8,
                    wrap=True,
                ),
            ],
            spacing=0,
        )

        def _on_save(e) -> None:
            # Validazione Perizia Ladro
            if self._review_class.lower() == "ladro" and len(self._review_expertise) != 2:
                error_text.value   = "Ladro: seleziona 2 abilità per la Perizia nella fase Scelte."
                error_text.visible = True
                try:
                    error_text.update()
                except RuntimeError:
                    pass
                return

            error_text.visible = False
            try:
                error_text.update()
            except RuntimeError:
                pass

            try:
                # Build Character via wizard_engine (applica bonus razziali + tratti BG random)
                char = _stat_engine.build_character(
                    name=self._name,
                    player_name=self._player_name,
                    class_name=self._review_class,
                    race=self._review_race,
                    background=self._review_bg,
                    alignment=self._review_align,
                    stat_assignment=self._review_stats,
                    subrace=self._review_subrace,
                )
                char.subclass         = self._review_subclass
                char.subrace          = self._review_subrace
                char.dragon_ancestry  = self._review_dragon_ancestry
                char.fighting_style   = self._review_fighting_style

                # Bonus PF permanente da capacità di sottoclasse
                # (es. Resilienza Draconica dello Stregone)
                if char.subclass:
                    hp_bonus = get_permanent_class_hp_bonus(
                        char.class_name, char.subclass, char.level
                    )
                    char.hp_max += hp_bonus
                    char.hp_current = char.hp_max

                # Mezzelf: applica bonus flessibili (+1 a 2 stat scelte)
                if self._review_race == "Mezzelfo" and len(self._review_mezzelf_flex) == 2:
                    stat_map = {
                        "str": "str_score", "dex": "dex_score", "con": "con_score",
                        "int": "int_score", "wis": "wis_score", "cha": "cha_score",
                    }
                    for stat_key in self._review_mezzelf_flex:
                        attr = stat_map.get(stat_key)
                        if attr:
                            setattr(char, attr, min(20, getattr(char, attr) + 1))

                ok = character_repo.create(char)
                if not ok:
                    detail = getattr(character_repo, "_last_create_error", "")
                    raise RuntimeError(f"Errore DB: {detail}" if detail else "Errore nel salvataggio sul database.")

                # ---- Tiri salvezza di classe ----
                for stat_name in _loader.get_class_saving_throws(self._review_class):
                    character_repo._save_single_proficiency(char.id, "save", stat_name)

                # ---- Abilità: background + scelte di classe ----
                bg_data   = _loader.get_background(self._review_bg)
                bg_skills: list[str] = bg_data.get("skill_proficiencies", []) if bg_data else []
                for skill in bg_skills:
                    character_repo._save_single_proficiency(char.id, "skill", skill)
                for skill in self._review_skills:
                    if skill and skill not in bg_skills:
                        character_repo._save_single_proficiency(char.id, "skill", skill)

                # Abilità Mezzelf (Versatilità nelle Abilità)
                for skill in self._review_mezzelf_skills:
                    if skill:
                        character_repo._save_single_proficiency(char.id, "skill", skill)

                # Perizia Ladro Lv1
                if self._review_class.lower() == "ladro" and self._review_expertise:
                    character_repo.set_expertise(char.id, self._review_expertise)

                # Trucchetto Alto Elfo
                if self._review_elf_cantrip:
                    character_repo.upsert_known_spell(
                        character_id=char.id,
                        name=self._review_elf_cantrip,
                        level=0,
                        is_prepared=True,
                        school="", casting_time="", spell_range="",
                        components="", duration="",
                        description="Trucchetto del Mago (tratto Elfo Alto — INT)",
                        higher_levels="", class_list="Mago",
                    )

                # Lingua aggiuntiva Umano
                if self._review_umano_language:
                    character_repo._save_single_proficiency(char.id, "language", self._review_umano_language)

                # Lingue scelte da background
                for lang in self._review_languages:
                    if lang:
                        character_repo._save_single_proficiency(char.id, "language", lang)

                # Strumenti: scelti + fissi da background
                tool_seen: set[str] = set()
                for tool in self._review_tools:
                    if tool and tool not in tool_seen:
                        character_repo._save_single_proficiency(char.id, "tool", tool)
                        tool_seen.add(tool)
                if bg_data:
                    for entry in bg_data.get("tool_proficiencies", []):
                        if isinstance(entry, str) and entry not in tool_seen:
                            character_repo._save_single_proficiency(char.id, "tool", entry)
                            tool_seen.add(entry)

                def _save_item(character_id: str, item: dict) -> None:
                    itype = item.get("item_type", "item")
                    if itype == "weapon_choice":
                        count = item.get("count", 1)
                        if count > 1:
                            for wname in item.get("chosen_weapons", []):
                                if wname:
                                    character_repo.create_inventory_item(
                                        character_id=character_id, name=wname,
                                        quantity=1, weight=0.0, category="weapon",
                                        is_equipped=False, description="",
                                    )
                        else:
                            wname = item.get("chosen_weapon", "")
                            if wname:
                                character_repo.create_inventory_item(
                                    character_id=character_id, name=wname,
                                    quantity=1, weight=0.0, category="weapon",
                                    is_equipped=False, description="",
                                )
                    elif itype == "currency":
                        cur = character_repo.get_currencies(character_id)
                        if cur:
                            ctype = item.get("currency_type", "gold")
                            qty = item.get("quantity", 0)
                            delta = {ctype: qty}
                            character_repo.update_currencies(
                                character_id=character_id,
                                copper=cur.copper + delta.get("copper", 0),
                                silver=cur.silver + delta.get("silver", 0),
                                electrum=cur.electrum + delta.get("electrum", 0),
                                gold=cur.gold + delta.get("gold", 0),
                                platinum=cur.platinum + delta.get("platinum", 0),
                            )
                    else:
                        cat = "weapon" if itype == "weapon" else \
                              "armor"  if itype == "armor"  else "misc"
                        character_repo.create_inventory_item(
                            character_id=character_id,
                            name=item["name"],
                            quantity=item.get("quantity", 1),
                            weight=0.0, category=cat,
                            is_equipped=False, description="",
                        )

                if self._gold_mode:
                    # Modalità oro: salva monete invece degli oggetti di classe
                    try:
                        gold_val = max(0, int(self._gold_amount or 0))
                    except ValueError:
                        gold_val = 0
                    if gold_val > 0:
                        cur = character_repo.get_currencies(char.id)
                        if cur:
                            character_repo.update_currencies(
                                character_id=char.id,
                                copper=cur.copper, silver=cur.silver,
                                electrum=cur.electrum,
                                gold=cur.gold + gold_val,
                                platinum=cur.platinum,
                            )
                else:
                    # Modalità equipaggiamento standard
                    for item in self._equip_fixed:
                        if item.get("selected", True):
                            _save_item(char.id, item)
                    for choice in self._equip_choices:
                        idx  = choice.get("chosen_idx", 0)
                        opts = choice.get("options", [])
                        if 0 <= idx < len(opts):
                            for item in opts[idx]:
                                _save_item(char.id, item)

                # Equipaggiamento background (currency → valute, item → inventario)
                # sempre salvato indipendentemente dalla scelta equipaggiamento/oro
                if bg_data:
                    for entry in bg_data.get("equipment", []):
                        if isinstance(entry, dict):
                            _save_item(char.id, entry)

                # Ricalcola la CA con le formule di classe senza armatura
                # (Monaco, Barbaro, Stregone+Discendenza Draconica) — alla
                # creazione nessuna armatura risulta equipaggiata di default.
                character_repo.calculate_and_update_ca(char.id)

                logger.info("Personaggio creato manualmente: %s (%s)", char.name, char.id)
                self.on_complete(char.id)

            except Exception as ex:
                logger.error("Errore salvataggio form manuale: %s", ex)
                error_text.value   = f"Errore durante il salvataggio: {ex}"
                error_text.visible = True
                try:
                    error_text.update()
                except RuntimeError:
                    pass


        content = ft.Column(
            [
                ft.Text("Riepilogo e salvataggio", size=22,
                        weight=ft.FontWeight.BOLD, color=COLOR_TEXT_TITLE),
                ft.Container(height=4),
                muted_text("Controlla i valori derivati e crea il personaggio.", size=13),
                ft.Container(height=20),
                fantasy_card(ft.Column([
                    section_header("Riepilogo"),
                    summary,
                ], spacing=12), padding=20),
                ft.Container(height=8),
                error_text,
                ft.Container(height=16),
                ft.Row(
                    [
                        ghost_button("Indietro", on_click=self._on_back),
                        primary_button("Crea personaggio", on_click=_on_save,
                                       icon=ft.Icons.SHIELD),
                    ],
                    alignment=ft.MainAxisAlignment.END,
                    spacing=12,
                ),
            ],
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )
        self._set_content(
            ft.Container(content=content, expand=True,
                         padding=ft.Padding.symmetric(horizontal=16, vertical=20))
        )
