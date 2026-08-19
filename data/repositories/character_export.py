"""
Export/Import di un personaggio in un file singolo (JSON), per portarlo su
un altro dispositivo o dopo una reinstallazione.

Principio architetturale: introspezione dello schema via `PRAGMA
table_info` invece di liste di colonne scritte a mano. Il progetto ha già
avuto più volte lo stesso bug (un campo aggiunto al dataclass/DB ma
dimenticato in una lista INSERT/UPDATE scritta a mano altrove). Leggendo le
colonne REALI della tabella a runtime, sia in export sia in import, questa
classe di bug è strutturalmente impossibile per questo modulo: ogni colonna
esistente viene sempre inclusa, senza bisogno di aggiornare questo file ad
ogni nuova colonna aggiunta al resto del progetto.

Questo ha anche un effetto collaterale positivo esplicitamente voluto:
l'export è "a prova di versione" in entrambe le direzioni.
  - Un file esportato da una versione PIÙ VECCHIA dell'app, importato in una
    versione più nuova (con colonne aggiuntive nel frattempo): le colonne
    mancanti nel file semplicemente non vengono incluse nell'INSERT, il DB
    applica i propri valori DEFAULT (tutte le colonne di questo schema hanno
    un DEFAULT, verificato in data/database.py).
  - Un file esportato da una versione PIÙ NUOVA, importato in una versione
    più vecchia (colonne nel file che la tabella locale non ha ancora): le
    colonne sconosciute vengono scartate con un warning nel log, non
    provocano un errore SQL.

Le tabelle figlio coperte sono le 12 con FK `character_id` verso
`characters` (CASCADE già presente nello schema, usato qui per "svuotare"
un personaggio prima di sovrascriverlo con dati importati — vedi
`import_character(mode="overwrite")`): character_proficiencies, weapons,
inventory_items, currencies, spell_slots, known_spells, diary_entries,
game_maps, class_resources, creature_entries, campaign_notes,
custom_abilities.

Le immagini (foto personaggio, immagini mappa) sono già colonne TEXT
base64 — finiscono nel JSON di export senza alcuna gestione file separata.

Nessuna dipendenza da Flet in questo modulo (stesso principio di
core/*.py e degli altri file di data/repositories/): la UI (home_view.py)
chiama queste funzioni e gestisce dialoghi/file picker/errori.
"""

import json
import logging
import sqlite3
import uuid
from datetime import datetime
from typing import Any

from data.database import get_connection

logger = logging.getLogger(__name__)

EXPORT_FORMAT_VERSION = 1

# Tabelle figlio con FK character_id → characters(id), stesso elenco della
# CASCADE già presente nello schema (vedi data/database.py). L'ordine qui
# non ha importanza per l'export (letture indipendenti); per l'import è
# comunque sicuro in qualsiasi ordine perché ogni riga porta il proprio
# character_id — nessuna tabella figlio referenzia un'altra tabella figlio.
CHILD_TABLES: tuple[str, ...] = (
    "character_proficiencies",
    "weapons",
    "inventory_items",
    "currencies",
    "spell_slots",
    "known_spells",
    "diary_entries",
    "game_maps",
    "class_resources",
    "creature_entries",
    "campaign_notes",
    "custom_abilities",
    # Deve restare in questa lista: le condizioni imposte dal master a
    # distanza (§7, `core/world_backend.py::_apply_condition_to_character`)
    # arrivano alla replica del giocatore solo perché
    # `_resync_character_from_host()` rimaterializza il personaggio
    # SOLO dalle tabelle elencate qui.
    "character_conditions",
)


# ---------------------------------------------------------------------------
# Introspezione schema
# ---------------------------------------------------------------------------

