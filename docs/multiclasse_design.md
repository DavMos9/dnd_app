# Multiclasse (PHB cap. 6) — progettazione e implementazione

> Progettato il 2026-07-26, rifinito il 2026-08-12, e — stesso giorno,
> **con il via libera esplicito di Davide** ("facciamo la sezione
> multiclasse adesso... implementiamo quando ti do io il via" seguito da
> "procedi senza chiedere permessi... fino alla fine del task") —
> **lo schema DB, la migrazione e l'intero repository layer sono stati
> implementati e testati in questa stessa sessione**. Le due tabelle PHB
> necessarie (prerequisiti, slot incantatore multiclasse) sono state lette
> visivamente dal PDF italiano (`pdftoppm`, mai `pdftotext`/OCR) — vedi §8
> per lo stato ESATTO di cosa è fatto/testato e cosa resta, con un limite
> deliberato: **nessuna nuova UI Flet è stata scritta in questo giro** (il
> dialog di level-up in `profilo_tab.py` è ~2400 righe di codice
> profondamente intrecciato con l'assunzione "una classe sola", mai
> visivamente testabile da questa sessione — rifarlo senza rischio
> richiede un giro dedicato, vedi §8.3). Non è più un documento di sola
> progettazione: è insieme progettazione E stato di avanzamento reale.

---

## 1. Perché è un intervento grosso

Oggi il personaggio ha **una** classe: `Character.class_name: str`,
`Character.subclass: str`, `Character.level: int`. Questi tre campi sono la base
di quasi tutta la logica di gioco dell'app. Una ricerca su `class_name` mostra che
viene letto in praticamente ogni modulo:

- `core/level_manager.py` — l'intero motore di level-up (`get_level_up_steps`)
- `core/wizard_engine.py` — creazione personaggio
- `data/repositories/character_repo.py` — `auto_init_spell_slots`,
  `init_class_resources`, `apply_class_base_proficiencies`,
  `sync_bonus_domain_spells`, `sync_borrowed_spellcasting_ability`,
  `calculate_and_update_ca`, `get_effective_speed`
- `config/settings.py` — `get_class_resource_defaults`, `get_permanent_class_hp_bonus`
- `ui/views/spells_view.py` — `_PREP_FULL`/`_PREP_HALF`/`_KNOW_CLASSES`, tetto
  dei preparati, CD e bonus di attacco
- i 5 tab della scheda + i 2 flussi di creazione

Non è quindi "aggiungere un campo": è **cambiare l'unità di ragionamento** da
"la classe del personaggio" a "le classi del personaggio, ciascuna con il suo
livello".

**Buona notizia verificata in questa revisione**: `get_level_up_steps()`
(`core/level_manager.py:254`) prende già `class_name` e `new_level` come
**parametri**, non li legge da `character.*` — oggi il chiamante
(`profilo_tab.py`) gli passa sempre la classe/livello primari perché esiste
una sola classe, ma la funzione stessa è già "per-classe". Stesso discorso
per `init_class_resources(character_id, class_name, level, character)` e
`apply_class_base_proficiencies(character_id, class_name)`
(`character_repo.py`): prendono `class_name`/`level` come argomenti, non li
derivano da `character.class_name` internamente. **Il motore dei singoli
livelli non va riscritto**: va richiamato una volta per ciascuna classe
posseduta invece che una volta sola sulla classe primaria. Il vero lavoro
nuovo è: (a) l'orchestrazione — quale classe sta salendo di livello, in
quale ordine vengono chiamate queste funzioni — e (b) le meccaniche che
sono **davvero** cross-classe e non esistono ancora in nessuna forma: slot
incantesimo condivisi, competenze ridotte da multiclasse, ASI/Attacco Extra
non cumulativi (§3).

---

## 2. Modello dati proposto

Nuova tabella, **senza toccare le colonne esistenti** (retrocompatibilità totale:
un personaggio a classe singola continua a funzionare identico):

