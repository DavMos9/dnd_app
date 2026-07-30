"""
Dialog "Genera Oggetto Magico" — Sezione Master, uno dei 3 nuovi strumenti
richiesti da Davide oltre ai 10 già completati (vedi CLAUDE.md, TODO
"Sezione Master (11) — Generatore Incontri Casuali" per il changelog del
primo dei tre e lo stesso requisito trasversale di varietà).

A differenza del Generatore Tesori (`master_treasure_dialog.py`, che tira da
tabelle d100 e produce solo nomi senza descrizione), questo generatore pesca
direttamente dal Compendio Oggetti Magici A-Z già trascritto per intero
(`data/game_data/magic_items.json`, 264 voci, `GameDataLoader.get_magic_items()`)
— ogni oggetto generato porta con sé la descrizione ufficiale completa.

Logica pura in `core/magic_item_generator.py` (filtro rarità/categoria +
estrazione casuale senza ripetizione quando il pool lo consente). Stesso
pattern UI di `master_treasure_dialog.py`: funzione top-level
`show_magic_item_generator_dialog(page)`, stato in closure, azione
"Aggiungi all'inventario" che riusa `character_repo.create_inventory_item()`
(nessuna nuova funzione di scrittura personaggio).

Accessibile da `MasterView` (pillola "Oggetto Magico" nella barra strumenti
sempre visibile, stesso stile delle altre 4 pillole già presenti).
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any

import flet as ft

from core import magic_item_generator as mig
from data.game_data.game_data_loader import GameDataLoader, magic_item_rarity_bucket
from data.repositories import character_repo
from ui.views.master.master_magic_items_view import (
    _rarity_color, _RARITY_LABELS, _RARITY_ORDER, _category_icon,
)
from ui.widgets import responsive_dialog_width, wrap_dialog_actions
from ui import design

logger = logging.getLogger(__name__)
_loader = GameDataLoader()


def show_magic_item_generator_dialog(page: ft.Page) -> None:
    """Apre il dialog "Genera Oggetto Magico". Nessun valore ritornato —
    tutta la logica di stato vive nella closure, stesso pattern già in uso
    per gli altri dialog generatore della Sezione Master."""

    all_items = _loader.get_magic_items()
    category_options = mig.get_category_options(all_items)
    characters = character_repo.get_all()

    result_state: dict[str, Any] = {"items": []}

    rarity_dd = ft.Dropdown(
        label="Rarità", value="", dense=True, border_radius=design.Radius.SM,
        options=[ft.DropdownOption(key="", text="Qualsiasi")]
        + [ft.DropdownOption(key=k, text=_RARITY_LABELS[k]) for k in _RARITY_ORDER],
        border_color=design.T().border, focused_border_color=design.T().primary,
        bgcolor=design.T().surface, label_style=ft.TextStyle(color=design.T().text_2),
        text_style=design.field_style()['text_style'])
    category_dd = ft.Dropdown(
        label="Categoria", value="", dense=True, border_radius=design.Radius.SM,
        options=[ft.DropdownOption(key="", text="Tutte")]
        + [ft.DropdownOption(key=c, text=c) for c in category_options],
        border_color=design.T().border, focused_border_color=design.T().primary,
        bgcolor=design.T().surface, label_style=ft.TextStyle(color=design.T().text_2),
        text_style=design.field_style()['text_style'])
    count_tf = ft.TextField(
        label="Quanti oggetti", value="1", dense=True, border_radius=design.Radius.SM,
        keyboard_type=ft.KeyboardType.NUMBER, width=140,
        border_color=design.T().border, focused_border_color=design.T().primary,
        bgcolor=design.T().surface, label_style=ft.TextStyle(color=design.T().text_2),
        text_style=design.field_style()['text_style'])
    pool_hint = ft.Text("", size=11, color=design.T().text_3)
    result_col = ft.Column(spacing=8)
    char_dd = ft.Dropdown(
        label="Aggiungi all'inventario di...",
        value=characters[0].id if characters else "",
        options=[ft.DropdownOption(key=c.id, text=f"{c.name} (Lv.{c.level})") for c in characters],
        border_color=design.T().border, focused_border_color=design.T().primary,
        bgcolor=design.T().surface, label_style=ft.TextStyle(color=design.T().text_2),
        disabled=not characters,
        border_radius=design.field_style()['border_radius'], text_style=design.field_style()['text_style'])
    feedback_text = ft.Text("", size=11, color=design.T().magic)

    def _update_pool_hint() -> None:
        pool = mig.filter_magic_items(all_items, rarity_dd.value or "", category_dd.value or "")
        pool_hint.value = f"{len(pool)} oggett{'o' if len(pool) == 1 else 'i'} disponibili con questi filtri."
        try:
            pool_hint.update()
        except RuntimeError:
            pass

    def _item_chip(text: str, color: str) -> ft.Container:
        return ft.Container(
            content=ft.Text(text, size=10, color=color, weight=ft.FontWeight.W_600),
            padding=ft.Padding.symmetric(horizontal=8, vertical=3),
            border=ft.Border.all(1, color),
            border_radius=10,
        )

    def _item_card(item: dict[str, Any]) -> ft.Control:
        name = item.get("name", "")
        category = item.get("category", "")
        rarity_raw = item.get("rarity", "")
        bucket = magic_item_rarity_bucket(rarity_raw)
        requires_att = bool(item.get("requires_attunement"))
        desc = item.get("description", "")

        chips: list[ft.Control] = []
        if rarity_raw:
            chips.append(_item_chip(
                _RARITY_LABELS.get(bucket, rarity_raw.strip().capitalize()),
                _rarity_color(bucket),
            ))
        if category:
            chips.append(_item_chip(category, design.T().text_3))
        if requires_att:
            chips.append(_item_chip("Sintonia", design.T().warning))

        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(_category_icon(category), size=16, color=design.T().primary),
                            ft.Container(width=8),
                            ft.Text(name, size=13, weight=ft.FontWeight.BOLD,
                                    color=design.T().text, expand=True),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Row(chips, spacing=6, wrap=True),
                    ft.Text(desc, size=11, color=design.T().text, selectable=True),
                ],
                spacing=6,
            ),
            padding=ft.Padding.all(10),
            bgcolor=design.T().bg,
            border=ft.Border.all(1, design.T().border),
            border_radius=8,
        )

    def _render_result() -> None:
        result_col.controls.clear()
        items = result_state["items"]
        if not items:
            result_col.controls.append(
                ft.Text("Premi «Genera» per estrarre uno o più oggetti magici.",
                        size=12, color=design.T().text_3)
            )
        else:
            for it in items:
                result_col.controls.append(_item_card(it))
        try:
            result_col.update()
        except RuntimeError:
            pass

    def _parse_count() -> int:
        try:
            return max(1, int((count_tf.value or "1").strip()))
        except ValueError:
            return 1

    def _on_filter_change(ev: Any) -> None:
        _update_pool_hint()

    def _on_generate(ev: Any) -> None:
        count = _parse_count()
        items = mig.generate_magic_items(
            all_items, rarity=rarity_dd.value or "", category=category_dd.value or "", count=count,
        )
        result_state["items"] = items
        feedback_text.value = "" if items else "Nessun oggetto combacia con questi filtri."
        _render_result()
        try:
            feedback_text.update()
        except RuntimeError:
            pass

    def _on_add_to_inventory(ev: Any) -> None:
        char_id = char_dd.value or ""
        items = result_state["items"]
        if not char_id or not items:
            return
        added = 0
        for name, qty in Counter(it.get("name", "") for it in items).items():
            item = next((it for it in items if it.get("name", "") == name), {})
            category = item.get("category", "")
            rarity_raw = item.get("rarity", "").strip()
            requires_att = bool(item.get("requires_attunement"))
            att_restriction = item.get("attunement_restriction", "")
            summary_bits = [b for b in (category, rarity_raw.capitalize()) if b]
            if requires_att:
                summary_bits.append("Richiede sintonia" + (f" ({att_restriction})" if att_restriction else ""))
            ok = character_repo.create_inventory_item(
                char_id, name, quantity=qty, category="magic",
                description=item.get("description", ""),
                effects=" · ".join(summary_bits),
            )
            if ok:
                added += 1
        char_name = next((c.name for c in characters if c.id == char_id), "personaggio")
        if added:
            feedback_text.value = f"Aggiunto a {char_name}: {added} oggett{'o' if added == 1 else 'i'} magic{'o' if added == 1 else 'i'}."
        else:
            feedback_text.value = "Errore nell'aggiunta all'inventario — vedi log."
        try:
            feedback_text.update()
        except RuntimeError:
            pass

    rarity_dd.on_select = _on_filter_change
    category_dd.on_select = _on_filter_change

    _update_pool_hint()
    _render_result()

    content = ft.Column(
        [
            ft.Row([rarity_dd, category_dd], spacing=10, wrap=True),
            ft.Row([count_tf], spacing=10),
            pool_hint,
            ft.ElevatedButton(
                "Genera", icon=ft.Icons.AUTO_AWESOME, on_click=_on_generate,
                style=ft.ButtonStyle(bgcolor=design.T().primary, color=design.T().on_primary),
            ),
            ft.Divider(height=1, color=design.T().border),
            ft.Container(content=result_col, expand=True),
            ft.Divider(height=1, color=design.T().border),
            char_dd,
            ft.ElevatedButton(
                "Aggiungi all'inventario", icon=ft.Icons.ADD_SHOPPING_CART,
                on_click=_on_add_to_inventory, disabled=not characters,
                style=ft.ButtonStyle(bgcolor=design.T().magic, color=design.T().on_accent),
            ),
            feedback_text,
        ],
        spacing=10, scroll=ft.ScrollMode.AUTO,
        width=responsive_dialog_width(page, 440), height=560,
        tight=True,
    )

    def _close(ev: Any) -> None:
        page.pop_dialog()

    dlg = ft.AlertDialog(
        title=design.dialog_title("Genera Oggetto Magico"),
        content=content,
        actions=wrap_dialog_actions([ft.TextButton("Chiudi", on_click=_close)]),
    )
    page.show_dialog(dlg)
