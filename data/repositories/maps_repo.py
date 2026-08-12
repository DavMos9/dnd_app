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
        # '' = nessun personaggio proprietario locale — la colonna DB è
        # NULL per una mappa condivisa non posseduta (Multiplayer passo 8,
        # §6.4); a livello di dataclass il sentinel resta la stringa vuota,
        # stessa convenzione già usata per gli altri campi opzionali.
        character_id=d.get("character_id") or "",
        name=d["name"],
        image_path=d.get("image_path", "") or "",
        image_data=d.get("image_data", "") or "",
        annotations=d.get("annotations", "[]") or "[]",
        notes=d.get("notes", "") or "",
        world_id=d.get("world_id", "") or "",
        is_shared=bool(d.get("is_shared", 0)),
        visible_to_players=bool(d.get("visible_to_players", 1)
                                 if d.get("visible_to_players") is not None else 1),
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
    """Una singola mappa per id — usata dagli handler di comando e dalla
    rotta HTTP dell'immagine (Multiplayer passo 8), oggi assente perché
    finora bastava sempre `get_maps(character_id)`."""
    try:
        conn = get_connection()
        row = conn.execute("SELECT * FROM game_maps WHERE id=?", (map_id,)).fetchone()
        conn.close()
        return _row_to_map(row) if row else None
    except Exception as e:
        logger.error("get_map(%s): %s", map_id, e)
        return None


def get_shared_maps(world_id: str) -> list[GameMap]:
    """Mappe pubblicate in un mondo (`is_shared=1`) — scoperta lato
    giocatore, indipendente da quale personaggio locale le possiede (una
    mappa condivisa non posseduta ha `character_id` NULL)."""
    try:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM game_maps WHERE world_id=? AND is_shared=1 ORDER BY updated_at DESC",
            (world_id,),
        ).fetchall()
        conn.close()
        return [_row_to_map(r) for r in rows]
    except Exception as e:
        logger.error("get_shared_maps(%s): %s", world_id, e)
        return []


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


# ---------------------------------------------------------------------------
# Mappe condivise (Multiplayer passo 8, §6.4)
# ---------------------------------------------------------------------------

def clone_map_for_sharing(source_map_id: str, world_id: str) -> GameMap | None:
    """
    Pubblica una mappa locale in un mondo CLONANDOLA in una riga nuova
    (`character_id=NULL`, id nuovo, annotazioni vuote) invece di
    riusare la riga personale del personaggio che l'ha creata.

    Bug corretto qui (2026-08-12, segnalato da Davide): la versione
    precedente riusava la STESSA riga (`UPDATE ... SET world_id=?,
    is_shared=1 WHERE id=?`), quindi disegnare sulla mappa condivisa nel
    mondo modificava anche la mappa personale del personaggio proprietario
    — anche se quel personaggio non faceva parte di NESSUN mondo. Clonare
    disaccoppia le due cose per sempre: il personale resta personale
    (mai toccato da qui in poi), il clone è dell'unico proprietario "il
    mondo" (nessun `character_id`, come una mappa caricata direttamente
    — vedi `create_shared_map`), e disegnarci sopra tocca solo il clone.
    """
    source = get_map(source_map_id)
    if source is None:
        return None
    return _insert_shared_map(source.name, source.image_data, world_id)


def create_shared_map(world_id: str, name: str, image_data: str = "",
                       visible_to_players: bool = True) -> GameMap | None:
    """Carica una mappa NUOVA direttamente nel mondo — mai passata da una
    mappa personale di un personaggio (nessuna clonazione, nessuna
    sorgente): stesso risultato finale di `clone_map_for_sharing`, una
    riga con `character_id=NULL`, ma il master non deve avere prima
    salvato l'immagine sotto un proprio personaggio."""
    return _insert_shared_map(name, image_data, world_id, visible_to_players)


def _insert_shared_map(name: str, image_data: str, world_id: str,
                        visible_to_players: bool = True) -> GameMap | None:
    now = datetime.now().isoformat()
    gm = GameMap(
        id=str(uuid.uuid4()), character_id="", name=name, image_data=image_data,
        annotations="[]", notes="", world_id=world_id, is_shared=True,
        visible_to_players=visible_to_players, created_at=now, updated_at=now,
    )
    try:
        conn = get_connection()
        conn.execute(
            """INSERT INTO game_maps
               (id, character_id, name, image_path, image_data, annotations, notes,
                world_id, is_shared, visible_to_players, created_at, updated_at)
               VALUES (?, NULL, ?, '', ?, '[]', '', ?, 1, ?, ?, ?)""",
            (gm.id, _s(gm.name), _s(gm.image_data), _s(world_id),
             int(visible_to_players), now, now),
        )
        conn.commit()
        conn.close()
        return gm
    except Exception as e:
        logger.error("_insert_shared_map(%s, %s): %s", name, world_id, e)
        return None


