# Regole Critiche: API Flet 0.85.3 → 0.86.5

> Consultare questo file **prima di scrivere o modificare qualunque codice UI Flet** in questo progetto. Ogni voce qui documenta una breaking change reale tra la firma/API "intuitiva" di Flet e quella effettiva della versione pinnata in `pyproject.toml`, già riscontrata e corretta nel codebase — non re-introdurre questi errori.
>
> **Aggiornato a `flet==0.86.5` il 2026-08-05** (prima `0.85.3`, vedi
> `dnd_app/docs/changelog_storico.md` per il perché — tentativo di fix per un
> bug di packaging Android). Tutte le voci sotto restano valide: verificate
> per introspezione anche contro 0.86.5 e riconfermate da `python3 -m
> compileall` + le 4 batterie di test (291/291) senza modifiche. Le voci
> aggiunte da questa data in poi indicano esplicitamente se una API è nuova
> di 0.86.

## Regole Critiche: API Flet 0.85.3 → 0.86.5

Tutte queste breaking changes sono già state corrette nel codebase. Rispettarle per ogni nuovo codice.

```python
# ENTRY POINT
ft.run(run_app)                          # ft.app() è deprecato

# ICONE
ft.Icons.PERSON                          # capital I — obbligatorio
# ft.icons.person  ← SBAGLIATO

# PADDING / MARGIN / BORDER (classmethods, non moduli)
ft.Padding.symmetric(horizontal=8)       # NON ft.padding.symmetric
ft.Padding.all(16)                       # NON ft.padding.all
ft.Padding.only(left=8)                  # NON ft.padding.only
ft.Margin.only(bottom=4)                 # NON ft.margin.only
ft.Border.all(1, COLOR)                  # NON ft.border.all
ft.Border.only(bottom=ft.BorderSide(...))# NON ft.border.only
ft.BorderRadius.all(6)                   # NON ft.border_radius.all

# ALIGNMENT
ft.Alignment.CENTER                      # NON ft.alignment.center

# ANIMATION
ft.Animation(120, ft.AnimationCurve.EASE_OUT)   # NON ft.animation.Animation
# ft.AnimationCurve.EASE_OUT è ancora valido

# IMAGE FIT
ft.BoxFit.COVER                          # NON ft.ImageFit.COVER (rinominato)

# DROPDOWN
ft.DropdownOption(key=x, text=str(x))   # NON ft.dropdown.Option(x)
# on_select= invece di on_change= (solo per Dropdown — NavigationRail usa ancora on_change)
# Icona iniziale: ft.Dropdown(leading_icon=ft.Icons.X)   # NON prefix_icon= (quello è di ft.TextField)
# leading_icon accetta IconData (es. ft.Icons.PUBLIC) o un Control — errore reale, Davide 2026-08-06:
# "Dropdown.__init__() got an unexpected keyword argument 'prefix_icon'" — arrivava dal client (web E
# locale, stesso identico Dropdown Python), non un try/except da aggiungere: il kwarg semplicemente
# non esiste sulla classe. Verificare SEMPRE con `inspect.signature(ft.Dropdown.__init__).parameters`
# prima di aggiungere un kwarg "plausibile" per analogia con un altro controllo (qui: TextField).

# BUTTON TEXT
ft.ElevatedButton("Testo", icon=..., on_click=...)   # testo come 1° positional, NON text="Testo"
ft.OutlinedButton("Testo", on_click=...)
ft.TextButton("Testo", on_click=...)

# TEXT STYLING
ft.Text("x", style=ft.TextStyle(letter_spacing=2))  # letter_spacing va in TextStyle, non in Text

# DIALOGS & SNACKBAR
page.show_dialog(dlg)    # NON page.dialog = dlg; dlg.open = True; page.update()
page.pop_dialog()         # NON dlg.open = False; page.update()
# SnackBar è un DialogControl → usa show_dialog anche per la SnackBar

# THEME
ft.ColorScheme(primary=..., surface=..., error=...)  # NON background= o on_background=

# UPDATE PRE-MOUNT
# .update() lancia RuntimeError se chiamato prima di page.add()
# Usare try/except RuntimeError: pass nei metodi chiamati da __init__

# NAVIGATION RAIL — NON usare NavigationRailDestination con icon_content/selected_icon_content
# Questi parametri NON esistono in Flet 0.85.3 → TypeError a runtime
# Usare invece una Column custom di Container cliccabili con colori espliciti (vedi ui/app.py)

# IMMAGINI BASE64 — src_base64 NON esiste in Flet 0.85.3
# ft.Image(src_base64=...)  ← SBAGLIATO → Image.__init__() got an unexpected keyword argument
# Usare data URI: ft.Image(src=f"data:{mime};base64,{b64}")
# Helper _data_uri(b64) disponibile in app.py, home_view.py, profilo_tab.py

# FILE PICKER
# ft.FilePicker su DESKTOP Flet 0.85.3 → "Unknown control: FilePicker" — NON usare
#
# ⚠️ CORREZIONE 2026-08-06 (log `adb logcat` reale, non un'altra ipotesi) — TUTTO
#   il blocco "MOBILE" qui sotto, scritto in due sessioni precedenti (2026-08-05/06),
#   diagnosticava la causa SBAGLIATA. Non cancellato (si vede il ragionamento e
#   perché sembrava plausibile), ma la conclusione era falsa: NON è un bug di
#   packaging Android upstream di Flet. La causa vera, trovata leggendo un log
#   `adb logcat` reale durante la riproduzione (mai fatto prima — le sessioni
#   precedenti avevano solo lo screenshot del banner nell'app, mai il log nativo):
#     `RuntimeWarning: coroutine 'FilePicker.pick_files' was never awaited`
#   `pick_files()`/`save_file()`/`get_directory_path()` sono metodi `async` (Flet
#   1.0/v0.8x — verificato per introspezione: `inspect.iscoroutinefunction(...)`
#   è `True`) che restituiscono il risultato DIRETTAMENTE tramite `await`. Il
#   codice di `profilo_tab.py::_pick_photo_mobile()` e `maps_view.py::_pick_mobile()`
#   li chiamava SENZA `await`, da un `on_click` sincrono, assegnando anche un
#   `on_result` che questa versione di FilePicker non ha mai avuto (solo
#   `on_upload`, verificato sui campi del dataclass installato). La coroutine
#   veniva creata e scartata subito: il picker nativo non si apriva MAI, silenziosamente
#   — nessun banner "Unknown control", nessuna eccezione visibile nell'app, solo
#   quel `RuntimeWarning` nel log nativo (invisibile senza `adb logcat`/Console.app).
#   **Regola generale da questo bug**: qualunque metodo di un controllo Flet che
#   sia `async def` (verificare con `inspect.iscoroutinefunction`, non assumere
#   dal nome) va SEMPRE chiamato con `await` dentro una funzione `async def`
#   schedulata con `page.run_task(...)` — mai come fire-and-forget da un
#   `on_click` sincrono, anche se in apparenza "funziona" (nessun errore a
#   runtime, il bug è silenzioso). Fix applicato: entrambe le funzioni sono ora
#   `async def`, i chiamanti usano `page.run_task(fn, ...)` invece di `fn(...)`.
#   Dettaglio completo in `changelog_storico.md`.
#
# ⚠️ SECONDA CORREZIONE, STESSO GIORNO (2026-08-06) — il fix dell'`await` era
#   corretto ma INSUFFICIENTE. Un secondo log `adb logcat`, preso DOPO aver
#   applicato il fix sopra (confermato dal numero di riga citato nel log,
#   coerente col codice corretto), ha mostrato un errore diverso e più a
#   fondo:
#     `RuntimeError: TimeoutException after 0:00:10.000000: Timeout waiting
#     for invoke method listener for FilePicker(N).pick_files`
#   La chiamata Python arriva correttamente al bridge Dart (l'`await` ora
#   funziona) ma **nessuna Activity nativa Android viene mai avviata** —
#   verificato leggendo il log COMPLETO, non solo quello filtrato: nessun
#   picker di sistema, nessun dialogo di permesso, nessuna traccia di un
#   Intent lanciato durante i 10 secondi di attesa. Questo combacia esattamente
#   con la classe di bug "packaging" + "platform: android" già documentata
#   più sotto in questo file (punti 3-4 del ragionamento SBAGLIATO — SBAGLIATO
#   nella diagnosi iniziale del banner "Unknown control", ma la CAUSA DI FONDO
#   che quei punti descrivevano era comunque reale, solo manifestata con un
#   sintomo diverso una volta corretto l'await): `ft.FilePicker` non è
#   utilizzabile su questa build Android, per NESSUNO dei suoi metodi
#   (`pick_files`, `save_file`, `get_directory_path` — stesso controllo
#   `Service`, stesso bridge). Non è un problema risolvibile scrivendo il
#   codice Python diversamente attorno a `FilePicker`.
#
#   **Decisione presa con Davide (2026-08-06), dopo aver valutato le
#   alternative**: bypassare del tutto `ft.FilePicker` su mobile con
#   `ft.WebView` (estensione ufficiale `flet-webview`, un controllo
#   `LayoutControl` — non `Service` — con un meccanismo di rendering
#   completamente diverso, non condivide questo bug) che mostra una pagina
#   HTML locale con un `<input type=file>`, lo stesso elemento standard che
#   ogni browser usa per allegare un file — apre il selettore nativo tramite
#   l'infrastruttura WebView di Android, un pezzo di codice molto più maturo
#   e testato dell'integrazione Service di FilePicker. Zero rete coinvolta
#   (HTML passato come `data:` URI, `FileReader.readAsDataURL()` legge il
#   file in memoria lato browser). Implementato in
#   `ui/mobile_webview_picker.py` (dettaglio completo in
#   `architettura_moduli.md` e `changelog_storico.md`), usato da
#   `profilo_tab.py`, `maps_view.py`, `home_view.py::_on_mobile_import()`.
#   Alternative valutate e scartate: Pyjnius (Java diretto, ma nessun modo
#   pulito di riportare un risultato Intent async in puro Python senza glue
#   Kotlin/Java); estensione Flutter nativa custom (costo molto più alto,
#   stesso risultato ottenibile con WebView a costo minore).
#   **Ancora fuori scope**: `home_view.py::_on_mobile_export()` (save_file)
#   non è stato migrato — un download via WebView è un meccanismo diverso
#   (mai verificato), probabilmente soggetto allo stesso bug ma non ancora
#   confermato con un log dedicato.
#
# Il ragionamento (SBAGLIATO nella diagnosi del banner "Unknown control",
# ma la causa di fondo — FilePicker non utilizzabile su questa build
# Android — si è poi rivelata comunque corretta, vedi sopra):
# ft.FilePicker su MOBILE (Android/iOS, build nativa "flet build apk/ipa") →
#   ⚠️ SMENTITO DEL TUTTO (confermato 2026-08-06, screenshot di Davide su un
#   vero Android): anche l'uso lazy/interattivo (tap sul pulsante → crea il
#   controllo al primo tocco reale → pick_files()) mostra lo stesso "Unknown
#   control: FilePicker" — non era quindi (solo) un problema di timing della
#   creazione anticipata in did_mount() (quel fix resta corretto e necessario,
#   ha eliminato il crash garantito all'apertura, ma non basta).
#
#   Indagine di causa fatta lo stesso giorno, letture dirette (non ipotesi):
#   1. Il pattern Python `page.overlay.append(fp); page.update()` è
#      MECCANICAMENTE CORRETTO in Flet 0.85.3 — verificato leggendo
#      controls/services/service.py del pacchetto installato: `Service.init()`
#      chiama da solo `context.page._services.register_service(self)` non
#      appena il controllo viene montato, qualunque sia il contenitore
#      (overlay compreso). `ft.Page` non espone affatto una lista pubblica
#      `page.services` da popolare a mano — l'ipotesi "va usato page.services
#      invece di page.overlay" è stata verificata e SCARTATA.
#   2. "Unknown control: X" per controlli `Service` è quindi un problema
#      lato CLIENT (il controllo Flutter compilato nell'app non riconosce
#      il tipo), non lato Python — combacia con l'errore già documentato in
#      web mode (flet-dev/flet#6040/#6250/#6251).
#   3. Su Android è una classe di bug NOTA e RICORRENTE nel repository
#      upstream flet-dev/flet, con le etichette esplicite "packaging" +
#      "platform: android" — non specifica di FilePicker: stesso identico
#      errore già segnalato per ft.Clipboard (#2900, dal 2024, Flet 0.21.1)
#      e ft.Flashlight (#3599), sempre "funziona su desktop, Unknown control
#      sull'APK compilato con flet build apk". Conclusione onesta: molto
#      probabilmente un problema di come `flet_cli` impacchetta/registra
#      certi plugin `Service` nella build Android, non qualcosa risolvibile
#      cambiando il nostro codice Python (già verificato corretto al punto 1).
#   4. Pista di fix concreta, NON ancora verificata: Flet 0.86.0 (uscito dopo
#      la 0.85.3 che usiamo) dichiara nel changelog ufficiale un "completely
#      re-designed Android packaging" (dart-bridge, FFI al posto del socket).
#      Potenzialmente rilevante per questa classe di bug — va verificato con
#      un aggiornamento di versione mirato e un vero test su Android, non
#      assunto. Un aggiornamento di Flet è un cambio ampio (tocca l'intero
#      progetto, non solo il file picker) e va deciso con Davide, non fatto
#      di riflesso.
#   5. Trovato anche un gap indipendente e reale, da correggere comunque:
#      pyproject.toml non dichiara ALCUN permesso di lettura media/storage
#      (`READ_MEDIA_IMAGES` su Android 13+, o `READ_EXTERNAL_STORAGE` sotto).
#      Non spiega da solo "Unknown control" (un permesso mancante di norma dà
#      un errore di permesso DOPO l'apertura del picker, non "tipo di
#      controllo sconosciuto" PRIMA), ma è comunque necessario perché la
#      selezione immagine funzioni una volta risolto il problema di fondo.
#
#   Se confermato (dopo un fix): può leggere e.files[0].path DIRETTAMENTE,
#   perché Python gira sullo stesso dispositivo del client (nessun upload
#   necessario).
#
#   AGGIORNAMENTO 2026-08-05 — tentativo di fix, Flet 0.85.3 → 0.86.5:
#   Davide ha scelto di provare l'aggiornamento (release ufficiale che
#   dichiara un "completely re-designed Android packaging", pista di fix
#   più promettente del riscrivere ancora il nostro codice, già verificato
#   corretto). Fatto: pyproject.toml `flet==0.86.5`, `requires-python =
#   ">=3.12,<3.13"` (fissa il Python imbarcato a 3.12, la stessa versione
#   usata implicitamente da TUTTE le build precedenti — 0.86 di default
#   userebbe 3.14, ma le ruote native di Pillow per Android/iOS su 3.14 non
#   sono verificabili da qui: isolare la sola variabile "packaging Android"
#   che ci interessa). `python3 -m compileall` + tutte e 4 le batterie di
#   test (289/289) verdi contro 0.86.5 — nessuna rottura d'API Python
#   rilevabile da qui. **Ancora NON verificato**: se questo risolve
#   davvero "Unknown control" su un vero APK — richiede una build reale
#   (`flet build apk`, non disponibile in questo sandbox: niente Android
#   SDK/NDK) e un test di Davide su dispositivo, stesso limite già noto per
#   tutto il lavoro Multiplayer/LAN (vedi CLAUDE.md).
#
#   Trovato durante l'indagine, migliore del previsto: flet_cli 0.86.5
#   (commands/build_base.py, `BuildCommand.cross_platform_permissions` +
#   `self.get_pyproject("tool.flet.permissions")`) espone un gruppo di
#   permessi cross-platform pronto "photo_library" → mappa su Android su
#   `android.permission.READ_MEDIA_VISUAL_USER_SELECTED` (permesso di
#   "selezione parziale", non `READ_MEDIA_IMAGES` a cui avevo pensato
#   inizialmente) e su iOS su `NSPhotoLibraryUsageDescription` insieme.
#   Il commento nel sorgente flet_cli spiega perché: la policy Play Store
#   "Photo and Video Permissions" rifiuta permessi media ampi senza un
#   caso d'uso puntuale, e READ_MEDIA_VISUAL_USER_SELECTED è pensato
#   esattamente per "scegli una foto", il nostro caso. Aggiunto in
#   pyproject.toml come `[tool.flet] permissions = ["photo_library"]`
#   (chiave distinta da `tool.flet.android.permission`, verificata nel
#   sorgente prima di scriverla, non per analogia).
# ft.FilePicker su WEB (ft.AppView.WEB_BROWSER, es. deploy Docker) → NON
#   USARE AFFATTO, in nessuna forma. Bug upstream CONFERMATO e non
#   risolvibile lato applicazione (2026-07-12, verificato con fonte
#   primaria diretta sulla issue tracker di Flet: flet-dev/flet#6040,
#   #6250, #6251) — a partire da Flet ^0.80.1 (qui: 0.85.3), i controlli
#   "Service" come FilePicker sono strutturalmente rotti in web mode
#   (server-side rendering): il solo AGGIUNGERE un'istanza di
#   ft.FilePicker a page.overlay produce "Unknown control: FilePicker",
#   indipendentemente da QUANDO o COME lo si fa. Confermato che TUTTE le
#   strategie di registrazione falliscono nello stesso modo (verificato sia
#   da altri sviluppatori sulla issue tracker sia empiricamente in questo
#   progetto, in tre tentativi successivi nella stessa giornata):
#     1. Creazione al click (codice originale) → "Unknown control"
#     2. Registrazione anticipata in did_mount() → stesso errore, solo
#        spostato prima nel tempo (mostrato istantaneamente al mount)
#     3. Vero upload via page.get_upload_url()+FilePicker.upload() →
#        comunque irraggiungibile, perché richiede che FilePicker sia un
#        controllo riconosciuto dal client, cosa che qui non avviene mai
#   Fix applicato: NON creare/registrare mai ft.FilePicker quando
#   page.web è True. Al posto dell'upload dal client, un picker su una
#   libreria immagini caricata a mano da Davide via SSH (scp/rsync) in
#   una cartella server-side dedicata (bind mount Docker, NON un volume
#   Docker gestito — vedi docker-compose.yml e data/database.py →
#   get_image_library_path()) — nessun controllo Flet coinvolto, solo
#   lettura diretta del filesystem del server. Vedi ui/image_library.py
#   (show_image_library_picker), richiamato da profilo_tab.py
#   (_pick_photo()) e maps_view.py (pick_image() nei dialog crea/modifica
#   mappa) quando page.web è True. Vedi CLAUDE.md "Note Importanti"
#   (2026-07-12) per il changelog completo dei tentativi precedenti
#   (registrazione anticipata, poi vero upload via FilePicker.upload —
#   entrambi falliti per lo stesso bug upstream) e della soluzione finale.
# Desktop: rilevare page.platform, poi subprocess nativo:
#   macOS   → osascript
#   Windows → powershell OpenFileDialog
#   Linux   → zenity / kdialog
#   ⚠️ Il subprocess nativo apre il dialogo sulla macchina che esegue il
#   processo Python (il SERVER, non il client) — inutile/fuorviante se
#   l'app è servita da remoto (es. Docker + ft.AppView.WEB_BROWSER). In
#   quel caso il ramo corretto è sempre quello "web" (page.web == True),
#   mai il subprocess nativo — già gestito da `_pick_photo()`.

