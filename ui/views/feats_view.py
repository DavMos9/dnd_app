"""
Browser di riferimento per i Talenti PHB 5e.

Visualizza tutti i talenti disponibili (da feats.json) come elenco scrollabile.
Cliccando su una card si apre il testo completo in un dialog.
Sezione di riferimento — non legata ad un personaggio specifico.
"""

import flet as ft
import logging
from typing import Any
from data.game_data.game_data_loader import GameDataLoader
from ui import design

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

        # Header — unico momento "hero" della schermata (audit Arcane Ledger).
        self.controls.append(design.card(
            ft.Row([
                design.icon_badge(ft.Icons.MILITARY_TECH, tone="warning"),
                ft.Container(width=design.Space.MD),
                design.hero_title(
                    "Compendio Talenti",
                    f"{len(all_feats)} talenti PHB 5e  ·  "
                    "Tocca una card per leggere la descrizione completa",
                ),
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER, wrap=True),
            hero=True,
        ))

        if not all_feats:
            self.controls.append(design.empty_state(
                ft.Icons.MILITARY_TECH,
                "Nessun talento disponibile",
                "Popola dnd_app/data/game_data/feats.json per abilitare questa sezione.",
            ))
            return

        # Separatore con contatore
        self.controls.append(ft.Divider(color=design.T().border, height=1))

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
                title=design.dialog_title(_name, ft.Icons.MILITARY_TECH, tone="warning"),
                content=ft.Column([
                    ft.Container(
                        content=ft.Row([
                            ft.Icon(ft.Icons.LOCK_OUTLINE, size=12, color=design.T().text_3),
                            ft.Container(width=4),
                            ft.Text(f"Prerequisito: {_pre}", size=11,
                                    color=design.T().text_3),
                        ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        visible=bool(_pre),
                        padding=ft.Padding.only(bottom=6),
                    ),
                    ft.Container(
                        content=ft.Row([
                            ft.Icon(ft.Icons.ADD_CIRCLE_OUTLINE, size=12,
                                    color=design.T().warning),
                            ft.Container(width=4),
                            ft.Text(_ab, size=11, color=design.T().warning,
                                    weight=ft.FontWeight.BOLD),
                        ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        visible=bool(_ab),
                        padding=ft.Padding.only(bottom=6),
                    ),
                    ft.Text(_desc, size=12, color=design.T().text),
                ], scroll=ft.ScrollMode.AUTO, spacing=2),
                actions=[
                    ft.TextButton(
                        "Chiudi",
                        on_click=lambda e: page.pop_dialog(),
                    ),
                ],
            ))

        return design.card(
            ft.Column([
                ft.Row([
                    ft.Text(name, size=13, weight=ft.FontWeight.BOLD,
                            color=design.T().text, expand=True),
                    ft.Icon(ft.Icons.CHEVRON_RIGHT, size=16, color=design.T().text_3),
                ], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Row([
                    ft.Container(
                        content=ft.Row([
                            ft.Icon(ft.Icons.LOCK_OUTLINE, size=10, color=design.T().text_3),
                            ft.Container(width=3),
                            ft.Text(prereq, size=10, color=design.T().text_3),
                        ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        visible=bool(prereq),
                    ),
                    ft.Container(
                        content=design.chip(ab_text or "—", "warning"),
                        visible=bool(ab_text),
                    ),
                ], spacing=10),
                ft.Text(preview, size=11, color=design.T().text_2),
            ], spacing=4),
            accent=design.T().warning,
            padding=design.Space.MD,
            on_click=_show_detail,
        )
