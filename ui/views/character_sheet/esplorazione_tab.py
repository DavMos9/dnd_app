"""
Tab Esplorazione della scheda personaggio.

Struttura (ListView scrollabile):
  - Percezione Passiva   — valore calcolato (10 + mod SAG + eventuale competenza)
  - Sensi                — scurovisione, altri sensi speciali da razza
  - Velocità             — base + nuoto / scalata / volo (se presenti)
  - Lingue               — dalla scheda proficiencies (type="language")
  - Strumenti            — dalla scheda proficiencies (type="tool")
  - Tiri Salvezza        — griglia compatta 6 valori con indicatore competenza
  - Abilità              — griglia compatta 18 abilità con modificatore calcolato
"""

import flet as ft
import logging
from typing import cast
from config.settings import *
from data.models import Character, CharacterProficiency
import data.repositories.character_repo as character_repo
from ui.theme import section_header, body_text, muted_text, label_text

logger = logging.getLogger(__name__)

# Caratteristica abbreviata → nome intero italiano
_STAT_LABEL: dict[str, str] = {
    "str": "Forza",
    "dex": "Destrezza",
    "con": "Costituzione",
    "int": "Intelligenza",
    "wis": "Saggezza",
    "cha": "Carisma",
}


class EsplorazioneTab(ft.ListView):
    """
    Tab esplorazione: sensi, velocità, lingue, strumenti,
    tiri salvezza compatti, abilità compatte.
    Eredita da ft.ListView per scroll corretto in Flet 0.85.3.
    """

    def __init__(self, character: Character):
        super().__init__(expand=True, spacing=12, padding=16)
        self.character = character
        self._profs: list[CharacterProficiency] = character_repo.get_proficiencies(character.id)
        self._build()

    # ------------------------------------------------------------------
    # Build principale
    # ------------------------------------------------------------------

    def _build(self):
        c = self.character
        pb = get_proficiency_bonus(c.level)

        # Set competenze per lookup rapido
        self._skill_profs: dict[str, bool] = {}   # nome abilità → is_expert
        self._save_profs: set[str] = set()        # nome caratteristica

        for p in self._profs:
            if p.proficiency_type == "skill":
                self._skill_profs[p.name] = p.is_expert
            elif p.proficiency_type in ("save", "saving_throw"):
                self._save_profs.add(p.name)

        self.controls = [
            self._section_percezione(c, pb),
            section_header("Sensi e Velocità"),
            self._section_sensi(c),
            section_header("Lingue"),
            self._section_lingue(),
            section_header("Strumenti"),
            self._section_strumenti(),
            section_header("Tiri Salvezza"),
            self._section_saves(c, pb),
            section_header("Abilità"),
            self._section_skills(c, pb),
        ]

    # ------------------------------------------------------------------
    # Percezione passiva
    # ------------------------------------------------------------------

    def _section_percezione(self, c: Character, pb: int) -> ft.Container:
        wis_mod = get_modifier(c.wis_score)
        has_perc = "Percezione" in self._skill_profs
        is_expert = self._skill_profs.get("Percezione", False)

        bonus = pb * (2 if is_expert else 1) if has_perc else 0
        passive = 10 + wis_mod + bonus

        # Colore in base al valore
        if passive >= 18:
            color = COLOR_ACCENT_GREEN
        elif passive >= 14:
            color = COLOR_ACCENT_BLUE
        else:
            color = COLOR_TEXT_PRIMARY

        indicator = ""
        if is_expert:
            indicator = "★ maestria"
        elif has_perc:
            indicator = "● competente"

        return ft.Container(
            content=ft.Row(
                [
                    ft.Column(
                        [
                            label_text("Percezione Passiva", 9),
                            ft.Text(
                                str(passive),
                                size=42,
                                weight=ft.FontWeight.BOLD,
                                color=color,
                                font_family=FONT_MONO,
                            ),
                            muted_text(f"10 + {wis_mod:+d} SAG" + (f" + {bonus} comp." if bonus else "") +
                                       (f"  {indicator}" if indicator else ""), size=11),
                        ],
                        spacing=2,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            bgcolor=COLOR_BG_CARD,
            padding=ft.Padding.symmetric(horizontal=16, vertical=20),
            border=ft.Border(
                top=ft.BorderSide(3, COLOR_ACCENT_CRIMSON),
                left=ft.BorderSide(1, COLOR_BORDER),
                right=ft.BorderSide(1, COLOR_BORDER),
                bottom=ft.BorderSide(1, COLOR_BORDER),
            ),
            border_radius=6,
        )

    # ------------------------------------------------------------------
    # Sensi e Velocità
    # ------------------------------------------------------------------

    def _section_sensi(self, c: Character) -> ft.Container:
        race_info = RACE_DATA.get(c.race, {})
        darkvision = race_info.get("darkvision", 0)

        rows: list[ft.Control] = []

        # Velocità — base + varianti speciali
        speed_rows: list[tuple[str, str]] = [
            ("Camminata", f"{c.speed or 9} m"),
        ]
        # Velocità speciali da tratti razziali (rilevamento testuale nei traits)
        for trait in race_info.get("traits", []):
            t_lower = trait.lower()
            if "nuoto" in t_lower or "swim" in t_lower:
                speed_rows.append(("Nuoto", f"{c.speed or 9} m"))
            elif "scalat" in t_lower or "climb" in t_lower:
                speed_rows.append(("Scalata", f"{c.speed or 9} m"))
            elif "volo" in t_lower or "fly" in t_lower:
                speed_rows.append(("Volo", f"{c.speed or 9} m"))

        for label, value in speed_rows:
            rows.append(self._info_row(label, value))

        # Separatore
        rows.append(ft.Container(height=8))

        # Scurovisione
        if darkvision:
            rows.append(self._info_row("Scurovisione", f"{darkvision} m"))
        else:
            rows.append(self._info_row("Scurovisione", "Nessuna"))

        return self._compact_card(rows)

    # ------------------------------------------------------------------
    # Lingue
    # ------------------------------------------------------------------

    def _section_lingue(self) -> ft.Container:
        lingue = [p.name for p in self._profs if p.proficiency_type == "language"]

        if not lingue:
            return self._compact_card([muted_text("Nessuna lingua registrata", 12)])

        rows: list[ft.Control] = [
            ft.Text(
                ", ".join(sorted(lingue)),
                size=13,
                color=COLOR_TEXT_PRIMARY,
                font_family=FONT_BODY,
            )
        ]
        return self._compact_card(rows)

    # ------------------------------------------------------------------
    # Strumenti
    # ------------------------------------------------------------------

    def _section_strumenti(self) -> ft.Container:
        strumenti = [p for p in self._profs if p.proficiency_type == "tool"]

        if not strumenti:
            return self._compact_card([muted_text("Nessuno strumento registrato", 12)])

        rows: list[ft.Control] = []
        for s in sorted(strumenti, key=lambda x: x.name):
            indicator = "★" if s.is_expert else "●"
            color = COLOR_ACCENT_BLUE if s.is_expert else COLOR_ACCENT_CRIMSON
            rows.append(
                ft.Row(
                    [
                        ft.Text(indicator, size=12, color=color, width=16),
                        ft.Text(s.name, size=13, color=COLOR_TEXT_PRIMARY, expand=True),
                        muted_text("maestria" if s.is_expert else "competenza", 11),
                    ],
                    spacing=4,
                )
            )
        return self._compact_card(rows)

    # ------------------------------------------------------------------
    # Tiri Salvezza (griglia compatta)
    # ------------------------------------------------------------------

    def _section_saves(self, c: Character, pb: int) -> ft.Container:
        scores = {
            "str": c.str_score, "dex": c.dex_score, "con": c.con_score,
            "int": c.int_score, "wis": c.wis_score, "cha": c.cha_score,
        }

        cells: list[ft.Control] = []
        for key, full_name, abbr in zip(
            ABILITY_KEYS, ABILITY_SCORES, ABILITY_ABBR
        ):
            score = scores[key]
            base_mod = get_modifier(score)
            prof = full_name in self._save_profs
            total = base_mod + (pb if prof else 0)
            total_str = f"+{total}" if total >= 0 else str(total)

            indicator_color = COLOR_ACCENT_CRIMSON if prof else COLOR_BORDER
            text_color = COLOR_TEXT_PRIMARY if prof else COLOR_TEXT_MUTED

            cells.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Container(
                                        width=6, height=6,
                                        bgcolor=indicator_color,
                                        border_radius=3,
                                    ),
                                    ft.Text(abbr, size=9, color=COLOR_TEXT_SECONDARY,
                                            weight=ft.FontWeight.BOLD,
                                            style=ft.TextStyle(letter_spacing=1)),
                                ],
                                spacing=4,
                                alignment=ft.MainAxisAlignment.CENTER,
                            ),
                            ft.Text(
                                total_str,
                                size=16,
                                weight=ft.FontWeight.BOLD,
                                color=text_color,
                                font_family=FONT_MONO,
                                text_align=ft.TextAlign.CENTER,
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=2,
                    ),
                    expand=True,
                    bgcolor=COLOR_BG_SECONDARY if prof else COLOR_BG_CARD,
                    padding=ft.Padding.symmetric(horizontal=4, vertical=8),
                    border=ft.Border.all(1, COLOR_BORDER),
                    border_radius=4,
                )
            )

        return ft.Container(
            content=ft.Row(cells, spacing=4),
            bgcolor=COLOR_BG_CARD,
            padding=ft.Padding.symmetric(horizontal=12, vertical=12),
            border=ft.Border(
                top=ft.BorderSide(3, COLOR_ACCENT_CRIMSON),
                left=ft.BorderSide(1, COLOR_BORDER),
                right=ft.BorderSide(1, COLOR_BORDER),
                bottom=ft.BorderSide(1, COLOR_BORDER),
            ),
            border_radius=6,
        )

    # ------------------------------------------------------------------
    # Abilità (griglia compatta 3 colonne)
    # ------------------------------------------------------------------

    def _section_skills(self, c: Character, pb: int) -> ft.Container:
        scores = {
            "str": c.str_score, "dex": c.dex_score, "con": c.con_score,
            "int": c.int_score, "wis": c.wis_score, "cha": c.cha_score,
        }

        skill_items: list[ft.Control] = []
        for skill_name, stat_key in sorted(SKILLS.items()):
            score = scores.get(stat_key, 10)
            base_mod = get_modifier(score)
            is_expert = self._skill_profs.get(skill_name, False) if skill_name in self._skill_profs else None
            is_prof = skill_name in self._skill_profs

            if is_expert:
                bonus = pb * 2
                indicator = "★"
                ind_color = COLOR_ACCENT_BLUE
            elif is_prof:
                bonus = pb
                indicator = "●"
                ind_color = COLOR_ACCENT_CRIMSON
            else:
                bonus = 0
                indicator = "○"
                ind_color = COLOR_BORDER

            total = base_mod + bonus
            total_str = f"+{total}" if total >= 0 else str(total)
            abbr = ABILITY_ABBR[ABILITY_KEYS.index(stat_key)]

            skill_items.append(
                ft.Row(
                    [
                        ft.Text(indicator, size=11, color=ind_color, width=14),
                        ft.Text(
                            total_str,
                            size=12,
                            weight=ft.FontWeight.BOLD,
                            color=COLOR_TEXT_PRIMARY if is_prof else COLOR_TEXT_MUTED,
                            font_family=FONT_MONO,
                            width=32,
                            text_align=ft.TextAlign.RIGHT,
                        ),
                        ft.Text(
                            skill_name,
                            size=12,
                            color=COLOR_TEXT_PRIMARY if is_prof else COLOR_TEXT_SECONDARY,
                            expand=True,
                        ),
                        muted_text(abbr, 10),
                    ],
                    spacing=4,
                )
            )

        # Dividi in 2 colonne
        mid = (len(skill_items) + 1) // 2
        col_left = skill_items[:mid]
        col_right = skill_items[mid:]

        return ft.Container(
            content=ft.Row(
                [
                    ft.Column(cast(list[ft.Control], col_left), spacing=6, expand=True),
                    ft.Container(width=1, bgcolor=COLOR_BORDER),
                    ft.Column(cast(list[ft.Control], col_right), spacing=6, expand=True),
                ],
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            bgcolor=COLOR_BG_CARD,
            padding=ft.Padding.symmetric(horizontal=12, vertical=12),
            border=ft.Border(
                top=ft.BorderSide(3, COLOR_ACCENT_CRIMSON),
                left=ft.BorderSide(1, COLOR_BORDER),
                right=ft.BorderSide(1, COLOR_BORDER),
                bottom=ft.BorderSide(1, COLOR_BORDER),
            ),
            border_radius=6,
        )

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    def _info_row(self, label: str, value: str) -> ft.Row:
        return ft.Row(
            [
                muted_text(label, 12),
                ft.Text(value, size=13, color=COLOR_TEXT_PRIMARY,
                        weight=ft.FontWeight.BOLD, font_family=FONT_BODY),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

    def _compact_card(self, rows: list[ft.Control]) -> ft.Container:
        return ft.Container(
            content=ft.Column(rows, spacing=6),
            bgcolor=COLOR_BG_CARD,
            padding=ft.Padding.symmetric(horizontal=12, vertical=12),
            border=ft.Border(
                top=ft.BorderSide(3, COLOR_ACCENT_CRIMSON),
                left=ft.BorderSide(1, COLOR_BORDER),
                right=ft.BorderSide(1, COLOR_BORDER),
                bottom=ft.BorderSide(1, COLOR_BORDER),
            ),
            border_radius=6,
        )

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    def _refresh(self):
        refreshed = character_repo.get_by_id(self.character.id)
        if refreshed:
            self.character = refreshed
        self._profs = character_repo.get_proficiencies(self.character.id)
        self.controls.clear()
        self._build()
        try:
            self.update()
        except RuntimeError:
            pass
