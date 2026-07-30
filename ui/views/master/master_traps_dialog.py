"""
Dialog "Generatore Trappole" — Sezione Master, punto 8 del design
(`dnd_app/docs/master_section_design.md`). Due modalità, come da design:

- **Suggerisci**: scegli livello del gruppo di PG + gravità desiderata
  (Imprevisto/Pericoloso/Letale) → mostra CD del tiro salvezza, bonus di
  attacco e dado danno suggeriti dalle 2 tabelle DMG (p.121), con un
  pulsante opzionale per tirare subito il danno.
- **Sfoglia Esempi**: le 8 trappole nominate del manuale (p.121-124), card
  cliccabili che aprono un dialog con il testo completo — stesso stile
  card-e-dialog già in uso in `FeatsView`.

Accessibile da `MasterView` (bottone in header, "Genera Trappola").
"""

from __future__ import annotations

from typing import Any, cast

import flet as ft

from config.settings import (
    COLOR_TEXT_TITLE, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
    COLOR_TEXT_MUTED, COLOR_BORDER, COLOR_BG_CARD, COLOR_BG_PRIMARY,
    COLOR_ACCENT_CRIMSON,
)
from core import trap_generator as tg
from data.game_data.game_data_loader import game_data
from ui.widgets import responsive_dialog_width
from ui import design


