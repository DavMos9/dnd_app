# Mondi condivisi e LAN party — documento di progettazione

> **Stato (aggiornato 2026-08-07 in una pulizia della documentazione — era
> rimasto fermo a "sola progettazione" da luglio, ormai falso): progettazione
> **chiusa** (§12) e **in gran parte implementata**. Dei nove passi di §13, i
> passi 1-6 sono fatti e testati (bottino, modello mondo, istanze di
> personaggio, host/client LAN, scoperta automatica + QR, interventi del
> master a distanza) — i passi 7-9 (condivisione, mappe condivise,
> robustezza/esportazione) restano da fare. Lo stato dettagliato e sempre
> aggiornato vive in `CLAUDE.md`, sezione "Piano di lavoro attivo" — questo
> file resta la fonte di verità per le DECISIONI di design (§1-§12, tutte
> chiuse: non riprogettare da capo), non per l'avanzamento.
> Documento redatto il 2026-07-31 su richiesta di Davide.

---

## 1. Il problema

L'app è stata costruita finora assumendo **un solo dispositivo**: chi la apre è
contemporaneamente il giocatore e (se apre la Modalità Master) il master. Regge
nel deploy web, dove tutti i client parlano con lo stesso processo e lo stesso
DB, ma **non regge nella versione locale** (desktop/mobile): lì il master non ha
alcun modo di toccare la scheda di un giocatore che gira su un altro
dispositivo, perché quei due DB non si conoscono.

L'unica scrittura del master su una scheda giocante esistente oggi
(`character_repo.add_xp()`, Fase 4) funziona solo perché in quel momento le due
schede vivono nello stesso file SQLite.

Quello che serve, con le parole di Davide: il master crea un **mondo**, i
giocatori si uniscono, ogni volta che si rivedono rientrano nello stesso mondo
con tutti i progressi, e il master può intervenire sui PG in modo interattivo.
Devono poter esistere **più master e più giocatori**.

---

## 2. Le quattro decisioni prese (2026-07-31, via domande dirette)

| Decisione | Scelta di Davide |
|---|---|
| **Topologia** | **Host in LAN sul dispositivo del master.** Nessun server esterno obbligatorio, nessun account. Il gioco a distanza resta un'estensione futura (§10). |
| **Dati** | **Il mondo è la fonte di verità**, ma il personaggio è salvato **anche in locale**, così può essere riusato in altri mondi — chiedendo se importarlo **com'è** o **dal livello 1**. |
| **Permessi** | **Azioni autorizzate + registro.** Il master fa un elenco definito di cose, ognuna tracciata e visibile al giocatore. Identità, classe, punteggi e talenti restano del giocatore. |
| **Bottino** | Tutte e quattro: monete in percentuale, oggetti a un destinatario, deposito comune del gruppo, archivio bottino pronto. Progettato a parte in `loot_design.md` — **non dipende dal multiplayer** e può essere fatto prima. |

Sette scelte di dettaglio decise subito dopo, nella stessa sessione:

| Decisione | Scelta di Davide | Dove |
|---|---|---|
| **Richiesta di modifica** | **Sì, con approvazione del giocatore.** Il master propone una modifica su un campo altrimenti vietato, il giocatore accetta o rifiuta. | §7.1 |
| **Foglio locale** | **Azione manuale** «Aggiorna il mio foglio»: il personaggio locale non si riallinea mai da solo. | §6.1 |
| **Diario e note** | **Il diario del giocatore resta privato.** Le Note di Campagna del Master (già esistenti) hanno una **visibilità per singola nota**: nessuno, tutti, o alcuni giocatori scelti. | §6.2 |
| **Esportazione del mondo** | **Sì, fin da subito** — file `.dndworld`, non rimandata alla fine. | §6.3 |
| **Mappe** | **Sì, condivise con le annotazioni in tempo reale** mentre il master disegna. | §6.4 |
| **Tracker di combattimento** | **Sì**: i giocatori vedono ordine di iniziativa e turno corrente; dei mostri **nome e stato descrittivo, mai i PF esatti**. | §6.5 |
| **Ruolo spettatore** | **No.** Tre ruoli: owner, master, giocatore. | §4 |

---

## 3. Vincoli reali, verificati sul progetto (non ipotesi)

Prima di progettare la rete ho controllato cosa è davvero disponibile, perché
diverse scelte ovvie qui sono impraticabili.

**3.1 — Il pacchetto `flet==0.85.3` non porta alcun server.** Le sue
dipendenze reali (lette da `Requires-Dist` nel `.dist-info` installato) sono
`oauthlib`, `httpx`, `repath`, `msgpack`. FastAPI/uvicorn arrivano solo con
l'extra `flet-web`, che nel progetto esiste **solo nell'immagine Docker**.
Quindi: *un server HTTP nell'app locale va scritto con la libreria standard di
Python oppure aggiungendo una dipendenza nuova.*

**3.2 — Aggiungere dipendenze è rischioso sul mobile.** `flet build apk/ipa`
impacchetta Python con serious-python: un pacchetto non puro-Python (o senza
wheel per quella piattaforma) non entra nella build, e il progetto oggi ha solo
`flet` + `Pillow`. **Decisione: nessuna dipendenza nuova per la rete.** Tutto
con la stdlib (`http.server`, `socket`, `json`, `threading`, `hmac`, `secrets`).

**3.3 — `qrcode` c'è ma non è garantito.** È installato nel `.venv`, ma come
dipendenza di `flet-cli` (lo strumento di build), non di `flet`. Non è quindi
utilizzabile a runtime in una build mobile senza aggiungerlo esplicitamente. Il
QR per entrare nel mondo è **opzionale**; il metodo sempre disponibile è un
codice a 6 caratteri digitato a mano.

**3.4 — I permessi Android sono vuoti.** `pyproject.toml` ha
`[tool.flet.android] permissions = []` con il commento «offline-first, nessuna
rete richiesta». Vanno aggiunti `INTERNET`, `ACCESS_NETWORK_STATE` e, se si fa
la scoperta automatica, `CHANGE_WIFI_MULTICAST_STATE`. **Va anche rivisto il
commento**, perché l'app smette di essere offline-first per definizione.

**3.5 — iOS ha due limiti reali che vanno detti prima, non scoperti dopo.**
(a) La scoperta automatica in rete locale richiede l'entitlement
`com.apple.developer.networking.multicast`, che **Apple concede su richiesta
motivata**, non automaticamente. (b) Un'app iOS in background viene sospesa: se
il master ospita da iPhone e mette l'app in secondo piano, **il mondo si ferma**.
Conclusione onesta: **ospitare da iOS è sconsigliato**; entrare come giocatore
da iOS funziona senza problemi. Su Android e desktop ospitare va bene.

**3.6 — Quello che il progetto ha già e che riusiamo.** UUID v4 come chiave
primaria e `created_at`/`updated_at` su ogni entità (scelti nel 2026-06 proprio
in vista di questo); `WAL` attivo su SQLite, quindi più lettori con uno
scrittore convivono; un thread daemon di polling già collaudato in
`home_view.py` (5 s, con firma `id:updated_at` per non ricostruire a vuoto);
`app_settings` chiave/valore già pronta per l'identità del dispositivo;
l'export `.dndchar` a introspezione di schema, che continuerà a funzionare
senza modifiche.

**3.7 — La tabella di cambio delle monete esiste già ed è verificata** contro
il manuale (`equipment/economy.json`, PHB IT p.143): 1 mr = 1, 1 ma = 10 mr,
1 me = 50 mr, 1 mo = 100 mr, 1 mp = 1000 mr. La ripartizione percentuale la
leggerà da lì — nessun numero riscritto a mano.

---

## 4. Modello concettuale

Cinque concetti nuovi, niente di più.

**Mondo** — una campagna. Ha un nome, un identificatore, un proprietario, e
vive nel DB di chi lo ospita. È l'unità che i giocatori «rientrano» ogni volta.

