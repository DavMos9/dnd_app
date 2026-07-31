# Funzionalità Implementate e TODO Storico

> Checklist storica dettagliata di implementazione feature per feature, con changelog di verifica per ogni voce
> completata (✅) e le rare voci ancora aperte. Le voci realmente aperte/attive di alto livello sono già riassunte
> in `CLAUDE.md` → "Revisione 2026-07-26 — Piano di lavoro attivo"; questo file è il dettaglio storico completo da
> consultare per capire COME e QUANDO una feature è stata implementata/verificata, o per evitare di rifare un
> lavoro già fatto.

## TODO — Implementazione Futura

### Priorità Alta (prossimi step)
- [x] **SheetView** (`sheet_view.py`) — mini stat bar + 5 tab con header personaggio ✅
- [x] **Tab Profilo** (`profilo_tab.py`) — anagrafica, fisico, personalità, storia, competenze, level-up, foto ✅
- [x] **Foto personaggio** — cross-platform file picker + base64 DB + data URI display ✅
- [x] **Tab Combattimento** (`combattimento_tab.py`) — HP tracker, slot BG3-style, azioni turno, death saves, riposo, **CA bonus cliccabile** ✅
- [x] **Tab Esplorazione** (`esplorazione_tab.py`) — sensi, velocità, lingue, strumenti, tiri salvezza, abilità, **Appunti di Sessione** ✅
- [x] **Tab Inventario** (`inventario_tab.py`) — CRUD armi (tipo Dropdown, proprietà Checkbox, danni magici,
  impugnatura Versatile), sezione Armature dedicata (CRUD armature/scudi con esclusione reciproca di postazione),
  CRUD oggetti (misc/tool/magic), monete ±delta ✅
- [x] **Tab Diario** (`diario_tab.py`) — lista voci, crea/modifica/elimina con dialog, stato vuoto ✅
- [x] Repository armi CRUD + `magic_damages` JSON ✅
- [x] Repository inventario CRUD + `ca_value/armor_type/effects` ✅
- [x] Repository diario CRUD ✅
- [x] `update_ca_bonus`, `update_session_notes`, `calculate_and_update_ca` ✅
- [x] `replace_proficiencies_by_types(character_id, proficiency_type, entries)` ✅ — usato da edit dialog competenze in ProfiloTab
- [x] DB migration: `ca_bonus`, `proficiency_bonus_override`, `session_notes`, `magic_damages`, `ca_value`, `armor_type`, `effects` ✅
- [x] **Modifica caratteristiche** dalla MiniStatBar (clic su qualunque box) — dialog 6 punteggi 1–30 ✅
- [x] **Bonus competenza override** — clic su "+X comp." nell'header, campo `proficiency_bonus_override`, propagato a Profilo/Combattimento/Esplorazione ✅
- [x] **Slot incantesimo BG3-style** — grafica cerchietti pieni/vuoti per livello ✅
- [x] **JSON dati di gioco** — 12 classi, 9 razze, 12 background ✅ (tags.json rimosso il 2026-07-10, era dato morto/sbagliato — vedi sezione `equipment/`)
- [x] **Tracker Indebolimento (Exhaustion) in UI** ✅ **implementato il 2026-07-16** — nuovo campo
  `Character.exhaustion_level: int = 0` (0-6), colonna DB `characters.exhaustion_level` via `_add_column()`, nuova
  `character_repo.update_exhaustion_level()` (clamp 0-6 anche lato repo, non solo UI). Nuova sezione
  "Indebolimento" in `combattimento_tab.py` (tra Statistiche e Azioni Turno): counter −/+ con colore che scala
  (grigio→ambra→rosso), lista degli effetti cumulativi da `EXHAUSTION_LEVELS` attivi al livello corrente. **Nessun
  enforcement automatico delle regole** (non dimezza velocità/HP max da solo, non applica/rimuove livelli da
  feature/incantesimi in automatico) — per scelta di design, stesso principio già usato per Abilità di
  Classe/Tratti di Razza: la sezione è un riferimento di consultazione rapida, il giocatore/master applica gli
  effetti a mano. Verificato con test end-to-end (DB temporaneo isolato): round-trip DB
  (create/update/update_exhaustion_level, incluso il clamp su valori fuori range), costruzione della sezione UI per
  tutti i livelli 0-6, click su +/− che clampano correttamente a 0 e 6, regressione su tutte le 12 classi.

### Priorità Media
- [x] **`game_data_loader.py`** — singleton lazy-loading JSON classi/razze/background/spell/tag con cache ✅
- [x] **Sezione Dadi** (`key="dice"`) — `dice_view.py` ✅
- [x] **Sezione Mappe** (`key="maps"`) — `maps_view.py` ✅ (vedi sezione dedicata sotto)
- [x] **Sezione Diario** (`key="diary"`) — `diary_view.py` ✅
- [x] **Features classi nei JSON** — array `features` (base + sottoclasse) per tutte le 12 classi PHB 5e 2014 italiano ✅
- [x] **Abilità di classe e tratti razza in CombattimentoTab** — sezione clickable rows + dialog, chip resistenze/vantaggio ✅
- [x] **Risorse razziali** — `get_race_resource_defaults()` + `get_race_display_traits()` in settings.py ✅
- [x] **Wizard 5 fasi complete** — sottorazza, sottoclasse lv1, abilità, lingue/strumenti background, equipment A/B ✅
- [x] **Scelte extra wizard** — Stregone+Draconiana, Guerriero stile combattimento, Mezzelfo flex bonus, Alto Elfo trucchetto, Umano lingua ✅ (bug attivazione Mezzelfo corretto il 2026-07-09)
- [x] **Level-up sottoclasse** — dropdown sottoclasse quando si raggiunge `subclass_choice_level` ✅
- [x] **Level-up scelte extra** — stile Paladino/Ranger Lv2, totem Barbaro Lv3, terreno Druido Lv2 ✅
- [x] **Level-up ASI/Talento** — RadioGroup +2/+1+1/Talento; dropdown feat da `feats.json` ✅
- [x] **Perizia (Expertise)** — Ladro Lv6, Bardo Lv3/Lv10 via `set_expertise()` ✅
- [x] **Invocazioni Occulte Warlock** — struttura `invocations.json` + UI checkbox con logica cumulativa ✅
- [x] **Metamagia Stregone** — 8 opzioni `METAMAGIC_OPTIONS`, Lv2 (+2) / Lv10+Lv17 (+1) ✅
- [x] **Patto del Warlock Lv3** — RadioGroup Catena/Lama/Tomo → `character.pact_boon` ✅
- [x] **Sezione Talenti in ProfiloTab** — visualizza feat, metamagie, patto e invocazioni ✅
- [x] **Validazione level-up** — `do_level_up` blocca il salvataggio se campi obbligatori mancanti (AlertDialog lista errori, dialog rimane aperto) ✅
- [x] **Compendio Talenti** (`FeatsView`) — 6° voce sidebar "Talenti", browser di tutti i 42 feat PHB con card cliccabili e dialog descrizione completa ✅
- [x] **Modifica talenti posseduti** — bottone "✎ Modifica talenti" in ProfiloTab sezione Talenti, dialog con checkbox per house rules ✅

### Da fare (contenuto JSON)
- [x] **`feats.json` contenuto** — 42 talenti PHB completi ✅
- [x] **`invocations.json` contenuto** — 32 invocazioni PHB complete ✅
- [x] **JSON incantesimi** — tutti completati: chierico, bardo, druido, mago, paladino, ranger, stregone, warlock ✅
- [x] **Sezione Incantesimi** (`key="spells"`) — `SpellsView` completa e connessa in `app.py` ✅
- [x] **`StepType.SPELL_LEARN`** — implementato in `level_manager.py` + `profilo_tab.py` ✅

### In sospeso (bassa priorità, utente ha rimandato)
- [x] **Ladro Lv1 Perizia alla creazione (wizard)** — sezione "Perizia (Ladro Lv.1)" nella fase Revisione: 2 abilità dal pool bg+classe, `set_expertise()` al salvataggio, validazione ✅
- [x] **Ladro Lv1 Perizia alla creazione (form manuale)** — inclusa nella riscrittura del form ✅
- [x] **Form manuale rifacimento** — `manual_form.py` completamente riscritto in 5 fasi con stesso sistema del wizard ✅

### Priorità Bassa / v2
- [x] ~~**Stile di Combattimento/Totem/Terreno non selezionabili nello stesso level-up in cui si sceglie la
  sottoclasse**~~ — **✅ risolto il 2026-07-16**. Bug reale confermato: in `profilo_tab.py → _on_level_up_click`, i
  picker di Animale Totem (Barbaro Lv3) e Terreno (Druido Lv2) erano condizionati da `sc_lower = (c.subclass or
  "").strip().lower()` — la sottoclasse GIA' persistita PRIMA di questo level-up — quindi non potevano mai
  comparire nello stesso level-up in cui si sceglie la sottoclasse (a quel punto `c.subclass` è ancora vuota), né
  al livello successivo (`new_level` non coincide più con la soglia). **Nota di scope**: verificato che lo Stile di
  Combattimento (Paladino/Ranger) NON era in realtà affetto dallo stesso bug — la sua condizione (`new_level == 2
  and cls_lower in ("paladino","ranger")`) non dipende affatto da `sc_lower`, perché lo stile si sceglie al Lv.2,
  un livello prima della soglia di scelta sottoclasse (Lv.3 per entrambe) — il testo del TODO originale lo
  includeva per errore.
  **Fix**: stesso pattern già usato per Mistificatore Arcano/Cavaliere Mistico — quando il level-up include lo step
  `SUBCLASS_CHOICE` (`subclass_dd_ref` popolato), Totem/Terreno vengono ora costruiti come `ft.Container` con
  visibilità agganciata dal vivo al dropdown sottoclasse tramite `on_select` (nuovo helper `_compose_on_select()`
  che concatena più handler sullo stesso dropdown senza sovrascriverli, per sicurezza futura anche se oggi
  Totem/Terreno/Mistificatore non si sovrappongono mai sulla stessa classe). Corretta anche la logica di
  salvataggio (`do_level_up`): il dropdown Totem/Terreno viene ora costruito "nascosto" anche per sottoclassi che
  non lo richiedono (per poterlo mostrare/nascondere reattivamente), quindi il salvataggio controlla la sottoclasse
  FINALE scelta prima di scrivere `c.totem_animal`/`c.land_terrain` — altrimenti un Barbaro Berserker si sarebbe
  visto salvare comunque il valore di default nascosto ("Orso").
  **Verificato** con test end-to-end (bypass Flet Page, DB temporaneo isolato): Barbaro Lv2→3 che sceglie
  "Combattente Totemico" nello stesso dialog vede comparire il picker Totem in tempo reale al cambio dropdown, e
  sceglierne uno lo salva correttamente sul personaggio; un Barbaro che sceglie "Cammino del Berserker" non ha
  alcun `totem_animal` salvato (non il default nascosto); stesso schema verificato per Druido Lv1→2 con "Circolo
  della Terra"/"Circolo della Luna".
- [x] ~~**Più scudi equipaggiabili contemporaneamente**~~ — **✅ risolto, TODO obsoleto (verificato 2026-07-16)**.
  Segnalato il 2026-07-11 come intervento futuro dedicato, ma di fatto già risolto lo stesso giorno come effetto
  collaterale del fix "CA non si aggiorna più con l'equipaggiamento" (vedi Note Importanti, stessa data):
  `core/equipment_manager.py → resolve_armor_equip()`/`ArmorCandidate` modella esplicitamente la postazione "scudo"
  come indipendente e limitata a 1 (`is_shield and a.armor_type == "scudo": continue  # un solo scudo alla volta:
  espelle l'altro`), applicata sia dal toggle rapido sia dal dialog Nuova/Modifica Armatura in `inventario_tab.py`
  tramite `_enforce_armor_exclusivity()`. Il checkbox era rimasto erroneamente non spuntato. Verificato con un
  nuovo test end-to-end dedicato (DB temporaneo isolato): due scudi creati entrambi `is_equipped=True`, dopo
  `_enforce_armor_exclusivity()` ne resta equipaggiato solo uno, CA ricalcolata correttamente (10 base + mod DES +
  2 scudo, non doppio scudo).
- [ ] **Mondi condivisi / LAN party** — modulo `network/` (oggi vuoto). ⚠️ **NON
  via websocket**: la progettazione del 2026-07-31 ha scartato i websocket
  (richiederebbero una dipendenza esterna, rischiosa per `flet build` mobile) in
  favore di HTTP con attesa lunga sulla sola stdlib. **Progettazione completa e
  decisioni tutte chiuse** in `dnd_app/docs/multiplayer_design.md` — leggerlo
  prima di scrivere qualunque cosa, e vedere la sezione «🌐 Mondi condivisi» in
  cima a questo file per il riepilogo delle 11 decisioni e dei vincoli tecnici.
- [ ] **Sistema bottino** (archivio del master, deposito comune del gruppo,
  assegnazione a destinatario, ripartizione monete in percentuale) —
  `dnd_app/docs/loot_design.md`. **Indipendente dal multiplayer**: funziona già
  su un dispositivo solo e in web, va implementato per primo. Collega i punti
  oggi scollegati: Compendio Oggetti Magici (264 voci), Artefatti e Veleni non
  hanno alcun modo di finire sulla scheda di un giocatore. **Passi 1-5 completati il
  2026-07-31** (schema, calcolo puro, tab Master, dialogo di assegnazione, wiring nei 6 punti);
  resta solo il passo 6 (deposito lato giocatore), bloccato sul modello mondo del Multiplayer.
  Ordine di lavoro `loot_design.md` §8:
  - [x] **Passo 1 — schema `loot_stash_entries` + repository** ✅ (2026-07-31) — tabella unica per Archivio del
    Master e Deposito del Gruppo (§2), distinti dal campo `stash_kind` (`"master"`/`"party"`); `world_id` ammette
    stringa vuota per l'archivio fuori-mondo (preparazione campagna prima che il mondo esista). CRUD in
    `data/repositories/loot_repo.py`, stesso stile try/except+logger di `master_repo.py`.
  - [x] **Passo 2 — `core/loot_calculator.py`** ✅ (2026-07-31) — modulo puro (nessuna dipendenza Flet), stesso
    principio architetturale di
    `treasure_generator.py`/`trap_generator.py`/`encounter_calculator.py`/`equipment_manager.py`. Due
    responsabilità (`loot_design.md` §5):
    - `split_coins_by_percentage(coins, quotas, mode)` — ripartizione monete per quota percentuale, due modalità
      (`"denomination"`: le 5 colonne di valuta spartite indipendentemente col metodo del resto più alto;
      `"value"`: intero controvalore in rame spartito e riconvertito nella combinazione di monete più efficiente).
      Le aliquote di cambio (1 mo=100 mr, 1 mp=1000 mr, 1 ma=10 mr, 1 me=50 mr) sono lette da
      `equipment/economy.json` tramite `GameDataLoader.get_currency_exchange_rate()` — mai riscritte a mano, stessa
      regola di ogni altra tabella del progetto.
    - `largest_remainder_allocation(total, quotas)` — metodo del resto più alto (§5.3): quota esatta → parte intera
      per troncamento → le unità rimanenti ai resti frazionari più alti, in ordine decrescente. Garantisce sempre
      che la somma delle parti assegnate sia **esattamente** il totale di partenza, mai un'unità creata o perduta —
      verificato con quote non intere (33/33/34 su 100), quote con uno zero, e il caso "resto negativo"
      (arrotondamento per eccesso che deve togliere un'unità a chi ha il resto più basso).
    - `split_quantity_by_shares(total_quantity, shares)` — validazione per oggetti indivisibili posseduti in più
      copie (pozioni, gemme): ripartizione per conteggio intero, mai per percentuale; blocca se la somma non
      combacia col totale.
    - `validate_quotas(quotas)` — quote negative o che non sommano a 100% (tolleranza 1e-6) bloccate con messaggio esplicito in italiano, mai corrette a discrezione dell'app (§5.1).
    - **Nuovi metodi `GameDataLoader`** (`get_economy()`, `get_currency_exchange_table()`,
      `get_currency_exchange_rate(frm, to)`) per leggere `equipment/economy.json → currency.exchange_table` senza
      mai hardcodare le aliquote.
    - **Verificato** con una batteria standalone di 40 controlli (nessun DB coinvolto, logica pura): ripartizione
      monete per denominazione e per valore su quote uguali/disuguali/con zero, somma sempre esattamente uguale al
      totale di partenza in ogni caso testato; conversione rame↔monete miste round-trip su importi arbitrari;
      validazione quote (somma≠100, quota negativa, dict vuoto) e validazione quantità (somma≠totale, quantità
      negativa, totale 0) tutte con messaggio corretto. `python3 -m compileall`/`pyflakes` puliti (zero warning).
  - [x] **Passo 3 — tab "Bottino" nella Sezione Master** ✅ (2026-07-31) — `ui/views/master/master_loot_view.py`
    (`MasterLootView`), quinta tab di `MasterView` accanto a "Oggetti Magici". Switch Archivio/Deposito (pillole),
    card per voce con azioni **assegna** (apre il dialogo condiviso, passo 4), **sposta** (`loot_repo.move_entry`,
    stesso id/timestamp, mai elimina+ricrea), **modifica** (dialog dedicato, monete a parte perché
    `loot_repo.update_entry()` non tocca le 5 colonne valuta), **elimina** (conferma). "+ Aggiungi voce" per bottino
    non ancora collegato a un generatore (via manuale, oltre a "Salva nell'archivio" nei punti del passo 5).
  - [x] **Passo 4 — dialog di assegnazione condiviso** ✅ (2026-07-31) — `ui/views/master/master_loot_assign_dialog.py`
    (`show_loot_assign_dialog(page, items, on_committed=None)`). Contratto d'ingresso: lista di dict costruiti da
    `simple_item()`/`coins_item()`/`item_from_stash_entry()` (mai `LootStashEntry` o formati diversi passati
    direttamente — disaccoppia il dialogo dalla sorgente, sia essa un tiro effimero non ancora salvato o una voce
    già in stash). Per voce: quantità 1 → un destinatario (personaggio/Deposito/Archivio) con "distribuisci a
    caso"; quantità >1 → contatori interi per destinatario, validati con `split_quantity_by_shares` (somma deve
    combaciare esattamente, non solo "non superare" — la funzione già scritta al passo 2 impone l'uguaglianza
    stretta, e questa è la fonte di verità seguita, non la formulazione più permissiva di `loot_design.md` §4.2).
    Monete: quote percentuali solo tra personaggi (mai deposito/archivio, come da §5.1), modalità
    denominazione/valore, anteprima dal vivo via `split_coins_by_percentage` — nessuna sezione "destinazione del
    resto" perché il metodo del resto più alto già implementato al passo 2 distribuisce sempre l'intero totale, senza
    mai lasciare resti scoperti (il §5.3 del design doc descriveva un problema che l'algoritmo scelto risolve da
    solo). Una sola schermata scrollabile con anteprima dal vivo per sezione, non il percorso guidato a 4 passi
    "Cosa/A chi/Monete/Riepilogo" del design doc — coerente con l'unico pattern dialog già in uso nel progetto
    (mai un wizard dentro un `AlertDialog`), motivato nel docstring del modulo. Validazione tutto-o-niente: se anche
    una sola voce inclusa fallisce, nessuna scrittura avviene.
  - [x] **Passo 5 — wiring nei 6 punti di generazione** ✅ (2026-07-31) — "Assegna…"/"Salva nell'archivio" aggiunti
    accanto alle scorciatoie esistenti (mai rimosse): Generatore Tesori (monete + gemme/arte + oggetti magici +
    cimelio in un colpo solo), Generatore Oggetto Magico, Compendio Oggetti Magici (dialog dettaglio, per nome
    esatto — prima l'unica via era il generatore casuale), Artefatti (lore + tutte le proprietà nominate per esteso
    nella `description`, mai un riassunto), Veleni. Nuovo helper condiviso `ui/widgets.show_snack()` (centralizza il
    pattern SnackBar già duplicato in `home_view.py`).
  - **Verificato** (senza mount Flet, DB SQLite temporaneo isolato in sandbox): `loot_repo` CRUD completo
    (create/get/move/delete), `simple_item`/`coins_item`/`item_from_stash_entry`/`save_items_to_stash` end-to-end,
    `MasterLootView()` costruibile senza eccezioni, la stessa sequenza di chiamate usata da `_on_confirm` del
    dialogo di assegnazione (split monete 101 mo su 2 PG con quote 50/50 → somma finale esattamente 101; ripartizione
    3 pozioni 2+1 tra 2 PG → inventari corretti). `python3 -m py_compile`/`pyflakes` puliti su tutti i file toccati.
  - **Passo 6 rimane bloccato** sul modello mondo del Multiplayer (deposito del gruppo lato giocatore — oggi il
    Deposito è comunque gestibile lato Master nella tab "Bottino", utile in locale dove Master e giocatori
    condividono lo stesso dispositivo).
- [ ] **Export scheda personaggio in PDF (scheda ufficiale D&D 5e IT)** — richiesta di Davide (2026-07-24), che ha
  caricato `dnd_blankcharactersheet_it.pdf` (la scheda ufficiale WotC italiana) chiedendo di generare l'export
  riempiendo esattamente quel modulo. **Ricognizione tecnica già completata in questa sessione** (non rifare
  l'analisi del PDF — tutto il materiale è salvato in `dnd_app/docs/pdf_sheet_reference/`, leggere prima
  `README.md` in quella cartella):
  - `dnd_blankcharactersheet_it.pdf` (copia del template originale, 3 pagine 594×783pt) — confermato **nessun campo
    AcroForm** (`pypdf.PdfReader.get_fields()` → `None`), è un PDF vettoriale piatto: l'unico modo di "compilarlo"
    è un overlay di testo a coordinate fisse (via `reportlab`) fuso con lo sfondo originale (via `pypdf`), non un
    vero "fill" di form.
  - `raw_extraction.json` — dump completo `pdfplumber` (words/rects/lines/curve_boxes con coordinate in pt) per tutte e 3 le pagine — usare questo invece di re-interrogare il PDF.
  - `grid-1.png`/`grid-2.png`/`grid-3.png` — le 3 pagine renderizzate con griglia in pt sovrapposta ogni 25pt, per calibrare a vista gli elementi grafici (cerchi/caselle) senza testo associato.
  - **Convenzione di layout scoperta**: il valore va scritto SOPRA l'etichetta di ogni campo (non sotto), verificato sul box header di pagina 1 e coerente in tutte le altre sezioni.
  - **Struttura already mappata** (dettaglio completo nel README): header pagina 1 (Classe&Livello/Background/Nome
    Giocatore + Razza/Allineamento/PX), 6 blocchi caratteristica, CA/Iniziativa/Velocità, Ispirazione/Bonus
    Competenza, le 18 abilità + 6 TS (posizioni Y tutte note), PF/Dadi Vita/TS contro morte, tabella armi (3
    righe), monete, box di testo liberi (tratti/ideali/legami/difetti/competenze/equipaggiamento/privilegi); pagina
    2 (dati fisici, aspetto, simbolo/fede, alleati, storia, tesoro, tratti aggiuntivi); pagina 3 — la più complessa
    — griglia a 3 colonne × livelli incantesimo (col1={0,1,2}, col2={3,4,5}, col3={6,7,8,9}), coordinate esatte di
    ogni marcatore di livello già estratte, pillole Slot Totali/Spesi per livello 1-9.
  - **Decisioni di design già confermate con Davide** (non richiedono altre domande): testo che eccede lo spazio →
    **riduci il font automaticamente**; più di 3 armi → **prime 3 nella tabella, le altre come elenco compresso in
    "Equipaggiamento"**; pagina 3 (incantesimi) → **inclusa solo se `character.spellcasting_ability` è
    valorizzata** (copre anche Mistificatore Arcano/Cavaliere Mistico via `sync_borrowed_spellcasting_ability()`
    già esistente).
  - **Cosa manca ancora** (elencato per intero nel README): calibrare a vista le coordinate esatte degli elementi
    grafici non testuali (cerchi caratteristica/competenza/ispirazione, scudi CA/Iniziativa/Velocità, colonna X dei
    pallini competenza, box PF, cerchi TS contro morte, caselle moneta, griglia armi, bounding box dei box di testo
    liberi, pagina 2 per intero, righe vuote sotto ogni livello incantesimo pagina 3); creare
    `core/pdf_sheet_exporter.py` (modulo puro, no Flet: overlay reportlab per pagina + merge pypdf con
    `PdfWriter`/`merge_page()`); aggiungere `reportlab`+`pypdf` a `requirements.txt` (oggi il progetto ha solo
    `flet`/`Pillow`); copiare il template in `dnd_app/assets/character_sheet_template.pdf` (asset bundlato, letto a
    runtime, nessun dato esterno); bottone "Esporta Scheda PDF" in `SheetView`/`ProfiloTab`, stesso pattern
    cross-platform già collaudato per l'export `.dndchar` (dialog nativo desktop, download web, file picker
    mobile).
