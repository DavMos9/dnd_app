"""
Dialog "Genera Tesoro" — Sezione Master, punto 6 del design
(`dnd_app/docs/master_section_design.md`). Tira Tesoro Singolo o Cumulo di
Tesori per fascia di CR (`core/treasure_generator.py`, dati da
`data/game_data/treasure_tables.json`), mostra il risultato e permette di
aggiungerlo direttamente all'inventario/alle valute di un personaggio già
esistente — riuso diretto di `character_repo.create_inventory_item()`/
`get_currencies()`/`update_currencies()`, nessuna nuova funzione di
scrittura personaggio (per istruzione esplicita del design doc).

Include anche il pulsante "+ Cimelio" (Oggetti Insoliti, PHB p.160-161) —
deciso con Davide il 2026-07-24: dentro questo dialog, non una voce di
navigazione a sé (un tiro 1d100 senza parametri non giustifica una
schermata dedicata).

Accessibile da `MasterView` (bottone in header, "Genera Tesoro").
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any, cast

import flet as ft

from core import treasure_generator as tg
from data.repositories import character_repo
from ui.widgets import responsive_dialog_width
from ui import design

logger = logging.getLogger(__name__)

_CR_LABELS = {"0-4": "Sfida 0-4", "5-10": "Sfida 5-10", "11-16": "Sfida 11-16", "17+": "Sfida 17 o più"}


def show_treasure_generator_dialog(page: ft.Page) -> None:
    """Apre il dialog "Genera Tesoro". Nessun valore ritornato — tutta la
    logica di stato vive nella closure, tipico pattern già in uso nel
    progetto per i dialog Flet complessi (vedi profilo_tab.py/wizard_view.py)."""

    mode_state: dict[str, str] = {"mode": "individual", "cr_band": "0-4"}
    result_state: dict[str, Any] = {}
    trinket_state: dict[str, Any] = {}
    characters = character_repo.get_all()

    mode_group = ft.RadioGroup(
        value="individual",
        content=ft.Row(
            [
                ft.Radio(value="individual", label="Tesoro Singolo"),
                ft.Radio(value="hoard", label="Cumulo di Tesori"),
            ],
        ),
    )
    cr_dd = ft.Dropdown(
        label="Fascia di Sfida (CR)",
        value="0-4",
        options=[ft.DropdownOption(key=k, text=v) for k, v in _CR_LABELS.items()],
        border_color=design.T().border, focused_border_color=design.T().primary,
        bgcolor=design.T().surface, label_style=ft.TextStyle(color=design.T().text_2),
        border_radius=design.field_style()['border_radius'], text_style=design.field_style()['text_style'])
    result_col = ft.Column(spacing=6)
    char_dd = ft.Dropdown(
        label="Aggiungi all'inventario di...",
        value=characters[0].id if characters else "",
        options=[ft.DropdownOption(key=c.id, text=f"{c.name} (Lv.{c.level})") for c in characters],
        border_color=design.T().border, focused_border_color=design.T().primary,
        bgcolor=design.T().surface, label_style=ft.TextStyle(color=design.T().text_2),
        disabled=not characters,
        border_radius=design.field_style()['border_radius'], text_style=design.field_style()['text_style'])
    add_btn_ref: list[ft.ElevatedButton] = []
    feedback_text = ft.Text("", size=11, color=design.T().magic)

    def _coin_lines(coins: list[dict[str, Any]]) -> list[ft.Control]:
        if not any(c.get("amount") for c in coins):
            return [ft.Text("Nessuna moneta", size=12, color=design.T().text_3)]
        return [
            ft.Text(f"• {c['amount']} {tg.CURRENCY_LABELS.get(c['currency'], c['currency'])}",
                     size=13, color=design.T().text)
            for c in coins if c.get("amount")
        ]

    def _render_result() -> None:
        result_col.controls.clear()
        if not result_state:
            result_col.controls.append(
                ft.Text("Premi «Tira» per generare un tesoro.", size=12, color=design.T().text_3)
            )
        elif mode_state["mode"] == "individual":
            result_col.controls.append(
                ft.Text(f"Tiro d100: {result_state['roll']}", size=11, color=design.T().text_3)
            )
            result_col.controls.extend(_coin_lines(result_state["coins"]))
        else:
            result_col.controls.append(ft.Text("Monete (formula fissa):", size=12, weight=ft.FontWeight.BOLD, color=design.T().text))
            result_col.controls.extend(_coin_lines(result_state["coins"]))
            result_col.controls.append(ft.Container(height=6))
            result_col.controls.append(
                ft.Text(f"Tiro d100 tabella aggiuntiva: {result_state['roll']}", size=11, color=design.T().text_3)
            )
            ga = result_state.get("gems_or_art")
            if ga:
                label = "Gemme" if ga["type"] == "gems" else "Oggetti d'Arte"
                result_col.controls.append(
                    ft.Text(f"{label} da {ga['value']} mo (×{ga['count']}):", size=12,
                             weight=ft.FontWeight.BOLD, color=design.T().text)
                )
                for item in ga["items"]:
                    result_col.controls.append(ft.Text(f"• {item}", size=12, color=design.T().text))
            magic = result_state.get("magic_items", [])
            if magic:
                result_col.controls.append(ft.Text("Oggetti Magici:", size=12, weight=ft.FontWeight.BOLD, color=design.T().text))
                for item in magic:
                    result_col.controls.append(ft.Text(f"• {item}", size=12, color=design.T().text))
            if not ga and not magic:
                result_col.controls.append(ft.Text("Nessuna gemma/oggetto d'arte/oggetto magico in questo tiro.",
                                                      size=12, color=design.T().text_3, italic=True))

        if trinket_state:
            result_col.controls.append(ft.Container(height=6))
            result_col.controls.append(ft.Divider(height=1, color=design.T().border))
            result_col.controls.append(
                ft.Text(f"Cimelio (tiro {trinket_state['roll']}):", size=12, weight=ft.FontWeight.BOLD, color=design.T().text)
            )
            result_col.controls.append(ft.Text(trinket_state["description"], size=12, color=design.T().text, italic=True))

        try:
            result_col.update()
        except RuntimeError:
            pass

    def _on_mode_change(ev: Any) -> None:
        mode_state["mode"] = mode_group.value or "individual"

    def _on_cr_change(ev: Any) -> None:
        mode_state["cr_band"] = cr_dd.value or "0-4"

    def _on_roll(ev: Any) -> None:
        band = mode_state["cr_band"]
        if mode_state["mode"] == "individual":
            result_state.clear()
            result_state.update(tg.generate_individual_treasure(band))
        else:
            result_state.clear()
            result_state.update(tg.generate_hoard_treasure(band))
        trinket_state.clear()
        feedback_text.value = ""
        _render_result()
        try:
            feedback_text.update()
        except RuntimeError:
            pass

    def _on_trinket(ev: Any) -> None:
        roll, description = tg.roll_trinket()
        trinket_state.clear()
        trinket_state.update({"roll": roll, "description": description})
        _render_result()

    def _on_add_to_inventory(ev: Any) -> None:
        char_id = char_dd.value or ""
        if not char_id or not result_state:
            return
        currency_map = {"mr": "copper", "ma": "silver", "me": "electrum", "mo": "gold", "mp": "platinum"}
        existing = character_repo.get_currencies(char_id)
        totals = {
            "copper": existing.copper if existing else 0,
            "silver": existing.silver if existing else 0,
            "electrum": existing.electrum if existing else 0,
            "gold": existing.gold if existing else 0,
            "platinum": existing.platinum if existing else 0,
        }
        for c in result_state.get("coins", []):
            field = currency_map.get(c["currency"])
            if field and c.get("amount"):
                totals[field] += c["amount"]
        ok_currency = character_repo.update_currencies(
            char_id, totals["copper"], totals["silver"], totals["electrum"],
            totals["gold"], totals["platinum"],
        )

        added_items = 0
        ga = result_state.get("gems_or_art")
        if ga and ga.get("items"):
            label = "Gemma" if ga["type"] == "gems" else "Oggetto d'arte"
            for name, qty in Counter(ga["items"]).items():
                character_repo.create_inventory_item(
                    char_id, name, quantity=qty, category="misc",
                    description=f"{label} da {ga['value']} mo (Generatore Tesori)",
                )
                added_items += 1
        for name, qty in Counter(result_state.get("magic_items", [])).items():
            character_repo.create_inventory_item(
                char_id, name, quantity=qty, category="magic",
                description="Oggetto magico (Generatore Tesori — descrizione completa non ancora disponibile)",
            )
            added_items += 1
        if trinket_state:
            character_repo.create_inventory_item(
                char_id, "Cimelio", quantity=1, category="misc",
                description=trinket_state["description"],
            )
            added_items += 1

        char_name = next((c.name for c in characters if c.id == char_id), "personaggio")
        if ok_currency:
            feedback_text.value = f"Aggiunto a {char_name}: monete aggiornate" + (f" + {added_items} oggetti" if added_items else "")
        else:
            feedback_text.value = "Errore nell'aggiornamento delle valute — vedi log."
        try:
            feedback_text.update()
        except RuntimeError:
            pass

    add_btn = ft.ElevatedButton(
        "Aggiungi all'inventario", icon=ft.Icons.ADD_SHOPPING_CART,
        on_click=_on_add_to_inventory,
        disabled=not characters,
        style=ft.ButtonStyle(bgcolor=design.T().magic, color=design.T().on_accent),
    )
    add_btn_ref.append(add_btn)

    mode_group.on_change = _on_mode_change
    cr_dd.on_select = _on_cr_change

    _render_result()

    content = ft.Column(
        [
            mode_group,
            cr_dd,
            ft.Row(
                [
                    ft.ElevatedButton(
                        "Tira", icon=ft.Icons.CASINO, on_click=_on_roll,
                        style=ft.ButtonStyle(bgcolor=design.T().primary, color=design.T().on_primary),
                    ),
                    ft.OutlinedButton("+ Cimelio", icon=ft.Icons.AUTO_AWESOME, on_click=_on_trinket),
                ],
                spacing=8,
            ),
            ft.Divider(height=1, color=design.T().border),
            ft.Container(
                content=result_col,
                bgcolor=design.T().bg, border_radius=design.Radius.MD,
                padding=ft.Padding.all(12),
            ),
            ft.Divider(height=1, color=design.T().border),
            char_dd,
            add_btn,
            feedback_text,
        ],
        spacing=10, scroll=ft.ScrollMode.AUTO,
        width=responsive_dialog_width(page, 420), height=520,
        tight=True,
    )

    def _close(ev: Any) -> None:
        page.pop_dialog()

    dlg = ft.AlertDialog(
        title=design.dialog_title("Genera Tesoro"),
        content=content,
        actions=cast(list[ft.Control], [
            ft.TextButton("Chiudi", on_click=_close),
        ]),
    )
    page.show_dialog(dlg)
