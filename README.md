# 🎲 D&D Companion

**Scheda personaggio digitale per Dungeons & Dragons 5a Edizione (regolamento italiano)**

App desktop e mobile scritta in Python + Flet, completamente offline, basata sul *Manuale del Giocatore* italiano (PHB 2014).

---

## ✨ Funzionalità

- **Wizard di creazione guidata** — 5 fasi interattive che suggeriscono classe, razza e background in base al tuo stile di gioco
- **Creazione manuale** — modulo completo con tutte le scelte PHB: punteggi, competenze, equipaggiamento iniziale
- **Scheda personaggio completa**
  - Profilo — anagrafica, caratteristiche, competenze, tratti razziali, foto personaggio
  - Combattimento — tracker HP, slot incantesimo (stile BG3), azioni turno, tiri salvezza
  - Esplorazione — sensi, velocità, lingue, strumenti, appunti di sessione auto-salvati
  - Inventario — armi (con danni magici), armature (calcolo CA automatico), oggetti, monete
  - Diario — voci di sessione con titolo, data e testo libero
- **Level-up guidato** — ASI, talenti, sottoclasse, nuove abilità (perizia, metamagia, invocazioni, incantesimi)
- **Sezione Incantesimi** — tutti gli incantesimi delle 8 classi PHB, preparazione e slot
- **Mappe** — caricamento immagini, disegno freehand con penna/gomma, annotazioni persistenti, zoom/pan con pinch (touch) e trackpad
- **Dadi** — tira qualsiasi combinazione direttamente dall'app
- **Compendio Talenti** — tutti i 42 talenti PHB con descrizione e prerequisiti
- **Multiclasse** — fino a 2 classi per personaggio, con prerequisiti/competenze/slot incantesimo calcolati secondo il PHB, level-up per singola classe, rimozione della classe secondaria e vista Incantesimi separata per classe
- **Esportazione scheda in PDF** — scheda personaggio compilata su modulo ufficiale PHB, pronta per la stampa
- **Esportazione/Importazione** — personaggio singolo (`.dndchar`) o mondo intero (`.dndworld`) in un file; trasferimento di un personaggio su un altro dispositivo con codice monouso
- **Mondi condivisi (LAN party)** — un Master ospita un mondo in rete locale (scoperta automatica o QR), i giocatori si uniscono col proprio personaggio; combattimento, note, mappe, bottino e appunti si sincronizzano in tempo reale; interventi rapidi a distanza del Master; riconnessione automatica anche se l'host cambia rete
- **Sezione Master**, tutto filtrato per il mondo selezionato:
  - **Rubrica NPC** — razza PHB con auto-riempimento tipo creatura/taglia, ritratto opzionale che il Master può caricare e che appare come dossier ("carta d'identità") al giocatore quando l'NPC è collegato a una nota di campagna condivisa
  - **Incontri** — generatore per Ambiente (tabelle DMG, quantità suggerite dal tiro con inserimento manuale sempre possibile) e per Difficoltà, tracker di combattimento condiviso in tempo reale con i giocatori
  - **Oggetti Magici** — compendio di 264 voci dal DMG con generatore casuale (anche in modalità "Personalizzato")
  - **Artefatti** — i 7 artefatti del DMG, pronti da assegnare
  - **Bottino** — creazione/assegnazione di voci (incluse armi/armature con campi meccanici e danni magici multipli) e Deposito del Gruppo condiviso, reclamabile dai giocatori
- **Aggiornamento automatico in-app** — controllo, download e installazione della nuova versione direttamente dall'app (nessuna disinstallazione richiesta)

---

## 📱 Piattaforme

| Piattaforma | Stato |
|---|---|
| macOS | ✅ build automatica ad ogni release |
| Windows | ✅ build automatica ad ogni release |
| Linux | ✅ build automatica ad ogni release |
| Android | ✅ build automatica ad ogni release, firmata, aggiornamento in-app |
| iOS | ⚠️ buildabile a mano (`flet build ipa`, richiede macOS + Xcode), non incluso nella pipeline di release automatica |

---

## 🛠 Stack tecnico