```sql
character_classes (
  id TEXT PK,
  character_id TEXT FK → characters(id) ON DELETE CASCADE,
  class_name TEXT NOT NULL,
  subclass   TEXT DEFAULT '',
  level      INTEGER NOT NULL,
  is_primary INTEGER DEFAULT 0,   -- la classe di 1° livello: decide competenze iniziali ed equipaggiamento
  order_index INTEGER DEFAULT 0,  -- ordine di acquisizione (serve al level-up)
  created_at, updated_at
)
```

`characters.class_name` / `subclass` / `level` **restano**, con semantica
**invariata e non ambigua** (decisione presa in questa revisione, risolve il
"da decidere" della v1):

- `characters.class_name`/`subclass` = **sempre la classe primaria** (quella
  presa al 1° livello), esattamente come oggi per un personaggio a classe
  singola. **Nessuna stringa composita ci va mai scritta dentro.** Questo è
  ciò che rende l'intervento davvero retrocompatibile: ogni confronto
  esistente tipo `class_name.lower() == "warlock"` continua a rispondere
  correttamente alla domanda "la classe primaria è Warlock?", che è quasi
  sempre la domanda giusta per un personaggio a classe singola.
- `"Guerriero 3 / Ladro 2"` (la stringa composita per la UI) si calcola
  **sempre a runtime** da `character_classes`, mai salvata su `characters`:
  nuova `get_class_display_string(character)` in un punto unico (candidato:
  `data/repositories/character_repo.py`, accanto alle altre funzioni
  derivate), usata da header/stat bar/scheda. Zero rischio di
  disallineamento tra la stringa e le righe reali.
- `characters.level` = **livello totale del personaggio** = somma dei
  livelli di classe (mantenuto per bonus competenza, PE, e i molti effetti
  che dipendono dal totale — vedi `char_prof_bonus()` in
  `config/settings.py:101`, già corretta perché usa `character.level`).

**Audit dei confronti su `class_name`** (fatto in questa revisione, non
nella v1): **25 occorrenze** di `class_name ==`/`class_name.lower() ==` in
tutto il codice, concentrate in 4 file (`config/settings.py` 10,
`core/level_manager.py` 8, `character_repo.py` 5, `profilo_tab.py` 2) — un
numero gestibile per un audit puntuale, non "riscrivere tutto". Ogni
occorrenza va classificata in una delle due categorie quando si implementa:
1. **"È il personaggio di classe X?"** (es. mostrare/nascondere un box UI
   specifico di classe primaria) → resta `character.class_name == "X"`,
   invariato.
2. **"Il personaggio HA (anche) livelli in X?"** (es. Rage disponibile se
   Barbaro è una qualsiasi delle classi, non solo se è la primaria) → va
   convertito in un nuovo helper `character_has_class(character, "X")` che
   guarda `character_classes`, con fallback a `class_name` per i
   personaggi non ancora migrati/a classe singola.

**Migrazione**: al primo avvio, per ogni personaggio esistente si crea una riga
`character_classes` da `class_name`/`subclass`/`level` con `is_primary=1`.
Idempotente, stesso pattern dei self-healing già presenti nel progetto.

---

## 3. I 7 punti di logica da riscrivere

