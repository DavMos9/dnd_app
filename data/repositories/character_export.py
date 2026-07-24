"""
Export/Import di un personaggio in un file singolo (JSON), per portarlo su
un altro dispositivo o dopo una reinstallazione — vedi CLAUDE.md TODO
"Import/Export personaggio" (richiesta di Davide, 2026-07-16) e il
changelog datato 2026-07-24 per il progetto completo di questa feature.

Principio architetturale: introspezione dello schema via `PRAGMA
table_info` invece di liste di colonne scritte a mano. Il progetto ha già
avuto più volte lo stesso bug (un campo aggiunto al dataclass/DB ma
dimenticato in una lista INSERT/UPDATE scritta a mano altrove — vedi
CLAUDE.md, sezione "Categoria B" e i vari fix "colonna assente
dall'INSERT/UPDATE generico"). Leggendo le colonne REALI della tabella a
runtime, sia in export sia in import, questa classe di bug è strutturalmente
impossibile per questo modulo: ogni colonna esistente viene sempre inclusa,
senza bisogno di aggiornare questo file ad ogni nuova colonna aggiunta al
resto del progetto.

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

def export_character(character_id: str) -> dict[str, Any] | None:
    """
    Costruisce il dizionario di export completo per un personaggio: la riga
    `characters` + tutte le righe di tutte le tabelle figlio, ciascuna come
    dict {colonna: valore} letto direttamente dallo schema reale.

    Ritorna None se il personaggio non esiste o in caso di errore (loggato).
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


def import_character(data: dict[str, Any], mode: str) -> str | None:
    """
    Importa un personaggio da un dict di export (stessa forma prodotta da
    export_character()).

    mode:
        "new"       → nessun conflitto atteso, inserisce con l'id originale
                      del file. Se l'id esiste già, l'INSERT fallisce
                      (IntegrityError) e la funzione ritorna None — la UI
                      deve SEMPRE controllare character_id_exists() prima
                      di usare questa modalità.
        "overwrite" → elimina il personaggio esistente con lo stesso id
                      (CASCADE rimuove automaticamente tutte le righe
                      figlio) e lo reinserisce da zero con gli id originali
                      del file.
        "copy"      → genera un nuovo id per il personaggio (e nuovi id per
                      ogni riga figlio che ne ha uno), creando un
                      personaggio distinto anche se il file aveva lo stesso
                      id di uno già presente.

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

    char_row: dict[str, Any] = dict(data["character"])
    related: dict[str, list[dict[str, Any]]] = data.get("related", {})

    source_id = str(char_row.get("id") or "")
    target_id = str(uuid.uuid4()) if mode == "copy" else source_id
    if not target_id:
        logger.error("import_character: id personaggio mancante nel file")
        return None

    try:
        conn = get_connection()
        try:
            if mode == "overwrite":
                # CASCADE rimuove automaticamente tutte le righe figlio.
                conn.execute("DELETE FROM characters WHERE id = ?", (target_id,))

            live_char_cols = _table_columns(conn, "characters")
            _insert_row(conn, "characters", char_row, live_char_cols, {"id": target_id})

            for table in CHILD_TABLES:
                rows = related.get(table) or []
                if not isinstance(rows, list):
                    continue
                live_cols = _table_columns(conn, table)
                has_id_column = "id" in live_cols
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    overrides: dict[str, Any] = {"character_id": target_id}
                    if has_id_column:
                        overrides["id"] = str(uuid.uuid4())
                    _insert_row(conn, table, row, live_cols, overrides)

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
