"""
Identità del dispositivo (§4 di `dnd_app/docs/multiplayer_design.md`) —
un `device_id` (UUID) stabile che identifica "questo dispositivo/browser" nei
mondi condivisi.

**Perché non è un semplice `get_setting()`**: `app_settings` (vedi
`settings_repo.py`) è una tabella per l'intero DB/processo. Su desktop e
mobile un'installazione = un dispositivo fisico, quindi va benissimo. Ma in
modalità web (deploy Docker) tutti i browser che aprono lo stesso URL
condividono lo stesso processo e lo stesso DB: con `app_settings` ogni
browser risulterebbe "lo stesso dispositivo", rendendo impossibile
distinguere master e giocatori diversi collegati alla stessa istanza web.
Decisione presa con Davide il 2026-08-05.

**Il tentativo web e il suo rischio dichiarato**: Flet 0.85.3 non ha più
`page.client_storage` come attributo diretto — è stato sostituito da
`ft.SharedPreferences`, un controllo `Service`. `dnd_app/docs/
regole_flet_api.md` documenta che i controlli `Service` (es. `ft.FilePicker`)
sono strutturalmente rotti in web mode dalla 0.80.1 in poi (bug upstream
confermato, flet-dev/flet#6040/#6250/#6251): è quindi plausibile che anche
`SharedPreferences` lo sia, ma non è stato ancora verificato empiricamente
in questo progetto (serve un vero deploy web, che Davide potrà controllare
aprendo due schede/browser diversi). Per questo `resolve_device_id()` avvolge
il tentativo in un try/except e ricade su un'identità di sola sessione se
`SharedPreferences` non risponde — mai un'eccezione che blocchi l'app.

**Il ripiego di sessione**: se `SharedPreferences` fallisce, l'id viene
generato una volta e tenuto come attributo sull'oggetto `page` — che in
Flet vive per l'intera durata di quella specifica connessione browser
(stesso principio per cui il polling di `home_view.py` sincronizza sessioni
web diverse: ogni scheda del browser è una sessione server-side a sé). Si
perde a un refresh della pagina, ma non richiede un dialogo dedicato: il nome
visualizzato del dispositivo viene comunque chiesto al momento di creare o
unirsi a un mondo (`display_name` in `world_repo.create_world()`/
`join_world_by_code()`), quindi non serve un secondo prompt "Chi sei?" solo
per l'identità tecnica.
"""

from __future__ import annotations

import logging
import uuid

import flet as ft

from data.repositories import settings_repo

logger = logging.getLogger(__name__)

#: Chiave in app_settings — solo desktop/mobile (un'installazione = un dispositivo).
DEVICE_ID_SETTINGS_KEY = "device_id"

#: Chiave in SharedPreferences — solo web, un tentativo per scheda/browser.
_WEB_SHARED_PREFS_KEY = "dnd_device_id"

#: Attributo tenuto direttamente su `page` come ripiego di sessione se
#: SharedPreferences non è disponibile in web mode.
_SESSION_FALLBACK_ATTR = "_dnd_device_id_session_fallback"


def _get_or_create_desktop_device_id() -> str:
    """Percorso desktop/mobile: `app_settings`, un'unica identità stabile
    per installazione, esattamente come `theme_mode` (vedi settings_repo.py)."""
    existing = settings_repo.get_setting(DEVICE_ID_SETTINGS_KEY, "")
    if existing:
        return existing
    new_id = str(uuid.uuid4())
    settings_repo.set_setting(DEVICE_ID_SETTINGS_KEY, new_id)
    return new_id


def _get_session_fallback_device_id(page: ft.Page) -> str:
    """Ripiego di sessione: un id generato una sola volta per questa
    connessione browser, tenuto in memoria su `page` (mai nel DB — sarebbe
    condiviso da tutte le schede, vanificando lo scopo)."""
    existing = getattr(page, _SESSION_FALLBACK_ATTR, None)
    if isinstance(existing, str) and existing:
        return existing
    new_id = str(uuid.uuid4())
    setattr(page, _SESSION_FALLBACK_ATTR, new_id)
    logger.info(
        "device_identity: SharedPreferences non disponibile, uso identità "
        "di sola sessione (%s) — si perderà al refresh del browser.", new_id,
    )
    return new_id


async def _get_or_create_web_device_id(page: ft.Page) -> str | None:
    """
    Tentativo di persistenza reale in web mode via `ft.SharedPreferences`.

    Ritorna `None` (mai solleva) se il servizio non risponde correttamente —
    il chiamante ricade allora su `_get_session_fallback_device_id()`.
    Stessa convenzione di registrazione già usata in questo progetto per
    `ft.FilePicker` (`page.overlay.append(...)` + `page.update()`, vedi
    `home_view.py::_ensure_file_picker`), per coerenza anche se il controllo
    dovesse rivelarsi altrettanto rotto in web mode.
    """
    try:
        prefs = ft.SharedPreferences()
        page.overlay.append(prefs)
        try:
            page.update()
        except RuntimeError:
            pass  # pagina non ancora montata: non impedisce l'uso del servizio

        existing = await prefs.get(_WEB_SHARED_PREFS_KEY)
        if isinstance(existing, str) and existing:
            return existing

        new_id = str(uuid.uuid4())
        ok = await prefs.set(_WEB_SHARED_PREFS_KEY, new_id)
        if not ok:
            logger.warning("device_identity: SharedPreferences.set ha risposto False.")
            return None
        return new_id
    except Exception as e:
        logger.warning("device_identity: SharedPreferences non utilizzabile (%s).", e)
        return None


async def resolve_device_id(page: ft.Page) -> str:
    """
    Punto d'ingresso unico: risolve l'identità di QUESTO dispositivo/browser.

    Va chiamato da un contesto async (es. `page.run_task(coroutine)`, stessa
    convenzione già in uso in questo progetto per `ft.FilePicker.pick_files`/
    `save_file` — vedi `home_view.py`), perché il percorso web è
    intrinsecamente asincrono (`await prefs.get/set`). Il percorso
    desktop/mobile è sincrono ma la funzione resta `async def` per offrire
    un'unica interfaccia al chiamante, che non deve sapere quale dei due rami
    è stato preso.
    """
    if not page.web:
        return _get_or_create_desktop_device_id()

    device_id = await _get_or_create_web_device_id(page)
    if device_id:
        return device_id
    return _get_session_fallback_device_id(page)
