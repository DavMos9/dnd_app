"""
Dialog "Genera Incontro per Ambiente" — Sezione Master, punto 10 del design
(`dnd_app/docs/master_section_design.md`). v1 ridotta, come da design:
solo l'ambiente "Foresta Silvana" (l'unico esempio completamente lavorato
nella DMG, Cap.3 p.87 — nessun'altra tabella ambiente→mostro pronta esiste
nel manuale, vedi il design doc per l'analisi completa del gap e la
raccomandazione di limitare questa v1 a un solo ambiente dimostrativo).

Meccanica di tiro: 1d12+1d8 (range 2-20), non un d20 piatto — privilegia i
risultati centrali della tabella, esattamente come stampato nel manuale.

Se il risultato cita una o più creature con una scheda nel bestiario
(`monsters.json`, tramite `ui/components/monster_picker.py`), viene mostrato
un pulsante "Vedi scheda" per ciascuna, che apre lo stesso stat block dialog
già condiviso con Forma Selvatica/Evocazioni/Rubrica NPC.

Accessibile da `MasterView` (bottone in header, "Incontri per Ambiente").
"""

from __future__ import annotations

from typing import Any, cast

import flet as ft

from config.settings import (
    COLOR_TEXT_TITLE, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
    COLOR_TEXT_MUTED, COLOR_BORDER, COLOR_BG_CARD, COLOR_BG_PRIMARY,
    COLOR_ACCENT_CRIMSON, COLOR_ACCENT_BLUE,
)
from data.game_data.game_data_loader import game_data
from ui.components.monster_picker import load_monsters, show_stat_block_dialog
from ui.widgets import responsive_dialog_width


def _resolve_creature(name: str) -> dict[str, Any] | None:
    """Cerca `name` (case-insensitive) nel bestiario già trascritto.
    Ritorna `None` senza errori se non risolve (es. un NPC dell'Appendice B
    non presente in monsters.json, o un nome non corrispondente)."""
    target = (name or "").strip().lower()
    if not target:
        return None
    for m in load_monsters():
        if str(m.get("name", "")).strip().lower() == target:
            return m
    return None


def show_forest_encounters_dialog(page: ft.Page) -> None:
    """Apre il dialog "Genera Incontro per Ambiente". Stato in closure,
    stesso pattern già in uso per `show_traps_dialog`/`show_health_hazards_dialog`."""

    env_names = game_data.get_environment_names()
    default_env = env_names[0] if env_names else ""
    state: dict[str, Any] = {"env": default_env, "result": None}

    env_dd = ft.Dropdown(
        label="Ambiente",
        value=default_env or None,
        options=[
            ft.DropdownOption(key=k, text=game_data.get_environment_table(k).get("label", k))
            for k in env_names
        ],
        border_color=COLOR_BORDER, focused_border_color=COLOR_ACCENT_CRIMSON,
        bgcolor=COLOR_BG_CARD, label_style=ft.TextStyle(color=COLOR_TEXT_SECONDARY),
    )
    result_col = ft.Column(spacing=8)

    def _open_creature_sheet(m: dict[str, Any]) -> None:
        show_stat_block_dialog(page, str(m.get("name", "")), m)

    def _render_result() -> None:
        result_col.controls.clear()
        r = state["result"]
        if not r:
            result_col.controls.append(
                ft.Text("Premi «Tira 1d12+1d8» per generare un incontro.", size=12, color=COLOR_TEXT_MUTED)
            )
        else:
            result_col.controls.append(
                ft.Text(
                    f"Tiro: {r['roll']}  (d12={r['d12']} + d8={r['d8']})",
                    size=13, weight=ft.FontWeight.BOLD, color=COLOR_ACCENT_CRIMSON,
                )
            )
            result_col.controls.append(ft.Text(r["text"], size=13, color=COLOR_TEXT_PRIMARY))
            if r.get("note"):
                result_col.controls.append(
                    ft.Text(r["note"], size=11, italic=True, color=COLOR_TEXT_MUTED)
                )
            links: list[ft.Control] = []
            for cname in r.get("creatures", []):
                mdata = _resolve_creature(cname)
                if mdata:
                    links.append(
                        ft.OutlinedButton(
                            f"Vedi scheda: {cname}",
                            icon=ft.Icons.MENU_BOOK_OUTLINED,
                            style=ft.ButtonStyle(color=COLOR_ACCENT_BLUE),
                            on_click=lambda e, mm=mdata: _open_creature_sheet(mm),
                        )
                    )
            if links:
                result_col.controls.append(ft.Row(links, spacing=6, wrap=True))
        try:
            result_col.update()
        except RuntimeError:
            pass

    def _on_env_change(ev: Any) -> None:
        state["env"] = env_dd.value or default_env
        state["result"] = None
        _render_result()

    def _on_roll(ev: Any) -> None:
        state["result"] = game_data.roll_environment_encounter(state["env"])
        _render_result()

    env_dd.on_select = _on_env_change
    _render_result()

    def _close(ev: Any) -> None:
        page.pop_dialog()

    empty_state = not env_names
    content_controls: list[ft.Control] = []
    if empty_state:
        content_controls.append(
            ft.Text(
                "Nessun ambiente disponibile — dato non ancora trascritto.",
                size=13, color=COLOR_TEXT_MUTED,
            )
        )
    else:
        content_controls.extend(
            [
                env_dd,
                ft.ElevatedButton(
                    "Tira 1d12+1d8", icon=ft.Icons.CASINO, on_click=_on_roll,
                    style=ft.ButtonStyle(bgcolor=COLOR_ACCENT_CRIMSON, color="#ffffff",
                                          shape=ft.RoundedRectangleBorder(radius=4)),
                ),
                ft.Divider(height=1, color=COLOR_BORDER),
                ft.Container(
                    content=result_col, bgcolor=COLOR_BG_PRIMARY,
                    border_radius=6, padding=ft.Padding.all(12),
                ),
            ]
        )

    content = ft.Column(
        content_controls, spacing=10, scroll=ft.ScrollMode.AUTO,
        width=responsive_dialog_width(page, 420), height=420, tight=True,
    )

    dlg = ft.AlertDialog(
        title=ft.Text("Genera Incontro per Ambiente", size=16, weight=ft.FontWeight.BOLD, color=COLOR_TEXT_TITLE),
        content=content,
        actions=cast(list[ft.Control], [ft.TextButton("Chiudi", on_click=_close)]),
        bgcolor=COLOR_BG_CARD,
    )
    page.show_dialog(dlg)
