# flet_apk_installer

Estensione Flet su misura per D&D Companion: consegna un APK scaricato
all'installer di pacchetti di **sistema** su Android.

Terza estensione nativa di questo progetto, dopo `flet_image_picker` (foto
profilo) e `flet_file_picker` (import `.dndchar`/`.dndworld`). A differenza di
quelle due, **non contiene una riga di Kotlin** — vedi "Perché open_filex".

## A cosa serve

Chiude l'ultimo passo dell'aggiornamento in-app chiesto da Davide il 2026-08-17
("l'upgrade automatico dell'app con la barra del download... senza dover
eliminare e reinstallare l'app ogni volta"). Il download con barra di
avanzamento è puro Python (`core/update_downloader.py`); aprire la finestra
"Vuoi installare questa applicazione?" non lo è.

**Android non installa mai in silenzio.** È il modello di sicurezza del sistema
operativo, non un limite di questo progetto: anche nella migliore
implementazione possibile l'utente deve toccare "Installa" nella finestra di
sistema, e la prima volta anche autorizzare "installa app sconosciute" per
questa app. Questa estensione porta fino a quella finestra, niente di più.

Il vero problema segnalato da Davide — dover **disinstallare** prima di
aggiornare — non si risolve qui: era causato dalla firma dell'APK, che la CI
generava con un keystore di debug diverso su ogni runner. È risolto altrove, in
`.github/workflows/release.yml` (chiave di rilascio permanente + step di verifica
che fa fallire la release se l'APK torna a essere firmato in debug).

## Tre ostacoli, e come sono risolti

| Ostacolo | Soluzione |
|---|---|
| Permesso `REQUEST_INSTALL_PACKAGES` | Dichiarato in `pyproject.toml` del progetto principale, `[tool.flet.android.permission]` — letto da flet_cli. Nulla da fare qui. |
| Serve un URI `content://` (da Android 7 un `file://` solleva `FileUriExposedException`), quindi un `FileProvider` **e** una risorsa XML `res/xml/filepaths.xml` | Nessuna chiave di `pyproject.toml` letta da flet_cli 0.86.5 permette di aggiungere una risorsa Android arbitraria (verificate tutte nel sorgente installato). Risolto appoggiandosi a `open_filex` — vedi sotto. |
| Lanciare l'intent di installazione | `ft.FilePicker`/`ft.UrlLauncher` sono controlli "Service", confermati rotti in questo progetto; `url=` sui bottoni è client-side e non può portare un `ACTION_VIEW` su un file locale. Risolto da `OpenFilex.open()` col MIME type degli APK. |

## Perché `open_filex`

Non perché sia il più popolare: perché porta con sé il **proprio**
`AndroidManifest.xml` con un `<provider>` FileProvider e il proprio
`res/xml/filepaths.xml`, che il manifest merger di Gradle unisce ai nostri.
È l'unico modo di ottenere l'URI `content://` senza aggiungere una risorsa XML al
progetto Android generato — cosa che da `pyproject.toml` non si può fare — e
quindi senza scrivere codice Kotlin.

È ciò che rende questa estensione sensibilmente meno rischiosa delle due
precedenti: la superficie nativa è un solo `await OpenFilex.open(path, type:
...)`.

## API Python

```python
from flet_apk_installer import ApkInstaller

installer = ApkInstaller()
page.services.append(installer)          # un Service va noto alla sessione
esito = await installer.install(percorso_apk)   # apre la finestra di sistema
```

Il wrapper da usare nell'app è `ui/native_apk_installer.py`, che solleva
`ApkInstallerUnavailable` se il pacchetto non è compilato in questa build — il
chiamante (`ui/update_dialogs.py`) la intercetta e mostra all'utente il percorso
del file già scaricato, così può installarlo a mano da un gestore file.

`install()` è `async` perché in Flet 0.86.5 `_invoke_method` è l'unico ponte
verso il lato Dart e restituisce una coroutine (verificato in
`flet/controls/base_control.py:431`: non esiste una variante "spara e
dimentica"). Il valore restituito dice solo se la **finestra** si è aperta: appena
l'utente conferma, Android uccide il processo per sostituire l'app. L'esito vero
si scopre al riavvio successivo, dal segnalibro in `app_settings`
(`core/update_state.py`) — è quello che produce la scritta "Aggiornamento
completato".

## ⚠️ Cosa NON è verificato

Nessun toolchain Flutter/Dart in questo sandbox, nessun dispositivo Android.
Del lato Python è verificata solo l'importazione. Da controllare al primo giro di
CI e sul tablet di Davide, in quest'ordine:

1. **I vincoli di versione su pub.dev.** C'è un precedente reale e costoso:
   `flet_file_picker` fu scritto con `file_picker: ^8.1.7` e ruppe la CI su tutte
   e 4 le piattaforme ("version solving failed") perché `flet==0.86.5` richiede
   internamente `^11.0.2`. Controllare che `open_filex: ^4.4.0` e
   `path_provider: ^2.1.0` coesistano con ciò che pinna Flet 0.86.5 **prima** di
   lanciare la build.
2. **Il path relativo `flet: path: ../../../../../../../packages/flet`** nel
   `pubspec.yaml`. Copiato dalle altre due estensioni, i cui README dichiarano
   che non è verificato nemmeno lì.
3. **Che i `provider_paths` di `open_filex` coprano la cartella in cui scriviamo
   l'APK** (`data/database.py::get_updates_path()`, accanto al database). È il
   punto di rottura più probabile: se non la coprono, `install` fallisce con un
   errore di permessi sull'URI. Per questo l'estensione espone
   `download_dir()` (= `getExternalFilesDir(null)`, l'albero che open_filex
   espone di certo): il rimedio è scaricare là, e cambia una riga sul lato
   Python.
4. **Che l'estensione si carichi affatto** nella build reale.

Test da fare sul dispositivo: scaricare un aggiornamento dall'app → toccare
"Installa" → verificare che compaia la finestra di sistema → concedere "installa
app sconosciute" alla prima richiesta → confermare → verificare che al riavvio
compaia "Aggiornamento completato" e che i personaggi e i mondi siano al loro
posto.