| Componente | Tecnologia |
|---|---|
| GUI | [Flet 0.86.5](https://flet.dev) (Flutter-based) |
| Database | SQLite (WAL mode, FK cascade) |
| Immagini | Pillow (foto personaggio, mappe, ritratti NPC) |
| PDF | ReportLab + pypdf (esportazione scheda) |
| LLM / AI | Nessuno — logica offline pura |
| Rete | Server LAN stdlib (`http.server`) per i Mondi condivisi, facoltativo; controllo/download aggiornamenti via GitHub Releases |

---

## 🚀 Avvio rapido

### Prerequisiti

- Python 3.10+
- pip

### Installazione

```bash
git clone https://github.com/DavMos9/dnd_app.git
cd dnd_app
pip install -r requirements.txt
```

### Avvio

```bash
python main.py
```

Il database viene creato automaticamente in `~/.dnd_companion/dnd_companion.db` al primo avvio.

---

## 📦 Build mobile (Android / iOS)

Richiede [Flet CLI](https://flet.dev/docs/publish):

```bash
pip install flet
```

**Android APK:**
```bash
flet build apk
```

**iOS IPA (richiede macOS + Xcode):**
```bash
flet build ipa
```

---

## 🐳 Modalità web (Docker)

In alternativa alla build nativa, l'app gira anche in modalità web servita da un container:

```bash
docker compose up -d
```

Espone la UI su `http://localhost:8000`. Il database SQLite persiste in un volume Docker (`dnd_data`); la libreria immagini e gli export personaggio/mondo usano bind mount reali sull'host (`./dnd_image_library`, `./dnd_character_exports`) — utile per copiarci dentro file via SSH quando non c'è un file picker nativo del browser. Vedi i commenti in `docker-compose.yml`.

---

## 📂 Struttura del progetto

```
dnd_app/
├── main.py                    # Entry point
├── version.py                 # Versione app (aggiornare prima di ogni release)
├── requirements.txt
│
├── config/
│   └── settings.py            # Costanti D&D 5e, colori, helper
│
├── core/                      # Logica di gioco pura (no Flet)
│   ├── wizard_engine.py / level_manager.py / equipment_manager.py / weapon_calculator.py
│   ├── npc_generator.py       # Generatore NPC (razza, allineamento, ruoli)
│   ├── encounter_generator.py / encounter_calculator.py / trap_generator.py   # Incontri, difficoltà, trappole DMG
│   ├── loot_calculator.py / treasure_generator.py / magic_item_generator.py
│   ├── pdf_sheet_exporter.py  # Esportazione scheda personaggio in PDF
│   ├── world_backend.py / world_sync.py / world_permissions.py / character_instances.py   # Mondi condivisi
│   └── update_checker.py / update_downloader.py   # Controllo e download aggiornamenti via GitHub Releases
│
├── network/                   # LAN party: scoperta, host/client, QR
│   ├── discovery.py
│   ├── host_server.py
│   ├── protocol.py
│   └── qr_join.py
│
├── data/
│   ├── database.py            # get_connection(), init_db(), migrazione idempotente
│   ├── models.py              # Dataclass Character e entità correlate
│   ├── game_data/
│   │   ├── classes/           # 12 JSON classi PHB
│   │   ├── races/             # 9 JSON razze PHB
│   │   ├── backgrounds/       # 13 JSON background PHB
│   │   ├── equipment/         # Armi, armature, attrezzatura, veicoli, economia
│   │   ├── spells/            # Incantesimi per classe
│   │   ├── feats.json         # 42 talenti PHB
│   │   └── invocations.json   # 32 invocazioni Warlock
│   └── repositories/
│       ├── character_repo.py  # CRUD personaggio (armi, inventario, valute, diario, ...)
│       ├── master_repo.py     # Rubrica NPC, incontri
│       ├── loot_repo.py / maps_repo.py
│       └── world_repo.py / world_export.py / world_transfer_repo.py / character_export.py   # Mondi condivisi, export/import, trasferimento dispositivo
│
├── ui/
│   ├── app.py                 # Router principale
│   ├── design.py              # Design system "Arcane Ledger" (token, tema chiaro/scuro, componenti)
│   ├── widgets.py             # Componenti riusabili (dropdown/multi-select con "Altro", ecc.)
│   ├── components/            # Componenti condivisi (sync in background, dossier NPC, ...)
│   └── views/                 # Tutte le schermate (character_sheet/, master/, world/, creation_wizard/, ...)
│
├── extensions/                # Estensioni Flet native su misura (picker foto/file, installer APK Android)
│
└── docs/                      # Design doc e changelog storico per feature
```

---

## 📖 Dati di gioco

Tutti i dati (nomi, valori meccanici, testi delle feature) provengono esclusivamente dal **Manuale del Giocatore D&D 5a Edizione — edizione italiana (2014)**.

L'app non include il testo del manuale: i file JSON contengono i dati meccanici necessari al funzionamento (dadi vita, competenze, progressione livelli, ecc.) come richiesto dalla [Systems Reference Document (SRD)](https://dnd.wizards.com/resources/systems-reference-document) sotto licenza Creative Commons.

---

## 🗺 Roadmap

- [ ] Conferma su dispositivi touch reali dello zoom mappa e del Dossier NPC in un Mondo condiviso (rilasciati in v0.3.4, non ancora testati dal vivo)

---

## 📄 Licenza

Questo progetto è distribuito sotto licenza [MIT](LICENSE).

*Dungeons & Dragons è un marchio registrato di Wizards of the Coast LLC.*