def _table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    """Nomi delle colonne REALI di una tabella, lette dal DB (non da un dataclass)."""
    cur = conn.execute(f"PRAGMA table_info({table})")
    return [row[1] for row in cur.fetchall()]  # row[1] = nome colonna


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def export_character(character_id: str, *, raise_errors: bool = False) -> dict[str, Any] | None:
    """
    Costruisce il dizionario di export completo per un personaggio: la riga
    `characters` + tutte le righe di tutte le tabelle figlio, ciascuna come
    dict {colonna: valore} letto direttamente dallo schema reale.

    Ritorna None se il personaggio non esiste o in caso di errore (loggato).

    `raise_errors`: di default `False` per non cambiare il contratto con i
    (molti) chiamanti esistenti, che si aspettano solo `None` in caso di
    errore e leggono il dettaglio dal log. Un chiamante che deve mostrare il
    dettaglio direttamente all'utente — es.
    `core/character_instances.py::_copy_character`, dove l'unico modo di
    vedere l'eccezione reale è lo schermo del telefono, senza alcun accesso
    alla console — può passare `True` per farsi rilanciare l'eccezione
    originale invece che un `None` muto.
    """
    try:
        conn = get_connection()
        try:
            char_row = conn.execute(
                "SELECT * FROM characters WHERE id = ?", (character_id,)
            ).fetchone()
            if char_row is None:
                logger.warning("export_character: personaggio %s non trovato", character_id)
                return None

            related: dict[str, list[dict[str, Any]]] = {}
            for table in CHILD_TABLES:
                rows = conn.execute(
                    f"SELECT * FROM {table} WHERE character_id = ?", (character_id,)
                ).fetchall()
                related[table] = [dict(r) for r in rows]

            return {
                "export_format_version": EXPORT_FORMAT_VERSION,
                "app": "dnd_companion",
                "exported_at": datetime.now().isoformat(),
                "character": dict(char_row),
                "related": related,
            }
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Errore export_character({character_id}): {e}")
        if raise_errors:
            raise
        return None


def get_character_summary(character_id: str) -> dict[str, Any] | None:
    """
    Riepilogo minimo (nome/classe/livello/razza) di un personaggio già
    presente sul DB — usato dalla UI per mostrare "stai per sovrascrivere
    X" nel dialog di conflitto import, senza dover esportare l'intero
    personaggio solo per leggere 4 campi.
    """
    try:
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT name, class_name, subclass, level, race FROM characters WHERE id = ?",
                (character_id,),
            ).fetchone()
            return dict(row) if row is not None else None
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Errore get_character_summary({character_id}): {e}")
        return None


def character_id_exists(character_id: str) -> bool:
    """True se un personaggio con questo id esiste già sul DB locale."""
    try:
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT 1 FROM characters WHERE id = ?", (character_id,)
            ).fetchone()
            return row is not None
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Errore character_id_exists({character_id}): {e}")
        # In dubbio, meglio segnalare "esiste" e far passare dal dialog di
        # conflitto piuttosto che rischiare un INSERT che fallisce a metà.
        return True


def peek_character_summary(data: dict[str, Any]) -> dict[str, str] | None:
    """
    Estrae nome/classe/livello/razza da un dict di export già caricato in
    memoria (es. il contenuto di un file appena letto) — usato dalla UI per
    mostrare un'anteprima prima di confermare l'import, senza scriverlo sul
    DB. Ritorna None se il dict non ha la forma attesa di un export valido.
    """
    try:
        char = data.get("character")
        if not isinstance(char, dict) or "id" not in char:
            return None
        return {
            "id": str(char.get("id", "")),
            "name": str(char.get("name", "") or "Senza nome"),
            "class_name": str(char.get("class_name", "")),
            "subclass": str(char.get("subclass", "")),
            "level": str(char.get("level", "")),
            "race": str(char.get("race", "")),
        }
    except Exception as e:
        logger.error(f"Errore peek_character_summary: {e}")
        return None


def validate_export_data(data: Any) -> str:
    """
    Verifica la forma minima di un dict di export prima di tentare
    l'import. Ritorna una stringa di errore in italiano (vuota = valido) —
    stesso pattern già in uso nel progetto per le validazioni di creazione
    personaggio (messaggio pronto per essere mostrato in un AlertDialog).
    """
    if not isinstance(data, dict):
        return "Il file non contiene un oggetto JSON valido."
    char = data.get("character")
    if not isinstance(char, dict):
        return "Il file non contiene i dati di un personaggio (sezione 'character' mancante)."
    if not char.get("id"):
        return "Il file non contiene un ID personaggio valido."
    related = data.get("related")
    if not isinstance(related, dict):
        return "Il file non contiene le sezioni collegate del personaggio (sezione 'related' mancante)."
    fmt = data.get("export_format_version")
    if not isinstance(fmt, int):
        return "Il file non indica una versione di formato riconoscibile."
    return ""


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

