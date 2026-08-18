"""
Dialog di assegnazione del Bottino — passo 4 di `dnd_app/docs/loot_design.md`
§8 ("Ordine di lavoro"): un unico dialogo condiviso, richiamato da ogni punto
di generazione (Generatore Tesori, Generatore Oggetti Magici, Compendio
Oggetti Magici, Artefatti, Veleni) e dalla scheda «Bottino» della Sezione
Master, così il comportamento di assegnazione è identico ovunque — stesso
principio già seguito da `wrap_dialog_actions`/`responsive_dialog_width` per
evitare N copie leggermente diverse dello stesso dialog.

**Contratto di ingresso**: `show_loot_assign_dialog(page, items)` accetta una
lista di dict "voce di bottino assegnabile" — mai `LootStashEntry` o oggetti
di dominio diversi direttamente, per restare disaccoppiato sia dalla sorgente
(un tiro effimero del Generatore Tesori non ancora salvato da nessuna parte,
o una voce già persistita nell'archivio/deposito) sia dal formato interno di
ciascun generatore. Le funzioni `simple_item()`/`coins_item()`/
`item_from_stash_entry()` in fondo al modulo costruiscono questo dict nella
forma corretta — sono la sola API pubblica che gli altri dialog devono usare:

    {
        "entry_kind": "item"|"magic_item"|"artifact"|"poison"|"gem"|"art"|"coins",
        "name": str, "description": str, "quantity": int, "source_note": str,
        "requires_attunement": bool,
        "coins": {"copper":N,...} | {},   # popolato solo per entry_kind=="coins"
        "stash_entry_id": str,             # "" se la voce non proviene dall'archivio/deposito
    }

**Perché un'unica schermata invece del percorso "Cosa/A chi/Monete/Riepilogo"
a 4 passi descritto in `loot_design.md` §4**: nessun dialog della Sezione
Master usa oggi una struttura a wizard (il pattern consolidato è "un'unica
`ft.Column` scrollabile con un'area di anteprima che si aggiorna dal vivo",
già in uso in `master_treasure_dialog.py`/`master_magic_item_generator_dialog.py`).
Qui si segue lo stesso principio: ogni sezione (oggetti indivisibili, monete)
mostra la propria anteprima di ripartizione in tempo reale mentre il Master
compila i campi, così il requisito "nessuna sorpresa dopo, non si scrive
nulla prima della conferma" è comunque rispettato senza introdurre un pattern
UI nuovo nel progetto.

**Validazione tutto-o-niente**: il pulsante "Conferma" ricalcola tutte le
ripartizioni (monete con `core.loot_calculator.split_coins_by_percentage`,
quantità con `split_quantity_by_shares`) prima di scrivere qualunque cosa; se
anche una sola voce inclusa fallisce la validazione, nessuna scrittura viene
eseguita e l'errore compare accanto alla voce incriminata — mai un'assegnazione
parziale silenziosa.
"""

from __future__ import annotations

import logging
import random
from typing import Any, Callable

import flet as ft

from core import loot_calculator as lc
from data.models import LootStashEntry
from data.repositories import character_repo, loot_repo
from ui import design
from ui.widgets import responsive_dialog_width, wrap_dialog_actions, show_snack

logger = logging.getLogger(__name__)

#: Destinazioni "pseudo-personaggio" sempre disponibili, con o senza PG creati.
DEST_PARTY = "__party__"
DEST_ARCHIVE = "__archive__"

#: Categoria dell'oggetto d'inventario creato sulla scheda del personaggio,
#: per `entry_kind` — stessa tassonomia già in uso in `inventario_tab.py`
#: (`_OGGETTI_CATEGORIES = ["misc", "weapon", "tool", "magic"]`).
_CATEGORY_BY_KIND: dict[str, str] = {
    "item": "misc",
    "magic_item": "magic",
    "artifact": "magic",
    "poison": "misc",
    "gem": "misc",
    "art": "misc",
}

_KIND_LABELS: dict[str, str] = {
    "item": "Oggetto",
    "magic_item": "Oggetto Magico",
    "artifact": "Artefatto",
    "poison": "Veleno",
    "gem": "Gemma",
    "art": "Oggetto d'Arte",
    "coins": "Monete",
}

