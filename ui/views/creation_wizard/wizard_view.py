"""
Wizard guidato di creazione personaggio.

Flusso in 4 fasi:
    1. Domande (una per schermata, progress bar)
    2. Raccomandazione (classe/razza/background suggeriti)
    3. Revisione e statistiche (modifica suggerimento + assegna stat)
    4. Nome + salvataggio

Il wizard è offline: nessuna API, solo albero decisionale + dati PHB.
"""

import flet as ft
import logging

from config.settings import (
    COLOR_BG_PRIMARY, COLOR_BG_SECONDARY, COLOR_BG_CARD,
    COLOR_ACCENT_GOLD, COLOR_ACCENT_RED, COLOR_BORDER,
    COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY, COLOR_TEXT_MUTED, COLOR_TEXT_TITLE,
    CLASSES, RACES, ALIGNMENTS, ABILITY_SCORES, ABILITY_KEYS, STANDARD_ARRAY,
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
from data.repositories import character_repo
from data.models import CharacterProficiency

logger = logging.getLogger(__name__)

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
        self._current_q_index: int = 0      # indice in WIZARD_QUESTIONS
        self._phase: str = "questions"       # questions | recommendation | review | confirm

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
            padding=ft.padding.symmetric(horizontal=24, vertical=14),
            bgcolor=COLOR_BG_SECONDARY,
            border=ft.border.only(bottom=ft.BorderSide(1, COLOR_BORDER)),
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
        self._progress_bar.update()

    def _set_content(self, control: ft.Control):
        self._content.content = control
        self._content.update()

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
        elif self._phase == "confirm":
            self._phase = "review"
            self._render_review()

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
                letter_spacing=2,
            ),
            padding=ft.padding.symmetric(horizontal=10, vertical=4),
            border=ft.border.all(1, COLOR_ACCENT_GOLD),
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
                padding=ft.padding.symmetric(horizontal=20, vertical=14),
                bgcolor=COLOR_BG_CARD,
                border=ft.border.all(1, COLOR_BORDER),
                border_radius=8,
                on_click=lambda e, o=opt: _toggle_option(o["id"]),
                ink=True,
                animate=ft.animation.Animation(120, ft.AnimationCurve.EASE_OUT),
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
                    card.border = ft.border.all(2, COLOR_ACCENT_GOLD)
                    # Aggiorna colore icona
                    row = card.content
                    row.controls[0] = _icon(
                        next(o["icon"] for o in q["options"] if o["id"] == oid),
                        COLOR_ACCENT_GOLD, 28,
                    )
                else:
                    card.bgcolor = COLOR_BG_CARD
                    card.border = ft.border.all(1, COLOR_BORDER)
                    row = card.content
                    row.controls[0] = _icon(
                        next(o["icon"] for o in q["options"] if o["id"] == oid),
                        COLOR_TEXT_MUTED, 28,
                    )
                card.update()

        # Bottone Avanti
        next_btn = ft.ElevatedButton(
            text="Avanti",
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
                padding=ft.padding.symmetric(horizontal=40, vertical=24),
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
        rec_class = top3[0][0]
        rec_bg    = self.engine.get_recommended_background()
        rec_race  = self.engine.get_recommended_race(rec_class)
        rec_align = self.engine.get_alignment_string()

        def _class_card(cls: str, pts: int, is_top: bool) -> ft.Container:
            border_color = COLOR_ACCENT_GOLD if is_top else COLOR_BORDER
            border_width = 2 if is_top else 1
            badge = ft.Container(
                content=ft.Text(
                    "★ CONSIGLIATO" if is_top else f"#{top3.index((cls, pts)) + 1}",
                    size=10,
                    weight=ft.FontWeight.BOLD,
                    color=COLOR_BG_PRIMARY if is_top else COLOR_TEXT_MUTED,
                ),
                bgcolor=COLOR_ACCENT_GOLD if is_top else COLOR_BG_SECONDARY,
                border_radius=4,
                padding=ft.padding.symmetric(horizontal=8, vertical=3),
            )
            hit_die = CLASSES.get(cls, {}).get("hit_die", 8)
            spell_ab = CLASSES.get(cls, {}).get("spellcasting_ability")
            spell_label = (
                {"int": "Intelligenza", "wis": "Saggezza", "cha": "Carisma"}.get(spell_ab, "—")
                if spell_ab else "—"
            )
            return ft.Container(
                content=ft.Column(
                    [
                        ft.Row([badge], alignment=ft.MainAxisAlignment.START),
                        ft.Container(height=8),
                        ft.Text(
                            cls,
                            size=20 if is_top else 16,
                            weight=ft.FontWeight.BOLD,
                            color=COLOR_ACCENT_GOLD if is_top else COLOR_TEXT_PRIMARY,
                        ),
                        ft.Container(height=6),
                        muted_text(CLASS_DESCRIPTIONS.get(cls, ""), size=12),
                        ft.Container(height=8),
                        ft.Row(
                            [
                                ft.Column(
                                    [
                                        label_text("Dado Vita", size=10),
                                        body_text(f"d{hit_die}", size=14),
                                    ],
                                    spacing=2,
                                ),
                                ft.VerticalDivider(width=1, color=COLOR_BORDER),
                                ft.Column(
                                    [
                                        label_text("Incantesimi", size=10),
                                        body_text(spell_label, size=14),
                                    ],
                                    spacing=2,
                                ),
                            ],
                            spacing=16,
                        ),
                    ],
                    spacing=0,
                ),
                padding=16,
                bgcolor="#2a1f08" if is_top else COLOR_BG_CARD,
                border=ft.border.all(border_width, border_color),
                border_radius=8,
            )

        class_cards = ft.Column(
            [_class_card(cls, pts, i == 0) for i, (cls, pts) in enumerate(top3)],
            spacing=10,
        )

        # Suggerimenti razza e background
        summary_row = ft.Row(
            [
                ft.Column(
                    [
                        label_text("RAZZA SUGGERITA", size=10),
                        body_text(rec_race, size=15, weight=ft.FontWeight.W_600),
                        muted_text("Ottima sinergia con la classe", size=11),
                    ],
                    spacing=4,
                    expand=True,
                ),
                ft.VerticalDivider(width=1, color=COLOR_BORDER),
                ft.Column(
                    [
                        label_text("BACKGROUND SUGGERITO", size=10),
                        body_text(rec_bg, size=15, weight=ft.FontWeight.W_600),
                        muted_text(
                            ", ".join(BACKGROUNDS.get(rec_bg, {}).get("skills", [])),
                            size=11,
                        ),
                    ],
                    spacing=4,
                    expand=True,
                ),
                ft.VerticalDivider(width=1, color=COLOR_BORDER),
                ft.Column(
                    [
                        label_text("ALLINEAMENTO", size=10),
                        body_text(rec_align, size=15, weight=ft.FontWeight.W_600),
                        muted_text("Dalle tue risposte", size=11),
                    ],
                    spacing=4,
                    expand=True,
                ),
            ],
            spacing=16,
        )

        content = ft.Column(
            [
                ft.Text(
                    "Il tuo personaggio ideale",
                    size=24,
                    weight=ft.FontWeight.BOLD,
                    color=COLOR_TEXT_TITLE,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Container(height=6),
                muted_text(
                    "Ecco i tre archetipi più adatti alle tue preferenze.",
                    size=13,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Container(height=20),
                class_cards,
                ft.Container(height=16),
                fantasy_card(summary_row, padding=16),
                ft.Container(height=20),
                ft.Row(
                    [
                        ghost_button("Indietro", on_click=self._on_back),
                        primary_button(
                            "Personalizza e continua",
                            on_click=lambda e: self._goto_review(rec_class, rec_race, rec_bg, rec_align),
                            icon=ft.Icons.ARROW_FORWARD,
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
                padding=ft.padding.symmetric(horizontal=40, vertical=24),
            )
        )

    # ------------------------------------------------------------------
    # FASE 3: Revisione (modifica suggerimento + statistiche)
    # ------------------------------------------------------------------

    def _goto_review(self, rec_class, rec_race, rec_bg, rec_align):
        self._review_class   = rec_class
        self._review_race    = rec_race
        self._review_bg      = rec_bg
        self._review_align   = rec_align
        self._review_stats   = self.engine.get_suggested_stat_assignment(rec_class)
        self._phase = "review"
        self._render_review()

    def _render_review(self):
        self._phase = "review"

        # ------ Dropdown identità ------
        class_dd = ft.Dropdown(
            label="Classe",
            value=self._review_class,
            options=[ft.dropdown.Option(c) for c in CLASSES.keys()],
            on_change=self._on_class_change,
            bgcolor=COLOR_BG_CARD,
            color=COLOR_TEXT_PRIMARY,
            label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=12),
            border_color=COLOR_BORDER,
            focused_border_color=COLOR_ACCENT_GOLD,
            expand=True,
        )
        race_dd = ft.Dropdown(
            label="Razza",
            value=self._review_race,
            options=[ft.dropdown.Option(r) for r in RACES],
            on_change=lambda e: setattr(self, "_review_race", e.control.value),
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
            options=[ft.dropdown.Option(b) for b in BACKGROUNDS.keys()],
            on_change=lambda e: setattr(self, "_review_bg", e.control.value),
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
            options=[ft.dropdown.Option(a) for a in ALIGNMENTS],
            on_change=lambda e: setattr(self, "_review_align", e.control.value),
            bgcolor=COLOR_BG_CARD,
            color=COLOR_TEXT_PRIMARY,
            label_style=ft.TextStyle(color=COLOR_TEXT_MUTED, size=12),
            border_color=COLOR_BORDER,
            focused_border_color=COLOR_ACCENT_GOLD,
            expand=True,
        )

        # ------ Statistiche (Standard Array) ------
        # I valori disponibili da assegnare
        available_values = list(STANDARD_ARRAY)  # [15,14,13,12,10,8]
        # Mappa stat_key → dropdown
        stat_dropdowns: dict[str, ft.Dropdown] = {}
        stat_section_ref = ft.Ref[ft.Column]()

        def _make_stat_row(key: str, label: str) -> ft.Row:
            current_val = self._review_stats.get(key, 10)
            mod = get_modifier(current_val)
            mod_str = get_modifier_str(current_val)

            dd = ft.Dropdown(
                value=str(current_val),
                options=[ft.dropdown.Option(str(v)) for v in sorted(available_values, reverse=True)],
                on_change=lambda e, k=key: _on_stat_change(k, int(e.control.value)),
                bgcolor=COLOR_BG_CARD,
                color=COLOR_TEXT_PRIMARY,
                border_color=COLOR_BORDER,
                focused_border_color=COLOR_ACCENT_GOLD,
                width=90,
            )
            stat_dropdowns[key] = dd

            mod_badge = ft.Container(
                content=ft.Text(
                    mod_str,
                    size=12,
                    weight=ft.FontWeight.BOLD,
                    color=COLOR_ACCENT_GOLD if mod >= 0 else COLOR_ACCENT_RED,
                ),
                width=42,
                alignment=ft.alignment.center,
            )

            return ft.Row(
                [
                    ft.Text(label, size=13, color=COLOR_TEXT_PRIMARY, width=120),
                    dd,
                    mod_badge,
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=8,
            )

        def _on_stat_change(key: str, new_val: int):
            self._review_stats[key] = new_val
            # Aggiorna i modificatori (solo il testo del badge)
            # Ri-render minimale: aggiorna solo il badge
            for k, dd_ctrl in stat_dropdowns.items():
                v = self._review_stats.get(k, 10)
                ms = get_modifier_str(v)
                row = dd_ctrl.parent
                if row and len(row.controls) >= 3:
                    badge = row.controls[2]
                    badge.content.value = ms
                    m = get_modifier(v)
                    badge.content.color = COLOR_ACCENT_GOLD if m >= 0 else COLOR_ACCENT_RED
                    badge.update()

        stat_rows = ft.Column(
            [
                _make_stat_row(key, label)
                for key, label in zip(ABILITY_KEYS, ABILITY_SCORES)
            ],
            spacing=8,
            ref=stat_section_ref,
        )

        # Nota sul dado vita
        def _hit_die_note() -> str:
            hd = CLASSES.get(self._review_class, {}).get("hit_die", 8)
            con_mod = get_modifier(self._review_stats.get("con", 10))
            hp = max(1, hd + con_mod)
            sign = "+" if con_mod >= 0 else ""
            return f"HP al Lv.1: d{hd}{sign}{con_mod} = {hp}  (modifica Cos. per cambiare)"

        hp_note_text = ft.Text(
            _hit_die_note(),
            size=11,
            color=COLOR_TEXT_MUTED,
            italic=True,
        )

        def _on_class_change(e):
            self._review_class = e.control.value
            # Ricalcola stat suggerite per la nuova classe
            self._review_stats = self.engine.get_suggested_stat_assignment(self._review_class)
            # Aggiorna i dropdown
            for key, dd_ctrl in stat_dropdowns.items():
                dd_ctrl.value = str(self._review_stats.get(key, 10))
                dd_ctrl.update()
            _on_stat_change("", 0)  # aggiorna tutti i badge
            hp_note_text.value = _hit_die_note()
            hp_note_text.update()

        content = ft.Column(
            [
                ft.Text(
                    "Personalizza il tuo personaggio",
                    size=22,
                    weight=ft.FontWeight.BOLD,
                    color=COLOR_TEXT_TITLE,
                ),
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

                ft.Container(height=20),
                ft.Row(
                    [
                        ghost_button("Indietro", on_click=self._on_back),
                        primary_button(
                            "Continua",
                            on_click=lambda e: self._goto_confirm(),
                            icon=ft.Icons.ARROW_FORWARD,
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
                padding=ft.padding.symmetric(horizontal=40, vertical=24),
            )
        )

    # ------------------------------------------------------------------
    # FASE 4: Nome + conferma + salvataggio
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
                padding=ft.padding.symmetric(horizontal=12, vertical=8),
                bgcolor=COLOR_BG_SECONDARY,
                border=ft.border.all(1, COLOR_BORDER),
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
                ok = character_repo.create(char)
                if not ok:
                    raise RuntimeError("Errore nel salvataggio sul database.")

                # Salva competenze del background (abilità suggerite)
                bg_skills = BACKGROUNDS.get(self._review_bg, {}).get("skills", [])
                for skill in bg_skills:
                    character_repo._save_single_proficiency(
                        char.id, "skill", skill
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
                padding=ft.padding.symmetric(horizontal=40, vertical=24),
            )
        )
