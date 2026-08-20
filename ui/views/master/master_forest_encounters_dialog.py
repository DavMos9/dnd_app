"""
Dialog "Genera Incontro per Ambiente" — Sezione Master, punto 10 del design
(`dnd_app/docs/master_section_design.md`). Copre 4 ambienti, tutti trascritti
dalla DMG con la stessa meccanica 1d12+1d8: Foresta Silvana (Cap.3, p.87),
Incontri Urbani/Sott'Acqua/In Mare (Cap.5, p.114-118) — vedi
`data/game_data/forest_encounters.json` per le 2 voci "Drago di bronzo" che
non risolvono una scheda per scelta deliberata, essendo l'età del drago non
specificata dal manuale. Il Dropdown ambiente è generico
(`game_data.get_environment_names()`): nuovi ambienti aggiunti solo al JSON
compaiono qui automaticamente, senza altre modifiche di codice.

Meccanica di tiro: 1d12+1d8 (range 2-20), non un d20 piatto — privilegia i
risultati centrali della tabella, esattamente come stampato nel manuale.

Se il risultato cita una o più creature con una scheda nel bestiario
(`monsters.json`, tramite `ui/components/monster_picker.py`), viene mostrato
un pulsante "Vedi scheda" per ciascuna, che apre lo stesso stat block dialog
già condiviso con Forma Selvatica/Evocazioni/Rubrica NPC.

Accessibile da `MasterView` (bottone in header, "Incontri per Ambiente").

**"Aggiungi Incontro"**: porta il tiro nella sezione "Incontri", stesso
pulsante già presente nel Generatore di Incontri Casuali
(`master_encounter_generator_dialog.py`). Crea un nuovo `MasterEncounter` (`master_repo.create_encounter`) con le
note = il testo integrale della riga tirata, e un membro "adhoc" per ciascuna
creatura della riga risolta nel bestiario (stesse `ac`/`hp_max`/`xp` già usate
da "Vedi scheda").

**Quantità (2026-08-20)**: la tabella DMG scrive la quantità in prosa dentro
`text` ("2d4 gnoll", "1d4 gnoll and 2d4 iene") mai come numero strutturato in
`creatures` — bug report Davide: "che tira i dadi e poi permette di creare
l'incontro descritto... permettiamo anche di inserire il risultato al
master, non costringiamolo al tiro automatico". Ogni creatura risolta ha ora
un campo "Quantità" (default 1, sempre editabile a mano) e, quando
`_suggest_quantities()` riesce ad abbinare con sicurezza un'espressione di
quantità della riga a quella creatura (stesso conteggio di numeri e
creature, unica euristica usata — mai un vero parser del regolamento: solo
un aiuto a leggere ciò che il testo già dice), un pulsante 🎲 che tira quella
espressione e precompila il campo. "Aggiungi Incontro" crea tante copie
numerate quante il campo Quantità indica al momento della conferma (stessa
convenzione "Nome 1"/"Nome 2" già in uso in "+ Aggiungi NPC dalla Rubrica" di
`MasterEncounterView`) — nessun tiro forzato, il Master può sempre ignorare
il dado e scrivere il numero che vuole.
"""

from __future__ import annotations

import re
from typing import Any

import flet as ft

from core import dice as core_dice
from data.game_data.game_data_loader import parse_monster_xp, game_data
from data.repositories import master_repo
from ui.components.monster_picker import load_monsters, show_stat_block_dialog
from ui.widgets import responsive_dialog_width, show_snack, wrap_dialog_actions
from ui import design

#: Percentuali tra parentesi ("(50%)") non sono mai una quantità — vanno
#: escluse prima di cercare i numeri, altrimenti "50" verrebbe scambiato per
#: una creatura in più.
_PAREN_RE = re.compile(r"\([^)]*\)")
#: Un'espressione di quantità: un dado "NdM" o un numero fisso.
_QTY_TOKEN_RE = re.compile(r"\d+d\d+|\d+")