# WEBVIEW (flet_webview, pacchetto separato flet-webview==0.86.5) — usato
# in ui/mobile_webview_picker.py come bypass di ft.FilePicker (vedi sopra).
# - `WebView` è un `LayoutControl` (widget visibile, va dimensionato con
#   width/height o expand=True), NON un `Service` come `FilePicker` — non
#   condivide la stessa classe di bug.
# - Caricare HTML locale via il parametro COSTRUTTORE `url=` come
#   `data:text/html;charset=utf-8;base64,<...>`, non tramite il metodo
#   async `load_html()` chiamato dopo il mount: `load_html()` richiede il
#   controllo già montato sulla pagina (stesso vincolo `BaseControl.page`
#   che affligge i metodi di `FilePicker`), passare l'HTML già pronto nel
#   costruttore evita del tutto la sequenza "monta, poi invoca" e la race
#   di timing che ne deriva.
# - `on_console_message: EventHandler[WebViewConsoleMessageEvent]` (campo
#   `.message: str`) è un canale JS→Python di prima classe, verificato per
#   introspezione sul pacchetto installato — usare `console.log(...)` nella
#   pagina HTML per restituire dati a Python, con un prefisso di stringa
#   per distinguere il proprio protocollo da log innocui del motore di
#   rendering.
# - Nessun evento/metodo dedicato per intercettare un download avviato
#   dalla pagina (es. un `<a download>` o `Blob` + click) — non verificato,
#   non usato: questo modulo copre solo la SELEZIONE di file esistenti
#   (`<input type=file>`), non il salvataggio.
#
# ⚠️ CONFERMATO ROTTO (2026-08-06, test reale su Android + log adb + ricerca mirata):
#   `<input type=file>` dentro `ft.WebView` NON apre alcun selettore su Android — il
#   dialog/la pagina si aprono correttamente (il processo sandboxed Chromium parte, la
#   pagina renderizza), ma toccare il pulsante non fa scattare nulla, nessun errore
#   visibile. Causa: `flet-webview` è basato sui pacchetti Flutter ufficiali
#   `webview_flutter`/`webview_flutter_web` (dichiarato sulla pagina PyPI del
#   pacchetto) — è un limite NOTO di `webview_flutter` su Android: `<input
#   type="file">` richiede che l'app ospite implementi esplicitamente il callback
#   nativo `WebChromeClient.onShowFileChooser` (Kotlin/Java) perché il selettore di
#   sistema si apra; supporto aggiunto solo di recente e solo come opt-in esplicito
#   (`AndroidWebViewController.setOnShowFileSelector()`, richiede codice Dart/Kotlin
#   dedicato). Verificato per introspezione sul pacchetto `flet_webview==0.86.5`
#   installato: `ft.WebView` NON espone alcun parametro/evento/metodo per questo
#   (nessun `on_show_file_chooser`, `on_file_chooser` o simile — l'elenco completo dei
#   parametri del costruttore non contiene nulla del genere). **`ft.WebView` +
#   `<input type=file>` non è utilizzabile per la selezione file su Android con l'API
#   Python attuale — non è un problema risolvibile nel nostro codice**, un pezzo di
#   integrazione che `flet_webview` non ha mai wired, non un bug applicativo.
#   Lezione generale: "il meccanismo è maturo/testato nel browser" (vero per
#   `<input type=file>` in un browser reale) NON implica "il wrapper WebView di
#   questo framework lo abilita per davvero" — le due cose vanno verificate
#   separatamente, per introspezione sul pacchetto installato, prima di scrivere
#   codice attorno a un'API di terze parti imbarcata in un controllo Flet.
#
# ⚠️ TERZO TENTATIVO (2026-08-06, stessa giornata) — estensione Flet nativa
#   su misura, `dnd_app/extensions/flet_image_picker/`, wrapper del plugin
#   Flutter ufficiale `image_picker`. Lato Python verificato per
#   costruzione/importazione contro `flet==0.86.5` (`ui/
#   native_image_picker.py`). **Lato Dart NON verificato**: nessun
#   toolchain Flutter/Dart in questo sandbox. Vedi il dettaglio completo in
#   `changelog_storico.md` (voce 2026-08-06 "Davide ha scelto l'opzione (b)")
#   e `dnd_app/extensions/flet_image_picker/README.md`.
#
#   Scoperta di API utile per qualunque futura estensione Service scritta
#   in questo progetto: in Flet 0.86.5 **non esiste più `page.overlay`**
#   (rimosso rispetto a versioni precedenti di Flet) e `Page._services` è
#   un `ServiceRegistry` interno, non una lista pubblica — un controllo
#   `Service` NON va mai registrato esplicitamente
#   (`page.overlay.append(...)`/`page.services.append(...)` non esistono/
#   non sono il modo corretto). Si AUTO-registra dentro il proprio `init()`
#   — chiamato automaticamente da `BaseControl.__post_init__` al momento
#   della costruzione, purché `context.page` (una contextvar, sempre
#   impostata durante un handler async schedulato da `page.run_task(...)`)
#   sia già valorizzata. Basta quindi `picker = ImagePicker()` seguito da
#   `await picker.pick_image(...)` — confermato sia leggendo il sorgente
#   installato (`flet/controls/services/service.py`,
#   `base_control.py::__post_init__`) sia dall'esempio ufficiale eseguibile
#   ("Try Online") su https://flet.dev/docs/services/audiorecorder, che fa
#   esattamente questo (`recorder = far.AudioRecorder(...)`, mai aggiunto
#   a nessuna lista).
#
# ⚠️ DIPENDENZE LOCALI/PATH-BASED in [project.dependencies] → MAI un URI
#   assoluto scritto a mano, usare [tool.flet.dev_packages] — bug reale
#   (2026-08-06) che ha rotto TUTTE le build CI (Windows/macOS/Linux/
#   Android) dopo aver aggiunto `flet-image-picker` come
#   `"nome @ file:///Users/davide/.../extensions/flet_image_picker"` in
#   `[project.dependencies]`: funziona in locale (il path esiste sul Mac di
#   chi l'ha scritto), ma `flet build` gira anche su un runner CI dove quel
#   path non esiste — `pip install` fallisce, sulle 4 piattaforme allo
#   stesso modo (stesso meccanismo, stesso errore). Il modo CORRETTO,
#   verificato leggendo il sorgente installato di `flet_cli==0.86.5`
#   (`commands/build_base.py`): mettere in `[project.dependencies]` SOLO il
#   nome nudo del pacchetto (`"flet-image-picker"`, nessun `@ url`), e il
#   percorso locale in una tabella dedicata:
#   ```toml
#   [tool.flet.dev_packages]
#   flet-image-picker = "extensions/flet_image_picker"   # relativo alla cartella con pyproject.toml
#   ```
#   `flet_cli` risolve da solo il percorso (relativo alla project dir, la
#   stessa sia in locale sia dopo un `actions/checkout` in CI) e lo
#   converte in un `file://` URI corretto per piattaforma con
#   `Path.as_uri()` — portabile per costruzione, non per convenzione da
#   rispettare a mano. Esiste anche `tool.flet.<piattaforma>.dev_packages`
#   per un override specifico di una sola piattaforma, non necessario in
#   questo caso. Dettaglio completo in `changelog_storico.md`. **Confermato
#   funzionante da un vero run CI (2026-08-06)**: il log di
#   `flet build apk` mostra `Registering Flutter user extensions...
#   Registered Flutter user extensions OK` seguito da `pub` che risolve
#   correttamente `flet_image_picker` — il meccanismo aggancia DAVVERO il
#   pacchetto Flutter nel progetto generato, non solo il pacchetto Python.
#
# `debugPrint` IN UNA ESTENSIONE FLET/DART → richiede un import esplicito
#   Non è una funzione "globale" del linguaggio Dart: vive in
#   `package:flutter/foundation.dart` (ri-esportata anche da
#   `package:flutter/widgets.dart`/`material.dart`). Un `Service`/
#   `LayoutControl` scritto per un'estensione Flet che lo chiama senza
#   importare uno dei due va in errore di compilazione ("The method
#   'debugPrint' isn't defined for the type..."), scoperto SOLO al primo
#   vero `flet build apk` (nessun modo di intercettarlo prima senza un
#   toolchain Flutter/Dart locale). Successo in `dnd_app/extensions/
#   flet_image_picker/src/flutter/flet_image_picker/lib/src/
#   image_picker_service.dart` (2026-08-06): fix `import
#   'package:flutter/foundation.dart' show debugPrint;`. Se si trascrive
#   un pattern da un pacchetto Flet ufficiale (`flet-camera`,
#   `flet-audio-recorder`, ecc.) che usa `debugPrint`, copiare SEMPRE
#   anche il suo import di `package:flutter/widgets.dart` (o
#   `foundation.dart`), non solo la logica.