| # | Cosa | Regola PHB coinvolta | Difficoltà | Nota 2026-08-12 |
|---|---|---|---|---|
| 1 | **Punti ferita** | il dado vita è quello della classe con cui si prende il livello; il massimo si applica solo al 1° livello della classe primaria | media | `get_level_up_steps()` già riceve `class_name`/`new_level` per chiamata — il dado giusto si legge già dal JSON di quella classe. Nuovo solo: sommare gli HP guadagnati per-classe nel totale del personaggio. |
| 2 | **Bonus competenza** | dipende dal livello **totale**, non di classe | bassa | Già corretto oggi (`char_prof_bonus()` usa `character.level` totale). Nessuna modifica necessaria se `level` resta la somma. |
| 3 | **Competenze iniziali** | prendendo una nuova classe si ottiene solo un **sottoinsieme** delle sue competenze (tabella dedicata nel PHB, diversa dalla creazione) | media | `apply_class_base_proficiencies(character_id, class_name)` esiste già ma applica il set COMPLETO (creazione lv.1) — serve una funzione gemella `apply_multiclass_proficiencies(character_id, class_name)` con la tabella ridotta (dal PHB, §3 tabella prerequisiti/competenze cap.6), mai riusare quella esistente per una seconda classe. |
| 4 | **Slot incantesimo** | tabella **degli incantatori multiclasse** con un livello da incantatore calcolato (pieni contano tutto, metà contano metà arrotondata per difetto, un terzo un terzo) | **alta** | Confermato: `spell_slot_progressions.json` ha solo `full_caster`/`half_caster`/`warlock` — nessuna tabella multiclasse oggi. Nuova chiave `multiclass_caster` nello stesso file (letta dal PHB) + nuova funzione che somma i "livelli da incantatore" pesati di tutte le classi non-Warlock e guarda quella riga. `auto_init_spell_slots()` va **davvero** riscritta per questo caso (l'unica funzione di questo elenco che non basta richiamare per-classe). |
| 5 | **Slot del Patto separati** | il Warlock non si fonde con gli altri: mantiene i suoi slot a parte | alta | Stessa `auto_init_spell_slots()`: se una delle classi è Warlock, i suoi slot restano nella tabella `warlock` esistente (già corretta, invariata) mentre le altre confluiscono nel nuovo calcolo di #4. Le due tabelle di slot coesistono sullo stesso personaggio — verificare che la UI (`spell_slots` per `character_id`, non per classe) non presupponga un'unica riga per `slot_level`; oggi lo schema è già `(character_id, slot_level, total, used)` senza colonna classe, quindi gli slot "normali" multiclasse si sommano in una riga sola per livello — corretto per le regole (sono condivisi) — ma quelli del Patto vanno tracciati **a parte**: serve capire se serve una colonna/flag `is_pact` su `spell_slots` o una tabella gemella, da decidere leggendo prima come la UI attuale del Warlock (slot Patto) è già disegnata in `combattimento_tab.py`/`spells_view.py`. |
| 6 | **Incantesimi conosciuti/preparati** | si calcolano **per classe**, col livello di quella classe, mentre gli slot sono condivisi | **alta** | Il punto più contro-intuitivo del capitolo, confermato invariato dalla v1: `_PREP_FULL`/`_PREP_HALF`/`_KNOW_CLASSES` in `spells_view.py` presumono una sola classe/lista. Un Chierico/Mago multiclasse prepara dalla lista del Chierico E dal libro del Mago con regole diverse per ciascuna — richiede che la UI incantesimi iteri su `character_classes`, non su `character.class_name` una volta sola. |
| 7 | **ASI, Attacco Extra, privilegi** | non si sommano tra classi (Attacco Extra di Guerriero e Ranger non cumulano); gli ASI arrivano ai livelli della singola classe | media | `get_level_up_steps()` già calcola l'ASI sul livello DI QUELLA CLASSE (parametro `new_level`) — se l'orchestrazione chiama la funzione col livello di classe giusto (non il totale), l'ASI ai livelli corretti viene già gratis. Il non-cumulo di feature omonime (es. Attacco Extra) va gestito nell'orchestrazione: prima di mostrare/applicare una feature `FEATURE_AUTO`, controllare se il personaggio la possiede già da un'altra classe (confronto per nome feature letto dal JSON, non hardcoded). |

Inoltre: **prerequisiti di caratteristica** (non puoi prendere una seconda classe
senza il punteggio minimo) — vanno letti dal manuale e verificati alla scelta,
con la possibilità di ignorarli per house rule (coerente con `proficiency_bonus_override`
e gli altri override già presenti nel progetto).

---

## 4. Impatto sulla UI

- **Creazione personaggio**: nessuna modifica. Si nasce sempre a classe singola,
  il multiclasse arriva col level-up (come nel manuale).
- **Level-up** (`profilo_tab.py`, il dialog — oggi 4.498 righe, era 4.469 il
  2026-07-26, quindi non è cresciuto molto nel frattempo): nuovo primo passo
  "in quale classe prendi questo livello?" con l'elenco delle classi possedute
  (da `character_classes`) + "nuova classe" (filtrata sui prerequisiti letti
  dal PHB). **Decisione di design per limitare il rischio**: questo nuovo
  step è un selettore che precede il dialog esistente, che poi viene
  richiamato **invariato** passandogli la classe scelta e il SUO livello di
  classe (non il totale) — non un riscritto del dialog stesso, che resta il
  motore già collaudato su 12 classi. Il rischio si concentra tutto nel nuovo
  step di selezione e nell'orchestrazione a valle (dove scrivere il risultato:
  la riga `character_classes` giusta, non più solo `characters`).
