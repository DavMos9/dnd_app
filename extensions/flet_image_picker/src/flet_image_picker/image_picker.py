"""
Controllo Flet "ImagePicker" — selettore immagini nativo per Android/iOS.

Perché esiste (contesto per chi legge questo file in futuro)
--------------------------------------------------------------
``ft.FilePicker`` (SDK ufficiale Flet) è confermato NON funzionante sulle
build Android reali di questo progetto: la Activity nativa non viene mai
avviata (``TimeoutException: Timeout waiting for invoke method listener``
in un log adb logcat reale di Davide, dopo aver escluso anche un bug più
superficiale di ``await`` mancante). Il fallback tentato subito dopo,
``ft.WebView`` con un ``<input type="file">`` in una pagina HTML locale, è
anch'esso confermato non funzionante: ``webview_flutter`` (il pacchetto
Flutter dietro ``flet_webview``) non implementa di default
``WebChromeClient.onShowFileChooser`` su Android, quindi il tap su "Scegli
file" non apre alcun selettore nativo — verificato sia leggendo la
documentazione/issue tracker di ``webview_flutter`` sia per introspezione
diretta (``inspect.signature``) sul pacchetto ``flet_webview==0.86.5``
installato: non espone alcun hook per abilitarlo.

Dettaglio completo di entrambe le diagnosi in
``dnd_app/docs/changelog_storico.md`` e ``dnd_app/docs/regole_flet_api.md``.

Questo controllo è una estensione Flet "Service" scritta su misura, che
avvolge il plugin Flutter ufficiale ``image_picker`` (pub.dev, publisher
verificato flutter.dev, versione corrente 1.2.3 verificata su pub.dev il
2026-08-06) seguendo lo STESSO pattern reale già usato in produzione da
``flet-camera`` (metodo ``take_picture``) e ``flet-audio-recorder`` (metodo
``start_recording``): un metodo Python ``async`` che chiama
``self._invoke_method(...)`` e riceve il risultato attraverso lo stesso
canale del protocollo di controllo standard (MsgPack) — non serve il
meccanismo ``DataChannel`` per payload grandi, perché ``flet-camera`` fa
esattamente questo con foto a piena risoluzione
(``camera.dart::take_picture -> file.readAsBytes()``, verificato leggendo il
sorgente Dart reale del pacchetto ufficiale).

⚠️ NON VERIFICABILE IN QUESTO SANDBOX: nessun toolchain Flutter/Dart è
disponibile qui per compilare o eseguire il lato nativo (verificato:
``which flutter dart`` non trova nulla). Il lato Python di questo file è
verificato per importazione/costruzione contro ``flet==0.86.5`` (la stessa
versione già pinnata in ``pyproject.toml`` dell'app), inclusi
``ft.control``/``ft.Service``/``BaseControl._invoke_method`` — confermati
esistere con questa identica firma nel pacchetto installato. Il metodo
``pick_image()`` non può però essere invocato davvero, né il lato Dart
compilato/testato, senza che Davide costruisca l'app su un dispositivo
reale.

Scope dichiarato v1: SOLO selezione da galleria (nessuna cattura fotocamera
— eviterebbe di dover dichiarare anche il permesso Android/iOS "camera" nel
``pyproject.toml`` dell'app, non richiesto dagli usi attuali: foto profilo
in ``profilo_tab.py``, immagine mappa in ``maps_view.py``). Il permesso
cross-platform ``photo_library`` già dichiarato in ``pyproject.toml``
dell'app (aggiunto 2026-08-05) copre sia ``NSPhotoLibraryUsageDescription``
su iOS sia (indirettamente) il caso Android: il plugin ``image_picker`` su
Android 13+ usa l'Android Photo Picker di sistema, che secondo la
documentazione ufficiale del plugin non richiede ALCUN permesso runtime
("No configuration required - the plugin should work out of the box").
"""

from __future__ import annotations

from typing import Optional

import flet as ft

__all__ = ["ImagePicker"]


@ft.control("ImagePicker")
class ImagePicker(ft.Service):
    """
    Selettore immagini nativo (galleria di sistema) per Android e iOS.

    Va aggiunto a ``page.services`` (stesso pattern di utilizzo di
    ``ft.AudioRecorder``/``ft.Camera`` nell'SDK ufficiale Flet) prima di
    chiamare :meth:`pick_image`. Su piattaforme diverse da Android/iOS/web
    questo controllo non ha un'implementazione Dart corrispondente in questa
    estensione (v1, scope volutamente minimo) — il codice chiamante deve
    continuare a usare il percorso desktop esistente
    (``ui/image_library.py``), non questo controllo.
    """

    async def pick_image(
        self,
        image_quality: Optional[int] = None,
        max_width: Optional[float] = None,
        max_height: Optional[float] = None,
    ) -> Optional[bytes]:
        """
        Apre il selettore immagini nativo di sistema (galleria foto) e
        attende la scelta dell'utente.

        Args:
            image_quality: compressione JPEG da 0 a 100 applicata da
                ``image_picker`` prima della restituzione. ``None`` = qualità
                originale (nessuna ricompressione).
            max_width: larghezza massima in pixel a cui ridimensionare
                l'immagine mantenendo le proporzioni. ``None`` = nessun
                limite.
            max_height: altezza massima in pixel. ``None`` = nessun limite.

        Returns:
            I byte dell'immagine scelta (formato originale, tipicamente
            JPEG o PNG), oppure ``None`` se l'utente ha annullato la
            selezione senza scegliere nulla.
        """
        return await self._invoke_method(
            "pick_image",
            {
                "image_quality": image_quality,
                "max_width": max_width,
                "max_height": max_height,
            },
        )