def show_traps_dialog(page: ft.Page) -> None:
    """Apre il dialog "Generatore Trappole". Stato in closure, stesso
    pattern già in uso per `show_treasure_generator_dialog`."""

    state: dict[str, Any] = {"tab": "suggest", "char_level": 1, "severity": "imprevisto", "result": {}}

    tab_row = ft.Row(spacing=8)
    body_col = ft.Column(spacing=10)

    # -- Modalità "Suggerisci" -------------------------------------------------
    level_dd = ft.Dropdown(
        label="Livello dei PG",
        value="1",
        options=[ft.DropdownOption(key=str(n), text=f"Livello {n}") for n in range(1, 21)],
        border_color=COLOR_BORDER, focused_border_color=COLOR_ACCENT_CRIMSON,
        bgcolor=COLOR_BG_CARD, label_style=ft.TextStyle(color=COLOR_TEXT_SECONDARY),
    )
    severity_group = ft.RadioGroup(
        value="imprevisto",
        content=ft.Row(
            [
                ft.Radio(value="imprevisto", label="Imprevisto"),
                ft.Radio(value="pericoloso", label="Pericoloso"),
                ft.Radio(value="letale", label="Letale"),
            ],
        ),
    )
    suggest_result_col = ft.Column(spacing=6)

    def _render_suggest_result() -> None:
        suggest_result_col.controls.clear()
        r = state["result"]
        if not r:
            suggest_result_col.controls.append(
                ft.Text("Premi «Suggerisci» per calcolare i valori.", size=12, color=COLOR_TEXT_MUTED)
            )
        else:
            suggest_result_col.controls.extend([
                ft.Text(f"Gravità: {r['severity_label']} (PG livello {r['char_level_range'] or '?'})",
                        size=13, weight=ft.FontWeight.BOLD, color=COLOR_TEXT_TITLE),
                ft.Text(f"CD Tiro Salvezza: {r['save_dc']}", size=13, color=COLOR_TEXT_PRIMARY),
                ft.Text(f"Bonus di Attacco: {r['attack_bonus']}", size=13, color=COLOR_TEXT_PRIMARY),
                ft.Text(f"Dado Danno: {r['damage_dice']}", size=13, color=COLOR_TEXT_PRIMARY),
            ])
            if r.get("rolled_damage") is not None:
                suggest_result_col.controls.append(
                    ft.Text(f"Danno tirato: {r['rolled_damage']}", size=14, weight=ft.FontWeight.BOLD,
                             color=COLOR_ACCENT_CRIMSON)
                )
        try:
            suggest_result_col.update()
        except RuntimeError:
            pass

    def _on_level_change(ev: Any) -> None:
        try:
            state["char_level"] = int(level_dd.value or 1)
        except ValueError:
            state["char_level"] = 1

    def _on_severity_change(ev: Any) -> None:
        state["severity"] = severity_group.value or "imprevisto"

    def _on_suggest(ev: Any) -> None:
        state["result"] = tg.suggest_trap_stats(state["char_level"], state["severity"])
        _render_suggest_result()

    def _on_roll_damage(ev: Any) -> None:
        if not state["result"]:
            _on_suggest(ev)
        state["result"]["rolled_damage"] = tg.roll_trap_damage(state["char_level"], state["severity"])
        _render_suggest_result()

    suggest_view = ft.Column(
        [
            level_dd,
            severity_group,
            ft.Row(
                [
                    ft.ElevatedButton(
                        "Suggerisci", icon=ft.Icons.CALCULATE, on_click=_on_suggest,
                        style=ft.ButtonStyle(bgcolor=COLOR_ACCENT_CRIMSON, color=design.T().on_primary,
                                              shape=ft.RoundedRectangleBorder(radius=4)),
                    ),
                    ft.OutlinedButton("Tira Danno", icon=ft.Icons.CASINO, on_click=_on_roll_damage),
                ],
                spacing=8,
            ),
            ft.Divider(height=1, color=COLOR_BORDER),
            ft.Container(
                content=suggest_result_col, bgcolor=COLOR_BG_PRIMARY,
                border_radius=6, padding=ft.Padding.all(12),
            ),
        ],
        spacing=10,
    )

    level_dd.on_select = _on_level_change
    severity_group.on_change = _on_severity_change

    # -- Modalità "Sfoglia Esempi" ----------------------------------------------
    def _open_trap_detail(trap: dict[str, Any]) -> None:
        rows: list[ft.Control] = [
            ft.Text(f"Trappola {trap.get('type', '')}", size=12, italic=True, color=COLOR_TEXT_MUTED),
            ft.Container(height=6),
            ft.Text(trap.get("description", ""), size=13, color=COLOR_TEXT_PRIMARY),
        ]
        for v in trap.get("variants", []):
            rows.append(ft.Container(height=10))
            rows.append(ft.Text(v.get("name", ""), size=14, weight=ft.FontWeight.BOLD, color=COLOR_TEXT_TITLE))
            rows.append(ft.Text(v.get("description", ""), size=13, color=COLOR_TEXT_PRIMARY))

        def _close_detail(ev: Any) -> None:
            page.pop_dialog()

        detail_dlg = ft.AlertDialog(
            title=ft.Text(trap.get("name", ""), size=16, weight=ft.FontWeight.BOLD, color=COLOR_TEXT_TITLE),
            content=ft.Column(rows, width=responsive_dialog_width(page, 380), height=420,
                              scroll=ft.ScrollMode.AUTO, tight=True),
            actions=cast(list[ft.Control], [ft.TextButton("Chiudi", on_click=_close_detail)]),
            bgcolor=COLOR_BG_CARD,
        )
        page.show_dialog(detail_dlg)

    def _trap_card(trap: dict[str, Any]) -> ft.Container:
        n_variants = len(trap.get("variants", []))
        subtitle = f"{n_variants} varianti" if n_variants else (trap.get("description", "")[:70] + "…")
        return ft.Container(
            content=ft.Column(
                [
                    ft.Text(trap.get("name", ""), size=14, weight=ft.FontWeight.BOLD, color=COLOR_TEXT_TITLE),
                    ft.Text(f"Trappola {trap.get('type', '')} — {subtitle}", size=11, color=COLOR_TEXT_MUTED),
                ],
                spacing=2,
            ),
            padding=ft.Padding.symmetric(horizontal=12, vertical=8),
            bgcolor=COLOR_BG_CARD,
            border=ft.Border.all(1, COLOR_BORDER),
            border_radius=6,
            on_click=lambda e, t=trap: _open_trap_detail(t),
            ink=True,
        )

    examples_view = ft.Column(
        [_trap_card(t) for t in game_data.get_example_traps()],
        spacing=6,
    )

    # -- Tab switching ------------------------------------------------------
    def _render_body() -> None:
        body_col.controls.clear()
        body_col.controls.append(suggest_view if state["tab"] == "suggest" else examples_view)
        try:
            body_col.update()
        except RuntimeError:
            pass

    def _tab_button(key: str, label: str) -> ft.Control:
        is_sel = state["tab"] == key
        return ft.Container(
            content=ft.Text(label, size=12, weight=ft.FontWeight.BOLD if is_sel else ft.FontWeight.NORMAL,
                             color=COLOR_ACCENT_CRIMSON if is_sel else COLOR_TEXT_SECONDARY),
            padding=ft.Padding.symmetric(horizontal=12, vertical=6),
            border=ft.Border.only(bottom=ft.BorderSide(2, COLOR_ACCENT_CRIMSON if is_sel else "transparent")),
            on_click=lambda e, k=key: _on_tab_click(k),
            ink=True,
        )

    def _rebuild_tab_row() -> None:
        tab_row.controls.clear()
        tab_row.controls.append(_tab_button("suggest", "Suggerisci"))
        tab_row.controls.append(_tab_button("examples", "Sfoglia Esempi"))
        try:
            tab_row.update()
        except RuntimeError:
            pass

    def _on_tab_click(key: str) -> None:
        if state["tab"] == key:
            return
        state["tab"] = key
        _rebuild_tab_row()
        _render_body()

    _rebuild_tab_row()
    _render_suggest_result()
    _render_body()

    def _close(ev: Any) -> None:
        page.pop_dialog()

    content = ft.Column(
        [tab_row, ft.Divider(height=1, color=COLOR_BORDER), body_col],
        spacing=10, scroll=ft.ScrollMode.AUTO,
        width=responsive_dialog_width(page, 420), height=520, tight=True,
    )

    dlg = ft.AlertDialog(
        title=ft.Text("Generatore Trappole", size=16, weight=ft.FontWeight.BOLD, color=COLOR_TEXT_TITLE),
        content=content,
        actions=cast(list[ft.Control], [ft.TextButton("Chiudi", on_click=_close)]),
        bgcolor=COLOR_BG_CARD,
    )
    page.show_dialog(dlg)
