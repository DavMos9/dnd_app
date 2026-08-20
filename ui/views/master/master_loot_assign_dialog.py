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
from core import world_permissions as perm
from core import world_sync
from core.world_backend import LocalBackend
from data.models import LootStashEntry
from data.repositories import character_repo, loot_repo, world_repo
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
    "armor": "armor",
    # "weapon" non ha voce qui di proposito: non crea mai un `inventory_item`
    # generico, vedi `_create_recipient_item()`/`_handle_loot_assign` — una
    # voce "weapon" diventa sempre una riga `weapons`, non `inventory_items`.
}

_KIND_LABELS: dict[str, str] = {
    "item": "Oggetto",
    "magic_item": "Oggetto Magico",
    "artifact": "Artefatto",
    "poison": "Veleno",
    "gem": "Gemma",
    "art": "Oggetto d'Arte",
    "weapon": "Arma",
    "armor": "Armatura",
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

#: Default vuoto dei campi meccanici weapon/armor — stessi nomi delle
#: colonne di `loot_stash_entries` (2026-08-20), riusato da `simple_item()`
#: e `item_from_stash_entry()` per non ripetere 9 parametri ovunque.
_EMPTY_MECHANICS: dict[str, Any] = {
    "weapon_damage_dice": "", "weapon_damage_type": "", "weapon_category": "",
    "weapon_properties": "", "weapon_attack_bonus": 0, "weapon_damage_bonus": 0,
    "armor_ca_value": 0, "armor_type": "", "armor_effects": "",
}

#: Stesso elenco di `inventario_tab.py::_DAMAGE_TYPES` (senza "—", qui un
#: campo vuoto è già "non specificato" di suo) — bug report Davide
#: (2026-08-20): le voci arma/armatura del Bottino devono avere "le stesse
#: caselle di quando crei l'arma... nella sezione giocatore".
WEAPON_DAMAGE_TYPES: list[str] = [
    "Taglio", "Perforazione", "Contundente",
    "Fuoco", "Freddo", "Fulmine", "Tuono",
    "Acido", "Veleno", "Psichico", "Radiante",
    "Necrotico", "Forza",
]
WEAPON_CATEGORY_OPTIONS: list[tuple[str, str]] = [
    ("", "— non specificata —"),
    ("semplice", "Arma semplice"),
    ("guerra", "Arma da guerra"),
]
ARMOR_TYPE_OPTIONS: list[tuple[str, str]] = [
    ("", "— seleziona —"),
    ("leggera", "Leggera (+ mod DES)"),
    ("media", "Media (+ min(mod DES, 2))"),
    ("pesante", "Pesante (DES ignorato)"),
    ("scudo", "Scudo (bonus CA fisso)"),
]


def build_weapon_mechanics_fields(prefill: dict[str, Any] | None = None) -> tuple[ft.Control, "Callable[[], dict[str, Any]]"]:
    """
    Le caselle meccaniche di un'arma — stesso sottoinsieme di
    `inventario_tab.py::_open_weapon_dialog` che si applica a un'arma
    ancora senza personaggio (dado danno/tipo/categoria/proprietà/bonus
    magici; NON le impostazioni post-equipaggiamento come Versatile a due
    mani o l'override del totale d'attacco, che dipendono dal personaggio
    che la riceverà, non dalla voce di bottino in sé). Ritorna il
    controllo da inserire nel form e una funzione che, chiamata al
    momento del salvataggio, legge i valori correnti nella forma attesa
    da `simple_item(..., mechanics=...)`/`loot_repo.create_entry(**...)`.
    """
    prefill = prefill or {}
    dice_tf = ft.TextField(label="Dado danno (es. 1d8)", dense=True,
                            value=str(prefill.get("weapon_damage_dice", "")), **design.field_style())
    dtype_dd = ft.Dropdown(
        label="Tipo danno", dense=True, value=str(prefill.get("weapon_damage_type", "")) or None,
        options=[ft.DropdownOption(key="", text="— non specificato —")]
        + [ft.DropdownOption(key=t, text=t) for t in WEAPON_DAMAGE_TYPES],
        **design.field_style(),
    )
    category_dd = ft.Dropdown(
        label="Categoria", dense=True, value=str(prefill.get("weapon_category", "")) or None,
        options=[ft.DropdownOption(key=k, text=label) for k, label in WEAPON_CATEGORY_OPTIONS],
        **design.field_style(),
    )
    props_tf = ft.TextField(label="Proprietà (es. Accurata, Leggera, A due mani)", dense=True,
                             value=str(prefill.get("weapon_properties", "")), **design.field_style())
    atk_bonus_tf = ft.TextField(label="Bonus attacco (se magica)", dense=True,
                                 value=str(prefill.get("weapon_attack_bonus", 0) or 0),
                                 keyboard_type=ft.KeyboardType.NUMBER, **design.field_style())
    dmg_bonus_tf = ft.TextField(label="Bonus danno (se magica)", dense=True,
                                 value=str(prefill.get("weapon_damage_bonus", 0) or 0),
                                 keyboard_type=ft.KeyboardType.NUMBER, **design.field_style())

    def _read() -> dict[str, Any]:
        def _int(tf: ft.TextField) -> int:
            try:
                return int((tf.value or "0").strip())
            except ValueError:
                return 0
        return {
            "weapon_damage_dice": (dice_tf.value or "").strip(),
            "weapon_damage_type": dtype_dd.value or "",
            "weapon_category": category_dd.value or "",
            "weapon_properties": (props_tf.value or "").strip(),
            "weapon_attack_bonus": _int(atk_bonus_tf),
            "weapon_damage_bonus": _int(dmg_bonus_tf),
        }

    column = ft.Column(
        [ft.Row([dice_tf, dtype_dd], spacing=10, wrap=True),
         category_dd, props_tf,
         ft.Row([atk_bonus_tf, dmg_bonus_tf], spacing=10, wrap=True)],
        spacing=10,
    )
    return column, _read


def build_armor_mechanics_fields(prefill: dict[str, Any] | None = None) -> tuple[ft.Control, "Callable[[], dict[str, Any]]"]:
    """Controparte di `build_weapon_mechanics_fields()` per un'armatura —
    stessi campi di `inventario_tab.py::_open_item_dialog` per un oggetto
    di categoria "armor" (CA base, tipo, effetti testuali)."""
    prefill = prefill or {}
    ca_tf = ft.TextField(label="CA base", dense=True,
                          value=str(prefill.get("armor_ca_value", 0) or 0),
                          keyboard_type=ft.KeyboardType.NUMBER, **design.field_style())
    type_dd = ft.Dropdown(
        label="Tipo armatura", dense=True, value=str(prefill.get("armor_type", "")) or None,
        options=[ft.DropdownOption(key=k, text=label) for k, label in ARMOR_TYPE_OPTIONS],
        **design.field_style(),
    )
    effects_tf = ft.TextField(label="Effetti (testo libero)", dense=True, multiline=True,
                               min_lines=2, max_lines=5,
                               value=str(prefill.get("armor_effects", "")), **design.field_style())

    def _read() -> dict[str, Any]:
        try:
            ca_value = int((ca_tf.value or "0").strip())
        except ValueError:
            ca_value = 0
        return {
            "armor_ca_value": ca_value,
            "armor_type": type_dd.value or "",
            "armor_effects": (effects_tf.value or "").strip(),
        }

    column = ft.Column([ft.Row([ca_tf, type_dd], spacing=10, wrap=True), effects_tf], spacing=10)
    return column, _read


def simple_item(
    entry_kind: str,
    name: str,
    description: str = "",
    quantity: int = 1,
    source_note: str = "",
    requires_attunement: bool = False,
    stash_entry_id: str = "",
    stash_kind: str = "",
    mechanics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Voce non monetaria (oggetto/oggetto magico/artefatto/veleno/gemma/
    arte/arma/armatura).

    `stash_kind`: "master"/"party"/"" (non da uno stash) —
    contenitore d'ORIGINE della voce, se ne aveva uno. Serve a
    `_on_confirm()` per decidere se la cancellazione/consumo della voce
    d'origine deve passare dalla rete (`CMD_LOOT_STASH_DELETE`, solo per
    `"party"`) o restare locale (`"master"`, mai sincronizzato — vedi
    `_handle_loot_stash_delete` in `core/world_backend.py`, che rifiuta
    apposta una voce non "party").

    `mechanics`: SOLO per `entry_kind in ("weapon", "armor")` — dict con le
    9 chiavi di `_EMPTY_MECHANICS` sopra (stessi nomi di
    `LootStashEntry`/`loot_stash_entries`). Per ogni altro `entry_kind`
    resta ai default vuoti."""
    return {
        "entry_kind": entry_kind or "item",
        "name": name,
        "description": description,
        "quantity": max(1, quantity),
        "source_note": source_note,
        "requires_attunement": requires_attunement,
        "coins": {},
        "stash_entry_id": stash_entry_id,
        "stash_kind": stash_kind,
        **_EMPTY_MECHANICS,
        **(mechanics or {}),
    }


def coins_item(coins: dict[str, int], *, source_note: str = "", stash_entry_id: str = "",
               stash_kind: str = "") -> dict[str, Any]:
    """Voce puramente monetaria. `stash_kind`: vedi `simple_item()`."""
    return {
        "entry_kind": "coins",
        "name": "",
        "description": "",
        "quantity": 0,
        "source_note": source_note,
        "requires_attunement": False,
        "coins": {k: max(0, coins.get(k, 0)) for k in _COIN_ORDER},
        "stash_entry_id": stash_entry_id,
        "stash_kind": stash_kind,
        **_EMPTY_MECHANICS,
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
            source_note=entry.source_note, stash_entry_id=entry.id, stash_kind=entry.stash_kind,
        )
    heuristic_attunement = "sintonia" in (entry.description + " " + entry.source_note).lower()
    return simple_item(
        entry.entry_kind, entry.name, entry.description, entry.quantity,
        entry.source_note, requires_attunement=heuristic_attunement, stash_entry_id=entry.id,
        stash_kind=entry.stash_kind,
        mechanics={
            "weapon_damage_dice": entry.weapon_damage_dice,
            "weapon_damage_type": entry.weapon_damage_type,
            "weapon_category": entry.weapon_category,
            "weapon_properties": entry.weapon_properties,
            "weapon_attack_bonus": entry.weapon_attack_bonus,
            "weapon_damage_bonus": entry.weapon_damage_bonus,
            "armor_ca_value": entry.armor_ca_value,
            "armor_type": entry.armor_type,
            "armor_effects": entry.armor_effects,
        },
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


def _mechanics_kwargs(it: dict[str, Any]) -> dict[str, Any]:
    """Le 9 chiavi weapon_*/armor_* di `it` (vedi `_EMPTY_MECHANICS`), per
    `**`-splattarle in `loot_repo.create_entry()`/il payload
    `CMD_LOOT_STASH_ADD` — evita di perderle quando una voce "weapon"/
    "armor" viene rimandata al deposito/archivio invece che assegnata a un
    personaggio (`_move_or_create_stash()`/`_create_stash_split()` sotto)."""
    return {k: it.get(k, v) for k, v in _EMPTY_MECHANICS.items()}


def _create_recipient_item(character_id: str, it: dict[str, Any], quantity: int) -> None:
    """
    Scrive UNA voce non monetaria sulla scheda di `character_id` — punto
    unico per la scrittura locale (senza rete), usato sia dal ramo
    "destinazione singola" sia dal ramo "quote multiple" di `_on_confirm()`
    sotto. `it["entry_kind"] == "weapon"` crea una riga in `weapons` (mai
    `inventory_items`: un'arma ha le sue caselle dedicate — dado danno,
    tipo, categoria, proprietà, bonus magici — non un `description` libero);
    `"armor"` crea comunque un `inventory_items`, ma con `category="armor"`
    e i campi meccanici dedicati (CA, tipo, effetti), stessa forma già usata
    da `inventario_tab.py` per un'armatura creata a mano dal giocatore.
    `create_weapon()` non ha un parametro quantità (un'arma non si
    "impila"): per `quantity>1` (raro, es. 3 spade identiche ripartite su 3
    personaggi diversi) viene chiamata una volta per unità.
    """
    entry_kind = it.get("entry_kind", "item")
    if entry_kind == "weapon":
        for _ in range(max(1, quantity)):
            character_repo.create_weapon(
                character_id, it.get("name", ""),
                damage_dice=it.get("weapon_damage_dice", ""),
                damage_type=it.get("weapon_damage_type", ""),
                attack_bonus=int(it.get("weapon_attack_bonus", 0) or 0),
                damage_bonus=int(it.get("weapon_damage_bonus", 0) or 0),
                properties=it.get("weapon_properties", ""),
                weapon_category=it.get("weapon_category", ""),
                magic_description=it.get("description", ""),
                is_magical=bool(it.get("requires_attunement")) or bool(it.get("weapon_attack_bonus")
                                                                        or it.get("weapon_damage_bonus")),
            )
    elif entry_kind == "armor":
        character_repo.create_inventory_item(
            character_id, it.get("name", ""), quantity=quantity, category="armor",
            description=it.get("description", ""),
            ca_value=int(it.get("armor_ca_value", 0) or 0),
            armor_type=it.get("armor_type", ""),
            effects=it.get("armor_effects", ""),
            requires_attunement=bool(it.get("requires_attunement")),
        )
    else:
        category = _CATEGORY_BY_KIND.get(entry_kind, "misc")
        character_repo.create_inventory_item(
            character_id, it.get("name", ""), quantity=quantity, category=category,
            description=it.get("description", ""),
            requires_attunement=bool(it.get("requires_attunement")),
        )


def _recipient_item_payload(it: dict[str, Any], target_character_id: str, quantity: int) -> dict[str, Any]:
    """Controparte di `_create_recipient_item()` per il payload
    `CMD_LOOT_ASSIGN` (scrittura via rete, applicata da
    `core.world_backend._handle_loot_assign` — stessa identica logica di
    branching per `weapon`/`armor`, duplicata lì perché gira sull'host, non
    su questo dispositivo)."""
    category = "armor" if it["entry_kind"] == "armor" else _CATEGORY_BY_KIND.get(it["entry_kind"], "misc")
    return {
        "target_character_id": target_character_id, "name": it.get("name", ""),
        "quantity": quantity, "category": category,
        "description": it.get("description", ""),
        "requires_attunement": bool(it.get("requires_attunement")),
        "effects": it.get("armor_effects", "") if it["entry_kind"] == "armor" else "",
        "entry_kind": it["entry_kind"],
        "weapon_damage_dice": it.get("weapon_damage_dice", ""),
        "weapon_damage_type": it.get("weapon_damage_type", ""),
        "weapon_category": it.get("weapon_category", ""),
        "weapon_properties": it.get("weapon_properties", ""),
        "weapon_attack_bonus": it.get("weapon_attack_bonus", 0),
        "weapon_damage_bonus": it.get("weapon_damage_bonus", 0),
        "armor_ca_value": it.get("armor_ca_value", 0),
        "armor_type": it.get("armor_type", ""),
    }


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

def show_loot_assign_dialog(
    page: ft.Page,
    items: list[dict[str, Any]],
    *,
    on_committed: Callable[[], None] | None = None,
    world_id: str = "",
    device_id: str = "",
) -> None:
    """
    Apre il dialog di assegnazione per `items` (costruiti con
    `simple_item()`/`coins_item()`/`item_from_stash_entry()`). `on_committed`
    viene richiamato dopo una conferma andata a buon fine (es. per far
    ricaricare la lista alla scheda «Bottino»).

    `world_id`: il mondo correntemente selezionato in `MasterView` — "" per
    la modalità locale. Determina sia l'elenco dei personaggi destinatari
    (`character_repo.get_master_visible_characters()`) sia il mondo a cui
    viene assegnata una voce spedita al "Deposito del Gruppo" (mai
    all'"Archivio": resta sempre privato del dispositivo del Master, vedi
    `LootStashEntry` in `data/models.py`).

    `device_id`: identità di QUESTO dispositivo, necessaria per instradare
    l'assegnazione via rete (`CMD_LOOT_ASSIGN`/`CMD_LOOT_STASH_ADD`/
    `CMD_LOOT_STASH_MOVE`) quando `world_id` è valorizzato — senza,
    la scrittura resterebbe locale al dispositivo che esegue l'azione
    invece di raggiungere l'host. Con `world_id` valorizzato ma
    `device_id` vuoto/host irraggiungibile, la conferma fallisce con un
    errore esplicito invece di scrivere silenziosamente solo sulla
    replica locale.
    """
    _remote_backends: dict[str, Any] = {}

    def _resolve_backend():
        if not world_id:
            return None
        world = world_repo.get_world(world_id)
        if world is None:
            return None
        return world_sync.resolve_backend_for_world(
            world, device_id, LocalBackend(), _remote_backends,
        )
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

        # Instradamento in rete: con un mondo selezionato, OGNI scrittura
        # verso un personaggio o verso il deposito del gruppo passa da qui
        # — mai un'assegnazione locale-sola. Se l'host non è raggiungibile
        # si fallisce esplicitamente (fail closed) invece di scrivere
        # silenziosamente solo sulla replica di questo dispositivo.
        backend = _resolve_backend() if world_id else None
        if world_id and backend is None:
            error_text.value = (
                "Impossibile raggiungere l'host di questo mondo — riprova "
                "quando la connessione è di nuovo attiva."
            )
            try:
                error_text.update()
            except RuntimeError:
                pass
            return

        error_text.value = ""
        n_items = 0
        n_chars_coins = 0
        loot_assign_items: list[dict[str, Any]] = []
        loot_assign_coins: list[dict[str, Any]] = []

        def _consume_stash_source(it: dict[str, Any]) -> None:
            """Rimuove la voce d'origine (se questa assegnazione parte da
            una voce già in archivio/deposito) dopo che è stata consumata
            interamente da un'assegnazione a personaggio. Solo una voce
            d'origine "party" passa dalla rete (`CMD_LOOT_STASH_DELETE`,
            l'unica che l'handler host accetta — vedi il suo docstring):
            una voce "master" non ha mai lasciato questo dispositivo, quindi
            resta una cancellazione locale anche con un mondo selezionato."""
            stash_id = it.get("stash_entry_id")
            if not stash_id:
                return
            if world_id and backend is not None and it.get("stash_kind") == "party":
                backend.send_command(
                    world_id, device_id, perm.CMD_LOOT_STASH_DELETE,
                    {"entry_id": stash_id}, target_type="loot_stash", target_id=stash_id,
                )
            else:
                loot_repo.delete_entry(stash_id)

        def _move_or_create_stash(it: dict[str, Any], dest: str, quantity: int) -> None:
            """Crea (o sposta, se la voce viene già dall'archivio/deposito)
            una voce verso `DEST_PARTY`/`DEST_ARCHIVE`. Solo il deposito del
            gruppo sincronizza in rete — l'archivio del Master resta sempre
            locale, per design."""
            new_kind = "party" if dest == DEST_PARTY else "master"
            stash_id = it.get("stash_entry_id")
            if world_id and backend is not None:
                if stash_id:
                    backend.send_command(
                        world_id, device_id, perm.CMD_LOOT_STASH_MOVE,
                        {"entry_id": stash_id, "new_stash_kind": new_kind},
                        target_type="loot_stash", target_id=stash_id,
                    )
                elif new_kind == "party":
                    backend.send_command(
                        world_id, device_id, perm.CMD_LOOT_STASH_ADD,
                        {
                            "entry_kind": it["entry_kind"], "name": it.get("name", ""),
                            "description": it.get("description", ""), "quantity": quantity,
                            "source_note": it.get("source_note", ""),
                            **_mechanics_kwargs(it),
                        },
                        target_type="loot_stash",
                    )
                else:
                    loot_repo.create_entry(
                        "master", it["entry_kind"], name=it.get("name", ""),
                        description=it.get("description", ""), quantity=quantity,
                        source_note=it.get("source_note", ""),
                        **_mechanics_kwargs(it),
                    )
            elif stash_id:
                loot_repo.move_entry(stash_id, new_kind, new_world_id=world_id if new_kind == "party" else "")
            else:
                loot_repo.create_entry(
                    new_kind, it["entry_kind"], name=it.get("name", ""),
                    description=it.get("description", ""), quantity=quantity,
                    source_note=it.get("source_note", ""),
                    world_id=world_id if new_kind == "party" else "",
                    **_mechanics_kwargs(it),
                )

        def _create_stash_split(it: dict[str, Any], dest: str, quantity: int) -> None:
            """Variante di `_move_or_create_stash` per il ramo "quote
            multiple" (una voce indivisibile con quantity>1 ripartita su
            più destinazioni): crea SEMPRE una nuova voce, non sposta mai
            quella d'origine — la stessa riga non può "spostarsi" verso più
            di una destinazione. La voce d'origine (se esisteva) viene
            cancellata una sola volta a ripartizione completata, vedi il
            richiamo di `_consume_stash_source` più sotto — stesso
            comportamento del codice pre-rete."""
            new_kind = "party" if dest == DEST_PARTY else "master"
            if world_id and backend is not None and new_kind == "party":
                backend.send_command(
                    world_id, device_id, perm.CMD_LOOT_STASH_ADD,
                    {
                        "entry_kind": it["entry_kind"], "name": it.get("name", ""),
                        "description": it.get("description", ""), "quantity": quantity,
                        "source_note": it.get("source_note", ""),
                        **_mechanics_kwargs(it),
                    },
                    target_type="loot_stash",
                )
            else:
                loot_repo.create_entry(
                    new_kind, it["entry_kind"], name=it.get("name", ""),
                    description=it.get("description", ""), quantity=quantity,
                    source_note=it.get("source_note", ""),
                    world_id=world_id if new_kind == "party" else "",
                    **_mechanics_kwargs(it),
                )

        # -- Oggetti indivisibili --------------------------------------
        for st in included_states:
            it = st["item"]
            qty = it.get("quantity", 1)
            category = _CATEGORY_BY_KIND.get(it["entry_kind"], "misc")
            if qty <= 1:
                dest = st["dest"]
                if dest in (DEST_PARTY, DEST_ARCHIVE):
                    _move_or_create_stash(it, dest, qty)
                elif world_id and backend is not None:
                    loot_assign_items.append(_recipient_item_payload(it, dest, qty))
                    _consume_stash_source(it)
                else:
                    _create_recipient_item(dest, it, qty)
                    _consume_stash_source(it)
                n_items += 1
            else:
                for dest, share in st["shares"].items():
                    if share <= 0:
                        continue
                    if dest in (DEST_PARTY, DEST_ARCHIVE):
                        _create_stash_split(it, dest, share)
                    elif world_id and backend is not None:
                        loot_assign_items.append(_recipient_item_payload(it, dest, share))
                    else:
                        _create_recipient_item(dest, it, share)
                # L'intera quantità è sempre completamente ripartita (per la
                # validazione sopra) quindi la voce d'origine, se esisteva,
                # è del tutto consumata — sempre cancellata qui (mai
                # spostata: `_create_stash_split` sopra crea sempre righe
                # nuove per ogni destinazione, mai la stessa riga d'origine).
                if it.get("stash_entry_id"):
                    _consume_stash_source(it)
                n_items += 1

        # -- Monete -----------------------------------------------------
        if has_coins and char_options and coins_valid:
            result = lc.split_coins_by_percentage(total_coins, quotas, mode=coin_mode["value"])
            if not result["error"]:
                for cid, per in result["per_recipient"].items():
                    if not any(per.values()):
                        continue
                    if world_id and backend is not None:
                        loot_assign_coins.append({"target_character_id": cid, **per})
                    else:
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
                        _consume_stash_source(it)

        if world_id and backend is not None and (loot_assign_items or loot_assign_coins):
            result = backend.send_command(
                world_id, device_id, perm.CMD_LOOT_ASSIGN,
                {"items": loot_assign_items, "coins": loot_assign_coins},
                target_type="world", target_id=world_id,
            )
            if not result.success:
                error_text.value = result.error or "Assegnazione fallita."
                try:
                    error_text.update()
                except RuntimeError:
                    pass
                return

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
        # nessun feedback visibile. Stesso ordine già corretto in
        # `home_view.py._confirm_import()`.
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
