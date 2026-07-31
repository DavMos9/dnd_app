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

**Bottino (2026-07-31, `dnd_app/docs/loot_design.md` §6, punto 5/6)**: la
scheda di un veleno ha ora "Assegna…"/"Salva nell'archivio" (Malattie e
Follia restano di sola consultazione — non sono oggetti che finiscono in un
inventario).
"""

from __future__ import annotations

from typing import Any, cast

import flet as ft

from data.game_data.game_data_loader import game_data
from ui.widgets import responsive_dialog_width, wrap_dialog_actions
from ui import design


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
    def _text_dialog(title: str, body_controls: list[ft.Control],
                     extra_actions: list[ft.Control] | None = None) -> None:
        def _close(ev: Any) -> None:
            page.pop_dialog()

        dlg = ft.AlertDialog(
            title=design.dialog_title(title),
            content=ft.Column(body_controls, width=responsive_dialog_width(page, 380), height=420,
                              scroll=ft.ScrollMode.AUTO, tight=True),
            actions=wrap_dialog_actions(
                [ft.TextButton("Chiudi", on_click=_close)] + (extra_actions or [])
            ),
        )
        page.show_dialog(dlg)

    def _simple_card(name: str, subtitle: str, on_click) -> ft.Container:
        return ft.Container(
            content=ft.Column(
                [
                    ft.Text(name, size=14, weight=ft.FontWeight.BOLD, color=design.T().text),
                    ft.Text(subtitle, size=11, color=design.T().text_3),
                ],
                spacing=2,
            ),
            padding=ft.Padding.symmetric(horizontal=12, vertical=8),
            bgcolor=design.T().surface,
            shadow=design.elevation(1),
            border_radius=design.Radius.MD,
            on_click=on_click,
            ink=True,
        )

    # -- Modalità "Malattie" -------------------------------------------------
    def _open_disease_detail(disease: dict[str, Any]) -> None:
        _text_dialog(
            disease.get("name", ""),
            [ft.Text(disease.get("description", ""), size=13, color=design.T().text)],
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
    # Bottino (2026-07-31, `dnd_app/docs/loot_design.md` §6, punto 5/6): prima
    # non c'era alcun modo di far arrivare uno dei 14 veleni sulla scheda di
    # un giocatore — solo consultazione, applicazione manuale del Master.
    def _build_poison_loot_item(poison: dict[str, Any]) -> dict[str, Any]:
        from ui.views.master.master_loot_assign_dialog import simple_item
        ptype = poison.get("type", "")
        price = poison.get("price", "")
        return simple_item(
            "poison", poison.get("name", ""),
            description=f"Tipo: {ptype} — Prezzo: {price}\n\n{poison.get('description', '')}",
            source_note=f"Veleni — {ptype}" + (f" · {price}" if price else ""),
        )

    def _open_poison_detail(poison: dict[str, Any]) -> None:
        def _on_assign_loot(ev: Any) -> None:
            from ui.views.master.master_loot_assign_dialog import show_loot_assign_dialog
            show_loot_assign_dialog(page, [_build_poison_loot_item(poison)])

        def _on_save_to_archive(ev: Any) -> None:
            from ui.views.master.master_loot_assign_dialog import save_items_to_stash
            from ui.widgets import show_snack
            save_items_to_stash([_build_poison_loot_item(poison)])
            show_snack(page, f"«{poison.get('name', '')}» salvato nell'archivio.")

        _text_dialog(
            poison.get("name", ""),
            [
                ft.Text(f"Tipo: {poison.get('type', '')} — Prezzo: {poison.get('price', '')}",
                        size=12, italic=True, color=design.T().text_3),
                ft.Container(height=6),
                ft.Text(poison.get("description", ""), size=13, color=design.T().text),
            ],
            extra_actions=[
                ft.OutlinedButton("Salva nell'archivio", icon=ft.Icons.ARCHIVE_OUTLINED,
                                  on_click=_on_save_to_archive),
                ft.OutlinedButton("Assegna…", icon=ft.Icons.SEND_OUTLINED, on_click=_on_assign_loot),
            ],
        )

    def _open_poison_types_info(ev: Any) -> None:
        _text_dialog(
            "Tipi di Veleno",
            [ft.Text(game_data.get_poison_types_intro(), size=13, color=design.T().text)],
        )

    def _open_poison_acquiring_info(ev: Any) -> None:
        _text_dialog(
            "Acquistare i Veleni",
            [ft.Text(game_data.get_poison_acquiring_text(), size=13, color=design.T().text)],
        )

    def _open_poison_crafting_info(ev: Any) -> None:
        _text_dialog(
            "Fabbricare ed Estrarre i Veleni",
            [ft.Text(game_data.get_poison_crafting_text(), size=13, color=design.T().text)],
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
            ft.Divider(height=1, color=design.T().border),
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
        border_color=design.T().border, focused_border_color=design.T().primary,
        bgcolor=design.T().surface, label_style=ft.TextStyle(color=design.T().text_2),
        border_radius=design.field_style()['border_radius'], text_style=design.field_style()['text_style'])
    madness_result_col = ft.Column(spacing=6)

    def _render_madness_result() -> None:
        madness_result_col.controls.clear()
        r = state["rolled"]
        if not r:
            madness_result_col.controls.append(
                ft.Text("Premi «Tira 1d100» per estrarre un effetto.", size=12, color=design.T().text_3)
            )
        else:
            madness_result_col.controls.extend([
                ft.Text(f"Tiro: {r['roll']} (intervallo {r['range']})", size=13,
                        weight=ft.FontWeight.BOLD, color=design.T().primary),
                ft.Text(r["effect"], size=13, color=design.T().text),
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
            _text_dialog(title, [ft.Text(text, size=13, color=design.T().text)])
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
            ft.Divider(height=1, color=design.T().border),
            madness_dd,
            ft.ElevatedButton(
                "Tira 1d100", icon=ft.Icons.CASINO, on_click=_on_madness_roll,
                style=ft.ButtonStyle(bgcolor=design.T().primary, color=design.T().on_primary),
            ),
            ft.Container(
                content=madness_result_col, bgcolor=design.T().bg,
                border_radius=design.Radius.MD, padding=ft.Padding.all(12),
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
                             color=design.T().primary if is_sel else design.T().text_2),
            padding=ft.Padding.symmetric(horizontal=12, vertical=6),
            border=ft.Border.only(bottom=ft.BorderSide(2, design.T().primary if is_sel else "transparent")),
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
        [tab_row, ft.Divider(height=1, color=design.T().border), body_col],
        spacing=10, scroll=ft.ScrollMode.AUTO,
        width=responsive_dialog_width(page, 440), height=540, tight=True,
    )

    dlg = ft.AlertDialog(
        title=design.dialog_title("Malattie, Veleni e Follia"),
        content=content,
        actions=cast(list[ft.Control], [ft.TextButton("Chiudi", on_click=_close)]),
    )
    page.show_dialog(dlg)
