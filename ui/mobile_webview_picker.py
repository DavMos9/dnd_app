"""
Selezione file su Android/iOS tramite WebView locale — bypassa
`ft.FilePicker`, confermato non funzionante su build Android reali.

**Perché esiste**: su Android, la chiamata a `ft.FilePicker.pick_files()`
arriva correttamente al bridge Dart ma va in `TimeoutException: Timeout
waiting for invoke method listener` — **nessuna Activity nativa Android
viene mai avviata** (nessun picker di sistema, nessun dialogo di permesso).
Il controllo `FilePicker` di Flet non è utilizzabile su questa build, punto
— non è un problema risolvibile cambiando il nostro codice attorno a
`ft.FilePicker` (vedi `dnd_app/docs/regole_flet_api.md`, sezione FILE
PICKER).

**Come funziona questo modulo, invece**: usa `ft.WebView` (estensione
ufficiale `flet-webview`, mantenuta allo stesso ritmo di release del
pacchetto `flet` core, meccanismo di rendering completamente diverso da
`FilePicker` — non condivide lo stesso bug) per mostrare una paginetta HTML
**locale** (mai caricata da rete: costruita in Python, passata alla
WebView come `data:` URI, MAI un URL remoto) con un elemento
`<input type="file">` — lo stesso elemento standard che ogni sito web usa
per allegare un file. Toccarlo apre il selettore nativo di Android (lo
stesso di qualunque altra app: il file-chooser di WebView è uno dei
meccanismi più maturi e collaudati dell'intero ecosistema Android, usato da
milioni di app con una webview integrata — un pezzo di infrastruttura
completamente diverso, e molto più testato, di `ft.FilePicker`).

Il file scelto non lascia mai il dispositivo: la pagina lo legge in memoria
con `FileReader.readAsDataURL()` (API JavaScript standard, nessuna rete
coinvolta) e lo restituisce a Python come stringa base64, tramite
`console.log()` — non un hack: `WebView.on_console_message` è un evento di
prima classe di `flet-webview`, verificato leggendo il sorgente del
pacchetto installato prima di scegliere questo meccanismo (l'alternativa
più comune, un canale di messaggi JS→Python dedicato, non esiste in questa
versione dell'estensione).

Nessuna funzionalità di SALVATAGGIO file (`save_file`) è coperta qui —
resta un problema a sé (un download via WebView richiede intercettare un
meccanismo diverso, mai verificato). Copre solo la SELEZIONE di un file
già esistente sul dispositivo: foto profilo, immagine mappa, import
personaggio.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Optional

import flet as ft

from ui import design
from ui.widgets import wrap_dialog_actions

logger = logging.getLogger(__name__)

# Prefissi usati per distinguere, dentro on_console_message, i messaggi che
# arrivano dalla nostra pagina da qualunque altro log JS della WebView
# (errori del motore di rendering, warning, ecc. — tutti passano dallo
# stesso evento).
_RESULT_PREFIX = "FLET_PICKER_RESULT:"
_ERROR_PREFIX = "FLET_PICKER_ERROR:"

# Pagina minimale, interamente locale (nessuna richiesta di rete: niente
# <script src>/<link> esterni, tutto inline). `{accept}` è l'unico valore
# interpolato, sempre una costante scelta da questo stesso modulo (mai
# testo proveniente dall'utente) — nessun rischio di injection nel
# contesto in cui è usato.
_PICKER_HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  html, body {{
    margin: 0; height: 100%;
    display: flex; align-items: center; justify-content: center;
    font-family: -apple-system, Roboto, sans-serif;
    background: #f2f2f2;
  }}
  button {{
    font-size: 17px; padding: 16px 32px; border-radius: 14px; border: none;
    background: #8B1E1E; color: white; box-shadow: 0 2px 6px rgba(0,0,0,0.2);
  }}
  button:active {{ opacity: 0.8; }}
</style>
</head>
<body>
  <input type="file" id="picker" accept="{accept}" style="display:none">
  <button type="button" onclick="document.getElementById('picker').click()">
    Scegli file
  </button>
  <script>
    document.getElementById('picker').addEventListener('change', function (ev) {{
      var file = ev.target.files && ev.target.files[0];
      if (!file) {{ return; }}
      var reader = new FileReader();
      reader.onload = function () {{
        try {{
          console.log({result_prefix!r} + JSON.stringify({{
            name: file.name,
            dataUrl: reader.result
          }}));
        }} catch (err) {{
          console.log({error_prefix!r} + String(err));
        }}
      }};
      reader.onerror = function () {{
        console.log({error_prefix!r} + (reader.error ? reader.error.message : 'lettura fallita'));
      }};
      reader.readAsDataURL(file);
    }});
  </script>
</body>
</html>
"""


