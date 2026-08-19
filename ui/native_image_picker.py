"""
Wrapper Python per il controllo Flet nativo `ImagePicker`
(`dnd_app/extensions/flet_image_picker/`) — selezione immagine da galleria
su Android/iOS tramite il plugin Flutter ufficiale `image_picker`.

**Perché esiste**: sia `ft.FilePicker` sia il fallback
`ui/mobile_webview_picker.py` (WebView + `<input type=file>`) sono
confermati non funzionanti su build Android reali — diagnosi complete in
`dnd_app/docs/changelog_storico.md` e `dnd_app/docs/regole_flet_api.md`,
sezione FILE PICKER. Questa è la terza strada: un'estensione nativa
scritta su misura per questo progetto (non parte dell'SDK ufficiale Flet).

**Import ritardato dentro `pick_image_native()`**, stesso motivo di
`ui/mobile_webview_picker.py::pick_file_via_webview()`: il pacchetto
`flet_image_picker` è pensato per essere installato solo sulle build
Android/iOS (dipendenza path-based dichiarata in `pyproject.toml`), un
import eager in cima a questo modulo lo renderebbe un requisito anche per
l'avvio desktop — esattamente il bug già riprodotto una volta con
`flet_webview` (vedi commento equivalente in `mobile_webview_picker.py`).

**Come si registra il controllo**: NESSUNA chiamata esplicita di tipo
`page.overlay.append(...)`/`page.services.append(...)` — verificato che in
Flet 0.86.5 questo pattern non esiste più (`Page` non ha più `overlay`,
`Page._services` è un `ServiceRegistry` interno). Il vero meccanismo,
verificato leggendo il sorgente installato
(`flet/controls/services/service.py`, `flet/controls/base_control.py`) e
confermato dall'esempio ufficiale runnable in
https://flet.dev/docs/services/audiorecorder (`recorder =
far.AudioRecorder(...)`, mai aggiunto esplicitamente da nessuna parte): un
`Service` si AUTO-registra nel `ServiceRegistry` della pagina dentro il
proprio `init()`, chiamato automaticamente da `BaseControl.__post_init__`
al momento stesso della costruzione — a patto che `context.page` (una
contextvar, non un parametro esplicito) sia già impostata, cosa sempre
vera quando il controllo viene costruito dentro un handler async
scatenato da un evento della pagina (come `_pick_photo_mobile()` in
`profilo_tab.py`, invocato via `page.run_task(...)`). Basta quindi
costruire `ImagePicker()` e chiamare `pick_image()` su di essa.

⚠️ NON VERIFICATO end-to-end: nessun toolchain Flutter/Dart in questo
sandbox per compilare l'estensione (vedi
`dnd_app/extensions/flet_image_picker/README.md`). `pick_image_native()`
solleva `ImagePickerUnavailable` se il pacchetto non è importabile o se
l'invocazione fallisce per qualunque motivo — i chiamanti (`profilo_tab.py`,
`maps_view.py`) DEVONO intercettarla e ricadere su
`pick_file_via_webview()` (`ui/mobile_webview_picker.py`), mai assumere che
questo percorso funzioni al primo colpo su un dispositivo reale non ancora
testato end-to-end.
"""

from __future__ import annotations

import logging
from typing import Optional

import flet as ft

logger = logging.getLogger(__name__)


class ImagePickerUnavailable(Exception):
    """
    Sollevata quando il controllo nativo `ImagePicker` non è disponibile
    (pacchetto `flet_image_picker` non installato in questa build, oppure
    un errore qualunque durante l'invocazione — inclusa una build Android
    dove l'estensione non è stata ancora compilata dentro l'APK). Il
    chiamante deve intercettarla e ricadere sul fallback WebView, non
    trattarla come "utente ha annullato la selezione".
    """


async def pick_image_native(
    page: ft.Page,
    *,
    image_quality: Optional[int] = None,
    max_width: Optional[float] = None,
    max_height: Optional[float] = None,
) -> Optional[bytes]:
    """
    Apre il selettore immagini nativo di sistema (galleria) tramite
    l'estensione Flet su misura `flet_image_picker`.

    Args:
        page: la pagina corrente (non usata direttamente per registrare il
            controllo — vedi il docstring di modulo sul meccanismo di
            auto-registrazione — ma richiesta per uniformità con
            `pick_file_via_webview()` e per eventuali usi futuri, es.
            `page.platform`).
        image_quality: vedi `ImagePicker.pick_image`.
        max_width: vedi `ImagePicker.pick_image`.
        max_height: vedi `ImagePicker.pick_image`.

    Returns:
        I bytes dell'immagine scelta, o `None` se l'utente ha annullato la
        selezione.

    Raises:
        ImagePickerUnavailable: se il pacchetto non è installato in questa
            build o se l'invocazione fallisce per qualunque motivo. Il
            chiamante deve intercettarla e ricadere su
            `pick_file_via_webview()`.
    """
    try:
        from flet_image_picker import ImagePicker
    except ImportError as ex:
        raise ImagePickerUnavailable(
            f"pacchetto flet_image_picker non installato in questa build: {ex}"
        ) from ex

    try:
        picker = ImagePicker()
        return await picker.pick_image(
            image_quality=image_quality, max_width=max_width, max_height=max_height,
        )
    except Exception as ex:
        raise ImagePickerUnavailable(
            f"invocazione pick_image() fallita: {ex}"
        ) from ex