#: Stesso registro cromatico "arcano" già usato in `master_loot_view.py`
#: (voci d'archivio/deposito): il chip di una voce magica prende il tono
#: `magic` (indaco) invece del generico `primary`, per distinguerla a colpo
#: d'occhio dalle voci mondane anche in questo dialog di assegnazione.
_MAGIC_KINDS: frozenset[str] = frozenset({"magic_item", "artifact"})

_COIN_ORDER = ("platinum", "gold", "electrum", "silver", "copper")
_COIN_LABELS = {"copper": "mr", "silver": "ma", "electrum": "me", "gold": "mo", "platinum": "mp"}


# ---------------------------------------------------------------------------
# Costruttori del dict "voce assegnabile" — API pubblica per gli altri dialog
# ---------------------------------------------------------------------------

def simple_item(
    entry_kind: str,
    name: str,
    description: str = "",
    quantity: int = 1,
    source_note: str = "",
    requires_attunement: bool = False,
    stash_entry_id: str = "",
) -> dict[str, Any]:
    """Voce non monetaria (oggetto/oggetto magico/artefatto/veleno/gemma/arte)."""
    return {
        "entry_kind": entry_kind or "item",
        "name": name,
        "description": description,
        "quantity": max(1, quantity),
        "source_note": source_note,
        "requires_attunement": requires_attunement,
        "coins": {},
        "stash_entry_id": stash_entry_id,
    }


def coins_item(coins: dict[str, int], *, source_note: str = "", stash_entry_id: str = "") -> dict[str, Any]:
    """Voce puramente monetaria."""
    return {
        "entry_kind": "coins",
        "name": "",
        "description": "",
        "quantity": 0,
        "source_note": source_note,
        "requires_attunement": False,
        "coins": {k: max(0, coins.get(k, 0)) for k in _COIN_ORDER},
        "stash_entry_id": stash_entry_id,
    }


def item_from_stash_entry(entry: LootStashEntry) -> dict[str, Any]:
    """
    Ricostruisce il dict "voce assegnabile" da una `LootStashEntry` già
    persistita (archivio o deposito). `requires_attunement` non è una colonna
    di `loot_stash_entries` (la sintonia non è mai stata la fonte di verità
    per una voce d'archivio, solo per l'oggetto finale sulla scheda): qui è
    dedotta euristicamente cercando "sintonia" nel testo — corretta per ogni
    voce prodotta oggi dal Compendio/Generatore/Artefatti (che scrivono
    sempre quella parola quando si applica), ma resta un'euristica di
    comodo per l'interfaccia, non un dato di regolamento.
    """
    if entry.entry_kind == "coins":
        return coins_item(
            {
                "copper": entry.copper, "silver": entry.silver, "electrum": entry.electrum,
                "gold": entry.gold, "platinum": entry.platinum,
            },
            source_note=entry.source_note, stash_entry_id=entry.id,
        )
    heuristic_attunement = "sintonia" in (entry.description + " " + entry.source_note).lower()
    return simple_item(
        entry.entry_kind, entry.name, entry.description, entry.quantity,
        entry.source_note, requires_attunement=heuristic_attunement, stash_entry_id=entry.id,
    )


def save_items_to_stash(items: list[dict[str, Any]], *, stash_kind: str = "master", world_id: str = "") -> int:
    """
    Scorciatoia "Salva nell'archivio"/"Salva nel deposito": crea una nuova
    voce di stash per ciascun elemento di `items` (mai per quelli che hanno
    già `stash_entry_id` — quelli vivono già in uno dei due contenitori,
    spostarli è compito di `loot_repo.move_entry`, non di questa funzione).
    Ritorna quante voci sono state effettivamente create.
    """
    created = 0
    for it in items:
        if it.get("stash_entry_id"):
            continue
        if it["entry_kind"] == "coins":
            coins = it.get("coins", {})
            if not any(coins.values()):
                continue
            ok = loot_repo.create_entry(
                stash_kind, "coins", source_note=it.get("source_note", ""), world_id=world_id,
                copper=coins.get("copper", 0), silver=coins.get("silver", 0),
                electrum=coins.get("electrum", 0), gold=coins.get("gold", 0),
                platinum=coins.get("platinum", 0),
            )
        else:
            ok = loot_repo.create_entry(
                stash_kind, it["entry_kind"], name=it.get("name", ""),
                description=it.get("description", ""), quantity=it.get("quantity", 1),
                source_note=it.get("source_note", ""), world_id=world_id,
            )
        if ok:
            created += 1
    return created


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

