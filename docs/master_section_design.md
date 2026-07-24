# Sezione Master — Architettura (progettata il 2026-07-24)

> Design confermato con Davide via 3 domande dirette prima di scrivere questo documento:
> 1. Collocazione → **indipendente dai personaggi**, nuovo punto d'accesso da `HomeView`
>    ("Modalità Master"), non una voce di sidebar dentro la scheda di un PG.
> 2. Ambito v1 → **entrambe**: rubrica NPC persistente + tracker da combattimento, fin
>    da subito (non solo una delle due).
> 3. Iniziativa → **ordine unificato**: il Master vede in un unico ordine turni sia le
>    proprie creature sia i personaggi giocanti già presenti nel DB.

Nessun codice scritto ancora — solo progettazione. Prossimo passo: conferma di Davide
prima di iniziare l'implementazione (feature grande, non "poco lavoro").

---

## Navigazione

- `HomeView`: nuovo punto d'ingresso "Modalità Master" (bottone in header, separato
  dalle card personaggio).
- `ui/app.py` (`DnDApp`): nuovo stato di routing a sé, `_show_master_view()` —
  stesso pattern già usato per `_show_wizard()`/`_show_manual_form()`/`_show_main_layout()`,
  MAI innestato dentro `MainLayout` (che resta esclusivamente per la scheda di UN
  personaggio selezionato).
