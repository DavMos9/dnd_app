# Progettazione delle 4 feature autorizzate — 2026-07-26

> Documento di **progettazione**. Nessuna riga di codice applicata.
> Feature autorizzate da Davide: (1) dadi collegati alla scheda,
> (2) concentrazione + condizioni PHB, (3) oggetti magici + sintonia lato
> giocatore, (4) iniziativa e PE lato master.
> Il multiclasse è progettato separatamente in `multiclasse_design.md`.
>
> **Regola dati del progetto rispettata**: ogni testo di regolamento nuovo
> (le 15 condizioni dell'Appendice A) va **letto visivamente dal PDF italiano**
> prima di essere scritto in JSON — non tradotto dall'inglese, non ricostruito a
> memoria. Nessun testo di regolamento è stato scritto in questo documento.

---

## 1 · Dadi collegati alla scheda

### Il problema

`DiceView` è dichiaratamente standalone ("nessun DB, stato solo in sessione") e
non conosce il personaggio. Nel frattempo la scheda calcola già ogni modificatore
utile — ma il calcolo è **duplicato inline in almeno 6 punti**: `pb =
char_prof_bonus(c)` seguito dalla matematica per-abilità compare in
`esplorazione_tab.py:77`, `combattimento_tab.py:1146/1534`, `sheet_view.py:134`,
`profilo_tab.py:110`, `spells_view.py:658/1418`. Non esiste un'unica fonte per
"quanto tira questo personaggio su Atletica".

### Architettura proposta

**Nuovo `core/character_stats.py`** (modulo puro, nessuna dipendenza Flet —
stesso principio di `weapon_calculator.py`/`level_manager.py`). Unica fonte di
verità per ogni modificatore tirabile:

```
RollSpec = {kind, label, modifier, ability, proficient, expert, note}

skill_roll(character, profs, skill_name)      -> RollSpec
save_roll(character, profs, ability_key)      -> RollSpec
ability_check_roll(character, ability_key)    -> RollSpec
initiative_roll(character)                    -> RollSpec   (include initiative_bonus)
attack_roll(character, weapon, profs)         -> RollSpec   (riusa weapon_calculator)
damage_roll(character, weapon)                -> RollSpec   (formula + danni magici extra)
death_save_roll()                             -> RollSpec   (CD 10 fisso, nessun mod.)
hit_die_roll(character)                       -> RollSpec
```

Beneficio collaterale importante: **le 6 duplicazioni inline diventano chiamate a
questo modulo**, quindi la feature *riduce* il codice invece di aggiungerne.

**Nuovo `core/dice.py`**: `roll(formula, advantage=None, modifier=0)` →
`RollResult {dice_results, kept, dropped, total, is_crit, is_crit_fail, formula_str}`.
Gestisce `NdM+K`, vantaggio/svantaggio (tira 2d20 e mostra quale scartato),
critico (20 naturale) e fallimento critico (1 naturale). Oggi la logica di tiro
vive dentro `DiceView._roll` — va estratta lì e riusata.

**UI**: un solo componente condiviso `ui/components/roll_button.py` →
`rollable(control, spec, page)` che rende qualunque riga/badge esistente
cliccabile-per-tirare, mostrando il risultato in un **pannello persistente**
(non un dialog modale: al tavolo serve vedere l'ultimo tiro mentre si continua a
leggere la scheda).

### Punti di aggancio (tutti già esistenti, solo da rendere tirabili)

| dove | cosa diventa tirabile |
|---|---|
| `esplorazione_tab` sezione Abilità | le 18 abilità |
| `esplorazione_tab` / `combattimento_tab` Tiri Salvezza | i 6 TS |
| `sheet_view` mini stat bar | prova di caratteristica pura (6 box) |
| `combattimento_tab` sezione Armi | tiro per colpire + danno di ogni arma |
| `combattimento_tab` Statistiche | iniziativa |
| `combattimento_tab` Tiri Salvezza contro Morte | TS morte (CD 10) — con **applicazione automatica** del successo/fallimento ai pallini |
| `combattimento_tab` Dadi Vita | tiro del dado vita nel riposo breve (oggi si digita il totale a mano) |
| `spells_view` | tiro per colpire con incantesimo; la CD è già mostrata |

### Decisioni da prendere con Davide

- **Storico dei tiri**: solo in sessione (come oggi) o persistito per personaggio?
  Persistito abilita "cronologia dell'ultima sessione" ma aggiunge una tabella.
- **Vantaggio/svantaggio**: chiedere ogni volta con un mini-selettore nel pannello,
  o tirare normale con due pulsanti scorciatoia accanto?
- **Il tiro modifica la scheda?** Il TS contro morte sì (proposto). Il danno no.
  Il dado vita nel riposo breve sì (compila il campo).

---

## 2 · Concentrazione + Condizioni

### 2a — Concentrazione

Il dato è **già presente**: tutti i 361 incantesimi in
`incantesimi_completi.json` hanno il campo `concentration`, e la UI lo mostra già
come tag (`spells_view.py:363`, `combattimento_tab.py:1745`). Manca solo lo stato.

**Schema**: nuove colonne su `characters` (via `_add_column()` idempotente, stessa
convenzione di tutte le migrazioni del progetto):
`concentrating_spell TEXT DEFAULT ''`, `concentrating_since TEXT DEFAULT ''`
(timestamp, per mostrare "da quanto").

**Comportamento (PHB p.203-204)**:
- Lanciare un incantesimo con concentrazione da `spells_view` → propone di
  attivare la concentrazione; se un'altra è già attiva, **avverte che la prima si
  interrompe** (regola PHB: una sola concentrazione).
- Sezione "Concentrazione" in `combattimento_tab` (sopra Azioni Turno): nome
  dell'incantesimo, pulsante "Interrompi".
- Al **danno subito** (`_on_damage_click`): se concentrato, propone il TS
  Costituzione con **CD = max(10, metà del danno)** — già calcolabile, e con la
  feature 1 diventa un tiro con un click. In caso di fallimento la concentrazione
  cade automaticamente.
- A **0 HP** o alla morte: cade automaticamente.
- Al **riposo lungo/breve**: azzerata.

### 2b — Condizioni (Appendice A PHB)

Oggi è tracciato solo l'Indebolimento. Le altre 14 condizioni non esistono.

**Prerequisito dati obbligatorio**: nuovo `data/game_data/conditions.json` con
nome e testo integrale delle 15 condizioni, **trascritti leggendo visivamente le
pagine dell'Appendice A del PHB italiano** (`pdftoppm`, mai `pdftotext`/OCR, mai
traduzione dall'inglese — la terminologia italiana non è deducibile: es.
"Frightened"→"Spaventato" ma "Restrained"→"Trattenuto" e "Grappled"→"Afferrato"
vanno verificati sul manuale). Prima di implementare la UI serve una sessione di
trascrizione, come per tutti gli altri dati di gioco.

