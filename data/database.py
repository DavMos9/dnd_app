"""
Inizializzazione e connessione al database SQLite.
Tutte le operazioni DDL (creazione tabelle) sono qui.
"""

import sqlite3
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _writable(p: Path) -> bool:
    """Verifica che il path esista e sia scrivibile senza creare directory parent."""
    try:
        p.mkdir(exist_ok=True)          # crea solo la dir finale, NON i parent
        t = p / ".write_test"
        t.touch(); t.unlink()
        return True
    except Exception:
        return False


def get_db_path() -> str:
    """Restituisce il percorso del database.

    Android: tre strategie in ordine di affidabilità:
      1. TMPDIR  → Android lo punta alla cache dell'app, saliamo di un livello per files/
      2. Percorsi interni noti (senza mkdir parents — le dir parent esistono già)
      3. CWD come ultima spiaggia
    Desktop (Mac/Win/Linux): ~/.dnd_companion/ come sempre.
    """
    _BUNDLE = "com.davmos9.dndcompanion"

    # ANDROID_DATA è sempre impostata su Android (= /data); assente su desktop
    is_android = bool(os.environ.get("ANDROID_DATA"))

    if is_android:
        # Logga le env var utili per il debug
        for var in ("TMPDIR", "TMP", "TEMP", "HOME", "ANDROID_DATA", "EXTERNAL_STORAGE"):
            logger.debug("ENV %s=%s", var, os.environ.get(var, "<non impostata>"))

        # ── Strategia 1: TMPDIR ──────────────────────────────────────────────
        # Android imposta TMPDIR sulla cache privata dell'app:
        #   /data/user/0/{bundle}/cache  →  saliamo di un livello → .../files/
        tmpdir = os.environ.get("TMPDIR") or os.environ.get("TMP") or ""
        if tmpdir:
            candidate = Path(tmpdir).parent / "files"
            if _writable(candidate):
                logger.info("DB path Android (TMPDIR): %s", candidate)
                return str(candidate / "dnd_companion.db")

        # ── Strategia 2: percorsi interni noti ───────────────────────────────
        # Le directory già esistono dopo l'installazione; NON usiamo parents=True
        for p in [
            Path(f"/data/user/0/{_BUNDLE}/files"),
            Path(f"/data/data/{_BUNDLE}/files"),
        ]:
            if _writable(p):
                logger.info("DB path Android (hardcoded): %s", p)
                return str(p / "dnd_companion.db")

        # ── Strategia 3: CWD ─────────────────────────────────────────────────
        cwd = Path.cwd()
        if _writable(cwd):
            logger.warning("DB path Android (CWD): %s", cwd)
            return str(cwd / "dnd_companion.db")

        logger.error("Nessun path Android scrivibile trovato — il DB non verrà salvato")
        return "dnd_companion.db"

    else:
        # Desktop: comportamento originale invariato
        app_dir = Path.home() / ".dnd_companion"
        app_dir.mkdir(parents=True, exist_ok=True)
        return str(app_dir / "dnd_companion.db")