- **Level-down**: deve sapere da quale classe togliere il livello — stesso
  selettore del level-up, riusato.
- **Scheda**: header e stat bar mostrano `get_class_display_string()` (§2);
  le sezioni "Abilità di Classe" e "Risorse di Classe" uniscono le fonti di
  tutte le classi (già facile per le Risorse: `init_class_resources()` è
  chiamabile una volta per classe, le risorse — Rage, Ki, Punti Stregoneria
  — non si fondono mai tra classi diverse, a differenza degli slot
  incantesimo).
- **Incantesimi**: la vista deve gestire più liste di classe contemporaneamente
  (vedi §3 punto 6) — oggi `_PREP_FULL`/`_KNOW_CLASSES` presumono una sola
  classe.

---

## 5. Prerequisiti prima di iniziare

Rivisti in questa revisione contro lo stato attuale del codice (2026-08-12):

1. ~~**Pulizia del codice duplicato**: `wizard_view.py`/`manual_form.py`
   duplicati al 67%~~ — **parzialmente vero ancora**. Da luglio esiste
   `ui/views/creation_wizard/creation_shared.py` (creato lo stesso
   2026-07-26, quindi un primo scorporo era già in corso), ma i due file
   restano grandi (`wizard_view.py` 3.950 righe, `manual_form.py` 3.480
   righe). Non è più un blocco assoluto — il multiclasse **non tocca la
   creazione** (§4, si nasce sempre a classe singola) — ma se si aggiungono
   ulteriori campi condivisi in futuro vale la pena continuare lo scorporo
   in `creation_shared.py` per lo stesso motivo di sempre (non raddoppiare
   il lavoro). Non bloccante per il multiclasse.
2. **`profilo_tab.py` a 4.498 righe** — qui sì che il multiclasse aggiunge
   un pezzo di UI dentro il file più grande del progetto. Vale la pena, PRIMA
   di iniziare l'implementazione (non ora), valutare se estrarre il dialog
   di level-up in un modulo a sé (`level_up_dialog.py` o simile) così il
   nuovo step "quale classe" ha una casa pulita invece di aggiungere altre
   centinaia di righe a un file già enorme. Decisione da confermare con
   Davide al via.
3. **Trascrizione dal manuale** delle 2 tabelle (prerequisiti, incantatore
   multiclasse, competenze ridotte in multiclasse) — da fare in sessione con
   il PDF caricato, prima di scrivere qualunque JSON. Nessuna di queste è
   stata letta finora (né nella v1 né in questa revisione).
4. **Test di regressione esistenti**: va verificato che tutti i personaggi a
   classe singola continuino a comportarsi identici — la matrice già in uso nel
   progetto (12 classi × sottoclassi × livelli 1-20) è il punto di partenza.
   La decisione di §2 (`class_name` resta sempre la classe primaria, mai una
   stringa composita) è pensata apposta per rendere questo test quasi
   automatico: un personaggio senza righe in `character_classes` oltre alla
   primaria deve comportarsi byte-per-byte come oggi.