**Dispositivo** — ogni installazione dell'app genera un `device_id` (UUID) alla
prima apertura e lo salva in `app_settings`. Non è un account: non c'è
registrazione, email o password. È l'identità che permette di riconoscere «lo
stesso portatile di Marco» alla sessione successiva.

**Membro** — un dispositivo dentro un mondo, con un nome visualizzato scelto
dal giocatore e un **ruolo**.

**Ruoli** — **tre**, in scala. Lo spettatore è stato scartato: è un caso raro, e
un giocatore senza personaggio assegnato ottiene già quasi lo stesso effetto
senza aggiungere un ruolo da verificare in ogni controllo di permesso.

| Ruolo | Chi è | Cosa può fare |
|---|---|---|
| `owner` | chi ha creato il mondo, uno solo | tutto ciò che fa un master, più: promuovere/degradare, espellere, rinominare o eliminare il mondo, trasferire la proprietà, esportare il mondo |
| `master` | co-master promossi dall'owner | tutte le azioni master sui PG e sul mondo (§7) |
| `player` | giocatore | gestisce le proprie istanze di personaggio; vede il registro degli interventi ricevuti |

L'owner è chi **ospita fisicamente** il mondo: il DB è sul suo dispositivo. Un
co-master ha gli stessi poteri di gioco ma non possiede i dati (§11.4 spiega
cosa succede se l'owner sparisce).

**Istanza di personaggio** — la copia di un personaggio *dentro un mondo*. È il
pezzo che risolve la richiesta «riusabile in altri mondi» senza creare
ambiguità: vedi §6.

---

## 5. Il meccanismo centrale: comando → validazione → evento

Un solo meccanismo copre tre requisiti che sembrano distinti (sincronizzazione,
permessi, registro degli interventi). Vale la pena spiegarlo prima dello schema,
perché il resto ne discende.

I client **non scrivono mai direttamente** nello stato del mondo. Inviano un
**comando** all'host; l'host lo valida contro i permessi del mittente, lo
applica al proprio DB e **registra un evento** in un giornale con numero
progressivo. I client leggono il giornale e riportano l'effetto sulla propria
replica locale.

```
 Giocatore                      Host (master)                    Altri client
 ---------                      -------------                    ------------
 "−7 PF"  ──── comando ───────►  valida permessi
                                 applica al DB
                                 scrive evento #482
                                        │
        ◄──── evento #482 ──────────────┴──── evento #482 ───────►
        aggiorna la vista                     aggiornano la vista
```

Perché è la scelta giusta qui:

- **Niente conflitti.** Un solo scrittore decide l'ordine. Non serve
  risoluzione di conflitti né *last-write-wins*, che sui punti ferita darebbe
  risultati assurdi (due giocatori che applicano danni «insieme» e uno dei due
  sparisce).
- **I permessi hanno un unico punto di controllo.** Sono la validazione del
  comando: impossibile aggirarli da un client modificato, perché il client non
  tocca il DB dell'host.
- **Il registro richiesto da Davide è il giornale stesso**, non una tabella in
  più da tenere allineata. «Il master ti ha assegnato 500 PE» è semplicemente
  l'evento #482 mostrato in forma leggibile.
- **La sincronizzazione è incrementale**: un client chiede «cosa è successo dopo
  il #481» invece di riscaricare lo stato intero.

Il costo è che ogni azione che oggi scrive dritta sul DB deve passare da un
livello intermedio. Per questo §9 propone un'astrazione unica con due
implementazioni, così la UI non deve sapere se è collegata o no.

---

## 6. Il personaggio: locale, e dentro i mondi

Questa è la parte che Davide ha specificato più nel dettaglio, e ha un caso
limite non ovvio.

**Il problema.** Se lo stesso personaggio (stesso `id`) entra in due mondi
diversi, dopo tre sessioni ha due storie divergenti — livelli, oggetti, PF
diversi — e un unico record non può rappresentarle entrambe.

**La soluzione: il personaggio locale è un *modello*, ogni mondo ne ha una
*istanza*.**

- Il personaggio creato sul proprio dispositivo e non ancora entrato in un
  mondo è **locale**: è il tuo foglio personale, resta com'è.
- Quando entra in un mondo, si crea un'**istanza** con un proprio UUID nuovo,
  che ricorda da quale personaggio locale è nata (`origin_character_id`).
- Le istanze sono personaggi a tutti gli effetti: hanno tutte le tabelle
  figlio, funzionano con le 5 schede esistenti senza modifiche, si esportano in
  `.dndchar`.
- Nella schermata Home compaiono raggruppate per mondo, con il personaggio
  locale in una sezione «Non in un mondo».

**All'ingresso** l'app chiede, come da richiesta di Davide:

| Scelta | Cosa fa |
|---|---|
| **Porta com'è** | Copia integrale: livello, PE, inventario, incantesimi, diario. Per continuare la stessa storia in un nuovo gruppo. |
| **Ricomincia dal 1° livello** | Tiene identità, razza, classe, background, aspetto, personalità, ritratto. Azzera livello/PE/inventario/diario/condizioni e riassegna l'equipaggiamento iniziale della classe. |
| **Riprendi** *(automatica)* | Se in quel mondo esiste già un'istanza nata da questo personaggio, non se ne crea una nuova: si riprende quella. È il caso normale della sessione successiva. |

**Ricadute dichiarate**, così nessuno le scopre dopo:

1. Le due istanze **non si sincronizzano tra loro**. Salire di livello nel mondo
   A non tocca l'istanza nel mondo B né il personaggio locale. È l'unico
   comportamento sensato — sono due partite diverse — ma va detto nella UI al
   momento della scelta, non lasciato intuire.
2. **Il personaggio locale non si aggiorna da solo** con i progressi fatti in un
   mondo: serve un'azione esplicita (§6.1).
3. Un'istanza di cui hai una replica **resta leggibile offline** e resta
   esportabile: se il gruppo si scioglie, il personaggio non è perso.

**Sul dispositivo di chi ospita** le istanze sono i record autoritativi. Sul
dispositivo del giocatore sono repliche, aggiornate dagli eventi. Sono la
stessa forma di dato: cambia solo chi ha l'ultima parola.

### 6.1 «Aggiorna il mio foglio» — manuale, mai automatico

Il personaggio locale **non si riallinea mai da solo**. Nella scheda di
un'istanza compare un'azione «Aggiorna il mio foglio personale da questa
istanza», che ricopia lo stato dell'istanza sul personaggio locale di origine.

- Chiede **conferma esplicita**, perché sovrascrive: il riepilogo mostra cosa
  cambia (livello 4 → 7, 12 oggetti in più, ecc.) prima di procedere.
- È disponibile **solo al proprietario** del personaggio, mai al master.
- Se il personaggio locale di origine non esiste più (eliminato), l'azione
  propone di **crearne uno nuovo** invece di fallire.

Il motivo della scelta manuale: l'automatismo all'uscita dal mondo sembra
comodo finché non hai due mondi attivi, e a quel punto l'ultimo che chiudi
sovrascrive silenziosamente il lavoro dell'altro. Meglio un pulsante in più che
una perdita di dati inspiegabile.

### 6.2 Diario privato, note del master a visibilità scelta

**Il diario del giocatore resta privato.** `diary_entries` e `campaign_notes`
(il Codex personale: PNG, luoghi, missioni, fazioni) non vengono mai condivisi
né letti dal master. Sono gli appunti del giocatore.

**Le Note di Campagna del Master** (`master_campaign_notes`, le 8 categorie già
esistenti — PNG, PNG da cercare, luoghi, luoghi da esplorare, missioni,
fazioni, eventi, segreti) diventano invece **condivisibili una per una**:

| Visibilità | Significato |
|---|---|
| `private` *(default)* | solo master e co-master — comportamento identico a oggi |
| `all` | tutti i membri del mondo la vedono, in sola lettura |
| `selected` | solo i giocatori indicati la vedono |

`selected` è il caso interessante: una profezia rivelata a un solo personaggio,
un segreto che conosce il ladro e non gli altri. Due colonne aggiunte a
`master_campaign_notes`: `visibility TEXT DEFAULT 'private'` e
`shared_with TEXT DEFAULT '[]'` (JSON di `device_id`).

Le note condivise arrivano ai giocatori come sezione in sola lettura, distinta
dal proprio Codex. **Cambiare la visibilità è un'azione registrata**: togliere
una condivisione non cancella il fatto che c'è stata.

Il master **può anche scrivere una voce sul diario di un personaggio** (una
visione, un ricordo indotto) — è tra le azioni autorizzate di §7, ed è cosa
diversa dal leggerlo: scrive, non guarda.

### 6.3 Esportazione del mondo — subito, non alla fine

File `.dndworld`, stesso identico meccanismo già collaudato per `.dndchar`:
JSON con introspezione dello schema (`PRAGMA table_info`), quindi «a prova di
versione» in entrambe le direzioni senza manutenzione.

Contiene: il mondo, i membri con i ruoli, **tutte le istanze di personaggio con
le loro tabelle figlio**, il giornale degli eventi, i due contenitori di
bottino, le note del master con la loro visibilità e le richieste di modifica
pendenti.

Serve a due cose diverse, entrambe reali:
1. **Passare la campagna a un altro master** — chi importa diventa `owner` e
   ospita da lì in avanti.
2. **Non perdere tutto** se il dispositivo che ospita si rompe. Senza questo, la
   perdita è definitiva: i client hanno solo repliche parziali (§11.4).

All'importazione le stesse tre modalità di `.dndchar` — nuovo, sovrascrivi,
copia — con la copia che rigenera gli identificatori per non collidere con un
mondo già presente. Va offerto un **promemoria periodico di esportazione** al
master (ogni N sessioni), perché un backup che nessuno ricorda di fare non è un
backup.

**Implementato e testato (2026-08-12, passo 9D/9E/9F).** `data/repositories/
world_export.py`, stesso principio di introspezione schema di
`character_export.py` (riusa direttamente le sue funzioni interne — nessuna
seconda copia della stessa logica di lettura/scrittura generica). In OGNI
modalità di import questo dispositivo diventa l'owner/host del mondo da lì in
avanti — unica eccezione deliberata all'invariante "solo `create_world()`
imposta `is_local_host=1`" (§11.5): un'importazione da file è un'azione
esplicita dell'utente per iniziare/riprendere a ospitare, mai un effetto
collaterale di sincronizzazione. "N sessioni" non è tracciabile (l'app non
registra sessioni di gioco in automatico): la taratura scelta CON Davide è
eventi di giornale dall'ultimo export riusciti, soglia 20 — riflette
l'attività reale della campagna invece del calendario. Bug reale trovato
scrivendo il test di questa soglia: `world_events.seq` è l'autoincrement
GLOBALE della tabella (condiviso da tutti i mondi), una sottrazione diretta
di seq avrebbe fatto scattare il promemoria su un mondo appena creato e mai
esportato — corretto con `world_repo.count_events_since()` (un `COUNT(*)`
filtrato, mai una sottrazione tra seq incomparabili). Dettaglio completo,
incluse le scelte su cosa entra nell'export (tutte le istanze comprese
quelle archiviate — mai perdere un personaggio rimosso in un backup) e sui
dialoghi nativi del SO (estratti in `ui/file_export.py` senza toccare
`home_view.py`), in `changelog_storico.md`.

