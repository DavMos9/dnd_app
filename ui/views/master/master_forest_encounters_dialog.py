"""
Dialog "Genera Incontro per Ambiente" — Sezione Master, punto 10 del design
(`dnd_app/docs/master_section_design.md`). Copre 4 ambienti, tutti trascritti
dalla DMG con la stessa meccanica 1d12+1d8: Foresta Silvana (Cap.3, p.87,
2026-07-24), Incontri Urbani/Sott'Acqua/In Mare (Cap.5, p.114-118,
aggiunti il 2026-07-26 — una revisione precedente aveva concluso per errore
che non esistesse altro materiale pronto nel manuale, vedi
`data/game_data/forest_encounters.json` per il changelog completo e le
2 voci "Drago di bronzo" che non risolvono una scheda per scelta deliberata,
essendo l'età del drago non specificata dal manuale). Il Dropdown ambiente è
generico (`game_data.get_environment_names()`): nuovi ambienti aggiunti solo
al JSON compaiono qui automaticamente, senza altre modifiche di codice.

Meccanica di tiro: 1d12+1d8 (range 2-20), non un d20 piatto — privilegia i
risultati centrali della tabella, esattamente come stampato nel manuale.

Se il risultato cita una o più creature con una scheda nel bestiario
(`monsters.json`, tramite `ui/components/monster_picker.py`), viene mostrato
un pulsante "Vedi scheda" per ciascuna, che apre lo stesso stat block dialog
già condiviso con Forma Selvatica/Evocazioni/Rubrica NPC.

Accessibile da `MasterView` (bottone in header, "Incontri per Ambiente").

**"Aggiungi Incontro" (2026-07-31, segnalazione di Davide)**: prima il tiro
veniva generato e mostrato ma non c'era alcun modo di farlo arrivare nella
sezione "Incontri" — a differenza del Generatore di Incontri Casuali
(`master_encounter_generator_dialog.py`), che quel pulsante ce l'ha già.
Ora crea un nuovo `MasterEncounter` (`master_repo.create_encounter`) con le
note = il testo integrale della riga tirata, e un membro "adhoc" per ciascuna
creatura della riga risolta nel bestiario (stesse `ac`/`hp_max`/`xp` già usate
da "Vedi scheda"). **Le quantità non vengono moltiplicate**: la tabella DMG
scrive quantità in prosa dentro `text` ("2d4 gnoll", "1d4 gnoll and 2d4
iene") mai come numero strutturato in `creatures` — inventarne uno sarebbe
scrivere un dato di regolamento non presente nella fonte. Il Master legge la
riga (rimasta nelle note dell'incontro) e aggiunge le copie extra a mano con
"+ Aggiungi mostro", già esistente in `MasterEncounterView`.
"""

from __future__ import annotations

from typing import Any

import flet as ft

from data.game_data.game_data_loader import parse_monster_xp, game_data
from data.repositories import master_repo
from ui.components.monster_picker import load_monsters, show_stat_block_dialog
from ui.widgets import responsive_dialog_width, show_snack, wrap_dialog_actions
from ui import design


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