**Condizione della v1 ("farlo solo dopo restyle, pulizia, le 4 feature")**:
soddisfatta — tutti e tre chiusi, vedi "Piano di lavoro attivo" in
`CLAUDE.md`. Il multiclasse resta comunque l'ultimo intervento del progetto
(su richiesta esplicita di Davide, invariata) e **non parte senza il suo via
libera esplicito**.

---

## 6. Stima onesta

Non è un task da una sessione. Realisticamente, con l'orchestrazione
"chiama le funzioni esistenti per-classe" confermata in questa revisione al
posto di un riscritto totale:

- 1 sessione: trascrizione dati dal PDF + schema DB (`character_classes`) +
  migrazione + repository (audit dei 25 confronti `class_name ==`, §2)
- 1-2 sessioni: slot incantesimo multiclasse + slot del Patto separati (§3
  punti 4-5, l'unica parte che è davvero nuova logica, non riuso)
- 1 sessione: UI del level-up (nuovo selettore di classe + eventuale
  estrazione del dialog da `profilo_tab.py`, §5 punto 2)
- 1 sessione: scheda + incantesimi (liste multiple, §3 punto 6, §4)
- 1 sessione: test di regressione (12 classi × sottoclassi × livelli 1-20,
  invariati, più i nuovi casi multiclasse)

**Raccomandazione**: procedere solo dietro via libera esplicito di Davide.
Resta l'unico intervento del progetto che può far regredire funzionalità già
collaudate su tutte le 12 classi — da qui la scelta di §2/§4 di minimizzare
la superficie toccata (riuso del motore esistente, mai una riscrittura).

---

## 7. Changelog di questa revisione (2026-08-12)

Richiesta da Davide: "facciamo la sezione multiclasse adesso... progettiamola
per bene adesso e poi la implementiamo quando ti do io il via" — nessuna riga
di codice scritta, solo progettazione rifinita. Verificato contro il codice
reale (non assunto dalla v1):
- Tutti i riferimenti a file/funzioni della v1 sono ancora validi (nessuno
  rinominato/rimosso).
- `get_level_up_steps()`/`init_class_resources()`/`apply_class_base_proficiencies()`
  sono già parametrizzate per classe — riducono lo scope reale di riscrittura
  (§1, §3 punti 1/2/7).
- Risolta l'ambiguità "da decidere" della v1 sulla rappresentazione di
  `class_name`: resta sempre la classe primaria, mai una stringa composita
  (§2).
- Contati i 25 confronti `class_name ==` reali nel codice e classificati in
  2 categorie per l'audit futuro (§2).
- Verificato lo stato dei 2 prerequisiti della v1: dedup wizard/manual_form
  parzialmente fatto e non bloccante (creation_shared.py esiste già),
  `profilo_tab.py` sostanzialmente invariato in dimensione (§5).
- Confermato che `spell_slot_progressions.json` non ha ancora una tabella
  multiclasse (§3 punto 4) — resta l'unico pezzo di logica davvero nuovo,
  insieme agli slot del Patto separati (punto 5).

---

## 8. Stato implementazione (2026-08-12, sessione successiva — via libera di Davide)

> Davide ha dato il via libera esplicito nello stesso giorno della
> rifinitura ("procedi senza chiedere permessi... fai quello che vuoi fino
> alla fine del task"). Questa sezione sostituisce ogni frase precedente
> "da NON implementare" per le parti effettivamente scritte: registra
> ESATTAMENTE cosa è fatto e testato, cosa è deliberatamente fuori scope in
> questo giro (con motivazione), e cosa resta come prossimo passo concreto.
> Non è una promessa, è un consuntivo verificabile — ogni riga sotto "Fatto"
> ha un test che la copre in `test_multiclasse.py` (29/29 file di
> regressione verdi, incluso questo nuovo file — unica eccezione le stesse
> 2 cause pre-esistenti e note in `test_qr_scan.py`, indipendenti da questa
> feature).

### 8.1 Fatto e testato

**Dati PHB** (letti visivamente dal PDF italiano, `pdftoppm`, cap.6 p.163-165,
mai `pdftotext`/OCR): `data/game_data/multiclass_data.json` — tabella
Prerequisiti di Multiclasse (p.163) e Competenze dei Multiclasse (p.164).
Confermato che la tabella "Incantatore Multiclasse" (p.165) è **identica**
a `full_caster` già esistente — nessuna tabella duplicata, riusata via
`game_data.get_multiclass_spell_slot_table()`.

**Schema DB**: nuova tabella `character_classes` (`data/database.py`) +
migrazione self-healing idempotente (`_migrate_backfill_character_classes`)
che backfilla ogni personaggio pre-esistente con una riga primaria da
`class_name`/`subclass`/`level`. `create()` inserisce la riga primaria per
ogni nuovo personaggio. Verificato: un personaggio "legacy" inserito con
SQL diretto (senza riga) viene backfillato correttamente e
idempotentemente da `init_db()`.

**Repository** (`data/repositories/character_repo.py`), tutte testate in
`test_multiclasse.py`:
- `get_character_classes`/`get_primary_character_class`/`character_has_class`/
  `get_class_display_string`/`add_character_class`/`set_character_class_level`/
  `remove_character_class`/`sync_character_total_level`
- `check_multiclass_prerequisites` — advisory (mai un blocco duro, stesso
  principio degli altri override del progetto), controlla sia le classi
  già possedute sia quella nuova, riproduce l'esempio del manuale
  (Guerriero: Forza 13 OPPURE Destrezza 13)
- `apply_multiclass_proficiencies`/`resolve_multiclass_choice_options`/
  `apply_multiclass_proficiency_choices` — competenze RIDOTTE (mai quelle
  complete di creazione), riusa `classify_bonus_proficiency_entries`/
  `apply_subclass_bonus_proficiencies` già esistenti
- `init_class_resources` **modificata** (bug reale trovato PRIMA di
  scrivere qualunque UI: la strategia "replace totale per nome" avrebbe
  cancellato le risorse di un'altra classe se richiamata una volta per
  classe) — ora unisce i default di TUTTE le classi possedute, con
  gestione esplicita del caso di nome omonimo tra classi (es. Incanalare
  Divinità di Chierico/Paladino — tiene il valore più alto, limite
  documentato nel codice, non "il PHB letterale" per questo incrocio raro)
- `sync_multiclass_spell_slots` — nuova funzione, usata SOLO quando
  `get_character_classes()` ha più di una riga (un personaggio a classe
  singola continua a passare da `auto_init_spell_slots()`, invariata).
  **Riproduce esattamente l'esempio numerico del manuale stesso**
  (p.164: "ranger 4/mago 3... personaggio di 5° livello... 4/3/2 slot")

**Sicurezza del level-up esistente** (`ui/views/character_sheet/profilo_tab.py`,
`_on_level_up_click`): fix mirato, non un riscritto — la funzione sale
SEMPRE la classe primaria (invariato), ma prima di questa sessione
scriveva `characters.level = new_level` usando `new_level` calcolato dal
livello TOTALE (`c.level + 1`). Per un personaggio multiclasse questo
avrebbe SOVRASCRITTO il totale con solo il livello della classe primaria,
perdendo i livelli delle altre classi (bug reale trovato leggendo il
codice, non ancora osservabile perché nessun personaggio è mai stato
multiclasse finora). Corretto: `new_level` ora è esplicitamente "il
livello che la classe primaria sta per raggiungere", separato da
`new_total_level` (usato solo per il bonus competenza, che resta sul
totale). A fine funzione, `character_classes` viene risincronizzata e
`characters.level` ricalcolato come somma reale — per un personaggio a
classe singola i due numeri coincidono sempre, **zero comportamento
diverso per nessun personaggio esistente** (verificato dalla suite di
regressione completa, 28 file preesistenti tutti ancora verdi).

### 8.2 Limiti noti e documentati (scelte di scope, non dimenticanze)

- **Slot del Patto del Warlock in un multiclasse Warlock+altra classe**:
  lo schema `spell_slots` ha una sola riga per `(character_id,
  slot_level)`, senza colonna per distinguere il pool condiviso da quello
  del Patto — separarli richiede una colonna/tabella nuova E la UI che la
  legge (`combattimento_tab.py`). `sync_multiclass_spell_slots()` logga
  un warning esplicito e scrive solo il pool condiviso (corretto per le
  classi non-Warlock) quando rileva questa combinazione — mai un crash,
  mai un numero silenziosamente sbagliato senza log. Un Warlock a classe
  SINGOLA non è toccato (percorso invariato).
- **Dadi Vita di tipo diverso tra le classi** (es. Guerriero d10 + Mago d6):
  `characters.hit_dice_type` resta una singola colonna (il dado della
  classe primaria); `hit_dice_total` continua a contare correttamente il
  NUMERO totale di dadi (ogni level-up della primaria ne aggiunge 1, come
  sempre), ma un personaggio con tipi di dado misti vedrebbe tutti i dadi
  mostrati come se fossero dello stesso tipo — cosmetico lato "riposo
  breve", non tocca HP/CA/altro. Richiede una tabella `character_hit_dice`
  dedicata per essere corretto al 100%, fuori scope qui.
- **Terzo-incantatore (Mistificatore Arcano/Cavaliere Mistico) in un
  multiclasse**: `init_borrowed_caster_slots()` resta un percorso
  indipendente (invariato) — il suo contributo al pool condiviso
  multiclasse (PHB: un terzo dei livelli, arrotondato per difetto) non è
  ancora sommato da `sync_multiclass_spell_slots()`. Incrocio raro (serve
  un Ladro/Guerriero CON quella sottoclasse specifica multiclassato con un
  altro incantatore), stesso principio di scope del punto sopra.

### 8.3 Cosa resta — prossimo passo concreto

**Nessuna nuova UI Flet.** Tutta la UI di livello (selettore "quale classe
sale", dialog per aggiungere una nuova classe con scelta competenze/
prerequisiti, scheda che mostra `get_class_display_string()`, vista
Incantesimi con liste per classe) resta da scrivere. Motivo: `profilo_tab.py`
`_on_level_up_click` è ~2400 righe profondamente intrecciate con `c.class_name`/
`c.subclass` (48 riferimenti), mai visivamente testabile da questa sessione
(nessun ambiente Flet interattivo) — costruire quel tanto di UI senza
poterla vedere funzionare sarebbe il tipo di rischio che questo stesso
documento, fin dalla v1, raccomandava di minimizzare (§6: "l'unico
intervento del progetto che può far regredire funzionalità già collaudate
su tutte le 12 classi"). Tutto il lavoro di backend che questa UI dovrà
richiamare esiste già ed è testato (§8.1) — il prossimo giro è
"1 sessione: UI del level-up" + "1 sessione: scheda + incantesimi" della
stima di §6, ora con zero incognite di schema/dati residue. Concretamente,
per riprendere: un nuovo dialog "Aggiungi una classe" (riusa
`get_level_up_steps(nuova_classe, 1, ...)`, già verificato produrre gli
step corretti per un livello 1 di qualunque classe — l'unico pezzo
mancante è la selezione degli incantesimi/trucchetti iniziali per le
classi "know"-caster, oggi gestita solo dal flusso di creazione, non da
`level_manager.py`) più il selettore "quale classe" da anteporre al
dialog di level-up esistente quando `get_character_classes()` ha più di
una riga.
