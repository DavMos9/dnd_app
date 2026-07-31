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


def get_character_exports_path() -> str:
    """
    Cartella condivisa per l'export/import di personaggi in modalità web —
    doppio ruolo, entrambi introdotti il 2026-07-24:

    1. IMPORT (stesso identico principio di get_image_library_path(),
       2026-07-12): ft.FilePicker è strutturalmente non utilizzabile in web
       mode (bug upstream Flet confermato flet-dev/flet#6040/#6250/#6251),
       quindi l'import mostra un picker con l'elenco dei file .dndchar già
       presenti qui — Davide li carica a mano via SSH/scp (vedi
       ui/character_transfer.py). Questo lato resta bloccato in web mode,
       nessun modo per farlo funzionare lato applicazione.

    2. EXPORT (aggiunto in un secondo momento, stessa data): questa cartella
       è anche passata come assets_dir a ft.run() in modalità web (vedi
       main.py) — Flet la monta staticamente alla radice dell'app. L'export
       web scrive qui il file .dndchar e lo apre con
       Button(url="/nomefile.dndchar", target=BLANK), che NON è un
       controllo Service (a differenza di FilePicker/UrlLauncher) e quindi
       non soffre dello stesso bug: il browser scarica il file con la sua
       UI standard di download, senza bisogno di alcun accesso SSH.

    Su desktop nativo questa funzione non viene usata: export/import
    passano dai dialoghi nativi del SO (vedi home_view.py), che lasciano
    scegliere liberamente il percorso — nessuna cartella fissa necessaria.

    Vedi CLAUDE.md per il changelog completo della feature Import/Export
    personaggio.
    """
    exports_dir = Path.home() / "dnd_character_exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    return str(exports_dir)


def get_assets_path() -> str:
    """
    Cartella `dnd_app/assets/` — passata come `assets_dir` a `ft.run()` su
    TUTTE le piattaforme (Fase A del restyle, 2026-07-26).

    Prima di questa modifica `assets_dir` non era impostata affatto su
    desktop/mobile, ed era occupata dalla cartella degli export in web mode:
    era quindi tecnicamente impossibile caricare un font custom, che è il
    prerequisito della Fase B del restyle (`ft.Page.fonts` legge da qui).

    L'export web continua a funzionare: scrive in una sottocartella servita
    (`assets/exports/`, vedi `get_web_export_staging_path()`), quindi l'URL
    di download passa da `/<file>.dndchar` a `/exports/<file>.dndchar`.
    L'IMPORT web resta invece su `get_character_exports_path()`
    (`~/dnd_character_exports`, il bind mount Docker che Davide popola via
    SSH): quel percorso NON cambia, nessuna modifica a docker-compose.yml.
    """
    assets_dir = Path(__file__).resolve().parent.parent / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    return str(assets_dir)