def _suggest_quantities(text: str, creatures: list[str]) -> list[str]:
    """
    Prova ad abbinare, in ordine di lettura, un'espressione di quantità di
    `text` a ciascuna voce di `creatures` — le tabelle DMG scrivono sempre
    la quantità PRIMA del nome della creatura, nello stesso ordine in cui le
    creature compaiono in `creatures` (verificato a mano su tutte le voci
    multi-creatura di Foresta Silvana/Incontri Urbani/Sott'Acqua/In Mare:
    es. "1 gnoll signore del branco e 2d4 gnoll" → `["1", "2d4"]` per
    `["Gnoll Signore del Branco", "Gnoll"]`; "1d4 alci (75%) o 1 alce
    gigante (25%)" → `["1d4", "1"]` per `["Alce", "Alce Gigante"]").

    Ritorna una lista della stessa lunghezza di `creatures` — tutte voci
    vuote `""` se il conteggio dei numeri trovati non coincide con quello
    delle creature: MEGLIO nessun suggerimento che uno probabilmente
    sbagliato (es. una CD/un'altra quantità nella prosa che confonderebbe il
    conteggio) — il Master scrive comunque la quantità a mano in quel caso,
    non è mai bloccato dall'euristica.
    """
    if not creatures:
        return []
    stripped = _PAREN_RE.sub(" ", text)
    tokens = _QTY_TOKEN_RE.findall(stripped)
    if len(tokens) != len(creatures):
        return ["" for _ in creatures]
    return tokens


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
    `world_id`: il mondo correntemente selezionato in Modalità Master,
    inoltrato a `master_repo.create_encounter()`."""

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
            creatures = r.get("creatures", [])
            suggested = _suggest_quantities(r.get("text", ""), creatures)
            state["quantity_fields"] = {}
            creature_rows: list[ft.Control] = []
            for cname, sugg in zip(creatures, suggested):
                mdata = _resolve_creature(cname)
                if not mdata:
                    continue
                is_dice = bool(sugg) and "d" in sugg.lower()
                try:
                    prefill = int(sugg) if sugg and not is_dice else 1
                except ValueError:
                    prefill = 1
                qty_tf = ft.TextField(
                    label="Quantità", value=str(max(1, prefill)), width=64, dense=True,
                    keyboard_type=ft.KeyboardType.NUMBER, **design.field_style(),
                )
                state["quantity_fields"][cname] = qty_tf

                def _do_roll(ev: Any, tf: ft.TextField = qty_tf, formula: str = sugg) -> None:
                    total = core_dice.roll(formula).total
                    tf.value = str(max(1, total))
                    try:
                        tf.update()
                    except RuntimeError:
                        pass

                row_controls: list[ft.Control] = [
                    ft.OutlinedButton(
                        f"Vedi scheda: {cname}",
                        icon=ft.Icons.MENU_BOOK_OUTLINED,
                        style=ft.ButtonStyle(color=design.T().magic),
                        on_click=lambda e, mm=mdata: _open_creature_sheet(mm),
                    ),
                    qty_tf,
                ]
                if is_dice:
                    row_controls.append(ft.IconButton(
                        icon=ft.Icons.CASINO, tooltip=f"Tira {sugg} e precompila la quantità",
                        icon_color=design.T().primary_icon, on_click=_do_roll,
                    ))
                creature_rows.append(ft.Row(row_controls, spacing=6, wrap=True,
                                            vertical_alignment=ft.CrossAxisAlignment.CENTER))
            if creature_rows:
                result_col.controls.append(ft.Column(creature_rows, spacing=8))
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

    # -- "Aggiungi Incontro" ---------------------------------------------
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
        order_index = 0
        quantity_fields = state.get("quantity_fields", {})
        for cname in r.get("creatures", []):
            m = _resolve_creature(cname)
            if not m:
                continue
            qty_tf = quantity_fields.get(cname)
            try:
                qty = max(1, int((qty_tf.value or "1").strip())) if qty_tf is not None else 1
            except ValueError:
                qty = 1
            base_name = str(m.get("name", cname))
            for i in range(qty):
                master_repo.add_member(
                    encounter_id=enc.id, kind="adhoc",
                    display_name=f"{base_name} {i + 1}" if qty > 1 else base_name,
                    ac=int(m.get("ac", 10) or 10),
                    hp_current=int(m.get("hp_max", 1) or 1),
                    hp_max=int(m.get("hp_max", 1) or 1),
                    xp=parse_monster_xp(m.get("xp", 0)),
                    initiative=10, order_index=order_index,
                )
                order_index += 1
                added += 1
        msg = f"Incontro «{name}» creato"
        msg += (
            f" con {added} creatur{'a' if added == 1 else 'e'}."
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
