# Regole Critiche: API Flet 0.85.3

> Consultare questo file **prima di scrivere o modificare qualunque codice UI Flet** in questo progetto. Ogni voce qui documenta una breaking change reale tra la firma/API "intuitiva" di Flet e quella effettiva della versione 0.85.3 pinnata (`requirements.txt`), già riscontrata e corretta nel codebase — non re-introdurre questi errori.

## Regole Critiche: API Flet 0.85.3

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
# ft.FilePicker su MOBILE (Android/iOS, build nativa "flet build apk/ipa") →
#   funziona correttamente E può leggere e.files[0].path DIRETTAMENTE, perché
#   Python gira sullo stesso dispositivo del client (nessun upload necessario).
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

# CLIENT_STORAGE — page.client_storage NON esiste in Flet 0.85.3
# `page.client_storage.get/set(...)` ← SBAGLIATO → AttributeError, l'attributo
#   non esiste su ft.Page in questa versione (verificato per introspezione sul
#   pacchetto installato, 2026-08-05). Sostituito da `ft.SharedPreferences`,
#   un controllo che eredita da `Service` — la STESSA classe base di
#   `ft.FilePicker`, documentato qui sopra come strutturalmente rotto in web
#   mode (flet-dev/flet#6040/#6250/#6251). Verificato empiricamente con una
#   FakePage che il tentativo fallisce fuori da una pagina montata
#   ("Control must be added to the page first") — **il comportamento in un
#   vero browser web NON è stato ancora verificato**, va fatto da Davide
#   prima di fidarsene per qualunque dato importante.
# Uso corretto (vedi ui/device_identity.py, Multiplayer 2026-08-05):
#   prefs = ft.SharedPreferences(); page.overlay.append(prefs); page.update()
#   value = await prefs.get(key)   # async — SEMPRE via page.run_task
#   await prefs.set(key, value)
# SEMPRE avvolto in try/except con un ripiego funzionante: se si rivela rotto
# in web mode come FilePicker, l'app non deve bloccarsi né fallire in
# silenzio.

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

# EXPAND=True su Column dentro Row dentro ListView → stesso crash silenzioso
# ft.Column([...], expand=True) dentro ft.Row(..., vertical_alignment=STRETCH)
# dentro ft.ListView → Flutter non risolve il constraint verticale → widget successivi scompaiono
# Fix: NON usare expand=True su Column dentro Row in contesti ListView.
#   Per colonne "greedy" in orizzontale: usare ft.Container(expand=True) come spacer
#   Per bordi laterali colorati: usare BorderSide sul Container esterno invece di una sidebar STRETCH

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
```

---


---

> Questo file è stato estratto da `CLAUDE.md` il 2026-07-31 durante la riorganizzazione della documentazione del progetto (il file principale era cresciuto fino a superare 860 KB, causando compattazioni troppo frequenti della chat). Il contenuto è verbatim, nessuna informazione è stata riassunta o rimossa. Per la mappa completa dei documenti del progetto vedi `CLAUDE.md` alla radice.