def get_image_library_path() -> str:
    """
    Cartella "libreria immagini" server-side, gestita a mano da Davide via
    SSH (scp/rsync) -- NON un upload dal client attraverso Flet.

    Aggiunta il 2026-07-12 in sostituzione di un precedente tentativo
    (get_upload_dir_path(), rimosso) che si basava su ft.FilePicker +
    page.get_upload_url() per un vero upload client-server: quel
    meccanismo si e' rivelato IRRAGGIUNGIBILE in modalita' web per un bug
    upstream confermato di Flet (flet-dev/flet#6040, #6250, #6251 -- i
    controlli "Service" come FilePicker sono strutturalmente rotti in web
    mode, indipendentemente da come li si usa). Vedi CLAUDE.md per il
    changelog completo dei tre tentativi.

    Soluzione adottata: Davide carica le immagini direttamente sul
    filesystem del server (bind mount Docker, vedi docker-compose.yml ->
    "./dnd_image_library:/root/dnd_image_library") usando SSH/scp -- nessun
    controllo Flet coinvolto. L'app legge questa cartella e mostra un
    picker con le miniature (vedi ui/image_library.py).

    Deliberatamente FUORI da "~/.dnd_companion/" (che resta un dotfolder
    privato per il DB, non pensato per essere navigato a mano): questa
    cartella e' invece pensata per essere raggiunta direttamente da
    Davide, quindi ha un nome visibile e descrittivo. Nessuna logica
    speciale per Android: questa funzione e' pensata per il solo deploy
    web via Docker, dove l'app gira come root -- Path.home() risolve a
    "/root", coerente con il path del bind mount in docker-compose.yml.
    """
    lib_dir = Path.home() / "dnd_image_library"
    lib_dir.mkdir(parents=True, exist_ok=True)
    return str(lib_dir)


def get_connection() -> sqlite3.Connection:
    """Apre e restituisce una connessione SQLite con row_factory."""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db() -> None:
    """Crea tutte le tabelle se non esistono ancora."""
    conn = get_connection()
    try:
        _create_tables(conn)
        _migrate(conn)
        conn.commit()
        logger.info("Database inizializzato correttamente.")
    except Exception as e:
        logger.error(f"Errore durante l'inizializzazione del database: {e}")
        raise
    finally:
        conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    """Esegue migrazioni incrementali sul DB esistente (idempotenti)."""
    cur = conn.cursor()

    _add_column(cur, "characters",     "image_data",      "TEXT DEFAULT ''")
    _add_column(cur, "characters",     "ca_bonus",                    "INTEGER DEFAULT 0")
    _add_column(cur, "characters",     "proficiency_bonus_override",  "INTEGER DEFAULT 0")
    _add_column(cur, "characters",     "session_notes",               "TEXT DEFAULT ''")
    _add_column(cur, "characters",     "max_prepared_spells_override", "INTEGER DEFAULT 0")
    _add_column(cur, "characters",     "dragon_ancestry",  "TEXT DEFAULT ''")
    _add_column(cur, "characters",     "fighting_style",   "TEXT DEFAULT ''")
    _add_column(cur, "characters",     "totem_animal",     "TEXT DEFAULT ''")
    _add_column(cur, "characters",     "land_terrain",     "TEXT DEFAULT ''")
    _add_column(cur, "characters",     "pact_boon",         "TEXT DEFAULT ''")
    _add_column(cur, "characters",              "initiative_bonus",  "INTEGER DEFAULT 0")
    _add_column(cur, "character_proficiencies", "bonus_data",        "TEXT DEFAULT NULL")
    _add_column(cur, "character_proficiencies", "level_obtained",    "INTEGER DEFAULT 0")
    _add_column(cur, "weapons",                 "magic_damages",     "TEXT DEFAULT '[]'")
    _add_column(cur, "weapons",                 "versatile_damage_dice", "TEXT DEFAULT ''")
    _add_column(cur, "weapons",                 "grip_two_handed",   "INTEGER DEFAULT 0")
    _add_column(cur, "inventory_items","ca_value",        "INTEGER DEFAULT 0")
    _add_column(cur, "inventory_items","armor_type",      "TEXT DEFAULT ''")
    _add_column(cur, "inventory_items","effects",          "TEXT DEFAULT ''")
    _add_column(cur, "game_maps",      "image_data",       "TEXT DEFAULT ''")
    _add_column(cur, "game_maps",      "notes",            "TEXT DEFAULT ''")
    # Mistificatore Arcano (Ladro) / Cavaliere Mistico (Guerriero) — traccia se
    # una riga known_spells è un pick "libero da vincolo di scuola" (8°/14°/20°
    # livello, +3° per il Cavaliere Mistico) — necessario per sapere, in un
    # futuro scambio, se il rimpiazzo può essere di qualsiasi scuola. Vedi
    # CLAUDE.md 2026-07-15, fix Mistificatore Arcano/Cavaliere Mistico.
    _add_column(cur, "known_spells",   "origin_unrestricted", "INTEGER DEFAULT 0")
    # Override manuali (2026-07-16, richiesta Davide: "rendiamo modificabili
    # anche i campi che non si possono modificare attualmente") — stesso
    # pattern di proficiency_bonus_override/max_prepared_spells_override:
    # 0 = nessun override, usa il valore calcolato dalla formula PHB.
    _add_column(cur, "characters", "passive_perception_override", "INTEGER DEFAULT 0")
    _add_column(cur, "characters", "carry_capacity_override",     "REAL DEFAULT 0")
    # Bonus permanente al massimo di una risorsa di classe (es. talento o
    # oggetto magico che concede +1 uso) — additivo rispetto al valore PHB
    # calcolato da get_class_resource_defaults(), sopravvive al ri-sync di
    # init_class_resources() (che altrimenti sovrascriverebbe max_value a
    # ogni apertura tab/level-up). Vedi CLAUDE.md 2026-07-16.
    _add_column(cur, "class_resources", "max_value_bonus", "INTEGER DEFAULT 0")
    # Incantesimo bonus aggiunto manualmente dal giocatore (es. concesso dal
    # master) — sezione dedicata "Incantesimi Bonus" in spells_view.py,
    # sempre visibile anche per classi senza spellcasting_ability. Distinto
    # dal meccanismo "extra" già esistente (Segreti Magici/Mistificatore)
    # perché quello si basa solo sul nome non presente nella lista di classe:
    # un incantesimo bonus scelto dalla STESSA lista della classe del
    # personaggio andrebbe altrimenti confuso con un incantesimo normale già
    # preparato. Vedi CLAUDE.md 2026-07-16.
    _add_column(cur, "known_spells", "is_bonus", "INTEGER DEFAULT 0")
    # Incantesimo sempre pronto da privilegio di Dominio/Giuramento/Circolo
    # (es. Paladino Giuramento degli Antichi Lv.3: Colpo Intrappolante,
    # Parlare con gli Animali) — non conta nel tetto di preparazione
    # giornaliera e non è disattivabile dal giocatore. Sincronizzato
    # automaticamente da character_repo.sync_bonus_domain_spells() ad ogni
    # apertura tab/level-up/level-down (self-healing, stesso pattern delle
    # risorse di classe). Vedi CLAUDE.md 2026-07-16.
    _add_column(cur, "known_spells", "always_prepared", "INTEGER DEFAULT 0")