def _insert_row(
    conn: sqlite3.Connection,
    table: str,
    row: dict[str, Any],
    live_columns: list[str],
    overrides: dict[str, Any],
) -> None:
    """
    Inserisce una riga in `table` usando solo le colonne effettivamente
    presenti sia nel dict `row` (dati importati) sia nello schema live
    della tabella corrente — le colonne extra nel file (schema più nuovo di
    quello locale) vengono scartate con un warning, quelle mancanti nel
    file (schema più vecchio) restano al DEFAULT della tabella.

    `overrides` ha sempre precedenza sul valore del file (usato per
    riscrivere sempre character_id/id al target, mai fidarsi del file).
    """
    merged = dict(row)
    merged.update(overrides)

    unknown = set(merged.keys()) - set(live_columns)
    if unknown:
        logger.warning(
            "import_character: %s → colonne ignorate (non presenti nello schema locale): %s",
            table, sorted(unknown),
        )

    cols = [c for c in merged.keys() if c in live_columns]
    if not cols:
        return
    placeholders = ", ".join("?" for _ in cols)
    col_list = ", ".join(cols)
    values = [merged[c] for c in cols]
    conn.execute(f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})", values)


def _write_character_and_children(
    conn: sqlite3.Connection,
    char_row: dict[str, Any],
    related: dict[str, list[dict[str, Any]]],
    target_id: str,
    delete_existing: bool,
    char_overrides: dict[str, Any],
    skip_tables: frozenset[str] = frozenset(),
) -> None:
    """
    Nucleo comune a `import_character()` e `import_replica_character()`:
    scrive la riga `characters` e tutte le tabelle figlio sulla
    connessione/transazione già aperta dal chiamante. L'unica differenza tra
    le due funzioni pubbliche è QUALI colonne di mondo vengono forzate
    (`char_overrides`) — azzerate per un import `.dndchar` normale, valorizzate
    per una replica LAN — quindi la logica di scrittura, identica in
    entrambi i casi, vive qui una volta sola (evita la stessa classe di bug
    già risolta altrove in questo modulo con l'introspezione dello schema:
    due copie della stessa logica destinate a divergere).

    `skip_tables`: tabelle di `CHILD_TABLES` da NON toccare — né cancellare
    né reinserire — anche quando `delete_existing=True` fa scattare il
    DELETE CASCADE su `characters`. Nata per `game_maps`: le mappe personali
    (`ui/views/maps_view.py`, mai condivise con l'host, per design) sono
    comunque elencate in `CHILD_TABLES` per l'export/import `.dndchar`
    completo — ma un resync di replica innescato da un evento che NON
    riguarda le mappe (danno HP, PE, ecc.) porta uno snapshot dell'host che
    di `game_maps` non contiene mai nulla (l'host non le ha mai viste),
    quindi il DELETE CASCADE le cancellerebbe silenziosamente ad ogni
    resync se non fossero protette qui. Chi chiama con `delete_existing=
    True` e vuole preservare una tabella la aggiunge qui; il DELETE CASCADE
    di riga `characters` sopra la toccherebbe comunque, quindi le righe di
    quella tabella vanno lette PRIMA della cancellazione e reinserite dopo
    — vedi il blocco dedicato subito sotto.
    """
    preserved_rows: dict[str, list[sqlite3.Row]] = {}
    if delete_existing and skip_tables:
        for table in skip_tables:
            preserved_rows[table] = conn.execute(
                f"SELECT * FROM {table} WHERE character_id = ?", (target_id,)
            ).fetchall()

    if delete_existing:
        # CASCADE rimuove automaticamente tutte le righe figlio.
        conn.execute("DELETE FROM characters WHERE id = ?", (target_id,))

    live_char_cols = _table_columns(conn, "characters")
    overrides = {"id": target_id, **char_overrides}
    _insert_row(conn, "characters", char_row, live_char_cols, overrides)

    for table in CHILD_TABLES:
        if table in skip_tables:
            continue
        rows = related.get(table) or []
        if not isinstance(rows, list):
            continue
        live_cols = _table_columns(conn, table)
        has_id_column = "id" in live_cols
        for row in rows:
            if not isinstance(row, dict):
                continue
            row_overrides: dict[str, Any] = {"character_id": target_id}
            if has_id_column:
                row_overrides["id"] = str(uuid.uuid4())
            _insert_row(conn, table, row, live_cols, row_overrides)

    for table, rows in preserved_rows.items():
        live_cols = _table_columns(conn, table)
        for row in rows:
            _insert_row(conn, table, dict(row), live_cols, {"character_id": target_id})


