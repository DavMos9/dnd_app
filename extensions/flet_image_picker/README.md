# flet-image-picker

Estensione Flet su misura per D&D Companion. Aggiunge un controllo
`ImagePicker` (categoria "Service") che apre il selettore immagini nativo
di sistema su Android/iOS, avvolgendo il plugin Flutter ufficiale
[`image_picker`](https://pub.dev/packages/image_picker) (versione `^1.2.3`,
verificata su pub.dev il 2026-08-06).

## Perché esiste

Sia `ft.FilePicker` (SDK ufficiale Flet) sia il fallback `ft.WebView` +
`<input type="file">` tentato subito dopo sono stati confermati NON
funzionanti su build Android reali di questo progetto — diagnosi completa
in `dnd_app/docs/changelog_storico.md` e `dnd_app/docs/regole_flet_api.md`
(sezione FILE PICKER). Questa è la terza strada, l'unica rimasta secondo
quella diagnosi: un'estensione nativa vera, non un ennesimo modo di
invocare `ft.FilePicker`/`ft.WebView`.

## Cosa fa (v1, scope minimo)

Solo selezione di UNA immagine dalla galleria di sistema. Niente cattura
fotocamera (avrebbe richiesto dichiarare anche il permesso `camera` nel
`pyproject.toml` dell'app, non necessario per gli usi attuali: foto
profilo e immagine mappa). Niente selezione multipla, niente video.

## Struttura

```
flet_image_picker/
├── pyproject.toml
├── src/
│   ├── flet_image_picker/          # lato Python — verificato per importazione
│   │   ├── __init__.py
│   │   └── image_picker.py
│   └── flutter/
│       └── flet_image_picker/      # lato Dart/Flutter — NON compilato/testato qui
│           ├── pubspec.yaml
│           └── lib/
│               ├── flet_image_picker.dart
│               └── src/
│                   ├── extension.dart
│                   └── image_picker_service.dart
```

Struttura di cartelle e pattern di codice presi 1:1 dai sorgenti REALI e
attualmente in produzione di `flet-camera` e `flet-audio-recorder`
(`github.com/flet-dev/flet/tree/main/sdk/python/packages/`), non
inventati — letti direttamente prima di scrivere questo codice, per lo
stesso principio già scritto in `regole_flet_api.md` dopo il fallimento
della WebView: verificare il meccanismo specifico del wrapper, non solo
che "il plugin sottostante esiste ed è maturo".

## ⚠️ Cosa NON è verificato da qui

Questo sandbox non ha Flutter/Dart installati (`which flutter dart` non
trova nulla) e quindi **nessuna riga di codice Dart in questa cartella è
mai stata compilata o eseguita**. Il lato Python è verificato per
importazione/costruzione contro `flet==0.86.5` (stessa versione già
pinnata nell'app).

**Verificato il 2026-08-06** (aggiornamento rispetto alla nota originale
qui sotto): il packaging Python imbarca davvero
`src/flutter/flet_image_picker/**` nel pacchetto installato — confermato
con un vero `pip install --target ...` in sandbox (bypassando solo il
vincolo `requires-python` non soddisfatto dal Python locale, `>=3.10` in
una copia di prova invece di `>=3.12`): la wheel risultante installa sia
`flet_image_picker/` (Python) sia `flutter/flet_image_picker/` (con
`pubspec.yaml` e tutto `lib/`) fianco a fianco, esattamente come nei
pacchetti ufficiali `flet-camera`/`flet-audio-recorder`. La sezione
`[tool.setuptools.package-data]` funziona quindi come previsto, non era
necessario rigenerare lo scaffold con `flet create --template extension`.

**Verificato il 2026-08-06 (stesso giorno, run CI reale di Davide su
GitHub Actions)** — risolve anche il punto 1 sopra: il log del job
`build-android` mostra `Registering Flutter user extensions... Registered
Flutter user extensions OK`, poi `Resolving dependencies... Got
dependencies!` con `flet_image_picker` elencato tra i pacchetti risolti da
`pub`. **`flet build` individua e collega correttamente
`flutter/flet_image_picker/` come dipendenza Flutter** — non solo il
packaging Python, anche l'aggancio lato Flutter funziona, senza bisogno di
alcun intervento manuale.

La build è arrivata fino a `Running Gradle task 'assembleRelease'` (174s)
prima di fallire con un vero errore di compilazione Dart:
```
image_picker_service.dart:25:5: Error: The method 'debugPrint' isn't
defined for the type 'ImagePickerService'.
```
Causa: `debugPrint` è definito in `package:flutter/foundation.dart`, mai
importato in `image_picker_service.dart` (il file da cui ho copiato il
pattern, `audio_recorder_service.dart` di flet-audio-recorder, lo importa
tramite `package:flutter/widgets.dart` — importo mancato nella trascrizione).
**Corretto**: aggiunto `import 'package:flutter/foundation.dart' show
debugPrint;`. Nessun altro errore riportato dal compilatore per
`extension.dart`/`image_picker_service.dart` in questo run — il resto del
codice (import di `flet`/`image_picker`, dispatch `_invokeMethod`,
`parseInt`/`parseDouble`, ciclo di vita `FletService`) è quindi risultato
corretto al primo vero tentativo di compilazione. **Non ancora
verificato**: se questo fix è sufficiente a far compilare l'APK per
intero (richiede un altro run CI/build di Davide) e se `pick_image()`
funziona a runtime su un dispositivo reale.

Prossimo passo per Davide: rilanciare la build (`flet build apk` o
tramite CI) e, se completa, testare `pick_image()` su un dispositivo
reale (foto profilo, immagine mappa).

## Riferimenti

- Pattern Service + `_invoke_method` restituente bytes: `flet-camera`
  (`take_picture`), `flet-audio-recorder` (`start_recording`).
- Doc ufficiale estensioni Flet: https://flet.dev/docs/extend/user-extensions/
- Plugin Flutter avvolto: https://pub.dev/packages/image_picker