def _add_column(cur: sqlite3.Cursor, table: str, column: str, definition: str) -> None:
    """Aggiunge una colonna a una tabella se non esiste già."""
    try:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        logger.info("Migrazione: aggiunta colonna %s.%s", table, column)
    except sqlite3.OperationalError:
        pass  # colonna già esistente


def _create_tables(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()

    # ------------------------------------------------------------------
    # Personaggi
    # ------------------------------------------------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS characters (
            id                   TEXT PRIMARY KEY,
            name                 TEXT NOT NULL DEFAULT '',
            player_name          TEXT NOT NULL DEFAULT '',
            class_name           TEXT NOT NULL DEFAULT '',
            subclass             TEXT NOT NULL DEFAULT '',
            level                INTEGER NOT NULL DEFAULT 1,
            race                 TEXT NOT NULL DEFAULT '',
            subrace              TEXT NOT NULL DEFAULT '',
            background           TEXT NOT NULL DEFAULT '',
            alignment            TEXT NOT NULL DEFAULT '',
            xp                   INTEGER NOT NULL DEFAULT 0,
            image_path           TEXT NOT NULL DEFAULT '',

            -- Caratteristiche
            str_score            INTEGER NOT NULL DEFAULT 10,
            dex_score            INTEGER NOT NULL DEFAULT 10,
            con_score            INTEGER NOT NULL DEFAULT 10,
            int_score            INTEGER NOT NULL DEFAULT 10,
            wis_score            INTEGER NOT NULL DEFAULT 10,
            cha_score            INTEGER NOT NULL DEFAULT 10,

            -- Punti ferita
            hp_max               INTEGER NOT NULL DEFAULT 0,
            hp_current           INTEGER NOT NULL DEFAULT 0,
            hp_temp              INTEGER NOT NULL DEFAULT 0,

            -- Combattimento
            ac                   INTEGER NOT NULL DEFAULT 10,
            speed                REAL NOT NULL DEFAULT 9,
            hit_dice_type        INTEGER NOT NULL DEFAULT 6,
            hit_dice_total       INTEGER NOT NULL DEFAULT 1,
            hit_dice_remaining   INTEGER NOT NULL DEFAULT 1,

            -- Tiri salvezza contro morte
            death_saves_success  INTEGER NOT NULL DEFAULT 0,
            death_saves_failure  INTEGER NOT NULL DEFAULT 0,

            -- Stato turno (persiste tra sessioni per sicurezza)
            action_used          INTEGER NOT NULL DEFAULT 0,
            bonus_action_used    INTEGER NOT NULL DEFAULT 0,
            reaction_used        INTEGER NOT NULL DEFAULT 0,
            movement_used        REAL NOT NULL DEFAULT 0,
            previous_turn_state  TEXT NOT NULL DEFAULT '',

            -- Magia
            spellcasting_ability TEXT NOT NULL DEFAULT '',

            -- Ispirazione
            inspiration          INTEGER NOT NULL DEFAULT 0,

            -- Dettagli fisici
            age                  TEXT NOT NULL DEFAULT '',
            height               TEXT NOT NULL DEFAULT '',
            weight               TEXT NOT NULL DEFAULT '',
            eyes                 TEXT NOT NULL DEFAULT '',
            skin                 TEXT NOT NULL DEFAULT '',
            hair                 TEXT NOT NULL DEFAULT '',

            -- Personalità e background narrativo
            personality_traits   TEXT NOT NULL DEFAULT '',
            ideals               TEXT NOT NULL DEFAULT '',
            bonds                TEXT NOT NULL DEFAULT '',
            flaws                TEXT NOT NULL DEFAULT '',
            backstory            TEXT NOT NULL DEFAULT '',
            allies_organizations TEXT NOT NULL DEFAULT '',
            additional_traits    TEXT NOT NULL DEFAULT '',
            appearance_notes     TEXT NOT NULL DEFAULT '',

            -- Metadati
            created_at           TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at           TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    # ------------------------------------------------------------------
    # Competenze (abilità, tiri salvezza, strumenti, linguaggi, armi, armature)
    # ------------------------------------------------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS character_proficiencies (
            id                TEXT PRIMARY KEY,
            character_id      TEXT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
            proficiency_type  TEXT NOT NULL,
            name              TEXT NOT NULL,
            is_expert         INTEGER NOT NULL DEFAULT 0
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_proficiencies_character
        ON character_proficiencies(character_id)
    """)

    # ------------------------------------------------------------------
    # Armi equipaggiate
    # ------------------------------------------------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS weapons (
            id                TEXT PRIMARY KEY,
            character_id      TEXT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
            name              TEXT NOT NULL DEFAULT '',
            damage_dice       TEXT NOT NULL DEFAULT '',
            damage_type       TEXT NOT NULL DEFAULT '',
            attack_bonus      INTEGER NOT NULL DEFAULT 0,
            damage_bonus      INTEGER NOT NULL DEFAULT 0,
            properties        TEXT NOT NULL DEFAULT '',
            is_magical        INTEGER NOT NULL DEFAULT 0,
            magic_description TEXT NOT NULL DEFAULT '',
            is_equipped       INTEGER NOT NULL DEFAULT 1,
            range_normal      INTEGER NOT NULL DEFAULT 0,
            range_max         INTEGER NOT NULL DEFAULT 0
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_weapons_character
        ON weapons(character_id)
    """)

    # ------------------------------------------------------------------
    # Inventario
    # ------------------------------------------------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS inventory_items (
            id           TEXT PRIMARY KEY,
            character_id TEXT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
            name         TEXT NOT NULL DEFAULT '',
            quantity     INTEGER NOT NULL DEFAULT 1,
            weight       REAL NOT NULL DEFAULT 0.0,
            description  TEXT NOT NULL DEFAULT '',
            category     TEXT NOT NULL DEFAULT 'misc',
            is_equipped  INTEGER NOT NULL DEFAULT 0
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_inventory_character
        ON inventory_items(character_id)
    """)

    # ------------------------------------------------------------------
    # Valute
    # ------------------------------------------------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS currencies (
            character_id TEXT PRIMARY KEY REFERENCES characters(id) ON DELETE CASCADE,
            copper       INTEGER NOT NULL DEFAULT 0,
            silver       INTEGER NOT NULL DEFAULT 0,
            electrum     INTEGER NOT NULL DEFAULT 0,
            gold         INTEGER NOT NULL DEFAULT 0,
            platinum     INTEGER NOT NULL DEFAULT 0
        )
    """)

    # ------------------------------------------------------------------
    # Slot incantesimo (livelli 1-9)
    # ------------------------------------------------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS spell_slots (
            character_id TEXT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
            slot_level   INTEGER NOT NULL CHECK(slot_level BETWEEN 1 AND 9),
            total        INTEGER NOT NULL DEFAULT 0,
            used         INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (character_id, slot_level)
        )
    """)

    # ------------------------------------------------------------------
    # Incantesimi conosciuti/preparati
    # ------------------------------------------------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS known_spells (
            id            TEXT PRIMARY KEY,
            character_id  TEXT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
            name          TEXT NOT NULL DEFAULT '',
            spell_level   INTEGER NOT NULL DEFAULT 0,
            is_prepared   INTEGER NOT NULL DEFAULT 0,
            school        TEXT NOT NULL DEFAULT '',
            casting_time  TEXT NOT NULL DEFAULT '',
            spell_range   TEXT NOT NULL DEFAULT '',
            components    TEXT NOT NULL DEFAULT '',
            duration      TEXT NOT NULL DEFAULT '',
            description   TEXT NOT NULL DEFAULT '',
            higher_levels TEXT NOT NULL DEFAULT '',
            class_list    TEXT NOT NULL DEFAULT ''
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_spells_character
        ON known_spells(character_id)
    """)

    # ------------------------------------------------------------------
    # Diario
    # ------------------------------------------------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS diary_entries (
            id           TEXT PRIMARY KEY,
            character_id TEXT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
            title        TEXT NOT NULL DEFAULT '',
            content      TEXT NOT NULL DEFAULT '',
            session_date TEXT NOT NULL DEFAULT '',
            created_at   TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_diary_character
        ON diary_entries(character_id)
    """)

    # ------------------------------------------------------------------
    # Mappe
    # ------------------------------------------------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS game_maps (
            id           TEXT PRIMARY KEY,
            character_id TEXT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
            name         TEXT NOT NULL DEFAULT '',
            image_path   TEXT NOT NULL DEFAULT '',
            annotations  TEXT NOT NULL DEFAULT '[]',
            created_at   TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_maps_character
        ON game_maps(character_id)
    """)

    # ------------------------------------------------------------------
    # Risorse di classe (Furia, Ki, Incanalare Divinità, ecc.)
    # ------------------------------------------------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS class_resources (
            id            TEXT PRIMARY KEY,
            character_id  TEXT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
            name          TEXT NOT NULL DEFAULT '',
            max_value     INTEGER NOT NULL DEFAULT 0,
            current_value INTEGER NOT NULL DEFAULT 0,
            reset_on      TEXT NOT NULL DEFAULT 'long_rest',
            display_type  TEXT NOT NULL DEFAULT 'circles'
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_class_resources_character
        ON class_resources(character_id)
    """)

    # ------------------------------------------------------------------
    # Creature (Forme Selvatiche e Evocazioni)
    # ------------------------------------------------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS creature_entries (
            id                    TEXT PRIMARY KEY,
            character_id          TEXT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
            entry_type            TEXT NOT NULL DEFAULT 'evocazione',
            name                  TEXT NOT NULL DEFAULT '',
            creature_type         TEXT NOT NULL DEFAULT '',
            alignment             TEXT NOT NULL DEFAULT '',
            cr                    TEXT NOT NULL DEFAULT '',
            ac                    INTEGER NOT NULL DEFAULT 10,
            ac_note               TEXT NOT NULL DEFAULT '',
            hp_max                INTEGER NOT NULL DEFAULT 1,
            hp_formula            TEXT NOT NULL DEFAULT '',
            hp_current            INTEGER NOT NULL DEFAULT 1,
            speed                 TEXT NOT NULL DEFAULT '',
            str_score             INTEGER NOT NULL DEFAULT 10,
            dex_score             INTEGER NOT NULL DEFAULT 10,
            con_score             INTEGER NOT NULL DEFAULT 10,
            int_score             INTEGER NOT NULL DEFAULT 10,
            wis_score             INTEGER NOT NULL DEFAULT 10,
            cha_score             INTEGER NOT NULL DEFAULT 10,
            saving_throws         TEXT NOT NULL DEFAULT '{}',
            skills                TEXT NOT NULL DEFAULT '{}',
            damage_vulnerabilities TEXT NOT NULL DEFAULT '',
            damage_resistances    TEXT NOT NULL DEFAULT '',
            damage_immunities     TEXT NOT NULL DEFAULT '',
            condition_immunities  TEXT NOT NULL DEFAULT '',
            senses                TEXT NOT NULL DEFAULT '',
            languages             TEXT NOT NULL DEFAULT '',
            traits                TEXT NOT NULL DEFAULT '[]',
            actions               TEXT NOT NULL DEFAULT '[]',
            legendary_actions     TEXT NOT NULL DEFAULT '[]',
            is_active             INTEGER NOT NULL DEFAULT 0,
            notes                 TEXT NOT NULL DEFAULT '',
            source_page           INTEGER NOT NULL DEFAULT 0,
            created_at            TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at            TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_creature_entries_character
        ON creature_entries(character_id, entry_type)
    """)

    # ------------------------------------------------------------------
    # Note di Campagna (PNG, Luoghi, Missioni, Fazioni)
    # ------------------------------------------------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS campaign_notes (
            id           TEXT PRIMARY KEY,
            character_id TEXT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
            category     TEXT NOT NULL DEFAULT '',
            name         TEXT NOT NULL DEFAULT '',
            description  TEXT NOT NULL DEFAULT '',
            status       TEXT NOT NULL DEFAULT '',
            tags         TEXT NOT NULL DEFAULT '',
            created_at   TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_campaign_notes_character
        ON campaign_notes(character_id, category)
    """)

    # ------------------------------------------------------------------
    # Abilità Speciali custom (2026-07-16, richiesta Davide: abilità
    # concesse dal master o voci aggiuntive non presenti nel PHB — non
    # vanno mai a modificare in-place il testo ufficiale di una feature di
    # classe/razza già rappresentata nei JSON, solo ad affiancarlo).
    # category: "esplorazione" | "combattimento"
    # ------------------------------------------------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS custom_abilities (
            id           TEXT PRIMARY KEY,
            character_id TEXT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
            category     TEXT NOT NULL DEFAULT 'esplorazione',
            name         TEXT NOT NULL DEFAULT '',
            description  TEXT NOT NULL DEFAULT '',
            created_at   TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_custom_abilities_character
        ON custom_abilities(character_id, category)
    """)
