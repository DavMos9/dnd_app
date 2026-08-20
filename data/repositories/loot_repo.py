"""
Repository per il Bottino (`dnd_app/docs/loot_design.md`): archivio privato
del Master e deposito comune del gruppo, entrambi ospitati sulla stessa
tabella `loot_stash_entries`, distinta dal campo `stash_kind`.

Deliberatamente indipendente da `character_repo.py`/`master_repo.py` —
`loot_stash_entries` non ha alcuna FK obbligatoria: una voce di bottino non
appartiene a nessun personaggio finché non viene assegnata (quel passaggio
usa direttamente `character_repo.create_inventory_item()`/
`get_currencies()`/`update_currencies()`, mai una scrittura da qui).
`world_id` (esteso a ENTRAMBI gli `stash_kind` — vedi
`LootStashEntry` in data/models.py): "" per una voce locale/di nessun
mondo (comportamento di sempre per chi non usa il Multiplayer), altrimenti
l'id del mondo selezionato in `MasterView` — questo modulo si limita a
filtrare per uguaglianza esatta, la UI (`master_loot_view.py`) decide quale
mondo passare.
"""

import logging
from datetime import datetime

from data.database import get_connection
from data.models import LootStashEntry

logger = logging.getLogger(__name__)


def _s(value) -> str:
    """Converte None in stringa vuota per i campi TEXT NOT NULL."""
    return value if value is not None else ""


def _row_to_entry(row) -> LootStashEntry:
    d = dict(row)
    return LootStashEntry(
        id=d["id"],
        stash_kind=d.get("stash_kind", "master"),
        world_id=d.get("world_id", ""),
        entry_kind=d.get("entry_kind", "item"),
        name=d.get("name", ""),
        description=d.get("description", ""),
        quantity=d.get("quantity", 1),
        source_note=d.get("source_note", ""),
        copper=d.get("copper", 0),
        silver=d.get("silver", 0),
        electrum=d.get("electrum", 0),
        gold=d.get("gold", 0),
        platinum=d.get("platinum", 0),
        added_by_device_id=d.get("added_by_device_id", ""),
        weapon_damage_dice=d.get("weapon_damage_dice", ""),
        weapon_damage_type=d.get("weapon_damage_type", ""),
        weapon_category=d.get("weapon_category", ""),
        weapon_properties=d.get("weapon_properties", ""),
        weapon_attack_bonus=d.get("weapon_attack_bonus", 0),
        weapon_damage_bonus=d.get("weapon_damage_bonus", 0),
        weapon_magic_damages=d.get("weapon_magic_damages", "[]") or "[]",
        armor_ca_value=d.get("armor_ca_value", 0),
        armor_type=d.get("armor_type", ""),
        armor_effects=d.get("armor_effects", ""),
        created_at=d.get("created_at", ""),
        updated_at=d.get("updated_at", ""),
    )


def get_entries(stash_kind: str = "master", world_id: str = "") -> list[LootStashEntry]:
    """
    Voci di un contenitore, ordinate per data di creazione (le più vecchie
    per prime — un archivio/deposito si legge come una lista cronologica).
    `world_id` filtra esattamente (stringa vuota = solo le voci senza mondo,
    coerente con l'archivio del Master pre-multiplayer).
    """
    conn = None
    try:
        conn = get_connection()
        rows = conn.execute(
            """SELECT * FROM loot_stash_entries
               WHERE stash_kind=? AND world_id=?
               ORDER BY created_at ASC""",
            (stash_kind, world_id),
        ).fetchall()
        return [_row_to_entry(r) for r in rows]
    except Exception as e:
        logger.error(f"Errore get_entries: {e}")
        return []
    finally:
        if conn is not None:
            conn.close()


