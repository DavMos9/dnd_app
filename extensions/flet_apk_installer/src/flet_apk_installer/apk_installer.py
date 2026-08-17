"""
Controllo Flet "ApkInstaller" — consegna un APK all'installer di pacchetti di
sistema su Android.

Perché esiste (contesto per chi legge questo file in futuro)
-----------------------------------------------------------
Davide ha chiesto (2026-08-17) "l'upgrade automatico dell'app con la barra del
download e la scritta aggiornamento completato, senza dover eliminare e
reinstallare l'app ogni volta". Il download e la barra sono puro Python
(``core/update_downloader.py``); la parte che NON si può fare in Python è l'ultimo
passo: aprire la finestra di sistema "Vuoi installare questa applicazione?".

**Android non può installare in silenzio.** È il modello di sicurezza del sistema
operativo, non un limite di questo progetto: anche nella migliore implementazione
possibile l'utente deve toccare "Installa" nella finestra di sistema. Questo
controllo fa arrivare fino a quella finestra, niente di più — ed è già tutto ciò
che serve, perché il vero problema (dover DISINSTALLARE prima) era causato dalla
firma dell'APK, risolta a parte con la chiave di rilascio permanente in CI.

Tre ostacoli, e come sono risolti:

1. **Permesso ``REQUEST_INSTALL_PACKAGES``** — dichiarato in ``pyproject.toml``
   del progetto principale (``[tool.flet.android.permission]``), letto da
   flet_cli. Non serve nulla qui.
2. **``FileProvider``** — da Android 7 passare un ``file://`` a un'altra app
   solleva ``FileUriExposedException``: serve un URI ``content://``, e quindi un
   ``<provider>`` nel manifest PIÙ una risorsa XML ``res/xml/filepaths.xml``.
   Nessuna chiave di ``pyproject.toml`` letta da flet_cli permette di aggiungere
   una risorsa Android arbitraria (verificate tutte nel sorgente installato di
   flet_cli 0.86.5). **Risolto appoggiandosi a ``open_filex``**, che porta con sé
   il proprio ``AndroidManifest.xml`` con un FileProvider e il proprio
   ``filepaths.xml``: il manifest merger di Gradle li unisce ai nostri. Così non
   serve scrivere una riga di Kotlin — che è ciò che rende questa estensione
   molto meno rischiosa delle due precedenti.
3. **Lanciare l'intent** — ``ft.FilePicker``/``ft.UrlLauncher`` sono controlli
   "Service", confermati rotti in questo progetto; la proprietà ``url=`` dei
   bottoni funziona ma è client-side e non può portare un ``ACTION_VIEW`` su un
   file locale. Risolto da ``OpenFilex.open()`` con il MIME type degli APK.

⚠️ NON VERIFICABILE IN QUESTO SANDBOX: nessun toolchain Flutter/Dart (stessa
limitazione di ``flet_image_picker``/``flet_file_picker`` — vedi il README di
questa cartella per l'elenco preciso di cosa resta da verificare su un
dispositivo reale). Il lato Python è verificato solo per importazione e
costruzione contro ``flet==0.86.5``.
"""

from __future__ import annotations

import flet as ft

__all__ = ["ApkInstaller"]

#: MIME type degli APK. Deve essere esatto: con un MIME generico
#: (``application/octet-stream``) Android aprirebbe un selettore di app invece
#: dell'installer di pacchetti.
APK_MIME_TYPE = "application/vnd.android.package-archive"


@ft.control("ApkInstaller")
class ApkInstaller(ft.Service):
    """
    Passa un file APK all'installer di pacchetti di sistema.

    Stesso pattern degli altri due controlli Service su misura di questo
    progetto (``ImagePicker``, ``FilePicker``): nessuna superficie visiva, solo
    metodi invocabili.
    """

    async def install(self, apk_path: str) -> str:
        """
        Apre la finestra di installazione di sistema per ``apk_path``.

        ``async`` perché in Flet 0.86.5 ``_invoke_method`` è l'UNICO ponte verso
        il lato Dart e restituisce una coroutine (verificato nel sorgente
        installato, ``flet/controls/base_control.py:431``: non esiste una
        variante "spara e dimentica").

        Restituisce il messaggio di esito di ``open_filex`` (``"done"`` quando
        l'installer si è aperto). Attenzione: appena l'utente conferma
        l'installazione, Android uccide questo processo per sostituire l'app —
        quindi il valore di ritorno dice solo se la FINESTRA si è aperta, mai se
        l'installazione è riuscita. L'esito vero si scopre al riavvio
        successivo, dal segnalibro scritto in ``app_settings``
        (``core/update_state.py``).
        """
        result = await self._invoke_method("install", {"apk_path": apk_path})
        return str(result) if result is not None else ""

    async def can_install(self) -> bool:
        """
        ``True`` su Android, ``False`` altrove.

        ⚠️ NON interroga davvero ``canRequestPackageInstalls()``: quel metodo non
        è esposto da alcun plugin Flutter pubblicato, e chiamarlo richiederebbe il
        codice Kotlin che questa estensione evita di proposito (vedi il docstring
        del modulo). Il metodo esiste per non dover cambiare l'interfaccia se un
        giorno servisse distinguere davvero i due casi.

        Non serve comunque a decidere se chiamare ``install()``: quando il
        permesso manca, Android mostra da sé la finestra "per la tua sicurezza…"
        con la scorciatoia alle impostazioni — un tocco in più solo la prima
        volta.
        """
        return bool(await self._invoke_method("can_install", {}))

    async def download_dir(self) -> str | None:
        """
        Cartella in cui il FileProvider di ``open_filex`` è in grado di esporre i
        file (``getExternalFilesDir(null)``).

        Esposta perché è **il punto più probabile di rottura** dell'intera
        estensione: se i ``provider_paths`` di ``open_filex`` non coprono
        l'albero in cui abbiamo scritto l'APK, l'apertura falliscce con un errore
        di permessi. Avendo il percorso dall'estensione stessa, il rimedio è
        cambiare dove si scarica invece di riprogettare — e cambia una riga.
        """
        result = await self._invoke_method("download_dir", {})
        return str(result) if result else None