- `MasterView` (nuovo modulo, es. `ui/views/master/master_view.py`): tab bar interna
  con due sezioni — "Rubrica NPC" e "Incontri". Click su un incontro → `MasterEncounterView`
  (vista a schermo intero per il tracker di combattimento di quell'incontro specifico),
  con un bottone "torna agli Incontri" e uno per tornare alla Home.

## Perché NON riusare `creature_entries`

`creature_entries` esiste già (usata da Forma Selvatica/Evocazioni in `combattimento_tab.py`)
ma ha `character_id` come FK **obbligatoria** con CASCADE — è concettualmente "una creatura
temporanea di UN personaggio specifico". Renderla nullable per riusarla anche per il Master
significherebbe toccare una tabella già in produzione con semantica FK diversa (rischio di
regressione sulle feature esistenti). Più sicuro e più pulito: **3 tabelle nuove**,
completamente indipendenti da `characters`, mai una `character_id` NOT NULL.

## Schema DB proposto

```sql
master_npcs (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  role TEXT DEFAULT '',              -- es. "Alleato", "Antagonista", "Comune" — testo libero
  notes TEXT DEFAULT '',             -- note di ruolo/backstory, sempre presenti anche senza stat block
  tags TEXT DEFAULT '',              -- CSV libero per filtro/ricerca nella rubrica
  has_stat_block INTEGER DEFAULT 0,  -- 0 = solo scheda di ruolo, 1 = ha anche le statistiche sotto
  -- Campi stat block, stessa forma di creature_entries, TUTTI opzionali:
  creature_type TEXT DEFAULT '', size TEXT DEFAULT '', alignment TEXT DEFAULT '',
  ac INTEGER DEFAULT 0, ac_note TEXT DEFAULT '',
  hp_max INTEGER DEFAULT 0, hp_formula TEXT DEFAULT '',
  speed TEXT DEFAULT '',
  str_score INTEGER DEFAULT 10, dex_score INTEGER DEFAULT 10, con_score INTEGER DEFAULT 10,
  int_score INTEGER DEFAULT 10, wis_score INTEGER DEFAULT 10, cha_score INTEGER DEFAULT 10,
  saving_throws TEXT DEFAULT '', skills TEXT DEFAULT '',
  damage_vulnerabilities TEXT DEFAULT '', damage_resistances TEXT DEFAULT '',
  damage_immunities TEXT DEFAULT '', condition_immunities TEXT DEFAULT '',
  senses TEXT DEFAULT '', languages TEXT DEFAULT '', cr TEXT DEFAULT '',
  traits TEXT DEFAULT '[]', actions TEXT DEFAULT '[]',
  reactions TEXT DEFAULT '[]', legendary_actions TEXT DEFAULT '[]',
  source_page TEXT DEFAULT '',       -- es. "da Bestiario: Goblin (p.167)" se creato da monsters.json
  created_at, updated_at
)

master_encounters (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  notes TEXT DEFAULT '',
  round_number INTEGER DEFAULT 1,
  current_turn_index INTEGER DEFAULT 0,
  is_archived INTEGER DEFAULT 0,     -- incontro concluso, resta nello storico ma non nella lista attiva
  created_at, updated_at
)

master_encounter_members (
  id TEXT PRIMARY KEY,
  encounter_id TEXT NOT NULL REFERENCES master_encounters(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,                -- "character" | "npc" | "adhoc"
  character_id TEXT REFERENCES characters(id) ON DELETE CASCADE,   -- solo se kind="character"
  npc_id TEXT REFERENCES master_npcs(id) ON DELETE SET NULL,       -- solo se kind="npc"
  display_name TEXT DEFAULT '',      -- usato per "adhoc"; per character/npc è un override opzionale
  ac INTEGER DEFAULT 0,              -- cache per npc/adhoc; per "character" si legge live da characters.ac
  hp_current INTEGER DEFAULT 0, hp_max INTEGER DEFAULT 0,  -- tracciati solo per npc/adhoc
  initiative INTEGER DEFAULT 0,
  order_index INTEGER DEFAULT 0,     -- per pareggi/riordino manuale
  is_active INTEGER DEFAULT 1,       -- rimosso dall'incontro senza cancellare la riga (storico)
  notes TEXT DEFAULT '',
  created_at, updated_at
)
```

**Nota sulla FK di `npc_id`**: `ON DELETE SET NULL` (non CASCADE) — se un NPC viene cancellato
dalla rubrica mentre è già dentro un incontro salvato, il membro dell'incontro resta (con
`display_name`/`ac`/`hp_*` già cachati al momento dell'aggiunta), invece di sparire dallo
storico dell'incontro. Per `character_id` invece CASCADE è corretto: se il personaggio viene
eliminato dall'app non ha senso tenere un riferimento morto nell'incontro.

**Perché i PF dei personaggi giocanti NON sono duplicati qui**: `characters.hp_current` resta
l'unica fonte di verità (il giocatore la gestisce dalla propria tab Combattimento). Il Master
vede questi valori in sola lettura (join su `characters` al momento del render) — evita
il rischio di due copie che divergono silenziosamente. Se in futuro Davide vuole che il
Master possa modificare gli HP di un PG assente dal tavolo, si può aggiungere un pulsante
esplicito "scrivi sul personaggio" che scrive direttamente su `characters.hp_current`
(stessa riga di verità, nessuna copia parallela) — non implementato in v1 salvo richiesta.

## Repository (`data/repositories/master_repo.py`, nuovo modulo)

CRUD standard per le 3 tabelle, stesso stile di `character_repo.py`:
`get_npcs()`, `create_npc(...)`, `update_npc(...)`, `delete_npc(id)`,
`get_encounters(include_archived=False)`, `create_encounter(...)`, `archive_encounter(id)`,
`get_encounter_members(encounter_id)` (con `character_id` risolto via JOIN su `characters`
per nome/CA/PF live quando `kind="character"`), `add_member(...)`, `update_member_hp(...)`,
`remove_member(...)` (soft: `is_active=0`), `advance_turn(encounter_id)` (incrementa
`current_turn_index`, avanza `round_number` al giro completo).

## Creazione NPC/mostro — due percorsi (non un wizard multi-fase)

Gli NPC non hanno le scelte a cascata di razza/classe/background dei personaggi giocanti:
un vero wizard guidato sarebbe sovradimensionato. Due percorsi pragmatici:

1. **"Nuovo dal Bestiario"** — riusa il picker già scritto in `combattimento_tab.py`
   (`_open_manual_creature_dialog`, ricerca per nome/tipo/CR su `monsters.json`, 444 mostri
   già auditati al 100%) per precompilare tutti i campi stat block, poi atterra sullo stesso
   form manuale (punto 2) per gli ultimi ritocchi (nome personalizzato, note di ruolo, tag).
2. **"Nuovo Manuale"** — form vuoto con tutti i campi di `master_npcs`; sezione statistiche
   di combattimento dietro un toggle "Ha statistiche di combattimento" (nascosta di default,
   per non intimidire chi vuole solo salvare un NPC di puro ruolo).

**Refactoring necessario per il riuso**: il picker bestiario e il dialog di dettaglio stat
block (tratti/azioni/reazioni/azioni leggendarie con badge e descrizione) vivono oggi come
metodi privati di `CombattimentoTab` — vanno estratti in helper condivisi (`ui/widgets.py`
o nuovo `ui/components/monster_picker.py` + `ui/components/stat_block_view.py`) così sia
il giocatore (Forma Selvatica/Evocazioni) sia il Master usano la stessa identica logica,
invece di duplicarla. Questo tocca `combattimento_tab.py` per estrarre senza rompere
l'uso esistente — va fatto con attenzione e verificato con test di regressione sulle
funzionalità già in produzione.

## Vista tracker di combattimento (`MasterEncounterView`)

- Header: nome incontro, round corrente, "Prossimo Turno" (avanza `current_turn_index`,
  wrap a fine lista con incremento `round_number`), "Termina Incontro" (archivia).
- "Aggiungi Combattente" → dialog con 4 scelte: Personaggio Giocante (lista da `characters`,
  sola lettura su CA/PF), NPC dalla Rubrica (da `master_npcs`), Mostro dal Bestiario
  (ricerca `monsters.json`, non salvato in rubrica a meno che il Master non lo richieda
  esplicitamente con un "Salva anche in Rubrica"), Creazione Rapida (nome+CA+PF, nessuno
  stat block, per un avversario improvvisato al tavolo).
- Corpo: lista/card ordinata per iniziativa decrescente. Ogni card: nome, badge iniziativa,
  CA, barra PF (+/− cliccabili per npc/adhoc; per "character" mostra il valore live con
  etichetta "gestito dal giocatore", nessun controllo di modifica). Click sul nome apre il
  dialog di dettaglio stat block completo (riuso del componente condiviso di cui sopra) per
  npc/adhoc; per "character" apre invece un link rapido alla sua scheda (se si vuole
  navigarci, opzionale).
- Pulsanti quantità rapida ("Aggiungi 3×") per aggiungere subito N istanze identiche dello
  stesso mostro (comodo per gruppi di goblin), ciascuna come membro `adhoc` distinto con
  nome numerato ("Goblin 1", "Goblin 2", ...).

## Vista rubrica (`MasterNpcListView`)

Lista di tutti i `master_npcs`, ricerca per nome/tag/ruolo. Card → dialog di dettaglio
(stesso componente condiviso stat block) con "Modifica"/"Elimina". Da qui si può anche
aggiungere direttamente un NPC a un incontro esistente ("Aggiungi a Incontro...").

## Cosa NON è in scope per v1 (per restare fedeli alla domanda "entrambe fin da subito"
senza sconfinare in territorio non richiesto)