### 6.4 Mappe condivise, con le annotazioni in tempo reale

Il master «pubblica» una mappa nel mondo; i giocatori la vedono comparire sul
proprio dispositivo e **vedono i tratti mentre lui disegna**.

Due canali distinti, ed è il punto tecnico che rende la cosa sostenibile:

- **L'immagine non passa mai dal giornale.** È base64 nel DB e può pesare
  megabyte: passa da una rotta dedicata (`GET /map/<id>/image`), scaricata una
  volta sola e tenuta in cache dal client. Metterla in un evento intaserebbe la
  sincronizzazione di tutti.
- **I tratti passano dal giornale**, in pacchetti: durante il disegno i punti
  vengono raggruppati e spediti **ogni ~200 ms**, non uno per volta. Il tratto
  cresce sotto gli occhi dei giocatori, ma con ~5 eventi al secondo mentre si
  disegna, non decine. Gomma e «cancella tutto» sono anch'essi eventi, coerenti
  con il fatto che la gomma già lavora modificando la lista dei tratti in
  memoria e non i pixel.

Il master decide **quali** mappe pubblicare: le altre restano sue. Due colonne
su `game_maps`: `world_id TEXT DEFAULT ''` e `is_shared INTEGER DEFAULT 0`.

**Va detto onestamente**: questa è la parte più pesante dell'intero livello di
rete e l'unica il cui intervallo (i 200 ms) potrebbe richiedere una taratura su
dispositivi veri. Se su una Wi-Fi lenta risultasse a scatti, il ripiego naturale
è spedire il tratto **a fine tratto** anziché durante — un solo parametro da
cambiare, nessuna riprogettazione.

**Implementato (2026-08-11, passo 8) con due scelte di scopo prese in fase di
UI, non previste sopra** — dettaglio completo in `changelog_storico.md`,
voce "8b/8c":

1. **Pubblicare/disegnare è permesso solo a master/owner che OSPITA il
   mondo** (`world.is_local_host`), non a un co-master remoto: la riga
   `game_maps` da pubblicare vive sul DB locale di chi la pubblica, non su
   quello dell'host se sono dispositivi diversi. Un co-master non-host resta
   in sola lettura come un giocatore.
2. **Il ripiego "a fine tratto" è quello effettivamente implementato fin da
   subito** (non i 200 ms durante il disegno) — scelto per semplicità
   implementativa, non per un problema di rete osservato. Se in prova reale
   risultasse troppo "a scatti", il passo successivo è il batching a 200ms
   già previsto qui sopra, non una riprogettazione.

**Rivisto (2026-08-12) dopo il primo uso reale** — dettaglio completo in
`changelog_storico.md`, voce "8d":

- **Pubblicare CLONA, non riusa la riga personale.** `CMD_MAP_PUBLISH`
  crea una riga NUOVA (`character_id=NULL`, come una mappa caricata
  direttamente), mai la stessa della mappa personale di origine — bug
  reale corretto: prima disegnare sulla mappa condivisa modificava anche
  quella personale del personaggio che l'aveva creata.
- **"Nascondere ai giocatori" è un comando a sé**
  (`CMD_MAP_VISIBILITY`, colonna `game_maps.visible_to_players`),
  DISTINTO dall'eliminazione: una mappa nascosta resta nell'elenco del
  master, sparisce solo dalla vista/dal download dei giocatori.
  `CMD_MAP_DELETE` è l'unico modo per farla sparire anche dal master.
- **Caricare una mappa nuova direttamente nel mondo** è un comando a sé
  (`CMD_MAP_UPLOAD`) — stesso risultato di una pubblicazione clonata, ma
  senza una mappa personale di origine.
- **Le coordinate dei tratti sono frazioni [0,1] del riquadro di disegno**
  (`ui/canvas_geometry.py`), non più pixel assoluti — altrimenti la stessa
  mappa aperta in un riquadro di dimensione diversa (finestra del master
  vs. schermo del giocatore) mostrava i tratti disallineati.

### 6.5 Il combattimento visto dai giocatori

Durante un incontro i giocatori vedono, sul proprio dispositivo: l'**ordine di
iniziativa** completo, **di chi è il turno** in quel momento, il **round**, e i
PF esatti **dei soli personaggi giocanti**.

Dei mostri vedono nome e uno **stato descrittivo**, mai i PF esatti:

| Stato | PF residui |
|---|---|
| Illeso | 100 % |
| Ferito | sotto il 100 % |
| Gravemente ferito | 50 % o meno |
| In fin di vita | 25 % o meno |
| Fuori combattimento | 0 |