# CLIENT_STORAGE — page.client_storage NON esiste in Flet 0.85.3
# `page.client_storage.get/set(...)` ← SBAGLIATO → AttributeError, l'attributo
#   non esiste su ft.Page in questa versione (verificato per introspezione sul
#   pacchetto installato, 2026-08-05). "Sostituito" da `ft.SharedPreferences` —
#   ma vedi la voce subito sotto: in web mode va evitato del tutto, non solo
#   usato con cautela.
#
# SHAREDPREFERENCES — CONFERMATO ROTTO in web mode, mai crearlo se page.web
#   `ft.SharedPreferences` eredita da `Service`, la STESSA classe base di
#   `ft.FilePicker` (documentato sopra come strutturalmente rotto in web mode,
#   flet-dev/flet#6040/#6250/#6251). Confermato empiricamente da Davide su un
#   vero deploy web (2026-08-06): `page.overlay.append(ft.SharedPreferences());
#   page.update()` produce **"Unknown control: SharedPreferences"**.
#   Punto sottile: l'errore arriva dal client Flutter via websocket DOPO che
#   la chiamata Python è già "riuscita" — un try/except sincrono in Python
#   NON lo intercetta (stesso identico comportamento già visto per FilePicker
#   nei tre tentativi falliti documentati sopra). Un ripiego "prova e ricadi
#   sull'eccezione" non funziona per questa classe di bug: bisogna evitare la
#   creazione del controllo a monte con un `if page.web:` PRIMA di istanziarlo,
#   non un try/except attorno.
# Fix applicato in ui/device_identity.py: in web mode `resolve_device_id()`
#   non tenta più affatto SharedPreferences, va dritto a un'identità di sola
#   sessione tenuta come attributo su `page` (si perde al refresh della
#   pagina — limite noto, non un bug). Stesso pattern già in uso per
#   FilePicker in web mode (vedi sopra: "NON creare/registrare mai
#   ft.FilePicker quando page.web è True").
# Regola generale per QUALSIASI controllo `Service` non ancora provato in web
#   mode: non fidarsi finché non è verificato su un vero browser. Un
#   try/except attorno alla creazione dà un falso senso di sicurezza.

