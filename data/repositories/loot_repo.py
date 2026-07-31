"""
Repository per il Bottino (`dnd_app/docs/loot_design.md`): archivio privato
del Master e deposito comune del gruppo, entrambi ospitati sulla stessa
tabella `loot_stash_entries`, distinta dal campo `stash_kind`.

Deliberatamente indipendente da `character_repo.py`/`master_repo.py` —
`loot_stash_entries` non ha alcuna FK obbligatoria: una voce di bottino non
appartiene a nessun personaggio finché non viene assegnata (quel passaggio
usa direttamente `character_repo.create_inventory_item()`/
`get_currencies()`/`update_currencies()`, mai una scrittura da qui), e
l'archivio del Master funziona già oggi — un dispositivo solo, nessuna rete
— con `world_id=""`. Il deposito comune (`stash_kind="party"`) avrà sempre
un `world_id` valorizzato una volta introdotto il mondo condiviso
(Multiplayer), ma questo modulo non impone il vincolo: lo farà la UI, che
prima del multiplayer non espone affatto la modalità "party".
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
    try:
        conn = get_connection()
        rows = conn.execute(
            """SELECT * FROM loot_stash_entries
               WHERE stash_kind=? AND world_id=?
               ORDER BY created_at ASC""",
            (stash_kind, world_id),
        ).fetchall()
        conn.close()
        return [_row_to_entry(r) for r in rows]
    except Exception as e:
        logger.error(f"Errore get_entries: {e}")
        return []


def get_entry_by_id(entry_id: str) -> LootStashEntry | None:
    try:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM loot_stash_entries WHERE id=?", (entry_id,)
        ).fetchone()
        conn.close()
        return _row_to_entry(row) if row else None
    except Exception as e:
        logger.error(f"Errore get_entry_by_id: {e}")
        return None


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
) -> LootStashEntry | None:
    """
    Crea una nuova voce di bottino. Ritorna la voce creata, o None in caso
    di errore. Per `entry_kind="coins"` `name`/`description` restano vuoti
    e il valore vive nelle 5 colonne valuta.
    """
    import uuid as _uuid
    entry_id = str(_uuid.uuid4())
    now = datetime.now().isoformat()
    try:
        conn = get_connection()
        conn.execute(
            """
            INSERT INTO loot_stash_entries (
                id, stash_kind, world_id, entry_kind, name, description,
                quantity, source_note,
                copper, silver, electrum, gold, platinum,
                added_by_device_id, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                entry_id, _s(stash_kind) or "master", _s(world_id),
                _s(entry_kind) or "item", _s(name), _s(description),
                max(1, quantity) if entry_kind != "coins" else max(0, quantity),
                _s(source_note),
                max(0, copper), max(0, silver), max(0, electrum),
                max(0, gold), max(0, platinum),
                _s(added_by_device_id), now, now,
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM loot_stash_entries WHERE id=?", (entry_id,)
        ).fetchone()
        conn.close()
        return _row_to_entry(row) if row else None
    except Exception as e:
        logger.error(f"Errore create_entry: {e}")
        return None


def update_entry_quantity(entry_id: str, quantity: int) -> bool:
    """Aggiorna solo la quantità (clamp a 0 minimo — 0 non elimina la riga,
    resta visibile come "esaurita" finché non viene rimossa esplicitamente)."""
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE loot_stash_entries SET quantity=?, updated_at=? WHERE id=?",
            (max(0, quantity), datetime.now().isoformat(), entry_id),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore update_entry_quantity: {e}")
        return False


def update_entry(
    entry_id: str,
    name: str = "",
    description: str = "",
    quantity: int = 1,
    source_note: str = "",
) -> bool:
    """Aggiorna i campi testuali/quantità di una voce non monetaria."""
    try:
        conn = get_connection()
        conn.execute(
            """UPDATE loot_stash_entries
               SET name=?, description=?, quantity=?, source_note=?, updated_at=?
               WHERE id=?""",
            (_s(name), _s(description), max(0, quantity), _s(source_note),
             datetime.now().isoformat(), entry_id),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore update_entry: {e}")
        return False


def delete_entry(entry_id: str) -> bool:
    try:
        conn = get_connection()
        conn.execute("DELETE FROM loot_stash_entries WHERE id=?", (entry_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore delete_entry: {e}")
        return False


def move_entry(entry_id: str, new_stash_kind: str, new_world_id: str = "") -> bool:
    """
    Sposta una voce da un contenitore all'altro (es. dall'archivio privato
    del Master al deposito comune del gruppo) senza perdere id/storico —
    un semplice UPDATE, non una cancellazione+ricreazione.
    """
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE loot_stash_entries SET stash_kind=?, world_id=?, updated_at=? WHERE id=?",
            (_s(new_stash_kind) or "master", _s(new_world_id),
             datetime.now().isoformat(), entry_id),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Errore move_entry: {e}")
        return False