**Queste soglie sono una convenzione dell'app, non una regola del manuale**: il
PHB non definisce stati di ferita descrittivi. Vanno indicate come tali nel
codice, per non confonderle un domani con un dato di regolamento verificato.

Il master mantiene il controllo: un interruttore «mostra il combattimento ai
giocatori» per incontro, spento di default, così può preparare l'incontro senza
rivelarlo prima del tempo.

---

## 7. Cosa può fare un master, esattamente

Elenco chiuso. Ogni voce produce un evento nel registro, visibile al giocatore
con autore, momento e valori prima/dopo.

**Consentito ai ruoli `master` e `owner`:**

| Azione | Note |
|---|---|
| Assegnare PE | già esiste come `add_xp()`; il level-up resta del giocatore |
| Assegnare oggetti, monete, oggetti magici, artefatti, veleni | §*loot_design.md* |
| Applicare danni e cure | inclusi PF temporanei |
| Applicare o rimuovere condizioni e Indebolimento | le 15 già modellate |
| Consumare/ripristinare slot incantesimo e risorse di classe | |
| Concedere un'abilità speciale personalizzata | `custom_abilities`, già puramente additiva |
| Concedere un incantesimo bonus | `known_spells.is_bonus`, già esistente |
| Aggiungere una voce al diario del personaggio | |
| Far tirare un dado al giocatore | richiesta, non forzatura |
| Aggiungere un PG a un incontro, gestire iniziativa e PE dell'incontro | già esistente lato master |
| Pubblicare (clonare) una mappa personale, caricarne una nuova, disegnarci sopra | §6.4 |
| Mostrare/nascondere ai giocatori o eliminare una mappa condivisa | §6.4, distinti (2026-08-12) |
| Condividere una nota di campagna con tutti o con alcuni | §6.2 |
| Mostrare o nascondere il combattimento in corso | §6.5 |
| Proporre una richiesta di modifica | §7.1 |
| Rimuovere un personaggio dal mondo (senza espellere il giocatore) | archiviato, non cancellato — come l'espulsione, 2026-08-12 |
| Accettare o rifiutare una richiesta di rientro di un personaggio archiviato | §7.2, 2026-08-12 |
| Generare (o revocare) un codice di trasferimento per un giocatore | §11.9, 2026-08-17 — mai per l'owner |

**Consentito anche al `player`, ma solo su se stesso:** aggiornare i propri PF,
applicare/rimuovere le proprie condizioni, rispondere a una richiesta di
modifica, chiedere il rientro di una propria istanza archiviata, e **generare un
codice di trasferimento per il proprio dispositivo** (§11.9, 2026-08-17).

**Vietato a chiunque tranne il giocatore** — sono le scelte che definiscono il
personaggio, e toglierle svuoterebbe l'app del suo scopo:

- nome, razza, classe, sottoclasse, background, allineamento, aspetto, ritratto
- i sei punteggi di caratteristica
- competenze, talenti, stile di combattimento, scelte di sottoclasse
- salire o scendere di livello
- eliminare il personaggio

**Riservato all'`owner`:** promuovere/degradare membri, espellere, rinominare o
eliminare il mondo, trasferire la proprietà.

### 7.1 La richiesta di modifica (decisa: sì, con approvazione)

Le house rule esistono, e un master può voler cambiare davvero un punteggio.
Invece di aprire un varco permanente nei divieti qui sopra, il master compila
una **richiesta di modifica**; il giocatore la vede e **accetta o rifiuta**.

- Riguarda **solo** i campi altrimenti vietati: punteggi, competenze, talenti,
  livello, e le scelte di classe. Tutto il resto passa dalle azioni dirette:
  **il bottino non passa mai di qui**, sarebbe cinque conferme per cinque
  oggetti.
- La richiesta porta con sé una **motivazione** scritta dal master, che il
  giocatore legge prima di decidere: senza, «vuoi passare da Forza 16 a 18?»
  arriva senza contesto.
- Mostra sempre **prima → dopo**, campo per campo.
- Resta in sospeso finché non viene risolta; se il giocatore è scollegato la
  trova al rientro. Il master può revocarla.
- **Sia la richiesta sia la risposta finiscono nel registro**: chi ha chiesto,
  cosa, perché, e se è stata accettata.

La tabella `world_change_requests` (§8) è già prevista per questo.

### 7.2 La richiesta di rientro (decisa e implementata: 2026-08-12)

Un personaggio archiviato (espulsione via `member.kick`, o rimozione singola
via §7 sopra) **non torna mai visibile da solo**: prima di questa decisione
alcuni testi/commenti del codice affermavano che si sarebbe "riattivato al
primo resync del proprietario", ma nessun punto del codice lo implementava
davvero — trovato analizzando il codice dopo la richiesta di Davide di
gestire correttamente il rientro. Verso opposto di §7.1: qui propone il
**giocatore**, risponde il **master/owner**.

- Accessibile sia dalla sezione "Rimossi dai mondi" sulla Home del
  giocatore, sia dal personaggio locale di origine ("Aggiungi a un mondo" su
  un mondo dove esiste già un'istanza archiviata di quel personaggio) —
  stesso esito in entrambi i casi, un'unica richiesta.
- Un giocatore **espulso del tutto** (`member.kick`, non più membro) deve
  prima rientrare nel mondo col flusso di ingresso normale (codice/LAN/QR,
  già approvato dal master) prima di poter chiedere il rientro del vecchio
  personaggio — l'invio di QUALSIASI comando richiede di essere membro,
  nessuna eccezione per questa richiesta: due approvazioni in sequenza,
  nessuna logica di membership duplicata.
- **Due modalità**, scelte dal giocatore all'invio (mai dal master):
  `frozen` riprende l'istanza esattamente come fu archiviata; `refresh_from_local`
  sovrascrive il CONTENUTO (livello, PF, inventario, incantesimi...) con lo
  stato ATTUALE del personaggio locale di origine — che nel frattempo può
  essere cambiato, dato che le due righe (istanza congelata / locale) non si
  risincronizzano mai da sole finché non c'è un'azione esplicita —
  preservando sempre identità e collegamento al mondo dell'istanza (mai
  quelli, vuoti, del personaggio locale esportato). Disponibile solo se il
  personaggio locale di origine esiste ancora.
- Guardie anti-fantasma: una sola richiesta `pending` per personaggio alla
  volta; se il proprietario viene espulso mentre la richiesta è in sospeso,
  l'accettazione viene rifiutata automaticamente (richiesta chiusa come
  "scaduta") invece di riammettere un personaggio senza un proprietario
  membro; `create_or_resume_instance()` non "riprende" mai più in silenzio
  un'istanza archiviata (prima lo faceva, senza toglierle l'archiviazione —
  il personaggio restava invisibile al master nonostante l'apparente
  successo).

Nuova tabella `world_rejoin_requests` (§8), nuovi comandi
`character_rejoin.request`/`character_rejoin.respond` in
`core/world_permissions.py`, handler in `core/world_backend.py`. Dettaglio
completo, incluso il ragionamento su ogni guardia, in `changelog_storico.md`.

---

## 8. Schema del database

Cinque tabelle nuove e cinque colonne su `characters`. Le tabelle esistono su
**ogni** dispositivo con lo stesso schema: chi ospita ci tiene lo stato
autoritativo, chi si collega ci tiene la replica. Un solo schema, nessun ramo.