async def pick_file_via_webview(
    page: ft.Page,
    *,
    accept: str = "*/*",
    title: str = "Seleziona un file",
    dialog_width: int = 380,
    dialog_height: int = 480,
) -> Optional[tuple[str, str]]:
    """
    Mostra un dialog con una WebView locale per scegliere un file sul
    dispositivo (Android/iOS). Attende la scelta dell'utente.

    Args:
        page: la pagina corrente.
        accept: valore dell'attributo HTML `accept` dell'`<input type=file>`
            (es. `"image/*"` per sole immagini, `".dndchar,.json"` per file
            di export personaggio). Passare sempre una costante nota, mai
            input dell'utente (interpolato senza escaping nella pagina).
        title: titolo mostrato in cima al dialog.

    Returns:
        Una tupla `(nome_file, contenuto_base64)` se l'utente ha scelto un
        file, `None` se ha annullato o in caso di errore. `contenuto_base64`
        è già ripulito del prefisso `data:<mime>;base64,` del data URI.
    """
    # Import RITARDATO qui dentro, apposta: `flet_webview` è un pacchetto che
    # serve SOLO su Android/iOS (l'unica strada che chiama questa
    # funzione, vedi profilo_tab.py/maps_view.py/home_view.py — tutti
    # instradano desktop/web verso tutt'altro codice). Un `from
    # flet_webview import ...` in cima al modulo lo rende invece un
    # requisito per QUALUNQUE avvio dell'app, qualunque piattaforma —
    # esattamente il bug riprodotto: "No module named 'flet_webview'"
    # avviando l'app su desktop, dove il pacchetto non è (né deve essere)
    # installato per forza. Ritardando l'import al momento in cui questa
    # funzione viene davvero chiamata, desktop e web non toccano mai
    # questa riga e non hanno bisogno del pacchetto.
    from flet_webview import WebView, WebViewConsoleMessageEvent

    loop = asyncio.get_event_loop()
    result_future: "asyncio.Future[Optional[tuple[str, str]]]" = loop.create_future()

    def _finish(value: Optional[tuple[str, str]]) -> None:
        if not result_future.done():
            result_future.set_result(value)

    def _on_console_message(e: WebViewConsoleMessageEvent) -> None:
        msg = e.message or ""
        if msg.startswith(_RESULT_PREFIX):
            try:
                payload = json.loads(msg[len(_RESULT_PREFIX):])
                name = str(payload.get("name") or "file")
                data_url = str(payload.get("dataUrl") or "")
                # data_url = "data:<mime>;base64,<contenuto>" — ci interessa
                # solo la parte dopo la virgola.
                _, _, b64_data = data_url.partition(",")
                if not b64_data:
                    logger.error("pick_file_via_webview: data URI senza contenuto base64")
                    _finish(None)
                    return
                _finish((name, b64_data))
            except Exception as exc:
                logger.error(f"pick_file_via_webview: payload JS malformato: {exc}")
                _finish(None)
        elif msg.startswith(_ERROR_PREFIX):
            logger.error(
                f"pick_file_via_webview: errore lato JS: {msg[len(_ERROR_PREFIX):]}"
            )
            _finish(None)
        # Qualunque altro messaggio in console (log innocui del motore di
        # rendering) viene ignorato: non riguarda il nostro protocollo.

    html = _PICKER_HTML_TEMPLATE.format(
        accept=accept, result_prefix=_RESULT_PREFIX, error_prefix=_ERROR_PREFIX,
    )
    # data: URI invece di WebView.load_html(): quest'ultimo è un metodo
    # async che richiede il controllo già montato sulla pagina (stesso
    # vincolo di ft.FilePicker.pick_files() — vedi BaseControl.page).
    # Passare l'HTML già pronto in `url`
    # evita del tutto la sequenza "monta, poi invoca", niente race di
    # timing da gestire.
    b64_html = base64.b64encode(html.encode("utf-8")).decode("ascii")
    data_uri = f"data:text/html;charset=utf-8;base64,{b64_html}"

    webview = WebView(url=data_uri, on_console_message=_on_console_message, expand=True)

    def _on_cancel(_: ft.Event) -> None:
        _finish(None)

    dlg = ft.AlertDialog(
        title=design.dialog_title(title, icon=ft.Icons.UPLOAD_FILE),
        content=ft.Container(width=dialog_width, height=dialog_height, content=webview),
        actions=wrap_dialog_actions([
            ft.TextButton("Annulla", on_click=_on_cancel),
        ]),
    )
    page.show_dialog(dlg)

    try:
        result = await result_future
    finally:
        try:
            page.pop_dialog()
        except Exception:
            pass

    return result