- Nessuna scrittura del Master sugli HP dei personaggi giocanti (sola lettura, vedi sopra).
- Nessun collegamento con LAN party/sync in tempo reale (dipende dal modulo `network/`,
  ancora vuoto — v2 separato).
- Nessuna gestione delle Azioni di Tana/Effetti Regionali già presenti nel bestiario per i
  mostri con tana — mostrabili in sola lettura nello stesso dialog di dettaglio già esistente
  in `combattimento_tab.py`, nessuna automazione aggiuntiva.

## Effort stimato (solo i punti 1-3 sopra: tracker + rubrica + creazione)

Feature grande, paragonabile per scope alla creazione dell'intero sistema Import/Export
personaggio (3 tabelle nuove, 1 nuovo repository, 2-3 nuove view, refactoring di codice
condiviso da `combattimento_tab.py`, test end-to-end su DB temporaneo isolato per ogni
CRUD e per il flusso di turno/iniziativa). Da trattare come sessione dedicata, non una
modifica rapida.

---

# Estensione del design (2026-07-24) — 7 strumenti aggiuntivi

Ampliamento deciso con Davide via `AskUserQuestion` dopo aver consultato l'indice della
**Guida del Dungeon Master** (`Guida del Dungeon Master - 5a e - AA.VV_.pdf`, 319 pagine,
mai usata come fonte in questo progetto prima d'ora — stessa regola di sourcing rigorosa
già in vigore per il PHB/Manuale dei Mostri: solo testo letto direttamente dal PDF italiano,
mai da altre edizioni/lingue/fonti web). Confermati **4 strumenti "principali"** (Calcolatore
Difficoltà Incontro, Note di Campagna del Master, Generatore Tesori Casuali, Compendio
Oggetti Magici) e **3 "minori"** (Generatore Trappole, Riferimento Malattie/Veleni/Follia,
Generatore Incontri per Ambiente) — tutti e 7 confermati da Davide, nessuno scartato.

Per ciascuno: fonte esatta nella DMG (capitolo/pagina/riga nel dump `pdftotext -layout`),
struttura dei dati, e — onestamente — la scala dello sforzo di trascrizione, perché **due di
questi 7 punti sono progetti di trascrizione su scala bestiario**, non "aggiungi una vista".

## 4. Calcolatore Difficoltà Incontro

**Fonte**: Cap.3 "Creare le Avventure" (DMG dump righe ~5300-5450) — sistema "Costruire un
Incontro Equilibrato": tabella **"Soglie di PE per Livello del Personaggio"** (4 colonne
Facile/Medio/Difficile/Mortale × 20 righe livello 1-20 — presente nel dump ma con
corruzione OCR evidente su alcune cifre, es. cifre confuse; **va riverificata visivamente**
con `pdftoppm` prima di trascriverla, stessa tecnica già collaudata in questo progetto per
le tabelle del Manuale dei Mostri) + tabella **"Moltiplicatori degli Incontri"** (già estratta
pulita, nessuna ambiguità):

| N. mostri | Moltiplicatore |
|---|---|
| 1 | ×1 |
| 2 | ×1,5 |
| 3-6 | ×2 |
| 7-10 | ×2,5 |
| 11-14 | ×3 |
| 15+ | ×4 |

(con una nota di rettifica: +1 categoria di moltiplicatore se il gruppo ha meno di 3 PG,
-1 categoria se ne ha 6 o più — testo esatto da riverificare insieme alla tabella soglie).

**Semplificazione importante trovata**: la tabella "Punti Esperienza per Grado di Sfida"
(PE-per-CR, Cap.9) **non serve trascriverla** — verificato via Python che `monsters.json`
(444 mostri, già interamente auditato) ha già un campo `xp` valorizzato per ogni mostro,
oltre a `cr`. Il calcolatore può quindi sommare direttamente gli `xp` dei mostri/NPC
aggiunti a un `master_encounter` (vedi schema sopra), senza bisogno di alcuna nuova tabella
di conversione.

**Design**: nessuna nuova tabella DB — calcolo interamente a runtime.
- Input: lista combattenti dell'incontro corrente (da `master_encounter_members`, sia NPC
  con `cr`/`xp` propri sia mostri "adhoc" con XP inserito a mano) + composizione del gruppo
  (livelli dei PG — letti da `characters.level` per i membri `kind="character"` già presenti
  nell'incontro, con possibilità di aggiungere "PG fantasma" solo per livello, per calcolare
  la difficoltà anche prima di sapere chi sarà presente al tavolo).
- Output: XP totale mostri × moltiplicatore (per numero di combattenti, con la rettifica per
  dimensione del gruppo) confrontato contro la somma delle soglie individuali dei PG per la
  fascia Facile/Medio/Difficile/Mortale → etichetta a colori (stesso stile "verde/ambra/rosso"
  già usato altrove nel progetto, es. barra Peso in Inventario).
- Punto di accesso: pulsante "Difficoltà" sempre visibile nell'header di `MasterEncounterView`
  (calcolo live, si aggiorna ad ogni aggiunta/rimozione di combattente) — nessuna vista a sé.

