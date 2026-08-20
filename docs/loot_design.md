# Bottino: archivio, deposito comune, assegnazione e ripartizione

> **Stato al 2026-08-20: tutti i 6 passi di §8 implementati e verificati**
> (schema `loot_stash_entries` + repository, `core/loot_calculator.py`, tab
> "Bottino" nella Sezione Master, dialogo di assegnazione condiviso, wiring
> nei 6 punti di generazione, e — ultimo, 2026-08-20 — il deposito del
> gruppo lato giocatore, `WorldsView._shared_loot_section()` in
> `ui/views/world/world_view.py`). **Revisione dello stesso giorno**: il
> deposito del gruppo è passato da sola-lettura ad auto-servizio — un
> giocatore può prendere una voce da solo (`CMD_LOOT_STASH_CLAIM`), vedi §6
> più sotto per il dettaglio. Dettaglio completo in
> `dnd_app/docs/funzionalita_e_todo.md` e `dnd_app/docs/changelog_storico.md`.
>
> **Aggiunta 2026-08-15**: il Generatore Oggetti Magici ha ora anche una
> modalità "Personalizzato" (oggetto inventato dal Master, non pescato dal
> Compendio) — produce lo stesso tipo di voce (`entry_kind="magic_item"`,
> via `simple_item()`/`_build_loot_items()`) con `source_note` che inizia
> per `"Creato dal Master"` invece di `"Generatore Oggetti Magici"`, unica
> differenza rispetto a un oggetto generato casualmente. Nessun cambio di
> schema: `LootStashEntry` non ha mai avuto colonne per rarità/categoria/
> sintonia, entrambi i percorsi le codificano come testo dentro
> `source_note`, per convenzione già esistente. Dettaglio in
> `changelog_storico.md`.

---

## 1. Cosa manca oggi

I generatori della Sezione Master producono già bottino corretto e verificato,
ma il passaggio dal bottino al personaggio è incompleto e incoerente:

| Strumento | Oggi |
|---|---|
| Generatore Tesori | ha «Aggiungi all'inventario di…», **un solo destinatario** |
| Generatore Oggetti Magici | idem, un solo destinatario |
| Compendio Oggetti Magici (264 voci) | **nessun modo** di darne uno a un giocatore |
| Artefatti (5 voci + tabelle) | **nessun modo** |
| Veleni (14 voci) | **nessun modo** |
| Tesoro tirato ma non ancora distribuito | **si perde**: chiudi il dialogo e non esiste più |

Le tre richieste di Davide: poter assegnare **a più giocatori con quote in
percentuale**, poter **salvare** il bottino per assegnarlo dopo, e (aggiunta in
fase di scelta) avere un **deposito comune del gruppo**.

---

## 2. I tre contenitori

Tutto passa da un'unica idea: il bottino è una **voce** che sta in uno di tre
posti, e si muove tra loro.

```
   Generatori / Compendi
   (Tesori · Oggetti Magici · Artefatti · Veleni · Trappole)
              │  "Salva nell'archivio"        │  "Assegna subito"
              ▼                               │
   ┌──────────────────────┐                   │
   │  ARCHIVIO DEL MASTER │  privato          │
   │  (non assegnato)     │  ────────────┐    │
   └──────────────────────┘              │    │
              │  "Metti nel deposito"    │    │
              ▼                          ▼    ▼
   ┌──────────────────────┐        ┌──────────────────────┐
   │  DEPOSITO DEL GRUPPO │ ─────► │   SCHEDA GIOCATORE   │
   │  (visibile a tutti)  │        │   (inventario/monete)│
   └──────────────────────┘        └──────────────────────┘
```

**Archivio del master** — privato, la sua «cassaforte». Ci finisce il bottino
preparato in anticipo o tirato e non ancora dato. Esiste anche **fuori da un
mondo** (`world_id = ''`), così il master può prepararsi la campagna prima
ancora che i giocatori esistano.