# HELPER THEME (ui/theme.py) — parametri supportati
label_text(text, size=10)
body_text(text, size=14, color=..., weight=...)
muted_text(text, size=12, text_align=..., weight=...)

# LISTVIEW CONTROLS — NON riassegnare self.controls
# self.controls = [...]  ← SBAGLIATO in Flet 0.85.3
#   rimpiazza la ControlsList interna che Flutter usa per il rendering
#   → il tab/lista appare completamente BIANCO senza errori Python
# Usare SEMPRE la modifica in-place:
#   self.controls.clear()
#   self.controls.append(widget1)
#   self.controls.append(widget2)
# Questo vale per __init__, _build(), _refresh() e qualunque except block.

# GESTURE DETECTOR — DragStartEvent / DragUpdateEvent NON hanno local_x/local_y
# Usare local_position.x e local_position.y (Offset object):
#   def on_pan_start(e: ft.DragStartEvent): x, y = e.local_position.x, e.local_position.y
#   def on_pan_update(e: ft.DragUpdateEvent): x, y = e.local_position.x, e.local_position.y
# TapEvent (on_tap_down): usa local_position.x / local_position.y (stessa struttura)

# FLET CANVAS (import flet.canvas as cv)
# cv.Paint NON esiste → usare ft.Paint (in flet principale)
# cv.PaintingStyle NON esiste → usare ft.PaintingStyle
# cv.StrokeCap NON esiste → usare ft.StrokeCap
# Il modulo cv espone: Canvas, Path, Text, Circle, Line, Arc, Rect, Oval, ecc. (solo shape)
# BlendMode.CLEAR NON funziona su CustomPaint senza saveLayer → appare nero, non trasparente
# Per la gomma NON usare BlendMode.CLEAR: manipolare la lista _strokes (rimuovere o spezzare)
# Gomma geometrica precisa: _split_stroke_by_circle() + _circle_segment_ts() (equazione quadratica)