**Schema**: nuova tabella `character_conditions`
`(id, character_id FK, condition_key, source TEXT, note TEXT, created_at)` —
tabella e non colonne, perché le condizioni sono più di una insieme e ognuna può
avere una fonte ("Incantesimo Spavento del Bardo", "morso del ragno gigante").
L'Indebolimento resta dov'è (`characters.exhaustion_level`): è l'unica con dei
livelli cumulativi, non un on/off.

**UI**: sezione "Condizioni" in `combattimento_tab` subito sotto HP — chip
attivi con colore semantico + "+ Aggiungi condizione" (picker con le 15 voci,
descrizione visibile prima di scegliere, coerente con il pattern `CardPicker`
già adottato). Ogni chip apre il testo integrale.

**Coerenza col manuale, senza automatismi invasivi** (stesso principio già scelto
per l'Indebolimento): l'app non applica meccanicamente gli effetti, ma li mostra
**dove servono** — es. se il personaggio è Avvelenato, accanto ai tiri per
colpire compare un indicatore "svantaggio". Questo va deciso: è la differenza tra
un tracker passivo e un assistente vero.

### Decisione da prendere

- Promemoria contestuali degli effetti (svantaggio accanto ai tiri, velocità 0 se
  Afferrato…) **sì/no**? Consigliato sì, in sola lettura: è quello che rende
  l'app fedele al manuale senza toglierti il controllo.

---

## 3 · Oggetti magici + sintonia lato giocatore

### Il problema

I 264 oggetti magici trascritti sono visibili **solo** in Modalità Master
(`MasterMagicItemsView`, quinta tab). Il giocatore non può sfogliarli né
aggiungerli alla propria scheda: l'unico modo è che il master li generi e li
spinga nell'inventario. E la **sintonia** non è tracciata da nessuna parte,
nonostante `requires_attunement` sia già nel dato di tutte le 264 voci (135
richiedono sintonia).

### Proposta

**A) Compendio anche lato giocatore.** `MasterMagicItemsView` è già una vista di
sola consultazione senza dipendenze dal master → si estrae in
`ui/views/magic_items_view.py` riusabile, e si aggiunge come voce nella sidebar
del giocatore accanto a "Talenti" (che è esattamente lo stesso caso: compendio
PHB indipendente dal personaggio). **Zero duplicazione**: la Modalità Master usa
lo stesso componente.

**B) "Aggiungi alla mia scheda"** dal compendio: crea un `InventoryItem` con
`category="magic"`, `description` = testo ufficiale integrale, `effects` = riga di
riepilogo (categoria · rarità · sintonia) — **esattamente la convenzione già usata
dal Generatore Oggetti Magici del master**, quindi nessuna nuova regola.

**C) Sintonia.** Nuova colonna `inventory_items.is_attuned INTEGER DEFAULT 0` +
`requires_attunement INTEGER DEFAULT 0` (va salvata sull'item, perché un oggetto
homebrew inserito a mano può richiederla e non sta nel catalogo).
- Sezione/riga "Sintonia: 2 / 3" nell'inventario, con i tre slot mostrati
  esplicitamente.