**Deposito del gruppo** — il forziere comune, visibile a tutti i membri del
mondo. Serve al caso reale del tavolo: «prendiamo tutto, dividiamo dopo». Vive
sempre dentro un mondo.

**Scheda del giocatore** — la destinazione finale: `inventory_items` e
`currencies`, cioè le tabelle già esistenti. **Nessun cambiamento alla scheda**:
un oggetto assegnato è un normale oggetto d'inventario con la sua descrizione
ufficiale integrale, esattamente come lo crea oggi il Generatore Tesori.

Una sola tabella per i primi due contenitori (`loot_stash_entries`, schema in
`multiplayer_design.md` §8), distinti dal campo `stash_kind` = `master` |
`party`. Sono lo stesso oggetto con visibilità diversa: separarli in due
tabelle avrebbe duplicato ogni operazione di spostamento.

---

## 3. Cosa può essere una voce di bottino

`entry_kind` ∈ `item` · `magic_item` · `artifact` · `weapon` · `armor` ·
`poison` · `gem` · `art` · `coins`.

Tutte le voci portano con sé **il testo ufficiale integrale** già trascritto nel
progetto (264 oggetti magici, 5 artefatti, 14 veleni, gemme e oggetti d'arte
delle tabelle dei tesori): niente riassunti, niente rimandi. È la stessa
convenzione già seguita dal Generatore Oggetti Magici quando scrive
`description` sull'oggetto d'inventario.