def set_map_visibility(map_id: str, visible: bool) -> bool:
    """Mostra/nasconde una mappa condivisa ai giocatori (`CMD_MAP_
    VISIBILITY`) — NON tocca `is_shared`: la mappa resta nell'elenco del
    master anche nascosta, solo i giocatori smettono di vederla (§6.4).
    Stessa funzione usata sia dall'handler sull'host sia dal ramo replica
    in `core.world_sync` (identica alla scrittura, nessuna logica in più
    da duplicare)."""
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE game_maps SET visible_to_players=?, updated_at=? WHERE id=?",
            (int(visible), datetime.now().isoformat(), map_id),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error("set_map_visibility(%s): %s", map_id, e)
        return False


def apply_stroke_batch(map_id: str, batch: list[dict]) -> bool:
    """
    Applica un pacchetto di operazioni di disegno alle `annotations` di una
    mappa — unico punto che interpreta la forma del pacchetto (§6.4),
    usato SIA dall'handler `CMD_MAP_DRAW` (scrittura autoritativa
    sull'host) SIA dal ramo replica in `core.world_sync.
    apply_event_to_replica`: nessuna logica duplicata tra le due parti.

    Ogni elemento di `batch` ha una chiave `"op"`:
      - assente o "add"    → aggiunge il tratto (l'intero dict, meno "op")
      - "clear"             → svuota tutti i tratti
      - "replace_all"       → sostituisce l'intera lista (usata dalla
                              gomma: più semplice e corretta di codificare
                              un diff, dato che cancellare è raro rispetto
                              a disegnare)
    """
    gm = get_map(map_id)
    if gm is None:
        return False
    try:
        strokes = json.loads(gm.annotations or "[]")
    except (json.JSONDecodeError, TypeError):
        strokes = []
    for item in batch:
        op = item.get("op", "add")
        if op == "clear":
            strokes = []
        elif op == "replace_all":
            strokes = item.get("strokes", [])
        else:
            stroke = {k: v for k, v in item.items() if k != "op"}
            strokes.append(stroke)
    return update_map(map_id, annotations=json.dumps(strokes))


def replica_create_map_stub(map_id: str, world_id: str, name: str,
                             visible_to_players: bool = True) -> bool:
    """
    Crea (o aggiorna) sulla replica locale una mappa condivisa NON
    posseduta — `character_id` resta NULL (mai una stringa vuota: la
    colonna ha `PRAGMA foreign_keys=ON`, un valore che non combacia con
    nessun `characters.id` violerebbe il vincolo). `image_data` resta
    vuota: l'immagine si scarica lazy dalla rotta dedicata
    `GET /map/<id>/image` la prima volta che la mappa viene aperta, mai da
    qui (troppo grande per il giornale/lo snapshot). Usata sia per
    `map.publish` (clonazione di una mappa personale) sia per `map.upload`
    (mappa caricata direttamente) — stesso identico stub per entrambe, la
    replica non distingue le due origini.
    """
    now = datetime.now().isoformat()
    try:
        conn = get_connection()
        existing = conn.execute(
            "SELECT created_at FROM game_maps WHERE id=?", (map_id,)
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE game_maps SET name=?, world_id=?, is_shared=1,
                   visible_to_players=?, updated_at=? WHERE id=?""",
                (_s(name), _s(world_id), int(visible_to_players), now, map_id),
            )
        else:
            conn.execute(
                """INSERT INTO game_maps
                   (id, character_id, name, image_path, image_data, annotations, notes,
                    world_id, is_shared, visible_to_players, created_at, updated_at)
                   VALUES (?, NULL, ?, '', '', '[]', '', ?, 1, ?, ?, ?)""",
                (map_id, _s(name), _s(world_id), int(visible_to_players), now, now),
            )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error("replica_create_map_stub(%s): %s", map_id, e)
        return False
