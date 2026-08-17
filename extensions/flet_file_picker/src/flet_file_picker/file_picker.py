"""
Controllo Flet "FilePicker" — selettore file generico nativo per Android/iOS.

Perché esiste (contesto per chi legge questo file in futuro)
--------------------------------------------------------------
Import personaggio/mondo su mobile (``.dndchar``/``.dndworld``) passa oggi
da ``ui/mobile_webview_picker.py`` (``ft.WebView`` + ``<input type=file>``),
lo stesso bypass costruito per la selezione immagini prima che
``flet_image_picker`` lo sostituisse. Quel bypass è però **confermato NON
funzionante su Android reale** (segnalato da Davide anche per import
personaggio/mondo, non solo foto): ``webview_flutter`` non implementa
``WebChromeClient.onShowFileChooser`` di default, quindi il tap su "Scegli
file" non apre alcun selettore di sistema — stessa identica diagnosi già
scritta in ``ui/native_image_picker.py``/``dnd_app/docs/changelog_storico.md``
per il caso foto, mai stata risolta per il caso file generico perché
``flet_image_picker`` avvolge il plugin Flutter ``image_picker`` (SOLO
immagini da galleria — nessuna API per file arbitrari).

``ft.FilePicker`` (SDK ufficiale Flet) resta scartato per lo stesso motivo
già documentato per le foto: nessuna Activity nativa Android viene mai
avviata su questa build (``TimeoutException: Timeout waiting for invoke
method listener``, log adb logcat reale di Davide).

Questo controllo applica **la stessa tecnica già verificata funzionante per
le foto** (Davide, 2026-08-06: "il picker immagini nativo funziona") a un
selettore di file generico: un'estensione Flet "Service" scritta su misura,
identico pattern di ``ImagePicker`` (``flet_image_picker``), che avvolge
stavolta il plugin Flutter ufficiale ``file_picker`` (pub.dev, publisher
``miguelpruivo``) invece di ``image_picker``.

⚠️ Nota di onestà tecnica: quando fu scelto ``image_picker`` per le foto, il
changelog di quella sessione osservava che ``file_picker`` ha "una storia di
affidabilità" più incerta di ``image_picker`` nell'ecosistema Flutter — ma
resta comunque il pacchetto standard e più maturo per la selezione di file
arbitrari (nessun pacchetto "immagini" può leggere un ``.dndchar``/
``.dndworld``), e la causa di rottura di ``ft.FilePicker``/WebView qui è
comunque a monte nel bridge Flet, non nel plugin sottostante — la stessa
logica che ha reso ``image_picker`` la scelta giusta per le foto si applica
qui per i file.

⚠️ NON VERIFICABILE IN QUESTO SANDBOX: nessun toolchain Flutter/Dart
disponibile (stessa limitazione di ``flet_image_picker`` — vedi il README di
questa cartella). Il lato Python è verificato solo per importazione/
costruzione contro ``flet==0.86.5``.
"""

from __future__ import annotations

from typing import Optional

import flet as ft

__all__ = ["FilePicker"]


@ft.control("FilePicker")
class FilePicker(ft.Service):
    """
    Selettore file generico nativo (file manager di sistema) per Android e
    iOS, tramite il plugin Flutter ``file_picker``.

    Va costruito dentro un handler async schedulato con ``page.run_task``
    (stesso vincolo di ``flet_image_picker.ImagePicker`` — il controllo si
    auto-registra nel ``ServiceRegistry`` della pagina al momento della
    costruzione, niente ``page.overlay.append(...)`` esplicito).
    """

    async def pick_file(
        self,
        allowed_extensions: Optional[list[str]] = None,
    ) -> Optional[dict]:
        """
        Apre il selettore file nativo di sistema e attende la scelta
        dell'utente.

        Args:
            allowed_extensions: estensioni ammesse SENZA il punto (es.
                ``["dndchar", "json"]``). ``None`` = qualunque file.

        Returns:
            ``{"name": <nome file>, "bytes": <contenuto>}`` se l'utente ha
            scelto un file, ``None`` se ha annullato la selezione.
        """
        return await self._invoke_method(
            "pick_file",
            {"allowed_extensions": allowed_extensions},
        )