- [x] **Import/Export personaggio (file singolo, cross-device)** ✅ **implementato il 2026-07-24** — richiesta di
  Davide (2026-07-16, progettata e implementata in una sessione dedicata l'24/07 su suo esplicito invito
  "progettiamolo prima un attimo e poi mettiamoci al lavoro"). Permette di esportare un personaggio in un file
  `.dndchar` e importarlo in questa stessa app su un altro dispositivo (o dopo una reinstallazione), senza doverlo
  ricreare da capo.

  **Decisioni di design, prese via `AskUserQuestion` prima di scrivere codice** (le uniche due scelte genuinamente ambigue, non deducibili dal resto del progetto):
  - **Gestione conflitti in import** (personaggio con lo stesso `id` già presente sul dispositivo di destinazione)
    → **"Chiedi ogni volta"**: dialog con 3 scelte esplicite — **Sovrascrivi** (elimina il personaggio esistente +
    tutte le entità figlie via CASCADE, poi reinserisce da zero con gli stessi id del file), **Crea copia** (nuovo
    UUID, importato come personaggio distinto), **Annulla**.
  - **Estensione file** → **`.dndchar`** (contenuto comunque puro JSON, ma estensione distinta e riconoscibile rispetto agli altri `.json` di dati di gioco del progetto, filtrabile nei dialog nativi).

  **Architettura — `data/repositories/character_export.py`** (nuovo modulo puro, no Flet): a differenza di ogni
  altro punto del progetto che scrive INSERT/UPDATE con liste di colonne scritte a mano (fonte storica di bug
  ricorrenti in questo progetto — vedi tutte le voci "colonna dimenticata nell'INSERT" in questo file, es.
  `dragon_ancestry`/`fighting_style`/`max_prepared_spells_override`/ecc.), l'intero modulo usa **introspezione di
  schema via `PRAGMA table_info(tabella)`** (`_table_columns()`): sia in export (legge sempre e solo le colonne che
  esistono davvero) sia in import (`_insert_row()`, filtra silenziosamente — con `logger.warning` — ogni chiave del
  file che non corrisponde a una colonna reale dello schema locale). Questo rende l'intero meccanismo "a prova di
  versione" in entrambe le direzioni: un file esportato da una versione più VECCHIA dell'app (colonna mancante)
  importa comunque, usando il DEFAULT della colonna nello schema locale; un file esportato da una versione più
  NUOVA (colonna sconosciuta) importa comunque, scartando silenziosamente il campo ignoto — mai un crash per un
  semplice disallineamento di schema.
  - `export_character(character_id)` → `{"export_format_version": 1, "app", "exported_at", "character": {...},
    "related": {tabella: [righe...]}}` — `related` copre tutte e 12 le tabelle figlio con FK verso `characters.id`
    (`character_proficiencies`, `weapons`, `inventory_items`, `currencies`, `spell_slots`, `known_spells`,
    `diary_entries`, `game_maps`, `campaign_notes`, `creature_entries`, `custom_abilities`, `class_resources` —
    costante `CHILD_TABLES`). Le immagini (`characters.image_data`, `game_maps.image_data`) sono già base64 nel DB,
    incluse direttamente nel JSON senza alcun file binario separato da gestire.
  - `import_character(data, mode)` (`mode: "new"|"overwrite"|"copy"`) — **transazione atomica** (una sola
    connessione/commit per l'intera importazione, `rollback()` su qualunque eccezione): mai uno stato di
    importazione parziale in caso di errore. `mode="overwrite"` sfrutta `ON DELETE CASCADE` (già presente su tutte
    le tabelle figlio) con un semplice `DELETE FROM characters WHERE id=?` — nessuna cancellazione manuale tabella
    per tabella. **Politica sugli id**: l'id del personaggio è preservato (mode "new"/"overwrite") o rigenerato
    (mode "copy"); l'id di riga delle tabelle figlio che ne hanno uno (non `currencies`/`spell_slots`, che non
    hanno una colonna "id") viene **sempre** rigenerato con un nuovo UUID ad ogni import, indipendentemente dalla
    modalità — mai riusati gli id del file sorgente, per evitare collisioni tra personaggi diversi importati nello
    stesso DB; `character_id` di ogni riga figlia è sempre riscritto sull'id di destinazione risolto, mai fidato
    dal file.
  - `validate_export_data()`, `character_id_exists()`, `peek_character_summary()`, `load_json_string()`,
    `export_to_json_string()`, `suggested_export_filename()` (es. `Thorin_Testarossa_Lv5_20260724_104302.dndchar`)
    completano l'API pubblica del modulo.

  **`data/database.py`**: nuova `get_character_exports_path()` — stesso identico principio di
  `get_image_library_path()` (2026-07-12): `~/dnd_character_exports/`, creata idempotente. Nessuna nuova colonna DB
  necessaria per questa feature (l'approccio a introspezione non ne richiede).

  **UI — strategia per piattaforma, stesso vincolo già ampiamente documentato in questo file** (`ft.FilePicker`
  strutturalmente non utilizzabile né su desktop né in web mode in Flet 0.85.3, bug upstream confermato
  flet-dev/flet#6040/#6250/#6251):
  - **Desktop nativo** (`ui/views/home_view.py`): dialog nativi via subprocess (macOS `osascript`, Windows
    PowerShell `SaveFileDialog`/`OpenFileDialog`, Linux `zenity`/`kdialog`) — stesso pattern già in uso per le foto
    in `profilo_tab.py`/`maps_view.py`. Aggiunta per la prima volta in questo progetto una variante **"save"** del
    dialog nativo (`_save_dialog_native()`), prima esisteva solo la variante "open".
  - **Web (deploy Docker)**: nuovo `ui/character_transfer.py` (`show_character_import_picker()`) — mirror esatto di
    `ui/image_library.py`: Davide copia/preleva i file `.dndchar` via SSH (scp/rsync) in una cartella dedicata
    (`get_character_exports_path()`), il picker in-app mostra i file lì presenti con anteprima nome/classe/livello
    letta dal contenuto prima di confermare. Nuovo bind mount Docker
    `./dnd_character_exports:/root/dnd_character_exports` in `docker-compose.yml`, stesso principio del bind mount
    già esistente per `dnd_image_library`. L'export in web scrive direttamente nella stessa cartella (nessuna
    interazione richiesta, a differenza dell'import).
  - **Mobile (Android/iOS)**: **scoperta tecnica non prevista, non richiesta dal task ma verificata prima di
    scrivere codice** — ispezionando direttamente il sorgente del package `flet==0.85.3` installato
    (`file_picker.py`), `FilePicker` in questa versione **non ha alcun attributo `on_result`** (solo `on_upload`);
    `pick_files()`/`save_file()` sono metodi `async def` che ritornano il risultato direttamente. Il codice
    mobile-picker già esistente nel progetto (`profilo_tab.py → self._file_picker.on_result = ...`) fa quindi
    riferimento a un attributo inesistente in questa versione pinnata — un bug latente pre-esistente, mai stato
    verificato contro una vera build mobile (nessuna prova che ne esistano in questo progetto). **Decisione presa
    in autonomia** (per non introdurre codice mobile non verificabile né copiare lo stesso pattern probabilmente
    rotto): Export/Import su Mobile mostrano un dialog onesto "non ancora disponibile" invece di codice non testato
    — Desktop e Web sono completi e verificati. Il bug latente pre-esistente in `profilo_tab.py`/`maps_view.py` è
    stato notato ma **deliberatamente non corretto in questa sessione** (fuori scope, non richiesto).
  - `HomeView`: pulsante "Esporta" (icona `IOS_SHARE`) su ogni card personaggio; pulsante "Importa" nell'header e
    nello stato vuoto; dialog di conferma conflitto a 3 scelte con anteprima nome/classe/livello sia del
    personaggio esistente sia di quello in arrivo.

  **Verificato** con una batteria di test end-to-end (DB temporanei isolati via `tempfile.mkdtemp()` + `HOME`
  separato per "device A" e "device B" — mai il DB reale di Davide): personaggio complesso (arma magica con danni
  extra, armatura, valute, 2 competenze, 9 slot incantesimo, 1 incantesimo conosciuto, 1 voce diario, 1 mappa con
  immagine base64 finta, 1 nota di campagna, 1 abilità custom, risorse di classe, 1 creatura evocata) esportato su
  "device A" e importato su "device B" pulito — **tutti i campi di `characters` combaciano esattamente**, tutti i
  conteggi delle 12 tabelle figlio corretti, l'immagine base64 della mappa preservata byte-per-byte, gli id delle
  righe figlie correttamente rigenerati (mai collisi con quelli del file sorgente) col contenuto intatto.
  Verificati tutti e 3 i percorsi di conflitto: `mode="new"` su un id già esistente fallisce puliamente senza
  duplicare nulla; `mode="overwrite"` ripristina correttamente nome/livello originali sovrascrivendo modifiche
  manuali fatte sul device di destinazione E ripulisce via CASCADE una riga diario estranea aggiunta a mano (prova
  diretta che l'`DELETE`+reinserimento funziona, non un semplice `UPDATE`); `mode="copy"` genera un id personaggio
  distinto con dati duplicati fedelmente e zero collisioni di id tra le armi delle due copie. Verificata la
  resilienza allo schema: un file con una colonna mancante (simulando un export da versione precedente, rimosso
  `frenzy_active`) importa comunque usando il DEFAULT della colonna; un file con una colonna sconosciuta aggiunta
  (simulando un export da versione futura) importa comunque scartando quel campo. Verificata la validazione su
  input malformati (JSON non parsabile, JSON valido ma non un dict, dict senza `"character"`/`"related"`/id vuoto)
  — tutti rifiutati con messaggio d'errore in italiano, mai un crash. `python3 -m py_compile`/`pyflakes` puliti su
  tutti i file toccati (`data/repositories/character_export.py`, `ui/character_transfer.py`,
  `ui/views/home_view.py`, `data/database.py` — zero errori, incluso zero rumore residuo su
  `character_export.py`/`database.py` verificati isolatamente); `python3 -m compileall` sull'intero albero sorgente
  (esclusa `build/`) — 0 errori.

  **Bug report di Davide (2026-07-24, stesso giorno) — "premuto salva non riesco a trovare il file"**: usando
  l'export desktop nativo (macOS, `python main.py` da terminale), il dialog di salvataggio del SO appariva e
  "Salva" sembrava completarsi, ma il file non risultava reperibile da nessuna parte. **Causa radice, trovata
  leggendo con attenzione `_save_dialog_native()`** (impossibile riprodurre/testare `osascript` in questo ambiente
  sandbox Linux — diagnosi fatta per lettura del codice, non per riproduzione diretta): la funzione trattava
  **qualunque esito diverso da "successo con path non vuoto" come un annullamento silenzioso**, `return None` senza
  mai mostrare nulla all'utente — indistinguibile dal caso reale "l'utente ha premuto Annulla". Se
  `osascript`/`choose file name` falliva per un motivo genuino (il più probabile su macOS moderno: permesso di
  Automazione negato a Python/Terminal per controllare "System Events", richiesto la prima volta che uno script
  tenta di generarlo), l'utente vedeva un dialog di sistema (magari proprio quello di richiesta permesso, o un
  errore dell'OS) e poi, dal punto di vista dell'app, "nulla" — nessun file scritto, nessun messaggio, esattamente
  il sintomo descritto. Un secondo fattore aggravante, indipendente dal primo: **nessuna cartella di destinazione
  esplicita** — `choose file name`/`SaveFileDialog`/`zenity --save` senza una cartella di partenza dichiarata si
  aprono nell'ultima cartella usata da quel meccanismo di sistema per un dialog qualsiasi (imprevedibile, spesso
  non quella che l'utente si aspetta), quindi anche in caso di successo reale il file poteva finire in un posto non
  intuitivo da controllare.

  **Fix, applicato simmetricamente a export E import** (stesso difetto di design presente in `_open_dialog_native()`, mai segnalato ma identico):
  - `_save_dialog_native()`/`_open_dialog_native()` non ritornano più solo `path`, ma `(path, error)`: `(path,
    None)` successo, `(None, None)` annullamento pulito (su macOS riconosciuto dal codice errore AppleScript
    `-128`/"User canceled" nello stderr — l'unico modo affidabile di distinguerlo da un errore vero), `(None,
    "messaggio")` per qualunque altro fallimento — che ora produce un `AlertDialog` di errore esplicito invece di
    un silenzio totale, con un suggerimento mirato ("Impostazioni di Sistema → Privacy e Sicurezza → Automazione")
    per il caso più probabile su macOS.
  - **Cartella di partenza fissata a Desktop** su tutte e 3 le piattaforme (`default location (path to desktop
    folder)` in AppleScript, `$d.InitialDirectory = [Environment]::GetFolderPath('Desktop')` in PowerShell, path
    assoluto `~/Desktop/<nome>` passato a `zenity`/`kdialog`) — un salvataggio "al buio" (utente preme Salva senza
    guardare la cartella) finisce comunque in un posto sempre uguale e facile da controllare.
  - **Verifica post-scrittura**: dopo aver scritto il file, `_export_desktop()` controlla `os.path.isfile(path)`
    prima di mostrare il dialog di successo — se per qualunque motivo il file non risulta presente, mostra un
    errore invece di promettere un salvataggio che potrebbe non essere avvenuto.
  - **Pulsante "Mostra nel Finder"/"Mostra nella cartella"** aggiunto al dialog di conferma export (solo per export
    desktop, non web — il file web vive sul server) — `_reveal_in_file_manager()`, nuovo metodo che lancia `open
    -R` (macOS)/`explorer /select,` (Windows)/`nautilus --select` con fallback `xdg-open` sulla cartella (Linux):
    risolve il problema alla radice indipendentemente dalla causa specifica, dando sempre un modo di localizzare il
    file con un click invece di dover leggere e capire un percorso testuale.
  - **Bug trovato e corretto durante l'implementazione stessa** (non nel codice originale, introdotto e poi
    corretto nello stesso passaggio): nel fallback Linux zenity→kdialog, se zenity falliva con uno stderr non vuoto
    (comune: warning GTK innocui tipo "cannot open display" su alcune distro, stampati anche in caso di successo)
    l'`error` veniva impostato e — se kdialog SUBITO DOPO riusciva con un path valido — quell'`error` restava
    comunque settato, facendo mostrare un errore all'utente nonostante il salvataggio fosse in realtà riuscito.
    Corretto azzerando `error` nel momento esatto in cui un tool successivo ottiene un path valido.
  - **Verificato** con una batteria di test di classificazione (monkeypatch di `subprocess.run`, nessuna vera GUI
    necessaria — l'unico modo di testare questa logica in questo ambiente sandbox, che non ha
    `osascript`/PowerShell/un display grafico): successo macOS/Windows, annullamento pulito riconosciuto
    correttamente su entrambi (incluso lo specifico codice `-128` di AppleScript), errore reale (automazione negata
    su macOS, ExecutionPolicy su Windows) correttamente distinto da un annullamento e con messaggio propagato,
    fallback Linux zenity→kdialog con il caso esatto del bug sopra (zenity fallisce con stderr, kdialog riesce
    subito dopo → deve risultare in successo pulito, non in un errore fantasma) — tutti e 9 gli scenari passati.
    `python3 -m py_compile`/`pyflakes` puliti su `ui/views/home_view.py`; `python3 -m compileall` sull'intero
    albero sorgente — 0 errori. **Limite onesto**: l'effettivo comportamento del dialog nativo (in particolare il
    vero messaggio d'errore che macOS restituisce per un diniego di Automazione, e se il pulsante "Mostra nel
    Finder" funziona come previsto) non è verificabile in questo ambiente sandbox Linux senza GUI — richiede
    conferma di Davide su un vero avvio `python main.py` su macOS.

  **Bug reale confermato da Davide, stesso giorno, subito dopo il fix sopra**: il fix precedente ha funzionato
  esattamente come previsto (l'errore vero è comparso invece di un silenzio), rivelando la causa radice reale —
  screenshot con l'errore AppleScript esatto: `"208:218: execution error: System Events ha trovato un errore: Non
  posso trasformare POSIX path of file \"Macintosh HD:Users:davide:Desktop:....dndchar\" nel tipo specifier.
  (-1700)"`. **Causa**: `choose file name` (e per lo stesso motivo `choose file`) e il successivo `POSIX path of f`
  erano annidati dentro `tell application "System Events" ... end tell` — quando il file di destinazione non esiste
  ancora (sempre vero per un salvataggio: si sta nominando un file nuovo), il riferimento restituito da `choose
  file name` viene interpretato da System Events secondo il proprio sistema di classi (da cui il path in stile Mac
  classico coi due punti "Macintosh HD:Users:...", visibile nell'errore) invece che secondo la classe generica
  delle Standard Additions — `POSIX path of`, anch'esso indirizzato a System Events dentro lo stesso blocco, non
  riesce a fare la coercizione e solleva `-1700`. **Non un problema di stile**: è l'idiom AppleScript standard e
  ampiamente documentato per questo genere di errore — `choose file`/`choose file name`/`POSIX path of` vanno
  eseguiti nel contesto di scripting di livello top (dove le Standard Additions si applicano correttamente), non
  dentro un `tell application` — `System Events` va usato solo per `activate` (portare in primo piano il dialogo).
  **Fix**: entrambi gli script AppleScript (`_save_dialog_native` E `_open_dialog_native`, corretti simmetricamente
  anche se solo l'export era stato segnalato) riscritti con `tell application "System Events" to activate` su una
  riga a sé, seguito da `choose file`/`choose file name`/`POSIX path of f` FUORI da qualunque blocco `tell` —
  nessun'altra modifica alla logica di classificazione annullamento/errore introdotta nel fix precedente (quella
  resta corretta, era proprio grazie a quel fix che l'errore reale è emerso invece di restare silenzioso).
  **Verificato**: rieseguita la stessa batteria di test di classificazione (monkeypatch `subprocess.run`, 9
  scenari) — tutti ancora passati, la logica di distinzione annullamento/errore non dipende dalla struttura interna
  dello script AppleScript, solo dal contenuto di stdout/stderr/returncode. `python3 -m py_compile`/`pyflakes`
  puliti; `python3 -m compileall` sull'intero albero sorgente — 0 errori. **Stesso limite onesto di prima**: il
  vero comportamento AppleScript non è testabile in questo sandbox Linux (nessun `osascript` disponibile) — questa
  correzione è basata sulla lettura diretta del messaggio d'errore esatto fornito da Davide (fonte primaria, non
  un'ipotesi) e sull'idiom AppleScript standard per risolvere `-1700` in questo scenario, ma richiede comunque
  conferma di Davide su un vero riavvio dell'export/import da macOS.

  **Follow-up, stesso giorno (2026-07-24) — Davide ha confermato il fix su macOS ("ok su mc funziona") e ha chiesto
  di 3 punti scoperti**: "ma attualmente non posso provarlo su android e nemmeno su linux, funzionano? per la
  versione web deve permettere il download con le schermate standard delle app web, poi è possibile fare l'import o
  abbiamo lo stesso problema delle immagini". Analisi (prima di scrivere codice, come da regola del progetto)
  trovata leggendo il sorgente installato di `flet==0.85.3`/`flet_web==0.85.3`, non per ipotesi:
  - **Web export → possibile con un download reale**: la libreria immagini (`get_image_library_path()`) e il picker
    import via cartella SSH esistevano già perché `ft.FilePicker`/`ft.UrlLauncher` sono controlli `Service`
    strutturalmente rotti in web mode (bug upstream confermato, issue flet-dev/flet#6040/#6250/#6251, "FilePicker
    and UrlLauncher Service controls fail in web mode") — ma i bottoni ordinari
    (`ElevatedButton`/`IconButton`/ecc.) espongono una proprietà `url: Optional[Union[str, Url]]` **nativa e
    gestita interamente lato client**, NON un controllo Service, quindi non soggetta allo stesso bug (verificato
    leggendo `inspect.signature(ft.ElevatedButton.__init__)` e la classe `ft.Url`/`ft.UrlTarget` nel pacchetto
    installato). Confermato anche (lettura diretta del sorgente Starlette scaricato, `responses.py`) che
    `FileResponse` usa `guess_type(...)` con fallback `application/octet-stream` per estensioni sconosciute —
    `.dndchar` non è mai riconosciuto, quindi ogni browser lo tratta come download invece di tentare di
    visualizzarlo.
  - **Web import → resta bloccato, stesso bug di sempre**: confermando il sospetto di Davide ("abbiamo lo stesso
    problema delle immagini") — anzi più ampio di quanto pensasse, perché sia `FilePicker` SIA `UrlLauncher` sono
    nominati esplicitamente rotti nella stessa issue: non esiste alcun modo, lato applicazione, di far scegliere un
    file al browser in questa versione di Flet in web mode. Resta quindi il picker via cartella SSH già esistente
    (`ui/character_transfer.py`), nessuna modifica.
  - **Android/iOS export/import → bug DIVERSO da quello web, genuinamente risolvibile**: alla domanda di
    chiarimento di Davide ("per android non ho capito, come mai non funziona? non avevamo il problema solo su
    web?") ho spiegato la distinzione: su mobile `FilePicker` FUNZIONA come controllo (nessun bug di framework), ma
    il codice pre-esistente in questo progetto (`profilo_tab.py`/`maps_view.py`, foto/mappe, mai scritto in questa
    sessione) usa `picker.on_result = callback` — un attributo che **non esiste affatto** in `flet==0.85.3`
    (verificato leggendo `flet/controls/services/file_picker.py`: l'unico event handler è `on_upload`, per il
    progresso di un upload). L'API reale è `await picker.pick_files(...)`/`await picker.save_file(...,
    src_bytes=...)`, metodi `async` che ritornano il risultato direttamente. Confermato che su mobile (a differenza
    del desktop) `save_file(src_bytes=...)` scrive realmente il file — il docstring lo dice esplicitamente ("On
    desktop this method only opens a dialog... The file itself is not created or saved", implicando che su
    mobile/web CON `src_bytes` lo fa per davvero) — e che `pick_files(with_data=True)` restituisce i byte
    direttamente in `FilePickerFile.bytes`, senza mai dover leggere un path locale (`FilePickerFile.path` è "sempre
    None in web mode" e non garantito nemmeno su mobile).
  - **Istruzione finale di Davide**: "fai entrambi poi li testo io in futuro e ti dico" — implementate entrambe le
    soluzioni, nessun test su vero dispositivo possibile in questo sandbox, in attesa della conferma di Davide.

  **Implementazione — web export (`ui/views/home_view.py`, `main.py`, `data/database.py`)**:
  - `main.py`: il ramo web di `ft.run()` ora passa `assets_dir=str(get_character_exports_path())` — Flet monta
    questa cartella staticamente alla radice dell'app (`FletStaticFiles`, verificato leggendo
    `flet_web/fastapi/flet_static_files.py`: l'esistenza di `assets_dir` è validata UNA SOLA VOLTA, pigramente,
    alla prima richiesta HTTP — deve quindi esistere già quando `ft.run()` viene chiamato, non essere creata più
    tardi; `get_character_exports_path()` la crea già idempotentemente da tempo, nessun problema). Stessa cartella
    già usata per l'import via SSH, ora con un secondo ruolo — documentato nel docstring di
    `get_character_exports_path()` in `data/database.py`.
  - `home_view.py`: `_export_web()` invariata nella logica di scrittura file, ma ora chiama
    `_show_export_success_dialog(filename, full_path, system=None, download_url=f"/{filename}")`.
    `_show_export_success_dialog()` esteso con un nuovo parametro opzionale `download_url` — se presente, aggiunge
    un bottone "Scarica" (`ft.ElevatedButton(url=ft.Url(url=download_url, target=ft.UrlTarget.BLANK), ...)`) PRIMA
    del bottone "Mostra nel Finder" già esistente (che resta condizionato a `system is not None`, quindi mai
    mostrato insieme a "Scarica" — sono mutuamente esclusivi per costruzione, export web non ha mai un `system`).

  **Implementazione — mobile Android/iOS export/import (`ui/views/home_view.py`)**:
  - `__init__`: nuovo `self._file_picker: ft.FilePicker | None = None`. Nuovo `did_mount()`: registra il FilePicker
    in `page.overlay` SOLO se `page.platform in (ft.PagePlatform.ANDROID, ft.PagePlatform.IOS)` — mai su
    desktop/web (dove `ft.FilePicker` è confermato rotto/inutile, vedi la regola già in cima a questo file "FILE
    PICKER").
  - Nuovo `_ensure_file_picker()` (fallback lazy-create, stesso pattern già in uso in
    `profilo_tab.py`/`maps_view.py` per lo stesso identico scenario, ma qui usato SOLO come rete di sicurezza se
    `did_mount()` non avesse ancora fatto in tempo).
  - `_on_export_click`/`_on_import_click`: nuovo ramo `platform in (ANDROID, IOS)` →
    `page.run_task(self._on_mobile_export, char)`/`page.run_task(self._on_mobile_import)` (il meccanismo
    Flet-nativo per lanciare una coroutine da un handler sincrono; confermato che `flet==0.85.3` supporta anche
    `async def` direttamente come `on_click=`, ma qui si parte da un `on_click` sincrono già esistente che gestisce
    anche i rami desktop/web, quindi `run_task` è la scelta corretta).
  - Nuovo `async def _on_mobile_export(char)`: `await picker.save_file(dialog_title=..., file_name=filename,
    file_type=ft.FilePickerFileType.CUSTOM, allowed_extensions=["dndchar"], src_bytes=json_text.encode("utf-8"))` —
    ritorna il path direttamente; `None`/stringa vuota → annullamento pulito (nessun errore mostrato, stesso
    principio già stabilito per i dialog nativi desktop); eccezione → dialog di errore; successo →
    `_show_export_success_dialog(filename, result_path, system=None)` (nessun bottone "Scarica"/"Mostra nel
    Finder", il file è già sul dispositivo del giocatore).
  - Nuovo `async def _on_mobile_import()`: `await picker.pick_files(dialog_title=...,
    file_type=ft.FilePickerFileType.CUSTOM, allowed_extensions=["dndchar","json"], allow_multiple=False,
    with_data=True)` — lista vuota → annullamento pulito; `files[0].bytes is None` → errore esplicito invece di un
    crash silenzioso; decodifica UTF-8 con proprio `try/except UnicodeDecodeError` (file corrotto/non testuale) →
    errore dedicato; successo → `self._do_import_from_text(text)`.
  - **Refactor di supporto**: `_do_import_from_path(path)` (usata da desktop e dal picker web, entrambi lavorano su
    un path locale) ridotta a un thin wrapper che legge il file e delega alla nuova `_do_import_from_text(text)` —
    che contiene tutta la logica di validazione/conflitto/import precedentemente inline in `_do_import_from_path`
    (`load_json_string`→`validate_export_data`→`peek_character_summary`→conflitto/`_run_import`), ora condivisa
    anche dal ramo mobile (che non passa mai da un path, solo da byte già in memoria).

  **Verificato**: `python3 -m py_compile` su `main.py`/`data/database.py`/`ui/views/home_view.py` — 0 errori;
  `pyflakes` sugli stessi 3 file — 0 errori genuini (solo il rumore preesistente di `from config.settings import *`
  in `home_view.py`, già noto). Confermato con introspezione diretta del pacchetto `flet==0.85.3` installato:
  `ft.Url`/`ft.UrlTarget` esistono, `ft.UrlTarget.BLANK` risolve correttamente, `ElevatedButton.__init__` accetta
  `url: Union[str, Url, None]`.

  **Test reale di Davide, stesso giorno (2026-07-24)** — confermato ("ok sembra funzionare su web e riesco a
  importarlo anche in locale (l'export web), quindi test superati su mc e web per il resto devo ancora testare"):
  **web export/download** ✅ confermato funzionante (bottone "Scarica" produce un vero download browser); **import
  locale del file scaricato** ✅ confermato funzionante (il file `.dndchar` scaricato via browser è stato importato
  correttamente su un'altra istanza dell'app — conferma indiretta anche che il contenuto scritto in
  `get_character_exports_path()`/servito da `assets_dir` è integro byte-per-byte, non solo che l'URL risponde);
  **macOS** (fix precedente, stesso giorno) ✅ già confermato. **Ancora da testare da Davide**: Android/iOS
  (`_on_mobile_export`/`_on_mobile_import`, `await picker.save_file()`/`pick_files()`) e Linux desktop nativo
  (dialog `zenity`/`kdialog` in `_save_dialog_native`/`_open_dialog_native`) — nessuno dei due è mai stato eseguito
  su un vero dispositivo/ambiente, la correttezza resta per costruzione (lettura diretta dell'API installata), non
  verificata end-to-end.
- [x] **Sezione Master — gestione NPC/mostri + strumenti da DM (INDICE)** ✅ **tutti i 10 punti completati
  (2026-07-24)** — richiesta di Davide (2026-07-16), **architettura progettata per intero il 2026-07-24, poi
  ESPANSA lo stesso giorno a 10 strumenti totali** dopo aver consultato l'indice della Guida del Dungeon Master,
  infine **suddivisa in task singoli il 2026-07-24** su richiesta esplicita di Davide ("crea i task per tutte le
  azioni medio piccole poi per quella grande la facciamo in una sezione a parte ma documentala bene"), e
  implementata per intero nella stessa giornata attraverso più sessioni consecutive (incluse alcune non
  interattive, "vai"/"non fermarti", con Davide assente). Documento completo in
  `dnd_app/docs/master_section_design.md` — resta il riferimento di progettazione originale, utile per capire il
  ragionamento dietro ogni scelta, ma tutti i sotto-task sono ormai implementati (vedi changelog dettagliato di
  ciascuno qui sotto). **Unico punto rimasto volutamente fuori scope**: il Compendio Oggetti Magici (punto 7 del
  design doc), un progetto a parte su scala paragonabile al bestiario (~250-350+ voci, ~25 sessioni stimate) — mai
  iniziato, richiede una sessione dedicata futura, vedi il TODO separato più sotto ("Sezione Master (7) — Compendio
  Oggetti Magici").

  **I 10 strumenti confermati** (i primi 3 già presenti nella richiesta iniziale di Davide, gli altri 7 proposti da
  Claude dopo lettura dell'indice DMG e confermati da Davide via `AskUserQuestion`, tutti selezionati — nessuno
  scartato): (1) tracker di combattimento multi-creatura, (2) rubrica NPC persistente, (3) creazione NPC/mostro (da
  bestiario / manuale / selezione diretta), (4) Calcolatore Difficoltà Incontro, (5) Note di Campagna del Master
  (indipendenti da ogni personaggio), (6) Generatore Tesori Casuali, (7) Compendio Oggetti Magici, (8) Generatore
  Trappole, (9) Riferimento Malattie/Veleni/Follia, (10) Generatore Incontri Casuali per Ambiente.

  **Suddivisione (2026-07-24)**: i punti 1-6 + 8-10 sono raccolti nei 7 sotto-task checkbox singoli qui sotto —
  implementabili in una o più sessioni normali, nessuno richiede trascrizione dati su scala pluri-sessione. Il
  punto **7 (Compendio Oggetti Magici) è volutamente ESCLUSO da questi task** e vive in un task a sé stante subito
  dopo (stessa scala di lavoro del bestiario, ~25 sessioni per 444 voci — non va iniziato "en passant" dentro una
  sessione dedicata ad altro).

  - [x] **Sezione Master (1-3) — nucleo: tracker di combattimento + rubrica NPC + creazione NPC/mostro** ✅
    (2026-07-24) — il nucleo originale richiesto da Davide, scope "Grande" (paragonabile all'Import/Export
    personaggio). Vedi `master_section_design.md` righe 1-181 per: le 3 decisioni `AskUserQuestion` già prese
    (collocazione in `HomeView`/"Modalità Master", ambito v1 = entrambe, iniziativa unificata PG+NPC), lo schema
    SQL completo (`master_npcs`/`master_encounters`/`master_encounter_members`, mai un riuso di `creature_entries`
    — FK `character_id` NOT NULL lì, andrebbe rotta), i due percorsi di creazione NPC ("Nuovo dal Bestiario" via
    `monsters.json` già 444/444 auditato, "Nuovo Manuale"), il refactoring PRELIMINARE necessario (estrarre il
    picker bestiario + dialog stat block da `CombattimentoTab`, oggi metodi privati, in helper condivisi — da fare
    con test di regressione su Forma Selvatica/Evocazioni PRIMA di costruire la parte nuova), e il design di
    `MasterEncounterView`/`MasterNpcListView`.
    - **Refactoring preliminare** ✅: nuovo modulo condiviso `ui/components/monster_picker.py` — estrae da
      `combattimento_tab.py` sia il picker di ricerca bestiario (`show_monster_picker(page, title, pool,
      existing_names, on_select, select_label, select_color, on_manual)`, generico e parametrizzato: non scrive più
      direttamente su `creature_entries`, il chiamante decide cosa fare del mostro scelto tramite `on_select`) sia
      il rendering dello stat block (`build_stat_block_column(dict)` + `show_stat_block_dialog()`), con un adapter
      `creature_entry_dict(obj)` che normalizza sia un dict grezzo di `monsters.json` sia un `CreatureEntry`
      persistito nella stessa forma. `combattimento_tab.py → _open_creature_search()`/`_show_creature_sheet()`
      ridotti a thin wrapper (`_open_manual_creature_dialog()` non toccato, resta specifico del personaggio).
      Verificato con 20 controlli end-to-end (DB temporaneo isolato): flusso Forma Selvatica (Druido, pool filtrato
      solo `type=="Bestia"`) e flusso Evocazioni (Stregone, pool intero) invariati byte-per-byte nel comportamento,
      smoke test sulle 12 classi. Nessuna regressione.
    - **Schema DB** ✅: le 3 tabelle (`master_npcs`, `master_encounters`, `master_encounter_members`) aggiunte a
      `data/database.py → _create_tables()`, con indici (`idx_master_npcs_name`, `idx_master_encounters_archived`,
      `idx_master_encounter_members_encounter`) — nessuna FK obbligatoria verso `characters`, coerente col design.
      **Unica deviazione deliberata dal design doc**: `master_npcs.saving_throws`/`skills` hanno default `'{}'`
      (non la stringa vuota `''` indicata nella bozza) — stessa convenzione già in uso e collaudata per
      `creature_entries` in questo progetto, evita un `json.loads('')` che solleverebbe eccezione; l'adapter
      `creature_entry_dict()` avrebbe comunque protetto da questo caso, ma il default a livello di colonna deve
      restare JSON valido di per sé. Dataclass `MasterNpc`/`MasterEncounter`/`MasterEncounterMember` aggiunte a
      `data/models.py`, stesso stile di `CreatureEntry`/`GameMap` (UUID via `default_factory`, liste/dict come
      stringa JSON).
    - **Repository** ✅: nuovo `data/repositories/master_repo.py` — CRUD completo per le 3 tabelle:
      `get_npcs(query="")`/`get_npc_by_id()`/`create_npc(...)`/`create_npc_from_monster(monster_dict, ...)`
      (convenienza per il percorso "Nuovo dal Bestiario", precompila tutto lo stat block da un dict `monsters.json`
      con `has_stat_block=True`)/`update_npc()`/`delete_npc()` (FK `ON DELETE SET NULL` sui membri d'incontro
      collegati — un NPC cancellato non fa sparire lo storico dell'incontro);
      `get_encounters(include_archived=False)`/`get_encounter_by_id()`/`create_encounter()`/`update_encounter_notes()`/`archive_encounter()`/`delete_encounter()`
      (CASCADE sui membri)/`advance_turn(encounter_id)` (avanza tra i soli membri `is_active=1` ordinati per
      iniziativa decrescente poi `order_index`, wrap con incremento di `round_number` a fine giro);
      `get_encounter_members(encounter_id, active_only=False)` (dataclass grezze) e
      `get_encounter_members_resolved(encounter_id, active_only=True)` (lista di dict pronti per la UI — per
      `kind="character"` risolve nome/CA/PF **live** da `characters` via JOIN, mai una copia cachata, coerente con
      la regola "il Master non scrive mai sugli HP dei PG"; per `kind="npc"`/`"adhoc"` usa i valori già cachati
      sulla riga membro)/`add_member()`/`update_member_hp()`/`update_member_initiative()`/`remove_member()` (soft
      delete, `is_active=0`, resta in storico)/`delete_member()` (hard delete, per correggere un'aggiunta per
      errore). Verificato con 57 controlli end-to-end (DB temporaneo isolato, mai quello reale): CRUD completo su
      tutte e 3 le tabelle, `create_npc_from_monster()` con un mostro fittizio, risoluzione live del PG (compreso
      un cambio HP fatto DOPO l'aggiunta all'incontro, verificato che si riflette subito, non una copia congelata
      al momento dell'aggiunta), riordino per iniziativa dopo un cambio, `advance_turn()` col wrap di round sia a 3
      sia a 2 membri attivi, soft-delete che esclude da `active_only=True` ma resta nello storico grezzo,
      hard-delete che rimuove davvero, `ON DELETE SET NULL` di un NPC referenziato (il membro resta con nome
      cachato), archiviazione/cascata di eliminazione incontro, idempotenza di `init_db()` su schema già popolato.
      `python3 -m py_compile`/`pyflakes` puliti; `python3 -m compileall` sull'intero albero sorgente (esclusa
      `build/`) — 0 errori.
    - **Navigazione** ✅ (2026-07-24): `HomeView` ha un nuovo bottone header "Modalità Master"
      (`_master_mode_button()`, icona `CASTLE_OUTLINED`, stile blu per distinguerlo visivamente da "Importa"/"Nuovo
      Personaggio" — è un cambio di modalità, non un'azione sui personaggi) — nuovo parametro opzionale
      `on_open_master=None` su `HomeView.__init__` (default `None` per retrocompatibilità: se non passato, nessun
      bottone viene renderizzato invece di sollevare un'eccezione). `ui/app.py → DnDApp`: nuovo
      `_show_master_view()` (stesso pattern di `_show_wizard()`/`_show_manual_form()` — MAI innestato in
      `MainLayout`, che resta esclusivo della scheda di UN personaggio selezionato), passato come callback a
      `HomeView` da `_show_home()`. Nuovo modulo `ui/views/master/master_view.py → MasterView` (shell): header con
      "Torna alla Home" + titolo, tab bar interna a 2 sezioni ("Rubrica NPC"/"Incontri", stesso stile visivo delle
      tab già in uso in `SheetView`/`DiaryView`) — ogni tab tenta di importare la vista reale
      (`MasterNpcListView`/`MasterEncounterListView`, non ancora scritte) e ricade su un placeholder "in
      costruzione" se il modulo non esiste ancora (`ImportError` catturato), così la navigazione è già completa e
      testabile prima che i task #4/#5 scrivano le viste vere — quando quei moduli verranno creati con quei nomi
      esatti, `MasterView` li userà automaticamente senza bisogno di modificare `master_view.py`. Verificato con 16
      controlli end-to-end (bypass `page` reale, `FakePage` minimale): bottone presente solo se la callback è
      passata, click che invoca la callback, instanziazione di `MasterView` senza eccezioni, cambio tab senza
      eccezioni (incluso il fallback placeholder per entrambe le tab, dato che nessuna vista reale esiste ancora),
      routing completo `DnDApp._show_home()`→click Master→`_show_master_view()`→click "Torna alla Home"→di nuovo
      `HomeView`. `python3 -m compileall`/`pyflakes` puliti (solo il rumore preesistente di `from config.settings
      import *`).
    - **`MasterNpcListView` + creazione NPC** ✅ (2026-07-24): nuovo `ui/views/master/master_npc_list_view.py` —
      lista/ricerca (nome/ruolo/tag) di tutti i `master_npcs`, card cliccabile (icona scudo se `has_stat_block`,
      altrimenti icona persona; badge CA/PF/GS se ha uno stat block; chip ruolo+tag) → dialog di dettaglio
      (ruolo/note/tag in testa, poi `build_stat_block_column(creature_entry_dict(npc))` se `has_stat_block` —
      stesso componente condiviso del refactoring di Task #1, riusato senza alcuna modifica) con 4 azioni:
      "Aggiungi a Incontro..." (dropdown sugli incontri non archiviati da `master_repo.get_encounters()`, messaggio
      informativo se nessuno esiste ancora — nessuna dipendenza rigida da Task #5, il repository era già pronto da
      Task #2), "Modifica", "Elimina" (dialog di conferma dedicato), "Chiudi".
      **Creazione, i due percorsi del design**: pulsante "+ Nuovo NPC" → dialog di scelta ("Nuovo dal Bestiario" /
      "Nuovo Manuale") → entrambi atterrano sullo STESSO form (`_open_npc_form()`, un solo form per creazione
      manuale/da bestiario/modifica, parametrizzato su `npc`/`prefill_monster`) — "Nuovo dal Bestiario" riusa
      `show_monster_picker()` (Task #1) sull'intero bestiario, poi chiude il picker e apre il form precompilato con
      l'intero stat block del mostro scelto (CA/PF/velocità/6
      caratteristiche/sensi/linguaggi/resistenze/GS/`source_page` leggibile) e `has_stat_block` già attivo, per gli
      "ultimi ritocchi" (nome/ruolo/note/tag, correggibili anche i campi numerici) prima del salvataggio effettivo
      — mai scritto su `master_npcs` prima della conferma esplicita. Il form ha un checkbox "Ha statistiche di
      combattimento" che mostra/nasconde l'intera sezione stat block (nascosta di default per "Nuovo Manuale", per
      non intimidire chi vuole solo un NPC di puro ruolo, coerente col design). **Scelta di scope deliberata**:
      Tratti/Azioni/Reazioni/Azioni Leggendarie non sono editabili riga per riga nel form (troppa complessità per
      un form rapido) — per un NPC creato dal Bestiario restano quelli importati dal mostro (mostrati come un
      conteggio di sola lettura, "Tratti N · Azioni N · ..."); per cambiarli davvero si ricrea l'NPC dal Bestiario.
      Validazione: nome obbligatorio, messaggio d'errore inline se mancante, dialog resta aperto.
      **Verificato** con 49 controlli end-to-end (`FakePage` minimale, DB temporaneo isolato, mai quello reale —
      stesso pattern già consolidato nel progetto per testare dialog Flet senza un vero client): creazione manuale
      completa (form→salvataggio→persistenza, `has_stat_block=False`), validazione nome vuoto (blocca il
      salvataggio, messaggio d'errore mostrato), intero flusso "dal Bestiario" (ricerca "GOBLIN" nel picker
      condiviso → click risultato → dettaglio stat block → "Usa questo mostro" → form prefill con nome/CA/checkbox
      già compilati correttamente → modifica del ruolo → salvataggio → verificato che `has_stat_block=True`,
      `actions` non vuoto/importato dal mostro, `source_page` leggibile), dettaglio con stat block reale
      renderizzato (tipo/allineamento visibili), Modifica (form precompilato coi valori esistenti, bottone "Salva"
      invece di "Crea NPC", persistenza confermata), "Aggiungi a Incontro..." sia col caso "nessun incontro"
      (messaggio informativo) sia con un incontro reale creato al volo (dropdown pre-selezionato, membro
      `kind="npc"` effettivamente inserito via `master_repo.add_member`), Elimina con dialog di conferma (NPC
      rimosso dal DB), ricerca filtrata end-to-end sulla vista reale (trova per nome parziale, stato vuoto per
      ricerca senza corrispondenze). Confermato anche che `MasterView` (Task #3) ora monta la vera
      `MasterNpcListView` nella tab "Rubrica NPC" invece del placeholder (l'`ImportError` di fallback non scatta
      più, il modulo esiste). `python3 -m py_compile`/`pyflakes` puliti; `python3 -m compileall` sull'intero albero
      sorgente (esclusa `build/`) — 0 errori.
    - **`MasterEncounterView`/`MasterEncounterListView` (tracker combattimento)** ✅ (2026-07-24): prima di scrivere
      il tracker, aggiunto un nuovo campo `xp` (colonna DB + dataclass + repository, vedi punto sotto) su
      `master_npcs`/`master_encounter_members` — necessario perché il Calcolatore Difficoltà (task #4, implementato
      nello stesso passaggio) deve sommare i PE dei mostri/NPC attivi in un incontro, e catturare quel valore al
      momento della creazione dell'NPC/dell'aggiunta del membro evita di dover ricostruire una tabella di
      conversione GS→PE separata (`monsters.json` ha già `xp` per tutti i 444 mostri auditati; per un NPC "Nuovo
      Manuale"/una Creazione Rapida il Master lo inserisce a mano). Colonna aggiunta sia nel `CREATE TABLE IF NOT
      EXISTS` (installazioni nuove) sia via `_add_column()` idempotente in `_migrate()` (DB già esistenti da prima
      di questa colonna) — stessa doppia convenzione già in uso per ogni altra migrazione di schema del progetto.
      `MasterNpc.xp`/`MasterEncounterMember.xp` aggiunti a `data/models.py`; `master_repo.py` esteso end-to-end:
      `_row_to_npc()`/`create_npc()`/`create_npc_from_monster()` (lo eredita da
      `monster.get("xp")`)/`update_npc()`, `_row_to_member()`/`add_member()`/`get_encounter_members_resolved()`
      (per `kind="character"` **sempre `0`** — un personaggio giocante non conta mai come PE mostro nel calcolo,
      coerente con la regola "il Master non tocca mai i PG"; per `kind="npc"`/`"adhoc"` il valore cachato sulla
      riga membro). Il form NPC esistente (`master_npc_list_view.py`, Task #4) esteso con un nuovo `xp_tf` (label
      "PE (per Calcolatore Difficoltà)"), wired in tutti e 3 i percorsi di creazione (modifica/da
      Bestiario/manuale) e nella card della rubrica (badge "N PE" se valorizzato).
      **`core/encounter_calculator.py`** (nuovo modulo puro, nessuna dipendenza Flet, stesso principio di
      `wizard_engine.py`/`level_manager.py`/`equipment_manager.py`/`weapon_calculator.py`): implementa il metodo in
      5 passi del DMG IT (Cap.3 "Creare le Avventure", p.82-83) — `PE_THRESHOLDS_BY_LEVEL` (tabella completa 20
      livelli × 4 categorie, letta visivamente dalle pagine renderizzate del PDF via `pdftoppm -r 200`, MAI da
      `pdftotext`/OCR, che su questa tabella corrompe diverse cifre — es. "l.100" al posto di "1.100"),
      `_BASE_MULTIPLIERS` (tabella "Moltiplicatori degli Incontri", 1/2/3-6/7-10/11-14/15+ mostri →
      ×1/1.5/2/2.5/3/4, questa tabella non presentava corruzione OCR), `encounter_multiplier(monster_count,
      party_size)` (applica la rettifica "Dimensioni del Gruppo" verificata visivamente sulla pagina successiva:
      gruppo <3 PG → riga superiore della tabella, con un valore extra ×5 sopra il ×4 di base per 15+ mostri, dato
      esplicitamente come esempio nel testo del manuale; gruppo ≥6 PG → riga inferiore, con un valore extra ×0,5
      sotto l'×1 di base per un singolo mostro, anch'esso citato testualmente — nessuno dei due valori estremi è
      un'estrapolazione, entrambi combaciano con gli esempi del DMG), `get_pe_threshold(level, difficulty)`,
      `calculate_difficulty(monster_xp_list, party_levels)` (ritorna PE totale mostri, moltiplicatore, PE
      modificato, soglie di gruppo per le 4 categorie, e la categoria di difficoltà finale — confronto "soglia più
      vicina e inferiore al PE modificato", esattamente come descritto nel manuale). Nessuna tabella GS→PE
      separata: il calcolatore somma direttamente il campo `xp` già presente su ogni mostro/NPC.
      **`MasterEncounterListView`** (`ui/views/master/master_encounter_list_view.py`, nuovo): lista degli incontri
      non archiviati (card con nome/round/conteggio combattenti/note, pulsante elimina con conferma), "+ Nuovo
      Incontro" (dialog nome+note, auto-apre l'incontro appena creato). **Self-contained per il routing**: gestisce
      da sola lo stato "lista" vs "incontro aperto" al proprio interno (nuovo stato `_open_encounter_id`, innesta
      `MasterEncounterView` quando valorizzato) — nessuna modifica a `master_view.py`, che la istanzia già senza
      argomenti fin dal Task #3 (stesso principio già usato lì per il cambio tab interno).
      **`MasterEncounterView`** (`ui/views/master/master_encounter_view.py`, nuovo): header (torna alla lista, nome
      incontro, round corrente, "Difficoltà", "Prossimo Turno" — `master_repo.advance_turn()` — "Termina Incontro"
      — `master_repo.archive_encounter()`); lista combattenti ordinata per iniziativa (già ordinata da
      `get_encounter_members_resolved()`), card con badge iniziativa cliccabile (dialog modifica), icona/colore per
      tipo (PG/NPC/adhoc), PF con −/+ per npc/adhoc (mai per `kind="character"`, mostrato come testo di sola
      lettura "PF gestiti dal giocatore" — la stessa regola "il Master non scrive mai sugli HP dei PG" già
      stabilita nel design), badge PE se presente, pulsante rimuovi (`remove_member()`, soft-delete — il
      combattente resta nello storico); "+ Aggiungi Combattente" con le 4 scelte del design (Personaggio Giocante —
      dropdown da `character_repo.get_all()`, esclude chi è già nell'incontro; NPC dalla Rubrica — dropdown da
      `master_repo.get_npcs()`, con quantità per aggiungere più copie con nome numerato "Goblin 1/2/3"; Mostro dal
      Bestiario — riusa `show_monster_picker()`/`load_monsters()` del refactoring Task #1, con quantità e un
      checkbox opzionale "Salva anche in Rubrica NPC" via `create_npc_from_monster()`; Creazione Rapida — form
      manuale nome/CA/PF/PE/iniziativa). Dialog "Difficoltà" (`_on_difficulty_click`): calcola i livelli di gruppo
      dai membri `kind="character"` attivi (letti live da `character_repo.get_by_id()`, mai una copia cachata) più
      eventuali "PG fantasma" aggiungibili/rimovibili solo nel dialog stesso (mai persistiti — per pianificare con
      personaggi non ancora seduti al tavolo) e i PE dei membri `kind in ("npc","adhoc")`, richiama
      `calculate_difficulty()` e mostra il risultato con un badge colorato per categoria
      (Trascurabile/Facile/Medio/Difficile/Letale) più il dettaglio del calcolo (PE totale × moltiplicatore = PE
      modificato, soglie di gruppo).
      **Verificato** con una batteria di test end-to-end (DB temporaneo isolato via `tempfile.mkdtemp()`+`HOME`
      separato, mai il DB reale di Davide; `FakePage` minimale + scansione ricorsiva dell'albero controlli per
      pilotare i veri dialog Flet, stesso pattern già consolidato nel progetto): esempio calcolato a mano dal
      manuale stesso (bugbear 200 PE + 3 hobgoblin 100 PE ciascuno, gruppo di tre PG di 3° livello + uno di 2°
      livello → PE modificato 1000 → "difficile", combacia esattamente); tutti i casi limite del moltiplicatore
      (gruppo <3 con 1 mostro →×1,5, con 15+ mostri →×5; gruppo ≥6 con 1 mostro →×0,5, con 2 mostri →×1); 0 mostri
      →"trascurabile"; 0 personaggi →"indeterminato"; clamp dei livelli fuori 1-20. Flusso UI end-to-end completo
      su un incontro reale: creazione incontro, aggiunta di un PG (iniziativa impostata correttamente), aggiunta di
      3× lo stesso NPC dalla rubrica (nomi numerati "Goblin Esploratore 1/2/3", CA/PF/PE ereditati correttamente
      dalla rubrica), aggiunta di un mostro adhoc (Creazione Rapida), ordinamento per iniziativa decrescente
      confermato su tutti e 5 i combattenti; modifica PF (−/+ con clamp a 0), modifica iniziativa via dialog;
      avanzamento turno con wrap corretto e incremento di round; rimozione di un membro (soft-delete: sparisce
      dalla lista attiva ma resta nella query grezza non filtrata); apertura del dialog Difficoltà senza eccezioni
      con i dati reali dell'incontro; navigazione `MasterEncounterListView` lista↔incontro (apri/chiudi) e
      creazione di un nuovo incontro con auto-apertura. `python3 -m py_compile`/`pyflakes` puliti su tutti i file
      toccati/nuovi; `python3 -m compileall` sull'intero albero sorgente (esclusa `build/`) — 0 errori.
  - [x] **Sezione Master (4) — Calcolatore Difficoltà Incontro** ✅ (2026-07-24, implementato insieme al punto 1-3
    sopra, stesso `core/encounter_calculator.py`) — vedi il changelog completo appena sopra per dati
    verificati/metodo/test. `master_section_design.md` sezione "4." confermava già che nessuna nuova tabella DB
    fosse necessaria (calcolo a runtime) — l'unica aggiunta di schema è stata il campo `xp` su
    `master_npcs`/`master_encounter_members`, per lo stesso motivo spiegato sopra.
  - [x] **Sezione Master (5) — Note di Campagna del Master** ✅ (2026-07-24) — nessuna fonte DMG coinvolta, puro
    strumento organizzativo (design già chiaro dalla sessione precedente, `master_section_design.md` sezione "5.").
      **Schema** (`data/database.py`): nuova `master_campaign_notes` (id, category, name, description, status,
      tags, `linked_npc_id TEXT REFERENCES master_npcs(id) ON DELETE SET NULL`, created_at, updated_at) — stessa
      forma di `campaign_notes`/`DiaryView` già esistente, ma **senza** `character_id`: indipendente da ogni
      personaggio, vive solo nella Sezione Master. Tabella nuova (mai esistita prima), quindi nessuna
      `_add_column()` di migrazione necessaria — solo `CREATE TABLE IF NOT EXISTS` in `_create_tables()`, applicato
      sia a installazioni nuove sia esistenti alla prossima `init_db()`. Indice su `category`. 8 categorie: le 6
      già condivise con `campaign_notes` (`"npc"`/`"npc_todo"`/`"place"`/`"place_todo"`/`"quest"`/`"faction"`) + 2
      nuove (`"event"`, `"secret"`).
      **`data/models.py`**: nuovo dataclass `MasterCampaignNote` (mirror di `CampaignNote` meno `character_id`, più `linked_npc_id: str = ""`).
      **`data/repositories/master_repo.py`**: nuove `get_master_campaign_notes(category="")` (filtro esatto
      opzionale, altrimenti ordina per categoria poi data), `get_master_campaign_note_by_id()`,
      `create_master_campaign_note()`, `update_master_campaign_note()`, `delete_master_campaign_note()` — stesso
      pattern try/except+logger.error già in uso in tutto il modulo, nomi distinti (prefisso `master_`) per non
      collidere con gli omonimi per-personaggio già esistenti in `character_repo.py`.
      **`ui/views/master/master_notes_view.py`** (nuovo): `MasterNotesView`, layout a due pannelli — mirror quasi
      1:1 di `DiaryView` (letta per intero prima di scrivere questo file) ma senza la tab "Cronaca" (quella resta
      per-personaggio, backed da `diary_entries`, non pertinente qui) e senza `character_id` in nessun punto.
      Pannello sinistro (200px): 8 categorie cliccabili con badge contatore + lista voci della categoria attiva,
      memoria dell'ultima voce vista per categoria. Pannello destro: pagina di lettura stile pergamena (nome, badge
      stato colorato, descrizione, PNG collegato se presente, tag) con azioni Modifica/Elimina, oppure form di
      modifica inline (nome, stato — dropdown per categoria da `STATUS_OPTIONS`, PNG collegato — dropdown da
      `master_repo.get_npcs()` con opzione "— nessuno —", tag, descrizione). Dialog "Aggiungi" con gli stessi
      campi. `STATUS_OPTIONS` estende quello di `DiaryView` con due nuove liste per `"event"` (pianificato/in
      corso/concluso) e `"secret"` (nascosto/parzialmente svelato/svelato) — scelte organizzative, non regolamento.
      **`ui/views/master/master_view.py`**: nuova terza tab `{"key": "notes", "label": "Note di Campagna", "icon":
      MENU_BOOK_OUTLINED}` in `_TABS`, nuovo ramo in `_get_tab_content()` (stesso pattern `try: import ... / except
      ImportError: placeholder` già in uso per le altre 2 tab).
      **Verificato** con una batteria di test end-to-end (DB temporaneo isolato via `tempfile.mkdtemp()`+`HOME`
      separato, mai il DB reale di Davide; `FakePage` minimale + scansione ricorsiva dell'albero controlli per
      pilotare i veri dialog Flet — stesso pattern già consolidato per Task #4/#5): CRUD completo a livello
      repository (creazione con/senza `linked_npc_id`, lettura filtrata per categoria e non filtrata, aggiornamento
      — incluso azzerare `linked_npc_id` passando stringa vuota —, eliminazione); verificato esplicitamente `ON
      DELETE SET NULL` — una nota collegata a un NPC sopravvive alla cancellazione di quell'NPC dalla rubrica, con
      `linked_npc_id` ripulito a `NULL` invece di far sparire la nota o sollevare un errore di FK; flusso UI
      end-to-end pilotando i veri controlli Flet: cambio categoria, creazione di una nuova nota via dialog
      (categoria "secret", inclusi i campi nome/descrizione), modifica inline (cambio stato + descrizione),
      eliminazione con dialog di conferma; ri-istanziazione della vista (simula riapertura tab) senza eccezioni;
      wiring della terza tab in `MasterView` verificato costruendo la vista con `active_tab="notes"`. **Bug del
      test stesso, non del codice applicativo, trovato e corretto durante la scrittura**: `ft.ElevatedButton` in
      Flet 0.85.3 non ha un attributo `.text` leggibile (il testo passato come primo argomento posizionale è
      salvato in `.content`, non in una proprietà `.text` — verificato con `dir()`/instanziazione diretta) — il
      test iniziale cercava `.text == "Crea"`/`"Elimina"` e falliva con `AttributeError`; corretto cercando
      `.content == "Crea"`/`"Elimina"`. `python3 -m py_compile`/`pyflakes` puliti su tutti i file toccati/nuovi
      (zero rumore, questi file non usano `from config.settings import *`); `python3 -m compileall` sull'intero
      albero sorgente (esclusa `build/`) — 0 errori.
  - [x] **Sezione Master (6) — Generatore Tesori Casuali** ✅ (2026-07-24) — dati trascritti visivamente da "ED 5.0
    Guida del Dungeon Master.pdf" (`pdftoppm`, mai `pdftotext`/OCR per il contenuto — usato solo per navigazione,
    tramite un dump di controllo `/tmp/dmg_full.txt` mai letto come fonte del contenuto), Capitolo 7 "Tesori"
    p.133-149. **Formula di conversione pagina scoperta per questo PDF**: `pagina_stampata = split_index_pdftotext
    + 12` (verificata incrociando i numeri di pagina visibili nei footer delle immagini renderizzate contro la
    posizione dei form-feed `\f` nel dump di navigazione) — utile per future letture mirate nello stesso file.
    **Dati trascritti** (tutti verificati leggendo le immagini di pagina, nessun valore indovinato): 4 tabelle
    "Tesoro Singolo" per fascia di CR (0-4/5-10/11-16/17+, p.136 — righe d100→valuta/e, alcune fasce alte concedono
    due valute nella stessa riga); 4 tabelle "Cumulo di Tesori" per fascia di CR (p.137-139 — formula di monete
    fissa sempre assegnata per intero + un tiro d100 aggiuntivo la cui fascia di valore gemme/oggetti d'arte CAMBIA
    riga per riga, non è fissa per l'intera tabella, e la cui parte "oggetti magici" può indicare più di una
    Tabella A-I nella stessa riga con conteggi di tiro come "1d6 volte"/"1 volta"); 6 tabelle Gemme per fascia di
    valore (10/50/100/500/1.000/5.000 mo, p.134, nomi con descrizione cromatica completa); 5 tabelle Oggetti d'Arte
    per fascia di valore (25/250/750/2.500/7.500 mo, p.134-135); 9 Tabelle degli Oggetti Magici A-I (p.143-149,
    solo nome+range di tiro — **non** la descrizione completa, che appartiene al Compendio Oggetti Magici, punto 7,
    deliberatamente rimandato — comprese le 2 sotto-tabelle annidate: G "Statuina del potere meraviglioso" con un
    d8, I "Armatura magica" con un d12).
    **`data/game_data/treasure_tables.json`** (nuovo, scritto via script Python usa-e-getta poi rimosso, stesso
    pattern già collaudato per i batch del bestiario): schema deliberatamente diverso dalla bozza iniziale del
    design doc su 2 punti, corretti per fedeltà ai dati reali — `art_by_value` è una chiave separata da
    `gems_by_value` (fasce di valore diverse tra le due categorie) e ogni riga d100 del Cumulo ha la propria coppia
    tipo/valore per gemme-o-arte (`{"type","value","dice","avg"}`), non una fascia fissa per l'intera tabella di
    CR. Ogni riga di "drops"/"coins" è `{"currency","dice","mult","avg"}` (valuta = mr/ma/me/mo/mp, stessa
    convenzione già in uso in tutto il progetto per `Currency`); ogni riga del Cumulo è `{"range":[lo,hi],
    "gems_art": null|{...}, "magic": [{"table","rolls"}, ...]}`. Copertura d100 di ogni tabella verificata a
    100/100 con uno script di controllo (nessun buco/sovrapposizione).
    **`GameDataLoader`**: nuovo `_ensure_treasure()` (stesso pattern lazy-load-e-cache di `_ensure_feats()`) + 6
    getter a sola lettura: `get_treasure_tables()`, `get_individual_treasure_table(cr_band)`,
    `get_hoard_treasure_table(cr_band)`, `get_gems_by_value(value)`, `get_art_by_value(value)`,
    `get_magic_item_table(letter)`.
    **`core/treasure_generator.py`** (nuovo modulo puro, nessuna dipendenza Flet, stesso principio di
    `wizard_engine.py`/`level_manager.py`/`equipment_manager.py`/`weapon_calculator.py`/`encounter_calculator.py`):
    `roll_dice(formula)` (parsa "NdM" o un intero puro fisso, per le entry "rolls":"1" del Cumulo — un oggetto
    garantito, non un vero tiro), `generate_individual_treasure(cr_band)`, `generate_hoard_treasure(cr_band)`
    (monete fisse sempre incluse per intero + risoluzione della riga d100 tirata, con
    `_roll_gems_or_art()`/`_roll_magic_items()`/`_roll_magic_item_row()` — quest'ultima risolve automaticamente
    l'eventuale sotto-tabella G/I), `roll_trinket()` (hook Oggetti Insoliti, 1d100 su
    `game_data.get_trinket_by_roll()`), `format_coins()`.
    **UI — `ui/views/master/master_treasure_dialog.py`** (nuovo) + bottone "Genera Tesoro" nell'header di
    `MasterView` (`_open_treasure_dialog()`): dialog con `RadioGroup` Tesoro Singolo/Cumulo di Tesori, Dropdown
    fascia CR, pulsanti "Tira"/"+ Cimelio" (deciso con Davide il 2026-07-24: dentro questo dialog, non una voce di
    navigazione a sé), area risultato (monete, gemme/oggetti d'arte estratti, nomi oggetti magici, cimelio),
    Dropdown "Aggiungi all'inventario di..." (da `character_repo.get_all()`, disabilitato se non esistono
    personaggi) + pulsante che **riusa direttamente**
    `character_repo.create_inventory_item()`/`get_currencies()`/`update_currencies()` (nessuna nuova funzione di
    scrittura personaggio, come da istruzione del design doc) — le valute si sommano a quelle già possedute (non le
    sovrascrivono), i nomi ripetuti (es. più copie della stessa gemma) vengono raggruppati con
    `collections.Counter` in un'unica riga inventario con `quantity` corretta invece di N righe duplicate; gli
    oggetti magici sono salvati con `category="magic"` e una nota che avverte che la descrizione completa non è
    ancora disponibile (in attesa del Compendio, punto 7).
    **Verificato** con una batteria di test end-to-end (DB temporaneo isolato via `tempfile.mkdtemp()`+`HOME`
    separato, mai il DB reale di Davide; `FakePage` minimale + pilotaggio diretto dei controlli Flet reali del
    dialog, stesso pattern già consolidato nel progetto): Tesoro Singolo su tutte e 4 le fasce di CR (monete
    plausibili, incluse le fasce con 2 valute insieme); Cumulo di Tesori con retry-seed fino a un tiro che produce
    sia gemme/oggetti d'arte sia un oggetto magico (verificato il caso "niente" quando la riga d100 è vuota,
    coerente col manuale); "+ Cimelio" aggiunge la sezione dedicata al risultato mostrato; "Aggiungi
    all'inventario" verificato sia su Tesoro Singolo (valute sommate correttamente, cimelio salvato come oggetto)
    sia su Cumulo (valute sommate SOPRA quelle già presenti da un tiro precedente nello stesso test, oggetti
    raggruppati per nome con quantità corretta — es. 3 copie dello stesso oggetto d'arte in un'unica riga
    `quantity=3`); Dropdown/pulsante "Aggiungi all'inventario" correttamente disabilitati quando
    `character_repo.get_all()` non ritorna alcun personaggio. `python3 -m py_compile`/`pyflakes` puliti su tutti i
    file toccati (solo il rumore preesistente di `from config.settings import *`); `python3 -m compileall`
    sull'intero albero sorgente (esclusa `build/`) — 0 errori.
  - [x] **Sezione Master (8) — Generatore Trappole** ✅ (2026-07-24) — dati trascritti visivamente da "Guida del
    Dungeon Master - 5a e - AA.VV_.pdf" (`pdftoppm`, mai `pdftotext`/OCR per il contenuto — usato solo per
    navigazione, tramite il dump di controllo `/tmp/dmg_full.txt` già esistente da un batch precedente), Capitolo 5
    "Ambienti delle Avventure", sezione "Trappole" (pag.120-124, mappatura pagina stampata↔indice PDF confermata
    leggendo i footer delle immagini renderizzate). **Lettura completata fino in fondo alla sezione**: la pagina
    successiva (124 stampata) è un'illustrazione a piena pagina senza testo e il Capitolo 6 "Tra le Avventure"
    inizia subito dopo (125 stampata) — confermato che l'elenco alfabetico degli esempi di trappole nominate si
    ferma esattamente alla lettera S, nessuna voce oltre "Statua del Soffio di Fuoco" esiste in questa sezione del
    manuale (la stima "5-10 voci residue" del design doc si è rivelata di 5, tutte trovate: Fossa con Spuntoni,
    Rete in Caduta, Sfera Annientatrice, Sfera Rotolante — già nota — e Statua del Soffio di Fuoco).
    **Dati trascritti** (tutti verificati leggendo le immagini di pagina, nessun valore indovinato): meccaniche
    generali (innescare/individuare/disinnescare una trappola, trappole complesse) lette per intero ma non
    trascritte in JSON (sono prosa di riferimento per il DM, non dati strutturati); tabella "Bonus di Attacco e CD
    dei Tiri Salvezza delle Trappole" (3 righe, pag.121); tabella "Gravità dei Danni per Livello" (4 fasce di
    livello × 3 gravità, pag.121); le 8 voci di "Esempi di Trappole" in ordine alfabetico (pag.121-124) con testo
    integrale: Ago Avvelenato (meccanica), Crollo del Tetto (meccanica), Dardi Avvelenati (meccanica), Fosse
    (meccanica — unica voce con 4 varianti annidate: Fossa Semplice/Nascosta/Richiudibile/con Spuntoni, esattamente
    come il manuale le presenta sotto un'unica intestazione "FOSSE"), Rete in Caduta (meccanica), Sfera
    Annientatrice (magica), Sfera Rotolante (meccanica), Statua del Soffio di Fuoco (magica).
    **`data/game_data/traps.json`** (nuovo): schema identico alla bozza già presente nel design doc —
    `danger_table` (3 righe `{"level","save_dc","attack_bonus"}`), `damage_by_level` (4 righe
    `{"char_level_range","imprevisto","pericoloso","letale"}`, dado come stringa "NdM"), `example_traps` (8 voci
    `{"name","type":"meccanica"|"magica","description"}`, con un campo aggiuntivo
    `"variants":[{"name","description"}]` presente solo per "Fosse" — unica voce del manuale con sotto-varianti
    nominate, stesso principio di fedeltà al testo già seguito altrove nel progetto per evitare di appiattire una
    struttura annidata in un'unica stringa).
    **`GameDataLoader`**: nuovo `_ensure_traps()` (stesso pattern lazy-load-e-cache di `_ensure_treasure()`) + 6
    getter a sola lettura: `get_traps_data()`, `get_trap_danger_table()`, `get_trap_damage_table()`,
    `get_trap_damage_dice(char_level, severity)` (risolve la fascia di livello corretta), `get_example_traps()`,
    `get_example_trap(name)`.
    **`core/trap_generator.py`** (nuovo modulo puro, nessuna dipendenza Flet, stesso principio di
    `wizard_engine.py`/`level_manager.py`/`equipment_manager.py`/`weapon_calculator.py`/`encounter_calculator.py`/`treasure_generator.py`):
    `suggest_trap_stats(char_level, severity)` (risolve CD/bonus attacco/dado danno dalle 2 tabelle per una
    trappola custom), `roll_trap_damage(char_level, severity)` (tira effettivamente il dado suggerito),
    `roll_dice(formula)` (stesso helper già in uso in `treasure_generator.py`, duplicato qui per mantenere il
    modulo autonomo, stesso principio di indipendenza già seguito dagli altri moduli `core/`).
    **UI — `ui/views/master/master_traps_dialog.py`** (nuovo) + bottone "Genera Trappola" nell'header di
    `MasterView` (`_open_traps_dialog()`, stesso pattern lazy-import già usato per "Genera Tesoro"): dialog con 2
    modalità a tab interne — **Suggerisci** (Dropdown livello PG 1-20, `RadioGroup` gravità
    Imprevisto/Pericoloso/Letale, pulsanti "Suggerisci"/"Tira Danno") e **Sfoglia Esempi** (card cliccabili per le
    8 trappole nominate, stesso stile card-e-dialog già in uso in `FeatsView` — click apre un `AlertDialog` con
    tipo+testo completo, incluse le 4 varianti annidate per "Fosse", mostrate in sequenza con intestazione
    propria).
    **Verificato** con una batteria di test end-to-end (`FakePage` minimale + pilotaggio diretto dei controlli Flet
    reali del dialog, stesso pattern già consolidato nel progetto — DB temporaneo isolato via
    `tempfile.mkdtemp()`+`HOME` separato per il test di wiring in `MasterView`, mai il DB reale di Davide):
    `suggest_trap_stats()`/`get_trap_damage_dice()` testati su tutti gli 8 livelli-chiave (1/4/5/10/11/16/17/20) ×
    tutte e 3 le gravità — CD/bonus attacco/dado danno combacianti esattamente con le 2 tabelle del manuale in ogni
    combinazione; modalità Suggerisci pilotata end-to-end (Dropdown livello 5 + RadioGroup "letale" → click
    "Suggerisci" → risultato "CD 16-20, Bonus +9 a +12, Dado 10d10" — confermato contro la tabella; click "Tira
    Danno" → riga "Danno tirato: N" aggiunta); modalità Sfoglia Esempi pilotata end-to-end (8 card presenti coi
    nomi attesi, click sulla card "Fosse" apre il dialog di dettaglio con tutte e 4 le varianti annidate visibili
    per intero, incluso il testo integrale di ciascuna); cambio tab avanti e indietro verificato senza eccezioni;
    wiring del bottone "Genera Trappola" in `MasterView` verificato con `unittest.mock.patch.object` sulla property
    `page` (bypassa il vincolo read-only di Flet 0.85.3 su `Control.page` per un controllo mai montato su una vera
    pagina) — click apre correttamente il dialog "Generatore Trappole". `python3 -m py_compile`/`pyflakes` puliti
    su tutti i file toccati (zero rumore, nessuno di questi file usa `from config.settings import *`); `python3 -m
    compileall` sull'intero albero sorgente (esclusa `build/`) — 0 errori.
  - [x] **Sezione Master (9) — Riferimento Malattie/Veleni/Follia** ✅ (2026-07-24) — dati trascritti visivamente da
    "Guida del Dungeon Master - 5a e - AA.VV_.pdf" (`pdftoppm -r 150`, mai `pdftotext`/OCR per il contenuto),
    Capitolo 8 "Condurre il Gioco", sezioni "Malattie" (pag.256), "Veleni" (pag.257-258) e "Follia" (pag.258-260).
    **Localizzazione via dump di navigazione, poi ri-verifica visiva obbligatoria**: il documento di design
    (`master_section_design.md`, sezione "9.") conteneva già un'estrazione di questo stesso contenuto ottenuta da
    un dump testuale (`pdftotext`, usato in una sessione precedente solo per localizzare la sezione — mai per il
    contenuto) — coerente con la regola critica del progetto, quell'estrazione NON è stata presa per buona: è stata
    usata solo per stringere il range di pagine (ricerca di `["MALATTIE","Epidemia Fognaria","VELENI","Essenza di
    etere","FOLLIA","Follia Temporanea","Follia Duratura","Follia Indeterminata"]` sul dump `/tmp/dmg_full.txt`,
    cluster trovato a pag.256-260), poi ogni pagina di quel range è stata renderizzata e letta visivamente da zero
    prima di scrivere qualunque dato — la ri-verifica ha confermato che l'estrazione del design doc era già
    corretta (nessuna discrepanza), ma la conferma indipendente restava comunque necessaria prima di fidarsene,
    esattamente come richiesto dalla regola del progetto.
    **Confermato l'ambito esatto della sezione, nessun'altra voce oltre queste**: 3 malattie di esempio (Epidemia
    Fognaria, Febbre da Gallina, Vista Putrefatta — il capitolo non ne nomina altre), 14 veleni nella tabella
    "Veleni" (con prezzo di una dose + descrizione meccanica completa per ciascuno, più i testi introduttivi sui 4
    tipi di veleno — Contatto/Ferimento/Inalazione/Ingestione — e le sezioni "Acquistare i Veleni"/"Fabbricare ed
    Estrarre i Veleni"), 3 tabelle d100 di Follia (Temporanea 10 righe/copertura 1-100, Duratura 12 righe/copertura
    1-100, Indeterminata 12 righe/copertura 1-100 — tutte e 3 verificate senza buchi né sovrapposizioni con uno
    script di controllo) più i testi di contesto "Impazzire"/"Effetti della Follia"/"Curare la Follia".
    **`data/game_data/diseases_poisons_madness.json`** (nuovo): `diseases` (3 voci `{"name","description"}`, testo
    integrale), `poisons` (14 voci `{"name","type","price","description"}`),
    `poison_types_intro`/`poison_acquiring`/`poison_crafting` (testi di contesto, stringhe),
    `madness_intro`/`madness_inducing`/`madness_effects_intro`/`madness_curing` (testi di contesto),
    `madness_tables` (dict `"temporanea"|"duratura"|"indeterminata"` →
    `{"label","duration","entries":[{"range","effect"}]}`).
    **`GameDataLoader`**: nuovo `_ensure_health_hazards()` (stesso pattern lazy-load-e-cache di
    `_ensure_traps()`/`_ensure_treasure()`) + 13 getter a sola lettura: `get_health_hazards_data()`,
    `get_diseases()`/`get_disease(name)`, `get_poisons()`/`get_poison(name)`,
    `get_poison_types_intro()`/`get_poison_acquiring_text()`/`get_poison_crafting_text()`,
    `get_madness_intro_text()`/`get_madness_inducing_text()`/`get_madness_effects_intro_text()`/`get_madness_curing_text()`,
    `get_madness_table(kind)`, `roll_madness_effect(kind)` (tira 1d100 e risolve la riga corrispondente — **nessun
    modulo `core/` dedicato**: a differenza di `trap_generator.py`/`treasure_generator.py`, che combinano più
    tabelle e un calcolo, qui è un singolo lookup su un tiro 1d100, motivato nel docstring del metodo stesso).
    **UI — `ui/views/master/master_health_hazards_dialog.py`** (nuovo) + bottone "Malattie e Veleni" nell'header di
    `MasterView` (`_open_health_hazards_dialog()`, stesso pattern lazy-import già usato per "Genera Tesoro"/"Genera
    Trappola"): dialog puramente di consultazione (nessuna scrittura sui personaggi, a differenza del Generatore
    Tesori — qui non c'è nulla da "aggiungere all'inventario", sono regole/effetti che il Master applica a mano)
    con 3 sotto-tab — **Malattie** (card cliccabili, dialog con testo integrale), **Veleni** (card con tipo/prezzo
    + dialog con meccanica completa, più 3 pulsanti "Tipi di Veleno"/"Acquistare"/"Fabbricare" per i testi di
    contesto), **Follia** (Dropdown scelta tabella + pulsante "Tira 1d100" che mostra tiro+effetto risultante, più
    3 pulsanti "Impazzire"/"Effetti"/"Curare" per i testi di contesto).
    **Verificato** con una batteria di test end-to-end (`FakePage` minimale + pilotaggio diretto dei controlli Flet
    reali del dialog, stesso pattern già consolidato nel progetto — DB temporaneo isolato per il test di wiring in
    `MasterView`, mai il DB reale di Davide): tutti i 13 getter testati singolarmente (3 malattie, 14 veleni con
    tipo/prezzo corretti, testi di contesto non vuoti); `roll_madness_effect()` testato con 300 tiri per ciascuna
    delle 3 tabelle (range sempre 1-100, copertura ampia, nessun tiro che ritorna `None` per una tabella valida,
    `None` corretto per una chiave inesistente); dialog pilotato end-to-end: tab "Malattie" di default mostra tutte
    e 3 le card coi nomi attesi; cambio tab "Veleni" mostra tutte e 14 le card, click su "Veleno Drow" apre il
    dettaglio con "CD 13"/testo su "drow" presenti, chiusura del dettaglio torna al dialog principale; i 3 pulsanti
    info di Veleni ("Tipi di Veleno"/"Acquistare"/"Fabbricare") aprono ciascuno un dialog dedicato; cambio tab
    "Follia" mostra il Dropdown (default "temporanea") e il pulsante "Tira 1d100" — click produce un risultato
    "Tiro: N (intervallo ...)" + testo effetto; cambio Dropdown a "duratura" azzera il risultato precedente (mostra
    il placeholder "Premi «Tira 1d100»...") prima di un nuovo tiro; i 3 pulsanti info di Follia
    ("Impazzire"/"Effetti"/"Curare") aprono ciascuno un dialog dedicato; wiring del bottone "Malattie e Veleni" in
    `MasterView` verificato con `unittest.mock.patch.object` sulla property `page` (bypassa il vincolo read-only di
    Flet 0.85.3 su `Control.page` per un controllo mai montato su una vera pagina) — click apre correttamente il
    dialog "Malattie, Veleni e Follia". `python3 -m py_compile`/`pyflakes` puliti su tutti i file toccati (solo il
    rumore preesistente di `from config.settings import *` in `master_view.py`, già noto); `python3 -m compileall`
    sull'intero albero sorgente (esclusa `build/`) — 0 errori.
  - [x] **Sezione Master (10) — Generatore Incontri Casuali per Ambiente (v1 ridotta)** ✅ (2026-07-24) —
    implementata solo la strada 1 già raccomandata dal design doc (`master_section_design.md` sezione "10."): la
    DMG non ha un dataset ambiente→mostro pronto per tutti i terreni (gap reale, confermato leggendo per intero la
    sezione "Creare le Tabelle degli Incontri Casuali", Cap.3 — solo guida metodologica in prosa + un singolo
    esempio completamente lavorato), quindi trascritto SOLO l'esempio "Incontri nella Foresta Silvana" (Cap.3 DMG,
    pagina fisica PDF 86 / pagina stampata 87 — stesso scarto di un'unità già confermato nel resto di questa
    sessione) come tabella dimostrativa. Il tagging sistematico dei 444 mostri per ambiente resta un'estensione
    futura separata, esplicitamente NON iniziata in questo task (nessuna conversazione di scope dedicata avvenuta,
    coerente con l'istruzione originale).
    **Lettura della tabella**: `pdftoppm -r 150` per la lettura iniziale, poi crop mirati a 300dpi (`pdftoppm -r
    300` + ritaglio PIL) per ri-verificare ogni riga con precisione, incluso un tentativo iniziale che ha reso per
    errore la pagina fisica sbagliata (87 invece di 86 — stesso scarto footer/pagina-fisica già noto,
    momentaneamente dimenticato) e autocorretto non appena l'illustrazione non corrispondeva. La tabella usa un
    tiro **1d12+1d8** (range 2-20, 19 righe), non un d20 piatto — meccanica a curva che privilegia i risultati
    centrali, diversa da tutti i lookup d100 già usati altrove nel progetto (Trappole/Follia/Tesori). Confermato
    con certezza, riga per riga incluse le 2 letture ad alta risoluzione dedicate, un refuso reale già presente nel
    manuale italiano stampato: la riga 4 recita testualmente **"1d4 gnoll and 2d4 iene"** — la parola inglese "and"
    al posto di "e" è stampata così com'è nel PHB IT, non un'invenzione né un errore di lettura da parte mia —
    trascritta verbatim con una nota esplicativa dedicata nel campo `note`, senza "correggerla".
    **`data/game_data/forest_encounters.json`** (nuovo): `roll_note` ("1d12 + 1d8 (range 2-20)"),
    `environments.foresta_silvana` → `{"label","entries":[{"roll","text","creatures":[...],"note"?}, ...]}` — 19
    righe (roll 2-20, copertura verificata senza buchi/duplicati), `creatures` elenca i nomi (già verificati contro
    il manuale) delle creature in **grassetto** nel testo originale, che nel manuale indicano un rimando a una
    scheda del Manuale dei Mostri — usato per il link opzionale "Vedi scheda".
    **`GameDataLoader`**: nuovo `_ensure_forest_encounters()` (stesso pattern lazy-load-e-cache già consolidato) +
    `get_forest_encounters_data()`, `get_environment_names()` (v1: solo `["foresta_silvana"]`),
    `get_environment_table(env_key)`, `roll_environment_encounter(env_key)` (tira davvero 1d12+1d8, risolve la riga
    corrispondente, ritorna anche i due dadi singoli `d12`/`d8` per trasparenza — **nessun modulo `core/`
    dedicato**, stesso principio già motivato per `roll_madness_effect()`: un singolo lookup su una tabella già
    pronta non giustifica un modulo a parte).
    **UI — `ui/views/master/master_forest_encounters_dialog.py`** (nuovo) + bottone "Incontri per Ambiente"
    nell'header di `MasterView` (`_open_forest_encounters_dialog()`, stesso pattern lazy-import di "Genera
    Tesoro"/"Genera Trappola"/"Malattie e Veleni"): Dropdown scelta ambiente (v1: solo "Foresta Silvana") →
    pulsante "Tira 1d12+1d8" → risultato con testo completo + nota se presente + un pulsante "Vedi scheda: {nome}"
    per ciascuna creatura del risultato che risolve nel bestiario (`_resolve_creature()`, ricerca case-insensitive
    su `ui.components.monster_picker.load_monsters()`, `None` senza errori se non risolve — nessuna creatura di
    questa tabella è risultata irrisolta, incluse le due voci NPC "Esploratore"/"Druido" dell'Appendice B, già
    presenti in `monsters.json`), aperto con lo stesso `show_stat_block_dialog()` condiviso già in uso per Forma
    Selvatica/Evocazioni/Rubrica NPC.
    **Verificato** con una batteria di test end-to-end (mai il DB reale di Davide): tutti i 19 getter/entry
    validati (copertura 2-20 esatta, nessun buco/duplicato); 5000 tiri simulati di `roll_environment_encounter()` —
    `d12+d8` sempre uguale a `roll`, range sempre 2-20, ogni valore raggiunto, testo restituito sempre coerente con
    la riga JSON corrispondente, curva a campana confermata (l'11 è comparso ~420 volte contro le ~49 di ciascun
    estremo 2/20); tentativo con chiave ambiente inesistente → `None` senza eccezioni; le 19 creature della tabella
    risolte al 100% contro `monsters.json` (zero nomi orfani); dialog pilotato end-to-end (`FakePage` + scansione
    ricorsiva dei controlli, stesso pattern consolidato): dropdown/pulsante presenti, placeholder iniziale
    corretto, un tiro produce "Tiro: N (d12=X + d8=Y)" + testo, il pulsante "Vedi scheda" (comparso e cliccato su
    un tiro reale, es. Orsogufo) apre correttamente un secondo dialog con lo stat block, la chiusura funziona;
    cambio Dropdown azzera il risultato precedente prima di un nuovo tiro; wiring del bottone in `MasterView`
    verificato con `unittest.mock.patch.object` sulla property `page` (stesso bypass già in uso per gli altri
    dialog Master). `python3 -m py_compile`/`pyflakes` puliti su tutti i file toccati (solo il rumore preesistente
    di `from config.settings import *`); `python3 -m compileall` sull'intero albero sorgente (esclusa `build/`) — 0
    errori.

    **Espansione a 4 ambienti (2026-07-26)** — Davide, usando il tool, ha notato che il Dropdown ambiente aveva
    un'unica voce ("Il tasto ambiente ha solo foresta silvana") e ha chiesto di affrontarlo subito ("si
    affrontiamolo adesso"). **La motivazione originale del 2026-07-24 era sbagliata**: quella sessione aveva
    concluso, dopo aver letto per intero SOLO la sezione metodologica "Creare le Tabelle degli Incontri Casuali"
    del Cap.3, che la DMG non contenesse altro materiale pronto oltre alla Foresta Silvana — conclusione che si è
    rivelata falsa non appena si è cercato con più attenzione: il **Cap.5 "Ambienti delle Avventure"** contiene
    altre 3 tabelle complete con la stessa identica meccanica 1d12+1d8, mai notate nella sessione precedente perché
    quella lettura si era fermata al solo Cap.3.
    **Localizzazione**: `pdftotext -layout` sull'intero PDF, usato SOLO per navigazione (mai per il contenuto,
    coerente con la regola critica del progetto) — ricerca delle stringhe `["Incontri Urbani Casuali", "Incontri
    Casuali Sott'Acqua", "Incontri Casuali in Mare"]` su un dump usa-e-getta, che ha isolato il range di pagine PDF
    113-118. **Scarto pagina fisica/stampata per questa sezione confermato empiricamente in +1** (`pdftoppm -r 150`
    su pag. 113 → piè di pagina "114" nell'immagine) — **diverso** dal +12 già noto per Tesori/Trappole/Malattie
    dello stesso PDF (sezione "Guida del Dungeon Master" più avanti nel libro): l'offset non è una costante del
    documento, va sempre riverificato per ogni sezione separatamente, mai assunto da un capitolo diverso già noto.
    **Lettura visiva pagina per pagina** (`pdftoppm -r 150`, mai `pdftotext`/OCR per il contenuto): pag.113
    (stampata 114) — tabella "Incontri Urbani Casuali" (19 righe) + inizio descrizioni; pag.114 (115) — solo
    illustrazione a piena pagina di un insediamento, nessun testo; pag.115 (116) — fine descrizioni Urbani +
    tabella completa "Incontri Casuali Sott'Acqua" (19 righe); pag.116 (117) — tabella "Distanza degli Incontri
    Sott'Acqua" (3 righe, prosa di regolamento non pertinente allo schema di questo file) + inizio prosa "Il
    Mare"/"Navigazione"; pag.117 (118) — tabella completa "Incontri Casuali in Mare" (16 righe distinte/19 valori
    di tiro tramite 4 intervalli combinati) + riquadro "Naufragi" (prosa, escluso) + inizio "Tempo Atmosferico in
    Mare" (rimanda a una tabella già nota altrove, nessun dato nuovo); pag.118 (119) — tabella statistiche
    "Imbarcazioni e Aeronavi" + sezione "In Cielo": **confermato il confine netto di fine sezione**, nessun'altra
    tabella 1d12+1d8 oltre questo punto.
    **Schema dato invariato** (`data/game_data/forest_encounters.json`): nessuna nuova chiave introdotta, solo 3
    nuovi oggetti dentro `environments` (`incontri_urbani`, `sott_acqua`, `in_mare`), ciascuno con lo stesso
    identico formato già in uso per `foresta_silvana` (`label`, `source`, `entries:
    [{"roll","text","creatures":[...],"note"?}]`).
    `GameDataLoader.get_environment_names()`/`get_environment_table()`/`roll_environment_encounter()` sono **già
    generici** dal 2026-07-24 (leggono le chiavi di `environments` a runtime) — **zero modifiche di codice**
    necessarie a `game_data_loader.py` o al dialog `master_forest_encounters_dialog.py` per il funzionamento: solo
    il docstring di modulo di quest'ultimo è stato aggiornato per riflettere i 4 ambienti invece di 1.
    **Decisioni di trascrizione**:
    - **"Incontri Urbani Casuali"** non ha nomi di creatura in **grassetto** nella tabella come le altre 3 — il
      rimando al bestiario compare invece in prosa dentro la descrizione di alcune voci ("si usano le statistiche
      del/della X contenute nel Manuale dei Mostri"). Il campo `creatures` valorizzato comunque per queste voci
      (Malvivente/Spia/Popolano, tutti presenti in `monsters.json`) per coerenza funzionale col resto del file (il
      pulsante "Vedi scheda" deve comparire ovunque sia sensato), non per estendere arbitrariamente la convenzione
      — nessun nome inventato, solo quelli esplicitamente citati nel testo.
    - **"Incontri Casuali in Mare"** presenta 4 righe a intervallo combinato (7-8, 9-10, 11-12, 13-14) invece di un
      valore singolo per riga di tiro — rappresentate come **coppie di voci JSON duplicate** (stesso
      `text`/`creatures`, un oggetto per ciascun valore intero dell'intervallo), scelta deliberata per restare
      compatibili al 100% con `roll_environment_encounter()` (che confronta sempre `roll == e["roll"]` su un
      singolo intero) **senza alcuna modifica di codice/schema** (niente nuovo campo tipo `roll_range`) —
      verificato che la copertura 2-20 risulta comunque esatta, senza buchi né doppioni percepibili dall'utente.
    - **"Drago di bronzo"** (citato sia in Sott'Acqua riga 18 sia in In Mare riga 3) è nominato dal manuale **senza
      specificare l'età** — `monsters.json` ha solo le 4 varianti d'età (Cucciolo/Giovane/Adulto/Antico), nessuna
      voce "Drago di Bronzo" nuda. Coerente con la regola "mai inventare, documenta l'ambiguità": il nome resta
      scritto esattamente come stampato, **nessuna età scelta a caso**, e il pulsante "Vedi scheda" per queste 2
      voci semplicemente non compare (comportamento già esistente e corretto di `_resolve_creature()`: `None` senza
      errori se il nome non risolve) — annotato con un campo `"note"` dedicato su entrambe le voci JSON per rendere
      esplicita la scelta a chiunque legga il dato in futuro, non solo a chi legge questo changelog.
    **Verificato** con una nuova batteria di test end-to-end (mai il DB reale di Davide, stesso rigore già
    applicato il 2026-07-24): copertura 2-20 esatta e senza buchi/duplicati su tutti e 4 gli ambienti (19 valori di
    tiro raggiungibili ciascuno, incluso "In Mare" nonostante le righe a intervallo combinato); cross-check di
    tutti i nomi creatura citati nelle 3 nuove tabelle contro `monsters.json` — **44 risolti su 46**, i soli 2 non
    risolti sono le due voci "Drago di Bronzo" già documentate come ambiguità intenzionale (nessun altro nome
    orfano); 3000 tiri simulati di `roll_environment_encounter()` per ciascuno dei 4 ambienti (12.000 tiri totali)
    — `d12+d8` sempre uguale a `roll`, range sempre 2-20, ogni valore raggiunto per tutti e 4; dialog pilotato
    end-to-end (`FakePage` + scansione ricorsiva dei controlli, stesso pattern consolidato) su tutti e 4 gli
    ambienti selezionabili dal Dropdown, incluso un tiro reale su "Incontri Urbani" (pulsante "Vedi scheda:
    Malvivente" comparso e cliccato con successo) e un tiro su "Sott'Acqua"/"In Mare" che produce la voce "Drago di
    bronzo" (confermato che **nessun** pulsante "Vedi scheda" compare per quella voce specifica, il resto del
    risultato — testo e nota — si mostra comunque correttamente); cambio Dropdown tra i 4 ambienti azzera
    correttamente il risultato precedente. `python3 -m py_compile`/`pyflakes` puliti su
    `data/game_data/game_data_loader.py` (invariato) e `ui/views/master/master_forest_encounters_dialog.py` (solo
    il docstring toccato); `python3 -m compileall -q -x '^\./build/' .` sull'intero albero sorgente — 0 errori,
    nessuna regressione.
    **Con questo si chiudono tutti e 10 i punti della Sezione Master** (i 9 sopra + questo) — resta fuori scope,
    per scelta esplicita e documentata separatamente, solo il Compendio Oggetti Magici (punto 7 del design doc,
    progetto a parte su scala bestiario, mai iniziato).

  **Fuori scope per tutti i sotto-task sopra** (per restare fedeli alla richiesta senza sconfinare): nessuna
  scrittura del Master sugli HP dei PG (solo lettura); nessun collegamento con LAN party (dipende dal modulo
  `network/`, ancora vuoto, v2 separato); nessuna automazione per Azioni di Tana/Effetti Regionali dei mostri con
  tana (mostrabili in sola lettura, stesso dialog già esistente).

- [x] **Sezione Master (11) — Generatore Incontri Casuali (CR+Tema)** ✅ (2026-07-25) — nuovo strumento richiesto da
  Davide oltre ai 10 già completati sopra, insieme a Generatore Oggetti Magici e Generatore Rapido NPC (vedi voci
  dedicate). Requisito trasversale esplicito di Davide, valido per tutti e 3: *"La generazione deve essere fatta
  bene, l'app non deve generare sempre gli stessi personaggi o incontri o oggetti, deve essere uno strumento utile
  per il master"* — nessun seed fisso, varietà reale ad ogni generazione, verificata con test dedicati (vedi
  sotto).
  **Design confermato con Davide via `AskUserQuestion`** ("Modalità di calcolo del grado di sfida per il Generatore
  Incontri Casuali?" → "Entrambe le modalità (consigliato)"): due modalità nello stesso dialog.
  - **`core/encounter_generator.py`** (nuovo modulo puro, nessuna dipendenza Flet/DB, stesso principio di
    `core/encounter_calculator.py`/`treasure_generator.py`/`trap_generator.py`): il "tema" è ricavato interamente
    dal campo `type` già presente in `monsters.json` (444 mostri auditati) — nessuna nuova tabella di
    classificazione. `_normalize_theme()`/`_THEME_MERGE` risolve 3 incoerenze del dato originale in fase di
    raggruppamento (mai un cambio al dato stesso): "Non Morto"/"Non morto" (maiuscole incoerenti, 6 voci contro 23)
    → un solo bucket; "Diavolo" (ARCANALOTH/NYCALOTH/ULTROLOTH, in realtà Yugoloth, mistag di trascrizione di una
    sessione precedente) → bucket "Immondo"; "Mostruosità Mastodontica" (solo TARRASQUE) → bucket "Mostruosità".
    `get_theme_options()`/`filter_by_theme()`/`filter_by_cr_range()` (quest'ultima tollerante ai GS non numerici
    come il Drago Fatato, tramite `cr_to_float`).
    - **Modalità Diretta** (`generate_direct(monsters, theme, cr_min, cr_max, count)`): estrazione casuale CON
      ripetizione (`random.choices`) dal pool filtrato — le ripetizioni sono volute e realistiche (es. "4 goblin"),
      non un difetto. Lista vuota se il pool è vuoto o `count<=0`.
    - **Modalità Per Gruppo** (`generate_for_party(monsters, party_levels, difficulty, theme, cr_min, cr_max)`):
      stesso concetto di "PG fantasma" già usato dal Calcolatore Difficoltà (punto 4); algoritmo goloso che ad ogni
      passo ricalcola il budget PE residuo con
      `calculate_difficulty()`/`encounter_multiplier()`/`get_pe_threshold()` (le stesse funzioni già verificate e
      in uso, nessuna duplicazione) e pesca un candidato A CASO (`random.choice`, non deterministico) tra quelli
      che rientrano nel budget (tolleranza 25%, per non restare sistematicamente sotto-soglia); tetto di sicurezza
      `_MAX_MONSTERS_PER_GROUP_MODE=15` anti-loop; se anche il mostro più debole del pool eccede il budget, lo
      aggiunge comunque da solo invece di restituire un incontro vuoto. Lista vuota se `party_levels` è vuoto,
      `difficulty` non è una delle 4 categorie PHB, o il pool filtrato è vuoto.
  - **Bug reale di dato trovato durante l'implementazione (non specifico di questo task, latente in codice già in
    produzione)**: il campo `xp` di `monsters.json` è incoerente nel formato tra le 444 voci — intero vero, stringa
    di sole cifre, stringa italiana con separatore delle migliaia a punto ("1.800", "25.000", 68 voci — soprattutto
    draghi/giganti/elementali/golem di alto livello), o stringa vuota `""` (9 voci: ARCANALOTH, MANTO SCURO,
    WRAITH, XORN, YETI ABOMINEVOLE, YUAN-TI SANGUE PURO, ZOMBI, ZOMBI BEHOLDER, ZOMBI OGRE). Il pattern
    `int(m.get("xp", 0) or 0)` già usato in 3 punti di codice Master già scritto (`master_encounter_view.py`,
    `master_repo.py → create_npc_from_monster`, `master_npc_list_view.py`) solleva `ValueError` su queste 77 voci —
    bug latente mai emerso prima perché nessun flusso precedente aveva mai iterato sistematicamente l'intero
    bestiario filtrato per tema/GS. Fix: nuova `parse_monster_xp(raw)` in `data/game_data/game_data_loader.py` (mai
    un modulo Flet/DB — deve restare chiamabile sia da `core/` sia da `ui/`/`data/`), gestisce tutti e 4 i formati
    senza mai sollevare eccezioni (fallback 0); applicata ai 3 call site pre-esistenti + a tutti i punti nuovi di
    questo task.
  - **Violazione architetturale trovata e corretta nello stesso passaggio**: `cr_to_float()` viveva in
    `ui/components/monster_picker.py`, che fa `import flet as ft` — importarla da `core/encounter_generator.py`
    avrebbe introdotto una dipendenza Flet transitiva in un modulo `core/`, contro la regola esplicita del progetto
    ("Core: mai dipendenze da Flet"). Fix: `cr_to_float()` spostata in `data/game_data/game_data_loader.py` (zero
    dipendenze Flet/DB), con un re-export in `monster_picker.py` (`from data.game_data.game_data_loader import
    cr_to_float  # noqa: F401`) per i suoi 3 call site interni già esistenti.
  - **UI — `ui/views/master/master_encounter_generator_dialog.py`** (nuovo) + pulsante "Genera Incontro Casuale"
    nell'header di `MasterEncounterListView` (`_on_generate_click()`, accanto a "+ Nuovo Incontro"): `RadioGroup`
    Diretta/Per Gruppo, Dropdown Tema (da `get_theme_options()`, con "Qualsiasi" come prima voce), sezione Diretta
    (Dropdown/TextField GS min-max, TextField numero mostri) o sezione Per Gruppo (stesso pattern "PG fantasma" già
    collaudato in `master_encounter_view.py → _on_difficulty_click`: checkbox sui PG reali + righe livello
    aggiungibili/rimuovibili, Dropdown Difficoltà bersaglio, GS min-max opzionali), pulsante "Genera" (rebuilda
    `result_col` con `Counter` per raggruppare copie dello stesso mostro, mostra PE totale e la difficoltà
    raggiunta via `calculate_difficulty()`), pulsante "Crea Nuovo Incontro con questi Mostri" (`_on_create`: crea
    l'incontro via `master_repo.create_encounter()` con nota "Generato automaticamente dal Generatore di Incontri
    Casuali", poi un `add_member(kind="adhoc", ...)` per ciascun mostro con `xp=parse_monster_xp(...)`, chiude il
    dialog e apre subito il nuovo incontro tramite lo stesso `_open_encounter()` già usato da "+ Nuovo Incontro").
  - **Verificato** con una batteria di test end-to-end (mai il DB reale di Davide, nessun personaggio coinvolto in
    questi test — solo logica pura + dataset reale `monsters.json`): `parse_monster_xp()` su tutti i formati
    (int/stringa cifre/stringa puntata/vuota/None/float/non parsabile); **tutti i 444 mostri parsano senza
    eccezioni** (prova diretta che il bug è risolto, non solo teoricamente); `get_theme_options()` conferma le 3
    fusioni attese (15 temi finali, "Non Morto"/"Diavolo"/"Mostruosità Mastodontica" assenti come voci separate);
    generazione Diretta a tema "Drago" (esercita esplicitamente le voci con XP puntato, che prima avrebbero fatto
    crashare la funzione) — 10/10 generazioni da 4 mostri ciascuna senza eccezioni; varietà Diretta — 20/20
    risultati distinti su un pool ristretto (Umanoide, GS 0-3); pool vuoto (tema "Non morto", GS 999-1000) → lista
    vuota, nessun errore; Per Gruppo su tutte e 4 le difficoltà con un gruppo di 4 PG di livello 10-11 e tema
    "Gigante" (stesse voci a XP puntato) — nessuna eccezione, PE modificato e difficoltà raggiunta sempre coerenti
    con `calculate_difficulty()`; varietà Per Gruppo — 11/15 risultati distinti (variabilità intrinseca
    dell'algoritmo goloso, non un difetto); `difficulty` inesistente o `party_levels` vuoto → lista vuota senza
    eccezioni; `cr_to_float` verificato identica sia dal nuovo percorso sia dal vecchio re-export (`is` identity
    check). `python3 -m py_compile`/`pyflakes` puliti su tutti gli 8 file toccati/creati (`game_data_loader.py`,
    `monster_picker.py`, `master_repo.py`, `master_encounter_view.py`, `master_npc_list_view.py`,
    `core/encounter_generator.py`, `master_encounter_generator_dialog.py`, `master_encounter_list_view.py`);
    `python3 -m compileall -q -x '^\./build/' .` sull'intero albero sorgente — 0 errori.

- [x] **Sezione Master (12) — Generatore Oggetti Magici Casuale** ✅ (2026-07-25) — secondo dei 3 nuovi strumenti
  richiesti da Davide oltre ai 10 già completati (vedi punto (11) sopra per il requisito trasversale di varietà,
  valido identico anche qui: nessun seed fisso, nessuna generazione ripetitiva, verificato con test dedicati).
  **Differenza di fondo rispetto al Generatore Tesori** (già esistente,
  `core/treasure_generator.py`/`master_treasure_dialog.py`): quel generatore tira da tabelle d100 del DMG e produce
  SOLO NOMI di oggetti magici, con una nota "descrizione completa non ancora disponibile" — necessaria all'epoca
  perché il Compendio Oggetti Magici A-Z non esisteva ancora (vedi punto (7) sotto, completato lo stesso giorno).
  Questo nuovo generatore lavora invece **direttamente sul Compendio già trascritto per intero**
  (`data/game_data/magic_items.json`, 264 voci): ogni oggetto generato porta con sé la sua descrizione ufficiale
  completa, pronta per essere aggiunta all'inventario di un personaggio senza alcuna nota di "mancante".
  **`core/magic_item_generator.py`** (nuovo modulo puro, nessuna dipendenza Flet/DB, stesso principio di
  `core/encounter_generator.py`/`treasure_generator.py`/`trap_generator.py`): il Master fissa (entrambi opzionali —
  nessun filtro = l'intero compendio) una **rarità** e/o una **categoria**, più un numero di oggetti desiderato.
  `get_category_options(items)` (elenco ordinato delle categorie base disponibili) e `filter_magic_items(items,
  rarity, category)` riusano due funzioni pure già scritte per il browser `MasterMagicItemsView` —
  `magic_item_category_base()` ("Arma (qualsiasi spada)"→"Arma") e `magic_item_rarity_bucket()` (normalizza il
  testo libero e spesso multi-rarità del campo `rarity` in una delle 6 fasce, ricadendo su "variabile" se il testo
  menziona più fasce distinte — stessa logica già verificata per 264/264 voci nel punto (7) sotto). **Estrazione
  senza ripetizione quando il pool lo consente** (`generate_magic_items()`, `random.sample`) — a differenza del
  Generatore Incontri (dove più copie dello stesso mostro sono realistiche, es. "4 goblin"), qui gli oggetti sono
  unici e nominati: chiedere 3 oggetti da un pool di 20 non deve quasi mai restituire lo stesso oggetto due volte.
  Se la richiesta eccede la dimensione del pool filtrato, il pool viene esaurito una volta per intero
  (`random.shuffle`) e completato con ripetizioni (`random.choices`) solo per la parte eccedente — non solleva mai
  un errore, ma nemmeno finge una varietà che i dati non permettono. Lista vuota se il pool filtrato è vuoto o
  `count<=0`.
  **Violazione architetturale trovata e corretta nello stesso passaggio** (stesso tipo di problema già risolto per
  `cr_to_float()` nel punto (11) sopra): `_category_base()`/`_rarity_bucket()` vivevano come funzioni private di
  `ui/views/master/master_magic_items_view.py`, che fa `import flet as ft` — importarle da
  `core/magic_item_generator.py` avrebbe introdotto una dipendenza Flet transitiva in un modulo `core/`, contro la
  regola esplicita del progetto. Fix: entrambe spostate (non riscritte, stesso identico corpo) in
  `data/game_data/game_data_loader.py` come `magic_item_category_base()`/`magic_item_rarity_bucket()` (zero
  dipendenze Flet/DB), con un re-export/alias in `master_magic_items_view.py` (`from
  data.game_data.game_data_loader import magic_item_category_base as _category_base, magic_item_rarity_bucket as
  _rarity_bucket`) per preservare invariati tutti i call site interni già esistenti in quel file.
  **UI — `ui/views/master/master_magic_item_generator_dialog.py`** (nuovo) + pillola "Oggetto Magico" nella barra
  strumenti sempre visibile di `MasterView` (`_build_tools_row()`, tra "Tesoro" e "Trappola", icona `AUTO_AWESOME`
  — stessa icona già usata per la tab "Oggetti Magici", coerenza visiva voluta): Dropdown Rarità/Categoria (con
  opzioni "Qualsiasi"/"Tutte" come prima voce), TextField "Quanti oggetti", una riga informativa che mostra dal
  vivo quanti oggetti restano disponibili con i filtri correnti (`_update_pool_hint()`, ricalcolata ad ogni cambio
  Dropdown), pulsante "Genera" (rebuilda `result_col` con una card per oggetto — icona categoria, nome, chip
  rarità/categoria/sintonia colorati, descrizione integrale selezionabile), Dropdown "Aggiungi all'inventario
  di..." (da `character_repo.get_all()`, disabilitato se non esistono personaggi) + pulsante che riusa direttamente
  `character_repo.create_inventory_item()` (nessuna nuova funzione di scrittura personaggio, stesso principio già
  seguito dal Generatore Tesori) — i nomi ripetuti (es. più copie dello stesso oggetto per un draw con `count`
  maggiore del pool) vengono raggruppati con `collections.Counter` in un'unica riga inventario con `quantity`
  corretta invece di N righe duplicate; ogni oggetto è salvato con `category="magic"`, `description` (il testo
  ufficiale integrale, già visibile nella tab Inventario del personaggio — verificato per grep che sia
  `description` sia `effects` sono renderizzati da `inventario_tab.py`) ed `effects` (una riga di riepilogo
  "Categoria · Rarità · Richiede sintonia (restrizione)", stessa convenzione già in uso per gli oggetti del
  Generatore Tesori).
  **Verificato** con una batteria di test end-to-end (DB temporaneo isolato via `tempfile.mkdtemp()`+`HOME`
  separato, mai il DB reale di Davide; `FakePage` minimale + scansione ricorsiva dell'albero controlli per pilotare
  i veri dialog Flet, stesso pattern già consolidato nel progetto): logica pura — dataset reale (264/264 voci,
  distribuzione rarità di nuovo confermata `{"raro":84,"leggendario":32,"non comune":82,"molto
  raro":50,"variabile":15,"comune":1}`), filtro per categoria/rarità con conteggi corretti, 20/20 estrazioni da 5
  oggetti senza duplicati intra-draw, richiesta eccedente il pool (9 Verghe, richieste 15) che include l'intero
  pool base + ripetizioni solo per l'eccedenza, pool vuoto e `count<=0` → lista vuota senza eccezioni, ogni oggetto
  generato ha sempre una `description` non vuota; dialog pilotato end-to-end — generazione di 3 Verghe (isolando
  correttamente il testo del nome, size=13 bold, dal testo del chip categoria "Verga" che altrimenti in un primo
  giro di test aveva prodotto un falso positivo di conteggio — bug del test stesso, non dell'applicazione, corretto
  restringendo il filtro), caso rarità+categoria senza corrispondenze → zero card mostrate con messaggio
  informativo, aggiunta all'inventario di un personaggio verificata end-to-end (3 Verghe distinte salvate con
  `quantity=1` ciascuna, `description` integrale — fino a 3756 caratteri per "Verga della Potenza Divina" — e
  `effects` col riepilogo corretto, incluso "Richiede sintonia" solo per le 2 voci che lo richiedono davvero).
  `python3 -m py_compile`/`pyflakes` puliti su tutti i 5 file toccati/creati (`core/magic_item_generator.py`,
  `ui/views/master/master_magic_item_generator_dialog.py`, `ui/views/master/master_view.py`,
  `ui/views/master/master_magic_items_view.py`, `data/game_data/game_data_loader.py`); `python3 -m compileall -q -x
  '^\./build/' .` sull'intero albero sorgente — 0 errori.

- [x] **Sezione Master (13) — Liste nomi NPC per razza/genere** ✅ (2026-07-25) — dato di supporto propedeutico al
  Generatore Rapido NPC (punto 14 sotto), terzo dei 3 nuovi strumenti richiesti da Davide oltre ai 12 già
  completati sopra.
  **Vincolo di contenuto esplicito**: nomi in stile fantasy generico, **NON copiati dal PHB né da alcuna altra
  opera pubblicata/protetta da copyright** ("stile fantasy generico non copiato da PNG ufficiali") — scelta di
  design deliberata per restare distinta dal materiale ufficiale/di terze parti mentre si offre comunque un pool di
  nomi pronto all'uso per un NPC generato al volo. Durante la stesura è stato necessario un autoaudit e la
  riscrittura di diverse liste che collidevano per errore con nomi di altre opere note (hobbit alla Tolkien,
  personaggi di Game of Thrones, carte Magic: The Gathering, NPC di moduli D&D pubblicati) — nessuno di questi è
  rimasto nel file finale.
  **`data/game_data/npc_names.json`** (nuovo): 9 razze
  (Umano/Elfo/Nano/Halfling/Gnomo/Mezzelfo/Mezzorco/Tiefling/Dragonide) × maschio/femmina × 16 nomi inventati
  ciascuno = 288 nomi totali. Le chiavi razza sono identiche, carattere per carattere, a quelle già usate ovunque
  nel progetto (`RACES_BASE`/`character.race`), così `core/npc_generator.py` può risolvere la lista con un semplice
  lookup diretto, senza alcuna normalizzazione di stringa. Campo `_note` nel file stesso che documenta la scelta di
  non-derivazione da fonti ufficiali.
  **`GameDataLoader.get_npc_names(race, gender)`** (nuovo, `data/game_data/game_data_loader.py`): lazy-load-e-cache
  dal file (stesso pattern di `_ensure_*()` già consolidato nel progetto), ritorna la lista di 16 nomi per la
  combinazione richiesta o lista vuota per una combinazione non riconosciuta (mai un'eccezione).
  **Verificato**: validazione JSON (9 razze × 2 generi × 16 nomi = 288, nessun nome duplicato all'interno della
  stessa lista razza/genere); round-trip funzionale di `get_npc_names()` su tutte le 18 combinazioni razza/genere;
  `python3 -m py_compile` su `game_data_loader.py` pulito.

- [x] **Sezione Master (14) — Generatore Rapido NPC** ✅ (2026-07-25) — terzo e ultimo dei 3 nuovi strumenti
  richiesti da Davide, si appoggia al punto 13 sopra per i nomi. Stesso requisito trasversale di varietà già citato
  per i punti 11/12: nessun risultato ripetitivo, verificato con test dedicati.
  **A differenza dei generatori Incontri/Oggetti Magici (punti 11/12), questo strumento NON ha una propria pillola
  nella barra strumenti sempre visibile di `MasterView`** — per esplicita indicazione del task, è innestato come
  terza scelta ("Genera Casuale") dentro il dialog "Nuovo NPC" già esistente di `MasterNpcListView`, accanto a
  "Nuovo dal Bestiario"/"Nuovo Manuale".
  **`core/npc_generator.py`** (nuovo modulo puro, nessuna dipendenza Flet/DB, stesso principio di
  `encounter_generator.py`/`magic_item_generator.py`): il Master sceglie razza/ruolo/allineamento/genere, ognuno
  lasciabile su "Qualsiasi" (risolto a caso tra le opzioni PHB — mai un default fisso). `generate_npc()` produce:
  un nome da `npc_names.json` (punto 13, `GameDataLoader.get_npc_names()`); tratti di
  personalità/ideale/legame/difetto presi da UN background PHB scelto a caso — **stesso identico meccanismo già in
  uso in `wizard_engine.py.build_character()`** per i personaggi giocanti (`random.choice` su
  `personality_traits`/`ideals`/`bonds`/`flaws` di `data/game_data/backgrounds/*.json`), riusato qui pari pari
  invece di reinventare una logica equivalente; se il `role` scelto (case-insensitive, spazi normalizzati) combacia
  con una delle 21 voci dell'Appendice B "Personaggi Non Giocanti" del Manuale dei Mostri
  (Accolito/Arcimago/.../Veterano, già presenti in `monsters.json`), anche lo stat block di combattimento completo
  di quella voce. `generate_npcs(count, ...)` genera N NPC indipendenti (ogni estrazione è a sé, nessuno stato
  condiviso tra un NPC e il successivo nello stesso batch).
  **`GameDataLoader` — nuovi metodi di supporto** (`data/game_data/game_data_loader.py`):
  `get_appendix_b_role_names()` (le 21 voci, casistica italiana scritta a mano — es. "Capo dei Banditi", non un
  banale `.title()` che produrrebbe "Capo Dei Banditi"); `get_appendix_b_stat_block(role)`, che verifica **prima di
  tutto** l'appartenenza di `role` (normalizzato) alle 21 voci di Appendice B, e solo in caso positivo cerca lo
  stat block esatto in `monsters.json` (nuovo `_ensure_monsters()`, lazy-load separato) — questo ordine di
  controllo è deliberato: un ruolo scritto a mano che nomini un mostro qualsiasi del bestiario (es. "Drago Rosso
  Antico") non deve **mai** agganciare uno stat block, solo le 21 voci di Appendice B lo fanno, per restare fedeli
  esattamente alla richiesta originale.
  **UI — `ui/views/master/master_npc_generator_dialog.py`** (nuovo) + terza scelta "Genera Casuale" nel dialog
  "Nuovo NPC" di `MasterNpcListView._on_new_click()` (icona `AUTO_AWESOME`, colore oro per distinguerla dalle due
  scelte esistenti crimson/blu): Dropdown Razza/Genere/Allineamento/Ruolo (quest'ultimo con le 21 opzioni Appendice
  B, ciascuna etichettata "(scheda combattimento)"), TextField "Ruolo personalizzato" (testo libero, sovrascrive la
  scelta del Dropdown se compilato — permette ruoli puramente narrativi non presenti in Appendice B), TextField
  "Quanti NPC", pulsante "Genera" che produce una card per NPC (nome, chip razza/genere/allineamento/ruolo,
  tratto/ideale/legame/difetto, riga CA/PF/GS/PE + pulsante "Vedi scheda" se ha uno stat block — riusa
  `show_stat_block_dialog()` già condiviso, passando direttamente il dict grezzo di `monsters.json` senza bisogno
  di `creature_entry_dict()`, dato che è già nella forma "risolta" attesa), etichetta "Background usato" a fondo
  card per trasparenza. **Ogni card ha un proprio pulsante "Salva in Rubrica"** (non un salvataggio unico in blocco
  come nel Generatore Oggetti Magici — un NPC generato è più individualmente prezioso di un oggetto, il Master può
  voler tenere solo alcuni dei risultati di un batch), che diventa "Salvato ✓" disabilitato dopo il salvataggio,
  senza impedire di salvare le altre card dello stesso batch indipendentemente.
  **Persistenza** (`_do_save()`): NPC senza stat block → `master_repo.create_npc()` diretto; NPC con stat block →
  `master_repo.create_npc_from_monster()` seguito da un `update_npc()` dedicato per sovrascrivere l'allineamento —
  necessario perché `create_npc_from_monster()` non accetta un parametro di override allineamento (eredita sempre
  quello grezzo del mostro), quindi l'allineamento scelto/risolto dal Master nel dialog va applicato in un secondo
  passaggio esplicito, altrimenti un NPC con scheda di combattimento ignorerebbe silenziosamente la
  caratterizzazione scelta in questo generatore. Razza/genere finiscono nel campo `tags` (CSV, `MasterNpc` non ha
  campi dedicati `race`/`gender`), personalità/background nel campo `notes` (multilinea, "Tratto: ...", "Ideale:
  ...", ecc., più "(Personalità generata da background: X)" per tracciabilità).
  **Verificato** con una batteria di test end-to-end (DB temporaneo isolato via `tempfile.mkdtemp()`+`HOME`
  separato, mai il DB reale di Davide; `FakePage`/`unittest.mock.patch.object(ft.Control, "page", ...)` + scansione
  ricorsiva dell'albero controlli, stesso pattern già consolidato nel progetto): tutte e 21 le voci di Appendice B
  risolvono correttamente il proprio stat block (nome combaciante); matching case/spazi-insensitive confermato ("
  capo   dei banditi " → CAPO DEI BANDITI); un ruolo che nomina un vero mostro del bestiario ma non è tra le 21
  voci di Appendice B (es. "Drago Rosso Antico") **non** aggancia alcuno stat block, né un ruolo vuoto né un ruolo
  completamente inventato; `generate_npc()` testato su ogni combinazione razza×genere×allineamento×ruolo
  (vuoto/Appendice B/custom) — parametri fissati sempre rispettati, parametri vuoti sempre risolti a un valore
  valido, personalità (tratto/ideale/legame/difetto) sempre non vuota per qualunque background estratto;
  **varietà**: batch interamente casuale di 30 NPC → 29/30 nomi unici, 9/9 razze rappresentate, 7/9 allineamenti
  rappresentati; batch con razza/genere fissati (pool ristretto a 16 nomi) → 8/15 nomi unici, variabilità
  statisticamente attesa e accettabile con un pool più piccolo, non un difetto; persistenza — NPC senza stat block
  salvato e riletto con tag/note/allineamento corretti; NPC con stat block (Assassino) salvato via
  `create_npc_from_monster`+`update_npc`, riletto con `has_stat_block=True`, CA/PF/GS/PE reali, `actions` non
  vuote, e **l'allineamento scelto nel generatore correttamente sovrascritto** sopra quello grezzo del mostro
  (prova diretta che il fix del gap "nessun parametro alignment in `create_npc_from_monster`" funziona); NPC
  generato aggiunto con successo a un vero incontro via `master_repo.add_member()`; salvataggio parziale di un
  batch di 5 (solo 3 salvati) verificato indipendente, nessuna riga spuria; dialog pilotato end-to-end —
  generazione di 3 "Veterano" prevede esattamente 3 pulsanti "Salva in Rubrica" e 3 "Vedi scheda" (click su
  quest'ultimo apre correttamente un secondo `AlertDialog` con lo stat block, poi si richiude), il click su "Salva
  in Rubrica" salva esattamente 1 NPC e disabilita quel pulsante trasformandolo in "Salvato ✓" lasciando gli altri
  2 ancora attivi, un NPC senza ruolo non mostra mai "Vedi scheda", un ruolo personalizzato in testo libero compare
  correttamente come chip sulla card generata; wiring in `MasterNpcListView._on_new_click()` verificato con lo
  stesso bypass `patch.object` — il pulsante "Genera Casuale" chiude il dialog di scelta e apre quello del
  generatore, e il callback `on_saved=self.refresh` viene effettivamente invocato dopo un salvataggio riuscito;
  regressione — `MasterView` (con la vera tab "Rubrica NPC") continua a instanziarsi senza eccezioni. `python3 -m
  py_compile`/`pyflakes` puliti su tutti i 4 file toccati/creati (`core/npc_generator.py`,
  `data/game_data/game_data_loader.py`, `ui/views/master/master_npc_generator_dialog.py`,
  `ui/views/master/master_npc_list_view.py`); `python3 -m compileall -q -x '^\./build/' .` sull'intero albero
  sorgente — 0 errori.
  **Con questo si chiudono tutti e 3 i nuovi strumenti richiesti da Davide oltre ai 12 punti della Sezione Master
  già completati** (Generatore Incontri Casuali, Generatore Oggetti Magici, Generatore Rapido NPC).

- [x] **Sezione Master (7) — Compendio Oggetti Magici — ✅ ELENCO A-Z COMPLETATO il 2026-07-25 (264 voci) + ✅ UI DI
  CONSULTAZIONE COMPLETATA lo stesso giorno** — deliberatamente escluso dai 7 task già completati della Sezione
  Master, poi ripreso come progetto a sé stante e portato a termine nella stessa giornata attraverso 4 batch di
  trascrizione, e infine collegato a una vera UI browsabile nella stessa giornata (sessione separata, su richiesta
  esplicita di Davide dopo una revisione dello stato del progetto). Fonte: `Guida del Dungeon Master - 5a e -
  AA.VV_.pdf` (già nel progetto), Cap.7 "Tesori", sezione "Oggetti Magici A-Z". Formato voce confermato (nome /
  `Categoria (qualificatori), rarità [(richiede sintonia [restrizione])]` / descrizione). Dettaglio completo,
  schema dati proposto e design UI in `master_section_design.md` sezione "7. Compendio Oggetti Magici". **Resta
  fuori scope, per scelta esplicita e già discussa** (vedi "Ricognizione range pagine" sotto): la sezione
  "Artefatti" (~13 manufatti unici, formato strutturalmente diverso — nessuna scheda
  nome/categoria/rarità/descrizione standard, ma tabelle di proprietà casuali d100 per manufatto), rimandata a un
  mini-task futuro a sé stante.

  **UI di consultazione — nuovo `ui/views/master/master_magic_items_view.py` (`MasterMagicItemsView`)**, quinta tab
  della Sezione Master (`master_view.py → _TABS`, chiave `"magic_items"`, etichetta "Oggetti Magici", icona
  `ft.Icons.AUTO_AWESOME`, stesso pattern lazy-import con fallback placeholder già usato per le altre 3 tab). Sola
  consultazione — nessuna scrittura su nessuna tabella DB, il dato vive interamente in `magic_items.json` letto via
  `GameDataLoader.get_magic_items()` — stesso principio già stabilito per `FeatsView` (compendio talenti), qui
  innestato nella Sezione Master perché è il Master, non il giocatore, a consultarlo mentre distribuisce tesori.
  - **Ricerca + 2 filtri**: `TextField` di ricerca per nome (case-insensitive, substring); Dropdown "Rarità" (6
    fasce: comune/non comune/raro/molto raro/leggendario/variabile — vedi normalizzazione sotto); Dropdown
    "Categoria" (le 9 categorie base effettivamente presenti nel dataset, calcolate dinamicamente da
    `_category_base()`, mai una lista scritta a mano). Entrambi i Dropdown filtro e la Row che li contiene usano
    `wrap=True`, coerente con le convenzioni responsive già stabilite il 2026-07-24 in questo stesso file.
  - **Normalizzazione rarità** (`_rarity_bucket()`): il campo `rarity` di `magic_items.json` è testo libero e
    spesso multi-rarità (es. "non comune (+1), rara (+2) o molto rara (+3)" per Cintura della Forza dei
    Giganti/Corno del Valhalla/Pietra di Ioun, già documentate come tali nella sessione di trascrizione). La
    funzione rileva quante fasce distinte compaiono nel testo (leggendario/molto raro/non
    comune/raro/comune/variabile) e, se ne trova più di una, ricade su "variabile" invece di sceglierne
    arbitrariamente una — **mai un'invenzione**, coerente con la scelta di trascrizione già fatta (multi-rarità
    trascritta letteralmente in un'unica scheda). Verificato sull'intero dataset reale: distribuzione
    `{"raro":84,"leggendario":32,"non comune":82,"molto raro":50,"variabile":15,"comune":1}`, somma 264 — nessuna
    eccezione, nessun bucket fuori dai 6 attesi.
  - **Card lista**: icona per categoria (`_CATEGORY_ICONS`, fallback `AUTO_AWESOME_OUTLINED` per categorie non
    mappate — nessuna categoria del dataset reale ricade sul fallback, tutte e 9 sono mappate esplicitamente),
    nome, chip rarità (colorato per fascia: grigio/verde/blu/ambra/crimson/grigio-ardesia per
    comune→leggendario→variabile, stesse palette già in uso altrove nell'app), chip categoria, chip "Sintonia" se
    `requires_attunement` (135/264 voci, già noto dalla sessione di trascrizione), anteprima (prima riga della
    descrizione, troncata a 130 caratteri con "…"). Click → `AlertDialog` con testo integrale
    (`ft.Text(selectable=True)`, pattern già verificato sicuro e in uso in 11 altri file del progetto), nota
    sintonia/restrizione se presente, e riferimento pagina ("Guida del Master, pag. N" — non "PHB", dato che questa
    sezione proviene dalla Guida del Dungeon Master, non dal Manuale del Giocatore). Larghezza dialog resa
    responsive tramite `responsive_dialog_width()` (helper già esistente in `ui/widgets.py` dall'audit responsivo
    del 2026-07-24).
  - **Icone verificate contro una whitelist reale**: prima di scegliere i nomi `ft.Icons.*` per categoria/sintonia,
    estratta con `grep -rhoE 'ft\.Icons\.[A-Z_0-9]+' --include='*.py' .` la lista di tutti i nomi icona già usati
    (e quindi già confermati validi) in questa esatta versione di Flet installata nel progetto — evitando di
    introdurre un nome enum inesistente che avrebbe sollevato `AttributeError` solo a runtime.
  **Verificato** con una batteria di test end-to-end (nessun DB coinvolto, dato puramente statico — comunque
  nessuna interazione con `~/.dnd_companion/dnd_companion.db` di Davide): dataset reale — 264/264 voci,
  distribuzione rarità/categoria confermata come sopra; `MasterMagicItemsView()` instanziata senza eccezioni
  (header+body, lista popolata); ricerca per nome ("anello" → 22 risultati, tutti con "anello" nel nome); filtro
  rarità ("molto raro" → 50 risultati, tutti col bucket corretto); filtro categoria ("Verga" → esattamente 9
  risultati, combacia col conteggio noto delle verghe trascritte); dialog dettaglio pilotato con un `FakePage`
  minimale (stesso pattern già consolidato nel progetto per testare dialog Flet senza un vero client) su 4 casi
  rappresentativi — voce semplice (Ascia del Berserker), voce multi-rarità (Cintura della Forza dei Giganti, bucket
  risolto correttamente "variabile"), voce con tabella lunga imbustata nella descrizione (Ampolla di Ferro, 2092
  caratteri, mostrata per intero senza troncamento), voce senza sintonia (nessuna riga "Richiede sintonia"
  mostrata) — tutti aperti senza eccezioni. Wiring `MasterView` → `MasterMagicItemsView` verificato end-to-end (tab
  presente in `_TABS`, `_get_tab_content("magic_items")` istanzia correttamente la vista reale, non il
  placeholder). `python3 -m py_compile`/`pyflakes` puliti su entrambi i file toccati; `python3 -m compileall -q -x
  '^\./build/' .` sull'intero albero sorgente — 0 errori.

  **Ricognizione range pagine (2026-07-25, prima di iniziare a trascrivere)** — la stima "~80 pagine" sotto era
  approssimativa (mai verificata visivamente); confermato con lettura diretta: la sezione "Oggetti Magici A-Z"
  occupa le **pagine stampate 150-214 (pagine PDF 149-213), 65 pagine effettive**, non 80. Mappatura
  pagina-PDF↔pagina-stampata confermata leggendo i footer delle immagini renderizzate: `pagina_stampata =
  pagina_PDF + 1` (diversa dalla formula già nota per la Guida del Master usata altrove in questo file per
  Tesori/Trappole/Malattie — quella sezione del libro ha un offset diverso, +12; qui l'offset è +1, verificato
  empiricamente su più pagine, non assunto). Confermato anche l'inizio della sezione "Oggetti Magici Senzienti"
  (solo regole generali, nessuna voce A-Z, esclusa) e l'inizio della sezione "Artefatti" (pagina PDF 218 circa,
  struttura diversa — nomi propri unici con tabelle di proprietà casuali d100 invece del formato standard
  nome/categoria/rarità/descrizione) subito dopo la fine dell'elenco A-Z. **Decisione presa con Davide via
  `AskUserQuestion` prima di iniziare**: la sezione "Artefatti" (~13 manufatti unici, formato strutturalmente
  diverso) è esclusa da questo task e rimandata a un mini-task futuro a sé stante — questo compendio copre solo
  l'elenco alfabetico standard.

  **Schema dati finale** (`data/game_data/magic_items.json`, lista `items`, ogni voce): `{"name", "category",
  "rarity", "requires_attunement", "attunement_restriction", "description", "source_page"}` — schema confermato
  identico a quello già bozzato, nessuna modifica necessaria durante la trascrizione del batch 1. `category`
  contiene la categoria e l'eventuale qualificatore tra parentesi esattamente come stampato (es. `"Arma (qualsiasi
  spada)"`, `"Armatura (leggera, media o pesante)"`, `"Anello"`, `"Bacchetta"`, `"Oggetto meraviglioso"`); `rarity`
  è testo libero, non un enum — decisione confermata durante la trascrizione: le voci che coprono più rarità nella
  stessa scheda (es. "Arma +1, +2 o +3") si trascrivono letteralmente così come stampate ("non comune (+1), rara
  (+2) o molto rara (+3)") invece di essere spezzate in 3 voci JSON separate, dato che il libro le presenta come
  un'unica scheda con un'unica descrizione condivisa. Le tabelle imbustate nel testo di una singola voce (es. il
  d100 "Contenuto" dell'Ampolla di Ferro, il d10 "Tipo di Danno" dell'Anello di Resistenza/Armatura della
  Resistenza, la tabella "Sfere/Danni da Fulmine" dell'Anello delle Stelle Cadenti, la tabella "Leve" dell'Apparato
  di Kwalish) sono trascritte come testo formattato a righe dentro lo stesso campo `description` — nessun campo
  aggiuntivo per-voce introdotto, per restare fedeli allo schema a 7 campi già proposto e concordato, dato che
  queste tabelle sono regolamento intrinseco di quell'unico oggetto (non un lookup riusabile come le tabelle di
  `treasure_tables.json`/`traps.json`).

  **`GameDataLoader`**: aggiunto `self._magic_items: list[dict[str, Any]] | None = None` in `__init__`, più
  `_ensure_magic_items()` (lazy-load-e-cache da `magic_items.json`, stesso pattern di
  `_ensure_traps()`/`_ensure_treasure()`) e i 3 getter già progettati: `get_magic_items()` (lista completa),
  `get_magic_item(name)` (lookup case-insensitive per nome esatto, `None` se non trovato),
  `get_magic_item_names(rarity=None, category=None)` (filtro opzionale esatto su entrambi i campi). Nessuna UI
  collegata ancora (fuori scope di questa sessione, la Sezione Master aveva già menzionato che la v1 della vista
  può essere costruita anche a compendio parzialmente popolato).

  **Batch 1 (2026-07-25) — pagine stampate 150-159 (PDF 149-158), 52 voci** — lettura visiva pagina per pagina
  (`pdftoppm -r 150`, mai `pdftotext`/OCR per il contenuto, coerente con la regola critica del progetto), dalla A
  ("Ali del Volo") fino a metà della lettera B ("Bacchetta della Metamorfosi") — fermato a un punto di rottura
  pulito (nessuna voce a cavallo tra pagina 158 e 159, verificato leggendo anche l'inizio della pagina 159 prima di
  chiudere il batch). Voci trascritte: Ali del Volo, Ammazzadraghi, Ammazzagiganti, Ampolla di Ferro (con tabella
  d100 contenuti), Amuleto Anti-Individuazione e Localizzazione, Amuleto dei Piani, Amuleto della Salute, Anello
  Accumula Incantesimi, Anello dei Tre Desideri, Anello del Calore, Anello del Camminare sull'Acqua, Anello del
  Comando degli Elementali (con le 4 sotto-sezioni Fuoco/Acqua/Aria/Terra, tutte nella stessa voce — il libro le
  presenta come varianti di un unico oggetto "collegato a uno dei quattro Piani Elementali", non 4 oggetti
  distinti), Anello del Nuotare, Anello del Saltare, Anello dell'Ariete, Anello della Caduta Morbida, Anello della
  Libertà di Azione, Anello della Vista a Raggi X, Anello delle Stelle Cadenti (con tabella Sfere/Danni da
  Fulmine), Anello di Eludere, Anello di Evocazione del Djinni, Anello di Influenza sugli Animali, Anello di
  Invisibilità, Anello di Protezione, Anello di Resistenza (con tabella d10 Tipo di Danno/Gemma), Anello di
  Rigenerazione, Anello di Scudo Mentale, Anello di Telecinesi, Anello Rifletti Incantesimo, Apparato di Kwalish
  (oggetto-veicolo con blocco statistiche proprio CA/PF/Velocità/Immunità e tabella "Leve" a 10 righe), Arco del
  Giuramento, Arma +1/+2/+3, Arma dell'Avvertimento, Arma Spietata, Armatura +1/+2/+3, Armatura Adamantina,
  Armatura Completa della Forma Eterea, Armatura Completa Nanica, Armatura del Marinaio, Armatura
  dell'Invulnerabilità, Armatura della Resistenza (con tabella d10), Armatura della Vulnerabilità (con paragrafo
  Maledizione), Armatura Demoniaca (con paragrafo Maledizione), Armatura di Cuoio Borchiato Incantata, Armatura in
  Mithral, Ascia del Berserker (con paragrafo Maledizione), Bacchetta dei Dardi Incantati, Bacchetta dei Fulmini,
  Bacchetta dei Segreti, Bacchetta del Legame, Bacchetta del Mago da Guerra +1/+2/+3, Bacchetta della Metamorfosi.

  **Punto di verifica testuale non ovvio, risolto durante la trascrizione**: la voce "Armatura della Vulnerabilità"
  (pagina stampata 157) termina il suo primo paragrafo (il beneficio: resistenza a uno tra
  contundente/perforante/tagliente) in fondo alla colonna destra di quella pagina, e il paragrafo "Maledizione"
  prosegue orfano (senza intestazione propria) in cima alla colonna sinistra della pagina successiva (158) —
  verificato con un secondo render ad alta risoluzione (250 DPI) della coda della pagina 157 per escludere che ci
  fosse un paragrafo mancante tra i due, e confermato per contenuto (il meccanismo "resistenza a 1 dei 3 tipi
  fisici, vulnerabilità agli altri 2" è coerente e si richiama esplicitamente da solo) che si tratta della stessa
  identica voce, semplicemente spezzata dall'interruzione di pagina — nessun testo mancante, nessuna voce persa in
  mezzo.

  **Verificato**: script Python di controllo — 52/52 voci con tutti i campi obbligatori non vuoti, `source_page`
  sempre intero, zero nomi duplicati; round-trip `GameDataLoader.get_magic_items()`/`get_magic_item(name)`
  (case-insensitive, `None` per nome inesistente)/`get_magic_item_names(rarity=...)` testati funzionalmente;
  `python3 -m py_compile data/game_data/game_data_loader.py` pulito. File batch usa-e-getta rimosso dopo l'uso,
  coerente con la convenzione già stabilita per i batch del bestiario.

  **Batch 2 (2026-07-25) — pagine stampate 160-180 (PDF 159-179), 81 voci nuove (52→133 totali)** — lettura visiva
  pagina per pagina (`pdftoppm -r 150`, mai `pdftotext`/OCR per il contenuto), da "Bacchetta della Paralisi" fino a
  "Guanti del Potere Orchesco" — fermato a un punto di rottura pulito subito prima di "Guanti Ladreschi"
  (confermato leggendo anche l'inizio della pagina 181 prima di chiudere il batch). Voci trascritte, per pagina:
  **pg.160** Bacchetta della Paralisi, Bacchetta della Paura, Bacchetta della Ragnatela; **pg.161** Bacchetta delle
  Meraviglie (con tabella d100 completa degli effetti), Bacchetta delle Palle di Fuoco; **pg.162** Bacchetta di
  Individuazione dei Nemici, Bacchetta di Individuazione del Magico, Barca Pieghevole, Bastone dei Boschi, Bastone
  dei Maghi (con tabella, testo a cavallo pg.162→163); **pg.163** Bastone dei Tuoni e Fulmini; **pg.164** Bastone
  del Colpo Possente, Bastone del Deperimento, Bastone del Fuoco, Bastone del Gelo; **pg.165** Bastone del Pitone,
  Bastone del Potere (con tabella), Bastone della Guarigione (con tabella), Bastone della Vipera; **pg.166**
  Bastone dello Charme, Bastone dello Sciame di Insetti, Biglia di Forza; **pg.167** Boccia del Comando degli
  Elementali dell'Acqua, Borsa Conservante, Borsa dei Fagioli Magici (con tabella d100); **pg.168** Borsa dei
  Trucchi (Grigia/Marrone/Ruggine, con i 3 sotto-tabelle d8), Borsa Divorante, Bottiglia del Fumo Perenne,
  Bottiglia dell'Efreeti; **pg.169** Bracciali dell'Arciere, Bracciali della Difesa, Braciere del Comando degli
  Elementali del Fuoco, Buco Portatile; **pg.171** (nessuna voce a cavallo dalla 169, salto diretto — pg.170 priva
  di voci A-Z, verificato) Campana dell'Apertura, Candela dell'Invocazione (con tabella), Cappa del Saltimbanco,
  Cappello del Camuffamento; **pg.172** Caraffa dell'Acqua Eterna, Cintura della Forza dei Giganti (con la tabella
  Tipo/Forza/Rarità: colline/pietre-gelo/fuoco/nuvole/tempeste), Cintura Nanica, Colla Meravigliosa, Collana del
  Rosario; **pg.173** Collana dell'Adattamento, Collana delle Palle di Fuoco, Copricapo del Respirare Sott'Acqua,
  Corazza di Scaglie di Drago, Corda Intralciante; **pg.174** Corda per Scalare, Corno del Valhalla (con tabella
  d100/Tipo di Corno), Corno della Distruzione, Cotta di Maglia dell'Efreeti, Cubo dei Portali; **pg.175** Cubo di
  Forza (con tabella), Diadema Incandescente, Difensiva, Elisir della Salute; **pg.176** Elmo del Teletrasporto,
  Elmo della Comprensione dei Linguaggi, Elmo della Luminosità (con tabella), Elmo della Telepatia, Faretra di
  Ehlonna; **pg.177** Fasce Metalliche di Bilarro, Fascia dell'Intelletto, Fermaglio dello Scudo, Ferri della
  Velocità, Ferri dello Zefiro, Filtro d'Amore; **pg.178** Flauto dei Topi, Flauto Incantatore, Fortezza Istantanea
  di Daern, Freccia Assassina; **pg.179** Gemma della Luminosità, Gemma della Visione, Gemma Elementale, Giaco di
  Maglia Elfico; **pg.180** Giara Alchemica, Giavellotto del Fulmine, Globo Fluttuante, Guanti Catturaproiettili,
  Guanti del Nuotare e Scalare, Guanti del Potere Orchesco.

  **Voce ripristinata dal changelog di una prima stesura errata di questo stesso batch**: una prima versione di
  questa voce, scritta ripartendo da un riassunto di sessione anziché rileggendo `magic_items.json`, elencava una
  lista di nomi (es. "Guanti del Furfante", "Cappa dei Pipistrelli", "Bastone dei Frutti") mai realmente trascritti
  — errore individuato e corretto SUBITO, prima di proseguire al batch successivo, incrociando l'elenco con il
  contenuto reale del file (`source_page` 160-180, 81 voci) e ri-verificando a video le pagine 179-180 per dirimere
  il dubbio. Nessun dato applicativo era stato scritto in modo errato (il JSON era sempre stato corretto fin
  dall'inizio) — solo il testo del changelog stesso conteneva nomi inventati, ora sostituito con l'elenco sopra,
  letto direttamente dal file.

  **Convenzioni applicate identiche al Batch 1**: voci multi-rarità in un'unica scheda con `rarity` come stringa
  libera che riporta letteralmente tutte le varianti (Cintura della Forza dei Giganti: `"rara (colline), molto rara
  (pietre/gelo, fuoco), leggendaria (nuvole, tempeste)"`; Corno del Valhalla: `"raro (ottone o argento), molto raro
  (bronzo) o leggendario (ferro)"`), nessuno split in voci separate. Tabelle imbustate nel testo di una singola
  voce trascritte come testo formattato a righe dentro lo stesso campo `description` (Bacchetta delle Meraviglie:
  intera tabella d100 degli effetti casuali; Borsa dei Fagioli Magici: tabella d100 dei tipi di fagiolo; Borsa dei
  Trucchi: 3 tabelle d8 per le varianti Grigia/Marrone/Ruggine, tutte nella stessa voce sotto un'unica
  intestazione, stesso principio già usato per l'Anello del Comando degli Elementali nel Batch 1; Cintura della
  Forza dei Giganti: tabella Tipo/Forza/Rarità; Collana del Rosario: tabella perle; Corno del Valhalla: tabella
  d100/Tipo di Corno/Berserker Evocati/Requisiti; Corazza di Scaglie di Drago: tabella Drago/Resistenza; Cubo di
  Forza: tabella facce del cubo; Elmo della Luminosità, Bastone del Potere, Bastone della Guarigione, Bastone dei
  Maghi, Bacchetta di Individuazione dei Nemici, Bacchetta della Paura/Paralisi/Ragnatela, Candela
  dell'Invocazione, Gemma Elementale, Giara Alchemica: tabelle proprie più piccole, stesso trattamento). Voce a
  cavallo tra due pagine (Bastone dei Maghi: testo che prosegue da pg.162 a pg.163, `source_page` impostato a 162
  dove inizia l'intestazione) — stessa convenzione del Batch 1 (source_page = pagina di apertura della voce, non
  quella di chiusura, verificato coerente con le voci a cavallo già presenti nel Batch 1).

  **Verificato**: script Python di controllo — 133/133 voci totali con tutti i campi obbligatori non vuoti,
  `source_page` sempre intero, zero nomi duplicati (case-insensitive); confermato che le 52 voci del Batch 1
  (source_page 150-159) restano invariate byte per byte; le 81 nuove voci del Batch 2 confermate presenti con
  `source_page` nel range 160-180 atteso; round-trip funzionale `GameDataLoader.get_magic_items()` (133),
  `get_magic_item(name)` (case-insensitive, incluso un test negativo per un nome inesistente → `None`),
  `get_magic_item_names()` (133 nomi), con verifica puntuale delle voci multi-rarità (Cintura della Forza dei
  Giganti, Corno del Valhalla) e di voci con tabella imbustata (Bacchetta delle Meraviglie, Borsa dei Fagioli
  Magici) — tutte risolte correttamente; `python3 -m py_compile data/game_data/game_data_loader.py` pulito. File
  batch usa-e-getta e cartelle di render temporanee rimossi dopo l'uso, coerente con la convenzione già stabilita.

  **Batch 3 (2026-07-25) — pagine stampate 181-195 (PDF 180-194), 60 voci nuove (133→193 totali)** — lettura visiva
  pagina per pagina (`pdftoppm -r 150`, mai `pdftotext`/OCR per il contenuto), da "Guanti Ladreschi" fino a
  "Pozione di Invulnerabilità" — fermato a un punto di rottura pulito (verificato che il resto della pagina
  stampata 195 è solo illustrazione, nessuna voce a cavallo con la 196). **Recupero di un salto temporale nella
  sessione**: il dettaglio verbatim delle pagine 181-192 letto in una sessione precedente non era sopravvissuto a
  una compattazione del contesto (solo note di sintesi erano rimaste) — coerente con la regola critica del progetto
  di non ricostruire mai un testo trascritto dalla sola memoria/sintesi, tutte quelle pagine sono state rilette da
  zero dalle immagini già renderizzate prima di scrivere qualunque dato in questo batch. Voci trascritte, per
  pagina: **pg.181** Guanti Ladreschi, Incensiere del Controllo degli Elementali dell'Aria, Lama del Sole, Lama
  della Fortuna, Lanterna della Rivelazione; **pg.182** Lenti dell'Aquila, Lenti della Visione Dettagliata, Lenti
  dello Charme, Lingua di Fiamme, Manette Dimensionali, Mantello del Pipistrello (testo a cavallo pg.182→183);
  **pg.183** Mantello dell'Aracnide, Mantello dell'Invisibilità, Mantello della Manta, Mantello della Protezione,
  Mantello Distorcente, Mantello Elfico (testo a cavallo pg.183→184); **pg.184** Manto della Resistenza agli
  Incantesimi, Manuale dei Golem (con tabella d20 Golem/Tempo/Costo), Manuale dell'Esercizio Fisico, Manuale della
  Salute, Manuale della Velocità di Azione (testo a cavallo pg.184→185); **pg.185** Martello dei Fulmini (con
  sotto-sezione "Anatema dei Giganti (Richiede Sintonia)"), Martello Nanico da Lancio, Mazza del Terrore;
  **pg.186** Mazza della Distruzione, Mazza della Punizione, Mazzo delle Illusioni (con tabella completa 34
  carte→creatura), Mazzo delle Meraviglie (voce più lunga del compendio finora, testo a cavallo pg.186→189 inclusa
  una pagina di sola illustrazione — pg.187 — nel mezzo: due tabelle carte 13/22, descrizione per-carta completa di
  tutte le 22 carte, il blocco statistiche completo dell'"Avatar della Morte" evocato dalla carta Teschio
  incorporato come testo supplementare, e la nota del DM "Una Questione di Inimicizia" incorporata come testo
  supplementare — nessuna di queste tre appendici è una voce separata del compendio, tutte appartengono/si
  riferiscono unicamente al Mazzo delle Meraviglie); **pg.189** Medaglione dei Pensieri, Munizione +1, +2 o +3,
  Occhiali della Notte, Olio dell'Affilatura, Olio della Forma Eterea; **pg.191** (pg.190 priva di voci A-Z, pura
  illustrazione, verificato) Olio della Scivolosità, Pantofole del Ragno, Pergamena di Protezione (con tabella d100
  Tipo di Creatura), Pergamena Magica (con tabella Livello/Rarità/CD/Bonus di Attacco), Perla del Potere;
  **pg.192** Pietra del Controllo degli Elementali della Terra, Pietra della Buona Fortuna (Pietrafortuna), Pietra
  di Ioun (voce a 14 varianti, testo a cavallo pg.192→193 a metà della descrizione della variante "Riserva");
  **pg.193** Pietre Parlanti, Pigmenti Meravigliosi di Nolzur, Piuma di Quaal (con tabella d100 e 6 varianti, testo
  a cavallo pg.193→194); **pg.194** Polvere della Sparizione, Polvere dello Starnuto e del Soffocamento, Polvere
  Prosciugante, Pozione del Respirare Sott'Acqua, Pozione del Soffio di Fuoco, Pozione della Forma Gassosa, Pozione
  della Forza dei Giganti (con tabella Tipo di Gigante/Forza/Rarità), Pozione di Amicizia con gli Animali, Pozione
  di Chiaroveggenza, Pozione di Crescita; **pg.195** Pozione di Diminuzione, Pozione di Eroismo, Pozione di
  Guarigione (con tabella "Pozioni di Guarigione"), Pozione di Invisibilità, Pozione di Invulnerabilità.

  **Voce multi-variante più estesa del compendio finora — Pietra di Ioun**: 14 sotto-pietre nominate (Agilità,
  Assorbimento, Assorbimento Superiore, Autorità, Consapevolezza, Forza, Intelletto, Intuizione, Maestria,
  Protezione, Rigenerazione, Riserva, Sostentamento, Tempra), ciascuna con rarità propria (da Rara a Leggendaria) e
  un paragrafo di regolamento indipendente — trattata, coerente con la convenzione già stabilita per Cintura della
  Forza dei Giganti/Corno del Valhalla nel Batch 2, come un'unica voce JSON con `rarity` come stringa libera che
  riassume tutte le variazioni (`"molto rara (agilità, assorbimento, autorità, forza, intelletto, intuizione,
  tempra), leggendaria (assorbimento superiore, maestria, rigenerazione), rara (consapevolezza, protezione,
  riserva, sostentamento)"`) e il testo completo di ogni variante nella `description`. Stesso trattamento applicato
  a Pozione della Forza dei Giganti (rarità per tipo di gigante, tabella imbustata) e Pozione di Guarigione (rarità
  per grado, tabella imbustata "Pozioni di Guarigione").

  **Verificato**: script Python di controllo — 193/193 voci totali con tutti i campi obbligatori non vuoti,
  `source_page` sempre intero, zero nomi duplicati (case-insensitive); confermato che le 133 voci dei Batch 1+2
  (source_page 150-180) restano invariate; le 60 nuove voci del Batch 3 confermate presenti con `source_page` nel
  range 181-195 atteso (52 Batch 1 + 81 Batch 2 + 60 Batch 3 = 193); round-trip funzionale
  `GameDataLoader.get_magic_items()` (193), `get_magic_item(name)` (case-insensitive, incluso un test negativo per
  un nome inesistente → `None`), `get_magic_item_names()` con filtro per rarità/categoria, con verifica puntuale
  delle voci più complesse (Mazzo delle Meraviglie, Pietra di Ioun, Pozione di Guarigione, Manette Dimensionali,
  Lama del Sole, Munizione +1/+2/+3) — tutte risolte correttamente con la lunghezza di descrizione attesa; `python3
  -m py_compile data/game_data/game_data_loader.py` pulito. File batch usa-e-getta rimosso dopo l'uso, coerente con
  la convenzione già stabilita.

  **Batch 4 (2026-07-25) — pagine stampate 196-214 (PDF 195-213), 71 voci nuove (193→264 totali, ULTIMO BATCH)** —
  lettura visiva pagina per pagina (`pdftoppm -r 150`, mai `pdftotext`/OCR per il contenuto), da "Pozione di
  Lettura della Mente" fino a "Zainetto Pratico di Heward" — fermato al confine naturale della sezione: la pagina
  stampata 214 chiude con la fine dello Zainetto Pratico di Heward e subito dopo inizia "OGGETTI MAGICI SENZIENTI"
  (solo regole generali, nessuna voce A-Z, già escluso per ricognizione), confermando che l'elenco alfabetico A-Z
  si conclude esattamente qui. Voci trascritte, per pagina: **pg.196** Pozione di Lettura della Mente, Pozione di
  Longevità, Pozione di Resistenza (con tabella d10 tipo di danno), Pozione di Scalare, Pozione di Velocità,
  Pozione di Vitalità, Pozione di Volare, Pozione Velenosa, Pozzo dei Mondi, Pugnale Avvelenato (testo a cavallo
  pg.196→197); **pg.197** Sacro Vendicatore, Scarabeo di Protezione, Scimitarra della Velocità, Scopa Volante,
  Scudo +1, +2 o +3, Scudo Animato (testo a cavallo pg.197→198); **pg.198** Scudo Anti-Incantesimi, Scudo
  Attiraproiettili, Scudo Catturafrecce, Scudo Sentinella, Sella del Cavaliere, Sfera Annientatrice (con tabella
  d100 contatto con un portale), Sfera di Cristallo (voce base + le 3 varianti leggendarie Lettura del
  Pensiero/Telepatia/Visione del Vero, testo a cavallo pg.198→199); **pg.199** Solvente Universale, Spada Affilata,
  Spada Danzante, Spada del Ferimento; **pg.200** Spada del Furto Vitale, Spada della Vendetta (con paragrafo
  Maledizione), Spada delle Risposte (con la tabella completa delle 9 spade Nome/Allineamento/Gemma —
  Conclusione/Confutazione/Controbattuta/Obiezione/Polemica/Replica/Rimbeccata/Risposta/Sentenza), Spada Ruba Nove
  Vite, Spada Vorpal, Spadone del Gelo (testo a cavallo pg.200→201); **pg.201** Specchio Imprigionante;
  **pg.202-203** Statuine del Potere Meraviglioso (voce più estesa del batch: 9 sotto-statuine nominate — Cane
  d'Onice, Capre d'Avorio con le sue 3 varianti Viaggio/Dolore/Terrore, Corvo d'Argento, Elefante di Marmo, Grifone
  di Bronzo, Gufo di Serpentino, Leoni d'Oro, Mosca d'Ebano, Stallone di Ossidiana — con il blocco statistiche
  completo della "Mosca Gigante" incorporato come testo supplementare, dato che non esiste altrove nel progetto un
  bestiario del DMG collegato); **pg.204** Stivali Alati, Stivali dell'Inverno, Stivali della Levitazione, Stivali
  della Velocità, Stivali Elfici, Stivali Molleggiati, Strumento dei Bardi (voce a cavallo pg.204→205, con la
  tabella completa dei 7 tipi di strumento — Arpa di Anstruth/Arpa di Ollamh/Bandura di Fochlucan/Cetera di
  Mac-Fuirmidh/Lira di Cli/Liuto di Doss/Mandolino di Canaith — coerente con il "sette tipi" dichiarato nel testo
  introduttivo); **pg.206** Talismano Anti-Veleno, Talismano del Bene Puro, Talismano del Male Estremo (testo a
  cavallo pg.206→207), Talismano della Rimarginazione, Talismano della Salute; **pg.207** Talismano della Sfera,
  Tappeto Volante (con tabella d100 dimensioni/capacità/velocità), Tomo del Comando e dell'Influenza, Tomo del
  Nitido Pensiero, Tomo della Comprensione (testo a cavallo pg.207→208); **pg.208** Tomo della Lingua Essiccata,
  Tridente del Comando dei Pesci, Tunica degli Occhi (testo a cavallo pg.208→209); **pg.209** Tunica degli Oggetti
  Utili (con la tabella d100 completa delle 13 toppe extra), Tunica dei Colori Scintillanti, Tunica dell'Arcimago
  (testo a cavallo pg.209→210); **pg.210** Tunica delle Stelle, Unguento di Keoghtom, Ventaglio; **pg.211** Verga
  dei Tentacoli, Verga del Patto Rispettato, Verga dell'Allerta, Verga dell'Assorbimento (testo a cavallo
  pg.211→212); **pg.212-213** Verga della Potenza Divina (voce più complessa del batch: 6 pulsanti che trasformano
  l'arma — lingua di fiamme/ascia da battaglia/lancia/pertica/ariete portatile/bussola magnetica — più 3 proprietà
  nominate Risucchio Vitale/Paralizzante/Terrificante, testo a cavallo pg.212→213); **pg.213** Verga della
  Resurrezione, Verga della Sicurezza, Verga della Sovranità, Verga Inamovibile, Zainetto Pratico di Heward (testo
  a cavallo pg.213→214, conclude a pg.214).

  **Nuove categorie confermate necessarie in questo batch** (nessuna estensione di schema, solo nuovi valori del
  campo libero `category`, verificato assenti dalle 193 voci precedenti prima di introdurle): `"Armatura (scudo)"`
  (6 voci: Scudo +1/+2/+3, Scudo Animato, Scudo Anti-Incantesimi, Scudo Attiraproiettili, Scudo Catturafrecce,
  Scudo Sentinella) e `"Verga"` (9 voci: Verga dei Tentacoli, Verga del Patto Rispettato, Verga dell'Allerta, Verga
  dell'Assorbimento, Verga della Potenza Divina, Verga della Resurrezione, Verga della Sicurezza, Verga della
  Sovranità, Verga Inamovibile). Nessuna delle due famiglie era mai comparsa nei primi 3 batch (nessuna arma-scudo,
  nessuna verga come categoria di oggetto — solo bacchette/bastoni, categoria diversa).

  **Convenzioni multi-rarità/multi-variante applicate identiche ai batch precedenti**: Scudo +1/+2/+3 e Verga del
  Patto Rispettato con `rarity` come stringa libera che riassume tutte le varianti ("non comune (+1), rara (+2) o
  molto rara (+3)"), stesso principio già stabilito per Cintura della Forza dei Giganti/Pietra di Ioun. Sfera di
  Cristallo trattata come un'unica voce con la base (molto rara) più le 3 varianti leggendarie nominate nella
  `description`, stesso principio di Statuine del Potere Meraviglioso (rarità variabile, 9 sotto-oggetti nominati
  con rarità/durata proprie) e di Strumento dei Bardi (rarità variabile, per-strumento via la tabella imbustata).

  **Verificato**: script Python di controllo — 264/264 voci totali con tutti i campi obbligatori non vuoti,
  `source_page` sempre intero (range 150-213), zero nomi duplicati (case-insensitive); confermato che tutte le 193
  voci dei Batch 1-3 (source_page 150-195) restano invariate; le 71 nuove voci del Batch 4 confermate presenti con
  `source_page` nel range 196-213 atteso (52+81+60+71 = 264); round-trip funzionale
  `GameDataLoader.get_magic_items()` (264), `get_magic_item(name)` (case-insensitive, incluso un test negativo per
  un nome inesistente → `None`), `get_magic_item_names()` con filtro per categoria (es. `category="Verga"` → tutte
  e 9 le verghe attese, nessuna in più/meno) — con verifica puntuale delle voci più complesse (Statuine del Potere
  Meraviglioso, Spada delle Risposte, Strumento dei Bardi, Verga della Potenza Divina, Sfera di Cristallo, Tunica
  degli Oggetti Utili) — tutte risolte correttamente con il contenuto imbustato atteso presente in `description`;
  `python3 -m py_compile data/game_data/game_data_loader.py` pulito. File batch usa-e-getta rimosso dopo l'uso,
  coerente con la convenzione già stabilita.

  **Riconciliazione finale (2026-07-25, chiusura dell'intero elenco A-Z)** — a differenza del bestiario, la Guida
  del Dungeon Master non contiene un indice alfabetico dedicato agli oggetti magici con numero di pagina per voce
  (verificato: l'"Indice Analitico" del libro, pag. 317+, è un indice concettuale generico — es. `"anelli, 139"`,
  `"bacchetta, 139"` — che rimanda solo alle pagine di regole introduttive del Cap.7, non un indice per-oggetto
  come l'"Indice delle Schede delle Statistiche" del Manuale dei Mostri usato per chiudere l'audit dei 444 mostri).
  La riconciliazione è stata quindi eseguita per **continuità di copertura pagine** invece che per confronto con un
  indice: script Python di controllo sull'insieme di tutti i `source_page` (150-213) contro il range completo
  atteso — individuate 6 pagine senza alcuna voce con quel `source_page` esatto (170, 187, 188, 190, 203, 205),
  tutte verificate a mano come pagine di **continuazione** di una voce già attribuita alla pagina precedente (es.
  pg.203 = coda di "Statuine del Potere Meraviglioso", attribuita a pg.202; pg.205 = coda di "Strumento dei Bardi",
  attribuita a pg.204 — entrambe confermate con lettura diretta in questo stesso batch) o pagine di sola
  illustrazione già annotate come tali nei changelog dei Batch 2-3 (pg.170, 187, 188, 190) — nessuna voce risulta
  mancante o saltata. Con questo si chiude l'intera trascrizione dell'elenco "Oggetti Magici A-Z" (264 voci, pag.
  150-214 stampate).

  Vedi `dnd_app/docs/master_section_design.md` per lo schema SQL completo di tutti i punti, il repository proposto
  (`data/repositories/master_repo.py`), il dettaglio di ogni vista, e la tabella riassuntiva di sforzo per tutti e
  10 gli strumenti.
- [x] **Selezione Umano Standard vs Umano Variante nel wizard/form** — **✅ implementata il 2026-07-16**, entrambi i
  file (`manual_form.py` fase Scelte, `wizard_view.py` fase Revisione, stessa identica implementazione
  mirror-portata da un file all'altro). Dato già presente in `umano.json → variant_human_optional_rule` (trascritto
  dal manuale il 2026-07-09, nessuna modifica al dato in questa sessione): +1 a due caratteristiche diverse a
  scelta, competenza in un'abilità a scelta, un talento a scelta (riusa lo stesso pool `feats.json` e lo stesso
  `dropdown_with_info`/`make_feat_describe` già usati per il picker ASI del level-up) — in sostituzione integrale
  del tratto standard "+1 a tutte le caratteristiche".
  **UI**: `ft.RadioGroup` "Standard"/"Variante (regola opzionale)" nella sezione Extra Razziali, subito dopo il
  blocco Alto Elfo e prima delle lingue a scelta di razza (stessa posizione in entrambi i file). Se "Variante": 2
  dropdown a mutua esclusione per le caratteristiche (stesso pattern già usato per il flex Mezzelfo — ogni dropdown
  esclude dalle proprie opzioni il valore corrente dell'altro), 1 dropdown abilità (esclude le abilità già concesse
  da background/classe/Mezzelfo, e viceversa la abilità Variante appena scelta esclude sé stessa dal pool di classe
  — `_class_skill_options()` esteso), 1 dropdown talento con icona ⓘ (descrizione completa prima di scegliere) + un
  dropdown condizionale "Scegli la caratteristica da aumentare" per i talenti `choose_one` (es. Atleta: Forza o
  Destrezza).
  **Salvataggio**: sottrae il bonus standard (+1 a tutte e sei le caratteristiche, già applicato da
  `build_character()`/`_stat_engine.build_character()` tramite `get_resolved_race("Umano")["ability_bonuses"]`) e
  applica +1 solo alle due caratteristiche scelte — net effect corretto per qualunque combinazione. Ricalcola
  `hp_max`/`hp_current` (`dado vita + mod CON`) dato che CON potrebbe essere cambiata rispetto al calcolo iniziale
  di `build_character()` — **gap esplicitamente NON risolto per il percorso Mezzelfo** (stesso identico limite
  pre-esistente: la preview HP mostrata in fase Punteggi/Revisione resta quella calcolata PRIMA della scelta
  Mezzelfo/Variante, mai un bug segnalato finora, fuori scope di questo task). Talento salvato con lo stesso schema
  "ricevuta" (`bonus_data`/`level_obtained=1`) già usato per i talenti ASI del level-up — compare nella sezione
  Talenti di `ProfiloTab` e resta reversibile via `remove_feat_with_bonuses()`.
  **Validazione**: aggiunta sia al pulsante "Continua" (`_scelte_validation_error()`/`_review_validation_error()`)
  sia come difesa in profondità nel salvataggio finale (`_on_save`), stesso pattern doppio già in uso nel progetto
  — blocca se le due caratteristiche non sono distinte, se manca l'abilità, se manca il talento, o se il talento è
  `choose_one` senza caratteristica scelta.
  **Bug reale trovato e corretto durante l'implementazione** (non nella richiesta originale, scoperto scrivendo i
  test end-to-end): il dropdown "Scegli la caratteristica da aumentare (+1)" (per i talenti `choose_one`, es.
  Atleta) non aveva **mai** un `on_select` — né qui né nell'equivalente identico `feat_bonus_dd` del dialog di
  level-up ASI in `profilo_tab.py` (quest'ultimo però non ne risente: legge `.value` direttamente dal controllo al
  salvataggio, e Flet sincronizza `.value` lato server ad ogni selezione tramite un messaggio `UpdateControlProps`
  indipendente dall'evento `on_select` — verificato leggendo `flet/messaging/session.py`/`flet_socket_server.py`
  del pacchetto installato, non assunto). Il bug qui era diverso e reale: il codice copia il valore in una
  variabile Python separata (`self._review_umano_variant_feat_bonus_stat`), valorizzata **una sola volta** col
  default (prima opzione disponibile) dentro `_refresh_uv_feat_bonus_dd()` e mai più riaggiornata — il salvataggio
  legge quella copia stantia, non il `.value` live del controllo. Risultato pratico: scegliere una caratteristica
  diversa dal default per un talento `choose_one` preso come talento Variante Umana veniva ignorato in silenzio,
  sempre applicato alla prima caratteristica della lista. **Fix**: aggiunto `on_select` che tiene la copia
  sincronizzata con la selezione reale, in entrambi i file.
  **Verificato** con test end-to-end (DB temporaneo isolato, mai quello reale, harness che pilota i controlli Flet
  reali — RadioGroup/Dropdown/Checkbox/pulsanti — attraverso l'intero flusso multi-fase fino alla persistenza DB):
  - `manual_form.py`: flusso completo Identità→Punteggi→Scelte→Equipaggiamento→Conferma per un Mago Umano Variante,
    con scelta DELIBERATAMENTE non-default per la caratteristica del talento `choose_one` (Atleta→Destrezza, non
    Forza) — verificato che il valore salvato su `character_proficiencies.bonus_data` sia esattamente quello scelto
    (non il default), prova diretta che il fix del bug sopra funziona; HP ricalcolati correttamente; abilità e
    talento persistiti; reversibilità del talento via `remove_feat_with_bonuses()` verificata (la caratteristica
    torna al valore precedente).
  - `wizard_view.py`: stesso identico test (stessa scelta non-default) più un regression sweep completo **su tutte
    le 12 classi PHB × Standard/Variante (24 combinazioni)** attraverso l'intero flusso
    `_goto_review()`→Revisione→Equipaggiamento→Conferma→creazione DB — tutte e 24 le combinazioni creano
    correttamente il personaggio; per Stregone Standard vs Variante gli HP finali differiscono legittimamente (9 vs
    8) perché lo Standard dà sempre +1 CON mentre la Variante lo dà solo se il giocatore sceglie CON tra le due
    caratteristiche (non scelta in questo test generico) — comportamento corretto, non un bug.
  - Regressione mirata: il fix di `_class_skill_options()` (esclusione dell'abilità Variante dal pool di classe)
    non rompe l'esclusione reciproca già esistente per il Mezzelfo; il test di regressione Standard (nessuna
    Variante) su Guerriero Umano conferma che il percorso preesistente resta invariato.
  - `python3 -m compileall -q -x '^\./build/' .` sull'intero albero sorgente e `pyflakes` mirato su entrambi i file: puliti (solo il rumore preesistente di `from config.settings import *`).
  - **Fix minore collaterale trovato e corretto**: in `wizard_view.py → _on_save`, le prime due chiamate
    `error_text.update()` (controllo nome obbligatorio, a inizio funzione) non erano protette da `try/except
    RuntimeError`, a differenza di TUTTE le altre ~10 occorrenze nello stesso file e nell'equivalente
    `manual_form.py → _on_save` — incoerenza con la convenzione esplicita del progetto (vedi sezione "Regole
    Critiche: API Flet 0.85.3" più sopra). Non innescabile nell'uso reale (il controllo è sempre montato quando il
    giocatore raggiunge la fase Conferma), ma corretto per coerenza e robustezza futura.
- [x] **Audit `BACKGROUNDS` (wizard_data.py) vs `data/game_data/backgrounds/*.json`** ✅ **completato il
  2026-07-10** — tutti i 13 background verificati riga per riga contro il PHB IT e corretti in
  `backgrounds/*.json`; `wizard_data.py → BACKGROUNDS` (il dataset Python divergente) è stato rimosso interamente e
  tutti i call site ora leggono solo dai JSON. Vedi Checklist Revisione Dati PHB → sezione "Background" per il
  changelog completo file per file, e i 4 punti segnalati per revisione manuale di Davide.
- [x] **Audit riga per riga di `equipment/*.json`** ✅ **completato il 2026-07-17** (6 file:
  weapons/armor/adventuring_gear/tools/mounts_and_vehicles/economy), verificati uno alla volta con Davide contro il
  manuale — nessuna correzione necessaria in nessuno dei 6 file. Vedi Checklist Revisione Dati PHB → "Altri file di
  riferimento" per il changelog completo.
- [x] **Tabella d100 "Oggetti Insoliti"** ✅ **trascritta il 2026-07-24** (100 cimeli, PHB IT p.160-161) — esclusa
  deliberatamente da `equipment/adventuring_gear.json` il 2026-07-10 su scelta di Davide (pura ambientazione,
  nessun effetto meccanico), recuperata ora su sua richiesta esplicita in vista del Generatore Tesori Casuali /
  Compendio della Sezione Master (vedi `master_section_design.md`). Trascritta in `equipment/trinkets.json`, stesso
  metodo già usato per incantesimi/mostri: lettura visiva delle pagine renderizzate (`pdftoppm -r 200`), mai
  `pdftotext`/OCR — verificata riga per riga direttamente dalle immagini di pag.160-161. Tutte e 100 le voci
  `{"roll": N, "description": "..."}`, nessuna duplicata, range 1-100 completo (verificato con script Python).
  Nuovi `GameDataLoader.get_trinkets()` (lista completa) e `get_trinket_by_roll(n)` (singola voce per tiro, `None`
  se fuori range 1-100) — stesso pattern lazy-load-e-cache di `get_weapons()`/`get_pack_contents()`,
  `_ensure_equipment_file("trinkets")` riusa il meccanismo generico già esistente per le altre 6 sezioni equipment.
  Nota di esclusione in `adventuring_gear.json` aggiornata per puntare al nuovo file. **Ancora nessun collegamento
  UI** (né generatore né picker alla creazione personaggio) — solo dato trascritto e caricabile, in attesa di
  decidere con Davide se va integrato come pulsante dentro il Generatore Tesori Casuali (6) o come voce a sé nella
  navigazione della Sezione Master. `python3 -m py_compile`/test funzionale del loader puliti.
- [x] ~~**Wiring del resto di `equipment/*.json` alla UI**~~ — **✅ parzialmente risolto il 2026-07-16** (task
  #22/#23, scope confermato con Davide via `AskUserQuestion`: **solo informazioni di riferimento in sola lettura**,
  nessuna modifica allo schema DB, nessuna modifica al calcolo del peso trasportato già esistente).
  `GameDataLoader` espone già getter per tutti e 6 i file
  (`get_weapons()`/`get_weapon()`/`get_weapon_names()`/`get_armor()`/`get_armor_item()`/`get_armor_names()`/`get_adventuring_gear()`/`get_tools()`/`get_mounts_and_vehicles()`/`get_economy()`)
  — gli strumenti erano già consumati (`get_tool_names()`/`get_tool_categories()`), armi/armature erano già usate
  per l'autofill dei dialog di creazione/modifica (task #100-ish, 2026-07-16 stessa giornata) ma non ancora per la
  sola visualizzazione nelle card.
  **Implementato**: nuovo `InventarioTab._catalog_ref_line(name, kind)` — risolve il nome dell'arma/armatura nel
  catalogo (`_loader.get_weapon()`/`_loader.get_armor_item()`, case-insensitive, stessa fonte già usata
  dall'autofill) e produce una riga di sola consultazione (`"PHB: 5 mo · 1 kg"`, con `For N`/`Furtività:
  Svantaggio` aggiuntivi per le armature che li hanno) mostrata in fondo a `_weapon_card()`/`_armor_card()`, sotto
  le righe esistenti (proprietà/effetti/descrizione). Ritorna `None` — nessuna riga mostrata, nessun errore — per
  nomi non nel catalogo (armi/armature homebrew inserite a mano, o indumenti come "Abito comune"/"Costume" che non
  sono armature del Capitolo 5 per definizione, vedi task #93/#96).
  **Deliberatamente non toccato** (fuori dallo scope confermato): schema `Weapon`/`InventoryItem` (nessun nuovo
  campo persistito — il costo/peso è ricalcolato a runtime dal catalogo ad ogni render, mai salvato), calcolo del
  peso trasportato totale (resta quello già esistente, basato su `InventoryItem.weight`/`Weapon` non ha un campo
  peso proprio), contenuto reale delle dotazioni (`packs` — resta mostrato come testo, non ancora espanso in card
  separate al di fuori del già esistente meccanismo di espansione al salvataggio, task #96).
  **Verificato** con test end-to-end (DB temporaneo isolato, mai quello reale): "Ascia" (arma semplice) → `"PHB: 5
  mo · 1 kg"`; "Scudo" (armatura via `ac_bonus`, non `ac_formula`) → `"PHB: 10 mo · 3 kg"`; "Cotta di Maglia"
  (armatura pesante con requisito Forza e svantaggio Furtività) → `"PHB: 75 mo · 27.5 kg · For 13 · Furtività:
  Svantaggio"`; arma homebrew non catalogata → nessuna riga (verificato sia sulla funzione isolata sia sulla card
  completa via ricerca nell'albero controlli); "Abito comune"/"Costume" → nessuna riga spuria (non sono armature
  PHB). `_weapon_card()`/`_armor_card()` costruite end-to-end senza eccezioni in tutti i casi. `python3 -m
  compileall`/`pyflakes` puliti su `inventario_tab.py` (solo il rumore preesistente di `from config.settings import
  *`).
- [x] ~~**`bonus_proficiencies` nelle sottoclassi di `chierico.json`/`bardo.json`**~~ — **✅ risolto il 2026-07-16**
  (task #19/#20/#21). Trovato durante l'eliminazione di `tags.json` (2026-07-10): questi campi avevano ancora i
  vecchi tag `"#armature_pesanti"`/`"#armi_da_guerra_mischia"`/ecc. (stesso schema rotto già rimosso da
  `armor_proficiencies`/`weapon_proficiencies`), ed erano un campo dati completamente **non collegato a nessuna
  logica** — nessun codice li leggeva né li applicava mai al personaggio (né alla creazione né al level-up), quindi
  le competenze bonus di sottoclasse (es. Chierico Dominio della Vita → armature pesanti, Bardo Collegio del Valore
  → armatura media/scudi/armi da guerra) non venivano mai assegnate.
  **Normalizzazione dato (task #19)**: i vecchi tag `#...` sostituiti con gli stessi token bare già usati da
  `armor_proficiencies`/`weapon_proficiencies` a livello di classe (`"leggere"/"medie"/"pesanti"/"scudi"` per le
  armature, `"semplice"/"semplice_mischia"/"guerra"/"guerra_mischia"` per le armi) — stessa convenzione, nessun
  nuovo formato inventato. `chierico.json`: Dominio della Vita `['pesanti']`; Dominio della Natura `['pesanti',
  {scelta 1 abilità tra Addestrare Animali/Natura/Sopravvivenza}]`; Dominio della Tempesta `['pesanti',
  'guerra_mischia']`; Dominio della Guerra `['pesanti', 'guerra']`; Dominio della Conoscenza (già senza tag rotti)
  `[{scelta 2 abilità tra 4}]`. `bardo.json`: Collegio del Valore `['medie', 'scudi', 'guerra']`; Collegio della
  Conoscenza (già senza tag rotti) `[{scelta 3 abilità, qualsiasi}]`. Verificato che `ladro.json → Assassino`
  (`['Trucchi per il Camuffamento', 'Sostanze da Avvelenatore']`, competenze specifiche non tag armatura/arma) non
  necessitava normalizzazione, solo applicazione.
  **Core layer generico (task #20)**: nuovo `GameDataLoader.get_subclass_bonus_proficiencies(class_name,
  subclass_name)` (wrapper su `get_subclass_data()`) e, in `character_repo.py`:
  `classify_bonus_proficiency_entries(entries)` (divide una lista `bonus_proficiencies` in voci fisse pronte per il
  salvataggio e voci `{"type":"choice","count":N,"from":[...]|"any_skill"}` che richiedono una scelta del
  giocatore), `resolve_bonus_proficiency_choice_options(entry)` (risolve il pool, `"any_skill"` → tutte le 18
  abilità PHB), `_classify_bonus_proficiency_type(entry_name)` (instrada verso `proficiency_type` corretto: token
  armatura → `"armor"`, token arma → `"weapon"`, una delle 18 abilità → `"skill"`, altrimenti → `"tool"`),
  `apply_subclass_bonus_proficiencies(character_id, resolved_entries)` (salva tutte le voci risolte, idempotente
  per contenuto — a differenza di `_save_single_proficiency()`, che non ha vincolo UNIQUE sulla tabella e
  duplicherebbe ad ogni richiamo, qui serve perché la scelta sottoclasse può essere ripetuta con level-down poi di
  nuovo level-up sulla stessa sottoclasse).
  **UI creazione** (`wizard_view.py` fase Revisione, `manual_form.py` fase Scelte — Chierico è l'unica classe con
  `subclass_choice_level == 1`, quindi l'unica a mostrare questa sezione alla creazione): nuova sezione reattiva
  `subclass_bonus_col`, ricostruita ad ogni cambio del dropdown Dominio Divino (`_rebuild_subclass_bonus_col()`) —
  mostra un promemoria testuale per le voci fisse e N dropdown a mutua esclusione per le voci "choice" (stesso
  pattern già consolidato nel progetto per i trucchetti Lv.1/strumenti di classe: ogni dropdown esclude dalle
  proprie opzioni i valori scelti negli altri dropdown dello stesso gruppo, più le abilità già possedute da
  background/classe/Mezzelfo/Umano Variante). Wired nelle stesse esclusioni incrociate live già esistenti (toggle
  abilità di classe, abilità Mezzelfo, dropdown abilità Umano Variante). Validazione sia al pulsante "Continua" sia
  in difesa di profondità al salvataggio finale (nessuna scelta mancante, nessun duplicato). Salvataggio via
  `apply_subclass_bonus_proficiencies()` dopo che `char.subclass` è definitivo.
  **UI level-up** (`profilo_tab.py`, per le sottoclassi con `subclass_choice_level != 1` — Bardo/Ladro, entrambe
  Lv.3): stesso principio già stabilito il 2026-07-16 per Totem/Terreno/Mistificatore Arcano — la scelta va fatta
  nello STESSO level-up in cui si sceglie la sottoclasse, quindi la sezione (container con dropdown dinamici) è
  agganciata dal vivo al dropdown sottoclasse tramite `_compose_on_select()` (mai sovrascrive handler già
  presenti). A differenza di Totem/Terreno (solo toggle di visibilità), qui il *numero* di dropdown cambia con la
  sottoclasse, quindi l'intero blocco viene ricostruito (`_rebuild_scb_container()`) ad ogni cambio. Validazione
  contro la sottoclasse FINALE scelta (ricalcolata da `c.class_name`/`_final_subclass`, non dal solo stato dei
  dropdown già costruiti — doppio controllo per sicurezza). Salvataggio subito dopo `c.subclass =
  subclass_dd_ref[0].value`, ricalcolando fixed/choices dalla sottoclasse appena scritta.
  **Verificato** con test end-to-end (DB temporaneo isolato, mai quello reale): tutti e 6 i domini del Chierico
  creati via `wizard_view.py` e via `manual_form.py` (inclusi i 2 con scelta — Natura 1 abilità, Conoscenza 2
  abilità, entrambi con selezione esplicitamente NON di default) — competenze fisse e scelte verificate riga per
  riga contro `character_proficiencies` con il `proficiency_type` corretto; level-up Bardo Lv2→3 su entrambe le
  sottoclassi (Collegio della Conoscenza: 3 abilità scelte e salvate; Collegio del Valore: 3 competenze fisse
  salvate) e Ladro Lv2→3 su entrambe (Assassino: 2 strumenti fissi salvati; Furfante: nessuna voce spuria salvata)
  — `subclass` persistita correttamente in tutti i casi. Regressione `get_level_up_steps()` su tutte le 12 classi ×
  tutte le sottoclassi × lv2-20 (0 eccezioni). `python3 -m compileall`/`pyflakes` puliti su tutti i file toccati
  (`wizard_view.py`, `manual_form.py`, `profilo_tab.py`, `character_repo.py`, `game_data_loader.py` — solo il
  rumore preesistente di `from config.settings import *`, nessun errore genuino). Validazione JSON di
  `chierico.json`/`bardo.json` dopo la normalizzazione.
  ~~**Non affrontato, fuori scope**: i campi base-classe `armor_proficiencies`/`weapon_proficiencies`... segnalato
  qui per una futura sessione dedicata.~~ — **✅ risolto il 2026-07-16**, vedi "Note Importanti" → "Fix bug/gap
  funzionali: Indebolimento + competenze base-classe" per il changelog completo.
- [x] ~~**Level-up incantesimi per Cavaliere Mistico (Guerriero) e Mistificatore Arcano (Ladro) non
  implementato**~~ — **✅ risolto il 2026-07-15**, vedi "Note Importanti" per il changelog completo (nuova sezione
  "Fix Mistificatore Arcano/Cavaliere Mistico"). Bug report di Davide: "Il mistificatore arcano non riesce a
  visualizzare gli incantesimi, tantomeno glieli fa scegliere" — confermato che era esattamente il gap descritto
  qui sotto, esteso su conferma esplicita di Davide anche al Cavaliere Mistico (stessa identica architettura,
  stesso gap). Testo originale del TODO mantenuto sotto per riferimento storico.
  - Trovato durante l'Audit Level-Up Phase 3 (2026-07-10, task "Audit level-up: Guerriero"). Entrambe le
    sottoclassi hanno un campo `spell_progression` completo e verificato (Cavaliere Mistico riconfermato riga per
    riga contro pag.75 "Incantesimi del Cavaliere Mistico" — 100% corretto), con colonne
    `cantrips_known`/`spells_known` che crescono per livello, ma `get_level_up_steps()` in `core/level_manager.py`
    non genera MAI uno step per questo: un personaggio con queste sottoclassi non viene mai invitato a scegliere
    nuovi incantesimi/trucchetti quando sale di livello, nonostante il dato esista e sia corretto. Non è un fix
    "mordi e fuggi" come gli altri bug trovati in questa sessione perché la classe incantatrice per questi
    personaggi è concettualmente "Mago" (la lista incantesimi da usare) anche se `character.class_name` è
    "Guerriero"/"Ladro" — nessuna struttura esistente (`_SPELL_LEARN_DELTA`, gli handler SPELL_LEARN in
    `profilo_tab.py` per Bardo/Stregone/Warlock/Ranger) gestisce questo caso "classe incantesimi ≠ classe
    personaggio". Serve inoltre gestire il vincolo speciale del Cavaliere Mistico (2 dei 3 incantesimi di 1°
    livello devono essere Abiurazione o Invocazione; quelli imparati a lv8/14/20 possono essere di qualsiasi scuola
    — la scuola di ogni incantesimo dovrebbe già essere nel campo `school` di `incantesimi_mago.json` una volta
    auditato). Da progettare come intervento dedicato, non da affrontare come singolo bugfix.
- ~~**Crescita "Trucchetti Conosciuti" mai proposta al level-up (Bardo/Mago/Stregone/Warlock)**~~ — **✅ risolto il
  2026-07-11**, esteso anche a Chierico/Druido (le 6 classi con `cantrips_known_at_1` nel JSON, non solo le 4
  "know"). Bug report di Davide: "il bardo e altri incantatori imparano anche altri trucchetti a determinati
  livelli, non solo incantesimi, non mi sembra gestita questa cosa." Vedi "Note Importanti" per il changelog
  completo del fix (dati verificati visivamente dalle 6 tabelle di classe PHB, nuovo `StepType.CANTRIP_LEARN`).
- [x] ~~**Picker incantesimo specifico per Arcanum Mistico del Warlock (lv13/15/17)**~~ — **✅ implementato il
  2026-07-16**. Nuovo `StepType.ARCANUM_SPELL` in `core/level_manager.py`, esteso anche al lv11 (6° livello, prima
  non generava nemmeno il promemoria informativo — bug scoperto durante l'implementazione: la feature JSON "Arcanum
  Mistico" a quel livello produceva solo un FEATURE_AUTO col nome nudo, nessuna spiegazione del livello
  incantesimo). Nuovo dropdown in `profilo_tab.py` (ramo `ARCANUM_SPELL`), filtrato per livello ESATTO (non "fino
  a" come SPELL_LEARN) sulla lista incantesimi Warlock, con esclusione degli incantesimi già conosciuti; salvato
  come `known_spell` con lo stesso `_save_known_spell()` già usato per SPELL_LEARN/CANTRIP_LEARN (la meccanica
  "lanciabile senza slot, 1/riposo lungo" non è tracciata a parte, coerente con la semplificazione già adottata per
  tutti gli incantesimi conosciuti). La generica scansione feature (sezione 2c di `level_manager.py`) ora esclude
  "Arcanum Mistico" dal FEATURE_AUTO al lv11 per non duplicare col nuovo picker. **Verificato** con test end-to-end
  (DB temporaneo isolato): un Warlock che sale 10→11→…→17 riceve il picker esattamente ai
  lv11(6°)/13(7°)/15(8°)/17(9°), mai al lv12/14/16/18, ogni dropdown filtrato al livello incantesimo corretto e col
  vincolo di non ripetere un incantesimo già scelto; regressione `get_level_up_steps()` su tutte le 12 classi ×
  sottoclassi × lv2-20 senza eccezioni.
- [x] **Incantesimi razziali di Drow/Tiefling mai realmente utilizzabili (Magia Drow, Eredità Infernale)** ✅
  **risolto il 2026-07-16, con la progettazione dedicata già indicata qui sotto** (sezione "di razza" sempre
  visibile, CD su CAR fisso — confermato come design con Davide prima di implementare). Trovato durante l'Audit
  Risorse Razziali (2026-07-10): `get_race_resource_defaults()` tracciava già correttamente il CONTATORE di
  utilizzo (1/riposo lungo) di Luminescenza/Oscurità (Drow) e Intimorire Infernale/Oscurità (Tiefling), ma
  l'incantesimo vero e proprio non era mai consultabile/lanciabile da nessuna parte, e la tab Incantesimi si
  nascondeva del tutto per classi non incantatrici.
  **Dato aggiunto** (`elfo.json → subraces[Elfo Oscuro (Drow)] → traits[Magia Drow]` e `tiefling.json →
  traits[Eredità Infernale]`): nuovo campo strutturato `"innate_spells"` (array di `{name, cast_level,
  min_char_level, uses, ability, resource_name, note?}`) — trascrive in forma di dati la stessa prosa già presente
  e verificata nel tratto (nessun nuovo fatto di regolamento introdotto, `traits`/`resources` restano invariati).
  Copre: Drow — Luci Danzanti (trucchetto, a volontà, da lv1), Luminescenza (1°, 1/riposo lungo, da lv3), Oscurità
  (2°, 1/riposo lungo, da lv5); Tiefling — Taumaturgia (trucchetto, a volontà, da lv1), Intimorire Infernale
  (lanciato come 2° livello — upcast fisso dal tratto, annotato nel campo `note`, da lv3), Oscurità (2°, da lv5).
  **`GameDataLoader`**: nuovo `get_racial_innate_spells(race, subrace)` (legge `innate_spells` da tutti i tratti
  risolti, base+sottorazza) e `get_spell_master_entry(name)` (lookup diretto nel file master
  `incantesimi_completi.json` per nome, senza passare da una lista di classe — necessario perché un incantesimo
  innato di razza potrebbe non comparire in nessuna lista di classe).
  **`spells_view.py`**: nuova sezione "Incantesimi Razziali", **sempre visibile** quando la razza/sottorazza li
  concede — inserita PRIMA del controllo `if c.spellcasting_ability:`, quindi visibile anche per un
  Barbaro/Guerriero Drow o Tiefling. Sola lettura (nessun toggle preparazione/rimozione: sono un tratto fisso, non
  una scelta del giocatore), filtrata per `character.level >= min_char_level`, CD calcolata SEMPRE su Carisma fisso
  (`8 + char_prof_bonus(c) + get_modifier(c.cha_score)`, indipendentemente da `spellcasting_ability` della classe —
  un Barbaro Drow calcola comunque la CD su CAR, mai su FOR/COS). Ogni voce è una card cliccabile che apre un
  dialog con testo completo (tempo/gittata/durata/componenti/descrizione, risolti dal file master) e la nota di
  upcast quando presente; per gli incantesimi "1/riposo lungo" un chip "Disponibile"/"Usato (riposo lungo)"
  incrocia lo stato già tracciato in `class_resources` per nome esatto — **nessuna duplicazione della logica di
  utilizzo**: il contatore resta gestito e modificabile solo dalla tab Combattimento (unica fonte di verità),
  questa sezione si limita a renderlo leggibile insieme al testo dell'incantesimo (il gap originale).
  `SpellsView.__init__` chiama `character_repo.init_class_resources(...)` in modo difensivo (self-healing, stesso
  pattern già in uso per `sync_borrowed_spellcasting_ability`/`sync_bonus_domain_spells`) così il contatore esiste
  anche se il giocatore apre Incantesimi prima di Combattimento.
  **Verificato** con test end-to-end (DB temporaneo isolato, mai quello reale): Barbaro Drow lv.4 mostra Luci
  Danzanti+Luminescenza ma non Oscurità (sotto soglia lv5), CD calcolata correttamente (8+2+3=13); lo stesso
  personaggio salito a lv.5 mostra anche Oscurità; consumare la risorsa "Oscurità (drow)" da Combattimento
  (`update_class_resource`) e riaprire la tab Incantesimi mostra correttamente il chip "Usato (riposo lungo)";
  click sulla card apre il dialog con la descrizione integrale dell'incantesimo; Tiefling lv.5 mostra tutti e 3 gli
  incantesimi con la nota di upcast per Intimorire Infernale; regressione su tutte le altre 9 combinazioni
  razza/sottorazza (nessuna mostra la sezione, zero falsi positivi) e smoke test su tutte le 12 classi × Drow
  (nessuna eccezione). `py_compile`/`pyflakes` puliti (solo il rumore preesistente di `from config.settings import
  *`).
- [x] ~~**Picker discipline elementali per Monaco, Via dei Quattro Elementi**~~ — **✅ implementato il 2026-07-16**,
  esteso anche alla scelta INIZIALE di Lv.3 (prima assente del tutto — il monaco nasceva senza nessuna disciplina
  scelta, solo la feature testuale). Due parti:
  - **Lv.3** (scelta iniziale, dentro il blocco `SUBCLASS_CHOICE` in `profilo_tab.py`, stesso pattern di reattività
    live già usato per il fix Mistificatore Arcano/Cavaliere Mistico/Totem/Terreno — necessario perché la scelta va
    fatta nello STESSO level-up in cui si sceglie la sottoclasse "Via dei Quattro Elementi"): "Sintonia Elementale"
    viene assegnata automaticamente (fissa, gratuita, PHB) + 1 dropdown per la disciplina aggiuntiva, pool =
    discipline con `level` nullo (quelle senza soglia, disponibili da subito). Container nascosto/mostrato in base
    al valore live del dropdown sottoclasse; salvataggio condizionato alla sottoclasse FINALE scelta (un Monaco che
    sceglie "Via delle Ombre"/"Via della Mano Aperta" non riceve nessuna disciplina spuria).
  - **Lv.6/11/17** (crescita, nuovo `StepType.MONK_DISCIPLINE` in `core/level_manager.py`, sostituisce il vecchio
    promemoria informativo): dropdown "Nuova Disciplina Elementale" con pool = discipline con `level is None or
    level <= livello_attuale`, escluse quelle già conosciute (nuovo `proficiency_type="monk_discipline"`).
  - Nuova sezione "Discipline Elementali" in `profilo_tab.py → _build_talenti` (visibile solo per Monaco Via dei
    Quattro Elementi), card cliccabili con dialog descrizione + costo in ki, stesso pattern della sezione
    Metamagia.
  - **Verificato** con test end-to-end (DB temporaneo isolato, bypass Flet Page): scelta iniziale Lv.3 reattiva al
    cambio dropdown sottoclasse (Sintonia Elementale + 1 scelta salvate solo se la sottoclasse finale è "Via dei
    Quattro Elementi", zero discipline salvate per un Monaco "Via delle Ombre"); crescita Lv.6 con pool che esclude
    le 2 già note e include correttamente sia le discipline senza soglia sia le 2 con soglia esatta 6 (escludendo
    quelle con soglia 11/17 non ancora sbloccate); crescita Lv.11 con pool aggiornato di conseguenza. Regressione
    `get_level_up_steps()` su tutte le 12 classi × sottoclassi × lv2-20 senza eccezioni.
- [x] **Mezzelfo non riceve mai la scelta della terza lingua libera** ✅ **risolto il 2026-07-16** — trovato il
  2026-07-10 mentre si correggeva il bug delle lingue fisse di razza. `mezzelfo.json → languages` contiene
  `["Comune", "Elfico", {"type":"choice","count":1,"from":"any"}]` — la stessa identica struttura di `umano.json`,
  che però aveva un dropdown dedicato hardcoded solo su quel nome razza (`_review_umano_language`) in
  `wizard_view.py`/`manual_form.py`. **Fix, esattamente come suggerito nel TODO originale**: il vecchio campo di
  stato `_review_umano_language: str` è stato generalizzato in `_review_race_languages: list[str]` (entrambi i
  file, identico), con un nuovo metodo `_race_language_choice_count()` che somma tutte le entry
  `{"type":"choice","count":N}` in `get_resolved_race(razza, sottorazza)["languages"]` — nessuno special-case sul
  nome razza, copre Umano e Mezzelfo (e qualunque razza futura con la stessa struttura) dallo stesso identico
  codice. Il dropdown mostrato in "Extra razziali" ora si genera dinamicamente per `race_lang_count` slot (oggi
  sempre 1 per entrambe le razze, ma il codice supporta `count > 1` con N dropdown a mutua esclusione, stesso
  schema già usato per i trucchetti/strumenti di classe). **Bug distinto trovato e corretto nello stesso
  passaggio** (non nel codice originale Umano-only, introdotto solo generalizzando): il pool di opzioni del
  dropdown escludeva prima SOLO "Comune", corretto per l'Umano (unica lingua fissa) ma sbagliato per il Mezzelfo,
  che ha anche "Elfico" fisso — senza la correzione, il dropdown avrebbe offerto "Elfico" come "3ª lingua a
  scelta", duplicando una lingua già posseduta. Fix: il pool ora esclude tutte le lingue fisse lette da
  `get_resolved_race(...)["languages"]` (le stringhe, non le entry `{"type":"choice"}`), non solo "Comune". La
  sezione lingue del background (`_rebuild_lang_tool_col`) già escludeva `_review_umano_language`; generalizzata
  per escludere tutte le voci di `_review_race_languages`. Salvataggio (`_on_save`) generalizzato allo stesso modo:
  loop su `_review_race_languages` invece del singolo campo, con lo stesso dedup `lang_seen` già in uso.
  **Verificato** con test end-to-end (DB temporaneo isolato, mai quello reale) in entrambi i file: dropdown "Lingua
  aggiuntiva (tratto razziale)" presente SOLO per Umano/Mezzelfo su tutte le 9 razze (regressione confermata, zero
  falsi positivi); per il Mezzelfo il pool esclude correttamente sia "Comune" sia "Elfico"; selezionare una lingua
  (es. "Draconico") la rimuove immediatamente, dal vivo, anche dalle checkbox del background (testato con
  "Accolito", 2 lingue a scelta) — nessuna doppia spesa dello stesso slot; salvataggio end-to-end verificato:
  Mezzelfo + Accolito produce esattamente 5 lingue distinte su `character_proficiencies` (Comune, Elfico,
  Draconico, + 2 di background), nessun duplicato. `py_compile`/`pyflakes` puliti su entrambi i file.
- [x] **`spells_view.py._PREP_HALF` includeva erroneamente il Ranger tra i "mezzo preparatori"** ✅ **risolto il
  2026-07-11** — trovato il 2026-07-11 (task "Add initial prepared spell choice for Chierico/Druido/Paladino")
  mentre si decideva quali classi dovessero ricevere la nuova scelta di incantesimi preparati iniziali alla
  creazione, poi confermato da Davide con il testo del manuale ("Un ranger conosce due incantesimi di 1° livello a
  sua scelta... quando un ranger acquisisce un livello, può scegliere un incantesimo da ranger che conosce e
  sostituirlo con un altro"). `_PREP_HALF: set[str] = {"paladino", "ranger"}` applicava al Ranger la formula "mod.
  caratteristica + metà livello, min 1" come tetto massimo di incantesimi preparabili contemporaneamente — ma il
  Ranger non prepara nulla ogni giorno, **conosce** una lista fissa di incantesimi sempre pronti, esattamente come
  Bardo/Stregone/Warlock. **Fix**: `"ranger"` spostato da `_PREP_HALF` a `_KNOW_CLASSES` in `spells_view.py` (ora
  `_PREP_HALF = {"paladino"}`, `_KNOW_CLASSES = {"bardo", "ranger", "stregone", "warlock"}`), docstring di modulo e
  commenti aggiornati con la citazione del manuale. **Verificato** con test end-to-end (DB temporaneo isolato): un
  Ranger Lv.5 Sag 14 con 3 incantesimi conosciuti tutti preparati ora ha `_calc_max_prepared() is None` (nessun
  tetto, prima avrebbe dato 4) e tutti e 3 restano `is_prepared=True` senza essere sbloccati/toccati dal cambio; il
  Paladino (rimasto in `_PREP_HALF`) continua a restituire correttamente il tetto calcolato dalla formula
  (verificato Lv.5 Car 14 → 4). `py_compile`/`pyflakes` puliti (solo il rumore preesistente di `from
  config.settings import *`, nessun errore genuino).
  - **Gap più ampio scoperto nello stesso momento, NON ancora implementato**: il testo del manuale incollato da
    Davide rivela una seconda meccanica — "quando un ranger acquisisce un livello, può scegliere un incantesimo da
    ranger che conosce e **sostituirlo** con un altro" — che oggi non esiste da nessuna parte nel codice. Lo step
    `SPELL_LEARN` in `profilo_tab.py` (ramo `else`, righe ~1699-1733) lascia scegliere solo tra incantesimi NON
    ancora conosciuti (`s.get("name") not in _known_set`), mai la sostituzione di uno già posseduto — quindi un
    giocatore può solo accumulare incantesimi, mai scambiarli. Verificato che questa stessa frase di "sostituzione"
    compare, con lo stesso identico schema testuale, anche in `stregone.json` e `warlock.json` (entrambi già
    auditati). **Curiosità del Bardo risolta lo stesso giorno**: Davide ha incollato anche il testo completo della
    feature "Incantesimi" del Bardo, confermando che la clausola di sostituzione esiste identica pure per questa
    classe ("quando un bardo acquisisce un livello, può scegliere un incantesimo da bardo che conosce e sostituirlo
    con un altro..."). `bardo.json → feature "Incantesimi"` è stata quindi riscritta per includere il testo
    completo (prima conteneva solo le due frasi di formula CD/attacco, senza la parte narrativa su incantesimi
    conosciuti/appresi/sostituibili — un'omissione reale, non un'assenza nel manuale). Il testo aggiunto conferma
    anche, con fonte primaria diretta, il valore `spells_known_at_1: 4` già presente in `bardo.json` (in precedenza
    ottenuto per calcolo indiretto, vedi nota task #74 — ora riscontro testuale esatto: "Un bardo conosce quattro
    incantesimi di 1° livello a sua scelta"). **Conclusione**: la meccanica di sostituzione è confermata universale
    a tutte e 4 le classi "know" (Bardo, Ranger, Stregone, Warlock), nessuna esclusa. Implementarla richiederebbe
    una nuova UI dedicata (dropdown "sostituisci quale incantesimo conosciuto" + dropdown "con quale nuovo
    incantesimo", entrambi filtrati per livello ≤ slot posseduti) in aggiunta, non al posto, dell'apprendimento di
    nuovi incantesimi via `_SPELL_LEARN_DELTA` — resta un TODO, non implementato per scelta esplicita finché Davide
    non conferma di volerlo ora.
- [x] **Talenti (feats) che concedono competenze/PF/bonus passivi non erano collegati a nessuna logica** ✅
  **risolto il 2026-07-16** — Davide ha chiesto verifica se i talenti che modificano competenze/abilità venissero
  applicati correttamente. Analisi di tutti e 42 i talenti in `feats.json` ha trovato 8 talenti con effetti
  meccanici mai implementati, oltre a `ability_bonus`/`other_bonuses` (già gestiti da tempo): **Corazze
  Leggere/Medie/Pesanti** (competenza armatura, Medie include anche Scudi), **Maestro d'Armi** (4 armi a scelta),
  **Abile** (3 tra abilità/strumenti a scelta), **Linguista** (3 lingue a scelta), **Lottatore da Taverna**
  (competenza "Armi Improvvisate", fissa), **Resiliente** (competenza al tiro salvezza della stat scelta — mancava
  solo questo pezzo, il +1 caratteristica era già gestito), **Robusto** (+2 PF max per livello, cumulativo),
  **Osservatore** (+5 Percezione e Indagare passivi). Nessuno di questi produceva alcun effetto reale sul
  personaggio: il talento veniva salvato come riga "feat" ma senza mai toccare `character_proficiencies`
  (competenze), `hp_max` (Robusto) o alcuna sezione UI (Osservatore).
  **Schema dati (`feats.json`)**: nuovi campi generici, applicabili a qualunque talento futuro senza altro codice —
  `proficiency_grants` (lista di `{"type":"fixed","proficiency_type":...,"name":...}` per competenze automatiche, o
  `{"type":"choice","proficiency_type":...,"count":N}` per scelte del giocatore; `proficiency_type` può essere
  `"skill"`, `"tool"`, `"skill_or_tool"` — Abile può scegliere liberamente tra abilità e strumenti — `"weapon"`,
  `"language"`, `"armor"`), `ability_bonus.grants_save_proficiency: true` (Resiliente: competenza nel TS della
  stessa stat scelta per il bonus), `hp_bonus_per_level` (Robusto: `2`, stesso principio "ricalcola il totale per
  livello" già usato per `get_permanent_class_hp_bonus`), `passive_bonuses` (Osservatore:
  `{"perception":5,"investigation":5}`, dict libero per bonus passivi futuri). Nessun nome/valore inventato: dati
  già presenti nella descrizione testuale di ciascun talento (verificata contro il manuale in una sessione
  precedente), qui solo resi machine-readable.
  **`config/settings.py`**: nuova `get_feats_permanent_hp_bonus(feat_names, level) -> int` — stesso pattern
  "categoria A" già stabilito per `get_permanent_class_hp_bonus()`: somma `hp_bonus_per_level` di tutti i talenti
  posseduti che hanno quel campo e restituisce il **totale accumulato** al livello indicato (non un delta) — il
  chiamante calcola sempre `nuovo_totale - vecchio_totale`. Import locale di `game_data` per evitare un ciclo di
  import.
  **`data/repositories/character_repo.py`**: `resolve_feat_proficiency_choice_pool(proficiency_type)` (risolve il
  pool disponibile per ciascun tipo: skill→18 abilità PHB, tool→`get_all_tool_names()` nuovo in `GameDataLoader`,
  skill_or_tool→unione, weapon→`get_weapon_names()`, language→`LANGUAGES`);
  `apply_feat_proficiency_grants(character_id, feat_name, choice_values, save_ability_key)` — applica sia le voci
  fisse sia le scelte, più l'eventuale competenza al TS, **idempotente** (controlla `(proficiency_type,name)` già
  esistenti prima di inserire, stesso principio di `apply_subclass_bonus_proficiencies()`) e ritorna la lista delle
  competenze **realmente nuove** (non quelle già possedute per altra via, es. già concesse dalla classe) — questa
  lista è quella che va scritta nella "ricevuta" `bonus_data`, altrimenti rimuovere il talento cancellerebbe anche
  una competenza posseduta per un motivo indipendente; `get_feat_names_at_level(character_id, level)` — query SQL
  diretta (il dataclass `CharacterProficiency` non espone `level_obtained`) per trovare i talenti presi esattamente
  a un dato livello, usata dal level-down.
  **Reversibilità**: `undo_level()` esteso per leggere `bonus_data["granted_proficiencies"]` di ogni talento/ASI
  rimosso e cancellare esattamente quelle righe (nessun'altra); `remove_feat_with_bonuses()` (rimozione manuale da
  checkbox house-rule) esteso allo stesso modo, più il calcolo e l'applicazione autonoma del delta HP per talenti
  con `hp_bonus_per_level` (qui non c'è un chiamante esterno che lo precalcola, a differenza di `do_level_down`,
  quindi la funzione lo gestisce da sola leggendo `characters.level/hp_max` direttamente).
  **UI, 3 punti di scelta** (stesso pattern ovunque: N dropdown a mutua esclusione, si ricostruiscono ad ogni cambio talento):
  - `profilo_tab.py`, ASI del level-up: nuovi widget `feat_prof_dds`/`feat_prof_col`/`feat_prof_fixed_text`,
    ricostruiti da `on_feat_select()` quando cambia il talento scelto; validazione in `do_level_up` (completezza +
    no-duplicati); salvataggio cattura `_feats_before_lu`/`_feats_after_lu` per calcolare il delta HP di Robusto
    con la formula "totale a nuovo livello − totale a vecchio livello"; `_on_level_down_click` fa lo speculare
    (calcola il delta HP di Robusto DA RIMUOVERE prima che `undo_level()` cancelli la riga del talento, leggendo
    `get_feat_names_at_level()`).
  - `manual_form.py`/`wizard_view.py`, sezione Umano Variante (il talento scelto come tratto razziale, non da ASI):
    stessa struttura dropdown, stessa validazione (`_scelte_validation_error()`/`_review_validation_error()` +
    difesa in profondità al salvataggio), stesso calcolo HP (`get_feats_permanent_hp_bonus([talento], char.level or
    1)`, applicato prima del salvataggio finale del personaggio).
  - `esplorazione_tab.py` (Osservatore, sola lettura): `_build()` somma `passive_bonuses` di tutti i talenti
    posseduti in `self._feat_passive_perception_bonus`/`self._feat_passive_investigation_bonus` (mai hardcoded il
    nome "Osservatore" — qualunque futuro talento con lo stesso campo funziona automaticamente);
    `_section_percezione()` esteso con questo bonus; nuova `_section_indagare_passiva()` (prima non esisteva ALCUNA
    sezione "Indagare Passivo" in nessuna tab — creata da zero, sola lettura, nessun override manuale come invece
    esiste per Percezione Passiva).
  **Verificato** con una batteria di test end-to-end guidati attraverso i veri closure Flet (non solo le funzioni
  di repository in isolamento) — un `FakePage` minimale (`show_dialog`/`pop_dialog`/`update`) pilota il vero
  `AlertDialog` prodotto da `_on_level_up_click`/`_on_level_down_click`/il dialog "✎ Modifica talenti",
  localizzando i controlli reali (RadioGroup/Dropdown/Checkbox) con una scansione ricorsiva dell'albero e
  invocandone `on_change`/`on_select`/`on_click` esattamente come farebbe un click utente, poi verificando lo stato
  risultante sul DB (mai quello reale, sempre `tempfile.mkdtemp()` + `HOME` isolato):
  - **Level-up → talento** (8 scenari, uno per talento): Abile (3 scelte skill/tool), Maestro d'Armi (4 armi),
    Linguista (3 lingue), Corazze Leggere (armatura fissa), Resiliente (TS fisso sulla stat scelta), Robusto (HP:
    30→35 base level-up, poi 30→43 con Robusto = +8 per il salto 3→4 dato `2×livello`), Osservatore (nessuna
    proficiency, solo bonus passivo verificato separatamente), Lottatore da Taverna (arma fissa "Armi
    Improvvisate") — tutti e 8 salvano correttamente `character_proficiencies` coi tipi giusti e la riga "feat" con
    `bonus_data`.
  - **Level-up → level-down, round-trip completo** (6 scenari): Maestro d'Armi, Robusto, Abile, Linguista, Corazze
    Medie, Resiliente — ciascuno sale di 1 livello con il talento, poi scende di nuovo tramite il vero dialog di
    conferma "Scendi a Lv.N" (`dlg.actions[1].on_click`); in tutti e 6 i casi livello, HP max e l'intero set di
    `character_proficiencies` tornano **esattamente** allo stato pre-level-up (0 righe residue, HP tornato a 30).
  - **Rimozione via checkbox house-rule** (3 scenari): Robusto (HP 44→36, il +8 del talento sparisce lasciando solo
    il +6 base del level-up, che NON viene toccato — corretto, la checkbox rimuove solo il talento, non l'intero
    livello), Corazze Leggere e Maestro d'Armi (tutte le competenze concesse spariscono insieme al talento, nessuna
    riga orfana).
  - **Regressione generale**: `get_level_up_steps()` rieseguito su tutte le 12 classi × tutte le sottoclassi ×
    livelli 2-20 (988 combinazioni) — 0 eccezioni; `python3 -m compileall` sull'intero albero sorgente (esclusi
    `build/`/`.venv/`) — 0 errori; `pyflakes` sull'intero albero — 0 errori genuini (solo il rumore noto di `from
    config.settings import *` più un `f-string is missing placeholders` preesistente e non in scope in
    `combattimento_tab.py`, già segnalato in una nota precedente).
  - **Non testato con un vero client Flet** (solo per revisione di codice attenta, essendo lo stesso identico
    pattern già verificato end-to-end sopra): il ramo di salvataggio Umano Variante in
    `manual_form.py`/`wizard_view.py` — la sequenza applica ability_bonus/other_bonuses, poi
    `apply_feat_proficiency_grants()`, poi salva la riga "feat" con `bonus_data["granted_proficiencies"]`, poi
    applica il delta HP di Robusto e chiama `character_repo.update(char)`; stesso ordine e stessa logica del
    percorso ASI già testato, nessuna discrepanza trovata nella lettura del codice.

- **Bug report di Davide (2026-07-17) — 9 punti su Abilità Speciali, effetti magici armatura, calcolo tiro per
  colpire, competenze varie in Profilo.** Testo del report (sintetizzato, screenshot allegato di una card "ABILITÀ
  SPECIALI" con descrizione troncata a "…"):
  1. Descrizioni Abilità Speciali completamente leggibili (erano troncate a 90 caratteri + "…", solo prima riga).
  2. Effetti speciali di armature/scudi magici leggibili in Combattimento, "come già fatto con le armi" (mancava del tutto una sezione armatura equipaggiata in Combattimento).
  3. Calcolo automatico del tiro per colpire dell'arma equipaggiata = caratteristica (For/Des, o scelta del player
     per armi Accurate) + bonus competenza (se competente) + bonus magico dell'arma (anche negativo, arma
     maledetta).
  4. Verifica/implementazione applicazione del bonus/malus di competenza alle armi (non era applicato da nessuna parte — `attack_bonus` esisteva ma non veniva mai sommato a nulla).
  5. In Profilo, sotto la tabella abilità/TS, mostrare TUTTE le altre competenze possedute (lingue, strumenti, veicoli, giochi), non solo armi/armature.
  6. Rendere modificabile (aggiunta/eliminazione) l'intera sezione competenze con tendina di autofill dal catalogo PHB, MA sempre con possibilità di compilazione completamente manuale.
  7. Bug: descrizione arma/armatura poteva uscire dai margini in web (overflow orizzontale).
  8. Domanda aperta: effetti come Furia del Barbaro causano Indebolimento — già automatizzato? — ~~Non
     implementato, in attesa di risposta esplicita di Davide~~ **✅ risolto il 2026-07-19**, vedi voce dedicata
     "Frenesia automatica (Berserker) + Stile di Combattimento/Suppliche Occulte in Combattimento" più sotto.
  9. Solo discussione (non implementazione): dove dovrebbero vivere Stile di Combattimento/Suppliche Occulte (oggi
     solo in Profilo, ma con effetto in combattimento)? — ~~Non implementato~~ **✅ risolto il 2026-07-19** (Davide
     ha confermato "solo consultazione in Combattimento", stesso identico pattern già usato per Abilità di
     Classe/Tratti di Razza — la scelta resta unicamente in Profilo), vedi voce dedicata più sotto.

  Prima di implementare i punti 3-6 (scelte architetturali vere, non semplici bugfix) ho posto 4 domande via `AskUserQuestion`; risposte di Davide:
  - **Calcolo attacco**: "Automatico + override manuale, ma nella creazione arma deve essere previsto un bonus al
    tiro per colpire e il bonus danno" (il campo `attack_bonus`/`damage_bonus` già esisteva, confermato di
    mantenerlo come componente magico del calcolo).
  - **Arma Accurata**: "Automatico con il modificatore più alto ma sempre con la possibilità di scegliere per il player".
  - **Competenza arma**: "l'arma anche creata a mano è comunque di un certo tipo, quindi si fa il controllo sul
    tipo, con possibilità di competenza manuale messa dal giocatore solo su quell'arma, esempio arma magica che
    dice che si è automaticamente competenti in quell'arma".
  - **Sede competenze**: "Tutto in Profilo (consigliato)".

  **Punti 1-2 — descrizioni complete** (`combattimento_tab.py`/`esplorazione_tab.py → _custom_ability_row()`):
  rimossa la troncatura a 90 caratteri/prima riga (era duplicata identica in entrambi i file, bug mai notato perché
  le abilità custom introdotte il 2026-07-16 erano ancora tutte brevi nei test). Ora mostra
  `ab.description.strip()` per intero, `ft.Text(..., no_wrap=False)` implicito (comportamento di default già
  corretto, il problema era solo il troncamento a monte).

  **Punto 2 — sezione Armatura/Scudo Equipaggiati in Combattimento** (nuova, non esisteva):
  `CombattimentoTab.__init__` carica `self._armor_items = [it for it in character_repo.get_inventory(character.id)
  if it.category == "armor" and it.is_equipped]`; nuova `_section_armor()` (stesso stile visivo di
  `_section_weapons()`) mostra per ogni armatura/scudo equipaggiato: nome, badge CA (`ca_value`), tipo
  (`_ARMOR_TYPE_LABELS`, es. "pesante"→"Pesante"), ed **effetti magici per intero** (`item.effects`, mai mostrato
  prima in nessuna sezione di Combattimento — solo in Inventario, e lì solo come badge senza testo). `_refresh()`
  ricarica `self._armor_items` in sync con `self._weapons`/`self._profs`.

  **Punto 3+4 — nuovo `core/weapon_calculator.py`** (modulo puro, no Flet, stesso principio di
  `wizard_engine.py`/`level_manager.py`/`equipment_manager.py`): `AttackContext` (vista minima di un'arma),
  `resolve_weapon_ability()` (regola PHB Cap.9/Cap.5: mischia→Forza; distanza, proprietà "Munizioni"→Destrezza;
  "Lancio" da mischia→stessa caratteristica della mischia, quindi Forza salvo sia anche Accurata; "Accurata"→scelta
  libera, default il modificatore più alto), `is_weapon_proficient()` (vero se: `proficiency_override` esplicito
  sull'arma, oppure il nome esatto dell'arma è tra le competenze possedute, oppure la categoria "semplice"/"guerra"
  dell'arma lo è), `compute_attack_total()` (mod. caratteristica + bonus competenza se competente + `attack_bonus`
  magico, oppure `attack_override_value` se `attack_total_override` è attivo — quest'ultimo ha sempre precedenza
  assoluta, utile per casi PHB non modellabili come un'arma maledetta con malus fisso indipendente dalla
  caratteristica), `compute_damage_formula()` (stessa caratteristica dell'attacco + `damage_bonus` magico + tipo di
  danno — **incluso il modificatore caratteristica nel danno**, non richiesto esplicitamente da Davide ma corretto
  per PHB e necessario perché la card mostrava da sempre solo dado+bonus magico, mai il modificatore).

  **Modello dati** (`data/models.py → Weapon`): 5 nuovi campi — `weapon_category: str = ""`
  ("semplice"|"guerra"|"", **sempre richiesto anche per armi homebrew**, coerente con la risposta di Davide),
  `proficiency_override: bool = False`, `finesse_ability: str = ""` (""=automatico|"str"|"dex"),
  `attack_total_override: bool = False`, `attack_override_value: int = 0`. Colonne aggiunte via `_add_column()`
  idempotenti in `data/database.py → _migrate()`.
  `character_repo.get_weapons()`/`create_weapon()`/`update_weapon()` estesi per leggere/scrivere tutti e 5 (lista
  colonne INSERT/SET + tupla parametri, stesso pattern già consolidato — e stesso tipo di bug già capitato in
  passato con `dragon_ancestry`/`fighting_style` se dimenticato, verificato con test di round-trip dedicato che
  nessuno dei 5 campi vada perso).

  **UI Inventario** (`inventario_tab.py → _open_weapon_dialog()`): nuovi controlli — `category_dd` (Dropdown
  Semplice/Guerra/non specificata), `prof_override_cb` (Checkbox "Competenza garantita da quest'arma"),
  `ability_dd` (Dropdown Automatico/Forza/Destrezza, per Accurate), `atk_override_cb` + `f_atk_override_val`
  (Checkbox+TextField per il totale manuale). Il dropdown "Tipo (autoriempi da catalogo PHB)" già esistente ora
  autoriempie anche `category_dd` da `data.get("category")` del catalogo `equipment/weapons.json`.
  `_weapon_card()`: badge rietichettati "ATT"→"BONUS ATT."/"DANNO"→"BONUS DANNO" (per non confondere il bonus
  grezzo inserito con il totale calcolato, che si vede solo in Combattimento) e aggiunta la visualizzazione per
  intero di `w.magic_description` (prima solo un badge "magica" senza testo — stesso identico problema del punto
  1/2, replicato qui per l'arma).

  **UI Combattimento** (`combattimento_tab.py → _section_weapons()`): `weapon_prof_names` costruito da
  `self._profs` (competenze tipo "weapon", nomi in minuscolo); nuova `_ctx(w)` costruisce l'`AttackContext`;
  `_atk_str(w)` ritorna `(display, tooltip)` — il badge mostra il totale con segno (es. "+7"), il tooltip il
  breakdown completo ("For +3, Comp. +3, Magico +1" o "Override manuale: +7 (calcolo automatico sarebbe +6)" se
  `attack_total_override`); `_dmg_str(w)` ora usa `compute_damage_formula()`.

  **Punto 7 — overflow orizzontale in web**: causa confermata (stesso bug Flet già documentato in questo file —
  "EXPAND=True su Column dentro Row dentro ListView → crash silenzioso") applicato al contrario:
  `_weapon_card()`/`_armor_card()` in `inventario_tab.py` usavano `ft.Column(content_rows, spacing=4)` diretto
  dentro una `Row`, senza vincolo di larghezza — su schermi stretti (web) il testo lungo (descrizione
  magica/effetti) spingeva la card oltre il bordo invece di andare a capo. Fix: wrappato in
  `ft.Container(content=ft.Column(content_rows, spacing=4), expand=True)` — stesso pattern "sicuro" già stabilito
  nel progetto per questo genere di bug, applicato in entrambe le card.

  **Punti 5+6 — sezione unificata "Altre Competenze" in Profilo, editing centralizzato**: nuova
  `ProfiloTab._section_altre_competenze()` (`proficiency_type in ("language","tool")`, mostra tutte le
  lingue/strumenti/veicoli/giochi posseduti con icona distinta lingua/strumento e indicatore Maestria), inserita in
  `_build()` subito dopo "Competenze Armatura e Armi" (già esistente da una sessione precedente, anch'essa ora con
  lo stesso pulsante "+ Aggiungi").

  **Dialog generico "Aggiungi Competenza"** (`ProfiloTab._open_add_competenza_dialog(default_type)`), riusabile per
  tutti e 4 i tipi (`_COMPETENZA_TIPI`: Lingua/Strumento-Veicolo-Gioco/Arma/Armatura) — stesso pattern già
  stabilito nel progetto per il dialog Arma/Armatura di Inventario: dropdown "Tipo" → dropdown "Suggerimenti dal
  catalogo" (autoriempie il campo Nome alla selezione, tramite `_competenza_catalog_options(tipo)`: lingue da
  `LANGUAGES`, strumenti da `GameDataLoader.get_all_tool_names()` + 2 voci fisse "Veicoli (terrestri)"/"Veicoli
  (acquatici)" (dato dal testo di `equipment/mounts_and_vehicles.json → rules.competenza_in_un_veicolo`, il PHB
  concede competenza per categoria ampia non per singolo modello), armi da `get_weapon_names()` + le 2 categorie
  "semplice"/"guerra", armature dagli stessi token già usati da `_ARMOR_TOKEN_LABELS`) → campo Nome **sempre
  editabile a mano**, anche senza selezionare nulla dal catalogo (opzione "— nessuno, compila a mano —" sempre in
  cima alla lista). Checkbox Maestria mostrata solo per tipo "tool" (Perizia non ha senso per lingue/armi/armature
  in questo contesto generico).

  **Deduplica manuale obbligatoria** (`character_proficiencies` **non ha un vincolo UNIQUE nello schema DB** —
  `_save_single_proficiency()` usa `INSERT OR IGNORE`, ma senza UNIQUE quella clausola non deduplica nulla,
  inserirebbe comunque una riga identica): il dialog controlla `any(p.proficiency_type == ptype and
  p.name.strip().lower() == name.lower() for p in self.proficiencies)` PRIMA di salvare, mostrando un errore inline
  se già presente — verificato esplicitamente con un test che dimostra il comportamento "non deduplicante" di
  `_save_single_proficiency()` da sola, a conferma che il controllo lato dialog è necessario e non ridondante.

  **`_on_delete_proficiency()`**: `_TIPO_LABELS` esteso con `"language": "lingua"` (prima mancava, sarebbe ricaduta sul default generico "competenza").

  **Esplorazione resa sola lettura** (`esplorazione_tab.py`, coerente con la risposta di Davide "Tutto in
  Profilo"): rimossi i pulsanti "+ Aggiungi" dagli header di Lingue/Strumenti, rimossi gli `IconButton` di
  rimozione dalle righe, rimossi interamente `_on_add_lingua()`/`_on_add_strumento()` (dialog con TextField
  completamente libero, nessun catalogo — superati dal nuovo dialog centralizzato) e il metodo locale
  `_on_delete_proficiency()` (nessun chiamante residuo nel file dopo la rimozione dei due dialog — verificato via
  grep prima di cancellarlo). Rimosso anche l'import ormai inutilizzato `from data.database import get_connection`.
  Docstring di modulo e commenti di sezione aggiornati per riflettere lo stato sola-lettura e rimandare a
  `ProfiloTab._section_altre_competenze`.

  **Verificato** con una batteria di test end-to-end (DB temporaneo isolato via `tempfile.mkdtemp()` + `HOME`
  separato, mai il DB reale di Davide — installato `flet==0.85.3`/`pyflakes` nel sandbox di verifica, non presenti
  di default):
  - **`core/weapon_calculator.py` in isolamento** (14 assert): mischia→Forza non competente (totale = solo mod.
    caratteristica), competenza per categoria "guerra" (+bonus competenza), arma a distanza (proprietà
    "Munizioni")→Destrezza, arma "Accurata" sceglie automaticamente il modificatore più alto in entrambe le
    direzioni (For>Des e Des>For), scelta esplicita `finesse_ability` rispettata anche quando non è la più alta,
    `proficiency_override` forza competenza anche senza alcuna competenza reale posseduta (caso arma magica
    senziente), `attack_total_override` ha sempre precedenza sul calcolo automatico, `compute_damage_formula()`
    include correttamente il modificatore caratteristica nella stringa risultante.
  - **Round-trip DB** dei 5 nuovi campi `Weapon` via `create_weapon()`→`get_weapons()`→`update_weapon()`→`get_weapons()`.
  - **Smoke test**: tutte le 12 classi PHB × 4 tab
    (`ProfiloTab`/`CombattimentoTab`/`EsplorazioneTab`/`InventarioTab`) istanziate con un personaggio Lv.5 dotato
    di arma magica equipaggiata, armatura magica equipaggiata, un'abilità custom con descrizione lunga, e una
    competenza "tool" extra — **0 eccezioni**.
  - **Verifica approfondita del contenuto renderizzato** (scansione ricorsiva dell'intero albero controlli, non
    solo assenza di eccezioni): per un Guerriero Lv.5 (For 16/mod+3, Des 14/mod+2, competente "guerra", Spada Lunga
    Accurata +1/+1) il totale attacco mostrato in Combattimento è **esattamente "+7"** (For scelta come il
    modificatore più alto tra For/Des per l'Accurata, +3 mod, +3 bonus competenza lv5, +1 magico — calcolato a mano
    e confrontato); la descrizione magica dell'arma e gli effetti dell'armatura compaiono per intero sia in
    Combattimento sia in Inventario (nessun troncamento); la descrizione lunga dell'abilità custom compare per
    intero in Combattimento; la sezione "Altre Competenze" di Profilo mostra correttamente lo strumento aggiunto.
  - **Pilotaggio end-to-end del vero dialog "Aggiungi Competenza"** (FakePage minimale
    `show_dialog`/`pop_dialog`/`update`, stesso pattern già stabilito nel progetto per testare dialog Flet senza un
    vero client): (1) selezione "Draconico" dal catalogo lingue → autofill del campo Nome → salvataggio → riga
    persistita correttamente e dialog chiuso; (2) tentativo di aggiungere di nuovo "Draconico" → bloccato con
    messaggio "già presente", dialog resta aperto, **nessuna riga duplicata creata** (conferma diretta che il
    controllo di deduplica lato dialog funziona, a differenza di `_save_single_proficiency()` da sola); (3)
    compilazione completamente manuale di uno strumento mai presente nel catalogo (mai selezionato dal dropdown) →
    salvata correttamente, a conferma che l'editing libero resta sempre disponibile come richiesto; (4)
    eliminazione via il nuovo pulsante "Rimuovi" → riga cancellata dal DB.
  - **Regressione**: `python3 -m py_compile` su tutti gli 8 file toccati (`profilo_tab.py`, `inventario_tab.py`,
    `combattimento_tab.py`, `esplorazione_tab.py`, `core/weapon_calculator.py`, `character_repo.py`, `database.py`,
    `models.py`) — 0 errori; `pyflakes` sugli stessi file — 0 errori genuini (solo il rumore noto di `from
    config.settings import *` più lo stesso `f-string is missing placeholders` preesistente in
    `combattimento_tab.py`, non toccato, non in scope).
  - **Punti 8 e 9 esplicitamente NON implementati** — restano come domande aperte in attesa di risposta/conferma di Davide, nessuna modifica al codice per questi due punti.

- **Scelta dotazioni equipaggiamento — da RadioGroup a `CardPicker` (2026-07-17)** — richiesta di Davide
  (verbatim): "rendere come la scelta degli incantesimi la scelta delle dotazioni quando si crea il personaggio, in
  modo da vedere cosa ti concede quella dotazione quando il player sceglie, in pratica quando scelgo voglio vedere
  cosa mi dà la dotazione scelta". Stesso principio già stabilito il 2026-07-16 per
  incantesimi/trucchetti/talenti/Suppliche Occulte/Metamagia/Stile di Combattimento: click-e-rivela in un solo
  gesto, niente più bisogno di aprire una descrizione a parte.
  **Nuovi helper condivisi in `ui/widgets.py`** (stesso principio DRY già seguito per
  `spell_card_options()`/`feat_card_options()`/ecc. — la UI chiamante resta duplicata per convenzione di
  file-mirroring del progetto, ma la logica pura di formattazione vive in un solo posto):
  - `format_equipment_item_body(item, loader)` — per una singola voce di equipaggiamento, se è il nome di una
    Dotazione riconosciuta (`loader.get_pack_contents(name)`, già esistente dall'11/07) ritorna il suo contenuto
    espanso riga per riga (`"Contenuto di \"Dotazione da Avventuriero\": \n• Zaino\n• Corda di Canapa (15
    metri)\n..."`); stringa vuota per qualunque altro oggetto (incluse le voci `weapon_choice`, che non hanno un
    corpo descrittivo qui).
  - `equipment_option_card_options(options, loader)` — converte una lista di opzioni A/B (ciascuna una lista di
    item) nel formato `CardPicker.options`: titolo = elenco compatto degli oggetti dell'opzione (es. "Cotta di
    Maglia  +  Scudo", con "Qualsiasi arma guerra ×1" per le voci `weapon_choice`), corpo = concatenazione dei
    contenuti dotazione espansi di tutti gli item di quell'opzione (vuoto se nessuno degli item è una Dotazione).
  **`wizard_view.py`/`manual_form.py`, identico in entrambi i file**:
  - Sezione "Oggetti garantiti" (item fissi): ogni voce che risolve come Dotazione ora mostra sotto di sé, in un
    `ft.Container` indentato, il contenuto espanso via `format_equipment_item_body()` — prima il nome della
    dotazione appariva da solo, senza alcun modo di sapere cosa contenesse senza consultare il manuale.
  - Sezione "Scelte A/B": il vecchio `ft.RadioGroup` (con le funzioni locali `_fmt()`/`_make_radio_change()`)
    sostituito da un `CardPicker` costruito da `equipment_option_card_options(opts, _loader)` — selezionare una
    card mostra subito il contenuto delle eventuali Dotazioni incluse in quell'opzione, inline, senza un secondo
    gesto. La logica sottostante di `chosen_idx` e dei Dropdown arma per le voci `weapon_choice` (mostrati sotto il
    CardPicker quando l'opzione corrente ne contiene) resta identica a prima — solo il controllo di selezione è
    cambiato, non la struttura dati né il salvataggio finale.
  **Verificato** con test end-to-end (bypass `__init__`, mai un vero client Flet — stesso pattern
  "TrackedCardPicker" già usato per verificare gli altri redesign CardPicker di questo progetto): tutte le 12
  classi PHB con scelte A/B (Chierico/Mago/Guerriero/Bardo/Stregone/Warlock/Ladro/Paladino/Ranger/Monaco) producono
  almeno un `CardPicker` in `manual_form.py`, con "Contenuto di" presente nell'albero controlli renderizzato per
  ogni classe; le prime 3 classi ri-verificate anche in `wizard_view.py` con lo stesso esito; le 2 classi con
  Dotazione fissa (non a scelta — Druido, Barbaro) mostrano correttamente il contenuto espanso senza alcun
  CardPicker; click simulato su una card diversa dalla corrente (`picker.on_select(ev)`) aggiorna correttamente
  `choice["chosen_idx"]`; per il Guerriero (che ha una scelta A/B con un item `weapon_choice` nell'opzione
  corrente) confermato che il Dropdown arma resta presente e funzionante sotto il CardPicker, invariato rispetto a
  prima del redesign. `python3 -m py_compile`/`pyflakes` puliti su `ui/widgets.py`, `wizard_view.py`,
  `manual_form.py` (solo il rumore preesistente di `from config.settings import *`).

- **Fix scroll-to-top al click sul CardPicker dotazioni + restyling scelta oro (2026-07-17, stesso giorno, feedback
  diretto di Davide sul redesign appena sopra)** — "non mi piace che fa uno strano effetto quando clicco e cambio
  selezione mi porta in cima alla scheda, la selezione dell'oro è brutta da vedere perché è rimasta del vecchio
  stile". Due bug distinti nello stesso redesign, entrambi in `wizard_view.py`/`manual_form.py` (identico in
  entrambi):
  1. **Jump-to-top al click sulla scelta A/B**: causa radice — `_make_picker_select().on_select` richiamava sempre
     `self._render_equipment()`, che ricostruisce l'INTERA fase (`rows` da zero: oggetti garantiti, tutte le scelte
     A/B, equipaggiamento background, monete iniziali) e la passa a `_set_content(...)` — sostituendo l'intero
     content Column, Flet resetta lo scroll in cima. La reveal della card stessa (icona radio + testo espanso) è
     già gestita internamente da `CardPicker` (rebuild + `.update()` sul proprio `.control`, non sul content
     dell'intera pagina) — il full-render esterno era quindi del tutto superfluo, unico scopo reale era rigenerare
     i Dropdown arma per le voci `weapon_choice` dell'opzione appena scelta.
     **Fix**: `_on_select` non richiama più `self._render_equipment()`. Ogni scelta A/B ha ora un
     `weapon_pickers_col: ft.Column` persistente e sempre montato (anche vuoto) accanto al `CardPicker`; una nuova
     `_build_weapon_pickers(c)` (estratta dal corpo che prima costruiva `weapon_pickers` inline) ricalcola solo i
     Dropdown arma per l'opzione corrente; l'handler fa `col.controls.clear()` →
     `col.controls.extend(_build_weapon_pickers(c))` → `col.update()` (guard `try/except RuntimeError`) — stesso
     identico pattern già in uso nel file per altre sezioni reattive
     (`_rebuild_subrace_picker`/`_rebuild_lang_tool_col`/ecc., vedi convenzione "LISTVIEW CONTROLS" del progetto,
     qui applicata a un `ft.Column` generico non a un `ft.ListView`). Nessuna modifica alla struttura dati
     (`chosen_idx`, `chosen_weapon(s)`) né al salvataggio finale.
  2. **Stile della sezione "Monete iniziali"**: usava ancora un `ft.RadioGroup`/`ft.Radio` nudo (default Flet, mai
     skinnato), stonato rispetto al resto della fase ormai tutta a `CardPicker`. **Fix**: sostituito con lo stesso
     `CardPicker` a 2 opzioni ("Equipaggiamento standard" / "Oro iniziale — tira {formula}", quest'ultima con un
     corpo esplicativo che appare al click, stesso stile delle altre card) — stessa coerenza visiva del resto della
     schermata. Stesso principio del fix 1: `on_select` NON richiama `self._render_equipment()`, si limita a
     mostrare/nascondere `gold_field` (`.visible` + `.update()` guardato) in-place.
  **Verificato** con nuova batteria di test end-to-end (bypass `__init__`, `TrackedCardPicker` per intercettare le
  istanze create, `_set_content` sostituito con un contatore di chiamate): (1) click su una card di una scelta A/B
  (Chierico) — `chosen_idx` aggiornato correttamente, **contatore `_set_content` resta a 1** (nessun secondo render
  dell'intera fase); (2) stesso test sul Guerriero con una scelta A/B contenente `weapon_choice` —
  `weapon_pickers_col` si aggiorna con i Dropdown corretti per la nuova opzione, ancora **zero** re-render della
  pagina; (3) click sulla card "Oro iniziale" (Chierico) — `self._gold_mode` diventa `True`, `gold_field.visible`
  diventa `True`, **zero** re-render della pagina; (4) scansione dell'intero albero controlli della fase
  equipaggiamento — **zero** `ft.RadioGroup`/`ft.Radio` residui; (5) stesso identico comportamento ri-verificato in
  `wizard_view.py` (Mago) — contatore `_set_content` invariato dopo il click. Smoke test di regressione su tutte le
  12 classi PHB in entrambi i file (istanziazione completa della fase equipaggiamento) — 0 eccezioni. `python3 -m
  py_compile`/`pyflakes` puliti su entrambi i file (solo il rumore preesistente di `from config.settings import
  *`).

---


---

> Questo file è stato estratto da `CLAUDE.md` il 2026-07-31 durante la riorganizzazione della documentazione del
> progetto (il file principale era cresciuto fino a superare 860 KB, causando compattazioni troppo frequenti della
> chat). Il contenuto è verbatim, nessuna informazione è stata riassunta o rimossa. Per la mappa completa dei
> documenti del progetto vedi `CLAUDE.md` alla radice.