def show_forest_encounters_dialog(page: ft.Page, world_id: str = "") -> None:
    """Apre il dialog "Genera Incontro per Ambiente". Stato in closure,
    stesso pattern già in uso per `show_traps_dialog`/`show_health_hazards_dialog`.
    `world_id` (2026-08-12): il mondo correntemente selezionato in
    Modalità Master, inoltrato a `master_repo.create_encounter()`."""

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
        border_color=design.T().border, focused_border_color=design.T().primary,
        bgcolor=design.T().surface, label_style=ft.TextStyle(color=design.T().text_2),
        border_radius=design.field_style()['border_radius'], text_style=design.field_style()['text_style'])
    result_col = ft.Column(spacing=8)

    def _open_creature_sheet(m: dict[str, Any]) -> None:
        show_stat_block_dialog(page, str(m.get("name", "")), m)

    def _render_result() -> None:
        result_col.controls.clear()
        r = state["result"]
        if not r:
            result_col.controls.append(
                ft.Text("Premi «Tira 1d12+1d8» per generare un incontro.", size=12, color=design.T().text_3)
            )
        else:
            result_col.controls.append(
                ft.Text(
                    f"Tiro: {r['roll']}  (d12={r['d12']} + d8={r['d8']})",
                    size=13, weight=ft.FontWeight.BOLD, color=design.T().primary,
                )
            )
            result_col.controls.append(ft.Text(r["text"], size=13, color=design.T().text))
            if r.get("note"):
                result_col.controls.append(
                    ft.Text(r["note"], size=11, italic=True, color=design.T().text_3)
                )
            links: list[ft.Control] = []
            for cname in r.get("creatures", []):
                mdata = _resolve_creature(cname)
                if mdata:
                    links.append(
                        ft.OutlinedButton(
                            f"Vedi scheda: {cname}",
                            icon=ft.Icons.MENU_BOOK_OUTLINED,
                            style=ft.ButtonStyle(color=design.T().magic),
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

    # -- "Aggiungi Incontro" (2026-07-31) --------------------------------
    default_label = game_data.get_environment_table(default_env).get("label", default_env)
    name_tf = ft.TextField(
        label="Nome nuovo incontro", value=f"{default_label} — Incontro" if default_label else "",
        dense=True, **design.field_style(),
    )

    def _on_add_encounter(ev: Any) -> None:
        r = state["result"]
        if not r:
            show_snack(page, "Tira prima un incontro (premi «Tira 1d12+1d8»).", tone="warning")
            return
        name = (name_tf.value or "").strip() or "Incontro per Ambiente"
        notes = r.get("text", "")
        if r.get("note"):
            notes += f"\n\n{r['note']}"
        enc = master_repo.create_encounter(name=name, notes=notes, world_id=world_id)
        if not enc:
            show_snack(page, "Errore nella creazione dell'incontro — vedi log.", tone="danger")
            return
        added = 0
        for idx, cname in enumerate(r.get("creatures", [])):
            m = _resolve_creature(cname)
            if not m:
                continue
            master_repo.add_member(
                encounter_id=enc.id, kind="adhoc", display_name=str(m.get("name", cname)),
                ac=int(m.get("ac", 10) or 10),
                hp_current=int(m.get("hp_max", 1) or 1),
                hp_max=int(m.get("hp_max", 1) or 1),
                xp=parse_monster_xp(m.get("xp", 0)),
                initiative=10, order_index=idx,
            )
            added += 1
        msg = f"Incontro «{name}» creato"
        msg += (
            f" con {added} creatur{'a' if added == 1 else 'e'} (1 copia ciascuna — "
            "le quantità esatte sono nelle note, aggiungi le altre copie a mano)."
            if added else " (nessuna creatura con scheda nel bestiario da aggiungere)."
        )
        show_snack(page, msg)

    empty_state = not env_names
    content_controls: list[ft.Control] = []
    if empty_state:
        content_controls.append(
            ft.Text(
                "Nessun ambiente disponibile — dato non ancora trascritto.",
                size=13, color=design.T().text_3,
            )
        )
    else:
        # Audit anti-AI-slop (Arcane Ledger): scheletro condiviso `generator_
        # dialog_shell()` — intestazione + form "Parametri" + card
        # "risultato" (level=2, accento primario, la riga appena tirata) +
        # azione "Aggiungi Incontro". Nessun dato/callback cambia.
        form = ft.Column(
            [
                env_dd,
                ft.ElevatedButton(
                    "Tira 1d12+1d8", icon=ft.Icons.CASINO, on_click=_on_roll,
                    style=ft.ButtonStyle(bgcolor=design.T().primary_fill, color=design.T().on_primary_fill),
                ),
            ],
            spacing=design.Space.MD,
        )
        content_controls.append(design.generator_dialog_shell(
            "Genera Incontro per Ambiente", ft.Icons.FOREST, form, result_col,
            actions=[name_tf, ft.OutlinedButton("Aggiungi Incontro", icon=ft.Icons.ADD, on_click=_on_add_encounter)],
        ))

    content = ft.Column(
        content_controls, spacing=10, scroll=ft.ScrollMode.AUTO,
        width=responsive_dialog_width(page, 420), height=560, tight=True,
    )

    dlg = ft.AlertDialog(
        title=design.dialog_title("Genera Incontro per Ambiente") if empty_state else None,
        content=content,
        actions=wrap_dialog_actions([ft.TextButton("Chiudi", on_click=_close)]),
    )
    page.show_dialog(dlg)
