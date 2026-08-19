"""
Dialog condivisi per tre delle azioni "da combattimento" di §7 del design
doc del Multiplayer (Danno/Cura/Condizione) inviabili a un PG istanza di un
mondo — stesso identico contenuto sia da "Interviene a distanza"
(`ui/views/world/world_view.py`) sia dal tracker di combattimento
(`ui/views/master/master_encounter_view.py`).

Un dialog non sa nulla di comandi di rete, permessi o cooldown: valida solo
l'input e chiama `on_confirm(payload)` col payload già pronto per
`WorldBackend.send_command()`. Chi chiama decide COSA fare con quel payload
(quale personaggio, quale mondo, quale pipeline di invio) — stessa
separazione già in uso in tutto il progetto tra "costruzione della UI" e
"logica applicativa".
"""

from __future__ import annotations

from typing import Callable

import flet as ft

from data.game_data.game_data_loader import GameDataLoader
from ui import design
from ui.widgets import show_snack, wrap_dialog_actions

OnConfirm = Callable[[dict], None]


def show_damage_dialog(page: ft.Page, character_name: str, on_confirm: OnConfirm) -> None:
    amount_field = ft.TextField(
        label="Danno", dense=True, value="0",
        keyboard_type=ft.KeyboardType.NUMBER, **design.field_style(),
    )
    critical_cb = ft.Checkbox(label="Colpo critico", value=False)

    def _confirm(e):
        try:
            amount = int((amount_field.value or "0").strip())
        except ValueError:
            show_snack(page, "Il valore deve essere un numero intero.", tone="danger")
            return
        if amount <= 0:
            show_snack(page, "Il danno deve essere positivo.", tone="danger")
            return
        page.pop_dialog()
        on_confirm({"amount": amount, "is_critical": bool(critical_cb.value)})

    page.show_dialog(ft.AlertDialog(
        modal=True,
        title=design.dialog_title(f"Applica danno — {character_name}",
                                   ft.Icons.FAVORITE_BORDER, tone="danger"),
        content=ft.Column([amount_field, critical_cb], tight=True),
        actions=wrap_dialog_actions([
            ft.TextButton("Annulla", on_click=lambda e: page.pop_dialog(),
                          style=ft.ButtonStyle(color=design.T().text_2)),
            ft.ElevatedButton("Conferma", icon=ft.Icons.CHECK, on_click=_confirm,
                               style=ft.ButtonStyle(bgcolor=design.T().danger_fill,
                                                    color=design.T().on_accent)),
        ]),
    ))


def show_heal_dialog(page: ft.Page, character_name: str, on_confirm: OnConfirm) -> None:
    amount_field = ft.TextField(
        label="Cura", dense=True, value="0",
        keyboard_type=ft.KeyboardType.NUMBER, **design.field_style(),
    )

    def _confirm(e):
        try:
            amount = int((amount_field.value or "0").strip())
        except ValueError:
            show_snack(page, "Il valore deve essere un numero intero.", tone="danger")
            return
        if amount <= 0:
            show_snack(page, "La cura deve essere positiva.", tone="danger")
            return
        page.pop_dialog()
        on_confirm({"amount": amount})

    page.show_dialog(ft.AlertDialog(
        modal=True,
        title=design.dialog_title(f"Applica cura — {character_name}", ft.Icons.HEALING),
        content=ft.Column([amount_field], tight=True),
        actions=wrap_dialog_actions([
            ft.TextButton("Annulla", on_click=lambda e: page.pop_dialog(),
                          style=ft.ButtonStyle(color=design.T().text_2)),
            ft.ElevatedButton("Conferma", icon=ft.Icons.CHECK, on_click=_confirm,
                               style=ft.ButtonStyle(bgcolor=design.T().primary_fill,
                                                    color=design.T().on_primary_fill)),
        ]),
    ))


def show_condition_dialog(page: ft.Page, character_name: str, on_confirm: OnConfirm) -> None:
    conditions = GameDataLoader().get_conditions()
    options = [ft.DropdownOption(key=c["key"], text=c.get("name", c["key"]))
               for c in conditions]
    condition_dd = ft.Dropdown(label="Condizione", options=options, dense=True,
                                **design.field_style())
    note_field = ft.TextField(label="Nota (opzionale)", dense=True, **design.field_style())

    def _confirm(e):
        key = condition_dd.value
        if not key:
            show_snack(page, "Seleziona una condizione.", tone="danger")
            return
        page.pop_dialog()
        on_confirm({"condition_key": key, "note": (note_field.value or "").strip()})

    page.show_dialog(ft.AlertDialog(
        modal=True,
        title=design.dialog_title(f"Imponi condizione — {character_name}",
                                   ft.Icons.SICK, tone="magic"),
        content=ft.Column([condition_dd, note_field], tight=True, spacing=design.Space.SM),
        actions=wrap_dialog_actions([
            ft.TextButton("Annulla", on_click=lambda e: page.pop_dialog(),
                          style=ft.ButtonStyle(color=design.T().text_2)),
            ft.ElevatedButton("Conferma", icon=ft.Icons.CHECK, on_click=_confirm,
                               style=ft.ButtonStyle(bgcolor=design.T().magic,
                                                    color=design.T().on_accent)),
        ]),
    ))
