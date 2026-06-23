"""
Repository CRUD per le mappe di gioco (game_maps).
Una mappa è associata a un personaggio e contiene:
  - image_data: immagine in base64
  - notes: testo libero
  - annotations: JSON list di annotazioni (testo + coordinate opzionali)
"""

import json
import logging
import uuid
from datetime import datetime

from data.database import get_connection
from data.models import GameMap

logger = logging.getLogger(__name__)


def _s(v) -> str:
    return v if v is not None else ""


def _row_to_map(row) -> GameMap:
    d = dict(row)
    return GameMap(
        id=d["id"],
        character_id=d["character_id"],
        name=d["name"],
        image_path=d.get("image_path", "") or "",
        image_data=d.get("image_data", "") or "",
        annotations=d.get("annotations", "[]") or "[]",
        notes=d.get("notes", "") or "",
        created_at=d.get("created_at", ""),
        updated_at=d.get("updated_at", ""),
    )


def get_maps(character_id: str) -> list[GameMap]:
    """Restituisce tutte le mappe del personaggio, ordinate per updated_at DESC."""
    try:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM game_maps WHERE character_id=? ORDER BY updated_at DESC",
            (character_id,),
        ).fetchall()
        conn.close()
        return [_row_to_map(r) for r in rows]
    except Exception as e:
        logger.error("get_maps(%s): %s", character_id, e)
        return []


def get_map(map_id: str) -> GameMap | None:
    """Restituisce una singola mappa per ID."""
    try:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM game_maps WHERE id=?", (map_id,)
        ).fetchone()
        conn.close()
        return _row_to_map(row) if row else None
    except Exception as e:
        logger.error("get_map(%s): %s", map_id, e)
        return None


def create_map(
    character_id: str,
    name: str,
    image_data: str = "",
    notes: str = "",
    annotations: str = "[]",
) -> GameMap | None:
    """Crea una nuova mappa. Restituisce l'oggetto GameMap o None in caso di errore."""
    now = datetime.now().isoformat()
    gm = GameMap(
        id=str(uuid.uuid4()),
        character_id=character_id,
        name=name,
        image_data=image_data,
        notes=notes,
        annotations=annotations,
        created_at=now,
        updated_at=now,
    )
    try:
        conn = get_connection()
        conn.execute(
            """INSERT INTO game_maps
               (id, character_id, name, image_path, image_data, annotations, notes, created_at, updated_at)
               VALUES (?, ?, ?, '', ?, ?, ?, ?, ?)""",
            (gm.id, gm.character_id, _s(gm.name),
             _s(gm.image_data), _s(gm.annotations), _s(gm.notes),
             gm.created_at, gm.updated_at),
        )
        conn.commit()
        conn.close()
        return gm
    except Exception as e:
        logger.error("create_map: %s", e)
        return None


def update_map(
    map_id: str,
    name: str | None = None,
    image_data: str | None = None,
    notes: str | None = None,
    annotations: str | None = None,
) -> bool:
    """Aggiorna i campi forniti (None = non modificare)."""
    sets = ["updated_at=?"]
    params: list = [datetime.now().isoformat()]
    if name is not None:
        sets.append("name=?")
        params.append(_s(name))
    if image_data is not None:
        sets.append("image_data=?")
        params.append(_s(image_data))
    if notes is not None:
        sets.append("notes=?")
        params.append(_s(notes))
    if annotations is not None:
        sets.append("annotations=?")
        params.append(_s(annotations))
    params.append(map_id)
    try:
        conn = get_connection()
        conn.execute(
            f"UPDATE game_maps SET {', '.join(sets)} WHERE id=?",
            params,
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error("update_map(%s): %s", map_id, e)
        return False


def delete_map(map_id: str) -> bool:
    """Elimina una mappa."""
    try:
        conn = get_connection()
        conn.execute("DELETE FROM game_maps WHERE id=?", (map_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error("delete_map(%s): %s", map_id, e)
        return False
