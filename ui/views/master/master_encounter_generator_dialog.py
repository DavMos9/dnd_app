"""
Dialog "Genera Incontro Casuale" — Sezione Master. Due modalità (`core.
encounter_generator`, vedi quel modulo per il dettaglio dell'algoritmo):
"Diretta" (GS min/max + tema + numero di mostri, estrazione casuale con
ripetizione) e "Per Gruppo" (livelli del gruppo — PG reali selezionati dalla
lista esistente + eventuali "PG fantasma" solo-livello — più difficoltà
bersaglio, assemblaggio goloso randomizzato via `encounter_calculator`).

Il risultato generato viene mostrato raggruppato per nome (es. "Goblin ×3")
con GS/PE di riferimento, e — se in modalità "Per Gruppo" — con la
difficoltà risultante ricalcolata (stessa logica del Calcolatore Difficoltà
già esistente, mai duplicata). "Genera" è anche il pulsante di rigenerazione
(ogni click ripete l'estrazione casuale da zero). Alla conferma, crea un
NUOVO incontro (`master_repo.create_encounter`) e vi aggiunge tutti i mostri
generati come membri "adhoc" (stesso schema già usato da
`MasterEncounterView._open_add_monster_dialog`), poi invoca `on_created`
con l'id del nuovo incontro — il chiamante (`MasterEncounterListView`)
decide se aprirlo subito.

Accessibile da `MasterEncounterListView` (pulsante header "Genera Incontro
Casuale", accanto a "+ Nuovo Incontro").
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any, Callable, cast

import flet as ft

from core import encounter_generator as eg
from core.encounter_calculator import DIFFICULTY_LABELS, DIFFICULTY_ORDER, calculate_difficulty
from data.game_data.game_data_loader import parse_monster_xp
from data.repositories import character_repo, master_repo
from ui.components.monster_picker import load_monsters, monster_display_name
from ui.widgets import responsive_dialog_width, wrap_dialog_actions
from ui import design

logger = logging.getLogger(__name__)



def _int_or(text: str | None, default: int) -> int:
    if not text or not text.strip():
        return default
    try:
        return int(text.strip())
    except ValueError:
        try:
            return int(float(text.strip()))
        except ValueError:
            return default


def _parse_cr(text: str | None, default: float) -> float:
    """Parsa un Grado di Sfida testuale ("5", "0.5", "1/2") in float. Stringa
    vuota → `default` (non 0), per distinguere "nessun limite impostato" da
    "limite esplicito a GS 0"."""
    if not text or not text.strip():
        return default
    t = text.strip()
    if "/" in t:
        try:
            a, b = t.split("/")
            return int(a) / int(b)
        except Exception:
            return default
    try:
        return float(t.replace(",", "."))
    except ValueError:
        return default


def show_encounter_generator_dialog(page: ft.Page, on_created: Callable[[str], None],
                                     world_id: str = "") -> None:
    """Apre il dialog "Genera Incontro Casuale". `on_created(encounter_id)`
    viene invocato dopo la creazione riuscita del nuovo incontro (con tutti i
    mostri generati già aggiunti come membri) — il chiamante decide se
    aprirlo subito o solo aggiornare la lista.

    `world_id` (2026-08-06): il mondo correntemente selezionato in
    `MasterView` — "" per la modalità locale. Determina quali PG reali
    compaiono nella modalità "Per Gruppo", vedi
    `character_repo.get_master_visible_characters()`."""

    monsters = load_monsters()
    theme_options = eg.get_theme_options(monsters)
    characters = character_repo.get_master_visible_characters(world_id)

    state: dict[str, Any] = {"mode": "direct", "theme": ""}
    generated: list[dict] = []
    ghost_levels: list[int] = []
    checked_char_ids: set[str] = set()

    mode_group = ft.RadioGroup(
        value="direct",
        content=ft.Row(
            [
                ft.Radio(value="direct", label="Diretta (GS + numero)"),
                ft.Radio(value="party", label="Per Gruppo (difficoltà)"),
            ],
        ),
    )
    theme_dd = ft.Dropdown(
        label="Tema",
        value="",
        options=[ft.DropdownOption(key="", text="Qualsiasi")]
        + [ft.DropdownOption(key=t, text=t) for t in theme_options],
        border_color=design.T().border, focused_border_color=design.T().primary,
        bgcolor=design.T().surface, label_style=ft.TextStyle(color=design.T().text_2),
        dense=True,
        border_radius=design.field_style()['border_radius'], text_style=design.field_style()['text_style'])

    # --- Modalità Diretta ---
    cr_min_tf = ft.TextField(label="GS min", value="0", width=90, dense=True,
                              keyboard_type=ft.KeyboardType.NUMBER, **design.field_style())
    cr_max_tf = ft.TextField(label="GS max", value="5", width=90, dense=True,
                              keyboard_type=ft.KeyboardType.NUMBER, **design.field_style())
    count_tf = ft.TextField(label="Numero mostri", value="4", width=140, dense=True,
                             keyboard_type=ft.KeyboardType.NUMBER, **design.field_style())
    direct_col = ft.Container(
        content=ft.Column(
            [
                ft.Row([cr_min_tf, cr_max_tf], spacing=8, wrap=True),
                count_tf,
            ],
            spacing=8,
        ),
        visible=True,
    )

    # --- Modalità Per Gruppo ---
    char_checks: list[ft.Checkbox] = []
    for c in characters:
        cb = ft.Checkbox(label=f"{c.name} (Lv.{c.level})", value=False, data=c.id)
        char_checks.append(cb)
    char_checks_col: ft.Control = (
        ft.Column(cast(list[ft.Control], char_checks), spacing=2)
        if char_checks
        else ft.Text("Nessun personaggio creato ancora.", size=11, color=design.T().text_3)
    )

    difficulty_dd = ft.Dropdown(
        label="Difficoltà bersaglio", value="medio",
        options=[ft.DropdownOption(key=d, text=DIFFICULTY_LABELS[d]) for d in DIFFICULTY_ORDER],
        border_color=design.T().border, focused_border_color=design.T().primary,
        bgcolor=design.T().surface, label_style=ft.TextStyle(color=design.T().text_2),
        dense=True,
        border_radius=design.field_style()['border_radius'], text_style=design.field_style()['text_style'])
    party_cr_min_tf = ft.TextField(label="GS min (opz.)", dense=True, width=120, **design.field_style())
    party_cr_max_tf = ft.TextField(label="GS max (opz.)", dense=True, width=120, **design.field_style())
    ghost_tf = ft.TextField(label="Livello PG fantasma", value="1", width=160, dense=True,
                             keyboard_type=ft.KeyboardType.NUMBER, **design.field_style())
    ghost_row = ft.Row([], spacing=6, wrap=True)

    party_col = ft.Container(
        content=ft.Column(
            [
                ft.Text("Personaggi nel gruppo:", size=11, color=design.T().text_2, weight=ft.FontWeight.W_600),
                char_checks_col,
                ft.Row(
                    [ghost_tf, ft.IconButton(ft.Icons.ADD_CIRCLE, icon_color=design.T().magic,
                                              tooltip="Aggiungi PG fantasma")],
                    spacing=6,
                ),
                ft.Text(
                    "PG fantasma: solo livello, per pianificare senza personaggi reali già creati.",
                    size=10, color=design.T().text_3, italic=True,
                ),
                ghost_row,
                difficulty_dd,
                ft.Row([party_cr_min_tf, party_cr_max_tf], spacing=8, wrap=True),
            ],
            spacing=8,
        ),
        visible=False,
    )

    result_col = ft.Column(spacing=4)
    feedback_text = ft.Text("", size=11, color=design.T().magic)
    name_tf = ft.TextField(label="Nome nuovo incontro", value="Incontro Casuale", dense=True, border_radius=design.Radius.SM, border_color=design.field_style()['border_color'], focused_border_color=design.field_style()['focused_border_color'], bgcolor=design.field_style()['bgcolor'], text_style=design.field_style()['text_style'])

    # ------------------------------------------------------------------
    # Helper di stato
    # ------------------------------------------------------------------

    def _current_party_levels() -> list[int]:
        return [c.level for c in characters if c.id in checked_char_ids] + ghost_levels

    def _render_result() -> None:
        result_col.controls.clear()
        if not generated:
            result_col.controls.append(
                ft.Text("Premi «Genera» per creare un incontro.", size=12, color=design.T().text_3)
            )
            try:
                result_col.update()
            except RuntimeError:
                pass
            return

        counts = Counter(monster_display_name(m.get("name", "")) for m in generated)
        for name, qty in counts.items():
            inst = next(m for m in generated if monster_display_name(m.get("name", "")) == name)
            label = f"{name} ×{qty}" if qty > 1 else name
            result_col.controls.append(
                ft.Text(
                    f"• {label}  —  GS {inst.get('cr', '—')}, {parse_monster_xp(inst.get('xp', 0))} PE",
                    size=13, color=design.T().text,
                )
            )

        total_xp = sum(parse_monster_xp(m.get("xp", 0)) for m in generated)
        result_col.controls.append(ft.Container(height=4))

        if state["mode"] == "party":
            levels = _current_party_levels()
            if levels:
                res = calculate_difficulty([parse_monster_xp(m.get("xp", 0)) for m in generated], levels)
                diff_key = res["difficulty"]
                diff_label = DIFFICULTY_LABELS.get(diff_key, diff_key)
                diff_color = design.difficulty_color(diff_key)
                result_col.controls.append(
                    ft.Container(
                        content=ft.Text(
                            f"Difficoltà risultante: {diff_label.upper()}  "
                            f"(PE modificato {res['adjusted_xp']} su bersaglio {DIFFICULTY_LABELS.get(state.get('target_difficulty', ''), '')})",
                            size=12, weight=ft.FontWeight.BOLD, color=design.T().on_primary, text_align=ft.TextAlign.CENTER,
                        ),
                        bgcolor=diff_color, border_radius=design.Radius.MD, padding=ft.Padding.symmetric(vertical=8),
                        alignment=ft.Alignment.CENTER,
                    )
                )
        else:
            result_col.controls.append(
                ft.Text(f"PE totale (non modificato): {total_xp}", size=11, color=design.T().text_3)
            )

        try:
            result_col.update()
        except RuntimeError:
            pass

    def _rebuild_ghost_row() -> None:
        ghost_row.controls.clear()
        for i, lvl in enumerate(ghost_levels):
            ghost_row.controls.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Text(f"Lv.{lvl}", size=11, color=design.T().text_2),
                            ft.IconButton(ft.Icons.CLOSE, icon_size=12, icon_color=design.T().text_3,
                                          on_click=lambda e, ix=i: _remove_ghost(ix)),
                        ],
                        spacing=0, tight=True,
                    ),
                    padding=ft.Padding.symmetric(horizontal=6),
                    border=ft.Border.all(1, design.T().border), border_radius=12,
                )
            )
        try:
            ghost_row.update()
        except RuntimeError:
            pass

    def _add_ghost(_e: Any) -> None:
        lvl = max(1, min(20, _int_or(ghost_tf.value, 1)))
        ghost_levels.append(lvl)
        _rebuild_ghost_row()

    def _remove_ghost(idx: int) -> None:
        if 0 <= idx < len(ghost_levels):
            ghost_levels.pop(idx)
        _rebuild_ghost_row()

    # ------------------------------------------------------------------
    # Handler
    # ------------------------------------------------------------------

    def _on_mode_change(_e: Any) -> None:
        state["mode"] = mode_group.value or "direct"
        direct_col.visible = state["mode"] == "direct"
        party_col.visible = state["mode"] == "party"
        try:
            direct_col.update()
            party_col.update()
        except RuntimeError:
            pass

    def _on_theme_change(_e: Any) -> None:
        state["theme"] = theme_dd.value or ""

    def _on_char_check(_e: Any, char_id: str) -> None:
        if _e.control.value:
            checked_char_ids.add(char_id)
        else:
            checked_char_ids.discard(char_id)

    for cb in char_checks:
        cb.on_change = lambda e, cid=cb.data: _on_char_check(e, cid)

    def _on_generate(_e: Any) -> None:
        generated.clear()
        feedback_text.value = ""
        if state["mode"] == "direct":
            cr_min = _parse_cr(cr_min_tf.value, 0.0)
            cr_max = _parse_cr(cr_max_tf.value, 9999.0)
            count = _int_or(count_tf.value, 4)
            generated.extend(eg.generate_direct(monsters, state["theme"], cr_min, cr_max, count))
            if not generated:
                feedback_text.value = "Nessun mostro combacia con tema/GS scelti — allarga i filtri."
        else:
            levels = _current_party_levels()
            if not levels:
                feedback_text.value = "Seleziona almeno un personaggio (reale o fantasma) per il gruppo."
                try:
                    feedback_text.update()
                except RuntimeError:
                    pass
                return
            difficulty = difficulty_dd.value or "medio"
            state["target_difficulty"] = difficulty
            cr_min = _parse_cr(party_cr_min_tf.value, 0.0)
            cr_max = _parse_cr(party_cr_max_tf.value, 9999.0)
            generated.extend(eg.generate_for_party(monsters, levels, difficulty, state["theme"], cr_min, cr_max))
            if not generated:
                feedback_text.value = "Nessun mostro combacia con tema/GS scelti — allarga i filtri."
        _render_result()
        try:
            feedback_text.update()
        except RuntimeError:
            pass

    def _on_create(_e: Any) -> None:
        if not generated:
            feedback_text.value = "Genera prima un incontro (premi «Genera»)."
            try:
                feedback_text.update()
            except RuntimeError:
                pass
            return
        name = (name_tf.value or "").strip() or "Incontro Casuale"
        enc = master_repo.create_encounter(
            name=name, notes="Generato automaticamente dal Generatore di Incontri Casuali.",
            world_id=world_id,
        )
        if not enc:
            feedback_text.value = "Errore nella creazione dell'incontro — vedi log."
            try:
                feedback_text.update()
            except RuntimeError:
                pass
            return

        counts = Counter(monster_display_name(m.get("name", "")) for m in generated)
        idx = 0
        for name_key, qty in counts.items():
            inst = next(m for m in generated if monster_display_name(m.get("name", "")) == name_key)
            for i in range(qty):
                disp = f"{name_key} {i + 1}" if qty > 1 else name_key
                master_repo.add_member(
                    encounter_id=enc.id, kind="adhoc", display_name=disp,
                    ac=int(inst.get("ac", 10) or 10),
                    hp_current=int(inst.get("hp_max", 1) or 1),
                    hp_max=int(inst.get("hp_max", 1) or 1),
                    xp=parse_monster_xp(inst.get("xp", 0)),
                    initiative=10, order_index=idx,
                )
                idx += 1
        page.pop_dialog()
        on_created(enc.id)

    mode_group.on_change = _on_mode_change
    theme_dd.on_select = _on_theme_change

    _render_result()
    _rebuild_ghost_row()

    content = ft.Column(
        [
            mode_group,
            theme_dd,
            direct_col,
            party_col,
            ft.ElevatedButton(
                "Genera", icon=ft.Icons.CASINO, on_click=_on_generate,
                style=ft.ButtonStyle(bgcolor=design.T().primary_fill, color=design.T().on_primary_fill),
            ),
            ft.Divider(height=1, color=design.T().border),
            ft.Container(
                content=result_col, bgcolor=design.T().bg, border_radius=design.Radius.MD, padding=ft.Padding.all(12),
            ),
            ft.Divider(height=1, color=design.T().border),
            name_tf,
            ft.ElevatedButton(
                "Crea Nuovo Incontro con questi Mostri", icon=ft.Icons.ADD, on_click=_on_create,
                style=ft.ButtonStyle(bgcolor=design.T().magic, color=design.T().on_accent),
            ),
            feedback_text,
        ],
        spacing=10, scroll=ft.ScrollMode.AUTO,
        width=responsive_dialog_width(page, 460), height=620,
        tight=True,
    )

    dlg = ft.AlertDialog(
        title=design.dialog_title("Genera Incontro Casuale"),
        content=content,
        actions=wrap_dialog_actions([
            ft.TextButton("Chiudi", on_click=lambda e: page.pop_dialog()),
        ]),
    )
    page.show_dialog(dlg)