```sql
-- Un mondo/campagna.
CREATE TABLE IF NOT EXISTS worlds (
  id                TEXT PRIMARY KEY,
  name              TEXT NOT NULL,
  description       TEXT DEFAULT '',
  owner_device_id   TEXT NOT NULL,
  join_code         TEXT DEFAULT '',   -- 6 caratteri, solo sull'host
  is_local_host     INTEGER DEFAULT 0, -- 1 = questo dispositivo ospita
  last_seen_host    TEXT DEFAULT '',   -- "192.168.1.7:8765", per riconnettersi
  session_token     TEXT DEFAULT '',   -- token RemoteBackend, solo client (2026-08-07)
  last_synced_seq   INTEGER DEFAULT 0, -- ultimo evento applicato (solo client)
  created_at        TEXT NOT NULL,
  updated_at        TEXT NOT NULL
);

-- Chi partecipa a un mondo.
CREATE TABLE IF NOT EXISTS world_members (
  id            TEXT PRIMARY KEY,
  world_id      TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
  device_id     TEXT NOT NULL,
  display_name  TEXT NOT NULL,
  role          TEXT NOT NULL DEFAULT 'player',  -- owner|master|player
  is_connected  INTEGER DEFAULT 0,
  last_seen_at  TEXT DEFAULT '',
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL,
  UNIQUE (world_id, device_id)
);

-- Il giornale: sincronizzazione E registro delle azioni, insieme.
CREATE TABLE IF NOT EXISTS world_events (
  seq            INTEGER PRIMARY KEY AUTOINCREMENT,
  id             TEXT NOT NULL UNIQUE,
  world_id       TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
  actor_device_id TEXT NOT NULL,
  actor_name     TEXT DEFAULT '',      -- copiato: leggibile anche dopo un'espulsione
  kind           TEXT NOT NULL,        -- "xp.grant", "hp.change", ...
  target_type    TEXT DEFAULT '',      -- "character" | "world" | "member" | ...
  target_id      TEXT DEFAULT '',
  summary        TEXT DEFAULT '',      -- riga già leggibile per il registro
  payload        TEXT DEFAULT '{}',    -- JSON: cosa applicare
  before_state   TEXT DEFAULT '{}',    -- JSON: i soli campi toccati, prima
  created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_world_events_world_seq ON world_events(world_id, seq);

-- Bottino: archivio del master e deposito comune (vedi loot_design.md).
CREATE TABLE IF NOT EXISTS loot_stash_entries (
  id            TEXT PRIMARY KEY,
  world_id      TEXT DEFAULT '',       -- '' = archivio personale fuori dai mondi
  stash_kind    TEXT NOT NULL,         -- 'master' | 'party'
  entry_kind    TEXT NOT NULL,         -- 'item'|'magic_item'|'artifact'|'poison'|'coins'|'gem'|'art'
  name          TEXT NOT NULL,
  quantity      INTEGER DEFAULT 1,
  description   TEXT DEFAULT '',
  effects       TEXT DEFAULT '',
  coins         TEXT DEFAULT '{}',     -- JSON {"gold":150,"silver":30,...}
  source        TEXT DEFAULT '',       -- "Generatore Tesori", "Compendio", ...
  notes         TEXT DEFAULT '',
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
);

-- Richieste del master che il giocatore deve approvare (§7, valvola di sfogo).
CREATE TABLE IF NOT EXISTS world_change_requests (
  id             TEXT PRIMARY KEY,
  world_id       TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
  character_id   TEXT NOT NULL,
  requested_by   TEXT NOT NULL,
  payload        TEXT NOT NULL,        -- JSON: campi e nuovi valori
  reason         TEXT DEFAULT '',
  status         TEXT DEFAULT 'pending', -- pending|accepted|rejected|expired
  created_at     TEXT NOT NULL,
  resolved_at    TEXT DEFAULT ''
);
```

Su `characters`, cinque colonne aggiunte con `_add_column()` idempotente come
tutte le altre migrazioni del progetto:

```sql
world_id             TEXT DEFAULT ''   -- '' = personaggio locale
origin_character_id  TEXT DEFAULT ''   -- da quale personaggio locale nasce
owner_device_id      TEXT DEFAULT ''   -- di chi è il personaggio
is_replica           INTEGER DEFAULT 0 -- 1 = replica, l'autorità è altrove
world_seq            INTEGER DEFAULT 0 -- ultimo evento applicato a questa scheda
```

Su tre tabelle già esistenti servono poche colonne, tutte con lo stesso
`_add_column()` idempotente:

```sql
-- Note del master: visibilità per singola nota (§6.2)
master_campaign_notes.visibility   TEXT DEFAULT 'private'  -- private|all|selected
master_campaign_notes.shared_with  TEXT DEFAULT '[]'       -- JSON di device_id

-- Mappe: quali sono pubblicate in un mondo (§6.4)
game_maps.world_id   TEXT DEFAULT ''
game_maps.is_shared  INTEGER DEFAULT 0

-- Incontri: il master decide se i giocatori lo vedono (§6.5)
master_encounters.world_id            TEXT DEFAULT ''
master_encounters.visible_to_players  INTEGER DEFAULT 0
```

**Perché l'istanza è un record di `characters` e non una tabella nuova.** È la
scelta che rende il lavoro fattibile: le 5 schede, i 3.233 righe di
`character_repo.py`, l'export `.dndchar`, i generatori e i tab funzionano
**senza una riga di modifica**, perché un'istanza *è* un personaggio. Una
tabella parallela avrebbe imposto di duplicare o parametrizzare tutto.

**Nota su `app_settings`:** ospita `device_id` e `display_name`, ed essendo per
installazione **non** finisce nell'export `.dndchar` — la sua esclusione è già
verificata da un test esistente e va mantenuta.

---

## 9. La rete, in concreto

### 9.1 Un'astrazione, due implementazioni

```
                    WorldBackend  (interfaccia)
                    ├── send_command(kind, payload) -> Result
                    ├── fetch_events(since_seq) -> list[Event]
                    └── connection_state()
                         │
        ┌────────────────┴────────────────┐
   LocalBackend                      RemoteBackend
   scrive sul DB di questo           parla via HTTP con
   dispositivo                       l'host, applica gli
   (host LAN, e deploy web           eventi alla replica
   Docker dove tutti i client
   sono già sullo stesso DB)
```

Il deploy web esistente ricade in `LocalBackend` senza rete: lì i client sono
già sullo stesso processo e sullo stesso DB, quindi serve solo il *concetto* di
mondo (ruoli, permessi, registro), non il trasporto. **Un solo modello per
entrambe le modalità.**

### 9.2 Trasporto: HTTP su stdlib, con attesa lunga

`http.server.ThreadingHTTPServer` in un thread daemon, sulla porta 8765 (con
ripiego sulle successive se occupata). Nessuna dipendenza nuova (§3.2), e il
progetto usa già thread daemon per polling ed export.

| Rotta | Uso |
|---|---|
| `GET /world` | biglietto da visita: nome, versione protocollo, se accetta ingressi |
| `POST /join` | ingresso: codice + PIN + `device_id` + nome → token di sessione |
| `GET /events?since=N` | **attesa lunga** fino a 25 s: risponde appena c'è un evento nuovo, altrimenti a vuoto |
| `POST /command` | invia un comando, riceve esito o motivo del rifiuto |
| `GET /snapshot` | stato completo, per il primo ingresso o dopo una lunga assenza |
| `POST /leave` | uscita pulita |

**Perché attesa lunga e non WebSocket:** i WebSocket richiederebbero una
libreria esterna (§3.2) e un'implementazione a mano del protocollo. L'attesa
lunga dà latenza percepita praticamente identica (l'evento arriva appena
prodotto), sta interamente nella stdlib, e degrada da sola a un normale polling
se una rete taglia le connessioni lunghe.

**Attenzione al numero di connessioni:** un thread per client bloccato in attesa
è accettabile con 4-8 giocatori, non con 50. È un limite dichiarato e coerente
con l'uso (un tavolo di D&D).

### 9.3 Trovare la partita

Tre modi, in ordine di comodità, con l'ultimo **sempre** disponibile:

1. **Scoperta automatica** — l'host manda un breve annuncio in broadcast UDP
   sulla porta 8766 ogni 2 s (nome del mondo, indirizzo, se accetta ingressi);
   i client in ascolto lo mostrano in un elenco. Solo `socket` di stdlib,
   nessun mDNS/zeroconf. Non funziona su reti che bloccano il broadcast (molti
   Wi-Fi pubblici, «isolamento client») né su iOS senza l'entitlement (§3.5).
