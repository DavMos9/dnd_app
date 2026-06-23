"""
Wizard guidato di creazione personaggio.

Flusso in 5 fasi:
    1. Domande (una per schermata, progress bar)
    2. Raccomandazione (classe/razza/background suggeriti)
    3. Revisione (identità, stat, sottorazza, sottoclasse lv1, abilità, lingue/strumenti)
    4. Equipaggiamento (oggetti fissi + scelte A/B)
    5. Nome + salvataggio

Il wizard è offline: nessuna API, solo albero decisionale + dati PHB.
"""

import flet as ft
import json
import logging
from typing import Any, cast

from config.settings import (
    COLOR_BG_PRIMARY, COLOR_BG_SECONDARY, COLOR_BG_CARD, COLOR_BG_SELECTED,
    COLOR_ACCENT_GOLD, COLOR_ACCENT_RED, COLOR_ACCENT_CRIMSON, COLOR_BORDER,
    COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY, COLOR_TEXT_MUTED, COLOR_TEXT_TITLE,
    CLASSES, RACES_BASE, DRACONIDE_ANCESTRIES, ALIGNMENTS,
    ABILITY_SCORES, ABILITY_KEYS, STANDARD_ARRAY, SKILLS,
    CLASS_SAVING_THROWS, LANGUAGES, TOOL_CATEGORIES, TOOL_CATEGORY_LABEL,
    FIGHTING_STYLES, MAGO_CANTRIPS,
    get_modifier, get_modifier_str,
)
from ui.theme import (
    title_text, body_text, muted_text, label_text,
    fantasy_card, section_header, primary_button, ghost_button,
)
from core.wizard_engine import WizardEngine
from data.game_data.wizard_data import (
    WIZARD_QUESTIONS, BACKGROUNDS, CLASS_DESCRIPTIONS, CLASS_SUGGESTED_RACES,
)
from data.game_data.game_data_loader import GameDataLoader
from data.repositories import character_repo
from data.models import CharacterProficiency

logger = logging.getLogger(__name__)
_loader = GameDataLoader()

# ------------------------------------------------------------------
# Icone sicure (presenti in Flet 0.85.3)
# ------------------------------------------------------------------
_ICON_MAP = {
    "SPORTS_MARTIAL_ARTS": ft.Icons.SPORTS_MARTIAL_ARTS,
    "EXPLORE":             ft.Icons.EXPLORE,
    "CHAT":                ft.Icons.CHAT,
    "FAVORITE":            ft.Icons.FAVORITE,
    "PSYCHOLOGY":          ft.Icons.PSYCHOLOGY,
    "FITNESS_CENTER":      ft.Icons.FITNESS_CENTER,
    "SPEED":               ft.Icons.SPEED,
    "GPS_FIXED":           ft.Icons.GPS_FIXED,
    "AUTO_AWESOME":        ft.Icons.AUTO_AWESOME,
    "HEALING":             ft.Icons.HEALING,
    "STARS":               ft.Icons.STARS,
    "FLASH_ON":            ft.Icons.FLASH_ON,
    "SHIELD":              ft.Icons.SHIELD,
    "ACCOUNT_TREE":        ft.Icons.ACCOUNT_TREE,
    "TUNE":                ft.Icons.TUNE,
    "BOLT":                ft.Icons.BOLT,
    "VISIBILITY":          ft.Icons.VISIBILITY,
    "SELF_IMPROVEMENT":    ft.Icons.SELF_IMPROVEMENT,
    "NIGHTS_STAY":         ft.Icons.NIGHTS_STAY,
    "PARK":                ft.Icons.PARK,
    "MUSIC_NOTE":          ft.Icons.MUSIC_NOTE,
    "WHATSHOT":            ft.Icons.WHATSHOT,
    "HANDSHAKE":           ft.Icons.HANDSHAKE,
    "FLARE":               ft.Icons.FLARE,
    "MENU_BOOK":           ft.Icons.MENU_BOOK,
    "FOREST":              ft.Icons.FOREST,
    "MILITARY_TECH":       ft.Icons.MILITARY_TECH,
    "GAVEL":               ft.Icons.GAVEL,
    "CHURCH":              ft.Icons.CHURCH,
    "SCHOOL":              ft.Icons.SCHOOL,
    "WORKSPACE_PREMIUM":   ft.Icons.WORKSPACE_PREMIUM,
    "HARDWARE":            ft.Icons.HARDWARE,
    "THEATER_COMEDY":      ft.Icons.THEATER_COMEDY,
    "PEOPLE":              ft.Icons.PEOPLE,
    "BALANCE":             ft.Icons.BALANCE,
    "DANGEROUS":           ft.Icons.DANGEROUS,
    "PERSON":              ft.Icons.PERSON,
}

def _icon(name: str, color: str = COLOR_TEXT_SECONDARY, size: int = 28) -> ft.Icon:
    return ft.Icon(_ICON_MAP.get(name, ft.Icons.HELP_OUTLINE), color=color, size=size)


