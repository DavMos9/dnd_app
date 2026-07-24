"""
Dialog "Malattie, Veleni e Follia" — Sezione Master, punto 9 del design
(`dnd_app/docs/master_section_design.md`). Puro riferimento di consultazione
per il Master, nessuna scrittura sui personaggi (a differenza del
Generatore Tesori, qui non c'è nulla da "aggiungere all'inventario" — sono
regole/effetti da applicare a mano dal Master). 3 sotto-tab, come da design:

- **Malattie**: le 3 malattie di esempio del DMG (p.256) — card cliccabili,
  dialog con il testo completo.
- **Veleni**: i 14 veleni della tabella DMG (p.257-258) — card con
  tipo/prezzo, dialog con la meccanica completa; più il testo introduttivo
  sui 4 tipi di veleno e le note su acquisto/fabbricazione.
- **Follia**: le 3 tabelle d100 (Temporanea/Duratura/Indeterminata, p.259-260)
  — dropdown di scelta tabella + pulsante "Tira 1d100" che mostra il tiro e
  l'effetto risultante, più i testi di contesto (Impazzire/Effetti/Curare).

Accessibile da `MasterView` (bottone in header, "Malattie e Veleni").
"""

from __future__ import annotations

from typing import Any, cast

import flet as ft

from config.settings import (
    COLOR_TEXT_TITLE, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
    COLOR_TEXT_MUTED, COLOR_BORDER, COLOR_BG_CARD, COLOR_BG_PRIMARY,
    COLOR_ACCENT_CRIMSON,
)
from data.game_data.game_data_loader import game_data
from ui.widgets import responsive_dialog_width


_MADNESS_KIND_LABELS = {
    "temporanea": "Temporanea (1d10 minuti)",
    "duratura": "Duratura (1d10 x 10 ore)",
    "indeterminata": "Indeterminata (permanente)",
}