- Il limite di 3 è una **regola del manuale**: superarlo va impedito con un
  messaggio chiaro (non silenziosamente), coerente con come già si impedisce di
  superare il tetto di incantesimi preparati.
- Sintonia richiede un riposo breve: promemoria testuale nel dialog, senza
  automatismi.

### Da verificare prima di implementare

Il limite "massimo 3 oggetti sintonizzati" e la procedura di sintonia vanno
**riletti dal manuale italiano** (sono nella DMG, capitolo 7, sezione oggetti
magici) per riportare il testo esatto invece di una parafrasi.

---

## 4 · Iniziativa e PE lato master

### 4a — Tiro automatico dell'iniziativa

Oggi `add_member(...)` ha `initiative=10` di default e il master digita a mano
ogni valore: aggiungere 5 goblin significa compilare 5 campi. Il modificatore di
Destrezza è **già disponibile** nello stat block di tutti i 444 mostri.

**Proposta**:
- Nel dialog "Aggiungi Combattente", accanto al campo Iniziativa, un pulsante
  **"Tira"** (d20 + mod. DES calcolato dallo stat block, tramite il nuovo
  `core/dice.py`). Con quantità > 1, ogni copia riceve **il proprio tiro**
  (goblin 1 → 14, goblin 2 → 7): è la regola corretta se il master li tratta
  come individui, ed è ciò che rende utile il tracker.
- Pulsante **"Tira iniziativa per tutti"** nell'header dell'incontro: ritira
  l'iniziativa di tutti i membri `npc`/`adhoc` in un colpo. **I PG non vengono
  toccati** — coerente con la regola già stabilita "il master non scrive mai sui
  personaggi giocanti": per loro resta il campo manuale (il giocatore tira al
  proprio tavolo e comunica il valore).
- Opzione "gruppi identici tirano insieme" (variante DMG, un solo tiro per
  tutti i goblin) come checkbox — è una scelta del master, non una regola fissa.

### 4b — Assegnazione dei PE

È l'anello mancante più evidente tra Modalità Master e schede: il calcolatore di
difficoltà somma già i PE dei mostri, ma dopo l'incontro non c'è modo di
assegnarli.

**Proposta**: pulsante "Assegna PE" nell'header dell'incontro (accanto a
"Termina Incontro"):
- Somma i PE dei membri `npc`/`adhoc` **attivi e sconfitti** (serve una nozione
  di "sconfitto": oggi `hp_current == 0` oppure la rimozione soft del membro →
  va deciso quale usare, probabilmente entrambi con una checkbox per membro).
- Divide per il numero di PG partecipanti (membri `kind="character"`), con la
  possibilità di modificare il risultato a mano (il master può voler assegnare
  PE bonus per obiettivi narrativi — DMG).
- Scrive su `characters.xp` di ciascun PG. **Questa è la prima scrittura del
  master su un personaggio giocante in tutto il progetto**: è una deviazione
  consapevole dalla regola "il master non tocca i PG", che finora valeva per gli
  HP. Va confermata da Davide, e comunque con un dialog di conferma che mostra
  esplicitamente chi riceve quanto e il livello risultante ("Thorin: 6.500 →
  7.200 PE, sale al livello 6").
- Nessun level-up automatico: il giocatore lo fa dalla propria scheda, dove
  sceglie HP/ASI/incantesimi. L'app mostra solo il badge "Sali di Livello"
  che già esiste.

---

## Dipendenze tra le feature

```
core/dice.py + core/character_stats.py   (feature 1)
        │
        ├──► feature 1 · dadi sulla scheda
        ├──► feature 2 · TS Costituzione per la concentrazione (con un click)
        └──► feature 4a · tiro iniziativa dei mostri

data/game_data/conditions.json (trascrizione dal PDF)  ──► feature 2b

estrazione MasterMagicItemsView → componente condiviso ──► feature 3
```

Ordine consigliato: **1 → 4a → 2a → 3 → 2b → 4b**.
Motivo: la 1 costruisce le fondamenta (dadi + stats) e già di per sé rimuove
duplicazione; la 4a è piccolissima una volta che esiste `core/dice.py`; la 2b
richiede una sessione di trascrizione dal manuale; la 4b richiede la decisione
sulla scrittura dei PE sui PG.

---

## Decisioni aperte, in sintesi

1. Storico dei tiri persistito o solo in sessione?
2. Il TS contro morte tirato dall'app aggiorna automaticamente i pallini? (proposto: sì)
3. Promemoria contestuali degli effetti delle condizioni? (proposto: sì, in sola lettura)
4. Il master può scrivere i PE sui personaggi giocanti? (proposto: sì, con conferma esplicita)
5. Iniziativa: un tiro per ogni copia o un tiro per gruppo di mostri identici? (proposto: per copia, con opzione)