2. **QR code** — se disponibile (§3.3): l'host lo mostra, il giocatore lo
   inquadra. Opzionale.
3. **Codice a 6 caratteri + indirizzo** — l'host mostra `192.168.1.7:8765` e un
   codice; il giocatore li digita. Brutto ma funziona sempre, ed è il ripiego
   che rende il resto non essenziale.

### 9.4 Sicurezza, proporzionata

Rete di casa, gruppo di amici: non serve un sistema di autenticazione, serve
evitare che qualcuno entri per sbaglio o per scherzo e che chi è dentro faccia
più di quanto gli compete.

- **PIN a 6 cifre** generato a ogni apertura del mondo e mostrato dal master.
  Serve per entrare la prima volta.
- **Token di sessione** casuale (`secrets.token_urlsafe`) consegnato
  all'ingresso e da ripresentare a ogni chiamata. Legato al `device_id`.
- **Il master approva ogni nuovo ingresso** con una notifica («Marco vuole
  entrare»). I dispositivi già noti rientrano senza chiedere.
- **Solo HTTP in chiaro, dichiarato.** Il traffico è leggibile da chi è sulla
  stessa rete. In una LAN domestica è accettabile; **va scritto nella UI**, non
  lasciato intendere. HTTPS richiederebbe certificati e un'esperienza d'uso
  peggiore per un guadagno nullo in questo scenario.
- **Il server si accende solo quando il master apre un mondo** e si spegne alla
  chiusura. Nessuna porta aperta di default: l'app resta offline finché non si
  gioca insieme.
- **Nessun percorso di file, nessun comando arbitrario** attraverso la rete: i
  comandi sono un elenco chiuso con payload validato campo per campo.

### 9.5 Sincronizzazione in background — da dove parte

Principio dichiarato esplicitamente da Davide (2026-08-12): **le app
collegate devono mostrare gli stessi dati condivisi** — non solo mentre si
sta guardando la schermata "giusta". `ui/components/background_sync.py::
BackgroundSyncLoop` (thread dedicato + ponte thread-safe verso il loop
asyncio di Flet, §9.2) è il pezzo comune; ogni vista che ha bisogno di
riflettere un mondo remoto senza refresh manuale ne avvia una propria
istanza, con la propria logica di dominio (cosa scaricare, cosa conta come
"stato cambiato"):

| Vista | Cosa sincronizza | Quando parte |
|---|---|---|
| `WorldsView` | il mondo aperto in dettaglio | apertura del dettaglio |
| `MasterEncounterView` | l'incontro world-linked aperto | apertura della vista |
| `HomeView` | OGNI mondo remoto in cui questo dispositivo possiede un'istanza (2026-08-12) | risoluzione del `device_id`, resta attivo finché la Home è aperta |

`HomeView` è la più ampia delle tre: non un solo mondo, ma tutti quelli
rilevanti per questo dispositivo — è così che una rimozione decisa dal
master (§7, "Rimuovere un personaggio dal mondo") si vede sulla Home del
giocatore senza dover aprire Sezione Mondi apposta.

---

## 10. Il gioco a distanza (non ora, ma senza chiudersi le porte)

Davide l'ha rimandato esplicitamente. L'architettura scelta lo rende
un'aggiunta, non una riscrittura: `RemoteBackend` parla HTTP con un indirizzo,
e a quell'indirizzo può rispondere tanto il portatile del master in LAN quanto
il **server Docker che Davide ha già**. Tre strade possibili in futuro, in
ordine di sforzo: server Docker che ospita mondi in modo permanente (nessuna
configurazione lato giocatore, il mondo vive anche a master spento); port
forwarding sul router del master (zero codice, ma configurazione manuale e
espone una porta su internet); una VPN tipo Tailscale (zero codice, i
dispositivi si vedono come se fossero in LAN). **Nessuna delle tre richiede di
cambiare quanto progettato qui.**

---

## 11. Casi limite, e cosa succede davvero

**11.1 — Il master chiude l'app a metà sessione.** I client perdono la
connessione, mostrano «Mondo non raggiungibile» e passano in sola lettura sulla
replica. Alla riapertura si riconnettono da soli usando `last_seen_host`. Non si
perde nulla: lo stato autoritativo è nel DB del master, che è su disco.

**11.2 — Un giocatore va offline e rientra dopo due sessioni.** Chiede gli
eventi dal proprio ultimo numero. Se sono troppi (o il giornale è stato
compattato), l'host risponde «troppo indietro» e il client scarica uno
`snapshot` intero. Il caso va gestito fin dall'inizio, non aggiunto dopo.

**11.3 — Un giocatore modifica la scheda mentre è scollegato.** Con la scelta
«il mondo è la fonte di verità» la modifica **non deve essere possibile**:
scollegati, l'istanza è in sola lettura, con un avviso chiaro. È spiacevole ma è
l'unica alternativa onesta ai conflitti; il personaggio *locale* resta invece
sempre modificabile.

**11.4 — L'owner sparisce per sempre.** Il mondo vive sul suo dispositivo: gli
altri hanno solo repliche. Due rimedi, entrambi confermati: **esportazione del
mondo** in un file `.dndworld` (§6.3) e **trasferimento della proprietà** mentre
l'owner è ancora collegato. Senza un backup recente il mondo non si può
resuscitare — per questo l'app ricorda al master di esportarlo.

**11.5 — Due dispositivi aprono lo stesso mondo insieme.** Vietato: apre solo
`is_local_host = 1`, e le repliche non possono essere promosse a host senza un
passaggio di proprietà esplicito. Altrimenti nascerebbero due storie divergenti
con lo stesso identificatore.

**11.6 — Versioni dell'app diverse al tavolo.** Il biglietto da visita
`GET /world` porta un numero di versione del protocollo. Se non combacia,
l'ingresso viene rifiutato con un messaggio esplicito («aggiorna l'app»)
invece di fallire in modi imprevedibili a metà partita.

**11.7 — Cambio di rete o di indirizzo IP.** `last_seen_host` diventa vecchio;
il client ripiega sulla scoperta automatica e, se anche quella non trova nulla,
chiede l'indirizzo. Nessun blocco definitivo.

**11.8 — Lo stesso personaggio in due mondi.** Non è un errore: sono due
istanze indipendenti (§6). Va reso evidente nella UI, non impedito.

---

## 11.9 — Il giocatore cambia dispositivo (2026-08-17, implementato)

Caso **non previsto** dai §11.1-11.8, aggiunto su richiesta di Davide: *"vorrei
inserire un modo in cui un utente può accedere anche con un dispositivo diverso
al mondo, magari scaricando il proprio personaggio dall'host, assegnando un
codice univoco per accedere al mondo con quel personaggio in caso cambi
dispositivo"*.

### Il problema

L'identità di un giocatore è il `device_id` (§4): un UUID generato per
installazione e conservato in `app_settings`. Le sue istanze di personaggio sono
legate a quello (`characters.owner_device_id`), e così la sua appartenenza
(`world_members.device_id`, con `UNIQUE (world_id, device_id)`).

Un dispositivo nuovo è quindi, per l'host, uno sconosciuto senza personaggi. Lo
è anche **lo stesso dispositivo dopo una reinstallazione**, perché disinstallare
cancella `app_settings` e con esso il `device_id` — motivo per cui questa
sezione è strettamente legata alla migrazione alla firma di rilascio descritta in
RELEASE.md, l'unico aggiornamento che obbliga a disinstallare.

Le vie che esistevano già non risolvono il caso: esportare `.dndchar` e
importarlo sul dispositivo nuovo produce un personaggio LOCALE (l'import azzera
di proposito `world_id`/`is_replica`/`owner_device_id`, §14.1), che entrando nel
mondo creerebbe una SECONDA istanza — il master vedrebbe un doppione e la prima
resterebbe orfana sull'host.