**Effort**: piccolo. Una singola tabella da riverificare a vista (~20 righe × 4 colonne) +
la tabella moltiplicatori già pulita; nessun nuovo file dati oltre a una costante Python
(stessa categoria di `ASI_LEVELS_DEFAULT`/`LEVEL_PROGRESSION` già in `config/settings.py`).

## 5. Note di Campagna del Master

**Nessuna fonte DMG da trascrivere** — è un puro strumento organizzativo, non regolamento.

**Design**: nuova tabella `master_campaign_notes`, stessa forma di `campaign_notes` (già
esistente per `DiaryView`, vedi schema DB in CLAUDE.md) ma **senza** `character_id` — le
note del Master sono indipendenti da qualunque personaggio, campagna-wide:

```sql
master_campaign_notes (
  id TEXT PRIMARY KEY,
  category TEXT NOT NULL,   -- "npc" | "npc_todo" | "place" | "place_todo" | "quest" | "faction" | "event" | "secret"
  name TEXT NOT NULL,
  description TEXT DEFAULT '',
  status TEXT DEFAULT '',   -- libero, dipendente dalla categoria (stesso pattern di CampaignNote)
  tags TEXT DEFAULT '',
  linked_npc_id TEXT REFERENCES master_npcs(id) ON DELETE SET NULL,  -- opzionale: collega una nota a un NPC della rubrica
  created_at, updated_at
)
```

Aggiunte due categorie rispetto a `campaign_notes` esistente: `"event"` (eventi di trama
già accaduti o programmati) e `"secret"` (informazioni riservate al Master, mai visibili
al giocatore — utile perché a differenza di `DiaryView`, che vive dentro la sessione di UN
personaggio e potrebbe teoricamente essere vista dal giocatore che tiene in mano il device,
questa sezione vive solo in "Modalità Master").

UI: stesso layout a due pannelli già collaudato in `DiaryView` (categorie a sinistra, lista
voci della categoria + dettaglio/editor a destra) — nuova vista `MasterNotesView`, terza tab
di `MasterView` insieme a "Rubrica NPC" e "Incontri".

**Effort**: piccolo — riuso quasi 1:1 di un pattern UI già scritto e collaudato (`DiaryView`),
solo con uno schema DB leggermente diverso (niente FK obbligatoria a `characters`).

## 6. Generatore Tesori Casuali

**Fonte**: Cap.7 "Tesori" (DMG dump riga 8610, "TESORI CASUALI") — sistema a doppio livello:
1. **Tesoro Individuale** (monete sparse su un singolo mostro ucciso) — tabelle per fascia
   di CR del mostro (0-4 / 5-10 / 11-16 / 17+), tiro dado percentuale → monete di vario tipo.
2. **Tesoro di Gruppo** (bottino di una tana/covo) — stessa suddivisione per fascia di CR,
   ogni riga dà monete + un certo numero di tiri su:
   - Tabelle **Gemme o Oggetti d'Arte** per fascia di valore (10/50/500/1000/5000 mo — righe
     `dl00` già visibili nel dump alle righe 8884/8910/8977/9076, con un elenco di oggetti
     concreti per fascia, es. "Pugnale da cerimonia in electrum con una perla nera" per la
     fascia da 25 mo, "Coppa d'oro incastonata di smeraldi" per una fascia più alta — righe
     8762/8797 già lette).
   - Tabella **Oggetti Magici** (per fascia di CR, un tiro dado indica su quale "tabella
     oggetto magico" tirare ulteriormente — A/B/C/.../I per rarità/categoria, questo è il
     punto di aggancio col Compendio Oggetti Magici del punto 7: il generatore tira il nome
     dell'oggetto, il Compendio ne fornisce la descrizione completa se già trascritto,
     altrimenti mostra solo il nome).

**Design dati**: nuovo `data/game_data/treasure_tables.json` — tabelle di tiro pure (righe
dado→risultato), non prosa lunga: dimensione contenuta, stessa scala di `feats.json`
(42 voci) o `invocations.json` (32 voci), non paragonabile al bestiario. Struttura prevista:
```json
{
  "individual_by_cr": {"0-4": [...righe...], "5-10": [...], "11-16": [...], "17+": [...]},
  "hoard_by_cr": {"0-4": {"coins": {...}, "gem_art_rolls": N, "magic_item_table": "A"}, ...},
  "gems_by_value": {"10": [...nomi...], "50": [...], "500": [...], "1000": [...], "5000": [...]},
  "magic_item_tables": {"A": [...nomi oggetto...], "B": [...], ...}
}
```