class WizardView(ft.Column):
    """
    View principale del wizard.
    Gestisce la navigazione tra le 4 fasi e lo stato globale.

    Callback:
        on_complete(character_id: str)  → personaggio salvato
        on_cancel()                     → torna alla Home
    """

    def __init__(self, on_complete, on_cancel):
        super().__init__(expand=True, spacing=0)
        self.on_complete = on_complete
        self.on_cancel = on_cancel

        self.engine = WizardEngine()
        self._current_q_index: int = 0
        # questions | recommendation | review | equipment | confirm
        self._phase: str = "questions"

        # Stato review (popolato in _goto_review)
        self._review_class:     str        = ""
        self._review_race:      str        = ""
        self._review_subrace:   str        = ""   # sottorazza o discendenza Draconide
        self._review_subclass:  str        = ""   # sottoclasse (solo se lv1)
        self._review_bg:        str        = ""
        self._review_align:     str        = ""
        self._review_stats:     dict       = {}
        self._review_skills:    list[str]  = []   # abilità scelte dalla lista di classe
        self._review_languages: list[str]  = []   # lingue scelte dal background
        self._review_tools:     list[str]  = []   # strumenti scelti dal background
        # Scelte extra per razza/classe
        self._review_dragon_ancestry: str       = ""   # Stregone Discendenza Draconiana
        self._review_fighting_style:  str       = ""   # Guerriero/Paladino/Ranger
        self._review_mezzelf_flex:    list[str] = []   # 2 stat key per +1 Mezzelf
        self._review_mezzelf_skills:  list[str] = []   # 2 abilità Mezzelf (Versatilità)
        self._review_elf_cantrip:     str       = ""   # trucchetto Alto Elfo
        self._review_umano_language:  str       = ""   # lingua aggiuntiva Umano

        # Stato equipment (popolato in _render_equipment)
        # lista di dict: {name, item_type, quantity, selected}
        self._equip_fixed:   list[dict[str, Any]] = []
        # lista di dict: {options: [[item,...]], chosen_idx: int}
        self._equip_choices: list[dict[str, Any]] = []

        # Area di contenuto centrale (sostituita ad ogni step)
        self._content = ft.Container(expand=True, bgcolor=COLOR_BG_PRIMARY)
        self._progress_bar = ft.ProgressBar(
            value=0.0,
            color=COLOR_ACCENT_GOLD,
            bgcolor=COLOR_BORDER,
            height=4,
        )

        self._build_shell()
        self._render_question()

    # ------------------------------------------------------------------
    # Shell persistente (header + progress + content area)
    # ------------------------------------------------------------------

    def _build_shell(self):
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
                            title_text("Wizard Guidato", size=20),
                            muted_text("Rispondi per trovare il personaggio adatto a te", size=12),
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

        self.controls = [
            header,
            self._progress_bar,
            self._content,
        ]

    def _update_progress(self):
        total = len(WIZARD_QUESTIONS)
        done = self._current_q_index
        self._progress_bar.value = done / total if total > 0 else 0
        try:
            self._progress_bar.update()
        except RuntimeError:
            pass  # non ancora montato sulla page

    def _set_content(self, control: ft.Control):
        self._content.content = control
        try:
            self._content.update()
        except RuntimeError:
            pass  # non ancora montato sulla page

    # ------------------------------------------------------------------
    # Navigazione
    # ------------------------------------------------------------------

    def _on_back(self, e=None):
        if self._phase == "questions":
            if self._current_q_index == 0:
                self.on_cancel()
            else:
                # Annulla l'ultima risposta e torna alla domanda precedente
                prev_q = WIZARD_QUESTIONS[self._current_q_index - 1]
                self.engine.undo_answer(prev_q["id"])
                self._current_q_index -= 1
                self._update_progress()
                self._render_question()
        elif self._phase == "recommendation":
            # Torna all'ultima domanda
            self._phase = "questions"
            self._current_q_index = len(WIZARD_QUESTIONS)
            # Togli l'ultima domanda risposta
            last_q = WIZARD_QUESTIONS[-1]
            self.engine.undo_answer(last_q["id"])
            self._current_q_index -= 1
            self._update_progress()
            self._render_question()
        elif self._phase == "review":
            self._phase = "recommendation"
            self._render_recommendation()
        elif self._phase == "equipment":
            self._phase = "review"
            self._render_review()
        elif self._phase == "confirm":
            self._phase = "equipment"
            self._render_equipment()

    # ------------------------------------------------------------------
    # FASE 1: Domande
    # ------------------------------------------------------------------

    def _render_question(self):
        if self._current_q_index >= len(WIZARD_QUESTIONS):
            self._phase = "recommendation"
            self._render_recommendation()
            return

        self._phase = "questions"
        q = WIZARD_QUESTIONS[self._current_q_index]
        self._update_progress()

        # Stato selezione corrente
        selected: set[str] = set()

        # ------ Header domanda ------
        phase_label = ft.Container(
            content=ft.Text(
                q["phase"].upper(),
                size=10,
                weight=ft.FontWeight.BOLD,
                color=COLOR_ACCENT_GOLD,
                style=ft.TextStyle(letter_spacing=2),
            ),
            padding=ft.Padding.symmetric(horizontal=10, vertical=4),
            border=ft.Border.all(1, COLOR_ACCENT_GOLD),
            border_radius=4,
        )

        counter = muted_text(
            f"{self._current_q_index + 1} / {len(WIZARD_QUESTIONS)}",
            size=12,
        )

        question_text = ft.Text(
            q["text"],
            size=22,
            weight=ft.FontWeight.BOLD,
            color=COLOR_TEXT_TITLE,
            text_align=ft.TextAlign.CENTER,
        )

        subtitle_row = []
        if q.get("subtitle"):
            subtitle_row = [muted_text(q["subtitle"], size=13)]

        # ------ Opzioni ------
        option_controls: list[ft.Control] = []
        option_refs: dict[str, ft.Container] = {}

        def make_option_card(opt: dict) -> ft.Container:
            card = ft.Container(
                content=ft.Row(
                    [
                        _icon(opt["icon"], COLOR_TEXT_MUTED, 28),
                        ft.Container(width=16),
                        ft.Column(
                            [
                                ft.Text(
                                    opt["text"],
                                    size=15,
                                    weight=ft.FontWeight.W_600,
                                    color=COLOR_TEXT_PRIMARY,
                                ),
                                ft.Text(
                                    opt["desc"],
                                    size=12,
                                    color=COLOR_TEXT_MUTED,
                                ),
                            ],
                            spacing=2,
                            expand=True,
                        ),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=ft.Padding.symmetric(horizontal=20, vertical=14),
                bgcolor=COLOR_BG_CARD,
                border=ft.Border.all(1, COLOR_BORDER),
                border_radius=8,
                on_click=lambda e, o=opt: _toggle_option(o["id"]),
                ink=True,
                animate=ft.Animation(120, ft.AnimationCurve.EASE_OUT),
            )
            option_refs[opt["id"]] = card
            return card

        def _toggle_option(opt_id: str):
            if q["multi"]:
                if opt_id in selected:
                    selected.discard(opt_id)
                else:
                    selected.add(opt_id)
            else:
                selected.clear()
                selected.add(opt_id)
            _refresh_option_styles()
            _update_next_btn()

        def _refresh_option_styles():
            for oid, card in option_refs.items():
                if oid in selected:
                    card.bgcolor = "#2a1f08"
                    card.border = ft.Border.all(2, COLOR_ACCENT_GOLD)
                    # Aggiorna colore icona
                    row = cast(ft.Row, card.content)
                    row.controls[0] = _icon(
                        next(o["icon"] for o in q["options"] if o["id"] == oid),
                        COLOR_ACCENT_GOLD, 28,
                    )
                else:
                    card.bgcolor = COLOR_BG_CARD
                    card.border = ft.Border.all(1, COLOR_BORDER)
                    row = cast(ft.Row, card.content)
                    row.controls[0] = _icon(
                        next(o["icon"] for o in q["options"] if o["id"] == oid),
                        COLOR_TEXT_MUTED, 28,
                    )
                card.update()

        # Bottone Avanti
        next_btn = ft.ElevatedButton(
            "Avanti",
            icon=ft.Icons.ARROW_FORWARD,
            disabled=True,
            on_click=lambda e: _on_next(),
            style=ft.ButtonStyle(
                bgcolor=COLOR_ACCENT_GOLD,
                color=COLOR_BG_PRIMARY,
                shape=ft.RoundedRectangleBorder(radius=6),
            ),
        )

        def _update_next_btn():
            next_btn.disabled = len(selected) == 0
            next_btn.update()

        def _on_next():
            if not selected:
                return
            self.engine.record_answer(q["id"], list(selected))
            self._current_q_index += 1
            self._update_progress()
            self._render_question()

        for opt in q["options"]:
            option_controls.append(make_option_card(opt))

        # Layout opzioni: griglia 2 colonne su schermo largo
        # Usiamo semplicemente una Column scrollabile
        options_col = ft.Column(
            option_controls,
            spacing=10,
            scroll=ft.ScrollMode.AUTO,
        )

        content = ft.Column(
            [
                ft.Row(
                    [phase_label, ft.Container(expand=True), counter],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Container(height=16),
                question_text,
                *subtitle_row,
                ft.Container(height=20),
                options_col,
                ft.Container(height=20),
                ft.Row(
                    [next_btn],
                    alignment=ft.MainAxisAlignment.END,
                ),
            ],
            expand=True,
            scroll=ft.ScrollMode.AUTO,
        )

        self._set_content(
            ft.Container(
                content=content,
                expand=True,
                padding=ft.Padding.symmetric(horizontal=40, vertical=24),
            )
        )

    # ------------------------------------------------------------------
    # FASE 2: Raccomandazione
    # ------------------------------------------------------------------

    def _render_recommendation(self):
        self._phase = "recommendation"
        self._progress_bar.value = 1.0
        self._progress_bar.update()

        top3 = self.engine.get_top_classes(3)
        # Stato di selezione: default alla classe top
        selected_class = [top3[0][0]]
        card_refs: dict[str, ft.Container] = {}

        rec_bg    = self.engine.get_recommended_background()
        rec_race_by_class = {cls: self.engine.get_recommended_race(cls) for cls, _ in top3}
        rec_align = self.engine.get_alignment_string()

        # Etichette razza dinamiche in base alla classe selezionata
        race_label_ref = ft.Ref[ft.Text]()
        race_note_ref  = ft.Ref[ft.Text]()
        continue_btn_ref = ft.Ref[ft.ElevatedButton]()

        def _refresh_cards():
            sel = selected_class[0]
            for cls, card in card_refs.items():
                is_sel = cls == sel
                card.bgcolor = COLOR_BG_SELECTED if is_sel else COLOR_BG_CARD
                card.border = ft.Border(
                    top=ft.BorderSide(2, COLOR_ACCENT_CRIMSON if is_sel else COLOR_BORDER),
                    left=ft.BorderSide(1, COLOR_ACCENT_CRIMSON if is_sel else COLOR_BORDER),
                    right=ft.BorderSide(1, COLOR_BORDER),
                    bottom=ft.BorderSide(1, COLOR_BORDER),
                )
                try:
                    card.update()
                except RuntimeError:
                    pass
            # Aggiorna razza suggerita in base alla classe selezionata
            new_race = rec_race_by_class.get(sel, "Umano")
            if race_label_ref.current:
                race_label_ref.current.value = new_race
                try:
                    race_label_ref.current.update()
                except RuntimeError:
                    pass

        def _select_class(cls: str):
            selected_class[0] = cls
            _refresh_cards()

        def _class_card(cls: str, pts: int, rank: int) -> ft.Container:
            is_top = rank == 0
            badges = [
                ft.Container(
                    content=ft.Text(
                        "★ CONSIGLIATO" if is_top else f"#{rank + 1}",
                        size=9, weight=ft.FontWeight.BOLD,
                        color=COLOR_BG_PRIMARY if is_top else COLOR_TEXT_MUTED,
                    ),
                    bgcolor=COLOR_ACCENT_GOLD if is_top else COLOR_BG_SECONDARY,
                    border_radius=3,
                    padding=ft.Padding.symmetric(horizontal=8, vertical=3),
                ),
                ft.Container(width=6),
                ft.Container(
                    content=ft.Text(
                        "● SELEZIONATO" if is_top else "  Seleziona",
                        size=9, weight=ft.FontWeight.BOLD,
                        color=COLOR_ACCENT_CRIMSON if is_top else COLOR_TEXT_MUTED,
                    ),
                    border=ft.Border.all(1, COLOR_ACCENT_CRIMSON if is_top else COLOR_BORDER),
                    border_radius=3,
                    padding=ft.Padding.symmetric(horizontal=8, vertical=3),
                ),
            ]
            hit_die = CLASSES.get(cls, {}).get("hit_die", 8)
            spell_ab = CLASSES.get(cls, {}).get("spellcasting_ability")
            spell_label = (
                {"int": "Intelligenza", "wis": "Saggezza", "cha": "Carisma"}.get(spell_ab, "—")
                if spell_ab else "—"
            )
            card = ft.Container(
                content=ft.Column(
                    controls=cast(list[ft.Control], [
                        ft.Row(cast(list[ft.Control], badges), alignment=ft.MainAxisAlignment.START),
                        ft.Container(height=8),
                        ft.Text(cls, size=18 if is_top else 15, weight=ft.FontWeight.BOLD,
                                color=COLOR_ACCENT_GOLD if is_top else COLOR_TEXT_PRIMARY),
                        ft.Container(height=4),
                        muted_text(CLASS_DESCRIPTIONS.get(cls, ""), size=12),
                        ft.Container(height=8),
                        ft.Row([
                            ft.Column([label_text("Dado Vita", 9), body_text(f"d{hit_die}", 14)], spacing=2),
                            ft.Container(width=24),
                            ft.Column([label_text("Incantesimi", 9), body_text(spell_label, 14)], spacing=2),
                        ], spacing=0),
                    ]),
                    spacing=0,
                ),
                padding=14,
                bgcolor=COLOR_BG_SELECTED if is_top else COLOR_BG_CARD,
                border=ft.Border(
                    top=ft.BorderSide(2, COLOR_ACCENT_CRIMSON if is_top else COLOR_BORDER),
                    left=ft.BorderSide(1, COLOR_ACCENT_CRIMSON if is_top else COLOR_BORDER),
                    right=ft.BorderSide(1, COLOR_BORDER),
                    bottom=ft.BorderSide(1, COLOR_BORDER),
                ),
                border_radius=6,
                on_click=lambda e, c=cls: _select_class(c),
                ink=True,
            )
            card_refs[cls] = card
            return card

        class_cards = ft.Column(
            [_class_card(cls, pts, i) for i, (cls, pts) in enumerate(top3)],
            spacing=8,
        )

        # Suggerimenti dinamici
        summary_row = ft.Row(
            [
                ft.Column([
                    label_text("RAZZA SUGGERITA", 10),
                    ft.Text(
                        rec_race_by_class[top3[0][0]], size=15,
                        weight=ft.FontWeight.W_600, color=COLOR_TEXT_PRIMARY,
                        ref=race_label_ref,
                    ),
                    muted_text("Sinergia ottimale con la classe", 11),
                ], spacing=4, expand=True),
                ft.VerticalDivider(width=1, color=COLOR_BORDER),
                ft.Column([
                    label_text("BACKGROUND SUGGERITO", 10),
                    body_text(rec_bg, 15, weight=ft.FontWeight.W_600),
                    muted_text(", ".join(BACKGROUNDS.get(rec_bg, {}).get("skills", [])), 11),
                ], spacing=4, expand=True),
                ft.VerticalDivider(width=1, color=COLOR_BORDER),
                ft.Column([
                    label_text("ALLINEAMENTO", 10),
                    body_text(rec_align, 15, weight=ft.FontWeight.W_600),
                    muted_text("Dalle tue risposte", 11),
                ], spacing=4, expand=True),
            ],
            spacing=16,
        )

        def _on_continue(e):
            cls  = selected_class[0]
            race = rec_race_by_class.get(cls, "Umano")
            self._goto_review(cls, race, rec_bg, rec_align)

        content = ft.Column(
            [
                ft.Text("Il tuo personaggio ideale", size=22, weight=ft.FontWeight.BOLD,
                        color=COLOR_TEXT_TITLE, text_align=ft.TextAlign.CENTER),
                ft.Container(height=4),
                muted_text("Clicca su una classe per selezionarla, poi personalizza.",
                           size=13, text_align=ft.TextAlign.CENTER),
                ft.Container(height=16),
                class_cards,
                ft.Container(height=14),
                fantasy_card(summary_row, padding=16),
                ft.Container(height=20),
                ft.Row(
                    [
                        ghost_button("Indietro", on_click=self._on_back),
                        primary_button("Personalizza e continua",
                                       on_click=_on_continue,
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
            ft.Container(
                content=content,
                expand=True,
                padding=ft.Padding.symmetric(horizontal=40, vertical=24),
            )
        )

    # ------------------------------------------------------------------
    # FASE 3: Revisione (modifica suggerimento + statistiche)
    # ------------------------------------------------------------------

    def _goto_review(self, rec_class, rec_race, rec_bg, rec_align):
        self._review_class    = rec_class
        self._review_race     = rec_race
        self._review_subrace  = ""
        self._review_subclass = ""
        self._review_bg       = rec_bg
        self._review_align    = rec_align
        self._review_stats    = self.engine.get_suggested_stat_assignment(rec_class)
        self._review_skills   = []
        self._review_languages = []
        self._review_tools    = []
        self._review_dragon_ancestry = ""
        self._review_fighting_style  = ""
        self._review_mezzelf_flex    = []
        self._review_mezzelf_skills  = []
        self._review_elf_cantrip     = ""
        self._review_umano_language  = ""
        self._phase = "review"
        self._render_review()

    # ------------------------------------------------------------------
    # Helper: costruisce le sezioni dinamiche della Review
    # ------------------------------------------------------------------

    def _bg_skill_proficiencies(self) -> list[str]:
        """Abilità fisse concesse dal background corrente."""
        bg_data = _loader.get_background(self._review_bg)
        if bg_data:
            return bg_data.get("skill_proficiencies", [])
        return BACKGROUNDS.get(self._review_bg, {}).get("skills", [])

    def _class_skill_options(self) -> tuple[int, list[str]]:
        """(count, options) per le abilità di classe."""
        cls_data = _loader.get_class(self._review_class)
        if not cls_data:
            return 0, []
        sc = cls_data.get("skill_choices", {})
        count = sc.get("count", 0)
        opts = sc.get("options", [])
        if opts == "any":
            opts = list(SKILLS.keys())
        return count, [o for o in opts if o not in self._bg_skill_proficiencies()]

    def _bg_language_choices(self) -> tuple[int, str]:
        """(count, from) per le lingue a scelta del background, o (0,'') se nessuna."""
        bg_data = _loader.get_background(self._review_bg)
        if not bg_data:
            return 0, ""
        for entry in bg_data.get("languages", []):
            if isinstance(entry, dict) and entry.get("type") == "choice":
                return entry.get("count", 1), entry.get("from", "any")
        return 0, ""

    def _bg_tool_choices(self) -> list[tuple[int, list[str]]]:
        """Lista di (count, opzioni) per gli strumenti a scelta del background."""
        bg_data = _loader.get_background(self._review_bg)
        if not bg_data:
            return []
        result: list[tuple[int, list[str]]] = []
        for entry in bg_data.get("tool_proficiencies", []):
            if isinstance(entry, dict) and entry.get("type") == "choice":
                frm = entry.get("from", "")
                count = entry.get("count", 1)
                if isinstance(frm, list):
                    seen_labels: set[str] = set()
                    opts = []
                    for k in frm:
                        label = TOOL_CATEGORY_LABEL.get(k) or TOOL_CATEGORIES.get(k, [k])[0]
                        if label not in seen_labels:
                            opts.append(label)
                            seen_labels.add(label)
                else:
                    opts = TOOL_CATEGORIES.get(frm, [])
                result.append((count, opts))
        return result

    # ------------------------------------------------------------------
    # FASE 3: Revisione (modifica suggerimento + statistiche + scelte)
    # ------------------------------------------------------------------

    def _render_review(self):
        self._phase = "review"

        # ------ Dropdown identità ------
        class_dd = ft.Dropdown(
            label="Classe",
            value=self._review_class,
            options=[ft.DropdownOption(key=c, text=str(c)) for c in CLASSES.keys()],
            on_select=lambda e: _on_class_change(e),
            bgcolor=COLOR_BG_CARD,
            color=COLOR_TEXT_PRIMARY,
            label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=12),
            border_color=COLOR_BORDER,
            focused_border_color=COLOR_ACCENT_GOLD,
            expand=True,
        )
        race_dd = ft.Dropdown(
            label="Razza",
            value=self._review_race if self._review_race in RACES_BASE else list(RACES_BASE.keys())[0],
            options=[ft.DropdownOption(key=r, text=str(r)) for r in RACES_BASE.keys()],
            on_select=lambda e: _on_race_change(e),
            bgcolor=COLOR_BG_CARD,
            color=COLOR_TEXT_PRIMARY,
            label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=12),
            border_color=COLOR_BORDER,
            focused_border_color=COLOR_ACCENT_GOLD,
            expand=True,
        )
        bg_dd = ft.Dropdown(
            label="Background",
            value=self._review_bg,
            options=[ft.DropdownOption(key=b, text=str(b)) for b in BACKGROUNDS.keys()],
            on_select=lambda e: _on_bg_change(e),
            bgcolor=COLOR_BG_CARD,
            color=COLOR_TEXT_PRIMARY,
            label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=12),
            border_color=COLOR_BORDER,
            focused_border_color=COLOR_ACCENT_GOLD,
            expand=True,
        )
        align_dd = ft.Dropdown(
            label="Allineamento",
            value=self._review_align if self._review_align in ALIGNMENTS else ALIGNMENTS[0],
            options=[ft.DropdownOption(key=a, text=str(a)) for a in ALIGNMENTS],
            on_select=lambda e: setattr(self, "_review_align", e.control.value),
            bgcolor=COLOR_BG_CARD,
            color=COLOR_TEXT_PRIMARY,
            label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=12),
            border_color=COLOR_BORDER,
            focused_border_color=COLOR_ACCENT_GOLD,
            expand=True,
        )

        # ------ Statistiche (Standard Array) ------
        available_values = list(STANDARD_ARRAY)
        stat_dropdowns: dict[str, ft.Dropdown] = {}

        def _make_stat_row(key: str, label: str) -> ft.Row:
            current_val = self._review_stats.get(key, 10)
            mod = get_modifier(current_val)
            mod_str = get_modifier_str(current_val)
            dd = ft.Dropdown(
                value=str(current_val),
                options=[ft.DropdownOption(key=str(v), text=str(v)) for v in sorted(available_values, reverse=True)],
                on_select=lambda e, k=key: _on_stat_change(k, int(e.control.value or 10)),
                bgcolor=COLOR_BG_CARD,
                color=COLOR_TEXT_PRIMARY,
                border_color=COLOR_BORDER,
                focused_border_color=COLOR_ACCENT_GOLD,
                width=90,
            )
            stat_dropdowns[key] = dd
            mod_badge = ft.Container(
                content=ft.Text(mod_str, size=12, weight=ft.FontWeight.BOLD,
                                color=COLOR_ACCENT_GOLD if mod >= 0 else COLOR_ACCENT_RED),
                width=42,
                alignment=ft.Alignment.CENTER,
            )
            return ft.Row(
                [ft.Text(label, size=13, color=COLOR_TEXT_PRIMARY, width=120), dd, mod_badge],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=8,
            )

        def _on_stat_change(key: str, new_val: int):
            self._review_stats[key] = new_val
            for k, dd_ctrl in stat_dropdowns.items():
                v = self._review_stats.get(k, 10)
                ms = get_modifier_str(v)
                row = dd_ctrl.parent
                if row and len(cast(ft.Row, row).controls) >= 3:
                    badge = cast(ft.Container, cast(ft.Row, row).controls[2])
                    cast(ft.Text, badge.content).value = ms
                    m = get_modifier(v)
                    cast(ft.Text, badge.content).color = COLOR_ACCENT_GOLD if m >= 0 else COLOR_ACCENT_RED
                    badge.update()

        stat_rows = ft.Column(
            [_make_stat_row(key, label) for key, label in zip(ABILITY_KEYS, ABILITY_SCORES)],
            spacing=8,
        )

        def _hit_die_note() -> str:
            hd = CLASSES.get(self._review_class, {}).get("hit_die", 8)
            con_mod = get_modifier(self._review_stats.get("con", 10))
            hp = max(1, hd + con_mod)
            sign = "+" if con_mod >= 0 else ""
            return f"HP al Lv.1: d{hd}{sign}{con_mod} = {hp}  (modifica Cos. per cambiare)"

        hp_note_text = ft.Text(_hit_die_note(), size=11, color=COLOR_TEXT_MUTED, italic=True)

        # ------ Sezione sottorazza / discendenza (dinamica) ------
        subrace_col = ft.Column([], spacing=8, visible=False)

        def _rebuild_subrace_col():
            subrace_col.controls.clear()
            race = self._review_race
            subraces = RACES_BASE.get(race, [])
            if race == "Draconide":
                # Discendenza draconiana
                anc_dd = ft.Dropdown(
                    label="Discendenza Draconiana",
                    value=self._review_subrace or DRACONIDE_ANCESTRIES[0],
                    options=[ft.DropdownOption(key=a, text=a) for a in DRACONIDE_ANCESTRIES],
                    on_select=lambda e: setattr(self, "_review_subrace", e.control.value),
                    bgcolor=COLOR_BG_CARD,
                    color=COLOR_TEXT_PRIMARY,
                    label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=12),
                    border_color=COLOR_BORDER,
                    focused_border_color=COLOR_ACCENT_GOLD,
                    expand=True,
                )
                if not self._review_subrace:
                    self._review_subrace = DRACONIDE_ANCESTRIES[0]
                subrace_col.controls.append(anc_dd)
                subrace_col.visible = True
            elif subraces:
                val = self._review_subrace if self._review_subrace in subraces else subraces[0]
                self._review_subrace = val
                sr_dd = ft.Dropdown(
                    label="Sottorazza",
                    value=val,
                    options=[ft.DropdownOption(key=s, text=s) for s in subraces],
                    on_select=lambda e: [
                        setattr(self, "_review_subrace", e.control.value or ""),
                        _rebuild_race_extras_col(),
                    ],
                    bgcolor=COLOR_BG_CARD,
                    color=COLOR_TEXT_PRIMARY,
                    label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=12),
                    border_color=COLOR_BORDER,
                    focused_border_color=COLOR_ACCENT_GOLD,
                    expand=True,
                )
                subrace_col.controls.append(sr_dd)
                subrace_col.visible = True
            else:
                self._review_subrace = ""
                subrace_col.visible = False
            try:
                subrace_col.update()
            except RuntimeError:
                pass

        _rebuild_subrace_col()

        # ------ Sezione sottoclasse lv1 (dinamica) ------
        subclass_col = ft.Column([], spacing=8, visible=False)

        def _rebuild_subclass_col():
            subclass_col.controls.clear()
            cls_data = _loader.get_class(self._review_class)
            if not cls_data or cls_data.get("subclass_choice_level", 99) != 1:
                self._review_subclass = ""
                subclass_col.visible = False
                try:
                    subclass_col.update()
                except RuntimeError:
                    pass
                return
            subclasses = [sc.get("name", "") for sc in cls_data.get("subclasses", [])]
            label_name = cls_data.get("subclass_label", "Sottoclasse")
            val = self._review_subclass if self._review_subclass in subclasses else (subclasses[0] if subclasses else "")
            self._review_subclass = val
            sc_dd = ft.Dropdown(
                label=label_name,
                value=val,
                options=[ft.DropdownOption(key=s, text=s) for s in subclasses],
                on_select=lambda e: [
                    setattr(self, "_review_subclass", e.control.value or ""),
                    _rebuild_dragon_col(),
                ],
                bgcolor=COLOR_BG_CARD,
                color=COLOR_TEXT_PRIMARY,
                label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=12),
                border_color=COLOR_BORDER,
                focused_border_color=COLOR_ACCENT_GOLD,
                expand=True,
            )
            subclass_col.controls.append(sc_dd)
            subclass_col.visible = bool(subclasses)
            try:
                subclass_col.update()
            except RuntimeError:
                pass

        _rebuild_subclass_col()

        # ------ Tipo drago antenato (Stregone + Discendenza Draconiana) ------
        dragon_col = ft.Column([], spacing=8, visible=False)

        def _rebuild_dragon_col():
            dragon_col.controls.clear()
            if self._review_subclass == "Discendenza Draconiana":
                if not self._review_dragon_ancestry:
                    self._review_dragon_ancestry = DRACONIDE_ANCESTRIES[0]
                curr = self._review_dragon_ancestry if self._review_dragon_ancestry in DRACONIDE_ANCESTRIES else DRACONIDE_ANCESTRIES[0]
                self._review_dragon_ancestry = curr
                dragon_col.controls.append(ft.Dropdown(
                    label="Tipo di Drago Antenato",
                    hint_text="Determina resistenza e tipo di danno magico",
                    value=curr,
                    options=[ft.DropdownOption(key=a, text=a) for a in DRACONIDE_ANCESTRIES],
                    on_select=lambda e: setattr(self, "_review_dragon_ancestry", e.control.value or ""),
                    bgcolor=COLOR_BG_CARD,
                    color=COLOR_TEXT_PRIMARY,
                    label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=12),
                    border_color=COLOR_BORDER,
                    focused_border_color=COLOR_ACCENT_GOLD,
                    expand=True,
                ))
                dragon_col.visible = True
            else:
                self._review_dragon_ancestry = ""
                dragon_col.visible = False
            try:
                dragon_col.update()
            except RuntimeError:
                pass

        _rebuild_dragon_col()

        # ------ Stile di combattimento (Guerriero Lv1) ------
        fighting_style_col = ft.Column([], spacing=8, visible=False)

        def _rebuild_fighting_style_col():
            fighting_style_col.controls.clear()
            styles = FIGHTING_STYLES.get((self._review_class or "").strip().lower(), [])
            if styles:
                if not self._review_fighting_style or self._review_fighting_style not in styles:
                    self._review_fighting_style = styles[0]
                fighting_style_col.controls.append(ft.Dropdown(
                    label="Stile di Combattimento",
                    value=self._review_fighting_style,
                    options=[ft.DropdownOption(key=s, text=s) for s in styles],
                    on_select=lambda e: setattr(self, "_review_fighting_style", e.control.value or ""),
                    bgcolor=COLOR_BG_CARD,
                    color=COLOR_TEXT_PRIMARY,
                    label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=12),
                    border_color=COLOR_BORDER,
                    focused_border_color=COLOR_ACCENT_GOLD,
                    expand=True,
                ))
                fighting_style_col.visible = True
            else:
                self._review_fighting_style = ""
                fighting_style_col.visible = False
            try:
                fighting_style_col.update()
            except RuntimeError:
                pass

        _rebuild_fighting_style_col()

        # ------ Extra razziali: Mezzelf flex / Alto Elfo trucchetto / Umano lingua ------
        race_extras_col = ft.Column([], spacing=10, visible=False)

        def _rebuild_race_extras_col():
            race_extras_col.controls.clear()
            has_content = False
            race   = (self._review_race or "").strip()
            subrace = (self._review_subrace or "").strip()

            # --- Mezzelf: +1 a 2 caratteristiche (escluso CHA già +2) ---
            if race == "Mezzelf":
                has_content = True
                all_stat_keys = [k for k in ABILITY_KEYS if k != "cha"]
                all_stat_labels = {k: ABILITY_SCORES[i] for i, k in enumerate(ABILITY_KEYS)}
                # Mantieni selezioni valide
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
                        def _handler(e: Any):
                            while len(self._review_mezzelf_flex) <= slot_idx:
                                self._review_mezzelf_flex.append("")
                            self._review_mezzelf_flex[slot_idx] = e.control.value or ""
                        return _handler

                    flex_dds.append(ft.Dropdown(
                        label=f"+1 a (scelta {slot + 1})",
                        value=curr_key,
                        options=[ft.DropdownOption(key=k, text=all_stat_labels.get(k, k)) for k in all_stat_keys],
                        on_select=_make_flex_handler(slot),
                        bgcolor=COLOR_BG_CARD,
                        color=COLOR_TEXT_PRIMARY,
                        label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=12),
                        border_color=COLOR_BORDER,
                        focused_border_color=COLOR_ACCENT_GOLD,
                        expand=True,
                    ))
                race_extras_col.controls.append(ft.Row(flex_dds, spacing=12))

                # Mezzelf: 2 abilità a scelta (Versatilità nelle Abilità)
                all_skills = list(SKILLS.keys())
                self._review_mezzelf_skills = [s for s in self._review_mezzelf_skills if s in all_skills]
                mez_skill_count = 2
                mez_label_row = ft.Row([
                    ft.Text(f"Scegli {mez_skill_count} abilità (tratto razziale)",
                            size=13, color=COLOR_TEXT_PRIMARY, weight=ft.FontWeight.W_600),
                    ft.Container(expand=True),
                    ft.Text(f"({len(self._review_mezzelf_skills)}/{mez_skill_count})",
                            size=11, color=COLOR_TEXT_MUTED),
                ])
                race_extras_col.controls.append(mez_label_row)
                mez_counter = cast(ft.Text, mez_label_row.controls[2])
                mez_checks: dict[str, ft.Checkbox] = {}

                def _on_mez_skill(skill: str, val: bool):
                    if val:
                        if len(self._review_mezzelf_skills) < mez_skill_count:
                            if skill not in self._review_mezzelf_skills:
                                self._review_mezzelf_skills.append(skill)
                        else:
                            cb = mez_checks.get(skill)
                            if cb:
                                cb.value = False
                                try: cb.update()
                                except RuntimeError: pass
                            return
                    else:
                        if skill in self._review_mezzelf_skills:
                            self._review_mezzelf_skills.remove(skill)
                    mez_counter.value = f"({len(self._review_mezzelf_skills)}/{mez_skill_count})"
                    try: mez_counter.update()
                    except RuntimeError: pass

                left_m: list[ft.Control] = []
                right_m: list[ft.Control] = []
                for i, sk in enumerate(all_skills):
                    cb = ft.Checkbox(
                        label=sk,
                        value=sk in self._review_mezzelf_skills,
                        fill_color=COLOR_ACCENT_GOLD,
                        check_color="#ffffff",
                        label_style=ft.TextStyle(size=12, color=COLOR_TEXT_PRIMARY),
                        on_change=lambda e, s=sk: _on_mez_skill(s, bool(e.control.value)),
                    )
                    mez_checks[sk] = cb
                    if i % 2 == 0: left_m.append(cb)
                    else: right_m.append(cb)
                race_extras_col.controls.append(ft.Row(
                    [ft.Column(left_m, spacing=4, expand=True),
                     ft.Column(right_m, spacing=4, expand=True)],
                    spacing=8,
                ))

            # --- Alto Elfo: trucchetto del Mago ---
            if race == "Elfo" and subrace == "Alto Elfo":
                has_content = True
                if not self._review_elf_cantrip or self._review_elf_cantrip not in MAGO_CANTRIPS:
                    self._review_elf_cantrip = MAGO_CANTRIPS[0]
                race_extras_col.controls.append(ft.Dropdown(
                    label="Trucchetto del Mago (tratto Alto Elfo)",
                    value=self._review_elf_cantrip,
                    options=[ft.DropdownOption(key=c, text=c) for c in MAGO_CANTRIPS],
                    on_select=lambda e: setattr(self, "_review_elf_cantrip", e.control.value or ""),
                    bgcolor=COLOR_BG_CARD,
                    color=COLOR_TEXT_PRIMARY,
                    label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=12),
                    border_color=COLOR_BORDER,
                    focused_border_color=COLOR_ACCENT_GOLD,
                    expand=True,
                ))
            else:
                if race != "Elfo":
                    self._review_elf_cantrip = ""

            # --- Umano: lingua aggiuntiva ---
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
                    bgcolor=COLOR_BG_CARD,
                    color=COLOR_TEXT_PRIMARY,
                    label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=12),
                    border_color=COLOR_BORDER,
                    focused_border_color=COLOR_ACCENT_GOLD,
                    expand=True,
                ))
            else:
                self._review_umano_language = ""

            race_extras_col.visible = has_content
            try:
                race_extras_col.update()
            except RuntimeError:
                pass

        _rebuild_race_extras_col()

        # ------ Sezione abilità di classe (dinamica) ------
        skills_col = ft.Column([], spacing=6, visible=False)
        skill_checks: dict[str, ft.Checkbox] = {}

        def _rebuild_skills_col():
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
            # Mantieni le selezioni valide
            self._review_skills = [s for s in self._review_skills if s in opts]
            selected_count_ref = [len(self._review_skills)]

            label_row = ft.Row([
                ft.Text(f"Scegli {count} abilità dalla lista", size=13,
                        color=COLOR_TEXT_PRIMARY, weight=ft.FontWeight.W_600),
                ft.Container(expand=True),
                ft.Text(f"({len(self._review_skills)}/{count} selezionate)",
                        size=11, color=COLOR_TEXT_MUTED),
            ])
            skills_col.controls.append(label_row)

            counter_text = cast(ft.Text, label_row.controls[2])

            def _on_skill_toggle(skill: str, val: bool):
                if val:
                    if len(self._review_skills) < count:
                        if skill not in self._review_skills:
                            self._review_skills.append(skill)
                    else:
                        # Già raggiunto il limite — deseleziona
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
                    label_row.update()
                except RuntimeError:
                    pass

            # Checkbox in griglia 2 colonne
            left_col: list[ft.Control] = []
            right_col: list[ft.Control] = []
            for i, skill in enumerate(opts):
                cb = ft.Checkbox(
                    label=skill,
                    value=skill in self._review_skills,
                    fill_color=COLOR_ACCENT_CRIMSON,
                    check_color="#ffffff",
                    label_style=ft.TextStyle(size=12, color=COLOR_TEXT_PRIMARY),
                    on_change=lambda e, s=skill: _on_skill_toggle(s, bool(e.control.value)),
                )
                skill_checks[skill] = cb
                if i % 2 == 0:
                    left_col.append(cb)
                else:
                    right_col.append(cb)

            skills_col.controls.append(ft.Row(
                [ft.Column(left_col, spacing=4, expand=True),
                 ft.Column(right_col, spacing=4, expand=True)],
                spacing=8,
            ))
            # Nota abilità da background
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

        _rebuild_skills_col()

        # ------ Sezione lingue + strumenti (dinamica) ------
        lang_tool_col = ft.Column([], spacing=8, visible=False)

        def _rebuild_lang_tool_col():
            lang_tool_col.controls.clear()
            has_content = False

            # Lingue
            lang_count, lang_from = self._bg_language_choices()
            if lang_count > 0:
                has_content = True
                avail_langs = LANGUAGES
                # Mantieni selezioni valide
                self._review_languages = [l for l in self._review_languages if l in avail_langs]
                lang_label = ft.Row([
                    ft.Text(f"Scegli {lang_count} lingua{'e' if lang_count > 1 else ''}",
                            size=13, color=COLOR_TEXT_PRIMARY, weight=ft.FontWeight.W_600),
                    ft.Container(expand=True),
                    ft.Text(f"({len(self._review_languages)}/{lang_count})",
                            size=11, color=COLOR_TEXT_MUTED),
                ])
                lang_tool_col.controls.append(lang_label)
                lang_counter = cast(ft.Text, lang_label.controls[2])

                lang_checks: dict[str, ft.Checkbox] = {}

                def _on_lang_toggle(lang: str, val: bool):
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
                        label=lang,
                        value=lang in self._review_languages,
                        fill_color=COLOR_ACCENT_GOLD,
                        check_color="#ffffff",
                        label_style=ft.TextStyle(size=12, color=COLOR_TEXT_PRIMARY),
                        on_change=lambda e, lg=lang: _on_lang_toggle(lg, bool(e.control.value)),
                    )
                    lang_checks[lang] = cb
                    if i % 2 == 0:
                        ll.append(cb)
                    else:
                        rl.append(cb)
                lang_tool_col.controls.append(ft.Row(
                    [ft.Column(ll, spacing=4, expand=True),
                     ft.Column(rl, spacing=4, expand=True)],
                    spacing=8,
                ))

            # Strumenti
            tool_choices = self._bg_tool_choices()
            for tc_idx, (tc_count, tc_opts) in enumerate(tool_choices):
                if not tc_opts:
                    continue
                has_content = True
                # Reset selezione se non valida
                if len(self._review_tools) <= tc_idx:
                    self._review_tools.append("")
                curr_tool = self._review_tools[tc_idx] if tc_idx < len(self._review_tools) else ""
                if curr_tool not in tc_opts:
                    curr_tool = tc_opts[0]
                    if tc_idx < len(self._review_tools):
                        self._review_tools[tc_idx] = curr_tool
                    else:
                        self._review_tools.append(curr_tool)

                tool_dd = ft.Dropdown(
                    label="Strumento a scelta",
                    value=curr_tool,
                    options=[ft.DropdownOption(key=t, text=t) for t in tc_opts],
                    on_select=lambda e, idx=tc_idx: _set_tool(idx, e.control.value or ""),
                    bgcolor=COLOR_BG_CARD,
                    color=COLOR_TEXT_PRIMARY,
                    label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=12),
                    border_color=COLOR_BORDER,
                    focused_border_color=COLOR_ACCENT_GOLD,
                    expand=True,
                )
                lang_tool_col.controls.append(tool_dd)

            lang_tool_col.visible = has_content
            try:
                lang_tool_col.update()
            except RuntimeError:
                pass

        def _set_tool(idx: int, val: str):
            while len(self._review_tools) <= idx:
                self._review_tools.append("")
            self._review_tools[idx] = val

        _rebuild_lang_tool_col()

        # ------ Handler dropdown principali ------

        def _on_class_change(e):
            self._review_class = e.control.value
            self._review_stats = self.engine.get_suggested_stat_assignment(self._review_class)
            self._review_skills = []
            self._review_subclass = ""
            self._review_dragon_ancestry = ""
            self._review_fighting_style = ""
            for key, dd_ctrl in stat_dropdowns.items():
                dd_ctrl.value = str(self._review_stats.get(key, 10))
                dd_ctrl.update()
            _on_stat_change("", 0)
            hp_note_text.value = _hit_die_note()
            hp_note_text.update()
            _rebuild_subclass_col()
            _rebuild_dragon_col()
            _rebuild_fighting_style_col()
            _rebuild_skills_col()
            _update_extra_card()

        def _on_race_change(e):
            self._review_race = e.control.value or ""
            self._review_subrace = ""
            self._review_mezzelf_flex = []
            self._review_mezzelf_skills = []
            self._review_elf_cantrip = ""
            self._review_umano_language = ""
            _rebuild_subrace_col()
            _rebuild_race_extras_col()
            _update_extra_card()

        def _on_bg_change(e):
            self._review_bg = e.control.value or ""
            self._review_skills = []
            self._review_languages = []
            self._review_tools = []
            _rebuild_skills_col()
            _rebuild_lang_tool_col()
            _update_extra_card()

        # ------ Layout finale (dinamico: extra_card aggiornata via _update_extra_card) ------

        # Section headers come widget per poterne aggiornare la visibilità
        sec_razza_classe  = ft.Container(content=section_header("Razza e Classe"),  visible=False)
        sec_extra_razziali = ft.Container(content=section_header("Extra Razziali"),  visible=False)
        sec_abilita       = ft.Container(content=section_header("Abilità di Classe"), visible=False)
        sec_lang_tool     = ft.Container(content=section_header("Lingue e Strumenti"), visible=False)

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
            sec_lang_tool,
            lang_tool_col,
        ], spacing=12)

        extra_card = ft.Container(
            content=extra_card_content,
            visible=False,
            bgcolor=COLOR_BG_CARD,
            border=ft.Border.only(top=ft.BorderSide(3, COLOR_ACCENT_CRIMSON)),
            border_radius=ft.BorderRadius.all(8),
            padding=20,
        )

        def _update_extra_card():
            has_rc = subrace_col.visible or subclass_col.visible or dragon_col.visible or fighting_style_col.visible
            sec_razza_classe.visible   = has_rc
            sec_extra_razziali.visible = race_extras_col.visible
            sec_abilita.visible        = skills_col.visible
            sec_lang_tool.visible      = lang_tool_col.visible
            extra_card.visible = has_rc or race_extras_col.visible or skills_col.visible or lang_tool_col.visible
            try:
                extra_card.update()
            except RuntimeError:
                pass

        _update_extra_card()

        content_sections: list[ft.Control] = [
            ft.Text("Personalizza il tuo personaggio", size=22,
                    weight=ft.FontWeight.BOLD, color=COLOR_TEXT_TITLE),
            ft.Container(height=4),
            muted_text("Puoi modificare i suggerimenti del wizard.", size=13),
            ft.Container(height=20),
            fantasy_card(ft.Column([
                section_header("Identità"),
                ft.Row([class_dd, race_dd], spacing=12),
                ft.Row([bg_dd, align_dd], spacing=12),
            ], spacing=12), padding=20),
            ft.Container(height=16),
            fantasy_card(ft.Column([
                section_header("Caratteristiche — Standard Array"),
                muted_text(
                    "Assegna i valori [15, 14, 13, 12, 10, 8] alle caratteristiche. "
                    "I valori ripetuti sono permessi nel wizard (potrai aggiustare nel form).",
                    size=11,
                ),
                ft.Container(height=8),
                stat_rows,
                ft.Container(height=6),
                hp_note_text,
            ], spacing=8), padding=20),
        ]

        # extra_card gestisce autonomamente la propria visibilità via _update_extra_card()
        content_sections += [
            ft.Container(height=16),
            extra_card,
        ]

        content_sections += [
            ft.Container(height=20),
            ft.Row(
                [
                    ghost_button("Indietro", on_click=self._on_back),
                    primary_button(
                        "Continua",
                        on_click=lambda e: self._goto_equipment(),
                        icon=ft.Icons.ARROW_FORWARD,
                    ),
                ],
                alignment=ft.MainAxisAlignment.END,
                spacing=12,
            ),
        ]

        content = ft.Column(content_sections, scroll=ft.ScrollMode.AUTO, expand=True)
        self._set_content(
            ft.Container(content=content, expand=True,
                         padding=ft.Padding.symmetric(horizontal=40, vertical=24))
        )

    # ------------------------------------------------------------------
    # FASE 4: Equipaggiamento iniziale
    # ------------------------------------------------------------------

    def _goto_equipment(self):
        self._phase = "equipment"
        # Costruisce la lista oggetti dalla classe
        cls_data = _loader.get_class(self._review_class)
        self._equip_fixed = []
        self._equip_choices = []
        if cls_data:
            for entry in cls_data.get("starting_equipment", []):
                if entry.get("type") == "fixed":
                    for item in entry.get("items", []):
                        self._equip_fixed.append({**item, "selected": True})
                elif entry.get("type") == "choice":
                    self._equip_choices.append({
                        "options": entry.get("options", []),
                        "chosen_idx": 0,
                    })
        self._render_equipment()

    def _render_equipment(self):
        self._phase = "equipment"

        rows: list[ft.Control] = [
            ft.Text("Equipaggiamento iniziale", size=22,
                    weight=ft.FontWeight.BOLD, color=COLOR_TEXT_TITLE),
            ft.Container(height=4),
            muted_text("Seleziona l'equipaggiamento di partenza della tua classe.", size=13),
            ft.Container(height=20),
        ]

        # --- Oggetti fissi ---
        if self._equip_fixed:
            fixed_checks: list[ft.Control] = []
            for item in self._equip_fixed:
                qty = item.get("quantity", 1)
                label = item["name"] + (f" ×{qty}" if qty > 1 else "")
                cb = ft.Checkbox(
                    label=label,
                    value=item["selected"],
                    fill_color=COLOR_ACCENT_CRIMSON,
                    check_color="#ffffff",
                    label_style=ft.TextStyle(size=13, color=COLOR_TEXT_PRIMARY),
                    on_change=lambda e, it=item: it.update({"selected": bool(e.control.value)}),
                )
                fixed_checks.append(cb)
            rows.append(fantasy_card(ft.Column([
                section_header("Oggetti garantiti"),
                ft.Column(fixed_checks, spacing=6),
            ], spacing=12), padding=20))
            rows.append(ft.Container(height=16))

        # --- Scelte A/B ---
        for ci, choice in enumerate(self._equip_choices):
            opts = choice["options"]
            if not opts:
                continue

            def _fmt_option(pkg: list[dict]) -> str:
                parts = []
                for it in pkg:
                    qty = it.get("quantity", 1)
                    parts.append(it["name"] + (f" ×{qty}" if qty > 1 else ""))
                return "  +  ".join(parts)

            radio_group = ft.RadioGroup(
                content=ft.Column(
                    [ft.Radio(value=str(i), label=_fmt_option(opts[i]))
                     for i in range(len(opts))],
                    spacing=4,
                ),
                value=str(choice["chosen_idx"]),
                on_change=lambda e, c=choice: c.update({"chosen_idx": int(e.control.value or 0)}),
            )
            rows.append(fantasy_card(ft.Column([
                section_header(f"Scelta {ci + 1}"),
                radio_group,
            ], spacing=12), padding=20))
            rows.append(ft.Container(height=16))

        # --- Equipaggiamento background (testo) ---
        bg_data = _loader.get_background(self._review_bg)
        if bg_data:
            bg_equip = bg_data.get("equipment", [])
            if bg_equip:
                bg_items_text = "\n".join(
                    f"• {it['name']}" if isinstance(it, dict) else f"• {it}"
                    for it in bg_equip
                )
                rows.append(fantasy_card(ft.Column([
                    section_header("Equipaggiamento background"),
                    muted_text("Aggiunto automaticamente all'inventario.", size=11),
                    ft.Container(height=4),
                    ft.Text(bg_items_text, size=13, color=COLOR_TEXT_PRIMARY),
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
                         padding=ft.Padding.symmetric(horizontal=40, vertical=24))
        )

    # ------------------------------------------------------------------
    # FASE 5: Nome + conferma + salvataggio
    # ------------------------------------------------------------------

    def _goto_confirm(self):
        self._phase = "confirm"
        self._render_confirm()

    def _render_confirm(self):
        self._phase = "confirm"

        name_field = ft.TextField(
            label="Nome del personaggio *",
            hint_text="Come si chiama il tuo eroe?",
            bgcolor=COLOR_BG_CARD,
            color=COLOR_TEXT_PRIMARY,
            label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=12),
            border_color=COLOR_BORDER,
            focused_border_color=COLOR_ACCENT_GOLD,
            cursor_color=COLOR_ACCENT_GOLD,
            autofocus=True,
        )
        player_field = ft.TextField(
            label="Nome del giocatore (opzionale)",
            bgcolor=COLOR_BG_CARD,
            color=COLOR_TEXT_PRIMARY,
            label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=12),
            border_color=COLOR_BORDER,
            focused_border_color=COLOR_ACCENT_GOLD,
            cursor_color=COLOR_ACCENT_GOLD,
        )
        error_text = ft.Text("", color=COLOR_ACCENT_RED, size=13, visible=False)

        # Riepilogo
        hd    = CLASSES.get(self._review_class, {}).get("hit_die", 8)
        con_m = get_modifier(self._review_stats.get("con", 10))
        hp    = max(1, hd + con_m)
        dex_m = get_modifier(self._review_stats.get("dex", 10))
        ac    = 10 + dex_m

        def _stat_chip(label: str, val) -> ft.Container:
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
                        ft.Column(
                            [
                                label_text("Classe", size=11),
                                body_text(self._review_class, size=16,
                                          weight=ft.FontWeight.BOLD),
                            ],
                            spacing=2,
                        ),
                        ft.Column(
                            [
                                label_text("Razza", size=11),
                                body_text(self._review_race, size=16),
                            ],
                            spacing=2,
                        ),
                        ft.Column(
                            [
                                label_text("Background", size=11),
                                body_text(self._review_bg, size=16),
                            ],
                            spacing=2,
                        ),
                        ft.Column(
                            [
                                label_text("Allineamento", size=11),
                                body_text(self._review_align, size=16),
                            ],
                            spacing=2,
                        ),
                    ],
                    spacing=24,
                ),
                ft.Container(height=12),
                ft.Row(
                    [
                        _stat_chip("HP", hp),
                        _stat_chip("CA", ac),
                        _stat_chip("VEL", "9 m"),
                        *[
                            _stat_chip(lbl[:3].upper(), self._review_stats.get(k, 10))
                            for k, lbl in zip(ABILITY_KEYS, ABILITY_SCORES)
                        ],
                    ],
                    spacing=8,
                    wrap=True,
                ),
            ],
            spacing=0,
        )

        def _on_save(e):
            nm = name_field.value.strip() if name_field.value else ""
            if not nm:
                error_text.value = "Il nome del personaggio è obbligatorio."
                error_text.visible = True
                error_text.update()
                return

            error_text.visible = False
            error_text.update()

            try:
                char = self.engine.build_character(
                    name=nm,
                    player_name=player_field.value.strip() if player_field.value else "",
                    class_name=self._review_class,
                    race=self._review_race,
                    background=self._review_bg,
                    alignment=self._review_align,
                    stat_assignment=self._review_stats,
                )
                # Sottorazza e sottoclasse (se scelte in review)
                if self._review_subrace:
                    char.subrace = self._review_subrace
                if self._review_subclass:
                    char.subclass = self._review_subclass

                # Scelte razza/classe extra
                if self._review_dragon_ancestry:
                    char.dragon_ancestry = self._review_dragon_ancestry
                if self._review_fighting_style:
                    char.fighting_style = self._review_fighting_style

                # Mezzelf: applica i bonus flessibili (+1 a 2 stat)
                if self._review_race == "Mezzelf" and len(self._review_mezzelf_flex) == 2:
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
                    raise RuntimeError("Errore nel salvataggio sul database.")

                # Tiri salvezza competenti dalla classe (PHB)
                for stat_name in CLASS_SAVING_THROWS.get(self._review_class, []):
                    character_repo._save_single_proficiency(char.id, "save", stat_name)

                # Abilità: background (fisso) + scelte di classe
                bg_data = _loader.get_background(self._review_bg)
                bg_skills: list[str] = []
                if bg_data:
                    bg_skills = bg_data.get("skill_proficiencies", [])
                else:
                    bg_skills = BACKGROUNDS.get(self._review_bg, {}).get("skills", [])
                for skill in bg_skills:
                    character_repo._save_single_proficiency(char.id, "skill", skill)
                for skill in self._review_skills:
                    if skill and skill not in bg_skills:
                        character_repo._save_single_proficiency(char.id, "skill", skill)

                # Abilità Mezzelf (Versatilità nelle Abilità — 2 abilità razziali)
                for skill in self._review_mezzelf_skills:
                    if skill:
                        character_repo._save_single_proficiency(char.id, "skill", skill)

                # Trucchetto Alto Elfo → known_spell level 0
                if self._review_elf_cantrip:
                    character_repo.upsert_known_spell(
                        character_id=char.id,
                        name=self._review_elf_cantrip,
                        level=0,
                        is_prepared=True,
                        school="",
                        casting_time="",
                        spell_range="",
                        components="",
                        duration="",
                        description="Trucchetto del Mago (tratto Alto Elfo — INT)",
                        higher_levels="",
                        class_list="Mago",
                    )

                # Lingua aggiuntiva Umano
                if self._review_umano_language:
                    character_repo._save_single_proficiency(char.id, "language", self._review_umano_language)

                # Lingue scelte da background
                for lang in self._review_languages:
                    if lang:
                        character_repo._save_single_proficiency(char.id, "language", lang)

                # Strumenti scelti (+ strumenti fissi del background)
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

                # Equipaggiamento — oggetti fissi selezionati
                for item in self._equip_fixed:
                    if item.get("selected", True):
                        character_repo.create_inventory_item(
                            character_id=char.id,
                            name=item["name"],
                            quantity=item.get("quantity", 1),
                            weight=0.0,
                            category="weapon" if item.get("item_type") == "weapon" else
                                     "armor" if item.get("item_type") == "armor" else "misc",
                            is_equipped=False,
                            description="",
                        )

                # Equipaggiamento — scelte A/B
                for choice in self._equip_choices:
                    idx = choice.get("chosen_idx", 0)
                    opts = choice.get("options", [])
                    if 0 <= idx < len(opts):
                        for item in opts[idx]:
                            character_repo.create_inventory_item(
                                character_id=char.id,
                                name=item["name"],
                                quantity=item.get("quantity", 1),
                                weight=0.0,
                                category="weapon" if item.get("item_type") == "weapon" else
                                         "armor" if item.get("item_type") == "armor" else "misc",
                                is_equipped=False,
                                description="",
                            )

                # Equipaggiamento background
                if bg_data:
                    for entry in bg_data.get("equipment", []):
                        if isinstance(entry, dict):
                            character_repo.create_inventory_item(
                                character_id=char.id,
                                name=entry["name"],
                                quantity=entry.get("quantity", 1),
                                weight=0.0,
                                category="misc",
                                is_equipped=False,
                                description="",
                            )

                logger.info(f"Personaggio wizard creato: {char.name} ({char.id})")
                self.on_complete(char.id)

            except Exception as ex:
                logger.error(f"Errore salvataggio wizard: {ex}")
                error_text.value = f"Errore durante il salvataggio: {ex}"
                error_text.visible = True
                error_text.update()

        content = ft.Column(
            [
                ft.Text(
                    "Dai un nome al tuo eroe",
                    size=22,
                    weight=ft.FontWeight.BOLD,
                    color=COLOR_TEXT_TITLE,
                ),
                ft.Container(height=4),
                muted_text("Quasi fatto! Assegna un nome e salva il tuo personaggio.", size=13),
                ft.Container(height=20),
                fantasy_card(ft.Column([
                    ft.Row([name_field, player_field], spacing=12),
                ], spacing=0), padding=20),
                ft.Container(height=16),
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
                        primary_button(
                            "Crea personaggio",
                            on_click=_on_save,
                            icon=ft.Icons.SHIELD,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.END,
                    spacing=12,
                ),
            ],
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

        self._set_content(
            ft.Container(
                content=content,
                expand=True,
                padding=ft.Padding.symmetric(horizontal=40, vertical=24),
            )
        )
