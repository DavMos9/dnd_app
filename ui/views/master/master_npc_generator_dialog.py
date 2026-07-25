"""
Dialog "Genera NPC" — Sezione Master, terzo dei 3 nuovi strumenti richiesti
da Davide oltre ai 10 già completati (vedi CLAUDE.md, TODO "Sezione Master
(11)"/"(12)" per gli altri due e lo stesso requisito trasversale di
varietà: la generazione non deve mai produrre sempre gli stessi risultati).

Logica pura in `core/npc_generator.py` (razza/genere/allineamento risolti a
caso se lasciati su "Qualsiasi", nome da `npc_names.json`, personalità da un
background PHB casuale, stat block agganciato automaticamente se il ruolo
combacia con una delle 21 voci di Appendice B). Questo file si occupa solo
di UI + persistenza in Rubrica (`master_repo.create_npc()`/
`create_npc_from_monster()`, nessuna nuova funzione di scrittura).

Accessibile sia dalla pillola "Genera NPC" nella barra strumenti sempre
visibile di `MasterView`, sia come terza scelta ("Genera Casuale") nel
dialog "Nuovo NPC" di `MasterNpcListView`, accanto a "Nuovo dal Bestiario"/
"Nuovo Manuale" già esistenti.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

import flet as ft

from config.settings import (
    COLOR_ACCENT_BLUE, COLOR_ACCENT_CRIMSON, COLOR_ACCENT_GOLD,
    COLOR_BG_CARD, COLOR_BG_PRIMARY, COLOR_BORDER,
    COLOR_TEXT_MUTED, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY, COLOR_TEXT_TITLE,
)
from core import npc_generator as ng
from data.models import MasterNpc
from data.repositories import master_repo
from ui.components.monster_picker import show_stat_block_dialog
from ui.widgets import responsive_dialog_width, wrap_dialog_actions

logger = logging.getLogger(__name__)

_ANY = ""  # valore Dropdown per "Qualsiasi" — risolto a caso da core/npc_generator.py
_NO_ROLE = ""


def show_npc_generator_dialog(page: ft.Page, on_saved: Callable[[], None] | None = None) -> None:
    """
    Apre il dialog "Genera NPC". `on_saved`, se passato, viene richiamato
    dopo ogni salvataggio riuscito in Rubrica (usato da `MasterNpcListView`
    per aggiornare la lista senza dover riaprire la tab).
    """

    result_state: dict[str, list[dict[str, Any]]] = {"npcs": []}
    saved_ids: set[int] = set()  # indice nella lista result_state["npcs"] già salvato

    race_dd = ft.Dropdown(
        label="Razza", value=_ANY, dense=True, border_radius=6,
        options=[ft.DropdownOption(key=_ANY, text="Qualsiasi")]
        + [ft.DropdownOption(key=r, text=r) for r in ng.get_race_options()],
        border_color=COLOR_BORDER, focused_border_color=COLOR_ACCENT_CRIMSON,
        bgcolor=COLOR_BG_CARD, label_style=ft.TextStyle(color=COLOR_TEXT_SECONDARY),
    )
    gender_dd = ft.Dropdown(
        label="Genere", value=_ANY, dense=True, border_radius=6,
        options=[ft.DropdownOption(key=_ANY, text="Qualsiasi")]
        + [ft.DropdownOption(key=k, text=v) for k, v in ng.get_gender_options()],
        border_color=COLOR_BORDER, focused_border_color=COLOR_ACCENT_CRIMSON,
        bgcolor=COLOR_BG_CARD, label_style=ft.TextStyle(color=COLOR_TEXT_SECONDARY),
    )
    alignment_dd = ft.Dropdown(
        label="Allineamento", value=_ANY, dense=True, border_radius=6,
        options=[ft.DropdownOption(key=_ANY, text="Qualsiasi")]
        + [ft.DropdownOption(key=a, text=a) for a in ng.get_alignment_options()],
        border_color=COLOR_BORDER, focused_border_color=COLOR_ACCENT_CRIMSON,
        bgcolor=COLOR_BG_CARD, label_style=ft.TextStyle(color=COLOR_TEXT_SECONDARY),
    )
    role_dd = ft.Dropdown(
        label="Ruolo (Appendice B)", value=_NO_ROLE, dense=True, border_radius=6,
        options=[ft.DropdownOption(key=_NO_ROLE, text="Nessuno / Generico")]
        + [ft.DropdownOption(key=r, text=f"{r} (scheda combattimento)") for r in ng.get_appendix_b_role_options()],
        border_color=COLOR_BORDER, focused_border_color=COLOR_ACCENT_CRIMSON,
        bgcolor=COLOR_BG_CARD, label_style=ft.TextStyle(color=COLOR_TEXT_SECONDARY),
    )
    custom_role_tf = ft.TextField(
        label="Ruolo personalizzato (sovrascrive la scelta sopra)",
        value="", dense=True, border_radius=6,
        border_color=COLOR_BORDER, focused_border_color=COLOR_ACCENT_CRIMSON,
        bgcolor=COLOR_BG_CARD, label_style=ft.TextStyle(color=COLOR_TEXT_SECONDARY),
    )
    count_tf = ft.TextField(
        label="Quanti NPC", value="1", dense=True, border_radius=6,
        keyboard_type=ft.KeyboardType.NUMBER, width=140,
        border_color=COLOR_BORDER, focused_border_color=COLOR_ACCENT_CRIMSON,
        bgcolor=COLOR_BG_CARD, label_style=ft.TextStyle(color=COLOR_TEXT_SECONDARY),
    )
    result_col = ft.Column(spacing=8)
    feedback_text = ft.Text("", size=11, color=COLOR_ACCENT_BLUE)

    def _parse_count() -> int:
        try:
            return max(1, int((count_tf.value or "1").strip()))
        except ValueError:
            return 1

    def _resolved_role() -> str:
        custom = (custom_role_tf.value or "").strip()
        return custom if custom else (role_dd.value or "")

    def _chip(text: str, color: str) -> ft.Container:
        return ft.Container(
            content=ft.Text(text, size=10, color=color, weight=ft.FontWeight.W_600),
            padding=ft.Padding.symmetric(horizontal=8, vertical=3),
            border=ft.Border.all(1, color),
            border_radius=10,
        )

    def _npc_card(idx: int, npc_data: dict[str, Any]) -> ft.Control:
        chips: list[ft.Control] = [
            _chip(npc_data["race"], COLOR_ACCENT_BLUE),
            _chip(npc_data["gender_label"], COLOR_TEXT_MUTED),
            _chip(npc_data["alignment"], COLOR_TEXT_MUTED),
        ]
        if npc_data["role"]:
            chips.append(_chip(npc_data["role"], COLOR_ACCENT_CRIMSON if npc_data["has_stat_block"] else COLOR_ACCENT_GOLD))

        personality_lines: list[ft.Control] = []
        if npc_data["personality_trait"]:
            personality_lines.append(ft.Text(f"Tratto: {npc_data['personality_trait']}", size=11, color=COLOR_TEXT_PRIMARY))
        if npc_data["ideal"]:
            personality_lines.append(ft.Text(f"Ideale: {npc_data['ideal']}", size=11, color=COLOR_TEXT_PRIMARY))
        if npc_data["bond"]:
            personality_lines.append(ft.Text(f"Legame: {npc_data['bond']}", size=11, color=COLOR_TEXT_PRIMARY))
        if npc_data["flaw"]:
            personality_lines.append(ft.Text(f"Difetto: {npc_data['flaw']}", size=11, color=COLOR_TEXT_PRIMARY))

        stat_line: ft.Control = ft.Container(height=0)
        if npc_data["has_stat_block"] and npc_data["monster"]:
            m = npc_data["monster"]
            stat_line = ft.Row(
                [
                    ft.Text(
                        f"CA {m.get('ac', '?')} · PF {m.get('hp_max', '?')} · "
                        f"GS {m.get('cr', '?')} · {m.get('xp', 0)} PE",
                        size=11, color=COLOR_TEXT_SECONDARY,
                    ),
                    ft.Container(expand=True),
                    ft.TextButton(
                        "Vedi scheda", icon=ft.Icons.SHIELD_OUTLINED,
                        on_click=lambda e, mm=m: show_stat_block_dialog(page, mm.get("name", ""), mm),
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )

        already_saved = idx in saved_ids
        save_btn = ft.ElevatedButton(
            "Salvato ✓" if already_saved else "Salva in Rubrica",
            icon=ft.Icons.CHECK if already_saved else ft.Icons.PERSON_ADD_ALT_1,
            disabled=already_saved,
            on_click=lambda e, i=idx: _on_save_one(i),
            style=ft.ButtonStyle(bgcolor=COLOR_ACCENT_BLUE, color="#ffffff",
                                  shape=ft.RoundedRectangleBorder(radius=4)),
        )

        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(
                                ft.Icons.SHIELD if npc_data["has_stat_block"] else ft.Icons.PERSON_OUTLINE,
                                size=18, color=COLOR_ACCENT_CRIMSON,
                            ),
                            ft.Container(width=8),
                            ft.Text(npc_data["name"], size=14, weight=ft.FontWeight.BOLD,
                                    color=COLOR_TEXT_TITLE, expand=True),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Row(chips, spacing=6, wrap=True),
                    *personality_lines,
                    stat_line,
                    ft.Text(f"Background usato: {npc_data['background_used']}",
                            size=10, color=COLOR_TEXT_MUTED, italic=True),
                    save_btn,
                ],
                spacing=6,
            ),
            padding=ft.Padding.all(10),
            bgcolor=COLOR_BG_PRIMARY,
            border=ft.Border.all(1, COLOR_BORDER),
            border_radius=8,
        )

    def _render_result() -> None:
        result_col.controls.clear()
        npcs = result_state["npcs"]
        if not npcs:
            result_col.controls.append(
                ft.Text("Premi «Genera» per creare uno o più NPC casuali.",
                        size=12, color=COLOR_TEXT_MUTED)
            )
        else:
            for idx, npc_data in enumerate(npcs):
                result_col.controls.append(_npc_card(idx, npc_data))
        try:
            result_col.update()
        except RuntimeError:
            pass

    def _on_generate(ev: Any) -> None:
        count = _parse_count()
        role = _resolved_role()
        npcs = ng.generate_npcs(
            count=count,
            race=race_dd.value or "",
            role=role,
            alignment=alignment_dd.value or "",
            gender=gender_dd.value or "",
        )
        result_state["npcs"] = npcs
        saved_ids.clear()
        feedback_text.value = ""
        _render_result()
        try:
            feedback_text.update()
        except RuntimeError:
            pass

    def _do_save(npc_data: dict[str, Any]) -> MasterNpc | None:
        tags = f"{npc_data['race']}, {npc_data['gender_label']}"
        notes_lines: list[str] = []
        if npc_data["personality_trait"]:
            notes_lines.append(f"Tratto: {npc_data['personality_trait']}")
        if npc_data["ideal"]:
            notes_lines.append(f"Ideale: {npc_data['ideal']}")
        if npc_data["bond"]:
            notes_lines.append(f"Legame: {npc_data['bond']}")
        if npc_data["flaw"]:
            notes_lines.append(f"Difetto: {npc_data['flaw']}")
        if npc_data["background_used"]:
            notes_lines.append(f"(Personalità generata da background: {npc_data['background_used']})")
        notes = "\n".join(notes_lines)

        monster = npc_data.get("monster")
        if npc_data["has_stat_block"] and monster:
            npc = master_repo.create_npc_from_monster(
                monster, name_override=npc_data["name"], role=npc_data["role"],
                notes=notes, tags=tags,
            )
            if npc is not None:
                # L'allineamento scelto dal Master (o risolto a caso)
                # sovrascrive quello grezzo del mostro, così anche un NPC
                # con scheda di combattimento riflette la caratterizzazione
                # scelta in questo dialog, non solo lo stat block.
                npc.alignment = npc_data["alignment"]
                master_repo.update_npc(npc)
            return npc
        return master_repo.create_npc(
            name=npc_data["name"], role=npc_data["role"], notes=notes, tags=tags,
            alignment=npc_data["alignment"], has_stat_block=False,
        )

    def _on_save_one(idx: int) -> None:
        npcs = result_state["npcs"]
        if idx < 0 or idx >= len(npcs) or idx in saved_ids:
            return
        npc = _do_save(npcs[idx])
        if npc is not None:
            saved_ids.add(idx)
            feedback_text.value = f"\"{npc.name}\" salvato in Rubrica NPC."
            _render_result()
            if on_saved:
                on_saved()
        else:
            feedback_text.value = "Errore durante il salvataggio — vedi log."
        try:
            feedback_text.update()
        except RuntimeError:
            pass

    _render_result()

    content = ft.Column(
        [
            ft.Row([race_dd, gender_dd], spacing=10, wrap=True),
            ft.Row([alignment_dd, role_dd], spacing=10, wrap=True),
            custom_role_tf,
            ft.Row([count_tf], spacing=10),
            ft.ElevatedButton(
                "Genera", icon=ft.Icons.AUTO_AWESOME, on_click=_on_generate,
                style=ft.ButtonStyle(bgcolor=COLOR_ACCENT_CRIMSON, color="#ffffff",
                                      shape=ft.RoundedRectangleBorder(radius=4)),
            ),
            ft.Divider(height=1, color=COLOR_BORDER),
            ft.Container(content=result_col, expand=True),
            feedback_text,
        ],
        spacing=10, scroll=ft.ScrollMode.AUTO,
        width=responsive_dialog_width(page, 460), height=600,
        tight=True,
    )

    def _close(ev: Any) -> None:
        page.pop_dialog()

    dlg = ft.AlertDialog(
        title=ft.Text("Genera NPC", size=16, weight=ft.FontWeight.BOLD, color=COLOR_TEXT_TITLE),
        content=content,
        actions=wrap_dialog_actions([ft.TextButton("Chiudi", on_click=_close)]),
        bgcolor=COLOR_BG_CARD,
    )
    page.show_dialog(dlg)