**`weapon`/`armor` (2026-08-20)** hanno, oltre a nome/descrizione, le caselle
meccaniche della scheda giocatore invece di restare testo libero — bug report
Davide: "devono avere le stesse caselle di quando crei l'arma o l'armatura
nella sezione giocatore". `weapon`: dado danno, tipo danno, categoria
(semplice/guerra), proprietà, bonus attacco/danno (per una versione magica), e
**danni magici aggiuntivi tipizzati e ripetibili** (colonna `weapon_magic_
damages`, JSON `[{"dice","type","note"}]`, stesso formato/UI di `weapons.
magic_damages` — es. ghiaccio 1d8 + fuoco 1d6 oltre al danno base, aggiunto
2026-08-20 dopo un secondo bug report: il form aveva solo un dado/tipo
singolo). `armor`: CA base, tipo (leggera/media/pesante/scudo), effetti
testuali. Alla presa/assegnazione, `weapon` crea sempre una riga vera in
`weapons` (mai un oggetto d'inventario generico); `armor` crea un
`inventory_items` con `category="armor"`. Stesso form (`master_loot_assign_
dialog.build_weapon_mechanics_fields()`/`build_armor_mechanics_fields()`)
riusato sia in "+ Aggiungi voce"/"Modifica Voce" del Bottino sia nell'Oggetto
Magico Personalizzato del Generatore Oggetti Magici, quando la categoria
scelta è un'arma o un'armatura — **ma non ancora per le 264 voci pescate dal
Compendio in modalità "random"**, che non hanno mai dati meccanici strutturati
nel JSON (solo prosa): quelle vengono instradate a `weapon`/`armor` da
`_resolve_entry_kind()` (`master_magic_item_generator_dialog.py`, 2026-08-20)
solo per finire nella sezione giusta, senza precompilare dado/CA (il Master li
compila a mano se vuole, la descrizione ufficiale resta comunque intatta in
`magic_description`/`description`).

**Il tipo (`entry_kind`) di una voce è modificabile anche dopo il
salvataggio** (2026-08-20) — bug report Davide su un Artefatto in archivio:
"quando lo modifico deve avere la possibilità di essere modificato in toto...
può essere selezionato il tipo". "Modifica Voce" ora ha lo stesso dropdown
tipo di "Aggiungi Voce" (tutte le opzioni tranne `coins`, che resta un cambio
di forma dei dati a parte); cambiare tipo verso `weapon`/`armor` fa comparire
le caselle meccaniche (vuote, salvo che il tipo scelto sia lo stesso di
partenza — in quel caso precompilate con i valori già salvati).
`loot_repo.update_entry(entry_kind=...)`, `""` = lascia invariato.

`coins` è l'unica voce **divisibile**, e ha un trattamento a parte (§5). Tutte
le altre sono indivisibili: si assegnano a **un** destinatario. Con quantità
maggiore di uno (3 pozioni, 5 gemme da 50 mo) si può ripartire **per quantità**,
non per percentuale — 3 pozioni tra 4 giocatori non fanno 0,75 pozioni a testa.

---

## 4. Assegnazione

Un unico dialogo, richiamato da ogni punto (generatori, compendi, archivio,
deposito), così il comportamento è lo stesso ovunque:

1. **Cosa** — l'elenco delle voci coinvolte, con caselle per scegliere cosa
   assegnare adesso e cosa lasciare dov'è.
2. **A chi** — i personaggi del mondo (o, senza mondo, quelli sul dispositivo).
   Per gli indivisibili: un destinatario per voce, con un pulsante «distribuisci
   a caso» per il caso «tirate voi chi la prende». Per le quantità multiple: un
   contatore per giocatore, con la verifica che la somma non superi il totale.
3. **Monete** — §5.
4. **Riepilogo prima di confermare** — chi riceve cosa, riga per riga. Non si
   scrive nulla su nessuna scheda prima della conferma.

Destinazioni possibili, oltre ai personaggi: **deposito del gruppo** e
**archivio** (per rimandare).

**Con il multiplayer attivo** l'assegnazione è un comando (`loot.assign`) che
produce un evento del registro: il giocatore vede «Il master ti ha assegnato
Ampolla di Ferro e 120 mo» e può risalire a quando e da chi. Senza multiplayer
è una scrittura diretta, esattamente come oggi.

---

## 5. Monete: la ripartizione in percentuale

È la parte con più insidie, e merita di essere esplicita.

**5.1 — Le quote.** Il master imposta una percentuale per giocatore. Default
**parti uguali** (con un pulsante che le ripristina). Le quote devono sommare a
100 %; l'app lo verifica e non lascia confermare altrimenti. Un giocatore può
essere escluso mettendolo a 0.

**5.2 — Due modi di dividere, ed è una scelta di gioco, non un dettaglio.**

| Modo | Cosa fa | Quando serve |
|---|---|---|
| **Per denominazione** *(default)* | Divide ogni tipo di moneta separatamente: 100 mo tra 4 → 25 mo a testa; 7 mp tra 4 → 1 mp a testa e 3 mp di resto | fedele al tavolo: le monete si spartiscono fisicamente, nessuno «converte» |
| **Per valore** | Somma tutto in rame usando la tabella di cambio, divide, riconverte nelle denominazioni più grandi possibili | quando si vuole che le quote tornino davvero, accettando il cambio |

La conversione usa **esclusivamente** `equipment/economy.json` («Valori di
Scambio», PHB IT p.143, già verificato contro il manuale): 1 ma = 10 mr,
1 me = 50 mr, 1 mo = 100 mr, 1 mp = 1000 mr. Nessun numero riscritto a mano nel
codice — stessa regola già applicata a tutte le tabelle del progetto.

**5.3 — I resti, che ci sono quasi sempre.** 100 mo con quote 33/33/34 non
danno numeri interi. Metodo: si calcola la quota esatta, si assegna la parte
intera, e le unità avanzate vanno **ai resti più grandi** (chi è stato
penalizzato di più dall'arrotondamento ne riceve una). Così **la somma delle
quote è sempre esattamente il totale**: non spariscono monete e non se ne creano.
Se anche così restano unità indivisibili, il master sceglie: al **deposito del
gruppo** (default), a un giocatore indicato, o restano nell'archivio.

**5.4 — Cosa vede il master prima di confermare.** La tabella completa: per
ogni giocatore, la quota in percentuale, il valore che gli spetta e le monete
effettive che riceverà, più la riga del resto. Nessuna sorpresa dopo.

**5.5 — Le monete si sommano, non si sovrascrivono.** Come già fa oggi il
Generatore Tesori: si leggono le monete correnti con `get_currencies()` e si
scrive la somma con `update_currencies()`. Nessuna funzione nuova di scrittura
sulle schede.

---

## 6. Dove compare, nell'app

**Sezione Master, nuova scheda «Bottino»** accanto a Rubrica NPC / Incontri /
Note / Oggetti Magici, con due elenchi (archivio e deposito) e le operazioni:
assegna, sposta tra i due, modifica, elimina, «genera e salva qui».

**Nei generatori e nei compendi**, accanto all'attuale «Aggiungi
all'inventario di…», due pulsanti: **«Assegna…»** (apre il dialogo di §4) e
**«Salva nell'archivio»**. Il pulsante odierno resta come scorciatoia per il
caso più semplice — un solo destinatario — perché funziona e va bene così.

Punti da collegare, oggi tutti scollegati salvo i primi due: Generatore Tesori,
Generatore Oggetti Magici, **Compendio Oggetti Magici** (264 voci),
**Artefatti**, **Veleni**, e le gemme/oggetti d'arte già prodotti dai Cumuli di
Tesori.

**Lato giocatore**: il deposito del gruppo compare come sezione con un pulsante
**"Prendi" per voce** (design rivisto il 2026-08-20 — Davide: "i giocatori
possono prendere da soli", sostituisce il design originale sola-lettura in cui
solo il master distribuiva). Un membro con un proprio personaggio attivo in
quel mondo può prendere una voce direttamente: va per intero (mai una quota,
coerente con §3) sulla propria scheda — oggetto in Inventario, monete sommate
alle proprie — e sparisce dal deposito per tutti, via il comando di rete
`CMD_LOOT_STASH_CLAIM` (`core/world_backend.py::_handle_loot_stash_claim`), un
solo giro di rete che applica ed elimina insieme. Un membro senza personaggio
in quel mondo vede comunque il deposito, ma senza pulsante. Il master mantiene
comunque le proprie azioni di assegnazione/spostamento/eliminazione dalla tab
«Bottino» della Sezione Master, invariate.

---

## 7. Casi limite

- **Assegnazione a un giocatore scollegato** (con multiplayer): il comando è
  comunque valido, l'evento resta nel giornale, il giocatore lo riceve al
  rientro. Non serve che sia presente.
- **Bottino generato senza alcun personaggio esistente**: oggi il pulsante di
  assegnazione è disabilitato e il tiro si perde. Con l'archivio si può salvare
  comunque, ed è esattamente il caso «preparo la campagna prima».
- **Voce con quantità 0 o quote che non sommano a 100 %**: bloccate con
  messaggio, non correggibili a discrezione dell'app.
- **Oggetti magici con sintonia**: l'oggetto assegnato porta già
  `requires_attunement`, e le regole DMG (massimo 3, mai due copie dello stesso)
  sono già applicate da `core/equipment_manager.can_attune()` quando il
  giocatore prova a sintonizzarsi. L'assegnazione non tocca la sintonia:
  **è il giocatore a decidere se sintonizzarsi**, coerente con la divisione dei
  ruoli.
- **Eliminare una voce dall'archivio** non toglie nulla a chi l'ha già ricevuta:
  l'assegnazione ha creato un oggetto d'inventario indipendente.

---

## 8. Ordine di lavoro

1. Tabella `loot_stash_entries` e il suo repository (con lo stesso stile
   try/except + logger degli altri).
2. Il calcolo puro della ripartizione in un modulo `core/` senza dipendenze da
   Flet, come `treasure_generator.py` e gli altri: quote, conversione, resti.
   È la parte che si presta a essere verificata a fondo da sola.
3. La scheda «Bottino» nella Sezione Master.
4. Il dialogo di assegnazione condiviso.
5. Il collegamento dei sei punti di §6.
6. ✅ Il deposito del gruppo lato giocatore (richiede il modello mondo, quindi
   arriva col passo 2 del piano multiplayer) — fatto il 2026-08-20.

I passi 1-5 funzionano **senza rete**, su un dispositivo solo e nel deploy web.
