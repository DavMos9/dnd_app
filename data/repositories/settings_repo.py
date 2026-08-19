"""
Preferenze dell'installazione — tabella chiave/valore `app_settings`.

Introdotto con la **Fase D del restyle** (vedi
`dnd_app/docs/restyle_design.md` § FASE D): serviva un posto dove ricordare la
preferenza di tema tra un avvio e l'altro.

**Perché non sul personaggio**: il tema è una proprietà della macchina su cui
si sta giocando, non del personaggio. Un giocatore che usa l'app sul tablet la
sera e sul portatile di giorno vuole una scelta diversa per dispositivo, non
per PG; e importare un `.dndchar` da un altro dispositivo non deve cambiare
l'aspetto dell'app. Per lo stesso motivo `app_settings` **non** compare tra le
`CHILD_TABLES` di `character_export.py`.

**Perché chiave/valore e non una colonna per preferenza**: aggiungerne una in
futuro (densità dell'interfaccia, dimensione del testo — entrambe valutate e
rimandate) non richiede una migrazione di schema.

Robustezza: nessuna funzione qui solleva mai un'eccezione verso la UI. Un DB
irraggiungibile o un valore corrotto/scritto a mano produce un `logger` e il
default, mai un avvio fallito — una preferenza estetica non deve poter
impedire l'apertura dell'app.
"""

from __future__ import annotations

import logging
from typing import Literal, get_args

from data.database import get_connection

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Chiavi note
# ---------------------------------------------------------------------------

#: Preferenza di tema. "system" segue il tema del sistema operativo e reagisce
#: dal vivo quando cambia (vedi `DnDApp._on_system_brightness_change`).
THEME_MODE_KEY = "theme_mode"

ThemePreference = Literal["light", "dark", "system"]

#: I tre valori ammessi, nell'ordine in cui il pulsante li cicla.
THEME_PREFERENCES: tuple[ThemePreference, ...] = get_args(ThemePreference)

#: Default alla prima apertura: seguire il sistema operativo.
DEFAULT_THEME_PREFERENCE: ThemePreference = "system"


# ---------------------------------------------------------------------------
# Accesso generico
# ---------------------------------------------------------------------------


def get_setting(key: str, default: str = "") -> str:
    """Legge una preferenza. Ritorna `default` se assente o in caso di errore."""
    try:
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT value FROM app_settings WHERE key = ?", (key,)
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return default
        value = row["value"]
        return default if value is None else str(value)
    except Exception as e:
        logger.error(f"Lettura della preferenza '{key}' fallita: {e}")
        return default


def set_setting(key: str, value: str) -> bool:
    """
    Scrive una preferenza. Ritorna `False` (senza sollevare) in caso di errore.

    `INSERT OR REPLACE` invece di `ON CONFLICT ... DO UPDATE`: qui le due forme
    sono equivalenti (nessuna FK punta a questa tabella, nessuna colonna da
    preservare oltre a quelle riscritte) e la prima è supportata da qualunque
    versione di SQLite, incluse quelle di sistema più vecchie su macOS/Linux.
    """
    try:
        conn = get_connection()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO app_settings (key, value, updated_at)
                VALUES (?, ?, datetime('now'))
                """,
                (key, value),
            )
            conn.commit()
        finally:
            conn.close()
        return True
    except Exception as e:
        logger.error(f"Scrittura della preferenza '{key}' fallita: {e}")
        return False


# ---------------------------------------------------------------------------
# Tema
# ---------------------------------------------------------------------------


def get_theme_preference() -> ThemePreference:
    """
    Preferenza di tema salvata, normalizzata.

    Un valore assente, vuoto o non riconosciuto (DB modificato a mano, versione
    futura dell'app che ha salvato una modalità che questa non conosce) ricade
    sul default invece di propagare una stringa che `DnDApp` non saprebbe
    risolvere.
    """
    raw = get_setting(THEME_MODE_KEY, "").strip().lower()
    if raw in THEME_PREFERENCES:
        return raw  # type: ignore[return-value]
    if raw:
        logger.warning(
            f"Preferenza di tema non riconosciuta nel DB: {raw!r} — "
            f"uso il default {DEFAULT_THEME_PREFERENCE!r}."
        )
    return DEFAULT_THEME_PREFERENCE


def set_theme_preference(preference: str) -> bool:
    """Salva la preferenza di tema. Rifiuta i valori fuori dai tre ammessi."""
    if preference not in THEME_PREFERENCES:
        logger.error(
            f"Preferenza di tema non valida: {preference!r} "
            f"(ammessi: {', '.join(THEME_PREFERENCES)})."
        )
        return False
    return set_setting(THEME_MODE_KEY, preference)


def next_theme_preference(current: str) -> ThemePreference:
    """
    Prossimo valore del ciclo Chiaro → Scuro → Sistema → Chiaro.

    Un valore corrente non riconosciuto riparte dal primo della lista, così il
    pulsante resta utilizzabile anche partendo da uno stato sporco.
    """
    try:
        idx = THEME_PREFERENCES.index(current)  # type: ignore[arg-type]
    except ValueError:
        return THEME_PREFERENCES[0]
    return THEME_PREFERENCES[(idx + 1) % len(THEME_PREFERENCES)]