def import_replica_character(
    data: dict[str, Any], target_id: str, world_seq: int = 0,
    skip_tables: frozenset[str] = frozenset(),
) -> str | None:
    """
    Materializza (o rimaterializza per intero) la replica locale di
    un'istanza di personaggio ricevuta dall'host — Multiplayer passo 6
    (`dnd_app/docs/multiplayer_design.md` §6: "sul dispositivo del
    giocatore sono repliche, aggiornate dagli eventi").

    `skip_tables`: inoltrato a `_write_character_and_children`
    — vedi il suo docstring. I chiamanti di QUESTA funzione decidono se
    passarlo: `core/world_sync.py::_resync_character_from_host()` e
    `_finalize_join()` lo passano (`{"game_maps"}`, mappe personali mai
    condivise con l'host — vedi il loro docstring), mentre
    `core/world_backend.py::_handle_character_instance_sync()` (l'host che
    RICEVE il push completo di un client) non lo passa mai: lì la
    direzione è l'opposto (client → host, il giocatore vuole intenzionalmente
    che l'host rifletta anche le proprie mappe personali).

    A differenza di `import_character()` (pensata per un file `.dndchar`
    portato da fuori, che deve SEMPRE azzerare le colonne di mondo — §14.1)
    questa funzione fa l'opposto: PRESERVA `world_id`/`origin_character_id`/
    `owner_device_id` esattamente come arrivano nel export (sono già
    corretti: l'host li ha scritti sulla propria riga autoritativa quando
    l'istanza è nata, `core/character_instances.py::_link_to_world()`) e
    forza `is_replica=1` — perché questo è precisamente ciò che sta
    scrivendo: la copia locale di un'istanza la cui autorità resta
    sull'host, mai una nuova istanza né un personaggio locale.

    `world_seq`: il numero di sequenza dell'evento del giornale che ha
    causato questa rimaterializzazione (0 per la semina iniziale al primo
    ingresso, dove non c'è ancora un evento specifico) — permette in
    futuro di sapere "questa scheda riflette il mondo fino a
    almeno l'evento #N", stesso significato dichiarato dalla colonna nello
    schema (§8) ma finora mai scritto da nessun punto del codice.

    Sempre "sovrascrivi": la replica non ha una storia propria da
    preservare, è sempre e solo lo specchio dell'ultimo stato noto
    dell'host. Chiamata sia al primo ingresso (semina iniziale, tramite lo
    snapshot) sia dopo ogni evento che tocca l'istanza (`core/world_sync.py`).

    Ritorna `target_id` in caso di successo, `None` in caso di errore
    (loggato) — nessuna scrittura parziale resta applicata (stessa garanzia
    di `import_character()`: un'unica transazione, rollback su eccezione).
    """
    err = validate_export_data(data)
    if err:
        logger.error(f"import_replica_character: dati non validi — {err}")
        return None
    if not target_id:
        logger.error("import_replica_character: target_id mancante")
        return None

    char_row: dict[str, Any] = dict(data["character"])
    related: dict[str, list[dict[str, Any]]] = data.get("related", {})

    world_id = str(char_row.get("world_id") or "")
    if not world_id:
        logger.error(
            "import_replica_character: il personaggio esportato non ha "
            "world_id — non è un'istanza di mondo, rifiuto di trattarlo come replica."
        )
        return None

    try:
        conn = get_connection()
        try:
            _write_character_and_children(
                conn, char_row, related, target_id, delete_existing=True,
                char_overrides={
                    "world_id": world_id,
                    "origin_character_id": str(char_row.get("origin_character_id") or ""),
                    "owner_device_id": str(char_row.get("owner_device_id") or ""),
                    "is_replica": 1,
                    "world_seq": int(world_seq),
                },
                skip_tables=skip_tables,
            )
            conn.commit()
            logger.info(
                "import_replica_character: replica aggiornata id=%s (world=%s, seq=%s)",
                target_id, world_id, world_seq,
            )
            return target_id
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Errore import_replica_character: {e}")
        return None