**Design UI**: dialog "Genera Tesoro" (accessibile da `MasterView` o da dentro un
`MasterEncounterView` per generare il bottino di un incontro appena concluso) — scegli
Individuale/Gruppo + fascia di CR → tira → mostra il risultato (monete + lista
gemme/oggetti d'arte estratti + eventuale nome oggetto magico) con un pulsante "Aggiungi
all'inventario di..." che scrive direttamente su `inventory_items`/`currencies` di un
personaggio scelto (riuso diretto di `character_repo.create_inventory_item()`/
`update_currencies()` già esistenti — nessuna nuova funzione di scrittura personaggio).

**Effort**: medio (non piccolo, ma nemmeno paragonabile al bestiario) — sono tabelle di
tiro strutturate, non blocchi statistici o descrizioni narrative lunghe; il grosso del
lavoro è trascrivere con precisione le fasce di valore monetario e gli ~50-100 nomi di
gemme/oggetti d'arte, verificabile in 1-2 sessioni dedicate con lo stesso metodo
`pdftoppm`+lettura visiva già stabilito.

**Aggiornamento 2026-07-24 — Oggetti Insoliti già pronti**: la tabella d100 "Oggetti
Insoliti" (PHB IT p.160-161, cimeli di ambientazione senza effetto meccanico — esclusa a
suo tempo da `adventuring_gear.json` il 2026-07-10) è stata trascritta su richiesta di
Davide e vive già in `equipment/trinkets.json` (100/100 voci, `GameDataLoader.get_trinkets()`/
`get_trinket_by_roll(n)` già disponibili). Non ancora deciso se agganciarla come pulsante
opzionale dentro il dialog "Genera Tesoro" (es. "Aggiungi un Cimelio") o come voce a sé
nella navigazione — decisione da prendere insieme a Davide quando si passa
all'implementazione UI di questo punto.

## 7. Compendio Oggetti Magici

**Fonte**: Cap.7, sotto-sezione "Oggetti Magici" — confermato dall'indice che occupa le
**pagine 135-214 del libro (~80 pagine)**. Formato di ogni voce (verificato leggendo diversi
esempi nel dump, es. righe 10644/10969/10981/11016/11048/11106/11136/11145/11152):
```
<Nome Oggetto>
Oggetto <categoria>, <rarità> [(richiede sintonia [da <classe/vincolo>])]
<descrizione completa, uno o più paragrafi>
```
Categorie viste finora: "Oggetto meraviglioso" (wondrous item) — il libro ne ha altre
(Armi, Armature, Anelli, Bacchette, Bastoni, Pergamene, Pozioni, Verghe — stesse 8-9
categorie standard 5e). Rarità: Comune/Non Comune/Raro/Molto Raro/Leggendario/Artefatto
(confermate citate nel testo delle regole generali, righe 9200-9260 già lette: sezioni
"Cariche", "Resilienza degli Oggetti Magici", "Tratti Speciali", + le regole di
identificazione/sintonizzazione/attivazione già lette per intero).

**Stima realistica della scala**: 80 pagine di catalogo A-Z, verosimilmente **250-350+
oggetti** (per confronto: il Manuale dei Mostri ha 444 blocchi statistici su 353 pagine —
densità di testo per oggetto magico è simile o leggermente inferiore a un blocco mostro
medio, ma il numero di pagine è comunque un quinto del Manuale dei Mostri, quindi un ordine
di grandezza plausibile è "qualche centinaio di voci"). **Questo è, con tutta onestà, un
secondo progetto di trascrizione su scala bestiario** — il Manuale dei Mostri ha richiesto
~25 sessioni/batch di lavoro dedicato (`pdftoppm` pagina per pagina, verifica di chiusura
ad ogni batch, correzione di contaminazioni OCR) per 444 voci; un compendio di oggetti
magici di scala comparabile richiederebbe lo stesso tipo di impegno pluri-sessione.

**Raccomandazione esplicita**: **non bundlare la trascrizione completa nella v1 della
Sezione Master**. Proposta:
1. La v1 della Sezione Master implementa lo **schema dati e la UI del compendio** (vista
   sfogliabile, ricerca per nome/categoria/rarità, dialog di dettaglio) con un
   `magic_items.json` che parte **vuoto o con una manciata di oggetti-esempio** trascritti
   a mano per collaudare il formato.
2. Il popolamento completo del compendio diventa un **progetto dedicato separato**,
   esattamente come fu il bestiario — batch per batch, pagina per pagina, con checklist
   di audit in CLAUDE.md, su un ritmo di sessioni scelto da Davide (non bloccante per il
   resto della Sezione Master).

**Design dati** (`data/game_data/magic_items.json`, stessa lista piatta di `monsters.json`):
```json
{
  "name": "...", "category": "Oggetto Meraviglioso|Arma|Armatura|Anello|Bacchetta|Bastone|Pergamena|Pozione|Verga",
  "rarity": "Comune|Non Comune|Raro|Molto Raro|Leggendario|Artefatto",
  "requires_attunement": true, "attunement_restriction": "solo da un mago",
  "description": "...", "source_page": "..."
}
```
`GameDataLoader.get_magic_items()`/`get_magic_item(name)`/`get_magic_item_names(rarity=None, category=None)`
— stesso pattern lazy-load-e-cache già usato per `get_weapons()`/`monsters.json`.

**Design UI**: `MagicItemCompendiumView` (browsabile da `MasterView`, ma utile anche al
giocatore in sola lettura per consultazione — da valutare se esporla anche fuori dalla
Modalità Master) — ricerca testo + filtro rarità/categoria, card cliccabile → dialog
descrizione completa, stesso stile già consolidato per `FeatsView`/il picker bestiario.

**Effort**: **grande, su scala bestiario** — esplicitamente da NON considerare "poco
lavoro", e da non promettere completo nella stessa sessione che implementa il resto della
Sezione Master.

### Procedura di riferimento per il popolamento (quando si deciderà di iniziare)

Stesso identico metodo già collaudato per `monsters.json` (444 mostri, ~25 batch/sessioni),
riadattato agli oggetti magici. Da seguire alla lettera quando si apre la sessione dedicata,
senza bisogno di re-inventare l'approccio:

