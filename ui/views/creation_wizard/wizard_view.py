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

import copy
import flet as ft
import logging
from typing import Any, cast

from config.settings import (
    RACES_BASE, DRACONIDE_ANCESTRIES, ALIGNMENTS, ABILITY_SCORES, ABILITY_KEYS,
    STANDARD_ARRAY, SKILLS, LANGUAGES, WEAPONS_BY_CATEGORY, get_modifier, get_modifier_str,
    get_permanent_class_hp_bonus, get_feats_permanent_hp_bonus,
)
from ui.theme import (
    title_text, muted_text,
    section_header, primary_button, ghost_button,
)
from ui.widgets import (
    CardPicker, spell_card_options, feat_card_options,
    format_equipment_item_body, equipment_option_card_options,
)
from core.wizard_engine import WizardEngine
from core.equipment_manager import ArmorCandidate, resolve_armor_equip
from data.game_data.wizard_data import (
    WIZARD_QUESTIONS, CLASS_DESCRIPTIONS,
)
from data.game_data.game_data_loader import GameDataLoader
from data.repositories import character_repo
from ui.views.creation_wizard.creation_shared import CreationSharedMixin
from ui import design

logger = logging.getLogger(__name__)
_loader = GameDataLoader()

# Classi "preparatrici" (nessuna lista di incantesimi conosciuti fissa —
# scelgono ogni giorno dal pool completo) per cui, a differenza di
# Bardo/Stregone/Warlock (known) e del Mago (libro degli incantesimi,
# gestito a parte), aggiungiamo comunque una scelta di incantesimi
# preparati iniziale alla creazione: senza, il personaggio nascerebbe a 0
# incantesimi preparati e il giocatore dovrebbe aprire la tab Incantesimi
# prima di poter giocare. Il Ranger NON è incluso:
# nonostante SpellsView._PREP_HALF lo tratti (erroneamente, vedi TODO in
# CLAUDE.md) come "mezzo preparatore", ranger.json conferma testualmente che
# il ranger "conosce" un numero fisso di incantesimi (stessa meccanica di
# Bardo/Stregone/Warlock), quindi va escluso da questa lista — i suoi
# incantesimi iniziali arrivano dal 2° livello via lo step SPELL_LEARN del
# level-up, già esistente.
# _PREPARED_CASTER_CLASSES vive ora in creation_shared.py insieme ai metodi
# che la usano (_compute_prepared_spell_count).

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

def _icon(name: str, color: str | None = None, size: int = 28) -> ft.Icon:
    return ft.Icon(_ICON_MAP.get(name, ft.Icons.HELP_OUTLINE),
                   color=color or design.T().text_2, size=size)