### Le quattro decisioni (Davide, 2026-08-17)

| Domanda | Scelta |
|---|---|
| Trasferimento o multi-dispositivo? | **Trasferimento esclusivo.** Il vecchio dispositivo perde l'accesso. Niente `player_id` portabile separato dal `device_id`: sarebbe più potente ma un refactor che toccherebbe membri, proprietà delle schede, visibilità delle note, permessi, export/import e tutta la batteria multiplayer. |
| Chi emette il codice? | **Il giocatore per sé** (sta per cambiare telefono e ha ancora quello vecchio in mano) **e il master per un giocatore** (il telefono è perso, rotto o venduto). Senza la seconda via il caso che rende utile la funzione resterebbe scoperto. |
| Serve anche l'approvazione del master? | **Sì.** Il codice sostituisce il PIN, non l'approvazione: chi intercetta un codice non entra comunque. Riusa `PendingJoinRequest`, già collaudato. |
| L'owner può trasferirsi così? | **No.** Il suo `device_id` è su `worlds.owner_device_id` e la riassegnazione non lo tocca (riscriverlo sposterebbe la proprietà del mondo, che è un'altra operazione). Per lui la via esiste già ed è migliore: esportare `.dndworld` e importarlo sul dispositivo nuovo, che ne diventa owner e host (§6.3/§11.4). |

### Il codice

8 caratteri dall'alfabeto del codice d'ingresso (`ABCDEFGHJKMNPQRSTUVWXYZ23456789`,
senza `0/O/1/I/L`), **monouso**, con **scadenza a 7 giorni**, legato a UN membro.
Emetterne uno nuovo revoca automaticamente il precedente: un membro ha sempre al
massimo un codice valido, così un codice letto ad alta voce per sbaglio muore
appena se ne genera un altro.

**Persistito in una tabella** (`world_device_transfers`), non in memoria come il
PIN. `WorldHostServer.stop()` azzera PIN e token per progetto (§9.4) e l'hosting
si riavvia spesso (il fix `HostServerSlot` del 2026-08-07 esiste proprio per
questo): un codice emesso dal master per un dispositivo rotto e riscattato giorni
dopo, in memoria, evaporerebbe. La tabella è stato dell'HOST — non viaggia
nell'export `.dndworld` e non viene replicata ai client.

Le righe `redeemed` non si cancellano mai: sono l'audit trail **e** la fonte del
messaggio con cui l'host spiega al vecchio dispositivo perché non è più membro.

### Il protocollo: `PROTOCOL_VERSION` resta 1

`POST /join` accetta un campo `transfer_code` opzionale. **Non** è stata creata
una rotta `POST /transfer`: `handle_join` regala già la verifica di versione, il
rate limit su `device_id` (10 s), il controllo del `join_code`, la coda di
approvazione e il polling `/join/status`; e lato client `start_lan_join` →
`finish_pending_join` → `_finalize_join` esistono già. Soprattutto:
`handle_snapshot` restituisce di suo le istanze del chiamante
(`owner_device_id == device_id`), quindi **una volta fatta la riassegnazione lo
scaricamento del personaggio funziona senza una riga nuova**. Una rotta separata
avrebbe richiesto una copia parallela di tutto.

`PROTOCOL_VERSION` **non** è stato alzato a 2: la modifica è puramente additiva
(un client vecchio non manda `transfer_code`, un host vecchio ignora la chiave) e
`_check_protocol_version` è un'uguaglianza stretta che rifiuta l'ingresso con
"Aggiorna l'app su entrambi i dispositivi" — alzarlo avrebbe spento OGNI
accoppiamento esistente per una funzionalità che nessuno stava ancora usando.

Al suo posto, `GET /world` annuncia le **capacità opzionali** in
`features: ["device_transfer"]` (`protocol.HOST_FEATURES`). Un client che vuole
riscattare un codice lo verifica prima: con un host più vecchio riceve un
messaggio specifico invece di mandargli una richiesta che quello interpreterebbe
come un ingresso normale con PIN vuoto — cioè "PIN errato", fuorviante.

### La riassegnazione: cosa si sposta e cosa NON si sposta

Una sola transazione (`world_transfer_repo.rebind_device`). La riga
`world_members` mantiene lo **stesso `id`**, così le repliche la aggiornano in
posizione (`save_replica_member` fa `INSERT OR REPLACE` per `id`) senza violare
`UNIQUE (world_id, device_id)`; ruolo e nome sono preservati — cambiare
dispositivo non è né una promozione né un rinomino.

| Colonna | Azione | Perché |
|---|---|---|
| `world_members.device_id` | spostata | L'appartenenza è la cosa che si trasferisce. `is_connected` va a 0. |
| `characters.owner_device_id` | spostata, **incluse le istanze archiviate** | Senza le archiviate, il nuovo dispositivo non potrebbe mai chiederne il rientro e resterebbero orfane sull'host. |
| `master_campaign_notes.visible_to_device_ids` | rimappata (lista JSON, in Python) | Senza, il giocatore perde **in silenzio** ogni nota condivisa specificamente con lui: nessun errore, la nota semplicemente non compare più. Ristretta a `visibility='selected'` e a QUESTO mondo. |
| `world_rejoin_requests.requested_by` | spostata (solo le `pending`) | `handle_snapshot` le filtra per `requested_by`: una richiesta lasciata sul vecchio id diventa invisibile per sempre — il master la vede, il giocatore no. |
| `worlds.owner_device_id` | **mai** | Sposterebbe la proprietà del mondo; per l'owner la via è `.dndworld`. |
| `world_events.actor_device_id` | **mai** | Il giornale è un registro storico (§5): non si riscrive la storia, si aggiunge un evento. |
| `loot_stash_entries.added_by_device_id` | **mai** | Verificato: scritta, **mai letta** per autorizzare o mostrare. È pura provenienza ("chi ha messo questo qui"), e riscriverla falsificherebbe un dato storico esatto. |
| `world_change_requests.requested_by` | **mai** | È il `device_id` del MASTER che propone, non del giocatore. |
| `app_settings` | **mai** | Per installazione, per progetto (§14.2). |

Segue un evento `device_transfer.redeem` nel giornale, e la **revoca dei token
vivi** del vecchio dispositivo: la sua attesa lunga su `GET /events` torna 401 al
giro successivo, che è il segnale con cui scopre di essere stato sostituito.

Il codice non compare **mai** nel payload di un evento: il giornale è trasmesso a
tutte le repliche, il codice è un segreto per un solo membro. Torna al solo
chiamante in `CommandResult.data`, campo aggiunto per questo.

### Il destino del vecchio dispositivo: conserva, marca, congela

Non si cancella (la replica contiene il giornale, le note e le mappe ricevute,
cioè la memoria della campagna vista da lì, più il diario del giocatore) e non si
archivia (richiederebbe una colonna nuova). Diventa una **copia locale in sola
lettura**, con un chip "trasferito" nell'elenco dei mondi e un banner nel
dettaglio; l'utente la rimuove quando vuole, con l'azione che esiste già.

Marcata con `settings_repo.set_setting("world_transferred_away:<world_id>", "1")`
— nessuna modifica di schema — più l'azzeramento di `worlds.session_token`, senza
il quale `resolve_backend_for_world` ritenterebbe un ingresso completo con PIN
vuoto e mostrerebbe un errore sul PIN.

Due strade portano alla marcatura, perché il caso realistico è il secondo:
l'evento `device_transfer.redeem` visto sulla replica (se il dispositivo era
collegato al momento dell'approvazione), oppure la risposta `403` con
`reason="transferred_away"` al primo ritentativo di riconnessione (se era spento,
che è quasi sempre).

---

## 12. Decisioni: tutte chiuse

Le sette scelte che erano aperte sono state decise da Davide il 2026-07-31 —
elenco in §2, dettaglio nelle sezioni indicate lì. **Non c'è nulla di
architetturale in sospeso: il documento è pronto per l'implementazione.**