1. **Fonte unica**: `Guida del Dungeon Master - 5a e - AA.VV_.pdf`, pagine 135-214. Mai altre
   fonti (non il web, non l'edizione 2024, non l'inglese) — stessa regola critica di sempre.
2. **Mai `pdftotext`/OCR per il contenuto, nemmeno con `-layout`/`-raw`** — solo per
   *localizzare* una voce (già fatto: righe 10644/10969/10981/11016/11048/11106/11136/11145/11152
   nel dump di ricognizione). Il contenuto reale si legge SOLO da `pdftoppm -r 150` (alzare a
   `-r 200` se un blocco specifico risulta illeggibile), una pagina alla volta, con lettura
   visiva diretta dell'immagine — mai indovinare un valore poco leggibile: segnalarlo a Davide.
3. **Decidere il range di pagine PRIMA di iniziare a trascrivere** — un intervallo contiguo
   (es. "pag. 135-150") o una categoria completa (es. "tutte le Pergamene"), mai l'intero
   compendio in un colpo solo. Stessa logica già adottata per `equipment/*.json` (un file alla
   volta) e per il primo batch di `monsters.json`.
4. **Schema dati obbligatorio per ogni voce** (già bozzato sopra, non cambiare senza
   controllare anche il codice consumer una volta scritto): `name`, `category`, `rarity`,
   `requires_attunement`, `attunement_restriction`, `description` (testo integrale del
   manuale, non riassunto), `source_page` (per verificabilità futura, come già fatto per
   `monsters.json`).
5. **Un piccolo script Python usa e getta per ogni batch** (stesso pattern degli script
   `build_monsters_batch_*.py` già usati e poi rimossi per il bestiario): costruisce un dict
   con le voci trascritte in quella sessione, carica `magic_items.json` esistente, **sostituisce**
   (per nome, case-insensitive) le voci già presenti ma da correggere, **aggiunge** quelle
   assenti, poi riscrive il file con `json.dump(..., ensure_ascii=False, indent=2)`. Rimuovere
   lo script a fine batch (richiedere permesso via `allow_cowork_file_delete` se serve).
6. **Verifica di chiusura ad ogni batch, sempre uguale**: JSON sintatticamente valido; ogni
   nuova voce ha tutti i campi obbligatori del punto 4 (script di controllo automatico, non a
   occhio); le voci NON toccate in questo batch restano identiche a prima (nessuna regressione
   silenziosa); `py_compile` sul modulo consumer (`game_data_loader.py` e l'eventuale
   `MagicItemCompendiumView`) pulito dopo ogni scrittura.
7. **Aggiornare la checklist in CLAUDE.md alla fine di ogni batch** con il nuovo conteggio
   (`N/~300`, stima da confermare a fine lavoro), l'elenco degli oggetti completati in quel
   batch e il range di pagine coperto — stesso identico stile già usato per i batch di
   `monsters.json` in "Note Importanti".
8. **Se un batch rivela un problema strutturale** (es. un oggetto con meccanica di cariche/
   ricarica complessa, o una tabella di sotto-opzioni come le Vesti Elementali, che non entra
   nello schema a 7 campi sopra) — fermarsi e discuterne con Davide prima di estendere lo
   schema a metà lavoro, non improvvisare.
9. **Riconciliazione finale contro l'indice del libro** (se la DMG ha un indice alfabetico
   degli oggetti magici, come il Manuale dei Mostri lo ha per le creature) — stesso passo che
   ha chiuso l'audit dei 444 mostri: confrontare programmaticamente ogni nome dell'indice
   contro `magic_items.json` per intercettare lacune sfuggite ai singoli batch, prima di
   dichiarare il compendio completo.

## 8. Generatore Trappole

**Fonte**: Cap.5 "Ambienti delle Avventure" (DMG dump righe ~7710-7900+), sezione
"Trappole" — **sistema compatto e completo**, già letto per intero:
- Meccaniche generali: innesco, individuazione (Percezione attiva/passiva), disinnesco
  (Indagare + Destrezza con arnesi da scasso, o Intelligenza (Arcano) per le trappole
  magiche), trappole complesse (agiscono a iniziativa propria, come un mini-combattimento).
- **Tabella "Bonus di Attacco e CD dei Tiri Salvezza delle Trappole"** (3 righe):

  | Pericolo | CD Tiro Salvezza | Bonus di Attacco |
  |---|---|---|
  | Imprevisto | 10-11 | da +3 a +5 |
  | Pericoloso | 12-15 | da +6 a +8 |
  | Letale | 16-20 | da +9 a +12 |

- **Tabella "Gravità dei Danni per Livello"** (4 fasce di livello × 3 gravità = 12 celle,
  valori in dadi d10):

  | Livello PG | Imprevisto | Pericoloso | Letale |
  |---|---|---|---|
  | 1°-4° | 1d10 | 2d10 | 4d10 |
  | 5°-10° | 2d10 | 4d10 | 10d10 |
  | 11°-16° | 4d10 | 10d10 | 18d10 |
  | 17°-20° | 10d10 | 18d10 | 24d10 |

