# Come rilasciare una nuova versione

## Prerequisiti (una volta sola)

1. **Flutter SDK** installato sul tuo Mac:
   ```bash
   brew install flutter
   flutter doctor   # verifica che tutto sia ok
   ```

2. **Repository GitHub** deve essere pubblico (o privato con GitHub Actions abilitato)

3. **Chiave di firma Android** generata e caricata nei GitHub Secrets — vedi
   [Migrazione alla firma di rilascio](#migrazione-alla-firma-di-rilascio-una-volta-sola).
   Senza di essa la build Android **fallisce di proposito**: un APK firmato in
   debug obbligherebbe tutti a disinstallare l'app per aggiornarla.

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
```

**Non toccare `build_number`** (il versionCode Android): dal 2026-08-17 lo
inietta la CI dal tag git, con la formula `major*1_000_000 + minor*1_000 + patch`
in `version.compute_build_number()` — v0.2.0 → 2000. Modificarlo a mano è
inutile, viene sovrascritto.

> **Corretto il 2026-08-17.** Questa sezione diceva di aggiornare anche
> `app.version` e `app.build_number` sotto `[tool.flet]`. Quelle chiavi sono lo
> schema di una versione precedente di flet_cli e **non vengono lette** da
> flet_cli 0.86.5 (la versione arriva da `[project].version`, il build number da
> `tool.flet.build_number` senza prefisso `app.`). La CI, per lo stesso motivo,
> riscriveva da mesi una chiave inesistente: una sostituzione a vuoto silenziosa,
> per cui ogni APK mai rilasciato porta `versionCode 1`. Un test lo presidia ora
> (`test_versione_app.py`) e la CI stampa il valore reale nel log.

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

*Implementato il 2026-08-17 (prima era solo un link al browser, e la
funzionalità era stata rimandata il 2026-08-06 — vedi
`docs/changelog_storico.md` per l'indagine originale).*

L'app controlla GitHub Releases all'avvio. Se c'è una versione più recente:

**Android** — download in-app con barra di avanzamento reale, poi consegna
all'installer di pacchetti di sistema. L'utente tocca "Installa" nella finestra
di sistema (Android **non** può installare in silenzio: è il modello di sicurezza
del SO, non un limite di questo progetto), e la prima volta autorizza anche
"installa app sconosciute" per l'app. Al riavvio successivo compare
**"Aggiornamento completato"**. Non serve disinstallare nulla: l'APK è firmato
con una chiave permanente.

**Desktop (Windows/macOS/Linux)** — download con barra di avanzamento, poi
apertura della cartella e istruzioni per sistema operativo. **Nessuna
sostituzione automatica dei file:** richiederebbe di uscire dall'app, lanciare un
processo helper che aspetta la chiusura, scambiare i file e rilanciare — lavoro
specifico per ogni SO col rischio concreto che l'app non riparta se lo scambio si
interrompe a metà. Valutato il 2026-08-06 e respinto, decisione confermata da
Davide il 2026-08-17.

Il messaggio "Aggiornamento completato" non può essere mostrato dal processo che
ha avviato l'aggiornamento (su Android viene ucciso dall'installer): viaggia in un
segnalibro su `app_settings`, scritto prima della consegna e letto al primo avvio
successivo. Vedi `core/update_state.py`.

---

## Migrazione alla firma di rilascio (una volta sola)

**Il problema che questo risolve.** Fino alla v0.2.15 la CI produceva l'APK con
il keystore di **debug**, che Flutter/Gradle rigenera su ogni runner: ogni release
aveva una firma diversa, e Android rifiutava l'aggiornamento in loco
(`INSTALL_FAILED_UPDATE_INCOMPATIBLE`) obbligando a **disinstallare e
reinstallare** — cancellando il database. È la causa del problema segnalato da
Davide, e nessuna barra di download poteva aggirarla.

*(Nota storica: le installazioni ≤ v0.1.35 avevano anche un `applicationId`
diverso, `com.flet.dnd_companion` invece di `com.davmos9.dndcompanion`, corretto
alla v0.1.36 — quelle non potevano aggiornarsi in loco a prescindere dalla
firma.)*

### 1. Genera il keystore (sul Mac, UNA volta, mai committato)

```bash
keytool -genkeypair -v \
  -keystore "$HOME/dnd-companion-upload.jks" \
  -storetype PKCS12 -keyalg RSA -keysize 4096 -validity 10950 \
  -alias upload -dname "CN=DnD Companion, O=DavMos9, C=IT"
```

Usa la **stessa password** per store e chiave. L'alias deve essere `upload` (è il
default che flet_cli si aspetta).

> ⚠️ **Fai un backup del `.jks` fuori dal Mac** (1Password, USB cifrata, un repo
> privato). Perderlo significa dover rifare un ciclo di disinstallazione per
> **tutti** ad ogni release futura. Il `CN=DnD Companion` non è cosmetico: la CI
> lo verifica per rifiutare un APK firmato con la chiave sbagliata.

### 2. Carica i due GitHub Secrets

`Settings → Secrets and variables → Actions`:

| Secret | Valore |
|---|---|
| `ANDROID_KEYSTORE_BASE64` | output di `base64 -i "$HOME/dnd-companion-upload.jks" \| pbcopy` |
| `ANDROID_KEYSTORE_PASSWORD` | la password scelta al passo 1 |

### 3. Prova con un tag usa e getta

```bash
git tag v0.2.16-rc1 && git push origin v0.2.16-rc1
```

Controlla nel log del job `build-android` lo step **"Verify APK signature and
version"**: deve stampare `CN=DnD Companion` e completarsi. Se qualcosa non
torna, la release si ferma lì invece di uscire e costringere tutti a
disinstallare di nuovo — è esattamente lo scopo di quello step. Solo dopo un
esito verde, tagga la versione vera.

### 4. La disinstallazione, una volta sola

Il primo APK firmato con la nuova chiave **non** può installarsi sopra quello
attuale: la firma è cambiata. L'app se ne accorge da sé
(`UpdateInfo.requires_reinstall`, soglia in `version.FIRST_SIGNED_VERSION`) e
mostra un flusso guidato invece del normale download. La sequenza:

1. **Esporta i personaggi** (Home → Esporta) e i **mondi che ospiti tu**
   (Mondi → Backup, file `.dndworld`). I personaggi che vivono solo in un mondo
   ospitato da un altro dispositivo si riprendono dall'host; quelli **locali**
   esistono solo sul dispositivo.
2. Per ogni mondo in cui giochi ospitato da altri, **chiedi al master un codice
   di trasferimento**: dopo la reinstallazione questo dispositivo sarà nuovo per
   lui (la disinstallazione cancella `app_settings`, e con esso il `device_id`), e
   quel codice è ciò che ti restituisce il personaggio. Vedi
   `docs/multiplayer_design.md` §11.9.
3. **Scarica l'APK dal browser**, non dall'app: l'app lo scaricherebbe nella
   propria cartella privata, che la disinstallazione cancella. Il dialogo di
   migrazione porta direttamente alla pagina della release proprio per questo.
4. Disinstalla, installa il nuovo APK, riprendi i personaggi.

**Da qui in avanti gli aggiornamenti Android avvengono in loco, senza perdere
nulla.**

---

## Checklist pre-rilascio

- [ ] Testato su almeno un dispositivo reale
- [ ] Versione aggiornata in `version.py` e `pyproject.toml` (`build_number` no:
      lo inietta la CI)
- [ ] `git status` pulito (nessun file non committato)
- [ ] Tag creato nel formato `v0.X.Y`
- [ ] Build GitHub Actions completata con successo
- [ ] Lo step "Verify APK signature and version" ha stampato `CN=DnD Companion`