def show_health_hazards_dialog(page: ft.Page) -> None:
    """Apre il dialog "Malattie, Veleni e Follia". Stato in closure, stesso
    pattern già in uso per `show_traps_dialog`/`show_treasure_generator_dialog`."""

    state: dict[str, Any] = {"tab": "diseases", "madness_kind": "temporanea", "rolled": None}

    tab_row = ft.Row(spacing=8)
    body_col = ft.Column(spacing=10)

    # -- Helper card-e-dialog condiviso ------------------------------------
    def _text_dialog(title: str, body_controls: list[ft.Control]) -> None:
        def _close(ev: Any) -> None:
            page.pop_dialog()

        dlg = ft.AlertDialog(
            title=ft.Text(title, size=16, weight=ft.FontWeight.BOLD, color=COLOR_TEXT_TITLE),
            content=ft.Column(body_controls, width=responsive_dialog_width(page, 380), height=420,
                              scroll=ft.ScrollMode.AUTO, tight=True),
            actions=cast(list[ft.Control], [ft.TextButton("Chiudi", on_click=_close)]),
            bgcolor=COLOR_BG_CARD,
        )
        page.show_dialog(dlg)

    def _simple_card(name: str, subtitle: str, on_click) -> ft.Container:
        return ft.Container(
            content=ft.Column(
                [
                    ft.Text(name, size=14, weight=ft.FontWeight.BOLD, color=COLOR_TEXT_TITLE),
                    ft.Text(subtitle, size=11, color=COLOR_TEXT_MUTED),
                ],
                spacing=2,
            ),
            padding=ft.Padding.symmetric(horizontal=12, vertical=8),
            bgcolor=COLOR_BG_CARD,
            border=ft.Border.all(1, COLOR_BORDER),
            border_radius=6,
            on_click=on_click,
            ink=True,
        )

    # -- Modalità "Malattie" -------------------------------------------------
    def _open_disease_detail(disease: dict[str, Any]) -> None:
        _text_dialog(
            disease.get("name", ""),
            [ft.Text(disease.get("description", ""), size=13, color=COLOR_TEXT_PRIMARY)],
        )

    diseases_view = ft.Column(
        [
            _simple_card(
                d.get("name", ""), "Malattia — tocca per il testo completo",
                lambda e, dd=d: _open_disease_detail(dd),
            )
            for d in game_data.get_diseases()
        ],
        spacing=6,
    )

    # -- Modalità "Veleni" ----------------------------------------------------
    def _open_poison_detail(poison: dict[str, Any]) -> None:
        _text_dialog(
            poison.get("name", ""),
            [
                ft.Text(f"Tipo: {poison.get('type', '')} — Prezzo: {poison.get('price', '')}",
                        size=12, italic=True, color=COLOR_TEXT_MUTED),
                ft.Container(height=6),
                ft.Text(poison.get("description", ""), size=13, color=COLOR_TEXT_PRIMARY),
            ],
        )

    def _open_poison_types_info(ev: Any) -> None:
        _text_dialog(
            "Tipi di Veleno",
            [ft.Text(game_data.get_poison_types_intro(), size=13, color=COLOR_TEXT_PRIMARY)],
        )

    def _open_poison_acquiring_info(ev: Any) -> None:
        _text_dialog(
            "Acquistare i Veleni",
            [ft.Text(game_data.get_poison_acquiring_text(), size=13, color=COLOR_TEXT_PRIMARY)],
        )

    def _open_poison_crafting_info(ev: Any) -> None:
        _text_dialog(
            "Fabbricare ed Estrarre i Veleni",
            [ft.Text(game_data.get_poison_crafting_text(), size=13, color=COLOR_TEXT_PRIMARY)],
        )

    poisons_view = ft.Column(
        [
            ft.Row(
                [
                    ft.OutlinedButton("Tipi di Veleno", icon=ft.Icons.INFO_OUTLINE, on_click=_open_poison_types_info),
                    ft.OutlinedButton("Acquistare", icon=ft.Icons.SHOPPING_BAG_OUTLINED, on_click=_open_poison_acquiring_info),
                    ft.OutlinedButton("Fabbricare", icon=ft.Icons.SCIENCE_OUTLINED, on_click=_open_poison_crafting_info),
                ],
                spacing=6, wrap=True,
            ),
            ft.Divider(height=1, color=COLOR_BORDER),
        ]
        + [
            _simple_card(
                p.get("name", ""), f"{p.get('type', '')} — {p.get('price', '')}",
                lambda e, pp=p: _open_poison_detail(pp),
            )
            for p in game_data.get_poisons()
        ],
        spacing=6,
    )

    # -- Modalità "Follia" ------------------------------------------------------
    madness_dd = ft.Dropdown(
        label="Tabella",
        value="temporanea",
        options=[ft.DropdownOption(key=k, text=v) for k, v in _MADNESS_KIND_LABELS.items()],
        border_color=COLOR_BORDER, focused_border_color=COLOR_ACCENT_CRIMSON,
        bgcolor=COLOR_BG_CARD, label_style=ft.TextStyle(color=COLOR_TEXT_SECONDARY),
    )
    madness_result_col = ft.Column(spacing=6)

    def _render_madness_result() -> None:
        madness_result_col.controls.clear()
        r = state["rolled"]
        if not r:
            madness_result_col.controls.append(
                ft.Text("Premi «Tira 1d100» per estrarre un effetto.", size=12, color=COLOR_TEXT_MUTED)
            )
        else:
            madness_result_col.controls.extend([
                ft.Text(f"Tiro: {r['roll']} (intervallo {r['range']})", size=13,
                        weight=ft.FontWeight.BOLD, color=COLOR_ACCENT_CRIMSON),
                ft.Text(r["effect"], size=13, color=COLOR_TEXT_PRIMARY),
            ])
        try:
            madness_result_col.update()
        except RuntimeError:
            pass

    def _on_madness_change(ev: Any) -> None:
        state["madness_kind"] = madness_dd.value or "temporanea"
        state["rolled"] = None
        _render_madness_result()

    def _on_madness_roll(ev: Any) -> None:
        result = game_data.roll_madness_effect(state["madness_kind"])
        state["rolled"] = result
        _render_madness_result()

    def _open_madness_info(title: str, text: str):
        def _handler(ev: Any) -> None:
            _text_dialog(title, [ft.Text(text, size=13, color=COLOR_TEXT_PRIMARY)])
        return _handler

    madness_dd.on_select = _on_madness_change

    madness_view = ft.Column(
        [
            ft.Row(
                [
                    ft.OutlinedButton("Impazzire", icon=ft.Icons.INFO_OUTLINE,
                                      on_click=_open_madness_info("Impazzire", game_data.get_madness_inducing_text())),
                    ft.OutlinedButton("Effetti", icon=ft.Icons.INFO_OUTLINE,
                                      on_click=_open_madness_info("Effetti della Follia", game_data.get_madness_effects_intro_text())),
                    ft.OutlinedButton("Curare", icon=ft.Icons.HEALING_OUTLINED,
                                      on_click=_open_madness_info("Curare la Follia", game_data.get_madness_curing_text())),
                ],
                spacing=6, wrap=True,
            ),
            ft.Divider(height=1, color=COLOR_BORDER),
            madness_dd,
            ft.ElevatedButton(
                "Tira 1d100", icon=ft.Icons.CASINO, on_click=_on_madness_roll,
                style=ft.ButtonStyle(bgcolor=COLOR_ACCENT_CRIMSON, color="#ffffff",
                                      shape=ft.RoundedRectangleBorder(radius=4)),
            ),
            ft.Container(
                content=madness_result_col, bgcolor=COLOR_BG_PRIMARY,
                border_radius=6, padding=ft.Padding.all(12),
            ),
        ],
        spacing=10,
    )

    # -- Tab switching ------------------------------------------------------
    def _render_body() -> None:
        body_col.controls.clear()
        body_col.controls.append(
            {"diseases": diseases_view, "poisons": poisons_view, "madness": madness_view}[state["tab"]]
        )
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
        tab_row.controls.append(_tab_button("diseases", "Malattie"))
        tab_row.controls.append(_tab_button("poisons", "Veleni"))
        tab_row.controls.append(_tab_button("madness", "Follia"))
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
    _render_madness_result()
    _render_body()

    def _close(ev: Any) -> None:
        page.pop_dialog()

    content = ft.Column(
        [tab_row, ft.Divider(height=1, color=COLOR_BORDER), body_col],
        spacing=10, scroll=ft.ScrollMode.AUTO,
        width=responsive_dialog_width(page, 440), height=540, tight=True,
    )

    dlg = ft.AlertDialog(
        title=ft.Text("Malattie, Veleni e Follia", size=16, weight=ft.FontWeight.BOLD, color=COLOR_TEXT_TITLE),
        content=content,
        actions=cast(list[ft.Control], [ft.TextButton("Chiudi", on_click=_close)]),
        bgcolor=COLOR_BG_CARD,
    )
    page.show_dialog(dlg)
