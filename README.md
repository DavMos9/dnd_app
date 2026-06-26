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
├── core/
│   ├── wizard_engine.py       # Logica scoring wizard (no Flet)
│   ├── level_manager.py       # Step di level-up per classe
│   └── update_checker.py      # Controllo aggiornamenti via GitHub Releases
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
│       └── character_repo.py  # CRUD completo
│
└── ui/
    ├── app.py                 # Router principale
    ├── theme.py               # Helper widget e tema
    └── views/                 # Tutte le schermate
```

---

## 📖 Dati di gioco

Tutti i dati (nomi, valori meccanici, testi delle feature) provengono esclusivamente dal **Manuale del Giocatore D&D 5a Edizione — edizione italiana (2014)**.

L'app non include il testo del manuale: i file JSON contengono i dati meccanici necessari al funzionamento (dadi vita, competenze, progressione livelli, ecc.) come richiesto dalla [Systems Reference Document (SRD)](https://dnd.wizards.com/resources/systems-reference-document) sotto licenza Creative Commons.

---

## 🗺 Roadmap

- [ ] Sincronizzazione LAN party (più giocatori in rete locale)
- [ ] Export scheda in PDF

---

## 📄 Licenza

Questo progetto è distribuito sotto licenza [MIT](LICENSE).

*Dungeons & Dragons è un marchio registrato di Wizards of the Coast LLC.*