# PROGRESSBAR — richiede vincolo di larghezza esplicito
# ft.ProgressBar dentro un Column dentro un Container (senza expand) → crash Flutter silenzioso
# → l'intera ListView diventa bianca senza errori Python
# Fix: wrappare sempre la ProgressBar in un ft.Row con expand=True:
#   ft.Row([ft.ProgressBar(value=pct, height=8, color=c, bgcolor=bg, expand=True)])

# WRAP=True su una Row/Column con un figlio expand=True → crash Flutter silenzioso
# ft.Row([..., ft.Text(..., expand=True)], wrap=True) → riquadro vuoto/grigio, NESSUN errore Python
# Causa: wrap=True genera lato Flutter un widget Wrap, che non supporta figli Expanded
# (solo Row/Column "veri" lo supportano) — trovato 2026-07-31 nel dialogo di assegnazione
# del Bottino (master_loot_assign_dialog.py/master_loot_view.py).
# Fix: MAI wrap=True su una Row/Column che ha un figlio con expand=True. Per troncare un
# testo lungo in quella posizione: no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS (senza
# expand, oppure expand SENZA wrap sulla Row — mai entrambi insieme).
#
# TAB BAR / BARRE DI PILLOLE CON TROPPE VOCI PER LO SCHERMO — non usare wrap=True
#   (2026-08-06): il fix "sicuro" (`wrap=True` + pillole senza `expand`, per evitare il
#   crash sopra) evita il crash ma introduce un difetto visivo diverso, segnalato da
#   Davide come "bruttissima, si prende tutto lo schermo": le pillole in eccesso vanno
#   su una riga in più A PIENA LARGHEZZA del contenitore, allungando verticalmente una
#   barra che deve restare una striscia sottile fissa (tab bar di SheetView/MasterView,
#   entrambe colpite). Fix corretto: `scroll=ft.ScrollMode.AUTO` sulla Row (NON `wrap`),
#   pillole senza `expand` — riga UNICA di altezza fissa, scorre ORIZZONTALMENTE quando
#   il contenuto non ci sta. Pattern già in uso e collaudato da tempo nella bottom nav
#   dell'app (`ui/app.py::_build_bottom_nav()`, 9 voci su smartphone stretto) — riusato,
#   non inventato ad-hoc. `wrap=True` va bene per contenuto che DEVE restare tutto
#   visibile senza scorrimento (es. chip di riepilogo, filtri) dove crescere in altezza
#   è accettabile; per una tab bar/barra di navigazione, dove l'altezza deve restare
#   fissa, usare sempre `scroll=ft.ScrollMode.AUTO`, mai `wrap=True`.
#
# ⚠️ SEGUITO (stesso giorno): `scroll=ft.ScrollMode.AUTO` risolve l'altezza ma NON
#   mettere mai un `bgcolor`/bordo/sfondo colorato sul `Container` che avvolge una Row
#   con `scroll=...`, se quel Container non ha una propria larghezza esplicita. Motivo
#   (comportamento noto di Flutter, non un bug Flet): un `SingleChildScrollView`
#   orizzontale (quello che Flet genera per `scroll=...`) NON si restringe MAI al
#   contenuto lungo l'asse di scroll — prende sempre la larghezza MASSIMA concessa dal
#   genitore, anche quando il contenuto reale è molto più stretto. Un `Container` senza
#   `width` esplicita eredita quella larghezza "gonfiata" e, se ha un `bgcolor`, la
#   disegna visibilmente anche dove non c'è alcun contenuto — un "alone" colorato che si
#   allunga fino al bordo dello schermo/finestra (segnalato da Davide su un vero
#   screenshot desktop: la pista beige dietro le 5 pillole della tab bar arrivava quasi
#   al bordo della finestra, molto oltre le pillole vere). Nota bene: con `wrap=True` lo
#   stesso problema NON si vede, perché il widget `Wrap` di Flutter SI restringe al
#   contenuto per riga — motivo per cui non era stato notato nel fix precedente.
#   Fix: NON dare mai un `bgcolor` al Container che avvolge la Row scorrevole. Se serve
#   un indicatore visivo di "gruppo" (tab bar, barra pillole), applicarlo a ogni singola
#   pillola (bordo/sfondo quando attiva/selezionata), mai a un contenitore che le
#   racchiude tutte — esattamente il pattern già in uso per "Generatori Rapidi"
#   (`design.pill()`, MasterView): nessuno sfondo di gruppo, ogni pillola ha il proprio.
#
# SEGUITO 2 (stesso giorno): anche `scroll=ft.ScrollMode.AUTO` si è rivelato sbagliato
#   per una tab bar — risolve l'altezza e l'alone, ma NASCONDE le voci che non ci stanno
#   dietro uno scroll orizzontale non scoperto (segnalato da Davide: "le selezioni vengono
#   tagliate o scompaiono, non si adattano alla pagina"). In questo progetto la preferenza
#   esplicita è per un'interfaccia sempre visibile, senza contenuto nascosto dietro un
#   gesto non ovvio (vedi la memoria persistente su "no hidden UI actions"). Per un
#   controllo con troppe voci per la larghezza minima da supportare, la sequenza di
#   tentativi corretta è: (1) provare a far entrare TUTTO restringendo il contenuto
#   stesso (qui: pillole icona-sola invece di icona+testo sotto un breakpoint, non
#   riduzione di font/padding — con etichette italiane lunghe una riduzione cosmetica non
#   basta comunque a farle stare in ~360px), PRIMA di (2) `wrap` (cresce in verticale) o
#   (3) `scroll` (nasconde). Il breakpoint per "sotto quale larghezza passare alla
#   versione compatta" va riusato da uno già esistente nel progetto se c'è (qui:
#   `ui/app.py::_MOBILE_BP = 600`, già usato per sidebar/bottom-nav), non inventato — un
#   secondo valore diverso creerebbe un'esperienza incoerente tra due parti dell'app che
#   cambiano "modalità mobile" a soglie diverse.
#
# page.on_resize È UN SINGOLO HANDLER, NON UN EVENTO A CUI CI SI PUÒ ISCRIVERE IN PIÙ PUNTI
#   `page.on_resize = f` SOVRASCRIVE qualunque handler già assegnato — non esiste un
#   equivalente di `addEventListener`. In questo progetto `page.on_resize` è di proprietà
#   esclusiva di `DnDApp._on_page_resize()` (`ui/app.py`), che lo usa per switchare tra
#   sidebar e bottom nav al breakpoint mobile. Se una vista figlia (es. `SheetView`,
#   `MasterView`) deve sapere "lo schermo è stretto?" per un proprio scopo (qui: la
#   modalità compatta della tab bar), NON deve assegnare un proprio `page.on_resize` —
#   romperebbe silenziosamente lo switch sidebar/bottom-nav. Corretto: calcolare il flag
#   (`is_mobile`) nel punto che già possiede `page.on_resize` (`DnDApp`) e passarlo giù
#   come parametro al costruttore della vista figlia. Limite accettato: la vista figlia
#   non si aggiorna da sola se ridimensionata DOPO essere stata costruita, a meno che il
#   punto che la costruisce non venga già richiamato dal resize esistente (vero per
#   `SheetView`, che vive dentro `content_area` e viene ricostruita da
#   `_show_main_layout()`; falso per `MasterView`, che sostituisce l'intera pagina via
#   `_navigate()` e quindi resta fissata al valore letto alla sua apertura).

