# Changelog Storico — Note Importanti

> Log cronologico dettagliato di bug corretti, decisioni architetturali, bug report di Davide e relative
> analisi/fix, con verifica end-to-end per ciascuno. **Prima di correggere un bug o affrontare un gap funzionale,
> cercare (grep) qui il termine pertinente per verificare se è già stato risolto in passato** — è lo scopo primario
> di questo file. È il file più corposo del progetto (era quasi metà di CLAUDE.md): non va letto per intero, va
> interrogato per parola chiave.

## Note Importanti

- **Audit gestione risorse di classe e slot incantesimo (2026-07-09)** — completata la revisione di tutte e 12 le
  classi, Davide ha chiesto una verifica architetturale: l'app traccia correttamente slot incantesimo e risorse a
  consumo (Furia, Ki, Incanalare Divinità, Imposizione delle Mani, Punti Stregoneria, Ispirazione Bardica, Recupero
  Arcano, ecc.)? Risultato dell'analisi + fix applicati:
  - **Slot incantesimo**: già gestiti bene. `character_repo.py` ha tre tabelle PHB complete (`_FULL_CASTER_SLOTS`,
    `_HALF_CASTER_SLOTS`, `_WARLOCK_SLOTS` — quest'ultima già gestiva correttamente il caso speciale del Warlock:
    tutti gli slot allo stesso livello, ripristino a riposo breve). `auto_init_spell_slots()` le applica in base a
    classe+livello.
  - **Risorse di classe** (`ClassResource` + `get_class_resource_defaults()` in settings.py + UI in
    `combattimento_tab.py`): sistema generico già esistente (cerchietti o counter −/+, reset breve/lungo). Trovati
    e corretti 3 bug: (1) **Incanalare Divinità del Chierico** compariva già al lv1 invece che al lv2 → aggiunto
    guard `if level >= 2`; (2) **Azione Impetuosa del Guerriero** (la risorsa era ancora chiamata col nome obsoleto
    "Baldanza d'Azione" — allineato al nome corretto già in guerriero.json — e compariva dal lv1 invece che dal
    lv2) → rinominata e aggiunto guard `if level >= 2`; rinominata anche "Ripresa"→**"Recupera Energie"** per
    coerenza col nome feature corretto; (3) **Furia del Barbaro** era cappata a 6 usi anche al lv20, ma nel PHB al
    lv20 diventa illimitata → aggiunto un nuovo `display_type: "unlimited"` (badge "∞ Illimitata" invece dei
    cerchietti) gestito in `combattimento_tab.py`.
  - **Bug più serio trovato durante l'implementazione, non nella lista originale**: `init_class_resources()` (che
    ricalcola i pool in base al livello) veniva chiamato SOLO alla creazione del personaggio e in modo lazy nella
    tab Combattimento (solo se la lista risorse era vuota) — **mai durante il level-up**. Risultato: pool come
    Furia, Punti Ki, Punti Stregoneria, Incanalare Divinità, Imposizione delle Mani restavano congelati al valore
    calcolato alla creazione, senza scalare mai con i livelli successivi. Fix: `init_class_resources()` ora viene
    chiamato anche a ogni level-up e level-down in `profilo_tab.py` (accanto a `auto_init_spell_slots()`, stesso
    pattern), e la tab Combattimento ora sincronizza SEMPRE le risorse a ogni apertura (non solo se vuote) — la
    funzione è idempotente e già gestiva aggiunta/aggiornamento/rimozione delle risorse obsolete, quindi il fix è
    stato un semplice "chiamarla più spesso", nessun rischio di regressione.
  - **Rimosso un duplicato per il Warlock**: esisteva sia la risorsa "Slot del Patto" (`ClassResource`, sezione
    "Risorse di Classe") sia gli slot reali già corretti nella sezione "Slot Incantesimo" (tramite
    `_WARLOCK_SLOTS`) — stesso dato tracciato due volte in due tabelle indipendenti, a rischio di disallineamento
    (usare uno slot da una sezione non aggiornava l'altra). Rimossa la voce duplicata da
    `get_class_resource_defaults()`; grazie al fix precedente (sync ad ogni apertura tab), le voci "Slot del Patto"
    già salvate per personaggi Warlock esistenti verranno rimosse automaticamente al prossimo caricamento della tab
    Combattimento.
  - **Entrambi i punti in sospeso implementati il 2026-07-09**:
    - **Incantesimi Flessibili (Stregone)** — nuova sotto-sezione "Incantesimi Flessibili" in
      `combattimento_tab.py` (`_section_flexible_casting`, dentro "Risorse di Classe", visibile solo se il
      personaggio ha la risorsa "Punti Stregoneria"): due Dropdown + bottoni — "Crea Slot" (spende punti
      stregoneria per un nuovo slot temporaneo, costo letto da `stregone.json → spell_slot_creation_cost`, unica
      fonte dato) e "Converti" (sacrifica uno slot esistente per punti stregoneria pari al suo livello).
      Validazione con `AlertDialog` di errore se punti insufficienti o nessuno slot disponibile. Effetto
      collaterale corretto in `_section_riposo_lungo`: il riposo lungo ora richiama anche `auto_init_spell_slots()`
      (non solo `reset_all_spell_slots()`) per **rimuovere gli slot temporanei creati**, coerente con la regola PHB
      "spariscono al riposo lungo" — prima questa chiamata mancava e uno slot creato con Incantesimi Flessibili
      sarebbe rimasto per sempre nel totale.
    - **Scelte di classe mai mostrate** — nuova sezione "Scelte di Classe" in `profilo_tab.py` (`_build_talenti`,
      tra i Talenti e la Metamagia — nota terminologica: questa è la posizione nel metodo Python `_build_talenti`,
      NON la tab "Talenti"/`FeatsView`, che è un concetto di gioco distinto — Davide l'ha segnalato il 2026-07-09,
      nessuna abilità di classe è un "talento" nel senso PHB del termine): mostra `fighting_style`, `totem_animal`,
      `land_terrain` e `dragon_ancestry` — ognuno visibile solo se il campo è valorizzato. `pact_boon` del Warlock
      resta nella sua sezione dedicata preesistente, invariata.
- **Audit + implementazione bonus permanenti alle statistiche da abilità di classe (2026-07-09, richiesta separata
  di Davide)** — dopo la nota precedente, Davide ha chiesto: le abilità di classe/sottoclasse che aumentano una
  statistica in modo permanente (non temporaneo) vengono applicate in automatico ai valori reali del personaggio,
  come già avviene per i talenti (`bonus_data` + `remove_feat_with_bonuses()`/`undo_level()`)? Risposta: no,
  nessuna lo era. Scansionate tutte e 12 le classi, i casi trovati sono stati categorizzati in 3 gruppi (confermato
  da Davide prima di implementare):
  - **Categoria A — bonus fisso incondizionato** (sempre applicabile a prescindere da equipaggiamento/situazione):
    unico caso trovato, **Stregone, Discendenza Draconiana → Resilienza Draconica, +1 PF massimo per livello da
    stregone** (cumulativo, PHB). Implementato con un pattern nuovo e diverso da quello dei talenti: **non** una
    "ricevuta" `bonus_data` fissa salvata una tantum, ma una funzione che **ricalcola il totale da zero a ogni
    chiamata** in base al livello attuale — `get_permanent_class_hp_bonus(class_name, subclass, level) -> int` in
    `config/settings.py`, che restituisce il bonus TOTALE accumulato fino a quel livello (non un delta; chi chiama
    calcola la differenza tra nuovo e vecchio livello). Motivo della scelta architetturale: a differenza di un
    talento (bonus fisso assegnato una volta), questo bonus scala automaticamente col livello, quindi "ricalcolare
    sempre" è più robusto di "salvare una ricevuta e sperare che resti sincronizzata". Punti di applicazione:
    `wizard_view.py` e `manual_form.py` (alla creazione, se il personaggio parte già a un livello con la
    sottoclasse impostata), `profilo_tab.py → do_level_up` (aggiunge il delta a `hp_max`/`hp_current`) e
    `do_level_down` (lo sottrae, simmetrico alla stima PF persi). Testato con script Python standalone su più
    livelli.
  - **Categoria B — bonus condizionato all'equipaggiamento attuale** (richiede ricalcolo dinamico, non una ricevuta
    fissa): riscritta per intero `calculate_and_update_ca()` in `character_repo.py` per includere, oltre alla
    formula armatura/scudo già esistente:
    - **Monaco** (Difesa Senza Armatura): 10 + mod DES + mod SAG, valida solo se non indossa né armatura né scudo
    - **Barbaro** (Difesa Senza Armatura): 10 + mod DES + mod COS, valida se non indossa armatura (lo scudo è permesso e si somma)
    - **Stregone con Discendenza Draconica** (Resilienza Draconica): 13 + mod DES, valida se non indossa armatura
    - **Stile di Combattimento "Difesa"** (Guerriero/Paladino/Ranger): +1 CA, solo se indossa un'armatura
    - Il pattern segue esattamente quello già esistente per armatura/scudo: nessun campo salvato, tutto ricalcolato
      da `dex/con/wis_score` + `class_name`/`subclass`/`fighting_style` + inventario equipaggiato ogni volta che la
      funzione viene chiamata. Punti di chiamata aggiunti (prima esisteva solo in `inventario_tab.py` al toggle
      equipaggiamento): `profilo_tab.py → do_level_up` e `do_level_down` (un ASI su DES/COS/SAG o un cambio
      sottoclasse può alterare la CA), `wizard_view.py` e `manual_form.py` (subito dopo la creazione, così un
      Monaco/Barbaro/Stregone Draconiana ha la CA corretta da subito, non solo dopo la prima modifica manuale
      dell'inventario). Testato con script Python standalone: Monaco/Barbaro/Stregone Draconiana senza armatura,
      Guerriero+Difesa+armatura leggera, Barbaro+scudo, Monaco+scudo (perde la Difesa Senza Armatura, come da
      regola) — tutti i valori confermati corretti.
  - **Categoria C — non rappresentabile come numero fisso** (es. Istinto Ferino del Barbaro: vantaggio a un tiro,
    non un bonus numerico): **nessuna meccanica da introdurre**, per decisione esplicita di Davide — è già coperta
    dalla sezione generica cliccabile "Abilità di Classe" in Combattimento (il giocatore legge la descrizione e
    applica l'effetto a mano, es. tira 2d20 e prende il più alto).
  - **Bug reale scoperto durante il testing di verifica di Categoria B** (non nella richiesta originale, trovato
    scrivendo lo script di test): `character_repo.create()` non ha mai salvato le colonne `dragon_ancestry`,
    `fighting_style`, `totem_animal`, `land_terrain`, `pact_boon`, `initiative_bonus` nell'INSERT — queste colonne
    esistono nel DB (aggiunte via `_migrate()`/`ALTER TABLE` in un secondo momento) ma erano assenti dalla lista
    colonne/parametri dell'INSERT in `create()`. Risultato pratico: quando wizard/form manuale impostavano
    `char.fighting_style = "Difesa"` (o discendenza draconica, totem, terreno, patto) PRIMA di chiamare
    `character_repo.create(char)`, il valore veniva scartato silenziosamente e il personaggio veniva creato con
    questi campi vuoti — la sezione "Scelte di Classe" e il nuovo bonus CA "Difesa" non avrebbero mai funzionato su
    un personaggio appena creato. Confermato con test end-to-end (`create()` → `get_by_id()` → campo tornava `''`
    invece del valore impostato). **Fix**: aggiunte le 6 colonne mancanti all'INSERT e al dizionario parametri di
    `create()`. Riverificato con lo stesso test: tutti e 6 i campi ora persistono correttamente. Nessun altro punto
    del codebase risultava affetto (l'`UPDATE` generico in `update()` include già tutte le colonne, quindi
    level-up/level-down e le altre modifiche post-creazione non erano toccate dal bug).
  - **Categoria B, parte Velocità — implementata il 2026-07-09 (richiesta separata "risolviamo la sezione b")**:
    prima di scrivere codice, verificato che `character.speed` ha già DUE meccanismi consolidati che un
    ricalcolo-e-sovrascrivi in stile CA avrebbe rotto: (1) override manuale del giocatore (dialog "✎ Modifica CA /
    Velocità" in Combattimento, `combattimento_tab.py → _on_edit_stats_click`), (2) bonus fisso del Talento Mobile
    (+3m) già applicato come ricevuta diretta su `speed` (`profilo_tab.py`, `other_bonuses.speed`). Presentate a
    Davide 3 alternative con pro/contro (ricalcolo-a-display senza persistenza / nuovo campo additivo `speed_bonus`
    stile `ca_bonus` / `base_speed`+ricalcolo totale come la CA) — **scelta confermata: ricalcolo-a-display,
    nessuna modifica al DB o a `character.speed`**.
    - Nuova funzione **`get_effective_speed(character: Character) -> float`** in `character_repo.py` (NON scrive
      mai sul DB, a differenza di `calculate_and_update_ca`): legge `character.speed` come base (già comprensiva di
      override manuale + Talento Mobile) e somma il bonus dinamico se la classe è Monaco o Barbaro e
      l'equipaggiamento attuale lo consente.
    - **Monaco, "Movimento Senza Armatura"** (dal 2° livello, testo confermato in `monaco.json` già ✅): +3 m se non
      indossa armatura né scudo; il bonus non è cumulativo, sale a +4,5 m al 6°, +6 m al 10°, +7,5 m al 14°, +9 m
      al 18° (sostituisce, non si somma ai livelli precedenti).
    - **Barbaro, "Movimento Veloce"** (dal 5° livello, testo confermato in `barbaro.json` già ✅): +3 m se non indossa un'armatura pesante (armatura leggera/media e scudo non ostacolano).
    - Scelta di scope deliberata: il bonus si applica solo alla Camminata. Le velocità speciali
      (Nuoto/Scalata/Volo) mostrate in Esplorazione quando presenti come tratto razziale restano al valore base —
      il PHB descrive entrambe le capacità come bonus alla velocità di movimento a piedi, non alle velocità
      speciali di razza.
    - Punti di chiamata (sola lettura, mai scrittura): `combattimento_tab.py → _section_stats` (box "VELOCITÀ" in
      cima, con indicatore "✦" e colore blu quando il bonus è attivo, mirror visivo del pattern già usato per
      `ca_bonus`), `combattimento_tab.py` tracker movimento del turno (velocità disponibile per il movimento
      effettivo, non solo il numero mostrato), `esplorazione_tab.py → _section_sensi` (riga "Camminata"). Valori
      frazionari (es. 13,5 m) formattati con `:g` per evitare "13.0m" al posto di "13.5m"/"12m".
    - Testato con script Python standalone su tutte le combinazioni classe/livello/equipaggiamento (Monaco a ogni
      soglia 1/2/6/10/14/18, con armatura/scudo che disattiva il bonus; Barbaro a lv4/5 con armatura
      leggera/scudo/pesante; classe non Monaco/Barbaro invariata; scenario con Talento Mobile già applicato sul
      base) — tutti i valori confermati corretti.
- **Audit sistematico di stabilità (2026-07-09, richiesta esplicita di Davide prima di procedere alle razze)** —
  prima di continuare la revisione dati, Davide ha chiesto una verifica completa con test di tutti i meccanismi
  implementati finora (CRUD, risorse di classe, slot incantesimo, level-up/down, bonus talenti) per assicurarsi che
  la base fosse stabile. Eseguiti test automatizzati (script Python standalone, DB temporaneo isolato, mai il DB
  reale) su: round-trip completo di ogni campo di
  `Character`/`Weapon`/`InventoryItem`/`Currency`/`DiaryEntry`/`CampaignNote`/`CreatureEntry` (110 controlli),
  `calculate_and_update_ca`/`get_effective_speed` su casi limite (armature multiple, DES estrema, classe vuota),
  `get_class_resource_defaults` su tutte le 12 classi × 20 livelli (1216 controlli), `auto_init_spell_slots` contro
  le tabelle PHB, idempotenza di `init_class_resources`, reversibilità bonus talenti/ASI e `undo_level` con più
  talenti sullo stesso livello, validazione strutturale di tutti i 46 file JSON di `game_data/`,
  `get_permanent_class_hp_bonus` e le funzioni di progressione livello/XP/bonus competenza, e l'intera matrice
  `level_manager.get_level_up_steps` per le 12 classi × 20 livelli (746 controlli). Totale >2400 controlli
  automatizzati, tutti passati dopo i fix sotto. Trovati e corretti 3 bug reali (nessuno noto in precedenza):
  1. **`character_repo.create()`/`update()`: colonna `max_prepared_spells_override` assente dall'INSERT/UPDATE
     generico** — stesso tipo di bug già trovato e corretto in precedenza per
     `dragon_ancestry`/`fighting_style`/ecc. (vedi nota Categoria B sopra), sfuggito perché questo campo ha anche
     un setter dedicato (`update_max_prepared_override()`) che la UI usa sempre oggi — nessun impatto pratico
     attuale, ma un difetto latente corretto per coerenza e sicurezza futura. Verificato con un diff automatico
     schema-DB vs colonne INSERT/UPDATE (script Python, `PRAGMA table_info` vs regex sul codice sorgente) che ora
     risulta perfettamente allineato per la tabella `characters`.
  2. **`init_class_resources()`: bug nel merge quando una risorsa passa da/a "illimitata" (sentinel
     `max_value=-1`)** — caso concreto: Barbaro che raggiunge il 20° livello (Furia illimitata, `current_value=-1`)
     e poi scende di nuovo al 19° livello (level-down). La riga `new_current = min(ex.current_value,
     d["max_value"])` calcolava `min(-1, 6) = -1`, quindi `current_value` restava bloccato a `-1` anche se
     `max_value` tornava correttamente a `6` e `display_type` a `"circles"` — la UI avrebbe mostrato un pool di
     Furia rotto/incoerente. Fix: gestiti esplicitamente i due casi limite (nuovo max illimitato → forza sempre
     `-1`; da illimitato a un max finito → riparte a piena carica sul nuovo massimo, non c'è un "usato" reale da
     riportare indietro). Verificato con test su Barbaro lv20→19, lv20→19 dopo un uso di Furia poi risalita a lv20,
     e un salto diretto lv20→lv12.
  3. **`core/level_manager.py`: il Ladro non veniva mai messo in condizione di scegliere le abilità di Maestria
     (Expertise) al 6° livello nel flusso di level-up** — il rilevamento dello step `EXPERTISE` cercava solo la
     sottostringa `"perizia"` nel testo della feature (funziona per il Bardo, che usa letteralmente il termine
     "Perizia" nel PHB), ma il Ladro usa il termine PHB diverso **"Maestria"** per lo stesso meccanismo di gioco
     (già annotato nell'audit di `ladro.json`) — la feature di lv6 `"Maestria (2 altre competenze)"` finiva quindi
     nel ramo generico `FEATURE_AUTO` (solo informativo), e il giocatore non veniva mai mostrato il picker per
     scegliere le 2 abilità aggiuntive. Fix: aggiunta una condizione `class_name == "Ladro" and "maestria" in
     feat_lower`, ristretta esplicitamente alla classe Ladro per non intercettare per errore "Maestria degli
     Incantesimi" del Mago (lv18, feature completamente diversa, nessuna scelta di abilità). Verificato che il fix
     non introduce falsi positivi sul Mago e non rompe il funzionamento esistente per il Bardo (lv3/lv10).
  - **Nessun altro bug trovato.** Slot incantesimo, risorse di classe (inclusi tutti i breakpoint per livello
    confermati contro i valori già documentati in CLAUDE.md), ASI, scelta sottoclasse, invocazioni/metamagia/patto
    del Warlock e Stregone, e tutti i 46 file JSON sono risultati strutturalmente corretti e coerenti.
  - **Osservazione poi risolta dalla revisione manuale (stesso giorno)**: a questo punto dell'audit
    `invocations.json` conteneva 33 voci contro le 32 documentate altrove — sospettata una semplice discrepanza di
    conteggio nella documentazione. La revisione riga-per-riga con Davide (subito dopo, stesso giorno) ha chiarito
    che il conteggio corretto è **32**: la 33ª voce ("Esplosione Accecante") era in realtà una voce
    inventata/inesistente nel manuale, non un errore di conteggio. Vedi la voce ✅ di `invocations.json` nella
    Checklist Revisione Dati PHB per il changelog completo.
- **JSON incantesimi stato attuale**: tutti completati ✅ — chierico, bardo, druido, mago, paladino, ranger,
  stregone, warlock. ⚠️ Vedi però la nota su `incantesimi_chierico.json` nella Checklist Revisione Dati PHB
  (sospetto contaminato da SRD 2024).
- **⚠️ Conflitti di nomenclatura incantesimi cross-file (aperti, 2026-07-03)** — durante la revisione dei domini
  del Chierico, Davide ha confermato dal manuale cartaceo alcuni nomi diversi da quelli già presenti in altri file
  `incantesimi_*.json` condivisi tra classi. Applicati SOLO in `chierico.json` (lista incantesimi di dominio) e in
  `incantesimi_chierico.json` dove non c'era conflitto. Non ancora propagati ai file delle altre classi, che vanno
  verificati quando arriviamo alla loro revisione: "Pelle di Quercia" (in druido.json, ranger.json) → probabilmente
  "Pelle Coriacea"; "Crescita di Piante" (druido, ranger) → probabilmente "Crescita Vegetale"; "Dominare Animale"
  (druido) → probabilmente "Dominare Bestie"; "Passo Arboreo" (ranger) → probabilmente "Traslazione Arborea"; "Nube
  di Foschia" (druido, ranger) → probabilmente "Nube di Nebbia"; "Onda di Tuono" (bardo, stregone) → probabilmente
  "Onda Tonante"; "Ripristino Inferiore" (druido, ranger, chierico) → **confermato "Ristorare Inferiore"** (Davide
  l'ha confermato transcrivendo paladino.json il 2026-07-07, già corretto in quel file — resta da correggere in
  `incantesimi_chierico.json`, `incantesimi_paladino.json`, `incantesimi_ranger.json`, `incantesimi_druido.json` e
  in druido.json/ranger.json/chierico.json quando li revisioniamo); "Ravvivare" (chierico, paladino) →
  probabilmente "Rinascita". Da confermare pagina per pagina quando revisioniamo quei file, non assumere
  automaticamente.
- **⚠️ Trucchetti da Druido sbagliati/mancanti in `incantesimi_druido.json`** (trovato 2026-07-03 controllando i
  trucchetti bonus del Dominio della Natura del Chierico) — "Arte Druidica" nel file dovrebbe essere "Artificio
  Druidico"; "Fiamma Consacrata" secondo Davide **non esiste nel manuale tra i trucchetti da druido** (probabile
  voce inventata/errata, da rimuovere o sostituire); "Randello Incantato" e "Frusta di Spine" non sono affatto
  presenti nel file (solo "Randello" e "Flagello Spinoso" mancano — nomi da correggere quando aggiunti). Corretto
  nel frattempo solo l'elenco `bonus_cantrips_options` di Dominio della Natura in `chierico.json`. Il file
  `incantesimi_druido.json` stesso va corretto quando arriviamo alla sua revisione.
- **⚠️ `bonus_proficiencies` sulle sottoclassi (Chierico, Bardo, Ladro, Barbaro) non è collegato a nessuna logica
  Python** — è un campo dati presente nei JSON ma non letto da wizard/manual_form/level-up (nessuna occorrenza di
  `bonus_proficiencies` fuori dai file JSON). Le competenze bonus di sottoclasse (es. armature pesanti da Dominio
  della Vita, 3 abilità dal Collegio della Conoscenza) NON vengono quindi assegnate automaticamente al personaggio
  oggi. **Piano concordato con Davide (2026-07-03): non implementare ora — si sistema come blocco unico dopo aver
  completato la revisione dati di TUTTI i JSON** (classi, razze, background, incantesimi, feats, invocations).
- **Dominio della Natura, livello 1 — risolto/chiarito (2026-07-03)**: non manca nessuna feature narrativa. A
  livello 1 il dominio concede solo privilegi meccanici, già tutti rappresentati nel JSON: un trucchetto da druido
  a scelta (`bonus_cantrips_choice`/`bonus_cantrips_options`), competenza in un'abilità a scelta tra Addestrare
  Animali/Natura/Sopravvivenza (`bonus_proficiencies`, aggiunta oggi), e competenza nelle armature pesanti
  (`bonus_proficiencies`, già presente). Nessuna voce in `features` necessaria per il livello 1 di questo dominio.
- **⚠️ Possibile refuso ricorrente "Bastone"→"Bastone Ferrato" e "Falce"→"Falcetto"** — confermato da Davide su
  druido.json e mago.json (Bastone→Bastone Ferrato). **Risolto (2026-07-10)**: `tags.json` (che conteneva
  "Bastone"/"Falce" tra le altre forme brevi/sbagliate) è stato eliminato interamente — vedi "Eliminazione di
  `tags.json`" più sopra; `stregone.json → weapon_proficiencies` in realtà aveva già "Bastone Ferrato" per esteso
  (verificato il 2026-07-10 durante il fix dei riferimenti a `tags.json` nei file classe), quindi il refuso lì non
  esisteva più al momento del controllo — nota chiusa.
- **Note "richiede competenza" nell'equipaggiamento** (es. Martello da guerra, Cotta di maglia per il Chierico)
  sono solo informative nel JSON — wizard/manual_form non verificano ancora se la competenza è effettivamente
  posseduta prima di offrire la scelta.
- **Eliminazione di `RACE_DATA` — codice ridotto a sola lettura dai JSON (2026-07-09)** — dopo il completamento
  dell'audit delle 9 razze, Davide ha chiesto di verificare che il codice Python non tenga più copie scritte a mano
  dei dati di regolamento, in modo che aggiungere/correggere una razza (o supportare un'altra edizione in futuro)
  richieda di toccare solo i JSON. Trovato che `RACE_DATA` in `config/settings.py` (dict con bonus
  caratteristica/velocità/scurovisione/tratti per le 14 combinazioni razza-sottorazza) **non era codice morto**:
  veniva letto in 4 punti reali — `core/wizard_engine.py → build_character()` (applicazione EFFETTIVA dei bonus
  caratteristica e della velocità alla creazione), `ui/views/creation_wizard/manual_form.py` (×2: anteprima bonus
  in fase Punteggi, velocità nel riepilogo finale), `ui/views/character_sheet/esplorazione_tab.py` e
  `profilo_tab.py` (sezione "Tratti Razziali"). Conteneva quindi sia gli errori di terminologia già noti (nomi
  tratti sbagliati, tratti inventati) sia un rischio di disallineamento futuro con i JSON ormai corretti.
  - **Fix**: aggiunto un nuovo metodo `GameDataLoader.get_resolved_race(race_name, subrace_name="")` in
    `data/game_data/game_data_loader.py` — legge solo dai JSON in `data/game_data/races/`, somma i bonus
    caratteristica base+sottorazza, risolve velocità/scurovisione (override di sottorazza se presente, altrimenti
    base) e concatena i tratti (lista di dict `{"name","description",...}`, non più stringhe "Nome — descrizione").
    Tollerante: accetta sia il nome della razza base sia direttamente il nome di una sottorazza.
  - Sostituiti tutti e 4 i punti di lettura con questo metodo. In `manual_form.py` questo ha anche eliminato codice
    morto/parzialmente rotto (il merge manuale dei bonus di sottorazza dopo il fallito lookup su `RACE_DATA`). In
    `esplorazione_tab.py`/`profilo_tab.py` la ricerca di velocità speciali (nuoto/scalata/volo) nei tratti ora
    ispeziona `trait["description"]` invece di una stringa flat.
  - **Bug reale scoperto durante l'implementazione, indipendente dal refactor**: in `wizard_view.py` e
    `manual_form.py` la sezione che assegna il bonus flessibile del Mezzelfo (+1 a due caratteristiche a scelta) e
    le 2 abilità di "Versatilità nelle Abilità" era protetta da `if race == "Mezzelf":` — ma `self._review_race`
    per questa razza vale sempre **"Mezzelfo"** (come da `RACES_BASE`, confermato anche dal manuale, che non usa
    mai la forma tronca "Mezzelf"). La condizione non scattava **mai**: ogni Mezzelfo creato via wizard o form
    manuale perdeva silenziosamente questi due tratti PHB. Causa radice: il file
    `data/game_data/races/mezzelf.json` aveva sia il nome-file sia il campo `"name"` interno troncati ("Mezzelf"
    invece di "Mezzelfo"), incoerente con `RACES_BASE` e con `Character.race`. **Fix**: rinominato il file in
    `mezzelfo.json`, corretto il campo `"name"` a "Mezzelfo", corrette le 4 occorrenze del confronto stringa in
    `wizard_view.py`/`manual_form.py` da `"Mezzelf"` a `"Mezzelfo"`.
  - **Fix minore trovato in verifica**: durante il test di `get_race_resource_defaults()` su tutte le razze, il
    `resource.name` interno del tratto "Tenacia Implacabile" del Mezzorco era rimasto "Resistenza Implacabile"
    (nome vecchio) nonostante il nome del tratto fosse già stato corretto in precedenza lo stesso giorno — corretto
    anche questo campo annidato.
  - **Verifica**: script di test standalone — round-trip di `build_character()` per tutte le 14 combinazioni
    razza/sottorazza (bonus caratteristica, velocità, HP tutti confrontati contro i valori precedenti di
    `RACE_DATA`, nessuna regressione), verifica che tutti i moduli importino senza errori, verifica che
    `get_race_resource_defaults()`/`get_race_display_traits()` continuino a funzionare per
    Dragonide/Drow/Tiefling/Mezzorco dopo il rename del file Mezzelfo, scansione automatica di tutti i file razza
    per altre discrepanze nome-tratto/nome-risorsa (nessun'altra trovata). `RACE_DATA` rimosso interamente da
    `config/settings.py` (sostituito da un commento esplicativo). Nessun altro file Python fa più riferimento a
    `RACE_DATA` (verificato via grep).
  - **Follow-up completato lo stesso giorno**: vedi la nota successiva "Eliminazione delle 7 costanti di classe
    duplicate" — il "prossimo giro di audit" qui promesso è stato eseguito subito dopo, nella stessa sessione.
- **Eliminazione delle 7 costanti di classe duplicate — stesso refactor di RACE_DATA applicato ai dati di classe
  (2026-07-09)** — follow-up diretto della nota precedente: dopo RACE_DATA, verificate le 7 liste scritte a mano in
  `config/settings.py` che duplicavano (o avrebbero dovuto duplicare) dati già nei JSON classe:
  `CLASS_SAVING_THROWS`, `FIGHTING_STYLES`, `METAMAGIC_OPTIONS`, `PACT_BOONS`, `TOTEM_ANIMALS`, `LAND_TERRAINS`,
  `MAGO_CANTRIPS`. Risultato della verifica, per categoria:
  - **Duplicati sicuri, 100% coerenti col JSON** (nessun errore di dato, solo duplicazione architetturale): `CLASS_SAVING_THROWS`, `METAMAGIC_OPTIONS`, `PACT_BOONS`, `FIGHTING_STYLES`.
  - **Contenuto corretto ma non strutturato nel JSON**: `TOTEM_ANIMALS` — richiesta una piccola aggiunta a `barbaro.json` (vedi sotto) prima di poter eliminare la costante.
  - **Discrepanza reale ma finora innocua**: `LAND_TERRAINS` conteneva `"Piana"`/`"Sottosuolo"` mentre `druido.json
    → circle_spells` (già auditato) usa `"Prateria"`/`"Underdark"` — nessun bug live perché `land_terrain` è oggi
    solo un campo testo salvato su `Character`, mai usato per filtrare liste di incantesimi; comunque un dato
    sbagliato, corretto sostituendo la fonte con le chiavi di `circle_spells`.
  - **Problema più serio, il JSON stesso non è affidabile**: `MAGO_CANTRIPS` — solo 5 dei 16 nomi combaciavano con
    `incantesimi_mago.json` (che tra l'altro elenca solo 11 trucchetti, con nomi diversi), e quel file è già
    segnalato nella Checklist Revisione Dati PHB come sospetto contaminato da traduzioni dall'inglese/SRD, mai
    auditato riga per riga. Presentata a Davide la scelta se agganciarsi comunque a quel JSON incompleto o
    aspettare il suo audit dedicato; Davide ha indicato una terza opzione migliore, non considerata inizialmente:
    riusare i nomi (16, identici) già presenti e già verificati manuale-alla-mano nelle sottoclassi Cavaliere
    Mistico (`guerriero.json`) e Mistificatore Arcano (`ladro.json`) — la coincidenza esatta tra i due file
    indipendenti rafforza la fiducia che quella lista sia corretta. Il fatto che due sottoclassi di classi diverse
    condividano la stessa identica lista di trucchetti Mago non è un caso: entrambe concedono "trucchetti da mago"
    con le stesse regole PHB.
  - **Dati JSON aggiunti per supportare l'eliminazione**:
    - `paladino.json` e `ranger.json`: aggiunto un array `"options"` all'interno della feature "Stile di
      Combattimento" (livello 2) con i nomi degli stili disponibili per quella classe (Paladino: Combattere con
      Armi Possenti/Difesa/Duellare/Protezione; Ranger: Combattere con Due Armi/Difesa/Duellare/Tiro) — dati già
      confermati testualmente durante l'audit di quelle classi, solo non ancora strutturati come lista.
    - `barbaro.json`: **nessuna aggiunta definitiva** — un primo tentativo aveva aggiunto `"options":
      [{"name":"Orso"},{"name":"Aquila"},{"name":"Lupo"}]` alla feature "Spirito Totemico", ma è stato annullato
      subito dopo su correzione di Davide (vedi voce dedicata subito sotto, "Correzione: rimossa duplicazione
      options in barbaro.json").
    - `mago.json`: **nessuna aggiunta definitiva** — un primo tentativo aveva aggiunto un campo `"cantrip_names"`
      con nota di provenienza, ma è stato annullato subito dopo su correzione di Davide (vedi voce dedicata subito
      sotto, "Correzione: cantrip_names spostato da mago.json a incantesimi_mago.json").
  - **Nuovi metodi `GameDataLoader`** (in `data/game_data/game_data_loader.py`), tutti a sola lettura dai JSON,
    nessuna scrittura: `get_class_saving_throws(class_name)` (converte le chiavi brevi `"str"/"dex"/...` del JSON
    in etichette italiane via `ABILITY_KEYS`/`ABILITY_SCORES`, import locale per evitare un import circolare con
    `config.settings`), `get_fighting_styles(class_name)` (legge `fighting_style_details` per il Guerriero, le
    `options` della feature "Stile di Combattimento" per Paladino/Ranger), `get_metamagic_options()`,
    `get_pact_boons()`, `get_totem_animals()`, `get_land_terrains()` (chiavi di `circle_spells`),
    `get_mago_cantrips()` (vedi sotto per la fonte dato definitiva).
  - **Call site aggiornati**: `wizard_engine.py` non usava direttamente nessuna di queste 7 costanti (solo
    `RACE_DATA`, già sistemato). Aggiornati invece: `manual_form.py` e `wizard_view.py` (dropdown stile di
    combattimento, dropdown trucchetto Alto Elfo, tiri salvezza di classe alla creazione) e `profilo_tab.py`
    (dropdown Patto Warlock lv3, checkbox Metamagia disponibili, dropdown stile combattimento Paladino/Ranger lv2,
    dropdown Totem Barbaro lv3, dropdown Terreno Druido lv2).
  - **Rimozione**: le 7 costanti eliminate da `config/settings.py`, sostituite da due blocchi di commento
    esplicativo (stesso stile/posizione della nota di rimozione di `RACE_DATA`), con riferimento a dove ora vive
    ciascun dato e ai 2 problemi di dati risolti nel percorso (LAND_TERRAINS, MAGO_CANTRIPS).
  - **Verifica**: `py_compile` su tutto l'albero sorgente (esclusi i vendor di build Flutter); import di tutti i
    moduli toccati; test funzionale di ognuno dei 7 nuovi metodi `GameDataLoader` con assert sui valori attesi
    (tutti confermati identici ai dati già auditati); round-trip `build_character()` su 168 combinazioni
    classe×razza/sottorazza (12 classi × 14 combinazioni) — tutte con `hp_max`/`speed` validi, nessuna eccezione;
    grep finale su tutto l'albero `.py` (esclusa `build/`) per ciascuna delle 7 costanti — zero occorrenze fuori
    dai commenti esplicativi in `config/settings.py`.
  - **Non affrontato in questo passaggio**: alcuni file UI (`profilo_tab.py`, `manual_form.py`, `wizard_view.py`)
    istanziano un proprio `GameDataLoader()` locale invece di usare il singleton `game_data` di modulo —
    duplicazione innocua (stesso contenuto JSON) ma non ripulita.
- **Correzione: cantrip_names spostato da mago.json a incantesimi_mago.json (2026-07-09, stessa sessione)** —
  Davide ha segnalato un errore architetturale nella scelta appena fatta sopra: aggiungere `cantrip_names` dentro
  `mago.json` duplicava dati che appartengono esclusivamente a `incantesimi_mago.json` (il file esiste apposta per
  dividere gli incantesimi per classe — il JSON di classe deve dire solo "quanti/quali può scegliere", non ripetere
  il contenuto). Era esattamente lo stesso errore di duplicazione appena eliminato con RACE_DATA e le altre 6
  costanti, commesso di nuovo nel tentativo di risolverlo. Fix applicato su indicazione esplicita di Davide
  ("sostituisci in incantesimo mago tutti i nomi dei trucchetti con quelli giusti e lasciali senza descrizione, poi
  quando facciamo il controllo le mettiamo"):
  - **`incantesimi_mago.json`**: i precedenti 11 trucchetti (livello 0) con nomi sospetti/sbagliati e descrizioni
    complete — "Getto Acido", "Saetta di Fuoco", "Mano del Mago", "Gioco di Prestigio", "Colpo Mirato" (questi 5
    non combaciavano affatto con la lista verificata; gli altri 6 — Illusione Minore/Luce/Messaggio/Raggio di
    Gelo/Riparare/Stretta Folgorante — erano già corretti per coincidenza) — sono stati rimossi interamente e
    sostituiti con **16 voci** corrispondenti ai nomi già verificati in `guerriero.json → Cavaliere Mistico` e
    `ladro.json → Mistificatore Arcano` (confermati identici in entrambi i file, ri-controllati sul posto prima di
    procedere): Amicizia, Colpo Accurato, Dardo di Fuoco, Fiotto Acido, Illusione Minore, Interdizione alle Lame,
    Luce, Luci Danzanti, Mano Magica, Messaggio, Prestidigitazione, Raggio di Gelo, Riparare, Spruzzo Velenoso,
    Stretta Folgorante, Tocco Gelido. Ogni voce ha **solo `name` e `level:0` valorizzati**; tutti gli altri campi
    (`school`, `casting_time`, `range`, `components`, `material`, `duration`, `description`, `higher_levels`) sono
    `null`/vuoti **per scelta esplicita** — non si inventano descrizioni prima dell'audit dedicato. Aggiunta una
    nota top-level `_cantrips_note` che spiega la provenienza dei nomi e lo stato "solo nome verificato,
    descrizione in sospeso". Gli incantesimi di livello 1-9 del file (21 voci) non sono stati toccati.
  - **`mago.json`**: rimossi `cantrip_names` e `_cantrip_names_note` aggiunti in precedenza nella stessa sessione (revert completo, nessuna traccia residua).
  - **`GameDataLoader.get_mago_cantrips()`**: riscritta per leggere `self.get_spells_by_level("mago", 0)` (il
    metodo generico già esistente per gli incantesimi di classe) ed estrarne i nomi, invece di leggere un campo
    dedicato in `mago.json`. Questo significa che la lista si aggiornerà automaticamente, senza toccare il codice,
    quando `incantesimi_mago.json` riceverà il suo audit dedicato e le descrizioni complete.
  - **Verifica**: validazione JSON di `incantesimi_mago.json` (16 trucchetti + 21 incantesimi di livello superiore
    invariati) e di `mago.json`; test funzionale di `get_mago_cantrips()` (16 nomi, contenuto esatto confermato via
    `assert` sull'insieme atteso; confermato che `cantrip_names` non è più presente in `get_class("mago")`); grep
    su tutto l'albero `.py`/`.json` per pattern `.get("description", ...)` usati nei tre punti UI che mostrano
    descrizioni di incantesimi (`combattimento_tab.py`, `spells_view.py`, `profilo_tab.py`) — tutti già proteggono
    con `if desc:`/`or` contro un valore `None`, quindi i nuovi trucchetti senza descrizione non causano crash,
    semplicemente non mostrano la sezione descrizione finché non verrà compilata; `py_compile` sull'intero albero
    sorgente; round-trip `build_character()` su tutte le 168 combinazioni classe×razza — nessuna regressione.
  - **Stato di `incantesimi_mago.json` dopo questa correzione**: resta comunque **non auditato riga per riga** (era
    già segnalato sospetto contaminato in Checklist Revisione Dati PHB) — cambiato solo lo stato dei 16 trucchetti
    da "contenuto probabilmente sbagliato sotto nomi sbagliati" a "nome corretto, contenuto onestamente assente" in
    attesa dell'audit dedicato; i 21 incantesimi di livello 1-9 restano nello stato precedente (mai verificati,
    potenzialmente affetti dallo stesso problema di contaminazione SRD già ipotizzato).
- **Correzione: rimossa duplicazione `options` in barbaro.json (2026-07-09, stessa sessione)** — Davide ha
  segnalato che avevo commesso lo stesso errore di duplicazione anche nella feature "Spirito Totemico" di
  `barbaro.json`: la description di quella feature contiene già per esteso "Scegli un totem: Orso, Aquila o
  Lupo...", quindi l'array `"options": [{"name":"Orso"},{"name":"Aquila"},{"name":"Lupo"}]` aggiunto durante il
  refactor delle 7 costanti ripeteva solo quei 3 nomi senza aggiungere alcuna informazione nuova — a differenza di
  Paladino/Ranger, dove l'array `"options"` di "Stile di Combattimento" seleziona un sottoinsieme dei 6 stili
  canonici definiti in `guerriero.json → fighting_style_details` (dato non altrimenti ricavabile dalla sola
  description di quelle classi, quindi non duplicazione ma informazione strutturale legittima). Fix: rimosso
  l'array `"options"` da `barbaro.json`, la feature "Spirito Totemico" è tornata esattamente allo stato precedente
  a questa sessione (solo `name`+`description`, nessun'altra modifica). `GameDataLoader.get_totem_animals()` non
  legge più da `barbaro.json`: restituisce direttamente i 3 nomi fissi (`["Orso", "Aquila", "Lupo"]`), con un
  commento nel codice che spiega perché — a differenza degli altri 6 metodi di questa categoria, qui non c'è nessun
  dato da "salvare da duplicazione multi-file", solo 3 nomi PHB stabili già scritti per esteso nell'unico posto in
  cui vivono. Verificato: `barbaro.json` validato come JSON, nessun campo `"options"` residuo nella feature,
  `get_totem_animals()` restituisce ancora `["Orso", "Aquila", "Lupo"]`, `py_compile` sull'intero albero sorgente
  senza errori.
- **Audit generale codice — bug e dati hardcoded (2026-07-10)** — su richiesta esplicita di Davide ("controllo su
  tutto il codice... che i dati vengano presi sempre dai json e non siano scritti a mano"), eseguita una scansione
  sistematica di tutto l'albero `.py` (esclusi `build/`/`.venv/`, ~24.000 righe reali) alla ricerca di: dati di
  gioco scritti a mano invece che nei JSON, bug logici/concettuali. Trovati 4 problemi, di gravità molto diversa:
  1. **Bug attivo confermato — `core/level_manager.py`, `_CLASS_FEATURES`**: tabella hardcoded 12 classi × 20
     livelli con i nomi feature mostrati nel dialog di level-up, mai aggiornata dopo i numerosi audit dei JSON
     classe — confronto automatico riga per riga contro tutti i 12 file JSON: decine di nomi non più coerenti (es.
     Guerriero lv1 "Secondo Respiro"→corretto "Recupera Energie", lv2 "Ondata d'Azione"→"Azione Impetuosa", lv9
     "Inarrestabile"→"Indomito"; Mago lv20 "Firma degli Incantesimi"→"Incantesimi Personali"; Barbaro lv7/11/18
     "Istinto Bestiale"/"Furore Implacabile"/"Potere Indomito"→"Istinto Ferino"/"Ira Implacabile"/"Potenza
     Indomabile"; Barbaro lv3 "Percorso Primordiale"→"Cammino Primordiale"; Monaco lv4/14/20 "Caduta
     Rallentata"/"Anima di Diamante"/"Essere Perfetto"→"Caduta Lenta"/"Anima Adamantina"/"Perfezione Interiore";
     Bardo lv3/10 "Perizia"→in realtà "Maestria" per il manuale, come già confermato nell'audit di bardo.json).
     **Effetto pratico**: ogni level-up, per ogni classe, mostrava nomi feature superati, anche se "Abilità di
     Classe" in Combattimento (già JSON-based) mostrava quelli corretti. **Fix**: `level_manager.py` riscritto per
     leggere sempre da `game_data.get_class()`, vedi la voce dedicata sopra in "core/level_manager.py" per i
     dettagli completi (meccaniche ricorrenti, nuovo parametro `subclass`, scope deliberatamente limitato per non
     inventare tabelle numeriche non verificate).
  2. **Duplicazione con contenuto divergente, non risolta — `data/game_data/wizard_data.py`, `BACKGROUNDS`**:
     dizionario Python di ~500 righe con tutti i 12 background PHB (skill, traits, ideali, legami, difetti), usato
     attivamente da `wizard_engine.py`/`wizard_view.py`/`manual_form.py`/`profilo_tab.py`, che esiste **in
     parallelo** a `data/game_data/backgrounds/*.json` con lo stesso scopo ma **testo diverso, non solo diversa
     formattazione** (es. Acolito, primo tratto — Python: "Veneri un particolare eroe della tua fede..."; JSON:
     "Idolatro i miei dei e trovo pace..."). Nessuno dei due dataset è mai stato auditato riga per riga contro il
     manuale (checklist "Background" tutta `[ ]`), quindi non è possibile stabilire quale sia corretto senza il PDF
     — stesso processo già fatto per razze/classi, ancora da fare. **Deliberatamente non toccato**: Davide ha
     scelto di non includerlo tra i 3 fix di questa sessione (vedi sotto), resta in sospeso come futuro audit
     dedicato.
  3. **Bug minore, corretto — `CLASS_SUGGESTED_RACES`** (`wizard_data.py`): 3 nomi sottorazza non allineati ai nomi
     canonici — "Nano Collinare"→"Nano delle Colline", "Halfling Pieleggero"→"Halfling Piedelesto", "Gnomo
     (Roccia)"→"Gnomo delle Rocce". Impatto reale verificato: solo il Chierico ne era influenzato
     (`get_recommended_race()` filtra i nomi non validi, quindi le altre classi avevano già una razza valida in
     prima posizione) — la razza consigliata per il Chierico cadeva su "Umano" invece di "Nano delle Colline".
     Corretto e verificato: ora `get_recommended_race("Chierico")` restituisce "Nano delle Colline".
  4. **Duplicazione sicura, corretta — `CLASSES` in `config/settings.py`**: dizionario con
     `hit_die`/`spellcasting_ability` per le 12 classi, duplicato rispetto agli stessi campi già presenti in ogni
     `classes/*.json`. Verificato con uno script di confronto: **nessuna discrepanza** al momento del fix (a
     differenza di `RACE_DATA` o `_CLASS_FEATURES`, qui i due dataset erano ancora sincronizzati) — comunque stesso
     rischio architetturale già eliminato per razze e le altre 7 costanti classe. **Fix**: rimosso da
     `settings.py`, sostituito da `GameDataLoader.get_class(name)` (dict completo) e `get_class_names()` (elenco
     nomi per i dropdown "Classe") in tutti e 5 i punti di lettura (`wizard_engine.py`, `wizard_view.py` ×4,
     `manual_form.py` ×5, `profilo_tab.py` ×1). Verificato anche `RACES` (lista piatta legacy) contro `RACES_BASE`:
     coerente, nessuna azione necessaria (stesso rischio latente, non affrontato per scelta di scope — Davide ha
     approvato solo i 3 fix sopra).
  - **Altre osservazioni, priorità bassa, non affrontate** (per scelta di scope, non richiesto):
    `get_class_resource_defaults()` e le tabelle slot incantesimo
    (`_FULL_CASTER_SLOTS`/`_HALF_CASTER_SLOTS`/`_WARLOCK_SLOTS` in `character_repo.py`) contengono numeri PHB
    scritti a mano senza controparte JSON, ma sono tabelle universali stabili già testate a fondo in un audit
    precedente (2026-07-09) — nessuna discrepanza nota; `_DAMAGE_TYPES`/`_WEAPON_PROPERTIES` in `inventario_tab.py`
    sono liste PHB standard usate solo come dropdown di comodo per l'inserimento manuale in inventario, non
    enforcement di regole.
  - **Verifica finale**: `py_compile` sull'intero albero sorgente; round-trip `build_character()` su tutte le
    combinazioni classe×razza già usate negli audit precedenti (nessuna regressione); `get_level_up_steps()`
    testato su tutte le 12 classi × tutte le sottoclassi reali × livelli 2-20 (nessuna eccezione, nessuna etichetta
    vuota); simulazione di un level-up completo 1→20 per il Warlock (progressione Suppliche Occulte/Dono del
    Patto/ASI/Bonus Competenza) confrontata contro la progressione PHB attesa — coerente in ogni dettaglio.
- **proficiency_type valori DB** (completo): `"save"`, `"skill"`, `"tool"`, `"weapon"`, `"armor"`, `"language"`, `"feat"`, `"metamagic"`, `"invocation"`, `"cantrip"`, `"asi_record"`
  - ⚠️ wizard usa `"save"` non `"saving_throw"`
  - `is_expert=True` su `"skill"` o `"tool"` = Perizia (Expertise)
  - `"asi_record"` — riga sintetica che traccia i +2/+1+1 ASI per livello; `bonus_data={"ability":{...}}`, `level_obtained=N`; usato da `undo_level()` per reversal
- `character_proficiencies.proficiency_type` può essere: `"saving_throw"`, `"skill"`,
  `"tool"`, `"weapon"`, `"armor"`, `"language"`, `"feat"`, `"metamagic"`, `"invocation"`, `"cantrip"`, `"asi_record"`
- `spell_slots` viene inizializzato con tutti e 9 i livelli a `total=0, used=0`
  al momento della creazione del personaggio
- `previous_turn_state` è una stringa JSON con lo snapshot dello stato turno precedente
  (per il tasto "Annulla ultima mossa")
- Il wizard estrae traits/ideali/legami/difetti **casualmente** dai dati PHB al momento
  del salvataggio — il giocatore può editarli poi dalla scheda
- `speed` è in **metri** (non feet): 9 m = 30 ft standard
- `magic_damages` in Weapon è una stringa JSON, non un oggetto Python — usare `json.loads()` / `json.dumps()`
- `armor_type` valori ammessi: `"leggera"`, `"media"`, `"pesante"`, `"scudo"`, `""` (nessuna armatura)
- `ca_bonus` in Character è additivo rispetto alla CA calcolata dall'armatura; reset a 0 dopo riposo lungo
- Pylance type stubs Flet: handler `on_click`/`on_blur`/`on_select` → `ft.Event[SpecificType]`, non `ControlEvent`
  Attributi non in stub (es. `error_text`) → `cast(Any, widget).attr = val`
  Liste eterogenee → `cast(list[ft.Control], [...])`
  `Checkbox.label` è `StrOrControl` → `str(cb.label) if cb.label else ""`

- **Bug report di Davide (2026-07-10) — fix creazione personaggio, batch P1** — 9 problemi segnalati dall'uso reale dell'app, corretti in ordine di priorità (task #72-79):
  - **#72 — Armi iniziali salvate in inventario invece che nella tabella `weapons`**
    (`wizard_view.py`/`manual_form.py → _save_item()`): sia `weapon_choice` (scelta A/B) sia `weapon` fisso
    finivano sempre in `create_inventory_item(category="weapon")`, mai in `character_repo.create_weapon()` — un
    personaggio appena creato non aveva armi nella sezione Armi di Inventario, solo un oggetto generico senza dado
    danno/tipo danno/proprietà. Fix: nuova funzione `_save_weapon_by_name(character_id, wname)` in entrambi i file,
    identica in entrambi — cerca il nome in `equipment/weapons.json` via `_loader.get_weapon()`, crea la riga in
    `weapons` con `damage_dice`/`damage_type`/`properties` (join della lista) ed `is_equipped=True`; se il nome non
    viene trovato (refuso di trascrizione in un JSON classe), non perde silenziosamente l'oggetto ma logga un
    `logger.warning()` e ripiega su un inventory_item generico — diagnosticabile invece di un fallimento muto.
    `_save_item()` riscritta per chiamare questa funzione sia per `weapon_choice` (conteggio singolo e multiplo)
    sia per il branch `weapon` esplicito.
  - **#73 — Lingue fisse di razza mai salvate alla creazione**: `get_resolved_race(race, subrace)["languages"]`
    (usata da tempo solo per la UI di sola lettura in Esplorazione/Profilo) non veniva mai letta al momento del
    salvataggio — un personaggio Elfo nasceva senza "Elfico" tra le competenze lingua, un Nano senza "Nanico",
    ecc., a meno che il background non gliela concedesse per altra via. Solo le lingue *scelte* (background a
    scelta, extra Umano) venivano effettivamente salvate, mai quelle fisse di razza. Fix in entrambi i file: prima
    di salvare le lingue scelte, itera `get_resolved_race(self._review_race, self._review_subrace)["languages"]`,
    filtra solo le voci stringa (le voci `dict` sono le entry "a scelta" già gestite altrove, es. Umano) e le salva
    come `proficiency_type="language"`; aggiunto un set `lang_seen` condiviso per evitare doppioni se la stessa
    lingua compare sia come fissa di razza sia come scelta di background. **Trovato un gap correlato non incluso in
    questo fix** (fuori scope del bug report, che parlava solo di lingue fisse mancanti): il Mezzelfo ha nel suo
    JSON una entry `{"type":"choice","count":1,"from":"any"}` per la terza lingua libera, identica a quella
    dell'Umano, ma nessuna UI la espone (l'Umano ha un dropdown dedicato hardcoded sul nome razza, il Mezzelfo no)
    — segnalato come nuovo TODO in "Priorità Bassa / v2".
  - **Refuso "seleziona linguae"→corretto in "lingua"/"lingue"**: `f"Scegli {lang_count} lingua{'e' if lang_count >
    1 else ''}"` produceva letteralmente "linguae" al plurale (concatenazione errata, il plurale italiano di
    "lingua" è "lingue", non "lingua"+"e"). Corretto in entrambi i file con una scelta esplicita tra le due parole
    intere.
  - Verificato con `py_compile` su entrambi i file dopo ogni modifica.
  - **#78 — Nessun toggle rapido equip/disequip per oggetti generici/armature**: le armi avevano già un
    `IconButton` dedicato accanto a "Modifica" per equipaggiare/disequipaggiare al volo
    (`_toggle_weapon_equipped`), ma gli oggetti della sezione "Oggetti" (armature, scudi, attrezzi, ecc.) potevano
    cambiare stato equipaggiato solo aprendo il dialog "Modifica" e spuntando la checkbox. Aggiunto
    `_toggle_item_equipped(item)` in `inventario_tab.py`, stesso pattern del toggle armi: nuovo `IconButton` (●/○
    rosso/grigio, tooltip "Equipaggia"/"Disequipaggia") accanto a "Modifica" in `_item_row()`; se l'oggetto è
    un'armatura (`category == "armor"`), ricalcola subito la CA con `calculate_and_update_ca()` — prima,
    equipaggiare un'armatura da questo ipotetico toggle non lo faceva, un problema analogo (ma opposto) a quello
    risolto in precedenza per il dialog di modifica. Gestito anche l'errore di scrittura DB (`show_error_dialog`,
    in linea con il fix generale del task #67). Verificato con test end-to-end: creazione di un oggetto armatura
    (`ca_value=11`, tipo `leggera`), toggle equip, CA ricalcolata correttamente a `11 + mod DES`.
  - **#77 — Movimento e velocità solo ad interi**: `Character.speed`/`Character.movement_used` erano tipizzati
    `int` in `data/models.py`, e la colonna DB `speed`/`movement_used` era `INTEGER` — problema non solo cosmetico
    ma un **bug reale già latente**: il dialog "Modifica Statistiche" in `combattimento_tab.py` faceva `c.speed =
    max(0, int(f_speed.value or c.speed))`, quindi un personaggio con velocità di razza frazionaria (Nano/Halfling
    7,5 m, Elfo dei Boschi 10,5 m — valori PHB reali, già documentati altrove in questo file) non poteva MAI
    salvare quel dialog: `int("7.5")` solleva `ValueError`, intercettato da un `except: return` silenzioso — il
    dialog restava aperto senza alcun feedback visibile. Fix: `speed`/`movement_used` cambiati a `float` in
    `data/models.py` (default `9.0`/`0.0`), colonne DB cambiate a `REAL` in `data/database.py` (verificato con test
    diretto che SQLite conserva già correttamente i valori frazionari anche nelle colonne `INTEGER` esistenti per
    via della type affinity — nessuna migrazione necessaria per i DB già creati); `_on_edit_stats_click().save()`
    ora fa `float()` invece di `int()`, normalizzando anche la virgola italiana ("7,5"→"7.5") prima del parsing;
    `use_movement()` e `update_turn_state()` tipizzati `float`; aggiunti i pulsanti "−0,5m" e "−1,5m" nel tracker
    movimento (prima solo −1/−2/−3/−6m). Formattazione display corretta con `:g` in 3 punti che mostravano ancora
    il valore grezzo (`esplorazione_tab.py` righe Nuoto/Scalata/Volo, `profilo_tab.py` riga Velocità tratti
    razziali, `manual_form.py` chip "VEL" del riepilogo finale) per evitare "9.0 m" al posto di "9 m". Verificato
    con test end-to-end: creazione di un personaggio Nano con `speed=7.5` → persistito e riletto identico dal DB;
    parsing con virgola/punto senza `ValueError`; `use_movement()` con delta 1.5/0.5 accumula correttamente;
    `update_turn_state()` persiste `movement_used=3.5` senza troncamento.
  - **#75 — Abilità razza/classe non si escludevano a vicenda**: il pool di abilità del Mezzelfo (Versatilità nelle
    Abilità, 2 a scelta) e quello delle abilità di classe escludevano entrambi le abilità fisse di background, ma
    non si escludevano tra loro — un Mezzelfo poteva scegliere la stessa abilità sia come tratto razziale sia come
    abilità di classe, ottenendo (in teoria) una competenza duplicata sulla stessa voce. Fix in
    `wizard_view.py`/`manual_form.py`: `_class_skill_options()` ora esclude anche `self._review_mezzelf_skills`; il
    pool Mezzelfo (`all_skills`) esclude anche `self._review_skills` (oltre alle abilità di background, già escluse
    prima). Aggiunta una chiamata incrociata di ricostruzione (`_rebuild_skills_col()` dentro il toggle Mezzelfo,
    `_rebuild_race_extras_col()` dentro il toggle abilità di classe) così l'esclusione si riflette immediatamente
    nell'altra lista mentre il giocatore sceglie, senza dover cambiare schermata. Verificato con test end-to-end
    (istanza reale della classe, bypassando `__init__` che richiede una pagina Flet viva): scegliere un'abilità
    come tratto razziale la rimuove subito dalle opzioni di classe, in entrambi i file.
  - **#76 — Sottorazza scelta troppo tardi in `manual_form.py`** (solo il form manuale, il wizard guidato già
    accorpa tutto in un'unica fase "Revisione" e non ne soffre): la fase 2 "Punteggi" mostrava un'anteprima dei
    bonus razziali calcolata con `get_resolved_race(race, subrace)`, ma `self._review_subrace` era ancora vuota in
    quel momento — la sottorazza (Sottorazza / Discendenza Draconica) veniva scelta solo dopo, nella fase 3
    "Scelte". Per una razza come il Nano (Montagna FOR+2 / Colline SAG+1) o l'Elfo, l'anteprima mostrata durante
    l'assegnazione dei punteggi era quindi sempre incompleta o vuota, inducendo il giocatore ad assegnare i
    punteggi senza sapere quale bonus li avrebbe modificati. **Fix (confermato da Davide: "Sì, sottorazza +
    riordino form manuale")**: il picker Sottorazza/Discendenza Draconica è stato spostato dalla fase "Scelte"
    (rimossi `subrace_col`/`_rebuild_subrace_col()` e i riferimenti in `extra_card_content`/`_update_extra_card()`)
    alla fase "Punteggi", in cima al contenuto — nuove funzioni locali `_rebuild_subrace_picker()` (costruisce il
    dropdown, identica nella struttura alla vecchia `_rebuild_subrace_col()`) e `_refresh_bonus_preview()`
    (ricalcola `bonus_col`, un `ft.Column` dedicato ora aggiornato dal vivo a ogni cambio di sottorazza, invece
    della vecchia lista statica `bonus_lines` calcolata una sola volta). `_rebuild_subrace_picker()` viene sempre
    chiamata (non solo se la razza ha sottorazze) perché gestisce già internamente il caso "nessuna sottorazza"
    azzerando `self._review_subrace` — necessario per il caso in cui il giocatore torni indietro da una razza con
    sottorazze a una senza tramite "Indietro". La fase "Scelte" ora legge `self._review_subrace` già valorizzata
    (usata da `_rebuild_race_extras_col()` per Mezzelfo/Alto Elfo, dal riepilogo finale, dal salvataggio) senza più
    possederne la UI di scelta. Verificato con test end-to-end (bypass `__init__`, DB temporaneo isolato):
    Nano→sottorazza auto-selezionata alla prima renderizzazione di "Punteggi"; Dragonide→Discendenza Draconica
    auto-selezionata; Umano (nessuna sottorazza)→`_review_subrace` correttamente azzerata anche se sporca da un
    giro precedente; cambio manuale sottorazza→`bonus_col` riflette il nuovo bonus; creazione completa di un
    Chierico Nano delle Colline fino al salvataggio→CON e SAG del personaggio salvato riflettono correttamente sia
    lo Standard Array assegnato sia il bonus di sottorazza (+2 CON / +1 SAG), HP calcolati di conseguenza — nessuna
    regressione sul fix delle lingue fisse di razza (task #73, ancora verificato funzionante nello stesso test).
- **Bug report di Davide (2026-07-11) — validazione obbligatoria delle scelte in creazione personaggio**: "quando
  ai crea il personaggio, l'utente deve riempire tutti i campi ed effettuare tutte le selezioni se no non può
  avanzare... l'unico campo che può essere lasciato libero è nome giocatore... attualmente si può procedere anche
  senza aver selezionato le abilità a scelta." **Causa radice**: nel flusso di creazione (sia `wizard_view.py` fase
  Revisione, sia `manual_form.py` fase Scelte) le variabili di stato a scelta libera si dividono in due categorie
  mai distinte esplicitamente prima d'ora — (a) Dropdown/RadioGroup, che nel codice esistente sono SEMPRE
  pre-popolati con un default valido al primo render (pattern `if not self._review_X or self._review_X not in
  options: self._review_X = options[0]`), quindi intrinsecamente "sempre validi"; (b) Checkbox multi-select con un
  conteggio bersaglio (abilità di classe, abilità Mezzelfo, lingue a scelta del background), che partono invece da
  lista vuota e richiedono un'interazione esplicita del giocatore — per queste, **3 casi su 4 non avevano alcuna
  validazione che bloccasse l'avanzamento**: abilità di classe (il bug esplicitamente segnalato), abilità Mezzelfo
  (stesso identico pattern, mai segnalato ma stesso bug), lingue a scelta di background (idem); solo la Perizia
  Ladro aveva già una validazione, e solo al salvataggio finale, non al cambio fase. **Fix**: nuove funzioni
  `_scelte_validation_error()` (`manual_form.py`) e `_review_validation_error()` (`wizard_view.py`), identiche
  nella logica, che controllano in sequenza: conteggio abilità di classe (`_class_skill_options()`), conteggio
  abilità Mezzelfo (`_review_mezzelf_skills`, solo se razza Mezzelfo), conteggio lingue a scelta
  (`_bg_language_choices()`), Perizia Ladro (2 abilità, solo se classe Ladro — già presente, riportato qui per
  centralizzare i controlli in un unico punto), e trucchetti/incantesimi iniziali (già presente da task #74,
  spostato anch'esso in questa funzione) — ciascuna con messaggio d'errore in italiano dedicato, restituisce
  stringa vuota se tutto è valido. Il pulsante "Continua" della fase (che porta a Equipaggiamento) ora chiama
  questa funzione prima di avanzare: se ritorna un errore, lo mostra in un `ft.Text` rosso dedicato
  (`scelte_error_text`/`review_error_text`, stesso stile visivo delle validazioni preesistenti) e blocca
  l'avanzamento; se vuota, procede normalmente. **Difesa in profondità**: gli stessi controlli
  (skill/Mezzelfo/lingue) sono stati aggiunti anche a `_on_save` in entrambi i file, PRIMA dei controlli
  preesistenti Perizia Ladro/Trucchetti — ridondante nel flusso normale (l'utente non può più arrivare a "Conferma"
  senza aver già superato la validazione sul pulsante "Continua"), ma preserva la scheda da un futuro percorso di
  codice che bypassasse quel gate. **Nome giocatore** confermato correttamente opzionale in entrambi i flussi —
  nessuna modifica necessaria, non è mai stato validato come obbligatorio. **Verificato con test di regressione
  end-to-end** (DB temporaneo isolato, bypass `__init__` Flet) su tutte le 12 classi PHB in entrambi i file: (1) il
  pulsante "Continua"/"Crea personaggio" blocca correttamente l'avanzamento con il messaggio d'errore atteso quando
  abilità di classe/Mezzelfo/lingue sono lasciate vuote; (2) una volta compilate programmaticamente tutte le
  selezioni obbligatorie, la creazione va a buon fine end-to-end con persistenza DB corretta (nessun duplicato, es.
  lingua fissa di razza "Elfico" del Mezzelfo unita correttamente alle lingue scelte dal giocatore senza duplicare
  "Comune"); (3) `player_name = ""` non blocca mai la creazione in nessuno dei due file.
- **Bug report di Davide (2026-07-11) — testo UI "Perizia" errato per il Ladro Lv.1, deve essere "Maestria"**: "c'è
  ancora scritto perizia per il ladro, ma la perizia è per il bardo il ladro ha maestria". **Verifica contro i JSON
  già auditati** (unica fonte dati per nomi feature, per regola di progetto): `ladro.json` riga 450 e `bardo.json`
  riga 207 hanno **entrambi** `"name": "Maestria"` per questa feature (raddoppio del bonus di competenza su 2
  abilità) — il nome PHB italiano è "Maestria" per entrambe le classi, non "Perizia" per l'una e "Maestria" per
  l'altra. La UI di creazione personaggio (sezione scelta a Lv.1, screenshot di Davide) usava però ancora "Perizia"
  in tutte le stringhe visibili, per la sola parte relativa al Ladro — refuso residuo di una fase precedente in cui
  il termine non era stato ancora verificato contro i JSON. **Fix, scope limitato alla sezione Ladro Lv.1 come
  richiesto**: sostituito "Perizia"→"Maestria" in tutte le stringhe utente e nei commenti di `wizard_view.py` (fase
  Revisione) e `manual_form.py` (fase Scelte) relative a questa sezione: header sezione ("Maestria (Ladro Lv.1)"),
  testo scelta ("Scegli 2 abilità per la Maestria (Lv.1)"), testo esplicativo ("La Maestria raddoppia il bonus di
  competenza..."), tutti i messaggi di errore di validazione (fase e salvataggio finale), commenti di codice. **Non
  rinominati** gli identificatori Python interni non visibili all'utente (`_review_expertise`, `expertise_col`,
  `sec_perizia`, `set_expertise()`) — stessa convenzione già seguita per la rinomina "Invocazioni
  Occulte"→"Suppliche Occulte" del Warlock, per non introdurre rischio di refactoring su codice funzionante senza
  beneficio visibile all'utente. **Nota per Davide, non affrontata in questo fix perché fuori dallo scope
  esplicitamente richiesto ("nella sezione ladro")**: la stessa imprecisione esiste anche nel dialog generico di
  level-up (`profilo_tab.py`, step `EXPERTISE` condiviso da Ladro Lv6 e Bardo Lv3/Lv10), che mostra "Perizia —
  scegli N abilità da portare a Maestria" — per coerenza con quanto appena verificato nei JSON, anche questo testo
  sarebbe da correggere in "Maestria" per entrambe le classi, ma essendo un dialog condiviso (non specifico del
  Ladro) non è stato toccato senza conferma esplicita. Verificato con `py_compile` su entrambi i file di creazione;
  grep di conferma — zero occorrenze residue di "Perizia" in `ui/views/creation_wizard/`. **Correzione successiva
  (2026-07-11, stessa richiesta)**: Davide ha confermato che si era sbagliato lui e che "Maestria" è il nome
  corretto per ENTRAMBE le classi (coerente con `bardo.json`/`ladro.json`, entrambi `"name": "Maestria"`) —
  sistemato anche il dialog di level-up condiviso in `profilo_tab.py` (step `EXPERTISE`, Ladro Lv6 e Bardo
  Lv3/Lv10): testo "Perizia — scegli N abilità da portare a Maestria"→**"Maestria — scegli N abilità aggiuntive"**,
  più i 2 commenti di codice correlati. Verificato con `py_compile` e grep — zero occorrenze residue di "Perizia"
  in tutto `ui/views/character_sheet/profilo_tab.py`.
- **Bug report di Davide (2026-07-11) — equipaggiare un'arma non sostituisce quella già equipaggiata**: "non
  funziona bene la sezione armi se clicco equipaggia su non sostituisce l'arma attualmente equipaggiata, solo le
  armi utilizzabili a una mano si possono equipaggiare contemporaneamente, una per mano o in altre regole
  specificate dal manuale sul combattimento". **Causa radice**: `_toggle_weapon_equipped()` in `inventario_tab.py`
  si limitava a invertire il flag `is_equipped` dell'arma cliccata, senza alcun vincolo sulle altre armi già
  equipaggiate — un personaggio poteva avere un numero arbitrario di armi (incluse più armi a due mani) tutte
  marcate come equipaggiate contemporaneamente, cosa fisicamente impossibile con solo 2 mani. **Verifica contro il
  manuale** (letto con `pdftotext -layout` su "ED 5.0 manuale del giocatore.pdf"): proprietà "Due Mani" (Cap. 5,
  Proprietà delle Armi) — «Questa arma richiede di essere impugnata a due mani quando il personaggio la usa per
  attaccare»; Scudi (Cap. 5) — «Uno scudo [...] è impugnato a una mano. [...] Un personaggio può beneficiare di un
  solo scudo alla volta»; "Combattere con Due Armi" (Cap. 9) — «Quando un personaggio [...] attacca con un'arma da
  mischia leggera impugnata a una mano, può usare un'azione bonus per attaccare con un'altra arma da mischia
  leggera impugnata nell'altra mano» — **questa regola riguarda solo quale azione bonus è disponibile in
  combattimento, NON quali armi si possono fisicamente impugnare insieme**: due armi a una mano non leggere (es.
  spada lunga + mazza) si possono equipaggiare contemporaneamente, una per mano, semplicemente senza poter usare
  l'azione bonus di Combattere con Due Armi con quella coppia — la proprietà "Leggera" non entra quindi nella
  logica di equipaggiamento simultaneo, solo nella logica (già esistente altrove) delle regole di attacco. **Fix**:
  nuovo modulo puro `core/equipment_manager.py` (nessuna dipendenza Flet, stessa convenzione di
  `wizard_engine.py`/`level_manager.py`), con `weapon_hands(properties)` (2 se "Due Mani" tra le proprietà,
  altrimenti 1 — le armi "Versatile" erano trattate come arma a una mano ai fini dell'occupazione delle mani, dato
  che il modello dati dell'app non tracciava separatamente l'impugnatura scelta; **superato lo stesso giorno**,
  vedi la voce dedicata più sotto "Gestione dado danno Versatile a due mani") e `resolve_weapon_equip(weapons,
  target_id, shield_equipped)`, che calcola quali armi devono restare equipaggiate rispettando il limite di 2 mani:
  equipaggiare un'arma a due mani disequipaggia automaticamente tutte le altre armi e un eventuale scudo;
  equipaggiare un'arma a una mano, se non c'è spazio, disequipaggia automaticamente le armi equipaggiate da più
  tempo (si scorre la lista al contrario rispetto all'ordine di creazione/rowid, così le armi equipaggiate più di
  recente hanno la precedenza) finché non c'è posto. Disequipaggiare un'arma resta un'operazione isolata, senza
  effetti a cascata. `_toggle_weapon_equipped()` in `inventario_tab.py` riscritta per chiamare questa funzione
  quando si equipaggia (non quando si disequipaggia), applicare il nuovo stato a tutte le armi coinvolte via
  `update_weapon()`, e — se la funzione indica che va disequipaggiato anche lo scudo (caso arma a due mani con
  scudo già indossato) — disequipaggiare l'oggetto scudo in inventario e ricalcolare la CA con
  `calculate_and_update_ca()` (la rimozione dello scudo riduce la CA). Gestiti gli errori di scrittura DB con
  `show_error_dialog()` su ogni chiamata, coerente con il fix generale del task #67. **Verificato** con una
  batteria di test automatizzati sul modulo puro (nessun DB necessario): arma a due mani disequipaggia tutte le
  altre armi e lo scudo; due armi a una mano (anche non leggere) coesistono correttamente, una per mano; una terza
  arma a una mano espelle quella equipaggiata da più tempo; uno scudo già equipaggiato riduce a 1 la capacità
  residua per una nuova arma a una mano; arma "Versatile" trattata correttamente come arma a una mano; id non
  trovato non altera lo stato. **Nota per Davide, non affrontata in questo fix perché fuori scope (riguarda le
  armature/scudi, non le armi)**: `calculate_and_update_ca()` non impedisce di avere più scudi equipaggiati
  contemporaneamente (somma il `ca_value` di TUTTI gli scudi con `is_equipped=True`), nonostante il manuale dica
  esplicitamente che si può beneficiare di un solo scudo alla volta — la sezione Oggetti/Armature dell'inventario
  non ha un vincolo equivalente a quello appena introdotto per le armi. Segnalato come TODO.
- **Gestione dado danno Versatile a due mani (2026-07-11, stessa richiesta del fix equip-slot sopra)** — Davide,
  dopo il fix del limite di 2 mani, ha chiesto: "però ci sono alcune armi che possono essere impugnate sia a una
  mano che a 2 mani, se a una mano fanno 1d8 se a due mani 1d10 questa cosa l'abbiamo gestita?". Risposta: no, non
  lo era — `Weapon` aveva un solo campo `damage_dice`, e `weapon_hands()` (appena scritta) trattava sempre un'arma
  Versatile come a una mano, indipendentemente da come il giocatore la stesse effettivamente impugnando in quel
  momento.
  - **Verifica contro il manuale** (PHB IT, Cap. 5): «"Versatile": Questa arma può essere usata a una o due mani.
    La proprietà è accompagnata da un valore in danni indicato tra parentesi (i danni che l'arma infligge quando
    viene impugnata a due mani per effettuare un attacco in mischia).» — conferma sia il meccanismo (dado diverso
    in base all'impugnatura) sia che, impugnata a due mani, l'arma occupa a tutti gli effetti 2 mani (nessun'altra
    arma o scudo equipaggiabile insieme), esattamente come un'arma "Due Mani" vera e propria mentre è tenuta in
    quel modo. `equipment/weapons.json` (dato di riferimento già trascritto il 2026-07-10, non ancora auditato riga
    per riga) conferma i valori concreti per le armi PHB, es. spada lunga `"Versatile (1d10)"` con
    `damage_dice="1d8"`, lancia `"Versatile (1d8)"` con `damage_dice="1d6"` — non ancora wired alla creazione
    automatica delle armi (task #72), quindi questi valori restano di riferimento manuale per ora, non collegati
    alle armi già create dal personaggio.
  - **Bug pre-esistente scoperto mentre si estendeva `weapon_hands()`, non correlato al task originale**: la
    proprietà "Due Mani" del PHB, nella UI di creazione/modifica arma (`inventario_tab.py → _WEAPON_PROPERTIES`), è
    etichettata **"A due mani"** (non "Due Mani" nudo) — ma `weapon_hands()`, scritta poche ore prima nello stesso
    giorno per il fix del limite di 2 mani, confrontava le proprietà per **uguaglianza esatta** contro la stringa
    `"due mani"`, che non corrisponde mai a `"a due mani"`. Risultato pratico: **ogni arma a due mani veniva
    trattata come se occupasse una sola mano**, quindi il fix del task precedente (limite di 2 mani) non funzionava
    affatto per le vere armi a due mani create dalla UI — solo il caso "due armi a una mano" era stato testato con
    dati sintetici che non passavano mai dall'etichetta reale della checkbox. Fix: `weapon_hands()` ora confronta
    per sottostringa (`"due mani" in p` invece di `p == "due mani"`), che riconosce sia "Due Mani" sia "A due mani"
    sia eventuali varianti future; stesso criterio esteso a "Versatile". Bug documentato nel docstring della
    funzione.
  - **Modello dati**: due nuovi campi su `Weapon` (`data/models.py`) — `versatile_damage_dice: str = ""` (dado
    quando impugnata a due mani) e `grip_two_handed: bool = False` (impugnatura corrente; irrilevante per armi non
    Versatile, dato che quelle "Due Mani" sono sempre a due mani senza bisogno di un flag). Due colonne aggiunte
    via `_add_column()` idempotente in `data/database.py → _migrate()` (`weapons.versatile_damage_dice TEXT DEFAULT
    ''`, `weapons.grip_two_handed INTEGER DEFAULT 0`).
    `character_repo.get_weapons()`/`create_weapon()`/`update_weapon()` estesi per leggere/scrivere entrambi i campi
    end-to-end.
  - **`core/equipment_manager.py`**: `weapon_hands(properties, grip_two_handed=False)` ora ritorna 2 anche per
    un'arma Versatile con `grip_two_handed=True` (oltre al caso "Due Mani", sempre 2 a prescindere);
    `EquipCandidate` ha un nuovo campo `grip_two_handed`; `resolve_weapon_equip()` lo usa per il calcolo del
    conflitto (un'arma Versatile impugnata a due mani si comporta, ai fini delle mani occupate, esattamente come
    un'arma "Due Mani": disequipaggia tutte le altre armi/lo scudo).
  - **UI (`inventario_tab.py`)**:
    - Dialog Nuova/Modifica Arma: nuova sezione `versatile_fields` (TextField "Dado danno a due mani" + Checkbox
      "Impugnata a due mani ora"), visibile solo quando la checkbox proprietà "Versatile" è spuntata
      (`_on_versatile_toggle`, stesso pattern di visibilità dinamica già usato per `armor_fields` nel dialog
      Oggetto). Se "Versatile" viene deselezionata dopo aver compilato questi campi, `save()` li azzera invece di
      lasciare dati orfani non più raggiungibili da nessuna UI.
    - Card arma (`_weapon_card`): il dado danno mostrato nel badge "DANNO" ora riflette l'impugnatura corrente
      (`versatile_damage_dice` se `grip_two_handed` e compilato, altrimenti `damage_dice`); aggiunta una riga
      informativa "Versatile — impugnata a una mano/due mani: 1d8 (1 mano) / 1d10 (2 mani)" per rendere sempre
      visibili entrambi i valori.
    - Nuovo pulsante rapido "impugnatura" (icona mano aperta/chiusa) accanto al toggle equipaggia, visibile solo
      per armi Versatile con `versatile_damage_dice` compilato — nuovo metodo `_toggle_weapon_grip(weapon)`: se
      l'arma non è equipaggiata, o si sta tornando a una mano, cambia il flag senza effetti collaterali (non
      occupa/libera mai spazio in questi due casi); se invece l'arma è già equipaggiata e si passa a due mani,
      applica lo stesso calcolo di conflitto di `_toggle_weapon_equipped` (estratto in
      `_unequip_shield_and_recalc_ca()`, ora condiviso dalle due funzioni) — disequipaggia automaticamente le altre
      armi e un eventuale scudo, ricalcolando la CA se lo scudo viene rimosso.
  - **Bug di regressione trovato e corretto nello stesso passaggio**: `_update_weapon_equipped_flag()` (helper già
    esistente per il toggle rapido equip/disequip) chiamava `update_weapon()` senza ripassare
    `versatile_damage_dice`/`grip_two_handed` — dato che `update_weapon()` li accetta con default vuoti/`False`, un
    semplice click su "equipaggia/disequipaggia" avrebbe **azzerato silenziosamente** l'impugnatura e il dado a due
    mani di qualunque arma Versatile. Fix: la funzione ora ripassa sempre
    `weapon.versatile_damage_dice`/`weapon.grip_two_handed` (con un parametro opzionale `grip_two_handed` per i
    casi in cui va effettivamente cambiato, usato da `_toggle_weapon_grip`), documentato nel suo stesso docstring
    per evitare che si ripresenti in futuro.
  - **Verificato**: (1) script standalone su `core/equipment_manager.py` — confermato il bug "A due mani" (un'arma
    con quella proprietà tornava 1 mano prima del fix, 2 dopo), Versatile senza grip a due mani = 1 mano, Versatile
    con grip a due mani = 2 mani, arma normale non influenzata dal grip, equipaggiare una Versatile impugnata a due
    mani disequipaggia le altre armi/lo scudo, la stessa arma impugnata a una mano coesiste con un'altra arma già
    equipaggiata; (2) test end-to-end su `character_repo` con DB temporaneo isolato (mai quello reale) — round-trip
    di `versatile_damage_dice`/`grip_two_handed` attraverso `create_weapon`→`get_weapons`→`update_weapon`, e
    verifica esplicita che un toggle equip/disequip (stesso identico percorso della regressione trovata sopra)
    **non** azzeri più i due campi. `py_compile` su tutti i file toccati (`core/equipment_manager.py`,
    `ui/views/character_sheet/inventario_tab.py`, `data/models.py`, `data/database.py`,
    `data/repositories/character_repo.py`).
  - **Non affrontato in questo fix, segnalato per il futuro**: le armi create automaticamente alla creazione del
    personaggio (`_save_weapon_by_name`, task #72) non compilano ancora `versatile_damage_dice` a partire da
    `equipment/weapons.json` (che lo contiene già, embedded nella stringa proprietà come `"Versatile (1d10)"`) — un
    personaggio che nasce con una spada lunga ottiene oggi `versatile_damage_dice=""`, e il giocatore deve
    compilarlo a mano dal dialog Modifica la prima volta. Il collegamento automatico richiede un piccolo parser per
    estrarre il valore tra parentesi da quella stringa: rimandato perché `equipment/weapons.json` stesso non è
    ancora passato dall'audit riga-per-riga (vedi checklist), e il formato `"Versatile (1d10)"` embedded nella
    proprietà (diverso dal nuovo campo dedicato `versatile_damage_dice` sulle armi del personaggio) potrebbe
    cambiare quando quell'audit verrà fatto.
- **Bug report di Davide (2026-07-11) — CA non si aggiorna più con l'equipaggiamento, manca una sezione Armature
  dedicata**: "adesso in inventario dovremmo creare anche la sezione armature e metterci le armature e modificare
  correttamente la CA a seconda di cosa ha equipaggiato. Io mi ricordo che già veniva aggiornata la CA a seconda
  dell'equipaggiamento, come mai adesso non funziona?". **Causa radice della CA**: `calculate_and_update_ca()`
  (`character_repo.py`) filtra gli oggetti equipaggiati con `category=="armor"` e prende sempre `equipped_armor[0]`
  — il PRIMO per ordine di creazione (`get_inventory` ordina per `rowid`) — senza mai imporre che al massimo
  un'armatura corporea (e un solo scudo) risultino equipaggiati insieme. Se il giocatore equipaggia una seconda
  armatura senza prima disequipaggiare la prima (nessun vincolo lo impediva), `equipped_armor[0]` continua a
  restituire SEMPRE la prima armatura creata: la CA sembra "smettere di aggiornarsi" non perché il calcolo sia
  rotto, ma perché la lista di armature equipaggiate cresce silenziosamente invece di sostituirsi. Bug riprodotto e
  confermato con un test end-to-end dedicato (vedi sotto) prima di scrivere il fix, non solo ipotizzato. **Verifica
  contro il manuale** (PHB IT, Cap. 5): lo scudo ha una citazione letterale già nota — «Un personaggio può
  beneficiare di un solo scudo alla volta» — mentre per l'armatura corporea il manuale non contiene una singola
  frase equivalente, ma lo implica costantemente con la grammatica singolare («L'armatura che un personaggio
  indossa [...] determinano la sua Classe Armatura base», «aggiunge [...] al numero base del SUO tipo di armatura»)
  e dalla tabella "Indossare e Togliere Armature" (tempi per indossare UN tipo di armatura, non la sovrapposizione
  di più corazze) — trattata quindi nel codice come una scelta di progettazione dichiarata esplicitamente
  (fisicamente ovvia), non come citazione letterale, per non violare la regola "non inventare informazioni" del
  progetto.
  - **Fix**: estese le regole di `core/equipment_manager.py` (già usato per il limite di 2 mani delle armi, stesso
    modulo puro senza Flet) con `ArmorCandidate` e `resolve_armor_equip(armors, target_id)`: modella due
    "postazioni" indipendenti — armatura indossata (leggera/media/pesante, una alla volta) e scudo impugnato (uno
    alla volta) — equipaggiare un'armatura non tocca lo scudo già impugnato e viceversa (un Guerriero con cotta di
    maglia + scudo indossa correttamente entrambi).
  - **`inventario_tab.py`**: nuovo `_enforce_armor_exclusivity(target_id)`, chiamato sia da
    `_toggle_item_equipped()` (toggle rapido dalla card) sia da `_open_item_dialog().save()` (dialog completo) ogni
    volta che un'armatura/scudo viene equipaggiato — PRIMA di richiamare `calculate_and_update_ca()`, così la CA
    riflette sempre lo stato "vero" post-esclusione invece dello stato grezzo pre-esclusione. Il disequipaggiamento
    resta un'operazione isolata (nessun effetto a cascata), stesso principio già stabilito per le armi.
  - **`character_repo.create_inventory_item()` cambiato da `bool` a `str | None`** (ritorna l'id generato, o `None`
    in caso di errore): necessario perché `_enforce_armor_exclusivity()` deve conoscere l'id del nuovo oggetto
    appena creato per includerlo nel calcolo di esclusione al momento della creazione (non solo al toggle rapido su
    un oggetto già esistente). Il cambiamento resta compatibile con tutti i chiamanti preesistenti che facevano `if
    not create_inventory_item(...)`: un UUID valido non è mai stringa vuota, quindi il controllo di verità funziona
    identico a prima; nessuno dei 5 call site esistenti (`wizard_view.py` ×2, `manual_form.py` ×2,
    `inventario_tab.py` ×1) confrontava il valore di ritorno con `True`/`False` letterali.
    `calculate_and_update_ca()` documentata con una nota che spiega l'invariante ora garantita a monte, restando
    comunque difensiva.
  - **Nuova sezione "Armature" dedicata in Inventario** (richiesta esplicita di Davide, non solo il fix della CA):
    estratta dalla lista generica "Oggetti" (dove era mescolata con strumenti/oggetti magici/varie sotto
    l'etichetta "Armature & Scudi") in una sezione a sé tra "Armi" e "Oggetti", stesso stile a card della sezione
    Armi — badge CA, tipo armatura, toggle equipaggia/modifica/elimina. Pulsante "Aggiungi Armatura" apre lo stesso
    dialog condiviso con `force_category="armor"` (titolo dialog "Nuova Armatura"). `_CATEGORIES` (dropdown,
    invariato) vs nuovo `_OGGETTI_CATEGORIES` (`["misc","weapon","tool","magic"]`, esclude "armor" per non mostrare
    le armature due volte nella lista generica).
  - **Verificato con test end-to-end dedicato** (DB temporaneo isolato, mai quello reale): (1) riprodotto
    esplicitamente il bug — due armature equipaggiate contemporaneamente senza esclusione → CA resta quella della
    prima (13, cuoio+DES) anche equipaggiando la corazza di piastre (dovrebbe essere 18); (2) applicata
    `resolve_armor_equip` → la corazza di cuoio viene disequipaggiata automaticamente, CA passa correttamente a 18;
    (3) equipaggiare uno scudo dopo non tocca l'armatura pesante già indossata, CA passa a 20 (18+2) con l'armatura
    ancora equipaggiata. `resolve_armor_equip` testata anche in isolamento (4 casi: seconda armatura espelle la
    prima, scudo non tocca l'armatura, secondo scudo espelle il primo senza toccare l'armatura, id non trovato →
    stato invariato). `py_compile` e `pyflakes` puliti su tutti i file toccati (nessun errore genuino, solo il
    rumore preesistente di `from config.settings import *`).
  - **"Armi (riserva)" — risolto separatamente, stessa sessione**: la seconda parte del messaggio di Davide ("se io
    seleziono equipaggia nell'inventario con quelli di riserva non me li sostituisce a quelli equipaggiati già
    nella sezione armi") riguardava la categoria "Armi (riserva)" della sezione Oggetti generica (`InventoryItem`
    con `category="weapon"`) — un concetto dati COMPLETAMENTE SEPARATO dalla tabella `weapons` dedicata (nessun
    dado danno/proprietà/bonus attacco), nato in origine come solo fallback diagnostico di `_save_weapon_by_name()`
    quando un'arma di partenza non veniva trovata in `equipment/weapons.json` (task #72), non come feature pensata
    per armi di scorta. Presentate a Davide 3 alternative (eliminare la categoria e usare sempre `weapons`/
    estendere il calcolo mani anche a questi item generici/ lasciarli come storage passivo senza equip reale) —
    **scelta: eliminare la categoria**, coerente con lo stesso principio "unica fonte di verità" già applicato in
    questo progetto a `RACE_DATA`/`CLASSES`/`ASI_LEVELS`/ecc.
    - `_save_weapon_by_name()` (`wizard_view.py`/`manual_form.py`): il fallback per nomi arma non trovati nel
      catalogo non ricade più su `create_inventory_item(category="weapon")` — crea comunque la riga in `weapons`,
      ma con `damage_dice`/`damage_type`/`properties` vuoti (compilabili poi dal dialog "Modifica" in Armi). Da
      questo momento nessun nuovo item `category="weapon"` viene più creato da nessun punto del codice.
    - `inventario_tab.py`: rimossa l'opzione "Armi (riserva)" dal Dropdown categoria del dialog Nuovo/Modifica
      Oggetto (non più creabile a mano); riaggiunta dinamicamente SOLO quando si modifica un item che ha già quella
      categoria (etichettata "— legacy"), perché il Dropdown di Flet richiede che `value` compaia tra le `options`
      o il campo appare vuoto.
    - **Migrazione automatica** (`_migrate_legacy_weapon_items()`, chiamata in `InventarioTab.__init__`): per ogni
      personaggio, al primo caricamento della tab Inventario dopo l'aggiornamento, converte silenziosamente ogni
      `InventoryItem` residuo con `category=="weapon"` in una riga vera di `weapons` (stesso tentativo di
      risoluzione dal catalogo, altrimenti statistiche vuote) ed elimina la riga di inventario solo dopo che la
      creazione è andata a buon fine — se una scrittura fallisse, l'item legacy resta visibile e gestibile in
      Oggetti invece di sparire silenziosamente. Idempotente: dopo la prima esecuzione riuscita non resta più nulla
      da migrare per quel personaggio.
    - **Verificato**: test end-to-end (DB temporaneo isolato) sia sulla logica di migrazione in isolamento sia
      instanziando `InventarioTab` reale — un item legacy con nome risolvibile nel catalogo migra con dado
      danno/tipo/proprietà corretti, un item legacy con nome non in catalogo migra comunque con statistiche vuote,
      in entrambi i casi la riga `inventory_items` viene rimossa e non ricompare. `py_compile`/`pyflakes` puliti su
      tutti i file toccati (`inventario_tab.py`, `wizard_view.py`, `manual_form.py`).
- **Avvio audit `monsters.json` (2026-07-11) — scala reale del lavoro scoperta durante l'avvio**: Davide ha chiesto
  di lavorare "completamente" sul file dei mostri, prendendo tutto dal manuale "ED 5.0 Manuale dei mostri.pdf" (353
  pagine, presente tra i file del progetto ma non ancora usato come fonte in questa sessione) senza inventare
  nulla. Prima di trascrivere, verificata la scala reale del lavoro: il manuale contiene **399 blocchi statistici**
  (contati via `grep -c "Classe Armatura"` sul testo estratto, un'occorrenza per blocco — più delle 343 voci già
  presenti in `monsters.json`, perché famiglie come Giganti/Draghi/Angeli hanno più varianti ciascuna con blocco
  proprio), spalmati sulle 353 pagine. **Confermato che il file esistente è contaminato**: la prima voce
  ispezionata (`'TRIDRONE`) aveva un apice iniziale spurio nel nome, "Ciavellotto" invece di "Giavellotto", "ld4 +
  l" invece di "1d4 + 1" (confusione OCR cifra/lettera) e un frammento di testo estraneo "MODRO" in coda alla
  descrizione — stessa famiglia di problemi già vista e risolta altrove nel progetto (feats.json, invocations.json)
  con lo stesso rimedio: **ignorare il vecchio file e ritrascrivere dalle immagini del PDF**, non dal testo OCR.
  - **Verificato che `pdftotext -layout` NON è affidabile su questo manuale**: a differenza del Manuale del
    Giocatore (dove `pdftotext -layout`/`-raw` erano già stati usati con successo per razze/background/talenti), il
    layout a due colonne del Manuale dei Mostri fa sì che `pdftotext` intercali le due colonne riga per riga in
    base alla posizione verticale, producendo un ordine di lettura completamente mescolato (es. il nome "AARAKOCRA"
    appare isolato, seguito dal contenuto di "ABOLETH" prima ancora che appaia il vero testo di Aarakocra). L'unico
    metodo affidabile è la lettura visiva delle pagine renderizzate con `pdftoppm -r 150 -png` (stesso approccio
    già usato per talenti/incantesimi/equipaggiamento), una pagina alla volta.
  - **Schema dati confermato leggendo il codice consumer** (`ui/views/character_sheet/combattimento_tab.py`,
    funzioni `_save_creature`/`_open_manual_creature_dialog`/`_show_creature_sheet`): ogni voce richiede `name`
    (MAIUSCOLO, convertito in title case a display da `monster_display_name()`), `type` (tipo di creatura base, es.
    "Umanoide" — usato anche per il filtro Forma Selvatica del Druido, che accetta solo `type=="Bestia"`), `size`,
    `alignment`, `ac`/`ac_note`, `hp_max`/`hp_formula`, `speed`, i 6 punteggi caratteristica,
    `saving_throws`/`skills` (dict),
    `damage_vulnerabilities`/`damage_resistances`/`damage_immunities`/`condition_immunities` (stringhe), `senses`,
    `languages`, `cr`, `traits`/`actions`/`reactions`/`legendary_actions` (liste di `{"name","description"}`).
    Aggiunto anche un campo `source_page` (numero di pagina del PDF), già previsto come parametro opzionale da
    `create_creature_entry()` ma mai valorizzato dal vecchio file — utile per tracciabilità e per future verifiche
    mirate.
  - **9 mostri trascritti e verificati in questo avvio** (lettura diretta delle immagini pag. 12-22, nessun dato da
    `pdftotext`): Aarakocra (pag. 12), Aboleth (pag. 13), Deva/Planetar/Solar — le 3 varianti di "Angelo" (pag.
    16-18), Ankheg (pag. 19), Arpia (pag. 20), Artiglio Strisciante (pag. 21), Azer (pag. 22). Script Python
    (`build_monsters_batch_a1.py`, eseguito e poi rimosso — non fa parte del codice dell'app) ha sostituito le 6
    voci già presenti con lo stesso nome (Aboleth/Deva/Planetar/Solar/Ankheg/Artiglio Strisciante — tutte con lo
    stesso tipo di contaminazione OCR) e aggiunto le 3 mancanti (Aarakocra/Arpia/Azer, assenti dal file originale).
    Le altre 337 voci non toccate. Verificato: JSON valido, tutti i campi richiesti presenti nelle 9 nuove voci
    (nessuna regressione sulle altre, che restano nello stato pre-esistente — non auditate), `py_compile` su
    `combattimento_tab.py` invariato.
  - **Scala del lavoro rimanente, comunicata esplicitamente a Davide**: 9 blocchi su 399 sono stati verificati con
    lo stesso rigore già applicato al resto del progetto (lettura diretta dell'immagine, nessun dato indovinato). I
    restanti **390 blocchi statistici** richiedono lo stesso processo pagina per pagina — al ritmo sostenuto in
    questo avvio (~1 pagina/mostro per chiamata di lettura immagine), è un lavoro che si estende su molte sessioni
    future, non completabile in un'unica sessione. Si propone di proseguire per lettera/sezione (stesso principio
    già adottato per `equipment/*.json`, un file/blocco alla volta), aggiornando questa checklist ad ogni batch
    completato, così il progresso resta sempre tracciabile e verificabile invece di un'unica trascrizione integrale
    non controllabile a campione.
- **Audit `monsters.json`, batch B5-B14 (2026-07-16) — capitolo completo dei Draghi Puri + Dracolich/Drago d'Ombra,
  sessione non interattiva**: Davide, prima di allontanarsi per un periodo prolungato, ha dato istruzione esplicita
  di proseguire l'audit "quanti più batch possibile" senza fermarsi fino al termine dell'intero manuale, avvisando
  che non avrebbe potuto rispondere a domande nel frattempo ("non fermarti fino a che non hai finito tutto il
  libro"), poi ha dato il via con "vai". Questa nota copre l'intero lavoro svolto in quella finestra non
  interattiva, dalla ripresa da pag. 82 fino al completamento del capitolo dei Draghi a pag. 118 — stesso identico
  metodo già stabilito (lettura visiva delle immagini `pdftoppm -r 150`, mai `pdftotext`/OCR; script Python
  usa-e-getta per batch, poi lasciati sul disco per un limite del sandbox che impedisce `rm`; verifica di chiusura
  ad ogni batch: validità JSON, conteggio+duplicati, `py_compile` su `combattimento_tab.py`).
  - **Batch B5 (pag. 82, 86-91)**: corretto **Doppelganger** (pag. 82) — i punteggi COS/SAG/CAR nel vecchio file
    erano OCR-corrotti a 4/2/11 invece dei corretti 14/12/14, e conteneva 2 tratti-lore inventati ("Truffatori
    Edonisti"/"Cangianti", testo narrativo non presente nel manuale come tratto meccanico) rimossi. Aggiunta la
    famiglia completa **Drago Bianco** (Antico/Adulto/Giovane sostituiti, Cucciolo aggiunto ex-novo).
  - **Batch B6 (pag. 92-99)**: famiglie **Drago Blu** e **Drago Nero** complete (Antico/Adulto/Giovane sostituiti, Cucciolo aggiunto per entrambe).
  - **Batch B7 (pag. 100-103)**: famiglia **Drago Rosso** completa aggiunta ex-novo (nessuna voce pre-esisteva per questo colore) + **Drago Verde Antico** sostituito.
  - **Batch B8**: **Drago Verde** Adulto/Giovane sostituiti + Cucciolo aggiunto, completando la famiglia.
  - **Batch B9 (pag. 104-106)**: famiglia **Drago d'Argento** completa (Antico/Adulto sostituiti, Giovane/Cucciolo aggiunti).
  - **Batch B10**: famiglia **Drago di Bronzo** completa (Antico/Adulto/Giovane sostituiti, Cucciolo aggiunto) + **Drago di Rame Antico** aggiunto ex-novo.
  - **Batch B11**: **Drago di Rame** Adulto sostituito + Giovane/Cucciolo aggiunti, completando la famiglia.
  - **Batch B12**: famiglia **Drago d'Oro** completa (tutte e 4 le età sostituite) + **Drago d'Ottone Antico** sostituito.
  - **Batch B13**: **Drago d'Ottone** Adulto/Giovane sostituiti + Cucciolo aggiunto, completando la famiglia —
    **con questo si chiudono tutti i 10 colori × 4 categorie d'età = 40 stat block di Drago Puro**, tutti
    verificati contro le immagini delle pagine 86-118.
  - **Schema ricorrente stabilito e riusato identico per tutti i 40 blocchi**: categoria Antico/Adulto → Resistenza
    Leggendaria (3/Giorno), Presenza Terrificante, 3 Azioni Leggendarie standard (Individuazione/Attacco di
    Coda/Attacco di Ali costa 2); i draghi metallici (Argento/Bronzo/Rame/Oro/Ottone) aggiungono anche "Cambiare
    Forma" (trasformazione in bestia/umanoide di GS pari o inferiore, testo verbatim identico per tutti); categoria
    Giovane → Multiattacco + arma a soffio, nessuna Presenza Terrificante/Resistenza Leggendaria/Azioni
    Leggendarie/Cambiare Forma; categoria Cucciolo → solo Morso + arma a soffio, nessun Multiattacco. I draghi
    cromatici (Bianco/Nero/Blu/Verde/Rosso) hanno un solo tipo di arma a soffio (cono o linea); i metallici hanno
    "Armi a Soffio (Ricarica 5-6)" con **due** sotto-azioni a scelta (es. Argento: Soffio di Freddo + Soffio
    Paralizzante; Bronzo: Soffio di Fulmini + Soffio Respingente; Rame: Soffio di Acido + Soffio Rallentante; Oro:
    Soffio di Fuoco + Soffio Indebolente; Ottone: Soffio di Fuoco + Soffio di Sonno). Helper Python riusati
    identici in ogni batch script: `frightful(cd)`, `change_shape()`, `legendary_std(cd, dmg)`.
  - **Corruzione pre-esistente confermata su OGNI singola voce toccata**: senza eccezioni, ogni stat block di drago
    già presente nel vecchio `monsters.json` (Doppelganger, tutti i colori almeno per la categoria Antico,
    Dracolich Blu Adulto) si è rivelato corrotto in almeno uno di questi modi al confronto con l'immagine della
    pagina: schema vecchio incompleto/compresso (mancavano
    `traits`/`legendary_actions`/`saving_throws`/`skills`/`senses`/`languages`/`source_page`/`xp`/`ac_note`/`hp_formula`/`condition_immunities`,
    `actions` con solo un campo `text` sintetico invece di `description` completa, dadi danno incoerenti con i
    modificatori di caratteristica elencati), oppure corruzione OCR pura (cifre/lettere confuse), oppure testo di
    lore estraneo incollato dentro la descrizione di un'azione — confermando ancora una volta, su scala ora molto
    più ampia (42 voci), che la sola presenza di un campo con nome plausibile nel vecchio JSON non garantisce
    affatto che il contenuto sia corretto: ogni voce va sempre riverificata contro l'immagine sorgente, mai
    fidandosi del JSON esistente.
  - **Batch B14 (pag. 83-85)**: chiuso il sotto-capitolo Dracolich/Drago d'Ombra che segue immediatamente i Draghi
    Puri. **Confermato leggendo il testo del manuale** (pag. 83) che Dracolich è un vero e proprio
    **archetipo/template**, applicabile a qualunque drago puro **antico o adulto** (mai più giovane, mai a creature
    "tipo drago" come pseudodraghi/viverne, e un Drago d'Ombra non può MAI diventare un dracolich perché ha già
    perso la sua fisiologia vivente) — il manuale fornisce solo l'esempio completamente sviluppato "Dracolich Blu
    Adulto" più le regole generiche di trasformazione (cambio tipo in Non Morto, resistenza/immunità/vantaggio
    salvezza aggiuntivi, Resistenza Leggendaria aggiunta). Stessa struttura a template per **Drago d'Ombra** (pag.
    84): applicabile solo a un drago puro nato o rimasto per anni nella Coltre Oscura, un Dracolich non può
    diventarlo per lo stesso motivo inverso; unico esempio completo fornito: "Drago d'Ombra Rosso Giovane" (pag.
    85).
    - **Decisione di scope, non ancora un meccanismo generico implementato in app**: trascritti SOLO i due stat
      block d'esempio completamente sviluppati dal manuale (Dracolich Blu Adulto, Drago d'Ombra Rosso Giovane),
      esattamente come stampati — non generate combinazioni aggiuntive colore×età per questi due archetipi, che
      richiederebbero applicare a mano le regole di trasformazione a ciascuno dei 40 blocchi base (lavoro legittimo
      ma non uno stat block "stampato" nel manuale, quindi fuori dal principio "trascrivi solo ciò che è scritto,
      non inventare"). Se in futuro serve un Dracolich/Drago d'Ombra di un colore o età diversi, andranno applicate
      a mano le regole di trasformazione già trascritte nel testo delle due sezioni (pag. 83-84), non generate per
      estrapolazione automatica.
    - **DRACOLICH BLU ADULTO corretto** (sostituita la voce pre-esistente, gravemente corrotta: CD/tiri salvezza
      incoerenti con le physical stats attese per un drago blu adulto, "Ciorno" invece di "Giorno", confusione
      cifra/lettera "2dl0"/"ldlO", e testo di lore sul Drago d'Ombra mescolato dentro la descrizione dell'azione
      Morso). Nuovo testo pulito: CA 19, PF 225 (18d12+108), CD Presenza Terrificante 18, Soffio di Fulmini
      (Ricarica 5-6) 66 (12d10) danni, Resistenza Leggendaria (3/Giorno) + Resistenza alla Magia, Immunità alle
      Condizioni (affascinato/avvelenato/indebolimento/paralizzato/spaventato — il dracolich NON è immune a
      spaventato di suo, ma il template lo aggiunge esplicitamente).
    - **DRAGO D'OMBRA ROSSO GIOVANE aggiunto ex-novo** (non esisteva alcuna voce prima): CA 18, PF 178 (17d10+85),
      tratti Ombra Vivente (resistenza a tutti i danni tranne forza/psichici/radiosi in luce fioca/oscurità) +
      Furtività d'Ombra (Nascondersi come azione bonus) + Sensibilità alla Luce del Sole + raddoppio competenza
      Furtività; Morso e Soffio (cono 9m, 56/16d6 danni) convertiti a danno **necrotico** invece del tipo standard
      del Drago Rosso (fuoco), coerente con la regola del template "Nuova Azione: Morso"/"Nuova Azione: Soffio
      d'Ombra"; un umanoide ucciso da questi danni genera un'ombra non morta sotto il controllo del drago.
  - **Verifica di chiusura di tutta la sessione B5-B14**: 371 voci totali in `monsters.json` (era 356 all'inizio di
    questa continuazione), zero nomi duplicati, tutti i 40 stat block di drago puro presenti e verificati
    (confermato via script Python che elenca tutte le combinazioni colore×età attese), Dracolich Blu Adulto e Drago
    d'Ombra Rosso Giovane confermati presenti e non duplicati, `python3 -m py_compile` su `combattimento_tab.py`
    sempre passato dopo ogni batch. Restano correttamente NON toccati in questa sessione: Drago Fatato,
    Pseudodrago, Testuggine Dragona (creature "tipo drago" ma non draghi puri, già pre-esistenti, non verificati in
    questa sessione).
- **Audit `monsters.json`, batch B15 (2026-07-16) — coda capitolo D, capitoli Elementale/Elfo Drow, inizio capitolo
  F, sessione non interattiva prosegue senza interruzione**: stessa finestra "vai" di B5-B14, nessun nuovo
  messaggio di Davide nel frattempo. Renderizzate e lette tutte le 22 pagine 119-140 (`pdftoppm -r 150`, un secondo
  passaggio mirato per completare pag. 137-140 dopo un timeout del sandbox che aveva comunque completato il
  rendering in background, e un terzo passaggio per rigenerare pag. 136 dopo un errore "media removed" del primo
  file prodotto), poi scritte in un'unica infornata da 24 stat block (batch_b15.py):
  - **DRAGO FATATO** (pag. 119) — caso particolare: un solo stat block rappresenta più varianti colore/età tramite
    una tabella "Colori dell'Età" (Rosso 5 anni o meno → Viola 51+ anni) e incantesimi innati che si aggiungono
    progressivamente col cambio colore (nuovo trucchetto/incantesimo per ciascuna soglia, tutti trascritti nel
    tratto "Incantesimi Innati"); CD Sfida differenziato esplicitamente dal manuale stesso: 1
    (rosso/arancione/giallo) o 2 (verde/blu/indaco/viola) — riportato come stringa descrittiva nei campi `cr`/`xp`
    invece di un singolo numero, dato che il manuale stesso non ne fornisce uno solo per questa creatura.
  - **DRIADE, DRIDER, DUERGAR** (pag. 120-122) — nessuna particolarità di schema.
  - **Capitolo Elementale completo** (pag. 123-125): Elementale del Fuoco/dell'Acqua/dell'Aria/della Terra, tutti
    CR 5. Pag. 123 conteneva solo lore generica del capitolo (nessuno stat block autonomo).
  - **Capitolo Elfo Drow completo** (pag. 126-129): Drow base (CR 1/4), Drow Combattente Scelto (CR 5, con reazione
    Parata), Drow Mago (CR 7, incantatore di 10° livello da mago), Drow Sacerdotessa di Lolth (CR 8, incantatrice
    di 10° livello da chierico, evocazione yochlol). Pag. 126-127 lore generica (retaggio fatato, sensibilità al
    sole, organizzazione sociale) senza stat block proprio.
  - **EMPIREO** (pag. 130) — CR 23, Celestiale titano, con Resistenza Leggendaria e 3 Azioni Leggendarie.
  - **ETTERCAP, ETTIN** (pag. 131-132) — nessuna particolarità di schema. Una variante opzionale "Garrota di
    Ragnatela" per l'Ettercap (riquadro homebrew-alternativo nel manuale) è stata deliberatamente NON incorporata
    nello stat block base, stessa scelta di scope già adottata per varianti opzionali simili in altre
    creature/background di questo progetto (si trascrive solo lo stat block canonico, le varianti restano testo di
    riferimento nel manuale).
  - **FANTASMA, FATALE DELL'ACQUA, FAUCE GORGOGLIANTE, FLUMPH, FOMORIAN** (pag. 133-137) — nessuna particolarità di schema.
  - **Capitolo Fungo completo** (pag. 138-139): Boleto Stridente (CR 0), Fungo Viola (CR 1/4), Spora Gassosa (CR
    1/2, esplode a 0 PF con malattia contagiosa che genera nuove spore). Pag. 138 lore generica del capitolo senza
    stat block proprio.
  - **FUOCO FATUO** (pag. 140) — chiude il range di questo batch.
  - **Verifica di chiusura**: `Replaced: 21, Added: 3, Total entries now: 374` (i 21 "replaced" erano voci già
    pre-esistenti nel vecchio file con dati da riverificare/correggere secondo lo stesso principio "non fidarsi del
    JSON esistente" già confermato sistematicamente nei batch precedenti; i 3 "added" — Boleto Stridente, Fungo
    Viola, Spora Gassosa — erano del tutto assenti). Confermato via script Python: 374 voci totali, zero duplicati,
    tutti e 24 i nomi di questo batch presenti. `python3 -m py_compile` su `combattimento_tab.py` passato.
- **Audit `monsters.json`, batch B16 (2026-07-16) — Fustigatore/Galeb Duhr/Gargoyle, capitolo Genio, capitolo
  Gigante, sessione non interattiva prosegue senza interruzione**: stessa finestra "vai", nessun nuovo messaggio di
  Davide. Renderizzate e lette 20 pagine (141-160, `pdftoppm -r 150`), di cui solo 15 con uno stat block reale — le
  rimanenti sono lore pura (introduzioni di capitolo/sottorazza senza meccanica, tra cui l'intero avvio del
  capitolo Gith a pag. 159-160, i cui stat block Githyanki/Githzerai ricadranno nel prossimo batch):
  - **FUSTIGATORE** (Roper, pag. 141), **GALEB DUHR** (pag. 142), **GARGOYLE** (pag. 143) — nessuna particolarità di schema.
  - **Capitolo Genio completo** (pag. 144-149): Dao (CR 11), Djinni (CR 11), Efreeti (CR 11), Marid (CR 11) — tutti
    e 4 i geni nobili con Incantesimi Innati propri e "Dipartita Elementale" (nessun cadavere lasciato alla morte,
    solo gli oggetti indossati/trasportati). Pag. 144-145 lore pura (introduzione Genio, sotto-lore
    Dao/Djinni/Efreeti/Marid) senza alcuno stat block.
  - **GHAST, GHOUL** (pag. 150) — nessuna particolarità di schema.
  - **Capitolo Gigante completo, le 6 sottorazze principali** (pag. 156-158): Gigante del Fuoco (CR 9), del Gelo
    (CR 8), delle Colline (CR 5), delle Nuvole (CR 9, allineamento misto 50%/50% riportato come stringa
    descrittiva), delle Pietre (CR 7, con reazione Afferrare Roccia), delle Tempeste (CR 13, Anfibio + Colpo di
    Fulmine). Pag. 151-155 lore pura (introduzione Gigante, l'Ordinamento/gerarchia sociale, le 6 sottosezioni
    narrative Fuoco/Gelo/Colline/Nuvole/Pietre/Tempeste, sidebar "Divinità dei Giganti") senza alcuno stat block —
    le illustrazioni comparative di altezza a pag. 152/155 sono puro riferimento visivo, nessun dato meccanico.
  - **Verifica di chiusura**: `Replaced: 12, Added: 3, Total entries now: 377` (i 3 "added" — le 3 varianti di
    Gigante non ancora presenti nel vecchio file — gli altri 12 erano già presenti ma da riverificare/correggere).
    Confermato via script Python: 377 voci totali, zero duplicati, tutti i 15 nomi di questo batch presenti.
    `python3 -m py_compile` su `combattimento_tab.py` passato.
- **Audit `monsters.json`, batch B17 (2026-07-16/17) — coda capitolo Gith, capitolo Gnoll, Gnomo delle Profondità,
  capitolo Goblin, capitolo Golem, Gorgone/Grell/Grick/Grifone/Grimlock, Guardiano Protettore, capitolo Hobgoblin,
  sessione non interattiva prosegue senza interruzione**: stessa finestra "vai" aperta da Davide prima di
  allontanarsi, nessun nuovo messaggio nel frattempo. Renderizzate e lette tutte le 20 pagine 161-180 (`pdftoppm -r
  150`), di cui 16 con almeno uno stat block reale — pag. 163 (introduzione lore del capitolo Gnoll), 166
  (introduzione lore del capitolo Goblin), 168 (introduzione lore del capitolo Golem) e 178 (introduzione lore del
  capitolo Hobgoblin) sono risultate pura narrativa di capitolo senza alcun blocco statistico, confermate lette per
  intero e non saltate.
  - **GITHYANKI COMBATTENTE, GITHYANKI CAVALIERE** (pag. 161) — entrambi con "Incantesimi Innati (Psionici)" su
    Intelligenza; il Cavaliere ha la clausola speciale sullo Spadone d'Argento che permette, con un colpo critico
    su un bersaglio in un corpo astrale, di recidere il cordone d'argento anziché infliggere danni.
  - **GITHZERAI MONACO, GITHZERAI ZERTH** (pag. 162) — entrambi con "Incantesimi Innati (Psionici)" su Saggezza e
    il tratto "Difesa Psichica" (CA include il modificatore di Saggezza finché senza armatura/scudo).
  - **GNOLL SIGNORE DEL BRANCO, GNOLL, GNOLL ZANNA DI YEENOGHU** (pag. 164) — tutti e tre condividono il tratto
    "Furia" (attacco extra con azione bonus dopo aver ridotto una creatura a 0 PF in mischia); lo Zanna di Yeenoghu
    è classificato "Immondo" (non Umanoide) e il suo attacco di Morso infligge anche danno da veleno via TS su
    Costituzione.
  - **GNOMO DELLE PROFONDITÀ (SVIRFNEBLIN)** (pag. 165) — Incantesimi Innati su Intelligenza (anti-individuazione a
    volontà, camuffare se stesso/cecità e sordità/sfocatura 1/giorno ciascuno), oltre a Mimetismo nella Pietra e
    Astuzia Gnomesca.
  - **GOBLIN, GOBLIN CAPO** (pag. 167) — il Goblin Capo ha la reazione "Sviare Attacco" (scambia posto con un altro goblin entro 1,5 m, che diventa il nuovo bersaglio).
  - **Capitolo Golem completo** (pag. 169-171): Golem di Argilla (CR 9, Berserk + attacco che riduce il massimo dei
    PF), di Carne (CR 5, Berserk placabile dal creatore con Persuasione CD 15), di Ferro (CR 16, Soffio di Veleno),
    di Pietra (CR 10, Lentezza) — tutti e 4 condividono Forma Immutabile, Resistenza alla Magia, Armi Magiche.
  - **GORGONE** (pag. 172), **GRELL** (pag. 173), **GRICK, GRICK ALFA** (pag. 174), **GRIFONE** (pag. 175),
    **GRIMLOCK** (pag. 176) — nessuna particolarità di schema; il Grell ha immunità a fulmine e alle condizioni
    accecato/prono, oltre alla vista cieca come unico senso (nessuna vista normale).
  - **GUARDIANO PROTETTORE** (pag. 177) — costrutto con il tratto "Incantesimo Custodito" (può lanciare un
    incantesimo di 4° livello o inferiore custodito in precedenza dal portatore dell'amuleto) e la reazione
    "Protettore" (+2 CA al portatore entro 1,5 m).
  - **Capitolo Hobgoblin, le prime 3 varianti** (pag. 179-180): Hobgoblin, Hobgoblin Capitano, Hobgoblin Signore
    della Guerra — tutti condividono "Vantaggio Marziale" (danno extra 1/turno se il bersaglio ha un alleato
    dell'hobgoblin non incapacitato entro 1,5 m), Capitano e Signore della Guerra hanno anche "Autorità" (dado d4
    bonus a tiro per colpire/salvezza di un alleato entro 9 m); il Signore della Guerra ha inoltre la reazione
    "Parata" (+3 CA contro un attacco in mischia).
  - **Verifica di chiusura**: `Replaced: 21, Added: 3, Total entries now: 380` (i 3 "added" — Gnomo delle
    Profondità, Guardiano Protettore, Hobgoblin Signore della Guerra, assenti dal vecchio file — gli altri 21 erano
    già presenti ma da riverificare/correggere, incluse le 4 voci Githyanki/Githzerai mai auditate prima).
    Confermato via script Python: 380 voci totali, zero duplicati, tutti i 24 nomi di questo batch presenti.
    `python3 -m py_compile` su `combattimento_tab.py` passato. Sessione proseguita subito dopo con il capitolo
    successivo (Homunculus/Idra, pag. 181+) senza fermarsi, come da istruzione di Davide.
- **Audit `monsters.json`, batch B18 (2026-07-17) — Idra, Ippogrifo, Kenku, Kraken, capitolo Kuo-toa, Lamia,
  capitolo Licantropo, Lich, capitolo Lucertoloide, Magmin, sessione non interattiva prosegue dopo "riprendi da
  dove hai lasciato"**: Davide non ancora tornato, ripreso il lavoro esattamente da dove interrotto (pag. 181),
  stesso metodo (lettura visiva `pdftoppm -r 150`, mai `pdftotext`). Renderizzate e lette tutte le 20 pagine
  181-200.
  - **IDRA** (pag. 181) — CR8, tratti "Teste Multiple" (vantaggio TS contro accecato/affascinato/assordato/privo di
    sensi/spaventato/stordito finché ha più di una testa; muore una testa ogni 25+ danni subiti in un turno;
    ricrescono due teste per ogni testa morta a fine turno, +10 PF ciascuna, a meno che non abbia subito danni da
    fuoco nel frattempo) e "Teste Reattive" (una reazione extra per opportunità per ogni testa oltre la prima);
    Multiattacco = un morso per ogni testa posseduta.
  - **IPPOGRIFO** (pag. 182) — nessuna particolarità di schema, CR1.
  - **KENKU** (pag. 183) — tratto "Imitare" (imita qualsiasi suono sentito, CD 14 Intuizione per riconoscere
    l'imitazione) e "Imboscata" (vantaggio nel primo round contro chi sorprende); linguaggi particolari: capisce
    Auran e Comune ma parla solo tramite Imitare.
  - **KRAKEN** (pag. 185, CR23) — Mastodontica (titano); tratti Anfibio/Libertà di Movimento/Mostro da Assedio
    (danni doppi a oggetti/strutture); Morso può inghiottire creature Grandi o inferiori (danno acido continuo,
    copertura totale, rigurgito su 50+ danni in un turno o CD 25 Costituzione); Tentacolo afferra (10 tentacoli
    indipendenti); Scagliare; Tempesta di Fulmini; 3 Azioni Leggendarie (Attacco di Tentacolo/Scagliare, Tempesta
    di Fulmini costa 2, Nube di Inchiostro costa 3). **Pag. 184 "Effetti Regionali"/pag. 185 stessa sezione lette
    per intero** (controllo meteo entro 9 km, elementali dell'acqua, fascino su creature acquatiche INT≤2) —
    **nessun campo schema per lair actions/effetti regionali, non trascritti nel JSON**, stesso principio già
    stabilito per il Demilich (batch B3) e riapplicato identico qui.
  - **Capitolo Kuo-toa completo** (pag. 186-188): Kuo-toa base (CR1/4, reazione "Scudo Viscoso" che invischia
    l'arma dell'attaccante), Kuo-toa Gran Sacerdote (CR6, incantatore 10° livello da chierico), Kuo-toa Esecutore
    (CR1, incantatore 2° livello, Bastone Tenaglia che afferra), Kuo-toa Sovrintendente (variante sidebar pag. 186,
    CR3 — stesse statistiche dell'Esecutore ma CA13 con mod. Saggezza, perde Incantesimi, sostituisce le azioni con
    Multiattacco morso+2 colpi senz'armi, il colpo senz'armi infligge anche danno da fulmine e nega reazioni).
    Tutti e 4 condividono Anfibio/Percezione Ultraterrena/Sgusciante/Sensibilità alla Luce del Sole.
  - **LAMIA** (pag. 189, CR4) — Incantesimi Innati su Carisma (camuffare se stesso/immagine maggiore a volontà;
    charme su persone/immagine speculare/scrutare/suggestione 3/giorno; costrizione 1/giorno); Tocco Intossicante
    (maledizione: svantaggio TS Saggezza e prove di caratteristica per 1 ora).
  - **Capitolo Licantropo completo** (pag. 190-195, con pag. 190/191 lore-only — introduzione capitolo + sotto-lore
    Lupo/Orso/Tigre/Topo Mannaro, nessuno stat block su quelle 2 pagine): Cinghiale Mannaro (CR4, Carica +
    Implacabile ricarica riposo), Orso Mannaro (CR5, il più potente, Ascia Bipenne in forma umanoide), Lupo Mannaro
    (CR3), Tigre Mannara (CR4, Balzo con attacco bonus di morso se il bersaglio cade prono), Topo Mannaro (CR2, il
    più debole) — tutti e 5 condividono Mutaforma (3 forme: umanoide/ibrida/animale, statistiche identiche salvo CA
    e taglia) e immunità a danni non magici da armi non argentate; ogni morso in forma ibrida/animale può
    contagiare un umanoide (TS Costituzione).
  - **LICH** (pag. 196-197, CR21) — Resistenza Leggendaria 3/Giorno, Ringiovanimento (torna in vita in 1d10 giorni
    presso il filatterio), Incantesimi (incantatore 18° livello da mago, lista completa 0°-9°), Resistenza allo
    Scacciare; Tocco Paralizzante; 3 Azioni Leggendarie (Trucchetto, Tocco Paralizzante costa 2, Sguardo
    Terrificante costa 2, Distruggere Vita costa 3). **Pag. 197 "La Tana di un Lich"/"Azioni di Tana" letta per
    intero** (recupero slot, cordone di energia negativa, evocazione spiriti di creature morte nella tana) —
    **stesso principio del Kraken: nessun campo schema, non trascritta nel JSON**.
  - **Capitolo Lucertoloide, prime 3 varianti** (pag. 198-199): Lucertoloide base (CR1/2), Lucertoloide Sciamano
    (CR2, incantatore 5° livello da druido, Cambiare Forma in coccodrillo con ricarica), Re/Regina Lucertola (CR4,
    immunità spaventato, tratto "Trafiggere" 1/turno col tridente che dà PF temporanei pari al danno extra
    inflitto) — tutti e 3 condividono Trattenere il Respiro (15 min). **Lucertoloide Sciamano NON trascritta come
    pura variante**: ha uno stat block completo proprio con incantatore/Cambiare Forma, non solo un delta su
    un'altra voce.
  - **MAGMIN** (pag. 200, CR1/2) — chiude il range di questo batch; tratti "Esplosione Mortale" (danno da fuoco ad
    area alla morte, incendia oggetti infiammabili) e "Illuminazione Fiammeggiante" (azione bonus per
    infiammarsi/estinguersi, controlla la propria fonte di luce).
  - **Verifica di chiusura**: `Replaced: 9, Added: 10, Total entries now: 390` (i 9 "replaced" — Idra, Ippogrifo,
    Kenku, Kraken, Kuo-toa, Kuo-toa Gran Sacerdote, Kuo-toa Esecutore, Lucertoloide, Lich — erano già presenti nel
    vecchio file ma da riverificare/correggere; i 10 "added" — Kuo-toa Sovrintendente, Lamia,
    Cinghiale/Orso/Lupo/Tigre/Topo Mannaro, Lucertoloide Sciamano, Re/Regina Lucertola, Magmin — erano assenti).
    Confermato via script Python: 390 voci totali, zero duplicati, tutti i 19 nomi di questo batch presenti.
    `python3 -m py_compile` su `combattimento_tab.py` passato. Sessione proseguita subito dopo con il capitolo
    successivo (pag. 201+, presumibilmente Manticora e oltre) senza fermarsi, come da istruzione originale di
    Davide.
- **Audit `monsters.json`, batch B19 (2026-07-17) — capitolo Maligno, Manticora, Manto Assassino, Mantoscuro,
  Marinide, Medusa, capitolo Megera, capitolo Melma, capitolo Mephit, Merrow, Mezzodrago Rosso Veterano, sessione
  non interattiva prosegue senza interruzione**: stesso metodo (lettura visiva `pdftoppm -r 150`, mai `pdftotext`).
  Renderizzate e lette tutte le 20 pagine 201-220.
  - **Capitolo Maligno** (pag. 201-202, con pag. 201 lore-only, nessuno stat block): Ago Maligno (CR1/4, vista
    cieca, attacco a distanza con aghi), Arbusto Maligno (CR1/8, Falso Aspetto), Rampicante Maligno (CR1/2,
    Stritolare afferra + Vegetali Intralcianti ad area con ricarica) — tutti e 3 condividono vista
    cieca/comprendono ma non parlano.
  - **MANTICORA** (pag. 203, CR3) — Ricrescita degli Aculei Caudali (24 totali, ricrescono a riposo lungo), Multiattacco morso+2 artigli o 3 aculei caudali a distanza.
  - **MANTO ASSASSINO** (pag. 204, CR8) — Trasferire Danni (dimezza i danni subiti mentre avvinghiato, l'altra metà
    va alla vittima), Falso Aspetto, Sensibilità alla Luce (svantaggio con luce intensa); Morso avvinghia/acceca se
    avvinghiato alla testa; Gemito spaventa ad area; Allucinazioni (3 duplicati illusori, ricarica a riposo).
  - **MANTOSCURO** (pag. 205, CR1/2) — Senso Radar (vista cieca inutile se assordato), Falso Aspetto
    (stalattite/stalagmite); Schiacciare avvinghia (velocità 0, azione bonus per staccarsi); Aura di Oscurità
    1/giorno (dissolve luce di 2° livello o inferiore).
  - **MARINIDE** (pag. 206, CR1/8) — Anfibio, nessuna particolarità ulteriore di schema.
  - **MEDUSA** (pag. 207, CR6) — Sguardo Pietrificante (TS Costituzione, fallimento di 5+ = pietrificazione
    istantanea, altrimenti trattenuta con TS ripetuto; distogliere lo sguardo evita il TS iniziale ma nega la vista
    della medusa; se vede il proprio riflesso subisce il proprio sguardo); Multiattacco chioma di serpenti
    (morso+veleno) + 2 spada corta, oppure 2 arco lungo (con veleno).
  - **Capitolo Megera, prime 3 varianti** (pag. 208-211, con pag. 208 lore-only + sidebar meccanica "Congreghe di
    Megere" — nessun campo schema, letta ma non trascritta; sidebar oggetti magici da Megera Notturna su pag. 211
    letta ma non pertinente allo schema mostro): Megera Marina (CR2, Anfibio, Aspetto Orripilante spaventa ad area,
    Sguardo Mortale riduce a 0 PF una creatura già spaventata, Aspetto Illusorio), Megera Notturna (CR5,
    Incantesimi Innati su Carisma, Resistenza alla Magia, Cambiare Forma, Forma Eterea con pietra del cuore,
    Infestare Incubi 1/giorno — danneggia il massimo PF di un umanoide addormentato sul Piano Etereo), Megera Verde
    (CR3, Anfibio, Incantesimi Innati, Imitare voci/versi, Aspetto Illusorio, Passaggio Invisibile).
  - **Capitolo Melma, 4 varianti** (pag. 212-215, con pag. 212 lore-only del capitolo + sidebar "Variante: Melma
    Grigia Psichica" — INT 6 e azione psichica aggiuntiva, letta ma deliberatamente NON incorporata nella voce base
    Melma Grigia, stesso principio delle varianti opzionali già stabilito per l'Arma su Asta del Diavolo d'Ossa):
    Ameba Paglierina (CR2, Amorfo, Movimenti del Ragno, Scindersi su danni da fulmine/taglienti), Cubo Gelatinoso
    (CR2, occupa l'intero spazio/Trasparente, Avviluppare con TS Destrezza), Melma Grigia (CR1/2, Corrodere il
    Metallo — penalità permanente ad armi/armature di metallo, Falso Aspetto), Protoplasma Nero (CR4, Forma
    Corrosiva su legno/metallo, Movimenti del Ragno, Scindersi).
  - **Capitolo Mephit completo, tutti e 6 i tipi** (pag. 216-218, con sidebar "Variante: Evocare Mephit" su pag.
    218 letta ma deliberatamente NON incorporata in nessuno dei 6 stat block base — nessuno dei 6 la include nella
    propria lista Azioni, coerente con l'assenza dall'elenco ufficiale): Mephit del Fango (CR1/4, Esplosione
    Mortale trattiene, Falso Aspetto), Mephit del Fumo (CR1/4, Esplosione Mortale crea oscurità, Incantesimo Innato
    luci danzanti, Soffio di Cenere acceca), Mephit del Ghiaccio (CR1/2, vulnerabile a contundente, Incantesimo
    Innato nube di nebbia, Soffio di Gelo), Mephit del Magma (CR1/2, vulnerabile a freddo, Incantesimo Innato
    riscaldare il metallo, Soffio di Fuoco), Mephit del Vapore (CR1/4, Incantesimo Innato sfocatura, Soffio di
    Vapore), Mephit della Polvere (CR1/2, vulnerabile a fuoco, Incantesimo Innato sonno, Soffio Accecante) — tutti
    e 6 condividono Esplosione Mortale alla morte + immunità veleno/avvelenato.
  - **MERROW** (pag. 219, CR2) — Anfibio, Multiattacco morso + artigli/arpione (arpione a distanza tira il bersaglio più vicino su contesa di Forza).
  - **MEZZODRAGO ROSSO VETERANO** (esempio completo del template Mezzodrago/Half-Dragon, pag. 220, CR5) — le regole
    generiche del template (applicabile a qualunque umanoide/gigante/mostruosità con discendenza di un drago puro,
    bonus a CA/PF/velocità/resistenza danno/soffio in base al colore) sono prosa/tabella priva di campo schema
    dedicato e NON trascritte come dato autonomo, stesso principio già stabilito per Dracolich/Drago d'Ombra (batch
    B5-B14) — ma l'esempio interamente statuito fornito dal manuale (un Veterano umano con Discendenza Rossa
    applicata) è uno stat block completo a sé stante ed è stato trascritto come voce propria (Soffio di Fuoco
    ricarica 5-6, resistenza al fuoco, scurovisione + vista cieca 3m).
  - **Verifica di chiusura**: `Replaced: 20, Added: 3, Total entries now: 393` (i 20 "replaced" erano già presenti
    nel vecchio file con la consueta contaminazione OCR/traduzione da verificare; i 3 "added" — Kuo-toa
    Sovrintendente escluso qui, sono in realtà Ameba Paglierina, Cubo Gelatinoso, Protoplasma Nero, tutti assenti
    dal vecchio file). Confermato via script Python: 393 voci totali, zero duplicati, tutti i 23 nomi di questo
    batch presenti. `python3 -m py_compile` su `combattimento_tab.py` passato. Sessione proseguita subito dopo con
    il capitolo successivo (pag. 221+) senza fermarsi, come da istruzione originale di Davide.
- **Audit `monsters.json`, batch B20 (2026-07-17) — capitolo Miconide, Mimic, capitolo Mind Flayer, Minotauro,
  capitolo Modron, capitolo Mummia, capitolo Naga, Nothic, capitolo Oggetto Animato, Ogre/Mezzogre, sessione non
  interattiva prosegue senza interruzione, il file JSON raggiunge 399 voci totali**: stesso metodo (lettura visiva
  `pdftoppm -r 150`, mai `pdftotext`). Renderizzate e lette tutte le 20 pagine 221-240 (pg-240 rigenerata una
  seconda volta per un errore di trasmissione dell'immagine, stesso contenuto).
  - **Capitolo Miconide completo** (pag. 221-223): Miconide Germoglio (CR0, Spore Segnalatrici/Eliofobia/Spore
    Comunicanti), Miconide Adulto (CR1/2, + Spore Pacificatrici stordenti), Miconide Sovrano (CR2, + Spore Animanti
    che creano un servitore delle spore da un cadavere + Spore Allucinogene) + **archetipo "Servitore delle
    Spore"** (pag. 221, regole generiche di trasformazione di una creatura in servitore vegetale — prosa/tabella
    priva di campo schema dedicato, NON trascritta come dato autonomo, stesso principio già stabilito per i
    template Dracolich/Drago d'Ombra/Mezzodrago) con l'esempio interamente statuito **Quaggoth Servitore delle
    Spore** (CR1) trascritto come voce a sé.
  - **MIMIC** (pag. 224, CR2) — Mutaforma (si trasforma in oggetto/torna alla forma amorfa), Adesivo (afferra ciò
    che tocca in forma di oggetto), Falso Aspetto, Lottatore (vantaggio in lotta); Pseudopode + Morso con danno da
    acido.
  - **Capitolo Mind Flayer, 2 varianti** (pag. 225-226, con pag. 225 lore-only): Mind Flayer (CR7, Resistenza alla
    Magia, Incantesimi Innati psionici su Intelligenza, Tentacoli che afferrano/stordiscono, Estrarre Cervello
    letale su umanoidi incapacitati, Assalto Mentale ad area con ricarica), Mind Flayer Arcanista (variante
    sidebar, CR8 — stesse statistiche base + tratto "Incantesimi" aggiuntivo, incantatore di 10° livello da mago
    con lista completa 1°-5° — trascritta come voce a sé essendo un vero stat block alternativo completo, non solo
    un delta minore).
  - **MINOTAURO** (pag. 227, CR3) — Carica (danno perforante extra + spinta/prono se percorre 3+ m in linea retta),
    Ricordo Labirintico, Avventato (vantaggio auto-concesso ai propri attacchi ma vantaggio anche ai nemici contro
    di lui).
  - **Capitolo Modron completo, tutti e 5 i gradi** (pag. 228-230, con "Variante: Modron Fuori Controllo" sulla
    stessa pagina 228 — regola di eccezione applicabile a un modron di qualunque grado già esistente, nessun campo
    schema dedicato, non trascritta separatamente): Monodrone (CR1/8), Duodrone (CR1/4), Tridrone (CR1/2), Quadrone
    (CR1, volante, arco corto), Pentadrone (CR2, Gas Paralizzante ad area con ricarica) — tutti e 5 condividono
    Mente Assiomatica (immuni a coercizione contraria alle istruzioni) e Disintegrazione alla morte.
  - **Capitolo Mummia, 2 varianti** (pag. 231-233, con pag. 231 lore-only del capitolo — introduzione Mummia +
    Signore delle Mummie + "Il Cuore del Signore delle Mummie"/regole di indistruttibilità del cuore, nessuno stat
    block su quella pagina): Mummia (CR3, Pugno di Putrefazione con maledizione permanente al massimo PF, Sguardo
    Funesto spaventa/paralizza), Signore delle Mummie (CR15, Resistenza alla Magia, Ringiovanimento, Incantesimi da
    chierico 10° livello, 3 Azioni Leggendarie — Attacco/Polvere Accecante/Parola Blasfema costa 2/Incanalare
    Energia Negativa costa 2/Turbine di Sabbia costa 2). **Pag. 231 "La Tana di un Signore delle Mummie"/pag.
    232-233 "Azioni di Tana"/"Effetti Regionali" lette per intero** (individuazione creature viventi, vantaggio TS
    contro scacciare non morti, danno necrotico su incantesimi di 4° livello o inferiori nella tana; cibo/bevande
    rovinati, divinazione inaffidabile, maledizione su furto di tesori) — **stesso principio del Kraken/Lich:
    nessun campo schema per lair actions/effetti regionali, non trascritte nel JSON**.
  - **Capitolo Naga completo, tutte e 3 le varietà** (pag. 234-235): Naga d'Ossa (CR4, non morto, Incantesimi 5°
    livello con **doppia lista alternativa** — chierico se era naga guardiana in vita, mago se era naga spirituale
    in vita, entrambe trascritte nello stesso tratto "Incantesimi" come da manuale, non due voci separate essendo
    la stessa identica creatura con background narrativo variabile), Naga Spirituale (CR8, mostruosità,
    Ringiovanimento, Incantesimi 10° livello da mago), Naga Guardiana (CR10, mostruosità, Ringiovanimento,
    Incantesimi 11° livello da chierico, Sputo Velenoso a distanza) — tutte e 3 condividono Morso con danno da
    veleno collegato.
  - **NOTHIC** (pag. 236, CR2) — Vista Acuta, Sguardo Marcescente (danno necrotico a distanza), Intuizione Innaturale (prova contrapposta Inganno/Intuizione per apprendere un segreto).
  - **Capitolo Oggetto Animato completo, 3 varianti** (pag. 237-238): Armatura Animata (CR1, Suscettibilità
    all'Anti-magia, Falso Aspetto), Spada Volante (CR1/4, vola, stesso Falso Aspetto/Suscettibilità), Tappeto
    Soffocante (CR2, Trasferire Danni dimezzati in lotta, Soffocare afferra/acceca/soffoca) — tutti e 3 condividono
    immunità psichico/veleno e l'intera lista di immunità alle condizioni tipica dei costrutti senza intelletto.
  - **OGRE, MEZZOGRE** (pag. 239-240): Ogre (CR2, Randello Pesante/Giavellotto, nessuna particolarità di schema), Mezzogre/Ogrillon (CR1, prole di Ogre+umanoide, Ascia da Battaglia versatile).
  - **Verifica di chiusura**: `Replaced: 18, Added: 6, Total entries now: 399` (i 18 "replaced" erano già presenti
    nel vecchio file con la consueta contaminazione OCR/traduzione da riverificare; i 6 "added" — Quaggoth
    Servitore delle Spore, Mind Flayer Arcanista, Duodrone, Tridrone, Quadrone, Pentadrone — erano assenti dal
    vecchio file). Confermato via script Python: 399 voci totali, zero duplicati, tutti i 24 nomi di questo batch
    presenti. `python3 -m py_compile` su `combattimento_tab.py` passato. **Il conteggio totale delle voci nel file
    ha raggiunto 399** (lo stesso numero stimato di blocchi statistici nel manuale intero), ma questo NON significa
    che l'audit sia completo — il file conteneva già, prima dell'inizio di questo audit, una voce per quasi ogni
    mostro del manuale (parte del problema originale: contenuto spesso corrotto o mai verificato), quindi il
    conteggio delle voci è rimasto vicino a 399 per tutta la sessione mentre si sostituivano le voci corrotte e se
    ne aggiungevano di mancanti una alla volta — il vero indicatore di progresso è il conteggio dei blocchi
    effettivamente riverificati con lettura visiva pagina per pagina (239/399 a questo punto), non il conteggio
    totale delle voci nel file. Sessione proseguita subito dopo con il capitolo successivo (pag. 241+) senza
    fermarsi, come da istruzione originale di Davide.
- **Audit `monsters.json`, batch B21 (2026-07-17) — capitolo Ombra, Omuncolo, Oni, capitolo Orco, Orrore Corazzato,
  Orrore Uncinato, Orsogufo, Otyugh, Pegaso, Peryton, Pixie, Pseudodrago, capitolo Quaggoth, Rakshasa, capitolo
  Remorhaz, Revenant, Roc, sessione non interattiva prosegue dopo un secondo "riprendi da dove hai lasciato"**:
  stesso metodo (lettura visiva `pdftoppm -r 150`, mai `pdftotext`). Renderizzate e lette tutte le 20 pagine
  241-260 (pg-258 rigenerata una seconda volta per un errore di trasmissione dell'immagine, stesso contenuto).
  - **OMBRA** (pag. 241, CR1/2) — Amorfo, Furtività d'Ombra (Nascondersi come azione bonus in luce fioca/oscurità),
    Debolezza alla Luce del Sole (svantaggio a tiri per colpire/prove/TS); Risucchio di Forza riduce
    temporaneamente la Forza, genera una nuova ombra dal cadavere di un umanoide non malvagio ucciso in questo
    modo.
  - **OMUNCOLO** (pag. 242, CR0) — Legame Telepatico col creatore (percezione condivisa + comunicazione telepatica sullo stesso piano); Morso con veleno che può privare di sensi.
  - **ONI** (pag. 243, CR7) — Incantesimi Innati su Carisma, Armi Magiche, Rigenerazione; Multiattacco
    artiglio/falcione, Cambiare Forma (umanoide Piccolo/Medio ↔ gigante Grande ↔ vera forma, il falcione si
    ridimensiona di conseguenza).
  - **Capitolo Orco, prima parte** (pag. 244-245 lore-only — mitologia di Gruumsh/Luthic, sidebar "Re Obould
    Molte-Frecce" — nessuno stat block su queste 2 pagine): Orco (pag. 246, CR1/2, Aggressivo) + Orco Capotribù
    Guerriero (pag. 246, CR4, + Furia di Gruumsh, Grido di Battaglia 1/giorno che concede vantaggio di gruppo) +
    Orco Occhio di Gruumsh (pag. 247, CR2, + Incantesimi da chierico 3° livello) + Orog (pag. 247, CR2, armatura
    completa CA18, nessuna capacità magica) — tutti e 4 condividono il tratto Aggressivo (mossa come azione bonus
    verso un nemico visibile).
  - **ORRORE CORAZZATO** (pag. 248, CR4) — costrutto Resistenza alla Magia + Immunità agli Incantesimi (3
    incantesimi scelti dal creatore), vista cieca 18m oltre la quale è cieco, Multiattacco spada lunga.
  - **ORRORE UNCINATO** (pag. 249, CR3) — Senso Radar (vista cieca inutile se assordato), Udito Acuto; Multiattacco 2 uncini portata 3m.
  - **ORSOGUFO** (pag. 250, CR3) — Vista e Olfatto Acuti, Multiattacco becco+artigli.
  - **OTYUGH** (pag. 251, CR5) — Telepatia Limitata (non bidirezionale); Multiattacco morso (malattia progressiva
    che riduce il massimo PF)+2 tentacoli (afferrano, portata 3m), Schianto con Tentacolo (danno contundente ad
    area sui bersagli afferrati).
  - **PEGASO** (pag. 252, CR2) — nessuna capacità speciale oltre ai punteggi, solo attacco Zoccoli; capisce 4 lingue ma non parla.
  - **PERYTON** (pag. 253, CR2) — Attacco in Picchiata (danno bonus da tuffo in volo), Volo Sfuggente (nessun attacco di opportunità in fuga), Vista e Olfatto Acuti; Multiattacco incornata+speroni.
  - **PIXIE** (pag. 254, CR1/4) — Resistenza alla Magia, Incantesimi Innati su Carisma (inclusa invisibilità superiore come azione dedicata, non nella lista incantesimi standard).
  - **PSEUDODRAGO** (pag. 255, CR1/4) — Sensi Acuti, Resistenza alla Magia, Telepatia Limitata; Morso + Pungiglione
    (veleno che può rendere privi di sensi). Sidebar "Variante: Famiglio Pseudodrago" (tratto opzionale "Famiglio"
    per servire un incantatore) letta ma senza campo schema dedicato, non incorporata nella voce base — coerente
    col principio già stabilito per le varianti opzionali.
  - **Capitolo Quaggoth, 2 varianti** (pag. 256): Quaggoth (CR2, Furia del Ferimento — vantaggio+danno extra sotto
    10 PF, immune al veleno) + **Quaggoth Thonot** (sidebar "Variante: Quaggoth Thonot", CR3, stesso stat block
    base + tratto aggiuntivo "Incantesimi Innati (Psionici)" su Saggezza — trascritta come voce a sé essendo una
    variante pienamente statuita con CR proprio, stesso principio di Mind Flayer Arcanista/Mezzodrago).
  - **RAKSHASA** (pag. 257, CR13) — Immunità alla Magia Limitata (immune/vantaggio a incantesimi ≤6° livello),
    Incantesimi Innati su Carisma con CD18; vulnerabile a perforante da armi magiche impugnate da creature buone;
    Artiglio con maledizione permanente (nessun beneficio da riposo finché non rimossa).
  - **Capitolo Remorhaz, 2 varianti** (pag. 258, rigenerata una seconda volta per un errore di trasmissione
    immagine, stesso contenuto): Remorhaz Giovane (CR5, Corpo Surriscaldato, Morso) + Remorhaz (CR11, Corpo
    Surriscaldato più forte, Morso che afferra + Inghiottire con danno da acido continuo e possibilità di rigurgito
    forzato).
  - **REVENANT** (pag. 259, CR5) — Rigenerazione (interrotta da fuoco/radioso), Ringiovanimento (torna in un nuovo
    cadavere dopo 24h se distrutto), Immunità allo Scacciare, Inseguitore Vendicativo (localizza sempre il proprio
    bersaglio di vendetta anche su piani diversi); Multiattacco pugni (danno bonus contro il bersaglio di vendetta,
    opzione afferrare), Sguardo Vendicativo (paralisi poi spavento). Sidebar "Variante: Revenant con Armi e
    Incantesimi" letta ma puramente narrativa (nessun dato meccanico aggiuntivo da trascrivere).
  - **ROC** (pag. 260, CR11) — Vista Acuta; Multiattacco becco+speroni, speroni afferrano il bersaglio.
  - **Verifica di chiusura**: `Replaced: 16, Added: 6, Total entries now: 405` (i 16 "replaced" erano già presenti
    nel vecchio file con la consueta contaminazione OCR/traduzione da riverificare; i 6 "added" — Quaggoth Thonot,
    Remorhaz Giovane, Remorhaz, e altri assenti dal vecchio file). Confermato via script Python: 405 voci totali,
    zero duplicati, tutti i 22 nomi di questo batch presenti. `python3 -m py_compile` su `combattimento_tab.py`
    passato. **Il conteggio totale delle voci nel file (405) NON è un indicatore del progresso dell'audit** —
    stesso principio già chiarito nel changelog del batch B20: il vero indicatore è il conteggio dei blocchi
    effettivamente riverificati con lettura visiva pagina per pagina, ora **261/399**. Sessione proseguita subito
    dopo con il capitolo successivo (pag. 261+) senza fermarsi, come da istruzione originale di Davide.
- **Audit `monsters.json`, batch B22 (2026-07-17) — Rugginofago, capitolo Sahuagin, Serpente di Fuoco/Salamandra,
  Satiro, capitolo Scheletro, Sciacallo Mannaro, Segugio Infernale, capitolo Sfinge (Androsfinge/Ginosfinge),
  capitolo Slaad, Spaventapasseri, Spettro/Poltergeist, sessione non interattiva prosegue dopo un terzo "riprendi
  da dove hai lasciato"**: lettura visiva (`pdftoppm -r 150`) di tutte le pagine 261-280, 23 stat block
  trascritti/corretti. Nessun problema strutturale di schema incontrato in questo batch salvo i casi già noti (lair
  actions non rappresentabili, varianti opzionali non incorporate). Dettagli notevoli:
  - **Sahuagin** (pag. 262-263): famiglia completa di 3 taglie/ruoli — Sahuagin base (CR 1/2), Sahuagin
    Sacerdotessa (CR 2, incantatrice di 6° livello da chierico, Saggezza), Sahuagin Barone (CR 5, Grande, corazza
    di piastre, 4 braccia implicite nel lore ma statisticamente un multiattacco a 3 normale) — tutti e 3 con gli
    stessi tratti razziali (Frenesia di Sangue, Anfibio Limitato, Telepatia con gli Squali).
  - **Sfinge** (pag. 271-273): pag. 271 è quasi interamente lore/regole generiche del capitolo (introduzione
    Sfinge, Androsfinge, Ginosfinge in prosa) più la sezione "La Tana di una Sfinge" con le sue Azioni di Tana
    (flusso del tempo alterato, invecchiamento forzato, spostamento della tana, teletrasporto di gruppo) — letta
    per intero ma non trascritta, nessun campo schema per lair actions, stesso precedente già stabilito per
    Demilich/Kraken/Lich/Signore delle Mummie. Androsfinge (CR 17, legale neutrale, incantatrice di 12° livello da
    chierico, 3 Ruggiti progressivi 3/Giorno con effetti crescenti — spaventato → assordato+paralizzato → 8d10
    danni da tuono) e Ginosfinge (CR 11, legale neutrale, incantatrice di 9° livello da mago) condividono lo stesso
    tratto Imperscrutabile/Armi Magiche e lo stesso set di 3 Azioni Leggendarie (Attacco con Artiglio,
    Teletrasporto Costa 2, Lanciare un Incantesimo Costa 3) — nessuna interazione multiattacco extra oltre alle 2
    artigliate base.
  - **Capitolo Slaad** (pag. 274-278): pag. 274 è lore/regole generiche (ciclo riproduttivo, mutazione
    Rosso→Blu→Verde→Grigio→Morte) + sidebar "Variante: Gemme del Controllo degli Slaadi" (meccanica opzionale di
    dominio tramite una gemma innestata nel cervello di uno slaad, applicabile a qualunque slaad — letta ma non
    incorporata nella voce base, coerente con lo stesso principio già stabilito per le varianti opzionali come il
    Flauto del Satiro e l'Arma su Asta del Diavolo d'Ossa). 6 stat block della progressione completa: Slaad Girino
    (CR 1/8, Minuscolo, nessun incantesimo), Slaad Rosso (CR 5, nessun incantesimo, solo morso/artigli con rischio
    di infezione da uovo di slaad), Slaad Blu (CR 7, nessun incantesimo, rischio di infezione da virus del caos),
    Slaad Verde (CR 8, mutaforma + incantesimi innati CHA fino a palla di fuoco 1/giorno), Slaad Grigio (CR 9,
    mutaforma + incantesimi innati più ampi + Armi Magiche), Slaad della Morte (CR 10, caotico malvagio a
    differenza degli altri caotico neutrali, danni necrotici aggiuntivi su ogni attacco, incantesimo innato
    esclusivo nube mortale). Tutti e 6 condividono Resistenza alla Magia (tranne il Girino, che ha Resistenza alla
    Magia ma non Rigenerazione) e Rigenerazione (tranne il Girino).
  - **Spettro/Poltergeist** (pag. 280): il Poltergeist è presentato come "Variante: Poltergeist" ma — a differenza
    del Flauto del Satiro o delle Gemme degli Slaad — è un vero stat block alternativo completo con CR proprio (2
    anziché 1), un tratto aggiuntivo (Invisibilità) e un set di azioni interamente sostitutivo (Schianto Violento +
    Spinta Telecinetica al posto di Risucchio di Vita) — stesso principio già applicato a Quaggoth
    Thonot/Mezzodrago/Dracolich/Mind Flayer Arcanista: trascritto come voce JSON a sé stante ("POLTERGEIST"),
    costruito sullo stesso blocco statistico base dello Spettro (identico
    AC/HP/velocità/punteggi/resistenze/immunità/sensi/linguaggi) con le sole differenze meccaniche sopra applicate.
  - **Verifica di chiusura**: `Replaced: 14, Added: 9, Total entries now: 414` (i 14 "replaced" erano già presenti
    nel vecchio file con la consueta contaminazione OCR/traduzione da riverificare; i 9 "added" — Sahuagin
    Sacerdotessa, Sahuagin Barone, Serpente di Fuoco, Ginosfinge, Slaad Girino, Slaad Blu, Slaad Grigio, Slaad
    della Morte, Poltergeist — assenti dal vecchio file). Confermato via script Python: 414 voci totali, zero
    duplicati, tutti i 23 nomi di questo batch presenti. `python3 -m py_compile` su `combattimento_tab.py` passato.
    **Il conteggio totale delle voci nel file (414) NON è un indicatore del progresso dell'audit** — stesso
    principio già chiarito nei changelog precedenti: il vero indicatore è il conteggio dei blocchi effettivamente
    riverificati con lettura visiva pagina per pagina, ora **284/399**. Sessione proseguita subito dopo con il
    capitolo successivo (pag. 281+) senza fermarsi, come da istruzione originale di Davide.
- **Audit `monsters.json`, batch B23 (2026-07-17) — Spiritello, Succube/Incubo, Tarrasque, Teschio Infuocato,
  Testuggine Dragona, Thri-kreen, Treant, Troglodita, Troll, Uccello Stigeo, Umber Hulk, Unicorno, capitolo Vampiro
  (Vampiro/Progenie Vampirica), Verme Purpureo, Vermeiena, sessione non interattiva prosegue dopo un quarto
  "riprendi da dove hai lasciato"**: lettura visiva (`pdftoppm -r 150`) di tutte le pagine 281-300, 16 stat block
  trascritti/corretti. Nessun problema strutturale di schema incontrato in questo batch salvo i casi già noti
  (lair/regional actions non rappresentabili, varianti opzionali non incorporate). Dettagli notevoli:
  - **Tarrasque** (pag. 283-284): pag. 283 è quasi interamente lore (nessuno stat block). CR 30, Mostruosità
    Mastodontica — Resistenza Leggendaria (3/Giorno), Resistenza alla Magia, Carapace Riflettente (riflette dardo
    incantato/linee/tiri a distanza con 1 su d6), Mostro da Assedio, Multiattacco a 5 attacchi (morso/2
    artigli/corna/coda o Inghiottire al posto del morso), Presenza Terrificante, 3 Azioni Leggendarie (Attacco,
    Movimento, Masticare Costa 2).
  - **Vampiro** (pag. 295-297): pag. 295-296 quasi interamente lore (biografia di Strahd von Zarovich come esempio
    narrativo, "Personaggi Giocanti Come Vampiri", "La Tana di un Vampiro"/Effetti Regionali — letti per intero ma
    non trascritti, nessun campo schema per lair/regional effects, stesso precedente Kraken/Lich/Signore delle
    Mummie/Sfinge/Unicorno). Stat block CR13 con Mutaforma (pipistrello/nebbia/forma naturale), Resistenza
    Leggendaria, Fuga Nebbiosa, Rigenerazione, Movimenti del Ragno, Debolezze dei Vampiri (Proibizione/Acqua
    Corrente/Paletto/Ipersensibilità al Sole), Fascino, Figli della Notte, 3 Azioni Leggendarie. Sidebar "Varianti:
    Vampiri Combattenti e Incantatori" (pag. 298) letta ma **deliberatamente NON incorporata come voce a sé** — a
    differenza dei precedenti Mezzodrago Rosso Veterano/Quaggoth Thonot/Spettro-Poltergeist (tutti esempi singoli e
    pienamente statuiti), qui il manuale presenta due **modificatori generici opzionali** applicabili al Vampiro
    base (variante combattente: CA18 + spadone con Multiattacco a 2; variante incantatore: casting da mago di 9°
    livello con lista incantesimi completa) senza offrire un singolo stat block interamente pre-costruito e
    autonomo — trattata quindi come le altre varianti opzionali non incorporate di questo stesso batch
    (Thri-kreen/Troll).
  - **Thri-kreen** (pag. 287) e **Troll** (pag. 290): entrambi con una sidebar "Variante" opzionale letta ma non
    incorporata — "Armi e Poteri Psionici dei Thri-kreen" (arma gythka/chatkcha + incantesimi innati psionici via
    telepatia) e "Arti Abominevoli" (tabella d20 per smembramento/rigenerazione separata degli arti recisi) —
    stesso principio già stabilito per Flauto del Satiro/Arma su Asta del Diavolo d'Ossa/Gemme del Controllo degli
    Slaadi: meccanica opzionale applicabile a qualunque esemplare esistente, non un nuovo stat block.
  - **Unicorno** (pag. 293-294): pag. 293 lore + "La Tana di un Unicorno"/Effetti Regionali (letti ma non
    trascritti, stesso principio del Kraken/Lich/Mummie/Sfinge). Stat block CR5, Celestiale, con Carica,
    Incantesimi Innati (CD14 CAR), Resistenza alla Magia, Armi Magiche, Tocco Guaritore/Teletrasporto a consumo, 3
    Azioni Leggendarie.
  - **Progenie Vampirica** (pag. 298, CR5): stesso blocco base del Vampiro (Rigenerazione/Movimenti del
    Ragno/Debolezze dei Vampiri) ma senza Mutaforma/Resistenza Leggendaria/Fascino/Azioni Leggendarie — versione
    "minore" priva delle capacità da vampiro puro, coerente con la lore (nato dalla morte di una vittima, sotto il
    controllo del vampiro creatore).
  - **Verme Purpureo** (pag. 299, CR15) e **Vermeiena** (pag. 300, CR2): entrambi Mostruosità dell'Underdark con
    meccanica di ingoiare/afferrare (Inghiottire per il Verme Purpureo, tentacoli paralizzanti da veleno per la
    Vermeiena, quest'ultima con Movimenti del Ragno per muoversi sui soffitti).
  - **Verifica di chiusura**: `Replaced: 10, Added: 6, Total entries now: 420` (i 10 "replaced" erano già presenti
    nel vecchio file con la consueta contaminazione OCR/traduzione da riverificare; i 6 "added" — Tarrasque,
    Testuggine Dragona, Uccello Stigeo, Umber Hulk, Progenie Vampirica, Vermeiena — assenti dal vecchio file).
    Confermato via script Python: 420 voci totali, zero duplicati, tutti i 16 nomi di questo batch presenti.
    `python3 -m py_compile` su `combattimento_tab.py` passato. **Il conteggio totale delle voci nel file (420) NON
    è un indicatore del progresso dell'audit** — stesso principio già chiarito nei changelog precedenti: il vero
    indicatore è il conteggio dei blocchi effettivamente riverificati con lettura visiva pagina per pagina, ora
    **300/399**. Sessione proseguita subito dopo con il capitolo successivo (pag. 301+) senza fermarsi, come da
    istruzione originale di Davide.
- **Bug report di Davide (2026-07-11) — quantità di armi/oggetti compresse in un nome letterale invece che nel
  campo quantity, "Abito comune" senza dati di armatura**: "faretra con venti frecce sarebbe faretra quantità 1 e
  frecce quantità 20 \n abito comune pure è un armatura che non aumenta la classe armatura ma te la setta a 10,
  puoi indossare al massimo una armatura per volta e uno scudo, non due armature non 2 scudi, nell'equpaggiamento
  scrivi due pugnali ma sarebbe in realtà pugnali quantità 2, dobbiamo risolvere questi bug dell'equipaggiamento".
  Quattro problemi distinti, tutti nello stesso file di bug (equipaggiamento iniziale generato alla creazione del
  personaggio):
  1. **"Faretra con 20 frecce" era un'unica voce di equipaggiamento** invece di due oggetti distinti (una faretra +
     20 frecce) — presente in `ladro.json` e `ranger.json`. **Fix**: entrambe le voci divise in `{"name":
     "Faretra", "item_type": "item"}` + `{"name": "Frecce", "item_type": "item", "quantity": 20}`.
     `guerriero.json`, verificato per confronto, aveva già "Frecce" come voce separata con `quantity: 20` ma senza
     alcuna voce "Faretra" — gap segnalato ma NON toccato in questo fix (richiederebbe conferma contro il manuale
     se il guerriero riceve davvero solo le frecce senza faretra, fuori scope della richiesta esplicita di Davide).
  2. **"Due pugnali"/"Dardi" come nome letterale con `quantity: 2`/`10`** invece di un nome singolare risolvibile
     dal catalogo `equipment/weapons.json` — stesso bug in `stregone.json`, `ladro.json`, `warlock.json` ("Due
     pugnali"→**"Pugnale"**, quantity invariata a 2) e in `monaco.json` ("Dardi"→**"Dardo"**, quantity invariata a
     10; trovato durante la verifica di chiusura, non menzionato esplicitamente da Davide ma stesso identico bug —
     il catalogo armi ha la voce singolare "Dardo", non "Dardi"). **Causa strutturale**: `_save_item()` in
     `wizard_view.py`/`manual_form.py`, ramo `item_type == "weapon"`, ignorava completamente `item.get("quantity")`
     e chiamava `_save_weapon_by_name()` una sola volta con il nome letterale del JSON — se quel nome era un
     plurale/composto tipo "Due pugnali", `_loader.get_weapon()` non lo trovava mai nel catalogo (case-insensitive
     ma pur sempre un confronto esatto) e l'arma veniva creata con statistiche vuote invece di risolvere "Pugnale"
     x2 con dado danno/tipo/proprietà corrette. **Fix**: il ramo `weapon` ora itera `range(max(1,
     item.get("quantity", 1)))`, chiamando `_save_weapon_by_name()` una volta per unità — crea N righe distinte
     nella tabella `weapons`, ciascuna equipaggiabile/modificabile indipendentemente (coerente con la regola già
     stabilita in questo progetto che `Weapon` non ha un campo quantity, ogni arma fisica è una riga a sé — vedi
     fix #72).
  3. **"Abito comune" (e qualunque altro capo con `item_type: "armor"` nei background) non aveva mai
     `ca_value`/`armor_type` valorizzati** — la causa era più profonda del semplice bug di Davide: il ramo generico
     `else` di `_save_item()` impostava `category="armor"` per ogni `item_type: "armor"`, ma non leggeva MAI
     `ca_value`/`armor_type`/peso da nessuna fonte, quindi **ogni armatura iniziale di OGNI classe** (non solo
     "Abito comune") veniva creata con `ca_value=0, armor_type="", weight=0.0, is_equipped=False` — un Guerriero
     che sceglieva "Cotta di Maglia" nasceva con un'armatura completamente non funzionante, indistinguibile da un
     vestito. Scoperto durante l'analisi della causa radice, non menzionato esplicitamente da Davide ma la stessa
     identica classe di bug, risolto nello stesso intervento. **Fix**: nuovo `GameDataLoader.get_armor_item(name)`
     (`data/game_data/game_data_loader.py`) — cerca il nome (case-insensitive) in tutte e 4 le liste di
     `equipment/armor.json` (leggere/medie/pesanti/scudi, catalogo trascritto dalle immagini del PDF il 2026-07-10)
     e ritorna il dict originale arricchito con `armor_type` (dedotto dalla lista di provenienza) e `ca_value`
     (intero: per gli scudi da `ac_bonus`, per le armature dal prefisso numerico di `ac_formula` via regex — es.
     `"14 + modificatore di Des (max 2)"` → `14`, la parte testuale descrive esattamente la stessa formula già
     hardcoded in `calculate_and_update_ca()`, quindi non va sommata due volte). Nuova
     `_save_armor_by_name(character_id, name, quantity=1)` (identica in `wizard_view.py`/`manual_form.py`, stesso
     pattern di `_save_weapon_by_name`): se il nome risolve nel catalogo, crea l'oggetto con
     `ca_value`/`armor_type`/peso reali e `is_equipped=True`; se NON risolve (caso "Abito comune", che non è
     un'armatura del Cap.5 — è un vestito, non una protezione) crea comunque l'oggetto ma con `ca_value=0,
     armor_type=""` — `calculate_and_update_ca()` filtra esplicitamente solo gli item con `armor_type` in
     `("leggera","media","pesante")` o `"scudo"`, quindi un `armor_type=""` ha effetto ESATTAMENTE NULLO sul
     calcolo: il personaggio resta sulla formula "senza armatura" (10+DEX, o le formule speciali di
     Monaco/Barbaro/Stregone+Discendenza Draconica per chi le ha) — esattamente il comportamento richiesto da
     Davide ("abito comune... non aumenta la classe armatura"), senza bisogno di uno special-case sul nome "Abito
     comune": qualunque futuro indumento non in catalogo si comporta allo stesso modo automaticamente.
     `_save_item()` ha ora un ramo dedicato `elif itype == "armor": _save_armor_by_name(...)`.
  4. **Bug di dati scoperto durante la verifica di chiusura, non nella richiesta originale**: i nomi armatura nei
     JSON classe non corrispondevano affatto ai nomi del catalogo `equipment/armor.json` — "Armatura di cuoio"
     (bardo/chierico/druido/guerriero/ladro/ranger/warlock) vs catalogo **"Cuoio"**, "Armatura a scaglie"/"Corazza
     a scaglie" (chierico/ranger) vs catalogo **"Corazza di Scaglie"**, "Scudo di legno" (druido) vs catalogo
     **"Scudo"**. Con la sola aggiunta di `_save_armor_by_name()` (punto 3), TUTTE queste armature sarebbero
     silenziosamente cadute nel ramo "non trovato nel catalogo" (stesso effetto zero-CA pensato per "Abito
     comune"), vanificando il fix per la stragrande maggioranza delle classi — scoperto SOLO grazie a uno script di
     verifica automatico che confronta ogni nome `item_type: "armor"`/`"weapon"` nei 12 JSON classe contro i
     rispettivi cataloghi (stesso principio dei controlli di chiusura già usati per gli audit incantesimi/talenti).
     **Fix**: rinominate le 12 occorrenze nei 7 file (`bardo.json`, `chierico.json` ×2, `druido.json` ×2,
     `guerriero.json`, `ladro.json`, `ranger.json` ×2, `warlock.json`) per usare esattamente i nomi del catalogo —
     il catalogo è la fonte a maggiore confidenza (trascritto visivamente dalle immagini del PDF il 2026-07-10),
     coerente con la stessa convenzione già applicata a "Due pugnali"→"Pugnale". Nessuna informazione persa: sono
     tutti campi `"name"` puri senza testo descrittivo aggiuntivo, e per il druido lo scudo "di legno" resta
     meccanicamente identico a uno scudo normale nel PHB (nessuna riga distinta nel catalogo per materiale, solo
     `ac_bonus: 2`).
  - **Nuovo passaggio di finalizzazione in entrambi i file, prima del ricalcolo finale della CA**:
    `_save_armor_by_name()` crea sempre `is_equipped=True` (come già avviene per le armi), ma nessuna classe
    attuale ha più di un'armatura corporea o più di uno scudo fissi nello stesso pacchetto di equipaggiamento — per
    proteggere comunque l'invariante "al massimo 1 armatura + 1 scudo equipaggiati" richiesta esplicitamente da
    Davide anche contro un futuro JSON malformato, aggiunto un passaggio che ricostruisce tutti gli
    `ArmorCandidate` dall'inventario appena creato e applica `resolve_armor_equip()` (già esistente, vedi fix
    CA/Armature precedente) in ordine di creazione prima di chiamare `calculate_and_update_ca()`.
  - **Verificato** con una batteria di test end-to-end (DB temporaneo isolato, mai quello reale):
    `get_armor_item()` risolve correttamente Cotta di Maglia (pesante, ca_value=16, peso=27.5kg), Scudo (scudo,
    ca_value=2) e Cuoio Borchiato (leggera, ca_value=12, case-insensitive), e ritorna `None` per "Abito comune"; un
    personaggio con "Abito comune" equipaggiato ha CA = 10+mod DES esattamente come se non indossasse nulla; un
    personaggio con "Cotta di Maglia" risolta dal catalogo ha CA=16 (pesante, DES ignorato); Faretra+Frecce create
    come due righe distinte con quantity 1/20; "Pugnale" x2 crea 2 righe distinte in `weapons` con id diversi; il
    passaggio di finalizzazione riduce correttamente a 1 sola armatura corporea equipaggiata quando 2 vengono
    create entrambe `is_equipped=True`; un Guerriero con "Cuoio"+"Scudo" (nomi post-fix) ha CA=15 (11+2 DES+2
    scudo) risolvendo entrambi dal catalogo; "Dardo" (post-fix da "Dardi") risolve correttamente in
    `equipment/weapons.json` (1d4 perforanti). Script di cross-check automatico confermato: **zero** nomi
    `item_type: "armor"`/`"weapon"` residui nei 12 JSON classe che non risolvano nei rispettivi cataloghi.
    `py_compile`/`pyflakes` puliti su `game_data_loader.py`, `wizard_view.py`, `manual_form.py`,
    `core/equipment_manager.py`, `character_repo.py`; validazione JSON su tutti i file classe/background/equipment
    toccati.
  - **Non affrontato in questo fix, segnalato per il futuro**: durante la scansione per compound-name simili a "Due
    pugnali" è emerso `acolito.json → "5 bastoncini di incenso"` (`item_type: "item"`, quantità incorporata nel
    nome invece che nel campo `quantity`) — stessa classe di bug ma per un oggetto generico non-arma/non-armatura,
    quindi fuori dallo scope esplicito della richiesta di Davide (che riguardava specificamente armi ed
    equipaggiamento indossabile). Segnalato qui per una futura pulizia dedicata ai nomi oggetto generici, non
    corretto in questa sessione per non allargare lo scope oltre quanto richiesto.
- **Bug report di Davide (2026-07-11) — 4 bug distinti nella creazione personaggio**: "quando un incantatore
  sceglie i trucchetti conosciuti all'inizio la selezione mi permette di selezionare sempre lo stesso trucchetto
  oppure quello conosciuto tramite bonus raziale, ma devono essere trucchetti diversi, la scelta delle lingue mi
  permette di scegliere anche le lingue già conosciute di base, non devo poter indossare più armature alla volta, o
  indosso abito comune o indosso armatura di maglia ecc. quando viene creato il personaggio ha le armi equipagiate
  esempio arco e spada anche se ne può equipaggiare solo uno, se lo disequipaggio a mano poi funziona bene".
  Quattro bug indipendenti, tutti in `wizard_view.py`/`manual_form.py` (identici in entrambi i file, stesso pattern
  architetturale) salvo il terzo che è in `core/equipment_manager.py`:
  1. **Trucchetti/incantesimi Lv.1 duplicabili tra loro E col trucchetto razziale** — causa radice doppia: (a) le
     `options` di ogni dropdown trucchetto (`cantrip_dds`) e ogni dropdown incantesimo (`spell_dds`) mostravano
     SEMPRE l'intero pool (`cantrip_pool`/`spell_names`), mai filtrato per escludere i valori già scelti negli
     ALTRI dropdown dello stesso gruppo — nulla impediva di scegliere "Luce" sia in "Trucchetto 1" sia in
     "Trucchetto 2"; (b) `elf_reserved` (il trucchetto scelto come tratto razziale Alto Elfo, sempre dalla lista
     Mago) veniva escluso dal pool di classe SOLO quando `self._review_class == "Mago"` — ma le liste di trucchetti
     di classi diverse condividono spesso gli stessi nomi (verificato: 10 degli 11 trucchetti Bardo compaiono anche
     nella lista Mago, es. "Luce", "Illusione Minore", "Prestidigitazione"), quindi un Bardo Alto Elfo poteva
     scegliere lo stesso trucchetto sia come tratto razziale sia come trucchetto di classe, senza alcun blocco.
     **Fix**: (a) nuove `_refresh_cantrip_options()`/`_refresh_spell_options()` che ricalcolano le `options` di
     ogni dropdown escludendo dinamicamente i valori scelti negli altri dropdown del gruppo (mai il proprio valore
     corrente) — chiamate da `_set_cantrip()`/`_set_spell()` a ogni selezione e una volta subito dopo la
     costruzione iniziale dei dropdown; è un'esclusione preventiva (il duplicato non compare mai tra le opzioni),
     non una validazione a posteriori; (b) `elf_reserved` non è più condizionato da `self._review_class == "Mago"`
     — si applica sempre quando `self._review_elf_cantrip` è valorizzato, a prescindere dalla classe; l'handler
     `_on_elf_cantrip_select()` ora chiama sempre `_rebuild_spells_init_col()` (prima solo se classe Mago) così il
     pool si aggiorna live per qualunque classe. Verificato con simulazione standalone (nessun Flet necessario,
     logica pura su liste): Bardo Alto Elfo con "Luce" come trucchetto razziale → "Luce" assente dal pool di
     classe; selezionare un trucchetto nel dropdown 1 lo rimuove immediatamente dalle opzioni del dropdown 2;
     stesso comportamento verificato sugli incantesimi di 1° livello (Stregone, 2 dropdown).
  2. **Scelta lingue da background permette lingue già conosciute** — `_rebuild_lang_tool_col()` costruiva la
     checkbox list "scegli N lingue" con `avail_langs = LANGUAGES` (tutte e 15, senza filtri), quindi un
     personaggio poteva "scegliere" come lingua bonus una lingua fissa già posseduta per razza (es. "Elfico" per un
     Elfo, o "Comune" per qualunque razza — ogni razza in questo dataset ha "Comune" tra le lingue fisse) o già
     scelta dal dropdown dedicato del tratto Umano, sprecando la scelta su qualcosa già noto. **Fix**:
     `avail_langs` ora esclude le lingue fisse di razza lette da `_loader.get_resolved_race(self._review_race,
     self._review_subrace)["languages"]` (solo le voci stringa, non le entry `{"type":"choice",...}`) più
     `self._review_umano_language` se valorizzata; ricostruito ogni volta che razza/sottorazza/lingua Umano
     cambiano (`_rebuild_lang_tool_col()` aggiunta a `_on_race_change`, all'`on_select` del dropdown sottorazza e
     dell'`on_select` del dropdown lingua Umano). Verificato: un Elfo Alto ha "Comune" ed "Elfico" esclusi dal pool
     di scelta background; un Umano che sceglie "Nanico" come lingua extra del tratto non può più scegliere
     "Nanico" anche come lingua bonus del background.
  3. **Più armature/indumenti equipaggiati insieme** ("o indosso abito comune o indosso armatura di maglia ecc.") —
     `resolve_armor_equip()` in `core/equipment_manager.py` trattava un item con `armor_type=""` (indumento non
     protettivo come "Abito comune", creato dal fallback di `_save_armor_by_name()` per nomi non nel catalogo —
     vedi voce precedente) come una "postazione diversa" che non escludeva né veniva esclusa da una vera armatura
     corporea (leggera/media/pesante): un personaggio poteva risultare con "Abito comune" E "Cotta di Maglia"
     equipaggiati insieme (nessun effetto sulla CA, dato che solo l'armatura vera viene sommata, ma comunque
     scorretto — fisicamente non si indossano vestiti comuni sotto un'armatura contemporaneamente come se fossero
     entrambi "equipaggiati"). **Fix**: la condizione di esclusione è stata generalizzata da "`armor_type in
     {"leggera","media","pesante"}`" a "`armor_type != "scudo"`" — la postazione "corpo" ora include qualunque
     armatura vera O indumento non protettivo, quindi equipaggiare l'uno disequipaggia automaticamente l'altro.
     Rimossa la costante `_BODY_ARMOR_TYPES` (non più necessaria, non più usata altrove nel progetto). Verificato
     con test isolati sul modulo puro: equipaggiare "Cotta di Maglia" con "Abito comune" già equipaggiato lo
     espelle e viceversa; lo scudo resta indipendente da entrambi.
  4. **Armi multiple equipaggiate alla creazione (arco+spada)** — `_save_weapon_by_name()` crea sempre
     `is_equipped=True` per ogni arma di partenza, ma finora nessun passaggio applicava il limite di 2 mani
     (`resolve_weapon_equip()`, già usato per il toggle equip live in `inventario_tab.py`) al momento della
     creazione: un personaggio poteva nascere con un Arco Corto (proprietà "Due Mani", verificato in
     `equipment/weapons.json`) E una Spada Corta entrambi equipaggiati, fisicamente impossibile con 2 mani —
     coerente col fatto che disequipaggiando manualmente una delle due dall'inventario tutto tornasse a funzionare
     correttamente (il toggle live era già corretto dal fix precedente, mancava solo il passaggio equivalente alla
     creazione). **Fix**: nuovo passaggio di finalizzazione in `wizard_view.py`/`manual_form.py`, subito dopo
     quello analogo per le armature e prima del ricalcolo finale della CA — legge tutte le armi appena create
     (`get_weapons(char.id, equipped_only=False)`), le processa in ordine di creazione con `resolve_weapon_equip()`
     esattamente come farebbe una sequenza di click "equipaggia" dell'utente (la prima arma creata resta
     equipaggiata, le successive che non entrano più nelle mani libere vengono disequipaggiate), tenendo conto
     anche dello stato scudo risultante dalla finalizzazione armature appena eseguita; se una risoluzione arma
     richiede di liberare lo scudo (arma a due mani equipaggiata dopo che lo scudo era già stato risolto come
     equipaggiato), lo scudo viene disequipaggiato anche in inventario così la CA finale lo riflette. Verificato
     con test end-to-end (DB temporaneo isolato): riprodotto il bug (Arco Corto + Spada Corta entrambi equipaggiati
     prima della finalizzazione), poi confermato che dopo la finalizzazione resta equipaggiata solo la prima arma
     creata (Arco Corto, 2 mani) e che equipaggiare successivamente l'altra arma a mano funziona correttamente
     (nessuno stato residuo inconsistente).
  - **Verifica di chiusura**: `py_compile`/`pyflakes` puliti su tutti i file toccati (`wizard_view.py`,
    `manual_form.py`, `core/equipment_manager.py`); regressione completa `py_compile` sull'intero albero sorgente
    del progetto; nessuna modifica ai file JSON in questo batch (tutti e 4 i bug erano di logica UI/core, non di
    dato).
- **Bug report di Davide (2026-07-11) — dotazioni non espanse, quantità compressa nel nome, Giavellotto come arma
  singola, incantesimi mancanti per i "preparatori" e per il Mago**: "Nell'inventario scrivi dotazione da (tipo di
  dotazione) ma in realtà quella dotazione è un insieme di oggetti descritta nel libro, quindi non deve comparire
  dotazione da ma devono essere inseriti gli ogetti della dotazione scelta. ho lo stesso problema delle armi di
  prima tipo 5 bastoncini di incenso viene scritto come frase quando invece dovrebbe essere bastoncini di incenso
  quantità 5. il giavellotto è un arma da lancio paragonabile alle frecce, non va messa nella sezione armi come
  equipaggiabile come se fosse un arma singola. per gli incantatori i trucchetti iniziali me li fa scegliere, ma
  come gestiamo gli incantesimi del giocatore appena creato?". Quattro problemi, il quarto chiarito con due domande
  dirette a Davide prima di implementare (vedi sotto):
  1. **"Bastoncino di Incenso"** (`backgrounds/acolito.json`) — stesso identico bug già corretto altrove per le
     armi ("Due pugnali"→"Pugnale"), qui per un oggetto generico non-arma: `"5 bastoncini di incenso"` (nome-frase,
     nessun campo `quantity`) → **`"Bastoncino di Incenso"`** con `"quantity": 5`. Nessun cambiamento di codice
     necessario: il ramo generico `else` di `_save_item()` legge già `item.get("quantity", 1)` correttamente (era
     solo il dato JSON a comprimere la quantità nel nome, non un bug di `_save_item()` stesso).
  2. **Giavellotto riclassificato da arma singola equipaggiabile a oggetto trasportato in pila, come le Frecce** —
     Davide lo paragona esplicitamente alle Frecce: un personaggio non "impugna" 4-5 giavellotti
     contemporaneamente, li porta con sé e ne lancia uno alla volta. Prima di questo fix,
     `barbaro.json`/`paladino.json` avevano `"Giavellotto", item_type:"weapon", quantity:4/5` — dato lo stesso
     giorno era stato introdotto un loop che crea una riga distinta in `weapons` per unità (fix #90, per "Due
     pugnali"→2 armi separate, corretto per un'arma impugnabile a una mano come il pugnale), applicato anche al
     Giavellotto questo stesso loop, combinato col nuovo passaggio di finalizzazione equip a 2 mani introdotto
     nello stesso giorno (bug #4 della voce precedente), avrebbe equipaggiato solo le prime 2 delle 4-5 copie e
     disequipaggiato silenziosamente le altre alla creazione — comportamento tecnicamente "corretto" per il limite
     di 2 mani ma concettualmente sbagliato per un'arma da lancio pensata per essere portata in scorta, non tenuta
     in mano. **Fix**: `item_type` cambiato da `"weapon"` a `"item"` in entrambi i file (stesso identico schema già
     usato per "Frecce" in `ladro.json`/`guerriero.json`/`ranger.json` —
     `{"name":"Giavellotto","item_type":"item","quantity":N}`) — il Giavellotto ora finisce nella sezione Oggetti
     dell'inventario come oggetto impilato, non nella tabella `weapons`. Verificato con scansione automatica:
     nessun'altra occorrenza di "Giavellotto" in nessun altro JSON classe/background.
  3. **Dotazioni ("Dotazione da Avventuriero" ecc.) espanse nei singoli oggetti che contengono, invece di comparire
     come un'unica voce letterale** — root cause: `equipment/adventuring_gear.json → packs` (7 dotazioni,
     trascritte il 2026-07-10 dalla Tabella "Dotazioni" p.151) aveva il contenuto di ciascuna dotazione solo come
     **prosa** nel campo `"contents"` (es. "Uno zaino, un piede di porco, un martello, 10 chiodi da
     rocciatore..."), mai come lista strutturata — nessun codice poteva quindi "espandere" una dotazione anche
     volendo, il dato stesso non era machine-readable. `_save_item()` trattava ogni voce `"Dotazione da X"` come un
     `item_type: "item"` generico, creando un'unica riga di inventario con quel nome letterale. **Fix in due
     parti**:
     - **Dato**: aggiunto un nuovo campo `"contents_items": [{"name","quantity"},...]` a ciascuna delle 7 dotazioni
       in `adventuring_gear.json`, ottenuto da un parsing manuale della stessa prosa "contents" già verificata
       (nessun dato nuovo indovinato — solo la stessa lista resa strutturata), incrociato nome per nome contro il
       catalogo `items` dello stesso file per usare gli stessi nomi esatti dove esiste una corrispondenza (es.
       "Zaino", "Piede di Porco", "Corda di Canapa (15 metri)"). 7 oggetti citati nelle dotazioni non hanno una
       voce propria nel catalogo `items` di questo file (Cassetta per le Offerte, Cubetto di Incenso, Incensiere,
       Spago (3 metri), Sacchetto di Sabbia, Libro di Studio, Coltellino — quest'ultimo già noto come nome
       standalone nel background Sapiente) — mantenuti con lo stesso nome citato dal manuale, senza costo/peso
       proprio, annotato in un nuovo campo `"_contents_items_note"` a livello di `packs`. Verificato con script:
       somma delle quantità e conteggio righe per tutte e 7 le dotazioni, JSON validato.
     - **Codice**: nuovo `GameDataLoader.get_pack_contents(pack_name)` — cerca il nome (case-insensitive) tra le
       dotazioni note e ritorna la lista `contents_items`, o `None` se il nome non è una dotazione riconosciuta.
       `_save_item()` (ramo generico `else`, identico in `wizard_view.py`/`manual_form.py`) ora controlla
       `_loader.get_pack_contents(item["name"])` PRIMA di creare un item letterale: se risolve, itera la lista e
       crea un `create_inventory_item()` per ciascun oggetto contenuto (nome e quantità propri); se non risolve (un
       oggetto generico normale, non una dotazione), si comporta esattamente come prima. Nessuna nuova voce
       `item_type` introdotta — il meccanismo è trasparente sia per le 22 occorrenze di "Dotazione da X" nei 12
       file classe sia per l'equipaggiamento dei 13 background (stesso `_save_item()` condiviso, verificato
       leggendo il call site `for entry in bg_data.get("equipment", []): _save_item(char.id, entry)`). Verificato
       con test end-to-end (DB temporaneo isolato): "Dotazione da Sacerdote" espansa in 10 righe di inventario
       distinte (Zaino, Coperta, Candela×10, Acciarino e Pietra Focaia, Cassetta per le Offerte, Cubetto di
       Incenso×2, Incensiere, Veste, Razioni×2, Otre), nessuna riga "Dotazione da Sacerdote" residua; script di
       cross-check su tutti i 12 file classe + 13 background: **23 occorrenze totali** di "Dotazione da X",
       **tutte** risolte con successo da `get_pack_contents()` (nessuna dotazione orfana/nome sbagliato).
  4. **Gestione incantesimi per un incantatore appena creato — chiarito con Davide prima di implementare** (domanda
     esplicita nel bug report, non un bug con una correzione ovvia): posta la domanda via due scelte esplicite.
     Risposta di Davide: **sì a entrambe**.
     - **Chierico/Druido/Paladino** ("preparatori": nessuna lista di incantesimi conosciuti fissa, preparano ogni
       giorno dal pool completo della classe) **nascevano senza nessun incantesimo preparato** (a differenza dei
       trucchetti, già gestiti da task #74) — un giocatore doveva aprire la tab Incantesimi prima di poter giocare
       la prima sessione. **Fix**: nuova sezione "Incantesimi preparati iniziali" nello stesso blocco "Trucchetti e
       Incantesimi Iniziali" già esistente (task #74) — N dropdown incantesimi di 1° livello, N = mod.
       caratteristica da incantatore + livello (min 1), **stessa identica formula già applicata da
       `spells_view.py._calc_max_prepared()`** per i "full preparatori" (verificato che al Lv.1 anche la formula
       "mezzo preparatore" del Paladino produce lo stesso risultato: mod + max(1,1//2) = mod+1, quindi un'unica
       formula copre entrambi i casi in fase di creazione, sempre Lv.1). Punteggio caratteristica usato per il
       calcolo: Standard Array assegnato + bonus razziali risolti (`get_resolved_race()` + flex Mezzelfo se
       applicabile) — nuovo `_prepared_spell_ability_score()`/`_compute_prepared_spell_count()`, metodi di classe
       (non chiusure locali) per essere richiamabili sia dalla UI sia dalla validazione sia dal salvataggio. Nel
       wizard (dove la scelta stat e questa sezione convivono nella stessa schermata "Revisione") il ricalcolo è
       agganciato anche a `_on_stat_change` così cambiare la caratteristica da incantatore aggiorna live il numero
       di dropdown; nel form manuale (fasi "Punteggi" e "Scelte" separate, task #76) non serve: le stat sono già
       definitive quando si arriva alla fase Scelte. Salvati come `known_spell` con `is_prepared=True` (stessa
       convenzione già in uso per trucchetti/incantesimi conosciuti). **Il Ranger è stato deliberatamente escluso**
       da questa lista nonostante `spells_view.py._PREP_HALF = {"paladino","ranger"}` lo tratti come "mezzo
       preparatore" — verificato in `ranger.json → feature "Incantesimi" (lv2)` che il testo PHB già trascritto
       dice esplicitamente "*Un ranger **conosce** due incantesimi di 1° livello a sua scelta*", la stessa
       meccanica "know" di Bardo/Stregone/Warlock, non una preparazione giornaliera — quindi
       `spells_view.py._PREP_HALF` contiene un **bug pre-esistente** (Ranger non dovrebbe essere lì, dovrebbe
       essere trattato come le classi "know" senza alcun limite di preparazione), non toccato in questa sessione
       perché fuori scope rispetto alla richiesta di Davide (riguarda il calcolo del limite nella tab Incantesimi
       già esistente, non la creazione) — segnalato come nuovo TODO dedicato più sotto. Gli incantesimi iniziali
       del Ranger restano correttamente affidati al meccanismo già esistente (SPELL_LEARN al level-up dal 2°
       livello).
     - **Mago**: implementato il Libro degli Incantesimi iniziale — 6 incantesimi di 1° livello a scelta, dato già
       confermato testualmente nel JSON già auditato (`mago.json → feature "Incantesimi"`: "*Il tuo libro inizia
       con 6 incantesimi di 1° livello*"), non un numero indovinato. Aggiunto il campo
       `"spellbook_starting_spells": 6` a `mago.json` (stesso principio "il numero vive nel JSON, non hardcoded in
       Python" di tutte le migrazioni precedenti di questo progetto) e
       `GameDataLoader.get_spellbook_starting_spells(class_name)`. Nuova sezione "Libro degli Incantesimi" nello
       stesso blocco UI, 6 dropdown. **Punto delicato risolto correttamente**: la tab Incantesimi
       (`spells_view.py`, dove il Mago è già in `_PREP_FULL`) applica un tetto massimo di incantesimi "preparati"
       contemporaneamente (mod. Intelligenza + livello, min 1) e **blocca solo NUOVE preparazioni oltre il tetto —
       non corregge mai uno stato preesistente già sopra il limite**; salvare tutti e 6 gli incantesimi del libro
       come `is_prepared=True` incondizionatamente avrebbe quindi potuto far nascere un Mago con INT bassa già
       "sopra al limite" fin dal primo avvio (es. INT 14 → mod+2 → tetto 3, ma 6 incantesimi tutti preparati).
       **Fix**: tutti e 6 salvati come `known_spell` (nel libro), ma solo i primi `min(6, tetto)` con
       `is_prepared=True` — nuovo `_compute_mago_max_prepared()` (stessa formula/pattern di
       `_compute_prepared_spell_count()`, ma non ristretto a Chierico/Druido/Paladino). Verificato con test
       end-to-end (DB temporaneo isolato): Mago INT 14 (mod+2, tetto=3) con 6 incantesimi scelti → 6 righe
       `known_spell` di 1° livello create, esattamente 3 con `is_prepared=True` e 3 con `is_prepared=False`,
       nessuna violazione del tetto già applicato da `spells_view.py`.
  - **Validazione**: entrambe le nuove sezioni (Incantesimi preparati iniziali, Libro degli Incantesimi) integrate
    nei punti di validazione già esistenti per trucchetti/incantesimi conosciuti (pulsante "Continua" della fase
    Revisione/Scelte + validazione di difesa in profondità al salvataggio finale, stesso pattern gemello già in uso
    da task #74) — blocca l'avanzamento se mancano scelte o ci sono duplicati, stesso messaggio d'errore unificato.
  - ~~**Nuovo TODO segnalato, non affrontato in questa sessione**: `spells_view.py._PREP_HALF =
    {"paladino","ranger"}` include erroneamente il Ranger tra i "mezzo preparatori"~~ — **✅ risolto più tardi lo
    stesso giorno (2026-07-11)**, dopo che Davide ha incollato il testo completo della feature "Incantesimi" del
    Ranger dal manuale, confermando la diagnosi. Vedi la voce dedicata in Checklist Revisione Dati PHB → "Altri
    file di riferimento" / TODO qui sopra ("`spells_view.py._PREP_HALF` includeva erroneamente il Ranger...") per
    il changelog completo del fix — `"ranger"` è stato spostato da `_PREP_HALF` a `_KNOW_CLASSES`. Lo stesso
    scambio di messaggi ha anche fatto emergere un gap più ampio e non ancora implementato: la meccanica di
    **sostituzione** di un incantesimo conosciuto al level-up (Ranger/Stregone/Warlock, testo PHB identico in tutti
    e 3 i file classe) non ha nessuna UI dedicata — documentato come nuovo TODO nella stessa voce.
  - **Verifica di chiusura**: `py_compile`/`pyflakes` puliti su `wizard_view.py`, `manual_form.py`,
    `data/game_data/game_data_loader.py`; validazione JSON su `acolito.json`, `barbaro.json`, `paladino.json`,
    `equipment/adventuring_gear.json`, `mago.json`; test end-to-end (DB temporaneo isolato, mai quello reale) per
    l'espansione dotazioni, la scelta incantesimi preparati (Chierico Umano/Nano delle Colline/Mezzelfo con flex
    WIS, Paladino, Druido Elfo dei Boschi — tutti con N atteso corretto; Guerriero/Mago/Bardo correttamente N=0) e
    il libro del Mago (split preparati/non preparati); script di cross-check su tutti i 12 file classe + 13
    background per le 23 occorrenze "Dotazione da X" (zero non risolte) e per Giavellotto (zero occorrenze residue
    come `item_type:"weapon"`).
- **Fix "Unknown control: FilePicker" nel deploy web/Docker (2026-07-12)** — bug report di Davide (screenshot):
  apre l'app da browser desktop puntato a un server remoto (`moscaflixgame.ddns.net`) e cliccando "cambia foto" nel
  Profilo compare un banner rosso "Unknown control: FilePicker" invece del dialog di selezione file.
  **Chiarito il contesto di deploy** (non documentato altrove nel progetto): Davide usa il
  `Dockerfile`/`docker-compose.yml` già presenti in `dnd_app/` per esporre l'app come server web durante i test
  (`ENV FLET_WEB=true`, `main.py` chiama `ft.run(run_app, view=ft.AppView.WEB_BROWSER, port=8000, host="0.0.0.0")`)
  — un vero deploy Flet "web mode" servito da Docker, non solo l'app desktop vista in una finestra. L'obiettivo
  finale restano le build native per store (desktop/mobile), il web/Docker è solo per test in questa fase.
  **Causa reale, confermata via ricerca sui bug tracker upstream di Flet** (issue flet-dev/flet #6250/#6251, stesso
  pattern anche in #6040): in modalità web, i controlli "Service" come `ft.FilePicker` falliscono con "Unknown
  control" o `TimeoutException` se vengono creati e aggiunti a `page.overlay` nello stesso momento in cui si chiama
  `pick_files()` — il codice esistente (`_pick_photo_mobile()` in `profilo_tab.py`, `_pick_mobile()` in
  `maps_view.py`) faceva esattamente questo: creava un `ft.FilePicker()` nuovo dentro il click handler, lo
  aggiungeva subito all'overlay, chiamava `page.update()` e SUBITO DOPO `pick_files()` — l'handshake
  albero-controlli lato client JS (che deve "vedere" il nuovo controllo prima di poter registrare il suo listener)
  non fa in tempo a completarsi in quella finestra temporale. Questo comportamento era già documentato in CLAUDE.md
  per la modalità DESKTOP nativa ("Unknown control: FilePicker" → subprocess nativo come soluzione), ma non era mai
  stata verificata la modalità web/Docker, che soffre dello stesso bug upstream per un motivo diverso (timing, non
  "controllo non supportato del tutto").
  **Fix**: in entrambi i file, il `FilePicker` non viene più creato al momento del click. Creato invece UNA SOLA
  VOLTA in `did_mount()` (quando la tab/vista viene montata, ben prima che l'utente possa cliccare "cambia foto"),
  aggiunto subito a `page.overlay` e "flush-ato" con un `page.update()` — dando tempo all'handshake di completarsi
  prima che l'utente interagisca. Il click handler (`_pick_photo_mobile()`/`_pick_mobile()`) ora riusa questa
  istanza persistente (`self._file_picker` in `ProfiloTab`, `view._file_picker` in `MapsView`), richiamando solo
  `pick_files()` (e in `MapsView`, riassegnando `on_result` perché ogni dialog crea/modifica mappa ha il proprio
  `img_data`/label/preview) — mai più ricreando/riaggiungendo il controllo. Fallback difensivo in entrambi i file:
  se `did_mount()` non ha ancora fatto in tempo a registrare il picker (caso limite), il vecchio comportamento
  "crea al volo" resta come rete di sicurezza, esposto allo stesso bug ma senza crash.
  **`_on_mobile_file_picked()` (profilo_tab.py) aggiornato di conseguenza**: non rimuove più il picker da
  `page.overlay` dopo l'uso (prima lo faceva ad ogni foto caricata) — ora resta registrato permanentemente per
  essere riusato alla prossima modifica foto, coerente con la strategia "registra una sola volta".
  **Onestà sui limiti di questo fix**: si tratta della mitigazione raccomandata dalla community Flet per questo bug
  upstream, non di una garanzia assoluta — Flet non documenta ufficialmente una soglia di timing minima. Se il
  problema dovesse ripresentarsi (specialmente su connessioni più lente tra client e server Docker), il prossimo
  passo sarebbe aprire/aggiornare una issue upstream o valutare un downgrade/upgrade mirato della versione Flet —
  non ulteriori tentativi di patch lato nostro codice, che già segue il pattern corretto raccomandato.
  **Verificato**: `py_compile`/`pyflakes` puliti su `profilo_tab.py` e `maps_view.py` (solo il rumore preesistente
  di `from config.settings import *`); regressione `py_compile` sull'intero albero sorgente. Non verificabile
  end-to-end in questa sessione (richiede un vero client browser + server Docker in esecuzione, non riproducibile
  in un test headless) — Davide dovrà testare di nuovo su `moscaflixgame.ddns.net` e confermare se il banner rosso
  non compare più.
  ~~**Onestà sui limiti di questo fix**: si tratta della mitigazione raccomandata dalla community Flet...**~~ — **✅
  teoria del timing confermata INSUFFICIENTE, causa radice reale trovata e corretta lo stesso giorno
  (2026-07-12)**. Davide ha ritestato subito dopo questo fix e riportato: "adesso esce all'istante senza nemmeno
  cliccare sull'immagine" — l'errore compariva PRIMA ancora del click, non più al click. Questo sintomo è
  incompatibile con la teoria del timing/handshake: se fosse stata una race di registrazione tardiva, registrare il
  controllo prima (come fatto qui) avrebbe dovuto ridurre il problema, non renderlo immediato. Ri-analisi: il vero
  problema non era (solo) di timing, ma **architetturale**. In un deploy web genuino (Docker, browser su una
  macchina diversa dal processo server Python — esattamente il caso di Davide, `moscaflixgame.ddns.net`) il file
  scelto dall'utente esiste **SOLO lato client** finché non viene effettivamente trasferito byte per byte al
  server. Tutto il codice precedente (`_on_mobile_file_picked()` in `profilo_tab.py`, `_pick_mobile()` in
  `maps_view.py`) leggeva `e.files[0].path` **lato server**, assumendo che quel percorso fosse raggiungibile dal
  processo Python — assunzione VERA solo per le build mobile native (`flet build apk/ipa`, dove Python gira sullo
  stesso dispositivo del client) ma **FALSA** per un vero deploy browser remoto, dove client e server sono macchine
  diverse e non condividono filesystem. Nessuna quantità di "registra il FilePicker prima" poteva risolvere questo,
  perché il problema non era mai stato "il controllo non è pronto" ma "il percorso del file non esiste sul server".
  **Fix reale implementato**: vero meccanismo di upload client→server di Flet, verificato via introspezione diretta
  del package `flet==0.85.3` installato (stessa versione pinnata in `requirements.txt`/Dockerfile) — `ft.run(...,
  upload_dir=...)` configura una cartella server-side dedicata; `page.get_upload_url(file_name, expires)` genera un
  URL firmato per il trasferimento; `FilePicker.upload([ft.FilePickerUploadFile(name=..., upload_url=...)])` avvia
  il trasferimento reale dei byte; `FilePicker.on_upload` riceve eventi `FilePickerUploadEvent(file_name, progress,
  error)` col progresso, fino a `progress >= 1.0` a trasferimento completato.
  - **`data/database.py`**: nuova `get_upload_dir_path()` — stessa convenzione di `get_db_path()`
    (`~/.dnd_companion/`), sottocartella dedicata `uploads/`, creata se assente. Usata SOLO dal ramo web, mai
    raggiunta dalle build mobile native.
  - **`main.py`**: il ramo `if _web:` ora passa `upload_dir=get_upload_dir_path()` a `ft.run(...)` — senza questo, Flet non espone affatto l'endpoint di upload e `page.get_upload_url()` fallirebbe.
  - **`profilo_tab.py`**: `_on_mobile_file_picked()` ora si biforca in base a `page.web` — se `True`, chiama
    `page.get_upload_url(f.name, 600)` e poi `self._file_picker.upload([...])`, senza leggere alcun path locale; il
    completamento asincrono arriva nella nuova `_on_web_photo_uploaded()`, che attende `progress >= 1.0` (nessun
    errore), legge il file da `get_upload_dir_path()`, lo passa a `_load_photo()` (invariata, converte in
    JPEG/base64 e salva sul DB) e infine rimuove il file temporaneo. Se `page.web` è `False` (mobile nativo), il
    comportamento resta quello originale (lettura diretta di `e.files[0].path`), corretto in quel contesto.
  - **`maps_view.py`**: stessa identica architettura applicata a `_pick_mobile()` — `on_result()` si biforca su
    `page.web`; in modalità web richiede l'URL di upload e avvia `FilePicker.upload()`, con una nuova closure
    `on_upload()` che legge da `get_upload_dir_path()`, converte in base64 via `_load_image_base64()` (invariata) e
    aggiorna l'anteprima con `_update_preview()` (invariata); ripulisce il file temporaneo a fine elaborazione.
  - **Onestà sui limiti**: questo fix richiede che il browser del client possa raggiungere l'endpoint di upload
    esposto dal server Flet (stesso host/porta già usato per l'app, nessuna configurazione di rete aggiuntiva
    prevista) — non testabile end-to-end in questo ambiente sandbox (serve un vero client browser + server Docker
    in esecuzione). Verificato invece a livello di logica: simulazione standalone dell'intero ciclo
    `FilePickerUploadEvent` (eventi intermedi con `progress<1.0` ignorati correttamente, evento con `error` non
    processato, evento finale che legge il file dalla cartella upload temporanea e lo ripulisce dopo) sia per
    `profilo_tab.py` sia per `maps_view.py`, con cartella upload temporanea isolata (mai quella reale) — tutti i
    casi passati. `py_compile`/`pyflakes` puliti su `main.py`, `data/database.py`, `profilo_tab.py`,
    `maps_view.py`; regressione `py_compile` sull'intero albero sorgente (esclusa `build/`, contiene codice vendor
    Flutter di terze parti non gestito da questo progetto). Davide dovrà testare di nuovo su
    `moscaflixgame.ddns.net` e confermare che l'upload della foto/mappa funzioni davvero da browser remoto.
  ~~**Davide dovrà testare di nuovo... e confermare che l'upload funzioni davvero da browser remoto.**~~ — **❌
  CONFERMATO NON FUNZIONANTE, causa radice VERA trovata (2026-07-12, stesso giorno, terzo tentativo)**. Davide ha
  ritestato e inviato uno screenshot: il banner rosso "Unknown control: FilePicker" ora compare **immediatamente
  all'apertura della scheda personaggio**, prima ancora di poter cliccare su qualunque cosa — non più "al click"
  (fix #1) né "subito dopo il mount ma solo quando si tenta di selezionare una foto" (fix #2): stavolta la barra
  rossa copre la UI fin dal primo render della tab Profilo. Questo sintomo è la prova diretta che il problema non è
  mai stato risolvibile aggiustando IL MODO in cui il nostro codice usa `ft.FilePicker` — è la sola ESISTENZA del
  controllo `ft.FilePicker` nell'albero della pagina, in questa combinazione Flet+deploy web, a essere rifiutata
  dal client.
  **Causa reale, questa volta confermata con fonte primaria diretta** (non più solo ipotesi): ricerca mirata sulla
  issue tracker upstream di Flet (`flet-dev/flet`), che ha restituito 3 issue aperte che descrivono ESATTAMENTE
  questo sintomo:
    - [Issue #6040](https://github.com/flet-dev/flet/issues/6040) — "filepicker in 0.28.3 ok but in ^0.80.1 show
      unKnown control: FilePicker": regressione confermata a partire da Flet ^0.80.1 (il progetto usa 0.85.3,
      stessa era). Riproduzione minima identica al nostro caso: `ft.FilePicker()` aggiunto a `page.overlay` in
      modalità `ft.AppView.WEB_BROWSER` → "Unknown control: FilePicker", nessun altro codice coinvolto.
    - [Issue #6250](https://github.com/flet-dev/flet/issues/6250) e
      [#6251](https://github.com/flet-dev/flet/issues/6251) (duplicate) — "FilePicker and UrlLauncher Service
      controls fail in web mode": lo sviluppatore che ha segnalato il bug ha provato ESATTAMENTE le stesse
      strategie tentate in questa sessione, in questo ordine: FilePicker globale, FilePicker in
      `did_mount()`/`MainLayout` (→ "Unknown control" su OGNI vista, identico al comportamento ora riportato da
      Davide), FilePicker per-click con `overlay.append()+update()` (→ `TimeoutException` dopo 10s), persino un
      `asyncio.sleep(0.3)` prima di `pick_files()` (→ ancora `TimeoutException`, il sonno non basta). **Nessuna
      delle strategie ha funzionato.** Causa ipotizzata dagli stessi maintainer/contributor: i controlli "Service"
      (`FilePicker`, `UrlLauncher`) richiedono che il client JS registri un listener tramite handshake WebSocket:
      in web mode con server-side rendering questo handshake non si completa mai in modo affidabile,
      indipendentemente da quando o come il controllo viene creato/registrato/usato — non è una race risolvibile
      con un timing diverso, è un bug strutturale del protocollo di controllo in questa modalità.
  **Perché anche il fix #2 (vero upload via `page.get_upload_url()`+`FilePicker.upload()`) non poteva funzionare**:
  quel meccanismo richiede comunque che `ft.FilePicker` sia un controllo riconosciuto e funzionante lato client per
  invocare `.upload()` — esattamente la capacità che questo bug upstream nega del tutto. Il diagnostico riportato
  nella issue #6250 conferma che anche `FilePicker.upload()` esiste nell'API Python (`[OK] FilePicker.upload()
  exists`) ma è comunque irraggiungibile in pratica, perché il controllo stesso non viene mai
  riconosciuto/registrato dal client.
  **Conclusione onesta**: questo NON è un bug risolvibile lato nostro codice applicativo. È un bug aperto e non
  risolto nella libreria Flet stessa (nessuna delle 3 issue risulta chiusa/fixata al momento di questa verifica),
  per qualunque strategia di registrazione del controllo `ft.FilePicker` in modalità web. I due tentativi
  precedenti in questa stessa giornata erano entrambi in buona fede tecnicamente motivati, ma partivano dalla
  premessa sbagliata che il problema fosse risolvibile lato applicazione.
  **Fix reale e definitivo applicato**: smettere del tutto di creare/registrare `ft.FilePicker` quando `page.web == True`, in entrambi i file:
    - `profilo_tab.py`: `did_mount()` ora registra il FilePicker solo se `not self._page.web`; `_pick_photo()`
      intercetta `page.web` PRIMA di qualunque logica FilePicker e mostra `_show_web_upload_unavailable_dialog()` —
      un `AlertDialog` che spiega onestamente il limite (bug confermato in Flet, non risolvibile da questo lato)
      invece del banner rosso che rompeva la UI. La logica di vero upload scritta nel fix #2
      (`_on_web_photo_uploaded()`, il ramo `page.web` dentro `_on_mobile_file_picked()`) resta nel codice,
      commentata come storica/irraggiungibile, pronta da ricollegare se in futuro si implementa un bypass che non
      passi da `ft.FilePicker` (vedi TODO sotto) — non cancellata, per lo stesso principio "non buttare lavoro
      corretto" già seguito altrove in questo file.
    - `maps_view.py`: stesso pattern — `did_mount()` non registra più il FilePicker in web mode; i due
      `pick_image()` (crea/modifica mappa) it fanno lo stesso controllo `page.web` e chiamano una nuova
      `_show_web_upload_unavailable_dialog(page)` module-level condivisa. Il ramo "vero upload" dentro
      `_pick_mobile()` è stato rimosso (non solo commentato, per tenere la funzione più snella — il pattern
      equivalente resta comunque documentato in `profilo_tab.py` come riferimento se servisse riprenderlo).
  **Verificato**: `py_compile`/`pyflakes` puliti su tutti e 4 i file (solo il rumore preesistente di `from
  config.settings import *`); regressione `py_compile` sull'intero albero sorgente (esclusa `build/`). Test
  end-to-end via bypass `__init__`/monkeypatch della property `page` (mai il DB reale): confermato che
  `did_mount()` in modalità web NON crea/aggiunge alcun `ft.FilePicker` a `page.overlay` (sia per `ProfiloTab` sia
  per `MapsView`); confermato che `_pick_photo()` in modalità web mostra il dialog e non chiama mai
  `_pick_photo_mobile()`; confermato per contrasto che la registrazione normale del FilePicker su mobile
  nativo/desktop resta invariata (`page.web == False` → comportamento di sempre, mai stato rotto in queste
  modalità). Non riproducibile un vero "Unknown control" in sandbox (serve il client Flutter-web servito da Flet,
  non emulabile qui) — la prova che il banner sia sparito arriverà dal prossimo test di Davide su
  `moscaflixgame.ddns.net`; questa volta però la richiesta è verificare che NON compaia più alcun banner rosso
  (comportamento atteso: dialog "Foto/Immagine non disponibile da browser" al click su "cambia foto"/"scegli
  immagine", nessun errore al semplice apertura della scheda/mappa).
  ~~**TODO per il futuro, se Davide vorrà davvero l'upload funzionante durante i test web**~~ — **✅ implementato il
  2026-07-12, stesso giorno, con un approccio più semplice del bypass HTTP originariamente ipotizzato — vedi voce
  dedicata "Libreria immagini" più sotto.**
- **Libreria immagini — sostituto definitivo di ft.FilePicker in modalità web (2026-07-12)** — Davide, dopo il fix
  precedente (dialog "non disponibile"), ha proposto un'alternativa concreta: "ho pensato, se li carico io a mano
  le foto? ho creato una cartella nel progetto, se quella cartella la creo anche sul server e ci passo le foto
  dentro quando apro la finestra per caricare le foto mostra tutti i file multimediali di quella cartella, questo
  dovrebbe poterlo fare o no?" — un picker che legge una cartella del filesystem server invece di un vero upload
  dal browser, bypassando `ft.FilePicker` (e quindi il bug upstream Flet) del tutto, non solo aggirandolo.
  **Analisi preliminare (discussa con Davide prima di scrivere codice, su sua esplicita richiesta "parliamone
  prima")**: confermato che `~/.dnd_companion` in `docker-compose.yml` era mappato su un **volume Docker nominato**
  (`dnd_data`), non su una cartella host reale — quindi non raggiungibile da Finder/scp senza passare da comandi
  Docker. Chiarito con Davide che ha accesso **SSH** alla macchina che fa girare `moscaflixgame.ddns.net`, il che
  rende un **bind mount** (cartella reale sull'host, mappata nel container) nettamente preferibile a un `docker cp`
  manuale ripetuto per ogni immagine. Confermata anche la preferenza di Davide per **una cartella unica** condivisa
  tra foto personaggi e immagini mappa (più semplice da gestire lato SSH, il picker filtra comunque solo per
  estensione immagine).
  **Implementazione**:
  - **`docker-compose.yml`**: nuovo bind mount `./dnd_image_library:/root/dnd_image_library`, separato dal volume
    `dnd_data` del DB (nome cartella volutamente "in chiaro", non un dotfolder, perché è pensata per essere
    raggiunta a mano da Davide via `scp`/`rsync`; il DB invece resta privato). Docker Compose crea la cartella sul
    host automaticamente al primo `docker compose up` se non esiste.
  - **`data/database.py`**: `get_upload_dir_path()` (il tentativo precedente, ora morto — nessun chiamante lo usava
    più dopo l'abbandono del meccanismo `FilePicker.upload()`) **rimosso** e sostituito con
    **`get_image_library_path()`** — stessa convenzione (`Path.home() / ...`, `mkdir` idempotente), ma path e
    semantica diversi: non più una cartella di transito per upload temporanei, ma la libreria persistente che
    Davide popola a mano. Risolve a `/root/dnd_image_library` nel container (coerente col bind mount sopra, dato
    che il container gira come root).
  - **`main.py`**: rimosso `upload_dir=get_upload_dir_path()` dalla chiamata `ft.run()` in modalità web — non più necessario, dato che non usiamo più l'endpoint di upload interno di Flet per niente.
  - **Nuovo modulo `ui/image_library.py`**: `get_image_library_path()` → lista immagini (`_list_library_images()`,
    filtrate per estensione — png/jpg/jpeg/gif/webp/bmp — e ordinate per data di modifica decrescente, così i file
    appena caricati via scp compaiono in cima), miniatura ridotta via PIL (`_make_thumbnail_b64()`, max 160×160,
    non solleva mai eccezioni — un file con estensione valida ma contenuto non leggibile come immagine, es.
    corrotto durante il trasferimento, produce un placeholder invece di rompere l'intera griglia) e
    `show_image_library_picker(page, on_select)` — `AlertDialog` con una lista verticale di card (stesso stile
    visivo già usato per le card mappa in `maps_view.py`: `Container` con thumbnail + nome file + bottone di
    conferma, non un `GridView`/`Wrap` — nessuno dei due controlli era già in uso altrove nel progetto, quindi si è
    preferito riusare un pattern già collaudato piuttosto che introdurne uno nuovo non verificato). Bottone
    "Ricarica" per rileggere la cartella senza chiudere il dialog (utile se si copiano file via SSH mentre il
    dialog è aperto). Cartella vuota → messaggio con il path esatto (`get_image_library_path()`) da usare in `scp`.
  - **`profilo_tab.py`**: rimossi `_show_web_upload_unavailable_dialog()` e `_on_web_photo_uploaded()` (il codice
    storico del tentativo upload-via-FilePicker, ormai morto e irraggiungibile — non aveva senso lasciarlo "in caso
    servisse un bypass futuro" ora che il bypass è stato realmente implementato in un modo diverso); il ramo
    `page.web` dentro `_on_mobile_file_picked()` rimosso (quel metodo ora è chiamato SOLO dal ramo mobile nativo).
    `_pick_photo()` in modalità web chiama `show_image_library_picker(self._page, on_select=self._load_photo)` —
    riusa `_load_photo()` esistente senza alcuna modifica, dato che si aspettava già un path locale.
  - **`maps_view.py`**: stesso trattamento — `_show_web_upload_unavailable_dialog()` rimossa, sostituita da una
    nuova `_pick_from_library()` module-level (mirror di `_pick_mobile()` ma per il ramo web: chiama
    `show_image_library_picker()` con un `on_select` che riusa `_load_image_base64()` + `_update_preview()`,
    identico a quanto già faceva `_pick_mobile().on_result` per il path nativo). **Bug di regressione trovato e
    corretto nello stesso passaggio**: i due `pick_image()` (dialog crea/modifica mappa) chiamavano ancora
    incondizionatamente `_pick_mobile(...)` sia per `page.web` sia per mobile nativo (`if page.web or platform in
    (...)`) — un refuso della sessione precedente, quando la logica web era stata rimossa da **dentro**
    `_pick_mobile()` senza aggiornare i due punti che lo chiamavano. In pratica, aprendo "Cambia immagine" da
    browser web, il codice avrebbe chiamato `view._file_picker.pick_files()` su un `_file_picker` sempre `None` in
    web mode (dato che `did_mount()` non lo registra più lì) → `AttributeError` a runtime, mai eseguito perché mai
    testato end-to-end nel frattempo. Corretto separando esplicitamente i 3 rami (`page.web` → libreria; `platform
    in (ANDROID, IOS)` → `_pick_mobile`; altrimenti → dialogo nativo desktop) in entrambi i punti.
  **Verificato**: `py_compile`/`pyflakes` puliti su tutti i file toccati (solo il rumore preesistente di `from
  config.settings import *`); regressione `py_compile` sull'intero albero sorgente (esclusa `build/`, `.venv/`).
  Test end-to-end su `ui/image_library.py` con cartella temporanea isolata (mai quella reale): cartella vuota →
  lista vuota senza eccezioni; file con estensione valida ma contenuto corrotto → incluso nella lista (il filtro è
  solo per estensione) ma miniatura vuota con `logger.warning` (mai un crash); `.DS_Store`/file non-immagine
  esclusi correttamente (utile perché Davide copierà i file da un Mac via scp, che lascia sempre `.DS_Store` nelle
  cartelle sincronizzate); ordinamento per data di modifica decrescente confermato; `_data_uri()` rileva
  correttamente il mime; simulazione completa del flusso dialog→click→selezione (bypass `page`/`AlertDialog` reali,
  mai un vero client Flet) conferma che `on_select` riceve il path corretto e il dialog si chiude; stato vuoto
  renderizzato senza eccezioni. Verificata anche la wiring dei 2 call site reali in `maps_view.py` (lettura diretta
  del sorgente, non solo simulazione) per confermare che il fix del bug di regressione è applicato a entrambi i
  dialog (crea E modifica mappa), non solo a uno. Non riproducibile un vero client browser in questo ambiente
  sandbox — Davide dovrà: (1) applicare il nuovo bind mount (`docker compose up` ricrea il container con la nuova
  configurazione), (2) copiare qualche immagine di prova nella cartella `dnd_image_library` sul server via `scp`,
  (3) verificare che il picker le mostri correttamente sia da Profilo (foto personaggio) sia da Mappe
  (crea/modifica).
- **Mostrare rapporto "conosciuti/attesi" per gli incantesimi delle classi "know" (2026-07-11)** — ultimo punto del
  bug report multi-parte di Davide: "per le classi con incantesimi conosciuti fissi esce incantesimi conosciuti, ma
  non quelli selezionati, comodo per capire se hai sforato, una gestione simile va fatta se non c'è anche per gli
  altri incantatori." Analisi: in `spells_view.py → _section_prep_banner()`, le classi "preparatrici"
  (Chierico/Druido/Mago/Paladino) mostrano già un banner "X / Y preparati" con colore rosso al limite
  (`_calc_max_prepared()`, blocco rigido in `_toggle_prepared()`) — questa parte ("gli altri incantatori") esisteva
  già. Le classi "know" (Bardo/Ranger/Stregone/Warlock) mostravano invece solo un conteggio grezzo "N incantesimi
  conosciuti", senza alcun totale di riferimento: impossibile capire a colpo d'occhio se il giocatore aveva
  selezionato più incantesimi di quanti il suo livello ne concede.
  **Fix**: nuova `_expected_known_spell_count(c)` in `spells_view.py` — calcola il totale atteso di incantesimi
  (livello ≥1, trucchetti esclusi) per il livello attuale usando le stesse tabelle già verificate e usate da
  `core/level_manager.py` per lo step SPELL_LEARN (`get_spells_known_at_1()` + `get_spell_learn_delta()`
  cumulativo) — nessun dato nuovo, solo il numero di riferimento reso visibile qui. Il banner ora mostra "N / M
  incantesimi conosciuti" (era solo "N incantesimi conosciuti"), con ProgressBar e colore rosso quando `N > M`, e
  una nota esplicita ("Hai X incantesimi in più del previsto per il tuo livello — controlla se è corretto (Segreti
  Magici e simili contano a parte)").
  **Scelta deliberata: nessun blocco rigido come per i preparatori** — a differenza del tetto dei "preparati" (che
  blocca fisicamente nuove preparazioni oltre il limite), qui il toggle resta libero. Motivo: gli incantesimi extra
  da Segreti Magici del Bardo (presi "da qualsiasi classe", salvati direttamente come `known_spell` fuori da questo
  toggle) si sommerebbero al conteggio senza che ci sia nulla di sbagliato — un blocco rigido avrebbe impedito al
  giocatore di aggiungere manualmente da questa stessa tab un incantesimo legittimo in scenari limite (es.
  correzioni post-audit, homebrew). Stessa scelta di compromesso già accettata per i trucchetti (vedi TODO storico
  "Crescita Trucchetti Conosciuti", ora risolto solo per il promemoria al level-up, non per l'enforcement in questa
  tab) — qui però il numero di riferimento è ora almeno visibile, cosa che prima mancava del tutto anche per gli
  incantesimi.
  **Verificato** con test end-to-end (DB temporaneo isolato): `_expected_known_spell_count()` per
  Bardo/Ranger/Stregone/Warlock a vari livelli confrontato contro le tabelle "Incantesimi Conosciuti" già
  verificate in CLAUDE.md (Bardo lv20=22, Stregone lv20=15, Warlock lv20=15, Ranger lv20=11 — tutti coincidenti);
  render del banner con `SpellsView._section_prep_banner()` verificato per un Bardo Lv.3 con 2 incantesimi noti ("2
  / 6 incantesimi conosciuti", nessun avviso) e poi con 7 ("7 / 6 incantesimi conosciuti", avviso "1 incantesimo in
  più del previsto" mostrato correttamente). `py_compile`/`pyflakes` puliti (solo rumore preesistente `from
  config.settings import *`).
- **Fix equipaggiamento background: placeholder "(a scelta)" mai risolti, "Costume" non trattato come indumento
  (2026-07-11)** — bug report di Davide, parte di un batch più ampio: "liuto equipaggiamento del background non
  riconosciuto come strumento ma messo in inventario, strumento musicale a scelta penso sempre da background
  scritto come frase invece di permettere la scelta, abito, costume e costume scritto 2 volte e inserito in
  inventaio quando costume è un abito. trucchi per il camuffamento è in inventario ma anche in strumenti." Analisi
  separata dei 3 sintomi:
  1. **Placeholder "(a scelta)" mai risolti contro la scelta reale del giocatore** — `intrattenitore.json →
     equipment` ha `"Strumento musicale (a scelta)"` come nome letterale (non un nome di strumento reale come
     "Liuto"), stesso pattern in `artigiano_gilda.json`/`eroe_del_popolo.json → equipment` con `"Strumenti da
     artigiano (a scelta)"`. Questi placeholder esistono perché lo strumento/attrezzo EFFETTIVO viene scelto
     altrove (`tool_proficiencies → {"type":"choice",...}`, tracciato in `self._review_tools`), ma `_save_item()`
     (ramo generico, condiviso da `wizard_view.py`/`manual_form.py`) non aveva mai incrociato i due dati: il
     placeholder finiva sempre in inventario col nome letterale "(a scelta)" invece del nome scelto (es. "Liuto"),
     e sempre con `category="misc"` invece di `"tool"` — da cui la sensazione di Davide che lo strumento scelto
     "non fosse riconosciuto".
     **Fix**: nuovo contatore `_choice_equip_idx` (chiuso su `_save_item` via `nonlocal`, incrementato ogni volta
     che un nome equipaggiamento contiene la sottostringa `"(a scelta)"`) usato per indicizzare
     `self._review_tools` nell'ordine in cui i placeholder compaiono — se `self._review_tools[idx]` è valorizzato,
     l'oggetto viene creato con quel nome esatto e `category="tool"`; altrimenti (nessuna scelta disponibile, caso
     limite) resta il nome placeholder con un `logger.warning()` diagnosticabile invece di sparire silenziosamente.
     Identico in entrambi i file di creazione. Verificato con test end-to-end (DB temporaneo isolato):
     Intrattenitore con "Liuto" scelto → riga inventario `name="Liuto", category="tool"`; Artigiano di Gilda con
     "Strumenti da Ceramista" → risolto correttamente; Eroe Popolare con "Attrezzi da Contadino" → risolto
     correttamente; caso senza scelta disponibile → fallback al nome placeholder letterale, nessun crash.
  2. **"Costume" (Intrattenitore) non trattato come indumento** — `item_type` era `"item"` (oggetto generico,
     `category="misc"`) invece di `"armor"` — un costume da esibizione è concettualmente lo stesso tipo di oggetto
     di "Abito comune" (indumento indossabile, zero effetto meccanico sulla CA), già gestito correttamente da
     `_save_armor_by_name()` per nomi non presenti nel catalogo `equipment/armor.json` (crea comunque l'oggetto ma
     con `ca_value=0, armor_type=""`, che `calculate_and_update_ca()` ignora del tutto). **Fix**:
     `intrattenitore.json → equipment → "Costume"` cambiato da `item_type: "item"` a `item_type: "armor"`.
     **Effetto collaterale positivo, non richiesto esplicitamente ma coerente con "costume scritto 2 volte"**: un
     Bardo Intrattenitore riceve sia "Abito comune" (equipaggiamento di classe, se scelto) sia "Costume"
     (equipaggiamento di background) — con entrambi ora correttamente tipizzati come indumento `armor_type=""`, il
     passaggio di finalizzazione esclusività armature già esistente (`resolve_armor_equip()`, task #93) mantiene
     equipaggiato un solo indumento tra i due invece di "indossarli entrambi contemporaneamente", risolvendo
     automaticamente anche la sensazione di duplicazione segnalata, senza bisogno di nuova logica dedicata.
     Verificato con test end-to-end: "Costume" creato con `category="armor", armor_type="", ca_value=0,
     is_equipped=True`.
  3. **"Trucchi per il Camuffamento" presente sia in `tool_proficiencies` sia in `equipment` (Ciarlatano)** —
     verificato che questo NON è un bug ma un pattern già intenzionale e rivisto in precedenza in questo progetto
     (stesso principio già confermato per "Borsa da Erborista" dell'Eremita): la competenza/proficiency e il
     possesso fisico dell'oggetto sono due fatti distinti del PHB (hai la competenza E porti con te il kit).
     **Nessuna modifica** a `ciarlatano.json` — l'oggetto in `equipment` ora beneficia comunque del fix del punto 1
     se il suo nome contenesse "(a scelta)" (non è il caso qui, il nome è già letterale e corretto), e viene
     comunque creato con `category="misc"` come prima (non "tool", perché non passa dal resolver — non contiene "(a
     scelta)"); nessuna azione necessaria.
  - **Verifica di chiusura**: `py_compile` e `pyflakes` puliti su entrambi i file di creazione; validazione JSON di
    `intrattenitore.json`; 3 test end-to-end (DB temporaneo isolato, mai quello reale) coprenti
    Intrattenitore/Artigiano di Gilda/Eroe Popolare con scelta valorizzata, più un quarto test per il caso "nessuna
    scelta disponibile" (fallback sicuro).
- **Fix crescita "Trucchetti Conosciuti" mai proposta al level-up (2026-07-11)** — bug report di Davide: "il bardo
  e altri incantatori imparano anche altri trucchetti a determinati livelli, non solo incantesimi, non mi sembra
  gestita questa cosa." Confermato: TODO già segnalato in una sessione precedente (Audit Level-Up Phase 3,
  Stregone) ma mai risolto — `core/level_manager.py` non generava mai uno step quando il numero di trucchetti
  conosciuti cresce.
  **Dati verificati** leggendo visivamente (`pdftoppm`, non `pdftotext` — inaffidabile su queste tabelle) le
  colonne "Trucchetti Conosciuti" delle 6 tabelle di classe PHB IT che hanno un conteggio fisso di trucchetti
  (campo `cantrips_known_at_1` già presente nei rispettivi JSON): Bardo p.53, Chierico p.57, Druido p.65, Mago
  p.82, Stregone p.108, Warlock p.114. Tutte e 6 crescono di esattamente **+1 al 4° livello e di nuovo +1 al 10°
  livello**, nessuna eccezione (es. Bardo 2→3→4, Chierico 3→4→5, Stregone 4→5→6). Scope corretto rispetto al bug
  report originale: non solo Bardo/Mago/Stregone/Warlock (le 4 citate nel vecchio TODO) ma anche **Chierico e
  Druido**, che hanno lo stesso identico campo `cantrips_known_at_1` e la stessa progressione — il vecchio TODO le
  aveva escluse per errore.
  **Fix**:
  - `core/level_manager.py`: nuovo `StepType.CANTRIP_LEARN`. Costante `_CANTRIP_GROWTH_LEVELS = (4, 10)` — vive
    come costante Python (non duplicata in 6 file JSON identici) perché è una progressione PHB universale senza
    eccezioni tra le 6 classi, stessa categoria di `ASI_LEVELS_DEFAULT`. Generato uno step (`count: 1`, sempre
    esattamente +1) quando `class_name` è una delle 6 classi con `cantrips_known_at_1 > 0` e `new_level` è 4 o 10.
  - `ui/views/character_sheet/profilo_tab.py`: nuovo ramo `elif step.step_type == StepType.CANTRIP_LEARN` — un
    singolo dropdown "Nuovo trucchetto", popolato da `_loader.get_spells(c.class_name)` filtrato a `level == 0` ed
    escludendo i trucchetti già conosciuti dal personaggio (stesso pattern minimale di SPELL_LEARN ma senza vincolo
    di livello massimo/slot, dato che i trucchetti non ne hanno). Nuova lista `cantrip_learn_refs`, integrata nei
    blocchi di validazione (sempre obbligatorio, come SPELL_LEARN — non opzionale come SPELL_SWAP) e di salvataggio
    (`_save_known_spell(...)`, `is_prepared=True`, stessa convenzione dei trucchetti iniziali di task #74).
  - **Non affrontato, deliberatamente fuori scope**: l'assenza di un tetto massimo imposto in `spells_view.py` (i
    trucchetti restano trattati come illimitati in quella tab, come già segnalato nel vecchio TODO) — questo fix
    copre il promemoria/picker al level-up (il percorso normale con cui un giocatore impara nuovi trucchetti), non
    introduce enforcement retroattivo su personaggi già esistenti con trucchetti "in eccesso" da level-up passati
    non ancora tracciati da questo meccanismo.
  - **Verificato**: `get_level_up_steps()` testato su tutte le 12 classi × livelli 2-20 — le 6 classi
    cantrip-classes emettono lo step esattamente ai livelli 4 e 10 (nessun altro livello, nessuna delle altre 6
    classi non-incantatrici/senza trucchetti fissi emette nulla); test end-to-end (DB temporaneo isolato, mai
    quello reale) di risoluzione pool + salvataggio: un Bardo Lv.4 con 2 trucchetti già conosciuti (Luce,
    Prestidigitazione) vede correttamente questi due esclusi dal pool eleggibile, la scelta del terzo trucchetto
    viene salvata come `known_spell` aggiuntivo senza toccare i due esistenti. `py_compile`/`pyflakes` puliti su
    `core/level_manager.py` e `profilo_tab.py` (solo il rumore preesistente di `from config.settings import *`).
- **Fix bug `_PREP_HALF` (Ranger) + implementazione sostituzione incantesimo conosciuto al level-up (2026-07-11)**
  — seguito diretto della sessione precedente: Davide ha incollato il testo completo della feature "Incantesimi"
  del Ranger dal manuale, confermando la diagnosi già proposta come TODO (Ranger è una classe "know" come
  Bardo/Stregone/Warlock, non un "mezzo preparatore"). Poi ha incollato anche il testo della feature "Incantesimi"
  del Bardo, che ha rivelato un secondo problema (la trascrizione del Bardo era incompleta) e confermato che la
  meccanica di sostituzione è universale a tutte e 4 le classi.
  1. **Fix `spells_view.py._PREP_HALF`**: `"ranger"` spostato da `_PREP_HALF` a `_KNOW_CLASSES` (ora `_PREP_HALF =
     {"paladino"}`, `_KNOW_CLASSES = {"bardo", "ranger", "stregone", "warlock"}`). Docstring di modulo aggiornata
     con la citazione del manuale. Verificato con test end-to-end (DB temporaneo isolato): un Ranger Lv.5 Sag 14
     con 3 incantesimi conosciuti tutti preparati ora ha `_calc_max_prepared() is None` (nessun tetto — prima
     avrebbe dato 4) e nessuno dei 3 viene toccato dal cambio; il Paladino (rimasto in `_PREP_HALF`) continua a
     restituire correttamente il tetto calcolato dalla formula.
  2. **`bardo.json → feature "Incantesimi"` completata**: il testo esistente conteneva solo le due frasi di formula
     (CD/attacco), senza il paragrafo su incantesimi conosciuti/appresi/sostituibili — un'omissione reale della
     trascrizione originale, non un'assenza nel manuale. Riscritta con il testo fornito da Davide (ripulito dai
     refusi OCR tipici della scansione: "r •"→"1°", "Conos ciuti"→"Conosciuti", "H bardo"→"il bardo", stesso
     trattamento già applicato altrove nel progetto per le trascrizioni dalle pagine scansionate). Il nuovo testo
     conferma anche, con fonte primaria diretta, il valore `spells_known_at_1: 4` già presente nel file (ottenuto
     in precedenza per calcolo indiretto, task #74) — combacia esattamente ("Un bardo conosce quattro incantesimi
     di 1° livello a sua scelta").
  3. **Implementata la meccanica di sostituzione** (confermata testualmente identica in
     Bardo/Ranger/Stregone/Warlock: "quando [la classe] acquisisce un livello, può scegliere un incantesimo che
     conosce e sostituirlo con un altro incantesimo della lista; anche il nuovo incantesimo deve essere di un
     livello di cui [la classe] possiede degli slot incantesimo"), su richiesta esplicita di Davide dopo conferma
     via `AskUserQuestion` ("Sì, implementala ora").
     - **`core/level_manager.py`**: nuovo `StepType.SPELL_SWAP`, generato per Bardo/Stregone/Warlock a partire dal
       level-up verso il Lv.2 (hanno già incantesimi conosciuti dalla creazione) e per il Ranger a partire dal
       level-up verso il Lv.3 (i suoi primi incantesimi arrivano solo al level-up verso il Lv.2 tramite lo step
       SPELL_LEARN esistente — al Lv.2 stesso non avrebbe ancora nulla da scambiare). Soglie in un piccolo dict
       `_SWAP_MIN_LEVEL` — stessa categoria delle altre tabelle numeriche universali del modulo (ASI_LEVELS, ecc.),
       non testo/nomi. `data={"max_level": ...}` riusa `_max_spell_level_for()`, già esistente e già verificato per
       SPELL_LEARN.
     - **`ui/views/character_sheet/profilo_tab.py`**: nuovo ramo `elif step.step_type == StepType.SPELL_SWAP` nel
       costruttore del dialog di level-up. A differenza di SPELL_LEARN, questa scelta è **sempre opzionale** —
       checkbox "Sostituisci un incantesimo conosciuto" (default spenta) che abilita/disabilita 2 dropdown:
       "Incantesimo da sostituire" (popolato dagli incantesimi attualmente conosciuti dal personaggio) e "Nuovo
       incantesimo" (popolato dalla lista della classe, livello ≤ slot posseduti, esclusi tutti i conosciuti tranne
       quello selezionato per la rimozione — si aggiorna dal vivo quando cambia la selezione in "da sostituire").
       **Filtro corretto sul pool "da sostituire"**: include solo gli incantesimi che appartengono davvero alla
       lista della classe del personaggio (`s.get("name") in {nomi della lista di classe}`) — esclude sia i
       trucchetti (che non hanno slot, quindi non sono "sostituibili" secondo il testo del manuale) sia eventuali
       incantesimi ottenuti dal Bardo tramite Segreti Magici ("da qualsiasi classe", non "da bardo" — il manuale
       specifica esplicitamente che il nuovo incantesimo sostitutivo deve provenire "dalla lista degli incantesimi
       da [classe]"). Se il personaggio non ha ancora nessun incantesimo di classe sostituibile, la checkbox viene
       disabilitata con etichetta esplicita invece di mostrare un form vuoto e ingannevole.
     - **Validazione**: opzionale per costruzione — se la checkbox resta spenta, nessun controllo. Se accesa,
       entrambi i dropdown diventano obbligatori (stesso pattern di errore collettivo già usato per
       ASI/SPELL_LEARN/Segreti Magici/Metamagia/Suppliche Occulte).
     - **Salvataggio**: `character_repo.remove_known_spell(character_id, nome_vecchio, livello_vecchio)` (funzione
       già esistente, mai usata prima per questo scopo) seguita da `_save_known_spell(nome_nuovo, ...)` (stesso
       helper già usato per SPELL_LEARN/Segreti Magici) — il livello dell'incantesimo da rimuovere viene riletto
       dal DB al momento del salvataggio (non dalla selezione UI), per essere certi di cancellare la riga esatta
       anche se qualcos'altro fosse cambiato nel frattempo.
  - **Verificato**: `get_level_up_steps()` testato su tutte le 12 classi × livelli 2-20 (nessuna eccezione);
    confermato che SPELL_SWAP compare per Bardo/Stregone/Warlock dal Lv.2, per il Ranger solo dal Lv.3 (Lv.2
    correttamente escluso), mai per le altre 8 classi; `max_level` del `data` dello step confermato coerente con
    `_max_spell_level_for()` (es. Stregone Lv.5 → 3°, già verificato altrove). Test end-to-end (DB temporaneo
    isolato, mai quello reale) sul ciclo completo remove+upsert: uno Stregone con 2 incantesimi conosciuti, dopo lo
    scambio di uno dei due, risulta con lo stesso conteggio totale (2), il vecchio nome assente e il nuovo
    presente, l'altro incantesimo non toccato. Verificato separatamente il filtro Segreti Magici: un Bardo con un
    incantesimo normale + un incantesimo da Segreti Magici (preso dalla lista Mago) ha SOLO il primo nel pool "da
    sostituire" — il secondo, pur essendo `known_spell`, non appartiene alla lista incantesimi del Bardo e viene
    correttamente escluso. `py_compile`/`pyflakes` puliti su `core/level_manager.py` e
    `ui/views/character_sheet/profilo_tab.py` (solo il rumore preesistente di `from config.settings import *`,
    nessun errore genuino).
- **Fix Mistificatore Arcano (Ladro)/Cavaliere Mistico (Guerriero) — casting "preso in prestito dal Mago"
  (2026-07-15)** — bug report di Davide: "Il mistificatore arcano non riesce a visualizzare gli incantesimi,
  tantomeno glieli fa scegliere". Confermato che era il gap architetturale già segnalato come TODO (Audit Level-Up
  Phase 3, 2026-07-10): tutto il sistema incantesimi (`spells_view.py`, `auto_init_spell_slots()`,
  `core/level_manager.py`, i picker di creazione) è agganciato esclusivamente a `character.class_name` — Ladro e
  Guerriero hanno `spellcasting_ability: null` a livello di classe base, quindi non scattava mai nulla, nonostante
  entrambe le sottoclassi abbiano già `spell_progression` completo e verificato nei rispettivi JSON. Chiesto a
  Davide se estendere il fix anche al Cavaliere Mistico (stessa identica architettura) — confermato esplicitamente
  ("Entrambe le sottoclassi").
  - **Testo delle 2 feature "Incantesimi" letto per intero e confrontato riga per riga** (non solo la tabella
    `spell_progression`, già verificata nell'audit del 2026-07-10): entrambe concedono trucchetti (Ladro: Mano
    Magica fissa + 2 a scelta, +1 al lv10 = 4 totali; Guerriero: 2 a scelta, +1 al lv10 = 3 totali, nessun
    trucchetto fisso) e incantesimi conosciuti (identica progressione numerica per livello in entrambe:
    3,4,4,4,5,6,6,7,8,8,9,10,10,11,11,11,12,13 da lv3 a lv20), con 2 dei 3 incantesimi iniziali (lv3) vincolati a 2
    scuole specifiche (Ladro: Ammaliamento/Illusione; Guerriero: Abiurazione/Invocazione) e il 3° libero da
    vincolo, e i pick dell'8°/14°/20° livello sempre liberi da vincolo di scuola in entrambe. **Asimmetria reale
    confermata leggendo le due frasi due volte, non un refuso di trascrizione**: la clausola di sostituzione (ogni
    level-up si può scambiare un incantesimo conosciuto con un altro) è libera da vincolo di scuola per il Ladro
    solo se si sostituisce l'incantesimo dell'8°/14°/20° livello, mentre per il **Guerriero il testo include
    esplicitamente anche il 3° livello** tra le origini libere ("a meno che non stia sostituendo l'incantesimo
    ottenuto al 3°, 8°, 14° o 20° livello", contro "all'8°, 14° o 20° livello" del Ladro) — coerente con la
    struttura interna di ciascun testo: per entrambe le sottoclassi, UNO dei 3 incantesimi scelti al lv3 è già un
    pick "libero" per definizione (il terzo, non vincolato), ma solo il testo del Cavaliere Mistico dichiara
    esplicitamente che quella specifica "postazione" resta libera da vincolo anche per una futura sostituzione.
  - **Design discusso con Davide prima di scrivere codice** (`AskUserQuestion`): confermato il piano completo (non
    la versione ridotta senza sostituzione), inclusa una nuova colonna DB per tracciare quali incantesimi
    conosciuti sono "liberi da vincolo di scuola" — necessaria perché, senza di essa, non c'è modo di sapere a una
    futura sostituzione se il rimpiazzo può essere di qualsiasi scuola o resta vincolato.
  - **JSON** (`ladro.json`/`guerriero.json`, blocchi sottoclasse Mistificatore Arcano/Cavaliere Mistico) — 3 campi
    aggiunti, tutti strutturano prosa già presente nel testo della feature, nessun dato inventato:
    `"fixed_cantrip"` ("Mano Magica" solo per il Ladro, `null` per il Guerriero), `"restricted_schools"` (le 2
    scuole vincolate), `"unrestricted_origin_levels"` (i livelli il cui incantesimo è libero da vincolo anche per
    una futura sostituzione — `[8,14,20]` Ladro, `[3,8,14,20]` Guerriero, l'asimmetria sopra resa esplicita nel
    dato invece che in un `if` nascosto nel codice Python).
  - **`known_spells.origin_unrestricted`** (nuova colonna, `INTEGER DEFAULT 0`, stessa convenzione booleana di
    `is_prepared`) — aggiunta via `_add_column()` idempotente in `data/database.py`; nuovo campo
    `KnownSpell.origin_unrestricted: bool = False` in `data/models.py`; `get_known_spells()`/`upsert_known_spell()`
    in `character_repo.py` estese per leggerla/scriverla (default `False` per ogni altra chiamata esistente, zero
    impatto sulle altre 12 classi). Traccia se quella specifica riga è un pick "libero da vincolo di scuola" —
    impostata `True` solo per i pick dell'8°/14°/20° livello (entrambe le sottoclassi) e in più per il pick libero
    del 3° livello nel caso del Cavaliere Mistico.
  - **`GameDataLoader`** (`data/game_data/game_data_loader.py`) — 4 nuovi metodi, tutti a sola lettura dai JSON:
    `get_subclass_data()` (generico, cerca una sottoclasse per nome esatto),
    `get_borrowed_caster_subclass_name(class_name)` (rileva quale sottoclasse di una classe ha `spell_progression`,
    evita di duplicare in UI una mappa classe→sottoclasse scritta a mano), `get_borrowed_caster_data(class_name,
    subclass_name)` (il blocco sottoclasse completo, o `None` per qualunque altra combinazione),
    `get_borrowed_caster_progression_for_level(class_name, subclass_name, level)` (la riga di `spell_progression`
    per il livello indicato, con fallback all'ultima riga ≤ level).
  - **`character_repo.py`** — 2 nuove funzioni, entrambe no-op sicure per le 12 classi già funzionanti:
    - `init_borrowed_caster_slots(character_id, class_name, subclass, level)` — percorso di inizializzazione slot
      incantesimo completamente indipendente da `auto_init_spell_slots()` (che legge `caster_type` da
      `game_data.get_caster_type(class_name)`, sempre vuoto per Ladro/Guerriero) — legge `spell_progression.slots`
      per il livello indicato, stesso pattern UPDATE/clamp di `auto_init_spell_slots`.
    - `sync_borrowed_spellcasting_ability(character)` — imposta `character.spellcasting_ability` a `"int"` (letto
      dal JSON di sottoclasse, mai hardcoded) quando la sottoclasse concede casting; no-op immediato se la classe
      base ha già una propria `spellcasting_ability` (non tocca mai un incantatore vero); riporta a `""` se il
      personaggio non ha (più) una delle 2 sottoclassi gestite.
  - **`core/level_manager.py`** — 3 nuovi `StepType`: `BORROWED_CANTRIP`, `BORROWED_SPELL_LEARN`,
    `BORROWED_SPELL_SWAP`. **Decisione di design**: l'apprendimento INIZIALE (3° livello, contestuale alla scelta
    della sottoclasse) NON passa da questi step — `get_level_up_steps()` riceve sempre il valore GIA' persistito di
    `c.subclass` (vuoto al 3° livello, la sottoclasse non è ancora stata scelta in quel momento), esattamente lo
    stesso limite già presente in questo file per stile di combattimento/totem/terreno (verificato leggendo il
    codice: nessuno di questi ha mai `on_select` sul dropdown sottoclasse, quindi il loro effettivo trigger su
    `new_level` coincidente con `subclass_choice_level` non può mai scattare — **bug latente pre-esistente, non
    introdotto ora e non corretto in questo fix, fuori scope**, la fix di questa sessione non riusa quel pattern
    proprio per non ereditare lo stesso difetto). L'apprendimento iniziale è quindi gestito direttamente in
    `profilo_tab.py` insieme al dropdown `SUBCLASS_CHOICE` (vedi sotto); questi 3 step coprono solo la crescita dal
    4° livello in poi, quando `c.subclass` è già noto e affidabile. Dati (delta cantrip/spell, scuole vincolate,
    livelli liberi) letti sempre da `spell_progression`/i 3 nuovi campi JSON, mai ricalcolati a mano.
  - **`ui/views/character_sheet/profilo_tab.py`**:
    - **Apprendimento iniziale (Lv.3)**: nuovo blocco dentro il ramo `SUBCLASS_CHOICE`, con **reattività live**
      (`_sc_dd.on_select`) che mostra/nasconde un container di widget in base al valore corrente del dropdown
      sottoclasse — necessaria perché, a differenza di totem/terreno/stile di combattimento, qui la scelta va fatta
      nello STESSO level-up in cui si sceglie la sottoclasse, non in uno successivo. Contiene: N dropdown
      trucchetto (pool = `cantrip_options` meno il fisso, mutua esclusione tra loro), 2 dropdown incantesimo
      vincolati alla scuola + 1 libero (mutua esclusione tra tutti e 3). Validazione/salvataggio condizionati al
      valore FINALE del dropdown sottoclasse letto a fine dialog (non alla sola visibilità del container), quindi
      corretti anche se il giocatore cambia idea più volte prima di confermare.
    - **Crescita Lv.4+**: 3 nuovi rami nel loop principale
      (`BORROWED_CANTRIP`/`BORROWED_SPELL_LEARN`/`BORROWED_SPELL_SWAP`), stesso identico stile di
      `CANTRIP_LEARN`/`SPELL_LEARN`/`SPELL_SWAP` ma con pool sempre da `_loader.get_spells("Mago")` filtrato per
      scuola tramite un nuovo helper `_borrowed_eligible_mago_spells()`. Per lo scambio, il vincolo di scuola del
      rimpiazzo dipende dal flag `origin_unrestricted` della riga sostituita (letto da `known_spells`), non dal
      livello corrente — se si sostituisce un pick "libero", il rimpiazzo può essere di qualsiasi scuola, e il flag
      si propaga sulla nuova riga (la "postazione" resta libera anche in futuro).
    - **`_save_known_spell()`** esteso con un nuovo parametro opzionale `origin_unrestricted: bool = False`
      (propagato a `upsert_known_spell()`), default identico al comportamento precedente per tutte le chiamate
      esistenti (Bardo/Stregone/Warlock/Ranger/Segreti Magici — mai impostato).
    - **Trucchetto fisso salvato comunque**: bug trovato durante il primo giro di test end-to-end (non nella
      richiesta originale) — il trucchetto fisso del Ladro (Mano Magica) non veniva mai salvato come `known_spell`
      perché non passa da nessun dropdown (è automatico, non una scelta) — un Mistificatore Arcano non avrebbe mai
      visto Mano Magica nella propria lista incantesimi nonostante la possieda per regolamento. Fix: salvato
      incondizionatamente (se presente) insieme ai trucchetti scelti, stesso `_save_known_spell()`.
    - **`do_level_up`/`do_level_down`**: aggiunte le chiamate a
      `sync_borrowed_spellcasting_ability()`/`init_borrowed_caster_slots()` accanto a
      `auto_init_spell_slots()`/`init_class_resources()` già esistenti — no-op per qualunque altra
      classe/sottoclasse, quindi zero rischio per le 12 classi già funzionanti.
  - **`ui/views/spells_view.py`**: il placeholder "Nessun incantesimo per {classe}" era fuorviante per queste 2
    sottoclassi (che hanno regolarmente accesso a incantesimi, solo non tramite una lista di classe propria —
    `_class_spells` resta sempre vuota per Ladro/Guerriero) — soppresso quando `character.spellcasting_ability` è
    valorizzata ma `_class_spells` è vuota (condizione che, per costruzione, si verifica solo per queste 2
    sottoclassi: ogni classe con una propria lista ha sempre `spellcasting_ability` + `_class_spells` non vuota
    insieme). I loro incantesimi compaiono nel meccanismo "Incantesimi Extra" già esistente (lo stesso usato per i
    Segreti Magici del Bardo, che legge `known_spells` non presenti in `_class_spells` — **nessuna modifica
    strutturale necessaria a quel meccanismo**, già generico), con una nuova etichetta di sezione dedicata
    "Incantesimi da Mago" invece del generico "Incantesimi Extra".
  - **Verificato**: `get_level_up_steps()` ri-testato su tutte le 12 classi × tutte le sottoclassi reali × livelli
    2-20 dopo il fix — 0 eccezioni, nessuna regressione. Test end-to-end dedicato (DB temporaneo isolato, mai
    quello reale, `HOME` di test separato) per entrambe le sottoclassi dal Lv.3 al Lv.20: `spellcasting_ability`
    risulta `"int"` dopo `sync_borrowed_spellcasting_ability()`; gli slot incantesimo ad ogni livello combaciano
    esattamente con `spell_progression.slots` (verificato Lv.3 e Lv.20 nel dettaglio, es. Lv.20 `{1:4,2:3,3:3,4:1}`
    per entrambe); il conteggio finale di trucchetti/incantesimi conosciuti a Lv.20 combacia esattamente con
    `cantrips_known`/`spells_known` della tabella (Ladro: 4 trucchetti incluso Mano Magica, 13 incantesimi;
    Guerriero: 3 trucchetti, 13 incantesimi); l'asimmetria del flag `origin_unrestricted` confermata nel test — al
    Lv.3, il Ladro salva 0 pick "liberi da vincolo per lo scambio" mentre il Guerriero ne salva 1 (il pick libero
    iniziale), coerente con `3 in unrestricted_origin_levels`; test dedicato dello scambio (rimozione +
    reinserimento con propagazione del flag) confermato corretto. `py_compile`/`pyflakes` puliti su tutti i file
    toccati (`data/database.py`, `data/models.py`, `data/repositories/character_repo.py`,
    `data/game_data/game_data_loader.py`, `core/level_manager.py`, `ui/views/character_sheet/profilo_tab.py`,
    `ui/views/spells_view.py`, più i 2 file JSON — solo il rumore preesistente di `from config.settings import *`,
    nessun errore genuino).
  - **Non affrontato in questo fix, fuori scope**: il bug latente di totem/terreno/stile di combattimento descritto
    sopra (nessuna reattività sul dropdown sottoclasse, quindi quelle scelte non possono mai scattare esattamente
    al livello in cui si sceglie la sottoclasse) — scoperto incidentalmente analizzando il codice esistente per
    capire come replicare il pattern, non introdotto né corretto da questa sessione; segnalato qui per una futura
    sessione dedicata, dato che tocca 3 meccaniche già in produzione e richiede più test di regressione di quanti
    ne giustifichi un fix "en passant".
- **Fix strumenti di CLASSE mai salvati alla creazione (scelte E fisse) — Bardo/Monaco/Ladro/Druido (2026-07-15)**
  — bug report di Davide: "uno strumento a scelta per il bardo non permette di scegliere lo strumento nella
  creazione manuale". Analisi: `bardo.json → tool_proficiencies` è
  `[{"type":"choice","count":3,"from":"strumenti_musicali"}]` (3 strumenti musicali a scelta) — struttura identica,
  campo per campo, alla scelta strumenti di BACKGROUND già funzionante (`_bg_tool_choices()` in
  `manual_form.py`/`wizard_view.py`), ma nessuno dei due file leggeva mai `tool_proficiencies` dal lato CLASSE:
  entrambi filtravano solo `bg_data.get("tool_proficiencies", [])`, mai `cls_data.get("tool_proficiencies", [])`
  (confermato via grep: zero occorrenze in entrambi i file). **Scope ampliato oltre la sola richiesta di Davide,
  stessa causa radice**: la scansione di tutti i 12 JSON classe ha rivelato che il bug non è specifico del "tipo
  scelta" ma di QUALUNQUE `tool_proficiencies` di classe, incluse le competenze FISSE (stringhe pure, non dict
  `{"type":"choice"}`) — Ladro `"Arnesi da Scasso"` e Druido `"Borsa da Erborista"` non venivano MAI salvate alla
  creazione di un personaggio di quelle classi (né nel wizard né nel form manuale), un gap silenzioso mai segnalato
  prima perché non produce un errore visibile, solo una competenza mancante. Anche Monaco ha lo stesso pattern di
  scelta di Bardo: `[{"type":"choice","count":1,"from":"strumenti_artigiani_o_musicali"}]` (1 strumento artigiano O
  musicale). Verificato che `GameDataLoader.get_tool_categories()` espone già correttamente entrambe le chiavi
  categoria necessarie (`"strumenti_musicali"`, `"strumenti_artigiani_o_musicali"` — quest'ultima già costruita
  come unione artigiani+musicali) con i nomi giusti da `equipment/tools.json`: nessuna modifica al dato o al loader
  necessaria, gap puramente di wiring UI/salvataggio.
  - **Fix, identico in `manual_form.py` e `wizard_view.py`**: nuovo `_class_tool_choices()` (mirror esatto di
    `_bg_tool_choices()`, ma legge `cls_data = _loader.get_class(self._review_class)` invece di `bg_data`). Nuovo
    stato `self._review_class_tools: list[str] = []`, azzerato al cambio classe (`_on_class_change`). **Differenza
    strutturale rispetto alle scelte di background**: tutti i 13 background esistenti hanno sempre `count=1` per
    ogni entry di scelta strumento (un solo dropdown), ma la classe può chiedere N strumenti dalla STESSA categoria
    nella stessa entry (Bardo: `count=3`) — un singolo dropdown non basta. Implementato in
    `_rebuild_lang_tool_col()` un rendering a N dropdown con **esclusione reciproca** (stesso pattern già usato per
    i trucchetti Lv.1 in `_rebuild_spells_init_col()`, mai per un semplice "singolo dropdown per entry" come i
    background): `_refresh_class_tool_group()`/`_set_class_tool()` ricalcolano le opzioni disponibili di ogni
    dropdown del gruppo escludendo i valori già scelti negli ALTRI dropdown dello stesso gruppo (mai il proprio),
    con un offset cumulativo per gestire correttamente eventuali più entry di scelta nello stesso JSON classe
    (nessuna classe attuale ne ha più di una, ma il codice non assume che resti sempre così). Dropdown sempre
    pre-popolati con un default valido (stesso principio "sempre validi" già documentato per gli altri dropdown di
    questa fase) — nessuna nuova validazione bloccante necessaria in
    `_scelte_validation_error()`/`_review_validation_error()`.
  - **Bug aggiuntivo scoperto solo in `wizard_view.py`, non presente in `manual_form.py`**: `_on_class_change()`
    non richiamava mai `_rebuild_lang_tool_col()` (lo fa solo `_on_race_change()`/`_on_bg_change()`) — innocuo
    finché quella funzione dipendeva solo da `self._review_bg` (background, non toccato da un cambio classe), ma
    ora che `_class_tool_choices()` dipende da `self._review_class`, cambiare classe nella stessa schermata
    "Revisione" senza questo fix avrebbe lasciato i vecchi dropdown strumento-di-classe della classe precedente.
    **`manual_form.py` non soffre di questo problema**: la classe si sceglie nella fase "Identità" (fase 1),
    separata dalla fase "Scelte" dove vive `_rebuild_lang_tool_col()` — a quel punto la classe è già definitiva,
    nessun cambio classe possibile nella stessa schermata. Fix: aggiunta chiamata a `_rebuild_lang_tool_col()` in
    `_on_class_change()` di `wizard_view.py`.
  - **Salvataggio** (`_on_save`, identico in entrambi i file): la sezione "Strumenti" ora salva, in ordine con
    deduplica (`tool_seen`): strumenti scelti da background (`_review_tools`) → strumenti scelti di classe
    (`_review_class_tools`, NUOVO) → strumenti fissi da background (stringhe pure in
    `bg_data.get("tool_proficiencies")`, comportamento preesistente) → **strumenti fissi di classe** (stringhe pure
    in `cls_data.get("tool_proficiencies")`, NUOVO — questo è il fix per Ladro/Druido).
  - **Verificato**: `py_compile`/`pyflakes` puliti su entrambi i file (solo il rumore preesistente di `from
    config.settings import *`). Test end-to-end dedicato: `_class_tool_choices()` bypassando `__init__` (mai un
    vero Flet Page) conferma `(3, [10 strumenti musicali])` per Bardo, `(1, [27 strumenti artigiano+musicali])` per
    Monaco, `[]` per Ladro/Guerriero/Mago (nessuna scelta, solo eventuali fisse) — identico in entrambi i file.
    Test end-to-end con DB temporaneo isolato (mai quello reale, `HOME` di test separato) sulla logica di
    salvataggio: Bardo con 3 strumenti scelti (Liuto/Tamburo/Corno) → tutti e 3 salvati come
    `proficiency_type="tool"`; Monaco con 1 scelto (Strumenti da Falegname) → salvato; **Ladro senza alcuna
    scelta** → "Arnesi da Scasso" ora comunque presente (prima assente); **Druido senza alcuna scelta** → "Borsa da
    Erborista" ora comunque presente (prima assente); caso con sovrapposizione di nomi tra scelte diverse → nessuna
    riga duplicata (dedupe via `tool_seen` confermato). Non verificato con un vero client Flet (l'algoritmo di
    esclusione reciproca a N dropdown vive dentro una closure nested non richiamabile senza costruire l'intera fase
    UI) — la correttezza è per costruzione, essendo una copia strutturale 1:1 dell'algoritmo di esclusione già
    usato e verificato per i trucchetti Lv.1 (stesso schema slot/offset/refresh, solo rinominato per gli
    strumenti), non un algoritmo nuovo.

- **Sessione di 9 richieste (2026-07-16) — abilità custom, incantesimi bonus/sempre pronti, descrizioni prima della
  scelta, campi editabili, autofill arma/armatura, level up/down più visibili, HP temporanei diretti.** Bug
  report/richiesta di Davide, testo verbatim:
  > "Aggiungere sia nella sezione esplorazione, sia nella sezione combattimento abilità speciali (nella sezione
  > esplorazione sono abilità speciali di esplorazione e in quella di combattimento abilità speciali di
  > combattimento) sono praticamente abilità custom magari date dal master. Permettere a tutte le classi di
  > aggiungere un incantesimo, per esempio una sezione incantesimi bonus e il player può scegliere tra tutti gli
  > incantesimi e aggiungerli a quelli conosciuti o preparati. scelta incantesimi con descrizione. Quando si sale
  > di livello il player deve riuscire a vedere la descrizione degli incantesimi che sta per scegliere. La stessa
  > cosa per le suppliche occulte e per tutte le scelte del player in cui deve scegliere incantesimi abilità o
  > altro che sono complesse e hanno una descrizione (quindi anche i trucchetti). rendiamo modificabili anche i
  > campi che non si possono modificare attualmente, come le scelte di classe in profilo, Risorse di classe e
  > abilità di classe e tratti di razza in combattimento, sensi e velocità percezione passiva, Il peso in
  > inventario. quando un player aggiunge un arma può scegliere dalla tendina il tipo di arma... la scheda viene
  > autoriempita con le caratteristiche di quel tipo di arma e poi può modificare i campi a suo piacimento... fare
  > la stessa cosa con la sezione armature. rendere più visibili i pulsanti di level up e level down. Mancano
  > incantesimi sempre preparati per esempio per il paladino mancano gli incantesimi del giuramento sempre pronti.
  > Per esempio quelli del Giuramento degli antichi: Liv 3 colpo intrappolate, parlare con gli animali. Liv 5
  > bagliore lunare e passo velato ecc. Bisogna controllare tutte le classi e le sottoclassi che hanno questa
  > feature. poter aggiungere hp temporanei cliccando direttamente su hp temporanei senza cliccare sulla matita del
  > modifica che usiamo anche per la vita."

  Regola trasversale confermata da Davide prima di iniziare e valida per tutta questa sessione: "se non ti
  specifico che una modifica è solo per web o solo per app la applichi a tutti" — nessuna delle modifiche seguenti
  è mai stata ristretta a una sola piattaforma (nessuna di queste tocca `page.web`/FilePicker, quindi ricade
  automaticamente in entrambe).

  1. **Abilità Speciali custom (Esplorazione + Combattimento)** — nuova tabella `custom_abilities` (`category:
     "esplorazione"|"combattimento"`, `name`, `description`), CRUD completo (`get_custom_abilities`,
     `create_custom_ability`, `update_custom_ability`, `delete_custom_ability`) in `character_repo.py`, nuovo
     dataclass `CustomAbility` in `data/models.py`. Sezione dedicata in entrambi i tab
     (`esplorazione_tab.py`/`combattimento_tab.py`): header con "+ Aggiungi", card con nome/descrizione/pulsanti
     modifica/elimina, dialog crea/modifica, dialog conferma eliminazione. Puramente additivo — non tocca mai il
     testo ufficiale di feature/tratti già presenti nei JSON. Verificato con test end-to-end (DB temporaneo
     isolato): isolamento per categoria (un'abilità "combattimento" non compare in "esplorazione" e viceversa),
     CRUD completo, cascade-delete col personaggio.
  2. **Incantesimi Bonus per tutte le classi** — nuova sezione "Incantesimi Bonus" in `spells_view.py`, **sempre
     visibile** (anche per classi senza `spellcasting_ability`, es. un Guerriero senza Cavaliere Mistico), con
     pulsante "+ Aggiungi Incantesimo Bonus" che apre un picker a due livelli: dropdown "Lista incantesimi"
     (`GameDataLoader.get_spellcasting_class_names()`, nuovo metodo — calcola dinamicamente quali classi hanno un
     file `spells/incantesimi_*.json` non vuoto, niente hardcoded) → dropdown "Incantesimo" (tutti gli incantesimi
     di quella lista, trucchetti inclusi). Salvato come `known_spell(is_prepared=True, is_bonus=True,
     class_list=<classe scelta>)`. Nuova colonna `known_spells.is_bonus` (booleana) per distinguerlo dal meccanismo
     "extra" già esistente (Segreti Magici/Mistificatore) — necessario perché un incantesimo bonus scelto dalla
     STESSA lista della classe del personaggio andrebbe altrimenti confuso con uno normale già preparato. Sezione
     con lista per livello e pulsante di rimozione dedicato (a differenza dei Segreti Magici, un incantesimo bonus
     non ha una meccanica di sostituzione al level-up: rimovibile liberamente). Placeholder "Nessun incantesimo per
     {classe}" riformulato per non essere fuorviante quando esistono solo incantesimi bonus. Verificato con test
     end-to-end: Guerriero non-incantatore che aggiunge un trucchetto da Mago (compare, rimuovibile); Chierico che
     aggiunge un incantesimo dalla propria stessa lista (distinto correttamente dai normali preparati via
     `is_bonus`); placeholder soppresso correttamente in presenza di un bonus.
  3. **Descrizione prima di scegliere (incantesimi/trucchetti/talenti/suppliche occulte/metamagia/dono del
     patto/stile di combattimento)** — nuovo modulo condiviso `ui/widgets.py`: `dropdown_with_info(page_getter,
     dropdown, describe)` affianca un'icona ⓘ a un `ft.Dropdown` già costruito, che apre un `AlertDialog` con la
     descrizione dell'opzione **correntemente selezionata** (rilegge `dropdown.value` al momento del click, non uno
     snapshot preso alla creazione — cambia selezione, cambia descrizione). Formatter puri (nessuna dipendenza
     Flet) per ogni tipo di dato già nel progetto: `format_spell_body()`/`make_spell_describe()`
     (incantesimi/trucchetti), `format_feat_body()`/`make_feat_describe()` (talenti, gestisce sia bonus fisso sia
     `choose_one`), `format_invocation_body()`/`make_invocation_describe()` (Suppliche Occulte),
     `format_named_option_body()`/`make_named_option_describe()` (Metamagia/Dono del Patto/Stile di Combattimento —
     opzioni semplici `{"name","description"}`). Per i controlli non-Dropdown (Checkbox delle Suppliche
     Occulte/Metamagia, RadioGroup del Dono del Patto) un'icona ⓘ standalone per-opzione (`_make_info_icon()` in
     `profilo_tab.py`) accanto a ciascun controllo, stesso comportamento. Nuovi getter di sola lettura in
     `GameDataLoader`: `get_metamagic_option_data()`/`get_pact_boon_data()` (ritornano i dict completi
     `{"name","description"}` invece dei soli nomi, senza scartare più la descrizione come le vecchie
     `get_metamagic_options()`/`get_pact_boons()`, mantenute per compatibilità e ora implementate sopra le nuove),
     `get_fighting_style_data(class_name)` (Guerriero legge `fighting_style_details` proprio; Paladino/Ranger
     risolvono i nomi delle proprie `options` contro la lista canonica del Guerriero, unica fonte con la
     descrizione completa). Applicato in **creazione** (`wizard_view.py`/`manual_form.py`: trucchetti/incantesimi
     iniziali, trucchetto Alto Elfo) e nel **level-up** (`profilo_tab.py`: SPELL_LEARN sia per le classi "know" sia
     per il picker custom dei Segreti Magici, SPELL_SWAP, CANTRIP_LEARN,
     BORROWED_CANTRIP/BORROWED_SPELL_LEARN/BORROWED_SPELL_SWAP, talento nell'ASI, Metamagia, Suppliche Occulte,
     Dono del Patto, Stile di Combattimento Paladino/Ranger). Verificato con test end-to-end (dialog costruiti per
     Stregone/Warlock/Guerriero/Paladino/Ranger/Bardo/Ladro/Barbaro a vari livelli, ogni icona ⓘ trovata
     nell'albero controlli cliccata programmaticamente): 0 eccezioni, ogni click apre correttamente un dialog con
     la descrizione dell'opzione corrente.
  4. **Campi resi editabili**:
     - *Scelte di classe in Profilo* (Stile di Combattimento/Animale Totem/Terreno del Circolo/Discendenza
       Draconica) — dialog "✎ Modifica" dedicato in `profilo_tab.py`, dropdown pre-popolati dai getter
       `GameDataLoader` già esistenti, salvataggio diretto su `Character` (additivo, non tocca la logica di
       level-up che li assegna la prima volta).
     - *Risorse di classe/Abilità di classe/Tratti di razza in Combattimento* — le prime tramite un nuovo bonus
       additivo (`class_resources.max_value_bonus`, vedi punto architetturale sotto); le seconde due tramite le
       sezioni "Abilità Speciali" (punto 1) invece di editing in-place del testo ufficiale PHB (scelta di design:
       mai modificare la fonte di verità del manuale, solo aggiungere).
     - *Sensi/Velocità/Percezione Passiva in Esplorazione* — due nuove colonne
       `characters.passive_perception_override`/nessuna nuova colonna per la velocità (riusa `characters.speed` già
       esistente tramite `character_repo.update_speed()`). Sezione "Percezione" e riga "Camminata" rese cliccabili
       (`_editable_info_row()`), dialog con TextField, "Ripristina calcolato" torna al valore PHB (0 = nessun
       override).
     - *Peso in Inventario* — nuova colonna `characters.carry_capacity_override` (REAL, 0 = usa la formula FOR × 7,5 kg), sezione Peso cliccabile, dialog con reset alla formula.
     Tutti e 3 gli override seguono lo stesso pattern già consolidato nel progetto per
     `proficiency_bonus_override`/`max_prepared_spells_override`: 0 = "nessun override, usa la formula PHB", mai un
     valore magico diverso da zero per "disattivato".
  5. **Autofill Arma/Armatura da catalogo PHB** — nuovo dropdown "Tipo (autoriempi da catalogo PHB)" in cima ai
     dialog Nuova/Modifica Arma e Nuova/Modifica Armatura di `inventario_tab.py`, popolato da
     `GameDataLoader.get_weapon_names()`/il nuovo `get_armor_names()` (mirror di `get_weapon_names()`, itera tutte
     e 4 le liste di `equipment/armor.json`). Alla selezione, autoriempie i campi del form dai dati del catalogo
     (dado danno, tipo danno, proprietà, gittata/Versatile per le armi; CA, tipo armatura, peso per le armature) —
     **tutti i campi restano comunque modificabili dopo**, come richiesto esplicitamente. Traduzione dati non
     banale: `_map_catalog_damage_type()`/`_JSON_DAMAGE_TYPE_TO_UI` converte i valori minuscoli plurali del JSON
     ("taglienti") nelle etichette singolari maiuscole della UI ("Taglio"); `_resolve_catalog_weapon_properties()`
     estrae con regex i valori tra parentesi delle proprietà (es. "Versatile (1d10)" → dado a due mani, "Munizioni
     (gittata 24/96)" → range_normal/range_max) usando arrotondamento round-half-up (`int(x + 0.5)`, non `round()`
     che tronca 4,5→4 per via del banker's rounding di Python) per le gittate frazionarie in metri (es. Rete:
     1,5/4,5 m). Gestito il caso dati `None` (`dict.get(key, default)` NON copre un valore esplicitamente `None`
     nel JSON, es. la Rete ha `damage_dice: null` — serve `data.get(key) or default`). Verificato contro l'intero
     catalogo reale (37 armi, 13 armature/scudi): zero tipi danno/proprietà non mappati.
  6. **Pulsanti level up/down più visibili** — stile aggiornato in `profilo_tab.py` (colori/contrasto/dimensione), nessuna modifica funzionale.
  7. **Incantesimi sempre pronti da Dominio/Giuramento/Circolo della Terra** — esempio esatto di Davide verificato
     letteralmente: Paladino Giuramento degli Antichi Lv.3 → Colpo Intrappolante/Parlare con gli Animali, Lv.5 →
     Bagliore Lunare/Passo Velato (dati già presenti e verificati in `paladino.json → subclasses[].bonus_spells`,
     mai wired a nessuna logica prima d'ora). Stessa struttura dati già presente e verificata anche per
     `chierico.json` (tutti e 6 i domini, soglie 1/3/5/7/9) e per `druido.json → subclasses[Circolo della
     Terra].circle_spells` (annidato per terreno, poi per soglia 3/5/7/9 — filtrato per `character.land_terrain`).
     Nessun nuovo audit manuale necessario, solo wiring di dati già corretti. Nuova funzione
     `character_repo.sync_bonus_domain_spells(character)`: calcola l'insieme atteso di incantesimi per la
     sottoclasse/terreno/livello attuali, li upserta come `known_spell(is_prepared=True, always_prepared=True)`, e
     ripulisce le righe `always_prepared=1` non più valide (cambio sottoclasse/terreno, level-down sotto soglia) —
     se una riga ripulita ha ANCHE `is_bonus=True` (lo stesso incantesimo scelto manualmente dal giocatore come
     bonus, punto 2), viene rimosso solo il flag `always_prepared` (nuova `_clear_always_prepared_flag()`) invece
     di cancellare l'intera riga, per non perdere la scelta del giocatore. Self-healing: richiamata ad ogni
     apertura di `SpellsView` (accanto a `sync_borrowed_spellcasting_ability`) e ad ogni
     `do_level_up`/`do_level_down` in `profilo_tab.py` (accanto a
     `init_class_resources()`/`auto_init_spell_slots()`), stesso pattern già consolidato nel progetto. Nuova
     colonna `known_spells.always_prepared`. **`spells_view.py`**: `_prepared_count()` esclude questi incantesimi
     dal tetto di preparazione giornaliera (PHB: non contano nel numero preparabile); i normali incantesimi di
     classe che coincidono per nome (es. "Cura Ferite" per un Chierico, che è sia domain spell sia incantesimo
     standard della lista) vengono esclusi dalla lista togglabile normale per non comparire due volte; nuova
     sezione dedicata "Incantesimi Sempre Pronti" (badge 🔒, nessun toggle, nessuna rimozione manuale — lo stato
     dipende solo da sottoclasse/terreno/livello). Verificato con test end-to-end che riproduce esattamente
     l'esempio di Davide (Paladino Lv.3→5→3, i 2 incantesimi extra compaiono a Lv.5 e spariscono tornando a Lv.3),
     più Chierico (cambio dominio ripulisce i vecchi) e Druido (cambio terreno ripulisce i vecchi), l'interazione
     con `is_bonus` (la riga sopravvive, solo il flag si pulisce), l'assenza di duplicazione nella UI, e
     l'applicazione automatica attraverso il vero dialog di level-up (`do_level_up` → `sync_bonus_domain_spells` →
     verificato sul DB).
  8. **HP Temporanei cliccabili direttamente** — riconfermato che il box "HP TEMP" nella sezione HP di
     `combattimento_tab.py` ha un proprio `on_click=self._on_edit_temp_hp_click` indipendente dalla matita di
     modifica HP correnti/massimi (`_on_edit_hp_click`), con dialog dedicato. Verificato con test end-to-end: click
     sul box apre un `AlertDialog` distinto, non condiviso con l'editor HP principale.
  - **Verifica finale di sessione**: `python3 -m compileall` sull'intero albero sorgente (esclusi
    `build/`/`.venv/`) — 0 errori; `pyflakes` sull'intero albero — 0 errori genuini (solo il rumore noto di `from
    config.settings import *` più un `f-string is missing placeholders` preesistente e non toccato in
    `combattimento_tab.py`, riga del dialog dadi vita, non in scope di questa sessione). Smoke test end-to-end (DB
    temporaneo isolato, mai quello reale) che instanzia
    `EsplorazioneTab`/`CombattimentoTab`/`InventarioTab`/`SpellsView` per tutte e 12 le classi PHB senza eccezioni,
    più test dedicati per ciascuno degli 8 punti sopra (CRUD abilità custom e isolamento per categoria,
    sopravvivenza del bonus risorsa di classe al re-sync incluso il sentinel "illimitato" del Lv.20 Barbaro,
    disponibilità del catalogo armi/armature, handler HP temporanei dedicato).

- **Follow-up alla sessione di 9 richieste — bug "Unknown control: FilePicker" anche su desktop nativo + pulsanti
  level up/down ridimensionati (2026-07-16, stesso giorno)** — Davide ha inviato uno screenshot dell'app avviata
  `python main.py` da terminale (macOS, non web/Docker), con un banner rosso "Unknown control: FilePicker"
  sovrapposto al tab Profilo, e il messaggio (verbatim): "avviata da terminale mi dà questo errore, i tasti level
  up e down li volevo più visibili ma così è troppo." Due segnalazioni distinte, entrambe risolte:
  1. **Bug FilePicker su desktop nativo** — a prima vista sembrava una ricomparsa del bug web già ampiamente
     documentato sopra (2026-07-12, tre tentativi), ma quel bug era stato diagnosticato e confermato SOLO per
     `page.web == True`; Davide qui riportava un lancio nativo da terminale, non un deploy Docker/browser. **Causa
     radice reale**: `did_mount()` in `profilo_tab.py` e `maps_view.py` registrava `ft.FilePicker()` in
     `page.overlay` con la condizione `not self._page.web` — cioè "ovunque tranne il web", desktop incluso. Ma la
     primissima regola scritta in cima a questo stesso file, presente da PRIMA di questa sessione (sezione "Regole
     Critiche: API Flet 0.85.3" → "FILE PICKER"), dice esplicitamente: **"ft.FilePicker su DESKTOP Flet 0.85.3 →
     'Unknown control: FilePicker' — NON usare"** — lo stesso identico problema del web, per lo stesso motivo
     pratico (il solo aggiungere il controllo a `page.overlay` fa comparire il banner, prima ancora di qualunque
     click), ma sul desktop invece che sul browser. La UI di scelta foto (`_pick_photo()`/`pick_image()`)
     instradava già correttamente il desktop su un dialogo nativo via subprocess (`osascript`/PowerShell/`zenity`)
     e non aveva MAI avuto bisogno di un `ft.FilePicker` reale — solo `did_mount()` lo registrava comunque, senza
     alcun motivo pratico, introducendo il bug. Il problema esisteva silenziosamente da quando `did_mount()` è
     stato scritto (2026-07-12) e non era mai stato notato perché nessun lancio nativo da terminale era stato
     testato nel frattempo. **Fix**: la condizione di registrazione in entrambi i `did_mount()` è stata ristretta
     ai soli platform realmente mobile (`self._page.platform in (ft.PagePlatform.ANDROID, ft.PagePlatform.IOS)`),
     la stessa identica condizione già usata da `_pick_photo()`/`pick_image()` per instradare la UI — desktop e web
     ora si comportano allo stesso modo (nessun FilePicker mai registrato), mobile invariato. I fallback difensivi
     in `_pick_photo_mobile()` (profilo_tab.py) e `_pick_mobile()` (maps_view.py), che creano un FilePicker al volo
     se `did_mount()` non l'ha ancora fatto, non necessitavano modifiche: sono raggiungibili SOLO dal ramo mobile
     nativo già instradato correttamente da `_pick_photo()`/`pick_image()`, mai da desktop o web. **Verificato**
     con test end-to-end (bypass `__init__`, chiamata diretta a `ProfiloTab.did_mount`/`MapsView.did_mount` su un
     `self` fittizio con `page.overlay` reale): macOS/Windows/Linux → `_file_picker` resta `None`, nessun controllo
     aggiunto a `page.overlay`; Android/iOS → registrato correttamente in `page.overlay`; web (qualunque
     `platform`) → resta `None`, comportamento invariato rispetto al fix precedente. `python3 -m compileall`
     sull'intero albero sorgente — 0 errori. Non riproducibile un vero banner "Unknown control" in questo ambiente
     sandbox (serve un client Flutter desktop reale) — la conferma definitiva arriverà dal prossimo avvio di Davide
     da terminale.
  2. **Pulsanti level up/down ridimensionati** — il fix del task #13 di questa stessa sessione (pulsanti pieni
     `ElevatedButton`/`OutlinedButton` con etichetta lunga "▲ Sali a Lv.9"/"▼ Scendi a Lv.7", colore pieno, riga
     dedicata) era troppo ingombrante nell'uso reale, anche se aveva risolto il problema opposto segnalato in
     precedenza (le vecchie icone 22px erano "facili da perdere"). **Fix, via di mezzo**: sostituiti con due
     `ft.IconButton` circolari (`ARROW_CIRCLE_UP`/`ARROW_CIRCLE_DOWN`, 30px — più grandi dei 22px originali ma
     senza testo/riga dedicata), colorati (rosso `COLOR_ACCENT_CRIMSON` per salire, grigio-ardesia
     `COLOR_TEXT_SECONDARY` per scendere) per restare riconoscibili a colpo d'occhio, reinseriti nella stessa riga
     compatta "Lv.N  Comp. +N" invece di occupare una riga propria — il dettaglio testuale resta nel tooltip ("Sali
     a Lv.9"/"Scendi a Lv.7"), non più scritto per esteso sul pulsante. Nessuna modifica alla logica di
     `_on_level_up_click`/`_on_level_down_click`, solo allo stile/posizione dei due controlli. Verificato con
     `py_compile`.
  - **Verifica di chiusura**: `python3 -m compileall` sull'intero albero sorgente (esclusi `build/`) — 0 errori.

- **Pulsanti level up/down — terzo giro, "testo + dimensione media" (task #24, 2026-07-16)** — la versione "via di
  mezzo" appena sopra (icone circolari 30px senza testo) era ancora priva di etichetta testuale; richiesta
  esplicita di aggiungerne una mantenendo comunque una taglia intermedia (non tornare al pulsante largo con "▲ Sali
  a Lv.9" già respinto). **Fix**: `self._level_up_btn`/`self._level_down_btn` in `profilo_tab.py` ricostruiti come
  `ft.ElevatedButton`/`ft.OutlinedButton` compatti — icona (`ARROW_UPWARD`/`ARROW_DOWNWARD`, 14px) + etichetta
  testuale **breve e fissa** ("Su"/"Giù", non il numero di livello dinamico che aveva reso ingombrante il tentativo
  precedente), altezza 30px, font 12px bold, padding orizzontale ridotto (10px, verticale 0). Il dettaglio completo
  ("Sali a Lv.9"/"Scendi a Lv.7") resta nel tooltip, non scritto per esteso sul pulsante — via di mezzo reale tra
  le due estremità già provate (icona nuda vs. bottone largo). Spaziatura della riga "Lv.N Comp. +N" leggermente
  aumentata (`spacing=0→8`, spacer `width=4→10`) per dare respiro ai due pulsanti ora più larghi. Nessuna modifica
  alla logica di `_on_level_up_click`/`_on_level_down_click`.
  **Verificato** con test end-to-end (DB temporaneo isolato, mai quello reale): tipo controllo
  (`ElevatedButton`/`OutlinedButton`), altezza (30px per entrambi), testo esatto ("Su"/"Giù"), tooltip dinamico
  corretto (`"Sali a Lv.6"`/`"Scendi a Lv.4"` per un personaggio Lv.5). `python3 -m compileall`/`pyflakes` puliti
  sull'intero albero sorgente (solo il rumore preesistente di `from config.settings import *`).

- **Sessione bug fix + Arcanum Mistico/Discipline Elementali (2026-07-16, stessa giornata)** — su richiesta di
  Davide di affrontare prima i bug non risolti e poi le feature mancanti già segnalate come TODO.
  1. **Bug: Totem/Terreno non selezionabili nello stesso level-up della sottoclasse** — confermato reale (segnalato
     come TODO latente il 2026-07-15). `profilo_tab.py`: i picker di Animale Totem (Barbaro Lv3) e Terreno (Druido
     Lv2) leggevano `sc_lower` da `c.subclass` già persistita — sempre vuota nel momento esatto in cui si sceglie
     la sottoclasse. Fix: stesso pattern del fix Mistificatore Arcano/Cavaliere Mistico (2026-07-15) — quando
     `subclass_dd_ref` è popolato (SUBCLASS_CHOICE presente in questo level-up), il picker Totem/Terreno diventa un
     `ft.Container` con visibilità agganciata dal vivo al dropdown sottoclasse via `on_select` (nuovo helper
     `_compose_on_select()`, concatena più handler sullo stesso dropdown senza sovrascriverli). Corretto anche il
     salvataggio: il dropdown viene costruito "nascosto" anche per sottoclassi che non lo richiedono (necessario
     per la reattività), quindi si scrive `c.totem_animal`/`c.land_terrain` solo se la sottoclasse FINALE scelta
     corrisponde davvero — altrimenti un Barbaro Berserker si sarebbe visto salvare il default nascosto ("Orso").
     **Uno stile di Combattimento verificato NON affetto**: si sceglie al Lv.2, un livello prima della soglia
     sottoclasse (Lv.3) — il vecchio TODO lo includeva per errore. Verificato con test end-to-end (bypass Flet
     Page, DB temporaneo isolato): Barbaro Lv2→3 che sceglie "Combattente Totemico" nello stesso dialog vede
     comparire/sparire il picker Totem in tempo reale al cambio dropdown; scelto e salvato correttamente; un
     Barbaro "Cammino del Berserker" non salva alcun `totem_animal`. Stesso schema per Druido Lv1→2, "Circolo della
     Terra"/"Circolo della Luna".
  2. **Bug: più scudi equipaggiabili contemporaneamente** — verificato che era in realtà **già risolto** l'11/07
     come effetto collaterale del fix "CA non si aggiorna con l'equipaggiamento" (stessa data):
     `core/equipment_manager.py → resolve_armor_equip()`/`ArmorCandidate` modella già la postazione "scudo" come
     indipendente e limitata a 1. Il checkbox TODO era rimasto per errore non spuntato. Verificato con nuovo test
     end-to-end dedicato (DB temporaneo isolato): due scudi creati `is_equipped=True`, dopo
     `_enforce_armor_exclusivity()` ne resta equipaggiato solo uno, CA ricalcolata correttamente (10+mod DES+2
     scudo, non doppio). Documentazione aggiornata di conseguenza.
  3. **Feature: picker Arcanum Mistico (Warlock, lv.11/13/15/17)** — implementato per intero (era solo un
     promemoria testuale dal lv13 in poi, e nessun promemoria al lv11). Vedi changelog dettagliato nel TODO
     corrispondente sopra. Nuovo `StepType.ARCANUM_SPELL` in `core/level_manager.py`, dropdown filtrato per livello
     incantesimo ESATTO in `profilo_tab.py`, salvato come `known_spell`.
  4. **Feature: Discipline Elementali (Monaco, Via dei Quattro Elementi)** — implementata sia la scelta iniziale di
     Lv.3 (Sintonia Elementale automatica + 1 a scelta, prima assente del tutto) sia la crescita Lv.6/11/17 (prima
     solo un promemoria testuale). Vedi changelog dettagliato nel TODO corrispondente sopra. Nuovo
     `StepType.MONK_DISCIPLINE`, nuovo `proficiency_type="monk_discipline"`, nuova sezione "Discipline Elementali"
     in `profilo_tab.py → _build_talenti`.
  - **Verifica di chiusura di sessione**: `python3 -m compileall` sull'intero albero sorgente (esclusi
    `.venv/`/`build/`) — 0 errori; regressione `get_level_up_steps()` su tutte le 12 classi × tutte le sottoclassi
    × lv2-20 (nessuna eccezione, nessuna etichetta vuota) rieseguita dopo ENTRAMBE le feature nuove. Tutti i test
    end-to-end sopra usano un DB temporaneo isolato (`HOME` di test separato via `tempfile.mkdtemp()`), mai il DB
    reale di Davide.
  - **Rimandato su richiesta esplicita di Davide** (risposta a `AskUserQuestion`, priorità solo su queste 2 feature
    per questa sessione): terza lingua libera Mezzelfo, incantesimi razziali Drow/Tiefling (sezione dedicata sempre
    visibile, CD su Carisma fisso — confermato come design preferito quando si affronterà), Umano Standard vs
    Variante, wiring `equipment/*.json` alla UI + normalizzazione `bonus_proficiencies` sottoclassi Chierico/Bardo
    (tag ancora nel vecchio formato rotto `#armature_pesanti`/`#armi_da_guerra`, va prima sistemato il dato poi
    decisa la UI). Progettazione già discussa e pronta, non ancora implementata.

- **Sessione di follow-up (2026-07-16, stessa giornata) — 6 task rimandati sopra, tutti implementati**: terza
  lingua Mezzelfo, incantesimi razziali Drow/Tiefling, Umano Standard vs Variante, normalizzazione + applicazione
  `bonus_proficiencies` sottoclassi Chierico/Bardo, wiring informativo `equipment/*.json`, styling pulsanti
  level-up/down (3 iterazioni), e infine la **Lista Incantesimi Ampliata del Warlock**. Le prime voci sono già
  documentate nelle rispettive sezioni di questo file (Checklist Revisione Dati PHB → TODO "Mezzelfo non riceve mai
  la scelta della terza lingua...", "Incantesimi razziali di Drow/Tiefling...", "Selezione Umano Standard vs Umano
  Variante...", "`bonus_proficiencies` nelle sottoclassi di `chierico.json`/`bardo.json`...", "Wiring del resto di
  `equipment/*.json`...", più le due voci "Pulsanti level up/down" appena sopra). Questa voce documenta l'ultimo
  task, la Lista Incantesimi Ampliata:
  - **Lista Incantesimi Ampliata del Warlock — collegata ai picker di scelta incantesimo (task #25)**: il PHB IT
    concede a ciascuno dei 3 patroni Warlock (Il Signore Fatato/L'Immondo/Il Grande Antico) una "Lista Incantesimi
    Ampliata" — un elenco fisso di 10 incantesimi (2 per ogni livello di slot 1°-5°) **aggiunti al pool** da cui il
    Warlock può scegliere quando impara un nuovo incantesimo conosciuto (creazione, SPELL_LEARN al level-up,
    sostituzione via SPELL_SWAP) — **non** incantesimi gratuiti sempre pronti come i domain spell di
    Chierico/Paladino/Druido: contano comunque come una delle scelte normali del Warlock, semplicemente ampliano da
    dove puoi pescare. Il dato (`expanded_spells` in `classes/warlock.json`, dict `{"1":[...],...,"5":[...]}` con 2
    nomi ciascuno) era già presente e verificato in una sessione precedente ma non era mai stato collegato a
    nessuna UI: un Warlock non poteva mai scegliere, ad esempio, "Sonno"/"Comando" per Il Signore Fatato né alla
    creazione né al level-up, nonostante il PHB glielo conceda esplicitamente.
  - **`GameDataLoader.get_expanded_spells(class_name, subclass_name)`** (nuovo, `game_data_loader.py`): legge
    `expanded_spells` dal blocco sottoclasse via `get_subclass_data()`, risolve ogni nome tramite
    `get_spell_master_entry()` (lookup diretto nel file master `incantesimi_completi.json` — necessario perché
    questi incantesimi sono deliberatamente ASSENTI da `incantesimi_warlock.json`, la lista "normale" della classe,
    altrimenti non si distinguerebbero più come "ampliati"), deduplica, ordina per livello poi nome. No-op sicuro
    per qualunque classe/sottoclasse senza questo campo (ritorna lista vuota).
  - **Creazione personaggio** (`wizard_view.py`/`manual_form.py`, sezione "Trucchetti e Incantesimi Iniziali"): il
    pool di incantesimi di 1° livello mostrato nei dropdown ora include anche gli incantesimi ampliati di 1°
    livello della sottoclasse corrente (`_spell_lv1_pool = base + [ampliati non già in base]`), con deduplica per
    nome. Il dropdown sottoclasse Warlock (Il Signore Fatato/L'Immondo/Il Grande Antico) ora richiama anche la
    ricostruzione di questa sezione nel suo `on_select`, così cambiare patrono aggiorna dal vivo il pool mostrato
    (prima il pool restava quello del patrono scelto per primo, salvo essere comunque corretto al primissimo
    render).
  - **Level-up** (`profilo_tab.py`): sia lo step `SPELL_LEARN` (pool "eleggibile per imparare") sia `SPELL_SWAP`
    (sia il pool "da cui rimuovere" sia quello "con cui sostituire") ora uniscono gli incantesimi ampliati della
    sottoclasse corrente allo stesso modo, con lo stesso criterio di deduplica.
  - **Bug reale trovato e corretto durante il testing** (non nella richiesta originale, scoperto scrivendo i test
    end-to-end): le funzioni di SALVATAGGIO vero e proprio — `_save_known_spell_by_name()` in `wizard_view.py` E in
    `manual_form.py`, e `_save_known_spell()` in `profilo_tab.py` (condivisa da
    SPELL_LEARN/SPELL_SWAP/CANTRIP_LEARN/ARCANUM_SPELL/BORROWED_*) — cercavano il nome scelto SOLO in
    `_loader.get_spells(class_name)` (la lista base della classe). Risultato pratico: un giocatore poteva vedere e
    selezionare correttamente un incantesimo ampliato nel dropdown (il pool era già corretto), ma al salvataggio la
    ricerca falliva silenziosamente (`logger.warning(...)`, nessun crash, nessun avviso visibile) e l'incantesimo
    non veniva MAI scritto su `known_spells` — un fallimento silenzioso che sarebbe rimasto invisibile senza un
    test end-to-end dedicato che verificasse anche il DB, non solo il contenuto del dropdown. **Fix**: tutte e 3 le
    funzioni ora ricadono su `_loader.get_expanded_spells(class_name, char.subclass or "")` quando la ricerca nella
    lista base non trova nulla, prima di arrendersi e loggare l'avviso.
  - **Verificato** con test end-to-end (DB temporaneo isolato, mai quello reale): (1) creazione — entrambi i file
    (`wizard_view.py`/`manual_form.py`), tutti e 3 i patroni, conferma che il pool di 1° livello include i
    rispettivi incantesimi ampliati e che la scelta viene effettivamente persistita in `known_spells` dopo il
    salvataggio finale; (2) level-up SPELL_LEARN — Warlock Lv3→4 con "Il Signore Fatato" (harness
    `ProfiloTab`+`FakePage` già consolidato in sessione), dropdown "Incantesimo conosciuto" contiene correttamente
    "Allucinazione di Forza" (incantesimo ampliato del patrono), selezionato e confermato → verificato presente in
    `known_spells` a fine level-up; (3) level-up SPELL_SWAP — Warlock Lv3→4 con "L'Immondo", checkbox di
    sostituzione abilitata, un incantesimo base rimosso e "Comando" (ampliato) aggiunto al suo posto → verificato
    che il vecchio nome sparisce e il nuovo compare in `known_spells`; (4) `get_level_up_steps()` ri-eseguito su
    tutte le 12 classi × tutte le sottoclassi reali × livelli 2-20 (988 combinazioni) dopo tutte le modifiche di
    `profilo_tab.py` di questa sessione — 0 eccezioni, 0 etichette vuote, nessuna regressione. `python3 -m
    compileall`/`pyflakes` puliti su `profilo_tab.py`, `wizard_view.py`, `manual_form.py`, `game_data_loader.py`
    (solo il rumore preesistente di `from config.settings import *`).
  - **Non affrontato, fuori scope**: nessun'altra classe/sottoclasse PHB IT ha una "Lista Incantesimi Ampliata"
    equivalente (verificato che il campo `expanded_spells` esiste solo in `warlock.json`) — nessun altro punto di
    wiring necessario.

- **Fix bug/gap funzionali: Indebolimento + competenze base-classe (2026-07-16, sessione dedicata su richiesta di
  Davide "procediamo con i bug/gap funzionali")** — i due gap segnalati a fine sessione precedente (riepilogo dello
  stato del progetto), entrambi confermati reali e risolti nella stessa sessione:
  1. **Tracker Indebolimento (Exhaustion)** — `EXHAUSTION_LEVELS` esisteva in `config/settings.py` dal 2026-07-03
     ma non era mai stato collegato a nessun campo persistito né a un widget. Aggiunto `Character.exhaustion_level:
     int = 0` (0-6) in `data/models.py`; colonna `characters.exhaustion_level INTEGER DEFAULT 0` via
     `_add_column()` in `data/database.py`; `_row_to_character()`/`create()`/`update()` in `character_repo.py`
     estesi per leggere/scrivere il campo (stesso pattern già consolidato nel progetto: va aggiunto esplicitamente
     sia alla lista colonne dell'INSERT/UPDATE sia al dict parametri, non basta il campo sul dataclass — bug di
     questo tipo era già capitato in passato con `dragon_ancestry`/`fighting_style`/ecc., vedi Categoria B più
     sopra); nuova `character_repo.update_exhaustion_level(character_id, value)` con clamp 0-6 anche lato repo
     (difesa in profondità, non solo lato UI). Nuova sezione "Indebolimento" in `combattimento_tab.py` (tra
     "Statistiche di Combattimento" e "Azioni Turno"): counter −/+ con colore che scala grigio→ambra→rosso in base
     al livello, lista degli effetti cumulativi da `EXHAUSTION_LEVELS` attivi al livello corrente (es. a livello 3
     mostra gli effetti dei livelli 1, 2 e 3). **Scelta di design deliberata**: nessun enforcement automatico delle
     regole (non dimezza velocità/HP max da sola, non applica/rimuove livelli in automatico da feature come
     Frenesia del Barbaro o incantesimi come Guarigione) — stesso principio già adottato per "Abilità di
     Classe"/"Tratti di Razza" in questo progetto: la sezione è un riferimento di consultazione rapida per il
     giocatore/master, che applica gli effetti a mano. Verificato con test end-to-end (DB temporaneo isolato, mai
     quello reale): round-trip DB completo (create/update generico/update_exhaustion_level dedicato, incluso il
     clamp su input fuori range 0-6 sia sopra sia sotto), costruzione della sezione UI per tutti i livelli 0-6
     senza eccezioni, click programmatico su incremento/decremento che si fermano correttamente a 6 e a 0,
     regressione `CombattimentoTab` su tutte le 12 classi PHB.
  2. **Competenze armatura/armi base-classe mai applicate** — `armor_proficiencies`/`weapon_proficiencies` esistono
     in tutti e 12 i file `classes/*.json` fin dalla prima trascrizione JSON (non vanno confusi con
     `bonus_proficiencies` di SOTTOCLASSE, un campo diverso a un livello diverso del JSON, già applicato da
     `apply_subclass_bonus_proficiencies()` il 2026-07-16 nella sessione precedente), ma nessun codice li aveva mai
     letti né salvati come `character_proficiencies` — ogni personaggio di ogni classe nasceva senza competenza
     formale in armature/armi, nonostante il dato fosse già corretto e pronto. Nuova
     `character_repo.apply_class_base_proficiencies(character_id, class_name)`: legge i due campi da
     `game_data.get_class(class_name)`, li separa in voci fisse vs eventuali "choice" con
     `classify_bonus_proficiency_entries()` (verificato che nei 12 file attuali sono sempre liste piatte di
     stringhe — nessuna choice a questo livello, a differenza di `tool_proficiencies` — un'eventuale choice futura
     viene ignorata con un warning invece di far fallire la creazione), poi riusa
     `apply_subclass_bonus_proficiencies()` per il salvataggio deduplicato invece di reimplementare la stessa
     logica. **Bug di classificazione trovato e corretto nello stesso passaggio**:
     `_classify_bonus_proficiency_type()` riconosceva solo i token categoria (`"leggere"`/`"semplice"`/ecc.) e le
     18 abilità, ricadendo su `"tool"` per qualunque altro nome — ma diverse classi (Mago, Stregone, Druido, Bardo,
     Ladro, Monaco) elencano anche armi SPECIFICHE nel campo (es. "Stocco", "Bastone Ferrato", "Pugnale"), che
     sarebbero state salvate come competenza-strumento invece che come competenza-arma. Fix: la funzione ora
     controlla anche `game_data.get_weapon(entry_name)` (il catalogo `equipment/weapons.json`) prima di ricadere su
     `"tool"` — verificato che tutti i nomi arma specifica usati nei 12 file classe risolvono esattamente nel
     catalogo. Chiamata sia alla creazione (`wizard_view.py`/`manual_form.py`, subito dopo il salvataggio dei bonus
     di sottoclasse) sia come self-healing ad ogni apertura/refresh di `EsplorazioneTab` (stesso principio già
     consolidato nel progetto per `sync_borrowed_spellcasting_ability`/`sync_bonus_domain_spells` — backfilla
     automaticamente i personaggi creati prima di questo fix, idempotente). Nuova sezione di sola lettura
     "Competenze Armatura e Armi" in `esplorazione_tab.py` (dopo Strumenti): mostra le voci con etichetta leggibile
     per i token categoria (`_ARMOR_TOKEN_LABELS`/`_WEAPON_TOKEN_LABELS`, es. `"leggere"`→"Armature leggere") e il
     nome as-is per le armi specifiche; nessun "+ Aggiungi" (competenze derivate dalla classe, non scelte del
     giocatore) ma rimovibili per house rule, riusando `_on_delete_proficiency()` (esteso con un'etichetta di
     conferma generica "competenza" per i tipi armor/weapon, prima mancante e sarebbe ricaduta erroneamente su
     "strumento"). Verificato con test end-to-end (DB temporaneo isolato, mai quello reale): tutte e 12 le classi
     producono esattamente le competenze attese (confrontate insieme per insieme contro
     `armor_proficiencies`/`weapon_proficiencies` del JSON), chiamata doppia non duplica righe (idempotenza
     confermata), backfill su un personaggio "vecchio" creato bypassando il fix (simulando un personaggio
     pre-2026-07-16) che al primo apertura della tab Esplorazione riceve automaticamente le 5 competenze arma
     attese del Mago senza alcuna azione del giocatore, nomi arma specifica (es. "Pugnale") confermati classificati
     come `"weapon"` e non `"tool"`, regressione `EsplorazioneTab` su tutte le 12 classi.
  - **Verifica di chiusura comune a entrambi i fix**: `python3 -m py_compile`/`pyflakes` puliti su tutti i file
    toccati (`data/models.py`, `data/database.py`, `data/repositories/character_repo.py`,
    `ui/views/character_sheet/combattimento_tab.py`, `ui/views/character_sheet/esplorazione_tab.py`,
    `ui/views/creation_wizard/wizard_view.py`, `ui/views/creation_wizard/manual_form.py` — solo il rumore
    preesistente di `from config.settings import *`, nessun errore genuino); `python3 -m compileall` sull'intero
    albero sorgente (esclusi `build/`/`.venv/`) — 0 errori.

- **Redesign selezione incantesimi/talenti/trucchetti — da Dropdown+icona ⓘ a `CardPicker` (2026-07-16, sessione
  dedicata)** — bug report di Davide (verbatim): "non mi piace quando vengono scelti gli incantesimi devi prima
  selezionarli e poi premere info, è macchinoso e difficile per il player, ci vorrebbe più una interfaccia apposta,
  dobbiamo riprogettarlo... anche per la scelta di quelli bonus proprio in incantesimi. le competenze non le
  dobbiamo lasciare in esplorazione ma andrebbero messe in profilo". Tre richieste distinte, tutte implementate
  nella stessa sessione:
  1. **Nuovo pattern di selezione, sostituisce il `dropdown_with_info()` introdotto lo stesso giorno in una
     sessione precedente** (vedi voce "Descrizione prima di scegliere" più sopra) — quel pattern richiedeva due
     gesti separati (scegli dal Dropdown, poi clicca l'icona ⓘ per leggere la descrizione), esattamente il problema
     segnalato da Davide. **Decisione di design confermata via `AskUserQuestion` prima di scrivere codice** (2
     domande, risposte scelte da Davide): (a) "Lista a schede, stesso dialog" — niente nuovo step separato nel
     wizard di level-up, niente nuova scheda: un click su una card la seleziona E mostra subito la descrizione
     completa inline, sotto il titolo; (b) "Tutti i punti con `dropdown_with_info`" — la conversione copre ogni
     singolo punto che usava quel pattern (o l'equivalente icona ⓘ standalone accanto a Checkbox/RadioGroup), non
     solo un sottoinsieme.
  2. **Nuovo widget `CardPicker`** in `ui/widgets.py` — wrapper Python plain (NON un `ft.Control`, possiede un
     `ft.Column` in `.control`), con API compatibile Dropdown/Checkbox/RadioGroup: `.value`/`.values`
     (getter+setter, il setter NON invoca `on_select` — solo un click reale lo fa, stesso comportamento di
     `Dropdown.value = ...`), `.options` (setter: lista di dict `{"key","title","body"}`, ricostruisce le card e
     invalida la selezione corrente se la key non è più tra le opzioni — necessario per la stessa esclusione
     reciproca dinamica già in uso ovunque nel progetto per Dropdown multipli collegati), `.disabled`, `.visible`
     (delega a `.control.visible`), `.update()` (guard `try/except RuntimeError`), `.on_select` (invocato con
     `ev.control is self` dopo un click reale). Due modalità: single-select (`multi=False`, default — comportamento
     Dropdown/RadioGroup, ri-cliccare la card già selezionata non fa nulla) e multi-select (`multi=True`,
     `max_selected` opzionale — oltre il limite il click viene ignorato silenziosamente, stesso comportamento
     "revert silenzioso" già in uso per le Checkbox di Metamagia/Suppliche Occulte). **Helper per costruire
     `.options`** dagli stessi dati già usati da `make_*_describe()`: `spell_card_options(spells: list[dict])`,
     `feat_card_options(loader, names: list[str])`, `invocation_card_options(invocations: list[dict])`,
     `named_option_card_options(options: list[dict])` (Metamagia/Dono del Patto/Stile di Combattimento/Discipline
     Elementali — dati `{"name","description"}`). **`dropdown_with_info()` NON è stata rimossa** (nessun caso d'uso
     residuo la richiede più in questa sessione, ma resta come helper generico per eventuali usi futuri più
     semplici, dove il pattern a due gesti non sia un problema).
  3. **Conversione completa, punto per punto**:
     - **`profilo_tab.py`** (level-up) — tutti i ~14 punti convertiti: scelte iniziali borrowed casting
       (Mistificatore Arcano/Cavaliere Mistico) trucchetto+incantesimo, scelta iniziale disciplina Monaco Lv.3,
       `SPELL_LEARN`, `ARCANUM_SPELL`, `MONK_DISCIPLINE` (crescita), `SPELL_SWAP`, `CANTRIP_LEARN`,
       `BORROWED_CANTRIP`/`BORROWED_SPELL_LEARN`/`BORROWED_SPELL_SWAP`, talento all'ASI, Stile di Combattimento
       Paladino/Ranger. Rimossa la funzione `_make_info_icon()` (nessun chiamante residuo). **Deliberatamente non
       toccati** (fuori scope, mai usavano `dropdown_with_info`): Metamagia/Suppliche Occulte (Checkbox + icona ⓘ
       standalone — scelta "tutto o niente" su poche opzioni sempre visibili, diversa da un lungo elenco da
       scorrere), Dono del Patto (RadioGroup + icona ⓘ), il picker custom Segreti Magici (`_open_ms_picker`, dialog
       bespoke con riga+icona ⓘ propria), Totem/Terreno (semplici Dropdown, mai avuto un'icona ⓘ).
     - **`wizard_view.py`/`manual_form.py`** (creazione, fase Revisione/Scelte) — stessa identica conversione
       mirror in entrambi i file: trucchetto Alto Elfo, talento Umano Variante, e l'intera sezione reattiva
       "Trucchetti e Incantesimi Iniziali" (`_rebuild_spells_init_col()`, la più delicata perché è una funzione di
       *rebuild* richiamata ad ogni cambio classe/razza/sottoclasse, non una costruzione one-shot come nel dialog
       di level-up — le 4 liste `cantrip_dds`/`spell_dds`/`prepared_dds`/`spellbook_dds` e le rispettive
       `_refresh_*_options()` sono state convertite mantenendo esattamente la stessa logica di esclusione reciproca
       dinamica, solo sostituendo `dd.options = [ft.DropdownOption(...)]` con `dd.options =
       spell_card_options([...])`).
     - **`spells_view.py`** (sezione "Incantesimi Bonus", sempre visibile anche per classi non incantatrici) — il
       picker a due livelli classe→incantesimo: `class_dd` resta un `ft.Dropdown` semplice (lista breve di 12
       classi, mai il problema segnalato), `spell_dd` convertito a `CardPicker`, reattivo al cambio classe
       (`_refresh_spell_options()` ricostruisce `.options` e chiama `.update()` — **nessun guard `try/except`, a
       differenza di quasi tutti gli altri punti**: qui il dialog è sempre già montato quando si cambia `class_dd`,
       la funzione viene chiamata anche subito dopo la costruzione del dialog stesso, prima di `page.show_dialog()`
       — verificato che questo non causa mai un `RuntimeError` nei test, dato che il primo update avviene sempre
       prima del mount ma il metodo `CardPicker.update()` guarda già `try/except` internamente).
  4. **Competenze Armatura e Armi spostata da `EsplorazioneTab` a `ProfiloTab`** — stesso identico dato
     (`proficiency_type in ("armor","weapon")`, popolato da `apply_class_base_proficiencies()`), stessa resa visiva
     (`_ARMOR_TOKEN_LABELS`/`_WEAPON_TOKEN_LABELS`, icone scudo/martello, pulsante "Rimuovi" per house rule),
     semplicemente in una superficie diversa. `_section_armi_armature()` e le due costanti dizionario rimosse per
     intero da `esplorazione_tab.py` (nessun altro riferimento nel file); ricreate identiche in `profilo_tab.py`,
     appese subito dopo la sezione "Competenze" (tiri salvezza/abilità) e prima di "Talenti" — nuovo import `from
     data.database import get_connection` e un `_on_delete_proficiency()` locale (stesso identico SQL `DELETE FROM
     character_proficiencies WHERE id = ?` già in uso in `esplorazione_tab.py`, non condiviso tra i due file —
     `esplorazione_tab.py` mantiene la propria copia, ancora usata da Lingue/Strumenti, mai stata esclusiva della
     sezione armatura/armi).
  5. **Verificato end-to-end** (DB temporaneo isolato via `tempfile.mkdtemp()`+`HOME`, mai il DB reale di Davide;
     tecnica: sottoclasse `TrackedCardPicker(CardPicker)` monkeypatchata sul nome `CardPicker` importato in ciascun
     modulo, per catturare in ordine ogni istanza costruita e pilotarla con `._toggle(key)` — chiamata identica a
     un vero click, innesca `on_select` — senza dover disambiguare l'albero controlli Flet, dato che `CardPicker`
     non è un `ft.Control` e quindi non compare mai in un `find_all()` sull'albero, solo il suo `.control` ci
     compare):
     - `profilo_tab.py`: 13 scenari di sola costruzione + 5 scenari di click-e-salvataggio completi (Ladro
       Mistificatore Arcano scelta iniziale, Stregone SPELL_LEARN+CANTRIP_LEARN+SPELL_SWAP+METAMAGIC, Warlock
       ARCANUM_SPELL, Monaco MONK_DISCIPLINE crescita, Paladino Stile di Combattimento) — tutti passati, incluso un
       bug reale trovato e corretto (mancavano alcune chiamate `.update()` dopo aver riassegnato `.options` in un
       loop di esclusione reciproca — il setter di `.options` ricostruisce l'albero interno ma non richiama mai da
       solo `.update()` sul controllo Flet sottostante, quindi un picker già montato sarebbe rimasto visivamente
       non aggiornato finché non toccato di nuovo).
     - `wizard_view.py` E `manual_form.py` (stessi 4 scenari mirror in entrambi i file, stesso identico esito):
       Stregone (cantrip_dds+spell_dds, mutua esclusione confermata sia lato opzioni sia lato persistenza DB), Mago
       Elfo Alto (trucchetto razziale + Libro degli Incantesimi, 10 CardPicker attesi — 1 razziale + 3 di classe +
       6 libro), Guerriero Umano Variante (talento `Robusto` scelto via CardPicker, verificato salvato come
       `proficiency_type="feat"`), Chierico Nano delle Colline Dominio della Vita (incantesimi preparati iniziali).
       Tutti e 4 gli scenari completano la creazione fino al salvataggio DB e verificano che la scelta cliccata
       (non il default) sia quella effettivamente persistita in `known_spells`/`character_proficiencies`.
     - `spells_view.py`: dialog "Aggiungi Incantesimo Bonus" pilotato end-to-end su un personaggio Guerriero (non
       incantatore) — cambio `class_dd` a "Mago" aggiorna dal vivo le opzioni del `CardPicker` (215 incantesimi
       Mago), click su "Luce" tramite `_toggle()`, salvataggio verificato in `known_spells` con `is_bonus=True,
       class_list="Mago"`.
     - Spostamento Competenze: verificato che `ProfiloTab` mostra ora la sezione (header "COMPETENZE ARMATURA E
       ARMI" trovato nell'albero controlli) e che `EsplorazioneTab` non la mostra più (né l'header né il metodo
       `_section_armi_armature` esistono più su quella classe); flusso di eliminazione competenza pilotato
       end-to-end dal nuovo pulsante "Rimuovi" in `ProfiloTab` fino alla riga cancellata dal DB.
     - **Smoke test di regressione finale**: tutte le 12 classi PHB istanziate senza eccezioni su tutti e 5 i tab
       (`ProfiloTab`/`EsplorazioneTab`/`CombattimentoTab`/`InventarioTab`/`SpellsView`); `get_level_up_steps()`
       rieseguito su 760 combinazioni classe×sottoclasse×livello (2-20) — 0 eccezioni, 0 etichette vuote; `python3
       -m compileall`/`pyflakes` puliti su tutti i file toccati e sull'intero albero sorgente (esclusi
       `build/`/`.venv/`, solo il rumore preesistente di `from config.settings import *`); grep di chiusura
       confermato — zero occorrenze residue di `dropdown_with_info(` come CHIAMATA in tutto l'albero `ui/` (le
       uniche 2 occorrenze rimaste sono la definizione della funzione stessa e un riferimento in un docstring,
       entrambe in `ui/widgets.py`).

- **Bug fix: modalità incantesimi incoerente tra classi "prepara" e classi "conosce" (2026-07-16)** — bug report di
  Davide (verbatim): "il bardo impara incantesimi nuovi nel level up e può sostituire quelli conosciuti, ma nella
  sezione incantesimi può preparare gli incantesimi come gli incantatori puri, esempio mago e chierico. Tutte le
  classi devono avere la modalità coerente di incantesimi (anche le sottoclassi)".
  **Causa radice confermata in `ui/views/spells_view.py`**: la sezione "Incantesimi" di `_build()` renderizzava
  SEMPRE l'intero catalogo di classe (`self._class_spells`, es. tutti i 120 incantesimi del Bardo) con un
  cerchietto di toggle libero (`_section_spell_list()`/`_toggle_prepared()`) — identico per TUTTE le classi con una
  propria lista, incluse Bardo/Ranger/Stregone/Warlock (`_KNOW_CLASSES`, già distinte correttamente per il *calcolo
  del limite* — `_calc_max_prepared()` ritorna `None` per loro dal fix dell'11/07 — ma MAI per il *tipo di
  interazione* mostrato). Risultato pratico: un giocatore poteva aprire la tab Incantesimi di un Bardo e toccare il
  cerchietto di un incantesimo QUALSIASI tra i 120 della lista di classe per marcarlo "conosciuto" all'istante,
  bypassando del tutto i meccanismi già esistenti e corretti per imparare un incantesimo (scelta alla creazione,
  `SPELL_LEARN`/`SPELL_SWAP`/`CANTRIP_LEARN` al level-up) — esattamente la stessa interazione (aspetto, click,
  colore) di un vero preparatore come Chierico/Druido/Mago, per cui invece è corretta perché il PHB permette loro
  di scegliere ogni giorno tra l'intera lista. Le sottoclassi "prese in prestito dal Mago" (Mistificatore
  Arcano/Cavaliere Mistico) e i Segreti Magici del Bardo erano invece GIÀ in sola lettura da tempo
  (`_section_extra_spell_list()`, nessun toggle) — la stessa incoerenza segnalata da Davide, ma nella direzione
  opposta: due meccanismi diversi per la stessa categoria concettuale di classi "know".
  **Fix**: in `_build()`, la sezione "Incantesimi" ora si biforca esplicitamente in base al tipo di classe (stessa chiave `key = class_name.lower()` già usata da `_calc_max_prepared()`):
  - **Full/half preparatori** (`_PREP_FULL`={chierico,druido,mago}, `_PREP_HALF`={paladino}): comportamento INVARIATO — intero catalogo, toggle di preparazione, limite giornaliero PHB.
  - **Classi "know"** (`_KNOW_CLASSES`={bardo,ranger,stregone,warlock}): nuova sezione **read-only** — mostra SOLO
    gli incantesimi realmente presenti in `known_spells` che appartengono alla lista della propria classe (esclusi
    quelli `always_prepared`/`is_bonus`, che hanno già sezioni dedicate), raggruppati per livello, nessun toggle.
    Nuovo metodo `_section_known_class_spell_list()`, stesso stile/pattern di
    `_section_extra_spell_list()`/`_section_always_prepared_list()` (icona "●" crimson invece di "★" ambra, nessun
    badge di provenienza dato che è la propria classe, click sul nome apre comunque il dialog con la descrizione
    completa) — nessun modo di aggiungere un incantesimo arbitrario da questa vista: si impara solo alla creazione
    o tramite gli step di level-up già esistenti, oppure tramite la sezione generica "Incantesimi Bonus" (per
    aggiunte eccezionali concesse dal master, già esistente dal 16/07). Se la lista è vuota (personaggio appena
    creato, prima di qualunque scelta) un messaggio informativo lo spiega invece di una lista bianca.
  - Le sottoclassi "prese in prestito dal Mago" (Mistificatore Arcano/Cavaliere Mistico) non necessitavano
    modifiche: `self._class_spells` resta sempre vuota per Ladro/Guerriero (nessun
    `incantesimi_ladro.json`/`incantesimi_guerriero.json`), quindi i loro incantesimi passavano già, prima e dopo
    questo fix, dalla sezione "Incantesimi Extra" in sola lettura — ora l'intero sistema (preparatori pieni/mezzi
    vs know-class proprie vs know-class "in prestito") usa coerentemente lo stesso principio: toggle libero SOLO
    per chi prepara davvero ogni giorno dall'intera lista PHB, sola lettura per chiunque altro.
  - Aggiornati anche il testo del banner (`_section_prep_banner()`: "Tocca ◉ per segnare un incantesimo come
    conosciuto"→"Nuovi incantesimi si imparano alla creazione o al level-up", per non promettere più un'azione che
    ora non esiste in questa vista) e il docstring di modulo in cima al file, che già descriveva (erroneamente, in
    modo aspirazionale) una sezione "Incantesimi Conosciuti" distinta mai realmente implementata prima d'ora.
  **Verificato** con test end-to-end (DB temporaneo isolato, mai quello reale): Bardo con 2 incantesimi propri
  conosciuti + 1 "Segreto Magico" da Mago — zero nomi dell'intero catalogo Bardo (118 rimanenti) trapelano nella
  vista, i 2 conosciuti e il Segreto Magico compaiono entrambi; stesso identico test ripetuto su
  Ranger/Stregone/Warlock (nessuna leakage del catalogo); Chierico (full preparer) e Paladino (half preparer)
  verificati INVARIATI — l'intero catalogo di 1° livello compare ancora per intero, come deve; Mistificatore Arcano
  (Ladro) verificato invariato (incantesimo appreso da Mago mostrato correttamente in sola lettura); smoke test di
  regressione su tutte le 12 classi PHB senza eccezioni. `python3 -m compileall`/`pyflakes` puliti su
  `spells_view.py` (solo il rumore preesistente di `from config.settings import *`).

- **`CardPicker`: badge livello + eliminazione dello scroll annidato (2026-07-16, stesso giorno, feedback diretto
  sul redesign appena fatto)** — Davide, dopo aver provato il redesign incantesimi appena sopra: "vorrei solo 2
  modifiche, 1 nei titoli degli incantesimi affianco sia indicato anche il livello dell'incantesimo, 2 lo
  scorrimento è difficoltoso, se scelgo l'incantesimo e poi voglio scorrere alle sezioni sotto ho difficoltà a
  scorrere la finestra perché mi scorre la lista degli incantesimi, contando che viene usata pure da tablet".
  1. **Badge livello** — `spell_card_options()` (`ui/widgets.py`) ora include per ogni card un campo opzionale
     `"badge"`/`"badge_color"` (nuovo schema generico su `CardPicker.options`, non solo per gli incantesimi),
     risolto a `"0"` blu per i trucchetti e `"Lv{N}"` crimson per gli incantesimi di livello N — stessa convenzione
     testo/colore già usata nei dialog di dettaglio di `spells_view.py`, per coerenza visiva.
     `CardPicker._rebuild()` disegna il badge come piccolo chip accanto al titolo, solo se presente (nessun impatto
     su `feat_card_options()`/`invocation_card_options()`/`named_option_card_options()`, che non hanno un concetto
     di "livello" e restano senza badge). Applicato automaticamente ovunque nel progetto tramite l'unico punto
     condiviso (`spell_card_options()`): creazione, tutti gli step di level-up con incantesimi/trucchetti
     (SPELL_LEARN/SPELL_SWAP/CANTRIP_LEARN/ARCANUM_SPELL/BORROWED_*), "Incantesimi Bonus" — particolarmente utile
     lì e in SPELL_LEARN/SPELL_SWAP, dove una singola lista può mescolare incantesimi di livelli diversi (es. tutti
     gli incantesimi fino al livello massimo di slot posseduto) e non era ovvio a colpo d'occhio quale livello
     avesse ciascuna voce.
  2. **Scroll annidato — causa radice**: `CardPicker.control` era una `ft.Column` ad ALTEZZA FISSA (180-300px a
     seconda del punto d'uso) con un proprio `scroll=ft.ScrollMode.AUTO` — sempre annidata dentro un contenitore
     GIÀ scrollabile: il content Column del dialog di level-up in `profilo_tab.py` (`ft.Column(dlg_rows, spacing=8,
     scroll=ft.ScrollMode.AUTO)`, un unico grande dialog che aggrega TUTTI gli step di quel livello) o il Column
     dell'intera fase "Revisione"/"Scelte" in `wizard_view.py`/`manual_form.py` (anch'esso
     `scroll=ft.ScrollMode.AUTO`, l'intera schermata di creazione è un unico form scrollabile). Due regioni
     scrollabili annidate = il trascinamento sopra la lista di card viene sempre catturato dalla lista (la più
     vicina al dito), mai dal contenitore esterno — bug di "nested scroll" classico, aggravato su tablet dove non
     c'è una scrollbar visibile da afferrare fuori dalla lista per "bucare" verso lo scroll esterno. Flet 0.85.3
     non espone un equivalente del "NestedScrollView" nativo (nessuna fisica "scrolla la lista solo se non è già al
     limite, altrimenti passa lo scroll al genitore") — l'unica soluzione robusta è eliminare la seconda regione
     scrollabile.
  **Fix**: `CardPicker.control` ora è una `ft.Column(spacing=4)` senza `scroll` e senza `height` fissa — si
  dimensiona naturalmente al contenuto, esattamente come ogni altra sezione-lista già presente nel progetto (es.
  `_section_spell_list`/`_section_extra_spell_list` in `spells_view.py`, mai avute uno scroll proprio), diventando
  parte della stessa, unica regione scrollabile del contenitore che la ospita. Parametro `height` rimosso dalla
  firma di `CardPicker.__init__` e da tutte le ~24 chiamate nel progetto (`profilo_tab.py`, `wizard_view.py`,
  `manual_form.py`, `spells_view.py`) — inclusi 2 casi con altezza calcolata dinamicamente (`height=min(260, 60 +
  46 * len(available_mm))` per Metamagia, `height=min(300, 60 + 46 * len(available_inv))` per Suppliche Occulte),
  anch'essi rimossi (la formula era solo un tentativo di dimensionare la vecchia viewport fissa, superfluo ora che
  la Column si dimensiona da sola).
  **Unico punto che richiedeva una modifica strutturale aggiuntiva**: il dialog "Aggiungi Incantesimo Bonus" in
  `spells_view.py`, dove il CardPicker era l'UNICA regione scrollabile del dialog (il Column del dialog non
  scrollava affatto, `tight=True`, dimensionato solo dal contenuto) — rimuovendo lo scroll del CardPicker lì
  dentro, un elenco di 215 incantesimi (es. Mago) avrebbe reso il dialog assurdamente alto e privo di scroll. Fix:
  spostato lo scroll sul Column del dialog stesso (`scroll=ft.ScrollMode.AUTO`) con un contenitore a dimensione
  fissa (`width=340, height=460`), stesso pattern già in uso in tutti gli altri dialog del progetto — la regola
  resta quindi universale e senza eccezioni: **CardPicker non scrolla mai se stesso, è sempre il contenitore che lo
  ospita a farlo**.
  **Bug di uno script di migrazione trovato e corretto durante l'implementazione** (non nella richiesta originale):
  la rimozione meccanica di `height=` dalle ~24 chiamate è stata fatta con uno script Python (parsing a
  bilanciamento di parentesi, poi cancellato — non fa parte del codice dell'app), ma un primo giro ha mancato 7
  chiamate per due motivi distinti — 5 erano scritte su una singola riga (`CardPicker(options=x, height=240)`,
  senza andare a capo) e non corrispondevano al pattern regex "riga propria" cercato dallo script; le altre 2
  (Metamagia/Suppliche Occulte) usavano un'espressione con una virgola INTERNA (`height=min(260, 60 + 46 *
  len(available_mm))`), che troncava erroneamente il match della regex al primo comma trovato (quello dentro
  `min(...)`, non quello di fine argomento) lasciando la riga intatta. Scoperto SOLO grazie ai test end-to-end
  (istanziando davvero il dialog di level-up per tutte le 12 classi + scenari mirati Warlock lv4→5/Stregone lv2→3
  per toccare gli step INVOCATION/METAMAGIC), non dalla sola compilazione — un `python3 -m py_compile` da solo non
  basta a intercettare un `TypeError` che scatta solo a runtime quando quello specifico step del level-up viene
  effettivamente costruito. Corretti tutti e 7 manualmente; una nuova scansione finale (script dedicato a
  bilanciamento di parentesi, non regex) ha confermato **zero** occorrenze residue di `height=` in qualunque
  chiamata `CardPicker(...)` di tutto il progetto.
  **Verificato** con test end-to-end (DB temporaneo isolato, mai quello reale): `CardPicker` isolato —
  `control.scroll is None`, `control.height is None`, badge "0"/"Lv1" presenti nell'albero controlli renderizzato;
  dialog di level-up per tutte le 12 classi PHB (Lv2→3) — il content Column del dialog scrolla ancora
  (`ScrollMode.AUTO`), **nessuna** colonna interna (incluse tutte le istanze CardPicker annidate) ha uno scroll
  proprio; scenari mirati Warlock Lv4→5 (Suppliche Occulte, CardPicker multi-select) e Stregone Lv2→3 (Metamagia,
  CardPicker multi-select) — stesso esito; dialog "Aggiungi Incantesimo Bonus" (Guerriero non incantatore) — il
  Column del dialog ora scrolla con `height=460`, il CardPicker interno non ha più scroll proprio. `python3 -m
  compileall`/`pyflakes` puliti su `ui/widgets.py`, `spells_view.py`, `profilo_tab.py`, `wizard_view.py`,
  `manual_form.py` (solo il rumore preesistente di `from config.settings import *`).

- **Bug fix: livello massimo incantesimi preparabili non filtrato dagli slot posseduti (2026-07-16, stesso
  giorno)** — bug report di Davide (verbatim): "L'aumento del livello mi mostar tutti gli incantesimi, invece
  teoricamente dovrebbe mostrarmi solo gli incantesimi che posso imparare, quindi come spiegato nel libro di ogni
  classe il livello massimo degli incantesimi imparati corrisponde al livello dello slot incantesimo più alto
  posseduto dall'incantatore, quindi se ho 3 slot liv 1 2 liv 2. e 1 liv 3 il massimo che posso imparare è un
  incantesimo di livello 3. questo non viene gestito bene da quello che vedo, controlla".
  **Analisi**: prima di correggere qualcosa ho letto per intero `core/level_manager.py` (`_max_spell_level_for()`,
  usata da `get_level_up_steps()` per gli step `SPELL_LEARN`/`SPELL_SWAP` delle classi "know" e per i Segreti
  Magici del Bardo) e i rami
  `SPELL_LEARN`/`SPELL_SWAP`/`ARCANUM_SPELL`/`BORROWED_SPELL_LEARN`/`BORROWED_SPELL_SWAP` in `profilo_tab.py` —
  tutti già filtrano correttamente `0 < livello <= max_lv` (confermato: le soglie PHB in `_max_spell_level_for()`
  per bardo/stregone/warlock/ranger combaciano esattamente con le rispettive tabelle di slot già verificate altrove
  in questo file, e `BORROWED_SPELL_LEARN` calcola `max_lv` direttamente dalla tabella `spell_progression` della
  sottoclasse, non dalla formula generica). Il vero bug non era quindi nel **level-up delle classi "know"**, ma
  nella **tab Incantesimi stessa, per i preparatori** (Chierico/Druido/Mago/Paladino) — il ramo `else` di
  `SpellsView._build()` (appena riorganizzato nel fix precedente di questa stessa giornata) iterava l'INTERO
  `self._class_spells` (fino al 9° livello) senza alcun filtro basato sugli slot incantesimo realmente posseduti
  dal personaggio: un Chierico di 3° livello (che possiede solo slot di 1° e 2°) vedeva comunque, e poteva
  tranquillamente "preparare" con un semplice click, incantesimi di 3°-9° livello mai lanciabili. Questa è
  esattamente la regola PHB citata da Davide ("il livello massimo... corrisponde al livello dello slot incantesimo
  più alto posseduto"), che si applica sia a chi "impara" (know classes, già corretto) sia a chi "prepara" ogni
  giorno dall'intera lista (dove però mancava del tutto l'enforcement).
  **Fix**: nuova `_max_preparable_spell_level(slots: list[SpellSlot]) -> int` in `spells_view.py` —
  `max((s.slot_level for s in slots if s.total > 0), default=0)`. Nel ramo preparatori di `_build()`, ogni
  incantesimo di livello > 0 viene escluso dalla lista se il suo livello supera questo massimo, **a meno che non
  sia già stato preparato in precedenza** (`self._is_prepared(nome, livello)`) — eccezione deliberata per non
  "intrappolare" un incantesimo già spuntato in uno stato non più togliibile dopo un level-down o un vecchio
  salvataggio precedente a questo fix: resta visibile solo per poterlo deselezionare, non per prepararne di nuovi
  allo stesso livello. I trucchetti (livello 0) restano sempre mostrati, coerente col fatto che non richiedono
  alcuno slot. Aggiunta anche una riga informativa nel banner "X / Y preparati" (`_section_prep_banner()`): "Lv.
  max preparabile: N°" (o "Nessuno slot incantesimo disponibile" se N=0, es. un Paladino di 1° livello prima di
  ottenere i primi slot al 2°), così il giocatore capisce subito perché alcuni livelli non compaiono, senza dover
  indovinare.
  **Verificato** con test end-to-end (DB temporaneo isolato, mai quello reale): Chierico Lv.3 (slot attivi
  1°×4/2°×2) — la UI mostra solo Trucchetti+1°+2°, **zero** voci di 3°-9° livello; Mago Lv.1 (solo slot 1°) —
  mostra solo Trucchetti+1°, **zero** voci di 2°-9°; Paladino Lv.1 (0 slot, half caster che inizia al 2° livello) —
  **zero** incantesimi di livello>0 mostrati, coerente col PHB; scenario di "grandfathering" — un Chierico con un
  incantesimo di 3° livello già preparato, poi con gli slot forzati artificialmente a un massimo di 1° (simulando
  un level-down/stato pregresso), continua a mostrare quell'incantesimo di 3° livello (così resta deselezionabile)
  pur non offrendone di nuovi allo stesso livello. Smoke test di regressione su tutte le 12 classi PHB × 5 livelli
  (1/3/5/9/20) — 0 eccezioni. `python3 -m compileall`/`pyflakes` puliti su `spells_view.py` (solo il rumore
  preesistente di `from config.settings import *`).

- **Frenesia automatica (Berserker) + Stile di Combattimento/Suppliche Occulte in Combattimento (2026-07-19)** —
  risolti i due punti 8 e 9 rimasti in sospeso dal bug report del 2026-07-17 (vedi TODO "Priorità Bassa / v2" più
  sopra), tramite due domande dirette a Davide via `AskUserQuestion` prima di scrivere codice, come da procedura
  del progetto per le scelte di design non deducibili a priori.

  **Punto 8 — risposta di Davide: "Automatico".** Verificato il testo esatto della feature "Frenesia" in
  `barbaro.json` (già auditata, invariata): *"Il barbaro può entrare in frenesia quando entra in ira. Se lo fa, per
  la durata della sua ira può effettuare un singolo attacco con un'arma da mischia come azione bonus in ognuno dei
  suoi turni successivi dopo di questo. Quando la sua ira termina, il barbaro subisce un livello di
  indebolimento."* — l'Indebolimento **non** è automatico ad ogni uso di Furia: è condizionato all'aver dichiarato
  la Frenesia per quell'ira specifica (a differenza, per esempio, di "Aure Migliorate" del Paladino o di altre voci
  puramente narrative già documentate in questo file). Prima di questo fix l'app non tracciava affatto uno stato
  "ira in corso"/"frenesia dichiarata" — la risorsa "Furia" (`class_resources`) traccia solo il numero di usi
  rimasti per riposo, mai se l'ira attualmente in corso sia stata dichiarata in frenesia. Automatizzare fedelmente
  la regola ha richiesto quindi introdurre per la prima volta questo stato, non solo agganciare un incremento a un
  evento già esistente (nessun evento "fine ira" esisteva prima).

  **Modello dati**: nuovo `Character.frenzy_active: bool = False` (`data/models.py`) — vive finché il giocatore non
  segnala la fine dell'ira frenetica. Colonna `characters.frenzy_active INTEGER DEFAULT 0` via `_add_column()`
  idempotente in `data/database.py`. `character_repo.py`: `_row_to_character()`/`create()`/`update()` estesi a
  leggere/scrivere il campo (stessa lista colonne INSERT/UPDATE — stesso tipo di bug già capitato in passato con
  `dragon_ancestry`/`fighting_style`/ecc. se dimenticato in una delle due liste, verificato esplicitamente con un
  test di round-trip dedicato che il campo sopravvive sia a `create()` sia a un `update()` generico).

  **Due nuove funzioni repository**, entrambe no-op per qualunque personaggio non Barbaro (nessun impatto sulle
  altre 11 classi): `update_frenzy_state(character_id, active)` — semplice setter, usato sia per "Dichiara
  Frenesia" sia per "Annulla dichiarazione" (correzione di un click accidentale, senza Indebolimento);
  `end_frenzy_rage(character_id, current_exhaustion)` — scrittura **atomica** (unica connessione/commit) che azzera
  `frenzy_active` E incrementa `exhaustion_level` di 1 (clampato a 6) nello stesso statement SQL, per evitare uno
  stato intermedio inconsistente se una delle due scritture fallisse da sola; ritorna il nuovo livello di
  Indebolimento o `None` in caso di errore.

  **UI** (`combattimento_tab.py`, dentro "Risorse di Classe", subito dopo la riga "Furia" — visibile solo se
  `class_name=="Barbaro"` e `"berserker" in subclass.lower()`, stesso pattern di riconoscimento sottoclasse via
  substring case-insensitive già usato altrove nel progetto per Totem/Terreno): nuova `_section_frenzy()`, due
  stati:
  - **Non dichiarata**: chip grigio "Frenesia: dichiara per questa Ira" → click → `_on_declare_frenzy()` (nessun effetto immediato, solo segna lo stato).
  - **Dichiarata**: chip rosso "Frenesia attiva — Termina Ira (+1 Indebolimento)" → click → `_on_end_frenzy()` (un
    solo click applica `end_frenzy_rage()` e aggiorna la UI — questa è l'automazione richiesta: nessun bisogno di
    aprire la sezione Indebolimento e incrementarla a mano), più un `TextButton` secondario "Annulla dichiarazione
    (senza Indebolimento)" → `_on_cancel_frenzy()` per correggere un click accidentale sul primo passo.

  **Punto 9 — risposta di Davide: "Solo consultazione in Combattimento".** Stesso principio già stabilito per
  Abilità di Classe/Tratti di Razza (sezioni di sola lettura che leggono dagli stessi dati, senza spostare la
  scelta): la scelta di Stile di Combattimento resta assegnata in Profilo al level-up (`character.fighting_style`),
  le Suppliche Occulte restano assegnate in Profilo (`character_proficiencies`, `proficiency_type="invocation"`) —
  **nessuna duplicazione della fonte di verità**, solo due nuove sezioni in Combattimento che leggono lo stesso
  dato.

  **`GameDataLoader`**: nuovo `get_invocation(name)` — risolve una singola Supplica Occulta per nome esatto
  case-insensitive (stesso pattern di `get_weapon()`/`get_armor_item()`), usato per recuperare la descrizione
  completa di ciascuna supplica posseduta senza rifiltrare l'intera lista per livello.

  **UI** (`combattimento_tab.py`): due nuove sezioni, inserite subito dopo "Tratti di Razza" e prima di "Abilità Speciali" —
  - **"Stile di Combattimento"** (`_section_fighting_style()`, visibile solo se `character.fighting_style` è
    valorizzato — quindi mai per un Guerriero Lv.1 che non l'ha ancora scelto, anche se la feature base "Stile di
    Combattimento" resta comunque visibile come riga cliccabile nella sezione "Abilità di Classe" già esistente,
    invariata): riga singola cliccabile (icona + nome stile), click → dialog con la descrizione completa risolta
    via `GameDataLoader.get_fighting_style_data(class_name)` (già esistente dal 2026-07-16, include già la
    risoluzione Paladino/Ranger→lista canonica del Guerriero).
  - **"Suppliche Occulte"** (`_section_invocations()`, visibile solo se il personaggio possiede almeno una riga
    `proficiency_type="invocation"` — quindi mai per un Warlock Lv.1 prima del 2° livello, quando ottiene la prima
    supplica): lista di righe cliccabili, una per supplica posseduta, ordinate alfabeticamente, ciascuna con dialog
    descrizione completa via `get_invocation()`.

  **Verificato** con una batteria di test end-to-end (DB temporaneo isolato via `tempfile.mkdtemp()`+`HOME` separato, mai il DB reale di Davide):
  - **Repository/loader in isolamento**: round-trip di `frenzy_active` tramite
    `create()`→`get_by_id()`→`update_frenzy_state(True)`→`get_by_id()`→`update_frenzy_state(False)`→`get_by_id()`;
    `end_frenzy_rage()` da Indebolimento 0→1 (azzera anche `frenzy_active`) e clamp a 6 (6→6, non 7); `update()`
    generico su un personaggio con `frenzy_active=True` preserva il campo (prova diretta contro il tipo di bug già
    capitato in passato su altri campi); `get_invocation("Armatura delle Ombre")` risolve correttamente
    name+description, un nome inesistente ritorna `None`; `get_fighting_style_data("Paladino")` non include mai
    "Tiro" (esclusivo del Ranger) e la descrizione di "Duellare" combacia esattamente con quella canonica del
    Guerriero.
  - **UI, scenari mirati**: Barbaro Cammino del Berserker Lv.3 — chip "dichiara" presente, "attiva" assente,
    all'inizio; dopo `_on_declare_frenzy()` il chip passa a "attiva" (verificato anche ricaricando il personaggio
    dal DB, non solo lo stato in memoria); dopo `_on_end_frenzy()` l'Indebolimento sale di 1 e `frenzy_active`
    torna `False`, sia in memoria sia sul DB. Barbaro Cammino del Totem Guerriero — nessuna traccia di "Frenesia"
    in tutto l'albero controlli (conferma che la sezione non compare per la sottoclasse sbagliata). Guerriero Lv.5
    con `fighting_style="Duellare"` — sezione "STILE DI COMBATTIMENTO" presente con "Duellare" cliccabile; click
    sulla riga apre un `AlertDialog` con titolo "Duellare" e corpo non vuoto (dialog pilotato con un `FakePage`
    minimale, stesso pattern già consolidato nel progetto per testare dialog Flet senza un vero client). Guerriero
    Lv.1 senza `fighting_style` ancora scelto — la sezione dedicata NON compare (verificato distinguendo
    esplicitamente dalla riga feature "Stile di Combattimento" già esistente in "Abilità di Classe", che invece
    resta visibile come sempre — le due cose condividono lo stesso testo ma provengono da sezioni distinte, il test
    iniziale aveva erroneamente confuso le due finché non è stato corretto per cercare il testo in maiuscolo
    `.upper()` prodotto da `section_header()`). Warlock Lv.5 con 2 Suppliche Occulte assegnate a mano
    (`_save_single_proficiency`) — sezione "SUPPLICHE OCCULTE" presente con entrambi i nomi; Warlock Lv.1 senza
    suppliche — sezione assente.
  - **Regressione generale**: tutte le 12 classi PHB × tutte le sottoclassi reali × livelli 1/5/20 (build completa
    di `CombattimentoTab`) — **0 eccezioni**. `python3 -m compileall` sull'intero albero sorgente (esclusi
    `build/`/`__pycache__/`) — 0 errori. `pyflakes` su `data/models.py`, `data/database.py`,
    `data/repositories/character_repo.py`, `data/game_data/game_data_loader.py`,
    `ui/views/character_sheet/combattimento_tab.py` — 0 errori genuini (solo il rumore preesistente di `from
    config.settings import *` più lo stesso `f-string is missing placeholders` preesistente e non toccato, già
    segnalato in una nota precedente).

- **Audit responsivo completo dell'app — header/toolbar/dialog che vanno in overflow su finestre strette/smartphone
  (2026-07-24)** — bug report di Davide con screenshot (Modalità Master → tab Incontri, riga pulsanti header
  troncata): *"lo spazio dei pulsanti in alto non è gestito bene, tutto l'interfaccia si deve sempre adattare alla
  finestra, conta che deve essere usato anche per smartphone, e questo vale per tutto non solo per la modalità
  master"* — segnalazione esplicitamente estesa a **tutta l'app**, non solo alla Sezione Master dove era stata
  notata.

  **Causa radice**: `ft.Row([...])` in Flet 0.85.3, con più
  `ElevatedButton`/`OutlinedButton`/`TextButton`/`IconButton` come figli, **non va mai a capo né scrolla da sola**
  — su finestre strette o schermi da smartphone i controlli in eccesso vengono tagliati visivamente dal contenitore
  invece di riorganizzarsi. Confermato essere lo stesso bug in almeno 17 punti diversi dell'app (header di sezione,
  toolbar, righe di azione nei dialog), non un caso isolato della Sezione Master.

  **Scope della sessione, deciso da Davide via `AskUserQuestion`**: offerte 3 opzioni ("Solo gli header più critici
  ora" / "Audit completo di tutta l'app ora" / "Solo Home per ora") — **scelta esplicita: "Audit completo di tutta
  l'app ora"**. Eseguita quindi una ricognizione sistematica (agente Explore) su tutta la UI, che ha catalogato
  ogni `ft.Row` multi-pulsante non protetta in 25 file, poi corretti tutti i punti a rischio HIGH/MEDIUM con due
  pattern coerenti, scelti in base al contesto:

  1. **Menu overflow `ft.PopupMenuButton`** — per gli header di sezione/titolo, dove "andare a capo" avrebbe reso
     il layout brutto (icone sparse sotto il titolo). Un solo pulsante-pillola (icona+etichetta, stile coerente col
     tema) che non può MAI andare in overflow qualunque sia la larghezza della finestra o il numero futuro di
     azioni. Nota tecnica: `ft.PopupMenuItem.__init__` accetta `content: Union[str, Control, None]`, **non**
     `text=` (verificato con `inspect.signature()` dopo un primo tentativo errato).
     - `ui/views/master/master_view.py` — i 4 `OutlinedButton` header (Genera Tesoro/Genera Trappola/Malattie e
       Veleni/Incontri per Ambiente) sostituiti da un unico `PopupMenuButton` "Strumenti" (icona `BUILD_OUTLINED`);
       titolo racchiuso in `Container(expand=True)`.
     - `ui/views/master/master_encounter_view.py` — tenuto inline solo `ElevatedButton "Prossimo Turno"` (l'azione
       usata di continuo durante il combattimento), "Difficoltà"/"Termina Incontro" spostati in un
       `PopupMenuButton` (icona `MORE_VERT`).
     - `ui/views/home_view.py` — rimossi `_master_mode_button()`/`_import_character_button()` come pulsanti
       autonomi, sostituiti da un nuovo `_more_menu()` (voce "Modalità Master" solo se `on_open_master` è passato,
       "Importa personaggio" sempre presente); resta inline solo il CTA primario "Nuovo Personaggio".

  2. **`wrap=True`** — per toolbar e righe di azione nei dialog, dove andare a capo su più righe è visivamente accettabile. Aggiunto un nuovo helper condiviso in `ui/widgets.py`:
     ```python
     def wrap_dialog_actions(buttons: list[ft.Control]) -> list[ft.Control]:
         return [ft.Row(buttons, wrap=True, alignment=ft.MainAxisAlignment.END, spacing=8)]
     ```
     necessario perché `AlertDialog.actions=` **non va mai a capo da sola** in Flet (è renderizzata internamente
     come Row rigida) — passare `wrap_dialog_actions([...])` invece della lista piatta di pulsanti preserva
     l'aspetto a riga singola allineata a destra su schermi larghi, permettendo l'a-capo su schermi stretti.
     Applicato a: `combattimento_tab.py` (dialog "Bonus CA Temporaneo"), `inventario_tab.py` (dialog "Capacità di
     Trasporto"), `esplorazione_tab.py` (dialog "Percezione Passiva"), `spells_view.py` (dialog "Limite
     Preparazione"), `master_npc_list_view.py` (dialog dettaglio NPC, 4 azioni).
     `wrap=True` diretto (nessun dialog coinvolto) applicato a: `combattimento_tab.py` (riga rapida movimento,
     rimosso anche lo spacer `Container(expand=True)` — incompatibile con `wrap=True`, i figli flex non si
     comportano in modo prevedibile in un `Wrap` Flutter), `dice_view.py` (riga Normale/Vantaggio/Svantaggio; riga
     spinner Numero Dadi/Modificatore, rimosso anche un `VerticalDivider` che sarebbe apparso orfano andando a
     capo), `diary_view.py` (barra azioni modalità lettura: "← Precedente"/"Successiva →" convertiti in
     `IconButton` compatti, "Modifica"+elimina raggruppati in una Row interna non-wrap, `alignment=SPACE_BETWEEN`
     al posto degli spacer `expand=True`), `profilo_tab.py` (riga pulsanti level up/down, già ridotti a icona+testo
     breve in una sessione precedente).
     Rifinitura complementare in `maps_view.py`: titoli header (`Text(gm.name, expand=True)`) senza alcuna gestione
     di overflow — aggiunti `no_wrap=True, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS` (sia nel dettaglio mappa
     sia nell'overlay fullscreen) così un nome mappa lungo tronca con "…" invece di spingere fuori schermo le icone
     accanto.

  **Verificato**: `python3 -m compileall -q -x '^\./build/' .` sull'intero albero sorgente — 0 errori; `pyflakes`
  sui 13 file toccati in questa sessione (`ui/widgets.py`, `ui/views/home_view.py`,
  `ui/views/master/master_view.py`, `ui/views/master/master_encounter_view.py`,
  `ui/views/master/master_npc_list_view.py`, `ui/views/character_sheet/combattimento_tab.py`,
  `ui/views/character_sheet/inventario_tab.py`, `ui/views/character_sheet/esplorazione_tab.py`,
  `ui/views/character_sheet/profilo_tab.py`, `ui/views/spells_view.py`, `ui/views/diary_view.py`,
  `ui/views/dice_view.py`, `ui/views/maps_view.py`) — **0 errori nuovi**, l'unico residuo è lo stesso `f-string is
  missing placeholders` già noto e fuori scope a pag. 2989 di `combattimento_tab.py` (non toccato, non introdotto
  da questa sessione). `HomeView` verificato con test dedicato: esattamente 1 voce nel menu "Altro" quando
  `on_open_master` non è passato, 2 quando lo è (comportamento nascosto-se-assente preservato identico a prima).

  **Deliberatamente fuori scope in questa prima passata** (identificati dalla ricognizione ma non ancora toccati,
  perché richiedono una decisione di design a sé, non un semplice "aggiungi wrap") — **tutti e 3 risolti nello
  stesso giorno, subito dopo, su richiesta di Davide "vai procedi adesso"**, vedi voce dedicata subito sotto:
  - `wizard_view.py`/`manual_form.py` — footer di navigazione a 2 pulsanti (`ghost_button()`/`primary_button()`),
    alcune etichette lunghe ("Personalizza e continua") rischiose su schermi molto stretti.
  - `master_treasure_dialog.py`/`master_traps_dialog.py` — dialog a **larghezza fissa** (`width=420`).
  - `ui/app.py` — la sidebar di navigazione principale, ipotizzata fissa lateralmente su schermi smartphone-width.

- **Seguito dello stesso giorno (2026-07-24) — footer wizard/form, larghezza dialog Master, verifica sidebar** —
  Davide: "vai procedi adesso", via libera esplicita sui 3 punti lasciati fuori scope sopra.

  1. **Footer wizard/form manuale** — gli 8 footer "Indietro/Continua" (o "Annulla/Continua"/"Crea personaggio") a
     2 pulsanti in `wizard_view.py` (4 punti) e `manual_form.py` (5 punti, incluso quello della card conferma
     classe in fase 1 non elencato nel giro precedente) sono `ft.Row(alignment=END, spacing=12)` senza `wrap`: su
     schermi molto stretti, un'etichetta lunga come "Personalizza e continua" (con icona) può eccedere la larghezza
     disponibile e mandare in overflow l'intera Row invece di andare a capo. Aggiunto `wrap=True` a tutti e 9 i
     punti (identico pattern già usato per le toolbar del giro precedente) — su schermi larghi il risultato resta
     identico (riga singola allineata a destra), su schermi stretti i due pulsanti si impilano.
  2. **Dialog Master a larghezza fissa** — oltre ai 2 file segnalati (`master_treasure_dialog.py`,
     `master_traps_dialog.py`), la stessa ricognizione aveva già individuato 2 dialog gemelli con lo stesso
     identico problema (`master_forest_encounters_dialog.py` width=420, `master_health_hazards_dialog.py`
     width=380+440) — stessa famiglia "dialog generatore/riferimento della Sezione Master", stesso bug, corretti
     insieme per coerenza (fixare 2 dei 4 dialog quasi identici e lasciarne 2 rotti sarebbe stata
     un'inconsistenza). Nuovo helper condiviso `ui/widgets.py → responsive_dialog_width(page, base_width,
     margin=32, min_width=260)`: ritorna `base_width` se `page.width` combacia o è più largo (comportamento
     identico a prima su desktop), altrimenti lo riduce fino a `min_width` lasciando `margin` px ai bordi — mai un
     dialog più largo dello schermo disponibile, mai più stretto di 260px (soglia di leggibilità). Applicato a
     tutte le 6 occorrenze `width=380/420/440` nei 4 file (inclusi i 2 sotto-dialog di dettaglio in
     `master_traps_dialog.py`/`master_health_hazards_dialog.py`, aperti al click su una card, non solo i 4 dialog
     principali).
  3. **Verifica sidebar (`app.py`)** — **la premessa del giro precedente era sbagliata**: rileggendo per intero
     `ui/app.py` prima di "riprogettarla", ho trovato che la sidebar è **già completamente responsive**, non un
     design fisso da rifare — `_MOBILE_BP = 600`, `_is_mobile()` (`page.width < 600`), `_build_bottom_nav()`
     (bottom navigation bar per mobile, le stesse 5 sezioni + "Cambia" della sidebar desktop, icone+etichette
     ridimensionate per schermi stretti), e `page.on_resize = self._on_page_resize` che ricostruisce l'intero
     layout (sidebar↔bottom-nav) dal vivo se la finestra attraversa la soglia dei 600px — nessuna nuova
     implementazione necessaria, solo una correzione della nota scritta in precedenza (probabilmente frutto di aver
     ispezionato solo `_build_nav_rail()` senza notare `_is_mobile`/`_build_bottom_nav`/`on_resize` nello stesso
     file).

  **Verificato**: `responsive_dialog_width()` testata in isolamento (375px→343px con base 420, clamp a 260 sotto i
  250px di finestra, `page.width=None`→fallback al valore fisso, 1200px→invariato); tutti e 4 i dialog principali
  (Genera Tesoro/Generatore Trappole/Incontri per Ambiente/Malattie e Veleni) istanziati end-to-end a 375px e
  1200px — larghezza del content sempre quella attesa in entrambi i casi; entrambi i sotto-dialog di dettaglio
  (scheda trappola, scheda malattia/veleno, aperti pilotando `on_click` sui controlli reali trovati nell'albero)
  confermati responsive allo stesso modo. Sidebar/bottom-nav verificata con
  `DnDApp._show_main_layout()`/`_on_page_resize()` istanziati via `object.__new__` + `FakePage` (bypass `__init__`,
  mai un vero client): a 375px produce `bottom_nav` + root `Column`; a 1280px produce `nav_rail` + root `Row`; un
  resize dal vivo che attraversa i 600px ricostruisce correttamente il layout; un resize che non attraversa la
  soglia non tocca nulla. `python3 -m compileall -q -x '^\./build/' .` sull'intero albero sorgente — 0 errori;
  `pyflakes` su tutti gli 8 file toccati in questo seguito (`ui/widgets.py`, `ui/app.py`,
  `ui/views/creation_wizard/wizard_view.py`, `ui/views/creation_wizard/manual_form.py`, i 4 dialog Master) — 0
  errori nuovi.

  **Con questo si chiudono tutti e 3 i punti lasciati fuori scope dal giro precedente** — l'audit responsivo
  dell'app è ora completo su tutta la superficie individuata dalla ricognizione iniziale (header, toolbar, dialog
  actions, footer di creazione personaggio, dialog a larghezza fissa, navigazione principale).

- **Redesign header Sezione Master — da menu a tre puntini a barra di pillole sempre visibili (2026-07-24, stesso
  giorno, feedback estetico di Davide)** — seguito diretto dell'audit responsivo appena sopra, che aveva introdotto
  in `master_view.py` un `PopupMenuButton` "Strumenti" (icona `BUILD_OUTLINED`+testo, tendina con le 4 voci Genera
  Tesoro/Genera Trappola/Malattie e Veleni/Incontri per Ambiente) e in `master_encounter_view.py` un
  `PopupMenuButton` con icona nuda `MORE_VERT` (i "tre puntini") per le 2 azioni Difficoltà/Termina Incontro.
  Davide ha dato un feedback estetico esplicito, stesso giorno: *"l'unico modo è mettere i tre pallini per mostare
  la tendina? non si può fare qualcosa di più bello da vedere e abbellire anche la sezione master, ovviamente
  sempre in modo che venga visualizzato bene anche da smartphone"*.

  Prima di scrivere codice, mostrate a Davide (mockup in stile schermo telefono, con la vera palette dell'app —
  pergamena `#f5f0e8`, crimson `#c0182c`, header scuro `#1a0808`) 3 alternative concrete al menu a tre puntini:
  **A** — barra icone sempre visibile (pillole icona+etichetta sotto il titolo, vanno a capo su schermi stretti);
  **B** — griglia di card "strumenti" nel contenuto (tipo pannello di controllo, sempre visibile sopra le tab);
  **C** — pulsante flottante a ventaglio (FAB stile speed-dial, si apre solo quando serve). **Davide ha scelto
  esplicitamente l'opzione A** ("Scelgo l'opzione A: barra icone sempre visibile che va a capo").

  **`ui/views/master/master_view.py`**: rimosso interamente `_build_tools_menu()` (il `PopupMenuButton` "Strumenti"
  con 4 `PopupMenuItem`) e il suo helper `_menu_row()`. L'header ora contiene solo back-arrow + icona castello +
  titolo (in un `Container(expand=True)` per l'ellissi su schermi stretti) — nessun pulsante azione più nell'header
  stesso. Nuova `_build_tools_row()`: una `ft.Container` a parte, sotto l'header, con una `ft.Row(pills, spacing=8,
  wrap=True)` per le 4 pillole (Tesoro/Trappola/Veleni/Ambiente), su sfondo `COLOR_BG_PRIMARY` con bordo inferiore
  — inserita in `_build()` tra `header` e `_build_tab_bar()`. Nuova `_tool_pill(icon, label, on_click)`
  (staticmethod): `ft.Container` pillola (bordo crimson 1px, `border_radius=16`, sfondo `COLOR_BG_TAB_ACTIVE`,
  icona+testo crimson 12px bold, `ink=True`) — stesso principio "pillola sempre visibile" già usato altrove nel
  progetto (es. i chip di stato), qui applicato per la prima volta a un gruppo di azioni di navigazione.
  `wrap=True` sulla Row delle pillole: su schermi stretti (smartphone) vanno semplicemente a capo su più righe, mai
  tagliate fuori dal bordo — stesso principio già stabilito nell'audit responsivo di poche ore prima, qui applicato
  in sostituzione del `PopupMenuButton` invece che come toppa sopra di esso.

  **`ui/views/master/master_encounter_view.py`** (stesso bug/pattern, stessa richiesta di Davide estesa
  esplicitamente da lui a "tutta la sezione master"): rimosso il `PopupMenuButton` con icona nuda `MORE_VERT` (le 2
  voci Difficoltà/Termina Incontro) da `_build_header()`. L'header, prima un'unica `ft.Row` (back+titolo+spacer
  `expand=True`+menu+spacer+pulsante "Prossimo Turno"), è stato diviso in due righe dentro la stessa `ft.Column`:
  la prima riga resta back-arrow + titolo/round; una seconda riga nuova contiene le 2 pillole azione (Difficoltà,
  Termina Incontro) più il pulsante "Prossimo Turno" (rimasto `ElevatedButton` pieno crimson, l'unica azione usata
  di continuo durante il combattimento) — anch'essa con `wrap=True, spacing=8`. Nuova `_action_pill(icon, label,
  color, on_click)` (staticmethod): stessa forma a pillola di `master_view.py` ma con colore parametrico (blu
  `COLOR_ACCENT_BLUE` per "Difficoltà", `COLOR_TEXT_SECONDARY` per "Termina Incontro" — stessa distinzione
  cromatica già presente nelle vecchie voci di menu, preservata) e sfondo `COLOR_BG_CARD` invece di
  `COLOR_BG_TAB_ACTIVE` (per distinguerla visivamente dal contesto della tab bar, non pertinente in questa vista).
  Rimosso lo spacer `ft.Container(expand=True)` tra titolo e azioni (lo stesso identico motivo già documentato in
  una nota precedente di questo file per la riga movimento di `combattimento_tab.py`: `Container(expand=True)` è
  incompatibile con `wrap=True` nello stesso Row, i figli flessibili non si comportano in modo prevedibile in un
  Wrap — sostituito dallo split in due righe separate, non da un `alignment=SPACE_BETWEEN`). Rimosso l'import ormai
  inutilizzato `cast` da `typing` (non più usato nel file dopo la rimozione del `cast(list[ft.PopupMenuItem],
  [...])`).

  **Verificato** con test end-to-end (bypass `__init__`/`object.__new__`, `FakePage` minimale, scansione ricorsiva
  dell'albero controlli — stesso pattern già consolidato nel progetto per testare Flet senza un vero client):
  `MasterView` istanziata — zero `ft.PopupMenuButton` residui nell'intero albero, tutte e 4 le etichette pillola
  (Tesoro/Trappola/Veleni/Ambiente) presenti, esattamente 1 `ft.Row` con `wrap=True`;
  `MasterEncounterView._build_header()` con un `MasterEncounter` fittizio — zero `PopupMenuButton`, entrambe le
  etichette pillola (Difficoltà/Termina Incontro) presenti, il pulsante "Prossimo Turno" (`ElevatedButton`,
  contenuto verificato via `.content`, non `.text` — coerente con la nota già presente in questo file sulle API
  bottoni Flet 0.85.3) presente, 1 `ft.Row` con `wrap=True`. Wiring dei click verificato in due passi: (1)
  simulazione diretta del click su ciascuna delle 4 pillole di `MasterView` non montata — solleva
  `RuntimeError('Control must be added to the page first')`, comportamento atteso e non un bug (la property `page`
  di un controllo Flet non montato solleva sempre questa eccezione, non ritorna `None` — nessuna differenza
  rispetto al comportamento preesistente degli stessi handler quando erano invocati da un
  `PopupMenuItem.on_click`); (2) confermato che il wiring è comunque corretto usando
  `unittest.mock.patch.object(ft.Control, "page", new=FakePage())` (stesso bypass già documentato altrove in questo
  file per testare dialog Master senza un vero client) — tutte e 4 le pillole invocano correttamente la rispettiva
  funzione `show_*_dialog` quando il controllo risulta montato. Le 2 pillole di `MasterEncounterView` (i cui
  handler `_on_difficulty_click`/`_on_end_encounter_click` già gestivano `self._page is None` internamente,
  comportamento preesistente non toccato) eseguite senza eccezioni. `python3 -m compileall -q -x '^\./build/' .`
  sull'intero albero sorgente — 0 errori; `pyflakes` su entrambi i file — 0 errori (rimosso il solo import `cast`
  divenuto inutilizzato).

- **Coerenza visiva finale Sezione Master — `wrap_dialog_actions()` applicato agli 8 dialog rimasti indietro
  (2026-07-24, stesso giorno)** — seguito diretto del redesign header appena sopra: alla domanda se continuare a
  rifinire visivamente la Sezione Master, Davide ha risposto "si, abbelliamo" (rimandando esplicitamente a una
  sessione FUTURA, non questa, l'aggiunta delle immagini dei mostri alle card — quella parte resta fuori scope, non
  toccata qui).

  **Analisi preliminare, prima di scrivere codice**: letti per intero i 3 file delle viste della Sezione Master
  (`ui/views/master/master_npc_list_view.py`, `ui/views/master/master_encounter_list_view.py`,
  `ui/views/master/master_notes_view.py`) per capire cosa migliorare visivamente. Controllato anche `ui/theme.py`
  (`fantasy_card()`: bordo rosso rubino 3px in cima, pensato per card di SEZIONE/DETTAGLIO dentro una scheda) e
  `ui/views/feats_view.py` (compendio talenti: bordo grigio 1px `COLOR_BORDER` + `border_radius=8`, pensato per
  liste sfogliabili di card cliccabili verso un dettaglio — stesso identico stile già usato dalle card NPC/incontro
  della Sezione Master). **Conclusione**: le card NPC (`_npc_card()` in `master_npc_list_view.py`) e le card
  incontro (`_encounter_card()` in `master_encounter_list_view.py`) sono GIÀ coerenti con la convenzione visiva
  stabilita dall'app per questo ruolo di UI (lista sfogliabile → dettaglio) — `fantasy_card()` è riservato a un
  ruolo diverso (sezione/dettaglio dentro una scheda). Applicare `fantasy_card()`/bordo crimson a quelle card
  sarebbe stata un'imposizione arbitraria di uno stile pensato per un contesto diverso, non una vera correzione di
  un disallineamento — **nessuna modifica fatta in questa direzione**.

  **Disallineamento reale trovato**: `ui/widgets.py → wrap_dialog_actions(buttons: list[ft.Control]) ->
  list[ft.Control]` (introdotto durante l'audit responsivo di poche ore prima, stesso giorno — vedi la voce
  CLAUDE.md dedicata a quell'audit) avvolge una lista di pulsanti dialog in un'unica `ft.Row(buttons, wrap=True,
  alignment=ft.MainAxisAlignment.END, spacing=8)`, perché `ft.AlertDialog.actions=` in Flet 0.85.3 non va mai a
  capo da sola (è renderizzata internamente come una Row rigida). Durante quell'audit l'helper era già stato
  applicato a MOLTI dialog della Sezione Master (es. `_open_detail()` in `master_npc_list_view.py`, 4 azioni), ma
  **non a tutti** — 8 dialog a 2 pulsanti erano rimasti con la vecchia `actions=[...]` piatta, un'incoerenza
  stilistica/di robustezza segnalata ma non ancora risolta. Trovati e corretti tutti e 8, in 3 file:
  - `ui/views/master/master_npc_list_view.py` — 3 dialog: `_confirm_delete()` (conferma eliminazione NPC,
    Annulla/Elimina), `_open_add_to_encounter()` (dialog "Aggiungi a Incontro", Annulla/Aggiungi — non il dialog
    informativo a un solo pulsante, quello resta invariato), `_open_npc_form()` (dialog di salvataggio unificato
    creazione/modifica NPC, Annulla/Salva o Crea NPC).
  - `ui/views/master/master_encounter_list_view.py` — 2 dialog: `_confirm_delete()` (conferma eliminazione
    incontro, Annulla/Elimina), `_on_new_click()` (dialog "Nuovo Incontro", Annulla/Crea). Aggiunto il nuovo import
    `from ui.widgets import wrap_dialog_actions`.
  - `ui/views/master/master_notes_view.py` — 2 dialog: `_on_note_delete()` (conferma eliminazione voce,
    Annulla/Elimina), `_open_new_note_dialog()` (dialog "Aggiungi [voce]", Annulla/Crea). Qui gli `actions=` erano
    già scritti come `cast(list[ft.Control], [...])` (per Pylance, liste eterogenee) — sostituiti direttamente con
    `actions=wrap_dialog_actions([...])`, che ritorna già `list[ft.Control]` di suo, rimuovendo quindi il `cast`
    esplicito in questi 2 punti; l'import `cast` resta comunque necessario e usato altrove nel file (`did_mount()`,
    `cast(ft.Page, self.page)`), quindi non è stato toccato. Aggiunto il nuovo import `from ui.widgets import
    wrap_dialog_actions`.

  **Dialog deliberatamente lasciati invariati**: quelli a UN solo pulsante ("Chiudi" nel dialog informativo "nessun
  incontro disponibile" di `master_npc_list_view.py`, "Annulla" nel dialog di scelta "Nuovo dal Bestiario"/"Nuovo
  Manuale") — nessun rischio di overflow con un solo pulsante, coerente con la regola già scritta nel docstring di
  `wrap_dialog_actions()` ("con 1-2 pulsanti il comportamento è invariato").

  **Verificato**: `python3 -m py_compile` su tutti e 5 i file della Sezione Master (i 3 toccati sopra +
  `master_view.py`/`master_encounter_view.py`, invariati in questa sessione ma ricompilati per sicurezza) — 0
  errori; `pyflakes` sui 3 file toccati — 0 errori genuini (solo il rumore preesistente di `from config.settings
  import *`); script Python di conteggio automatico (grep sul sorgente) che conferma 4/2/2 = 8 occorrenze totali di
  `actions=wrap_dialog_actions([` nei 3 file rispettivamente, e zero occorrenze residue del vecchio pattern piatto
  `actions=[` seguito da una lista non avvolta.

- **Redesign header Home — stesso trattamento "barra di pillole" già applicato alla Sezione Master (2026-07-24,
  stesso giorno)** — seguito diretto del redesign header appena sopra: Davide, dopo aver visto il risultato in
  `master_view.py`/`master_encounter_view.py`, ha chiarito con un nuovo messaggio che la stessa richiesta valeva
  ANCHE per la schermata Home ("ok, ma la modifica era intesa anche per la homepage che ha quel menu a tendina con
  i tre pallini"). `ui/views/home_view.py` aveva infatti lo stesso identico pattern "tre pallini" (`_more_menu()`,
  `ft.PopupMenuButton(icon=MORE_VERT, ...)`), introdotto poche ore prima nella stessa giornata durante l'audit
  responsivo generale per risolvere l'overflow della fila di 3 pulsanti header ("Modalità Master"/"Importa
  personaggio"/"Nuovo Personaggio") su schermi stretti — la stessa toppa "menu a tendina" già sostituita nella
  Sezione Master andava quindi sostituita anche qui, per coerenza.
  **Fix**: rimosso interamente `_more_menu()` (il `PopupMenuButton` con icona `MORE_VERT` e i `PopupMenuItem`
  "Modalità Master"/"Importa personaggio"). L'header, prima un'unica `ft.Row` (logo + spacer
  `Container(expand=True)` + `_more_menu()` + spacer + `_new_character_button()`), è stato diviso in due righe
  dentro lo stesso `ft.Column` header — stesso identico pattern già usato lo stesso giorno in
  `master_encounter_view.py` per lo stesso motivo (`Container(expand=True)` incompatibile con `wrap=True` nella
  stessa Row, i figli flessibili non si comportano in modo prevedibile in un Wrap, regola già documentata in questo
  file). Prima riga: solo il logo "D&D" (`ft.Row([logo_widget], ...)`, nessuno spacer). Seconda riga, nuova:
  `ft.Row(self._header_actions(), spacing=8, wrap=True, ...)` — pillole azione + pulsante primario, va a capo su
  schermi stretti invece di traboccare.
  Nuovo metodo `_header_actions()` (sostituisce `_more_menu()`): ritorna la pillola "Modalità Master" (icona
  `CASTLE_OUTLINED`, `COLOR_ACCENT_BLUE`) SOLO se `self.on_open_master is not None` (stesso comportamento "nascosto
  se assente" del vecchio menu, per non rompere chiamate legacy a `HomeView` senza questo parametro), la pillola
  "Importa personaggio" (icona `UPLOAD_FILE`, `COLOR_ACCENT_GOLD`, sempre presente), e infine
  `self._new_character_button()` (il pulsante primario "Nuovo Personaggio", rimasto un `ElevatedButton` pieno oro
  invariato — stesso principio già stabilito in `master_encounter_view.py`: l'azione primaria/più frequente resta
  un bottone pieno, le secondarie diventano pillole). Nuovo staticmethod `_action_pill(icon, label, color,
  on_click)` — stessa identica forma a pillola (bordo colorato 1px, `border_radius=16`, sfondo `COLOR_BG_CARD`,
  icona+testo bold nello stesso colore, `ink=True`) già introdotta in `master_view.py`/`master_encounter_view.py`,
  replicata pari pari per coerenza visiva tra Home e Sezione Master, che ora condividono lo stesso linguaggio di
  pillola. L'import `cast` in `home_view.py` non è stato toccato: restava già usato altrove nel file in due punti
  non correlati (`cast(list[ft.Control], [...])`) anche dopo la rimozione dell'unico uso legato al vecchio
  `_more_menu()` (`cast(list[ft.PopupMenuItem], items)`).
  **Verificato**: `python3 -m py_compile` su `home_view.py` — 0 errori; `pyflakes` — solo il rumore preesistente di
  `from config.settings import *` (nessun errore genuino). Test end-to-end (istanziando `HomeView` per intero, con
  e senza `on_open_master` passato — gli errori "no such table: characters" stampati durante il test sono il rumore
  atteso già noto in questo ambiente sandbox, non correlati al fix): confermato **zero** `ft.PopupMenuButton`
  residui nell'albero; entrambe le etichette "Modalità Master" e "Importa personaggio" presenti quando
  `on_open_master` è passato; "Nuovo Personaggio" presente in entrambi i casi; **esattamente 1** `ft.Row` con
  `wrap=True` nell'intero albero (la nuova riga azioni); con `on_open_master` NON passato, "Modalità Master"
  correttamente assente mentre "Importa personaggio" resta presente (comportamento "nascosto se assente" preservato
  identico al vecchio menu).

- **Audit "nessuna azione nascosta" sulle 5 tab della scheda personaggio — 3 controlli senza indizio visivo
  esplicito trovati e corretti (2026-07-24, stesso giorno)** — Davide ha stabilito una linea guida generale e
  permanente per tutta l'app (verbatim): *"Una linea generale da seguire è che l'app deve essere facile e intuitiva
  senza nulla di nascosto, chi la vede deve già sapere cosa fare anche se non l'ha mai usata."* — principio
  catturato come memoria di progetto persistente (feedback ricorrente, non un fix una tantum). Alla richiesta di
  una valutazione onesta su quanto l'app rispettasse già questo standard, ho condotto un audit mirato sulle 5 tab
  della scheda personaggio (Profilo/Combattimento/Esplorazione/Inventario/Diario) cercando specificamente controlli
  cliccabili privi di un indizio visivo esplicito (icona, tooltip, colore, forma) che ne rivelasse l'interattività
  a un utente che non avesse mai usato l'app prima.

  **Esito dell'audit**: l'app risulta già in gran parte conforme — la stragrande maggioranza dei controlli
  cliccabili ha già icona matita "✎"/tooltip/bordo colorato dedicato (stessa convenzione "editabile" ormai
  consolidata in tutto il progetto, vedi le innumerevoli sezioni "✎ Modifica" già documentate sopra). Trovati
  esattamente **3 gap concreti**, tutti piccoli e localizzati, nessuno strutturale:

  1. **Cerchi valuta in Inventario** (`ui/views/character_sheet/inventario_tab.py → _section_monete()`): i 5 cerchi
     cliccabili MR/MA/ME/MO/MP (monete di rame/argento/electrum/oro/platino) avevano già `ink=True` (feedback
     visivo al click) ma **nessun `tooltip`** — l'unico indizio che fossero cliccabili era la forma "a moneta" e il
     bordo della card, nessun testo esplicito a chiarirlo. Fix: aggiunto un dict `names` (`"Monete di
     Rame"`/`"d'Argento"`/`"di Electrum"`/`"d'Oro"`/`"di Platino"`) e `tooltip=f"Modifica {names[abbr]}"` su
     ciascuno dei 5 `ft.Container`.

  2. **Mini stat bar in `ui/views/character_sheet/sheet_view.py`** — due punti distinti nello stesso file:
     - `_build_stat_bar()` (i 6 box caratteristica FOR/DES/COS/INT/SAG/CAR): avevano già `tooltip="Clicca per
       modificare le caratteristiche"` + `ink=True` + bordo card, ma **nessuna icona** — l'unico modo di scoprire
       che fossero cliccabili era passarci sopra col mouse (inutile su tablet/touch, dove l'app viene
       esplicitamente usata anche) o intuirlo dal solo bordo. Fix: aggiunta una `ft.Icon(ft.Icons.EDIT, size=9,
       color=COLOR_TEXT_MUTED)` accanto all'abbreviazione (FOR/DES/ecc.) in una Row dedicata, stessa convenzione
       "✎" già usata ovunque nel progetto per segnalare "editabile".
     - Il box "+N comp." dell'header (bonus competenza, override manuale): l'icona "✎" compariva **solo** quando il
       bonus era già in stato di override — un personaggio senza override attivo non aveva alcuna icona, solo il
       tooltip, nonostante il box fosse comunque cliccabile fin dall'inizio. Fix: `pb_label` riscritto da `ft.Text`
       a `ft.Row([testo, ft.Icon(EDIT, size=10, color=...)])` — l'icona matita ora è **sempre** presente (colorata
       blu se in override, grigio-muted altrimenti), coerente con la stessa convenzione appena applicata ai 6 box
       caratteristica.

  3. **Dialog "✎ Modifica Competenze" in `ui/views/character_sheet/profilo_tab.py → _on_edit_competenze()`**: le 24
     righe cliccabili (6 tiri salvezza + 18 abilità, ciclo ○→●→★→○ al click) avevano solo `ink=True`, nessun
     tooltip per riga — il dialog ha già una legenda in cima ("Tocca una riga per ciclare: ○ nessuna ● competente ★
     maestria"), che mitiga parzialmente il problema ma richiede di ricordarla mentre si scorre l'elenco, invece di
     avere l'indizio direttamente sulla riga stessa. Fix: aggiunto `tooltip="Clicca per ciclare: ○ nessuna → ●
     competente → ★ maestria"` a ciascuna delle 24 righe (nella funzione locale `make_row()`), sulla stessa
     `Container` che ha già `on_click=cycle, ink=True`.

  Tutti e 3 i fix sono coerenti con la linea guida generale ora stabilita da Davide (vedi memoria di progetto):
  nessuna azione nascosta, ogni controllo interattivo deve avere un indizio visivo esplicito (icona/tooltip/colore)
  comprensibile anche da chi non ha mai usato l'app.

  **Verificato** con una batteria di test end-to-end (DB temporaneo isolato via `tempfile.mkdtemp()`+`HOME`
  separato, mai il DB reale di Davide; bypass `__init__`, `FakePage` minimale, scansione ricorsiva dell'albero
  controlli — stesso pattern già consolidato nel progetto per testare Flet senza un vero client):
  `_section_monete()` — tutti e 5 i tooltip presenti e col testo esatto atteso ("Modifica Monete di
  Rame"/"d'Argento"/"di Electrum"/"d'Oro"/"di Platino"); `_build_stat_bar()` — esattamente 6 icone matita trovate
  nell'albero (una per box caratteristica); `_build_header_and_tabs()` — 1 icona matita trovata nel box bonus
  competenza (verificata presente sia con override attivo sia senza); dialog `_on_edit_competenze()` pilotato
  end-to-end — esattamente 24 tooltip trovati tra le righe (6 tiri salvezza + 18 abilità), tutti col testo atteso
  "Clicca per ciclare: ○ nessuna → ● competente → ★ maestria". `python3 -m py_compile`/`pyflakes` puliti su tutti e
  3 i file toccati (`inventario_tab.py`, `sheet_view.py`, `profilo_tab.py`) — solo il rumore preesistente di `from
  config.settings import *`, nessun errore genuino.

  Con questo si chiude la lista dei 3 gap emersi dall'autovalutazione onesta richiesta da Davide, in risposta diretta al suo nuovo principio guida sull'interfaccia sempre autoevidente.

- **Revisione 2026-07-26 · FASE 1 COMPLETATA — 12 bug corretti (B1-B12)** — prima fase del piano approvato (vedi la
  sezione "🗂 Revisione 2026-07-26" in cima a questo file e `dnd_app/docs/revisione_2026_07_26.md`). Nessuno di
  questi bug era noto prima dell'analisi: `compileall` e `pyflakes` erano già puliti su tutte le 45k righe, i
  problemi erano tutti semantici.

  **Regole verificate leggendo il PDF prima di correggere** (regola critica del progetto rispettata — `pdftoppm` +
  lettura visiva delle pagine, mai `pdftotext`/OCR né conoscenza pregressa). Due letture hanno cambiato il fix
  rispetto a quanto avevo progettato:
  - **PHB p.197** («Scendere a 0 Punti Ferita», «Morte Istantanea», «Tiri Salvezza Contro Morte», «Danni a 0 punti ferita»).
  - **PHB p.186** («Riposo Breve», «Riposo Lungo»).
  - **PHB p.291** (Appendice A, riquadro «Indebolimento»).

  **B1 — curare da 0 PF non azzerava i tiri salvezza contro morte** (`combattimento_tab.py → _on_heal_click`). PHB
  p.197: *«Il numero di entrambi i tipi torna a zero quando il personaggio recupera dei punti ferita o diventa
  stabile»* + *«Il personaggio riprende i sensi se recupera un qualsiasi ammontare di punti ferita»*. I pallini
  restavano segnati dopo la cura. Fix: azzeramento automatico solo quando si passa davvero da 0 a >0 PF (verificato
  che curare un personaggio già sopra 0 non tocca i pallini).

  **B2 — danno subito a 0 PF non aggiungeva fallimenti** (`_on_damage_click`). PHB p.197: *«Se un personaggio
  subisce danni quando ha 0 punti ferita, questo equivale a un tiro salvezza contro morte fallito. Se i danni
  provengono da un colpo critico, equivalgono a due tiri salvezza contro morte falliti»*. Aggiunta una **checkbox
  "Colpo critico"** nel dialog del danno (il dato non è deducibile: solo il giocatore sa se era un critico), clamp
  a 3.

  **B3 — morte istantanea per danno massiccio** mai implementata. PHB p.197: *«il personaggio muore se i danni
  rimanenti sono pari o superiori al suo massimo dei punti ferita»*. Attenzione al calcolo del **danno residuo**:
  se il personaggio è già a 0 PF il residuo è il danno intero, altrimenti è `danno − PF attuali`. Non esiste un
  campo "morto" nello schema: la morte è rappresentata come `death_saves_failure = 3`, la stessa condizione che la
  UI già mostra come morte. Testato con l'esempio numerico del manuale stesso (chierico 12 PF max, 6 attuali, 18
  danni → muore).

  Nota trasversale a B2/B3: ogni applicazione automatica di una regola mostra un **avviso esplicito** con la
  citazione della pagina (nuovo helper `_show_rule_notice()`), coerente con il principio "nulla di nascosto" —
  l'app non deve mai modificare la scheda in silenzio.

  **B4 — il riposo lungo non riduceva l'Indebolimento** (`_section_riposo_lungo`). PHB p.291: *«Completando un
  riposo lungo, una creatura riduce di 1 il suo livello di indebolimento, purché abbia anche avuto modo di mangiare
  e bere qualcosa»*. La clausola su cibo e bevande è una condizione reale del manuale, quindi è una **scelta del
  giocatore** (checkbox nel dialog, mostrata solo se l'Indebolimento è > 0), non un automatismo.

  **B4b — riposo lungo a 0 PF, trovato leggendo p.186** (non era nella lista originale): *«[il personaggio] deve
  possedere almeno 1 punto ferita all'inizio del riposo per ottenerne i benefici»*. Ora bloccato con un dialog che
  cita la regola, invece di concedere silenziosamente tutti i benefici a un personaggio morente.

  **B5 — il riposo lungo non azzerava `ca_bonus` né `frenzy_active`**: un bonus CA temporaneo
  (incantesimo/reazione) sopravviveva alla notte, e una Frenesia dichiarata per un'ira restava attiva dopo 8 ore di
  sonno.

  **B6 — forme selvatiche/evocazioni attive sopravvivevano al riposo lungo.** La funzione corretta **esisteva già
  ed era dead code**: `character_repo.deactivate_all_creatures()` (mai chiamata da nessun punto del progetto) — era
  esattamente il fix già scritto e mai collegato. Ora invocata dal riposo lungo (ripristina anche i PF della
  creatura). Caso limite noto e accettato: la Forma Selvatica di un druido di 20° livello durerebbe 10 ore, quindi
  potrebbe teoricamente attraversare un riposo di 8 — resta riattivabile con un click.

  **B7 — minimo sbagliato nel riposo breve**, e **la mia ipotesi iniziale era errata**: avevo progettato "il minimo
  va applicato per dado". Il manuale (p.186) dice invece: *«Il personaggio recupera un numero di punti ferita pari
  al totale (fino a un minimo di 0)»* — minimo **0 sul totale**. Il codice aveva `max(1, ...)`, corretto in `max(0,
  ...)`. Rilevante solo con modificatore di Costituzione negativo. È il tipo di errore che la regola "leggi sempre
  il PDF, non fidarti di ciò che sai" esiste proprio per intercettare.

  **B8 — polling di sincronizzazione di `HomeView`** (thread ogni 5 s, introdotto per le sessioni web multiple
  sullo stesso DB). Tre problemi in una sola funzione: (a) girava **anche su desktop e mobile**, dove la sessione è
  unica e il polling è puro spreco → ora parte solo se `page.web`, e da `did_mount()` (serve `self.page` per
  saperlo) invece che da `__init__`; (b) **ricostruiva l'intera lista ogni 5 secondi anche a vuoto** → nuova
  `refresh(force=False)` che confronta una firma `id:updated_at` di tutti i personaggi e ricostruisce solo se è
  cambiata (`page.update()` viene chiamato solo in quel caso); (c) **`break` su qualunque eccezione** → un DB
  momentaneamente bloccato uccideva la sincronizzazione per sempre, in silenzio; ora l'eccezione transitoria viene
  loggata e il ciclo continua (resta `break` solo per vista smontata/`RuntimeError`). Aggiunto anche un
  `threading.RLock` attorno alla ricostruzione della lista: il thread di polling e il thread della UI
  (eliminazione/import personaggio) toccano gli stessi controlli.

  **B9 — dialog di aggiornamento aperto da un thread non-UI** (`app.py → _start_update_check`). Il check HTTP in
  background va bene, ma `page.show_dialog()` mutava l'albero dei controlli fuori dal thread della UI. Fix:
  `page.run_task(self._show_update_banner_async, ...)` — verificato leggendo il sorgente di Flet che
  `Page.run_task` usa `asyncio.run_coroutine_threadsafe` sul loop della sessione, quindi è il modo corretto di
  rientrare nel thread della UI da un thread di background.

  **B10 — lo scroll tornava in cima ad ogni azione** (il difetto UX più fastidioso dell'app). Tutti i tab si
  aggiornano con `controls.clear() + _build() + update()`, cioè ricostruendo tutto ad ogni singola interazione
  (anche "−1 HP"): i controlli sono oggetti nuovi, quindi Flutter riparte da capo. Su Combattimento (21 sezioni)
  applicare un danno rimandava il giocatore all'inizio della pagina.
  Fix: nuova classe base **`ScrollMemoryListView`** in `ui/widgets.py` — si aggancia a `on_scroll` (evento già
  esposto da `ft.ListView`, campo `pixels`) per ricordare l'ultimo offset, e `restore_scroll()` lo riapplica dopo
  il rebuild. Adottata da tutte e 6 le viste `ListView` con refresh frequente: `CombattimentoTab`, `ProfiloTab`,
  `EsplorazioneTab`, `InventarioTab`, `DiarioTab`, `SpellsView`.
  ⚠️ **Trappola trovata durante il test, da ricordare**: `ScrollableControl.scroll_to()` in Flet 0.85.3 è una
  **coroutine** (`async def`, confermato con `inspect.iscoroutinefunction`). Chiamarla normalmente non fa **nulla**
  e produce solo un `RuntimeWarning: coroutine was never awaited` — il fix sarebbe stato finto. Va pianificata con
  `page.run_task(self.scroll_to, offset=..., duration=0)`. Il primo giro di test l'ha intercettata solo perché il
  warning è comparso nell'output.
  `scroll_interval` alzato da 10 ms (default) a 100 ms: per ricordare un offset non serve un evento per frame, e in web mode 10 ms significherebbe traffico websocket continuo durante lo scorrimento.
  **Limite onesto**: il ripristino è verificato a livello di logica (l'offset viene tracciato e `scroll_to` viene
  pianificato con i parametri giusti), ma **l'effetto visivo reale non è verificabile in questo ambiente** — serve
  un vero client Flutter. Il docstring di Flet avverte inoltre che `scroll_to` "è inefficace per controlli che
  costruiscono gli elementi dinamicamente" e `ListView.build_controls_on_demand` è `True` di default: se Davide
  dovesse constatare che lo scroll torna ancora in cima, il passo successivo è provare
  `build_controls_on_demand=False` su quelle viste.

  **B11 — `danger_button()` illeggibile** (`theme.py`): testo `COLOR_TEXT_PRIMARY` (`#1c1e2c`) su fondo crimson
  (`#c0182c`) = contrasto **2.68:1**, molto sotto la soglia AA di 4.5. Corretto in bianco (7.75:1). La funzione è
  oggi dead code, ma va corretta prima di riusarla nel restyle.

  **B12 — f-string senza placeholder** in `combattimento_tab.py` (unico warning pyflakes dell'intero progetto).

  **Verificato** con 4 batterie di test end-to-end (DB temporaneo isolato via `tempfile.mkdtemp()` + `HOME`
  separato, mai il DB reale di Davide; `FakePage` minimale + scansione ricorsiva dell'albero controlli per pilotare
  i veri dialog Flet — pattern già consolidato nel progetto):
  - **B1-B3** (11 controlli): cura da 0 PF che azzera i pallini; cura sopra 0 che NON li tocca; 1 fallimento per
    danno a 0 PF, 2 con la checkbox critico, clamp a 3 con avviso; morte istantanea; **l'esempio numerico del
    manuale** (12 PF max / 6 attuali / 18 danni); danno non massiccio che porta a 0 senza fallimenti; HP temporanei
    che assorbono per primi.
  - **B4-B7** (16 controlli): Indebolimento 3→2 con cibo, invariato senza; checkbox assente e nessun underflow a
    Indebolimento 0; riposo lungo bloccato a 0 PF col testo della regola e **zero benefici applicati**; `ca_bonus`
    e `frenzy_active` azzerati; forma selvatica attiva disattivata e PF ripristinati; HP/dadi vita (1 + metà di 8 =
    5)/TS morte; riposo breve con CON −2 che non cura ma spende comunque i dadi.
  - **B8-B9** (13 controlli): nessun thread su desktop, thread avviato/daemon/nominato/fermabile in web mode;
    `refresh(force=False)` che non ricostruisce a vuoto, rileva un personaggio nuovo E un `updated_at` cambiato da
    un'altra sessione; eccezione transitoria che non uccide il ciclo; dialog aggiornamento pianificato con
    `run_task` e mai aperto dal thread.
  - **B10** (20 controlli): offset tracciato, `pixels=None` che non lo azzera, `on_scroll` del chiamante non
    sovrascritto, `restore_scroll()` che non solleva su controllo non montato, e tutte e 6 le viste che ereditano
    dalla nuova base e pianificano `scroll_to` con l'offset corretto dentro il proprio `_refresh()`.
  - **Regressione generale**: 12 classi × 3 livelli (1/5/20) × 7 viste = **252 viste costruite senza eccezioni**;
    **760 combinazioni** classe × sottoclasse × livello 2-20 di `get_level_up_steps()` — 0 eccezioni. `python3 -m
    compileall` sull'intero albero (esclusi `build/`/`.venv/`) e `pyflakes` su tutti i file: **puliti**, zero
    warning residui (anche il rumore preesistente di B12 è sparito).

- **Revisione 2026-07-26 · FASE 2 COMPLETATA — pulizia di codice morto, file morti e duplicazione** — seconda fase del piano approvato.

  **2a · Codice morto rimosso** (ogni nome riverificato con `grep` DOPO le modifiche della Fase 1, non solo con `vulture`, per non cancellare qualcosa diventato vivo nel frattempo):
  - `ui/widgets.py` — `dropdown_with_info()` e le 4 `make_*_describe()` (~200 righe). Erano state lasciate "come
    helper generico riutilizzabile" dopo il passaggio al `CardPicker` del 2026-07-16, ma non hanno mai più avuto un
    chiamante. Le `format_*_body()` **restano**: sono usate dagli `*_card_options()`.
  - `ui/theme.py` — `danger_card`, `divider`, `stat_badge`, `gold_button`, `danger_button` (quest'ultimo era anche
    B11, contrasto 2.68:1). La Fase A del restyle sostituirà comunque queste primitive con
    `card()`/`chip()`/`pill()`/`stat_tile()`.
  - `config/settings.py` — `get_xp_for_level`, `get_level_from_xp`, `POINT_BUY_COSTS`/`POINT_BUY_BUDGET` (point buy
    mai implementato), `CURRENCIES`/`CURRENCY_NAMES`, `COLOR_BORDER_STRONG`/`COLOR_SLOT_USED`/`COLOR_NAV_TEXT`,
    `DB_NAME`.
  - `data/game_data/game_data_loader.py` — **15 getter mai chiamati** (`get_all_classes/races/backgrounds`,
    `get_race_names`, `get_equipment`, `get_economy`, `get_mounts_and_vehicles`, `get_magic_item`,
    `get_magic_item_names`, `get_disease`, `get_poison`, `get_madness_intro_text`, `get_trap_damage_dice`,
    `get_example_trap`, `get_npc_name_races`).
  - repository — `maps_repo.get_map`, `character_repo.update_creature_notes`, `master_repo.get_npc_by_id`/`update_encounter_notes`/`delete_member`/`get_master_campaign_note_by_id`.
  - vari — `wizard_engine.get_recommended_class`/`get_class_description`,
    `treasure_generator.format_coins`/`CR_BANDS`, `trap_generator.SEVERITY_LEVELS`,
    `profilo_tab._is_asi_level`/`_can_level_up`, 3 variabili locali mai usate.
  - `core/level_manager.py` — campo `LevelStep.requires_player_choice`: **scritto 20 volte e mai letto**
    (write-only). Rimosso insieme a tutti i kwarg; la regressione delle 760 combinazioni copre esattamente questo.
  - **Criterio applicato**: cancellare tutto ciò che ha zero chiamanti *oggi*, e riaggiungerlo nella forma che
    servirà quando servirà (YAGNI). Alcuni di questi getter torneranno con le feature di Fase 4 — es.
    `get_magic_item()` per gli oggetti magici lato giocatore, un helper livello-da-PE per l'assegnazione dei PE del
    master: sono annotati in `feature_design_2026_07_26.md`.
  - **Deliberatamente NON rimosso**: `MasterEncounter.is_archived` (campo dataclass che rispecchia la colonna DB —
    è un mirror dello schema, non dead code) e i parametri evento `ev_inner`/`ev2` (richiesti dalla firma degli
    handler Flet, falsi positivi di vulture).

  **2b · File morti rimossi**: `mm_imgs/` (**306 MB, 152 PNG** di pagine del Manuale dei Mostri renderizzate
  durante i batch di trascrizione del bestiario b12–b20 — non più necessarie da quando l'audit è chiuso a 444/444)
  e `tools/parse_monsters.py` (estrattore `pdfplumber` il cui metodo è stato dichiarato inaffidabile e abbandonato
  in favore della lettura visiva: tenerlo era fuorviante). La cartella `tools/` è rimasta vuota ed è stata rimossa.
  ⚠️ **Non rimosso, da valutare con Davide**: `dnd_app/build/` = **1,1 GB** di artefatti Flutter/ipa/site-packages,
  rigenerabili con `flet build`. Non l'ho toccato perché potrebbe essere una build funzionante in uso.

  **2c · Duplicazione wizard/form — la misura iniziale era imprecisa, ecco quella vera.**
  L'analisi della revisione diceva "83 funzioni omonime, 1.965 righe identiche = 67%": era una similarità **riga
  per riga** su tutto il file (`difflib`), che conta anche le righe di boilerplate (`),`, `ft.Container(`…).
  Rimisurata correttamente con l'**AST**, funzione per funzione:
  - **51** funzioni (non 83) hanno lo stesso nome nei due file — il conteggio precedente includeva closure omonime definite più volte nello stesso file;
  - di queste, **24 hanno logica identica** a meno di annotazioni di tipo, docstring e commenti (una prima misura
    ne trovava solo 3, perché confrontava il testo grezzo: le differenze erano `-> None` e docstring);
  - le altre **27 divergono davvero**, ma il confronto del **grafo delle chiamate** mostra che **nessuna divergenza
    è una correzione applicata a un solo file** (nessun "drift bug"): tutte si spiegano con la diversa struttura a
    fasi (il wizard ha Domande/Raccomandazione e deve ricostruire mezza schermata al cambio classe perché tutto
    convive nella fase Revisione; il form ha Identità/Punteggi e ricostruisce la fase Scelte da zero). **Questo era
    il rischio principale che cercavo — non c'è.**
  - **Estratto** `ui/views/creation_wizard/creation_shared.py` con `CreationSharedMixin`: le **9 funzioni identiche
    che sono metodi di classe** (`_set_content`, `_bg_skill_proficiencies`, `_bg_language_choices`,
    `_class_skill_options`, `_race_language_choice_count`, `_prepared_spell_ability_score`,
    `_compute_prepared_spell_count`, `_compute_mago_max_prepared`, `_init_weapon_choice`) più la costante
    `_PREPARED_CASTER_CLASSES`. Entrambe le view ereditano dal mixin.
  - **Residuo, misurato e documentato nel docstring del nuovo modulo** (non fatto qui, richiede una sessione
    dedicata): le altre 15 identiche sono closure annidate dentro i metodi giganti, e i giganti stessi restano
    near-duplicati — `_render_confirm` (911 vs 845 righe, 73,7% simili), `_on_save` (758 vs 751, 78,0%),
    `_rebuild_race_extras_col` (553 vs 557, 91,9%), `_rebuild_spells_init_col` (312 vs 309, 95,6%),
    `_render_equipment` (269 vs 259, 92,2%), `_rebuild_lang_tool_col` (185 vs 164, 86,0%). Per estrarli bisogna
    prima spezzarli.

  **Verificato** con due nuove batterie end-to-end (DB temporaneo isolato, `HOME` separato, mai il DB reale):
  - **metodi condivisi** (36 controlli): entrambe le view espongono la *stessa identica funzione* (`WizardView._x
    is ManualCreationForm._x`), e i 9 metodi danno i risultati attesi — abilità di classe che escludono quelle di
    background, Chierico Umano SAG 15+1 → 4 preparati, Mago Umano INT 15+1 → 4 preparabili dal libro, Guerriero →
    0, lingue a scelta 1 per Umano e Mezzelfo e 0 per il Nano, bonus razziale del Nano delle Colline sul punteggio
    da incantatore, `weapon_choice` singola e multipla.
  - **creazione REALE end-to-end** (61 controlli): tutte le fasi costruite per **12 classi × 2 flussi**, e **24
    personaggi effettivamente salvati sul DB** (uno per classe per flusso) con HP/CA/competenze coerenti. Il
    controllo più forte: per **tutte e 12 le classi, wizard e form manuale producono lo stesso identico
    personaggio** — stessi HP, stessa CA, stessa velocità e lo **stesso insieme esatto di competenze**. Se
    l'estrazione del mixin avesse cambiato anche solo un comportamento, questo confronto lo avrebbe mostrato.
  - Rieseguite tutte le batterie della Fase 1 (B1-B7, B8-B9, B10, regressione 252 viste / 760 combinazioni level-up) — **0 fallimenti**. `compileall` + `pyflakes` sull'intero albero: puliti.
  - **Due comportamenti pre-esistenti confermati durante i test** (non regressioni, non modificati): gli slot
    incantesimo non vengono inizializzati alla creazione ma al primo caricamento della tab Combattimento
    (self-healing già in uso nel progetto); le armi di partenza vengono create **non equipaggiate** per scelta
    esplicita già documentata nel codice (il giocatore le equipaggia dall'Inventario).

- **Revisione 2026-07-26 · FASE 3A COMPLETATA — fondazioni del restyle** — prima fase del restyle
  (`dnd_app/docs/restyle_design.md`). Invisibile all'utente per la maggior parte, ma è ciò che rende economico
  tutto il resto: prima di questa fase cambiare un raggio o un colore significava toccare 25 file.

  **Nuovo modulo `ui/design.py`** — il design system dell'app:
  - **Token**: `Space` (4/8/12/16/24/32), `Radius` (8/12/16/20/pill — prima l'app usava 140× `radius=6` e 49×
    `radius=4`), `Duration` (120/200/320 ms), `Font`, `Size` (scala tipografica fissa, minimo 11px).
  - **Palette doppia `LIGHT`/`DARK`** con contrasti WCAG **calcolati**, non scelti a occhio. Letta tramite `T()`
    (funzione, non costante) + `set_mode()`: funziona perché tutte le view del progetto si ricostruiscono già da
    zero ad ogni refresh. Due valori che il calcolo ha imposto: `text_3` chiaro è `#5c6376` e non `#6b7185` (che
    dava 3.88 su `surface_alt`, sotto AA); il rosso scuro è `#f2696d` con foreground **scuro** `#241012` sul pieno,
    perché bianco su quel rosso dà 3.91 — sotto AA (è la convenzione Material 3 per il tema scuro).
  - **`elevation(1..3)`** come `ft.BoxShadow` predefinite, più diffuse e più opache in dark mode altrimenti scompaiono. Prima: **0 `BoxShadow` in tutte le 45k righe**.
  - **`page_gradient()`**: pergamena con un `LinearGradient` a ~2% di differenza di luminosità — nessuna immagine, peso zero, funziona identico in dark.
  - **Primitive**: `surface`, `card` (accento come barra a sinistra, non filetto in cima), `section`, `pill`,
    `chip`, `stat_tile`, `metric_bar`, `empty_state`. `pill` unifica le 3 copie di
    `_tool_pill`/`_action_pill`/`_header_actions` che vivevano in
    `master_view`/`master_encounter_view`/`home_view`.

  **`ui/theme.py` — `get_theme()` riscritta + `get_dark_theme()`**: prima usava **2 campi su 58** di `ft.Theme`.
  Ora ne configura 9 sotto-temi + un `ColorScheme` completo. L'effetto più grande a costo zero è `dialog_theme`
  (raggio 20, elevation 8, tipografia): **restyla in un colpo solo tutti i ~60 AlertDialog**, che erano stilizzati
  a mano uno per uno. Più `card_theme`, `text_theme`, i 3 temi bottone, `scrollbar_theme` (6px, arrotondata,
  semitrasparente — le scrollbar di default sono uno dei dettagli che più invecchiano un'app), `divider_theme`,
  `tooltip_theme`, `visual_density=COMFORTABLE`. `app.py` registra ora anche `page.dark_theme`: il toggle della
  Fase D dovrà solo cambiare `page.theme_mode` + `design.set_mode()` + rebuild.
  Gli helper legacy (`title_text`, `fantasy_card`, `section_header`, `primary_button`, `ghost_button`,
  `show_error_dialog`) restano invariati: le view migrano alle primitive nella Fase E, una superficie alla volta.

  **`assets_dir` collegata** (era il rischio segnalato: tocca l'export `.dndchar` già collaudato su web). Prima non
  era impostata affatto su desktop/mobile ed era occupata dalla cartella degli export in web mode — quindi era
  **tecnicamente impossibile caricare un font custom**, prerequisito della Fase B. Ora:
  - nuove `get_assets_path()` (→ `dnd_app/assets/`) e `get_web_export_staging_path()` (→ `assets/exports/`) in `data/database.py`;
  - `main.py` passa `assets_dir=get_assets_path()` su **tutte** le piattaforme;
  - l'export web scrive in **due** posti: la cartella condivisa `~/dnd_character_exports` (copia persistente che
    Davide preleva via SSH — **il bind mount Docker non cambia**) e `assets/exports/` (copia scaricabile). L'URL di
    download passa da `/<file>.dndchar` a **`/exports/<file>.dndchar`**;
  - l'**import** web continua a leggere `~/dnd_character_exports`: nessuna modifica a `docker-compose.yml`.

  **Verificato** (48 controlli + regressione completa): ogni combinazione testo/superficie di **entrambe** le
  palette calcolata e sopra soglia (il minimo assoluto è 4.79:1, il testo primario 12.7–16.7:1); tutti e 9 i
  sotto-temi valorizzati e il raggio dei dialog a 20; le 8 primitive costruite senza eccezioni, con ombra e raggio
  corretti, e la card che cambia superficie passando a `set_mode("dark")` e torna indietro; `assets/` e
  `assets/exports/` create, cartella SSH separata; **export web pilotato end-to-end** — file scritto in entrambe le
  cartelle, `download_url` corretto e JSON scaricabile che contiene il personaggio giusto. Rieseguite tutte le
  batterie delle Fasi 1-2 (B1-B7, B8-B9, B10, 252 viste, 760 combinazioni level-up, 24 personaggi creati dai due
  flussi): **0 fallimenti**. `compileall` + `pyflakes` sull'intero albero: puliti.

  **Da riverificare da Davide su un vero client** (non testabile in sandbox): il download dell'export dal browser con il nuovo URL `/exports/...`, e l'aspetto dei dialog/scrollbar col nuovo tema.

- **Revisione 2026-07-26 · FASE 3E (parziale) — Home restylata** — prima superficie migrata alle nuove primitive, scelta perché è la prima impressione dell'app.
  - **Card personaggio**: ritratto 76px arrotondato con ombra propria (o iniziali su gradiente se manca la foto, al
    posto dell'icona generica), nome in font display, **chip** semantici per livello/classe/razza al posto del solo
    badge livello, accento crimson come **barra a sinistra** invece del bordo grigio 1px su tutti i lati, ombra al
    posto del bordo, animazione di press. Pulsante "Gioca" più grande e in colore primario.
  - **Header**: superficie elevata (ombra) invece del bordo 1px; logo con sottotitolo "COMPANION" spaziato; pillole dalla primitiva condivisa.
  - **Sfondo**: `page_gradient()` — pergamena con gradiente a contrasto minimo.
  - **Stato vuoto**: sostituito dalla primitiva `empty_state()`.
  - **Dead code rimosso**: `_action_pill` locale (era **una delle 3 copie identiche** tra
    `home_view.py`/`master_view.py`/`master_encounter_view.py` — ora tutte e tre andranno a `design.pill()`), più
    gli import `title_text`/`body_text` diventati inutilizzati.
  - **Verificato** (14 controlli): stato vuoto e logo, pillole header, 2 card con ombra + raggio 12 + animazione,
    chip livello/classe/razza, accento a sinistra 3px con gli altri lati a 0, gradiente applicato, header elevato
    senza bordo — e la Home ricostruita con `set_mode("dark")` che usa davvero le superfici scure. Rieseguite tutte
    le batterie precedenti: 0 fallimenti.
  - **Nota su `ft.Border.only()`**: riempie i lati non specificati con `BorderSide(width=0, style=NONE)`, **non**
    con `None` — un test che si aspettava `border.top is None` falliva pur essendo il comportamento corretto.

  ~~**Fase B bloccata sui file dei font.**~~ — **✅ sbloccata: Davide ha caricato i font il 2026-07-30**, vedi la voce seguente.

- **Revisione 2026-07-26 · FASE B COMPLETATA (2026-07-30) — tipografia + eliminazione dei colori hardcoded** —
  Davide ha messo i font scaricati da Google Fonts in `assets/fonts/`, sbloccando il punto rimasto in sospeso; la
  Fase B è stata quindi chiusa per intero (B.1 tipografia + B.2 token + B.3, già fatta in Fase A con
  `page_gradient()`).

  **B.1 — font custom installati.** La cartella caricata era il pacchetto di download grezzo
  (`Cinzel,Inter,JetBrains_Mono/`, **23 MB** di statici + variabili + licenze, con una virgola nel nome —
  problematica in un URL in web mode). Tenuti i soli **3 file variable** rinominati e appiattiti in `assets/fonts/`
  (`Cinzel-Variable.ttf` 126 KB, `Inter-Variable.ttf` 875 KB, `JetBrainsMono-Variable.ttf` 189 KB = **1,2 MB
  totali**, −95%), più le 3 licenze OFL (obbligatorie per redistribuire questi font); il resto rimosso.
  - **Perché le versioni variable e non le statiche**: `page.fonts` in Flet 0.85.3 è un `dict[str, str]` — **un
    solo file per famiglia** (verificato leggendo `flet/controls/page.py`), quindi con le statiche si potrebbe
    registrare un unico peso e il grassetto sarebbe comunque sintetico. Con la variable (assi verificati leggendo
    la tabella `fvar` dei file: Cinzel `wght` 400-900, Inter `opsz`+`wght` 100-900, JetBrains Mono `wght` 100-800)
    il peggior caso possibile è identico a quello delle statiche, il migliore è il peso reale. **Limite onesto**:
    che Flutter mappi `FontWeight` sull'asse `wght` per un font registrato via `FontLoader` non è verificabile in
    questo ambiente — se il grassetto risultasse sintetico, il rimedio è registrare famiglie aggiuntive (`Cinzel
    Bold`, …), ma non c'è modo di saperlo senza guardare l'app.
  - **`ui/design.py → Font`**: `Georgia`/`Arial`/`Courier New` → **`Cinzel`/`Inter`/`JetBrains Mono`**, più il nuovo `FONT_FILES` (mappa famiglia → percorso relativo ad `assets_dir`).
  - **`ui/app.py → _setup_page()`**: `self.page.fonts = dict(design.FONT_FILES)` impostato **prima** del tema —
    `get_theme()` referenzia già le famiglie `d.Font.*` e senza la registrazione ricadrebbero silenziosamente sul
    font di sistema. È il pezzo che la Fase A non poteva fare: `assets_dir` era stata collegata proprio per questo.
  - **`config/settings.py`**: `FONT_TITLE`/`FONT_BODY`/`FONT_MONO` aggiornati ai nuovi nomi. Restano come **alias
    legacy** perché ~60 punti nelle view non ancora migrate li leggono: cambiare 3 valori applica i font nuovi
    anche là senza toccarle. È l'unica duplicazione di stringa accettata nel progetto e **c'è un test che verifica
    che i 3 valori combacino con `ui.design.Font`** — vanno rimossi a fine Fase E. Deliberatamente **non**
    importato `ui.design` da `config/settings.py`: quel modulo è importato anche da `core/`, che per regola non
    deve dipendere da Flet.
  - **Verificato** (62 controlli): i 3 file esistono, sono TrueType `sfnt` validi con le tabelle
    `glyf`/`cmap`/`head`/`name`, e ciascuno ha l'asse `wght` **col range esatto atteso**; le 3 licenze presenti;
    `assets/fonts` contiene esattamente 6 file e nessuna sottocartella residua (<2 MB); i token e gli alias legacy
    coerenti; **entrambi** i temi usano davvero le nuove famiglie in `font_family`, `text_theme` e `dialog_theme`,
    e nessuna dimensione della scala scende sotto 11px; `page.fonts` impostato con una **copia** del dict e prima
    del tema (verificato l'ordine reale delle assegnazioni con una `FakePage` che le registra); i percorsi sono
    relativi, `.ttf`, senza virgole né spazi.

  **B.2 — i colori hardcoded sostituiti con i token.** Era il prerequisito obbligatorio del tema scuro: censiti
  **321 letterali di colore** in 25 file (non 153 come stimava il documento di design — quella stima contava solo
  `#ffffff`). Alla fine restano **24 letterali, tutti dentro due blocchi di definizione dichiarati** in
  `maps_view.py`, più gli 86 che *definiscono* la palette in `design.py`/`settings.py`. Zero colori sparsi nel
  corpo delle view.
  - **Nuovi token in `Palette`** (entrambi i temi): `note_bg`/`info_bg`/`success_bg` (i fondi tenui dei riquadri:
    prima erano 6 hex diversi — `#fef9ec`, `#e8eef8`, `#eef4ff`, `#dce8f8`, `#d4edda` — tutti bianchissimi in
    dark), `parchment`/`parchment_alt` (pagina di lettura del Codex), `nav_bg_alt`/`nav_border`/`nav_accent`
    (chrome della navigazione), `alert`.
  - **`alert` — un token nato da un problema reale trovato durante il lavoro**: la scala di difficoltà degli
    incontri ha 5 gradini, ma la palette ha 4 accenti e `primary == danger`; mappando "difficile"→primary e
    "letale"→danger i due sarebbero diventati **identici** (prima erano `#d2691e` arancione e crimson,
    distinguibili). Aggiunto quindi un gradino intermedio con contrasto calcolato: light `#b8420a` (5.41:1 su
    surface), dark `#f0873f` (6.60:1). Ora i 5 gradini sono 5 colori distinti in entrambi i temi — verificato con
    un test.
  - **`nav_accent` — stesso tipo di problema**: la bottom nav usa l'accento come **colore del testo** sul fondo
    scuro della nav, dove `primary` dà solo **2.45:1**. Nuovo token a 4.55:1 (AA) per quell'uso, mentre la pillola
    selezionata della sidebar resta `primary` pieno con `on_primary` sopra (7.75:1) — due esigenze opposte, due
    token, ciascuno ottimale.
  - **Le 119 occorrenze di `"#ffffff"`** erano quasi tutte "testo/icona sopra un accento pieno": sostituite con
    `on_primary` (91) o `on_accent` (28) in base al riempimento circostante. In tema chiaro entrambi valgono
    `#ffffff` — il comportamento attuale non cambia di un pixel — mentre in dark diventano scuri, come vuole la
    convenzione Material 3.
  - **Tre duplicazioni reali eliminate** (il tipo di problema che questo progetto ha già affrontato con
    `RACE_DATA`/`CLASSES`/`ASI_LEVELS`): `_DIFFICULTY_COLORS`, un dizionario **identico** in
    `master_encounter_view.py` e `master_encounter_generator_dialog.py`, ora un'unica `design.difficulty_color()`;
    `_PARCHMENT`/`_LIST_BG`/`_STATUS_*`, identici in `diary_view.py` e `master_notes_view.py`, ora token; i 5
    colori delle monete, ora `design.CURRENCY_COLORS`.
  - **Trappola risolta — le costanti di colore a livello di modulo**: `_STATUS_GREEN = "#2e7d32"` e simili sono
    valutate a import-time, quindi un token letto lì avrebbe **congelato la palette chiara** rendendo il dark mode
    inefficace su quelle view. La mappa stato→colore è diventata stato→**nome di token** (`_STATUS_TONES`), risolta
    a runtime dentro `_status_color()`. Aggiunto un controllo AST che verifica che **nessun** `T()` in tutto `ui/`
    sia valutato a livello di modulo o come default di parametro: 0 casi.
  - **Due esclusioni deliberate, documentate nel codice**: `_PEN_COLORS` in `maps_view.py` (i colori del pennarello
    sono **persistiti** in `game_maps.annotations` per ogni tratto — renderli dipendenti dal tema cambierebbe il
    colore delle annotazioni già salvate) e la chrome dell'editor mappe, volutamente **scura in entrambi i temi**
    perché è un pannello sovrapposto a un'immagine: i ~40 hex inline sono stati raccolti in un unico dict `_CHROME`
    con la motivazione scritta accanto, invece di essere migrati.
  - **Verificato** (119 controlli): ogni campo di **entrambe** le palette è un hex valido; i 9 token nuovi sono
    davvero diversi tra i due temi (altrimenti il dark mode non avrebbe effetto su di essi); il contrasto WCAG di
    ogni nuovo token calcolato e sopra soglia (testo sui 5 fondi tenui ≥ 4.5, chrome nav ≥ 4.5/7.0, `on_accent` su
    `alert` ≥ 4.5); i 5 gradini di difficoltà distinti in entrambi i temi; **nessun letterale residuo** fuori dai
    blocchi dichiarati; **576 viste costruite senza eccezioni** (8 view × 12 classi × 3 livelli × **2 temi** —
    prima di questa fase la metà "dark" non avrebbe avuto senso), più `DiceView`/`FeatsView`; sidebar e bottom nav
    costruite in entrambi i temi con verifica che usino `nav_bg` e che non resti alcun bianco hardcoded; **988
    combinazioni** classe × sottoclasse × livello di `get_level_up_steps()` senza eccezioni né label vuote;
    export/import `.dndchar` end-to-end (la Fase A aveva toccato `assets_dir`) con scrittura in entrambe le
    cartelle, staging dentro `assets/`, cartella SSH separata e reimport in modalità "copy" che rigenera l'id.
    `compileall` + `pyflakes` sull'intero albero: puliti (rimosso anche un import diventato inutilizzato).

  **Da riverificare da Davide su un vero client** (non verificabile qui): la resa dei tre font — in particolare se
  il grassetto di Cinzel/Inter è reale o sintetico — e il fatto che Cinzel, essendo una capitale romana piuttosto
  larga, non tronchi i nomi di personaggio più lunghi. Il tema scuro esiste ora nei token ma **non ha ancora un
  interruttore**: è la Fase D.

- **Revisione 2026-07-26 · FASE E COMPLETATA (2026-07-30) — restyle di tutte le superfici** — Davide, dopo aver
  approvato la Home: *"la home mi piace molto… solo che tutte le altre schede mi sembrano ancora vecchie e non
  molto belle da vedere, anche la barra della vita mi sembra molto semplice e spartana così come lo stile dei tasti
  e degli slot incantesimo. io rivedrei il design di tutto scheda in ogni sua tab… compresa la barra flottante
  sopra con le caratteristiche. anche tutte le altre schede, quindi incantesimi, diario, mappe talenti e dadi."*
  **Due decisioni prese con lui via `AskUserQuestion` prima di iniziare**: (a) **solo aspetto**, stesse
  informazioni nelle stesse posizioni — nessuna riorganizzazione dei contenuti, così nessun flusso collaudato
  (level-up, equipaggiamento, incantesimi) cambia comportamento; (b) **micro-interazioni incluse** (Fase C
  assorbita qui: feedback al tocco, barre e pallini animati, transizione della tab bar).

  **E.1 — le 24 costanti `COLOR_*` sostituite dai token in tutte le view (2.264 usi).** Era il vero motivo per cui
  "le altre schede sembrano vecchie": la Fase B.2 aveva eliminato i colori *letterali*, ma ogni view leggeva ancora
  la vecchia palette a tema unico di `config/settings.py`. Sostituzione **basata su AST** (solo i nodi `ast.Name`,
  mai gli alias di `from … import`), con mappa semantica: `COLOR_BG_CARD`→`surface`, `COLOR_TEXT_MUTED`→`text_3`,
  `COLOR_ACCENT_CRIMSON`→`primary`, `COLOR_ACCENT_BLUE/GOLD`→`magic`, `COLOR_HP_*`→`success/warning/danger`, ecc.
  Effetto collaterale importante: **il tema scuro è ora a un interruttore di distanza** (Fase D), perché non resta
  un solo colore statico nelle view.
  - **Due errori miei, entrambi trovati e corretti**: (1) il primo giro usava una regex e ha sostituito i nomi
    **dentro le liste `from config.settings import (…)`**, rompendo 4 file — da qui la riscrittura con AST (gli
    alias di import non sono nodi `Name`, quindi diventano intoccabili per costruzione); (2) `ast.col_offset` è un
    offset in **byte UTF-8**, non in caratteri: sulle righe con accenti la sostituzione cadeva spostata di qualche
    colonna. Risolto lavorando sui `bytes` della riga. Entrambi sono trappole da ricordare per qualunque futuro
    refactor automatico su questo codice, che è pieno di commenti accentati.
  - Ripuliti anche i 190 nomi di import diventati inutilizzati e 5 `from config.settings import *` ormai vuoti
    (verificato con AST che nessun nome di `settings` fosse più usato in quei file, non solo fidandosi di
    pyflakes).

  **E.2 — superfici: ombre al posto dei fili da 1px, raggi dalla scala.** Trasformazione AST su tutti i `ft.Container`, 219 modifiche:
  - **39 card** con il vecchio stile "filetto colorato 3px in cima + bordo 1px sugli altri lati" → **accento come
    barra a sinistra + ombra morbida**. È la firma visiva che rendeva "vecchie" le tab della scheda, e il documento
    di design la indicava come il singolo cambiamento che sposta più percezione di modernità.
  - **44 bordi** `Border.all(1, border)` su superfici → `shadow=elevation(1)`.
  - **136 raggi** `4`/`6` → `Radius.SM`/`Radius.MD` (8/12), **saltando i cerchi** (dove raggio ≈ metà della larghezza) e i badge sotto i 28px, che altrimenti sarebbero diventati blob squadrati.
  - **Incidente e recupero, da raccontare per intero**: estraevo il colore d'accento dal testo con `split(")")`,
    che tronca se l'espressione contiene una chiamata — `design.T().primary` diventava `design.T(`. 35 accenti su
    39 sono andati persi, e il progetto **non ha git**. Recuperati dai `.pyc` in `__pycache__`: i 7 file rotti non
    si erano ricompilati, quindi il loro bytecode era ancora quello dello stato precedente. Ho cercato la sequenza
    `LOAD_METHOD BorderSide → LOAD_CONST 3 → … → LOAD_ATTR <token>` (il bordo di spessore 3 **è** l'accento) e
    riapplicato i token per funzione, nello stesso ordine. Anche qui un errore intermedio: la prima attribuzione
    cercava il `def` più vicino sopra la riga, che per un sito dopo una closure è la closure stessa — corretta con
    una pila di indentazione. **Verifica finale: tutti e 41 gli accenti dell'app confrontati uno per uno col
    bytecode originale, 0 discrepanze.** Nessun colore è stato indovinato.

  **E.3 — gli helper legacy di `ui/theme.py` riscritti sulle primitive.** `section_header()` (chiamata da **68
  punti**), `fantasy_card()`, `primary_button()`, `ghost_button()`, `title/body/muted/label_text()` ora delegano ai
  token e alle primitive: cambiare questi 8 helper ha restylato in un colpo solo tutte le sezioni e i pulsanti
  delle view non ancora riscritte a mano. `fantasy_card()` è diventata un alias di `design.card()` (accento a
  sinistra).
  - **7 default di parametro con `T()` dentro, trovati e corretti**: `def body_text(…, color=d.T().text)` e simili
    sono valutati **una sola volta all'import**, quindi avrebbero congelato la palette chiara vanificando il tema
    scuro proprio negli helper più usati dell'app. Erano stati introdotti dalla sostituzione automatica di E.1. Il
    controllo AST che li ha trovati è ora parte della batteria di test.

  **E.4 — i componenti che Davide ha citato esplicitamente**:
  - **Barra flottante delle caratteristiche**: pannello elevato con angoli inferiori arrotondati, riquadri
    *incassati* (`surface_alt`), punteggio in cifre tabellari a 20px e **modificatore in un chip d'accento** invece
    di testo blu nudo; feedback di scala al tocco. Le 6 icone matita restano (regola "nessuna azione nascosta").
  - **Tab bar**: da tab sottolineati a **controllo segmentato a pillole** — la pillola attiva è in rilievo con
    ombra, le altre trasparenti, con transizione animata. `_switch_tab` e la costruzione condividono ora un unico
    `_style_tab_button()` invece di duplicare lo stile.
  - **Barra HP**: nuova primitiva `design.hp_bar()` **a segmenti** (Container con peso `expand`, proporzioni
    esatte) che per la prima volta mostra i **PF temporanei come fascia dedicata** in colore `magic` — prima la
    `ProgressBar` piatta li ignorava del tutto. Numero grande in mono, riquadro "HP TEMP" con fondo tinto quando
    valorizzato, pulsanti Danno/Cura pieni e in rilievo.
  - **Slot incantesimo**: nuove primitive `design.slot_dots()` (sola lettura) e `design.dot_button()` (cliccabile).
    Prima erano i **caratteri "●"/"○" di un font di testo** — dimensione e allineamento dipendevano dal font e in
    tema scuro il "vuoto" spariva; ora sono forme vere, pieno = disponibile / **anello** = speso, con area di tocco
    allargata di 4px per il dito su tablet. Applicate a: slot in Incantesimi, slot e risorse di classe in
    Combattimento, tiri salvezza contro morte.
  - **Pulsanti**: rimosse **81 `shape=RoundedRectangleBorder(radius=4|6|8)` inline** dalle view; forma, padding,
    elevazione e tipografia vivono ora nel `button_theme`/`outlined_button_theme`/`text_button_theme` del tema,
    quindi valgono per ogni bottone dell'app. Restyle mirato dei tasti dado (attivo pieno e in rilievo, cifre in
    mono) e dei segmenti Vantaggio/Svantaggio; card dei Talenti con accento a sinistra, chip per il bonus
    caratteristica e stato vuoto dalla primitiva condivisa.

  **Pulizia finale**: rimosse da `config/settings.py` le 24 `COLOR_*` e i 3 alias `FONT_*` (37 usi residui migrati
  a `design.Font.*`) — erano diventati dead code, ed erano l'ultimo ostacolo strutturale al tema scuro. Al loro
  posto un commento che indica dove vivono ora colori e font, e **perché `T()` non va mai salvata in una costante
  di modulo**. `config/settings.py` torna a contenere solo costanti di regolamento, coerente con la regola "`core/`
  non dipende da Flet".

  **Verificato** (269 controlli in 3 batterie, DB temporanei isolati, mai quello reale): **576 viste costruite
  senza eccezioni** (8 view × 12 classi × 3 livelli × 2 temi) più `DiceView`/`FeatsView`; **988 combinazioni**
  classe × sottoclasse × livello di `get_level_up_steps()`; export/import `.dndchar` end-to-end; **85 controlli
  strutturali sui nuovi componenti in entrambi i temi** — pesi dei segmenti della barra HP (21/5/12 su un
  personaggio con 21 PF su 38 e 5 temporanei), clipping degli angoli, soglie di colore, pallini come forme e non
  caratteri, riassunto "+8" oltre i 12 mostrati, `dot_button` che invoca davvero il proprio `on_click`, 6 riquadri
  caratteristica tutti cliccabili e animati con le 6 matite, una sola tab attiva che si sposta correttamente al
  cambio, accento delle card **a sinistra** (`border.left.width == 3` e `border.top.width == 0`), nessun raggio
  fuori dalla scala nei bottoni; più il controllo AST che nessun `T()` sia valutato a import-time (0 casi) e che
  non resti alcun letterale di colore fuori dai due blocchi dichiarati di `maps_view.py`. `compileall` + `pyflakes`
  sull'intero albero: **puliti, zero warning**.

  ~~**Non toccato, per scelta**: la chrome dell'editor di mappe…~~ — l'editor mappe è stato poi restylato su
  richiesta di Davide, vedi la voce seguente. Restano fuori solo i **colori del pennarello** (persistiti su DB).
  **Da giudicare a occhio da Davide**: la resa complessiva delle 5 tab e delle altre schede su un vero client — qui
  è verificata la struttura, non l'estetica.

- **Revisione 2026-07-26 · FASE E (coda) — editor mappe e Sezione Master (2026-07-30)** — Davide: *"ok bello ma
  dobbiamo abbellire anche la modalità di modifica della mappa e la sezione master"*. Erano le due superfici
  rimaste indietro: la prima perché volutamente esclusa dagli sweep (è chrome scura, non segue la palette), la
  seconda perché aveva ricevuto solo i passaggi meccanici.

  **Editor mappe.** La barra strumenti resta **scura in entrambi i temi** — è un pannello sopra un'immagine, se
  seguisse la pergamena competerebbe con la mappa — ma i suoi ~40 hex non vivono più in un dizionario dentro la
  view: sono ora `design.CHROME`, un dataclass a sé in `ui/design.py` con la motivazione scritta accanto. Così
  anche questa superficie rispetta la regola "nessun colore magico nelle view", pur non essendo tematizzata.
  - **Barra strumenti**: da striscia incollata al bordo con un filo da 1px a **pannello flottante** — angoli superiori arrotondati e ombra rivolta verso l'alto, come se fosse posata sopra la mappa.
  - **Penna/Gomma**: da due riquadri squadrati a **controllo segmentato a pillole** dentro un binario scuro, con icona + etichetta.
  - **Colori del pennarello**: swatch più grandi con **anello di selezione** (il colore selezionato è cerchiato di
    chiaro e scalato al 100%, gli altri al 90%) invece di un bordo più spesso — la selezione si legge anche sui
    colori chiari, dove prima il bordo bianco spariva.
  - **Slider**: valore in un **badge monospaziato** invece di testo nudo, etichette in maiuscoletto spaziato; l'area di disegno ha ora un fondo scuro che stacca la mappa dal resto della scheda.
  - **Duplicazione eliminata**: lo stile di modalità/swatch/gomma era scritto **due volte** — una in costruzione e
    una dentro i vari `_select_*` — con il rischio concreto che restassero disallineati. Ora c'è un unico
    `_style_mode_btn`/`_style_swatch`/`_style_ersub_btn` usato da entrambi (stesso rimedio già applicato alla tab
    bar della scheda).
  - **Intoccati per necessità**: i 7 colori del pennarello, che sono **persistiti** dentro `game_maps.annotations`
    per ogni tratto — cambiarli o legarli al tema cambierebbe il colore delle annotazioni già salvate. C'è un test
    che lo verifica.

  **Sezione Master.**
  - **Header** elevato senza filo 1px; **tab bar** convertita in controllo segmentato a pillole (stesso linguaggio
    della scheda e della Home); le pillole degli strumenti ora vengono dalla primitiva condivisa `design.pill()`
    invece di una copia locale — era la quarta copia della stessa funzione nel progetto.
  - **Card NPC e card incontro**: avatar in cerchio tinto, nome in font display con ellissi, **accento a sinistra**
    (crimson se l'NPC ha una scheda di combattimento, blu altrimenti), chip per round e numero di combattenti,
    feedback di scala al tocco.
  - **Incontro aperto**: il combattente **di turno** è l'unico con accento più marcato e ombra più profonda — si
    trova a colpo d'occhio scorrendo l'ordine d'iniziativa; CA/PF/PE sono diventati chip invece di testo grigio in
    fila.
  - **Note di campagna** (e per simmetria il Codex del giocatore, che ne è il gemello): pulsanti categoria a
    pillola con ombra quando selezionati, contatore come chip, voce selezionata con **barra d'accento a sinistra**
    invece del bordo pieno su tutti i lati.
  - **Stati vuoti**: quattro copie scritte a mano sostituite dalla primitiva `design.empty_state()`.
  - Normalizzati anche i **45 raggi** di `TextField`/`Dropdown` nei dialog del Master (6/10 → scala).

  **Verificato** (58 controlli nuovi + le 3 batterie precedenti rieseguite, 327 in totale, 0 falliti): la chrome è
  la stessa in entrambi i temi e viene davvero da `design.CHROME`; barra strumenti con ombra e angoli superiori
  arrotondati (`top_left == 16`, `bottom_left == 0`); esattamente una modalità attiva e `_style_mode_btn` che
  sposta lo stato; 7 swatch con un solo anello di selezione; **i colori del pennarello invariati**; card
  mappa/NPC/incontro con accento a sinistra e animazione; tab bar del Master come segmento; il combattente di turno
  con accento 4px contro 3px degli altri. `compileall` + `pyflakes` puliti.

- **Revisione 2026-07-26 · FASE E (coda 2) — allineamento di TUTTE le finestre, Master e giocatore (2026-07-30)** —
  Davide: *"nella sezione master bisogna adattare anche tutte le finestre quando si clicca tesoro trappole ecc, lo
  stesso vale anche per la sezione giocatore, anche tutte le finestre che si aprono devono essere allineate"*.
  Erano **114 `AlertDialog`**, ciascuno stilizzato a mano: la Fase A aveva già unificato raggio/ombra/tipografia
  tramite `dialog_theme`, ma titolo, sfondo, pulsanti e campi restavano decisi caso per caso.

  **Quattro interventi, tutti guidati da AST** (mai regex sul testo grezzo — lezione della coda precedente):
  - **101 titoli** `title=ft.Text("…", size=…, weight=…, color=…)` → nuova primitiva `design.dialog_title()`: font
    display, dimensione dalla scala, icona opzionale in un cerchietto tinto. Prima erano 101 combinazioni diverse
    di size/weight/color.
  - **76 `bgcolor` inline** rimossi dagli `AlertDialog`: lo fornisce `dialog_theme`, e un valore inline **vincerebbe anche in tema scuro** — era un ostacolo silenzioso alla Fase D.
  - **229 kwarg di stile** aggiunti a `TextField`/`Dropdown` (`border_radius`, `border_color`,
    `focused_border_color`, `bgcolor`, `text_style`) dalla nuova `design.field_style()`. **Perché a mano e non dal
    tema**: `ft.Theme` in Flet 0.85.3 **non ha** `input_decoration_theme` (verificato per introspezione), quindi i
    campi sono l'unico controllo che non si può uniformare centralmente. Gli argomenti già presenti non sono mai
    stati toccati: si aggiunge solo ciò che manca, così le personalizzazioni volute (es. bordo rosso sul campo
    "Danno") restano.
  - **60 liste di pulsanti** ancora piatte avvolte in `wrap_dialog_actions()`: `AlertDialog.actions` non va a capo da sé, quindi su smartphone i pulsanti uscivano dal bordo. Ora sono 64 su 64.
  - **12 contenuti a larghezza fissa** (`width=340/380/420`) resi responsive con `responsive_dialog_width(page, base)`, che prima era applicata solo a 4 dialog del Master.

  **Uniformati dal tema anche i controlli Material** che vivono dentro i dialog e prima erano lasciati al default:
  `dropdown_theme`, `checkbox_theme` (spunta col colore primario, angoli morbidi), `radio_theme`, `slider_theme`,
  `chip_theme`, `icon_theme`, `snackbar_theme`.

  **Bug reale trovato dal test, non dal linter**: la Fase E.1 aveva rinominato `_RARITY_COLORS` →
  `_RARITY_TONES`/`_rarity_color()` in `master_magic_items_view.py`, ma `master_magic_item_generator_dialog.py`
  importava ancora il vecchio nome. `compileall` e `pyflakes` non lo vedono (un `ImportError` di un nome esistente
  solo a runtime), e la mia verifica "importa tutti i moduli di `ui/`" era stata eseguita *prima* di quel rename.
  Il dialog "Oggetto Magico" del Master sarebbe crollato all'apertura. Corretto, e la verifica di import di tutti i
  41 moduli è ora parte della batteria.

  **Verificato** (335 controlli, 0 falliti): parte statica — su tutte le 114 finestre, **zero** titoli grezzi,
  **zero** `bgcolor` inline, **zero** liste di pulsanti non avvolte, **zero** campi senza stile condiviso; parte
  dinamica — i 7 generatori del Master (Tesoro, Trappole, Veleni, Ambiente, Oggetti Magici, Incontri, NPC casuale)
  aperti davvero in **entrambi i temi × due larghezze (1280 e 375px)**, con verifica che il titolo sia in font
  display, che il contenuto non superi mai la larghezza della finestra meno i margini e che ogni campo abbia raggio
  e superficie del tema; più i dialog lato giocatore (Danno, Cura, HP max/temp, HP temporanei, Caratteristiche,
  Bonus competenza, Nuova arma) con gli stessi controlli. Rieseguite anche le 4 batterie precedenti (662 controlli
  totali, 0 falliti); `compileall` + `pyflakes` puliti.

- **Revisione 2026-07-26 · FASE D COMPLETATA (2026-07-30) — tema scuro con preferenza persistita. Il restyle è
  chiuso.** Ultimo pezzo mancante: le due palette con contrasti WCAG calcolati e `page.dark_theme` erano pronti
  dalla Fase A, e dopo la Fase E nelle view non restava più un solo colore statico — mancavano solo l'interruttore
  e la memoria della scelta.

  **Due decisioni prese con Davide via `AskUserQuestion` prima di scrivere codice**: (a) **tre stati** Chiaro /
  Scuro / **Sistema** (default), non un interruttore a due; (b) **solo il tema** — densità dell'interfaccia e
  dimensione del testo, che il documento di design lasciava "da valutare", sono state esplicitamente rimandate per
  non trasformare una pillola in un pannello Impostazioni.

  **"Sistema" è reale, non un'etichetta**: verificato per introspezione sul pacchetto `flet==0.85.3` installato che
  `page.platform_brightness` (`Optional[ft.Brightness]`, valori `LIGHT`/`DARK`) e
  `page.on_platform_brightness_change` esistono davvero — quindi con questa preferenza il tema segue il SO **anche
  mentre l'app è aperta** (es. la pianificazione automatica di macOS al tramonto), non solo al lancio.

  **Schema — nuova tabella `app_settings(key, value, updated_at)`**, chiave/valore, **nessun `character_id` e
  nessuna FK**. Il tema è una proprietà della macchina, non del personaggio: chi gioca sul tablet la sera e sul
  portatile di giorno vuole una scelta per dispositivo, e importare un `.dndchar` da un altro device non deve
  cambiare l'aspetto dell'app. Per lo stesso motivo la tabella **non** è tra le `CHILD_TABLES` di
  `character_export.py` — c'è un test che lo verifica. Forma chiave/valore invece di una colonna per preferenza
  così aggiungerne una in futuro (densità, dimensione testo) non richiede una migrazione.

  **`data/repositories/settings_repo.py`** (nuovo): `get_setting`/`set_setting` generiche più gli helper tipizzati
  `get_theme_preference`/`set_theme_preference`/`next_theme_preference`. **Nessuna funzione solleva mai verso la
  UI**: un DB irraggiungibile o un valore corrotto produce un `logger` e il default — una preferenza estetica non
  deve poter impedire l'apertura dell'app. `get_theme_preference()` normalizza (spazi/maiuscole) e ricade sul
  default per un valore ignoto, caso reale se una versione futura salvasse una modalità che questa non conosce.
  `INSERT OR REPLACE` invece di `ON CONFLICT DO UPDATE`: qui sono equivalenti (nessuna FK punta alla tabella) e la
  prima funziona su qualunque versione di SQLite.

  **`ui/app.py` — risoluzione in un punto solo.** `_resolve_theme_mode()` traduce la preferenza in
  `"light"`/`"dark"`; `_apply_theme_mode()` allinea `design.set_mode()`, `page.theme_mode` e `page.bgcolor` e
  ritorna se la modalità è cambiata davvero. **Scelta importante**: `page.theme_mode` riceve sempre un valore
  CONCRETO, **mai `ft.ThemeMode.SYSTEM`**, anche con la preferenza "Sistema" — i colori delle nostre view vengono
  da `design.T()`, che conosce solo due palette; lasciare a Flutter la risoluzione di SYSTEM significherebbe poter
  avere i controlli Material scuri e le nostre superfici chiare. La risoluzione la facciamo noi, una volta, per
  entrambi.

  **Il rebuild e il suo limite, dichiarato invece che nascosto.** Cambiare palette non ridisegna un albero di
  controlli già costruito (i colori sono letti da `design.T()` al momento della costruzione), quindi serve
  ricostruire la schermata. Nuovo `_rebuild_route: Callable | None` impostato da ogni `_show_*`: Home, Sezione
  Master e layout principale sono ricostruibili; **wizard e form di creazione no** — ricostruirli a metà
  compilazione perderebbe le scelte fatte. Lì il pulsante non compare, e nel solo caso possibile (preferenza
  "Sistema" + il SO che cambia tema durante la creazione) si applica il tema Material e le superfici custom si
  allineano alla schermata successiva. Il rebuild della Sezione Master preserva la **tab** attiva (nuovo parametro
  `active_tab` su `MasterView`, letto al momento del cambio, non alla creazione) ma non lo stato interno di una
  sotto-vista: un incontro aperto torna alla lista incontri. Il cambio di tema è raro, e la scelta è dichiarata nel
  codice invece che scoperta dall'utente.

  **Il pulsante, in tre superfici, mai un'icona muta.** Nuovi
  `theme_toggle_look()`/`theme_toggle_tooltip()`/`theme_toggle_pill()` in `ui/widgets.py` — un unico posto per
  icona ed etichetta, così i tre punti d'uso non divergono (stesso problema già capitato con le 3 copie di
  `_action_pill`, poi unificate in `design.pill()`). L'etichetta è lo **stato attuale**
  ("Chiaro"/"Scuro"/"Sistema"), non l'azione, coerente con un ciclo a tre stati; il tooltip dice entrambe le cose.
  Punti d'uso: pillola nell'header di **Home** e della **Sezione Master**; nella **sidebar** e nella **bottom nav**
  la stessa coppia icona/etichetta ma nella forma delle altre voci di navigazione (colonna su fondo scuro), non una
  pillola. Callback opzionale con default `None`: se assente la pillola non compare — stesso pattern "nascosto se
  assente" già usato per `on_open_master`, così le costruzioni legacy restano valide (c'è un test per entrambi i
  casi). La bottom nav passa da 7 a 8 voci: a 375px di viewport sono ~47px di larghezza ciascuna, appena sotto i
  48dp consigliati, ma l'altezza della barra è 64px quindi l'area di tocco resta ben oltre 48×48 — annotato nel
  codice.

  **Verificato** con una batteria di 99 controlli (`dnd_app/test_fase_d.py`, DB temporaneo isolato via
  `tempfile.mkdtemp()` + `HOME` separato — mai il DB reale di Davide; `FakePage` minimale + scansione ricorsiva
  dell'albero dei controlli, pattern già consolidato nel progetto): tabella creata con le colonne attese e **zero
  FK**; round-trip della preferenza per tutti e tre i valori; una sola riga per chiave dopo riscritture ripetute;
  valore non valido **rifiutato senza sovrascrivere** quello buono; valore sporco nel DB (`"sepia"`) che ricade sul
  default e `"  DARK  "` normalizzato; il ciclo nei tre versi e da uno stato sporco. Risoluzione: preferenza
  esplicita che **ignora** la brightness di sistema in entrambe le direzioni, `"system"` con brightness
  DARK/LIGHT/**None** (quest'ultima prima del primo layout → chiaro), `page.theme_mode` sempre concreto e mai
  `SYSTEM`, `bgcolor` dalla palette giusta, handler agganciato, font registrati prima del tema. Ciclo: i tre click
  con persistenza verificata sul DB e rebuild richiesto **anche quando la modalità risolta non cambia** (da
  "Chiaro" a "Sistema" col SO già chiaro: l'etichetta è cambiata); cambio di tema del SO che ricostruisce con
  "Sistema" e **non fa nulla** con una preferenza esplicita; stessa brightness due volte → **nessun rebuild
  inutile**; route `None` che non solleva. Route: Home/Master ricostruibili, wizard e form no, tab del Master
  preservata al rebuild e tab non valida che ricade su `npcs`. Pulsante: presente in Home, Master, sidebar e bottom
  nav (8 voci) **in entrambi i temi**, assente senza callback, con icona **e** etichetta e tooltip, e il click che
  invoca davvero la callback. Regressione: **104 costruzioni di view** (8 view × 12 classi × 2 temi) senza
  eccezioni, **760 combinazioni** classe × sottoclasse × livello di `get_level_up_steps()`, ed export/import
  `.dndchar` end-to-end con verifica che `app_settings` **non** compaia nel file esportato. `compileall` +
  `pyflakes`: puliti (resta solo il rumore preesistente di `from config.settings import *` in `app.py`).

  **Da guardare su un vero client** (non verificabile qui): la resa d'insieme del tema scuro. I contrasti sono
  calcolati e sopra soglia AA, ma se una superficie risultasse troppo piatta o un accento troppo acceso, si
  corregge il token in `ui/design.py` e cambia ovunque.

- **FASE 4 COMPLETATA (2026-07-30, seconda sessione) — le 4 feature autorizzate.** Davide ha chiesto di programmare
  più fasi insieme per poter lavorare a lungo senza interruzioni; le 8 decisioni aperte sono state raccolte tutte
  in due blocchi di domande prima di scrivere codice. **Scelte di Davide**: storico dei tiri **solo in sessione**
  (nessuna tabella nuova); promemoria contestuali delle condizioni **sì, in sola lettura**; il master **può**
  scrivere i PE sui PG con dialog di conferma; vantaggio/svantaggio con **tre pulsanti sul pannello del risultato**
  (si tira normale, si ritira se serve); TS contro morte **applicato automaticamente** ai pallini; iniziativa **un
  tiro per copia** con opzione gruppo; PE dell'incontro con **checkbox per mostro pre-spuntata**.

  **Fondamenta — `core/dice.py` e `core/character_stats.py`** (moduli puri, nessuna dipendenza Flet). `dice.py`
  estrae la logica che viveva solo dentro `DiceView._roll()`: parser di formule a più termini (`1d8+1d6+3`, utile
  per i danni magici extra già modellati come dadi aggiuntivi), vantaggio/svantaggio **applicato solo al primo
  1d20** (PHB Cap. 7: riguardano solo i tiri di d20 — su `2d6` viene ignorato invece di essere applicato a un dado
  qualsiasi), critico/fallimento critico, e il dado scartato sempre mostrato nel dettaglio. `character_stats.py`
  diventa l'unica fonte per "quanto tira questo personaggio su X": prima lo stesso calcolo era duplicato inline in
  **6 punti** della UI. La feature quindi *riduce* codice invece di aggiungerne — `esplorazione_tab` e
  `combattimento_tab` ora chiamano il modulo invece di rifare la matematica.

  **Feature 1 — dadi collegati alla scheda.** Nuovo `ui/components/roll_panel.py`: pannello **non modale** montato
  in `page.overlay` come `ft.Container` **posizionato** (`right`/`bottom`, verificati esistenti su `flet==0.85.3`)
  — occupa solo il proprio riquadro in basso a destra, quindi il resto della scheda resta cliccabile, e sopravvive
  alla ricostruzione delle view perché è agganciato alla pagina. Al tavolo serve vedere l'ultimo tiro mentre si
  continua a leggere la scheda: un `AlertDialog` lo avrebbe impedito. Agganci: 18 abilità, 6 TS, 6 prove di
  caratteristica (il chip del modificatore nella barra flottante diventa il pulsante di tiro, con la matita che
  resta per modificare il punteggio — due affordance distinte nello stesso riquadro), attacco e danni di ogni arma,
  iniziativa, TS contro morte, dadi vita nel riposo breve (prima il totale andava digitato a mano), attacco con
  incantesimo. **TS contro morte automatico** (PHB p.197): 20 naturale → 1 PF e pallini azzerati; 1 naturale →
  **due** fallimenti; ≥10 successo; terzo successo stabilizza, terzo fallimento uccide — ogni applicazione
  accompagnata da un avviso esplicito con la pagina citata, l'app non modifica mai la scheda in silenzio.

  **Feature 4a — iniziativa lato master.** Nuova colonna `master_encounter_members.dex_mod`, catturata al momento
  dell'aggiunta: senza di essa "Tira per tutti" non avrebbe alcun dato per i membri `adhoc` (un mostro preso dal
  bestiario non lascia traccia del proprio stat block). I tre dialog di aggiunta hanno ora "Tira l'iniziativa (d20
  + DES)" **attivo di default** — aggiungere 5 goblin significava compilare 5 campi a mano — più "Gruppi identici
  tirano insieme" (variante DMG, spenta di default: è una scelta del master, non una regola). Pulsante "Tira
  iniziativa" nell'header che ritira tutti i mostri **senza mai toccare i PG**, coerente con la regola del
  progetto.

  **Feature 2a — concentrazione** (PHB p.203-204, riletto visivamente prima di implementare). Nuove colonne
  `characters.concentrating_spell`/`concentrating_since` — colonne e non tabella perché il manuale è esplicito: "un
  incantatore non può concentrarsi su due incantesimi alla volta". Attivazione dal dettaglio dell'incantesimo in
  Incantesimi, con **avviso** se ne interrompe un'altra invece di sostituirla in silenzio. Al danno subito, TS di
  Costituzione con **CD = 10 o metà dei danni, il maggiore**; il dialog offre "Tira", "Ho superato il tiro" (al
  tavolo può aver già tirato il giocatore) e "Interrompi". A 0 PF cade da sola ("Incantatore incapacitato o
  ucciso", p.204). **Scostamento deliberato dal documento di design**, motivato dal manuale: il riposo **breve**
  NON la interrompe (è "un'ora di attività leggera", non sonno), il riposo **lungo** sì (si dorme almeno 6 ore, e
  una creatura addormentata è priva di sensi → incapacitata).

  **Feature 3 — oggetti magici e sintonia lato giocatore.** `MasterMagicItemsView` estratta in
  `ui/views/magic_items_view.py`, con un parametro opzionale `character`: **zero duplicazione**, la Modalità Master
  usa lo stesso componente (`MasterMagicItemsView is MagicItemsView`, c'è un test). Nuova voce di sidebar "Oggetti"
  accanto a "Talenti" — stessa natura, un compendio indipendente dal personaggio. "Aggiungi alla mia scheda" crea
  un `InventoryItem` con la descrizione ufficiale integrale, stessa convenzione del Generatore Oggetti Magici del
  master. **Sintonia** (DMG p.138, riletto visivamente): nuove colonne
  `inventory_items.requires_attunement`/`is_attuned` — `requires_attunement` vive sull'oggetto e non solo nel
  catalogo, perché un oggetto homebrew può richiederla. Nuova `core/equipment_manager.can_attune()`: applica le due
  regole del manuale — massimo 3 oggetti, e "una creatura non può entrare in sintonia con più di una copia di un
  determinato oggetto" — e quando rifiuta **spiega perché citando la pagina**, invece di fallire in silenzio.
  Contatore "Sintonia: N / 3" con i tre slot sempre visibili in Inventario.

  **Feature 2b — le 15 condizioni.** `data/game_data/conditions.json`: le 14 condizioni dell'Appendice A trascritte
  **leggendo visivamente** le pagine 290-292 del PHB italiano (`pdftoppm`, mai `pdftotext`/OCR, mai tradotte
  dall'inglese — la terminologia non è deducibile: Restrained→Trattenuto, Grappled→Afferrato). L'Indebolimento
  resta su `characters.exhaustion_level`: è l'unica con livelli cumulativi invece che on/off. Nuova tabella
  `character_conditions` (tabella e non colonne: le condizioni possono essere più di una insieme e ognuna ha una
  fonte diversa). Sezione a chip in Combattimento con `CardPicker` (descrizione visibile **prima** di scegliere,
  stesso pattern di incantesimi e talenti); click sul chip → testo integrale + "Rimuovi". **Promemoria contestuali
  in sola lettura**: accanto ai tiri per colpire compare "Svantaggio ai tiri per colpire — Avvelenato, Trattenuto",
  accanto ai TS "Svantaggio ai tiri salvezza su Destrezza — Trattenuto", e la velocità mostra 0 se
  Afferrato/Trattenuto. Il campo `effects` del JSON è dichiarato **non testo del manuale** ma la stessa
  informazione dei bullet resa leggibile dal codice; l'app segnala, non applica.

  **Feature 4b — assegnazione dei PE.** Reintrodotta `get_level_from_xp()` in `config/settings.py` (era stata
  rimossa nella pulizia del 2026-07-26 perché senza chiamanti; il documento di design ne aveva previsto il
  ritorno). Nuova `character_repo.add_xp()` — **l'unica scrittura del master su una scheda giocante in tutto il
  progetto**, autorizzata esplicitamente e sempre preceduta da conferma. Il dialog elenca i mostri con la casella
  pre-spuntata su chi è a 0 PF o è stato rimosso (un nemico in fuga o aggirato lo decide il master, non
  un'euristica), ricalcola dal vivo "PE totali ÷ PG = a testa", lascia il totale modificabile a mano (la DMG
  prevede PE bonus narrativi), e il secondo passo mostra per ciascun PG "Thorin: 6.400 → 6.520 PE · sale al livello
  5". **Nessun level-up automatico**: sale il giocatore dalla propria scheda.

  **Verificato** con una batteria di **277 controlli** (`dnd_app/test_fase_4.py`, DB temporaneo isolato via
  `tempfile.mkdtemp()` + `HOME` separato — mai il DB reale; `FakePage` + scansione ricorsiva dell'albero dei
  controlli, pattern già consolidato). In sintesi: parser dei dadi su formule valide e 8 malformate, 500 tiri
  sempre in range, vantaggio/svantaggio con RNG deterministico e il dado scartato corretto; tutti i modificatori
  confrontati con i valori PHB attesi (Maestria che raddoppia, `saving_throw` accettato accanto a `save`, arma
  Versatile a una/due mani, `magic_damages` malformato che non rompe il tiro); i 9 casi del TS contro morte
  pilotati end-to-end sul DB (20 naturale, 1 naturale, terzo successo, terzo fallimento, clamp); pannello
  posizionato e non a tutto schermo, storico limitato, formula non tirabile che ritorna `None`, `on_result` che
  esplode senza annullare il tiro; iniziativa con 200 tiri in range e "tira per tutti" che lascia intatto il PG a
  99; concentrazione in tutti i suoi percorsi (CD ai valori di confine 20/22 danni, caduta a 0 PF senza chiedere il
  TS, avviso prima di sostituire); sintonia con quarto oggetto e doppia copia rifiutati con la citazione della
  pagina; le 14 condizioni con nomi confrontati uno a uno contro l'Appendice A e i quattro promemoria contestuali
  verificati nel testo renderizzato; PE scritti su entrambi i PG con il livello risultante mostrato. Rieseguita
  anche la batteria della Fase D (101 controlli). `compileall` + `pyflakes` puliti (solo il rumore preesistente di
  `from config.settings import *`).

- **Artefatti della DMG (2026-07-30) — tabelle complete, 5 artefatti su ~7.** Capitolo 7 «Tesori», sezione
  «Artefatti» (pag. 219-225), letta visivamente (`pdftoppm -r 150`, mai `pdftotext`/OCR). **Scarto pagina
  fisica/stampata confermato in +1** per questa sezione — va sempre riverificato per ogni capitolo, mai assunto da
  uno diverso.

  `data/game_data/artifacts.json`: le **4 tabelle d100 complete** (Proprietà Benefiche Minori 9 righe, Benefiche
  Maggiori 9, Nocive Minori 18, Nocive Maggiori 19), la copertura 1-100 di ciascuna **verificata senza buchi né
  sovrapposizioni**; i 7 suggerimenti su come distruggere un artefatto; e 5 artefatti trascritti per intero con
  lore e proprietà nominate: **Ascia dei Signori dei Nani**, **Bacchetta di Orcus**, **Globo dei Draghi**, **Libro
  delle Fosche Tenebre**, **Libro delle Imprese Eroiche**.

  Nuovi getter in `GameDataLoader` (`get_artifacts`, `get_artifact`, `get_artifact_property_table`,
  `roll_artifact_property`) — nessun modulo `core/` dedicato: è un singolo lookup su una tabella già pronta, stesso
  principio già motivato per `roll_madness_effect()`. Nuovo `ui/views/master/master_artifacts_dialog.py` + pillola
  "Artefatti" nella barra strumenti della Sezione Master: due schede, l'elenco degli artefatti con la scheda
  completa al click e il generatore che tira 1d100 su una delle quattro tabelle mostrando tiro, intervallo e testo.

  **Perché non nel compendio Oggetti Magici**: gli artefatti hanno un formato strutturalmente diverso dalle 264
  voci A-Z (nome/categoria/rarità/descrizione) — ognuno è un pezzo unico con la propria storia, proprietà nominate
  e tabelle di proprietà casuali. È il motivo per cui erano rimasti fuori fin dalla trascrizione del compendio.

  **Cosa manca, dichiarato anche nel dato stesso** (`_incomplete_note` in `artifacts.json`, mostrato nella UI):
  «Occhio e Mano di Vecna» (pag. 225-226) e «Spada di Kas» (pag. 226). Le loro pagine non sono ancora state lette
  visivamente e, per la regola del progetto, non vanno scritte a memoria.

  **Verificato** (sezione 11 della batteria Fase 4): copertura d100 e assenza di sovrapposizioni su tutte e 4 le
  tabelle, 200 tiri per tabella sempre risolti e nel range, ogni artefatto con
  nome/sottotitolo/lore/pagina/proprietà e la propria voce "Proprietà Casuali", lookup case-insensitive, dialog
  pilotato end-to-end (elenco, scheda della Bacchetta di Orcus con lore e proprietà nominate, cambio scheda, tiro
  che produce "d100 = N").

- **Artefatti — completata la trascrizione: «Occhio e Mano di Vecna» e «Spada di Kas» (2026-07-31).** Chiusa
  l'ultima voce aperta della sezione «Artefatti» della DMG. Pagine lette visivamente (`pdftoppm -r 150`, mai
  `pdftotext`/OCR).

  **Scarto pagina fisica/PDF verificato di nuovo** (come richiesto dalla nota di audit generale — va sempre
  riconfermato per ogni capitolo): per questa sezione lo scarto è **PDF = pagina stampata − 1**. Confrontando col
  render, «Occhio e Mano di Vecna» occupa le pagine stampate **225-226** (lore + sintonia su 225, proprietà +
  distruzione su 226) e «Spada di Kas» occupa per intero la pagina stampata **227** — non 226 come indicato nella
  nota provvisoria lasciata nel dato (`_incomplete_note`, ora rimossa): quella nota era una stima non ancora
  verificata visivamente, la lettura ora corregge il numero.

  `data/game_data/artifacts.json`: aggiunti i 2 artefatti mancanti, ognuno con lore completa e le proprietà
  nominate («Proprietà Casuali», «Proprietà dell'Occhio», «Proprietà della Mano», «Proprietà dell'Occhio e della
  Mano», «Distruggere l'Occhio e la Mano» per Vecna; «Proprietà Casuali», «Spirito di Kas», «Incantesimi»,
  «Senziente», «Personalità», «Distruggere la Spada» per Kas). Il file arriva così a **7 artefatti su 7**, la
  sezione «Artefatti» della DMG è completa. `_source` aggiornato a "pag. 219-227", `_incomplete_note` rimossa
  (non più applicabile). Nessuna modifica di codice: `master_artifacts_dialog.py` itera genericamente su
  `art.get("properties", [])`, quindi i due nuovi artefatti compaiono nella UI (elenco + generatore) senza
  toccare la view — solo il commento di intestazione con il range di pagine è stato allineato.

  **Verificato**: `python3 -c "json.load(...)"` conferma JSON valido, 7 voci in `artifacts`, ognuna con
  `source_page` e lista `properties` non vuota.

- **Bottom nav resa scorrevole (2026-07-30)** — con l'aggiunta della voce "Oggetti" (Fase 4, feature 3) le voci
  della bottom navigation sono passate a 9: su un telefono da 375px la ripartizione a fisarmonica le avrebbe
  portate a ~41px di larghezza, sotto i 48dp minimi consigliati per un tap-target. Le voci hanno ora una larghezza
  garantita di 68px e la barra scorre orizzontalmente quando non ci stanno tutte, invece di comprimerle
  ulteriormente. Verificato con un controllo dedicato nella batteria della Fase D.

- **4 correzioni su segnalazione di Davide (2026-07-30, subito dopo la Fase 4).**

  1. **`ImportError` all'apertura di "Oggetti Magici" in Modalità Master** — l'app si apriva su una schermata
     bianca con «cannot import name `_rarity_color`». Causa: estraendo `MasterMagicItemsView` in
     `ui/views/magic_items_view.py` (feature 3) il file del Master era diventato uno shim che re-esportava **solo
     la classe**, ma `master_magic_item_generator_dialog.py` importava da lì anche gli helper privati di
     formattazione. **È esattamente lo stesso tipo di bug già documentato in questo file per il rename
     `_RARITY_COLORS`**, e per lo stesso motivo: `compileall` e `pyflakes` non vedono un `ImportError` che esiste
     solo a runtime, e la mia verifica "importa tutti i moduli" non era stata rieseguita dopo l'estrazione. Fix: il
     generatore punta alla nuova sede canonica, e lo shim ri-esporta anche gli helper (elencati in `__all__`, così
     pyflakes non li segnala come inutilizzati). **Guardia aggiunta alla batteria**: un controllo che importa
     davvero **tutti i 74 moduli** del progetto, non solo li compila — è la cosa che avrebbe intercettato sia
     questo bug sia quello di luglio.

  2. **Il menu laterale di Note di Campagna e Diario non scorreva** — con la finestra ridotta le categorie in fondo
     (Fazioni, Eventi…) restavano fuori schermo e non c'era modo di raggiungerle. Causa: la lista delle voci era
     una `ListView(expand=True)` dentro una `Column` **non** scrollabile — le voci sopra si prendevano tutta
     l'altezza e il resto veniva semplicemente tagliato. Fix: il pannello è ora un'unica regione scrollabile e la
     lista una `Column` normale — niente scroll annidato, stessa regola già stabilita per il `CardPicker`.
     Applicato a entrambe le viste gemelle (`master_notes_view.py`, `diary_view.py`).

  3. **1 e 20 naturali non sommano più il modificatore** — prima il pannello mostrava "1 +7 = 8" etichettato come
     fallimento critico, che è fuorviante: il tiro è già deciso. Ora mostra il **dado naturale** (1 o 20) con
     l'etichetta "FALLIMENTO CRITICO"/"SUCCESSO CRITICO", la riga di dettaglio dice esplicitamente «il modificatore
     non si applica», il verdetto contro la CD non compare (non ha senso su un naturale) e lo storico usa lo stesso
     valore, colorato. Applicato anche al TS di Costituzione della concentrazione, perché l'app mostri sempre la
     stessa cosa. **Nota onesta**: il PHB 2014 prevede l'auto-successo/auto-fallimento solo per i tiri per colpire
     e i tiri salvezza contro morte, non per prove e TS generici — questa è una convenzione da tavolo scelta da
     Davide, non una regola del manuale, ed è annotata come tale nel codice.

  4. **Sezione "Oggetti" rimossa dalla sidebar del giocatore** — alla domanda di Davide «ha senso nella scheda
     giocatore?», risposta concordata: no. È di fatto un manuale del DM, e gli oggetti che un personaggio possiede
     hanno già il testo ufficiale integrale nel proprio Inventario; per metterne uno sulla scheda di un giocatore
     il Master usa il Generatore Oggetti Magici, che ha già "Aggiungi all'inventario di…". Rimossi la voce di
     sidebar, il parametro `character` della vista e il metodo `_add_to_sheet` (~45 righe), coerente con la regola
     YAGNI già applicata nella pulizia del 2026-07-26. Effetto collaterale positivo: la bottom nav torna a 8 voci.

  **Verificato**: batteria Fase 4 salita a **298 controlli** (nuova sezione 12 dedicata a queste 4 regressioni:
  import di tutti i moduli, re-export dello shim, scroll dei due pannelli laterali, 1/20 naturale con RNG
  deterministico e confronto col totale grezzo che *sarebbe* stato mostrato, assenza della voce "Oggetti" dalle
  `SECTIONS`), Fase D rieseguita (101), `compileall` e `pyflakes` puliti.

---

- **Sistema Bottino — passi 1-5 di `loot_design.md` §8 (2026-07-31).** I passi 1 e 2 (schema `loot_stash_entries` +
  `data/repositories/loot_repo.py`, e `core/loot_calculator.py`) erano già stati completati e verificati in una
  sessione precedente lo stesso giorno (vedi `dnd_app/docs/funzionalita_e_todo.md` per il dettaglio di quei due
  passi). Questa sessione ha completato i passi 3-5, chiudendo tutto tranne il passo 6 (deposito lato giocatore,
  bloccato sul modello mondo del Multiplayer).

  **Passo 3 — tab "Bottino" nella Sezione Master**: `ui/views/master/master_loot_view.py` (`MasterLootView`),
  quinta voce di `_TABS` in `master_view.py`. Switch a pillole Archivio/Deposito (entrambi con `world_id=""`,
  coerente col fatto che il modello mondo non esiste ancora), card per voce con **assegna** (apre il dialogo del
  passo 4), **sposta** (`loot_repo.move_entry()` — un `UPDATE`, non elimina+ricrea, per non perdere id/timestamp),
  **modifica** (dialog dedicato; le voci "coins" passano da elimina+ricrea perché `loot_repo.update_entry()` non
  tocca le 5 colonne valuta — aggiungere una funzione di scrittura usata da un solo chiamante non ne valeva la
  pena), **elimina** (con conferma). "+ Aggiungi voce" copre il caso raro di bottino non ancora collegato a un
  generatore.

  **Passo 4 — dialogo di assegnazione condiviso**: `ui/views/master/master_loot_assign_dialog.py`
  (`show_loot_assign_dialog(page, items, on_committed=None)`). Contratto d'ingresso deliberatamente disaccoppiato
  dalla sorgente: `items` è una lista di dict costruiti da tre funzioni pubbliche del modulo —
  `simple_item()`/`coins_item()`/`item_from_stash_entry()` — mai `LootStashEntry` o il formato interno di un
  generatore passato direttamente, così lo stesso dialogo serve sia un tiro effimero mai salvato sia una voce già
  in stash. Per ogni voce non monetaria: quantità 1 → un destinatario (personaggio/Deposito/Archivio) con un
  pulsante "distribuisci a caso" tra i personaggi; quantità >1 → contatori interi per destinatario, validati con
  `split_quantity_by_shares()` che **impone la somma esattamente uguale al totale** (non "non superiore", come
  invece diceva alla lettera `loot_design.md` §4.2 — la funzione già scritta e testata al passo 2 è stata presa
  come fonte di verità, il documento di design descriveva l'intento non ancora verificato contro l'implementazione
  reale). Monete: quote percentuali solo tra personaggi (mai deposito/archivio, per `loot_design.md` §5.1),
  modalità "per denominazione"/"per valore", anteprima dal vivo via `split_coins_by_percentage()`. **Nessuna
  sezione "destinazione del resto"** prevista da §5.3 del design doc: il metodo del resto più alto già
  implementato al passo 2 distribuisce sempre l'intero totale tra le quote incluse, senza mai lasciare resti
  scoperti — il problema che §5.3 descriveva è già risolto dall'algoritmo scelto, non serviva altra UI. Una sola
  schermata scrollabile con anteprima dal vivo per sezione, non il percorso guidato "Cosa/A chi/Monete/Riepilogo"
  a 4 passi del design doc: nessun dialog della Sezione Master usa un pattern a wizard, il pattern consolidato è
  "un'unica `ft.Column` con area di anteprima aggiornata dal vivo" (`master_treasure_dialog.py` docet) — motivato
  nel docstring del modulo. Validazione tutto-o-niente prima di ogni scrittura: se anche una sola voce inclusa
  fallisce, nessuna scrittura avviene e l'errore compare in un `Text` sotto le sezioni.

  **Passo 5 — wiring nei 6 punti di generazione**: "Assegna…"/"Salva nell'archivio" aggiunti accanto alle
  scorciatoie esistenti (mai rimosse, restano il caso più semplice a un solo destinatario) in
  `master_treasure_dialog.py` (monete + gemme/oggetti d'arte + oggetti magici + cimelio del tiro corrente, tutti
  insieme), `master_magic_item_generator_dialog.py` (gli oggetti generati), `magic_items_view.py` — il Compendio,
  che prima era **sola consultazione**: ora si può assegnare una delle 264 voci per nome esatto, non solo pescando
  a caso dal generatore — `master_artifacts_dialog.py` (lore + tutte le proprietà nominate per esteso nella
  `description`, mai un riassunto, stessa regola di `LootStashEntry`), `master_health_hazards_dialog.py` (i 14
  veleni; Malattie e Follia restano di sola consultazione, non sono oggetti d'inventario). Nuovo helper condiviso
  `ui/widgets.show_snack()`: centralizza il pattern `ft.SnackBar` + `page.show_dialog()` già duplicato due volte in
  `home_view.py` (`_show_success`/`_show_error`), usato dai 5 punti di wiring per il feedback "Assegnato"/"Salvato
  nell'archivio".

  **Verificato** (senza mount Flet — non c'è un event loop in sessione non interattiva — su un DB SQLite temporaneo
  isolato nella sandbox, mai quello reale): `loot_repo` CRUD completo (`create_entry`/`get_entries`/`move_entry`/
  `update_entry`/`delete_entry`); `simple_item`/`coins_item`/`item_from_stash_entry`/`save_items_to_stash`
  end-to-end (creata una voce "gem" e una "coins", spostata tra archivio e deposito, ricostruita da
  `LootStashEntry`, ri-salvata); `MasterLootView()` costruibile senza eccezioni; la stessa sequenza di chiamate
  usata da `_on_confirm()` del dialogo di assegnazione replicata a mano con 2 personaggi di test — 101 mo con quote
  50/50 → somma finale sulle due schede esattamente 101 (50+51, resto assegnato correttamente), 3 pozioni ripartite
  2+1 tra due personaggi → inventari corretti. `python3 -m py_compile` e `pyflakes` puliti su tutti e 9 i file
  toccati/creati.

  **Verifica di coerenza con la documentazione**: prima di riprendere questo lavoro è emerso che i passi 1-2 erano
  già stati implementati in una sessione precedente lo stesso giorno, ma **né `CLAUDE.md` né il banner di
  `loot_design.md` erano stati aggiornati** — entrambi dicevano ancora "sola progettazione, nessuna riga di
  codice scritta", mentre `dnd_app/docs/funzionalita_e_todo.md` era corretto e aggiornato. Corretti entrambi i
  documenti stale in questa sessione, oltre ad aggiungere questa voce.

---

- **2 bug nel dialogo di assegnazione del Bottino, trovati da Davide al primo utilizzo reale (2026-07-31, stesso
  giorno del rilascio dei passi 3-5).** Non emersi nella verifica precedente perché fatta senza mount Flet (nessun
  event loop disponibile in sessione non interattiva) — la lezione: per codice UI Flet nuovo, **leggere
  `dnd_app/docs/regole_flet_api.md` prima di scrivere**, non solo verificarlo dopo. Non l'avevo fatto per questi due
  file nuovi.

  1. **"Assegna…" sul Tesoro andava in crash con `TextField.__init__() got an unexpected keyword argument
     'suffix_text'`.** In `master_loot_assign_dialog.py`, il campo percentuale delle quote monete usava
     `suffix_text="%"` — parametro che non esiste su `ft.TextField` in Flet 0.85.3 (verificato per introspezione:
     `inspect.signature(ft.TextField.__init__)` elenca `suffix`, non `suffix_text`). Fix: `suffix="%"` (accetta
     `str | Control | None`). Il crash compariva solo per il Tesoro perché è l'unico generatore che produce
     sempre anche una voce "coins", l'unica a toccare quel campo.

  2. **"Assegna…"/"Salva nell'archivio" su Oggetto Magico/Compendio/Artefatti/Veleni mostravano un riquadro
     grigio al posto della card**, sia nel dialogo di assegnazione sia nella lista della tab "Bottino" — nessun
     errore Python (il pulsante "Genera Tesoro" invece l'errore lo mostrava, per il bug #1 sopra: due sintomi
     diversi, due bug diversi, non lo stesso). Causa: sia `_render_item_card` (`master_loot_assign_dialog.py`) sia
     `_entry_card` (`master_loot_view.py`) avevano una `ft.Row(wrap=True, ...)` con dentro un `ft.Text(...,
     expand=True)` — combinazione che `regole_flet_api.md` non elencava ancora esplicitamente ma che è la stessa
     famiglia di bug già documentata lì ("EXPAND=True su Column dentro Row dentro ListView", "self.controls
     riassegnato"): `wrap=True` genera lato Flutter un widget `Wrap`, che non supporta figli `Expanded` (solo
     `Row`/`Column` lo fanno) — la combinazione produce un crash **silenzioso lato Flutter**, senza eccezione
     Python, sostituendo il widget con un riquadro vuoto (grigio, non bianco come nell'esempio già in doc, ma
     stessa causa strutturale: un vincolo di layout che Flutter non riesce a risolvere). Confermato **non** essere
     un problema di icone (`ft.Icons.X` note in uso altrove senza problemi) né di `design.field_style()` spread
     (pattern già in uso altrove). Fix: rimosso `wrap=True` dalle due Row con un figlio `expand=True`, il testo
     tronca con `no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS` invece di andare a capo — stesso pattern già
     usato con successo per il titolo dell'header di `master_view.py`. **Aggiunta la regola a
     `regole_flet_api.md`** perché non ricapiti: "wrap=True su una Row/Column con un figlio expand=True → crash
     Flutter silenzioso (riquadro vuoto, nessun errore Python)".

  **Verificato** (di nuovo su DB temporaneo isolato, senza mount Flet reale — non c'è modo di provare il vero
  rendering Flutter in sessione non interattiva): `python3 -m pyflakes`/`py_compile` puliti sui 2 file; costruite a
  mano tutte le card di `MasterLootView._entry_card()` per ogni `entry_kind` (item/magic_item/artifact/poison/gem/
  coins) senza eccezioni; `ft.TextField(suffix="%")` verificato per introspezione della firma reale di
  `ft.TextField.__init__` nel pacchetto `flet==0.85.3` installato. **La resa visiva finale nel client Flutter
  resta da confermare da Davide** — è la stessa categoria di verifica che nessuna sessione headless può fare
  (vedi la nota analoga per il Multiplayer).

  **Bug 3, segnalato subito dopo da Davide una volta il dialogo tornato visibile**: "Conferma assegnazione" non
  dava alcun feedback e non chiudeva il dialogo — non si capiva se l'assegnazione fosse riuscita. Causa in
  `master_loot_assign_dialog.py._on_confirm()`: `show_snack(page, ...)` veniva chiamato **prima** di
  `page.pop_dialog()`. `page.show_dialog()`/`page.pop_dialog()` in Flet 0.85.3 operano su un singolo dialogo
  attivo, non uno stack: aprire lo SnackBar (che usa `show_dialog()` al suo interno, per via della regola
  "SnackBar è un DialogControl") mentre l'`AlertDialog` di conferma era ancora aperto lo sostituiva
  silenziosamente, e il `pop_dialog()` subito dopo chiudeva lo SnackBar appena aperto invece del dialogo di
  conferma — risultato: nessun feedback visibile e il dialogo restava aperto. Fix: invertito l'ordine
  (`pop_dialog()` poi `show_snack()`), stesso ordine già corretto in `home_view.py._confirm_import()`. Essendo
  `show_loot_assign_dialog()` condiviso da tutti e 6 i punti di generazione più la tab "Bottino", un solo fix li
  copre tutti.

- **2 generatori senza collegamento alla sezione che dovrebbero alimentare, segnalati da Davide (2026-07-31, stessa
  giornata).**

  1. **"Genera Incontro per Ambiente" non aveva modo di creare l'incontro nella tab "Incontri"** — tirava e
     mostrava il risultato (testo + link "Vedi scheda" per le creature risolte nel bestiario) ma si fermava lì, a
     differenza del Generatore di Incontri Casuali (`master_encounter_generator_dialog.py`), che il pulsante
     "Crea Nuovo Incontro" ce l'ha da sempre. Aggiunto "Aggiungi Incontro" a `master_forest_encounters_dialog.py`:
     crea un `MasterEncounter` (`master_repo.create_encounter`) con le note = testo integrale della riga tirata, e
     un membro "adhoc" per ciascuna creatura della riga risolta nel bestiario (stesse `ac`/`hp_max`/`xp` già usate
     da "Vedi scheda"). **Deliberatamente una sola copia per creatura**: la tabella DMG scrive le quantità in
     prosa dentro `text` ("2d4 gnoll", "1d4 gnoll and 2d4 iene"), mai come numero strutturato in `creatures` —
     tirare quel dado e moltiplicare i membri sarebbe stato inventare un comportamento non specificato dalla
     fonte. Il Master legge la riga (resta nelle note dell'incontro) e aggiunge le copie in più a mano con
     "+ Aggiungi mostro", funzione già esistente in `MasterEncounterView`. Verificato end-to-end su DB isolato:
     tiro su "Foresta Silvana" con risultato "1d4 centauri", incontro creato, membro "Centauro" risolto nel
     bestiario con CA/PF corretti.

  2. **La scheda "Proprietà Casuali" degli Artefatti tirava e mostrava ma non salvava/assegnava** — unico
     generatore della Sezione Master senza quel collegamento (la scheda di un artefatto specifico, invece,
     l'aveva già dal passo 5 del Bottino). Aggiunte le stesse "Assegna…"/"Salva nell'archivio" a
     `master_artifacts_dialog.py`, operando sull'**ultimo tiro soltanto** (non sull'intero storico visibile in
     `result_col` — stesso principio "un solo risultato corrente" già seguito da Tesoro/Oggetto Magico).
     `entry_kind="item"`, non `"artifact"`: una proprietà casuale isolata non è un oggetto, è un ingrediente che
     il Master userebbe per comporre un artefatto o oggetto magico homebrew — trattarla come un intero artefatto
     avrebbe frainteso cosa rappresenta il dato. Verificato end-to-end: tiro su "Benefiche minori", salvataggio
     nell'archivio, voce ritrovata con nome/descrizione corretti.

  **Verificato per entrambi**: `python3 -m pyflakes`/`py_compile` puliti, nessun conflitto `wrap=True`+`expand=True`
  (bug della voce precedente) nei file toccati, import completo di `ui.app` senza eccezioni.

- **5 richieste sulla sezione "Incontri" e sui generatori del Master, segnalate da Davide (2026-08-03).**

  1. **Nessun modo di consultare la scheda di un npc/mostro dentro un incontro, né di tirare i suoi dadi** — a
     differenza della scheda del personaggio (Fase 4, `core/character_stats.py` + `ui/components/roll_panel.py`).
     Aggiunti due `IconButton` ("Vedi scheda"/"Tira dadi") su ogni riga combattente `kind` npc/adhoc in
     `MasterEncounterView._member_card()` (mai per `kind="character"`: i PG restano gestiti dal giocatore sulla
     propria scheda). Risoluzione dello stat block completo, mai inventata quando manca:
       - `kind="npc"` → nuova `master_repo.get_npc_by_id()` (mancava, stesso pattern di `get_encounter_by_id`) +
         `has_stat_block`, convertito con `creature_entry_dict()` già esistente in `monster_picker.py`;
       - `kind="adhoc"` da "Mostro dal Bestiario" → il nome (al netto del suffisso numerico "Goblin 2" → "Goblin",
         estratto in `_strip_copy_suffix()` per essere condiviso con `_on_roll_all_initiative()`, che duplicava la
         stessa logica come funzione locale `_base_name`) risolve in `monsters.json`;
       - `kind="adhoc"` da "Creazione Rapida" → nessuno stat block esiste da nessuna parte: "Vedi scheda" mostra
         solo CA/PF/mod. Destrezza/PE già tracciati con una nota esplicita, "Tira dadi" offre solo Prova/TS
         Destrezza (l'unico dato noto) più il tiro personalizzato.
     "Tira dadi" riusa **lo stesso motore già esistente per il personaggio** invece di duplicarlo:
     `core/dice.py` (formule, vantaggio/svantaggio, critico), `RollSpec` di `core/character_stats.py`,
     `ui/components/roll_panel.show_roll()` (pannello persistente in `page.overlay`, funziona già mentre un
     `AlertDialog` è aperto — verificato che il pattern fosse già in uso da `combattimento_tab.roll_hit_dice()`
     prima di riusarlo qui). Prove di caratteristica sempre tutte e 6 (mod. grezzo, PHB Cap.7); Tiri Salvezza
     mostrati **solo per le caratteristiche stampate** nello stat block (bonus già finale, mai ricalcolato dal
     GS/proficiency bonus — quelle non stampate equivalgono per regolamento alla prova di caratteristica, niente
     riga duplicata); Abilità per ogni voce stampata in `skills`. Attacchi/danni restano testo libero nello stat
     block (mai un numero strutturato in `monsters.json`): un campo "Tiro personalizzato" (validato con
     `dice_engine.parse_formula()` prima di tirare, altrimenti `show_snack` di errore) copre quel caso senza
     inventare un parser di prosa italiana.

  2. **Non era chiaro che il numero nella pillola a sinistra di ogni combattente fosse l'iniziativa** — aggiunta
     un'etichetta "INIZIATIVA" (maiuscolo, 8px, `text_3`) sopra il badge numerico in `_member_card()`, in una
     `Column` che sostituisce il precedente `Container` isolato.

  3. **Le pillole dei generatori rapidi (Tesoro/Oggetto Magico/Trappola/Veleni/Ambiente/Artefatti) in cima alla
     Sezione Master non si distinguevano dalla tab bar sottostante** — aggiunta un'etichetta di sezione "GENERATORI
     RAPIDI" (maiuscolo, icona dado) sopra la riga di pillole in `MasterView._build_tools_row()`.

  4. **L'archivio degli incontri ("Termina Incontro") non era consultabile da nessuna parte dell'interfaccia** —
     aggiunto uno switch "Attivi"/"Archiviati" in `MasterEncounterListView`, stesso pill-switch già in uso in
     `MasterLootView` per Archivio/Deposito. Filtro **client-side** su `MasterEncounter.is_archived` (nessuna
     nuova funzione di repository: `master_repo.get_encounters(include_archived=True)` già restituiva tutto). In
     "Archiviati" la creazione di nuovi incontri è nascosta (creerebbe un incontro attivo mentre si guarda una
     vista di sola consultazione, comportamento confuso) e ogni riga offre "Riapri"
     (`master_repo.archive_encounter(id, archived=False)`, già supportato come "house rule" dal repository fin
     dalla sua scrittura originale) oltre all'eliminazione definitiva già esistente.

  **Verificato end-to-end su DB temporaneo isolato** (monkeypatch di `data.database.get_db_path`, non si può
  toccare `HOME` in sessione: romperebbe la risoluzione del pacchetto `flet` installato in user-site, legato
  all'`HOME` reale): creato un incontro con un membro `npc` (da `create_npc_from_monster`, stat block completo),
  due membri `adhoc` da bestiario con suffisso di copia ("Goblin 1"/"Goblin 2"), un membro `adhoc` da Creazione
  Rapida; risolti correttamente tutti e 3 i casi di stat block (npc → rubrica, adhoc/bestiario → `monsters.json`
  via nome ripulito dal suffisso, adhoc/manuale → `None` senza eccezioni). Istanziate a mano `MasterEncounterView`,
  `MasterEncounterListView` (incluso lo switch Attivi/Archiviati) e `MasterView` sulla tab "encounters": nessuna
  eccezione in costruzione. Richiamati `_open_stat_block_click()`/`_open_dice_click()` per tutti e 4 i combattenti
  di prova con una `FakePage` che intercetta `show_dialog()`: 8 dialoghi costruiti senza eccezioni. Verificato
  l'archivio: creato un secondo incontro, archiviato, confermato che compaia nel filtro "Archiviati" e non in
  "Attivi", riaperto, confermato il ritorno tra gli "Attivi". `python3 -m pyflakes`/`py_compile` puliti su tutti i
  file toccati. Nessun conflitto `wrap=True`+`expand=True` nei blocchi nuovi (verificato anche con lo script di
  bilanciamento delle parentesi già in uso nella voce precedente — le uniche corrispondenze trovate erano righe
  preesistenti già verificate, non toccate da questa modifica). **La resa visiva finale nel client Flutter reale
  resta da confermare da Davide**, come per ogni modifica UI verificata in sessione headless.

- **Multiplayer, passo 2 di `multiplayer_design.md` — "Modello mondo, senza rete" (2026-08-05).**

  Prima implementazione di codice del progetto Multiplayer (i passi precedenti erano solo progettazione + il
  Bottino, indipendente). Schema, identità dispositivo, repository, matrice permessi, il meccanismo comando →
  validazione → evento (`LocalBackend`), e una UI minimale per verificarlo end-to-end senza dipendere dalle
  istanze di personaggio (passo 3, non toccato) né dalla rete LAN (passo 4, non toccato).

  1. **Schema** (`data/database.py`): 4 tabelle nuove (`worlds`, `world_members`, `world_events`,
     `world_change_requests`) esattamente come da §8 del design doc, e 5 colonne su `characters`
     (`world_id`/`origin_character_id`/`owner_device_id`/`is_replica`/`world_seq`, tutte `''`/`0` di default —
     un personaggio esistente non entra mai in un mondo da solo). `data/models.py`: dataclass `World`,
     `WorldMember`, `WorldEvent`, `WorldChangeRequest`.

  2. **Identità del dispositivo** (`ui/device_identity.py`) — la parte con più rischio scoperto durante
     l'implementazione. La decisione iniziale con Davide ("usa `page.client_storage`") si è rivelata basata su
     un'API che **non esiste più** in Flet 0.85.3: è stata sostituita da `ft.SharedPreferences`, un controllo
     `Service` — la stessa categoria di `ft.FilePicker`, che `regole_flet_api.md` documenta come strutturalmente
     rotto in web mode dalla 0.80.1 in poi (flet-dev/flet#6040/#6250/#6251). Corretto con Davide durante la
     sessione: `resolve_device_id(page)` tenta comunque `SharedPreferences` in web mode (avvolto in try/except),
     e ricade su un id generato una volta per sessione (tenuto come attributo su `page`, si perde al refresh del
     browser) se il servizio non risponde. Su desktop/mobile resta `app_settings` (chiave `"device_id"`, un'unica
     identità stabile per installazione — corretto lì, perché un'installazione È un dispositivo fisico). **Verificato
     con un `FakePage`** che il tentativo `SharedPreferences` fallisce davvero fuori da una pagina Flet reale
     montata ("Control must be added to the page first") e che il ripiego di sessione scatta correttamente,
     restando stabile sulla stessa pagina e diverso tra pagine diverse — **il comportamento reale in un browser
     vero resta da verificare da Davide** (unico modo per sapere se `SharedPreferences` funziona davvero in web
     mode o è rotto come `FilePicker`).

  3. **`data/repositories/world_repo.py`** — CRUD mondi/membri, giornale eventi (`append_event`/
     `get_events_since`/`get_latest_seq`), `join_world_by_code` (idempotente: un secondo ingresso dello stesso
     `device_id` ritorna il membro esistente invece di duplicarlo), CRUD `world_change_requests` (schema pronto,
     non ancora usato — serve il passo 3). Codice d'ingresso a 6 caratteri con alfabeto senza `0/O/1/I/L`
     (`generate_join_code()`).

  4. **`core/world_permissions.py`** — matrice permessi pura (no Flet, no DB): ogni comando di §7 ha un ruolo
     minimo richiesto, fail-closed per un comando sconosciuto (owner incluso). `FORBIDDEN_CHARACTER_FIELDS`/
     `CHANGE_REQUEST_ALLOWED_FIELDS` codificano la tabella "vietato a chiunque tranne il giocatore" e il
     sottoinsieme negoziabile con una richiesta di modifica (§7.1) — competenze/talenti non compaiono come nomi
     di campo perché non sono colonne di `characters`.

  5. **`core/world_backend.py`** — `WorldBackend` (interfaccia) + `LocalBackend` (unica implementazione di
     questo passo: scrive sul DB di questo stesso dispositivo, sufficiente a rendere il deploy web "multi-utente
     vero" già oggi). Registro comandi estendibile via `register_handler(kind)` — i passi successivi aggiungono
     handler, non modificano la classe. Handler operativi in questo passo: rinomina mondo, rigenera codice
     d'ingresso, promuovi/retrocedi/espelli membro, trasferisci proprietà, elimina mondo (nessun evento scritto
     per l'eliminazione: `world_events` è `ON DELETE CASCADE` su `worlds`, sparisce con lui). Guardie verificate:
     l'owner non può essere espulso, un player non può essere retrocesso (deve essere master), un master non può
     essere ripromosso, non ci si può trasferire la proprietà da soli.

  6. **Fix reale in `data/repositories/character_export.py`** (§14.1 del design doc, bug già individuato in
     progettazione, corretto ora che le colonne esistono davvero): `import_character()` azzera sempre le 5
     colonne mondo tramite il meccanismo `overrides` già esistente in `_insert_row()`, in **tutti e tre** i modi
     (`new`/`overwrite`/`copy`) — senza il fix, importare l'istanza di un mondo altrove avrebbe prodotto un
     personaggio marcato `is_replica=1` legato a un mondo inesistente, in sola lettura e non riparabile
     dall'interfaccia.

  7. **UI minimale** (`ui/views/world/world_view.py`, nuova cartella `ui/views/world/`) — elenco mondi del
     dispositivo, crea/unisciti (dialoghi), dettaglio con rinomina e zona pericolosa (solo owner), codice
     d'ingresso con rigenerazione, elenco membri con promuovi/retrocedi/espelli (visibilità dei pulsanti guidata
     da `world_permissions.can_perform`, mai un controllo hardcoded sul ruolo), registro eventi leggibile
     (`WorldEvent.summary`, più recenti in cima). Pillola "Mondi" sempre visibile in Home (mai un'azione nascosta,
     stesso principio già seguito per "Modalità Master") tramite `on_open_worlds`, nascosta se il callback non è
     passato. Routing in `ui/app.py`: `_show_worlds_view()` speculare a `_show_master_view()`.

  **Verificato end-to-end su DB temporaneo isolato**, nuova batteria dedicata `test_mondo_senza_rete.py` (139
  controlli, stesso pattern di `test_fase_d.py`): schema, CRUD/giornale/join idempotente di `world_repo`, l'intera
  matrice di `world_permissions`, `LocalBackend` end-to-end (comando → evento → stato, incluse tutte le guardie
  sopra), il fix di `character_export` nei tre modi, `device_identity` (stabilità desktop, fallimento reale di
  `SharedPreferences` fuori da una pagina montata, ripiego di sessione stabile e distinto per pagina),
  `WorldsView` costruita e renderizzata nei due temi (lista vuota/con mondi, dettaglio owner con più sezioni di
  quello player). Rieseguite anche `test_fase_d.py` (101/101) e `test_fase_4.py` (297/298 — l'unico fallito,
  sull'onestà del file `artifacts.json`, è preesistente e indipendente da questa modifica: non tocca schema,
  repository o UI qui toccati). **Il passo 4 (rete LAN) resta l'unico modo per sapere se `SharedPreferences`
  funziona davvero in un browser reale** — va verificato da Davide aprendo due schede di un deploy web, non
  prima.

- **Multiplayer — passo 3 "Istanze di personaggio" completato (2026-08-05)**, subito dopo il passo 2 nella stessa
  giornata. Copre §6/§6.1/§6.2 del design doc: un personaggio locale (`world_id == ""`) può entrare in un mondo
  come istanza indipendente ("porta com'è" o "ricomincia dal 1° livello"), riprendere un'istanza già esistente
  senza duplicarla, e riportare i progressi dell'istanza sul personaggio locale con "Aggiorna il mio foglio".

  1. **`core/character_instances.py`** (nuovo modulo, no Flet) — cuore del passo:
     - `create_or_resume_instance(world_id, local_character_id, owner_device_id, mode)`: se esiste già un'istanza
       per la terna (mondo, origine, dispositivo) la riprende (`resumed=True`, `mode` ignorato — §6 "Riprendi" è
       automatico); altrimenti copia il personaggio locale con `character_export` (stesso meccanismo a
       introspezione già usato per `.dndchar`, zero duplicazione), la collega al mondo (`world_id`/
       `origin_character_id`/`owner_device_id`), e se `mode="fresh"` applica il reset completo. Guardia esplicita:
       un personaggio con `world_id` già valorizzato (cioè già un'istanza) non può diventare a sua volta
       l'origine di un'altra istanza — errore chiaro, non un fallimento silenzioso.
     - **Reset "Ricomincia dal 1° livello"** (`_reset_to_level_one`) — decisione confermata da Davide durante la
       sessione: non la lista minima del design doc (livello/PE/inventario/diario/condizioni), ma un reset
       completo che inverte anche ASI/talenti/competenze bonus presi dopo il 1° livello. Riusa
       `character_repo.undo_level()` — la stessa funzione già testata dietro "Scendi di livello" in
       `ProfiloTab` — chiamata una volta per ciascun livello da rimuovere invece che una sola volta. I PF vengono
       ricalcolati con la formula ESATTA di 1° livello (`max(1, dado_vita + mod_costituzione)`, PHB p.12), non
       con la stima di perdita usata dal decremento di un singolo livello. Stato di sessione/combattimento
       (tiri salvezza morte, turno in corso, concentrazione, frenesia, `ca_bonus`) azzerato per coerenza — non è
       materia di regolamento, assunzione dichiarata nel codice, non silenziosa. Il diario (`diary_entries`)
       viene svuotato sull'istanza; le Note di Campagna (`campaign_notes`, il Codex) restano intatte per
       esplicita scelta — il design doc dice solo "diario".
     - **Equipaggiamento iniziale automatico** (`_assign_default_starting_equipment`) — versione non interattiva
       dell'assegnazione già fatta a mano nel wizard: ogni scelta risolve sulla prima opzione (stesso indice
       preselezionato di default prima che il giocatore lo cambi), le armi "a scelta per categoria" prendono la
       prima arma della categoria, i placeholder "(a scelta)" degli strumenti si risolvono contro le competenze
       tool già registrate sul personaggio. Decisione confermata da Davide: nessuna interattività qui, è un reset
       automatico. L'algoritmo di scelta arma (`_weapon_choice_default`) è una piccola duplicazione voluta e
       commentata di `CreationSharedMixin._init_weapon_choice()`: non importabile da `core/` perché quel modulo
       porta `import flet`.
     - **`preview_refresh`/`apply_refresh`** (§6.1, "Aggiorna il mio foglio", sempre manuale, mai automatico) —
       `preview_refresh` costruisce un riepilogo prima/dopo (livello, PE, conteggio oggetti) per la conferma
       esplicita; `apply_refresh` esporta l'istanza e la reimporta con `mode="overwrite"` sullo stesso id del
       personaggio locale di origine (azzerando sempre le colonne mondo, §14.1 — il risultato resta locale a
       tutti gli effetti). Se il personaggio locale di origine è stato eliminato nel frattempo, crea un nuovo
       personaggio locale invece di fallire — comportamento esplicito, non un ripiego silenzioso.

  2. **Estensione mirata di `character_export.import_character()`** — nuovo parametro opzionale
     `target_id: str | None = None`, onorato solo con `mode="overwrite"`: permette di sovrascrivere un id diverso
     da quello scritto nel file esportato (necessario per "Aggiorna il mio foglio", che scrive sull'id del
     personaggio locale mentre esporta dall'id dell'istanza). Nessun impatto sull'uso esistente (import/export
     `.dndchar` da file, che non passa mai `target_id`).

  3. **Bug scoperto e corretto durante l'implementazione**: la dataclass `Character` in `data/models.py` non
     aveva mai ricevuto le 5 colonne mondo introdotte nel passo 2, nonostante lo schema DB le avesse già —
     `char.world_id` sollevava `AttributeError` al primo utilizzo reale in `core/character_instances.py`. Il
     gap era silenzioso (le colonne esistevano ma non venivano né lette né scritte da `character_repo.py`),
     quindi nessun rischio di perdita dati pregressi. Fix: 5 campi aggiunti alla dataclass, mapping aggiunto in
     `_row_to_character()`, le 5 colonne aggiunte all'SQL/parametri di `update()` — deliberatamente NON aggiunte
     a `create()`, così un personaggio nuovo resta locale di default tramite i default della colonna DB.

  4. **Home raggruppata per mondo** (`ui/views/home_view.py`) — `_partition_characters()` separa i personaggi
     locali dalle istanze possedute da QUESTO dispositivo (confronto su `owner_device_id`, mai solo su
     `world_id`: un'istanza di un altro giocatore visibile nello stesso DB — es. web mode multi-scheda — non deve
     mai comparire nella Home di chi non la possiede). Nessuna sezione per mondo se il dispositivo non possiede
     istanze: lista piatta identica a sempre, zero sorprese visive per chi non usa il Multiplayer. Card
     personaggio estesa con due azioni contestuali, mai entrambe sulla stessa card: "Aggiungi a un mondo"
     (dialogo: scegli mondo + porta com'è/ricomincia dal 1° livello) sui personaggi locali con almeno un mondo
     disponibile, "Aggiorna il mio foglio" (dialogo con anteprima diff + conferma) sulle istanze. `_list_signature`
     estesa con `world_id`/`owner_device_id` così un personaggio appena entrato in un mondo sposta sezione al
     prossimo refresh.

  **Verificato end-to-end** con una nuova batteria dedicata `test_istanze_personaggio.py` (62 controlli): reset
  "fresh" con inversione reale di un ASI di Forza (18→17, tracciato con la stessa identica sequenza di scritture
  del level-up vero in `profilo_tab.py`) e ricalcolo PF esatto, "porta com'è" senza alcun reset, idempotenza di
  "Riprendi" (stesso device → stesso id, device diverso → istanza indipendente), la guardia contro l'istanza di
  un'istanza, refresh con origine esistente e con origine eliminata, partizione locali/istanze nella Home
  (incluso il caso di un'istanza altrui invisibile a un dispositivo estraneo), nessuna eccezione senza
  `device_id` risolto. La batteria richiama anche `test_mondo_senza_rete.py` come controllo di non-regressione
  (139/139 verde) essendo condivisi `data/models.py`, `character_repo.py` e `character_export.py`.

  Prossimo: passo 4 di §13 — "host/client LAN", il primo vero test su dispositivi reali (protocollo, scoperta,
  interventi del master, condivisione, mappe, robustezza su Wi-Fi vera — non verificabile da soli, vedi la
  sezione dedicata in `CLAUDE.md`).

- **Multiplayer — passo 4 "Host + client in LAN" completato (2026-08-05)**, stessa giornata dei passi 2 e 3.
  Copre §9 del design doc: il trasporto di rete vero e proprio (server stdlib sull'host, client via
  `RemoteBackend`), la sicurezza proporzionata di §9.4 (PIN, token, approvazione del master), e la replica locale
  di §4/§6 (un dispositivo che si unisce in LAN tiene una copia leggibile offline di mondo/membri/giornale).
  Scope dichiarato: SOLO ingresso manuale con indirizzo+codice+PIN (§9.3 punto 3) — la scoperta broadcast
  automatica è il passo 5, non toccata qui. Gli eventi applicabili sulla replica sono, per ora, solo quelli di
  gestione del mondo già esistenti dal passo 2 (rinomina, promuovi/retrocedi/espelli, trasferimento proprietà,
  ingresso membro): gli eventi sulle istanze di personaggio arriveranno con i loro handler nel passo 6.

  1. **`network/protocol.py`** (nuovo modulo/nuova cartella `network/` popolata per la prima volta) — un solo
     posto per `PROTOCOL_VERSION = 1` (controllato all'ingresso, §11.6), l'intervallo di porte di default
     (8765-8770, §9.2), il timeout dell'attesa lunga (25 s, stima dichiarata non misurata, §12.3), e la
     (de)serializzazione JSON di `WorldEvent`/`World`/`WorldMember` condivisa tra host e client.

  2. **`network/host_server.py`** — `WorldHostServer`, un'istanza per mondo ospitato. `start()`/`stop()`
     gestiscono un `http.server.ThreadingHTTPServer` (stdlib pura, §3.2: nessuna dipendenza nuova, coerente col
     vincolo verificato sul rischio serious-python in build mobile) su un thread daemon, con ripiego sulle
     porte successive se 8765 è occupata. Sicurezza (§9.4): PIN numerico a 6 cifre rigenerato ad ogni `start()`,
     token di sessione (`secrets.token_urlsafe`) consegnato a `POST /join` e ripresentato ad ogni chiamata
     autenticata (`Authorization: Bearer`). Un dispositivo già membro del mondo rientra senza approvazione; uno
     nuovo entra in una coda (`list_pending()`/`approve()`/`reject()`, chiamate dirette dalla UI del master,
     stesso processo dell'host — nessuna rotta HTTP dedicata, solo chi ospita deve vederle). Rotte: `GET /world`
     (biglietto da visita + versione protocollo), `POST /join`, `GET /join/status`, `GET /events` (attesa lunga
     vera: un ciclo che ripolla il giornale ogni 200 ms tenendo la connessione HTTP aperta fino a un evento o al
     timeout), `POST /command` (inoltra a `LocalBackend.send_command()` già esistente — nessuna duplicazione
     della validazione permessi), `GET /snapshot`, `POST /leave`.

  3. **`core/world_backend.py` — `RemoteBackend`** — seconda implementazione di `WorldBackend` (§9.1), parla
     HTTP con `http.client` (stdlib) invece di scrivere sul proprio DB. Stessa interfaccia di `LocalBackend`: la
     UI userà `send_command`/`fetch_events`/`connection_state` senza sapere quale delle due ha davanti. Aggiunge
     anche `check_world()` (verifica raggiungibilità + versione protocollo PRIMA di spendere un tentativo di
     join, §11.6), `join()`/`poll_join_status()` (il ciclo pending → approvato/rifiutato), `reconnect_with_token()`
     (riconnessione rapida con un token già ottenuto, §11.1/§11.7 — fallisce esplicitamente, senza insistere in
     automatico, se l'host è stato riavviato e i token in memoria sono scaduti), `leave()`, `get_snapshot()`.

  4. **`data/repositories/world_repo.py` — funzioni lato replica** — `save_replica_world`/`save_replica_member`/
     `remove_replica_member`/`save_replica_event`/`update_last_synced_seq`/`update_last_seen_host`. A differenza
     delle funzioni CRUD esistenti non generano un nuovo id né scrivono un evento proprio: registrano SOLO lo
     stato ricevuto dall'host, la validazione è già avvenuta lì. `save_replica_world` imposta sempre
     `is_local_host=0` — nessuna funzione tranne `create_world()` può impostarlo a 1, il che garantisce per
     costruzione la regola di §11.5 ("due dispositivi non possono ospitare lo stesso mondo").

  5. **`core/world_sync.py`** (nuovo modulo) — l'unico punto che orchestra `RemoteBackend` (trasporto) insieme a
     `world_repo` (scrittura della replica), così la UI non applica mai un evento da sola. `apply_event_to_replica()`
     interpreta `event.kind` per i sei tipi di evento già esistenti (world.rename/member.promote/member.demote/
     member.kick/world.transfer_ownership/world.created) e ignora con un log — senza sollevare — un `kind` non
     ancora gestito, così un client con una versione più vecchia non si blocca su un tipo di evento che ancora
     non conosce. `sync_replica()` è il ciclo incrementale (eventi da `last_synced_seq`, applicati in ordine,
     salvati localmente, `last_synced_seq` aggiornato) con un `refresh_members=True` di default che rilegge
     anche l'elenco membri intero da uno snapshot, più robusto di fidarsi solo degli eventi conosciuti.
     `start_lan_join()`/`finish_pending_join()`/`_finalize_join()` orchestrano l'ingresso completo lato client:
     controllo versione, join, attesa dell'approvazione, e — al successo — la semina della replica locale con
     l'intero snapshot (mondo, membri, giornale) cosicché sia leggibile offline fin dal primo momento (§6).

  6. **UI minimale in `ui/views/world/world_view.py`** — sezione "Ospita in LAN" nel dettaglio di un mondo
     (visibile solo all'owner sul mondo che ospita davvero, `is_local_host`): stato non avviato → pulsante
     "Avvia hosting"; avviato → indirizzo IP locale (`network.host_server.local_ip_hint()`, trucco standard via
     socket UDP senza inviare pacchetti) + porta + PIN a 4 cifre grandi, elenco delle richieste in attesa con
     approva/rifiuta, "Ferma hosting". `will_unmount()` ferma il server se l'utente esce dalla sezione senza
     fermarlo esplicitamente (§9.4: "nessuna porta aperta di default"). Nell'elenco mondi, nuova pillola
     "Unisciti in LAN" — dialogo con indirizzo/porta/codice/PIN/nome che chiama `world_sync.start_lan_join()`;
     se l'ingresso resta "pending", il dialogo NON si chiude, passa in uno stato di attesa con un pulsante
     "Controlla di nuovo" (chiama `finish_pending_join()`) invece di far reinserire tutti i campi.

  7. **`pyproject.toml` — bug reale scoperto e corretto (§14.5)**: la chiave esistente
     `[tool.flet.android] permissions = []` **non aveva mai avuto alcun effetto**, anche prima di questa
     sessione — verificato leggendo il sorgente installato di `flet_cli` 0.85.3
     (`flet_cli/utils/pyproject_toml.py` + `build_base.py`): quella versione legge SOLO
     `tool.flet.android.permission` (singolare, una tabella chiave/booleano), mai la chiave plurale. Corretto
     in `[tool.flet.android.permission]` con `INTERNET`/`ACCESS_NETWORK_STATE`/`CHANGE_WIFI_MULTICAST_STATE`
     (quest'ultimo per il passo 5). Scoperta ulteriore, non nel design doc: il build system di Flet include
     `android.permission.INTERNET` come base fissa a prescindere da questa tabella — l'app non era mai stata
     "offline-first" in senso stretto sul build Android, il commento precedente era già indicativo, non esatto.
     Verificato chiamando `flet_cli.utils.pyproject_toml.load_pyproject_toml()` (lo stesso loader che userebbe
     `flet build`) sul file reale: la nuova tabella viene letta correttamente, la vecchia tornava `None`.

  **Verificato end-to-end** con una nuova batteria dedicata `test_lan_host_client.py` (92 controlli, tre parti
  dichiarate separatamente): (1) protocollo di rete REALE su socket veri via 127.0.0.1 — join con codice/PIN
  corretti ed errati, dispositivo nuovo (pending → approvato o rifiutato) vs dispositivo già noto (approvazione
  immediata), comandi sulla rete (rifiutati per ruolo insufficiente, riusciti per l'owner, con l'evento di
  ritorno deserializzato correttamente), l'attesa lunga di `/events` misurata con un cronometro reale (~0.5-1.2 s
  per un timeout di 0.6 s), `/snapshot`, invalidazione del token su `/leave`, `reconnect_with_token` con token
  valido/invalido/di una sessione precedente dopo un riavvio, rotte sconosciute → 404; (2) applicazione degli
  eventi sulla replica in isolamento puro (nessun server vivo) per tutti e sei i tipi di evento gestiti, più
  l'idempotenza di `save_replica_event`; (3) l'orchestrazione di `start_lan_join`/`finish_pending_join` con un
  finto backend (versione incompatibile, host irraggiungibile, pending, approvato con verifica della replica
  scritta correttamente, rifiutato). **Dichiarato esplicitamente perché non un vero test a due database
  separati**: simulare "due dispositivi" scambiando `HOME` nello stesso processo introdurrebbe una corsa reale
  col thread del server, producendo un test che sembra passare senza provare nulla — la parte [1] usa quindi un
  solo DB condiviso (onesto: nessuna funzione di quella parte scrive nella tabella `worlds` del "client"), la
  parte [2]/[3] isolano la logica di scrittura della replica dal trasporto già verificato in [1]. Rieseguite
  anche `test_mondo_senza_rete.py` (139/139) e `test_istanze_personaggio.py` (62/62): nessuna regressione.

  **Ciò che resta esplicitamente non verificabile da qui, dichiarato nel design doc stesso (§15)**: il
  comportamento su una Wi-Fi reale con due dispositivi fisici distinti — un telefono che si addormenta, un
  router che chiude le connessioni ferme, la latenza reale dell'attesa lunga, se `flet build apk` include
  davvero i permessi appena dichiarati. Lista di verifica consegnata a Davide in coda a questa sessione.

- **Regressione reale trovata da Davide con uno screenshot, corretta in giornata (2026-08-05)**: la card
  personaggio raggruppata per mondo in `ui/views/home_view.py` (appena scritta nel passo 3, stessa sessione)
  mostrava un riquadro grigio vuoto al posto delle informazioni del personaggio. Causa: `wrap=True` aggiunto
  per errore sulla `Row` esterna della card (`avatar, spacer, info, actions`), che ha `info` con `expand=True`
  — esattamente il bug già documentato in `dnd_app/docs/regole_flet_api.md` ("WRAP=True su una Row/Column con
  un figlio expand=True → crash Flutter silenzioso, NESSUN errore Python"), trovato la prima volta il
  2026-07-31 nel dialogo di assegnazione del Bottino e **reintrodotto per errore in un punto diverso del
  codice**, non essendoci un controllo automatico che lo impedisse. Fix: rimosso `wrap=True` da quella `Row`
  (la `Row` interna delle azioni, senza figli `expand`, lo conserva legittimamente).

  **Prevenzione aggiunta, non solo il fix puntuale**: nuovo `test_regressione_wrap_expand.py` — cammina
  l'albero dei controlli REALMENTE costruiti (non il codice sorgente) di `HomeView` (card locali + card
  istanza raggruppate per mondo, nei due temi) e `WorldsView` (elenco, dettaglio, sezione hosting LAN attiva)
  e fallisce se trova una `Row`/`Column` con `wrap=True` che ha un figlio diretto con `expand` "vero" (`True`
  o un intero positivo, il peso flex). Verificato che il test intercetta davvero il bug: reintrodotto
  temporaneamente `wrap=True` nella stessa `Row`, il test è fallito indicando il path esatto nell'albero
  (`HomeView.controls[1].content [Row wrap=True] -> figlio #2 (Column) con expand=True`), poi ripristinato il
  fix e riverificato verde. 12 controlli, da estendere man mano che si aggiungono nuove view con liste/card —
  è un controllo strutturale generico, non specifico di Home o Mondi. Rieseguite anche le tre batterie del
  giorno (`test_mondo_senza_rete.py` 139/139, `test_istanze_personaggio.py` 62/62, `test_lan_host_client.py`
  92/92): nessuna regressione.

- **`SharedPreferences` confermato rotto in web mode, segnalato da Davide (2026-08-06)**: sul deploy web reale,
  aprire l'app produceva `Unknown control: SharedPreferences`. Era esattamente il rischio dichiarato ma non
  ancora verificato nel passo 2 (2026-08-05): `ft.SharedPreferences` eredita da `Service`, la stessa classe base
  di `ft.FilePicker`, già documentato come strutturalmente rotto in web mode (flet-dev/flet#6040/#6250/#6251).
  Il punto sottile, la ragione per cui il `try/except` già presente in `ui/device_identity.py` non bastava:
  l'errore arriva dal client Flutter via websocket DOPO che la chiamata Python (`page.overlay.append(...)` +
  `page.update()`) è già "riuscita" — un `try/except` sincrono in Python non può intercettare un fallimento che
  avviene lato client in un momento successivo. Stesso comportamento già osservato nei tre tentativi falliti di
  `FilePicker` documentati in `regole_flet_api.md`. Fix, stesso pattern già in uso per `FilePicker`: in
  `ui/device_identity.py`, `resolve_device_id()` in web mode NON tenta più affatto `SharedPreferences` — va
  dritto all'identità di sola sessione (id generato una volta e tenuto come attributo su `page`, si perde al
  refresh della pagina — limite noto e accettato, non un bug: il caso d'uso primario del Multiplayer resta
  desktop/mobile via LAN, dove `app_settings` è stabile). Rimossa la funzione `_get_or_create_web_device_id()`
  (il tentativo SharedPreferences) invece di lasciarla come codice morto mai raggiunto. Aggiornato
  `regole_flet_api.md` con una regola generale: per qualunque controllo `Service` non ancora provato in web
  mode, un `try/except` attorno alla creazione dà un falso senso di sicurezza — va evitata la creazione a monte
  con un `if page.web:` PRIMA di istanziare il controllo, non un tentativo con ripiego sull'eccezione.
  Riverificato `test_mondo_senza_rete.py` (139/139, inclusa la sezione `[6] ui/device_identity`): nessuna
  regressione, la firma pubblica di `resolve_device_id()` non è cambiata.

- **Build GitHub Actions falliva su Windows/macOS/Linux (7-13s ciascuna), segnalato da Davide con uno
  screenshot (2026-08-06)**: solo `build-android` completava (8m23s). Causa, confermata leggendo la cronologia
  git (`git ls-tree -d HEAD`, `git ls-tree HEAD -- version.py pyproject.toml`, `git show 3915642 --
  .github/workflows/release.yml`): lo step "Inject version from git tag", introdotto da Davide stesso il
  3 luglio 2026 (commit `3915642`, release v0.1.15) in `build-windows`/`build-macos`/`build-linux`, leggeva e
  riscriveva `dnd_app/version.py` e `dnd_app/pyproject.toml` — ma il repository Git ha questi due file
  **direttamente alla radice**, senza una sottocartella `dnd_app/` annidata (confermato: non esiste nel repo,
  esiste solo come nome della cartella genitore sul filesystem di Davide, fuori dal repository). Lo step
  falliva quindi immediatamente con un errore di file non trovato — coerente con le durate di 7-13s osservate.
  `build-android` non aveva mai avuto questo step, motivo per cui era l'unico a completare (ma restava anche
  l'unico a **non** ricevere mai la versione dal tag: l'APK pubblicato avrebbe sempre riportato
  `APP_VERSION = "0.1.15"` da `version.py`, indipendentemente dal tag effettivo).

  Fix in `.github/workflows/release.yml`: rimosso il prefisso `dnd_app/` nei tre step esistenti (ora
  `version.py`/`pyproject.toml`, percorsi relativi alla radice del checkout, corretti). **Aggiunto anche lo
  stesso step a `build-android`**, prima assente — non solo per coerenza tra le quattro piattaforme, ma perché
  è un gap funzionale reale: `core/update_checker.py` confronta `APP_VERSION` (da `version.py`) con l'ultima
  release GitHub per notificare in-app gli aggiornamenti disponibili; senza l'iniezione, un'installazione
  Android avrebbe sempre visto la propria versione come "0.1.15", risultando in falsi positivi di
  aggiornamento disponibile ad ogni release successiva. Nessun test automatico possibile per questo fix (la
  correttezza dipende dall'esecuzione reale su GitHub Actions, non riproducibile in sandbox): verifica
  rimandata al prossimo tag pushato da Davide, da controllare su
  `https://github.com/DavMos9/dnd_app/actions`.

- **Modalità Master world-scoped (2026-08-06)** — Davide ha segnalato (screenshot GitHub Actions + testo)
  tre problemi in un unico messaggio: (1) build CI rotta (voce sopra), (2) "quando aggiungo il player ad un
  mondo, quel player viene duplicato" in modalità web, (3) "nella versione del master escono tutti [i
  personaggi], il master deve selezionare il mondo da masterare e gestire i personaggi del mondo".

  **Diagnosi**: causa unica per (2) e (3). Nessun file di `ui/views/master/` aveva mai avuto un concetto di
  "mondo" — `character_repo.get_all()` (ogni personaggio mai creato, nessun filtro) era chiamato da 5 punti
  diversi: `master_treasure_dialog.py`, `master_magic_item_generator_dialog.py`,
  `master_loot_assign_dialog.py`, `master_encounter_generator_dialog.py`,
  `master_encounter_view.py._open_add_character_dialog`. Quando un giocatore entra in un mondo (passo 3 del
  Multiplayer, 2026-08-05) nasce una **seconda riga** in `characters` (l'istanza, per design — vedi §6 di
  `multiplayer_design.md`, decisione già chiusa: il personaggio locale resta riusabile altrove). Con
  `get_all()` senza filtro, quella seconda riga compariva ACCANTO all'originale locale in ogni picker
  personaggi della Sezione Master — da qui "il player viene duplicato". E senza alcun filtro per mondo, ogni
  istanza di ogni mondo compariva sempre — da qui "escono tutti".

  **Decisioni chieste a Davide e ricevute (AskUserQuestion) prima di scrivere codice**, coerente con la
  regola del progetto "se il requisito è ambiguo non scegliere arbitrariamente":
  1. Ampiezza del fix — tre opzioni proposte (solo i picker personaggi / + deposito del gruppo del Bottino,
     che aveva `world_id=""` fisso in codice, gap noto e già documentato come "passo 6 bloccato sul
     Multiplayer" / + visibilità per-nota delle Note di Campagna, progettata in `multiplayer_design.md` §7 ma
     mai implementata). **Scelta: "Tutto, incluse le Note di Campagna."**
  2. Persistenza della selezione mondo nella Modalità Master — sessione vs tra sessioni. **Scelta: solo per
     sessione** (si azzera riaprendo la Modalità Master, per non rischiare di restare sul mondo sbagliato).

  **Implementazione**:

  - `data/repositories/character_repo.py`: nuova `get_master_visible_characters(world_id="")` — `world_id==""`
    restituisce SOLO i personaggi locali (`characters.world_id==''`), un world_id valorizzato restituisce
    SOLO le istanze di quel mondo. I due insiemi sono sempre mutuamente esclusivi (a differenza di
    `get_all()`, usato da `HomeView`, che li mostra entrambi partizionati in sezioni — semantica diversa,
    voluta: la Home deve mostrare tutto ciò che il dispositivo possiede, il Master deve vedere solo il
    contesto che sta correntemente gestendo).
  - `data/repositories/world_repo.py`: `get_worlds_for_device()` guadagna un parametro opzionale
    `roles: tuple[str,...] | None` (filtro SQL `IN (...)`, non un post-filtro Python) — usato per popolare il
    selettore "mondo da masterare" con solo i mondi in cui questo dispositivo è `owner`/`master`, mai quelli
    in cui è solo `player`.
  - `ui/views/master/master_view.py`: nuovo selettore mondo SEMPRE visibile nell'header (un `ft.Dropdown`,
    mai un menu nascosto — coerenza con la regola già stabilita per la barra "Generatori Rapidi"). Risoluzione
    `device_id` asincrona in `did_mount()` (stesso pattern di `HomeView._init_identity`), validazione che il
    mondo selezionato resti tra quelli masterabili (mondo eliminato/espulsione/degradazione → torna a
    "Nessun mondo" invece di restare silenziosamente su un `world_id` invalido). La selezione sopravvive al
    rebuild causato dal cambio tema tramite lo stesso meccanismo già esistente per `active_tab`
    (`ui/app.py._show_master_view`/`_rebuild_route`), ma si azzera riaprendo la Modalità Master dalla Home
    (per scelta esplicita di Davide, decisione 2 sopra).
  - `world_id` inoltrato dal selettore a: `MasterEncounterListView`/`MasterEncounterView` (picker "Personaggio
    Giocante"), `MasterNotesView`, `MasterLootView`, e alle 6 funzioni `show_x_dialog()` dei generatori
    (Tesoro, Oggetto Magico, Bottino-assegna, Incontro Casuale, Artefatti, Veleni — le ultime due non
    chiamavano `get_all()` direttamente ma aprono comunque il dialogo di assegnazione bottino, quindi
    necessitavano comunque del parametro).
  - **Bottino ("Deposito del Gruppo")**: `MasterLootView`/`master_loot_assign_dialog.py` ora passano
    `world_id` a `loot_repo.get_entries()`/`create_entry()` **solo per `stash_kind="party"`**;
    `stash_kind="master"` (l'archivio privato del Master) resta **sempre** `world_id=""`, per scelta di
    design già scritta nel docstring di `LootStashEntry` (l'archivio è privato del dispositivo, mai
    condiviso via mondo — non va confuso col deposito). Con "Nessun mondo" selezionato il Deposito del Gruppo
    si comporta esattamente come prima (comportamento locale, world_id="", nessuna rottura per chi non usa il
    Multiplayer) — sblocca di fatto il "passo 6" di `loot_design.md` §8, prima bloccato in attesa di questo
    selettore.
  - **Note di Campagna — visibilità per-nota** (`multiplayer_design.md` §7): 3 nuove colonne su
    `master_campaign_notes` (`world_id`, `visibility` "private"/"all"/"selected", `visible_to_device_ids`
    JSON) via `_add_column()` (stesso meccanismo di migrazione incrementale già in uso per ogni colonna
    aggiunta dal 2026-07-09 in poi). `MasterCampaignNote` in `data/models.py` estesa con gli stessi 3 campi.
    `master_repo.get_master_campaign_notes(category="", world_id=None)` — `None` non filtra (compatibilità
    con la firma precedente), `""` solo note locali, un id solo quelle di quel mondo — stessa convenzione di
    `get_master_visible_characters()`. `create_master_campaign_note()`/`update_master_campaign_note()`
    estese; `world_id` NON è tra i campi modificabili dopo la creazione (una nota non cambia mondo, stessa
    scelta già fatta per `origin_character_id` sulle istanze). UI in `master_notes_view.py`: il selettore
    "Visibilità" (con l'elenco spuntabile dei membri `role="player"` del mondo attivo quando si sceglie
    "Solo i giocatori selezionati") compare SOLO quando la vista è legata a un mondo — in modalità locale una
    nota è per definizione privata, niente da scegliere.

    **Nota onesta, dichiarata esplicitamente a Davide**: questo passo registra correttamente l'INTENZIONE del
    Master (i 3 campi sono persistiti e rileggibili) ma **non implementa ancora la consegna effettiva ai
    dispositivi dei giocatori** — servirebbero un nuovo tipo di evento nel giornale del mondo (il comando
    `note.share` esiste già come slot riservato in `core/world_permissions.py` dal passo 2, mai collegato a
    un handler) più una schermata lato giocatore che oggi non esiste in nessuna forma. Segnalato come lavoro
    a sé, non ancora pianificato, non fatto passare per completo.

  **Bug reale trovato durante la verifica, non correlato al selettore mondo ma scoperto grazie ad esso** —
  `data/repositories/character_repo.py.create()`: l'INSERT era una lista di colonne scritta a mano che non
  includeva MAI le 5 colonne mondo (`world_id`/`origin_character_id`/`owner_device_id`/`is_replica`/
  `world_seq`), mentre `update()` le scrive correttamente da anni (dal passo 2, 2026-08-05). Passare a
  `create()` un `Character` con `world_id` già valorizzato lo perdeva silenziosamente. **Mai emerso finora**
  perché l'unico chiamante che crea istanze di mondo,
  `core/character_instances.py._link_to_world()`, aggira il problema con un `UPDATE` diretto subito dopo il
  `create()` — un workaround funzionante ma che nascondeva l'incoerenza. Trovato scrivendo
  `test_master_world_scoping.py` (sotto): un test che costruiva un `Character(world_id=...)` e lo passava a
  `create()` falliva in modo silenzioso e contro-intuitivo. Corretto aggiungendo le 5 colonne all'INSERT,
  stesso identico set già presente in `update()` — nessuna funzionalità esistente rotta (i valori di default
  restano gli stessi impliciti del DB), ma ora `create()` è coerente con `update()` e con la promessa del
  dataclass `Character`.

  **Verifica**: nuovo `test_master_world_scoping.py` (25 controlli — mutua esclusione locale/istanze per
  mondo, filtro ruolo di `get_worlds_for_device`, CRUD/filtro/visibilità delle note di campagna), nessuna
  dipendenza da Flet (solo repository/core, evita l'artefatto ambientale del sandbox descritto sotto).
  Rieseguite le tre batterie esistenti: `test_mondo_senza_rete.py` 139/139, `test_lan_host_client.py` 92/92,
  `test_istanze_personaggio.py` 61/62 con **un solo fallimento pre-esistente e non correlato**: il
  sub-check `[8]` di quel file lancia `test_mondo_senza_rete.py` in un sottoprocesso via `subprocess.run`, e
  in QUESTO sandbox quel sottoprocesso non trova il modulo `flet` (probabile artefatto di risoluzione
  user-site-packages quando `HOME` è sovrascritto su una cartella temporanea prima dello spawn) — non
  presente eseguendo `test_mondo_senza_rete.py` direttamente (139/139 verde), quindi non una regressione
  introdotta qui. Da riverificare comunque da Davide sul suo ambiente reale, dove l'intera batteria era
  già stata eseguita con successo il 2026-08-05.

- **Bug reale nel selettore mondo appena aggiunto, segnalato da Davide sia su web sia in locale
  (2026-08-06)**: `The application encountered an error: Dropdown.__init__() got an unexpected keyword
  argument 'prefix_icon'`. Causa: in `master_view.py._world_selector()` avevo scritto
  `ft.Dropdown(prefix_icon=ft.Icons.PUBLIC, ...)` per analogia con `ft.TextField(prefix_icon=...)`, già
  usato altrove nel progetto (`magic_items_view.py`, `master_npc_list_view.py`,
  `ui/components/monster_picker.py`) — ma `ft.Dropdown` **non ha** `prefix_icon`: il parametro giusto è
  `leading_icon` (accetta `IconData`, es. `ft.Icons.X`, o un `Control`). Verificato con
  `inspect.signature(ft.Dropdown.__init__).parameters` sul pacchetto realmente installato — non un'altra
  supposizione. **A differenza dei bug wrap+expand/SharedPreferences già documentati, questo è un
  `TypeError` Python puro, sollevato alla semplice costruzione del controllo**: identico su web e locale
  (stesso identico codice Python, nessuna differenza di piattaforma coinvolta), niente a che fare con un
  client Flutter che non riconosce un controllo — un motivo di più per cui bastava un test di costruzione,
  mai scritto prima per `MasterView`, per intercettarlo prima che Davide lo vedesse.

  Fix: `prefix_icon` → `leading_icon` nell'unico punto in cui compariva su un `Dropdown`. Verificato con
  un controllo statico (AST) su tutti i `ft.Dropdown(...)` di `ui/` che nessun altro kwarg invalido fosse
  presente (nessuno trovato) — stesso controllo esteso a Checkbox/Container/Column/Row/TextField/Text/
  IconButton/OutlinedButton/ElevatedButton/AlertDialog nei file toccati in questa sessione (nessuno trovato).

  **Prevenzione, non solo il fix puntuale** (richiesta esplicita di Davide: "non ripetiamo errori vecchi se
  no perdiamo solo tempo"): esteso `test_regressione_wrap_expand.py` con `test_master_view()` — costruisce
  `MasterView` per tutte e 5 le tab, con e senza un mondo selezionato, in entrambi i temi (20 combinazioni),
  cosa mai fatta prima per questa vista. Cattura sia conflitti wrap+expand sia (novità) qualunque eccezione
  sollevata durante la costruzione, quindi anche `TypeError` come questo. Verificato che il test intercetta
  davvero il bug: reintrodotto temporaneamente `prefix_icon`, tutte e 12 le combinazioni con mondo
  selezionato/non selezionato sono fallite con il messaggio esatto riportato da Davide, poi ripristinato il
  fix e riverificato verde. Aggiunta una regola generale in `regole_flet_api.md`: verificare SEMPRE con
  `inspect.signature()` prima di aggiungere un kwarg "plausibile per analogia" con un altro controllo — è
  esattamente come è nato questo bug (TextField ha `prefix_icon`, Dropdown no). Rieseguite tutte le batterie
  della sessione: `test_regressione_wrap_expand.py` 33/33, `test_master_world_scoping.py` 25/25,
  `test_mondo_senza_rete.py` 139/139, `test_lan_host_client.py` 92/92 — nessuna regressione.

- **FilePicker: assunzione "funziona su Android nativo" parzialmente smentita da un vero dispositivo
  (2026-08-06)** — Davide ha segnalato la barra rossa "Unknown control: FilePicker" su Android, comparsa
  **subito all'apertura della Home**, senza toccare nulla. Chiesta la localizzazione esatta prima di
  intervenire (ambiguo: 4 punti diversi del codice registrano un FilePicker) — risposta: "subito
  all'apertura dell'app / Home", non un'azione specifica.

  **Causa**: `HomeView.did_mount()` registrava un `ft.FilePicker()` in `page.overlay` in modo EAGER
  (incondizionato) ogni volta che `page.platform` è Android/iOS, ancora prima che l'utente tocchi
  Esporta/Importa. Stesso identico pattern, copiato letteralmente, in `maps_view.py.did_mount()` e
  `profilo_tab.py.did_mount()` (verificato con grep — 3 siti, non solo quello segnalato). L'affermazione
  "ft.FilePicker su MOBILE funziona correttamente", scritta a suo tempo in `regole_flet_api.md`, **non era
  mai stata verificata su un vero dispositivo** — dedotta dalla sintassi corretta (letta dal sorgente Flet
  installato: `docstring` di `_on_mobile_export()` in `home_view.py` lo dichiara esplicitamente), mai da un
  test end-to-end, perché fino a questa sessione Davide non aveva ancora potuto testare le app locali
  (bloccato dal problema di build). Il parallelo con web mode è diretto e già documentato: lì "TUTTE le
  strategie di registrazione falliscono nello stesso modo... la registrazione anticipata in did_mount()
  produce lo stesso errore, solo mostrato prima" — lo stesso principio vale qui.

  **Fix applicato, minimo e sicuro**: rimossa la registrazione eager in tutti e 3 i `did_mount()`
  (`home_view.py`, `maps_view.py`, `profilo_tab.py` — quest'ultimo con uno storico di commento già a 4
  capitoli di debugging precedenti, esteso con un quinto). In tutti e tre resta SOLO il fallback lazy già
  presente (crea il FilePicker al primo tocco reale del pulsante, se non già registrato) — nessuna funzione
  nuova scritta, il meccanismo di ripiego esisteva già ovunque, semplicemente non era più l'unico percorso.

  **Nota onesta, non ancora risolta**: questo fix elimina con certezza l'errore immediato al mount (bug
  riprodotto al 100%, ora impossibile per costruzione — non c'è più alcuna registrazione lì). **Non
  garantisce** che l'uso interattivo (tap sul pulsante → crea il FilePicker → `pick_files()`) funzioni
  davvero su Android: se il problema fosse strutturale come su desktop/web (dove ANCHE il click falliva,
  solo più tardi), il banner ricomparirebbe al primo tap di Esporta/Importa/foto profilo/immagine mappa —
  nel qual caso servirebbe un redesign (es. lo stesso approccio "libreria immagini su filesystem server"
  già usato per il web) e non un altro aggiustamento di timing. Segnalato esplicitamente a Davide: serve
  ancora testare quei tre flussi interattivi su un vero Android per saperlo con certezza.

  Verificato: `py_compile` sui 3 file, `test_regressione_wrap_expand.py` 33/33 (esercita comunque
  `HomeView`/`MasterView`), `test_mondo_senza_rete.py` 139/139, `test_master_world_scoping.py` 25/25,
  `test_lan_host_client.py` 92/92 — nessuna regressione. Nessun test automatico può verificare il
  comportamento REALE su Android (limite già noto e accettato per l'intera area Multiplayer/mobile di
  questo progetto).

- **5 problemi di leggibilità su smartphone segnalati con screenshot, indagati e corretti dove possibile
  (2026-08-05, sessione con Davide dopo il primo vero test su Android)** — Davide ha mandato 5 screenshot in
  un unico messaggio: nome/info illeggibili sulla card personaggio in Home, l'errore FilePicker anche
  cliccando davvero (non solo all'apertura), pulsanti/testo illeggibili su schermo stretto, la parte
  superiore della scheda sovrapposta a tacca/barra di stato, abilità in Esplorazione illeggibili, Sezione
  Master "completamente illeggibile" (titolo verticale, una lettera per riga). Più la richiesta generale
  "l'app si deve adattare bene alla finestra che sia smartphone o pc o tablet". Indagati tutti e 5 prima di
  correggere, poi Davide ha scelto priorità e approccio via domande mirate.

  1. **Titolo "MODALITÀ MASTER" verticale** — causato dal Dropdown mondo aggiunto nell'header nella sessione
     precedente lo stesso giorno: `title_text()`/`design.title()` non ha mai impostato `no_wrap`/`overflow`/
     `max_lines` nonostante un commento (sbagliato) dicesse il contrario, e il nuovo Dropdown a larghezza
     fissa nella stessa `Row` ha schiacciato il titolo abbastanza da far avvenire l'a-capo carattere per
     carattere. Fix: `no_wrap=True`/`overflow=ELLIPSIS`/`max_lines=1` esplicito sul titolo in
     `master_view.py`, selettore mondo spostato dall'header a una riga propria (`_world_selector_row()`,
     rinominata da `_world_selector()`) con `expand=True` esplicito sul Dropdown (non assunto: verificato
     che `ft.Dropdown`/`ft.Container` hanno entrambi il parametro `expand` prima di usarlo).

  2. **FilePicker rotto anche all'uso interattivo (non solo all'apertura)** — indagine approfondita, non
     un altro tentativo di aggiustare il timing. Verificato leggendo `flet/controls/services/service.py`
     installato che il pattern Python del progetto (`page.overlay.append(fp); page.update()`) è
     meccanicamente CORRETTO in Flet 0.85.3/0.86.5: `Service.init()` si autoregistra da solo in
     `context.page._services.register_service(self)` al mount, qualunque sia il contenitore — l'ipotesi
     "andava usato `page.services` invece di `page.overlay`" è stata verificata e scartata. "Unknown
     control: X" per i controlli `Service` è quindi un problema lato client, non lato Python. Confermato
     con fonti dirette (non per analogia) che è una classe di bug NOTA e RICORRENTE nel repository
     ufficiale `flet-dev/flet`, etichettata esplicitamente "packaging" + "platform: android": stesso
     identico sintomo già segnalato per `ft.Clipboard` (issue #2900, dal 2024) e `ft.Flashlight` (#3599) —
     "funziona su desktop, Unknown control sull'APK compilato con `flet build apk`". Non risolvibile
     cambiando il nostro codice (già verificato corretto). Trovato anche un gap reale indipendente:
     `pyproject.toml` non dichiarava nessun permesso di lettura immagini.

     Davide ha scelto di tentare il fix più promettente, non un aggiramento: **aggiornamento Flet 0.85.3 →
     0.86.5**, la cui release ufficiale dichiara un "completely re-designed Android packaging". Fatto,
     nello stesso giro:
     - `pyproject.toml`: `flet==0.86.5`; `requires-python = ">=3.12,<3.13"` (fissa il Python imbarcato a
       3.12 — la stessa versione usata implicitamente da TUTTE le build precedenti — invece di lasciare che
       0.86 scelga di default l'ultimo stabile, 3.14: isola l'aggiornamento al solo repackaging Android,
       senza aggiungere anche l'incognita "Pillow ha ruote 3.14 pronte per Android/iOS?", non verificabile
       da questo sandbox).
     - Permesso mancante corretto con la scelta MIGLIORE trovata durante l'indagine, non quella ovvia:
       non il permesso Android grezzo `READ_MEDIA_IMAGES` a cui si pensava all'inizio, ma il gruppo
       cross-platform `photo_library` (`[tool.flet] permissions = ["photo_library"]`, chiave verificata
       leggendo `flet_cli/commands/build_base.py` 0.86.5 installato — distinta da
       `tool.flet.android.permission` già presente) → su Android mappa su
       `android.permission.READ_MEDIA_VISUAL_USER_SELECTED` (permesso di "selezione parziale", commentato
       nel sorgente flet_cli come quello richiesto dalla policy Play Store "Photo and Video Permissions"
       per un caso d'uso come il nostro — scegliere una foto, non accesso libero alla libreria), copre
       anche iOS (`NSPhotoLibraryUsageDescription`) gratis.
     - `python3 -m compileall` sull'intero albero + tutte e 4 le batterie di test (289/289) verdi contro
       0.86.5. Verificato anche che i tre pattern più a rischio con lo storage riorganizzato di 0.86
       (`app files ship unpacked in a read-only bundle`) sono già sicuri: `data/database.py::get_db_path()`
       usa variabili d'ambiente Android note, mai la cwd; `data/game_data/game_data_loader.py::_DATA_DIR`
       e `data/database.py::get_assets_path()` sono già basati su `Path(__file__)`, non sulla cwd.
     - **Nota onesta, esplicita**: questo NON dimostra che il bug su Android sia risolto — richiede una
       build APK reale (`flet build apk`, impossibile in questo sandbox: nessun Android SDK/NDK) e un test
       di Davide su dispositivo, stesso limite già noto per tutta l'area Multiplayer/mobile del progetto.
       Verificato solo: nessuna rottura d'API Python rilevabile da qui.

  3. **Card personaggio in Home illeggibile su schermo stretto** — causa reale: la `Row` aveva avatar fisso
     (76px) + testo (`expand=True`) + fino a 4 `IconButton` che non si comprimono mai; su schermo stretto le
     azioni "mangiavano" lo spazio e nome/chip si schiacciavano. Fix in `home_view.py::_character_card()`:
     riga superiore avatar+info, riga azioni separata sotto (`ft.Column` invece di un'unica `ft.Row`) — così
     `info` è squeezato solo dall'avatar (largo fisso e noto), mai anche dalle azioni. Le azioni restano
     `wrap=True` (nessun figlio `expand=True` al suo interno, quindi sicuro rispetto al bug wrap+expand già
     documentato).

  4. **Barra caratteristiche sovrapposta a tacca/barra di stato Android** — causa: l'app non usava MAI
     `ft.SafeArea` da nessuna parte (verificato che esiste davvero in Flet 0.85.3/0.86.5 per introspezione,
     non assunto). Trovato che `ui/app.py` aveva **6 punti quasi identici** (`_show_home`,
     `_show_master_view`, `_show_worlds_view`, `_show_manual_form`, `_show_wizard`, `_show_main_layout`),
     ognuno con lo stesso terzetto `page.controls.clear() / page.add(X) / page.update()` — duplicazione
     esattamente del tipo che CLAUDE.md chiede di eliminare, e il punto giusto per risolvere la
     sovrapposizione UNA VOLTA per tutte le viste invece che vista per vista. Aggiunto `DnDApp._navigate()`,
     un solo punto che avvolge il contenuto in `ft.SafeArea(content=control, expand=True)` prima di
     montarlo; i 6 metodi di routing ora chiamano solo `self._navigate(X)`. `SafeArea` è un no-op su
     desktop/web (dove `MediaQuery` non riporta intrusioni di sistema), quindi nessun rischio di padding
     indesiderato lì.

  5. **Abilità in Esplorazione illeggibili su schermo stretto** — stesso schema del bug #1 (titolo Master),
     versione "a due colonne": `_section_skills()` in `esplorazione_tab.py` divideva le 18 abilità in due
     colonne FISSE via slicing Python, col nome abilità `expand=True` ma senza `no_wrap`/`overflow`/
     `max_lines` — su schermo stretto ogni colonna aveva ~150px, troppo poco perché il nome restasse
     leggibile. Fix più robusto del solo "aggiungere l'ellissi": sostituita la coppia di `ft.Column` fisse
     con `ft.ResponsiveRow` (`col={"xs": 12, "sm": 6}` per riga abilità) — una colonna sotto i 576px
     (default Flet), due sopra, valutato lato client in base alla larghezza REALE del contenitore, non da
     `page.width` letto in Python (che per `EsplorazioneTab`, come per la card Home, non è comunque
     affidabile a costruzione: il controllo viene spesso costruito prima del mount). Aggiunta anche la
     stessa protezione `no_wrap`/`overflow`/`max_lines` sul nome come rete di sicurezza. Nuovo test
     `test_esplorazione_tab()` in `test_regressione_wrap_expand.py` (prima `EsplorazioneTab` non aveva mai
     avuto un test di costruzione).

  **Verificato in totale**: `py_compile` su tutti i file toccati, `test_regressione_wrap_expand.py` esteso
  da 33 a 35 controlli (nuovo test Esplorazione), 291/291 controlli verdi su tutte e 4 le batterie
  (35+139+25+92) — nessuna regressione sul lavoro Multiplayer/LAN delle sessioni precedenti. **Non
  verificabile da questo sandbox, per Davide**: se l'aggiornamento a Flet 0.86.5 risolve davvero il bug
  FilePicker su un vero Android, e la resa visiva dei 4 fix di layout su un vero dispositivo (schermo
  stretto reale, tacca reale).

- **Trovato e corretto un gap reale nella pipeline di release, stessa sessione (2026-08-05)** — Davide ha
  chiesto se poteva continuare a buildare "normalmente" (git tag → push → GitHub Actions, come da
  `RELEASE.md`) dopo l'aggiornamento Flet sopra. Verifica prima di rispondere: `.github/workflows/
  release.yml` **non legge affatto `pyproject.toml`/`requirements.txt`** — la versione di `flet` è
  hardcoded `pip install flet==0.85.3 "Pillow>=10.0.0"` **in 4 punti indipendenti** (job Windows/macOS/
  Linux/Android), quindi senza questo fix la release reale avrebbe continuato silenziosamente a compilare
  con la versione vecchia, vanificando tutto il lavoro sopra senza alcun errore visibile. Anche
  `flutter-version: "3.41.7"` era hardcoded nei 4 job: verificato per via empirica, non assunto dal
  changelog di Flet, che versione di Flutter serve davvero eseguendo `flet --version` in un venv pulito
  con solo `flet==0.85.3`/`flet==0.86.5` installato — stampa la Flutter bundlata (`0.85.3` → Flutter
  `3.41.7`, confermando che il valore già in CI non era casuale ma allineato di proposito; `0.86.5` →
  Flutter `3.44.8`, non i "3.44.2" arrotondati citati nel blog post). Anche scoperto nello stesso giro,
  per completezza (non ancora agito): `flet-cli` NON è mai stato un requisito pip esplicito né in 0.85.3
  né in 0.86.5 (è un `extra` opzionale, `flet[cli]`) — il comando `flet` della release CI ha sempre
  funzionato perché **si auto-installa `flet-cli` al primo utilizzo** (comportamento reale del pacchetto,
  verificato eseguendo `flet --version` su un'installazione bare e osservando "Installing flet-cli ...
  package...OK" in output), non perché fosse dichiarato da qualche parte.

  Fix applicato: aggiornati tutti e 4 i job in `release.yml` a `flet==0.86.5` + `flutter-version:
  "3.44.8"`, con un commento in testa al file che spiega perché queste due cose vanno tenute allineate a
  mano (nessuna lettura automatica da `pyproject.toml`) — per non ripetere lo stesso gap alla prossima
  release. **Trovato ma NON ancora toccato, da decidere con Davide**: `Dockerfile` (deploy web) ha una
  TERZA occorrenza indipendente di `flet==0.85.3`, usata solo per il deploy Docker/web (separato dalla
  release desktop/mobile) — lasciato invariato per ora, la richiesta di Davide riguardava esplicitamente
  il flusso di release "come fatto finora", non il deploy web.

- **FilePicker ancora rotto su Android dopo l'aggiornamento a Flet 0.86.5 (2026-08-06)** — Davide ha
  testato l'app su un vero dispositivo Android e riportato che il file picker "attualmente non
  funziona" ancora, oltre a un problema di leggibilità sulle pillole di tab in Sezione Master e nella
  scheda personaggio (vedi voce successiva). **Verificato prima di agire** (non un altro tentativo alla
  cieca): `pyproject.toml` ha davvero `flet==0.86.5` e `permissions = ["photo_library"]` come da fix
  precedente; `flet==0.86.5` esiste realmente su PyPI (rilasciato il 1° agosto 2026, non ritirato —
  verificato con una fetch diretta della pagina versione, non assunto da una cache stale della pagina
  progetto principale che mostrava ancora "0.85.3" come ultima release). Cercato anche un fix noto più
  recente lato `flet-dev/flet` (issue tracker, PyPI cronologia versioni, ricerca web su eventuali
  changelog 0.86.x/0.87 relativi al packaging Android dei controlli `Service`): nessun fix ulteriore
  noto oltre al redesign già tentato in 0.86.0 ("completely re-designed Android packaging").

  **Chiesto a Davide** (non assunto): l'APK testato era stato ricompilato DOPO l'aggiornamento a
  0.86.5. Risposta confermata: sì, ricompilato dopo il fix, il bug persiste comunque su tutti e tre i
  punti interattivi (foto profilo, immagine mappa, export/import personaggio). **Questo esclude con
  certezza l'ipotesi "build vecchia"**: il redesign del packaging Android di Flet 0.86.0 non risolve
  questa classe di bug.

  **Seconda indagine, stessa sessione, prima di concludere che serva un redesign**: verificato se
  esiste un pattern d'uso di `ft.FilePicker` più recente/diverso da quello già in uso nel progetto.
  Trovato che la documentazione ufficiale corrente (`flet.dev/docs/services/filepicker/`) mostra un
  pattern più semplice — `ft.FilePicker()` creato al volo dentro l'handler e usato subito
  (`await ft.FilePicker().pick_files(...)`), senza mai registrarlo esplicitamente in
  `page.overlay`/`page.services`. **Verificato per introspezione diretta sul pacchetto 0.86.5
  installato** (non assunto dalla sola documentazione, che potrebbe essere semplificata a scopo
  didattico): `BaseControl.page` (proprietà usata da `_invoke_method`, chiamata da `pick_files()`)
  risale l'albero `.parent` finché non trova una `Page`, sollevando `RuntimeError` se non la trova —
  un `ft.FilePicker()` mai aggiunto da nessuna parte non ha alcun genitore, quindi l'esempio della
  documentazione così com'è scritto solleverebbe lo stesso errore. **Conclusione**: il pattern già in
  uso nel progetto (registrazione in `page.overlay`, poi riuso dell'istanza) resta l'unico
  meccanicamente valido nella versione installata — non è un pattern superato, è tuttora necessario.
  Nessun fix di codice nuovo da questa pista: conferma, con una seconda verifica indipendente da quella
  della sessione precedente (che aveva letto `service.py`), che il codice Python del progetto è
  corretto e il problema è lato client Flutter/Android, non lato Python.

  **Conclusione della sessione, dopo aver esaurito ogni pista verificabile da qui**: nessun fix di
  codice o di versione noto risolve la classe di bug "Unknown control: X" per i controlli `Service` sui
  build APK Android — confermato che affligge `Clipboard`, `Flashlight` e ora anche `FilePicker` dopo
  il redesign 0.86.0, su un arco di più anni nel repository ufficiale `flet-dev/flet`, senza una
  risoluzione nota. **Prossimo passo proposto a Davide, non ancora deciso**: raccogliere un log
  `adb logcat` reale durante la riproduzione del bug (Davide, dispositivo fisico via USB) — il banner
  rosso "Unknown control: X" è quasi certamente un messaggio di fallback generico che nasconde
  un'eccezione più specifica lato Flutter (es. `MissingPluginException`, un canale non registrato);
  finora nessuna sessione ha mai visto il log nativo reale, solo il banner sull'app. Diagnosticare
  dall'evidenza reale prima di tentare un'altra ipotesi alla cieca (redesign nativo con un plugin
  Flutter alternativo, richiederebbe comunque un loop di build/test su dispositivo che solo Davide può
  fare).

- **RISOLTO — la vera causa del bug FilePicker era un `await` mancante, non un bug di packaging
  Android (2026-08-06, stessa sessione, dopo il log `adb logcat` di Davide)** — Davide ha seguito la
  procedura passo-passo data (installare `adb`, attivare debug USB, `adb logcat -c` +
  `adb logcat > file.txt` durante la riproduzione, `grep` filtrato) e mandato due file di log
  raccolti riproducendo "foto profilo". **La riga decisiva**:

  ```
  08-05 23:46:54.619 ... E flet.python: /tmp/serious_python_.../ui/views/character_sheet/profilo_tab.py:4282:
    RuntimeWarning: coroutine 'FilePicker.pick_files' was never awaited
  ```

  Nessun "Unknown control" nel log — nessuna delle tre sessioni precedenti aveva mai visto questo, solo
  il banner nell'app (probabilmente un sintomo di una fase precedente, già corretta, e mai più
  ricontrollato con un log reale). **Causa reale**: `pick_files()`/`save_file()`/
  `get_directory_path()` in Flet 0.86.5 sono metodi `async` che restituiscono il risultato
  DIRETTAMENTE tramite `await` (confermato per introspezione: `inspect.iscoroutinefunction(...)` →
  `True`; `FilePicker` non ha mai avuto un evento `on_result` in questa versione, verificato sui campi
  del dataclass installato — solo `on_upload`). `profilo_tab.py::_pick_photo_mobile()` (riga 4282) e
  `maps_view.py::_pick_mobile()` chiamavano `pick_files()` **senza `await`**, da un `on_click`
  sincrono, assegnando anche un `on_result` che nessuno ha mai letto — la coroutine veniva creata e
  scartata dal garbage collector, il picker nativo non si apriva MAI. Bug silenzioso: nessuna
  eccezione, nessun banner, il tap sul pulsante semplicemente non faceva nulla. Il marker
  `# type: ignore[unused-coroutine]` già presente su quelle righe era la spia che il type-checker
  aveva segnalato esattamente questo, silenziata invece che investigata quando scritta.

  **Perché le tre sessioni precedenti non l'hanno trovato**: nessuna aveva mai avuto un log nativo
  reale, solo screenshot del banner "Unknown control" nell'app — evidenza indiretta che ha portato a
  ipotizzare (con verifiche Python-side genuinamente accurate, solo sulla domanda sbagliata) un bug di
  packaging upstream. Il log `adb logcat`, proposto esplicitamente come prossimo passo invece di
  un'altra ipotesi alla cieca, ha risolto in una lettura quello che tre sessioni di ipotesi (peraltro
  ciascuna correttamente verificata nei propri termini) non avevano trovato.

  **Fix applicato**, identico nei due file: `_pick_photo_mobile()`/`_pick_mobile()` sono ora `async
  def`, chiamano `await picker.pick_files(...)` e processano la lista di file restituita
  direttamente (niente più `on_result`), i chiamanti sincroni (`_pick_photo()` in profilo_tab.py, i
  due `pick_image()` nei dialog crea/modifica mappa) le schedulano con `page.run_task(...)` invece di
  chiamarle direttamente — stesso pattern già corretto e verificato in `home_view.py`
  (`_on_mobile_export`/`_on_mobile_import`, scritte il 2026-07-24 con l'API async corretta fin
  dall'inizio: **non erano il problema**, nonostante Davide le avesse indicate tra le azioni rotte —
  o testate prima del fix del 2026-07-24, o un bug diverso non ancora riprodotto in un log; da
  riverificare dopo questo fix). Corretto anche un secondo bug minore trovato nello stesso punto di
  `maps_view.py`: `allowed_extensions` ha effetto solo con `file_type=FilePickerFileType.CUSTOM`
  (documentazione ufficiale), mai passato prima — il filtro estensioni non aveva mai avuto effetto.

  Verificato: `py_compile` su entrambi i file; `inspect.iscoroutinefunction()` conferma che
  `ProfiloTab._pick_photo_mobile`/`_pick_mobile` sono ora vere coroutine; `page.run_task` esiste
  davvero sul pacchetto 0.86.5 installato (non assunto); tutte e 4 le batterie di test
  (37+25+139+92 = 293) verdi, nessuna regressione. **Non verificabile da qui**: che il picker si apra
  davvero adesso su un vero Android — richiede un altro giro di test da parte di Davide, sui tre punti
  (foto profilo, immagine mappa, export/import — quest'ultimo già scritto correttamente, ma da
  riconfermare). `regole_flet_api.md` corretto con la vera causa (la vecchia diagnosi "bug di
  packaging Android upstream" è stata lasciata visibile ma marcata come smentita, non cancellata).

- **5 pillole di tab troncate illeggibili su smartphone stretto — stesso bug in due punti indipendenti
  (2026-08-06)** — Davide ha mandato screenshot di due schermate: la scheda personaggio ("Pro...",
  "Co...", "Espl...", "Inve...", "Diario" — solo l'ultima per caso abbastanza corta da stare intera) e
  la tab bar interna della Sezione Master (icone con lettere singole troncate, "Rubrica NPC"/"Note di
  Campagna"/"Oggetti Magici" irriconoscibili). **Causa identica in entrambi i file**, non un fix
  puntuale copiato alla cieca: `SheetView._make_tab_button()`
  (`ui/views/character_sheet/sheet_view.py`) e `MasterView._build_tab_bar()`
  (`ui/views/master/master_view.py`) costruivano 5 pillole ciascuna con `expand=True` per forzarle a
  dividersi in parti uguali su UNA riga sola, con `no_wrap=True`+`overflow=ELLIPSIS` come unico argine —
  su uno smartphone stretto lo spazio per pillola scende sotto quanto serve anche solo per "Combattimento"
  o "Note di Campagna", e l'ellissi taglia a poche lettere.

  **Fix**, identico nei due file e coerente con un pattern già in uso e verificato altrove nell'app
  (le pillole "Generatori Rapidi" del Master, `design.pill()`, non hanno mai usato `expand`): tolto
  `expand=True` da ogni pillola (si dimensiona sul contenuto, come `design.pill()`), aggiunto
  `wrap=True` alla Row che le contiene — su schermi stretti le pillole vanno a capo su più righe invece
  di restare forzate su una sola riga illeggibile; su schermi larghi il comportamento visivo resta
  sostanzialmente identico (i 5 tab restano affiancati, semplicemente non più costretti a dividersi
  esattamente lo spazio disponibile). **Rispettata la regola già documentata in `regole_flet_api.md`**
  ("MAI `wrap=True` su una Row/Column con un figlio `expand=True` → crash Flutter silenzioso, riquadro
  vuoto senza errore Python", trovata nel dialogo Bottino il 2026-07-31): qui infatti `wrap` ed
  `expand` non sono mai compresenti sullo stesso figlio, verificato non solo a occhio ma con un
  controllo automatico strutturale (sotto).

  `no_wrap=True`+`overflow=ELLIPSIS` sul `ft.Text` di ogni pillola restano come rete di sicurezza per
  larghezze patologicamente strette, non più come unico argine.

  Verificato: `py_compile` su entrambi i file, `test_regressione_wrap_expand.py` esteso da 35 a 37
  controlli con un nuovo `test_sheet_view()` (SheetView non aveva mai avuto un test di costruzione in
  questo file — `test_master_view()` esisteva già dal 2026-08-06 precedente e cammina comunque l'intero
  albero di `MasterView`, quindi ha ri-validato il fix di `_build_tab_bar()` per costruzione, senza
  bisogno di scriverne uno nuovo). 37/37 verdi. Nessuna regressione sulle altre batterie:
  `test_master_world_scoping.py` 25/25, `test_mondo_senza_rete.py` 139/139, `test_lan_host_client.py`
  92/92. `test_istanze_personaggio.py` ha continuato a fallire per lo stesso artefatto ambientale del
  sandbox già annotato nella sessione precedente (lancia `test_mondo_senza_rete.py` come subprocess che
  non eredita l'ambiente Python con `flet` installato) — non correlato a queste modifiche, verificato
  eseguendo `test_mondo_senza_rete.py` da solo nello stesso ambiente (139/139 verde). **Non verificabile
  da qui**: la resa visiva reale su un vero smartphone stretto — solo Davide può confermarlo.

---

> Questo file è stato estratto da `CLAUDE.md` il 2026-07-31 durante la riorganizzazione della documentazione del
> progetto (il file principale era cresciuto fino a superare 860 KB, causando compattazioni troppo frequenti della
> chat). Il contenuto è verbatim, nessuna informazione è stata riassunta o rimossa. Per la mappa completa dei
> documenti del progetto vedi `CLAUDE.md` alla radice.
