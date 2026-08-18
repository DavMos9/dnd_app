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
        border_color=design.T().border, focused_border_color=design.T().primary,
        bgcolor=design.T().surface, label_style=ft.TextStyle(color=design.T().text_2),
        border_radius=design.field_style()['border_radius'], text_style=design.field_style()['text_style'])
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
                ft.Text("Premi «Suggerisci» per calcolare i valori.", size=12, color=design.T().text_3)
            )
        else:
            suggest_result_col.controls.extend([
                ft.Text(f"Gravità: {r['severity_label']} (PG livello {r['char_level_range'] or '?'})",
                        size=13, weight=ft.FontWeight.BOLD, color=design.T().text),
                ft.Text(f"CD Tiro Salvezza: {r['save_dc']}", size=13, color=design.T().text),
                ft.Text(f"Bonus di Attacco: {r['attack_bonus']}", size=13, color=design.T().text),
                ft.Text(f"Dado Danno: {r['damage_dice']}", size=13, color=design.T().text),
            ])
            if r.get("rolled_damage") is not None:
                suggest_result_col.controls.append(
                    ft.Text(f"Danno tirato: {r['rolled_damage']}", size=14, weight=ft.FontWeight.BOLD,
                             color=design.T().primary)
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

    # Audit anti-AI-slop (Arcane Ledger): scheletro condiviso `generator_
    # dialog_shell()` per la scheda "Suggerisci" — stessa card "risultato"
    # (level=2, accento primario) di ogni altro generatore, invece del
    # riquadro costruito a mano. Titolo/icona distinti dall'etichetta della
    # scheda ("Suggerisci" sopra) solo per differenziare visivamente
    # l'intestazione dal tab attivo, nessun cambio di dato/callback.
    suggest_form = ft.Column(
        [
            level_dd,
            severity_group,
            ft.Row(
                [
                    ft.ElevatedButton(
                        "Suggerisci", icon=ft.Icons.CALCULATE, on_click=_on_suggest,
                        style=ft.ButtonStyle(bgcolor=design.T().primary_fill, color=design.T().on_primary_fill),
                    ),
                    ft.OutlinedButton("Tira Danno", icon=ft.Icons.CASINO, on_click=_on_roll_damage),
                ],
                spacing=8, wrap=True,
            ),
        ],
        spacing=design.Space.MD,
    )
    suggest_view = design.generator_dialog_shell(
        "Valori Suggeriti", ft.Icons.CALCULATE, suggest_form, suggest_result_col, actions=[],
    )

    level_dd.on_select = _on_level_change
    severity_group.on_change = _on_severity_change

    # -- Modalità "Sfoglia Esempi" ----------------------------------------------
    def _open_trap_detail(trap: dict[str, Any]) -> None:
        rows: list[ft.Control] = [
            ft.Text(f"Trappola {trap.get('type', '')}", size=12, italic=True, color=design.T().text_3),
            ft.Container(height=6),
            ft.Text(trap.get("description", ""), size=13, color=design.T().text),
        ]
        for v in trap.get("variants", []):
            rows.append(ft.Container(height=10))
            rows.append(ft.Text(v.get("name", ""), size=14, weight=ft.FontWeight.BOLD, color=design.T().text))
            rows.append(ft.Text(v.get("description", ""), size=13, color=design.T().text))

        def _close_detail(ev: Any) -> None:
            page.pop_dialog()

        detail_dlg = ft.AlertDialog(
            title=design.dialog_title(trap.get("name", "")),
            content=ft.Column(rows, width=responsive_dialog_width(page, 380), height=420,
                              scroll=ft.ScrollMode.AUTO, tight=True),
            actions=cast(list[ft.Control], [ft.TextButton("Chiudi", on_click=_close_detail)]),
        )
        page.show_dialog(detail_dlg)

    def _trap_card(trap: dict[str, Any]) -> ft.Container:
        n_variants = len(trap.get("variants", []))
        subtitle = f"{n_variants} varianti" if n_variants else (trap.get("description", "")[:70] + "…")
        return ft.Container(
            content=ft.Column(
                [
                    ft.Text(trap.get("name", ""), size=14, weight=ft.FontWeight.BOLD, color=design.T().text),
                    ft.Text(f"Trappola {trap.get('type', '')} — {subtitle}", size=11, color=design.T().text_3),
                ],
                spacing=2,
            ),
            padding=ft.Padding.symmetric(horizontal=12, vertical=8),
            bgcolor=design.T().surface,
            shadow=design.elevation(1),
            border_radius=design.Radius.MD,
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
                             color=design.T().primary if is_sel else design.T().text_2),
            padding=ft.Padding.symmetric(horizontal=12, vertical=6),
            border=ft.Border.only(bottom=ft.BorderSide(2, design.T().primary if is_sel else "transparent")),
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
        [tab_row, ft.Divider(height=1, color=design.T().border), body_col],
        spacing=10, scroll=ft.ScrollMode.AUTO,
        width=responsive_dialog_width(page, 420), height=520, tight=True,
    )

    dlg = ft.AlertDialog(
        title=design.dialog_title("Generatore Trappole"),
        content=content,
        actions=cast(list[ft.Control], [ft.TextButton("Chiudi", on_click=_close)]),
    )
    page.show_dialog(dlg)
