"""
Wrapper Python per il controllo Flet nativo `FilePicker`
(`dnd_app/extensions/flet_file_picker/`) — selezione di un file generico su
Android/iOS tramite il plugin Flutter ufficiale `file_picker`.

**Perché esiste**: import personaggio (`.dndchar`) e import mondo
(`.dndworld`) su mobile passavano da `ui/mobile_webview_picker.py`
(`ft.WebView` + `<input type=file>`) — confermato NON funzionante su
Android reale anche per la selezione file generica (segnalato da Davide,
stessa diagnosi già nota per il caso foto: `webview_flutter` non implementa
`WebChromeClient.onShowFileChooser` di default). Questo modulo applica la
stessa tecnica già verificata funzionante per le foto
(`ui/native_image_picker.py`, estensione nativa su misura) al caso file
generico, avvolgendo stavolta `file_picker` invece di `image_picker` —
vedi `dnd_app/extensions/flet_file_picker/README.md` per il dettaglio
completo.

**Import ritardato dentro `pick_file_native()`**, stesso motivo di
`ui/native_image_picker.py::pick_image_native()`: il pacchetto
`flet_file_picker` è pensato per essere installato solo sulle build
Android/iOS (dipendenza path-based dichiarata in `pyproject.toml`), un
import eager in cima a questo modulo lo renderebbe un requisito anche per
l'avvio desktop.

⚠️ NON VERIFICATO end-to-end: nessun toolchain Flutter/Dart in questo
sandbox per compilare l'estensione. `pick_file_native()` solleva
`FilePickerUnavailable` se il pacchetto non è importabile o se
l'invocazione fallisce per qualunque motivo — i chiamanti
(`home_view.py::_on_mobile_import()`,
`world_view.py::_on_mobile_import_world()`) DEVONO intercettarla e ricadere
su `pick_file_via_webview()` (`ui/mobile_webview_picker.py`), mai assumere
che questo percorso funzioni al primo colpo su un dispositivo reale non
ancora testato da Davide.
"""

from __future__ import annotations

import logging
from typing import Optional

import flet as ft

logger = logging.getLogger(__name__)


class FilePickerUnavailable(Exception):
    """
    Sollevata quando il controllo nativo `FilePicker` non è disponibile
    (pacchetto `flet_file_picker` non installato in questa build, oppure un
    errore qualunque durante l'invocazione — inclusa una build Android dove
    l'estensione non è stata ancora compilata dentro l'APK). Il chiamante
    deve intercettarla e ricadere sul fallback WebView, non trattarla come
    "utente ha annullato la selezione".
    """


async def pick_file_native(
    page: ft.Page,
    *,
    allowed_extensions: Optional[list[str]] = None,
) -> Optional[tuple[str, bytes]]:
    """
    Apre il selettore file nativo di sistema (file manager) tramite
    l'estensione Flet su misura `flet_file_picker`.

    Args:
        page: la pagina corrente (non usata direttamente per registrare il
            controllo — stesso meccanismo di auto-registrazione di
            `pick_image_native()` — ma richiesta per uniformità e per
            eventuali usi futuri).
        allowed_extensions: estensioni ammesse senza il punto (es.
            `["dndchar", "json"]`). `None` = qualunque file.

    Returns:
        Una tupla `(nome_file, contenuto_bytes)` se l'utente ha scelto un
        file, `None` se ha annullato la selezione.

    Raises:
        FilePickerUnavailable: se il pacchetto non è installato in questa
            build o se l'invocazione fallisce per qualunque motivo. Il
            chiamante deve intercettarla e ricadere su
            `pick_file_via_webview()`.
    """
    try:
        from flet_file_picker import FilePicker
    except ImportError as ex:
        raise FilePickerUnavailable(
            f"pacchetto flet_file_picker non installato in questa build: {ex}"
        ) from ex

    try:
        picker = FilePicker()
        result = await picker.pick_file(allowed_extensions=allowed_extensions)
    except Exception as ex:
        raise FilePickerUnavailable(
            f"invocazione pick_file() fallita: {ex}"
        ) from ex

    if result is None:
        return None
    name = result.get("name")
    data = result.get("bytes")
    if not name or data is None:
        raise FilePickerUnavailable(
            f"risposta inattesa da FilePicker.pick_file(): {result!r}"
        )
    return str(name), bytes(data)