- **Esempi di trappole nominate** (elenco alfabetico nel manuale, letti finora: Ago
  Avvelenato, Crollo del Tetto, Dardi Avvelenati, Fossa [4 varianti: Semplice/Nascosta/
  Richiudibile/con meccanismo aggiuntivo], Sfera Rotolante — la lettura si interrompe qui
  nella ricognizione attuale, il capitolo prosegue oltre in ordine alfabetico, presumibilmente
  altre 5-10 voci: da verificare completando la lettura visiva delle pagine successive).

**Design dati**: nuovo `data/game_data/traps.json`:
```json
{
  "danger_table": [{"level":"Imprevisto","save_dc":"10-11","attack_bonus":"da +3 a +5"}, ...],
  "damage_by_level": [{"char_level_range":"1-4","imprevisto":"1d10","pericoloso":"2d10","letale":"4d10"}, ...],
  "example_traps": [{"name":"Ago Avvelenato","type":"meccanica","description":"..."}, ...]
}
```

**Design UI**: "Generatore Trappole" — due modalità: (a) **Suggerisci** (scegli livello PG
+ gravità desiderata → mostra CD/bonus attacco/dado danno suggeriti dalle 2 tabelle, per
progettare una trappola custom al volo), (b) **Sfoglia Esempi** (lista delle trappole
nominate del manuale, con testo completo, stesso stile card-e-dialog di `FeatsView`).

**Effort**: piccolo — le 2 tabelle numeriche sono già completamente trascritte qui sopra;
resta solo da completare la lettura degli esempi nominati rimanenti (poche pagine) prima
dell'implementazione.

## 9. Riferimento Malattie/Veleni/Follia

**Fonte**: Cap.8 "Condurre il Gioco" (DMG dump righe ~16860-17180) — **già letto per
intero**, contenuto compatto e completo:
- **Malattie**: regole generali (uno strumento narrativo, non un sistema meccanico rigido)
  + 3 malattie di esempio interamente trascritte nella lettura: **Epidemia Fognaria**
  (CD 11 Costituzione, indebolimento cumulativo), **Febbre da Gallina** (CD 13, risate
  spasmodiche/incapacitato, contagiosa), **Vista Putrefatta** (CD 15, penalità crescente
  alla vista fino a cecità, cura con fiore Occhiolucente).
