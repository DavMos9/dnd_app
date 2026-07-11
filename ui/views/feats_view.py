"""
Browser di riferimento per i Talenti PHB 5e.

Visualizza tutti i talenti disponibili (da feats.json) come elenco scrollabile.
Cliccando su una card si apre il testo completo in un dialog.
Sezione di riferimento — non legata ad un personaggio specifico.
"""

import flet as ft
import logging
from typing import Any
from config.settings import (
    COLOR_BG_CARD,
    COLOR_TEXT_TITLE, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY, COLOR_TEXT_MUTED,
    COLOR_ACCENT_AMBER, COLOR_BORDER,
    FONT_TITLE,
)
from ui.theme import muted_text
from data.game_data.game_data_loader import GameDataLoader

logger = logging.getLogger(__name__)
_loader = GameDataLoader()


class FeatsView(ft.ListView):
    """
    Browser compendio talenti: lista scrollabile con card cliccabili.
    Eredita da ft.ListView per compatibilità Flet 0.85.3.
    """

    def __init__(self) -> None:
        super().__init__(expand=True, spacing=10, padding=16)
        self._build()

    # ------------------------------------------------------------------

    def _build(self) -> None:
        all_feats: list[dict] = _loader.get_feats()

        self.controls.clear()

        # Header
        self.controls.append(ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.MILITARY_TECH, color=COLOR_ACCENT_AMBER, size=22),
                ft.Container(width=10),
                ft.Column([
                    ft.Text("Compendio Talenti", size=18,
                            weight=ft.FontWeight.BOLD,
                            color=COLOR_TEXT_TITLE,
                            font_family=FONT_TITLE),
                    muted_text(
                        f"{len(all_feats)} talenti PHB 5e  ·  "
                        "Tocca una card per leggere la descrizione completa",
                        size=11,
                    ),
                ], spacing=2),
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            bgcolor=COLOR_BG_CARD,
            border=ft.Border.all(1, COLOR_BORDER),
            border_radius=8,
            padding=ft.Padding.all(14),
        ))

        if not all_feats:
            self.controls.append(ft.Container(
                content=ft.Column([
                    ft.Icon(ft.Icons.MILITARY_TECH, size=56, color=COLOR_BORDER),
                    ft.Container(height=12),
                    ft.Text("Nessun talento disponibile",
                            size=15, color=COLOR_TEXT_MUTED, italic=True),
                    ft.Container(height=4),
                    muted_text("Popola dnd_app/data/game_data/feats.json per abilitare questa sezione.", size=11),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=0),
                alignment=ft.Alignment.CENTER,
                padding=ft.Padding.all(40),
            ))
            return

        # Separatore con contatore
        self.controls.append(ft.Divider(color=COLOR_BORDER, height=1))

        # Cards talenti — ordinate alfabeticamente
        for feat in sorted(all_feats, key=lambda f: f.get("name", "")):
            self.controls.append(self._feat_card(feat))

    # ------------------------------------------------------------------

    def _feat_card(self, feat: dict) -> ft.Container:
        name    = feat.get("name", "")
        prereq  = feat.get("prerequisite") or ""
        desc    = feat.get("description", "")
        ab      = feat.get("ability_bonus")

        # Anteprima: prima frase della descrizione (max ~110 char)
        dot = desc.find(". ")
        preview = desc[: dot + 1] if 0 < dot < 110 else desc[:110] + ("…" if len(desc) > 110 else "")

        # Badge bonus caratteristica
        ab_text = ""
        if isinstance(ab, dict):
            if ab.get("choose_one"):
                opts = [o.upper() for o in ab.get("options", [])]
                ab_text = f"+1 {' / '.join(opts)}"
            else:
                parts = [f"+{v} {k.upper()}" for k, v in ab.items() if isinstance(v, int)]
                ab_text = "  ".join(parts)

        def _show_detail(ev: Any, _name: str = name, _pre: str = prereq,
                          _desc: str = desc, _ab: str = ab_text) -> None:
            page = self.page
            if not page:
                return
            page.show_dialog(ft.AlertDialog(
                title=ft.Row([
                    ft.Icon(ft.Icons.MILITARY_TECH, color=COLOR_ACCENT_AMBER, size=16),
                    ft.Container(width=6),
                    ft.Text(_name, size=14, weight=ft.FontWeight.BOLD,
                            color=COLOR_TEXT_TITLE, expand=True),
                ]),
                content=ft.Column([
                    ft.Container(
                        content=ft.Row([
                            ft.Icon(ft.Icons.LOCK_OUTLINE, size=12, color=COLOR_TEXT_MUTED),
                            ft.Container(width=4),
                            ft.Text(f"Prerequisito: {_pre}", size=11,
                                    color=COLOR_TEXT_MUTED),
                        ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        visible=bool(_pre),
                        padding=ft.Padding.only(bottom=6),
                    ),
                    ft.Container(
                        content=ft.Row([
                            ft.Icon(ft.Icons.ADD_CIRCLE_OUTLINE, size=12,
                                    color=COLOR_ACCENT_AMBER),
                            ft.Container(width=4),
                            ft.Text(_ab, size=11, color=COLOR_ACCENT_AMBER,
                                    weight=ft.FontWeight.BOLD),
                        ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        visible=bool(_ab),
                        padding=ft.Padding.only(bottom=6),
                    ),
                    ft.Text(_desc, size=12, color=COLOR_TEXT_PRIMARY),
                ], scroll=ft.ScrollMode.AUTO, spacing=2),
                actions=[
                    ft.TextButton(
                        "Chiudi",
                        on_click=lambda e: page.pop_dialog(),
                    ),
                ],
                bgcolor=COLOR_BG_CARD,
            ))

        return ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.MILITARY_TECH, size=15, color=COLOR_ACCENT_AMBER),
                    ft.Text(name, size=13, weight=ft.FontWeight.BOLD,
                            color=COLOR_TEXT_TITLE, expand=True),
                    ft.Icon(ft.Icons.CHEVRON_RIGHT, size=16, color=COLOR_TEXT_MUTED),
                ], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Row([
                    ft.Container(
                        content=ft.Row([
                            ft.Icon(ft.Icons.LOCK_OUTLINE, size=10, color=COLOR_TEXT_MUTED),
                            ft.Container(width=3),
                            ft.Text(prereq, size=10, color=COLOR_TEXT_MUTED),
                        ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        visible=bool(prereq),
                    ),
                    ft.Container(
                        content=ft.Text(ab_text, size=10, color=COLOR_ACCENT_AMBER,
                                        weight=ft.FontWeight.BOLD),
                        visible=bool(ab_text),
                    ),
                ], spacing=10),
                ft.Text(preview, size=11, color=COLOR_TEXT_SECONDARY),
            ], spacing=4),
            bgcolor=COLOR_BG_CARD,
            border=ft.Border.all(1, COLOR_BORDER),
            border_radius=8,
            padding=ft.Padding.all(12),
            on_click=_show_detail,
            ink=True,
        )