# EXPAND=True su Column dentro Row dentro ListView → stesso crash silenzioso
# ft.Column([...], expand=True) dentro ft.Row(..., vertical_alignment=STRETCH)
# dentro ft.ListView → Flutter non risolve il constraint verticale → widget successivi scompaiono
# Fix: NON usare expand=True su Column dentro Row in contesti ListView.
#   Per colonne "greedy" in orizzontale: usare ft.Container(expand=True) come spacer
#   Per bordi laterali colorati: usare BorderSide sul Container esterno invece di una sidebar STRETCH

# DROPDOWN — il menu a tendina (popup delle opzioni) NON eredita lo stile
# dell'app da solo, nemmeno se `ft.Theme.dropdown_theme.text_style` è già
# impostato (bug report Davide 2026-08-15, screenshot: il menu di "Stato" in
# Note di Campagna si apriva come un riquadro grigio/nero semitrasparente,
# testo a malapena leggibile, sovrapposto al campo sopra invece di allinearsi
# sotto/sopra la tendina in modo pulito).
# Causa: `ft.DropdownTheme` ha DUE proprietà indipendenti — `text_style`
# (stile del testo scelto/delle opzioni, già impostato in questo progetto fin
# dalla Fase E) e `menu_style: ft.MenuStyle` (sfondo/ombra/forma del riquadro
# popup stesso, MAI impostato prima d'ora). Senza `menu_style`, il popup
# ricade sul default Material di Flutter — un riquadro con l'overlay di
# elevazione semitrasparente usato per il tema SCURO, visibile anche in tema
# chiaro perché non deriva affatto dalla palette dell'app. Colpisce OGNI
# `ft.Dropdown`/`DropdownAltro` dell'intera app (nessuna eccezione: non è un
# problema di un singolo campo), perché `dropdown_theme` è impostato una sola
# volta a livello di `ft.Theme` (`ui/theme.py::_build_theme()`).
# Fix (`ui/theme.py`, dentro `ft.DropdownTheme(...)`):
#   menu_style=ft.MenuStyle(
#       bgcolor=p.surface, shadow_color=p.shadow, elevation=8,
#       shape=ft.RoundedRectangleBorder(radius=d.Radius.SM),
#       side=ft.BorderSide(1, p.border),
#   )
#
# CORREZIONE 2026-08-16 (Davide ha confermato su build reale che il bug
# persisteva — su un ALTRO Dropdown dello stesso file, "Visibilità" — anche
# con questo fix già applicato): il fix sopra è necessario ma NON
# sufficiente da solo. In questa versione di Flet il riempimento del popup
# segue anche il `bgcolor` del CAMPO Dropdown stesso, non solo
# `menu_style.bgcolor` — un `ft.Dropdown(..., bgcolor="transparent")`
# produce un popup trasparente indipendentemente dal tema globale.
# Correlazione confermata su `master_notes_view.py`/`diary_view.py`: ogni
# Dropdown con `bgcolor="transparent"` mostrava il bug, ogni Dropdown con
# `**design.field_style()` (bgcolor opaco, `p.surface`) non l'ha mai
# mostrato. Fix completo: il `menu_style` del tema globale resta comunque
# necessario (ombra/forma/bordo del popup, e copre la maggioranza dei
# Dropdown già scritti con bgcolor opaco), MA un Dropdown scritto a mano con
# `bgcolor="transparent"` va corretto caso per caso a `bgcolor=p.surface`
# (o `**design.field_style()`) — non esiste un fix a un solo punto per
# questo caso, va cercato ogni `ft.Dropdown(...)` con `bgcolor="transparent"`
# nell'app (TextField non è interessato: nessun popup).

