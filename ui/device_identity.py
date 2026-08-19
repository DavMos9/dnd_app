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

**`ft.SharedPreferences` è CONFERMATO rotto in web mode — non tentarlo mai.**
Errore riscontrato su un vero deploy web: `Unknown control:
SharedPreferences`. Stesso identico bug già documentato per `ft.FilePicker`
in `dnd_app/docs/regole_flet_api.md` (controlli `Service` non riconosciuti
dal client Flutter in web mode dalla 0.80.1 in poi, bug upstream
flet-dev/flet#6040/#6250/#6251) — la particolarità è che l'errore arriva dal
lato client via websocket DOPO che il codice Python ha già "avuto successo"
nel registrare il controllo: un `try/except` sincrono in Python non lo
intercetta mai, esattamente come per `FilePicker`. Il fix è lo stesso già in
uso nel progetto: **non creare/registrare mai `ft.SharedPreferences` quando
`page.web` è `True`** — `resolve_device_id()` va dritto al ripiego di
sessione per il web, senza nemmeno provare (vedi `_ensure_file_picker()` in
`ui/views/home_view.py` per lo stesso pattern già collaudato).

**Il ripiego di sessione** (ora l'UNICO percorso web, non più un fallback su
un tentativo fallito): l'id viene generato una volta e tenuto come attributo
sull'oggetto `page` — che in Flet vive per l'intera durata di quella
specifica connessione browser (stesso principio per cui il polling di
`home_view.py` sincronizza sessioni web diverse: ogni scheda del browser è
una sessione server-side a sé). **Si perde a un refresh della pagina**: in
web mode un giocatore che ricarica la pagina risulta un "nuovo dispositivo"
agli occhi di un mondo condiviso — limite noto e accettato per questo passo,
da tenere presente se il Multiplayer viene usato in web mode (il caso d'uso
primario resta desktop/mobile via LAN, dove `app_settings` è stabile). Il
nome visualizzato del dispositivo viene comunque chiesto al momento di
creare o unirsi a un mondo (`display_name` in `world_repo.create_world()`/
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

#: Attributo tenuto direttamente su `page` — identità di sola sessione,
#: UNICO percorso in web mode (`ft.SharedPreferences` confermato rotto,
#: vedi il docstring del modulo: non va più nemmeno tentato).
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
    """Identità di sola sessione: un id generato una sola volta per questa
    connessione browser, tenuto in memoria su `page` (mai nel DB — sarebbe
    condiviso da tutte le schede, vanificando lo scopo). UNICO percorso in
    web mode (vedi il docstring del modulo)."""
    existing = getattr(page, _SESSION_FALLBACK_ATTR, None)
    if isinstance(existing, str) and existing:
        return existing
    new_id = str(uuid.uuid4())
    setattr(page, _SESSION_FALLBACK_ATTR, new_id)
    logger.info(
        "device_identity: identità di sola sessione (%s) per questa scheda "
        "web — si perderà al refresh del browser (SharedPreferences non "
        "utilizzabile in web mode, confermato: mai tentarlo).", new_id,
    )
    return new_id


async def resolve_device_id(page: ft.Page) -> str:
    """
    Punto d'ingresso unico: risolve l'identità di QUESTO dispositivo/browser.

    Resta `async def` (anche se il web non fa più alcuna chiamata asincrona
    reale, ora che `SharedPreferences` non viene più tentato) per offrire
    un'unica interfaccia al chiamante — che continua a usare
    `page.run_task(resolve_device_id(page))`, nessuna modifica richiesta nei
    chiamanti esistenti (`home_view.py`, `ui/views/world/world_view.py`).
    """
    if not page.web:
        return _get_or_create_desktop_device_id()
    return _get_session_fallback_device_id(page)
