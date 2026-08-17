"""
Wrapper Python per il controllo Flet nativo `ApkInstaller`
(`dnd_app/extensions/flet_apk_installer/`) — consegna un APK scaricato
all'installer di pacchetti di SISTEMA su Android.

**Perché serve un'estensione nativa.** Android non può MAI installare un'app in
silenzio: è il modello di sicurezza del sistema operativo, non un limite di
questo progetto. Il massimo possibile è passare al sistema l'APK e far comparire
la finestra "Vuoi installare questa applicazione?", dove l'utente tocca
"Installa". Per farlo servono tre cose, e due non si ottengono dal Python:

1. il permesso `REQUEST_INSTALL_PACKAGES` — questo sì, si dichiara in
   `pyproject.toml` (`[tool.flet.android.permission]`); ✅
2. un `FileProvider` che esponga il file come URI `content://` — da Android 7 un
   `file://` solleva `FileUriExposedException`. Un FileProvider richiede anche
   una risorsa XML (`res/xml/filepaths.xml`), e nessuna chiave di
   `pyproject.toml` letta da flet_cli permette di aggiungere una risorsa Android
   arbitraria (verificate tutte, sorgente installato di flet_cli 0.86.5); ❌
3. lanciare l'intent di installazione. `ft.FilePicker`/`ft.UrlLauncher` sono
   controlli "Service", confermati rotti in questo progetto; la proprietà `url=`
   dei bottoni funziona ma è client-side e non può portare un `ACTION_VIEW` su
   un file locale. ❌

L'estensione risolve (2) e (3) appoggiandosi al pacchetto Flutter `open_filex`,
che porta con sé il PROPRIO `AndroidManifest.xml` con un FileProvider e il
proprio `filepaths.xml`, uniti al nostro dal manifest merger di Gradle — così non
serve scrivere una riga di Kotlin.

⚠️ NON VERIFICATO end-to-end: nessun toolchain Flutter/Dart in questo sandbox.
`install_apk()` solleva `ApkInstallerUnavailable` se il pacchetto non è
importabile o se l'invocazione fallisce, e il chiamante
(`ui/update_dialogs.py::show_download_dialog`) DEVE intercettarla e dire
all'utente dove trovare il file scaricato — mai lasciare un pulsante che sembra
non fare nulla. Vedi `extensions/flet_apk_installer/README.md`.
"""

from __future__ import annotations

import logging

import flet as ft

logger = logging.getLogger(__name__)


class ApkInstallerUnavailable(Exception):
    """
    Sollevata quando il controllo nativo `ApkInstaller` non è disponibile
    (pacchetto non installato in questa build, estensione non compilata
    nell'APK, oppure un errore qualunque durante l'invocazione).

    Il chiamante deve intercettarla e mostrare all'utente il percorso del file
    già scaricato, così può installarlo a mano da un gestore file: il download è
    comunque andato a buon fine, è solo la consegna all'installer che non è
    riuscita.
    """


async def install_apk(page: ft.Page, apk_path: str) -> str:
    """
    Passa `apk_path` all'installer di pacchetti di sistema.

    `async` perché il ponte verso il lato Dart (`_invoke_method`) è una
    coroutine: in Flet 0.86.5 non esiste una variante "spara e dimentica"
    (verificato nel sorgente installato, `flet/controls/base_control.py:431`).
    Chi chiama deve quindi essere un handler `async def` — Flet li invoca
    direttamente.

    Il valore restituito dice solo se la FINESTRA di installazione si è aperta:
    appena l'utente conferma, Android uccide questo processo per sostituire
    l'app. Il messaggio "Aggiornamento completato" va perciò scritto PRIMA, come
    segnalibro in `app_settings` (vedi `core.update_state.mark_update_started`).

    Se l'utente non ha ancora concesso a questa app il permesso di installare
    app sconosciute, Android mostra da sé la finestra "per la tua sicurezza…"
    con la scorciatoia alle impostazioni: un tocco in più solo la prima volta.
    Non tentiamo di aprire noi `ACTION_MANAGE_UNKNOWN_APP_SOURCES` (richiederebbe
    codice Kotlin) — la strada di sistema esiste già e funziona.

    Raises:
        ApkInstallerUnavailable: pacchetto assente o invocazione fallita.
    """
    if not apk_path:
        raise ApkInstallerUnavailable("nessun percorso di APK da installare")

    try:
        from flet_apk_installer import ApkInstaller
    except ImportError as ex:
        raise ApkInstallerUnavailable(
            f"pacchetto flet_apk_installer non installato in questa build: {ex}"
        ) from ex

    try:
        installer = ApkInstaller()
        # Un controllo Service deve essere noto alla sessione prima di essere
        # invocato (`_invoke_method` solleva "must be added to the page first"
        # altrimenti). Le altre due estensioni di questo progetto si
        # auto-registrano costruendosi dentro un handler async; qui la
        # registrazione è esplicita perché l'oggetto vive solo per questa
        # chiamata.
        if installer not in (page.services or []):
            page.services.append(installer)
            page.update()
        esito = await installer.install(apk_path)
    except Exception as ex:
        raise ApkInstallerUnavailable(
            f"invocazione install() fallita: {ex}"
        ) from ex

    logger.info("APK %s consegnato all'installer di sistema (esito: %s).",
                apk_path, esito)
    return esito
