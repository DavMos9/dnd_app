"""
Export/Import di un intero Mondo condiviso in un file singolo (`.dndworld`)
— passo 9D di `dnd_app/docs/multiplayer_design.md` §6.3/§13, stesso
identico principio già collaudato per `.dndchar`
(`data/repositories/character_export.py`, 2026-07-24): introspezione dello
schema via `PRAGMA table_info` invece di liste di colonne scritte a mano,
"a prova di versione" in entrambe le direzioni senza manutenzione — vedi il
docstring di quel modulo per il ragionamento completo (si applica identico
qui). Questo modulo importa e riusa direttamente `_insert_row`/
`_table_columns`/`_write_character_and_children`/`CHILD_TABLES` da lì (sono
già generici, non specifici del "personaggio": scriverne una seconda copia
qui violerebbe esattamente il principio "una colonna dimenticata in una
lista scritta a mano" che quel modulo esiste per eliminare).

Contiene (§6.3): il mondo, i membri con i ruoli, TUTTE le istanze di
personaggio di questo mondo — comprese quelle archiviate (2026-08-12,
"Richiesta di rientro": un backup/trasferimento di campagna non deve MAI
perdere un personaggio rimosso, altrimenti la rimozione diventerebbe
silenziosamente definitiva al primo export/import) — con le loro tabelle
figlio, il giornale degli eventi, i due contenitori di bottino (bottino del
master/del gruppo, `loot_stash_entries.stash_kind`), le note del master con
la loro visibilità, gli NPC di rubrica (2026-08-12, da quando
`master_npcs` è world-scoped — vedi `_WORLD_FLAT_TABLES`), le richieste di
modifica pendenti, le richieste di rientro pendenti (2026-08-12, non
esisteva quando il design doc è stato scritto ma è a tutti gli effetti
stato del mondo) e le mappe condivise (idem, §6.4). NON contiene gli
Incontri (`master_encounters`): world-scoped anch'essi da questa stessa
sessione ma con una tabella figlio propria (`master_encounter_members`)
mai gestita da questo modulo — limite noto, vedi il commento su
`_WORLD_FLAT_TABLES`.

Nessuna dipendenza da Flet in questo modulo (stesso principio di
core/*.py e degli altri file di data/repositories/): la UI
(`ui/views/world/world_view.py`) chiama queste funzioni e gestisce
dialoghi/file picker/errori.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any

from data.database import get_connection
from data.repositories.character_export import (
    CHILD_TABLES,
    _insert_row,
    _table_columns,
    _write_character_and_children,
    export_character,
    validate_export_data as validate_character_export_data,
)
from data.repositories.world_repo import generate_join_code

logger = logging.getLogger(__name__)

EXPORT_FORMAT_VERSION = 1

#: Soglia del promemoria di backup periodico (passo 9E, §6.3) — numero di
#: eventi nel giornale del mondo dall'ultimo export riuscito oltre il quale
#: la UI (`ui/views/world/world_view.py::_backup_section`) mostra un avviso
#: non bloccante. Decisa insieme a Davide (2026-08-12): eventi di giornale
#: (attività REALE della campagna) invece di un intervallo di calendario o
#: di un conteggio di aperture della schermata — non disturba un mondo
#: fermo, avvisa quando c'è davvero qualcosa di nuovo da proteggere. Valore
#: medio tra le alternative proposte, non ancora misurato su un uso reale
#: — un valore da rivedere se in pratica risultasse troppo/poco frequente.
EXPORT_REMINDER_EVENT_THRESHOLD = 20

#: Tabelle "piatte" del mondo (nessuna tabella figlio propria, a differenza
#: delle istanze di personaggio) — ciascuna ha una colonna `world_id` che
#: la lega al mondo, scritta con lo stesso `_insert_row` generico di
#: `character_export.py`. `world_events` è gestita a parte qui sotto
#: (colonna `seq` autoincrement da MAI riportare da un file — vedi
#: `_export_events`/`_import_events`).
_WORLD_FLAT_TABLES: tuple[str, ...] = (
    "world_change_requests",
    "world_rejoin_requests",
    "loot_stash_entries",
    "master_campaign_notes",
    # NPC di rubrica (2026-08-12, Sezione Master world-scoped — bug report
    # Davide: "tutto deve essere dipendente dal mondo"): `master_npcs` ha
    # guadagnato una colonna `world_id` solo in questa stessa sessione,
    # stessa forma "piatta" di `loot_stash_entries`/`master_campaign_notes`
    # (nessuna tabella figlio, nessun `character_id` da rimappare) — quindi
    # entra qui invece che nel percorso "istanza di personaggio". LIMITE
    # NOTO: `master_encounters` resta escluso da export/import/eliminazione
    # del mondo (aveva già `world_id` da prima, ma per il flag "visibile ai
    # giocatori" §6.5, mai per l'appartenenza) — ha una tabella figlio
    # propria (`master_encounter_members`) che richiederebbe lo stesso
    # trattamento dedicato di `characters`/`CHILD_TABLES`, non il percorso
    # "piatto" qui sotto: un backup/trasferimento di mondo oggi NON porta
    # con sé gli incontri creati in quel mondo, solo NPC/note/bottino/mappe.
    "master_npcs",
)

MODES = ("new", "overwrite", "copy")


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def export_world(world_id: str) -> dict[str, Any] | None:
    """
    Costruisce il dizionario di export completo di un mondo. Ritorna None
    se il mondo non esiste o in caso di errore (loggato).
    """
    try:
        conn = get_connection()
        try:
            world_row = conn.execute(
                "SELECT * FROM worlds WHERE id = ?", (world_id,)
            ).fetchone()
            if world_row is None:
                logger.warning("export_world: mondo %s non trovato", world_id)
                return None

            members = [
                dict(r) for r in conn.execute(
                    "SELECT * FROM world_members WHERE world_id = ?", (world_id,)
                ).fetchall()
            ]
            events = [
                dict(r) for r in conn.execute(
                    "SELECT * FROM world_events WHERE world_id = ? ORDER BY seq ASC",
                    (world_id,),
                ).fetchall()
            ]
            flat: dict[str, list[dict[str, Any]]] = {}
            for table in _WORLD_FLAT_TABLES:
                flat[table] = [
                    dict(r) for r in conn.execute(
                        f"SELECT * FROM {table} WHERE world_id = ?", (world_id,)
                    ).fetchall()
                ]
            # Mappe condivise (§6.4): solo quelle SENZA proprietario locale
            # (`character_id IS NULL`, il clone/upload che vive di vita
            # propria nel mondo — stesso filtro di `maps_repo.get_shared_maps`,
            # letto qui in raw SQL per includere anche `image_data` per
            # intero, che quella funzione userebbe comunque tutta).
            shared_maps = [
                dict(r) for r in conn.execute(
                    "SELECT * FROM game_maps WHERE world_id = ? AND character_id IS NULL",
                    (world_id,),
                ).fetchall()
            ]

            # Tutte le istanze di personaggio del mondo, ARCHIVIATE COMPRESE
            # (character_repo.get_all_instances_of_world) — ciascuna con
            # l'export integrale delle sue 12 tabelle figlio, riusando
            # export_character() così nessuna logica di lettura duplicata.
            char_ids = [
                r["id"] for r in conn.execute(
                    "SELECT id FROM characters WHERE world_id = ?", (world_id,)
                ).fetchall()
            ]
        finally:
            conn.close()

        characters = []
        for cid in char_ids:
            data = export_character(cid)
            if data is not None:
                characters.append(data)

        return {
            "export_format_version": EXPORT_FORMAT_VERSION,
            "app": "dnd_companion",
            "kind": "world",
            "exported_at": datetime.now().isoformat(),
            "world": dict(world_row),
            "members": members,
            "events": events,
            "characters": characters,
            "shared_maps": shared_maps,
            **flat,
        }
    except Exception as e:
        logger.error(f"Errore export_world({world_id}): {e}")
        return None


# ---------------------------------------------------------------------------
# Validazione / anteprima
# ---------------------------------------------------------------------------

def validate_export_data(data: Any) -> str:
    """Stesso pattern di `character_export.validate_export_data` — stringa
    di errore in italiano, vuota = valido."""
    if not isinstance(data, dict):
        return "Il file non contiene un oggetto JSON valido."
    if data.get("kind") != "world":
        return "Il file non è un export di un mondo condiviso (era un file .dndchar?)."
    world = data.get("world")
    if not isinstance(world, dict):
        return "Il file non contiene i dati di un mondo (sezione 'world' mancante)."
    if not world.get("id"):
        return "Il file non contiene un ID mondo valido."
    if not isinstance(data.get("members"), list):
        return "Il file non contiene l'elenco dei membri (sezione 'members' mancante)."
    if not isinstance(data.get("events"), list):
        return "Il file non contiene il giornale degli eventi (sezione 'events' mancante)."
    if not isinstance(data.get("characters"), list):
        return "Il file non contiene le istanze di personaggio (sezione 'characters' mancante)."
    for char_data in data["characters"]:
        err = validate_character_export_data(char_data)
        if err:
            return f"Un personaggio del mondo non è valido: {err}"
    fmt = data.get("export_format_version")
    if not isinstance(fmt, int):
        return "Il file non indica una versione di formato riconoscibile."
    return ""


def peek_world_summary(data: dict[str, Any]) -> dict[str, Any] | None:
    """Riepilogo minimo per il dialog di conferma import, senza scrivere
    nulla — nome, numero membri, numero personaggi (attivi/archiviati)."""
    try:
        world = data.get("world")
        if not isinstance(world, dict) or "id" not in world:
            return None
        members = data.get("members") or []
        characters = data.get("characters") or []
        archived = sum(
            1 for c in characters
            if (c.get("character") or {}).get("world_instance_archived")
        )
        return {
            "id": str(world.get("id", "")),
            "name": str(world.get("name", "") or "Mondo senza nome"),
            "member_count": len(members),
            "character_count": len(characters),
            "archived_count": archived,
        }
    except Exception as e:
        logger.error(f"Errore peek_world_summary: {e}")
        return None


def world_id_exists(world_id: str) -> bool:
    conn = None
    try:
        conn = get_connection()
        row = conn.execute("SELECT 1 FROM worlds WHERE id = ?", (world_id,)).fetchone()
        return row is not None
    except Exception as e:
        logger.error(f"Errore world_id_exists({world_id}): {e}")
        return True  # in dubbio, fa passare dal dialog di conflitto
    finally:
        if conn is not None:
            conn.close()


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

def _delete_existing_world_data(conn, world_id: str) -> None:
    """
    "Sovrascrivi": ripulisce TUTTO ciò che vive sotto `world_id` prima di
    riscrivere da zero (stesso principio di
    `import_character(mode="overwrite")`, applicato all'intero mondo).

    `world_repo.delete_world()`-equivalente per `worlds`/`world_members`/
    `world_events`/`world_change_requests`/`world_rejoin_requests` è già
    coperto dal CASCADE dello schema (tutte e quattro referenziano
    `worlds(id) ON DELETE CASCADE`) — qui la riga `worlds` viene già
    cancellata da questa stessa funzione, quindi il CASCADE fa il resto.
    Le tabelle SENZA quella FK (`characters`/`loot_stash_entries`/
    `master_campaign_notes`/`master_npcs`/`game_maps`, tutte con `world_id`
    come semplice colonna testo, mai un vincolo — vedi il commento di
    `world_repo.delete_world()`) vanno svuotate esplicitamente qui.
    `characters` cascade sulle proprie 12 tabelle figlio tramite la FK
    già esistente verso `characters(id)`.
    """
    conn.execute("DELETE FROM characters WHERE world_id = ?", (world_id,))
    conn.execute("DELETE FROM loot_stash_entries WHERE world_id = ?", (world_id,))
    conn.execute("DELETE FROM master_campaign_notes WHERE world_id = ?", (world_id,))
    conn.execute("DELETE FROM master_npcs WHERE world_id = ?", (world_id,))
    conn.execute(
        "DELETE FROM game_maps WHERE world_id = ? AND character_id IS NULL", (world_id,)
    )
    conn.execute("DELETE FROM worlds WHERE id = ?", (world_id,))  # CASCADE il resto


def _write_world_row(conn, world_row: dict[str, Any], *, target_id: str,
                      owner_device_id: str) -> None:
    """
    Scrive la riga `worlds` — SEMPRE `is_local_host=1` (chi importa diventa
    l'host da qui in avanti, §6.3: "chi importa diventa owner e ospita da lì
    in avanti"). Un nuovo `join_code` (mai riusare quello del file: il
    vecchio potrebbe essere ancora noto a persone che non devono più entrare
    in QUESTA copia) e `session_token`/`last_synced_seq` azzerati (questo
    diventa lo stato AUTORITATIVO, non una replica).

    Questa è l'UNICA eccezione deliberata all'invariante "nessuna funzione
    fuori da `create_world()` imposta `is_local_host=1`"
    (`world_repo.save_replica_world`, §11.5 "due dispositivi non possono
    ospitare lo stesso mondo"): l'import da file è un'azione esplicita
    dell'utente per iniziare (o riprendere) a ospitare, esattamente come
    `create_world()` — mai un effetto collaterale di sincronizzazione.
    """
    live_cols = _table_columns(conn, "worlds")
    overrides = {
        "id": target_id,
        "owner_device_id": owner_device_id,
        "join_code": generate_join_code(),
        "is_local_host": 1,
        "last_seen_host": "",
        "session_token": "",
        "last_synced_seq": 0,
    }
    _insert_row(conn, "worlds", world_row, live_cols, overrides)


def _write_members(conn, members: list[dict[str, Any]], *, world_id: str,
                    owner_device_id: str, owner_display_name: str,
                    regenerate_ids: bool) -> None:
    """
    Scrive i membri esportati, poi garantisce che ESATTAMENTE UNO abbia
    ruolo `owner`: il dispositivo che sta importando (§6.3). Se era già tra
    i membri esportati, viene promosso (col NOME appena digitato nel
    dialogo di import, non quello — potenzialmente vecchio — del file: chi
    importa ha appena scritto come vuole essere chiamato ORA) e l'eventuale
    vecchio owner retrocesso a `master` (mai lasciare due `owner`);
    altrimenti viene aggiunto come nuovo membro — stesso schema a due passi
    già in uso in `core/world_backend.py::_handle_transfer_ownership` per
    lo stesso invariante ("un solo owner, sempre").
    """
    live_cols = _table_columns(conn, "world_members")
    importer_found = False
    for row in members:
        new_id = str(uuid.uuid4()) if regenerate_ids else row.get("id")
        device_id = str(row.get("device_id") or "")
        role = str(row.get("role") or "player")
        overrides: dict[str, Any] = {"id": new_id, "world_id": world_id}
        if device_id == owner_device_id:
            overrides["role"] = "owner"
            overrides["display_name"] = owner_display_name or row.get("display_name") or "Master"
            importer_found = True
        elif role == "owner":
            overrides["role"] = "master"  # il vecchio owner non è più QUESTO dispositivo
        _insert_row(conn, "world_members", row, live_cols, overrides)

    if not importer_found:
        now = datetime.now().isoformat()
        conn.execute(
            """INSERT INTO world_members (
                id, world_id, device_id, display_name, role,
                is_connected, last_seen_at, created_at, updated_at
            ) VALUES (?,?,?,?,'owner',0,'',?,?)""",
            (str(uuid.uuid4()), world_id, owner_device_id,
             owner_display_name or "Master", now, now),
        )


def _write_events(conn, events: list[dict[str, Any]], *, world_id: str,
                   char_id_map: dict[str, str], regenerate_ids: bool) -> None:
    """
    `seq` è l'autoincrement REALE della tabella (`INTEGER PRIMARY KEY
    AUTOINCREMENT`) — MAI riportato dal file: valori di un'altra
    installazione, potenzialmente in conflitto con quelli già presenti
    localmente. Omesso dalla riga prima di scriverla, SQLite ne assegna uno
    nuovo; inserendo nell'ordine originale (l'export li legge già
    `ORDER BY seq ASC`) l'ordine relativo resta identico anche con nuovi
    numeri. `id` (la UUID, distinta da `seq`) è invece preservato per
    default — regenerata solo in modalità "copia".
    """
    live_cols = _table_columns(conn, "world_events")
    for row in events:
        row = dict(row)
        row.pop("seq", None)
        new_id = str(uuid.uuid4()) if regenerate_ids else row.get("id")
        overrides = {"id": new_id, "world_id": world_id}
        if row.get("target_type") == "character" and row.get("target_id") in char_id_map:
            overrides["target_id"] = char_id_map[row["target_id"]]
        _insert_row(conn, "world_events", row, live_cols, overrides)


def _write_flat_table(conn, table: str, rows: list[dict[str, Any]], *, world_id: str,
                       char_id_map: dict[str, str], regenerate_ids: bool) -> None:
    live_cols = _table_columns(conn, table)
    for row in rows:
        new_id = str(uuid.uuid4()) if regenerate_ids else row.get("id")
        overrides = {"id": new_id, "world_id": world_id}
        if row.get("character_id") in char_id_map:
            overrides["character_id"] = char_id_map[row["character_id"]]
        _insert_row(conn, table, row, live_cols, overrides)


def _write_shared_maps(conn, maps: list[dict[str, Any]], *, world_id: str,
                        regenerate_ids: bool) -> None:
    live_cols = _table_columns(conn, "game_maps")
    for row in maps:
        new_id = str(uuid.uuid4()) if regenerate_ids else row.get("id")
        overrides = {"id": new_id, "world_id": world_id, "character_id": None}
        _insert_row(conn, "game_maps", row, live_cols, overrides)


def import_world(
    data: dict[str, Any], mode: str, importing_device_id: str,
    importing_display_name: str = "",
) -> str | None:
    """
    Importa un mondo da un dict di export (stessa forma prodotta da
    `export_world()`). Stesse 3 modalità di `character_export.import_character()`:

        "new"       → nessun conflitto atteso, id del file preservati.
                      Se il mondo esiste già, ritorna None (la UI deve
                      SEMPRE controllare `world_id_exists()` prima).
        "overwrite" → ripulisce tutto ciò che vive già sotto quell'id
                      (`_delete_existing_world_data`) e lo riscrive da zero.
        "copy"      → nuovi id per mondo, membri, personaggi (e ogni riga
                      collegata), nessun conflitto possibile con un mondo
                      già presente. `origin_character_id`/`owner_device_id`
                      di ogni personaggio NON vengono toccati (restano quelli
                      del file: identificano un personaggio locale e un
                      dispositivo REALI, mai id interni da rimappare).

    In OGNI modalità questo dispositivo diventa l'`owner`/host del mondo
    da qui in avanti (§6.3) — vedi `_write_world_row`/`_write_members`.

    Ritorna l'id del mondo importato, o `None` in caso di errore (loggato).
    Best-effort per riga/tabella (stesso principio già in uso in
    `core/world_sync.py::_finalize_join()` per seminare uno snapshot): non
    una singola transazione monolitica su 9 tabelle, ma ogni passo scrive
    sulla stessa connessione con commit finale — un fallimento a metà lascia
    lo stato scritto fin lì (mai peggio di quanto già accade oggi seminando
    un ingresso in un mondo), e "sovrascrivi" è comunque ripetibile: un
    nuovo tentativo ripulisce e riscrive da capo.
    """
    err = validate_export_data(data)
    if err:
        logger.error(f"import_world: dati non validi — {err}")
        return None
    if mode not in MODES:
        logger.error(f"import_world: mode non valido: {mode!r}")
        return None
    importing_device_id = (importing_device_id or "").strip()
    if not importing_device_id:
        logger.error("import_world: importing_device_id mancante")
        return None

    world_row = dict(data["world"])
    source_world_id = str(world_row.get("id") or "")
    if not source_world_id:
        logger.error("import_world: id mondo mancante nel file")
        return None

    regenerate = mode == "copy"
    target_world_id = str(uuid.uuid4()) if regenerate else source_world_id

    if mode == "new" and world_id_exists(target_world_id):
        logger.error(f"import_world: mondo {target_world_id} già esistente (mode='new')")
        return None

    try:
        conn = get_connection()
        try:
            if mode == "overwrite":
                _delete_existing_world_data(conn, target_world_id)

            _write_world_row(conn, world_row, target_id=target_world_id,
                              owner_device_id=importing_device_id)
            _write_members(
                conn, data.get("members") or [], world_id=target_world_id,
                owner_device_id=importing_device_id,
                owner_display_name=importing_display_name, regenerate_ids=regenerate,
            )

            # Personaggi: id nuovo per ognuno SOLO in modalità copia — mappa
            # vecchio->nuovo id, riusata per rimappare i riferimenti
            # (eventi/richieste) scritti dopo. `_write_character_and_children`
            # (importata da character_export.py) fa esattamente ciò che
            # serve qui: scrive riga+12 tabelle figlio con override espliciti,
            # nessuna logica di scrittura duplicata rispetto a `.dndchar`.
            char_id_map: dict[str, str] = {}
            for char_data in data.get("characters") or []:
                char_row = dict(char_data.get("character") or {})
                related = char_data.get("related") or {}
                old_id = str(char_row.get("id") or "")
                if not old_id:
                    continue
                new_id = str(uuid.uuid4()) if regenerate else old_id
                char_id_map[old_id] = new_id
                _write_character_and_children(
                    conn, char_row, related, new_id, delete_existing=(mode == "overwrite"),
                    char_overrides={
                        "world_id": target_world_id,
                        "origin_character_id": str(char_row.get("origin_character_id") or ""),
                        "owner_device_id": str(char_row.get("owner_device_id") or ""),
                        "is_replica": 0,  # da qui in poi è lo stato autoritativo su QUESTO device
                        "world_seq": 0,
                    },
                )

            _write_events(conn, data.get("events") or [], world_id=target_world_id,
                           char_id_map=char_id_map, regenerate_ids=regenerate)
            for table in _WORLD_FLAT_TABLES:
                _write_flat_table(
                    conn, table, data.get(table) or [], world_id=target_world_id,
                    char_id_map=char_id_map, regenerate_ids=regenerate,
                )
            _write_shared_maps(conn, data.get("shared_maps") or [],
                                world_id=target_world_id, regenerate_ids=regenerate)

            conn.commit()
            logger.info(
                "import_world: mondo importato id=%s (mode=%s, source_id=%s)",
                target_world_id, mode, source_world_id,
            )
            return target_world_id
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Errore import_world (mode={mode}): {e}")
        return None


# ---------------------------------------------------------------------------
# Helper file
# ---------------------------------------------------------------------------

def export_to_json_string(world_id: str) -> str | None:
    """`export_world()` + serializzazione JSON pronta da scrivere su file."""
    data = export_world(world_id)
    if data is None:
        return None
    try:
        return json.dumps(data, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Errore serializzazione JSON export mondo {world_id}: {e}")
        return None


def load_json_string(text: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except Exception as e:
        logger.error(f"Errore parsing JSON import mondo: {e}")
        return None


def suggested_export_filename(world_id: str) -> str:
    """Nome file suggerito, es. "La_Costa_Spezzata_20260812_153000.dndworld"
    — stesso pattern di `character_export.suggested_export_filename`."""
    import re

    conn = get_connection()
    try:
        row = conn.execute("SELECT name FROM worlds WHERE id = ?", (world_id,)).fetchone()
    finally:
        conn.close()
    name = str((row["name"] if row else "") or "mondo")
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_") or "mondo"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{slug}_{ts}.dndworld"