def get_web_export_staging_path() -> str:
    """
    Sottocartella servita staticamente da cui il browser scarica un
    `.dndchar` appena esportato (solo modalità web).

    È un'area di transito: in Docker vive nel filesystem del container, quindi
    il contenuto si perde al riavvio. Va bene — il file viene scaricato subito
    dopo l'export. La copia "persistente" che Davide preleva via SSH resta
    quella di `get_character_exports_path()`, dove l'export continua a
    scrivere in parallelo.
    """
    staging = Path(get_assets_path()) / "exports"
    staging.mkdir(parents=True, exist_ok=True)
    return str(staging)


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
    _add_column(cur, "characters", "exhaustion_level",            "INTEGER DEFAULT 0")
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
    # Bug reale trovato il 2026-07-17: il campo "reactions" esiste in
    # monsters.json ed è già letto/scritto da un mostro all'altro nel bestiary
    # picker, ma creature_entries non aveva MAI una colonna per riceverlo —
    # le Reazioni di un mostro (es. Parata) sparivano silenziosamente quando
    # il personaggio/master lo aggiungeva a Forma Selvatica/Evocazione. Vedi
    # CLAUDE.md 2026-07-17.
    _add_column(cur, "creature_entries", "reactions", "TEXT DEFAULT '[]'")
    # Azioni di Tana / Effetti Regionali (o "Tratti della Tana", stesso
    # concetto con nome diverso per il Demilich) — presenti solo per una
    # manciata di mostri con una tana propria (Kraken, Lich, Signore delle
    # Mummie, Sfinge, Unicorno, Vampiro, Demilich). Campi sempre vuoti per
    # tutti gli altri mostri. Vedi CLAUDE.md 2026-07-17.
    _add_column(cur, "creature_entries", "lair_actions_intro", "TEXT DEFAULT ''")
    _add_column(cur, "creature_entries", "lair_actions", "TEXT DEFAULT '[]'")
    _add_column(cur, "creature_entries", "regional_effects_label", "TEXT DEFAULT ''")
    _add_column(cur, "creature_entries", "regional_effects_intro", "TEXT DEFAULT ''")
    _add_column(cur, "creature_entries", "regional_effects", "TEXT DEFAULT '[]'")
    # Varianti opzionali "sidebar" del manuale (es. "Arma su Asta del Diavolo
    # d'Ossa", "Congreghe di Megere") — regole facoltative legate a un mostro
    # specifico, non un mostro a sé. Sola consultazione, il master decide se
    # applicarle. Vedi CLAUDE.md 2026-07-17.
    _add_column(cur, "creature_entries", "variant_rules", "TEXT DEFAULT '[]'")
    # Calcolo automatico tiro per colpire (2026-07-17, vedi CLAUDE.md) —
    # categoria PHB per il match di competenza (character_proficiencies),
    # override esplicito di competenza/caratteristica/totale attacco.
    _add_column(cur, "weapons", "weapon_category",        "TEXT DEFAULT ''")
    _add_column(cur, "weapons", "proficiency_override",   "INTEGER DEFAULT 0")
    _add_column(cur, "weapons", "finesse_ability",        "TEXT DEFAULT ''")
    _add_column(cur, "weapons", "attack_total_override",  "INTEGER DEFAULT 0")
    _add_column(cur, "weapons", "attack_override_value",  "INTEGER DEFAULT 0")
    # Barbaro Cammino del Berserker — Frenesia dichiarata per l'ira in corso
    # (0/1). Vedi data/models.py → Character.frenzy_active e CLAUDE.md
    # 2026-07-19 per il changelog completo.
    _add_column(cur, "characters", "frenzy_active", "INTEGER DEFAULT 0")
    # Sezione Master — Calcolatore Difficoltà Incontro (2026-07-24): PE del
    # mostro/NPC, per sommarli senza dover ricalcolare da un grado di sfida
    # (monsters.json ha già xp per ognuno dei 444 mostri auditati; per un NPC
    # "Nuovo Manuale" senza stat block il Master può valorizzarlo a mano).
    # Idempotente anche per chi ha già le 3 tabelle Master da prima di questa
    # colonna (create_table_if_not_exists non la aggiungerebbe da sola).
    _add_column(cur, "master_npcs", "xp", "INTEGER DEFAULT 0")
    # Modificatore di Destrezza del combattente, catturato quando lo si
    # aggiunge (Fase 4, feature 4a): serve a "Tira iniziativa per tutti", che
    # altrimenti non avrebbe alcun dato da cui tirare per i membri "adhoc"
    # (un mostro preso dal bestiario non lascia traccia del proprio stat block).
    _add_column(cur, "master_encounter_members", "dex_mod", "INTEGER DEFAULT 0")
    # Concentrazione (Fase 4, feature 2a — PHB p.203-204). Colonne e non una
    # tabella: il manuale è esplicito, "un incantatore non può concentrarsi su
    # due incantesimi alla volta", quindi lo stato è al più uno.
    _add_column(cur, "characters", "concentrating_spell", "TEXT DEFAULT ''")
    _add_column(cur, "characters", "concentrating_since", "TEXT DEFAULT ''")
    # Sintonia con gli oggetti magici (Fase 4, feature 3 — DMG p.138).
    # `requires_attunement` vive sull'ITEM e non solo nel catalogo: un oggetto
    # homebrew inserito a mano può richiederla pur non stando in magic_items.json.
    _add_column(cur, "inventory_items", "requires_attunement", "INTEGER DEFAULT 0")
    _add_column(cur, "inventory_items", "is_attuned", "INTEGER DEFAULT 0")
    _add_column(cur, "master_encounter_members", "xp", "INTEGER DEFAULT 0")


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

    # ------------------------------------------------------------------
    # Sezione Master — rubrica NPC/mostri, incontri, membri d'incontro
    # (2026-07-24). Deliberatamente INDIPENDENTI da `characters`/
    # `creature_entries`: quest'ultima ha character_id NOT NULL CASCADE,
    # semantica "creatura temporanea di UN personaggio" — renderla nullable
    # per riusarla anche qui avrebbe rischiato regressioni su Forma
    # Selvatica/Evocazioni già in produzione. Vedi
    # dnd_app/docs/master_section_design.md per il design completo.
    # ------------------------------------------------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS master_npcs (
            id                     TEXT PRIMARY KEY,
            name                   TEXT NOT NULL DEFAULT '',
            role                   TEXT NOT NULL DEFAULT '',
            notes                  TEXT NOT NULL DEFAULT '',
            tags                   TEXT NOT NULL DEFAULT '',
            has_stat_block         INTEGER NOT NULL DEFAULT 0,
            creature_type          TEXT NOT NULL DEFAULT '',
            size                   TEXT NOT NULL DEFAULT '',
            alignment              TEXT NOT NULL DEFAULT '',
            ac                     INTEGER NOT NULL DEFAULT 10,
            ac_note                TEXT NOT NULL DEFAULT '',
            hp_max                 INTEGER NOT NULL DEFAULT 1,
            hp_formula             TEXT NOT NULL DEFAULT '',
            speed                  TEXT NOT NULL DEFAULT '',
            str_score              INTEGER NOT NULL DEFAULT 10,
            dex_score              INTEGER NOT NULL DEFAULT 10,
            con_score              INTEGER NOT NULL DEFAULT 10,
            int_score              INTEGER NOT NULL DEFAULT 10,
            wis_score              INTEGER NOT NULL DEFAULT 10,
            cha_score              INTEGER NOT NULL DEFAULT 10,
            saving_throws          TEXT NOT NULL DEFAULT '{}',
            skills                 TEXT NOT NULL DEFAULT '{}',
            damage_vulnerabilities TEXT NOT NULL DEFAULT '',
            damage_resistances     TEXT NOT NULL DEFAULT '',
            damage_immunities      TEXT NOT NULL DEFAULT '',
            condition_immunities   TEXT NOT NULL DEFAULT '',
            senses                 TEXT NOT NULL DEFAULT '',
            languages              TEXT NOT NULL DEFAULT '',
            cr                     TEXT NOT NULL DEFAULT '',
            xp                     INTEGER NOT NULL DEFAULT 0,
            traits                 TEXT NOT NULL DEFAULT '[]',
            actions                TEXT NOT NULL DEFAULT '[]',
            reactions              TEXT NOT NULL DEFAULT '[]',
            legendary_actions      TEXT NOT NULL DEFAULT '[]',
            source_page            TEXT NOT NULL DEFAULT '',
            created_at             TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at             TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_master_npcs_name
        ON master_npcs(name)
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS master_encounters (
            id                  TEXT PRIMARY KEY,
            name                TEXT NOT NULL DEFAULT '',
            notes               TEXT NOT NULL DEFAULT '',
            round_number        INTEGER NOT NULL DEFAULT 1,
            current_turn_index  INTEGER NOT NULL DEFAULT 0,
            is_archived         INTEGER NOT NULL DEFAULT 0,
            created_at          TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_master_encounters_archived
        ON master_encounters(is_archived)
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS master_encounter_members (
            id            TEXT PRIMARY KEY,
            encounter_id  TEXT NOT NULL REFERENCES master_encounters(id) ON DELETE CASCADE,
            kind          TEXT NOT NULL DEFAULT 'adhoc',
            character_id  TEXT REFERENCES characters(id) ON DELETE CASCADE,
            npc_id        TEXT REFERENCES master_npcs(id) ON DELETE SET NULL,
            display_name  TEXT NOT NULL DEFAULT '',
            ac            INTEGER NOT NULL DEFAULT 0,
            hp_current    INTEGER NOT NULL DEFAULT 0,
            hp_max        INTEGER NOT NULL DEFAULT 0,
            xp            INTEGER NOT NULL DEFAULT 0,
            initiative    INTEGER NOT NULL DEFAULT 0,
            dex_mod       INTEGER NOT NULL DEFAULT 0,
            order_index   INTEGER NOT NULL DEFAULT 0,
            is_active     INTEGER NOT NULL DEFAULT 1,
            notes         TEXT NOT NULL DEFAULT '',
            created_at    TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_master_encounter_members_encounter
        ON master_encounter_members(encounter_id)
    """)

    # ------------------------------------------------------------------
    # master_campaign_notes (2026-07-24) — Note di Campagna del Master,
    # stessa forma di `campaign_notes` (già esistente per DiaryView) ma
    # SENZA character_id: indipendente da ogni personaggio, vive solo nella
    # Sezione Master. 8 categorie: le 6 già condivise con campaign_notes
    # ("npc"/"npc_todo"/"place"/"place_todo"/"quest"/"faction") più due
    # nuove ("event"/"secret"). Nessuna fonte DMG da citare — puro
    # strumento organizzativo, non regolamento. Vedi
    # dnd_app/docs/master_section_design.md sezione "5.".
    # ------------------------------------------------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS master_campaign_notes (
            id             TEXT PRIMARY KEY,
            category       TEXT NOT NULL DEFAULT 'npc',
            name           TEXT NOT NULL DEFAULT '',
            description    TEXT NOT NULL DEFAULT '',
            status         TEXT NOT NULL DEFAULT '',
            tags           TEXT NOT NULL DEFAULT '',
            linked_npc_id  TEXT REFERENCES master_npcs(id) ON DELETE SET NULL,
            created_at     TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at     TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_master_campaign_notes_category
        ON master_campaign_notes(category)
    """)

    # ------------------------------------------------------------------
    # app_settings (2026-07-30, Fase D del restyle) — preferenze
    # dell'INSTALLAZIONE, non del personaggio: nessun `character_id`,
    # nessuna FK, nessun CASCADE. Eliminare un personaggio non deve toccare
    # il tema scelto, ed esportare un personaggio in `.dndchar` non deve
    # portarsi dietro le preferenze della macchina di origine — per questo
    # la tabella NON compare in `CHILD_TABLES` di `character_export.py`.
    #
    # Forma chiave/valore generica invece di una colonna per preferenza:
    # aggiungerne una in futuro (densità, dimensione testo — entrambe
    # valutate e rimandate) non richiede una migrazione di schema.
    #
    # Prima e unica chiave oggi: "theme_mode" → "light" | "dark" | "system".
    # Vedi `data/repositories/settings_repo.py`.
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # character_conditions (2026-07-30, Fase 4 feature 2b) — le condizioni
    # dell'Appendice A del PHB attive su un personaggio. Tabella e non colonne
    # perche' le condizioni possono essere piu' di una insieme e ognuna puo'
    # avere una fonte diversa ("Spavento del Bardo", "morso del ragno").
    # L'Indebolimento resta su characters.exhaustion_level: e' l'unica con
    # livelli cumulativi invece che on/off.
    # ------------------------------------------------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS character_conditions (
            id             TEXT PRIMARY KEY,
            character_id   TEXT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
            condition_key  TEXT NOT NULL,
            source         TEXT NOT NULL DEFAULT '',
            note           TEXT NOT NULL DEFAULT '',
            created_at     TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_character_conditions_character
        ON character_conditions(character_id)
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS app_settings (
            key        TEXT PRIMARY KEY,
            value      TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
