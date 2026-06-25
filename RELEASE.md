# Come rilasciare una nuova versione

## Prerequisiti (una volta sola)

1. **Flutter SDK** installato sul tuo Mac:
   ```bash
   brew install flutter
   flutter doctor   # verifica che tutto sia ok
   ```

2. **Repository GitHub** deve essere pubblico (o privato con GitHub Actions abilitato)

---

## Processo di rilascio

### 1. Aggiorna la versione

In `version.py`:
```python
APP_VERSION = "0.2.0"   # ← nuova versione
```

In `pyproject.toml`:
```toml
[project]
version = "0.2.0"

[tool.flet]
app.version = "0.2.0"
app.build_number = 2    # ← incrementa di 1
```

### 2. Committa e crea il tag

```bash
cd dnd_app
git add version.py pyproject.toml
git commit -m "chore: release v0.2.0"
git tag v0.2.0
git push origin main --tags
```

### 3. GitHub Actions fa il resto

Dopo il push del tag, GitHub Actions:
- Compila automaticamente per **Windows**, **macOS**, **Linux**, **Android**
- Crea un **GitHub Release** con tutti i file allegati
- L'intero processo dura circa 15–25 minuti

Puoi seguire il progresso su: `https://github.com/DavMos9/dnd_app/actions`

---

## Build manuale (test locale)

Se vuoi testare la build prima del rilascio:

```bash
cd dnd_app

# Desktop (Mac)
flet build macos

# Desktop (Windows, solo su Windows)
flet build windows

# Android (APK per sideload)
flet build apk

# Linux
flet build linux
```

Gli artefatti vengono creati nella cartella `build/`.

---

## Distribuzione agli amici (fase test)

### Windows
- Scaricano `dnd-companion-windows.zip` dal GitHub Release
- Decomprimono e fanno doppio clic su `dnd_companion.exe`
- Windows potrebbe mostrare "App sconosciuta" → cliccare "Esegui comunque"

### macOS
- Scaricano `dnd-companion-macos.zip`
- Decomprimono, spostano `.app` nella cartella Applicazioni
- Prima apertura: clic destro → "Apri" (bypass del Gatekeeper)

### Android (tablet)
- Scaricano `dnd-companion-android.apk`
- Su Android: Impostazioni → Sicurezza → Abilita "Fonti sconosciute"
- Aprono l'APK per installare

### iPad (iOS)
- Richiede Apple Developer Account ($99/anno) e distribuzione via TestFlight
- Da implementare quando si decide di andare sugli store

---

## Aggiornamenti automatici in-app

L'app controlla automaticamente GitHub Releases all'avvio.
Se disponibile una versione più recente, appare un banner in basso con il tasto "Scarica"
che apre direttamente la pagina del rilascio nel browser.

---

## Checklist pre-rilascio

- [ ] Testato su almeno un dispositivo reale
- [ ] Versione aggiornata in `version.py` e `pyproject.toml`
- [ ] `git status` pulito (nessun file non committato)
- [ ] Tag creato nel formato `v0.X.Y`
- [ ] Build GitHub Actions completata con successo
