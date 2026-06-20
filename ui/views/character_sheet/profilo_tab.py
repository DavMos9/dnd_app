"""
Tab Profilo della scheda personaggio.

Sezioni:
    Anagrafica   — identità, livello, XP, bonus competenza
    Fisico       — età, altezza, peso, occhi, carnagione, capelli
    Personalità  — tratti, ideali, legami, difetti
    Storia       — backstory, alleanze, tratti aggiuntivi
    Competenze   — tiri salvezza e abilità con modificatori calcolati

Input:  Character + list[CharacterProficiency]
Output: ft.Column scrollabile
"""

import flet as ft
import logging
from config.settings import *
from data.models import Character, CharacterProficiency
from ui.theme import label_text, body_text, muted_text, fantasy_card, section_header

logger = logging.getLogger(__name__)


class ProfiloTab(ft.Column):
    """
    Tab Profilo: sola lettura, dati dal DB senza modifiche in-place.
    """

    def __init__(self, character: Character, proficiencies: list[CharacterProficiency]):
        super().__init__(
            scroll=ft.ScrollMode.AUTO,
            expand=True,
            spacing=12,
            margin=ft.Margin.all(16),
        )
        self.character = character
        self.proficiencies = proficiencies
        self._build()

    # ------------------------------------------------------------------
    # Build principale
    # ------------------------------------------------------------------

    def _build(self):
        c = self.character
        prof_bonus = get_proficiency_bonus(c.level)

        self.controls = [
            section_header("Anagrafica"),
            self._build_anagrafica(c, prof_bonus),
            section_header("Dettagli Fisici"),
            self._build_fisico(c),
            section_header("Personalità"),
            self._build_personalita(c),
            section_header("Storia e Alleanze"),
            self._build_storia(c),
            section_header("Competenze"),
            self._build_competenze(prof_bonus),
            ft.Container(height=20),  # padding bottom
        ]

    # ------------------------------------------------------------------
    # Sezioni
    # ------------------------------------------------------------------

    def _build_anagrafica(self, c: Character, prof_bonus: int) -> ft.Container:
        xp_next = get_xp_for_level(c.level + 1) if c.level < 20 else None
        xp_label = f"{c.xp:,} / {xp_next:,} PE" if xp_next else f"{c.xp:,} PE (livello max)"

        rows = [
            self._info_row("Nome", c.name),
            self._info_row("Giocatore", c.player_name or "—"),
            self._info_row(
                "Classe",
                c.class_name + (f"  •  {c.subclass}" if c.subclass else "")
            ),
            self._info_row("Livello", str(c.level)),
            self._info_row(
                "Razza",
                c.race + (f" ({c.subrace})" if c.subrace else "")
            ),
            self._info_row("Background", c.background or "—"),
            self._info_row("Allineamento", c.alignment or "—"),
            self._info_row("Punti Esperienza", xp_label),
            self._info_row("Bonus Competenza", f"+{prof_bonus}"),
            self._info_row("Ispirazione", "✦ Attiva" if c.inspiration else "—"),
        ]
        return fantasy_card(ft.Column(rows, spacing=6))

    def _build_fisico(self, c: Character) -> ft.Container:
        rows = [
            self._info_row("Età",        c.age    or "—"),
            self._info_row("Altezza",    c.height or "—"),
            self._info_row("Peso",       c.weight or "—"),
            self._info_row("Occhi",      c.eyes   or "—"),
            self._info_row("Carnagione", c.skin   or "—"),
            self._info_row("Capelli",    c.hair   or "—"),
        ]
        return fantasy_card(ft.Column(rows, spacing=6))

    def _build_personalita(self, c: Character) -> ft.Container:
        return fantasy_card(ft.Column([
            self._text_block("Tratti caratteriali", c.personality_traits),
            ft.Container(height=10),
            self._text_block("Ideali",  c.ideals),
            ft.Container(height=10),
            self._text_block("Legami",  c.bonds),
            ft.Container(height=10),
            self._text_block("Difetti", c.flaws),
        ], spacing=0))

    def _build_storia(self, c: Character) -> ft.Container:
        blocks = [self._text_block("Storia del personaggio", c.backstory)]
        if c.allies_organizations:
            blocks += [ft.Container(height=10),
                       self._text_block("Alleati e organizzazioni", c.allies_organizations)]
        if c.additional_traits:
            blocks += [ft.Container(height=10),
                       self._text_block("Tratti e privilegi aggiuntivi", c.additional_traits)]
        if c.appearance_notes:
            blocks += [ft.Container(height=10),
                       self._text_block("Note sull'aspetto", c.appearance_notes)]
        return fantasy_card(ft.Column(blocks, spacing=0))

    def _build_competenze(self, prof_bonus: int) -> ft.Container:
        # Set nomi competenti per tiri salvezza e abilità
        save_names = {
            p.name for p in self.proficiencies if p.proficiency_type == "save"
        }
        skill_map = {
            p.name: p.is_expert
            for p in self.proficiencies if p.proficiency_type == "skill"
        }

        # Tiri salvezza — una riga per caratteristica
        save_rows = []
        for score_name, abbr, key in zip(ABILITY_SCORES, ABILITY_ABBR, ABILITY_KEYS):
            is_prof = score_name in save_names
            score = getattr(self.character, f"{key}_score")
            mod = get_modifier(score) + (prof_bonus if is_prof else 0)
            mod_str = f"+{mod}" if mod >= 0 else str(mod)
            save_rows.append(
                ft.Row([
                    ft.Icon(
                        ft.Icons.CIRCLE if is_prof else ft.Icons.RADIO_BUTTON_UNCHECKED,
                        size=10,
                        color=COLOR_ACCENT_GOLD if is_prof else COLOR_TEXT_MUTED,
                    ),
                    ft.Container(width=6),
                    ft.Text(score_name, size=12, color=COLOR_TEXT_PRIMARY, expand=True),
                    ft.Text(mod_str, size=12,
                            color=COLOR_ACCENT_GOLD if is_prof else COLOR_TEXT_SECONDARY,
                            weight=ft.FontWeight.BOLD,
                            width=32,
                            text_align=ft.TextAlign.RIGHT,
                            font_family=FONT_MONO),
                ], spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER)
            )

        # Abilità — solo quelle con competenza
        skill_rows = []
        for skill_name, ability_key in SKILLS.items():
            if skill_name not in skill_map:
                continue
            is_expert = skill_map[skill_name]
            score = getattr(self.character, f"{ability_key}_score")
            bonus = prof_bonus * (2 if is_expert else 1)
            mod = get_modifier(score) + bonus
            mod_str = f"+{mod}" if mod >= 0 else str(mod)
            ability_abbr = ABILITY_ABBR[ABILITY_KEYS.index(ability_key)]
            skill_rows.append(
                ft.Row([
                    ft.Icon(
                        ft.Icons.STAR if is_expert else ft.Icons.CIRCLE,
                        size=10,
                        color=COLOR_ACCENT_GOLD,
                    ),
                    ft.Container(width=6),
                    ft.Text(skill_name, size=12, color=COLOR_TEXT_PRIMARY, expand=True),
                    ft.Text(f"({ability_abbr})", size=10, color=COLOR_TEXT_MUTED, width=36),
                    ft.Text(mod_str, size=12,
                            color=COLOR_ACCENT_GOLD,
                            weight=ft.FontWeight.BOLD,
                            width=32,
                            text_align=ft.TextAlign.RIGHT,
                            font_family=FONT_MONO),
                ], spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER)
            )

        if not skill_rows:
            skill_rows.append(muted_text("Nessuna competenza nelle abilità", 12))

        return fantasy_card(ft.Column([
            ft.Text("Tiri Salvezza", size=11, color=COLOR_TEXT_SECONDARY,
                    weight=ft.FontWeight.BOLD),
            ft.Container(height=6),
            *save_rows,
            ft.Container(height=14),
            ft.Text("Abilità", size=11, color=COLOR_TEXT_SECONDARY,
                    weight=ft.FontWeight.BOLD),
            ft.Container(height=6),
            *skill_rows,
        ], spacing=4))

    # ------------------------------------------------------------------
    # Helper widget
    # ------------------------------------------------------------------

    def _info_row(self, label: str, value: str) -> ft.Row:
        return ft.Row(
            [
                ft.Container(
                    content=label_text(label),
                    width=160,
                ),
                ft.Text(value, size=13, color=COLOR_TEXT_PRIMARY, selectable=True),
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def _text_block(self, label: str, text: str) -> ft.Column:
        return ft.Column(
            [
                label_text(label),
                ft.Container(height=4),
                ft.Text(
                    text or "—",
                    size=13,
                    color=COLOR_TEXT_PRIMARY if text else COLOR_TEXT_MUTED,
                    selectable=True,
                ),
            ],
            spacing=0,
        )