def create_entry(
    stash_kind: str,
    entry_kind: str,
    name: str = "",
    description: str = "",
    quantity: int = 1,
    source_note: str = "",
    world_id: str = "",
    copper: int = 0,
    silver: int = 0,
    electrum: int = 0,
    gold: int = 0,
    platinum: int = 0,
    added_by_device_id: str = "",
    weapon_damage_dice: str = "",
    weapon_damage_type: str = "",
    weapon_category: str = "",
    weapon_properties: str = "",
    weapon_attack_bonus: int = 0,
    weapon_damage_bonus: int = 0,
    weapon_magic_damages: str = "[]",
    armor_ca_value: int = 0,
    armor_type: str = "",
    armor_effects: str = "",
) -> LootStashEntry | None:
    """
    Crea una nuova voce di bottino. Ritorna la voce creata, o None in caso
    di errore. Per `entry_kind="coins"` `name`/`description` restano vuoti
    e il valore vive nelle 5 colonne valuta. I campi `weapon_*`/`armor_*`
    (2026-08-20) si usano solo per `entry_kind in ("weapon", "armor")` —
    vedi il docstring di `LootStashEntry` in `data/models.py`.
    """
    import uuid as _uuid
    entry_id = str(_uuid.uuid4())
    now = datetime.now().isoformat()
    conn = None
    try:
        conn = get_connection()
        conn.execute(
            """
            INSERT INTO loot_stash_entries (
                id, stash_kind, world_id, entry_kind, name, description,
                quantity, source_note,
                copper, silver, electrum, gold, platinum,
                added_by_device_id,
                weapon_damage_dice, weapon_damage_type, weapon_category,
                weapon_properties, weapon_attack_bonus, weapon_damage_bonus,
                weapon_magic_damages,
                armor_ca_value, armor_type, armor_effects,
                created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                entry_id, _s(stash_kind) or "master", _s(world_id),
                _s(entry_kind) or "item", _s(name), _s(description),
                max(1, quantity) if entry_kind != "coins" else max(0, quantity),
                _s(source_note),
                max(0, copper), max(0, silver), max(0, electrum),
                max(0, gold), max(0, platinum),
                _s(added_by_device_id),
                _s(weapon_damage_dice), _s(weapon_damage_type), _s(weapon_category),
                _s(weapon_properties), weapon_attack_bonus, weapon_damage_bonus,
                _s(weapon_magic_damages) or "[]",
                armor_ca_value, _s(armor_type), _s(armor_effects),
                now, now,
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM loot_stash_entries WHERE id=?", (entry_id,)
        ).fetchone()
        return _row_to_entry(row) if row else None
    except Exception as e:
        logger.error(f"Errore create_entry: {e}")
        return None
    finally:
        if conn is not None:
            conn.close()


def update_entry(
    entry_id: str,
    name: str = "",
    description: str = "",
    quantity: int = 1,
    source_note: str = "",
    weapon_damage_dice: str = "",
    weapon_damage_type: str = "",
    weapon_category: str = "",
    weapon_properties: str = "",
    weapon_attack_bonus: int = 0,
    weapon_damage_bonus: int = 0,
    weapon_magic_damages: str = "[]",
    armor_ca_value: int = 0,
    armor_type: str = "",
    armor_effects: str = "",
    entry_kind: str = "",
) -> bool:
    """
    Aggiorna i campi testuali/quantità di una voce non monetaria. I
    parametri `weapon_*`/`armor_*` vanno passati SOLO dal dialog di
    modifica di una voce "weapon"/"armor" (`master_loot_view.py`), che
    rilegge sempre il set COMPLETO dei valori correnti prima di inviarli —
    stesso principio già in uso per le monete (mai un aggiornamento
    parziale): per ogni altra voce restano ai default '' /0, coerenti con
    `create_entry()`.

    `entry_kind`: "" (default) lascia il tipo invariato — bug report Davide
    (2026-08-20): "quando un artefatto... modifico deve avere la possibilità
    di essere modificato in toto, e cioè può essere selezionato il tipo"
    (assegnare quell'effetto a un'arma, un anello, un abito, ecc.). Prima
    `update_entry()` non toccava affatto la colonna `entry_kind`: una volta
    salvata, una voce restava per sempre del tipo scelto alla creazione. Un
    valore non vuoto sovrascrive il tipo — nessun controllo di compatibilità
    qui: è compito del chiamante (`master_loot_view.py::_open_edit_dialog`)
    mostrare/nascondere le caselle meccaniche coerenti col nuovo tipo.
    """
    conn = None
    try:
        conn = get_connection()
        conn.execute(
            """UPDATE loot_stash_entries
               SET name=?, description=?, quantity=?, source_note=?,
                   weapon_damage_dice=?, weapon_damage_type=?, weapon_category=?,
                   weapon_properties=?, weapon_attack_bonus=?, weapon_damage_bonus=?,
                   weapon_magic_damages=?,
                   armor_ca_value=?, armor_type=?, armor_effects=?,
                   entry_kind=COALESCE(NULLIF(?, ''), entry_kind),
                   updated_at=?
               WHERE id=?""",
            (_s(name), _s(description), max(0, quantity), _s(source_note),
             _s(weapon_damage_dice), _s(weapon_damage_type), _s(weapon_category),
             _s(weapon_properties), weapon_attack_bonus, weapon_damage_bonus,
             _s(weapon_magic_damages) or "[]",
             armor_ca_value, _s(armor_type), _s(armor_effects),
             _s(entry_kind),
             datetime.now().isoformat(), entry_id),
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Errore update_entry: {e}")
        return False
    finally:
        if conn is not None:
            conn.close()


def delete_entry(entry_id: str) -> bool:
    conn = None
    try:
        conn = get_connection()
        conn.execute("DELETE FROM loot_stash_entries WHERE id=?", (entry_id,))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Errore delete_entry: {e}")
        return False
    finally:
        if conn is not None:
            conn.close()


def get_entry(entry_id: str) -> LootStashEntry | None:
    """Una singola voce per id — usata dagli handler di rete
    (`core/world_backend.py::_handle_loot_stash_*`) per includere lo stato
    aggiornato nell'evento del giornale dopo un `move_entry`/`update_entry`,
    così le repliche possono applicarlo senza un'altra interrogazione."""
    conn = None
    try:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM loot_stash_entries WHERE id=?", (entry_id,)
        ).fetchone()
        return _row_to_entry(row) if row else None
    except Exception as e:
        logger.error(f"Errore get_entry({entry_id}): {e}")
        return None
    finally:
        if conn is not None:
            conn.close()


