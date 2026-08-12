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
- **Mappe** — caricamento immagini, disegno freehand con penna/gomma, annotazioni persistenti
- **Dadi** — tira qualsiasi combinazione direttamente dall'app
- **Compendio Talenti** — tutti i 42 talenti PHB con descrizione e prerequisiti
- **Multiclasse** — fino a 2 classi per personaggio, con prerequisiti/competenze/slot incantesimo calcolati secondo il PHB, level-up per singola classe e vista Incantesimi separata per classe
- **Mondi condivisi (LAN party)** — un Master ospita un mondo in rete locale (scoperta automatica o QR), i giocatori si uniscono col proprio personaggio; combattimento, note, mappe e appunti si sincronizzano in tempo reale; esportazione/importazione di un mondo intero in un file `.dndworld`
- **Sezione Master** — rubrica NPC (razza PHB con auto-riempimento tipo creatura/taglia), Incontri e Bottino, tutto filtrato per mondo selezionato; azioni rapide a distanza sui personaggi dei giocatori
- **Controllo aggiornamenti automatico** — notifica in-app quando è disponibile una nuova versione

---

## 📱 Piattaforme

| Piattaforma | Stato |
|---|---|
| macOS | ✅ |
| Windows | ✅ |
| Linux | ✅ |
| Android | ✅ |
| iOS | ✅ |

---

## 🛠 Stack tecnico

| Componente | Tecnologia |
|---|---|
| GUI | [Flet 0.85.3](https://flet.dev) (Flutter-based) |
| Database | SQLite (WAL mode, FK cascade) |
| Immagini | Pillow (foto personaggio e mappe) |
| LLM / AI | Nessuno — logica offline pura |
| Rete | Solo controllo aggiornamenti (facoltativo) |

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
│   ├── wizard_engine.py       # Logica scoring wizard
│   ├── level_manager.py       # Step di level-up per classe
│   ├── npc_generator.py       # Generatore NPC (razza, allineamento, ruoli)
│   ├── encounter_generator.py / encounter_calculator.py   # Incontri e difficoltà
│   ├── loot_calculator.py / treasure_generator.py / magic_item_generator.py
│   ├── world_backend.py / world_sync.py / world_permissions.py   # Mondi condivisi
│   └── update_checker.py      # Controllo aggiornamenti via GitHub Releases
│
├── network/                   # LAN party: scoperta, host/client, QR
│   ├── discovery.py
│   ├── host_server.py
│   ├── protocol.py
│   └── qr_join.py
│
├── data/
│   ├── database.py            # init_db(), migrazione idempotente
│   ├── models.py              # Dataclass Character e entità correlate
│   ├── game_data/
│   │   ├── classes/           # 12 JSON classi PHB
│   │   ├── races/             # 9 JSON razze PHB
│   │   ├── backgrounds/       # 12 JSON background PHB
│   │   ├── spells/            # Incantesimi per classe
│   │   ├── feats.json         # 42 talenti PHB
│   │   └── invocations.json   # 32 invocazioni Warlock
│   └── repositories/
│       ├── character_repo.py  # CRUD personaggio
│       ├── master_repo.py     # NPC di rubrica
│       ├── loot_repo.py / maps_repo.py
│       └── world_repo.py / world_export.py / character_export.py   # Mondi condivisi
│
├── ui/
│   ├── app.py                 # Router principale
│   ├── theme.py               # Helper widget e tema
│   ├── widgets.py             # Componenti riusabili (dropdown/multi-select con "Altro", ecc.)
│   └── views/                 # Tutte le schermate (character_sheet/, master/, world/, ...)
│
└── docs/                      # Design doc e changelog storico per feature
```

---

## 📖 Dati di gioco

Tutti i dati (nomi, valori meccanici, testi delle feature) provengono esclusivamente dal **Manuale del Giocatore D&D 5a Edizione — edizione italiana (2014)**.

L'app non include il testo del manuale: i file JSON contengono i dati meccanici necessari al funzionamento (dadi vita, competenze, progressione livelli, ecc.) come richiesto dalla [Systems Reference Document (SRD)](https://dnd.wizards.com/resources/systems-reference-document) sotto licenza Creative Commons.

---

## 🗺 Roadmap

- [ ] Export scheda in PDF
- [ ] Verifica del multiplayer su Wi-Fi reale con dispositivi fisici
- [ ] Aggiornamento automatico in-app (rimandato: rischio se lo scambio file va storto a metà)

---

## 📄 Licenza

Questo progetto è distribuito sotto licenza [MIT](LICENSE).

*Dungeons & Dragons è un marchio registrato di Wizards of the Coast LLC.*