# TYPE STUBS Flet 0.85.3 — firme on_click / on_blur / on_select
# ControlEvent è troppo generico per Pylance; usare il tipo specifico:
#   def handler(ev: ft.Event[ft.TextButton]) -> None:   # on_click TextButton
#   def handler(ev: ft.Event[ft.IconButton]) -> None:   # on_click IconButton
#   def handler(ev: ft.Event[ft.Dropdown])  -> None:    # on_select Dropdown
#   def handler(ev: ft.Event[ft.TextField]) -> None:    # on_blur TextField
# Per handler generici / lambda usa Any: def handler(ev: Any) -> None:

# TYPE STUBS — attributi non noti (es. error_text su TextField post-costruzione)
# TextField.error_text non è assegnabile via stubs dopo __init__.
# Fix: cast(Any, widget).error_text = "messaggio"

# TYPE STUBS — liste eterogenee di Control
# list[Text | Column | Row | ...] non è assegnabile a list[Control] in Pylance
# Fix: cast(list[ft.Control], [...])

# TYPE STUBS — Checkbox.label è StrOrControl, non str
# cb.label or "" non è str per Pylance → usare str(cb.label) if cb.label else ""
# join() richiede Iterable[str] — usare list comprehension [...] non generator (...)

# SAFE AREA — ft.SafeArea esiste davvero (verificato per introspezione,
# Flet 0.85.3 e 0.86.5), non un'API inventata. Evita che header/barre in
# cima allo schermo finiscano sotto tacca/barra di stato su Android — no-op
# su desktop/web (MediaQuery non riporta intrusioni lì, nessun padding
# indesiderato). In questo progetto va SEMPRE e SOLO nel punto unico di
# navigazione `DnDApp._navigate()` in ui/app.py (2026-08-05) — non
# aggiungerlo dentro le singole view: se ogni vista lo facesse per conto
# proprio si tornerebbe alla stessa duplicazione già eliminata introducendo
# `_navigate()`.

# WRAP=True DENTRO UNA ROW NON-EXPAND → NON basta il flag, conta l'annidamento
# (trovato 2026-08-06 correggendo ProfiloTab, "Level up/Level down" tagliato
# al bordo su smartphone — vedi changelog_storico.md stessa data)
# Una ft.Row(...) di Flutter dà ai figli che NON hanno expand=True una
# larghezza MASSIMA lungo l'asse principale che è ILLIMITATA (unbounded),
# non la larghezza residua della Row. Se uno di quei figli non-expand è a
# sua volta un Column che contiene una Row con wrap=True, quella Row
# interna eredita il constraint illimitato e la sua Wrap non trova MAI un
# punto in cui andare a capo — il contenuto viene disegnato oltre il bordo
# fisico dello schermo, senza generare un overflow rosso di debug (il
# constraint è infinito, non superato). `wrap=True` da solo non è
# sufficiente a garantire che il contenuto vada a capo: bisogna verificare
# che la Row con wrap=True sia figlia diretta di un antenato che ha una
# larghezza REALMENTE vincolata (es. una Column che è l'unico contenuto di
# un Container con padding, o un figlio expand=True di una Row/Column
# genitore). Fix generale: quando un `wrap=True` non produce l'effetto
# atteso, non aggiungere altri flag alla cieca — risalire l'albero dei
# widget genitori e verificare dove la larghezza smette di essere
# vincolata, poi spostare/ristrutturare in modo che la Row da "wrappare"
# sia un figlio diretto di un contenitore vincolato.

# CALLBACK on_focus_change PER VISTE "A SCHERMO INTERO" DENTRO UNA SHELL
# (pattern introdotto 2026-08-06, MasterView + MasterEncounterListView —
# vedi changelog_storico.md stessa data)
# Quando una vista figlia entra in una modalità concettualmente "a schermo
# intero" (es. `MasterEncounterView`, aperta dentro `MasterEncounterListView`
# dentro `MasterView`), il genitore che possiede il proprio chrome fisso
# (selettore mondo, riga strumenti, barra tab) deve nascondere quel chrome
# mentre il figlio è a fuoco, altrimenti su schermo stretto il figlio eredita
# solo il rettangolo residuo. NON risolvere ricostruendo il genitore
# (`_build()`) quando il figlio cambia stato: `_build()` richiama
# `_get_tab_content()`, che ricrea il figlio da zero e ne perde lo stato di
# navigazione interno (es. quale elemento è aperto). Pattern corretto:
# passare al costruttore del figlio un callback `on_focus_change(bool)`;
# il genitore lo implementa salvando riferimenti ai propri controlli di
# chrome come attributi di istanza, e nel callback fa solo
# `ctrl.visible = not focused` seguito da `self.update()` — mai un rebuild.
# Il figlio invoca il callback nei propri punti di ingresso/uscita dal
# focus (qui: `_open_encounter()`/`_close_encounter()`).

# DRILL-DOWN MOBILE — pannello singolo invece di due colonne fisse
# (pattern usato 3 volte nel progetto: SheetView/MasterView per la tab bar
# compatta, MasterEncounterListView/MasterEncounterView per la lista
# incontri, MasterNotesView per Note di Campagna — quest'ultima 2026-08-06)
# Per una vista con layout a due pannelli fissi (lista/categorie a sinistra,
# dettaglio a destra) che su smartphone comprime il pannello di dettaglio
# sotto la soglia leggibile: NON restringere entrambe le colonne in
# proporzione (il pannello di dettaglio resta comunque troppo stretto per
# testo/pulsanti). Fix: un parametro `is_mobile: bool = False` nel
# costruttore, valorizzato dal chiamante con lo stesso breakpoint condiviso
# dell'app (`ui/app.py::_MOBILE_BP = 600`, mai un secondo valore), più uno
# stato interno che ricorda quale pannello mostrare. Sotto la soglia, la
# vista mostra UN pannello alla volta (lista, oppure dettaglio con un
# pulsante "indietro" al posto dell'icona/intestazione normale
# dell'header) invece della Row a due colonne; sopra la soglia, il layout a
# due colonne resta invariato. Ogni punto che cambia la selezione
# (click su un elemento, creazione, eliminazione, tasto indietro) deve
# aggiornare esplicitamente lo stato "quale pannello mostro" in modo
# coerente con l'azione (es.: elimina → torna alla lista; crea → mostra il
# nuovo dettaglio), altrimenti l'utente resta bloccato su un pannello
# vuoto o disallineato dopo l'azione.

