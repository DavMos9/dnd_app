# flet-file-picker

Estensione Flet su misura per D&D Companion. Aggiunge un controllo
`FilePicker` (categoria "Service") che apre il selettore file nativo di
sistema su Android/iOS, avvolgendo il plugin Flutter ufficiale
[`file_picker`](https://pub.dev/packages/file_picker) (versione `^8.1.7`).

## Perché esiste

Import personaggio (`.dndchar`) e import mondo (`.dndworld`) su mobile
passavano da `ui/mobile_webview_picker.py` (`ft.WebView` + `<input
type=file>`) — lo stesso bypass costruito a suo tempo per la selezione
foto, poi confermato NON funzionante su Android reale anche per la
selezione file generica (segnalato da Davide, 2026-08-17): `webview_flutter`
non implementa di default `WebChromeClient.onShowFileChooser`, quindi il tap
su "Scegli file" non apre alcun selettore — stessa identica diagnosi già
documentata per il caso foto in `dnd_app/docs/changelog_storico.md` e
`dnd_app/docs/regole_flet_api.md` (sezione FILE PICKER), mai risolta per il
caso file generico perché `flet_image_picker` avvolge `image_picker`, che
sa selezionare SOLO immagini da galleria — nessuna API per un file
arbitrario come `.dndchar`/`.dndworld`.

`ft.FilePicker` (SDK ufficiale Flet) resta scartato per lo stesso motivo già
noto: nessuna Activity nativa Android viene mai avviata su questa build.

Questa estensione applica **la stessa tecnica già verificata funzionante
per le foto** (Davide, 2026-08-06: "il picker immagini nativo funziona su
Android") a un selettore di file generico — stessa struttura di cartelle e
stesso pattern di codice di `flet_image_picker` (Service + `_invoke_method`
via canale MsgPack standard), stavolta attorno al plugin `file_picker`
invece di `image_picker`.

## Cosa fa (v1, scope minimo)

Selezione di UN file, con filtro opzionale per estensione
(`allowed_extensions`, es. `["dndchar", "json"]`). Nessuna selezione
multipla, nessun salvataggio (`save_file` — l'export mobile continua a
passare da `ft.FilePicker.save_file()`, non toccato da questa modifica:
diverso problema, mai confermato rotto con la stessa certezza dell'import).

## Struttura

```
flet_file_picker/
├── pyproject.toml
├── src/
│   ├── flet_file_picker/           # lato Python — verificato per importazione
│   │   ├── __init__.py
│   │   └── file_picker.py
│   └── flutter/
│       └── flet_file_picker/       # lato Dart/Flutter — NON compilato/testato qui
│           ├── pubspec.yaml
│           └── lib/
│               ├── flet_file_picker.dart
│               └── src/
│                   ├── extension.dart
│                   └── file_picker_service.dart
```

## ⚠️ Cosa NON è verificato da qui

Questo sandbox non ha Flutter/Dart installati — **nessuna riga di codice
Dart in questa cartella è mai stata compilata o eseguita**, esattamente
come per `flet_image_picker` alla sua prima stesura (quella estensione ha
richiesto due giri di build CI reale prima di funzionare: un import Dart
mancante, `debugPrint` non importato — vedi il suo README). È ragionevole
aspettarsi problemi simili qui al primo tentativo di build reale: Davide
deve rilanciare `flet build apk` (o CI) e leggere l'errore di compilazione
se presente, correggerlo, ripetere.

Nota di onestà anche sul plugin sottostante: quando fu scelto
`image_picker` per le foto, la diagnosi di quella sessione osservava che
`file_picker` ha una storia di affidabilità più incerta nell'ecosistema
Flutter — resta comunque il pacchetto standard per selezionare un file
arbitrario (nessun pacchetto "immagini" può farlo), e la causa di rottura
di `ft.FilePicker`/WebView qui è comunque a monte, nel bridge Flet, non nel
plugin `file_picker` in sé.

**Aggiornamento 2026-08-17 — primo giro di build CI reale, due bug trovati
e corretti:**

1. **Version solving failed su tutte e 4 le piattaforme** (run #54, log
   completo di GitHub Actions): `flet==0.86.5` dichiara internamente
   `file_picker ^11.0.2` (per il suo `ft.FilePicker` ufficiale — quello
   confermato non funzionante su Android, non questa estensione), in
   conflitto col vincolo `^8.1.7` scritto qui alla prima stesura (mai
   verificato su pub.dev, solo assunto per analogia con `image_picker`).
   `pub` risolve le dipendenze Flutter dell'INTERO progetto una volta sola,
   prima di compilare per qualsiasi piattaforma — per questo il conflitto
   ha fatto fallire Windows/macOS/Linux/Android nello stesso identico
   modo, non solo Android. **Fix**: `file_picker` allineato a `^11.0.2`,
   la stessa versione già richiesta da Flet stesso.
2. **API cambiata tra 8.x e 11.x**: `file_picker` 11.0.0 ha rifattorizzato
   `FilePicker` in una classe interamente statica, rimuovendo il getter
   `.platform` — `FilePicker.platform.pickFiles(...)` (sintassi 8.x, quella
   scritta qui alla prima stesura) non compila più su 11.x, va chiamato
   `FilePicker.pickFiles(...)` direttamente. Verificato sulla
   documentazione pub.dev della versione 11.0.2 prima di correggere (non
   assunto). Il resto della superficie usata (`FileType.custom`/`.any`,
   `allowedExtensions`, `withData`, `FilePickerResult.files`,
   `PlatformFile.name`/`.bytes`) risulta invariato tra 8.x e 11.x.

Nessuno dei due bug è stato compilato/verificato qui (stesso limite di
sempre, nessun toolchain Flutter/Dart in questo sandbox) — corretti per
lettura del log CI reale e della documentazione ufficiale del pacchetto,
stessa disciplina già applicata per `flet_image_picker`. Resta da
verificare col prossimo giro di CI se questi due fix bastano a far
compilare l'estensione per intero, o se emergerà un terzo problema (come
successo per `flet_image_picker`, due giri prima di arrivare a Gradle).

## Wiring lato app

`ui/native_file_picker.py::pick_file_native()` — chiamato PRIMA del
fallback WebView da `HomeView._on_mobile_import()`
(`ui/views/home_view.py`) e `WorldsView._on_mobile_import_world()`
(`ui/views/world/world_view.py`); se solleva `FilePickerUnavailable`
(pacchetto non installato in questa build, o qualunque errore
all'invocazione), i chiamanti ricadono automaticamente su
`pick_file_via_webview()` (`ui/mobile_webview_picker.py`), NON rimosso —
resta la rete di sicurezza, stesso schema già in uso per le foto.

## Riferimenti

- Pattern Service + `_invoke_method` restituente dati via MsgPack:
  `flet-camera` (`take_picture`), `flet_image_picker` (`pick_image`).
- Doc ufficiale estensioni Flet: https://flet.dev/docs/extend/user-extensions/
- Plugin Flutter avvolto: https://pub.dev/packages/file_picker