def show_loot_assign_dialog(
    page: ft.Page,
    items: list[dict[str, Any]],
    *,
    on_committed: Callable[[], None] | None = None,
    world_id: str = "",
) -> None:
    """
    Apre il dialog di assegnazione per `items` (costruiti con
    `simple_item()`/`coins_item()`/`item_from_stash_entry()`). `on_committed`
    viene richiamato dopo una conferma andata a buon fine (es. per far
    ricaricare la lista alla scheda «Bottino»).

    `world_id` (2026-08-06): il mondo correntemente selezionato in
    `MasterView` — "" per la modalità locale. Determina sia l'elenco dei
    personaggi destinatari (`character_repo.get_master_visible_characters()`)
    sia il mondo a cui viene assegnata una voce spedita al "Deposito del
    Gruppo" (mai all'"Archivio": resta sempre privato del dispositivo del
    Master, vedi `LootStashEntry` in `data/models.py`).
    """
    characters = character_repo.get_master_visible_characters(world_id)
    char_options = [(c.id, f"{c.name} (Lv.{c.level})") for c in characters]
    dest_options = char_options + [(DEST_PARTY, "Deposito del Gruppo"), (DEST_ARCHIVE, "Archivio")]

    non_coin_items = [it for it in items if it["entry_kind"] != "coins"]
    coin_items = [it for it in items if it["entry_kind"] == "coins"]
    total_coins: dict[str, int] = {k: 0 for k in _COIN_ORDER}
    for it in coin_items:
        for k in _COIN_ORDER:
            total_coins[k] += it.get("coins", {}).get(k, 0)
    has_coins = any(total_coins.values())

    # Stato per voce indivisibile: inclusione, destinazione singola
    # (quantità 1) o quote per destinazione (quantità > 1).
    item_states: list[dict[str, Any]] = []
    default_dest = char_options[0][0] if char_options else DEST_ARCHIVE
    for it in non_coin_items:
        item_states.append({
            "item": it,
            "included": True,
            "dest": default_dest,
            "shares": {k: 0 for k, _ in dest_options},
        })

    # Quote monete (per personaggio soltanto — §5.1 di loot_design.md).
    quotas: dict[str, float] = {}
    if characters:
        n = len(characters)
        base = round(100.0 / n, 2)
        for i, (cid, _) in enumerate(char_options):
            quotas[cid] = base
        if char_options:
            diff = round(100.0 - base * n, 2)
            first_id = char_options[0][0]
            quotas[first_id] = round(quotas[first_id] + diff, 2)
    coin_mode = {"value": "denomination"}

    error_text = ft.Text("", size=12, color=design.T().danger)
    items_col = ft.Column(spacing=10)
    coins_col = ft.Column(spacing=8)

    # ------------------------------------------------------------------
    # Rendering — voci indivisibili
    # ------------------------------------------------------------------

    def _coin_summary_line(coins: dict[str, int]) -> str:
        parts = [f"{coins[k]} {_COIN_LABELS[k]}" for k in _COIN_ORDER if coins.get(k)]
        return ", ".join(parts) if parts else "nessuna moneta"

    def _dest_label(key: str) -> str:
        if key == DEST_PARTY:
            return "Deposito del Gruppo"
        if key == DEST_ARCHIVE:
            return "Archivio"
        for cid, label in char_options:
            if cid == key:
                return label
        return key

    def _render_item_card(state: dict[str, Any], index: int) -> ft.Control:
        it = state["item"]
        qty = it.get("quantity", 1)
        preview = (it.get("description", "") or "").split("\n")[0]
        if len(preview) > 130:
            preview = preview[:130].rstrip() + "…"

        # `expand=True` + `wrap=True` sulla stessa Row non è valido in Flet 0.85.3:
        # `wrap=True` genera un widget Flutter `Wrap`, che non supporta figli
        # `Expanded` (solo `Row`/`Column` lo supportano) — la combinazione produce
        # un crash silenzioso lato Flutter (nessun errore Python, il widget appare
        # come un riquadro grigio vuoto). Fix: niente `wrap` su questa Row, il nome
        # tronca con l'ellissi invece di andare a capo.
        header = ft.Row(
            [
                ft.Checkbox(value=state["included"], on_change=lambda e, i=index: _on_toggle_included(i, e)),
                design.chip(_KIND_LABELS.get(it["entry_kind"], it["entry_kind"]),
                            "magic" if it["entry_kind"] in _MAGIC_KINDS else "neutral"),
                ft.Text(f"{it.get('name', '')}" + (f" ×{qty}" if qty > 1 else ""),
                        size=13, weight=ft.FontWeight.BOLD, color=design.T().text, expand=True,
                        no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS),
            ],
            spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        body: list[ft.Control] = [header]
        if preview:
            body.append(ft.Text(preview, size=11, color=design.T().text_2))

        if qty <= 1:
            dd = ft.Dropdown(
                label="Destinatario", value=state["dest"], dense=True,
                options=[ft.DropdownOption(key=k, text=label) for k, label in dest_options],
                on_select=lambda e, i=index: _on_dest_change(i, e),
                **design.field_style(),
            )
            random_btn = ft.IconButton(
                icon=ft.Icons.CASINO_OUTLINED, tooltip="Distribuisci a caso tra i personaggi",
                disabled=not char_options,
                on_click=lambda e, i=index: _on_random_dest(i),
            )
            body.append(ft.Row([dd, random_btn], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER))
        else:
            assigned = sum(state["shares"].values())
            body.append(ft.Text(f"Ripartisci {qty} unità tra i destinatari:", size=11, color=design.T().text_3))
            rows: list[ft.Control] = []
            for key, label in dest_options:
                tf = ft.TextField(
                    value=str(state["shares"].get(key, 0)), width=64, dense=True,
                    keyboard_type=ft.KeyboardType.NUMBER,
                    on_change=lambda e, i=index, k=key: _on_share_change(i, k, e),
                    **design.field_style(),
                )
                rows.append(ft.Row([ft.Text(label, size=12, color=design.T().text, expand=True), tf],
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER))
            body.extend(rows)
            tone = "success" if assigned == qty else "warning"
            body.append(ft.Text(f"Assegnate: {assigned} / {qty}", size=11,
                                 color=design.tone_color(tone), weight=ft.FontWeight.BOLD))

        # Audit anti-AI-slop: `design.card()` (barra accento sinistra + ombra
        # a strati) invece del riquadro bordato manuale — stessa primitiva
        # già in uso nel resto dell'app per una card di livello standard
        # (level=1, nessun elemento è "hero" qui: sono N voci configurate in
        # parallelo, non un risultato singolo da mettere in risalto).
        return design.card(ft.Column(body, spacing=6))

    def _render_items() -> None:
        items_col.controls.clear()
        if not item_states:
            items_col.controls.append(ft.Text("Nessun oggetto da assegnare.", size=12, color=design.T().text_3))
        else:
            for i, st in enumerate(item_states):
                items_col.controls.append(_render_item_card(st, i))
        try:
            items_col.update()
        except RuntimeError:
            pass

    def _on_toggle_included(i: int, e: Any) -> None:
        item_states[i]["included"] = bool(e.control.value)

    def _on_dest_change(i: int, e: Any) -> None:
        item_states[i]["dest"] = e.control.value or default_dest

    def _on_random_dest(i: int) -> None:
        if not char_options:
            return
        item_states[i]["dest"] = random.choice(char_options)[0]
        _render_items()

    def _on_share_change(i: int, key: str, e: Any) -> None:
        try:
            value = max(0, int((e.control.value or "0").strip()))
        except ValueError:
            value = 0
        item_states[i]["shares"][key] = value
        _render_items()

    # ------------------------------------------------------------------
    # Rendering — monete
    # ------------------------------------------------------------------

    def _render_coins() -> None:
        coins_col.controls.clear()
        if not has_coins:
            return
        coins_col.controls.append(ft.Divider(height=1, color=design.T().border))
        coins_col.controls.append(ft.Text("Monete", size=13, weight=ft.FontWeight.BOLD, color=design.T().text))
        coins_col.controls.append(ft.Text(_coin_summary_line(total_coins), size=12, color=design.T().text_2))

        if not char_options:
            coins_col.controls.append(ft.Text(
                "Nessun personaggio disponibile: le monete possono solo essere salvate nell'archivio o nel deposito.",
                size=11, color=design.T().text_3, italic=True,
            ))
            try:
                coins_col.update()
            except RuntimeError:
                pass
            return

        mode_group = ft.RadioGroup(
            value=coin_mode["value"],
            content=ft.Row([
                ft.Radio(value="denomination", label="Per denominazione"),
                ft.Radio(value="value", label="Per valore"),
            ], wrap=True),
            on_change=_on_mode_change,
        )
        coins_col.controls.append(mode_group)

        quota_rows: list[ft.Control] = []
        for cid, label in char_options:
            tf = ft.TextField(
                value=f"{quotas.get(cid, 0):g}", width=70, dense=True, suffix="%",
                keyboard_type=ft.KeyboardType.NUMBER,
                on_change=lambda e, c=cid: _on_quota_change(c, e),
                **design.field_style(),
            )
            quota_rows.append(ft.Row([ft.Text(label, size=12, color=design.T().text, expand=True), tf],
                                      vertical_alignment=ft.CrossAxisAlignment.CENTER))
        coins_col.controls.extend(quota_rows)
        coins_col.controls.append(
            ft.OutlinedButton("Reimposta parti uguali", icon=ft.Icons.BALANCE,
                              on_click=lambda e: _on_reset_quotas())
        )

        preview_col = ft.Column(spacing=4)
        _render_coin_preview(preview_col)
        coins_col.controls.append(preview_col)
        try:
            coins_col.update()
        except RuntimeError:
            pass

    def _render_coin_preview(preview_col: ft.Column) -> None:
        preview_col.controls.clear()
        err = lc.validate_quotas(quotas)
        if err:
            preview_col.controls.append(ft.Text(err, size=11, color=design.T().danger))
            return
        result = lc.split_coins_by_percentage(total_coins, quotas, mode=coin_mode["value"])
        if result["error"]:
            preview_col.controls.append(ft.Text(result["error"], size=11, color=design.T().danger))
            return
        for cid, label in char_options:
            per = result["per_recipient"].get(cid, {})
            preview_col.controls.append(
                ft.Text(f"{label}: {_coin_summary_line(per)}", size=11, color=design.T().text_2)
            )

    def _on_mode_change(e: Any) -> None:
        coin_mode["value"] = e.control.value or "denomination"
        _render_coins()

    def _on_quota_change(cid: str, e: Any) -> None:
        try:
            value = float((e.control.value or "0").replace(",", "."))
        except ValueError:
            value = 0.0
        quotas[cid] = value
        _render_coins()

    def _on_reset_quotas() -> None:
        n = len(char_options)
        if n == 0:
            return
        base = round(100.0 / n, 2)
        for cid, _ in char_options:
            quotas[cid] = base
        diff = round(100.0 - base * n, 2)
        quotas[char_options[0][0]] = round(quotas[char_options[0][0]] + diff, 2)
        _render_coins()

    # ------------------------------------------------------------------
    # Conferma
    # ------------------------------------------------------------------

    def _on_confirm(e: Any) -> None:
        errors: list[str] = []

        included_states = [st for st in item_states if st["included"]]
        for st in included_states:
            qty = st["item"].get("quantity", 1)
            if qty > 1:
                err = lc.split_quantity_by_shares(qty, st["shares"])
                if err:
                    errors.append(f"«{st['item'].get('name', '')}»: {err}")

        coins_valid = True
        if has_coins and char_options:
            err = lc.validate_quotas(quotas)
            if err:
                errors.append(f"Monete: {err}")
                coins_valid = False

        if errors:
            error_text.value = " · ".join(errors)
            try:
                error_text.update()
            except RuntimeError:
                pass
            return

        error_text.value = ""
        n_items = 0
        n_chars_coins = 0

        # -- Oggetti indivisibili --------------------------------------
        for st in included_states:
            it = st["item"]
            qty = it.get("quantity", 1)
            category = _CATEGORY_BY_KIND.get(it["entry_kind"], "misc")
            if qty <= 1:
                dest = st["dest"]
                if dest in (DEST_PARTY, DEST_ARCHIVE):
                    if it.get("stash_entry_id"):
                        loot_repo.move_entry(it["stash_entry_id"], "party" if dest == DEST_PARTY else "master")
                    else:
                        loot_repo.create_entry(
                            "party" if dest == DEST_PARTY else "master", it["entry_kind"],
                            name=it.get("name", ""), description=it.get("description", ""),
                            quantity=qty, source_note=it.get("source_note", ""),
                            world_id=world_id if dest == DEST_PARTY else "",
                        )
                else:
                    character_repo.create_inventory_item(
                        dest, it.get("name", ""), quantity=qty, category=category,
                        description=it.get("description", ""),
                        requires_attunement=bool(it.get("requires_attunement")),
                    )
                    if it.get("stash_entry_id"):
                        loot_repo.delete_entry(it["stash_entry_id"])
                n_items += 1
            else:
                for dest, share in st["shares"].items():
                    if share <= 0:
                        continue
                    if dest in (DEST_PARTY, DEST_ARCHIVE):
                        loot_repo.create_entry(
                            "party" if dest == DEST_PARTY else "master", it["entry_kind"],
                            name=it.get("name", ""), description=it.get("description", ""),
                            quantity=share, source_note=it.get("source_note", ""),
                            world_id=world_id if dest == DEST_PARTY else "",
                        )
                    else:
                        character_repo.create_inventory_item(
                            dest, it.get("name", ""), quantity=share, category=category,
                            description=it.get("description", ""),
                            requires_attunement=bool(it.get("requires_attunement")),
                        )
                # L'intera quantità è sempre completamente ripartita (per la
                # validazione sopra) quindi la voce d'origine, se esisteva,
                # è del tutto consumata.
                if it.get("stash_entry_id"):
                    loot_repo.delete_entry(it["stash_entry_id"])
                n_items += 1

        # -- Monete -----------------------------------------------------
        if has_coins and char_options and coins_valid:
            result = lc.split_coins_by_percentage(total_coins, quotas, mode=coin_mode["value"])
            if not result["error"]:
                for cid, per in result["per_recipient"].items():
                    if not any(per.values()):
                        continue
                    existing = character_repo.get_currencies(cid)
                    character_repo.update_currencies(
                        cid,
                        (existing.copper if existing else 0) + per.get("copper", 0),
                        (existing.silver if existing else 0) + per.get("silver", 0),
                        (existing.electrum if existing else 0) + per.get("electrum", 0),
                        (existing.gold if existing else 0) + per.get("gold", 0),
                        (existing.platinum if existing else 0) + per.get("platinum", 0),
                    )
                    n_chars_coins += 1
                for it in coin_items:
                    if it.get("stash_entry_id"):
                        loot_repo.delete_entry(it["stash_entry_id"])

        msg_bits = []
        if n_items:
            msg_bits.append(f"{n_items} ogget{'to' if n_items == 1 else 'ti'}")
        if n_chars_coins:
            msg_bits.append(f"monete a {n_chars_coins} personagg{'io' if n_chars_coins == 1 else 'i'}")
        # Chiudere il dialogo PRIMA di mostrare lo SnackBar, mai dopo: in Flet
        # 0.85.3 `show_dialog()`/`pop_dialog()` operano su un singolo dialogo
        # attivo (non uno stack) — chiamare `show_snack()` (che a sua volta usa
        # `show_dialog()` per lo SnackBar) mentre l'`AlertDialog` di conferma è
        # ancora aperto lo sostituisce silenziosamente, e il `pop_dialog()`
        # successivo chiude lo SnackBar appena aperto invece del dialogo —
        # nessun feedback visibile, bug segnalato da Davide il 2026-07-31.
        # Stesso ordine già corretto in `home_view.py._confirm_import()`.
        page.pop_dialog()
        show_snack(page, "Assegnato: " + ", ".join(msg_bits) if msg_bits else "Nessuna voce assegnata.")
        if on_committed:
            on_committed()

    # ------------------------------------------------------------------

    _render_items()
    _render_coins()

    def _close(ev: Any) -> None:
        page.pop_dialog()

    content = ft.Column(
        [items_col, coins_col, error_text],
        spacing=10, scroll=ft.ScrollMode.AUTO,
        width=responsive_dialog_width(page, 460), height=560, tight=True,
    )

    dlg = ft.AlertDialog(
        title=design.dialog_title("Assegna Bottino", icon=ft.Icons.INVENTORY_2_OUTLINED),
        content=content,
        actions=wrap_dialog_actions([
            ft.TextButton("Annulla", on_click=_close),
            ft.ElevatedButton("Conferma assegnazione", icon=ft.Icons.CHECK, on_click=_on_confirm,
                              style=ft.ButtonStyle(bgcolor=design.T().primary_fill, color=design.T().on_primary_fill)),
        ]),
    )
    page.show_dialog(dlg)