def import_character_data_as_world_refresh(
    data: dict[str, Any], target_id: str, *, world_id: str,
    origin_character_id: str, owner_device_id: str, world_seq: int = 0,
) -> str | None:
    """
    Sovrascrive il CONTENUTO di un'istanza di mondo ESISTENTE (`target_id`)
    con un export — tipicamente quello di un personaggio LOCALE (§"Richiesta
    di rientro", `core/world_backend.py::_handle_character_rejoin_respond`,
    `mode="refresh_from_local"`: il giocatore vuole rientrare con lo stato
    attuale della propria scheda locale invece di quello con cui l'istanza
    fu archiviata).

    A differenza di `import_replica_character()` sopra — che LEGGE
    `world_id`/`origin_character_id`/`owner_device_id` dall'export stesso e
    **rifiuta** un export senza `world_id` (pensata per una vera replica di
    rete, mai per un personaggio locale) — qui questi tre campi sono
    SEMPRE quelli passati esplicitamente dal chiamante, mai quelli
    dell'export sorgente (che per un personaggio locale sono vuoti): il
    contenuto cambia, l'identità e il collegamento al mondo dell'istanza
    bersaglio no. Forza anche `world_instance_archived=0` nello stesso
    `char_overrides` — un'unica scrittura transazionale fa contenuto e
    riattivazione insieme, mai due passi separati (evita una finestra in
    cui l'istanza sarebbe "riattivata ma con dati vecchi" o viceversa).

    Ritorna `target_id` in caso di successo, `None` in caso di errore
    (loggato) — nessuna scrittura parziale resta applicata, stessa garanzia
    delle altre funzioni di questo modulo.
    """
    err = validate_export_data(data)
    if err:
        logger.error(f"import_character_data_as_world_refresh: dati non validi — {err}")
        return None
    if not target_id:
        logger.error("import_character_data_as_world_refresh: target_id mancante")
        return None

    char_row: dict[str, Any] = dict(data["character"])
    related: dict[str, list[dict[str, Any]]] = data.get("related", {})

    try:
        conn = get_connection()
        try:
            _write_character_and_children(
                conn, char_row, related, target_id, delete_existing=True,
                char_overrides={
                    "world_id": world_id,
                    "origin_character_id": origin_character_id,
                    "owner_device_id": owner_device_id,
                    "is_replica": 1,
                    "world_seq": int(world_seq),
                    "world_instance_archived": 0,
                },
            )
            conn.commit()
            logger.info(
                "import_character_data_as_world_refresh: istanza aggiornata id=%s "
                "(world=%s, seq=%s)", target_id, world_id, world_seq,
            )
            return target_id
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Errore import_character_data_as_world_refresh: {e}")
        return None