def replica_upsert_entry(entry: dict) -> bool:
    """
    Materializza sulla replica locale una voce del deposito comune del
    gruppo (`stash_kind="party"`) arrivata dall'host — via snapshot
    (`core/world_sync.py::_refresh_snapshot_derived_state`) o via evento
    incrementale (`apply_event_to_replica`). A differenza delle tabelle
    figlio di un personaggio (`character_export.py`), qui l'id NON viene
    mai rigenerato: un `INSERT OR REPLACE` chiavato su `id` è corretto
    perché l'id di una voce di bottino è già stabile e condiviso da tutti i
    dispositivi (generato una sola volta da `create_entry()` sull'host),
    non un dettaglio interno di una singola replica.
    """
    conn = None
    try:
        conn = get_connection()
        conn.execute(
            """
            INSERT INTO loot_stash_entries (
                id, stash_kind, world_id, entry_kind, name, description,
                quantity, source_note,
                copper, silver, electrum, gold, platinum,
                added_by_device_id,
                weapon_damage_dice, weapon_damage_type, weapon_category,
                weapon_properties, weapon_attack_bonus, weapon_damage_bonus,
                weapon_magic_damages,
                armor_ca_value, armor_type, armor_effects,
                created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                stash_kind=excluded.stash_kind, world_id=excluded.world_id,
                entry_kind=excluded.entry_kind, name=excluded.name,
                description=excluded.description, quantity=excluded.quantity,
                source_note=excluded.source_note,
                copper=excluded.copper, silver=excluded.silver,
                electrum=excluded.electrum, gold=excluded.gold,
                platinum=excluded.platinum,
                weapon_damage_dice=excluded.weapon_damage_dice,
                weapon_damage_type=excluded.weapon_damage_type,
                weapon_category=excluded.weapon_category,
                weapon_properties=excluded.weapon_properties,
                weapon_attack_bonus=excluded.weapon_attack_bonus,
                weapon_damage_bonus=excluded.weapon_damage_bonus,
                weapon_magic_damages=excluded.weapon_magic_damages,
                armor_ca_value=excluded.armor_ca_value,
                armor_type=excluded.armor_type,
                armor_effects=excluded.armor_effects,
                updated_at=excluded.updated_at
            """,
            (
                str(entry.get("id") or ""), _s(entry.get("stash_kind")) or "party",
                _s(entry.get("world_id")), _s(entry.get("entry_kind")) or "item",
                _s(entry.get("name")), _s(entry.get("description")),
                int(entry.get("quantity") or 0), _s(entry.get("source_note")),
                int(entry.get("copper") or 0), int(entry.get("silver") or 0),
                int(entry.get("electrum") or 0), int(entry.get("gold") or 0),
                int(entry.get("platinum") or 0), _s(entry.get("added_by_device_id")),
                _s(entry.get("weapon_damage_dice")), _s(entry.get("weapon_damage_type")),
                _s(entry.get("weapon_category")), _s(entry.get("weapon_properties")),
                int(entry.get("weapon_attack_bonus") or 0), int(entry.get("weapon_damage_bonus") or 0),
                _s(entry.get("weapon_magic_damages")) or "[]",
                int(entry.get("armor_ca_value") or 0), _s(entry.get("armor_type")),
                _s(entry.get("armor_effects")),
                _s(entry.get("created_at")) or datetime.now().isoformat(),
                _s(entry.get("updated_at")) or datetime.now().isoformat(),
            ),
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Errore replica_upsert_entry: {e}")
        return False
    finally:
        if conn is not None:
            conn.close()


def replica_delete_entry(entry_id: str) -> bool:
    """Controparte di `replica_upsert_entry` per una voce rimossa
    dall'host (eliminata, o spostata fuori dal deposito comune verso
    l'archivio privato del Master, mai sincronizzato)."""
    return delete_entry(entry_id)


def move_entry(entry_id: str, new_stash_kind: str, new_world_id: str = "") -> bool:
    """
    Sposta una voce da un contenitore all'altro (es. dall'archivio privato
    del Master al deposito comune del gruppo) senza perdere id/storico —
    un semplice UPDATE, non una cancellazione+ricreazione.
    """
    conn = None
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE loot_stash_entries SET stash_kind=?, world_id=?, updated_at=? WHERE id=?",
            (_s(new_stash_kind) or "master", _s(new_world_id),
             datetime.now().isoformat(), entry_id),
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Errore move_entry: {e}")
        return False
    finally:
        if conn is not None:
            conn.close()