Restano solo tre tarature che si possono valutare unicamente su dispositivi
veri, e che **porterò a Davide invece di decidere da solo** quando ci si arriva:

1. **L'intervallo dei tratti sulle mappe** (§6.4): 200 ms è una stima
   ragionevole, non un valore misurato. Se su una Wi-Fi lenta il disegno
   risultasse a scatti, il ripiego è spedire a fine tratto.
2. **La frequenza del promemoria di esportazione** del mondo (§6.3): ogni
   quante sessioni ricordare il backup senza diventare fastidioso.
3. **La durata dell'attesa lunga** (§9.2): 25 s è un compromesso comune, ma
   alcuni router chiudono le connessioni ferme prima. Se succede, si abbassa.

---

## 13. Piano di lavoro proposto

Nove passi, ciascuno verificabile da solo. I primi due danno già valore anche
senza rete, e il quarto è il primo momento in cui due dispositivi si parlano.
Lo stato di avanzamento reale (cosa è fatto, cosa resta) non vive qui — è un
piano, non un tracker — ma nella sezione "Piano di lavoro attivo" di
`CLAUDE.md`, aggiornata ad ogni sessione.

| # | Passo | Contenuto | Nota |
|---|---|---|---|
| 1 | **Bottino** | archivio, deposito comune, assegnazione, percentuali | `loot_design.md` — **indipendente**, funziona già oggi in web e su un dispositivo |
| 2 | **Modello mondo, senza rete** | tabelle, identità dispositivo, ruoli, permessi, giornale, `LocalBackend` | qui il deploy web diventa già multi-utente vero |
| 3 | **Istanze di personaggio** | porta com'è / dal 1° livello / riprendi, Home raggruppata per mondo | il pezzo più delicato per i dati |
| 4 | **Host + client in LAN** | server stdlib, ingresso con codice e PIN, attesa lunga, riconnessione | primo vero test a due dispositivi |
| 5 | **Scoperta e comodità** | broadcast UDP, QR se disponibile, elenco partite vicine | tutto ripiegabile sull'inserimento manuale |
| 6 | **Interventi del master a distanza** | le azioni di §7 come comandi, registro visibile al giocatore, richiesta di modifica (§7.1) | è ciò che risolve il problema di partenza |
| 7 | **Condivisione** | note a visibilità scelta (§6.2), tracker di combattimento (§6.5), «aggiorna il mio foglio» (§6.1) | tutte poco costose una volta che gli eventi viaggiano |
| 8 | **Mappe condivise** | pubblicazione, immagine su rotta dedicata, tratti in pacchetti (§6.4) | la parte più pesante: va isolata e tarata a sé |
| 9 | **Robustezza** | snapshot, versione di protocollo, espulsione, trasferimento proprietà, **esportazione del mondo** (§6.3) | |

L'esportazione del mondo è al passo 9 solo perché ha bisogno che il modello sia
stabile: **è confermata fin da subito** e non va rimandata oltre, perché è
l'unica protezione contro la perdita del dispositivo che ospita.

Fuori da questo piano, per scelta: gioco a distanza (§10), voce o chat.

---

## 14. Interazioni col codice esistente, verificate

Cinque punti controllati sul codice reale, non ipotizzati. Il primo è un
problema vero che l'implementazione deve risolvere, non una nota.

**14.1 — L'export `.dndchar` porterebbe con sé il mondo. Va corretto.**
`character_export.py` legge e riscrive **tutte** le colonne di `characters` per
introspezione (`PRAGMA table_info`), ed è proprio la sua forza. Ma con le
colonne nuove significa che esportare l'istanza di un mondo produce un file che
porta `world_id`, `is_replica = 1`, `world_seq` e `owner_device_id`: importato
su un altro dispositivo darebbe un personaggio che dice di appartenere a un
mondo inesistente e, essendo marcato come replica, sarebbe **in sola lettura e
non riparabile dall'interfaccia**. Rimedio: `import_character()` deve azzerare
queste cinque colonne (l'importato diventa un personaggio locale a tutti gli
effetti, che è il comportamento atteso) e l'export può conservare il **nome** del
mondo di provenienza come semplice testo, per non perdere l'informazione. Va
aggiunto un test dedicato: oggi la batteria verifica solo che `app_settings`
non finisca nell'export.

**14.2 — `app_settings` è già esclusa dall'export**, ed è dove vanno `device_id`
e `display_name`: un file `.dndchar` non porterà mai l'identità di un
dispositivo su un altro. L'esclusione è già coperta da un test esistente
(`test_fase_d.py`) e va mantenuta.

**14.3 — Le migrazioni hanno già la forma giusta.** `_add_column()` è
idempotente (ignora l'errore «colonna già esistente»): le cinque colonne di
`characters` seguono la stessa strada di tutte le altre, e i DB esistenti si
aggiornano da soli alla prima apertura, senza migrazione manuale.

**14.4 — Il polling esistente va riusato, non affiancato.** `home_view.py` ha
già un thread daemon che ogni 5 s confronta una firma `id:updated_at` e
ricostruisce solo se qualcosa è cambiato. È esattamente la forma che serve al
client: cambia la sorgente (il giornale invece del DB locale) e la latenza
(attesa lunga invece di 5 s fissi). **Aggiungere un secondo meccanismo di
aggiornamento accanto a quello sarebbe un errore**: due cicli che ricostruiscono
la stessa lista.

**14.5 — I permessi Android e il commento sbagliato.** `pyproject.toml` ha
`permissions = []` con il commento «offline-first, nessuna rete richiesta». Con
questa feature vanno aggiunti `INTERNET` e `ACCESS_NETWORK_STATE` (più
`CHANGE_WIFI_MULTICAST_STATE` se si fa la scoperta automatica), e il commento va
riscritto: l'app resta *utilizzabile* offline, ma non è più *senza rete*.

---

## 15. Il rischio più grande, detto chiaramente

Non è la rete: è che **questo è il primo pezzo dell'app che non si può testare
da solo**. Tutto ciò che esiste oggi è verificabile con un DB temporaneo e una
pagina finta; un host e tre client su una vera Wi-Fi non lo sono. Le batterie di
test possono coprire il protocollo, i permessi, l'applicazione degli eventi e i
casi limite girando due backend nello stesso processo — ma **il comportamento su
una rete reale, con un telefono che si addormenta e un router che chiude le
connessioni ferme, lo può verificare solo Davide su dispositivi veri.**

Va messo in conto fin da ora, e per questo il passo 4 va fatto arrivare presto:
è il primo momento in cui si scopre se la cosa regge davvero.

> **Esito, 2026-08-17** — questo rischio si è materializzato esattamente come
> previsto, e si è chiuso: sono serviti **5 round di test su due dispositivi
> fisici** per confermare il piano, ciascuno con bug reali che nessun test del
> sandbox aveva colto (il più insidioso, il round 5, era una FK violata solo
> sulla replica di un giocatore — vedi `changelog_storico.md`, "round 5 —
> CHIUSO"). Oggi sono confermati dal vivo: scoperta LAN, ingresso via QR,
> ingresso e approvazione del master con aggiornamento automatico della
> schermata del giocatore, interventi del master a distanza, sync live di
> Incantesimi/Mappe/Diario, riconnessione dopo riavvio dell'host, note e mappe
> condivise. Restano non ancora provati dal vivo il tracker di combattimento
> condiviso (passo 7) e l'esportazione `.dndworld` (passo 9).
>
> Lezione da tenere, per la prossima feature che dipende da dati reali
> accumulati: i round 3-5 sono stati risolti solo quando si è smesso di provare
> con dati freschi e si è **riprodotto il flusso sul DB reale di Davide**
> (costruire lo snapshot con lo stesso codice dell'host, poi darlo al vero
> `_finalize_join()` con un backend finto su un DB replica vuoto).