- **Veleni**: 4 tipi di somministrazione (Contatto/Ferimento/Inalazione/Ingestione, regole
  generali già lette) + **tabella "Veleni" completa, 14 voci con prezzo**:

  | Veleno | Tipo | Prezzo |
  |---|---|---|
  | Essenza di etere | Inalazione | 300 mo |
  | Fumi di othur bruciato | Inalazione | 500 mo |
  | Lacrime di mezzanotte | Ingestione | 1.500 mo |
  | Malizia | Inalazione | 250 mo |
  | Muco di vermeiena | Contatto | 200 mo |
  | Olio di taggit | Contatto | 400 mo |
  | Sangue dell'assassino | Ingestione | 150 mo |
  | Siero della verità | Ingestione | 150 mo |
  | Tintura pallida | Ingestione | 250 mo |
  | Torpore | Ingestione | 600 mo |
  | Veleno di serpente | Ferimento | 200 mo |
  | Veleno di verme purpureo | Ferimento | 2.000 mo |
  | Veleno di viverna | Ferimento | 1.200 mo |
  | Veleno drow | Ferimento | 200 mo |

  — con la meccanica completa (CD, danno, effetto) di ognuno dei 14 già trascritta nella
  lettura di questa sessione (es. "Veleno Drow: CD 13 Costituzione, altrimenti avvelenato
  1 ora; se fallito di 5+, anche privo di sensi finché avvelenato").
- **Follia**: 3 tabelle `d100` complete, già interamente lette e trascritte in questa
  sessione — **Follia Temporanea** (9 fasce, dura 1d10 minuti), **Follia Duratura**
  (11 fasce, dura 1d10×10 ore), **Follia Indeterminata** (11 fasce, un difetto permanente
  finché curato — utile anche come generatore di difetti di personalità "seri" per NPC).

**Design dati**: nuovo `data/game_data/diseases_poisons_madness.json`, tre sezioni
(`diseases`, `poisons`, `madness_tables`) — dato interamente pronto da questa ricognizione,
nessuna ambiguità residua, trascrizione diretta senza bisogno di ulteriori letture visive
(il testo estratto qui è già pulito, nessuna corruzione OCR evidente in questa sezione).

**Design UI**: `HealthHazardsReferenceView` (o sezione dentro `MasterView`) — 3 sotto-tab,
sola lettura, card cliccabili con dialog descrizione completa (malattie/veleni) o tabella
di tiro visualizzata direttamente (follia, con un pulsante "Tira" che estrae una riga
casuale, utile al tavolo).

**Effort**: piccolo — dato già completamente estratto e verificato in questa sessione di
ricognizione, pronto per la trascrizione diretta in JSON senza ulteriori letture PDF.

## 10. Generatore Incontri Casuali per Ambiente

**Gap reale trovato, richiede una decisione di scope prima di procedere** (a differenza
degli altri 6 punti, qui **non esiste nella DMG una tabella pronta mostro-per-ambiente**
da trascrivere direttamente):

- **Appendice B "Liste dei Mostri"** (già nota, usata anche per altre feature del
  progetto) organizza i 444 mostri **solo per Grado di Sfida**, non per ambiente/terreno.
- **Cap.3 "Creare le Avventure"**, sezione "Creare le Tabelle degli Incontri Casuali"
  (dump righe ~5609-5686, letta per intero in questa sessione) fornisce **solo una guida
  metodologica** ("come costruirti la tua tabella") + **UN SOLO esempio completamente
  lavorato**: la tabella "Incontri nella Foresta Silvana" (menzionata ma il suo contenuto
  numerico riga-per-riga non risulta ancora estratto in questo dump — richiederebbe
  un'ulteriore lettura mirata se si vuole comunque usarla). Il testo di guida elenca però
  esplicitamente, in prosa, creature tipiche per 2 ambienti come esempio didattico (non
  come tabella pronta): **Foresta** (centauri, draghi fatati, pixie, spiritelli, driadi,
  satiri, cani intermittenti, alci, orsigufo, treant, gufi giganti, unicorno — con
  aggiunte se la foresta è popolata da elfi o minacciata da gnoll) e un accenno a
  **Deserto** (wight in un'oasi, drago blu su un promontorio — solo 2 esempi narrativi,
  non una lista).

**Conclusione onesta**: il manuale NON offre un dataset ambiente→mostro pronto e completo
per tutti gli ambienti standard (foresta/palude/montagna/deserto/costa/underdark/ecc.) —
solo una guida a costruirselo da soli più un singolo esempio parziale. Costruire un
generatore per ambiente richiederebbe una delle due strade seguenti, da **discutere con
Davide prima di implementare** (non una scelta arbitraria da prendere in autonomia, per
la stessa regola "non inventare dati" già al centro di questo progetto):

1. **Trascrivere solo l'esempio "Foresta Silvana"** del manuale (l'unico realmente
   completo e verificabile) come singola tabella dimostrativa, lasciando gli altri
   ambienti vuoti finché non si trascriveranno a loro volta (stesso principio di
   crescita incrementale già proposto per il Compendio Oggetti Magici).
2. **Costruire le tabelle per ambiente attribuendo manualmente un tag "ambiente tipico"**
   a ciascuno dei 444 mostri già in `monsters.json`, usando come riferimento il fatto che
   il Manuale dei Mostri stesso spesso descrive l'habitat nella prosa introduttiva di
   ogni creatura (non ancora verificato se questo testo prosa esiste per ogni mostro nel
   file già trascritto, dato che l'audit del bestiario si è concentrato sui blocchi
   statistici meccanici, non sulla prosa di ambientazione) — questo richiederebbe una
   nuova passata di lettura per verificare se l'informazione è già disponibile nel PDF
   sorgente o se andrebbe dedotta, il che not va mai fatto senza fonte primaria.

**Raccomandazione**: partire dalla strada 1 (piccola, sicura, subito fattibile) e
posticipare la strada 2 (tagging sistematico di 444 mostri) a una sessione dedicata
successiva, con lo stesso disciplinare "fonte primaria o niente" già rispettato in tutto
il resto di questo progetto.

**Design UI** (per la sola tabella Foresta Silvana, v1): dialog "Genera Incontro per
Ambiente" — scegli ambiente (dropdown, inizialmente solo "Foresta") → tira sulla tabella
→ mostra il risultato (nome mostro/evento, con link diretto alla scheda del bestiario se
è un mostro con `source_page` in `monsters.json`).

**Effort**: piccolo per la v1 limitata a un solo ambiente dimostrativo; il tagging
sistematico di tutti i 444 mostri per ambiente (se Davide lo vorrà in futuro) è uno sforzo
a parte, di scala paragonabile a un audit dati come quelli già fatti nel bestiario ma più
piccolo (un singolo campo aggiuntivo per mostro, non un intero blocco statistico).

---

## Riepilogo scala dello sforzo (tutti e 10 i punti)

| # | Strumento | Scala |
|---|---|---|
| 1-3 | Tracker combattimento + Rubrica NPC + Creazione | **Grande** (vedi sopra, ~Import/Export) |
| 4 | Calcolatore Difficoltà Incontro | Piccolo |
| 5 | Note di Campagna del Master | Piccolo (riuso pattern `DiaryView`) |
| 6 | Generatore Tesori Casuali | Medio |
| 7 | Compendio Oggetti Magici | **Grande, su scala bestiario — da NON bundlare in v1**, solo schema+UI+pochi esempi ora |
| 8 | Generatore Trappole | Piccolo (dati già quasi interamente estratti in questa sessione) |
| 9 | Riferimento Malattie/Veleni/Follia | Piccolo (dati già interamente estratti in questa sessione) |
| 10 | Generatore Incontri per Ambiente | Piccolo per v1 (1 solo ambiente demo), grande se esteso a tutti gli ambienti/444 mostri |

**Raccomandazione complessiva**: una v1 realistica della Sezione Master implementa i punti
1-6 + 8 + 9 + 10(v1 ridotta) in una o più sessioni dedicate (tutti "piccoli/medi" salvo il
nucleo 1-3 già scoping-ato come "grande" a sé), con il punto 7 (Compendio Oggetti Magici)
presente solo come **schema dati + UI vuota/dimostrativa**, il cui popolamento completo
diventa un progetto a parte — esattamente come fu il Manuale dei Mostri — da programmare
quando Davide vorrà dedicarci le sessioni necessarie.

Nessun codice ancora scritto per nessuno dei 10 punti. Prossimo passo: conferma di Davide
su questa suddivisione (in particolare sul trattamento separato del Compendio Oggetti
Magici) prima di iniziare l'implementazione.