class WizardView(CreationSharedMixin, ft.Column):
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
        self._review_subrace:   str        = ""   # sottorazza o discendenza Dragonide
        self._review_subclass:  str        = ""   # sottoclasse (solo se lv1)
        # Competenze bonus di sottoclasse a scelta — es. Chierico Dominio
        # della Natura/Conoscenza, Bardo Collegio della Conoscenza; vedi
        # bonus_proficiencies in classes/*.json e
        # character_repo.classify_bonus_proficiency_entries(). Solo Chierico
        # (subclass_choice_level=1) può valorizzarla in questa fase di
        # creazione — Bardo/Ladro (level 3) la gestiscono al level-up.
        self._review_subclass_bonus_choices: list[str] = []
        self._review_bg:        str        = ""
        self._review_align:     str        = ""
        self._review_stats:     dict       = {}
        self._review_skills:    list[str]  = []   # abilità scelte dalla lista di classe
        self._review_languages: list[str]  = []   # lingue scelte dal background
        self._review_tools:     list[str]  = []   # strumenti scelti dal background
        self._review_class_tools: list[str] = []  # strumenti a scelta di CLASSE (Bardo/Monaco)
        # Scelte extra per razza/classe
        self._review_dragon_ancestry: str       = ""   # Stregone Discendenza Draconica
        self._review_fighting_style:  str       = ""   # Guerriero/Paladino/Ranger
        self._review_mezzelf_flex:    list[str] = []   # 2 stat key per +1 Mezzelf
        self._review_mezzelf_skills:  list[str] = []   # 2 abilità Mezzelf (Versatilità)
        self._review_elf_cantrip:     str       = ""   # trucchetto Alto Elfo
        # Lingua/e a scelta libera concesse dalla RAZZA (Umano, Mezzelfo,
        # ecc.), vedi _race_language_choice_count()
        self._review_race_languages:  list[str] = []
        # Umano: Standard (+1 a tutte le stat) vs Variante
        self._review_umano_variant:            bool      = False
        self._review_umano_variant_stats:      list[str] = []
        self._review_umano_variant_skill:      str       = ""
        self._review_umano_variant_feat:       str       = ""
        self._review_umano_variant_feat_bonus_stat: str  = ""
        # Competenze a scelta concesse dal talento (proficiency_grants in
        # feats.json, es. Abile/Maestro d'Armi/Linguista) se il talento scelto
        # come Variante Umana ne ha — stesso schema dell'ASI level-up in
        # profilo_tab.py e di manual_form.py.
        self._review_umano_variant_feat_prof_values: list[str] = []
        self._review_expertise:       list[str] = []   # 2 abilità Maestria Ladro Lv1
        # Trucchetti/incantesimi conosciuti scelti alla creazione
        self._review_cantrips:        list[str] = []
        self._review_spells_lv1:      list[str] = []
        # Incantesimi preparati iniziali per Chierico/Druido/Paladino —
        # questi non hanno una lista "conosciuta" fissa (preparano ogni
        # giorno dal pool completo), ma senza questa scelta nascerebbero a 0
        # incantesimi preparati e il giocatore dovrebbe aprire la tab
        # Incantesimi prima di poter giocare.
        self._review_prepared_spells: list[str] = []
        # Libro degli Incantesimi del Mago: 6 incantesimi di 1° livello —
        # mago.json → "spellbook_starting_spells".
        self._review_spellbook_spells: list[str] = []

        # Stato equipment (popolato in _render_equipment)
        # lista di dict: {name, item_type, quantity, selected}
        self._equip_fixed:   list[dict[str, Any]] = []
        # lista di dict: {options: [[item,...]], chosen_idx: int}
        self._equip_choices: list[dict[str, Any]] = []

        # Area di contenuto centrale (sostituita ad ogni step)
        self._content = ft.Container(expand=True, bgcolor=design.T().bg)
        self._progress_bar = ft.ProgressBar(
            value=0.0,
            color=design.T().magic,
            bgcolor=design.T().border,
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
                        icon_color=design.T().text_2,
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
            bgcolor=design.T().surface_alt,
            border=ft.Border.only(bottom=ft.BorderSide(1, design.T().border)),
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
        phase_label = design.chip(q["phase"].upper(), tone="magic")

        counter = design.muted(
            f"{self._current_q_index + 1} / {len(WIZARD_QUESTIONS)}",
            size=12,
        )

        # Un solo momento tipografico "hero" per schermata (Arcane Ledger):
        # la domanda corrente è il contenuto dominante di questo step.
        question_hero = design.hero_title(q["text"], q.get("subtitle", ""))
        question_hero.horizontal_alignment = ft.CrossAxisAlignment.CENTER
        for _kid in question_hero.controls:
            if isinstance(_kid, ft.Text):
                _kid.text_align = ft.TextAlign.CENTER

        # ------ Opzioni ------
        option_controls: list[ft.Control] = []
        option_refs: dict[str, ft.Container] = {}
        option_icon_refs: dict[str, ft.Container] = {}

        def make_option_card(opt: dict) -> ft.Container:
            icon_slot = design.icon_badge(
                _ICON_MAP.get(opt["icon"], ft.Icons.HELP_OUTLINE), tone="neutral", size=44,
            )
            option_icon_refs[opt["id"]] = icon_slot
            card = design.card(
                ft.Row(
                    [
                        icon_slot,
                        ft.Container(width=16),
                        ft.Column(
                            [
                                ft.Text(
                                    opt["text"],
                                    size=15,
                                    weight=ft.FontWeight.W_600,
                                    color=design.T().text,
                                ),
                                ft.Text(
                                    opt["desc"],
                                    size=12,
                                    color=design.T().text_3,
                                ),
                            ],
                            spacing=2,
                            expand=True,
                        ),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                on_click=lambda e, o=opt: _toggle_option(o["id"]),
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
                is_sel = oid in selected
                card.bgcolor = design.T().info_bg if is_sel else design.T().surface
                card.border = ft.Border.all(2 if is_sel else 1,
                                            design.T().magic if is_sel else design.T().border)
                # Aggiorna la tinta del badge icona
                icon_slot = option_icon_refs[oid]
                icon_data = next(o["icon"] for o in q["options"] if o["id"] == oid)
                fresh_badge = design.icon_badge(
                    _ICON_MAP.get(icon_data, ft.Icons.HELP_OUTLINE),
                    tone="magic" if is_sel else "neutral", size=44,
                )
                icon_slot.content = fresh_badge.content
                icon_slot.bgcolor = fresh_badge.bgcolor
                card.update()

        # Bottone Avanti — CTA primaria (oro/bronzo Arcane Ledger)
        next_btn = ft.ElevatedButton(
            "Avanti",
            icon=ft.Icons.ARROW_FORWARD,
            disabled=True,
            on_click=lambda e: _on_next(),
            style=ft.ButtonStyle(
                bgcolor=design.T().primary_fill,
                color=design.T().on_primary_fill,
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

        # Griglia opzioni responsive: 2 colonne da schermo "md" in su, una
        # sola colonna impilata sotto (`ResponsiveRow`/`col=`, mai `expand=`
        # su una Row semplice — vedi `design.asymmetric_row()` per il
        # perché). Prima era una Column mono-colonna "temporanea" (il
        # commento originale già chiedeva la griglia a 2 colonne).
        options_col = ft.ResponsiveRow(
            [ft.Container(content=c, col={"xs": 12, "md": 6}) for c in option_controls],
            columns=12, spacing=10, run_spacing=10,
        )

        content = ft.Column(
            [
                ft.Row(
                    [phase_label, ft.Container(expand=True), counter],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Container(height=16),
                question_hero,
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
                padding=ft.Padding.symmetric(horizontal=16, vertical=20),
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

        # Etichetta razza dinamica in base alla classe selezionata
        race_label_ref = ft.Ref[ft.Text]()

        def _refresh_cards():
            sel = selected_class[0]
            for cls, card in card_refs.items():
                is_sel = cls == sel
                card.bgcolor = design.T().info_bg if is_sel else design.T().surface
                card.border = (
                    ft.Border.all(1.5, ft.Colors.with_opacity(0.55, design.T().primary))
                    if is_sel else ft.Border.all(1, design.T().border)
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
                        color=design.T().bg if is_top else design.T().text_3,
                    ),
                    bgcolor=design.T().magic if is_top else design.T().surface_alt,
                    border_radius=3,
                    padding=ft.Padding.symmetric(horizontal=8, vertical=3),
                ),
                ft.Container(width=6),
                ft.Container(
                    content=ft.Text(
                        "● SELEZIONATO" if is_top else "  Seleziona",
                        size=9, weight=ft.FontWeight.BOLD,
                        color=design.T().primary if is_top else design.T().text_3,
                    ),
                    border=ft.Border.all(1, design.T().primary if is_top else design.T().border),
                    border_radius=3,
                    padding=ft.Padding.symmetric(horizontal=8, vertical=3),
                ),
            ]
            _cls_data = _loader.get_class(cls) or {}
            hit_die = _cls_data.get("hit_die", 8)
            spell_ab = _cls_data.get("spellcasting_ability")
            spell_label = (
                {"int": "Intelligenza", "wis": "Saggezza", "cha": "Carisma"}.get(spell_ab, "—")
                if spell_ab else "—"
            )
            header_row: list[ft.Control] = [
                design.icon_badge(ft.Icons.AUTO_AWESOME if is_top else ft.Icons.SHIELD,
                                   tone="primary" if is_top else "neutral", size=36),
                ft.Container(width=12),
                ft.Column(
                    [
                        ft.Row(cast(list[ft.Control], badges), alignment=ft.MainAxisAlignment.START),
                        ft.Text(cls, size=18 if is_top else 15, weight=ft.FontWeight.BOLD,
                                color=design.T().primary if is_top else design.T().text),
                    ],
                    spacing=4, expand=True,
                ),
            ]
            card = design.card(
                ft.Column(
                    controls=cast(list[ft.Control], [
                        ft.Row(header_row, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        ft.Container(height=8),
                        design.muted(CLASS_DESCRIPTIONS.get(cls, ""), size=12),
                        ft.Container(height=8),
                        ft.Row([
                            ft.Column([design.label("Dado Vita"), design.body(f"d{hit_die}", 14)], spacing=2),
                            ft.Container(width=24),
                            ft.Column([design.label("Incantesimi"), design.body(spell_label, 14)], spacing=2),
                        ], spacing=0),
                    ]),
                    spacing=0,
                ),
                accent=design.T().primary if is_top else None,
                hero=is_top,
                on_click=lambda e, c=cls: _select_class(c),
            )
            card.bgcolor = design.T().info_bg if is_top else design.T().surface
            card_refs[cls] = card
            return card

        class_cards = ft.Column(
            [_class_card(cls, pts, i) for i, (cls, pts) in enumerate(top3)],
            spacing=8,
        )

        # Riepilogo delle scelte finora — pannello "minor" accanto alla
        # scelta di classe (asymmetric_row, Arcane Ledger): a differenza del
        # vecchio ft.Row a 3 colonne + VerticalDivider (pensato per schermo
        # largo), qui è impilato verticalmente perché vive in una colonna
        # più stretta (ratio 7/5) che può scendere sotto la soglia mobile.
        def _summary_item(label: str, value: ft.Control, hint: str) -> ft.Column:
            return ft.Column([design.label(label), value, design.muted(hint, size=11)], spacing=4)

        summary_col = ft.Column(
            [
                _summary_item(
                    "Razza suggerita",
                    ft.Text(rec_race_by_class[top3[0][0]], size=15,
                            weight=ft.FontWeight.W_600, color=design.T().text,
                            ref=race_label_ref),
                    "Sinergia ottimale con la classe",
                ),
                ft.Divider(height=1, color=design.T().border),
                _summary_item(
                    "Background suggerito",
                    design.body(rec_bg, 15, weight=ft.FontWeight.W_600),
                    ", ".join((_loader.get_background(rec_bg) or {}).get("skill_proficiencies", [])),
                ),
                ft.Divider(height=1, color=design.T().border),
                _summary_item(
                    "Allineamento",
                    design.body(rec_align, 15, weight=ft.FontWeight.W_600),
                    "Dalle tue risposte",
                ),
            ],
            spacing=12,
        )

        def _on_continue(e):
            cls  = selected_class[0]
            race = rec_race_by_class.get(cls, "Umano")
            self._goto_review(cls, race, rec_bg, rec_align)

        heading = design.hero_title(
            "Il tuo personaggio ideale",
            "Clicca su una classe per selezionarla, poi personalizza.",
        )

        content = ft.Column(
            [
                heading,
                ft.Container(height=20),
                design.asymmetric_row(
                    class_cards,
                    design.section("Riepilogo scelte", summary_col, accent=design.T().magic),
                    ratio=(7, 5),
                ),
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
                    wrap=True,
                ),
            ],
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

        self._set_content(
            ft.Container(
                content=content,
                expand=True,
                padding=ft.Padding.symmetric(horizontal=16, vertical=20),
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
        self._review_race_languages  = []
        self._review_expertise       = []
        self._review_cantrips        = []
        self._review_spells_lv1      = []
        self._review_prepared_spells = []
        self._phase = "review"
        self._render_review()

    # ------------------------------------------------------------------
    # Helper: costruisce le sezioni dinamiche della Review
    # ------------------------------------------------------------------

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
                tool_categories = _loader.get_tool_categories()
                if isinstance(frm, list):
                    seen_labels: set[str] = set()
                    opts = []
                    for k in frm:
                        label = _loader.get_tool_category_label(k) or tool_categories.get(k, [k])[0]
                        if label not in seen_labels:
                            opts.append(label)
                            seen_labels.add(label)
                else:
                    opts = tool_categories.get(frm, [])
                result.append((count, opts))
        return result

    def _class_tool_choices(self) -> list[tuple[int, list[str]]]:
        """
        (count, options) per gli strumenti/attrezzi a scelta concessi dalla
        CLASSE (non dal background) — es. Bardo: 3 strumenti musicali a
        scelta, Monaco: 1 strumento artigiano O musicale a scelta. Stessa
        fonte dato di _bg_tool_choices() (equipment/tools.json via
        get_tool_categories()), ma letta da cls_data invece che da bg_data.
        """
        cls_data = _loader.get_class(self._review_class)
        if not cls_data:
            return []
        result: list[tuple[int, list[str]]] = []
        for entry in cls_data.get("tool_proficiencies", []):
            if isinstance(entry, dict) and entry.get("type") == "choice":
                frm = entry.get("from", "")
                count = entry.get("count", 1)
                tool_categories = _loader.get_tool_categories()
                if isinstance(frm, list):
                    seen_labels: set[str] = set()
                    opts = []
                    for k in frm:
                        label = _loader.get_tool_category_label(k) or tool_categories.get(k, [k])[0]
                        if label not in seen_labels:
                            opts.append(label)
                            seen_labels.add(label)
                else:
                    opts = tool_categories.get(frm, [])
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
            options=[ft.DropdownOption(key=c, text=str(c)) for c in _loader.get_class_names()],
            on_select=lambda e: _on_class_change(e),
            bgcolor=design.T().surface,
            color=design.T().text,
            label_style=ft.TextStyle(color=design.T().text_3, size=12),
            border_color=design.T().border,
            focused_border_color=design.T().magic,
            expand=True,
            border_radius=design.field_style()['border_radius'], text_style=design.field_style()['text_style'])
        race_dd = ft.Dropdown(
            label="Razza",
            value=self._review_race if self._review_race in RACES_BASE else list(RACES_BASE.keys())[0],
            options=[ft.DropdownOption(key=r, text=str(r)) for r in RACES_BASE.keys()],
            on_select=lambda e: _on_race_change(e),
            bgcolor=design.T().surface,
            color=design.T().text,
            label_style=ft.TextStyle(color=design.T().text_3, size=12),
            border_color=design.T().border,
            focused_border_color=design.T().magic,
            expand=True,
            border_radius=design.field_style()['border_radius'], text_style=design.field_style()['text_style'])
        bg_dd = ft.Dropdown(
            label="Background",
            value=self._review_bg,
            options=[ft.DropdownOption(key=b, text=str(b)) for b in _loader.get_background_names()],
            on_select=lambda e: _on_bg_change(e),
            bgcolor=design.T().surface,
            color=design.T().text,
            label_style=ft.TextStyle(color=design.T().text_3, size=12),
            border_color=design.T().border,
            focused_border_color=design.T().magic,
            expand=True,
            border_radius=design.field_style()['border_radius'], text_style=design.field_style()['text_style'])
        align_dd = ft.Dropdown(
            label="Allineamento",
            value=self._review_align if self._review_align in ALIGNMENTS else ALIGNMENTS[0],
            options=[ft.DropdownOption(key=a, text=str(a)) for a in ALIGNMENTS],
            on_select=lambda e: setattr(self, "_review_align", e.control.value),
            bgcolor=design.T().surface,
            color=design.T().text,
            label_style=ft.TextStyle(color=design.T().text_3, size=12),
            border_color=design.T().border,
            focused_border_color=design.T().magic,
            expand=True,
            border_radius=design.field_style()['border_radius'], text_style=design.field_style()['text_style'])

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
                bgcolor=design.T().surface,
                color=design.T().text,
                border_color=design.T().border,
                focused_border_color=design.T().magic,
                width=110,
                border_radius=design.field_style()['border_radius'], text_style=design.field_style()['text_style'])
            stat_dropdowns[key] = dd
            mod_badge = ft.Container(
                content=ft.Text(mod_str, size=13, weight=ft.FontWeight.BOLD,
                                color=design.T().magic if mod >= 0 else design.T().danger),
                width=40,
                alignment=ft.Alignment.CENTER,
            )
            return ft.Row(
                [ft.Text(label, size=13, color=design.T().text, expand=True), dd, mod_badge],
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
                    cast(ft.Text, badge.content).color = design.T().magic if m >= 0 else design.T().danger
                    badge.update()
            # Cambiare la caratteristica da incantatore (es. Saggezza per un
            # Chierico) può cambiare quanti incantesimi preparati iniziali
            # spettano al personaggio — ricalcola la sezione.
            # `_rebuild_spells_init_col` è definita più avanti nello
            # stesso scope di `_render_review`, ma essendo risolta per nome
            # al momento della chiamata (non della definizione), è già
            # disponibile quando `_on_stat_change` viene davvero invocata
            # (sempre dopo il completamento dell'intero corpo del metodo).
            try:
                _rebuild_spells_init_col()
            except NameError:
                pass

        stat_rows = ft.Column(
            [_make_stat_row(key, label) for key, label in zip(ABILITY_KEYS, ABILITY_SCORES)],
            spacing=8,
        )

        def _hit_die_note() -> str:
            hd = (_loader.get_class(self._review_class) or {}).get("hit_die", 8)
            con_mod = get_modifier(self._review_stats.get("con", 10))
            hp = max(1, hd + con_mod)
            sign = "+" if con_mod >= 0 else ""
            return f"HP al Lv.1: d{hd}{sign}{con_mod} = {hp}  (modifica Cos. per cambiare)"

        hp_note_text = ft.Text(_hit_die_note(), size=11, color=design.T().text_3, italic=True)

        # ------ Sezione sottorazza / discendenza (dinamica) ------
        subrace_col = ft.Column([], spacing=8, visible=False)

        def _rebuild_subrace_col():
            subrace_col.controls.clear()
            race = self._review_race
            subraces = RACES_BASE.get(race, [])
            if race == "Dragonide":
                # Discendenza draconica
                anc_dd = ft.Dropdown(
                    label="Discendenza Draconica",
                    value=self._review_subrace or DRACONIDE_ANCESTRIES[0],
                    options=[ft.DropdownOption(key=a, text=a) for a in DRACONIDE_ANCESTRIES],
                    on_select=lambda e: setattr(self, "_review_subrace", e.control.value),
                    bgcolor=design.T().surface,
                    color=design.T().text,
                    label_style=ft.TextStyle(color=design.T().text_3, size=12),
                    border_color=design.T().border,
                    focused_border_color=design.T().magic,
                    expand=True,
                    border_radius=design.field_style()['border_radius'], text_style=design.field_style()['text_style'])
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
                        _rebuild_lang_tool_col(),
                    ],
                    bgcolor=design.T().surface,
                    color=design.T().text,
                    label_style=ft.TextStyle(color=design.T().text_3, size=12),
                    border_color=design.T().border,
                    focused_border_color=design.T().magic,
                    expand=True,
                    border_radius=design.field_style()['border_radius'], text_style=design.field_style()['text_style'])
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
                    _rebuild_subclass_bonus_col(),
                    # Cambiare patrono (Warlock) cambia il pool di incantesimi
                    # di 1° livello disponibili (Lista Incantesimi Ampliata)
                    # — no-op per qualunque altra classe/sottoclasse.
                    # Definita più avanti nello stesso
                    # scope di _render_review, risolta per nome al momento
                    # della chiamata (mai prima del completamento del metodo).
                    _rebuild_spells_init_col(),
                ],
                bgcolor=design.T().surface,
                color=design.T().text,
                label_style=ft.TextStyle(color=design.T().text_3, size=12),
                border_color=design.T().border,
                focused_border_color=design.T().magic,
                expand=True,
                border_radius=design.field_style()['border_radius'], text_style=design.field_style()['text_style'])
            subclass_col.controls.append(sc_dd)
            subclass_col.visible = bool(subclasses)
            try:
                subclass_col.update()
            except RuntimeError:
                pass

        _rebuild_subclass_col()

        # ------ Competenze bonus di sottoclasse ------
        # Chierico è l'unica classe lv1-subclass con bonus_proficiencies
        # (Stregone/Warlock non ne hanno). Voci fisse (armor/weapon token
        # bare) sono solo mostrate come promemoria informativo — vengono
        # applicate automaticamente al salvataggio via
        # character_repo.apply_subclass_bonus_proficiencies(). Voci
        # "choice" (es. Dominio della Natura: 1 abilità; Dominio della
        # Conoscenza: 2 abilità) mostrano N dropdown a mutua esclusione,
        # stesso pattern già usato per i trucchetti Lv.1/strumenti di
        # classe.
        subclass_bonus_col = ft.Column([], spacing=8, visible=False)
        _ARMOR_WEAPON_TOKEN_LABELS = {
            "leggere": "Armature Leggere", "medie": "Armature Medie",
            "pesanti": "Armature Pesanti", "scudi": "Scudi",
            "semplice": "Armi Semplici", "semplice_mischia": "Armi Semplici da Mischia",
            "guerra": "Armi da Guerra", "guerra_mischia": "Armi da Guerra da Mischia",
        }

        def _rebuild_subclass_bonus_col():
            subclass_bonus_col.controls.clear()
            entries = _loader.get_subclass_bonus_proficiencies(self._review_class, self._review_subclass)
            fixed, choices = character_repo.classify_bonus_proficiency_entries(entries)
            total_slots = sum(int(c.get("count", 0)) for c in choices)

            while len(self._review_subclass_bonus_choices) < total_slots:
                self._review_subclass_bonus_choices.append("")
            del self._review_subclass_bonus_choices[total_slots:]

            if not fixed and total_slots == 0:
                subclass_bonus_col.visible = False
                try:
                    subclass_bonus_col.update()
                except RuntimeError:
                    pass
                return

            if fixed:
                labels = ", ".join(_ARMOR_WEAPON_TOKEN_LABELS.get(f, f) for f in fixed)
                subclass_bonus_col.controls.append(ft.Text(
                    f"Competenze bonus dalla sottoclasse: {labels}",
                    size=12, color=design.T().text_2,
                ))

            if total_slots > 0:
                already = (
                    set(self._bg_skill_proficiencies())
                    | set(self._review_skills)
                    | set(self._review_mezzelf_skills)
                    | ({self._review_umano_variant_skill} if self._review_umano_variant_skill else set())
                )
                subclass_bonus_col.controls.append(ft.Text(
                    "Scegli le competenze bonus della sottoclasse",
                    size=13, color=design.T().text, weight=ft.FontWeight.W_600,
                ))
                def _build_choice_entry_dropdowns(choice_entry: dict, base: int) -> list[ft.Control]:
                    # Funzione dedicata (non un blocco inline dentro il for)
                    # così ogni entry ha il proprio scope locale isolato per
                    # `dds`/`base`/`n`/`pool` — evita un late-binding bug se
                    # in futuro una sottoclasse avesse più di un blocco
                    # "choice" (oggi non succede mai: ogni sottoclasse ne ha
                    # al massimo uno, ma la funzione resta generica).
                    count = int(choice_entry.get("count", 0))
                    pool = [
                        p for p in character_repo.resolve_bonus_proficiency_choice_options(choice_entry)
                        if p not in already
                    ]
                    dds: list[ft.Dropdown] = []

                    def _refresh() -> None:
                        for i, dd in enumerate(dds):
                            siblings = {
                                self._review_subclass_bonus_choices[base + j]
                                for j in range(count) if j != i
                            }
                            dd.options = [ft.DropdownOption(key=p, text=p) for p in pool if p not in siblings]
                            try:
                                dd.update()
                            except RuntimeError:
                                pass

                    for i in range(count):
                        idx = base + i
                        siblings = {
                            self._review_subclass_bonus_choices[base + j]
                            for j in range(count) if j != i
                        }
                        opts = [p for p in pool if p not in siblings]
                        curr = self._review_subclass_bonus_choices[idx] if idx < len(self._review_subclass_bonus_choices) else ""
                        if curr not in opts:
                            curr = opts[0] if opts else ""
                            self._review_subclass_bonus_choices[idx] = curr

                        def _make_handler(slot_idx=idx):
                            def _handler(e: Any) -> None:
                                self._review_subclass_bonus_choices[slot_idx] = e.control.value or ""
                                _refresh()
                            return _handler

                        dd = ft.Dropdown(
                            label=(f"Competenza bonus (scelta {i + 1})" if count > 1
                                   else "Competenza bonus (scelta sottoclasse)"),
                            value=curr,
                            options=[ft.DropdownOption(key=p, text=p) for p in opts],
                            on_select=_make_handler(),
                            bgcolor=design.T().surface, color=design.T().text,
                            label_style=ft.TextStyle(color=design.T().text_3, size=12),
                            border_color=design.T().border, focused_border_color=design.T().magic,
                            expand=True,
                            border_radius=design.field_style()['border_radius'], text_style=design.field_style()['text_style'])
                        dds.append(dd)
                    return list(dds)

                dd_row: list[ft.Control] = []
                slot_base = 0
                for choice_entry in choices:
                    dd_row.extend(_build_choice_entry_dropdowns(choice_entry, slot_base))
                    slot_base += int(choice_entry.get("count", 0))
                subclass_bonus_col.controls.append(ft.Row(dd_row, spacing=12, wrap=True))

            subclass_bonus_col.visible = True
            try:
                subclass_bonus_col.update()
            except RuntimeError:
                pass

        _rebuild_subclass_bonus_col()

        # ------ Tipo drago antenato (Stregone + Discendenza Draconica) ------
        dragon_col = ft.Column([], spacing=8, visible=False)

        def _rebuild_dragon_col():
            dragon_col.controls.clear()
            if self._review_subclass == "Discendenza Draconica":
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
                    bgcolor=design.T().surface,
                    color=design.T().text,
                    label_style=ft.TextStyle(color=design.T().text_3, size=12),
                    border_color=design.T().border,
                    focused_border_color=design.T().magic,
                    expand=True,
                    border_radius=design.field_style()['border_radius'], text_style=design.field_style()['text_style']))
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
            styles = _loader.get_fighting_styles((self._review_class or "").strip())
            if styles:
                if not self._review_fighting_style or self._review_fighting_style not in styles:
                    self._review_fighting_style = styles[0]
                fighting_style_col.controls.append(ft.Dropdown(
                    label="Stile di Combattimento",
                    value=self._review_fighting_style,
                    options=[ft.DropdownOption(key=s, text=s) for s in styles],
                    on_select=lambda e: setattr(self, "_review_fighting_style", e.control.value or ""),
                    bgcolor=design.T().surface,
                    color=design.T().text,
                    label_style=ft.TextStyle(color=design.T().text_3, size=12),
                    border_color=design.T().border,
                    focused_border_color=design.T().magic,
                    expand=True,
                    border_radius=design.field_style()['border_radius'], text_style=design.field_style()['text_style']))
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

            # --- Mezzelfo: +1 a 2 caratteristiche (escluso CHA già +2) ---
            if race == "Mezzelfo":
                has_content = True
                all_stat_keys = [k for k in ABILITY_KEYS if k != "cha"]
                all_stat_labels = {k: ABILITY_SCORES[i] for i, k in enumerate(ABILITY_KEYS)}
                # Mantieni selezioni valide
                self._review_mezzelf_flex = [k for k in self._review_mezzelf_flex if k in all_stat_keys]
                # Le due caratteristiche devono essere diverse (PHB: "+1 a
                # due caratteristiche a scelta") — se uno stato precedente ha
                # lasciato un duplicato, scarta il secondo valore e lascialo
                # rigenerare dal while sotto.
                if len(self._review_mezzelf_flex) == 2 and self._review_mezzelf_flex[0] == self._review_mezzelf_flex[1]:
                    self._review_mezzelf_flex = self._review_mezzelf_flex[:1]
                while len(self._review_mezzelf_flex) < 2:
                    for k in all_stat_keys:
                        if k not in self._review_mezzelf_flex:
                            self._review_mezzelf_flex.append(k)
                            break

                race_extras_col.controls.append(
                    ft.Text("Versatilità Mezzelf — assegna +1 a due caratteristiche (escluso Carisma)",
                            size=13, color=design.T().text, weight=ft.FontWeight.W_600)
                )
                flex_dds: list[ft.Control] = []
                flex_dd_refs: list[ft.Dropdown] = []

                def _refresh_mezzelf_flex_options() -> None:
                    # Ogni dropdown esclude dalle proprie opzioni il valore
                    # attualmente selezionato nell'ALTRO dropdown — le due
                    # caratteristiche non possono mai coincidere.
                    for i, dd in enumerate(flex_dd_refs):
                        other_idx = 1 - i
                        other_val = (
                            self._review_mezzelf_flex[other_idx]
                            if other_idx < len(self._review_mezzelf_flex) else None
                        )
                        dd.options = [
                            ft.DropdownOption(key=k, text=all_stat_labels.get(k, k))
                            for k in all_stat_keys if k != other_val
                        ]
                        try:
                            dd.update()
                        except RuntimeError:
                            pass

                for slot in range(2):
                    curr_key = self._review_mezzelf_flex[slot] if slot < len(self._review_mezzelf_flex) else all_stat_keys[slot]

                    def _make_flex_handler(slot_idx: int):
                        def _handler(e: Any):
                            while len(self._review_mezzelf_flex) <= slot_idx:
                                self._review_mezzelf_flex.append("")
                            self._review_mezzelf_flex[slot_idx] = e.control.value or ""
                            _refresh_mezzelf_flex_options()
                        return _handler

                    dd = ft.Dropdown(
                        label=f"+1 a (scelta {slot + 1})",
                        value=curr_key,
                        options=[ft.DropdownOption(key=k, text=all_stat_labels.get(k, k)) for k in all_stat_keys],
                        on_select=_make_flex_handler(slot),
                        bgcolor=design.T().surface,
                        color=design.T().text,
                        label_style=ft.TextStyle(color=design.T().text_3, size=12),
                        border_color=design.T().border,
                        focused_border_color=design.T().magic,
                        expand=True,
                        border_radius=design.field_style()['border_radius'], text_style=design.field_style()['text_style'])
                    flex_dd_refs.append(dd)
                    flex_dds.append(dd)
                race_extras_col.controls.append(ft.Row(flex_dds, spacing=12))
                _refresh_mezzelf_flex_options()

                # Mezzelf: 2 abilità a scelta (Versatilità nelle Abilità) —
                # esclude le abilità già concesse dal background e quelle già
                # scelte tramite le abilità di classe, per evitare doppia
                # competenza sulla stessa abilità (razza + classe).
                already_taken = set(self._bg_skill_proficiencies()) | set(self._review_skills)
                all_skills = [s for s in SKILLS.keys() if s not in already_taken]
                self._review_mezzelf_skills = [s for s in self._review_mezzelf_skills if s in all_skills]
                mez_skill_count = 2
                mez_label_row = ft.Row([
                    ft.Text(f"Scegli {mez_skill_count} abilità (tratto razziale)",
                            size=13, color=design.T().text, weight=ft.FontWeight.W_600),
                    ft.Container(expand=True),
                    ft.Text(f"({len(self._review_mezzelf_skills)}/{mez_skill_count})",
                            size=11, color=design.T().text_3),
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
                    # L'abilità appena scelta/deselezionata come tratto razziale
                    # non deve essere (più) selezionabile nel pool di abilità di
                    # classe, e viceversa — ricostruisce quella sezione per
                    # riflettere subito l'esclusione incrociata.
                    _rebuild_skills_col()
                    _rebuild_subclass_bonus_col()

                left_m: list[ft.Control] = []
                right_m: list[ft.Control] = []
                for i, sk in enumerate(all_skills):
                    cb = ft.Checkbox(
                        label=sk,
                        value=sk in self._review_mezzelf_skills,
                        fill_color=design.T().magic,
                        check_color=design.T().on_accent,
                        label_style=ft.TextStyle(size=12, color=design.T().text),
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
            if race == "Elfo" and subrace == "Elfo Alto":
                has_content = True
                mago_cantrips = _loader.get_mago_cantrips()
                if not self._review_elf_cantrip or self._review_elf_cantrip not in mago_cantrips:
                    self._review_elf_cantrip = mago_cantrips[0] if mago_cantrips else ""
                def _on_elf_cantrip_select(e):
                    self._review_elf_cantrip = e.control.value or ""
                    # Il trucchetto Alto Elfo (sempre dalla lista Mago) va
                    # escluso dal pool "Trucchetti Iniziali" di QUALUNQUE
                    # classe, non solo Mago — due liste di classi diverse
                    # possono condividere lo stesso nome di trucchetto (es.
                    # "Luce"). Va quindi sempre ricostruita, non solo quando
                    # la classe è Mago.
                    _rebuild_spells_init_col()
                    _update_extra_card()

                elf_cantrip_dd = CardPicker(
                    options=spell_card_options(_loader.get_spells_by_level("Mago", 0)),
                    value=self._review_elf_cantrip,
                    on_select=_on_elf_cantrip_select,
                )
                race_extras_col.controls.append(
                    muted_text("Trucchetto del Mago (tratto Elfo Alto)", size=11)
                )
                race_extras_col.controls.append(elf_cantrip_dd.control)
            else:
                if race != "Elfo":
                    self._review_elf_cantrip = ""

            # Umano: Standard vs Variante (regola opzionale PHB IT) —
            # umano.json → "variant_human_optional_rule". Se scelta,
            # sostituisce interamente il tratto standard "+1 a tutte le
            # caratteristiche" con: +1 a due caratteristiche a scelta, una
            # competenza in un'abilità a scelta, un talento a scelta (riusa
            # lo stesso pool feats.json/picker già usato per l'ASI del
            # level-up). Stessa implementazione di manual_form.py — nota:
            # la preview bonus/HP della fase Punteggi resta quella STANDARD
            # anche se qui si sceglie Variante, stessa limitazione già
            # accettata per il Mezzelfo.
            if race == "Umano":
                has_content = True
                _umano_raw = _loader.get_race("Umano") or {}
                variant_rule = _umano_raw.get("variant_human_optional_rule") or {}

                def _on_variant_radio_change(e: Any) -> None:
                    self._review_umano_variant = (e.control.value == "variant")
                    _rebuild_race_extras_col()

                race_extras_col.controls.append(ft.RadioGroup(
                    value="variant" if self._review_umano_variant else "standard",
                    on_change=_on_variant_radio_change,
                    content=ft.Column([
                        ft.Text("Tratti Umani", size=13, color=design.T().text,
                                weight=ft.FontWeight.W_600),
                        ft.Radio(value="standard",
                                 label="Standard — +1 a tutte le caratteristiche"),
                        ft.Radio(value="variant",
                                 label="Variante (regola opzionale) — +1 a due "
                                       "caratteristiche a scelta, un'abilità a "
                                       "scelta, un talento a scelta"),
                    ], spacing=2),
                ))

                if self._review_umano_variant and variant_rule:
                    # --- +1 a 2 caratteristiche a scelta (nessuna esclusa) ---
                    all_stat_keys_u = list(ABILITY_KEYS)
                    stat_labels_u = {k: ABILITY_SCORES[i] for i, k in enumerate(ABILITY_KEYS)}
                    if (len(self._review_umano_variant_stats) == 2
                            and self._review_umano_variant_stats[0] == self._review_umano_variant_stats[1]):
                        self._review_umano_variant_stats = self._review_umano_variant_stats[:1]
                    while len(self._review_umano_variant_stats) < 2:
                        for k in all_stat_keys_u:
                            if k not in self._review_umano_variant_stats:
                                self._review_umano_variant_stats.append(k)
                                break

                    race_extras_col.controls.append(
                        ft.Text("Variante Umana — assegna +1 a due caratteristiche diverse",
                                size=13, color=design.T().text, weight=ft.FontWeight.W_600)
                    )
                    uv_dds: list[ft.Control] = []
                    uv_dd_refs: list[ft.Dropdown] = []

                    def _refresh_umano_variant_stat_options() -> None:
                        for i, dd in enumerate(uv_dd_refs):
                            other_idx = 1 - i
                            other_val = (
                                self._review_umano_variant_stats[other_idx]
                                if other_idx < len(self._review_umano_variant_stats) else None
                            )
                            dd.options = [
                                ft.DropdownOption(key=k, text=stat_labels_u.get(k, k))
                                for k in all_stat_keys_u if k != other_val
                            ]
                            try:
                                dd.update()
                            except RuntimeError:
                                pass

                    for slot in range(2):
                        curr_key_u = (
                            self._review_umano_variant_stats[slot]
                            if slot < len(self._review_umano_variant_stats)
                            else all_stat_keys_u[slot]
                        )

                        def _make_uv_handler(slot_idx: int):
                            def _handler(e: Any) -> None:
                                while len(self._review_umano_variant_stats) <= slot_idx:
                                    self._review_umano_variant_stats.append("")
                                self._review_umano_variant_stats[slot_idx] = e.control.value or ""
                                _refresh_umano_variant_stat_options()
                            return _handler

                        dd_u = ft.Dropdown(
                            label=f"+1 a (scelta {slot + 1})",
                            value=curr_key_u,
                            options=[ft.DropdownOption(key=k, text=stat_labels_u.get(k, k))
                                     for k in all_stat_keys_u],
                            on_select=_make_uv_handler(slot),
                            bgcolor=design.T().surface, color=design.T().text,
                            label_style=ft.TextStyle(color=design.T().text_3, size=12),
                            border_color=design.T().border, focused_border_color=design.T().magic,
                            expand=True,
                            border_radius=design.field_style()['border_radius'], text_style=design.field_style()['text_style'])
                        uv_dd_refs.append(dd_u)
                        uv_dds.append(dd_u)
                    race_extras_col.controls.append(ft.Row(uv_dds, spacing=12))
                    _refresh_umano_variant_stat_options()

                    # --- 1 abilità a scelta ---
                    already_taken_u = set(self._bg_skill_proficiencies()) | set(self._review_skills)
                    uv_skill_opts = [s for s in SKILLS.keys() if s not in already_taken_u]
                    if (self._review_umano_variant_skill
                            and self._review_umano_variant_skill not in uv_skill_opts):
                        self._review_umano_variant_skill = ""
                    if not self._review_umano_variant_skill and uv_skill_opts:
                        self._review_umano_variant_skill = uv_skill_opts[0]

                    def _on_uv_skill_select(e: Any) -> None:
                        self._review_umano_variant_skill = e.control.value or ""
                        # La stessa abilità non deve poter essere scelta anche
                        # come abilità di classe — ricostruisce quella sezione.
                        _rebuild_skills_col()
                        _rebuild_subclass_bonus_col()

                    race_extras_col.controls.append(ft.Dropdown(
                        label="Abilità a scelta (Variante Umana)",
                        value=self._review_umano_variant_skill,
                        options=[ft.DropdownOption(key=s, text=s) for s in uv_skill_opts],
                        on_select=_on_uv_skill_select,
                        bgcolor=design.T().surface, color=design.T().text,
                        label_style=ft.TextStyle(color=design.T().text_3, size=12),
                        border_color=design.T().border, focused_border_color=design.T().magic,
                        expand=True,
                        border_radius=design.field_style()['border_radius'], text_style=design.field_style()['text_style']))

                    # --- 1 talento a scelta (stesso pool/picker dell'ASI level-up) ---
                    feat_names_u = _loader.get_feat_names()
                    if not self._review_umano_variant_feat or self._review_umano_variant_feat not in feat_names_u:
                        self._review_umano_variant_feat = feat_names_u[0] if feat_names_u else ""

                    def _on_uv_feat_bonus_select(e: Any) -> None:
                        # Il salvataggio legge la COPIA Python
                        # self._review_umano_variant_feat_bonus_stat, non il
                        # .value live del controllo — questo on_select deve
                        # tenere la copia sincronizzata con la selezione
                        # reale (stesso schema di manual_form.py).
                        self._review_umano_variant_feat_bonus_stat = e.control.value or ""

                    uv_feat_bonus_dd = ft.Dropdown(
                        label="Scegli la caratteristica da aumentare (+1)",
                        options=[], visible=False,
                        on_select=_on_uv_feat_bonus_select,
                        bgcolor=design.T().surface, color=design.T().text,
                        label_style=ft.TextStyle(color=design.T().text_3, size=12),
                        border_color=design.T().border, focused_border_color=design.T().magic,
                        expand=True,
                        border_radius=design.field_style()['border_radius'], text_style=design.field_style()['text_style'])

                    def _refresh_uv_feat_bonus_dd() -> None:
                        fd = _loader.get_feat(self._review_umano_variant_feat)
                        ab = fd.get("ability_bonus") if fd else None
                        if ab and ab.get("choose_one"):
                            opts_fb = ab.get("options", [])
                            uv_feat_bonus_dd.options = [
                                ft.DropdownOption(key=k, text=stat_labels_u.get(k, k))
                                for k in opts_fb
                            ]
                            if self._review_umano_variant_feat_bonus_stat not in opts_fb:
                                self._review_umano_variant_feat_bonus_stat = (
                                    opts_fb[0] if opts_fb else ""
                                )
                            uv_feat_bonus_dd.value = self._review_umano_variant_feat_bonus_stat
                            uv_feat_bonus_dd.visible = True
                        else:
                            self._review_umano_variant_feat_bonus_stat = ""
                            uv_feat_bonus_dd.visible = False
                        try:
                            uv_feat_bonus_dd.update()
                        except RuntimeError:
                            pass

                    def _on_uv_feat_select(e: Any) -> None:
                        self._review_umano_variant_feat = e.control.value or ""
                        # Il talento potrebbe concedere competenze a scelta
                        # diverse (proficiency_grants) — ricostruisce l'intera
                        # colonna extra razziali (non solo feat_bonus_dd), dato
                        # che il NUMERO di dropdown da mostrare dipende dal
                        # talento appena scelto.
                        self._review_umano_variant_feat_prof_values = []
                        _rebuild_race_extras_col()
                        try:
                            race_extras_col.update()
                        except RuntimeError:
                            pass

                    uv_feat_dd = CardPicker(
                        options=feat_card_options(_loader, feat_names_u),
                        value=self._review_umano_variant_feat,
                        on_select=_on_uv_feat_select,
                    )
                    race_extras_col.controls.append(muted_text("Talento a scelta (Variante Umana)", size=11))
                    race_extras_col.controls.append(uv_feat_dd.control)
                    race_extras_col.controls.append(uv_feat_bonus_dd)
                    _refresh_uv_feat_bonus_dd()

                    # --- Competenze concesse dal talento (proficiency_grants) ---
                    uv_feat_prof_dds: list[ft.Dropdown] = []
                    uv_feat_prof_col = ft.Column([], spacing=6)
                    uv_feat_prof_fixed_text = ft.Text("", size=12, color=design.T().text_2)

                    def _uv_feat_prof_excluded_skills() -> set:
                        return (
                            set(self._bg_skill_proficiencies())
                            | set(self._review_skills)
                            | set(self._review_mezzelf_skills)
                            | ({self._review_umano_variant_skill} if self._review_umano_variant_skill else set())
                        )

                    def _uv_feat_prof_excluded_languages() -> set:
                        fixed = {
                            v for v in _loader.get_resolved_race(
                                self._review_race, self._review_subrace
                            ).get("languages", []) if isinstance(v, str)
                        }
                        return fixed | set(self._review_race_languages) | set(self._review_languages)

                    def _uv_feat_prof_pool(ptype: str) -> list[str]:
                        pool_full = character_repo.resolve_feat_proficiency_choice_pool(ptype)
                        if ptype == "skill_or_tool":
                            excl_skills = _uv_feat_prof_excluded_skills()
                            return [v for v in pool_full if not (v in SKILLS and v in excl_skills)]
                        if ptype == "skill":
                            excl = _uv_feat_prof_excluded_skills()
                            return [v for v in pool_full if v not in excl]
                        if ptype == "language":
                            excl = _uv_feat_prof_excluded_languages()
                            return [v for v in pool_full if v not in excl]
                        return pool_full

                    def _refresh_uv_feat_prof_options() -> None:
                        chosen_now = {dd.value for dd in uv_feat_prof_dds if dd.value}
                        for dd in uv_feat_prof_dds:
                            pool = getattr(dd, "_prof_pool", [])
                            others_chosen = chosen_now - ({dd.value} if dd.value else set())
                            dd.options = [ft.DropdownOption(key=v, text=v) for v in pool if v not in others_chosen]
                        for dd in uv_feat_prof_dds:
                            try:
                                dd.update()
                            except RuntimeError:
                                pass

                    def _on_uv_feat_prof_select(e: Any) -> None:
                        self._review_umano_variant_feat_prof_values = [
                            dd.value or "" for dd in uv_feat_prof_dds
                        ]
                        _refresh_uv_feat_prof_options()

                    _uv_fp_labels = {
                        "skill": "Abilità", "tool": "Strumento", "weapon": "Arma",
                        "language": "Lingua", "skill_or_tool": "Abilità o Strumento",
                    }
                    _uv_fd_grants = (_loader.get_feat(self._review_umano_variant_feat) or {}).get(
                        "proficiency_grants", []
                    ) or []
                    _uv_fixed_labels: list[str] = []
                    _uv_prev_values = list(self._review_umano_variant_feat_prof_values)
                    _uv_val_idx = 0
                    for _grant in _uv_fd_grants:
                        if _grant.get("type") == "fixed":
                            _uv_fixed_labels.append(_grant.get("name", ""))
                            continue
                        if _grant.get("type") != "choice":
                            continue
                        _ptype = _grant.get("proficiency_type", "")
                        _count = int(_grant.get("count", 0) or 0)
                        _pool = _uv_feat_prof_pool(_ptype)
                        _label = _uv_fp_labels.get(_ptype, "Competenza")
                        for _i in range(_count):
                            _preset = _uv_prev_values[_uv_val_idx] if _uv_val_idx < len(_uv_prev_values) else ""
                            _uv_val_idx += 1
                            if _preset not in _pool:
                                _preset = ""
                            dd_fp = ft.Dropdown(
                                label=f"{_label} {_i + 1}/{_count}",
                                value=_preset or None,
                                options=[ft.DropdownOption(key=v, text=v) for v in _pool],
                                on_select=_on_uv_feat_prof_select,
                                bgcolor=design.T().surface, color=design.T().text,
                                label_style=ft.TextStyle(color=design.T().text_3, size=12),
                                border_color=design.T().border, focused_border_color=design.T().magic,
                                expand=True,
                                border_radius=design.field_style()['border_radius'], text_style=design.field_style()['text_style'])
                            setattr(dd_fp, "_prof_pool", _pool)
                            uv_feat_prof_dds.append(dd_fp)
                            uv_feat_prof_col.controls.append(dd_fp)
                    self._review_umano_variant_feat_prof_values = [dd.value or "" for dd in uv_feat_prof_dds]
                    if uv_feat_prof_dds:
                        _refresh_uv_feat_prof_options()
                    if _uv_fixed_labels:
                        uv_feat_prof_fixed_text.value = "Competenza automatica: " + ", ".join(_uv_fixed_labels)
                        race_extras_col.controls.append(uv_feat_prof_fixed_text)
                    if uv_feat_prof_dds:
                        race_extras_col.controls.append(uv_feat_prof_col)
                elif not self._review_umano_variant:
                    self._review_umano_variant_stats = []
                    self._review_umano_variant_skill = ""
                    self._review_umano_variant_feat = ""
                    self._review_umano_variant_feat_bonus_stat = ""
                    self._review_umano_variant_feat_prof_values = []
            else:
                self._review_umano_variant = False
                self._review_umano_variant_stats = []
                self._review_umano_variant_skill = ""
                self._review_umano_variant_feat = ""
                self._review_umano_variant_feat_bonus_stat = ""
                self._review_umano_variant_feat_prof_values = []

            # --- Lingua/e aggiuntive a scelta libera concesse dalla razza
            # (Umano: 1; Mezzelfo: 1, "terza lingua" oltre a Comune+Elfico) ---
            race_lang_count = self._race_language_choice_count()
            if race_lang_count > 0:
                has_content = True
                # Esclude non solo "Comune" ma TUTTE le lingue fisse della
                # razza (es. Mezzelfo ha anche "Elfico" fisso) — altrimenti
                # il dropdown offrirebbe come "scelta libera" una lingua che
                # il personaggio conosce già di base, sprecando lo slot.
                _fixed_race_langs = {
                    l for l in _loader.get_resolved_race(race, subrace).get("languages", [])
                    if isinstance(l, str)
                }
                avail_all = [l for l in LANGUAGES if l not in _fixed_race_langs]
                while len(self._review_race_languages) < race_lang_count:
                    self._review_race_languages.append("")
                del self._review_race_languages[race_lang_count:]

                def _on_race_lang_select(idx: int, val: str) -> None:
                    self._review_race_languages[idx] = val
                    _rebuild_race_extras_col()
                    _rebuild_lang_tool_col()

                for i in range(race_lang_count):
                    taken_by_others = {
                        l for j, l in enumerate(self._review_race_languages)
                        if j != i and l
                    }
                    opts = [l for l in avail_all if l not in taken_by_others]
                    curr = self._review_race_languages[i]
                    if curr not in opts:
                        curr = opts[0] if opts else ""
                        self._review_race_languages[i] = curr
                    label = (
                        "Lingua aggiuntiva (tratto razziale)"
                        if race_lang_count == 1
                        else f"Lingua aggiuntiva {i + 1} (tratto razziale)"
                    )
                    race_extras_col.controls.append(ft.Dropdown(
                        label=label,
                        value=curr,
                        options=[ft.DropdownOption(key=l, text=l) for l in opts],
                        on_select=lambda e, idx=i: _on_race_lang_select(idx, e.control.value or ""),
                        bgcolor=design.T().surface,
                        color=design.T().text,
                        label_style=ft.TextStyle(color=design.T().text_3, size=12),
                        border_color=design.T().border,
                        focused_border_color=design.T().magic,
                        expand=True,
                        border_radius=design.field_style()['border_radius'], text_style=design.field_style()['text_style']))
            else:
                self._review_race_languages = []

            race_extras_col.visible = has_content
            try:
                race_extras_col.update()
            except RuntimeError:
                pass

        _rebuild_race_extras_col()

        # ------ Maestria Ladro Lv1 (dinamica) ------
        expertise_col = ft.Column([], spacing=6, visible=False)
        expertise_checks: dict[str, ft.Checkbox] = {}

        def _rebuild_expertise_col():
            expertise_col.controls.clear()
            expertise_checks.clear()
            if self._review_class.lower() != "ladro":
                self._review_expertise = []
                expertise_col.visible = False
                try:
                    expertise_col.update()
                except RuntimeError:
                    pass
                return
            # Pool = background skills + abilità di classe già scelte
            bg_skills = self._bg_skill_proficiencies()
            pool = list(dict.fromkeys(bg_skills + self._review_skills))  # dedup, preserva ordine
            if not pool:
                expertise_col.visible = False
                try:
                    expertise_col.update()
                except RuntimeError:
                    pass
                return
            # Filtra selezioni non più valide
            self._review_expertise = [s for s in self._review_expertise if s in pool]

            exp_label_row = ft.Row([
                ft.Text("Scegli 2 abilità per la Maestria (Lv.1)",
                        size=13, color=design.T().text, weight=ft.FontWeight.W_600),
                ft.Container(expand=True),
                ft.Text(f"({len(self._review_expertise)}/2 selezionate)",
                        size=11, color=design.T().text_3),
            ])
            expertise_col.controls.append(exp_label_row)
            exp_counter = cast(ft.Text, exp_label_row.controls[2])

            def _on_expertise_toggle(skill: str, val: bool):
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
                    label=skill,
                    value=skill in self._review_expertise,
                    fill_color=design.T().magic,
                    check_color=design.T().on_accent,
                    label_style=ft.TextStyle(size=12, color=design.T().text),
                    on_change=lambda e, s=skill: _on_expertise_toggle(s, bool(e.control.value)),
                )
                expertise_checks[skill] = cb
                if i % 2 == 0:
                    left_exp.append(cb)
                else:
                    right_exp.append(cb)

            expertise_col.controls.append(ft.Row(
                [ft.Column(left_exp, spacing=4, expand=True),
                 ft.Column(right_exp, spacing=4, expand=True)],
                spacing=8,
            ))
            expertise_col.controls.append(
                muted_text("La Maestria raddoppia il bonus di competenza per le abilità scelte.", size=11)
            )
            expertise_col.visible = True
            try:
                expertise_col.update()
            except RuntimeError:
                pass

        _rebuild_expertise_col()

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

            label_row = ft.Row([
                ft.Text(f"Scegli {count} abilità dalla lista", size=13,
                        color=design.T().text, weight=ft.FontWeight.W_600),
                ft.Container(expand=True),
                ft.Text(f"({len(self._review_skills)}/{count} selezionate)",
                        size=11, color=design.T().text_3),
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
                # Aggiorna il pool di Maestria se siamo Ladro
                _rebuild_expertise_col()
                # Esclusione reciproca con l'abilità razziale Mezzelf (Versatilità
                # nelle Abilità) — l'abilità appena scelta qui non deve essere
                # (più) selezionabile anche come tratto razziale, e viceversa.
                _rebuild_race_extras_col()
                # Idem con le competenze bonus di sottoclasse a scelta
                # (es. Dominio della Natura/Conoscenza).
                _rebuild_subclass_bonus_col()

            # Checkbox in griglia 2 colonne
            left_col: list[ft.Control] = []
            right_col: list[ft.Control] = []
            for i, skill in enumerate(opts):
                cb = ft.Checkbox(
                    label=skill,
                    value=skill in self._review_skills,
                    fill_color=design.T().primary_fill,
                    check_color=design.T().on_primary_fill,
                    label_style=ft.TextStyle(size=12, color=design.T().text),
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
            lang_count, _lang_from = self._bg_language_choices()
            if lang_count > 0:
                has_content = True
                # Esclude le lingue già conosciute di base — fisse di razza
                # (get_resolved_race, es. "Elfico" per l'Elfo, "Comune" per
                # qualunque razza) e l'eventuale lingua extra già scelta dal
                # tratto Umano — così la scelta "N lingue a scelta" del
                # background non permette di selezionare una lingua che il
                # personaggio conosce già comunque.
                already_known: set[str] = set()
                if self._review_race:
                    resolved_race = _loader.get_resolved_race(self._review_race, self._review_subrace)
                    already_known |= {l for l in resolved_race.get("languages", []) if isinstance(l, str)}
                already_known |= {l for l in self._review_race_languages if l}
                avail_langs = [l for l in LANGUAGES if l not in already_known]
                # Mantieni selezioni valide
                self._review_languages = [l for l in self._review_languages if l in avail_langs]
                lang_label = ft.Row([
                    ft.Text(f"Scegli {lang_count} {'lingue' if lang_count > 1 else 'lingua'}",
                            size=13, color=design.T().text, weight=ft.FontWeight.W_600),
                    ft.Container(expand=True),
                    ft.Text(f"({len(self._review_languages)}/{lang_count})",
                            size=11, color=design.T().text_3),
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
                        fill_color=design.T().magic,
                        check_color=design.T().on_accent,
                        label_style=ft.TextStyle(size=12, color=design.T().text),
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
            for tc_idx, (_tc_count, tc_opts) in enumerate(tool_choices):
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
                    bgcolor=design.T().surface,
                    color=design.T().text,
                    label_style=ft.TextStyle(color=design.T().text_3, size=12),
                    border_color=design.T().border,
                    focused_border_color=design.T().magic,
                    expand=True,
                    border_radius=design.field_style()['border_radius'], text_style=design.field_style()['text_style'])
                lang_tool_col.controls.append(tool_dd)

            # Strumenti a scelta di CLASSE (Bardo/Monaco) — a differenza
            # degli strumenti di background (sempre un solo dropdown per
            # scelta), una singola entry può richiedere N strumenti dalla
            # stessa categoria (Bardo: 3 musicali), quindi servono N
            # dropdown con esclusione reciproca — stesso schema già usato
            # per i trucchetti Lv.1 più sotto e in manual_form.py.
            class_tool_dd_groups: list[list[ft.Dropdown]] = []

            def _refresh_class_tool_group(group_idx: int, offset: int, pool: list[str]) -> None:
                dds = class_tool_dd_groups[group_idx]
                for i, dd in enumerate(dds):
                    slot = offset + i
                    others = {
                        t for j, t in enumerate(self._review_class_tools)
                        if j != slot and offset <= j < offset + len(dds) and t
                    }
                    available = [t for t in pool if t not in others]
                    dd.options = [ft.DropdownOption(key=t, text=t) for t in available]
                    current = self._review_class_tools[slot] if slot < len(self._review_class_tools) else ""
                    if current not in available:
                        current = available[0] if available else ""
                        while len(self._review_class_tools) <= slot:
                            self._review_class_tools.append("")
                        self._review_class_tools[slot] = current
                    dd.value = current or None
                    try:
                        dd.update()
                    except RuntimeError:
                        pass

            def _set_class_tool(slot: int, val: str, group_idx: int, offset: int, pool: list[str]) -> None:
                while len(self._review_class_tools) <= slot:
                    self._review_class_tools.append("")
                self._review_class_tools[slot] = val
                _refresh_class_tool_group(group_idx, offset, pool)

            _ct_offset = 0
            for cc_count, cc_opts in self._class_tool_choices():
                if not cc_opts:
                    continue
                has_content = True
                lang_tool_col.controls.append(
                    ft.Text(f"Scegli {cc_count} strument{'o' if cc_count == 1 else 'i'} di classe",
                            size=13, color=design.T().text, weight=ft.FontWeight.W_600)
                )
                group_idx = len(class_tool_dd_groups)
                dds: list[ft.Dropdown] = []
                for i in range(cc_count):
                    slot = _ct_offset + i
                    current = self._review_class_tools[slot] if slot < len(self._review_class_tools) else ""
                    dd = ft.Dropdown(
                        label=f"Strumento di classe {i + 1}" if cc_count > 1 else "Strumento di classe a scelta",
                        value=current if current in cc_opts else (cc_opts[0] if cc_opts else None),
                        options=[ft.DropdownOption(key=t, text=t) for t in cc_opts],
                        on_select=lambda e, s=slot, gi=group_idx, off=_ct_offset, pl=cc_opts:
                            _set_class_tool(s, e.control.value or "", gi, off, pl),
                        bgcolor=design.T().surface, color=design.T().text,
                        label_style=ft.TextStyle(color=design.T().text_3, size=12),
                        border_color=design.T().border, focused_border_color=design.T().magic,
                        expand=True,
                        border_radius=design.field_style()['border_radius'], text_style=design.field_style()['text_style'])
                    dds.append(dd)
                    lang_tool_col.controls.append(dd)
                class_tool_dd_groups.append(dds)
                _refresh_class_tool_group(group_idx, _ct_offset, cc_opts)
                _ct_offset += cc_count

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

        # ------ Trucchetti e incantesimi conosciuti al Lv.1 ------
        # Stesso meccanismo di manual_form.py: numero fisso per classe da
        # GameDataLoader (dato trascritto/derivato dal testo delle feature
        # "Incantesimi"/"Trucchetti" nei JSON classe). Trucchetti: tutte le
        # classi incantatrici con cantrips_known_at_1 > 0. Incantesimi
        # conosciuti di 1° livello: solo le classi "know" (Bardo/Stregone/
        # Warlock) — i "preparatori" (Chierico/Druido/Paladino) scelgono ogni
        # giorno dal pool completo, il Mago parte con un libro degli
        # incantesimi (meccanica separata, non affrontata qui).
        spells_init_col = ft.Column([], spacing=10, visible=False)
        cantrip_dds: list[CardPicker] = []
        spell_dds: list[CardPicker] = []
        prepared_dds: list[CardPicker] = []
        spellbook_dds: list[CardPicker] = []

        def _rebuild_spells_init_col():
            spells_init_col.controls.clear()
            cantrip_dds.clear()
            spell_dds.clear()
            prepared_dds.clear()
            spellbook_dds.clear()

            n_cantrips  = _loader.get_cantrips_known_at_1(self._review_class)
            n_spells    = _loader.get_spells_known_at_1(self._review_class)
            n_prepared  = self._compute_prepared_spell_count()
            n_spellbook = _loader.get_spellbook_starting_spells(self._review_class)

            if n_cantrips <= 0 and n_spells <= 0 and n_prepared <= 0 and n_spellbook <= 0:
                self._review_cantrips         = []
                self._review_spells_lv1       = []
                self._review_prepared_spells  = []
                self._review_spellbook_spells = []
                spells_init_col.visible = False
                try:
                    spells_init_col.update()
                except RuntimeError:
                    pass
                return

            cantrip_names = sorted(s["name"] for s in _loader.get_spells_by_level(self._review_class, 0))
            # Lista Incantesimi Ampliata (Warlock) — i
            # nomi patrono-specifici di 1° livello (es. Il Signore Fatato →
            # Luminescenza/Sonno) vanno aggiunti al pool tra cui scegliere i
            # 2 incantesimi conosciuti iniziali, MAI concessi gratis: il
            # giocatore deve comunque "spenderci" una delle scelte iniziali,
            # come per un incantesimo della lista base. No-op per qualunque
            # altra classe (get_expanded_spells ritorna sempre []).
            _spell_lv1_base = _loader.get_spells_by_level(self._review_class, 1)
            _spell_lv1_expanded = [
                s for s in _loader.get_expanded_spells(self._review_class, self._review_subclass)
                if s.get("level") == 1
            ]
            _spell_lv1_pool = _spell_lv1_base + [
                s for s in _spell_lv1_expanded
                if s.get("name") not in {b.get("name") for b in _spell_lv1_base}
            ]
            spell_names   = sorted(s["name"] for s in _spell_lv1_pool)

            # Il trucchetto scelto come tratto razziale (Alto Elfo, sempre
            # dalla lista Mago) va escluso dal pool di classe A PRESCINDERE
            # dalla classe del personaggio — non solo quando è Mago: due
            # liste di classi diverse possono condividere lo stesso nome di
            # trucchetto (es. "Luce"), e sceglierlo sia come tratto
            # razziale sia come trucchetto di classe farebbe "sprecare" una
            # scelta su un trucchetto già posseduto.
            elf_reserved = {self._review_elf_cantrip} if self._review_elf_cantrip else set()
            cantrip_pool = [c for c in cantrip_names if c not in elf_reserved]
            # Lookup nome->dict per costruire le opzioni CardPicker (con
            # descrizione completa) a partire dai soli nomi già filtrati sopra.
            _cantrip_by_name = {s["name"]: s for s in _loader.get_spells_by_level(self._review_class, 0)}
            _spell_lv1_by_name = {s["name"]: s for s in _spell_lv1_pool}

            self._review_cantrips = [c for c in self._review_cantrips if c in cantrip_pool][:n_cantrips]
            while len(self._review_cantrips) < n_cantrips and len(self._review_cantrips) < len(cantrip_pool):
                for c in cantrip_pool:
                    if c not in self._review_cantrips:
                        self._review_cantrips.append(c)
                        break

            self._review_spells_lv1 = [s for s in self._review_spells_lv1 if s in spell_names][:n_spells]
            while len(self._review_spells_lv1) < n_spells and len(self._review_spells_lv1) < len(spell_names):
                for s in spell_names:
                    if s not in self._review_spells_lv1:
                        self._review_spells_lv1.append(s)
                        break

            # Incantesimi preparati iniziali (Chierico/Druido/Paladino) —
            # stesso pool di primo livello di `spell_names`,
            # nessuna esclusione incrociata necessaria: una classe non è mai
            # contemporaneamente "know" (n_spells>0) e "preparatrice"
            # (n_prepared>0), quindi le due liste non competono mai per lo
            # stesso personaggio.
            self._review_prepared_spells = [
                s for s in self._review_prepared_spells if s in spell_names
            ][:n_prepared]
            while len(self._review_prepared_spells) < n_prepared and len(self._review_prepared_spells) < len(spell_names):
                for s in spell_names:
                    if s not in self._review_prepared_spells:
                        self._review_prepared_spells.append(s)
                        break

            # Libro degli Incantesimi del Mago — stesso pool
            # `spell_names`; nessuna esclusione incrociata necessaria per lo
            # stesso motivo di `_review_prepared_spells` sopra (il Mago non
            # è mai anche "know" né "preparatore" nel senso di
            # _PREPARED_CASTER_CLASSES).
            self._review_spellbook_spells = [
                s for s in self._review_spellbook_spells if s in spell_names
            ][:n_spellbook]
            while len(self._review_spellbook_spells) < n_spellbook and len(self._review_spellbook_spells) < len(spell_names):
                for s in spell_names:
                    if s not in self._review_spellbook_spells:
                        self._review_spellbook_spells.append(s)
                        break

            # I dropdown trucchetti (e, separatamente, i dropdown incantesimi
            # di 1° livello) non devono mai permettere di scegliere lo stesso
            # nome due volte. Le `options` di ogni dropdown escludono quindi
            # dinamicamente i valori già scelti negli ALTRI dropdown dello
            # stesso gruppo (mai il proprio valore corrente), ricalcolate a
            # ogni selezione — non è quindi una validazione a posteriori ma
            # un'esclusione preventiva: il duplicato non appare mai come
            # opzione selezionabile.
            def _refresh_cantrip_options():
                for i, dd in enumerate(cantrip_dds):
                    others = {c for j, c in enumerate(self._review_cantrips) if j != i and c}
                    available = [c for c in cantrip_pool if c not in others]
                    dd.options = spell_card_options(
                        [_cantrip_by_name[c] for c in available if c in _cantrip_by_name]
                    )
                    current = self._review_cantrips[i] if i < len(self._review_cantrips) else ""
                    if current not in available:
                        current = available[0] if available else ""
                        while len(self._review_cantrips) <= i:
                            self._review_cantrips.append("")
                        self._review_cantrips[i] = current
                    dd.value = current or None
                    try:
                        dd.update()
                    except RuntimeError:
                        pass

            def _refresh_spell_options():
                for i, dd in enumerate(spell_dds):
                    others = {s for j, s in enumerate(self._review_spells_lv1) if j != i and s}
                    available = [s for s in spell_names if s not in others]
                    dd.options = spell_card_options(
                        [_spell_lv1_by_name[s] for s in available if s in _spell_lv1_by_name]
                    )
                    current = self._review_spells_lv1[i] if i < len(self._review_spells_lv1) else ""
                    if current not in available:
                        current = available[0] if available else ""
                        while len(self._review_spells_lv1) <= i:
                            self._review_spells_lv1.append("")
                        self._review_spells_lv1[i] = current
                    dd.value = current or None
                    try:
                        dd.update()
                    except RuntimeError:
                        pass

            def _set_cantrip(idx: int, val: str):
                while len(self._review_cantrips) <= idx:
                    self._review_cantrips.append("")
                self._review_cantrips[idx] = val
                _refresh_cantrip_options()

            def _set_spell(idx: int, val: str):
                while len(self._review_spells_lv1) <= idx:
                    self._review_spells_lv1.append("")
                self._review_spells_lv1[idx] = val
                _refresh_spell_options()

            def _refresh_prepared_options():
                for i, dd in enumerate(prepared_dds):
                    others = {s for j, s in enumerate(self._review_prepared_spells) if j != i and s}
                    available = [s for s in spell_names if s not in others]
                    dd.options = spell_card_options(
                        [_spell_lv1_by_name[s] for s in available if s in _spell_lv1_by_name]
                    )
                    current = self._review_prepared_spells[i] if i < len(self._review_prepared_spells) else ""
                    if current not in available:
                        current = available[0] if available else ""
                        while len(self._review_prepared_spells) <= i:
                            self._review_prepared_spells.append("")
                        self._review_prepared_spells[i] = current
                    dd.value = current or None
                    try:
                        dd.update()
                    except RuntimeError:
                        pass

            def _set_prepared(idx: int, val: str):
                while len(self._review_prepared_spells) <= idx:
                    self._review_prepared_spells.append("")
                self._review_prepared_spells[idx] = val
                _refresh_prepared_options()

            def _refresh_spellbook_options():
                for i, dd in enumerate(spellbook_dds):
                    others = {s for j, s in enumerate(self._review_spellbook_spells) if j != i and s}
                    available = [s for s in spell_names if s not in others]
                    dd.options = spell_card_options(
                        [_spell_lv1_by_name[s] for s in available if s in _spell_lv1_by_name]
                    )
                    current = self._review_spellbook_spells[i] if i < len(self._review_spellbook_spells) else ""
                    if current not in available:
                        current = available[0] if available else ""
                        while len(self._review_spellbook_spells) <= i:
                            self._review_spellbook_spells.append("")
                        self._review_spellbook_spells[i] = current
                    dd.value = current or None
                    try:
                        dd.update()
                    except RuntimeError:
                        pass

            def _set_spellbook(idx: int, val: str):
                while len(self._review_spellbook_spells) <= idx:
                    self._review_spellbook_spells.append("")
                self._review_spellbook_spells[idx] = val
                _refresh_spellbook_options()

            if n_cantrips > 0 and cantrip_pool:
                spells_init_col.controls.append(
                    ft.Text(f"Trucchetti conosciuti (scegli {n_cantrips})",
                            size=13, color=design.T().text, weight=ft.FontWeight.W_600)
                )
                for i in range(n_cantrips):
                    current = self._review_cantrips[i] if i < len(self._review_cantrips) else ""
                    dd = CardPicker(
                        options=spell_card_options(
                            [_cantrip_by_name[c] for c in cantrip_pool if c in _cantrip_by_name]
                        ),
                        value=current if current in cantrip_pool else (cantrip_pool[0] if cantrip_pool else None),
                        on_select=lambda e, idx=i: _set_cantrip(idx, e.control.value or ""),
                    )
                    cantrip_dds.append(dd)
                    spells_init_col.controls.append(muted_text(f"Trucchetto {i + 1}", size=11))
                    spells_init_col.controls.append(dd.control)
                _refresh_cantrip_options()

            if n_spells > 0 and spell_names:
                spells_init_col.controls.append(ft.Container(height=4))
                spells_init_col.controls.append(
                    ft.Text(f"Incantesimi di 1° livello conosciuti (scegli {n_spells})",
                            size=13, color=design.T().text, weight=ft.FontWeight.W_600)
                )
                for i in range(n_spells):
                    current = self._review_spells_lv1[i] if i < len(self._review_spells_lv1) else ""
                    dd = CardPicker(
                        options=spell_card_options(
                            [_spell_lv1_by_name[s] for s in spell_names if s in _spell_lv1_by_name]
                        ),
                        value=current if current in spell_names else (spell_names[0] if spell_names else None),
                        on_select=lambda e, idx=i: _set_spell(idx, e.control.value or ""),
                    )
                    spell_dds.append(dd)
                    spells_init_col.controls.append(muted_text(f"Incantesimo {i + 1}", size=11))
                    spells_init_col.controls.append(dd.control)
                _refresh_spell_options()

            if n_prepared > 0 and spell_names:
                spells_init_col.controls.append(ft.Container(height=4))
                spells_init_col.controls.append(
                    ft.Text(f"Incantesimi preparati iniziali (scegli {n_prepared})",
                            size=13, color=design.T().text, weight=ft.FontWeight.W_600)
                )
                spells_init_col.controls.append(
                    muted_text(
                        "Mod. caratteristica da incantatore + livello (min 1) — PHB. "
                        "Potrai prepararne di diversi dopo ogni riposo lungo.",
                        size=11,
                    )
                )
                for i in range(n_prepared):
                    current = self._review_prepared_spells[i] if i < len(self._review_prepared_spells) else ""
                    dd = CardPicker(
                        options=spell_card_options(
                            [_spell_lv1_by_name[s] for s in spell_names if s in _spell_lv1_by_name]
                        ),
                        value=current if current in spell_names else (spell_names[0] if spell_names else None),
                        on_select=lambda e, idx=i: _set_prepared(idx, e.control.value or ""),
                    )
                    prepared_dds.append(dd)
                    spells_init_col.controls.append(muted_text(f"Incantesimo preparato {i + 1}", size=11))
                    spells_init_col.controls.append(dd.control)
                _refresh_prepared_options()

            if n_spellbook > 0 and spell_names:
                spells_init_col.controls.append(ft.Container(height=4))
                spells_init_col.controls.append(
                    ft.Text(f"Libro degli Incantesimi (scegli {n_spellbook})",
                            size=13, color=design.T().text, weight=ft.FontWeight.W_600)
                )
                spells_init_col.controls.append(
                    muted_text(
                        "Il libro inizia con 6 incantesimi di 1° livello (PHB). "
                        "Verranno preparati automaticamente quelli che il tuo "
                        "modificatore ti permette; gli altri restano nel libro, "
                        "pronti da preparare dopo un riposo lungo.",
                        size=11,
                    )
                )
                for i in range(n_spellbook):
                    current = self._review_spellbook_spells[i] if i < len(self._review_spellbook_spells) else ""
                    dd = CardPicker(
                        options=spell_card_options(
                            [_spell_lv1_by_name[s] for s in spell_names if s in _spell_lv1_by_name]
                        ),
                        value=current if current in spell_names else (spell_names[0] if spell_names else None),
                        on_select=lambda e, idx=i: _set_spellbook(idx, e.control.value or ""),
                    )
                    spellbook_dds.append(dd)
                    spells_init_col.controls.append(muted_text(f"Incantesimo del libro {i + 1}", size=11))
                    spells_init_col.controls.append(dd.control)
                _refresh_spellbook_options()

            spells_init_col.visible = True
            try:
                spells_init_col.update()
            except RuntimeError:
                pass

        _rebuild_spells_init_col()

        # ------ Handler dropdown principali ------

        def _on_class_change(e):
            self._review_class = e.control.value
            self._review_stats = self.engine.get_suggested_stat_assignment(self._review_class)
            self._review_skills = []
            self._review_subclass = ""
            self._review_subclass_bonus_choices = []
            self._review_dragon_ancestry = ""
            self._review_fighting_style = ""
            self._review_expertise = []
            self._review_cantrips = []
            self._review_spells_lv1 = []
            self._review_prepared_spells = []
            self._review_spellbook_spells = []
            self._review_class_tools = []
            for key, dd_ctrl in stat_dropdowns.items():
                dd_ctrl.value = str(self._review_stats.get(key, 10))
                dd_ctrl.update()
            _on_stat_change("", 0)
            hp_note_text.value = _hit_die_note()
            hp_note_text.update()
            _rebuild_subclass_col()
            _rebuild_subclass_bonus_col()
            _rebuild_dragon_col()
            _rebuild_fighting_style_col()
            _rebuild_skills_col()
            _rebuild_expertise_col()
            _rebuild_spells_init_col()
            # _class_tool_choices() dipende da self._review_class (non solo
            # da self._review_bg, come le lingue/strumenti di background) —
            # senza questa chiamata, cambiare classe non aggiornerebbe mai i
            # dropdown strumento di classe.
            _rebuild_lang_tool_col()
            _update_extra_card()

        def _on_race_change(e):
            self._review_race = e.control.value or ""
            self._review_subrace = ""
            self._review_mezzelf_flex = []
            self._review_mezzelf_skills = []
            self._review_elf_cantrip = ""
            self._review_race_languages = []
            self._review_umano_variant = False
            self._review_umano_variant_stats = []
            self._review_umano_variant_skill = ""
            self._review_umano_variant_feat = ""
            self._review_umano_variant_feat_bonus_stat = ""
            self._review_umano_variant_feat_prof_values = []
            _rebuild_subrace_col()
            _rebuild_race_extras_col()
            _rebuild_spells_init_col()
            _rebuild_lang_tool_col()
            _update_extra_card()

        def _on_bg_change(e):
            self._review_bg = e.control.value or ""
            self._review_skills = []
            self._review_languages = []
            self._review_tools = []
            self._review_expertise = []
            _rebuild_skills_col()
            _rebuild_expertise_col()
            _rebuild_lang_tool_col()
            _update_extra_card()

        # ------ Layout finale (dinamico: extra_card aggiornata via _update_extra_card) ------

        # Section headers come widget per poterne aggiornare la visibilità
        sec_razza_classe  = ft.Container(content=section_header("Razza e Classe"),  visible=False)
        sec_extra_razziali = ft.Container(content=section_header("Extra Razziali"),  visible=False)
        sec_abilita       = ft.Container(content=section_header("Abilità di Classe"), visible=False)
        sec_perizia       = ft.Container(content=section_header("Maestria (Ladro Lv.1)"), visible=False)
        sec_incantesimi   = ft.Container(content=section_header("Trucchetti e Incantesimi Iniziali"), visible=False)
        sec_lang_tool     = ft.Container(content=section_header("Lingue e Strumenti"), visible=False)

        extra_card_content = ft.Column([
            sec_razza_classe,
            subrace_col,
            subclass_col,
            subclass_bonus_col,
            dragon_col,
            fighting_style_col,
            sec_extra_razziali,
            race_extras_col,
            sec_abilita,
            skills_col,
            sec_perizia,
            expertise_col,
            sec_incantesimi,
            spells_init_col,
            sec_lang_tool,
            lang_tool_col,
        ], spacing=12)

        extra_card = design.card(extra_card_content, accent=design.T().primary, padding=20)
        extra_card.visible = False

        def _update_extra_card():
            has_rc = (
                subrace_col.visible or subclass_col.visible or subclass_bonus_col.visible
                or dragon_col.visible or fighting_style_col.visible
            )
            sec_razza_classe.visible   = has_rc
            sec_extra_razziali.visible = race_extras_col.visible
            sec_abilita.visible        = skills_col.visible
            sec_perizia.visible        = expertise_col.visible
            sec_incantesimi.visible    = spells_init_col.visible
            sec_lang_tool.visible      = lang_tool_col.visible
            extra_card.visible = (
                has_rc or race_extras_col.visible or skills_col.visible
                or expertise_col.visible or spells_init_col.visible or lang_tool_col.visible
            )
            try:
                extra_card.update()
            except RuntimeError:
                pass

        _update_extra_card()

        content_sections: list[ft.Control] = [
            design.hero_title(
                "Personalizza il tuo personaggio",
                "Puoi modificare i suggerimenti del wizard.",
            ),
            ft.Container(height=20),
            design.section("Identità", ft.Column([
                class_dd,
                race_dd,
                bg_dd,
                align_dd,
            ], spacing=12), density="dense"),
            ft.Container(height=16),
            design.section("Caratteristiche — Standard Array", ft.Column([
                design.muted(
                    "Assegna i valori [15, 14, 13, 12, 10, 8] alle caratteristiche. "
                    "I valori ripetuti sono permessi nel wizard (potrai aggiustare nel form).",
                    size=11,
                ),
                ft.Container(height=8),
                stat_rows,
                ft.Container(height=6),
                hp_note_text,
            ], spacing=8), accent=design.T().primary, hero=True),
        ]

        # extra_card gestisce autonomamente la propria visibilità via _update_extra_card()
        content_sections += [
            ft.Container(height=16),
            extra_card,
        ]

        # ---- Validazione obbligatoria prima di avanzare ----
        # Stesso principio di manual_form.py: le checkbox multi-select senza
        # un default pre-compilato (abilità di classe, Versatilità Mezzelfo,
        # lingue a scelta dal background, Maestria Ladro, trucchetti/incantesimi
        # iniziali) devono essere completate esplicitamente dal giocatore
        # prima di poter proseguire — a differenza dei dropdown (sottorazza,
        # sottoclasse, stile di combattimento, trucchetto Alto Elfo, lingua
        # Umano, strumenti), che sono sempre auto-popolati con un valore
        # valido di default.
        def _review_validation_error() -> str:
            skill_count, skill_opts = self._class_skill_options()
            if skill_count > 0 and skill_opts and len(self._review_skills) != skill_count:
                return f"Seleziona {skill_count} abilità di classe (sezione Abilità di Classe)."

            if self._review_race == "Mezzelfo" and len(self._review_mezzelf_skills) != 2:
                return "Seleziona 2 abilità per il tratto Versatilità nelle Abilità (Mezzelfo)."

            lang_count, _ = self._bg_language_choices()
            if lang_count > 0 and len(self._review_languages) != lang_count:
                return f"Seleziona {lang_count} {'lingue' if lang_count > 1 else 'lingua'} (sezione Lingue e Strumenti)."

            if self._review_class.lower() == "ladro" and len(self._review_expertise) != 2:
                return "Ladro: seleziona 2 abilità per la Maestria (Lv.1)."

            if self._review_race == "Umano" and self._review_umano_variant:
                stats_u = [s for s in self._review_umano_variant_stats if s]
                if len(stats_u) != 2 or len(set(stats_u)) != 2:
                    return "Variante Umana: assegna +1 a due caratteristiche diverse."
                if not self._review_umano_variant_skill:
                    return "Variante Umana: seleziona un'abilità a scelta."
                if not self._review_umano_variant_feat:
                    return "Variante Umana: seleziona un talento a scelta."
                _fd_u = _loader.get_feat(self._review_umano_variant_feat)
                _ab_u = (_fd_u.get("ability_bonus") if _fd_u else None) or {}
                if _ab_u.get("choose_one") and not self._review_umano_variant_feat_bonus_stat:
                    return "Variante Umana: scegli la caratteristica da aumentare per il talento."
                _uv_fp_grants = (_fd_u or {}).get("proficiency_grants", []) or []
                _uv_fp_total = sum(
                    int(g.get("count", 0) or 0) for g in _uv_fp_grants if g.get("type") == "choice"
                )
                if _uv_fp_total > 0:
                    _uv_fp_filled = [v for v in self._review_umano_variant_feat_prof_values if v]
                    if len(_uv_fp_filled) != _uv_fp_total or len(set(_uv_fp_filled)) != len(_uv_fp_filled):
                        return "Variante Umana: completa la scelta delle competenze concesse dal talento (nessun duplicato ammesso)."

            # Competenze bonus di sottoclasse a scelta
            _sc_bonus_entries = _loader.get_subclass_bonus_proficiencies(self._review_class, self._review_subclass)
            _sc_fixed, _sc_choices = character_repo.classify_bonus_proficiency_entries(_sc_bonus_entries)
            _sc_total_slots = sum(int(c.get("count", 0)) for c in _sc_choices)
            if _sc_total_slots > 0:
                _sc_filled = [c for c in self._review_subclass_bonus_choices if c]
                if len(_sc_filled) != _sc_total_slots or len(set(_sc_filled)) != len(_sc_filled):
                    return "Completa la scelta delle competenze bonus di sottoclasse (nessun duplicato ammesso)."

            n_cantrips  = _loader.get_cantrips_known_at_1(self._review_class)
            n_spells    = _loader.get_spells_known_at_1(self._review_class)
            n_prepared  = self._compute_prepared_spell_count()
            n_spellbook = _loader.get_spellbook_starting_spells(self._review_class)
            cantrips_chosen  = [c for c in self._review_cantrips if c]
            spells_chosen    = [s for s in self._review_spells_lv1 if s]
            prepared_chosen  = [s for s in self._review_prepared_spells if s]
            spellbook_chosen = [s for s in self._review_spellbook_spells if s]
            if (
                len(cantrips_chosen) < n_cantrips
                or len(spells_chosen) < n_spells
                or len(prepared_chosen) < n_prepared
                or len(spellbook_chosen) < n_spellbook
                or len(set(cantrips_chosen)) < len(cantrips_chosen)
                or len(set(spells_chosen)) < len(spells_chosen)
                or len(set(prepared_chosen)) < len(prepared_chosen)
                or len(set(spellbook_chosen)) < len(spellbook_chosen)
            ):
                return "Completa la scelta di trucchetti/incantesimi iniziali (nessun duplicato ammesso)."

            return ""

        review_error_text = ft.Text("", color=design.T().danger, size=13, visible=False)

        def _on_continue_to_equipment(e):
            err = _review_validation_error()
            if err:
                review_error_text.value   = err
                review_error_text.visible = True
                try:
                    review_error_text.update()
                except RuntimeError:
                    pass
                return
            self._goto_equipment()

        content_sections += [
            ft.Container(height=12),
            review_error_text,
            ft.Container(height=8),
            ft.Row(
                [
                    ghost_button("Indietro", on_click=self._on_back),
                    primary_button(
                        "Continua",
                        on_click=_on_continue_to_equipment,
                        icon=ft.Icons.ARROW_FORWARD,
                    ),
                ],
                alignment=ft.MainAxisAlignment.END,
                spacing=12,
                wrap=True,
            ),
        ]

        content = ft.Column(content_sections, scroll=ft.ScrollMode.AUTO, expand=True)
        self._set_content(
            ft.Container(content=content, expand=True,
                         padding=ft.Padding.symmetric(horizontal=16, vertical=20))
        )

    # ------------------------------------------------------------------
    # FASE 4: Equipaggiamento iniziale
    # ------------------------------------------------------------------

    def _goto_equipment(self):
        self._phase = "equipment"
        # Reset stato monete iniziali
        self._gold_mode   = False
        self._gold_amount = ""
        # Costruisce la lista oggetti dalla classe (deep copy per non mutare la cache)
        cls_data = _loader.get_class(self._review_class)
        self._equip_fixed = []
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
        self._render_equipment()

    def _render_equipment(self):
        self._phase = "equipment"

        rows: list[ft.Control] = [
            design.hero_title(
                "Equipaggiamento iniziale",
                "Seleziona l'equipaggiamento di partenza della tua classe.",
            ),
            ft.Container(height=20),
        ]

        # --- Oggetti fissi ---
        if self._equip_fixed:
            fixed_checks: list[ft.Control] = []
            for item in self._equip_fixed:
                if item.get("item_type") == "weapon_choice":
                    # Weapon picker: Dropdown al posto del checkbox
                    cat = item.get("category", "semplice")
                    weapons = WEAPONS_BY_CATEGORY.get(cat, [])
                    count = item.get("count", 1)
                    if count > 1:
                        # "Due armi semplici da mischia" → N dropdown
                        chosen = item.setdefault("chosen_weapons", [weapons[0]] * count if weapons else [])
                        fixed_checks.append(design.label(f"Scegli {count} armi ({cat.replace('_', ' ')}):"))
                        for wi in range(count):
                            def _on_wsel(e: Any, it=item, idx=wi) -> None:
                                it["chosen_weapons"][idx] = e.control.value or ""
                            fixed_checks.append(ft.Dropdown(
                                value=chosen[wi] if wi < len(chosen) else (weapons[0] if weapons else ""),
                                options=[ft.DropdownOption(key=w, text=w) for w in weapons],
                                width=220,
                                text_size=13,
                                on_select=_on_wsel,
                                **design.field_style()))
                    else:
                        chosen_w = item.setdefault("chosen_weapon", weapons[0] if weapons else "")
                        fixed_checks.append(ft.Row([
                            design.label(f"Arma ({cat.replace('_', ' ')}):"),
                            ft.Dropdown(
                                value=chosen_w,
                                options=[ft.DropdownOption(key=w, text=w) for w in weapons],
                                width=220,
                                text_size=13,
                                on_select=lambda e, it=item: it.update({"chosen_weapon": e.control.value or ""}),
                                **design.field_style()),
                        ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER))
                elif item.get("item_type") == "tool_choice":
                    # Tool picker: Dropdown al posto del checkbox (stesso schema di weapon_choice)
                    cat = item.get("category", "strumenti_musicali")
                    tools = _loader.get_tool_categories().get(cat, [])
                    count = item.get("count", 1)
                    if count > 1:
                        chosen = item.setdefault("chosen_tools", [tools[0]] * count if tools else [])
                        fixed_checks.append(design.label(f"Scegli {count} strumenti:"))
                        for ti in range(count):
                            def _on_tsel(e: Any, it=item, idx=ti) -> None:
                                it["chosen_tools"][idx] = e.control.value or ""
                            fixed_checks.append(ft.Dropdown(
                                value=chosen[ti] if ti < len(chosen) else (tools[0] if tools else ""),
                                options=[ft.DropdownOption(key=t, text=t) for t in tools],
                                width=220,
                                text_size=13,
                                on_select=_on_tsel,
                                **design.field_style()))
                    else:
                        chosen_t = item.setdefault("chosen_tool", tools[0] if tools else "")
                        fixed_checks.append(ft.Row([
                            design.label("Strumento:"),
                            ft.Dropdown(
                                value=chosen_t,
                                options=[ft.DropdownOption(key=t, text=t) for t in tools],
                                width=220,
                                text_size=13,
                                on_select=lambda e, it=item: it.update({"chosen_tool": e.control.value or ""}),
                                **design.field_style()),
                        ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER))
                else:
                    qty = item.get("quantity", 1)
                    label = item["name"] + (f" ×{qty}" if qty > 1 else "")
                    cb = ft.Checkbox(
                        label=label,
                        value=item["selected"],
                        fill_color=design.T().primary_fill,
                        check_color=design.T().on_primary_fill,
                        label_style=ft.TextStyle(size=13, color=design.T().text),
                        on_change=lambda e, it=item: it.update({"selected": bool(e.control.value)}),
                    )
                    # Se l'oggetto è una Dotazione, mostra sempre il suo
                    # contenuto (nessun "scegliere" qui — è già garantita —
                    # ma il giocatore deve comunque vedere cosa riceve).
                    pack_body = format_equipment_item_body(item, _loader)
                    if pack_body:
                        fixed_checks.append(ft.Column([
                            cb,
                            ft.Container(
                                content=ft.Text(pack_body, size=11,
                                                 color=design.T().text_2, selectable=True),
                                padding=ft.Padding.only(left=32, top=2, bottom=4),
                            ),
                        ], spacing=2))
                    else:
                        fixed_checks.append(cb)
            rows.append(design.section(
                "Oggetti garantiti", ft.Column(fixed_checks, spacing=6), accent=design.T().primary,
            ))
            rows.append(ft.Container(height=16))

        # --- Scelte A/B ---
        # CardPicker invece di RadioGroup — un click seleziona l'opzione E
        # mostra subito il contenuto espanso di ogni eventuale Dotazione
        # inclusa, senza bisogno di un secondo gesto.
        #
        # IMPORTANTE: `self._render_equipment()` ricostruirebbe l'INTERA
        # fase (tutte le card, monete iniziali, ecc.) tramite `_set_content`,
        # che resetta lo scroll in cima — va quindi evitato qui. La reveal
        # della card stessa è già locale (CardPicker si aggiorna da sé, vedi
        # ui/widgets.py), quindi qui rebuilda SOLO i Dropdown arma della
        # scelta toccata (l'unica cosa che dipende davvero da
        # `chosen_idx`), stesso pattern `.controls.clear()+extend()+update()`
        # già in uso in questo file.
        for ci, choice in enumerate(self._equip_choices):
            opts = choice["options"]
            if not opts:
                continue

            card_opts = equipment_option_card_options(opts, _loader)
            weapon_pickers_col = ft.Column(spacing=8)

            def _build_weapon_pickers(c: dict) -> list[ft.Control]:
                c_opts = c["options"]
                idx = c["chosen_idx"]
                chosen_opt = c_opts[idx] if 0 <= idx < len(c_opts) else []
                pickers: list[ft.Control] = []
                for item in chosen_opt:
                    if item.get("item_type") == "weapon_choice":
                        cat = item.get("category", "semplice")
                        weapons = WEAPONS_BY_CATEGORY.get(cat, [])
                        count = item.get("count", 1)
                        if count > 1:
                            chosen_ws = item.setdefault("chosen_weapons", [weapons[0]] * count if weapons else [])
                            pickers.append(design.label(f"Scegli {count} armi ({cat.replace('_', ' ')}):"))
                            for wi in range(count):
                                def _on_wc(e: Any, it=item, idx=wi) -> None:
                                    it["chosen_weapons"][idx] = e.control.value or ""
                                pickers.append(ft.Dropdown(
                                    value=chosen_ws[wi] if wi < len(chosen_ws) else (weapons[0] if weapons else ""),
                                    options=[ft.DropdownOption(key=w, text=w) for w in weapons],
                                    width=220, text_size=13, on_select=_on_wc,
                                    **design.field_style()))
                        else:
                            chosen_w = item.setdefault("chosen_weapon", weapons[0] if weapons else "")
                            pickers.append(ft.Row([
                                design.label(f"Arma ({cat.replace('_', ' ')}):"),
                                ft.Dropdown(
                                    value=chosen_w,
                                    options=[ft.DropdownOption(key=w, text=w) for w in weapons],
                                    width=220, text_size=13,
                                    on_select=lambda e, it=item: it.update({"chosen_weapon": e.control.value or ""}),
                                    **design.field_style()),
                            ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER))
                    elif item.get("item_type") == "tool_choice":
                        cat = item.get("category", "strumenti_musicali")
                        tools = _loader.get_tool_categories().get(cat, [])
                        count = item.get("count", 1)
                        if count > 1:
                            chosen_ts = item.setdefault("chosen_tools", [tools[0]] * count if tools else [])
                            pickers.append(design.label(f"Scegli {count} strumenti:"))
                            for ti in range(count):
                                def _on_tc(e: Any, it=item, idx=ti) -> None:
                                    it["chosen_tools"][idx] = e.control.value or ""
                                pickers.append(ft.Dropdown(
                                    value=chosen_ts[ti] if ti < len(chosen_ts) else (tools[0] if tools else ""),
                                    options=[ft.DropdownOption(key=t, text=t) for t in tools],
                                    width=220, text_size=13, on_select=_on_tc,
                                    **design.field_style()))
                        else:
                            chosen_t = item.setdefault("chosen_tool", tools[0] if tools else "")
                            pickers.append(ft.Row([
                                design.label("Strumento:"),
                                ft.Dropdown(
                                    value=chosen_t,
                                    options=[ft.DropdownOption(key=t, text=t) for t in tools],
                                    width=220, text_size=13,
                                    on_select=lambda e, it=item: it.update({"chosen_tool": e.control.value or ""}),
                                    **design.field_style()),
                            ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER))
                return pickers

            def _make_picker_select(c: dict, col: ft.Column) -> Any:
                def _on_select(ev: Any) -> None:
                    try:
                        c["chosen_idx"] = int(getattr(ev.control, "value", 0) or 0)
                    except (TypeError, ValueError):
                        c["chosen_idx"] = 0
                    col.controls.clear()
                    col.controls.extend(_build_weapon_pickers(c))
                    try:
                        col.update()
                    except RuntimeError:
                        pass
                return _on_select

            picker = CardPicker(
                options=card_opts,
                value=str(choice["chosen_idx"]),
                on_select=_make_picker_select(choice, weapon_pickers_col),
            )
            weapon_pickers_col.controls.extend(_build_weapon_pickers(choice))

            card_children: list[ft.Control] = [
                picker.control,
                ft.Container(height=8),
                weapon_pickers_col,
            ]

            rows.append(design.section(
                f"Scelta {ci + 1}", ft.Column(card_children, spacing=8), accent=design.T().primary,
            ))
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
                rows.append(design.section("Equipaggiamento background", ft.Column([
                    design.muted("Aggiunto automaticamente all'inventario.", size=11),
                    ft.Container(height=4),
                    ft.Text(bg_items_text, size=13, color=design.T().text),
                ], spacing=8), accent=design.T().primary))
                rows.append(ft.Container(height=16))

        # --- Sezione Monete iniziali (alternativa all'equipaggiamento di classe) ---
        cls_data_gold = _loader.get_class(self._review_class)
        if cls_data_gold:
            gold_alt = cls_data_gold.get("starting_gold_alternative", {})
            dice_str = gold_alt.get("dice", "")
            mult     = gold_alt.get("multiplier", 1)
            if dice_str:
                formula = f"{dice_str} × {mult} mo" if mult > 1 else f"{dice_str} mo"

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
                    text_style=ft.TextStyle(size=14, color=design.T().text),
                    border_color=design.T().border,
                    focused_border_color=design.T().magic,
                    bgcolor=design.T().surface,
                    border_radius=design.field_style()['border_radius'])

                # CardPicker invece di RadioGroup — stessa card cliccabile
                # già usata per incantesimi/dotazioni, per coerenza visiva.
                # `on_select` NON richiama `self._render_equipment()` (stesso
                # motivo delle Scelte A/B sopra): mostra/nasconde solo
                # `gold_field` in-place, nessun jump-to-top.
                def _on_gold_select(ev: Any) -> None:
                    self._gold_mode = (getattr(ev.control, "value", "") == "gold")
                    gold_field.visible = self._gold_mode
                    try:
                        gold_field.update()
                    except RuntimeError:
                        pass

                gold_picker = CardPicker(
                    options=[
                        {"key": "equip", "title": "Equipaggiamento standard", "body": ""},
                        {
                            "key": "gold",
                            "title": f"Oro iniziale — tira {formula}",
                            "body": "Tira il dado indicato e inserisci il risultato "
                                    "nel campo qui sotto: potrai spendere l'oro "
                                    "liberamente per il tuo equipaggiamento.",
                        },
                    ],
                    value="gold" if self._gold_mode else "equip",
                    on_select=_on_gold_select,
                )

                rows.append(design.section("Monete iniziali", ft.Column([
                    design.muted(
                        "In alternativa all'equipaggiamento, puoi iniziare con "
                        "dell'oro e acquistare ciò che vuoi.",
                        size=11,
                    ),
                    ft.Container(height=4),
                    gold_picker.control,
                    gold_field,
                ], spacing=8), accent=design.T().primary))
                rows.append(ft.Container(height=16))

        rows.append(ft.Row(
            [
                ghost_button("Indietro", on_click=self._on_back),
                primary_button("Continua", on_click=lambda e: self._goto_confirm(),
                               icon=ft.Icons.ARROW_FORWARD),
            ],
            alignment=ft.MainAxisAlignment.END,
            spacing=12,
            wrap=True,
        ))

        content = ft.Column(rows, scroll=ft.ScrollMode.AUTO, expand=True)
        self._set_content(
            ft.Container(content=content, expand=True,
                         padding=ft.Padding.symmetric(horizontal=16, vertical=20))
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
            bgcolor=design.T().surface,
            color=design.T().text,
            label_style=ft.TextStyle(color=design.T().text_3, size=12),
            border_color=design.T().border,
            focused_border_color=design.T().magic,
            cursor_color=design.T().magic,
            autofocus=True,
            border_radius=design.field_style()['border_radius'], text_style=design.field_style()['text_style'])
        player_field = ft.TextField(
            label="Nome del giocatore (opzionale)",
            bgcolor=design.T().surface,
            color=design.T().text,
            label_style=ft.TextStyle(color=design.T().text_3, size=12),
            border_color=design.T().border,
            focused_border_color=design.T().magic,
            cursor_color=design.T().magic,
            border_radius=design.field_style()['border_radius'], text_style=design.field_style()['text_style'])
        error_text = ft.Text("", color=design.T().danger, size=13, visible=False)

        # Riepilogo
        hd    = (_loader.get_class(self._review_class) or {}).get("hit_die", 8)
        con_m = get_modifier(self._review_stats.get("con", 10))
        hp    = max(1, hd + con_m)
        dex_m = get_modifier(self._review_stats.get("dex", 10))
        ac    = 10 + dex_m

        def _stat_chip(label: str, val) -> ft.Container:
            return ft.Container(
                content=ft.Column(
                    [
                        design.label(label),
                        ft.Text(str(val), size=14, weight=ft.FontWeight.BOLD,
                                color=design.T().primary),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=2,
                ),
                padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                bgcolor=design.T().surface_alt,
                shadow=design.elevation(1),
                border_radius=design.Radius.MD,
            )

        summary = ft.Column(
            [
                ft.Row(
                    [
                        ft.Column(
                            [
                                design.label("Classe"),
                                design.body(self._review_class, size=16,
                                            weight=ft.FontWeight.BOLD),
                            ],
                            spacing=2,
                        ),
                        ft.Column(
                            [
                                design.label("Razza"),
                                design.body(self._review_race, size=16),
                            ],
                            spacing=2,
                        ),
                        ft.Column(
                            [
                                design.label("Background"),
                                design.body(self._review_bg, size=16),
                            ],
                            spacing=2,
                        ),
                        ft.Column(
                            [
                                design.label("Allineamento"),
                                design.body(self._review_align, size=16),
                            ],
                            spacing=2,
                        ),
                    ],
                    spacing=24,
                    wrap=True,
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
                char = self.engine.build_character(
                    name=nm,
                    player_name=player_field.value.strip() if player_field.value else "",
                    class_name=self._review_class,
                    race=self._review_race,
                    background=self._review_bg,
                    alignment=self._review_align,
                    stat_assignment=self._review_stats,
                    subrace=self._review_subrace,
                )
                # Sottorazza e sottoclasse (se scelte in review)
                if self._review_subrace:
                    char.subrace = self._review_subrace
                if self._review_subclass:
                    char.subclass = self._review_subclass
                    # Bonus PF permanente da capacità di sottoclasse
                    # (es. Resilienza Draconica dello Stregone)
                    hp_bonus = get_permanent_class_hp_bonus(
                        char.class_name, char.subclass, char.level
                    )
                    char.hp_max += hp_bonus
                    char.hp_current = char.hp_max

                # Scelte razza/classe extra
                if self._review_dragon_ancestry:
                    char.dragon_ancestry = self._review_dragon_ancestry
                if self._review_fighting_style:
                    char.fighting_style = self._review_fighting_style

                # Mezzelf: applica i bonus flessibili (+1 a 2 stat)
                if self._review_race == "Mezzelfo" and len(self._review_mezzelf_flex) == 2:
                    stat_map = {
                        "str": "str_score", "dex": "dex_score", "con": "con_score",
                        "int": "int_score", "wis": "wis_score", "cha": "cha_score",
                    }
                    for stat_key in self._review_mezzelf_flex:
                        attr = stat_map.get(stat_key)
                        if attr:
                            setattr(char, attr, min(20, getattr(char, attr) + 1))

                # Umano Variante: sostituisce il
                # tratto standard "+1 a tutte le caratteristiche" (già
                # applicato da build_character() tramite
                # get_resolved_race("Umano")["ability_bonuses"]) con +1 a
                # due caratteristiche a scelta. Sottrae prima il bonus
                # standard su TUTTE e sei, poi applica il bonus variante
                # solo sulle due scelte — net effect corretto per qualunque
                # combinazione. Stessa identica implementazione di
                # manual_form.py.
                if self._review_race == "Umano" and self._review_umano_variant:
                    stat_map_u = {
                        "str": "str_score", "dex": "dex_score", "con": "con_score",
                        "int": "int_score", "wis": "wis_score", "cha": "cha_score",
                    }
                    for attr_u in stat_map_u.values():
                        setattr(char, attr_u, max(1, getattr(char, attr_u) - 1))
                    for stat_key in self._review_umano_variant_stats:
                        attr_u = stat_map_u.get(stat_key)
                        if attr_u:
                            setattr(char, attr_u, min(20, getattr(char, attr_u) + 1))
                    # Ricalcola HP se CON è cambiata rispetto a quella usata
                    # da build_character() — il flex Mezzelfo sopra condivide
                    # lo stesso limite ma non lo ricalcola (segnalato in
                    # CLAUDE.md).
                    _hit_die_u = (_loader.get_class(self._review_class) or {}).get("hit_die", 8)
                    char.hp_max = max(1, _hit_die_u + get_modifier(char.con_score))
                    char.hp_current = char.hp_max

                # Validazione completa scelte obbligatorie — rete di sicurezza
                # (nel flusso normale l'utente non arriva qui senza aver già
                # superato _review_validation_error() sul pulsante "Continua"
                # della fase Revisione, ma la si riesegue per difesa in
                # profondità, stesso principio di manual_form.py).
                skill_count, skill_opts = self._class_skill_options()
                if skill_count > 0 and skill_opts and len(self._review_skills) != skill_count:
                    error_text.value = f"Seleziona {skill_count} abilità di classe (sezione Revisione)."
                    error_text.visible = True
                    error_text.update()
                    return

                if self._review_race == "Mezzelfo" and len(self._review_mezzelf_skills) != 2:
                    error_text.value = "Mezzelfo: seleziona 2 abilità per Versatilità nelle Abilità (sezione Revisione)."
                    error_text.visible = True
                    error_text.update()
                    return

                lang_count, _ = self._bg_language_choices()
                if lang_count > 0 and len(self._review_languages) != lang_count:
                    error_text.value = (
                        f"Seleziona {lang_count} {'lingue' if lang_count > 1 else 'lingua'} (sezione Revisione)."
                    )
                    error_text.visible = True
                    error_text.update()
                    return

                # Validazione Maestria Ladro
                if self._review_class.lower() == "ladro" and len(self._review_expertise) != 2:
                    error_text.value = "Ladro: seleziona 2 abilità per la Maestria (sezione Maestria nella fase Revisione)."
                    error_text.visible = True
                    error_text.update()
                    return

                # Validazione Umano Variante
                if self._review_race == "Umano" and self._review_umano_variant:
                    _stats_u_chk = [s for s in self._review_umano_variant_stats if s]
                    if len(_stats_u_chk) != 2 or len(set(_stats_u_chk)) != 2:
                        error_text.value = "Variante Umana: assegna +1 a due caratteristiche diverse (sezione Revisione)."
                        error_text.visible = True
                        error_text.update()
                        return
                    if not self._review_umano_variant_skill:
                        error_text.value = "Variante Umana: seleziona un'abilità a scelta (sezione Revisione)."
                        error_text.visible = True
                        error_text.update()
                        return
                    if not self._review_umano_variant_feat:
                        error_text.value = "Variante Umana: seleziona un talento a scelta (sezione Revisione)."
                        error_text.visible = True
                        error_text.update()
                        return
                    _fd_u2 = _loader.get_feat(self._review_umano_variant_feat)
                    _ab_u2 = (_fd_u2.get("ability_bonus") if _fd_u2 else None) or {}
                    if _ab_u2.get("choose_one") and not self._review_umano_variant_feat_bonus_stat:
                        error_text.value = "Variante Umana: scegli la caratteristica da aumentare per il talento (sezione Revisione)."
                        error_text.visible = True
                        error_text.update()
                        return
                    _uv_fp_grants2 = (_fd_u2 or {}).get("proficiency_grants", []) or []
                    _uv_fp_total2 = sum(
                        int(g.get("count", 0) or 0) for g in _uv_fp_grants2 if g.get("type") == "choice"
                    )
                    if _uv_fp_total2 > 0:
                        _uv_fp_filled2 = [v for v in self._review_umano_variant_feat_prof_values if v]
                        if len(_uv_fp_filled2) != _uv_fp_total2 or len(set(_uv_fp_filled2)) != len(_uv_fp_filled2):
                            error_text.value = "Variante Umana: completa la scelta delle competenze concesse dal talento (sezione Revisione)."
                            error_text.visible = True
                            error_text.update()
                            return

                # Validazione competenze bonus di sottoclasse (difesa in
                # profondità — stesso controllo già fatto dal pulsante
                # "Continua" tramite _review_validation_error())
                _sc_bonus_entries_chk = _loader.get_subclass_bonus_proficiencies(self._review_class, self._review_subclass)
                _sc_fixed_chk, _sc_choices_chk = character_repo.classify_bonus_proficiency_entries(_sc_bonus_entries_chk)
                _sc_total_slots_chk = sum(int(c.get("count", 0)) for c in _sc_choices_chk)
                if _sc_total_slots_chk > 0:
                    _sc_filled_chk = [c for c in self._review_subclass_bonus_choices if c]
                    if len(_sc_filled_chk) != _sc_total_slots_chk or len(set(_sc_filled_chk)) != len(_sc_filled_chk):
                        error_text.value = "Completa la scelta delle competenze bonus di sottoclasse (nessun duplicato ammesso)."
                        error_text.visible = True
                        error_text.update()
                        return

                # Validazione Trucchetti/Incantesimi iniziali
                n_cantrips_needed  = _loader.get_cantrips_known_at_1(self._review_class)
                n_spells_needed    = _loader.get_spells_known_at_1(self._review_class)
                n_prepared_needed  = self._compute_prepared_spell_count()
                n_spellbook_needed = _loader.get_spellbook_starting_spells(self._review_class)
                cantrips_chosen   = [c for c in self._review_cantrips if c]
                spells_chosen     = [s for s in self._review_spells_lv1 if s]
                prepared_chosen   = [s for s in self._review_prepared_spells if s]
                spellbook_chosen  = [s for s in self._review_spellbook_spells if s]
                if (
                    len(cantrips_chosen) < n_cantrips_needed
                    or len(spells_chosen) < n_spells_needed
                    or len(prepared_chosen) < n_prepared_needed
                    or len(spellbook_chosen) < n_spellbook_needed
                    or len(set(cantrips_chosen)) < len(cantrips_chosen)
                    or len(set(spells_chosen)) < len(spells_chosen)
                    or len(set(prepared_chosen)) < len(prepared_chosen)
                    or len(set(spellbook_chosen)) < len(spellbook_chosen)
                ):
                    error_text.value = (
                        "Completa la scelta di trucchetti/incantesimi iniziali "
                        "(sezione Trucchetti e Incantesimi Iniziali, nessun duplicato ammesso)."
                    )
                    error_text.visible = True
                    error_text.update()
                    return

                ok = character_repo.create(char)
                if not ok:
                    detail = getattr(character_repo, "_last_create_error", "")
                    raise RuntimeError(f"Errore DB: {detail}" if detail else "Errore nel salvataggio sul database.")

                # Tiri salvezza competenti dalla classe (PHB)
                for stat_name in _loader.get_class_saving_throws(self._review_class):
                    character_repo._save_single_proficiency(char.id, "save", stat_name)

                # Abilità: background (fisso) + scelte di classe
                bg_data = _loader.get_background(self._review_bg)
                bg_skills: list[str] = bg_data.get("skill_proficiencies", []) if bg_data else []
                for skill in bg_skills:
                    character_repo._save_single_proficiency(char.id, "skill", skill)
                for skill in self._review_skills:
                    if skill and skill not in bg_skills:
                        character_repo._save_single_proficiency(char.id, "skill", skill)

                # Abilità Mezzelf (Versatilità nelle Abilità — 2 abilità razziali)
                for skill in self._review_mezzelf_skills:
                    if skill:
                        character_repo._save_single_proficiency(char.id, "skill", skill)

                # Umano Variante: abilità a scelta + talento a scelta. Il
                # talento viene salvato con lo stesso schema "ricevuta"
                # (bonus_data/level_obtained) già usato per
                # i talenti scelti all'ASI del level-up, così compare nella
                # sezione Talenti di ProfiloTab e può essere rimosso/
                # reversato con remove_feat_with_bonuses() come qualunque
                # altro talento. Stessa identica implementazione di
                # manual_form.py.
                if self._review_race == "Umano" and self._review_umano_variant:
                    if self._review_umano_variant_skill:
                        character_repo._save_single_proficiency(
                            char.id, "skill", self._review_umano_variant_skill
                        )
                    if self._review_umano_variant_feat:
                        _fd_save = _loader.get_feat(self._review_umano_variant_feat)
                        _ab_save = (_fd_save.get("ability_bonus") if _fd_save else None) or {}
                        _ob_save = (_fd_save.get("other_bonuses") if _fd_save else None) or {}
                        _applied_ability: dict[str, int] = {}
                        _applied_other: dict[str, int] = {}
                        _grant_save_key_uv = ""  # per grants_save_proficiency (Resiliente)
                        if _ab_save:
                            if _ab_save.get("choose_one"):
                                if self._review_umano_variant_feat_bonus_stat:
                                    _stat_f = self._review_umano_variant_feat_bonus_stat
                                    _cur_f = getattr(char, f"{_stat_f}_score", 10)
                                    setattr(char, f"{_stat_f}_score", min(20, _cur_f + 1))
                                    _applied_ability[_stat_f] = 1
                                    _grant_save_key_uv = _stat_f
                            else:
                                for _stat_f, _val_f in _ab_save.items():
                                    if _stat_f in ABILITY_KEYS and isinstance(_val_f, int):
                                        _cur_f = getattr(char, f"{_stat_f}_score", 10)
                                        setattr(char, f"{_stat_f}_score", min(20, _cur_f + _val_f))
                                        _applied_ability[_stat_f] = _val_f
                                        _grant_save_key_uv = _stat_f
                        if _ob_save:
                            if "initiative" in _ob_save:
                                char.initiative_bonus = (char.initiative_bonus or 0) + _ob_save["initiative"]
                                _applied_other["initiative"] = _ob_save["initiative"]
                            if "speed" in _ob_save:
                                char.speed = (char.speed or 9) + _ob_save["speed"]
                                _applied_other["speed"] = _ob_save["speed"]

                        # Competenze concesse dal talento (proficiency_grants)
                        # + eventuale competenza nel tiro salvezza (Resiliente)
                        if not _ab_save.get("grants_save_proficiency"):
                            _grant_save_key_uv = ""
                        _granted_profs_uv = character_repo.apply_feat_proficiency_grants(
                            char.id, self._review_umano_variant_feat,
                            self._review_umano_variant_feat_prof_values, _grant_save_key_uv,
                        )

                        _bonus_data_save: dict = {}
                        if _applied_ability:
                            _bonus_data_save["ability"] = _applied_ability
                        if _applied_other:
                            _bonus_data_save["other"] = _applied_other
                        if _granted_profs_uv:
                            _bonus_data_save["granted_proficiencies"] = _granted_profs_uv
                        import json as _json_uv
                        character_repo._save_single_proficiency(
                            char.id, "feat", self._review_umano_variant_feat,
                            bonus_data=_json_uv.dumps(_bonus_data_save) if _bonus_data_save else None,
                            level_obtained=1,
                        )

                        # Bonus PF permanente per-livello (es. Robusto: 2×livello,
                        # a Lv.1 = 2) — stesso principio "ricalcola il totale"
                        # già usato per il bonus di sottoclasse più sopra.
                        _hp_feat_bonus_uv = get_feats_permanent_hp_bonus(
                            [self._review_umano_variant_feat], char.level or 1
                        )
                        if _hp_feat_bonus_uv:
                            char.hp_max += _hp_feat_bonus_uv
                            char.hp_current = char.hp_max

                        # Il talento può aver cambiato caratteristiche/PF —
                        # persiste le eventuali modifiche fatte sopra.
                        character_repo.update(char)

                # Maestria Ladro Lv1: raddoppia il bonus competenza per 2 abilità scelte
                if self._review_class.lower() == "ladro" and self._review_expertise:
                    character_repo.set_expertise(char.id, self._review_expertise)

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
                        description="Trucchetto del Mago (tratto Elfo Alto — INT)",
                        higher_levels="",
                        class_list="Mago",
                    )

                # Trucchetti e incantesimi conosciuti al Lv.1
                def _save_known_spell_by_name(
                    spell_name: str, class_name: str, is_prepared: bool = True
                ) -> None:
                    """Recupera i dettagli dell'incantesimo dal JSON di classe e lo salva come conosciuto."""
                    spell = next(
                        (s for s in _loader.get_spells(class_name) if s.get("name") == spell_name),
                        None,
                    )
                    if spell is None:
                        # Lista Incantesimi Ampliata (Warlock) — un nome
                        # scelto dal pool "ampliato" (es. Il Signore Fatato
                        # → Luminescenza) non è nella lista base della
                        # classe, va risolto qui.
                        spell = next(
                            (s for s in _loader.get_expanded_spells(class_name, char.subclass or "")
                             if s.get("name") == spell_name),
                            None,
                        )
                    if spell is None:
                        logger.warning(
                            "Incantesimo '%s' non trovato per classe '%s' (creazione wizard)",
                            spell_name, class_name,
                        )
                        return
                    comps = spell.get("components", [])
                    comp_str = ", ".join(comps) if isinstance(comps, list) else str(comps)
                    if spell.get("material"):
                        comp_str += f" ({spell['material']})"
                    character_repo.upsert_known_spell(
                        character_id=char.id,
                        name=spell_name,
                        level=spell.get("level", 0),
                        is_prepared=is_prepared,
                        school=spell.get("school", ""),
                        casting_time=spell.get("casting_time", ""),
                        spell_range=spell.get("range", ""),
                        components=comp_str,
                        duration=spell.get("duration", ""),
                        description=spell.get("description", ""),
                        higher_levels=spell.get("higher_levels", "") or "",
                        class_list=class_name,
                    )

                for cname in cantrips_chosen:
                    _save_known_spell_by_name(cname, self._review_class)
                for sname in spells_chosen:
                    _save_known_spell_by_name(sname, self._review_class)
                for pname in prepared_chosen:
                    _save_known_spell_by_name(pname, self._review_class)

                # Libro degli Incantesimi del Mago — tutti e 6
                # persistiti come "conosciuti" (nel libro), ma solo i primi
                # `_compute_mago_max_prepared()` marcati is_prepared=True: la
                # tab Incantesimi applica lo stesso limite mod.INT+livello
                # a QUALUNQUE nuova preparazione (spells_view.py._calc_max_prepared,
                # Mago è "full caster"), e non lo corregge mai automaticamente
                # se uno stato preesistente lo supera — salvare tutti e 6
                # come preparati creerebbe un Mago già "sopra al limite" fin
                # dalla creazione.
                if spellbook_chosen:
                    max_prep_mago = self._compute_mago_max_prepared()
                    for idx, bname in enumerate(spellbook_chosen):
                        _save_known_spell_by_name(
                            bname, self._review_class, is_prepared=idx < max_prep_mago
                        )

                # Lingue fisse concesse dalla razza (es. Comune + Elfico per l'Elfo)
                lang_seen: set[str] = set()
                resolved_race = _loader.get_resolved_race(self._review_race, self._review_subrace)
                for entry in resolved_race.get("languages", []):
                    if isinstance(entry, str) and entry not in lang_seen:
                        character_repo._save_single_proficiency(char.id, "language", entry)
                        lang_seen.add(entry)

                # Lingua/e aggiuntive a scelta libera concesse dalla razza
                # (Umano, Mezzelfo)
                for race_lang in self._review_race_languages:
                    if race_lang and race_lang not in lang_seen:
                        character_repo._save_single_proficiency(char.id, "language", race_lang)
                        lang_seen.add(race_lang)

                # Lingue scelte da background
                for lang in self._review_languages:
                    if lang and lang not in lang_seen:
                        character_repo._save_single_proficiency(char.id, "language", lang)
                        lang_seen.add(lang)

                # Strumenti scelti (background + classe) + strumenti fissi
                # (background + classe): sia le scelte (Bardo: 3 strumenti
                # musicali, Monaco: 1 artigiano/musicale) sia le fisse
                # (Ladro "Arnesi da Scasso", Druido "Borsa da Erborista").
                tool_seen: set[str] = set()
                for tool in self._review_tools:
                    if tool and tool not in tool_seen:
                        character_repo._save_single_proficiency(char.id, "tool", tool)
                        tool_seen.add(tool)
                for tool in self._review_class_tools:
                    if tool and tool not in tool_seen:
                        character_repo._save_single_proficiency(char.id, "tool", tool)
                        tool_seen.add(tool)
                if bg_data:
                    for entry in bg_data.get("tool_proficiencies", []):
                        if isinstance(entry, str) and entry not in tool_seen:
                            character_repo._save_single_proficiency(char.id, "tool", entry)
                            tool_seen.add(entry)
                cls_data_tools = _loader.get_class(self._review_class)
                if cls_data_tools:
                    for entry in cls_data_tools.get("tool_proficiencies", []):
                        if isinstance(entry, str) and entry not in tool_seen:
                            character_repo._save_single_proficiency(char.id, "tool", entry)
                            tool_seen.add(entry)

                # Competenze bonus di sottoclasse — es. Chierico Dominio della
                # Vita/Natura/Tempesta/Guerra (armature/armi fisse + scelta
                # abilità per Natura), letto da bonus_proficiencies in
                # classes/*.json. Solo le classi con subclass_choice_level
                # == 1 possono valorizzare char.subclass a questo punto della
                # creazione (oggi solo Chierico/Stregone/Warlock).
                _sc_bonus_entries_save = _loader.get_subclass_bonus_proficiencies(char.class_name, char.subclass)
                _sc_fixed_save, _sc_choices_save = character_repo.classify_bonus_proficiency_entries(_sc_bonus_entries_save)
                _sc_resolved_save = list(_sc_fixed_save) + [c for c in self._review_subclass_bonus_choices if c]
                character_repo.apply_subclass_bonus_proficiencies(char.id, _sc_resolved_save)

                # Competenze base di classe (armor_proficiencies/weapon_proficiencies
                # di classes/*.json — livello classe, non sottoclasse). Gap segnalato
                # in CLAUDE.md, mai applicate finora da nessun percorso di creazione.
                character_repo.apply_class_base_proficiencies(char.id, char.class_name)

                def _save_weapon_by_name(character_id: str, wname: str) -> None:
                    """
                    Crea l'arma nella tabella weapons (mai in inventario — unica
                    fonte di verità per le armi, vedi CLAUDE.md "Armi
                    riserva"), leggendo dado danno/tipo danno/proprietà da
                    equipment/weapons.json. Se il nome non viene trovato (es.
                    refuso di trascrizione), crea comunque la riga in weapons ma
                    con statistiche vuote (modificabili poi dal dialog "Modifica"
                    in Inventario → Armi) invece di perdere silenziosamente
                    l'oggetto o di farlo atterrare nella categoria "Armi
                    (riserva)" ormai rimossa dalla UI — logga comunque un
                    warning diagnosticabile.

                    Creata sempre `is_equipped=False`: nessuna arma parte
                    equipaggiata, il giocatore la equipaggia dalla tab
                    Inventario col pulsante dedicato (vedi
                    `inventario_tab.py`). Un approccio alternativo (auto-
                    equipaggiare ogni arma e poi risolvere i conflitti con
                    `resolve_weapon_equip()` in una passata di finalizzazione
                    a fine creazione) produce risultati imprevedibili con 3+
                    armi di partenza: quella passata chiama la funzione una
                    volta per OGNI arma ancora marcata equipaggiata dopo le
                    iterazioni precedenti, e ogni chiamata può ri-confermare
                    armi già "tenute" nell'iterazione precedente E
                    aggiungerne altre finché restano mani libere cumulate tra
                    chiamate diverse.
                    """
                    wdata = _loader.get_weapon(wname)
                    if wdata:
                        props = wdata.get("properties", [])
                        props_str = ", ".join(props) if isinstance(props, list) else str(props)
                        character_repo.create_weapon(
                            character_id=character_id, name=wname,
                            damage_dice=wdata.get("damage_dice", ""),
                            damage_type=wdata.get("damage_type", ""),
                            properties=props_str,
                            is_equipped=False,
                        )
                    else:
                        logger.warning(
                            "Arma '%s' non trovata in equipment/weapons.json — "
                            "creata in weapons con statistiche vuote", wname,
                        )
                        character_repo.create_weapon(
                            character_id=character_id, name=wname,
                            is_equipped=False,
                        )

                def _save_armor_by_name(character_id: str, aname: str, quantity: int = 1) -> None:
                    """
                    Crea un'armatura/scudo in inventario (category="armor"),
                    risolvendo ca_value/armor_type/peso dal catalogo
                    equipment/armor.json via GameDataLoader.get_armor_item().

                    Se il nome NON è nel catalogo (es. "Abito comune", un
                    indumento che il PHB non tratta come protezione del
                    Cap.5 Armature) crea comunque l'oggetto, ma con
                    ca_value=0 e armor_type="" — calculate_and_update_ca()
                    filtra esplicitamente solo gli item con armor_type in
                    ("leggera","media","pesante") o "scudo", quindi un
                    oggetto con armor_type="" ha effetto ESATTAMENTE NULLO
                    sulla CA anche se equipaggiato: il personaggio resta
                    sulla formula "senza armatura" (10+DEX, o le formule
                    speciali di Monaco/Barbaro/Stregone+Discendenza
                    Draconica). Comportamento intenzionale — vedi CLAUDE.md.
                    """
                    adata = _loader.get_armor_item(aname)
                    if adata:
                        character_repo.create_inventory_item(
                            character_id=character_id, name=aname, quantity=quantity,
                            weight=float(adata.get("weight_kg") or 0.0),
                            category="armor", is_equipped=True,
                            ca_value=adata.get("ca_value", 0),
                            armor_type=adata.get("armor_type", ""),
                        )
                    else:
                        logger.warning(
                            "Armatura '%s' non trovata in equipment/armor.json — "
                            "creata come indumento non protettivo (ca_value=0)", aname,
                        )
                        character_repo.create_inventory_item(
                            character_id=character_id, name=aname, quantity=quantity,
                            weight=0.0, category="armor", is_equipped=True,
                            ca_value=0, armor_type="",
                        )

                # Indice del prossimo "strumento a scelta" del background da
                # risolvere in _save_item() — vedi commento lì. Condiviso tra
                # tutte le chiamate di _save_item per lo stesso personaggio,
                # incrementato ogni volta che un placeholder "(a scelta)"
                # viene incontrato nell'equipaggiamento.
                _choice_equip_idx = 0

                def _save_item(character_id: str, item: dict) -> None:
                    """Salva un item di equipaggiamento: weapon/weapon_choice → tabella weapons
                    (una riga per unità se quantity>1), armor → inventario con ca_value/
                    armor_type risolti dal catalogo, currency → update_currencies,
                    regular item → inventario generico.

                    I nomi placeholder "(a scelta)" (es. "Strumento musicale
                    (a scelta)", "Strumenti da artigiano (a scelta)") non
                    sono trattati come oggetti letterali: vengono risolti
                    contro self._review_tools (lo/gli strumento/i che il
                    giocatore ha effettivamente scelto per la competenza
                    tool_proficiencies a scelta dello stesso background) e
                    salvati con quel nome esatto e category="tool" — non più
                    come oggetto generico "misc" col nome letterale del
                    placeholder. Se per qualche motivo non c'è una scelta
                    disponibile (background senza scelta strumenti, indice
                    esaurito), il placeholder letterale resta come fallback
                    diagnosticabile invece di sparire silenziosamente.
                    """
                    nonlocal _choice_equip_idx
                    itype = item.get("item_type", "item")
                    if itype == "weapon_choice":
                        count = item.get("count", 1)
                        if count > 1:
                            for wname in item.get("chosen_weapons", []):
                                if wname:
                                    _save_weapon_by_name(character_id, wname)
                        else:
                            wname = item.get("chosen_weapon", "")
                            if wname:
                                _save_weapon_by_name(character_id, wname)
                    elif itype == "tool_choice":
                        count = item.get("count", 1)
                        chosen_names = (
                            item.get("chosen_tools", []) if count > 1
                            else [item.get("chosen_tool", "")]
                        )
                        for tname in chosen_names:
                            if tname:
                                character_repo.create_inventory_item(
                                    character_id=character_id,
                                    name=tname,
                                    quantity=1,
                                    weight=0.0, category="tool",
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
                    elif itype == "weapon":
                        # Una riga distinta in weapons per ogni unità — un
                        # nome tipo "Due pugnali" con quantity=2 è un bug di
                        # dato già corretto nei JSON (rinominato "Pugnale"),
                        # ma il loop resta comunque la protezione strutturale
                        # corretta per qualunque item_type="weapon" con
                        # quantity>1.
                        for _ in range(max(1, item.get("quantity", 1))):
                            _save_weapon_by_name(character_id, item["name"])
                    elif itype == "armor":
                        _save_armor_by_name(character_id, item["name"], item.get("quantity", 1))
                    else:
                        item_name = item["name"]
                        item_category = "misc"
                        if "(a scelta)" in item_name:
                            chosen = (
                                self._review_tools[_choice_equip_idx]
                                if _choice_equip_idx < len(self._review_tools)
                                else ""
                            )
                            _choice_equip_idx += 1
                            if chosen:
                                item_name = chosen
                                item_category = "tool"
                            else:
                                logger.warning(
                                    "Equipaggiamento '%s': nessuna scelta strumenti "
                                    "disponibile da risolvere, mantenuto il nome "
                                    "placeholder", item["name"],
                                )
                        pack_items = _loader.get_pack_contents(item_name)
                        if pack_items is not None:
                            # "Dotazione da X" non è un oggetto in sé ma un
                            # insieme di oggetti (PHB p.151) — espansa nei
                            # singoli oggetti che contiene invece di creare
                            # un unico InventoryItem con il nome letterale
                            # della dotazione.
                            for sub in pack_items:
                                character_repo.create_inventory_item(
                                    character_id=character_id,
                                    name=sub["name"],
                                    quantity=sub.get("quantity", 1),
                                    weight=0.0, category="misc",
                                    is_equipped=False, description="",
                                )
                        else:
                            character_repo.create_inventory_item(
                                character_id=character_id,
                                name=item_name,
                                quantity=item.get("quantity", 1),
                                weight=0.0, category=item_category,
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
                    # Oggetti fissi selezionati
                    for item in self._equip_fixed:
                        if item.get("selected", True):
                            _save_item(char.id, item)
                    # Scelte A/B
                    for choice in self._equip_choices:
                        idx = choice.get("chosen_idx", 0)
                        opts = choice.get("options", [])
                        if 0 <= idx < len(opts):
                            for item in opts[idx]:
                                _save_item(char.id, item)

                # Equipaggiamento background (currency → update_currencies, item → inventario)
                # sempre salvato indipendentemente dalla scelta equipaggiamento/oro
                if bg_data:
                    for entry in bg_data.get("equipment", []):
                        if isinstance(entry, dict):
                            _save_item(char.id, entry)

                # Risolve eventuali conflitti di equipaggiamento tra le
                # armature/scudi appena creati (_save_armor_by_name li crea
                # sempre is_equipped=True) applicando la stessa esclusività
                # di resolve_armor_equip() già usata in inventario_tab.py —
                # nel normale caso (1 armatura + max 1 scudo per classe) non
                # cambia nulla, ma protegge da un futuro package JSON
                # malformato con 2 armature corporee/2 scudi fissi entrambi
                # equipaggiati (regola PHB: massimo un'armatura e uno scudo
                # indossati per volta).
                armor_rows = [
                    i for i in character_repo.get_inventory(char.id)
                    if i.category == "armor"
                ]
                candidates = [
                    ArmorCandidate(id=i.id, armor_type=i.armor_type, is_equipped=i.is_equipped)
                    for i in armor_rows
                ]
                for cand in candidates:
                    if not cand.is_equipped:
                        continue
                    keep_ids = resolve_armor_equip(candidates, cand.id)
                    for other in candidates:
                        other.is_equipped = other.id in keep_ids
                final_state = {c.id: c.is_equipped for c in candidates}
                for i in armor_rows:
                    if final_state.get(i.id, i.is_equipped) != i.is_equipped:
                        character_repo.update_inventory_item(
                            item_id=i.id, name=i.name, quantity=i.quantity,
                            weight=i.weight, description=i.description,
                            category=i.category, is_equipped=final_state[i.id],
                            ca_value=i.ca_value, armor_type=i.armor_type,
                            effects=i.effects,
                        )

                # Le armi non partono mai equipaggiate (vedi docstring di
                # _save_weapon_by_name) — nessuna risoluzione di conflitto
                # necessaria qui, il giocatore equipaggia dalla tab
                # Inventario (già corretto e testato per il singolo click).

                # Ricalcola la CA in base alle armature/scudi/stile di
                # combattimento effettivamente risultanti dalle risoluzioni
                # sopra, e alle formule di classe senza armatura (Monaco,
                # Barbaro, Stregone+Discendenza Draconica) per chi non ne ha
                # ricevuta nessuna.
                character_repo.calculate_and_update_ca(char.id)

                logger.info(f"Personaggio wizard creato: {char.name} ({char.id})")
                self.on_complete(char.id)

            except Exception as ex:
                logger.error(f"Errore salvataggio wizard: {ex}")
                error_text.value = f"Errore durante il salvataggio: {ex}"
                error_text.visible = True
                try:
                    error_text.update()
                except RuntimeError:
                    pass

        # Ultimo step: il form nome (contenuto primario di questo step) e il
        # riepilogo del personaggio (sintesi di TUTTE le scelte fatte finora
        # nel wizard) affiancati con `asymmetric_row` — il riepilogo prende
        # `hero=True` (unico per schermata) perché è l'elemento più
        # consultato prima di premere "Crea personaggio".
        content = ft.Column(
            [
                design.hero_title(
                    "Dai un nome al tuo eroe",
                    "Quasi fatto! Assegna un nome e salva il tuo personaggio.",
                ),
                ft.Container(height=20),
                design.asymmetric_row(
                    design.section("Identità del personaggio", ft.Column([
                        name_field,
                        player_field,
                    ], spacing=12), density="dense"),
                    design.section("Riepilogo", summary, accent=design.T().primary, hero=True),
                    ratio=(5, 7),
                ),
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
                    wrap=True,
                ),
            ],
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

        self._set_content(
            ft.Container(
                content=content,
                expand=True,
                padding=ft.Padding.symmetric(horizontal=16, vertical=20),
            )
        )