# scroll=ft.ScrollMode.AUTO SU UNA ROW NASCONDE CONTENUTO, wrap=True NO
# (trovato 2026-08-06 da PC, la tab bar della Modalità Master tagliava le
# etichette anche su un desktop di larghezza moderata, non solo mobile —
# vedi changelog_storico.md stessa data)
# Uno scroll orizzontale (`scroll=ft.ScrollMode.AUTO`) su una Row che non
# entra nello spazio disponibile NON avvisa in alcun modo che c'è altro
# contenuto fuori vista — viola la convenzione di questo progetto "nessuna
# azione nascosta" ogni volta che scatta, indipendentemente dalla
# larghezza dello schermo che lo fa scattare. `wrap=True` (+ `run_spacing`
# per lo spazio verticale tra le righe) è la scelta corretta ogni volta
# che il contenitore riceve davvero una larghezza vincolata (vedi la voce
# sotto su come verificarlo): non nasconde mai nulla, il contenuto in
# eccesso va semplicemente a capo. Bonus verificato: `wrap=True` è
# nativamente reattivo al ridimensionamento della finestra DAL VIVO, senza
# alcun coinvolgimento di codice Python — è Flutter stesso a ricalcolare i
# punti di interruzione a ogni resize — mentre una decisione presa in
# Python al momento della costruzione (es. `is_mobile` letto una volta)
# resta fissa finché qualcosa non ricostruisce esplicitamente il controllo.
#
# ATTENZIONE — NON applicare questo fix "per coerenza" a viste gemelle
# senza una segnalazione esplicita su quelle: applicato inizialmente anche
# a `ui/views/character_sheet/sheet_view.py` (stesso difetto latente, mai
# innescato dalle sue etichette più corte), Davide ha chiesto di
# riportarlo a `scroll=ft.ScrollMode.AUTO` perché quella tab bar andava
# già bene com'era — il fix resta SOLO in
# `ui/views/master/master_view.py::_build_tab_bar()`, l'unica vista per
# cui è stato davvero richiesto. Non ripetere l'estensione "per parità".

# COME VERIFICARE SE UNA Row/Container HA UNA LARGHEZZA DAVVERO VINCOLATA
# (utile prima di scegliere tra wrap=True "funziona" o "produce l'identico
# bug ProfiloTab" — vedi la voce WRAP=True più sotto)
# Non c'è introspezione diretta da Python per interrogare i constraint di
# Flutter. Una prova empirica affidabile, usata più volte in questo
# progetto: se un `ft.Row(..., scroll=ft.ScrollMode.AUTO)` messo nello
# stesso identico punto dell'albero mostra il proprio `SingleChildScrollView`
# allargarsi fino a un bordo FINITO (es. il bordo della finestra), allora
# quel punto riceve una larghezza vincolata finita dal genitore — uno
# scroll view orizzontale si allarga fino al MASSIMO consentito dal
# genitore, mai oltre, e mai fino all'infinito se il genitore stesso non è
# infinito. Se invece si estendesse oltre il bordo fisico dello schermo
# (o semplicemente disegnasse contenuto invisibile senza mai fermarsi),
# il genitore starebbe dando una larghezza illimitata: lì `wrap=True` da
# solo NON basterebbe (serve la ristrutturazione già documentata per
# ProfiloTab: spostare il contenuto fuori dalla Row non-expand che lo
# rende illimitato).

# page.on_resize — PROPAGARE A VISTE DI PRIMO LIVELLO SENZA VIOLARNE LA
# PROPRIETÀ ESCLUSIVA (pattern introdotto 2026-08-06, DnDApp + MasterView —
# vedi changelog_storico.md stessa data)
# `page.on_resize` resta un singolo handler assegnato in UN SOLO punto
# (`DnDApp._setup_page()`, chiamato una volta sola nell'`__init__`) — la
# regola "proprietà esclusiva" già documentata sotto non cambia. Il modo
# corretto per far reagire anche viste di primo livello che sostituiscono
# l'intera pagina (`MasterView`/`WorldsView`, che via `_navigate()` NON
# vivono dentro il `content_area` che il layout principale già ricostruisce
# sul resize) è: (1) `DnDApp` tiene un riferimento alla vista di primo
# livello correntemente a video (`self._active_top_view`, impostato alla
# fine di ognuno dei metodi `_show_*()`); (2) il singolo `_on_page_resize()`
# chiama `getattr(self._active_top_view, "set_mobile", None)`, e se il
# metodo esiste lo invoca con il nuovo valore di `is_mobile` — duck typing,
# nessun crash per le viste che non lo implementano ancora. Ogni vista che
# vuole aggiornarsi dal vivo implementa il proprio `set_mobile(is_mobile)`
# SENZA mai assegnare un proprio `page.on_resize`: dentro fa un
# aggiornamento mirato (rebuild solo delle parti che dipendono da
# `is_mobile`, preservando lo stato interno che un `_build()` completo
# perderebbe — es. quale nota è selezionata), non un rebuild totale da
# zero. Distinguere un caso speciale che RICHIEDE un rebuild completo (qui:
# il layout principale sidebar/bottom-nav, due alberi di widget
# strutturalmente diversi) con un flag dedicato (`_on_main_layout: bool`),
# non riusando `_active_top_view is None` in modo ambiguo.

# RESPONSIVE ROW — ft.ResponsiveRow + il parametro `col` su ogni Control
# (dict per breakpoint, es. `col={"xs": 12, "sm": 6}`) esistono davvero
# (verificato per introspezione). Breakpoint DEFAULT di Flet (letti dal
# sorgente installato, non assunti): xs=0, sm=576, md=768, lg=992, xl=1200,
# xxl=1400 px — valutati lato client sulla larghezza REALE del
# ResponsiveRow al momento del render, non da `page.width` letto in Python.
# Preferirlo a un controllo `page.width` in Python ogni volta che il
# controllo può essere costruito PRIMA del mount sulla pagina (es. card in
# una lista costruita in `__init__`/`refresh()`, come `HomeView` e i tab
# della scheda): `self.page` in quei punti è spesso `None`, quindi un
# controllo `if (self.page.width or 0) < soglia` lì sarebbe silenziosamente
# sbagliato (sempre `False`) — non un'ipotesi, verificato leggendo
# `HomeView.__init__()`: `_build()`/`refresh()` girano prima che il
# controllo sia aggiunto a `page.controls`. Usato per la prima volta in
# `esplorazione_tab.py::_section_skills()` (2026-08-05).
```

---


---

> Questo file è stato estratto da `CLAUDE.md` il 2026-07-31 durante la riorganizzazione della documentazione del progetto (il file principale era cresciuto fino a superare 860 KB, causando compattazioni troppo frequenti della chat). Il contenuto è verbatim, nessuna informazione è stata riassunta o rimossa. Per la mappa completa dei documenti del progetto vedi `CLAUDE.md` alla radice.