def import_character(data: dict[str, Any], mode: str, target_id: str | None = None,
                      *, raise_errors: bool = False) -> str | None:
    """
    Importa un personaggio da un dict di export (stessa forma prodotta da
    export_character()).

    mode:
        "new"       → nessun conflitto atteso, inserisce con l'id originale
                      del file. Se l'id esiste già, l'INSERT fallisce
                      (IntegrityError) e la funzione ritorna None — la UI
                      deve SEMPRE controllare character_id_exists() prima
                      di usare questa modalità.
        "overwrite" → elimina il personaggio esistente e lo reinserisce da
                      zero con gli id originali del file (CASCADE rimuove
                      automaticamente tutte le righe figlio). Sovrascrive
                      l'id nel file stesso, a meno che `target_id` non sia
                      passato esplicitamente (vedi sotto).
        "copy"      → genera un nuovo id per il personaggio (e nuovi id per
                      ogni riga figlio che ne ha uno), creando un
                      personaggio distinto anche se il file aveva lo stesso
                      id di uno già presente.

    target_id: onorato SOLO con mode="overwrite" — sovrascrive un id
        DIVERSO da quello presente nel file esportato invece dell'id del
        file stesso. Introdotto per il Multiplayer (passo 3, «Aggiorna il
        mio foglio»): esporta l'istanza di un mondo e reimportala sopra al
        personaggio locale di origine, che ha un id diverso dall'istanza.
        Ignorato (con un warning) per "new"/"copy", dove genererebbe
        ambiguità su quale id il chiamante si aspetta davvero.

    Operazione atomica: un'unica connessione/transazione, commit solo a
    fine funzione, rollback su qualsiasi eccezione — nessuno stato parziale
    (personaggio a metà importato) in caso di errore.

    Ritorna l'id del personaggio importato, o None in caso di errore
    (loggato) — in quel caso nessuna scrittura resta applicata.
    """
    err = validate_export_data(data)
    if err:
        logger.error(f"import_character: dati non validi — {err}")
        return None
    if mode not in ("new", "overwrite", "copy"):
        logger.error(f"import_character: mode non valido: {mode!r}")
        return None
    if target_id and mode != "overwrite":
        logger.warning(
            "import_character: target_id=%r ignorato — onorato solo con mode='overwrite' "
            "(mode richiesto: %r)", target_id, mode,
        )
        target_id = None

    char_row: dict[str, Any] = dict(data["character"])
    related: dict[str, list[dict[str, Any]]] = data.get("related", {})

    source_id = str(char_row.get("id") or "")
    if mode == "copy":
        target_id = str(uuid.uuid4())
    elif mode == "overwrite" and target_id:
        pass  # override esplicito del chiamante, non l'id del file
    else:
        target_id = source_id
    if not target_id:
        logger.error("import_character: id personaggio mancante nel file")
        return None

    try:
        conn = get_connection()
        try:
            _write_character_and_children(
                conn, char_row, related, target_id,
                delete_existing=(mode == "overwrite"),
                char_overrides={
                    # Un personaggio importato è SEMPRE locale, mai legato al
                    # mondo di provenienza (multiplayer_design.md §14.1): senza
                    # questo azzeramento un file esportato dall'istanza di un
                    # mondo porterebbe con sé world_id/is_replica=1, e il
                    # personaggio importato risulterebbe una replica di un mondo
                    # inesistente — in sola lettura e non riparabile
                    # dall'interfaccia. Vale per tutti e tre i modi (new/
                    # overwrite/copy): l'importazione è sempre un "porta com'è"
                    # verso un personaggio locale, mai verso un mondo. Per la
                    # controparte che valorizza queste colonne invece di
                    # azzerarle, vedi import_replica_character().
                    "world_id": "",
                    "origin_character_id": "",
                    "owner_device_id": "",
                    "is_replica": 0,
                    "world_seq": 0,
                    # world_instance_archived: stessa logica delle 5 colonne
                    # sopra — ha senso solo per un'istanza di mondo, un
                    # personaggio importato come locale non lo è mai.
                    "world_instance_archived": 0,
                },
            )
            conn.commit()
            logger.info(
                "import_character: personaggio importato con id=%s (mode=%s, source_id=%s)",
                target_id, mode, source_id,
            )
            return target_id
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Errore import_character (mode={mode}): {e}")
        if raise_errors:
            raise
        return None


# ---------------------------------------------------------------------------
# Helper file
# ---------------------------------------------------------------------------

def export_to_json_string(character_id: str) -> str | None:
    """export_character() + serializzazione JSON pronta da scrivere su file."""
    data = export_character(character_id)
    if data is None:
        return None
    try:
        return json.dumps(data, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Errore serializzazione JSON per {character_id}: {e}")
        return None


def load_json_string(text: str) -> dict[str, Any] | None:
    """Parsa una stringa JSON in un dict di export — ritorna None su errore di parsing."""
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except Exception as e:
        logger.error(f"Errore parsing JSON import: {e}")
        return None


def suggested_export_filename(character_id: str) -> str:
    """
    Nome file suggerito per l'export, es. "Thorin_Lv5_20260724_153000.dndchar"
    — leggibile a colpo d'occhio, senza caratteri problematici per il
    filesystem (solo alfanumerici, underscore e trattini).
    """
    import re

    summary = get_character_summary(character_id) or {}
    name = str(summary.get("name") or "personaggio")
    level = summary.get("level")
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_") or "personaggio"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    lvl_part = f"_Lv{level}" if level else ""
    return f"{slug}{lvl_part}_{ts}.dndchar"
