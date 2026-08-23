# Changelog Storico — Note Importanti

> Log cronologico dettagliato di bug corretti, decisioni architetturali, bug report di Davide e relative
> analisi/fix, con verifica end-to-end per ciascuno. **Prima di correggere un bug o affrontare un gap funzionale,
> cercare (grep) qui il termine pertinente per verificare se è già stato risolto in passato** — è lo scopo primario
> di questo file. È il file più corposo del progetto (era quasi metà di CLAUDE.md): non va letto per intero, va
> interrogato per parola chiave.

## Note Importanti

- **Sincronizzazione Multiplayer: armi/oggetti/monete/note del giocatore sovrascritte dai grant del master
  (e viceversa) + «Esci dal mondo» non disconnetteva (2026-08-20, sessione notturna autonoma)** — bug report
  Davide, la seconda volta ("in un'altra sessione ti avevo scritto queste istruzioni, le tue modifiche non hanno
  avuto effetto"): "aggiunta nota da parte del giocatore dopo nota master, cancella nota master... succede lo
  stesso con le mappe e incantesimi e tutto ciò che concede il master sulla scheda del giocatore (anche
  assegnazione oggetti e incantesimi e abilità)... devono coesistere non si devono sovrascrivere" + "il giocatore
  non ha la possibilità di lasciare e poi eliminare il mondo... l'abbandono del giocatore dal mondo deve
  disconnettere il giocatore".

  **Causa radice (note/oggetti)**: `core/world_sync.py::_resync_character_from_host()` rimaterializza per intero
  un personaggio da un evento mutante qualsiasi (DELETE CASCADE + reinsert di tutte le 13 `CHILD_TABLES` di
  `character_export.py` dallo snapshot dell'host). Incantesimi/diario/note di sessione/abilità custom erano già
  stati messi in sicurezza in una sessione precedente con comandi `*.self_*` che li scrivono SULL'HOST prima che
  un resync possa cancellarli — ma **`inventario_tab.py` (armi, oggetti, monete) e la creazione/modifica/
  eliminazione di note NPC/luogo/missiva in `diary_view.py` (`campaign_notes`, tabella DIVERSA da
  `master_campaign_notes` — quella del master, mai toccata da questo bug) erano rimasti fuori**, scrivendo SOLO
  in locale. Risultato: una qualunque aggiunta manuale del giocatore spariva al primo evento mutante successivo
  (anche un'azione del master non correlata, es. `xp.grant`) — non un vero conflitto "ultimo che scrive vince",
  un dato mai arrivato sull'host che il resync tratta come mai esistito. Bug MINORE gemello in `diary_view.py`:
  `_load_notes()` sovrascriveva `self._notes[cat]` con SOLO le proprie note appena salvate/eliminate, senza
  richiamare `_merge_shared_notes()` — le note condivise dal master sparivano dalla vista per ~2s fino al
  prossimo giro del polling periodico.

  **Fix**: 8 nuovi comandi in `core/world_permissions.py` (`CMD_WEAPON_SELF_UPSERT`/`_REMOVE`,
  `CMD_INVENTORY_SELF_UPSERT`/`_REMOVE`, `CMD_CURRENCY_SELF_UPDATE`, `CMD_CAMPAIGN_NOTE_SELF_CREATE`/`_UPDATE`/
  `_DELETE`) con handler in `core/world_backend.py`, stesso principio di `CMD_HP_SELF_UPDATE`/
  `CMD_SPELL_SELF_UPSERT` — ruolo minimo `player`, verifica `perm.is_character_owner()`, dentro
  `CHARACTER_MUTATING_COMMANDS` (un terzo dispositivo, es. un co-master, deve rimaterializzare). A differenza
  degli incantesimi (chiave naturale `character_id+name+level`), armi/oggetti/note non hanno una chiave naturale
  (due armi possono avere lo stesso nome): `weapon_id`/`item_id`/`note_id` sono generati lato CLIENT prima della
  scrittura locale e passati sia alla scrittura locale sia al comando, così client e host restano sullo stesso id
  fin dalla creazione (stesso principio già in uso per `CMD_CHARACTER_INSTANCE_SYNC`) — `create_weapon()`/
  `create_inventory_item()`/`create_campaign_note()` in `character_repo.py` ora accettano un id opzionale;
  `create_campaign_note()` ritorna l'id creato invece di un bool (unico chiamante esistente non ne usava il
  ritorno, cambio sicuro); nuovi `get_weapon_by_id()`/`get_inventory_item_by_id()`/`get_campaign_note_by_id()`
  per la verifica di proprietà lato host e per rileggere lo stato da inoltrare. `inventario_tab.py`: nuovi
  `_push_weapon_to_world()`/`_push_item_to_world()`/`_push_currency_to_world()` (rileggono la riga appena scritta
  e inoltrano TUTTI i campi in un colpo solo, un solo punto invece di ricostruire il payload nei ~10 punti di
  mutazione del tab — dialog armi/oggetti, elimina, equip/grip/sintonia/esclusione armatura, editor monete).
  `diary_view.py`: `_load_notes()` ora richiama sempre `_merge_shared_notes()` in coda; nuovo
  `_push_campaign_note_to_world()` agganciato a crea/modifica/elimina nota.

  **Causa radice («Esci dal mondo»)**: `ui/views/world/world_view.py::WorldsView._do_leave()` inviava
  `CMD_MEMBER_LEAVE` (rimozione membro + archiviazione istanze sull'host — già corretto) e cancellava la replica
  locale del mondo, ma non chiamava MAI `RemoteBackend.leave()` (`POST /leave`, il meccanismo che invalida
  davvero il token — già esisteva e già testato in isolamento in `test_lan_host_client.py`, semplicemente non
  richiamato da qui): il token restava valido sull'host anche a mondo abbandonato. Fix: `_do_leave()` ora
  recupera il `RemoteBackend` dalla cache (`self._remote_backends.pop(world.id, None)`) e chiama `.leave()` prima
  di cancellare la replica locale. Lato "il master non deve più vedere il giocatore/personaggio": già corretto
  a monte da `_handle_member_leave()`/`archive_world_instances()` (stessa archiviazione non distruttiva del kick,
  filtrata da ogni query del master via `world_instance_archived=0`) — nessuna modifica necessaria lì, solo
  verificato.

  **Non affrontato in questo giro** (fuori scope dei bug riportati, verificato ma non toccato): le "mappe"
  citate da Davide non condividono questo meccanismo — le mappe personali sono già escluse dal resync
  (`skip_tables={"game_maps"}`) e le mappe condivise usano già comandi a evento incrementale
  (`CMD_MAP_PUBLISH`/`_DRAW`/`_DELETE`/`_VISIBILITY`), non un full-replace; probabile che il sintomo riportato
  fosse lo stesso pattern generale osservato su note/oggetti nella stessa sessione di test. `class_resources`/
  `creature_entries`/`character_proficiencies` (altre 3 `CHILD_TABLES` senza self-command) non hanno un punto di
  scrittura manuale diretto in UI paragonabile — non affrontate, da riconsiderare se Davide segnala lo stesso
  sintomo lì.

  **Aggiornamento della stessa sessione, dopo prima conferma di Davide** ("risolto per le note e gli altri
  problemi, ma non per le mappe... quando seleziono una nota in diario, in una sezione ricarica la pagina e mi
  porta in alto... cosa succede se il giocatore inserisce una nota/mappa mentre il mondo non è hostato? cosa
  succede lato utente e master quando un giocatore abbandona il mondo?"). Ipotesi iniziale sulle mappe (nessun bug,
  già protette diversamente) **smentita** dal secondo bug report di Davide con la riproduzione esatta: "avevo 2
  mappe locali e una condivisa, carico manualmente una terza mappa, la mappa condivisa sparisce e rimangono solo
  le 2 mappe locali" — bug reale trovato subito dopo. Quattro fix in totale in questo secondo giro:

  1. **`diary_view.py` — scroll del pannello sinistro azzerato ad ogni selezione**: `_on_sel_note()`/
     `_on_sel_diary()`/`_on_cat_click()` chiamavano tutti `_refresh()` (rebuild completo), e
     `_build_left_panel()` creava un `ft.Column(scroll=...)` NUOVO ad ogni chiamata — stesso identico difetto già
     risolto altrove con `ScrollMemoryListView`/`ScrollMemoryColumn` (`ui/widgets.py`), qui MAI applicato a questa
     vista. Fix: `self._left_scroll_col` è ora un `ScrollMemoryColumn` UNICO creato in `__init__`,
     `_build_left_panel()` ne ripopola solo `.controls` (nuovo `_fill_left_scroll_col()`), `_refresh()`/il
     `_redraw()` del polling periodico chiamano `restore_scroll()` in coda.

  2. **`_do_leave()` non staccava la PROPRIA istanza locale dal mondo** — bug più serio, trovato rispondendo alla
     domanda "cosa succede lato utente quando un giocatore abbandona il mondo": `world_repo.delete_world()`
     cancella la riga `worlds` ma (per design dichiarato nel suo stesso docstring, mai più vero dal passo 3 in
     poi) NON tocca `characters` — la propria istanza restava con `world_id` puntato a un mondo appena sparito.
     `HomeView._partition_characters()` la raggruppa comunque per quel `world_id` (`by_world[world_id]`), ma
     `refresh()` filtra le sezioni sui soli `available_worlds` (`world_repo.get_worlds_for_device()`, che non lo
     contiene più): **il personaggio spariva del tutto dalla Home, in nessuna sezione** (non "locale" — `world_id`
     ancora valorizzato —, non "in un mondo" — il mondo non c'è più —, non "Rimosso dai mondi" — quella sezione è
     solo per `world_instance_archived`, mai scritto per un'uscita volontaria). Fix: nuova
     `character_repo.detach_world_instances(world_id, owner_device_id)` — azzera `world_id`/
     `origin_character_id`/`owner_device_id`/`world_seq` sulla PROPRIA copia locale (mai quella sull'host, che
     resta archiviata da `_handle_member_leave` come già corretto), riportandola a personaggio locale a tutti gli
     effetti (dati intatti: livello, inventario, incantesimi). Deliberatamente NON lo stesso trattamento
     dell'espulsione (`archive_world_instances`, congelata in attesa di un rientro approvato dal master): qui è
     uscita volontaria, il mondo sta per sparire anche localmente, un "rientro" non sarebbe nemmeno proponibile.
     Chiamata in `_do_leave()` subito prima di `world_repo.delete_world()`.

  3. **`ui/views/maps_view.py::_back_to_list()` — mappa condivisa che sparisce caricandone una locale** — bug
     riprodotto dal vivo da Davide (vedi sopra). Causa: `_build()` (chiamata all'apertura della sezione) compone
     correttamente `self._maps = maps_repo.get_maps(character_id) + self._shared_maps`, ma `_back_to_list()`
     (richiamata tornando alla lista dopo aver aperto/creato una mappa personale — lo stesso passo che segue un
     caricamento manuale) faceva `self._maps = maps_repo.get_maps(character_id)`, **senza** `+ self._shared_maps`
     — stesso identico difetto già corretto in `diary_view.py::_load_notes()` la sessione precedente, qui mai
     toccato. Non autoguarito: il ciclo di sync periodico (`_start_world_sync`) richiama
     `_refresh_shared_maps()` (che avrebbe corretto la lista) SOLO quando la firma `world.last_synced_seq` cambia
     — un'azione puramente locale come caricare una mappa propria non genera mai un nuovo evento nel giornale del
     mondo, quindi la mappa condivisa restava assente indefinitamente, non solo per un istante, esattamente come
     descritto da Davide. Fix: una riga, `self._maps = maps_repo.get_maps(character_id) + self._shared_maps`.

  4. **Coda di ritentativo per i comandi `*.self_*`** — chiude il "punto debole reale" segnalato rispondendo alla
     domanda "cosa succede se il giocatore inserisce una nota mentre il mondo non è hostato?": prima di questo fix
     la risposta era "resta solo in locale finché non arriva un resync innescato da altro, che la sovrascrive" —
     `push_character_self_command()` era "best effort" senza alcun ritentativo, a differenza di
     `CMD_CHARACTER_INSTANCE_SYNC` (`host_sync_pending`/`push_pending_instances`, passo 6 sopra). Nuova tabella
     `pending_self_commands` (id, character_id, world_id, device_id, kind, payload, created_at — self-healing in
     `data/database.py`) + `world_repo.enqueue_pending_self_command()`/`list_pending_self_commands()`/
     `delete_pending_self_command()`: `push_character_self_command()` mette in coda quando l'host non è
     raggiungibile ORA (`backend is None`) o il trasporto solleva un'eccezione; nuova
     `core/world_sync.py::push_pending_self_commands()` (stesso principio di `push_pending_instances`, stesso
     cooldown anti-spam condiviso) la svuota in ordine FIFO al prossimo giro utile, chiamata dallo stesso loop di
     `ui/views/world/world_view.py::WorldsView._start_detail_sync` che già chiama `push_pending_instances`. Scelta
     deliberata: su un fallimento **non** si rimuove mai dalla coda (a differenza di
     `push_pending_instances`/`push_pending_instance`, dove un rifiuto e un problema di raggiungibilità restano
     distinguibili) — `RemoteBackend.send_command()` non solleva mai, quindi un host tornato di nuovo
     irraggiungibile PROPRIO durante un ritentativo produrrebbe lo stesso esito di un vero rifiuto applicativo; la
     scelta più sicura è ritentare sempre, al costo (mai osservato in pratica: i payload sono costruiti dal codice
     stesso, mai da input libero) di un comando davvero invalido ritentato invano senza mai corrompere nulla. Un
     rifiuto esplicito immediato (host raggiungibile, comando rifiutato) resta invece "sparato e dimenticato" come
     prima — ritentarlo non lo farebbe mai riuscire.

  **Risposte alle due domande dirette di Davide, verificate a codice (non solo a parole) e comunicate in chat,
  ora entrambe chiuse**: "cosa succede se il giocatore inserisce una nota/mappa/altro mentre il mondo non è
  hostato" — la scrittura LOCALE è sempre corretta subito; l'invio all'host va in coda e viene ritentato da solo
  al ritorno online (punto 4 sopra, prima restava perso). "Cosa succede lato utente/master quando un giocatore
  abbandona il mondo" — lato giocatore: disconnesso, mondo rimosso dalla lista, PROPRIO personaggio tornato
  locale con tutti i dati intatti (punto 2 sopra); lato master: membro rimosso, istanza archiviata (già corretto
  prima di questa sessione, solo verificato).

  **Terzo aggiornamento della stessa sessione**, su domanda diretta di Davide sui due residui ambientali del
  `Verificato` sotto ("mi spieghi cosa sono e se è il caso di eliminarli?"). `test_qr_scan.py`: confermato NON un
  bug — `qr_scanner_view.py` importa `flet_camera`/`flet_permission_handler` in un `try/except ImportError` già
  commentato nel sorgente come "pacchetto non installato in questo ambiente"; su un dispositivo reale o in CI con
  quei pacchetti installati i due controlli passerebbero. Nessuna azione. `test_versione_app.py`: trovato un vero
  BUG NEL TEST, non nell'app — il controllo "il prossimo versionCode supera quello di ogni tag già rilasciato"
  confrontava `compute_build_number(FIRST_SIGNED_VERSION)` invece di `compute_build_number(APP_VERSION)`:
  `FIRST_SIGNED_VERSION` è un marcatore storico FISSO ("prima versione firmata", `version.py`, mai pensato per
  cambiare), quindi il controllo era strutturalmente destinato a fallire per sempre non appena fosse esistito un
  tag più recente di v0.3.0 (v0.3.1 in poi, già taggati) — confrontava contro il passato, non "il prossimo".
  Corretto a `version.APP_VERSION`. **Resta comunque rosso anche dopo il fix** (verificato: `APP_VERSION="0.3.2"`
  in sorgente è ancora identico all'ultimo tag già pubblicato, `v0.3.2` — stesso versionCode, non superiore): è il
  comportamento CORRETTO ora, un cancello pre-release che segnala "alza `APP_VERSION` prima del prossimo tag", non
  un'asserzione pensata per restare sempre verde tra un rilascio e l'altro.

  Verificato: `compileall` pulito, suite intera 36/38 file al 100% (`test_qr_scan.py` per limite d'ambiente —
  pacchetti mobile-native non installati qui — e `test_versione_app.py` per il cancello pre-release descritto
  sopra, non un vero residuo "ambientale" dopo il fix del refuso; un terzo file, `test_fase_4.py`, ha mostrato UNA
  volta un fallimento su un test preesistente non deterministico — tiro d20 casuale confrontato come sottostringa
  — e riconfermato 3/3 volte subito dopo, nessuna relazione con questa sessione). `test_note_e_inventario_sync.py`
  esteso a 93/93 (da 80): oltre a quanto sopra, riproduce anche il meccanismo esatto del bug delle mappe (una
  `MapsView` con mappe locali + una condivisa, `_back_to_list()` senza il fix fa sparire quella condivisa) e la
  coda di ritentativo end-to-end (host offline → comando in coda → host torna online tramite un vero
  `WorldHostServer` → coda svuotata con successo, id preservato). Nessuna regressione sulle suite esistenti
  (`test_mondo_senza_rete.py` 197/197, `test_master_remote_actions.py` 81/81, `test_lan_host_client.py` 113/113,
  `test_note_sharing.py` 26/26, `test_world_view_remote_routing.py` 16/16, `test_character_instance_sync.py`
  20/20, `test_home_sync_rimozione_mondo.py` 14/14, `test_istanze_personaggio.py` 67/67, `test_mappe_condivise.py`
  82/82, `test_mappe_condivise_ui.py` 64/64). **Lavoro svolto in
  autonomia notturna su mandato esplicito di Davide ("porta a termine il lavoro, hai il permesso di fare quello
  che vuoi") — nessun commit fatto**, da rivedere e testare dal vivo su due dispositivi fisici al risveglio
  (stesso limite di sempre: un vero conflitto a due database separati non è simulabile in modo affidabile in
  questo sandbox, qui verificato con lo stesso meccanismo — snapshot host applicato via
  `import_replica_character()` — usato da `_resync_character_from_host()` stesso).

- **Bottino: deposito del gruppo interattivo + campi meccanici arma/armatura (2026-08-20)** — seconda revisione
  dello stesso giorno del passo 6, su bug report/richieste dirette di Davide dopo averlo provato dal vivo.

  **1. Deposito del gruppo, da sola-lettura ad auto-servizio** — Davide: "non ne capisco il senso, serve solo a
  mostrare il bottino... il gruppo non può interagire con esso?". Risposta: sì, ora può. Nuovo comando
  `CMD_LOOT_STASH_CLAIM` (`core/world_permissions.py`, ruolo minimo `player` — l'unico comando `loot_stash.*` NON
  riservato a master/owner) e handler `_handle_loot_stash_claim()` in `core/world_backend.py`: un giocatore prende
  una voce per intero (mai una quota) direttamente sulla propria scheda in UN solo comando che applica e rimuove
  insieme (a differenza di `CMD_LOOT_ASSIGN`, che lascia alla UI un secondo comando `CMD_LOOT_STASH_DELETE`).
  Verifica di proprietà come `CMD_HP_SELF_UPDATE` (`perm.is_character_owner`): un giocatore reclama solo per il
  proprio personaggio. Pulsante «Prendi» per voce in `WorldsView._shared_loot_section()`, visibile solo a un
  membro con un personaggio attivo in quel mondo. **Bug pre-esistente trovato e corretto nello stesso giro**:
  `CMD_LOOT_ASSIGN` non era mai stato aggiunto a `CHARACTER_MUTATING_COMMANDS` — un oggetto assegnato dal Master a
  un giocatore su un dispositivo DIVERSO dall'host non faceva mai rimaterializzare la replica di quel giocatore
  (mai per costruzione, non un caso raro). Corretto insieme a `CMD_LOOT_STASH_CLAIM` (stessa forma). Design doc
  aggiornato in `loot_design.md` §6.

  **2. Campi meccanici per voci "weapon"/"armor"** — Davide: "il tipo di voce... non ti fa selezionare armi
  armature... devono avere le stesse caselle di quando crei l'arma o l'armatura nella sezione giocatore, manca il
  danno il tipo di arma ecc.", e la stessa lacuna nell'Oggetto Magico Personalizzato. Nuove 9 colonne
  `loot_stash_entries.weapon_*`/`armor_*` (migrazione self-healing in `data/database.py`), nuovi campi omonimi su
  `LootStashEntry`. Due nuovi `entry_kind`: "weapon" (dado danno, tipo danno, categoria semplice/guerra,
  proprietà testo libero, bonus attacco/danno magici) e "armor" (CA base, tipo leggera/media/pesante/scudo,
  effetti testo libero) — stesso sottoinsieme di campi già offerto e approvato da Davide (non l'intero dialog
  armi del giocatore con Versatile/Accurata/override attacco: quelli dipendono dal personaggio che la riceverà,
  non dalla voce di bottino). Form condivisi `build_weapon_mechanics_fields()`/`build_armor_mechanics_fields()` in
  `master_loot_assign_dialog.py`, riusati da **entrambi** i punti lamentati da Davide: "+ Aggiungi voce"/"Modifica
  Voce" di `master_loot_view.py`, e l'Oggetto Magico Personalizzato di `master_magic_item_generator_dialog.py`
  (nuova `_custom_mechanics_kind()`: la categoria scelta — "Arma (qualsiasi spada)", "Armatura (scudo)", ecc. —
  determina se mostrare le caselle meccaniche, riusando lo stesso `magic_item_category_base()` già impiegato da
  `magic_items_view.py` per l'icona). **Una voce "weapon" assegnata/presa crea sempre una riga vera in `weapons`,
  mai un `inventory_items` generico** (`character_repo.create_weapon()`); "armor" crea un `inventory_items` con
  `category="armor"` e i campi CA/tipo/effetti — stessa logica duplicata correttamente nei 3 punti che scrivono su
  un personaggio: `_handle_loot_assign`/`_handle_loot_stash_claim` (rete, in `core/world_backend.py`) e
  `_create_recipient_item()` (locale, in `master_loot_assign_dialog.py`). I campi meccanici sopravvivono anche
  quando una voce arma/armatura viene rimandata al deposito/archivio invece che assegnata (bug collaterale
  trovato e corretto in corsa: `_move_or_create_stash()`/`_create_stash_split()` non li propagavano).

  **Bug di battitura trovato durante l'implementazione**: l'INSERT di `loot_repo.create_entry()`/
  `replica_upsert_entry()` aveva 25 colonne ma solo 24 placeholder `?` — un `?` mancante in entrambe le query dopo
  l'aggiunta delle 9 nuove colonne (sqlite3 solleva `ProgrammingError`, `create_entry()` lo cattura e ritorna
  `None` silenziosamente: **ogni voce di bottino, di qualunque tipo, avrebbe smesso di salvarsi** se non catturato
  dai test prima del commit). Trovato subito dal primo giro di test dopo la migrazione schema, corretto.

  Verificato: `compileall` pulito, suite intera 33/35 file al 100% (stessi 2 residui ambientali pre-esistenti —
  `test_qr_scan.py`, `test_versione_app.py`). Nuovi test: `test_loot_stash_claim()`,
  `test_loot_weapon_armor_mechanics()` in `test_master_world_scoping.py` (round trip repository, presa dal
  deposito con verifica che l'arma finisca in `weapons` e MAI in `inventory_items`, assegnazione dal Master con
  gli stessi campi); `test_worlds_view_claim_loot()` (click reale sul pulsante «Prendi», dialog di conferma
  incluso) e `test_custom_magic_item_weapon_armor_detection()` in `test_mondo_senza_rete.py`. **Nessun commit
  fatto.**
  **Non affrontato in questo giro** (segnalato da Davide, richiede design): fields per veleni/gemme/oggetti
  d'arte oltre ad arma/armatura — non richiesti esplicitamente, restano voci testo libero come prima.

- **Bottino: "Salva nell'archivio"/"Sposta nell'archivio" risultavano vuoti, assegnazione dal Compendio Oggetti
  Magici sempre locale (2026-08-20)** — bug report Davide dopo aver provato il passo 6. Tre cause distinte, stessa
  famiglia (world-scoping incompleto):
  1. **`save_items_to_stash(items)` chiamata senza `world_id=world_id` in TUTTI E SEI i punti che la usano**
     (`master_artifacts_dialog.py` ×2, `master_health_hazards_dialog.py`, `master_magic_item_generator_dialog.py`,
     `master_treasure_dialog.py`, `magic_items_view.py`) — le voci finivano sempre in `world_id=""`, invisibili
     nella vista Archivio che filtra per il mondo selezionato in `MasterView`. `world_id` era già disponibile in
     ogni chiamante (usato correttamente due righe sopra per "Assegna…"): un parametro dimenticato, non un problema
     di design. Fix: aggiunto `world_id=world_id` a tutte e sei le chiamate.
  2. **`core/world_backend.py::_handle_loot_stash_move`** azzerava `new_world_id` a `""` quando la destinazione era
     `"master"` (`new_world_id=ctx.world_id if new_kind == "party" else ""`) — "Sposta all'Archivio" da
     `master_loot_view.py` (tab Bottino, con un mondo selezionato) passa da questo handler via
     `CMD_LOOT_STASH_MOVE`, quindi la voce spostata spariva dalla vista Archivio pur essendo tecnicamente ancora
     nel DB. Fix: `new_world_id=ctx.world_id` sempre, in entrambe le direzioni — l'archivio del Master resta
     privato/mai sincronizzato ma è comunque world-scoped, esattamente come il deposito del gruppo (stesso
     principio già stabilito dall'audit del 2026-08-12, "loot_repo — Bottino... world-scoped su ENTRAMBI gli
     stash_kind").
  3. **`MagicItemsView` (tab "Oggetti Magici" della Sezione Master, `ui/views/magic_items_view.py`) era l'UNICA tab
     istanziata senza `world_id`/`device_id`** (`MasterMagicItemsView()` in `master_view.py:654`, contro
     `MasterLootView(world_id=..., device_id=...)`/`MasterNpcListView(world_id=...)`/ecc. per tutte le altre 4
     tab) — "Assegna…" e "Salva nell'archivio" dal Compendio (264 voci) risultavano quindi SEMPRE locali:
     `character_repo.get_master_visible_characters("")` mostra solo i personaggi locali (mai le istanze del mondo
     selezionato, vedi il suo stesso docstring), e l'assegnazione non passava mai da `CMD_LOOT_ASSIGN` verso
     l'host. Fix: `MagicItemsView.__init__` accetta ora `world_id`/`device_id`, li inoltra a
     `show_loot_assign_dialog()`/`save_items_to_stash()`, `master_view.py` li passa come ogni altra tab.
  **Audit di coerenza** (richiesto esplicitamente da Davide, "controlla anche le altre sezioni"): verificati tutti
  i punti che generano bottino nella Sezione Master — Generatore Tesori, Generatore Oggetti Magici, Compendio
  Oggetti Magici, Artefatti, Veleni (tutti e 5 ora coerenti) — e le due tab senza funzioni di bottino, Trappole e
  Ambiente (`show_traps_dialog`/`show_forest_encounters_dialog`, nessun bug: non generano mai voci assegnabili,
  quindi non necessitavano di questo wiring). Nessun'altra tab Master risultava mancante.
  Nuovi test: `test_loot_stash_move_handler_preserves_world_id()` in `test_master_world_scoping.py` (sezione [7],
  passa dal vero `CMD_LOOT_STASH_MOVE` via `LocalBackend`, non dalla funzione di repository direttamente, per
  coprire lo strato che conteneva il bug reale); `test_magic_items_view_world_scoped_loot()` in
  `test_mondo_senza_rete.py` (sezione [10], apre davvero il dialog di dettaglio di una voce del Compendio e clicca
  "Salva nell'archivio"/"Assegna…" per verificare che il world_id/device_id arrivino corretti). Verificato:
  `compileall` pulito, suite intera 33/35 file al 100% (stessi 2 residui ambientali pre-esistenti). **Nessun
  commit fatto.**
  **Non affrontato in questo giro, segnalato da Davide nello stesso bug report** (richiede più lavoro/decisioni di
  design, vedi CLAUDE.md "Piano di lavoro attivo"): tipi di voce limitati in "+ Aggiungi voce" del Bottino (niente
  arma/armatura con i campi dedicati danno/tipo arma/CA), stessa lacuna nell'Oggetto Magico Personalizzato quando
  si sceglie di crearlo come arma/armatura, e una domanda di design aperta sullo scopo del Deposito del Gruppo
  (oggi in sola lettura per i giocatori — Davide ne chiede conferma/chiarimento).

- **Sistema Bottino, passo 6 — deposito del gruppo lato giocatore (2026-08-20)** — ultimo passo rimasto di
  `loot_design.md` §8, sbloccato dal modello mondo del Multiplayer (passo 2, chiuso il 2026-08-05). Tutta
  l'infrastruttura di rete (comandi `CMD_LOOT_STASH_*`, evento di giornale, sync via snapshot/evento incrementale
  su `loot_repo.replica_upsert_entry`/`replica_delete_entry`) era **già stata costruita insieme ai passi 1-5** —
  mancava solo la UI: nessuna vista lato giocatore mostrava mai il deposito comune (`stash_kind="party"`).
  Aggiunta `WorldsView._shared_loot_section()` in `ui/views/world/world_view.py` — sola lettura, visibile a
  QUALSIASI membro del mondo (non solo master/owner), stesso principio di `_shared_notes_section()`/
  `_shared_maps_section()` già presenti nella stessa vista: mostra nome/quantità/riepilogo monete di ogni voce nel
  deposito, mai l'archivio privato del Master (`stash_kind="master"`, resta un contenitore separato per
  `world_id`+`stash_kind`). Nessun pulsante di assegnazione/modifica/eliminazione qui, per design (§6: "non può
  servirsi da solo — è il master a distribuire"): l'assegnazione resta un privilegio della tab «Bottino» della
  Sezione Master (`master_loot_view.py`), che già scrive su inventario/monete del destinatario e lascia una riga
  nel registro mostrato da `_events_section()`, riusata as-is (nessuna modifica lì). Riuso diretto di
  `_coin_summary()`/`_KIND_ICONS`/`_KIND_LABELS`/`_MAGIC_KINDS` da `master_loot_view.py` (stesso pattern di import
  già in uso in questo file per `ui/views/maps_view.py`) invece di duplicare la logica di rendering. Nuovo test
  `test_worlds_view_shared_loot()` in `test_mondo_senza_rete.py` (sezione [9], 10 controlli nuovi): sezione assente
  a deposito vuoto, voce dell'archivio privato del Master mai visibile qui, voci del deposito visibili a master E
  giocatore semplice, nessuna azione di modifica esposta. Verificato: `compileall` pulito, suite intera 33/35 file
  al 100% (stessi 2 residui ambientali pre-esistenti — `test_qr_scan.py`, `test_versione_app.py`, non causati da
  questo lavoro). **Nessun commit fatto.**

- **Aggiornamento automatico in-app + trasferimento del personaggio su un altro dispositivo (2026-08-17)** — due
  richieste di Davide nella stessa sessione, che si sono rivelate lo stesso problema visto da due lati.
  Progettazione in `multiplayer_design.md` §11.9 (trasferimento) e `RELEASE.md` (firma di rilascio); dettaglio dei
  moduli in `architettura_moduli.md`. Le richieste: *"l'upgrade automatico dell'app con la barra del download e la
  scritta aggiornamento completato, senza dover eliminare e reinstallare l'app ogni volta"* e *"un modo in cui un
  utente può accedere anche con un dispositivo diverso al mondo, magari scaricando il proprio personaggio
  dall'host... in caso cambi dispositivo"*.

  **LA CAUSA RADICE DELLA DISINSTALLAZIONE NON ERA LA UI — ERA LA FIRMA DELL'APK.** `pyproject.toml` non aveva
  alcuna configurazione di firma Android, quindi il gradle generato ricadeva su
  `signingConfig = signingConfigs.getByName("debug")` (verificato nel file realmente prodotto,
  `build/flutter/android/app/build.gradle.kts`, non dedotto) e Flutter/Gradle rigenera il keystore di debug su
  **ogni runner CI**: ogni release aveva una firma diversa e Android rifiutava l'aggiornamento in loco
  (`INSTALL_FAILED_UPDATE_INCOMPATIBLE`), obbligando a disinstallare — e la disinstallazione cancella il database,
  `app_settings` incluso, quindi anche il `device_id`. Nessuna barra di download poteva aggirarlo: **è per questo
  che la firma è stata affrontata prima della UI.** (Concorrente storico, secondario: `applicationId` è cambiato da
  `com.flet.dnd_companion` a `com.davmos9.dndcompanion` alla v0.1.36 — le installazioni ≤ v0.1.35 non potevano
  aggiornarsi in loco a prescindere dalla firma.) Fix: le quattro variabili `FLET_ANDROID_SIGNING_*` come `env:`
  dello step di build — verificato nel sorgente installato di flet_cli 0.86.5 (`build_base.py:1217` e `:2166`) che
  `FLET_ANDROID_SIGNING_KEY_STORE` attiva ANCHE il blocco `signingConfigs { create("release") }` del template
  gradle, condizionato a `cookiecutter.options.android_signing`, quindi non serve nulla in `pyproject.toml`; il
  percorso del keystore deve essere ASSOLUTO perché nel gradle è `file(it)` dentro il modulo `app`. Più uno step
  **"Verify APK signature and version"** che fa fallire la release se l'APK torna a essere firmato in debug: è lo
  step che *dimostra* il fix invece di sperarlo.

  **Perché le due richieste erano la stessa cosa.** La disinstallazione una-volta-sola della migrazione cancella il
  `device_id`, quindi un dispositivo reinstallato è per ogni host un dispositivo NUOVO, senza personaggi. Il codice
  di trasferimento è esattamente il meccanismo di recupero per quella disinstallazione. Ordine di consegna scelto
  con Davide: **prima il trasferimento** (tutto verificabile in sandbox, nessun dispositivo necessario), poi la
  firma.

  **Tre bug preesistenti trovati strada facendo, tutti silenziosi:**
  1. `pyproject.toml` aveva `build_number = 1` hardcoded e la CI non lo iniettava affatto: riscriveva invece una
     chiave `app.version` **che non esiste più dal 2026-08-07** — una sostituzione a vuoto, nessun errore. Ogni APK
     mai rilasciato porta `versionCode 1`. Ora la formula vive in `version.compute_build_number()` (testabile) e la
     composite action `.github/actions/inject-version` **fallisce** se una sostituzione non trova nulla — la classe
     di bug non può ripetersi.
  2. `config/settings.py` conteneva un secondo `APP_VERSION = "0.1.0"` che nessuno importava. Non era codice
     inerte: `ui/app.py` fa `from config.settings import *`, quindi la costante sbagliata *entrava* nel namespace.
     Rimosso, con un test che impedisce il ritorno.
  3. `webbrowser.open(url)` in `ui/app.py` — il pulsante "Scarica" del dialogo di aggiornamento — è quasi
     certamente **un no-op su Android**: nessun binario browser né `xdg-open` nel sandbox dell'app, e in quel caso
     `webbrowser.open()` restituisce `False` in silenzio. Il pulsante probabilmente non faceva nulla da quando
     esisteva. Sostituito con `url=ft.Url(...)`, l'unico meccanismo verificato in questo progetto (vedi
     `regole_flet_api.md`, sezione nuova "APRIRE UN URL").

  **Contraddizione nella documentazione, chiusa da Davide.** `regole_flet_api.md` diceva che `save_file` su Android
  era "probabilmente soggetto allo stesso bug ma non confermato", `world_view.py` sosteneva che l'export mobile
  funzionasse. La risposta era bloccante (l'export è il backup obbligatorio prima della disinstallazione): chiesto
  direttamente, **l'export da tablet Android funziona e il file si ritrova.** Documentazione allineata.

  **Scelte deliberate, con la motivazione:**
  - **Nessuna auto-sostituzione dei file su desktop.** Richiederebbe di uscire dall'app, lanciare un helper che
    aspetta la chiusura, scambiare i file e rilanciare: specifico per ogni SO, col rischio concreto che l'app non
    riparta se lo scambio si interrompe a metà. Valutato e respinto il 2026-08-06, decisione riconfermata. Desktop
    ha download con barra + apertura cartella + istruzioni per SO.
  - **`PROTOCOL_VERSION` resta 1** per il trasferimento: la modifica è additiva, e quel numero è confrontato con
    un'uguaglianza stretta che avrebbe spento ogni accoppiamento esistente per una funzionalità che nessuno stava
    usando. Introdotto invece `protocol.HOST_FEATURES`, annunciato da `GET /world`.
  - **Il codice di trasferimento è persistito su tabella, non in memoria come il PIN.** `WorldHostServer.stop()`
    azzera PIN e token per progetto e l'hosting si riavvia spesso: un codice emesso dal master per un telefono
    rotto e riscattato giorni dopo, in memoria, evaporerebbe.
  - **Nessun checksum sul download.** L'API di GitHub Releases non pubblica digest per gli asset: dichiarato
    invece di simulare un controllo d'integrità inesistente. Restano HTTPS e la verifica della dimensione (una
    risposta troncata da un proxy non produce alcun errore di rete).
  - **`app.exclude` senza glob.** Aggiunto per togliere `.git` (43 MB), `.venv` (179 MB in locale) e `docs`
    (2,5 MB) dal pacchetto che ora l'app scarica da sé. **Solo nomi di cartella**: la lista va al packager Dart
    (`serious_python:main package --exclude`), non installato in questo ambiente, e se interpreti `test_*.py`/`*.md`
    non è verificabile da qui — un pattern ignorato in silenzio darebbe l'illusione di un'esclusione che non
    avviene, e i ~30 file di test pesano in tutto 760 KB.
  - **`loot_stash_entries.added_by_device_id` NON viene riscritto** dal trasferimento: verificato che è scritto ma
    **mai letto** per autorizzare o mostrare qualcosa. È pura provenienza storica, riscriverla la falsificherebbe.
    Stesso ragionamento per `world_events.actor_device_id` (il giornale è un registro: non si riscrive la storia, si
    aggiunge un evento).

  **Due regressioni introdotte e corrette nella stessa sessione**, entrambe in test che si agganciavano a dettagli
  fragili: il finto backend di `test_lan_host_client.py` non accettava il nuovo parametro `transfer_code` (la firma
  del doppio deve rispecchiare quella reale, altrimenti solleva `TypeError` invece di verificare ciò che verifica);
  e `test_ingresso_lan_sincronizzazione.py` prendeva i campi del dialogo d'ingresso **per indice negativo**
  (`controls[-7]`…`controls[-1]`), quindi aggiungere il campo del codice di trasferimento spostava tutto e il test
  riempiva i campi sbagliati, fallendo con un `AssertionError` a valle che non diceva nulla sulla causa. Sostituita
  con una ricerca per etichetta (`_find_field`), che sopravvive alle prossime aggiunte.

  **Verifica.** Due batterie nuove, 265 controlli in tutto, tutti eseguibili in sandbox:
  `test_trasferimento_dispositivo.py` (146 — codice, permessi, riassegnazione con iniezione di fallimento a metà
  transazione, protocollo su socket reali, ciclo completo emetti→riscatta→approva→scarica, QR, costruzione UI) e
  `test_aggiornamento_app.py` (119 — selezione asset, contratto dei nomi col workflow reale, download contro un
  `http.server` locale con troncamento/annullamento/assenza di `Content-Length`, tabella dei casi di
  "Aggiornamento completato", costruzione dei dialoghi incluso il vincolo `ProgressBar` dentro `Row(expand=True)`).
  Più `test_versione_app.py` (29). Tutta la batteria multiplayer preesistente ri-eseguita: verde.
  **Resta a Davide su dispositivo reale**: generare il keystore e caricare i 2 secret, un tag di prova per
  verificare lo step di firma, il ciclo di migrazione, e tutto ciò che riguarda `flet_apk_installer` (mai compilato
  qui — vedi il README della cartella per i quattro punti aperti, in particolare i vincoli di versione su pub.dev,
  dove esiste già un precedente di CI rotta su tutte e 4 le piattaforme con `flet_file_picker`).

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

- **Il fix dell'`await` era corretto ma insufficiente — un secondo log rivela un problema più
  profondo, genuinamente lato Android (2026-08-06, stessa sessione)** — Davide ha ricompilato (versione
  interna passata da 0.1.21 a 0.1.23, confermando questa volta una build reale con il fix) e rimandato
  un nuovo log. **Prima verifica di controllo**: il numero di riga nel traceback (`profilo_tab.py:4299`,
  non più 4282) conferma che questa volta il log riflette davvero il codice corretto — l'`await` è
  presente e funziona: non c'è più alcun `RuntimeWarning: never awaited`.

  **Il nuovo errore, però**:

  ```
  RuntimeError: TimeoutException after 0:00:10.000000: Timeout waiting for invoke method listener
  for FilePicker(5244).pick_files
  ```

  Verificato per introspezione che questa NON è la stessa eccezione già vista nella diagnosi
  precedente (`page.overlay`/timing) — è un timeout Python che scade DOPO aver correttamente inviato
  la richiesta lato Dart bridge, in attesa di una risposta che non arriva mai in 10 secondi.
  **Controllo aggiuntivo, decisivo**: letto il log COMPLETO non filtrato nella finestra dei 10 secondi
  precedenti l'eccezione (dal tap alle 00:31:21.221 all'eccezione alle 00:31:31.426) — nessuna riga
  `ActivityTaskManager: START` per un'Activity di sistema (nessun picker file/foto nativo, nessun
  dialogo di richiesta permesso `GrantPermissionsActivity` o simile). L'unica attività registrata è il
  tocco stesso (`ViewRootImpl: ViewRoot's Touch Event`) dentro la nostra app. **Conclusione**: la
  richiesta non arriva MAI al lato nativo Android — non è un permesso negato o un dialogo bloccato in
  attesa, è il meccanismo di dispatch lato Flutter/Dart che non risponde affatto alla chiamata
  `pick_files()` per questo controllo. Coerente con la classe di bug "packaging" + "platform: android"
  già documentata per `Clipboard`/`Flashlight` nel repository upstream — semplicemente mascherata,
  nelle sessioni precedenti, dal bug Python dell'`await` mancante (che falliva PRIMA di poter mai
  arrivare a questo timeout).

  (Nota separata trovata nello stesso log, non correlata: due errori `Dart_PostCObject_DL failed` alle
  00:31:16-19, causati dal Play/Package Installer che sostituiva l'APK precedente mentre il vecchio
  processo Python era ancora vivo in background — rumore dell'installazione stessa, non del bug.)

  **Non ancora deciso il prossimo passo** — presentate a Davide le opzioni con pro/contro (tentare una
  singola istanza `FilePicker` creata al volo invece che riutilizzata per sessione, pattern più vicino
  a quello mostrato nella documentazione ufficiale corrente, costo basso ma probabilità di successo
  ridotta vista l'evidenza; segnalare il bug upstream con questa evidenza precisa; investire in
  un'estensione Flutter nativa alternativa, costosa e richiede il loop di build/test di Davide;
  rimandare la selezione file su Android). Nessuna scelta ancora fatta.

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

- **2026-08-06 — Bypass di `ft.FilePicker` su Android: WebView locale al posto del controllo rotto.**
  Continuazione diretta delle due voci precedenti (await mancante trovato e corretto; poi il secondo log
  che ha rivelato il problema più a fondo). Un secondo log `adb logcat` di Davide, preso DOPO il fix
  dell'`await`, ha mostrato che `pick_files()` ora arriva correttamente al bridge Dart ma va in
  `RuntimeError: TimeoutException after 0:00:10.000000: Timeout waiting for invoke method listener for
  FilePicker(N).pick_files` — **nessuna Activity nativa Android viene mai avviata**, verificato leggendo
  il log COMPLETO (non solo quello filtrato): nessun picker di sistema, nessun dialogo di permesso,
  nessuna traccia di un Intent lanciato durante i 10 secondi di attesa. Conclusione: `ft.FilePicker` non
  è utilizzabile su questa build Android, per nessuno dei suoi metodi — non un problema risolvibile
  scrivendo il codice Python diversamente attorno alla chiamata, come già sospettato (ma mai confermato
  con un log) nelle sessioni precedenti che avevano trovato la stessa classe di bug "packaging" +
  "platform: android" nel repository upstream di Flet per altri controlli `Service` (Clipboard,
  Flashlight).

  Davide ha chiesto esplicitamente di valutare **tutte le alternative possibili, anche le più estreme**,
  prima di scegliere una strada, trattandosi di una funzionalità importante (scelta dell'immagine).
  Ricerca condotta: (1) Pyjnius — supportato ufficialmente da Flet per accesso Java diretto, ma nessun
  modo pulito di riportare un risultato Intent asincrono (`onActivityResult`) in puro Python senza glue
  Kotlin/Java scritto a mano; (2) estensione Flutter nativa custom via la "Enhanced Extensions API" di
  Flet — tecnicamente la soluzione più solida, ma costo di sviluppo molto più alto, richiede toolchain
  Dart/Flutter; (3) `ft.WebView` (estensione ufficiale separata `flet-webview`, mantenuta in lockstep di
  release col pacchetto `flet` core) con un `<input type=file>` — costo contenuto, riusa un meccanismo
  di selezione file (il file-chooser di WebView) enormemente più maturo e testato di qualunque controllo
  `Service` di Flet, perché usato da milioni di app con una WebView integrata. Scelta: opzione 3,
  rapporto costo/probabilità di successo migliore.

  **Chiarimento importante dato a Davide prima di procedere**: il progetto è offline-first
  (`CLAUDE.md`, principio architetturale dichiarato) e Davide ha giustamente chiesto conferma che
  `WebView` non introducesse una dipendenza da internet. Confermato che non è così: la pagina HTML è
  costruita interamente in Python e passata alla WebView come `data:` URI locale (mai un URL remoto,
  mai una richiesta di rete), e il file scelto viene letto in memoria dal browser con
  `FileReader.readAsDataURL()` (API JavaScript standard, zero upload, zero rete) — l'unico "confine"
  attraversato è lo stesso dispositivo, tramite `console.log()` → `WebView.on_console_message`.
  Approvato da Davide dopo questo chiarimento.

  **Implementato**: nuovo modulo `ui/mobile_webview_picker.py` —
  `async pick_file_via_webview(page, *, accept="*/*", title="...") -> Optional[tuple[str, str]]`
  (nome file, contenuto base64) o `None` se annullato/errore. Mostra un `ft.AlertDialog` (pattern
  `design.dialog_title()`/`wrap_dialog_actions()` già in uso nel progetto) contenente una `WebView` con
  `url=` impostato a un `data:text/html;charset=utf-8;base64,<...>` (scelto invece del metodo async
  `load_html()` post-mount per evitare la stessa race "monta poi invoca" che affligge `FilePicker` —
  `load_html()` richiede comunque il controllo già montato). La pagina HTML contiene un
  `<input type=file accept="{accept}">` nascosto, attivato da un bottone visibile stilizzato; alla
  scelta, `FileReader` legge il file e lo rimanda a Python con `console.log('FLET_PICKER_RESULT:' +
  JSON.stringify({{name, dataUrl}}))`, intercettato da `on_console_message` e portato al chiamante
  `async` tramite un `asyncio.Future` (ponte sincrono→asincrono dal callback dell'evento).

  Aggiunta la dipendenza `flet-webview==0.86.5` a `pyproject.toml` e `requirements.txt` (stessa versione
  di `flet`, per restare in lockstep come da convenzione già in uso per queste due liste).

  **Wiring** (tre siti, tutti verificati con `py_compile`/`compileall`):
  - `profilo_tab.py::_pick_photo_mobile()` — `accept="image/*"`. `_load_photo(path)` (storico) è stato
    diviso in `_load_photo(path)` (apre un path locale, invariato per il ramo desktop) + nuova
    `_save_photo_bytes(raw: bytes)` (la normalizzazione PIL→JPEG→base64 + salvataggio DB, estratta per
    essere condivisa col nuovo flusso WebView che riceve bytes diretti, non un path).
  - `maps_view.py::_pick_mobile()` — stesso pattern: `_load_image_base64(path)` diviso in sé stesso
    (ora un thin wrapper che apre il path) + nuova `_normalize_image_bytes_to_base64(raw: bytes)`.
  - `home_view.py::_on_mobile_import()` — `accept=".dndchar,.json,application/json"`, decodifica UTF-8
    e delega a `_do_import_from_text()` già esistente. Questa funzione, scritta il 2026-07-24, usava
    già correttamente l'`await` (non aveva il primo bug) — ma essendo comunque basata su
    `ft.FilePicker.pick_files()`, era ugualmente esposta al bug di fondo appena diagnosticato: un
    `await` corretto non basta se il controllo sottostante non è utilizzabile affatto su questa build.

  In tutti e tre i punti rimossi `self._file_picker` (l'attributo, la creazione lazy, i commenti storici
  del "did_mount() non registra più nulla" ormai superati) dove non più necessario; `home_view.py`
  mantiene `self._file_picker`/`_ensure_file_picker()` perché ancora usato da `_on_mobile_export()`.

  **Esplicitamente fuori scope in questa sessione**: `home_view.py::_on_mobile_export()` (save_file) —
  un download via WebView è un meccanismo diverso (intercettare un `<a download>`/Blob lato browser),
  mai verificato in questo progetto. Resta su `ft.FilePicker.save_file()`; per la stessa diagnosi è
  MOLTO PROBABILE che fallisca allo stesso modo su un vero dispositivo (TimeoutException), ma non
  ancora confermato con un log dedicato — il `try/except` già presente lo intercetterebbe comunque
  mostrando un errore invece di un blocco silenzioso. Segnalato chiaramente nei commenti del file e da
  affrontare a parte se Davide lo richiede.

  **Verificato**: `python3 -m py_compile` su tutti i file toccati, `python3 -m compileall` sull'intero
  albero (esclusa `build/`), import reale di `ui.mobile_webview_picker` nel sandbox (con
  `flet-webview==0.86.5` installato per la verifica), introspezione di `WebView.__init__`/
  `WebViewConsoleMessageEvent` per confermare i parametri usati. Tutte e 4 le batterie di test:
  `test_regressione_wrap_expand.py` 37/37, `test_master_world_scoping.py` 25/25,
  `test_mondo_senza_rete.py` 139/139, `test_lan_host_client.py` 92/92,
  `test_istanze_personaggio.py` 61/62 (stesso artefatto ambientale del sandbox già annotato in sessioni
  precedenti — il subprocess che lancia non eredita `flet` dall'ambiente del sandbox, non correlato a
  queste modifiche). Nessuna regressione.

  **Non verificabile da qui**: se il selettore WebView si apre davvero e funziona end-to-end su un vero
  dispositivo Android — richiede un rebuild (`flet build apk`, non disponibile in questo sandbox: niente
  Android SDK/NDK) e un test di Davide sul dispositivo reale, sui tre punti (foto profilo, immagine
  mappa, import personaggio).

  **Tab bar (pillole selezione tab) — NON ancora corretta oltre il fix precedente**: Davide ha segnalato
  che il fix `wrap=True` di `sheet_view.py`/`master_view.py` (voce precedente in questo changelog) è
  visivamente "bruttissima, si prende tutto lo schermo" su un vero smartphone. Non è stato tentato un
  secondo fix alla cieca in questa sessione: è stato chiesto a Davide uno screenshot per diagnosticare
  con precisione invece di ipotizzare di nuovo — lezione diretta dal ciclo di misdiagnosi del FilePicker
  appena concluso in questa stessa sessione. In attesa dello screenshot.

- **2026-08-06 (stessa giornata) — bug reale trovato da Davide: l'app crashava anche su DESKTOP dopo
  l'introduzione del picker WebView.** Screenshot di Davide: `python main.py` su macOS mostrava subito
  "The application encountered an error: No module named 'flet_webview'" — l'app non arrivava nemmeno
  alla Home. Causa: `ui/mobile_webview_picker.py` importava `from flet_webview import WebView,
  WebViewConsoleMessageEvent` in cima al modulo (import "eager"), e quel modulo è importato a sua volta
  in cima a `profilo_tab.py`/`maps_view.py`/`home_view.py` — tre file caricati all'avvio su QUALUNQUE
  piattaforma, non solo Android/iOS. Il pacchetto `flet-webview` serve SOLO al ramo mobile (l'unico che
  chiama `pick_file_via_webview()`; desktop/web instradano sempre altrove — `_pick_photo_desktop()`,
  `show_image_library_picker()`, ecc.), ma l'import eager lo rendeva un requisito per l'avvio dell'app
  su QUALUNQUE piattaforma, desktop compreso — dove il pacchetto non è (né deve essere) necessariamente
  installato. Un difetto di progettazione introdotto dalla sessione stessa che ha scritto il modulo, non
  notato perché la verifica di quella sessione aveva installato `flet-webview` nel sandbox prima di
  testare l'import, mascherando il problema.

  **Fix**: import di `flet_webview` spostato DENTRO `pick_file_via_webview()` (import ritardato a
  runtime, eseguito solo quando la funzione viene davvero chiamata — cioè solo sul ramo mobile). Per
  poter comunque annotare il tipo `WebViewConsoleMessageEvent` nella funzione interna
  `_on_console_message()` senza un secondo import eager, aggiunto `from __future__ import annotations`
  in cima al file (valuta le annotazioni pigramente, mai richiesto a runtime) e un blocco `if
  TYPE_CHECKING:` per l'import visibile solo agli strumenti di analisi statica, mai eseguito.

  **Verificato in modo specifico per questo bug** (non solo un compileall): disinstallato
  `flet-webview` dal sandbox e reimportati `ui.mobile_webview_picker` +
  `ui.views.character_sheet.profilo_tab` + `ui.views.maps_view` + `ui.views.home_view` — tutti importano
  senza errore SENZA il pacchetto installato, confermando che desktop/web non ne hanno più bisogno per
  avviarsi. Reinstallato `flet-webview` e ripetuto `compileall` + `test_regressione_wrap_expand.py`
  (37/37) + `test_master_world_scoping.py` (25/25) — nessuna regressione. **Non verificabile da qui**:
  che l'app si avvii ora pulita sul Mac di Davide (bastano gli import qui sopra a prevederlo con buona
  sicurezza, ma solo un lancio reale lo conferma) — e resta comunque da confermare, come sempre, il
  comportamento del picker vero e proprio su un Android reale.

- **2026-08-06 (stessa giornata) — tab bar: da `wrap=True` a riga singola scorrevole, in entrambe le
  sezioni.** Davide ha ripreso la segnalazione ancora aperta ("fissa enorme che occupa tutto lo spazio,
  brutta da vedere") chiedendo esplicitamente di adattare la sezione giocatore (`SheetView`) come già
  fatto, a suo dire, nella sezione Master. Verifica del codice: `MasterView._build_tab_bar()` non era
  MAI stata toccata dopo il primo fix `wrap=True` della sessione precedente — struttura identica,
  pillola per pillola, a `SheetView._build_header_and_tabs()`. Nessuna delle due sezioni era quindi
  "già sistemata"; probabile che Davide avesse notato meno il problema in Master (5 etichette in media
  leggermente più corte, ma comunque soggette allo stesso identico difetto) piuttosto che una reale
  differenza di codice.

  **Causa del difetto visivo** (deduttiva dal comportamento noto di `wrap=True` su Flutter, coerente col
  commento stesso che l'aveva introdotto nella sessione precedente): `wrap=True` con 5 pillole
  "Combattimento"/"Esplorazione"/"Rubrica NPC"/"Note di Campagna" che non ci stanno su una riga manda
  quelle in eccesso su una SECONDA (a volte terza) riga a piena larghezza del contenitore — per una tab
  bar, che deve restare una striscia sottile in alto, questo significa raddoppiare o triplicare la sua
  altezza e spingere giù tutto il resto: esattamente "si prende tutto lo schermo".

  **Fix**: sostituito `wrap=True` con `scroll=ft.ScrollMode.AUTO` sulla `Row` delle pillole, in
  ENTRAMBI i file (`sheet_view.py::_build_header_and_tabs()` e `master_view.py::_build_tab_bar()`) —
  non una scelta inventata sul momento: è lo STESSO pattern già scelto da Davide e collaudato da tempo
  nella bottom nav dell'app (`ui/app.py::_build_bottom_nav()`, 9 voci su un telefono stretto, commento
  originale: "con 9 voci... la barra scorre orizzontalmente quando non ci stanno tutte" — larghezza
  fissa per voce, mai `wrap`). Risultato: la tab bar resta sempre un'unica riga di altezza fissa: le
  pillole che non ci stanno restano semplicemente fuori vista finché l'utente non scorre lateralmente,
  invece di allungare la barra verticalmente. Le pillole restano senza `expand=True` (si dimensionano
  sul proprio contenuto, non si dividono lo spazio) — irrilevante ai fini del bug Flutter
  `wrap=True`+`expand=True` già documentato in `regole_flet_api.md`, dato che ora `wrap` non compare più
  affatto in nessuno dei due punti.

  Applicato a entrambe le sezioni per coerenza (lo stesso identico problema, la stessa identica causa,
  la stessa soluzione già in uso altrove nel progetto) — non solo alla sezione giocatore esplicitamente
  richiesta, per evitare di lasciare la sezione Master con un difetto equivalente non corretto.

  **Verificato**: `py_compile` su entrambi i file, `test_regressione_wrap_expand.py` 37/37 (nessuna
  modifica necessaria al test: cammina la struttura cercando l'anti-pattern `wrap`+`expand`
  co-presenti, che ora non c'è più in nessuno dei due punti, quindi continua a non trovarlo), nessuna
  regressione sulle altre 3 batterie (25/25, 139/139, 92/92). **Non verificabile da qui**: la resa reale
  su un vero smartphone stretto — solo Davide può confermare che la barra ora scorre invece di
  allungarsi.

  **Superata dalla voce successiva**: Davide ha poi segnalato che lo scroll stesso era sbagliato
  ("le selezioni vengono tagliate o scompaiono, non si adattano alla pagina") — vedi la terza voce più
  sotto per il fix definitivo (pillole icona-sola sotto un breakpoint), che sostituisce lo scroll come
  meccanismo primario.

- **2026-08-06 (stessa giornata) — la barra scorrevole introduceva un nuovo difetto: "alone allungato".**
  Davide ha inviato uno screenshot DESKTOP della Sezione Master mostrando che la pista beige
  (`bgcolor=surface_alt`) dietro le pillole si estendeva ben oltre le 5 pillole reali, quasi fino al
  bordo destro della finestra — "si deve adattare allo schermo la pagina, se fa quel alone allungato non
  va bene, è brutto".

  **Causa** (comportamento noto di Flutter, non un errore di configurazione): un `SingleChildScrollView`
  orizzontale — quello che Flet genera internamente per `ft.Row(..., scroll=ft.ScrollMode.AUTO)`, il fix
  della voce precedente — NON si restringe mai al contenuto lungo l'asse di scroll: prende sempre la
  larghezza massima concessa dal genitore, anche quando il contenuto reale (le 5 pillole) è molto più
  stretto. Il `Container` che dava lo sfondo `surface_alt` a quella Row, non avendo una larghezza
  propria, ereditava quella stessa larghezza "gonfiata" e la disegnava visibilmente — da cui l'alone.
  Lo stesso identico meccanismo era presente anche PRIMA di questa sessione, con `wrap=True`: lì però il
  widget `Wrap` di Flutter SI restringe al contenuto per riga, mascherando il problema finché il
  contenuto stava su una riga sola — motivo per cui probabilmente non era mai stato notato.

  **Fix**: tolti `bgcolor`/`border_radius`/`padding` dal `Container` esterno che avvolge la Row
  scorrevole, in ENTRAMBI i file (`sheet_view.py::_build_header_and_tabs()` e
  `master_view.py::_build_tab_bar()`) — resta solo il `margin` per lo spazio dai bordi. Nessun
  contenitore colorato avvolge più l'intera barra: ogni pillola porta il proprio sfondo quando attiva,
  esattamente il principio già usato con successo per "Generatori Rapidi" (`design.pill()`, visibile
  nello stesso screenshot di Davide senza alcun difetto) — MAI un contenitore che raggruppa
  visivamente tutte le pillole con un colore di sfondo.

  Per `MasterView`, la pillola attiva restava `bgcolor=p.surface` (invariato: contrasta già bene con lo
  sfondo della pagina dietro la barra, confermato dallo stesso screenshot). Per `SheetView` è stato
  necessario un piccolo aggiustamento in più: l'header che contiene la barra ha già
  `bgcolor=p.surface` — una pillola attiva con lo stesso colore sarebbe risultata invisibile (bianco su
  bianco) una volta tolto l'involucro beige che prima la faceva risaltare. Cambiato a `p.surface_alt`
  (lo stesso colore che prima dava lo sfondo all'INTERA barra, ora usato solo per la pillola selezionata)
  — risultato visivo pressoché identico a prima, senza il contenitore che si allargava oltre il
  contenuto.

  **Verificato**: `py_compile` + `compileall` su entrambi i file, tutte e 4 le batterie di test
  (`test_regressione_wrap_expand.py` 37/37, `test_master_world_scoping.py` 25/25,
  `test_mondo_senza_rete.py` 139/139, `test_lan_host_client.py` 92/92) — nessuna regressione. **Non
  verificabile da qui**: solo un lancio reale (desktop e mobile) può confermare che l'alone sia
  davvero sparito e che il contrasto della pillola selezionata resti leggibile in entrambi i temi
  chiaro/scuro.

- **2026-08-06 (stessa giornata) — fix DEFINITIVO: tab bar davvero responsive, non più uno scroll che
  taglia contenuto.** Davide ha segnalato, restringendo la finestra desktop, che le pillole "vengono
  tagliate o scompaiono, non si adattano alla pagina" — cioè lo `scroll=ft.ScrollMode.AUTO` della voce
  precedente, per quanto tecnicamente corretto e privo dell'alone, andava comunque contro la preferenza
  già nota di questo progetto per un'interfaccia sempre visibile, senza contenuto nascosto dietro un
  gesto di scroll non scoperto (`[[feedback_dnd_app_ui_no_hidden_actions]]` nella memoria persistente:
  "self-evident UI, no overflow/hamburger menus; prefer always-visible wrapping pills").

  Il vincolo reale però resta: 5-6 pillole con etichette italiane lunghe ("Combattimento",
  "Esplorazione", "Note di Campagna", "Oggetti Magici") non stanno fisicamente su una riga sola alla
  larghezza minima comune di uno smartphone (360-375px), qualunque sia il meccanismo scelto — né
  riducendo il font né stringendo il padding: servono decine di caratteri di spazio che a quella
  larghezza semplicemente non ci sono. `wrap=True` (primo tentativo) le mostrava tutte ma allungava la
  barra in verticale; lo scroll (secondo/terzo tentativo) le teneva compatte ma le nascondeva.

  **Fix**: reso lo spazio richiesto compatibile con lo spazio disponibile, invece di continuare a
  scegliere tra "alto" e "nascosto". Aggiunta un'icona a ogni tab (`SHEET_TABS` ne era privo, `_TABS` di
  Master già le aveva) e una modalità compatta — sotto il breakpoint mobile che l'app usa già per
  scegliere tra sidebar e bottom nav (`_MOBILE_BP = 600`, `ui/app.py::_is_mobile()`), ogni pillola mostra
  SOLO l'icona (etichetta completa nel `tooltip`, mai persa — un'informazione sempre raggiungibile non è
  "nascosta" nel senso della regola sopra, un'AZIONE dietro un menu overflow lo sarebbe stata); sopra il
  breakpoint, icona + etichetta come prima. 5-6 pillole icona-sola occupano collettivamente meno di
  250px, ben dentro anche i telefoni più stretti — la Row torna quindi a stare su una riga sola senza
  bisogno di scorrere né di andare a capo. `scroll=ft.ScrollMode.AUTO` resta sulla Row solo come rete di
  sicurezza per casi patologici (font di sistema molto ingranditi, finestre sotto i 360px), non più come
  meccanismo primario.

  **Wiring del breakpoint** (nessun nuovo meccanismo di resize introdotto, per non rischiare di scavalcare
  `page.on_resize` — già di proprietà esclusiva di `DnDApp._on_page_resize()` per lo switch
  sidebar/bottom-nav, un secondo handler l'avrebbe sovrascritto): `SheetView.__init__`/`MasterView.__init__`
  guadagnano un parametro opzionale `is_mobile: bool = False` (default compatibile con le chiamate
  esistenti nei test). `ui/app.py::_get_section_view()` passa `is_mobile=self._mobile` (il flag che l'app
  già mantiene); `_show_master_view()` passa `is_mobile=self._is_mobile()`. Nota onesta, documentata nel
  docstring di `MasterView.__init__`: a differenza di `SheetView` (che vive dentro `content_area`,
  ricostruita automaticamente quando `_on_page_resize()` fa scattare `_show_main_layout()`), `MasterView`
  sostituisce l'intera pagina via `_navigate()` e NON viene ricostruita se la finestra cambia larghezza
  mentre la Modalità Master è già aperta — resta fissata al valore letto all'apertura o all'ultimo
  rebuild (es. cambio tema). Limite noto e accettato, non un bug nascosto.

  **Refactor collaterale in `SheetView`** (necessario per supportare icona+testo opzionali): `_make_tab_button()`
  ora costruisce icona (sempre) e testo (solo se non compatta) come controlli separati, salvati in
  `btn.data = {"icon": ..., "text": ...}`; `_style_tab_button()` legge da lì invece che da `btn.content`
  direttamente (prima un `ft.Text` isolato, garantito). `MasterView._build_tab_bar()` non ha avuto
  bisogno dello stesso refactor: ricostruisce sempre l'intera barra da zero a ogni cambio tab
  (`_on_tab_click()` chiama `self._build()`), quindi non manteneva comunque riferimenti diretti ai
  singoli controlli da aggiornare in-place.

  **Verificato**: `py_compile`/`compileall` su tutti i file toccati (`sheet_view.py`, `master_view.py`,
  `app.py`). `test_regressione_wrap_expand.py` esteso da 37 a 63 controlli: `test_master_view()` e
  `test_sheet_view()` ora iterano anche `is_mobile in (False, True)`, esercitando per la prima volta il
  ramo `self._compact_tabs=True` mai toccato prima da nessun test; aggiunta anche una verifica mirata
  che chiama `_style_tab_button()` direttamente (bypassando `_switch_tab()`, che richiederebbe un vero
  `page.update()` non disponibile in un test di sola costruzione) per coprire il refactor `btn.data`.
  63/63 verdi. Nessuna regressione sulle altre 3 batterie (25/25, 139/139, 92/92) — 319 controlli totali,
  in crescita da 293 grazie alla nuova copertura, non per un ampliamento delle batterie esistenti.
  **Non verificabile da qui**: la resa reale su un vero smartphone stretto e su una finestra desktop
  ridimensionata a mano — solo Davide può confermare che le pillole restino leggibili e mai tagliate.

- **QR d'ingresso per l'hosting LAN — solo generazione (2026-08-06)** — Davide ha chiesto un modo più rapido di
  entrare in un mondo ospitato in LAN rispetto a leggere indirizzo/porta/codice/PIN dallo schermo del master e
  digitarli a mano, proponendo un QR da inquadrare. Prima di scrivere codice, analisi dei rischi (regola del
  progetto: mai una libreria non verificata) — cercato se Flet avesse un controllo camera/QR ufficiale: **non
  esiste** (nessun pacchetto `flet-qrcode`/`flet-barcode-scanner`, nessun controllo camera in Flet 0.86.5,
  verificato via ricerca). Questo divide il lavoro in due parti con rischio molto diverso:
  - **Generazione lato host**: basso rischio. Verificato su PyPI che `qrcode` (8.2, ultima release) è puro
    Python — nessuna libreria nativa, `Requires: Python <4.0,>=3.9` — e usa da solo Pillow come backend immagine
    se già installato (lo è: dipendenza del progetto da prima). Aggiunto come dipendenza esplicita in
    `pyproject.toml` e `requirements.txt` (`qrcode==8.2`).
  - **Scansione lato giocatore**: rischio alto, stesso genere di incognita della saga FilePicker (nessuna
    soluzione ufficiale, l'unica strada percorribile sarebbe `flet-webview` + `getUserMedia` + una libreria JS
    come jsQR, non verificabile senza un ciclo di test su dispositivo reale).

  **Decisione di Davide** (fatta scegliere esplicitamente prima di scrivere codice, con i due rischi separati
  davanti): procedere SOLO con la generazione lato host per ora. La scansione resta un'azione manuale — il
  giocatore continua a inserire i 4 dati nel dialogo "Unisciti in LAN" — ma può leggerli/copiarli da un QR
  invece di trascriverli a mano dallo schermo del master, il che riduce comunque l'attrito e gli errori di
  trascrizione del PIN.

  **Implementazione**: nuovo modulo `network/qr_join.py` (nessuna dipendenza da Flet, come tutto `network/*.py`)
  — `build_join_text()` costruisce un testo semplice leggibile (non un URI/deep link, così qualunque fotocamera
  del telefono lo mostra come testo senza bisogno di un'app dedicata) con mondo/host/porta/codice/PIN;
  `generate_qr_png_base64()` genera il PNG e lo ritorna in base64, senza fallback silenziosi — solleva
  l'eccezione originale, la gestisce chi chiama. `ui/views/world/world_view.py::_hosting_qr_image()` lo mostra
  nella sezione "Ospita in LAN" accanto al PIN testuale già esistente, con `ft.Image(src="data:image/png;
  base64,...")` — **mai `src_base64`**, non esiste in questa versione di Flet (regola già nota, vedi
  `regole_flet_api.md`). Un errore di generazione viene loggato e la sezione resta comunque utilizzabile: il
  PIN testuale non dipende dal QR.

  **Verificato**: `py_compile` su `network/qr_join.py` e `ui/views/world/world_view.py`. Generazione del QR
  testata end-to-end in un venv pulito (import del modulo, generazione, verifica della firma PNG nei byte
  risultanti). Import completo di `ui.views.world.world_view` (quindi anche di `flet`, `data.database`,
  `ui.design`, ecc.) in un venv con le dipendenze reali del progetto installate da `requirements.txt`, senza
  errori — verifica che i nomi usati (`ft.Colors.WHITE`, `ft.BoxFit.CONTAIN`, `d.Radius.SM`) esistano davvero
  nella versione installata, non assunti. Rieseguite le 5 batterie di test esistenti più rilevanti
  (`test_lan_host_client.py` 92/92, `test_mondo_senza_rete.py` 139/139, `test_master_world_scoping.py` 25/25,
  `test_istanze_personaggio.py` 62/62, `test_regressione_wrap_expand.py` 35/35 — quest'ultima con un numero
  diverso da quello riportato più sopra perché a quella data non includeva ancora l'estensione a 63 poi
  descritta altrove nel changelog, valore confermato dall'esecuzione reale in questa sessione): nessuna
  regressione.

  **Non verificabile da qui**: la resa reale del QR su un vero smartphone (leggibilità, contrasto in tema
  scuro — l'immagine ha comunque uno sfondo bianco proprio, indipendente dal tema dell'app) e se un lettore QR
  generico di un vero telefono lo interpreta come previsto — solo Davide può confermarlo. La scansione in-app
  resta esplicitamente fuori scope, da riprendere solo su richiesta esplicita.

  **Bug reale trovato subito da Davide, stessa sessione**: hosting avviato correttamente (PIN visibile,
  screenshot confermato: "In ascolto su 192.168.1.202:8765", PIN "300776", sezione "Ospita in LAN"
  pienamente funzionante), ma **nessun QR visibile** — non un riquadro vuoto, proprio nessuno spazio
  riservato, segno che `_hosting_qr_image()` stava ritornando `None` (il ramo d'errore silenzioso).
  Causa del difetto di **design**, non ancora della causa a monte: `generate_qr_png_base64()` solleva
  un'eccezione quando fallisce, ma `_hosting_qr_image()` la catturava con `logger.error(...)` e basta —
  e `main.py` configura `logging.basicConfig()` **senza alcun `FileHandler`**, quindi quel log va solo su
  stderr. Per un'app lanciata senza un terminale visibile aperto (il caso di Davide, a giudicare dallo
  screenshot: una finestra `python main.py` già in esecuzione, non una shell), quel log è **irraggiungibile
  quanto nessun log affatto** — il primo fallback era silenzioso esattamente quanto quello che il progetto
  vieta esplicitamente, solo spostato da "nessun log" a "un log che nessuno può leggere".

  **Fix**: `_hosting_qr_image()` non ritorna più `None` — ritorna sempre un `ft.Control`: il QR se la
  generazione riesce, altrimenti una riga rossa con l'icona di errore e il messaggio dell'eccezione
  (`f"QR non generato: {e}"`), visibile direttamente nella sezione "Ospita in LAN" senza bisogno di un
  terminale. Il PIN testuale sopra resta comunque sufficiente da solo per entrare anche quando il QR
  fallisce. `_hosting_section()` semplificato di conseguenza (il controllo `is not None` sul valore di
  ritorno era diventato morto). **Causa a monte non ancora confermata**: l'ipotesi più probabile è che
  l'ambiente Python di Davide non avesse ancora ricevuto `pip install -r requirements.txt` dopo l'aggiunta
  di `qrcode==8.2` — ma è un'ipotesi, non un fatto verificato: con il fix sopra, il prossimo tentativo di
  Davide mostrerà il messaggio d'errore esatto direttamente in UI, invece di dover indovinare una seconda
  volta alla cieca (lezione diretta dalla saga FilePicker, citata anche altrove in questo changelog: mai
  ipotizzare due volte senza prova reale). Verificato `py_compile` + import completo di
  `ui.views.world.world_view` in un venv con le dipendenze reali, nessuna regressione. **Non verificabile
  da qui**: il messaggio d'errore esatto che comparirà sullo schermo di Davide.

  **Causa a monte confermata dal messaggio d'errore reale** (`QR non generato: No module named 'PIL'`,
  screenshot di Davide): NON un bug nel codice del progetto — `qrcode==8.2` ha zero dipendenze
  obbligatorie proprie (verificato: `pip show qrcode` → `Requires:` vuoto), sia `Pillow` sia `pypng` sono
  extra opzionali, e la scelta automatica del backend immagine (`qrcode/main.py::make_image()`, riga 364:
  `from qrcode.image.pil import Image, PilImage`) fa un `import` non protetto da try/except — se Pillow
  non è importabile, l'eccezione risale fino al chiamante invece di ripiegare su `pypng` come la pagina
  PyPI del progetto lascia intendere (comportamento verificato leggendo il sorgente installato, non
  assunto dalla sola documentazione). Pillow è però già una dipendenza OBBLIGATORIA di questo progetto da
  prima di questa sessione (`Pillow>=10.0.0`, usata direttamente da `ui/image_library.py`,
  `ui/views/maps_view.py`, `ui/views/character_sheet/profilo_tab.py` per le foto profilo e le immagini
  delle mappe) — se manca davvero nell'ambiente da cui Davide lancia l'app, è un problema di installazione
  delle dipendenze più ampio del solo QR, non qualcosa da aggirare nel codice di `qr_join.py`. Deciso di
  NON rendere `qr_join.py` indipendente da Pillow (es. forzando `PyPNGImage`): mascherebbe il sintomo qui
  ma lascerebbe le foto profilo/mappe silenziosamente rotte per lo stesso motivo altrove.

  **Confermato risolto da Davide** dopo `pip install -r requirements.txt` nel venv corretto
  (`.venv/bin/pip`, verificato con `import PIL` → Pillow 12.3.0 presente). Un problema SEPARATO emerso
  subito dopo, stessa sessione: il primo riavvio dell'app restava bloccato a tempo indeterminato su una
  schermata "Working..." col titolo generico "Flet" (mai "D&D Companion") — non un errore nel codice del
  progetto: il log dedicato (`~/Documents/dnd_debug.log`, già esistente in `main.py` per la diagnostica su
  iOS) mostrava 4 avvii consecutivi arrivati puliti fino a `[8] calling ft.run()` senza mai un `FAILED`,
  ma `run_app()`/`DnDApp.__init__()` non avevano alcuna istrumentazione propria — aggiunti temporaneamente
  dei checkpoint nello stesso file per isolare se il blocco fosse lì o più a valle, PRIMA di proporre un
  secondo fix alla cieca (stessa disciplina della saga FilePicker). Non serviti: al riavvio successivo
  Davide ha riportato che l'app "ha fatto un'installazione" ed è ripartita normalmente — ipotesi più
  probabile, mai verificata nel dettaglio perché il problema si è risolto da solo: Flet scarica/prepara il
  proprio runtime desktop al primo avvio dopo un cambio di dipendenze rilevante, e quella schermata era
  quell'attesa, non un blocco. Checkpoint di debug rimossi da `ui/app.py` subito dopo la conferma, per non
  lasciare diagnostica temporanea nel codice permanente (erano esplicitamente documentati come "da
  rimuovere una volta isolata la causa reale").

  **QR verificato funzionante end-to-end da Davide** (hosting attivo, PIN e QR entrambi generati e
  visibili). Chiuso.

- **2026-08-06 — Secondo vicolo cieco confermato: anche il picker WebView non funziona su Android, causa
  diversa dal FilePicker ma altrettanto definitiva.** Davide ha testato il fix precedente (bypass di
  `ft.FilePicker` con `ft.WebView` + `<input type=file>`, vedi le voci precedenti) su un vero Android:
  il dialog SI APRE correttamente (confermato anche dal log — il processo sandboxed di Chromium
  `com.google.android.webview:sandboxed_process0` parte regolarmente, la pagina HTML viene renderizzata),
  ma **toccare il pulsante "Scegli file" non fa assolutamente nulla** — nessun selettore di sistema si
  apre, nessun errore visibile.

  **Causa, confermata con ricerca mirata (non un'altra ipotesi)**: `flet-webview` è basato sui pacchetti
  Flutter ufficiali `webview_flutter`/`webview_flutter_web` (dichiarato esplicitamente sulla pagina PyPI
  del pacchetto). È un limite NOTO e ben documentato di `webview_flutter` su Android: `<input
  type="file">` non fa scattare alcun selettore di sistema a meno che l'app ospite non implementi
  esplicitamente il callback nativo `WebChromeClient.onShowFileChooser` (lato Kotlin/Java) — un supporto
  che è stato aggiunto solo di recente e solo in modo opzionale/manuale a `webview_flutter_android`
  (`AndroidWebViewController.setOnShowFileSelector()`, richiede codice Dart/Kotlin dedicato, non
  automatico). Verificato per introspezione diretta sul pacchetto `flet_webview==0.86.5` installato:
  **`ft.WebView` non espone alcun parametro, evento o metodo relativo alla selezione file** (`on_show_
  file_chooser`, `on_file_chooser` o simili — nessuno dei due esiste; l'elenco completo dei parametri del
  costruttore non contiene nulla del genere). `flet_webview` non ha mai wired questo pezzo: usare `<input
  type=file>` dentro `ft.WebView` su Android non può funzionare con l'API Python attuale, punto — non è
  un problema risolvibile lato nostro codice Python, esattamente come il vicolo cieco precedente di
  `ft.FilePicker`, ma con una causa tecnica completamente diversa e più a monte (un pezzo di
  integrazione mai scritto in `flet_webview`, non un bug).

  **Onestà sul design precedente**: la scelta di `ft.WebView` era stata motivata (nella sessione
  precedente) con "il file-chooser di un browser è un meccanismo maturo, usato da milioni di app" — un
  ragionamento corretto per un VERO browser o una WebView con l'integrazione nativa completa, ma che
  avrebbe dovuto essere verificato ANCHE per l'implementazione specifica di Flet/webview_flutter su
  Android prima di scrivere il codice, non solo dopo — la stessa disciplina già applicata con successo
  altrove in questo progetto (verificare per introspezione prima di usare un'API, mai assumere). Lezione
  per il futuro: "il meccanismo esiste ed è maturo nel browser" non implica "il wrapper che lo espone in
  questo framework lo abilita per davvero" — vanno verificate entrambe le cose separatamente.

  **Stato**: nessun terzo tentativo scritto alla cieca in questa sessione. Le opzioni restanti valutate
  (dettaglio completo nella cronologia della chat, non ripetuto qui perché nessuna è ancora stata scelta):
  (a) riattivare per Android il fallback "incolla il percorso file" già esistente e funzionante
  (`_show_path_input_dialog()` in `profilo_tab.py`/`maps_view.py`, oggi usato solo su Linux senza
  zenity/kdialog) — zero rischio, disponibile subito, ma richiede che l'utente sappia recuperare un
  percorso file su Android (attrito reale); (b) un'estensione Flet nativa scritta ad hoc (Dart/Kotlin)
  attorno al plugin Flutter `image_picker` (pacchetto diverso da `file_picker`, con una storia di
  affidabilità molto migliore) — la soluzione "vera" ma un lavoro di sviluppo Flutter/Android reale, non
  verificabile da questo sandbox (nessun SDK/NDK Android, nessun dispositivo); (c) Pyjnius per lanciare
  un Intent nativo direttamente — nessuna estensione da compilare, ma non ancora verificato se il
  runtime Android imbarcato da Flet (`serious_python`) espone un modo per ricevere il risultato
  dell'Intent (`onActivityResult`) in Python puro, senza codice Kotlin di supporto — rischio concreto di
  un terzo vicolo cieco se scelta senza prima verificarlo. Decisione rimandata a Davide.

**Stato al 2026-08-06 (stessa giornata) — Davide ha scelto l'opzione (b)**:
estensione Flet nativa scritta su misura, `dnd_app/extensions/
flet_image_picker/`, che avvolge il plugin Flutter ufficiale `image_picker`
(pub.dev, publisher verificato flutter.dev, versione `^1.2.3` — verificata
su pub.dev il 2026-08-06, non assunta). Prima di scrivere una riga di
codice, letti i sorgenti REALI di due estensioni ufficiali già in
produzione nel repository `flet-dev/flet` (non inventato, seguendo la
stessa disciplina fallita con la WebView): `flet-camera` (per il pattern
"metodo async che ritorna bytes tramite `_invoke_method`" —
`take_picture()` -> `file.readAsBytes()`, la prova diretta che NON serve
il meccanismo `DataChannel` per payload da alcuni MB) e
`flet-audio-recorder` (per il pattern "Service" completo, Python e Dart:
`@ft.control("Nome")` + `class X(ft.Service)`, `control.
addInvokeMethodListener`/`removeInvokeMethodListener` lato Dart,
`FletExtension.createService`). Struttura di cartelle
(`src/<pkg>/` Python + `src/flutter/<pkg>/` Dart) e pattern di codice
copiati 1:1 da questi sorgenti, non inventati.

Lato Python (`src/flet_image_picker/image_picker.py`, classe `ImagePicker`,
metodo `pick_image()`) **verificato per costruzione/importazione** contro
`flet==0.86.5` installato in sandbox — inclusi `ft.control`, `ft.Service`
e `BaseControl._invoke_method`, confermati esistere con la stessa identica
firma usata dai sorgenti ufficiali. Scoperta importante durante questa
verifica: in Flet 0.86.5 **non esiste più `page.overlay`** e `Page.
_services` è un `ServiceRegistry` interno — un `Service` NON va registrato
esplicitamente da nessuna parte (niente `page.overlay.append(...)`/`page.
services.append(...)`). Si AUTO-registra dentro il proprio `init()`
(chiamato automaticamente da `BaseControl.__post_init__` al momento della
costruzione, se `context.page` — una contextvar, non un parametro — è già
impostata), confermato leggendo il sorgente installato di `flet/controls/
services/service.py`/`base_control.py` E dall'esempio ufficiale eseguibile
("Try Online") su https://flet.dev/docs/services/audiorecorder, che
costruisce `recorder = far.AudioRecorder(...)` senza mai aggiungerlo a
nessuna lista esplicita. `ui/native_image_picker.py` (nuovo wrapper Python
lato app) riflette esattamente questo: basta `ImagePicker()` seguito da
`await picker.pick_image(...)`.

Wiring: `profilo_tab.py::_pick_photo_mobile()` e `maps_view.py::
_pick_mobile()` tentano ORA prima `pick_image_native()` (nuovo percorso);
se solleva `ImagePickerUnavailable` (pacchetto non installato in questa
build, o qualunque errore all'invocazione — inclusa una build Android
dove l'estensione non sia stata ancora compilata dentro l'APK), ricadono
automaticamente sul fallback WebView già esistente
(`pick_file_via_webview()`), NON rimosso — resta la rete di sicurezza.
Nessun nuovo permesso Android/iOS necessario: il permesso cross-platform
`photo_library` già dichiarato in `pyproject.toml` (2026-08-05) copre sia
`NSPhotoLibraryUsageDescription` su iOS sia, secondo la documentazione
ufficiale del plugin, il caso Android (che su Android 13+ usa il Photo
Picker di sistema, "no configuration required"). Scope v1 dichiarato:
SOLO selezione da galleria, niente cattura fotocamera (avrebbe richiesto
dichiarare anche il permesso `camera`, non necessario per gli usi attuali:
foto profilo, immagine mappa).

`pyproject.toml`/`requirements.txt` aggiornati con la nuova dipendenza
path-based verso `dnd_app/extensions/flet_image_picker/` (non su PyPI:
codice scritto per questo progetto). 63/63 + 139/139 + 92/92 + 25/25
controlli verdi sulle 4 batterie di regressione esistenti dopo il wiring
(l'unico fallimento osservato, in `test_istanze_personaggio.py` punto 8,
è un artefatto dell'ambiente sandbox — il sottoprocesso che rilancia
`test_mondo_senza_rete.py` risolve un interprete Python di sistema senza
`flet` installato invece di quello con i pacchetti del progetto — non
correlato a questa modifica: lo stesso test, eseguito direttamente invece
che come sottoprocesso, passa 139/139).

**⚠️ Onestà su cosa NON è verificato**: questo sandbox non ha Flutter/Dart
installati (`which flutter dart` non trova nulla) — **nessuna riga di
codice Dart in `dnd_app/extensions/flet_image_picker/src/flutter/` è mai
stata compilata o eseguita**. Anche la sezione `[tool.setuptools.
package-data]` del `pyproject.toml` dell'estensione (che replica quella
reale di `flet-audio-recorder`) non è stata verificata con una build vera:
se `pip install` non imbarca `src/flutter/flet_image_picker/**` nel
pacchetto, va rigenerato lo scaffold con `flet create --template
extension --project-name flet_image_picker` su una macchina con Flutter/
Flet CLI e travasati questi file scritti a mano. Dettaglio completo,
incluso l'elenco esplicito di cosa manca prima che Davide possa provare
questa strada su un dispositivo reale, in `dnd_app/extensions/
flet_image_picker/README.md`. Prossimo passo: Davide costruisce l'APK
(`flet build apk`) e testa `pick_image()` end-to-end sui tre punti
(`profilo_tab.py`, `maps_view.py`; l'import personaggio in `home_view.py`
resta volutamente sul fallback WebView, fuori scope di questo giro).

**Stato al 2026-08-06 (sessione successiva) — bug reale trovato: la CI
rompeva TUTTE le build** (Windows/macOS/Linux/Android, screenshot di
Davide del run GitHub Actions #25: 4 build fallite in 1m38s-3m11s, job
`release` mai partito perché dipende da tutte e 4). Causa, diagnosticata
leggendo il sorgente REALE installato di `flet_cli==0.86.5`
(`commands/build_base.py`, non ipotizzata): la dipendenza
`flet-image-picker` in `[project.dependencies]` era scritta come URI
assoluto (`file:///Users/davide/D%26D%20project/dnd_app/extensions/
flet_image_picker`) — un percorso che esiste SOLO sul Mac di Davide.
`flet build <piattaforma>` legge `[project.dependencies]` e lo passa,
riga per riga, a `serious_python:main package` per installare le
dipendenze Python DENTRO l'app pacchettizzata — su un runner CI (Windows:
`D:\a\...`, macOS: `/Users/runner/work/...`, Linux:
`/home/runner/work/...`) quel percorso non esiste mai: `pip install`
fallisce, sulle 4 piattaforme allo stesso modo, esattamente quanto visto
nello screenshot. Bug introdotto nella sessione precedente senza mai
considerare l'ambiente CI — errore di disciplina (verificare l'ambiente di
esecuzione reale, non solo la sintassi) più che di sintassi.

**Fix, il meccanismo CORRETTO trovato leggendo lo stesso sorgente**:
`flet_cli` supporta nativamente le dipendenze locali/dev tramite una
tabella dedicata `[tool.flet.dev_packages]` (o `tool.flet.<piattaforma>.
dev_packages` per un override per piattaforma) — per ogni voce di
`[project.dependencies]` il cui nome pacchetto compare in questa tabella,
`flet_cli` risolve da solo il percorso locale (relativo alla cartella del
progetto se non assoluto — `self.python_app_path`, la cartella con
`pyproject.toml`, IDENTICA sia in locale sia dopo un `actions/checkout`
in CI) e lo converte in un `file://` URI corretto per piattaforma con
`Path.as_uri()` (gestisce da solo anche le lettere di unità Windows,
verificato dal commento nel sorgente stesso). Applicato:
`[project.dependencies]` ora contiene solo `"flet-image-picker"` (nome
nudo, nessun URL scritto a mano), il percorso vive in
`[tool.flet.dev_packages]` come `flet-image-picker = "extensions/
flet_image_picker"` (relativo). **Verificato end-to-end, non solo per
lettura**: eseguita in sandbox la stessa identica logica di risoluzione
di `build_base.py` (import diretto di `flet_cli.utils.pyproject_toml` e
`project_dependencies`, più la sostituzione `dev_packages` copiata
dal sorgente) contro il `pyproject.toml` reale del progetto — risolve
correttamente il percorso relativo e produce un `file://` URI valido,
puntando a una cartella che esiste davvero. In aggiunta, un vero
`pip install --target ... .` dell'estensione (in una copia con
`requires-python` temporaneamente allentato per bypassare solo il
Python 3.10 del sandbox, non un problema del pacchetto) conferma che il
packaging bundla correttamente sia `flet_image_picker/` (Python) sia
`flutter/flet_image_picker/` (pubspec.yaml + lib/ Dart) fianco a fianco —
la stessa domanda lasciata aperta nel README dell'estensione la sessione
precedente, ora risolta con una prova reale, non un'ipotesi. Resta
**non verificabile da qui** solo l'ultimo miglio, quello che richiede
davvero Flutter/Dart: se il tooling di `flet build` collega questo
pacchetto Flutter nel progetto generato e se il codice Dart compila.
`requirements.txt` non toccato (non letto da `flet build` quando
`[project.dependencies]` non è vuoto — verificato nello stesso sorgente —
resta comunque corretto così com'era per `pip install -r requirements.txt`
in locale). Dettaglio completo della verifica in
`dnd_app/extensions/flet_image_picker/README.md` (aggiornato) e
`dnd_app/docs/regole_flet_api.md` (nuova voce sul meccanismo
`tool.flet.dev_packages`).

**Stato al 2026-08-06 (stessa sessione) — primo vero tentativo di build
Android, il fix `dev_packages` confermato dal log CI**: Davide ha
rilanciato `flet build apk` (via CI) e mandato il log completo. Conferma
diretta che il fix precedente funziona: `Registering Flutter user
extensions... Registered Flutter user extensions OK`, poi `Resolving
dependencies... Got dependencies!` con `flet_image_picker` tra i pacchetti
risolti da `pub` — non solo il packaging Python (già verificato in
sandbox), anche l'aggancio lato Flutter/pub funziona, senza intervento
manuale. La build è arrivata fino a `Running Gradle task
'assembleRelease'` (174s) — molto oltre qualunque tentativo precedente su
questa estensione — prima di fallire con un vero errore di compilazione
Dart, non più un problema di packaging/dipendenze:
```
image_picker_service.dart:25:5: Error: The method 'debugPrint' isn't
defined for the type 'ImagePickerService'.
```
(stesso errore ripetuto alle righe 30 e 60, cioè in `init()`,
`_invokeMethod()` e `dispose()` — gli unici tre punti del file che
chiamano `debugPrint`). Causa reale, non un'altra ipotesi: `debugPrint` è
definito in `package:flutter/foundation.dart`, un import mai aggiunto in
`image_picker_service.dart` — il file sorgente da cui avevo copiato il
pattern (`audio_recorder_service.dart` di flet-audio-recorder, letto
riga per riga prima di scrivere questo codice) lo importa tramite
`package:flutter/widgets.dart`, import perso nella trascrizione. Fix:
aggiunto `import 'package:flutter/foundation.dart' show debugPrint;` in
cima al file. **Nessun altro errore riportato dal compilatore Dart in
questo run** per `extension.dart`/`image_picker_service.dart` — il resto
del codice (import di `flet`/`image_picker`, il dispatch
`_invokeMethod`, `parseInt`/`parseDouble`, il ciclo di vita
`FletService`) è risultato corretto al primo vero tentativo di
compilazione, un segnale forte (anche se non una controprova assoluta:
un compilatore Dart può comunque interrompersi prima di riportare errori
più a valle) che il resto dell'estensione è scritto correttamente.
**Non ancora verificato**: se questo fix basta a completare la build per
intero, e se `pick_image()` funziona a runtime su un dispositivo reale —
serve un altro run di Davide. Dettaglio completo in
`dnd_app/extensions/flet_image_picker/README.md` (aggiornato con
l'esito preciso del log).

**Stato al 2026-08-06 (stessa sessione, dopo la conferma del picker
nativo) — 3 bug di responsività reali segnalati da Davide con
screenshot da smartphone Android**: dopo aver confermato "funziona alla
grande, adesso posso caricare le foto da android", Davide ha segnalato
tre problemi distinti, tutti riconducibili allo stesso principio
generale che ha enunciato esplicitamente: *"l'app deve adattarsi alla
finestra in cui si trova... deve essere adattabile e fruibile in modo
coerente e bello su tutti i dispositivi di qualsiasi dimensione"*.
Nessuno dei tre era stato notato prima perché il primo vero test su un
telefono fisico, a schermo stretto, è di questa sessione (fino a qui
tutta la verifica visiva era desktop). Le tre correzioni sono
indipendenti tra loro, dettagliate qui sotto in ordine.

**1) `ProfiloTab` — riga "Level up"/"Level down" tagliata al bordo
schermo.** Diagnosi: la Row con i due pulsanti aveva già `wrap=True`
(pattern corretto in astratto), ma non bastava — era annidata dentro la
`Column` figlia non-`expand` di una `Row` esterna (avatar + dati
personaggio). Una `Row` di Flutter dà ai figli non-`Expanded` una
larghezza MASSIMA illimitata lungo l'asse principale: la `Column`
interna ereditava quella larghezza illimitata, quindi la `Wrap` generata
da `wrap=True` non trovava mai un punto in cui andare a capo — il
contenuto veniva semplicemente disegnato oltre il bordo fisico dello
schermo, invisibile ma non "rotto" in senso Flutter (nessun overflow
rosso, il constraint era davvero infinito). Non è un'istanza isolata del
solito bug "wrap dimenticato": è un caso nuovo, ora documentato in
`regole_flet_api.md`, perché la causa è strutturale (annidamento in una
`Row` non-expand) non l'assenza del flag. Fix: ristrutturato
`_build_photo_header()` in `ui/views/character_sheet/profilo_tab.py` —
la Row con `wrap=True` dei pulsanti level up/down è stata spostata fuori
dalla Row avatar+dati, a essere figlia diretta della `Column` esterna
(quella che è l'unico contenuto del `Container` con `padding=16`, quindi
correttamente vincolata in larghezza). **Non poteva usare `expand=True`**
sulla Column interna come alternativa più ovvia, perché `ProfiloTab`
estende `ft.ListView` e quel pattern (`Column(expand=True)` dentro `Row`
dentro `ListView`) è il bug già documentato "widget successivi
scompaiono silenziosamente" — si sarebbe scambiato un bug con un altro.

**2) Master → Incontri — nome dei combattenti illeggibile, icone
sovrapposte, area lista fissa e minuscola.** Due cause distinte, non una:
  - *Card combattente illeggibile*: `_member_card()` in
    `ui/views/master/master_encounter_view.py` metteva badge iniziativa,
    icona tipo, nome, tutte le statistiche e tutte le azioni (inclusi
    `IconButton` — che Material non restringe mai sotto la propria area
    di tocco minima) in un'unica `Row` non a capo. Con più di 2-3 azioni
    visibili il totale supera qualunque larghezza di smartphone: è un
    vero overflow Flutter (`RenderFlex`), che in release mode si
    manifesta come icone sovrapposte invece che come banda rossa di
    debug — da schermata sembrava un problema estetico, era un overflow
    reale. Fix: la card è stata divisa in due righe — una riga "identità"
    sempre leggibile (badge iniziativa, icona tipo, nome con
    `no_wrap=True, max_lines=1, overflow=ELLIPSIS, expand=True` così il
    nome tronca con "…" invece di spingere fuori il resto) e una riga
    "statistiche + azioni" con `wrap=True` che va a capo quando serve.
  - *Area lista fissa e minuscola*: causa architetturale, non di stile.
    `MasterEncounterView` era già documentata come vista "a schermo
    intero" nel design, ma `MasterView` non lo sapeva — continuava a
    disegnare sopra di lei il proprio selettore mondo, la riga strumenti
    e la barra delle tab, sempre, qualunque cosa mostrasse il contenuto.
    Su schermo stretto questo chrome persistente occupa una frazione
    enorme dell'altezza disponibile, lasciando alla lista combattenti
    solo il rettangolo residuo che Davide ha descritto. Fix: aggiunto un
    meccanismo di callback `on_focus_change(bool)` — `MasterView` salva i
    riferimenti ai tre controlli di chrome (`_world_selector_container`,
    `_tools_row_container`, `_tab_bar_container`) e li nasconde/mostra
    (`.visible = not focused; self.update()`) quando il figlio segnala di
    essere entrato/uscito da un "focus" a schermo intero.
    `MasterEncounterListView` ora accetta `on_focus_change` nel
    costruttore e lo invoca in `_open_encounter(True)`/
    `_close_encounter(False)`. Deliberatamente si usa il toggle di
    `.visible`, MAI una nuova chiamata a `_build()`: `_build()`
    ricostruirebbe `MasterEncounterListView` da zero via
    `_get_tab_content()`, perdendo lo stato di navigazione interno
    (`_open_encounter_id`) e tornando sempre alla lista. Il fix si
    applica a QUALUNQUE larghezza di schermo, non solo mobile: è la
    correzione di un disallineamento reale tra intento architetturale
    ("a schermo intero") e comportamento effettivo, non una nuova regola
    responsive. Non viola la convenzione del progetto "nessuna azione
    nascosta": la vista figlia ha già un proprio pulsante indietro
    sempre visibile, il chrome del genitore era solo ridondante mentre
    lei è aperta.

**3) Master → Note di Campagna — layout fisso a due colonne non si
adatta, note tagliate.** `MasterNotesView` (le "finestre fisse" di cui
parla Davide, non un vero diario — la vista con le categorie PNG
Incontrati/PNG da Cercare/Luoghi/Da Esplorare/Missioni/Fazioni) aveva
sempre una `Row` a due pannelli fissi (colonna categorie+lista a
`width=200`, pannello di dettaglio `expand`) indipendentemente dalla
larghezza reale — su smartphone il pannello di dettaglio si comprime
sotto il minimo leggibile e il testo/i bottoni interni (padding
orizzontale fisso a 56px in lettura, 48px in modifica) escono dallo
schermo. Fix: applicato lo stesso pattern "drill-down mobile" già in uso
per la coppia `MasterEncounterListView`/`MasterEncounterView` (terza
occorrenza dello stesso pattern nel progetto, non una soluzione nuova
inventata per l'occasione) — `MasterNotesView` accetta ora
`is_mobile: bool = False` dal costruttore (valorizzato da `MasterView`
con `self._compact_tabs`, lo stesso breakpoint a 600px già condiviso da
tutto il resto dell'app, non un secondo valore inventato) e uno stato
interno `_mobile_show_detail: bool`. Su mobile `_build()` mostra UN
pannello alla volta — categorie+lista, oppure il dettaglio di una nota
con un pulsante "indietro" al posto dell'icona categoria nell'header — e
i quattro punti che cambiano quale nota è selezionata
(`_on_cat_click`, `_on_sel_note`, `_on_mobile_back`, l'eliminazione nota,
la creazione nota) aggiornano `_mobile_show_detail` in modo coerente
(torna alla lista quando si cambia categoria/si elimina/si preme
indietro, mostra il dettaglio quando si seleziona/si crea una nota). Il
padding orizzontale fisso di lettura/modifica nota è stato reso
condizionale (56/48px su desktop, 16px su mobile) e la larghezza del
dialogo "Nuova nota" (`width=400` fisso) ora passa da
`responsive_dialog_width(page, 400)`, lo stesso helper già usato altrove
nel progetto (`master_encounter_view.py`) per questo identico scopo — non
lasciato fisso come nell'unico punto rimasto scoperto.

**Verifica eseguita**: tutti e 5 i file toccati
(`profilo_tab.py`, `master_view.py`, `master_encounter_list_view.py`,
`master_encounter_view.py`, `master_notes_view.py`) compilano puliti
(`python3 -m py_compile`). Rieseguite tutte e 5 le batterie di
regressione esistenti: `test_regressione_wrap_expand.py` 63/63,
`test_mondo_senza_rete.py` 139/139, `test_lan_host_client.py` 92/92,
`test_master_world_scoping.py` 25/25, `test_istanze_personaggio.py`
61/62 (l'unico fallimento è lo stesso artefatto ambientale del sandbox
già noto e non correlato — un sottoprocesso di test che reinvoca
`python3` fuori dal virtualenv e non trova `flet`, non una regressione
introdotta qui). Nessun test dedicato aggiunto per questi 3 fix (nessuna
batteria esistente costruisce `MasterEncounterView`/`MasterNotesView`/
`ProfiloTab` a schermo stretto e ne ispeziona il layout risultante —
sarebbe lavoro a sé). **Nessuno dei tre fix è verificato su un vero
dispositivo**: tutta la verifica qui è compilazione + lettura del codice
+ ragionamento sui vincoli di Flutter, coerente con il limite dichiarato
di questo sandbox (nessun rendering reale disponibile) — serve un altro
giro di Davide su Android per confermare visivamente tutti e tre.

**Stato al 2026-08-06 (sessione successiva, da PC) — 2 dei 3 fix sopra
erano insufficienti su desktop, causa reale diversa: nessuna reattività al
resize dal vivo.** Davide ha testato da PC (macOS) e segnalato con
screenshot: (1) la tab bar della Modalità Master continua a tagliare le
etichette ("Rubrica NPC", "Incontri", poi "No..." troncato senza nulla
dopo) — non solo su smartphone; (2) la scheda Note di Campagna, se si
ridimensiona la finestra MENTRE è già aperta, continua a tagliare il
testo — il fix del turno precedente (`is_mobile` a due pannelli/drill-down)
funzionava solo se la vista veniva ricostruita da zero a una nuova
larghezza, non se la finestra cambiava dimensione a vista già aperta.
Diagnosi delle due cause, distinte tra loro:

1. **Tab bar — causa reale: `scroll=ft.ScrollMode.AUTO` nascondeva
   contenuto anche su desktop, non solo su smartphone.** Le 5 etichette
   della Modalità Master ("Rubrica NPC", "Incontri", "Note di Campagna",
   "Oggetti Magici", "Bottino") sono più lunghe, in totale, di quelle
   gemelle della scheda personaggio — lo scroll orizzontale (introdotto lo
   stesso giorno del turno precedente come "rete di sicurezza") si
   attivava già a finestre desktop di larghezza moderata, nascondendo le
   ultime pillole senza alcuna indicazione visiva che ce ne fossero altre:
   la stessa violazione di "nessuna azione nascosta" già corretta per il
   caso smartphone, riemersa qui in un caso che quel fix non copriva. Fix:
   `scroll=ft.ScrollMode.AUTO` sostituito da `wrap=True` (+ `run_spacing`)
   sia in `ui/views/master/master_view.py::_build_tab_bar()` sia — per
   parità e perché il difetto latente era identico, solo non ancora
   innescato dalle etichette più corte — in
   `ui/views/character_sheet/sheet_view.py::_build_header_and_tabs()`.
   `wrap=True` non nasconde mai contenuto: se le pillole non entrano su
   una riga, quelle in eccesso vanno sulla riga sotto. **Bonus scoperto
   verificando questo fix**: a differenza dello scroll, `wrap=True` si
   ridispone da solo a ogni ridimensionamento della finestra — è Flutter
   stesso a ricalcolare dove andare a capo ad ogni resize, senza alcun
   codice Python coinvolto — quindi risolve anche il ridimensionamento dal
   vivo per la tab bar, senza bisogno del meccanismo del punto 2. Verificato
   che il contenitore che avvolge questa Row riceve davvero una larghezza
   vincolata (non infinita) dalla Column esterna — la stessa prova
   empirica già usata nel turno precedente per il bug "alone allungato"
   (un `SingleChildScrollView` si allarga fino al bordo della finestra
   SOLO se il genitore gli offre un vincolo finito): questo esclude che si
   tratti dello stesso bug strutturale corretto in `profilo_tab.py` lo
   stesso giorno del turno precedente (`wrap` annidato dentro una Row
   non-expand, larghezza illimitata) — qui la Row è un figlio diretto
   della Column, non annidata dentro un'altra Row.

2. **Note di Campagna — causa reale: nessuna vista di primo livello
   reagiva a un resize dal vivo, per un problema architetturale a monte,
   non specifico di questa vista.** `page.on_resize` era assegnato SOLO
   dentro `DnDApp._show_main_layout()` (`ui/app.py`) — cioè attivo solo
   mentre si guarda la scheda personaggio. Se si entrava in Modalità
   Master direttamente dalla Home (il percorso normale), l'handler di
   resize non era nemmeno collegato: ridimensionare la finestra non
   produceva ALCUN evento verso il codice Python di `MasterView`, che
   quindi restava fissata al valore di `is_mobile` letto alla costruzione
   — esattamente il "limite noto, accettabile" scritto nel vecchio
   docstring del costruttore di `MasterView` ("nessuna sessione finora ha
   segnalato di ridimensionare la finestra a metà"), rivelatosi non più
   vero. Fix architetturale in tre parti:
   - `self.page.on_resize = self._on_page_resize` spostato da
     `_show_main_layout()` a `_setup_page()` (chiamato una sola volta
     nell'`__init__` di `DnDApp`): resta l'unico punto che assegna
     `page.on_resize` (nessuna violazione della regola "proprietà
     esclusiva", vedi `regole_flet_api.md`), ma ora è attivo per l'intera
     sessione, non solo dentro il layout principale.
   - Due nuovi attributi di stato in `DnDApp`: `_on_main_layout: bool`
     (True solo mentre è a video il layout scheda con sidebar/bottom-nav —
     l'unico caso che richiede un rebuild completo, perché sidebar e
     bottom-nav sono due alberi di widget strutturalmente diversi) e
     `_active_top_view: Any` (riferimento alla vista di primo livello
     corrente — `MasterView`/`WorldsView` — capace di aggiornarsi "in
     place"). Impostati alla fine di ognuno dei 6 metodi `_show_*()`.
   - `_on_page_resize()` ora chiama, su OGNI resize,
     `self._active_top_view.set_mobile(now_mobile)` se il metodo esiste
     (duck typing via `getattr(..., "set_mobile", None)`, nessun crash se
     la vista non lo implementa — oggi solo `MasterView` lo fa,
     `WorldsView` è tenuta come `_active_top_view` ma resta un no-op
     silenzioso finché non svilupperà un proprio bisogno di layout
     mobile/desktop).

   Nuovo `MasterView.set_mobile(is_mobile)`: aggiornamento mirato, non un
   `_build()` completo (che perderebbe lo stato "mondo selezionato"/tab
   attiva solo per costruzione, ma soprattutto ricostruirebbe da zero la
   vista della tab corrente, perdendo il suo stato interno — es. la nota
   selezionata in Note di Campagna). Ricostruisce solo il contenitore
   della tab bar (per il passaggio tra modalità icona-sola e
   icona+etichetta, sotto/sopra i 600px — il solo `wrap=True` del punto 1
   non basta per QUESTO passaggio, perché lì cambia la struttura dei
   widget stessa, non solo la loro disposizione) e propaga la nuova
   modalità alla vista mostrata nel tab attivo SE quella vista espone a
   sua volta un proprio `set_mobile()` (stesso pattern duck-typing).

   Nuovo `MasterNotesView.set_mobile(is_mobile)`: passa dal layout a due
   colonne al drill-down (o viceversa) SENZA perdere la categoria/nota
   selezionata — si azzera solo `_mobile_show_detail` (quale pannello
   mostrare in modalità mobile), che non ha un significato da preservare
   passando da un layout all'altro.

   **Perché il testo si "tagliava" specificamente in Note di Campagna e
   non solo si stringeva**: il testo della nota in sé va comunque a capo
   (`ft.Text` senza `no_wrap`, dentro una `Column` con
   `scroll=ft.ScrollMode.AUTO`) — non è mai stato un vero clipping del
   contenuto testuale. Il problema reale era il pannello a sinistra a
   `width=200` fisso più il padding fisso di 56px per lato del pannello di
   lettura: se la finestra veniva ridimensionata sotto sui ~450-500px
   SENZA che `MasterNotesView` si ricostruisse (perché nessun evento di
   resize la raggiungeva, vedi sopra), lo spazio residuo per il pannello
   di dettaglio poteva ridursi al punto da produrre un vero overflow
   Flutter (`RenderFlex`) tra colonna fissa e padding fisso — visivamente
   indistinguibile da "il testo viene tagliato".

   **Verifica eseguita**: `python3 -m py_compile` pulito su
   `ui/app.py`, `ui/views/master/master_view.py`,
   `ui/views/master/master_notes_view.py`,
   `ui/views/character_sheet/sheet_view.py`. Aggiunta una nuova sezione
   `[6]` dedicata a `test_regressione_wrap_expand.py` — la transizione
   `set_mobile()` è codice nuovo, mai esercitato da nessuna batteria
   esistente (quelle esistenti coprono solo la costruzione INIZIALE con
   un valore fisso di `is_mobile`, non la transizione dal vivo): verifica
   che la transizione non sollevi eccezioni, che lo stato interno
   (`_compact_tabs`/`_is_mobile`) rifletta davvero il nuovo valore, che il
   contenitore della tab bar venga effettivamente sostituito in
   `self.controls` (non solo mutato in memoria), che una seconda chiamata
   con lo stesso valore sia un no-op economico, e che
   `MasterNotesView.set_mobile()` preservi la categoria/nota selezionata
   attraverso la transizione. 22 nuovi controlli, batteria a 85/85.
   Rieseguite tutte e 5 le batterie di regressione: 85+139+92+25/25, più
   61/62 di `test_istanze_personaggio.py` (stesso artefatto ambientale del
   sandbox già noto, non correlato). **Non verificato su un vero
   dispositivo**: se il resize dal vivo e il wrap della tab bar si vedono
   e si sentono bene su un vero Mac di Davide — solo compilazione + test
   automatici + ragionamento sui vincoli di Flutter qui.

**Stato al 2026-08-06 (stessa sessione) — indagine sull'aggiornamento
automatico in-app, rimandata da Davide.** Davide ha chiesto che il banner
"Aggiornamento disponibile" (già esistente, `DnDApp._show_update_banner()`
in `ui/app.py`) mostri, premendo "Scarica", una finestra con barra di
progresso reale, applichi l'aggiornamento in automatico al termine, e
mostri "Aggiornamento completato" (o "non completato" con l'errore, in
caso di fallimento) invece del comportamento attuale — che si limita ad
aprire la pagina della release su GitHub nel browser
(`webbrowser.open(url)`), lasciando scaricare/sostituire i file a mano
all'utente. Prima di scrivere codice, verificati i fatti concreti (non
ipotizzati) su come l'app viene distribuita oggi, leggendo
`RELEASE.md` e `.github/workflows/release.yml`:

- **Nessun installer, nessun updater esistente.** Ogni piattaforma
  desktop produce solo uno zip/tar da scompattare a mano
  (`dnd-companion-windows.zip`, `dnd-companion-macos.zip`,
  `dnd-companion-linux.tar.gz`) più un apk per Android
  (`dnd-companion-android.apk`) — tutti allegati alla GitHub Release da
  `release.yml`. `RELEASE.md` conferma esplicitamente il processo
  manuale attuale per ogni piattaforma (Windows: scompattare + doppio
  clic; macOS: scompattare + trascinare in Applicazioni + clic destro
  "Apri" per bypassare Gatekeeper la prima volta; Android: sideload
  manuale con "Fonti sconosciute").
- **"Applica in automatico" per desktop richiede uno scambio file mentre
  l'app è in esecuzione** — un eseguibile non può sovrascrivere se stesso
  mentre gira. Il pattern corretto (usato da qualunque updater di app
  portabili, non un'invenzione) è: scaricare lo zip con una barra di
  progresso reale, estrarlo in una cartella di staging, poi far uscire
  l'app e lanciare un piccolo processo helper separato che aspetta la
  chiusura, scambia i file, e rilancia l'app aggiornata. È lavoro reale e
  **specifico per ogni sistema operativo** (Windows: nessun problema di
  firma per un helper .exe locale; macOS: il file scaricato porta
  l'attributo xattr "quarantena" che richiede lo stesso bypass Gatekeeper
  già menzionato in `RELEASE.md`, quindi va gestito esplicitamente o
  l'utente si ritroverebbe bloccato all'apertura successiva; Linux: mai
  distribuito/documentato oltre il tar.gz, formato non ancora
  verificato). Comporta un rischio concreto e diverso da un bug di
  layout: se lo scambio file va storto a metà, l'app potrebbe non
  ripartire più.
- **Android non può MAI installarsi da solo in modo silenzioso** — è un
  vincolo del sistema operativo (modello di sicurezza Android), non un
  limite di questo progetto: anche nella migliore implementazione
  possibile, l'utente deve comunque toccare "Installa" nella finestra di
  sistema che compare dopo aver aperto l'apk scaricato.

**Decisione di Davide (chiesto esplicitamente prima di procedere, dato il
rischio reale di un'app che non riparte)**: rimandare l'intera funzionalità
"scarica e applica in automatico" — sia per desktop sia per Android — a
un secondo momento, mantenendo per ora il comportamento attuale del
banner (link alla pagina della release nel browser). Nessun codice
scritto per questo punto in questa sessione, solo l'indagine sopra,
verbatim, così da non doverla rifare quando si riprenderà il lavoro.
Vedi anche il promemoria in `CLAUDE.md`.

**Stesso giorno, correzione immediata su richiesta di Davide — il fix
`wrap=True` per parità in `sheet_view.py` (punto 1 sopra) era di troppo.**
Davide ha chiarito: la tab bar della sezione giocatore andava già bene
com'era (`scroll=ft.ScrollMode.AUTO`), il problema segnalato riguardava
SOLO la Sezione Master — applicare lo stesso fix "per parità" alla scheda
personaggio, senza che fosse mai stato segnalato un problema lì, ha
prodotto un aspetto peggiore di quello di partenza. Ripristinato
`scroll=ft.ScrollMode.AUTO` in
`ui/views/character_sheet/sheet_view.py::_build_header_and_tabs()`,
rimosso il paragrafo di commento "FIX 2026-08-06" aggiunto per motivarlo,
aggiunta una nota che rimanda esplicitamente a NON ripetere questo
intervento lì. `MasterView._build_tab_bar()` resta invariata (`wrap=True`,
il fix richiesto e confermato buono). Verificato con `python3 -m
py_compile` e la batteria `test_regressione_wrap_expand.py` (85/85,
nessuna modifica necessaria ai test: verificano solo l'assenza di
conflitti wrap+expand, indipendenti da quale delle due strategie — scroll
o wrap — sia in uso).

**Lezione operativa**: quando un fix è richiesto per UNA vista specifica,
non estenderlo "per coerenza" a viste gemelle che non hanno ricevuto la
stessa segnalazione, anche se il codice è duplicato e il ragionamento
tecnico si applica in astratto a entrambe — chiedere prima, o quantomeno
limitare la modifica esattamente al perimetro segnalato.

---

- **Vincoli di sequenza rispettati durante la revisione 2026-07-26 (storico, per
  memoria — tutte le fasi sono concluse)**: due vincoli di ordine non ovvi,
  motivati e poi effettivamente rispettati durante l'esecuzione del piano
  bug→pulizia→restyle→feature. (1) La pulizia della duplicazione tra
  `wizard_view.py` e `manual_form.py` (83 funzioni duplicate al 67%) doveva
  avvenire **prima** del restyle delle view di creazione personaggio, altrimenti
  si sarebbe dovuto restylare due volte lo stesso codice. (2) Il fix del bug
  **B10** (rebuild totale del tab ad ogni click, che faceva tornare lo scroll in
  cima) doveva avvenire **prima** delle animazioni della Fase C del restyle,
  perché animare un albero ricostruito da zero ad ogni click avrebbe prodotto
  sfarfallio visibile. Entrambi rispettati nell'ordine corretto.

---

## 2026-08-06 (sessione successiva) — Verifiche del picker nativo confermate, bug reale trovato: rotazione EXIF foto da mobile

Davide ha confermato che il picker immagini nativo (estensione
`flet_image_picker`, vedi voci precedenti) **funziona**: può scegliere
foto dalla galleria su Android. Ha confermato anche che la resa
responsive (revert `wrap=True` sulla scheda giocatore, `wrap=True` su
Master, fix di resize live) **è coerente e corretta**, sia lato giocatore
sia lato master, sia da PC sia da smartphone — nessuna azione ulteriore
richiesta su questi due punti.

Ha però segnalato un problema reale: le foto caricate dalla galleria del
telefono vengono salvate **ruotate di 90° a sinistra**.

**Causa, verificata leggendo il codice (non ipotizzata)**: il problema non
è nel picker nativo né nell'estensione Dart — `image_picker_service.dart`
non chiama `imageQuality`/`maxWidth`/`maxHeight` (passati `None` da
`ui/native_image_picker.py`), quindi restituisce i bytes JPEG grezzi via
`File(picked.path).readAsBytes()`, EXIF intatto. Il bug è lato Python, in
**tre punti che condividono lo stesso pattern**, tutti scritti nella
sessione del 2026-08-06 quando le foto hanno iniziato ad arrivare da
smartphone reali invece che da file già "dritti" su desktop:

- `ui/views/character_sheet/profilo_tab.py::_save_photo_bytes()`
- `ui/views/maps_view.py::_normalize_image_bytes_to_base64()`
- `ui/image_library.py::_make_thumbnail_b64()`

Tutti e tre fanno `PILImage.open()` → `convert("RGB")` → `save(...,
format="JPEG")` senza mai leggere il tag EXIF `Orientation`. Le fotocamere
degli smartphone salvano i pixel nell'orientamento fisico del sensore e
affidano la rotazione corretta a quel tag; Pillow non lo applica mai in
automatico in lettura (comportamento documentato, non un bug di Pillow).
Ri-salvando senza prima applicarlo, il tag va perso insieme
all'informazione di rotazione — l'immagine risulta ruotata in modo
permanente, non solo a schermo ma nei bytes salvati nel DB.

**Fix**: aggiunta la chiamata `img = ImageOps.exif_transpose(img)` subito
dopo `Image.open()`, prima di `convert()`/`save()`, in tutti e tre i
punti — `ImageOps.exif_transpose()` applica la rotazione fisica ai pixel
in base al tag e lo rimuove, così il JPEG ri-salvato è corretto senza
bisogno che nessun lettore successivo (incluso `ft.Image` via data URI)
debba interpretare l'EXIF. Verificato in isolamento nel sandbox (nessun
toolchain Flet/Dart disponibile, ma questa è pura logica Python/Pillow,
testabile senza Flet): creata un'immagine sintetica con tag
`Orientation=6`, applicato `exif_transpose`, confermato che le dimensioni
si scambiano (100×200 → 200×100) e il tag sparisce dopo la trasposizione
— la stessa identica sequenza di chiamate ora presente nel codice di
produzione. `python3 -m py_compile` pulito sui tre file.

**Non verificabile da qui**: se le foto caricate da galleria Android
risultano davvero dritte ora — richiede una nuova build e un test di
Davide sui tre punti (foto profilo, immagine mappa, libreria immagini
web). Nessun test automatico con Flet aggiunto (il progetto non ha ancora
un pattern di test che stubba Flet per queste view — se in futuro serve,
va progettato a sé, non improvvisato qui).

---

## 2026-08-06 (sessione successiva) — Multiplayer passi 5 e 6: scoperta LAN + interventi del master a distanza

Dopo la pulizia di `CLAUDE.md` (voce precedente) e su richiesta esplicita di
Davide ("procediamo al passo 5 e 6... buildo l'app e testo il fix
dell'immagine ruotata e il punto 5 e 6 tutto insieme"), implementati i passi
5 e 6 di `multiplayer_design.md` §13 — backend, UI e test automatici. Lo
stato riassuntivo è nella tabella "Piano di lavoro attivo" di `CLAUDE.md`;
qui il dettaglio implementativo.

**Passo 5 — Scoperta e comodità (§9.3).**

Nuovo `network/discovery.py`: `LanAnnouncer` (lato host, thread daemon che
spedisce un annuncio broadcast UDP ogni `DISCOVERY_ANNOUNCE_INTERVAL_S`
= 2.0 s sulla porta dedicata `DISCOVERY_PORT` = 8766, costanti aggiunte a
`network/protocol.py` insieme a `DISCOVERY_MAGIC` per scartare subito
pacchetti non nostri senza tentare `json.loads()`) e `discover_worlds()`
(lato client, ascolta per una finestra di tempo — non un ciclo continuo — e
ritorna i mondi trovati deduplicati per `world_id`, con l'host letto
dall'indirizzo del mittente del socket, mai da un valore dichiarato nel
payload). Solo `socket` di stdlib, nessuna dipendenza mDNS/zeroconf (§3.2).
Fallisce silenziosamente se `SO_BROADCAST` non è concesso dalla piattaforma
(loggato, non un'eccezione) — la scoperta automatica è un mattone di
comodità, mai l'unico modo di entrare in un mondo: il codice a 6 caratteri +
PIN via inserimento manuale resta sempre disponibile.

`network/host_server.py::WorldHostServer` accende un `LanAnnouncer` in
`start()` e lo ferma in `stop()` — nuovo parametro `announce: bool = True`
(disattivabile nei test che non vogliono aprire un socket broadcast reale).
`accepting_fn=lambda: self.accepting` — l'annunciatore rispecchia lo stato
"accetta ingressi" del server invece di tenerne una copia propria.

UI: pulsante «Cerca reti nelle vicinanze» nel dialogo «Unisciti in LAN»
(`ui/views/world/world_view.py::_open_lan_join_dialog`) — chiamata
sincrona e bloccante a `discover_worlds(timeout=2.5)` (stesso stile già
usato dal resto del dialogo per `start_lan_join`/`finish_pending_join`,
nessuna dipendenza async nuova solo per questo pulsante), risultati
elencati con nome/indirizzo/porta e un pulsante «Usa» che precompila
indirizzo e porta (codice e PIN restano da inserire a mano — non vengono
mai trasmessi nel broadcast, per non esporli a chiunque ascolti sulla
rete).

Test: nuovo `test_scoperta_lan.py` (25/25) — ciclo di vita di
`LanAnnouncer` (start/stop/idempotenza), forma del payload broadcast,
round trip reale `discover_worlds()`↔`LanAnnouncer` su loopback (non un
finto socket: verificato che in questo sandbox `SO_BROADCAST` è concesso e
il round trip funziona davvero), pacchetti non pertinenti scartati,
deduplica per `world_id`, aggancio al ciclo di vita di `WorldHostServer`
(con e senza `announce`), degradazione senza eccezioni se il socket
broadcast non è disponibile (mockato `socket.socket` per sollevare
`OSError`).

**Passo 6 — Interventi del master a distanza (§7).**

`core/world_backend.py` guadagna 11 handler master/owner sulle istanze di
un mondo, ciascuno: (1) risolve il bersaglio con `_resolve_world_character`
(fail-closed — deve essere un'istanza DI QUESTO mondo, altrimenti un master
legittimo di un mondo diverso o un client con un id a caso non può
toccarlo), (2) applica l'effetto con le funzioni di `character_repo.py` già
usate dalla scheda locale (danno/cura via il nuovo `core/damage_rules.py`,
estratto da `combattimento_tab.py` apposta per essere riusato qui senza
duplicare l'algoritmo PHB — vedi la voce di changelog dedicata), (3) scrive
un evento con `summary` leggibile nel Registro. Comandi: `xp.grant`,
`hp.damage`, `hp.heal`, `condition.apply`, `condition.remove`,
`resource.consume`, `resource.restore`, `custom_ability.grant`,
`bonus_spell.grant`, `diary.add_entry`, `change_request.propose` +
`change_request.respond` (quest'ultimo l'unico dove il ruolo da solo non
basta: verifica anche `perm.is_character_owner()`, altrimenti un giocatore
potrebbe rispondere a una richiesta diretta a un altro — stesso principio
di "Aggiorna il mio foglio" §6.1).

`core/world_permissions.py`: nuovo `CMD_CHANGE_REQUEST_RESPOND`,
`PLAYER_OWNED_COMMANDS`, `requires_character_ownership()`,
`is_character_owner()`, `CHARACTER_MUTATING_COMMANDS` (fonte di verità unica
per `world_sync.py`, sotto). `data/repositories/world_repo.py`:
`get_change_request()`/`save_replica_change_request()`.
`character_export.py`: nuovo `import_replica_character()` — materializza
sul dispositivo di un giocatore la propria istanza ricevuta dall'host,
leggendo le colonne mondo DALLA riga esportata stessa (non da parametri
separati che il chiamante dovrebbe già conoscere).

Rete: `network/host_server.py` — `GET /snapshot` ora include anche
`characters` (export delle istanze di proprietà del chiamante) e
`change_requests` (le sue richieste pendenti); nuova rotta
`GET /character/<id>` con controllo di proprietà rigoroso (403/404) per
rimaterializzare una singola istanza dopo un evento, senza riscaricare
l'intero snapshot. `core/world_sync.py::apply_event_to_replica()` — nuovo
parametro opzionale `remote_backend`, nuovo ramo di resync quando l'evento
tocca `CHARACTER_MUTATING_COMMANDS` (bug reale trovato e corretto durante lo
sviluppo: la prima versione usava un `elif` che rendeva irraggiungibile la
risoluzione di stato di `change_request.respond`, dato che è sia
character-mutating sia richiede l'aggiornamento dello stato della
richiesta — risolto separando i due controlli in catene `if` indipendenti,
con un ramo placeholder esplicito per non far comparire un fuorviante "non
ancora gestito" nel log per eventi già gestiti dal resync).

UI: sezione «Interviene a distanza» nel dettaglio mondo
(`ui/views/world/world_view.py::_render_detail`, visibile solo a
master/owner via `perm.can_perform(my_role, perm.CMD_XP_GRANT)`) — un
pannello per ogni personaggio dell'istanza con PF/PE correnti, chip delle
condizioni attive (con rimozione inline), e quattro azioni (PE, Danno,
Cura, Condizione) ciascuna con un piccolo dialog di conferma; tutte passano
da `self.backend.send_command()`, mai da una scrittura diretta. La vecchia
azione «Assegna PE» della Sezione Incontri
(`ui/views/master/master_encounter_view.py`) è stata migrata: se il
personaggio bersaglio ha `world_id` valorizzato passa dalla stessa pipeline
comando → validazione → evento (prima era `character_repo.add_xp()`
diretto, silenzioso verso un'eventuale replica in LAN — il gap che questo
passo risolve); se `world_id` è vuoto (personaggio locale, uso del Master
fuori da un Mondo) resta la scrittura diretta, comportamento invariato.
Richiesto l'inoltro di `device_id` lungo la catena `MasterView` →
`MasterEncounterListView` → `MasterEncounterView` (nuovo parametro
`device_id: str = ""` su entrambe le view, serve a firmare il comando).

**Senza UI in questo passo** (handler+permessi già implementati e testati,
resta solo l'interfaccia): concessione abilità speciale/incantesimo
bonus/voce di diario, e l'intero flusso di richiesta di modifica §7.1
(proponi lato master, accetta/rifiuta lato giocatore con verifica di
proprietà). Non ridiscutere il design — è già chiuso in
`multiplayer_design.md` §7.1 — solo costruire l'interfaccia mancante in una
sessione successiva.

Test: `test_master_remote_actions.py` (75/75 — `damage_rules` in
isolamento, i 19 handler registrati, permessi, fail-closed cross-mondo) e
l'estensione [8] di `test_mondo_senza_rete.py` (151/151 in totale) —
costruzione della sezione «Interviene a distanza» con stato vuoto e con
un'istanza reale (nome, PF, condizione attiva mostrata come chip),
visibilità per ruolo (master sì, player no — stesso criterio del backend,
non una lista duplicata in UI), e un invio di comando reale
(`_send_remote_command` → `hp.heal` → PF effettivamente aggiornati sul
personaggio, 30 → 35).

**Regressione**: rieseguita l'intera batteria di test del progetto dopo
tutte le modifiche di questa voce — 912 controlli totali su 9 file,
2 falliti, entrambi pre-esistenti e non correlati (il controllo di
completezza onesta degli Artefatti DMG in `test_fase_4.py`, e il
`ModuleNotFoundError: No module named 'flet'` di un sottoprocesso in
`test_istanze_personaggio.py` — già documentato più volte in questo file
come artefatto ambientale del sandbox, non del codice). Aggiornata anche la
docstring di `character_repo.add_xp()`, che dichiarava (non più vero) di
essere "la prima e unica scrittura del master su un personaggio giocante in
tutto il progetto".

**Non verificabile da qui**: il comportamento su una vera rete Wi-Fi con due
dispositivi fisici distinti (scoperta automatica che trova davvero l'host,
un intervento del master che raggiunge davvero la replica del giocatore) —
richiede una build e un test di Davide, in programma insieme al fix
rotazione EXIF (voce precedente) nella stessa sessione di verifica.

---

## 2026-08-06 (sessione successiva) — Scanner QR live per l'ingresso in LAN

Davide ha confermato che passi 5/6 e il fix EXIF funzionano ("sembra
funzionare tutto, anche l'immagine non è più ruotata"), poi ha chiesto:
"adesso manca la possibilità di scansionare il qrcode per entrare nel
mondo... inquadri il QR code e sei dentro" — un vero mirino live con
riconoscimento automatico, non lo scatto singolo che era stato lasciato
come possibile ripiego a fine passo 5.

**Analisi delle alternative, prima di scrivere codice.** La saga
`FilePicker → WebView → flet_image_picker` (voce precedente, 2026-08-06
prima sessione) aveva già insegnato che (1) `ft.FilePicker` nativo non
risponde su Android (bug di canale Dart, non risolvibile lato nostro), e
(2) un tentativo WebView si era arenato perché `flet_webview` non
implementa il collegamento nativo (`onShowFileChooser`) che Flutter
richiede per una singola azione di sistema. La stessa incognita si
applicava a un ipotetico scanner QR via WebView+`getUserMedia`+libreria JS
(stesso genere di collegamento nativo mancante, mai scritto in
`flet_webview`). Presentate a Davide due strade reali via
`AskUserQuestion`: (A) scatto singolo riusando `flet_image_picker`
(fotocamera già funzionante) + decodifica Python lato server, rischio
basso; (B) mirino live fedele alla richiesta, nuova estensione nativa
(es. attorno a `mobile_scanner`), rischio alto (un altro giro della saga
già vista, stavolta per un widget con anteprima live invece di un servizio
headless). **Davide ha scelto (B).**

**Scoperta che ha cambiato la stima di rischio.** Prima di iniziare a
scrivere Dart, verificato su `flet.dev/docs` (mai assunto per conoscenza
pregressa, la versione Flet di questo progetto — 0.86.5 — è recente
abbastanza da avere funzionalità non presenti quando la nota "nessun
controllo camera/QR ufficiale in Flet" era stata scritta la prima volta):
esiste un pacchetto **ufficiale** del team Flet, `flet-camera` (0.86.5,
powered dal pacchetto Flutter ufficiale `camera`), con anteprima live
E streaming dei fotogrammi (`start_image_stream()`/`on_stream_image`) —
copertura iOS+Android+Web, non desktop. Verificato anche che `pyzbar` (la
libreria di decodifica QR più diffusa in Python) è elencata tra i
pacchetti binari **già pre-compilati per Android/iOS** sull'indice
`pypi.flet.dev` del team Flet (dipendenza nativa `flet-libzbar`) — la
stessa categoria di garanzia che PRIMA non esisteva per `flet_image_picker`
(estensione scritta da zero per questo progetto, due giri di build CI
falliti prima di funzionare). Risultato pratico: **nessun codice Dart/
Flutter nuovo da scrivere né compilare** — l'intera "opzione B" si riduce a
due pacchetti Python ufficiali + un terzo (`flet-permission-handler`,
anch'esso ufficiale) per il permesso fotocamera a runtime, con un rischio
di packaging molto più basso di quanto stimato inizialmente nella domanda
posta a Davide. Riportato a Davide questo cambio di stima prima di
procedere.

**Implementazione.**

`network/qr_join.py` — aggiunta `parse_join_text()`, l'operazione inversa
di `build_join_text()` (già in produzione, generazione lato host):
riconosce il formato testuale del QR (prima riga come "magic" —
`_JOIN_TEXT_MAGIC`, stesso principio difensivo di
`network.protocol.DISCOVERY_MAGIC` per gli annunci broadcast — un QR
inquadrato per sbaglio che non è dei nostri viene scartato subito, non
genera un errore rumoroso), estrae host/porta/codice/PIN con un parser
tollerante agli spazi bianchi finali ma fail-closed su tutto il resto (mai
un dizionario parzialmente valorizzato). Generazione e parsing nello
stesso modulo apposta — un solo posto dove il formato può cambiare.

`ui/views/world/qr_scanner_view.py` (nuovo) — `QrScannerView`: import
protetti (`try/except ImportError`) di `flet_camera`/
`flet_permission_handler`, mai un crash all'avvio se mancano in un
ambiente che non li ha installati. Ciclo: `did_mount()` → richiede il
permesso fotocamera (`PermissionHandler.request(Permission.CAMERA)`,
raccomandato esplicitamente dalla documentazione ufficiale di
`flet-camera` prima di inizializzare il controllo) → enumera le
fotocamere, sceglie la posteriore (`CameraLensDirection.BACK`) → inizializza
con `image_format_group=ImageFormatGroup.JPEG` (stesso parametro
dell'esempio ufficiale) → `start_image_stream()`. Ogni fotogramma
(`on_stream_image`) viene decodificato con `pyzbar` (solo se non è già in
corso una decodifica sul fotogramma precedente — un flag `_decoding`
scarta i fotogrammi in eccesso invece di accumulare lavoro); al primo QR
riconosciuto da `parse_join_text()`, ferma lo stream e richiama
`on_scanned(parsed)` — il chiamante decide cosa farne, questa view non sa
nulla del resto del dialogo. `will_unmount()` ferma sempre lo stream
(`page.run_task`, "fire and forget": non c'è più una page ad attendere una
risposta a quel punto del ciclo di vita) — la fotocamera non deve mai
restare occupata dopo la chiusura della view. `qr_scanner_supported(page)`
— gate di visibilità: solo Android/iOS (`flet-camera` non copre desktop)
E solo se i pacchetti sono davvero importabili.

`ui/views/world/world_view.py::_open_lan_join_dialog` — nuovo pulsante
«Scansiona QR» (mostrato solo se `qr_scanner_supported()`), apre
`QrScannerView` in un dialogo impilato sopra quello «Unisciti in LAN»
(`page.show_dialog`/`pop_dialog` sono nativi di Flet 0.86.5 — verificato
leggendo `flet/controls/base_page.py` prima di assumerne il
comportamento — e supportano più dialoghi impilati, `pop_dialog()` chiude
sempre il più recente ancora aperto). Alla scansione riuscita: chiude lo
scanner, compila i 4 campi (indirizzo/porta/codice/PIN — non il nome del
giocatore, che il QR non porta) e chiama SUBITO `_attempt()`, la stessa
funzione già usata dal pulsante «Entra» — "inquadri e sei dentro", non
"inquadri e poi premi Entra" (richiesta esplicita di Davide).

`pyproject.toml` — aggiunte `flet-camera==0.86.5`,
`flet-permission-handler==0.86.5`, `pyzbar==0.1.9` (`[project.dependencies]`,
NON `[tool.flet.dev_packages]`: sono pacchetti pubblicati normalmente, non
codice locale come `flet-image-picker`). Aggiunto `"camera"` al bundle
cross-platform `permissions` (già usato per `"photo_library"`) — verificato
su `flet.dev/docs/publish/#predefined-cross-platform-permission-bundles`
cosa espande esattamente (`android.permission.CAMERA` +
`NSCameraUsageDescription` iOS/macOS + flag hardware "non obbligatori",
così l'app resta installabile anche su un dispositivo senza fotocamera).
Nessun permesso microfono: la fotocamera si inizializza con
`enable_audio=False`, non registra mai video.

**Test.** Nuovo `test_qr_scan.py` (27/27): round trip
`build_join_text()`↔`parse_join_text()`, tolleranza agli spazi bianchi,
rifiuto di un QR non nostro/incompleto/con porta non valida (fail-closed),
`qr_scanner_supported()` per ogni piattaforma E per pacchetti mancanti
(simulati azzerando temporaneamente i riferimenti al modulo), costruzione
di `QrScannerView` senza eccezioni, `_try_decode()` che non solleva mai
indipendentemente dalla disponibilità di `libzbar` in questo ambiente
(verificato con un controllo esplicito, `_pyzbar_functional()` — stesso
principio di `_broadcast_available()` in `test_scoperta_lan.py`, mai
un'assunzione silenziosa). Rieseguita l'intera batteria del progetto dopo
questa modifica: 939 controlli su 10 file, stessi 2 fallimenti
pre-esistenti e non correlati di sempre (Artefatti DMG in `test_fase_4.py`,
subprocess `flet` mancante in `test_istanze_personaggio.py`), zero
regressioni introdotte.

Corretta anche una dimenticanza trovata per caso mentre si verificava
`page.show_dialog`/`pop_dialog`: la tabella "Stack Tecnico" e la sezione
"Convenzioni di Codice" di `CLAUDE.md` dichiaravano ancora "Flet 0.85.3"
come versione corrente, sei giorni dopo l'aggiornamento reale a 0.86.5
(2026-08-05) — corretto in entrambi i punti. Aggiunta anche
`network/discovery.py` (passo 5, voce precedente) alla mappa "Struttura
File" di `CLAUDE.md`, che non l'aveva mai elencata.

**Non verificabile da questo sandbox** (oltre al solito limite "nessuna
Wi-Fi reale con due dispositivi", §15 del design doc): nessuna fotocamera
reale, nessun toolchain di build Android/iOS, e su questo Linux senza
permessi di root `pyzbar` da PyPI "puro" non trova la libreria di sistema
`libzbar` (irrilevante in pratica: lo scanner è raggiungibile solo su
Android/iOS, dove `flet build` fornisce automaticamente `flet-libzbar`
dall'indice ufficiale — un problema di packaging diverso, già risolto a
monte dal team Flet, non quello che questo sandbox non può verificare).
Il ciclo vero fotocamera→pyzbar→ingresso automatico resta da provare da
Davide su un dispositivo Android/iOS reale, nella stessa build dei passi
5/6.

---

## 2026-08-06 (sessione successiva) — Icona dell'app sostituita col logo D&D ufficiale

Davide ha fornito `Logo_app.png` (alla radice del progetto, fuori da
`dnd_app/`) — il logo ufficiale Dungeons & Dragons di Wizards of the Coast
(wordmark rossa "D&D" col drago), 254×127px, RGBA con sfondo trasparente —
e ha chiesto di sostituire l'icona dell'app, ancora quella di default di
Flet nonostante `pyproject.toml` dichiarasse già `app.icon =
"assets/icons/dnd_logo.png"` (verificato aprendo l'icona 1024×1024 dentro
`dnd_app/build/flutter/ios/.../Icon-App-1024x1024@1x.png` di una build
precedente: era davvero ancora il logo Flet — quella build risale a prima
che `dnd_logo.png`, un placeholder fatto in casa — cerchio rosso/oro con
scritta "D&D" — venisse impostato come icona, o comunque non l'aveva mai
recepito; da verificare con la prossima build se ora la raccoglie).

Segnalato a Davide (nota, non un blocco): quel logo è un marchio
registrato di Wizards of the Coast/Hasbro — per un'app personale come
questa non c'è alcun problema, ma andrebbe considerato se in futuro si
pensasse a una pubblicazione più ampia (Play Store/App Store).

**Problema tecnico**: `Logo_app.png` è rettangolare 2:1, mentre le icone
app richiedono un'immagine quadrata — usato direttamente sarebbe stato
schiacciato o tagliato in modo scorretto dalla pipeline di generazione
icone di `flet build` (`flutter_launcher_icons`, chiamata da `flet_cli`).

**Fix**: rigenerata `dnd_app/assets/icons/dnd_logo.png` (stesso path già
in `pyproject.toml`, nessuna modifica di configurazione necessaria) a
partire da `Logo_app.png` — script Pillow one-off (non salvato nel
repository, operazione di conversione asset una tantum): tela quadrata
1024×1024 bianca (l'alpha viene appiattito: le icone iOS non ammettono
trasparenza, l'App Store le rifiuta), logo ridimensionato mantenendo le
proporzioni e centrato con un margine di sicurezza del 18% per lato —
necessario perché Android ritaglia le icone "adattive" in un cerchio o
squircle: senza margine il bordo della scritta "D&D" verrebbe tagliato dal
ritaglio del sistema operativo. Salvata in RGB (niente canale alpha),
formato PNG, verificata apribile e con le dimensioni attese.

**Limite dichiarato**: la sorgente fornita da Davide è a bassa risoluzione
per un'icona 1024px (254px di partenza, poi ingrandita) — il risultato è
leggibile e pulito alla dimensione delle icone reali (che sono comunque
piccole, 48-180px a seconda della piattaforma) ma leggermente meno nitido
di quanto sarebbe con una sorgente vettoriale o già ad alta risoluzione.

**Non verificabile da questo sandbox**: l'icona vera sui dispositivi/nelle
varie dimensioni per piattaforma si genera solo con un giro reale di `flet
build` (nessun toolchain Flutter/Dart qui) — da controllare da Davide
nella prossima build, insieme al resto già in sospeso (fix EXIF, passi 5/6,
scanner QR).

**Corretto subito dopo, stessa sessione**: Davide ha ripensato al logo
ufficiale ("te ne ho caricato uno non ufficiale usiamo questo") e caricato
`Logo_companion_Dnd.png` (radice del progetto) — un'illustrazione originale
generica a tema fantasy (dado d20, spada, libro con il simbolo "&" del
drago, bussola), NON il marchio Wizards of the Coast: nessuna riserva sul
suo uso. Già quadrata (1254×1254, RGB, senza alpha) e a risoluzione più che
sufficiente — nessuna necessità del trattamento "tela + margine" fatto per
il tentativo precedente (rettangolare, bassa risoluzione). Copiata così
com'è su `dnd_app/assets/icons/dnd_logo.png` (stesso path già in
`pyproject.toml`).

⚠️ Unica particolarità notata: l'immagine ha già angoli arrotondati "cotti"
dentro il file (spazio nero nei quattro angoli fuori dal rettangolo
arrotondato dell'illustrazione) — tipico di chi genera un'immagine già "in
stile icona app". Le pipeline di icone (incluso `flutter_launcher_icons`,
usato da `flet build`) si aspettano normalmente un quadrato pieno bordo a
bordo e applicano da sole l'arrotondamento nativo di ciascuna piattaforma
sopra: con angoli già arrotondati nella sorgente, su piattaforme che
arrotondano di nuovo (es. iOS) c'è un rischio cosmetico minore di un sottile
bordo/angolo scuro visibile per un doppio arrotondamento non perfettamente
allineato. Non corretto in questa sessione (avrebbe richiesto ritagliare/
alterare l'illustrazione scelta da Davide, una decisione estetica sua, non
mia) — solo segnalato: se alla prossima build l'icona reale mostra angoli
poco puliti, la correzione è ritagliare la sola illustrazione interna
(senza gli angoli neri) ed estenderla a un quadrato pieno.

**Aggiornamento 2026-08-06, stessa giornata**: Davide ha ritoccato lui
stesso l'immagine (`Logo_companion_Dnd.png`, root del progetto) risolvendo
esattamente il problema segnalato sopra — niente più angoli smussati
precotti, quadrato 1254×1254 pieno bordo a bordo, verificato visivamente.
Copiata su `dnd_app/assets/icons/dnd_logo.png`, non ancora committata:
in attesa dell'esito del log verboso (`-vv`) della build Android CI
(vedi voce successiva, bug bundle-id/icona ignorati) per includere icona
nuova + eventuale fix nello stesso tag, invece di consumare un'altra
versione per un cambio che rischierebbe comunque di restare "invisibile".

**Bug aperto, stessa giornata — build Android CI ignora `[tool.flet].app`**:
Davide segnala che l'APK scaricato dalla release GitHub `v0.1.31` mostra
ancora l'icona di default di Flet nonostante il commit taggato (`1640abd`)
contenga la configurazione corretta in `pyproject.toml`
(`app.bundle_id`/`app.name`/`app.icon`). Diagnosi con `androguard`
sull'APK caricato da Davide (decodifica `AndroidManifest.xml`): il
pacchetto installato è `com.flet.dnd_companion` (non
`com.davmos9.dndcompanion`) e il nome è `dnd-companion` (non "D&D
Companion") — esattamente lo schema di default che `flet build` genera
**quando non trova affatto una sezione `[tool.flet].app`**, mentre
`versionName` nel manifest è corretto (0.1.31, iniettato correttamente
dallo step "Inject version from git tag"). Verificato che non è un
problema del sorgente: preso il `pyproject.toml` del commit taggato,
applicata la stessa sostituzione regex del workflow, il risultato fa
parsing TOML pulito con `tomli` e produce `tool.flet.app` completo e
corretto — quindi il file che è entrato nella build era valido, il bug è
nella pipeline `flet build apk` del job Android della Action, non nel
progetto. Passo diagnostico in corso: aggiunto `-vv` allo step "Build
Android APK" di `.github/workflows/release.yml` (tag `v0.1.32`, ancora
da esaminare) per capire cosa legge davvero `flet_cli` in quell'ambiente.
Non ancora risolto — vedi "Piano di lavoro attivo" in `CLAUDE.md` per lo
stato corrente prima di riprendere.

**Causa definitiva trovata e corretta, 2026-08-07** — Davide ha segnalato
che anche lo zip Windows (che non passa da `flutter_launcher_icons`/
adattatore Android, un meccanismo completamente diverso da quello Android)
mostrava la stessa icona di default: segnale che il problema non era
specifico di Android ma di come `flet build` legge `pyproject.toml` in
generale, su ogni piattaforma. Installato `flet-cli==0.86.5` in locale e
letto direttamente `flet_cli/commands/build_base.py` (stesso metodo già
usato con successo il 2026-08-06 per il permesso cross-platform) invece di
continuare a ipotizzare:

- `product_name` (riga ~918): `self.options.product_name or
  self.get_pyproject("tool.flet.product") or ...` — legge
  `tool.flet.product`, **non** `tool.flet.app.name`.
- `bundle_id` (riga ~1409): `self.get_pyproject(f"tool.flet.
  {self.config_platform}.bundle_id") or self.get_pyproject("tool.flet.
  bundle_id")` — legge `tool.flet.bundle_id`, **non**
  `tool.flet.app.bundle_id`.
- `build_number` (`commands/build.py` riga 154): legge
  `tool.flet.build_number`, **non** `tool.flet.app.build_number`.
- Icona (`customize_icons()` → `find_platform_image()`, righe ~1792-1926 e
  ~2912-2996): **nessuna chiave pyproject esiste per l'icona**. La funzione
  fa `glob.glob(str(assets_path.joinpath("icon.*")))` — cerca un file
  chiamato letteralmente `icon.<ext>` (png/webp/jpg/...) posizionato
  **direttamente dentro la cartella assets configurata** (default
  `assets/`), MAI in una sottocartella, e MAI leggendo alcun percorso da
  `pyproject.toml`. `assets/icons/dnd_logo.png` (sottocartella + nome
  diverso) non veniva quindi mai trovato, a prescindere da qualsiasi
  configurazione: l'icona restava sempre quella di default incorporata
  in `flutter_launcher_icons`/`flet build`. Supporta anche override per
  piattaforma nella stessa cartella: `icon_android.*`, `icon_ios.*`,
  `icon_web.*`, `icon_windows.*`, `icon_macos.*` (tutti col fallback a
  `icon.*` se assenti) — non necessari qui, un'unica icona per tutte le
  piattaforme come da intento originale del progetto.
- `tool.flet.app.module` (riga 863) è l'UNICA chiave che resta legittimamente
  sotto `app.*`, ma con nome `module` non `module_name` — la vecchia chiave
  `app.module_name` funzionava per puro caso, perché `"main"` è anche il
  default hardcoded quando la chiave non si trova (`... or "main"`), non
  perché venisse davvero letta.
- La versione (`versionName` corretto nel manifest, "0.1.31") non è mai
  passata da questo bug: arriva esclusivamente da `[project].version`
  (nessun riferimento a `tool.flet.version`/`tool.flet.app.version` in
  tutto `flet_cli`), che lo step "Inject version from git tag" del
  workflow aggiorna correttamente indipendentemente da questo problema.

Grep di conferma su `git blame`: le chiavi sbagliate risalgono al primissimo
commit della release workflow (`655b01f`, 2026-06-25) — **non è una
regressione dell'upgrade Flet 0.85.3→0.86.5 del 2026-08-05**, il bug è
sempre stato presente in ogni release CI dal giorno in cui la workflow è
stata creata; semplicemente nessuno aveva mai controllato l'icona/bundle id
da vicino finché Davide non l'ha notato oggi. Controllata la pagina
ufficiale breaking-changes di Flet 0.86.0
(flet.dev/docs/updates/breaking-changes/) per completezza: non documenta
esplicitamente questo spostamento di schema, quindi non c'è modo di sapere
con certezza in quale versione precedente lo schema `app.*` fosse invece
quello corretto (irrilevante in pratica: il progetto è sempre stato
buildato con CI, mai un'installazione locale precedente a verificare).

Fix applicato in `pyproject.toml` (sezione `[tool.flet]`): `app.name` →
`product`, `app.bundle_id` → `bundle_id`, `app.build_number` → `build_number`,
`app.module_name` → `app.module` (unica chiave rimasta sotto `app.*`),
rimossa `app.version` (chiave morta, la versione arriva solo da
`[project].version`) e rimossa `app.icon` (chiave inesistente per
`flet_cli`). File icona spostato da `assets/icons/dnd_logo.png` ad
`assets/icon.png` (root della cartella assets, nome file esatto richiesto)
— verificato con `grep` che `assets/icons/dnd_logo.png` non era referenziato
da nessun codice UI (`home_view.py` ha un commento esplicito: "il PNG in
assets/icons non è mai stato usato", il logo in-app è testo, non
immagine), quindi lo spostamento è sicuro. Verificato che il nuovo
`pyproject.toml` fa parsing TOML pulito con `tomli` e produce i valori
attesi (`product`, `bundle_id`, `build_number`, `app.module` tutti
risolti correttamente).

⚠️ Non ancora verificato con una build CI reale (bloccata nel pomeriggio del
2026-08-06 da un'interruzione infrastrutturale di GitHub Actions, status
page ufficiale — "Incident with Actions", Aug 06 15:22-15:53 UTC) — il
prossimo passo è ripetere la build con `-vv` (già attivo dalla diagnosi
precedente) per confermare che `product_name`/`bundle_id`/icona risultino
ora corretti nei log, poi rimuovere il flag `-vv` una volta confermato.

**Secondo bug trovato dal primo fix, stesso giorno (2026-08-07)** — il tag
`v0.1.33` con il fix sopra ha fatto fallire `build-android` e `build-macos`
(non `build-windows`/`build-linux`). Log reale fornito da Davide:
`ManifestMerger2` → `XmlLoader` → `PositionXmlParser` →
`SAXParserImpl.parse` risale a `org.xml.sax.SAXParseException; lineNumber:
33; columnNumber: 27; The reference to entity "D" must end with the ';'
delimiter.` — un vero errore di parsing XML, non un conflitto di merge
semantico. Causa: `product = "D&D Companion"` (appena reso effettivo dal
primo fix — mai applicato prima d'ora, quindi mai stato visto scorrere in
un file XML) contiene una "e commerciale" grezza; `AndroidManifest.xml`/
`strings.xml` (Android) e `Info.plist` (macOS, anch'esso XML) la
interpretano come inizio di un'entità XML (tipo `&amp;`) e falliscono il
parsing non trovando il `;` di chiusura. Confermato leggendo
`flet_cli/commands/build_base.py`: il valore di `product`/
`project.description` viene inserito nei template di piattaforma con una
sostituzione di stringa semplice (`.replace(...)` puro), senza alcuna
funzione di escape XML nel mezzo — non è quindi un bug risolvibile lato
nostro modificando `flet_cli` (libreria di terze parti, patcharla non
sarebbe manutenibile), e `product_name` non supporta una variante per
piattaforma in `pyproject.toml` (a differenza di `bundle_id`), quindi non
è possibile tenere "D&D Companion" solo su Windows/Linux (dove il
meccanismo non è XML) senza introdurre un nome diverso per piattaforma —
un'opzione scartata: avrebbe richiesto un'altra build di prova solo per
verificare un'assunzione non confermata sui file `.rc`/`.desktop`, e
avrebbe lasciato un'incoerenza di branding tra piattaforme.

Presentate a Davide due alternative (AskUserQuestion): rinominare senza
"&" ovunque (un solo valore, zero rischio residuo, ma nome visualizzato
diverso ovunque) oppure nome diverso per piattaforma (mantiene "D&D
Companion" dove possibile ma più fragile/da verificare). **Scelta di
Davide: rinominare senza "&" ovunque.** Applicato: `product = "D&D
Companion"` → `product = "DnD Companion"`; controllato anche
`[project].description` (stesso meccanismo di inserimento, stessa
vulnerabilità, non ancora incontrata solo perché non ancora arrivata a un
punto della pipeline che la esponesse) → `"D&D 5e Companion App — ..."` →
`"DnD 5e Companion App — ..."`. Nessun altro `&` rimasto in valori di
`pyproject.toml` (verificato con grep + parsing `tomli`). Il testo "D&D"
nell'interfaccia dell'app stessa (es. `home_view.py`, che mostra il nome
come `ft.Text`, non tramite un template XML di build) resta invariato:
non passa dalla stessa pipeline, non c'è alcun rischio lì.

**Confermato da Davide su build CI reale (2026-08-07, tag v0.1.34):
icona giusta visualizzata.** Rimosso il flag diagnostico `-vv` dallo step
"Build Android APK" del workflow, non più necessario. Bug chiuso: nome
prodotto/bundle id/build number/icona ora tutti applicati correttamente
su tutte e 4 le piattaforme (Windows/macOS/Linux/Android), come da schema
corretto di `flet_cli` 0.86.5 documentato nella voce precedente.

---

## 2026-08-07 — Passo 6: la UI mancante (abilità/incantesimo bonus/diario/richiesta di modifica §7.1) + bug di correttezza trovato e corretto

Davide ha confermato l'hosting LAN funzionante su rete reale e ha chiesto di
proseguire con i prossimi passi. Come da "Piano di lavoro attivo" di
`CLAUDE.md`, il pezzo rimasto aperto del passo 6 non era design né backend
(handler e permessi già testati il 2026-08-06) ma solo la UI mancante in
`ui/views/world/world_view.py`, sezione "Interviene a distanza" — costruita
qui, senza ridiscutere `multiplayer_design.md` §7/§7.1.

**Concedi abilità speciale / incantesimo bonus / voce di diario.** Tre nuove
pill sulla riga di ogni personaggio (master/owner), ciascuna con un dialog
dedicato che invia `custom_ability.grant`/`bonus_spell.grant`/
`diary.add_entry` via `self.backend.send_command()` (mai una scrittura
diretta). Il dialog dell'incantesimo bonus riusa esattamente il picker a due
livelli (classe → `CardPicker` sugli incantesimi reali del JSON via
`spell_card_options`) già in `spells_view.py::_open_add_bonus_spell_dialog`
per il caso locale — stesso principio "mai un nome di incantesimo scritto a
mano", qui applicato al caso remoto.

**Proponi modifica (§7.1), lato master.** Nuova pill "Proponi modifica" →
dialog con una riga per campo proponibile
(`perm.CHANGE_REQUEST_ALLOWED_FIELDS`, iterato in un ordine esplicito e non
sul `frozenset` direttamente — l'iterazione su un frozenset di stringhe non
è stabile tra un avvio e l'altro per via dell'hash randomization di Python,
avrebbe dato un ordine dei campi diverso ad ogni riavvio dell'app):
caratteristiche e livello con un campo numerico, le 5 scelte di classe
(stile di combattimento/totem/terreno/patto/discendenza draconica) con un
Dropdown sulle opzioni PHB reali lette da `GameDataLoader` — e, come in
`profilo_tab.py::_open_class_choices_edit`, una scelta di classe compare
nel dialog solo se il personaggio la ha già fatta (non si propone di
cambiare uno stile di combattimento mai scelto). Un checkbox per riga
seleziona quali campi includere nella proposta; il master può proporre più
campi in una sola richiesta. Motivazione obbligatoria (l'handler la
richiede già, validata qui anche lato client per un errore immediato).
Invia `change_request.propose`.

**Richieste in sospeso, lato giocatore — il pezzo che mancava davvero.**
Nessuna UI esisteva per `change_request.respond`: nuova sezione "Richieste
in sospeso" in `_render_detail`, visibile a **qualsiasi** membro del mondo
(non gated dietro `can_perform(..., CMD_XP_GRANT)` come le altre sezioni
master, perché qui il ruolo minimo è `player` — chiunque deve poter
rispondere sulla propria istanza). Filtra `world_repo.
get_pending_change_requests(world.id)` sulle sole richieste il cui
`character_id` appartiene a un personaggio con `owner_device_id ==
self.device_id`: un filtro di presentazione, non di sicurezza — l'unico
controllo che conta resta `perm.is_character_owner()` dentro l'handler.
Mostra motivazione e diff "campo: attuale → proposto" per ogni campo della
richiesta, con due pill Accetta/Rifiuta che inviano
`change_request.respond`. Soddisfa "se il giocatore è scollegato la trova
al rientro" (design doc, §7.1): la sezione si ricostruisce da DB ad ogni
apertura della Sezione Mondi, nessuno stato in memoria.

**Bug di correttezza trovato costruendo questa UI, corretto in
`core/world_backend.py`.** `_handle_change_request_respond` applicava
caratteristiche come DES/COS/SAG con un semplice `setattr` + `character_repo
.update()`, ma non richiamava mai `calculate_and_update_ca()` — a
differenza di OGNI altro punto dell'app che tocca queste caratteristiche
(`profilo_tab.py`, righe 1326 e 3968: cambiare stile di combattimento o
scelte di classe ricalcola sempre la CA subito dopo). La CA dipende da DES
sempre (10 + mod DES senza armatura, o con armatura leggera/media), e da
COS/SAG per le Difese Senza Armatura di Barbaro/Monaco — quindi una
richiesta di modifica accettata su una di queste tre caratteristiche
lasciava la CA visualizzata stantia finché qualcos'altro non la
ricalcolava (es. equipaggiare/disequipaggiare un'arma). Il bug esisteva già
nell'handler del 2026-08-06 ma era invisibile: nessuna UI lo esercitava
davvero prima d'ora, e l'unico test esistente (`test_change_request_
propose_and_respond` in `test_master_remote_actions.py`) usa `str_score`,
che non influenza la CA. Fix: se `changes` contiene `dex_score`,
`con_score` o `wis_score`, richiama `character_repo.calculate_and_update_ca
(character.id)` subito dopo l'update — stesso pattern già validato altrove,
nessun rischio di regressione.

**Test.** Nuovo `test_change_request_dex_recalculates_ca()` in
`test_master_remote_actions.py` (world con personaggio DES 12 → CA di base
11 verificata con `calculate_and_update_ca()` esplicito → proposta e
accettazione di DES 12→18 → CA verificata a 14): la suite passa 81/81
(era 75/75 prima di questa sessione). Nessuna regressione nelle suite
correlate: `test_mondo_senza_rete.py` 151/151 (incluso [8], la
costruzione/rendering di `WorldsView` con le nuove pill), `test_istanze_
personaggio.py` 62/62, `test_lan_host_client.py` 92/92, `test_master_world_
scoping.py` 25/25. Verificato anche l'import reale del modulo (`flet`
installato ad hoc in questo sandbox, non presente di default) per
escludere errori a runtime non rilevabili dalla sola analisi sintattica.

⚠️ **Non verificabile da questo sandbox**: la resa visiva dei nuovi dialog
(in particolare quello di "Proponi modifica", il più denso di controlli) su
schermo piccolo/tema scuro — stesso tipo di verifica che solo Davide può
fare su dispositivo reale, come già per il resto del restyle.

Aggiornata la tabella del passo 6 in "Piano di lavoro attivo" di
`CLAUDE.md`: passo 6 ora interamente chiuso (handler, permessi, UI, test).

---

## 2026-08-07 (sessione successiva) — Bug architetturale reale: WorldsView non parlava mai in rete dopo l'ingresso, più sincronizzazione automatica in background

Davide ha confermato l'hosting su Wi-Fi reale e ha chiesto cosa testare di
preciso. Rispondendo a quella domanda (non durante lo sviluppo della UI del
passo 6) è emerso un bug pre-esistente serio, mai esercitato da nessun
test: `ui/views/world/world_view.py::WorldsView` istanziava `self.backend =
LocalBackend()` una volta in `__init__` e non lo cambiava MAI, nemmeno dopo
che il dispositivo si univa a un mondo in LAN. Conseguenza: ogni comando
inviato da un dispositivo che NON è l'host (rinomina mondo, gestione
membri, e tutte le azioni di "Interviene a distanza" introdotte il
2026-08-06/07: PE/danno/cura/condizioni/abilità/incantesimo/diario/
richiesta di modifica) scriveva solo sulla replica locale di quel
dispositivo — "riusciva" a schermo, nessun errore, ma non lasciava mai il
dispositivo. Il `RemoteBackend` restituito da `world_sync.start_lan_join()`
al termine dell'ingresso veniva usato solo per il minuto dell'handshake
(`LanJoinResult.backend`), poi scartato — mai assegnato a `self.backend`.
Verificato con `grep` che nessun test esistente istanzia `WorldsView` con
un mondo `is_local_host=False`: il gap era invisibile a tutta la
suite esistente.

Un secondo gap collegato, trovato subito dopo: `core.world_sync.
sync_replica()` — la funzione che scarica dall'host gli eventi nuovi e li
applica alla replica — non era mai chiamata da nessuna parte nella UI, solo
dai test. Anche sistemando l'invio dei comandi, un giocatore che si univa
in LAN avrebbe visto solo l'istantanea del momento dell'ingresso: qualsiasi
cosa il master avesse fatto dopo non sarebbe mai arrivata sul suo
dispositivo senza un modo per "tirare giù" gli eventi nuovi.

Davide ha scelto esplicitamente la sincronizzazione automatica in
background invece di un pulsante manuale ("l'utente deve fare il meno
possibile... la parte tecnica la deve gestire in automatico l'app"), sia
per gli arrivi (richieste di modifica, concessioni del master) sia per le
risposte del giocatore che il master deve vedere.

**Persistenza del token di sessione.** `RemoteBackend.token` viveva solo in
memoria, perso ad ogni chiusura/riapertura della sezione Mondi — nessun
modo di ricostruire una connessione funzionante senza rifare l'intero
ingresso con codice+PIN (che cambia ad ogni riavvio dell'hosting, §9.4).
Nuova colonna `worlds.session_token` (`data/database.py`, sia nel
`CREATE TABLE` per le installazioni nuove sia con `_add_column()`
idempotente per quelle esistenti — significativa solo lato replica,
`is_local_host=0`), nuovo campo `World.session_token` (`data/models.py`),
letto/scritto in `data/repositories/world_repo.py`
(`_row_to_world`/`save_replica_world`). `core/world_sync.py::_finalize_join`
ora valorizza `session_token=backend.token` quando costruisce la replica
locale del mondo — lo stesso identico punto che già scriveva
`last_seen_host` per lo stesso scopo (riconnessione).

**Routing dei comandi per mondo, non più fisso sulla view.** Nuovo
`WorldsView._backend_for(world) -> WorldBackend | None`: `LocalBackend` se
`world.is_local_host`, altrimenti un `RemoteBackend` riconnesso con
`reconnect_with_token(world.session_token)` (mai una nuova `join()`
automatica: richiederebbe codice+PIN, che l'app non può indovinare da
sola — se il token non è più valido, l'host è stato riavviato e l'utente
deve rientrare a mano da "Unisciti in LAN", come da §9.4, "mai un
ritentativo automatico con credenziali scadute"). Cache per mondo
(`self._remote_backends: dict[str, RemoteBackend]`), riusata finché
`connection_state() == "connected"`. Nuovo `_send_command(world, kind,
payload, ...)` sostituisce OGNI chiamata diretta a
`self.backend.send_command(...)` nella view (7 punti: rinomina mondo,
rigenera codice, promuovi/retrocedi/espelli membro, elimina mondo, e il
punto condiviso da tutti i dialoghi di "Interviene a distanza" più
"Richieste in sospeso" tramite gli helper già esistenti
`_send_remote_command`/`_respond_change_request`).

**Applicazione immediata del proprio comando.** Dopo un `_send_command`
riuscito su un `RemoteBackend`, `_apply_own_remote_result()` richiama
subito `world_sync.sync_replica()` mirata invece di aspettare il prossimo
giro del thread in background — chi ha appena premuto un pulsante vede
l'effetto senza ritardo percepibile, anche se il giro periodico lo
riapplicherebbe comunque pochi istanti dopo (idempotente, nessun doppio
effetto: stessa garanzia già di `sync_replica()`).

**Sincronizzazione automatica in background.** Un thread per la scheda
mondo aperta (`_start_detail_sync`/`_stop_detail_sync`/
`_detail_sync_loop`, avviato in `_open_detail`, fermato in `_back_to_list`
e `will_unmount`): lato client richiama `sync_replica()` ogni
`_DETAIL_SYNC_INTERVAL_S` (2 s) — `RemoteBackend.fetch_events()` interroga
apposta SENZA attesa lunga (`wait=0`, per scelta di design già presente
prima di questa sessione: "la sincronizzazione periodica vera e propria
decide essa stessa quanto aspettare"), quindi il ritmo lo impone questo
ciclo; lato host non c'è nulla da scaricare (il DB locale È già lo stato
autoritativo, aggiornato all'istante da ogni comando ricevuto, anche da un
altro dispositivo) — solo una rilettura periodica per riflettere sullo
schermo ciò che è già vero nel DB. In entrambi i casi ridisegna SOLO se una
firma di stato calcolata da `_detail_signature_of()` (ultimo `seq` del
giornale + membri + richieste di modifica in sospeso) è cambiata — stesso
principio già in uso in `home_view.py::refresh(force=False)`, per non
interrompere una digitazione in corso (es. nel campo "Nome del mondo") con
un rebuild che la sostituirebbe di netto. `self._render_lock`
(`threading.Lock`) protegge la mutazione di `self._body.controls`,
condivisa tra il thread Flet e il thread di sync — stesso principio già in
uso in `home_view.py::_refresh_lock`. Nessuna dipendenza nuova: solo
`threading` di libreria standard, stesso pattern già in produzione per il
polling web multi-sessione di `home_view.py`.

**Codice morto rimosso**: `world_repo.update_session_token()`, scritta in
un primo momento pensando a un caso — un `join()` che rientra con un token
NUOVO — che in pratica non ha mai un chiamante automatico (l'unico punto
che ottiene un token nuovo, `_finalize_join()`, lo persiste già per intero
tramite `save_replica_world()`). Rimossa prima di lasciarla come codice
morto mai richiamato.

**Test.** Nuovo `test_world_view_remote_routing.py` (16/16) — con un vero
`WorldHostServer` su socket reale (stesso pattern di
`test_lan_host_client.py` parte [1], stessa limitazione dichiarata lì:
un vero test a due database SEPARATI non è simulabile in modo affidabile
in questo sandbox, `get_connection()` legge `Path.home()` ad ogni chiamata
e un secondo HOME introdurrebbe una corsa reale col thread del server):
verifica che `_backend_for()` risolva un `RemoteBackend` connesso per un
mondo non ospitato e lo riusi dalla cache, che `_send_command()` applichi
DAVVERO l'effetto sul DB che l'host usa (non su una copia locale) tramite
un comando `xp.grant` inviato via socket reale, che un comando non
autorizzato venga rifiutato dall'host stesso (non "riesca in locale"), che
un token non valido o un host irraggiungibile facciano fallire
`_backend_for()` in modo esplicito (mai un ritentativo automatico), che un
mondo ospitato da questo dispositivo continui a usare `LocalBackend`, e che
`_detail_signature_of()` cambi quando cambia davvero lo stato del mondo
(nuovo membro, nuovo evento) e resti stabile altrimenti. Nessuna
regressione nelle suite esistenti: `test_master_remote_actions.py` 81/81,
`test_mondo_senza_rete.py` 151/151, `test_istanze_personaggio.py` 62/62,
`test_lan_host_client.py` 92/92, `test_master_world_scoping.py` 25/25,
`test_scoperta_lan.py` 25/25, `test_fase_d.py` 101/101,
`test_regressione_wrap_expand.py` 85/85. Due fallimenti preesistenti in
`test_qr_scan.py`/`test_fase_4.py`, indipendenti da questa sessione:
dichiarano loro stessi di saltare la verifica reale perché i pacchetti
`flet-camera`/`pyzbar`/`libzbar` non sono installati in questo sandbox.

⚠️ **Resta da verificare solo su hardware reale** (due dispositivi fisici
distinti, §15 del design doc): che il thread di sync in background non
abbia un impatto percepibile sulla batteria/reattività dell'app su un
telefono reale nell'arco di un'intera sessione di gioco — un tipo di
verifica che nessun test automatico di questo sandbox può dare.

---

## 2026-08-07 (sessione successiva) — 4 bug reali dal primo vero test su Wi-Fi di Davide

Davide ha testato il passo 5/6 su due dispositivi fisici reali per la prima
volta ("riesco a scannerizzare gli host attivi, riesco a entrare con QR
code, riesco ad unirmi ad un mondo") e ha segnalato 4 problemi in un solo
messaggio. Tutti e 4 confermati e corretti in questa sessione.

**1. "Le richieste e le accettazioni non escono in automatico, ma bisogna
premere il pulsante di refresh."** Causa reale: il thread di sync in
background introdotto nella sessione precedente (`_detail_sync_loop`)
chiamava `self._render()` + `self.page.update()` **direttamente da un
thread `threading.Thread` qualunque** — copiato dal pattern già in uso in
`home_view.py::_poll_loop`, ma quel pattern è scoperto esplicitamente per
il SOLO caso web multi-sessione (`page.web`), mai per desktop/mobile.
Verificato leggendo il sorgente di Flet (`flet/controls/page.py`,
`flet/messaging/session.py`): `Page.run_task(handler, *args, **kwargs)` è
l'UNICA via ufficialmente thread-safe per programmare lavoro sulla UI da
un thread che non è quello del proprio event loop — usa internamente
`asyncio.run_coroutine_threadsafe(handler(...), self.session.connection.loop)`.
Una chiamata diretta a `page.update()` da un thread arbitrario "sembra"
funzionare nella build via socket di questo sandbox ma non è garantita sul
bridge Dart reale di un'app nativa — coerente col sintomo di Davide
(nessun errore, semplicemente "non succede niente" finché non si forza un
redraw sincrono col refresh manuale). **Fix**: `_maybe_redraw_detail()`
ora chiama solo `page.run_task(self._async_redraw_detail, world_id)`
invece di ridisegnare da sé; `_async_redraw_detail()` (nuova coroutine)
fa il controllo "sono ancora sulla scheda di questo mondo?" e ridisegna
dentro l'event loop di Flet, l'unico posto sicuro.

**2. "Non voglio permettere all'utente di spammare richieste, quindi
mettere un timer di 10 secondi alla richiesta successiva."** Chiarito lo
scope con una domanda: "Tutte le azioni di 'Interviene a distanza'" — PE,
danno, cura, condizione, abilità, incantesimo bonus, diario, proponi
modifica, TUTTE funnelate già da `_send_remote_command()` (punto unico,
verificato leggendo ogni `_open_*_dialog` di quella sezione: nessuna
scorciatoia che bypassa quel metodo). Aggiunto `_REMOTE_ACTION_COOLDOWN_S
= 10.0` e `self._last_remote_action_at` (`time.monotonic()`, non
`datetime.now()`: insensibile a un eventuale cambio dell'orologio di
sistema durante la sessione) — un solo timer globale sulla sezione, non
uno per tipo di azione né per personaggio, coerente con la risposta di
Davide. L'istante si registra SUBITO all'invio, PRIMA di conoscere
l'esito: anche un comando fallito ha già generato traffico verso l'host,
quindi non è aggirabile martellando durante un errore. Deliberatamente
NON applicato a `_send_command()` in generale (rinomina mondo, gestione
membri, risposta del giocatore a una richiesta di modifica): fuori dallo
scope indicato da Davide.

**3. "Mettere obbligatorio il nome prima di entrare in un mondo."** Prima,
sia "Unisciti a un mondo" (`_open_join_dialog`, caso web multi-sessione)
sia "Unisciti in LAN" (`_open_lan_join_dialog`, incluso l'ingresso via
QR — `_on_qr_scanned` richiama la stessa `_attempt()`) facevano cadere un
nome vuoto su `"Giocatore"` in silenzio: nel Registro/Sezione Master
diventava impossibile distinguere due giocatori entrambi senza nome.
Aggiunta una validazione esplicita in entrambi i punti (stesso stile già
in uso per "Il nome del mondo è obbligatorio" nella creazione di un
mondo): campo vuoto → `_show_error`/messaggio nel dialogo, nessun ripiego
silenzioso. La creazione di un mondo (`_open_create_dialog`, dove sei tu
l'owner) resta con il ripiego `"Master"` — fuori scope, Davide ha parlato
di "entrare", non di "creare".

**4. "Una volta entrato il player può far unire il personaggio al mondo...
ma il master non vede il personaggio... nella Sezione Master... non gli
esce il personaggio giocante."** Il bug più importante dei 4 — causa
architetturale, non un dettaglio di UI: `core/character_instances.py::
create_or_resume_instance()` è nata al passo 3 (2026-08-05), **prima che
esistesse la rete** — scrive SOLO sul DB del dispositivo che la chiama. Su
un dispositivo che ha solo una REPLICA del mondo (join in LAN, non lo
ospita), la riga `characters` restava solo lì: l'host — il DB che la
Sezione Master legge davvero — non ne sapeva nulla. Nessuna regressione
di questa sessione: il gap era dichiarato onestamente nel commento
originale di quella funzione ("Nessuna rete in questo passo"), mai
richiuso quando è arrivata la rete al passo 4.

**Fix**: nuovo comando `character_instance.sync`
(`core/world_permissions.py::CMD_CHARACTER_INSTANCE_SYNC`, ruolo minimo
`player`, aggiunto anche a `CHARACTER_MUTATING_COMMANDS` così un TERZO
dispositivo — es. un co-master su un telefono diverso dall'host — lo
rimaterializza automaticamente tramite il meccanismo già esistente
`core.world_sync._resync_character_from_host()`, nessuna logica nuova lì).
Handler `core/world_backend.py::_handle_character_instance_sync`: a
differenza di ogni altro handler della sezione "Interventi del master",
qui NON si passa da `_resolve_world_character()` (presuppone che l'host
conosca già il personaggio — qui può essere la primissima volta), la
proprietà si verifica sul payload esportato (`owner_device_id`) contro
l'autore del comando; riusa `character_export.import_replica_character()`
— stesso modulo già collaudato per la semina iniziale e per ogni
rimaterializzazione via eventi, nessuna logica di scrittura delle 12
tabelle figlio duplicata. Lato chiamante:
`ui/views/home_view.py::HomeView._push_instance_to_host()`, richiamata
subito dopo `create_or_resume_instance()` in `_open_add_to_world_dialog`:
se il dispositivo ospita già il mondo non fa nulla (la riga è già
autoritativa); altrimenti risolve il backend giusto ed invia l'export
integrale appena creato. Un fallimento del push (host momentaneamente
irraggiungibile) non annulla la creazione locale già riuscita — mostra un
avviso non bloccante invece di un errore duro, l'utente vede comunque il
proprio personaggio.

**Refactor collaterale, non richiesto ma necessario**: la logica di
`WorldsView._backend_for()` (risolvi `LocalBackend` se ospiti tu, altrimenti
un `RemoteBackend` via `session_token`) serviva identica anche a
`HomeView` per il push — estratta in
`core/world_sync.py::resolve_backend_for_world()` invece di duplicarla
(stesso principio già seguito nel resto del progetto: un solo punto di
verità). `WorldsView._backend_for()` è ora un sottile adattatore su quella
funzione condivisa.

**Nota sullo scope, da comunicare esplicitamente**: il fix del punto 4
copre SOLO la registrazione iniziale (creazione/ripresa di un'istanza).
NON risolve la sincronizzazione bidirezionale continua delle modifiche
successive fatte in locale da un giocatore (level-up, equipaggiamento,
ecc.) verso l'host — quella resta il passo 7 "Condivisione"/«aggiorna il
mio foglio» del piano (`multiplayer_design.md` §13), non ancora iniziato,
volutamente non ampliato in questa sessione senza che Davide lo chiedesse.

**Test.** Tre nuovi file, nessuna regressione nelle suite esistenti:
- `test_character_instance_sync.py` (13/13) — con un vero `WorldHostServer`
  su socket reale: riproduce il bug (istanza creata su un client LAN non
  esiste sull'host finché non viene inviata), verifica che
  `HomeView._push_instance_to_host()` la registri DAVVERO sul DB che
  l'host userebbe per rispondere alla Sezione Master, fail-closed su
  proprietario sbagliato e su mondo sbagliato, nessun push quando il
  dispositivo ospita già il mondo.
- `test_cooldown_azioni_remote.py` (13/13) — la primissima azione non è
  mai bloccata, una seconda entro 10s viene rifiutata SENZA toccare il
  personaggio, il timer si aggiorna anche su un comando fallito, l'azione
  successiva riesce di nuovo dopo la finestra, `_send_command()` generico
  non è soggetto al timer.
- Validazione nome obbligatorio verificata manualmente (nessun test
  automatico dedicato: stessa natura di ogni altro controllo `_show_error`
  su un campo vuoto già presente in questa view, coperti collettivamente
  dal fatto che l'intera suite `test_mondo_senza_rete.py` continua a
  costruire/renderizzare la view senza eccezioni).

Nessuna regressione: `test_mondo_senza_rete.py` 151/151,
`test_master_remote_actions.py` 81/81, `test_world_view_remote_routing.py`
16/16, `test_master_world_scoping.py` 25/25,
`test_regressione_wrap_expand.py` 85/85, `test_istanze_personaggio.py`
62/62, `test_lan_host_client.py` 92/92. Stessi due fallimenti preesistenti
e indipendenti da questa sessione (`test_fase_4.py`: nota sui dati degli
artefatti DMG, `test_qr_scan.py`: `pyzbar` non installato in questo
sandbox) — invariati rispetto a prima di questa sessione, non causati né
toccati da nessuno di questi 4 fix.

⚠️ **Resta da verificare da Davide su Wi-Fi reale**: proprio i 4 punti
sopra, in particolare il punto 1 (l'aggiornamento live funziona davvero
sul bridge Dart nativo, non solo nella logica testata qui?) e il punto 4
(il personaggio del giocatore compare davvero nella Sezione Master
dell'altro dispositivo?) — nessun test di questo sandbox può sostituire
quella prova, per lo stesso motivo già dichiarato per ogni sessione
precedente di questo modulo (§15 del design doc, DB separati non
simulabili in modo affidabile qui).

---

## 2026-08-07 (sessione successiva) — Timer anti-spam differenziati: 3s per il master, 10s per ingresso/sincronizzazione

Messaggio di Davide subito dopo il fix precedente: "il timer anti spam
intendo che deve essere attivo su tutte le richieste anche quelle per
cercare di unirsi, e tutte le richieste online da sincronizzare, per il
master facciamo un timer di 3 secondi meno stringente". Due correzioni
rispetto alla sessione precedente:

1. **Il timer di "Interviene a distanza" scende da 10s a 3s** (Davide:
   "meno stringente") — un master che gestisce un combattimento reale
   agisce più di frequente di un giocatore che tenta di entrare in un
   mondo, quindi merita un limite più permissivo. Rinominata la costante
   `_REMOTE_ACTION_COOLDOWN_S` → `_MASTER_ACTION_COOLDOWN_S = 3.0` in
   `ui/views/world/world_view.py` per chiarezza (il nome vecchio non
   distingueva più questo timer dal nuovo, introdotto nello stesso commit).

2. **Nuovo timer separato di 10s su "tutte le richieste anche quelle per
   cercare di unirsi, e tutte le richieste online da sincronizzare"**:
   - `_open_join_dialog._join` (ingresso per codice — anche nel caso web
     multi-sessione, stesso DB);
   - `_open_lan_join_dialog._attempt` (ingresso in LAN — richiamato anche
     da `_on_qr_scanned` dopo una scansione QR riuscita, stesso cancello
     quindi protegge anche quel percorso);
   - `_open_lan_join_dialog._retry` (interroga `finish_pending_join()` per
     sapere se il master ha approvato — letteralmente una "richiesta di
     sincronizzazione" dello stato di un ingresso in sospeso);
   - `ui/views/home_view.py::HomeView._push_instance_to_host()` (invia
     l'export del personaggio appena creato — comando chiamato
     letteralmente `character_instance.sync`).

   Costante condivisa `core.world_sync.NETWORK_REQUEST_COOLDOWN_S = 10.0`
   (non duplicata in ogni file: stesso principio già seguito con
   `resolve_backend_for_world()` nella sessione precedente) + funzione
   pura `core.world_sync.cooldown_remaining(last_at, cooldown_s) -> float`,
   usata sia dal nuovo timer di rete sia (dopo il refactor) dal timer del
   master — un solo modo di calcolare "quanto manca", non due copie della
   stessa aritmetica `time.monotonic() - last_at`.

   Stato: **due tracciati indipendenti**, non uno condiviso con quello del
   master. Su `WorldsView`, `_join`/`_attempt`/`_retry` condividono LO
   STESSO `self._last_network_request_at` (un tentativo di ingresso per
   codice blocca per 10s anche un tentativo in LAN subito dopo, e
   viceversa — "tutte le richieste", non una lista di eccezioni). Su
   `HomeView`, `_push_instance_to_host()` ha il proprio
   `self._last_instance_push_at`, separato: sono due classi/istanze
   diverse con cicli di vita diversi, non ha senso che l'una blocchi
   l'altra.

   **Deliberatamente escluso**: "Cerca reti nelle vicinanze"
   (`_search_nearby`, `network/discovery.py::discover_worlds()` — un
   broadcast UDP locale, non una richiesta autenticata verso un host
   specifico). Motivo: condividere lo stesso timer di `_attempt` avrebbe
   rotto il flusso normale "cerco una rete → clicco Usa → Entra", che
   capita quasi sempre a pochi secondi di distanza — non è lo scenario di
   spam che Davide vuole prevenire. Se in futuro serve un limite anche
   lì, va aggiunto come categoria a sé (terzo tracciato indipendente), non
   riusando questo. Decisione presa senza chiedere conferma esplicita a
   Davide (il messaggio nominava solo "ingresso" e "sincronizzazione"),
   segnalata qui e nella risposta in chat per poter essere corretta se non
   è quello che intendeva.

   **Stessa policy del timer del master**: l'istante si registra SUBITO
   all'invio, prima di conoscere l'esito — anche un tentativo fallito ha
   già generato traffico verso l'host, non è aggirabile martellando
   durante un errore.

**Test.** `test_cooldown_azioni_remote.py` riscritto (22/22, era 13/13):
verifica sia il timer del master a 3s (stesso comportamento di prima, solo
il valore è cambiato) sia il nuovo timer di rete a 10s — condiviso tra
`_join`/`_attempt`/`_retry` sulla stessa `WorldsView`, stato indipendente
su `HomeView`, e che `_push_instance_to_host()` REALE (non una replica
della sua logica) si fermi davvero al cancello anti-spam prima di provare
a risolvere un backend. Aggiornato anche `test_character_instance_sync.py`
(13/13 invariato): le due istanze di `HomeView.__new__(HomeView)` lì
dentro non passano da `__init__` (bypassato apposta per non aver bisogno
di `ft.Page` in un test), quindi non avevano mai `_last_instance_push_at`
— la nuova riga del cooldown lo leggeva e falliva con `AttributeError`
finché non è stato inizializzato anche lì (bug del test, non del codice:
`HomeView()` costruita normalmente altrove nella suite non ne risente).
Nessuna regressione sulle suite esistenti: `test_mondo_senza_rete.py`
151/151, `test_master_remote_actions.py` 81/81,
`test_world_view_remote_routing.py` 16/16, `test_master_world_scoping.py`
25/25, `test_regressione_wrap_expand.py` 85/85,
`test_istanze_personaggio.py` 62/62, `test_lan_host_client.py` 92/92,
`test_scoperta_lan.py` 25/25, `test_fase_d.py` 101/101. Stessi due
fallimenti preesistenti e indipendenti (`test_fase_4.py`, `test_qr_scan.py`
— vedi sopra).

---

## 2026-08-07 (sessione successiva) — Revisione dei timer anti-spam: stato di modulo, per-personaggio, difesa in profondità lato host, countdown visivo

Davide, dopo il fix precedente: "a te come sembra questa gestione del
timer? proponi qualche modifica?" — non una richiesta di funzionalità, un
invito a un'autovalutazione. La rilettura del codice ha trovato un bug
reale (non solo margini di miglioramento):

**Bug trovato: lo stato del timer si azzerava ad ogni ricreazione della
view.** `ui/app.py::_show_worlds_view()`/`_show_home()` costruiscono
un'istanza NUOVA di `WorldsView`/`HomeView` a ogni navigazione E a ogni
cambio tema (`_rebuild_route` passa da lì anche per quello) — i timer
della sessione precedente (`self._last_remote_action_at`,
`self._last_network_request_at`, `self._last_instance_push_at`) vivevano
come attributi di ISTANZA, quindi si azzeravano ogni volta. Il limite era
aggirabile semplicemente navigando avanti e indietro tra Home e Sezione
Mondi, o cambiando tema — senza che l'utente dovesse nemmeno volerlo.

Proposte tre modifiche a Davide via scelta multipla, tutte e tre accettate
(opzioni consigliate):

1. **"Sì, anche sull'host"** — difesa in profondità. Fino a questa
   revisione il limite viveva SOLO lato client (`WorldsView`/`HomeView`):
   un client modificato (o un bug futuro in un punto della UI che non
   passa da questi metodi) poteva aggirarlo del tutto. Ora
   `core.world_backend.LocalBackend.send_command()` — il choke point
   unico sia per un comando locale sia per uno arrivato via rete su un
   mondo ospitato da questo dispositivo — applica lo STESSO limite prima
   di raggiungere l'handler: 3s per `MASTER_REMOTE_ACTION_COMMANDS` (per
   `(actor_device_id, target_id)`), 10s per `CMD_CHARACTER_INSTANCE_SYNC`
   (per `actor_device_id`). Deliberatamente NON esteso a
   `network/host_server.py::WorldHostServer.handle_join()` in questa
   sessione (avrebbe richiesto uno stato scoped per istanza del server e
   la gestione di collisioni nei test che fanno più `handle_join()`
   ravvicinati sullo stesso `device_id` in `test_lan_host_client.py`) —
   la protezione lato host oggi copre l'endpoint `/command`, non ancora
   `/join`. Segnalato esplicitamente: se serve anche lì, è lavoro a sé.

2. **"Per personaggio"** — il timer del master (3s) non è più un
   cronometro unico su tutta la sezione "Interviene a distanza": un'AoE
   che colpisce 4 PG non costringe più il master ad aspettare 3s tra un
   personaggio e l'altro. Chiave `character_id` lato client
   (`dict[str, float]` in `core.world_sync`), `(actor_device_id,
   target_id)` lato host (anche per-dispositivo: un co-master su un altro
   telefono non condivide il limite col master principale).

3. **"Sì, aggiungi il countdown"** — i pulsanti mostrano ora il tempo
   rimanente e si disabilitano da soli, invece del solo messaggio
   reattivo al click. Sulle pillole di "Interviene a distanza"
   (`_remote_character_row` in `ui/views/world/world_view.py`): sfrutta
   il thread di sincronizzazione in background già esistente (nessun
   timer nuovo) tramite la nuova `_any_master_cooldown_active()`, che fa
   scattare un ridisegno periodico finché almeno un personaggio visibile
   è in cooldown. Sui pulsanti "Unisciti"/"Entra"/"Controlla di nuovo"
   dei dialoghi di ingresso: nuovo ciclo `async`
   (`_start_network_cooldown_ticker`/`_network_cooldown_ticker_loop`,
   schedulato con `page.run_task()`, mai un `threading.Thread` — si è già
   nel loop asyncio della sessione) che si ferma da solo quando il
   cooldown scade o quando `page.update()` fallisce (dialogo chiuso) —
   deliberatamente NON basato sulla lettura di `dlg.open` per rilevare la
   chiusura del dialogo, perché `dnd_app/docs/regole_flet_api.md`
   documenta che quel flag non è affidabile in questa versione di Flet
   (le uniche API corrette sono `page.show_dialog()`/`page.pop_dialog()`).

**Refactor architetturale conseguente.** Le costanti e l'aritmetica pura
(`MASTER_ACTION_COOLDOWN_S`, `NETWORK_REQUEST_COOLDOWN_S`,
`cooldown_remaining()`, il nuovo elenco chiuso
`MASTER_REMOTE_ACTION_COMMANDS`) si sono spostate da `core.world_sync` a
`core.world_permissions` — la base a dipendenza zero già condivisa da
client e host, dato che ora servono a entrambi. Lo STATO resta separato
per attore, ma non più per istanza di view: `core.world_sync` tiene lo
stato lato client a livello di MODULO (`_ClientCooldownState`, un
singolo dataclass di modulo, con helper `master_action_cooldown_remaining
()`/`mark_master_action()`/`network_request_cooldown_remaining()`/
`mark_network_request()`/`instance_push_cooldown_remaining()`/
`mark_instance_push()` più gli equivalenti `rewind_*_for_tests()`/
`reset_client_cooldowns_for_tests()` per i test); `core.world_backend`
tiene lo stato lato host allo stesso modo (`_HostCooldownState`,
`reset_host_cooldowns_for_tests()`, `rewind_host_master_action_for_tests()`
/`rewind_host_instance_sync_for_tests()`). Uno stato di modulo (non di
istanza) è esattamente ciò che serve a un guardrail "non permettere
all'utente di spammare": sopravvive per tutta la durata del processo,
non della singola view.

**Test.** `test_cooldown_azioni_remote.py` riscritto da zero (43/43, era
22/22): oltre alle verifiche già presenti (prima azione mai bloccata,
seconda entro la finestra rifiutata, timer aggiornato anche su comando
fallito, riapertura dopo la finestra, condivisione del timer di rete,
`_send_command()` generico mai soggetto a limiti), nuova copertura per
ciascuna delle tre scelte sopra: granularità per-personaggio (un'azione su
un PG non blocca quella su un altro, ma una seconda sullo STESSO PG resta
bloccata), stato che sopravvive alla ricreazione di `WorldsView`
(riproduzione diretta del bug trovato — creata una prima istanza, marcato
un cooldown, scartata l'istanza, creata una nuova istanza, verificato che
il cooldown sia ancora attivo), rate limiting lato host verificato
chiamando `LocalBackend.send_command()` due volte di seguito sullo stesso
`(actor, target)`/`actor` e osservando il rifiuto reale (non solo
l'assenza di collisioni con altri test), e `_any_master_cooldown_active()`
(la funzione che decide se ridisegnare). Il countdown VISIVO sui pulsanti
non ha un test automatico dedicato: è un ciclo `async` su un controllo
Flet vivo, la sua unica logica è la stessa funzione di cooldown già
verificata a fondo — costruire un test richiederebbe simulare l'intero
event loop di Flet per una copertura marginale; verifica visiva su
dispositivo reale a carico di Davide.

Aggiunte due righe di helper mancanti scoperte scrivendo i test:
`core.world_sync.rewind_instance_push_for_tests()` (mancava l'equivalente
di `rewind_master_action_for_tests()`/`rewind_network_request_for_tests()`
per il terzo tracciato, quello di `HomeView`). Corretti anche due bug nel
test stesso durante la stesura (non nel codice applicativo): una
transazione di scrittura tenuta aperta su una connessione condivisa tra
tre inserimenti di personaggio causava "database is locked" (fix:
connessione aperta e richiusa per ciascun personaggio, come già in
`_make_world_with_instance`); e un valore atteso sbagliato per gli XP di
partenza (900, il default della fixture, non 0).

Nessuna regressione sulle suite esistenti (invariate, stessi risultati
della sessione precedente): `test_mondo_senza_rete.py` 151/151,
`test_master_remote_actions.py` 81/81 (isolato dal nuovo rate limiter
host tramite un helper `_send()` che chiama
`world_backend.reset_host_cooldowns_for_tests()` prima di ogni comando —
quel file testa la correttezza degli handler, non l'anti-spam),
`test_character_instance_sync.py` 13/13 (stesso isolamento in 3 punti di
collisione trovati), `test_world_view_remote_routing.py` 16/16,
`test_master_world_scoping.py` 25/25, `test_regressione_wrap_expand.py`
85/85, `test_istanze_personaggio.py` 62/62, `test_lan_host_client.py`
92/92, `test_scoperta_lan.py` 25/25, `test_fase_d.py` 101/101. Stessi due
fallimenti preesistenti e indipendenti (`test_fase_4.py`, `test_qr_scan.py`
— vedi sopra).

---

## 2026-08-07 (sessione successiva) — Rate limiting anche su /join: chiusa l'ultima lacuna della difesa in profondità

Davide: "si completa il tutto poi buildo e testo il tutto" — chiude il
punto lasciato esplicitamente aperto nella revisione precedente: il rate
limiting lato host copriva solo `/command` (azioni del master,
`character_instance.sync`), non `/join`. Senza questo, nulla impediva di
martellare `/join` per tentare PIN diversi in rapida successione — il PIN
a 6 cifre (§9.4) è l'UNICA barriera per un dispositivo non ancora membro,
quindi è proprio lì che un limite serve di più.

**Implementazione** (`network/host_server.py`): nuovo stato di ISTANZA
`WorldHostServer._join_attempts: dict[device_id, float]` (a differenza dei
`_host_cooldowns` di modulo in `core.world_backend`: un `WorldHostServer`
vive quanto UNA sessione di hosting, `stop()` lo azzera già insieme a
token/pending — un nuovo `start()` è comunque una nuova sessione con PIN
nuovo). `_check_join_rate_limit(device_id)` applica lo stesso valore già
in uso lato client per "tutte le richieste di rete semplici"
(`perm.NETWORK_REQUEST_COOLDOWN_S`, 10s), chiamato in `handle_join()`
subito dopo la validazione di `device_id` e PRIMA di verificare
codice/PIN — l'istante si registra comunque, anche per un tentativo con
PIN sbagliato: è la stessa policy già in uso ovunque in questa revisione
("anche un tentativo fallito ha già generato traffico, non è aggirabile
martellando durante un errore"), qui applicata al bersaglio più sensibile
(indovinare un PIN a 6 cifre). Risposta HTTP 429 con messaggio pronto per
la UI — `RemoteBackend.join()` lo tratta già come qualunque altro
`status != 200` (nessuna modifica lato client necessaria: arriva a schermo
come lo stesso tipo di errore di un codice/PIN sbagliato).

Nuovo `reset_join_rate_limit_for_tests()` (istanza, non modulo — un test
che vuole isolamento vero crea semplicemente un nuovo `WorldHostServer`;
questo serve solo a un test che invia più tentativi ravvicinati dello
STESSO device_id allo STESSO host per verificare esiti diversi).

**Test.** Aggiornato `test_lan_host_client.py::test_network_protocol()`:
i tre `client.join()` ravvicinati preesistenti (codice errato / PIN errato
/ successo, stesso `device_id`) avrebbero collassato tutti sul nuovo
cancello anti-spam dal secondo in poi — inserito
`host.reset_join_rate_limit_for_tests()` tra un tentativo e l'altro, così
ciascuno verifica ancora l'esito che gli compete, non il rate limiter.
Nuova batteria dedicata `test_join_rate_limit()` (7 controlli): il primo
tentativo non è mai bloccato; un secondo IMMEDIATO sullo stesso
`device_id` viene rifiutato (429, messaggio con "ravvicinati"); un
tentativo con PIN sbagliato consuma comunque il cancello (protezione
anti-bruteforce, non solo sui tentativi validi); un `device_id` diverso
non è mai toccato dal limite di un altro; `reset_join_rate_limit_for_tests
()` lo riapre; `stop()`/`start()` non eredita alcun residuo dalla sessione
precedente. `test_lan_host_client.py` passa da 92/92 a 99/99. Nessuna
regressione sulle altre suite: `test_master_remote_actions.py` 81/81,
`test_character_instance_sync.py` 13/13, `test_mondo_senza_rete.py`
151/151, `test_istanze_personaggio.py` 62/62,
`test_master_world_scoping.py` 25/25, `test_world_view_remote_routing.py`
16/16, `test_cooldown_azioni_remote.py` 43/43, `test_scoperta_lan.py`
25/25, `test_fase_d.py` 101/101.

Con questo, la difesa in profondità lato host copre ORA entrambi gli
endpoint autenticabili senza token (`/join`) e con token (`/command`) —
nessuna lacuna nota rimasta aperta su questo fronte. Verifica su Wi-Fi
reale (build + due dispositivi) a carico di Davide — vedi in chat l'elenco
dei test manuali suggeriti.

---

## 2026-08-07 (sessione successiva) — Bug reale sull'ingresso in LAN: né il master né il giocatore vedevano l'ingresso in automatico

Davide, prima ancora di arrivare a provare l'elenco di test manuali
suggeriti nella sessione precedente: "non si sincronizzano, al master non
esce la richiesta a meno di un aggiornamento manuale e al giocatore non
esce l'approvazione del master". Due bug distinti, stessa causa di fondo:
un pezzo di stato che non passava MAI dal ciclo di sincronizzazione in
background già esistente (`WorldsView._detail_sync_loop`, ogni 2s).

**Bug 1 — il master non vede una nuova richiesta di ingresso.**
`WorldsView._detail_signature_of()` (la "firma" che decide se il ciclo di
sync deve ridisegnare la schermata) leggeva SOLO tabelle del DB
(`world_events`, `world_members`, `world_change_requests`). Le richieste
di ingresso in sospeso (`PendingJoinRequest`), però, non vivono nel DB per
scelta di design (§9.4: sono una fase transitoria prima di diventare un
vero membro) — vivono in memoria su `network.host_server.
WorldHostServer._pending`. La firma non poteva quindi MAI cambiare
all'arrivo di una nuova richiesta: architetturalmente invisibile al ciclo
di sync, a differenza di ogni altra mutazione del mondo (che passa sempre
da un evento scritto nel DB, §5). Fix minimo: `_detail_signature_of()`
ora include anche `self._host_server.list_pending()` (stesso processo,
nessuna chiamata di rete — `list_pending()` è già protetto dal proprio
lock interno) quando questo dispositivo ospita il mondo in questione,
stesso identico controllo già usato da `_hosting_section()` per decidere
se mostrare la lista.

**Bug 2 — il giocatore non vede l'approvazione del master.**
Qui non era un bug di "qualcosa che sfugge alla firma": `core.world_sync.
finish_pending_join()` era per design esplicito "azione manuale della UI,
non un ciclo automatico" (dal suo stesso docstring) — nessun polling
automatico è mai esistito, solo il pulsante "Controlla di nuovo". Fix:
nuovo ciclo `async` in `WorldsView._open_lan_join_dialog`
(`_poll_pending_join_loop`, schedulato con `page.run_task()` — mai un
`threading.Thread`, stesso principio del ticker del countdown della
sessione precedente) che si avvia da solo non appena il dialogo entra in
stato "in attesa" e richiama `finish_pending_join()` ogni
`_PENDING_JOIN_POLL_INTERVAL_S` (3s, nuova costante) finché non arriva un
esito finale o l'utente chiude il dialogo. Due decisioni di design
esplicite in questo fix:
- **Non passa dal cancello anti-spam di rete** (i 10s condivisi tra
  `_join`/`_attempt`/`_retry`): quel limite protegge i TENTATIVI di
  ingresso (`POST /join`, che consumano una `PendingJoinRequest` e
  potrebbero martellare PIN diversi), non un polling passivo di stato
  (`GET /join/status`) — coerente con la scelta, già presa lato host, di
  non sottoporre `WorldHostServer.join_status()` a nessun rate limit
  (economico, in sola lettura). Il pulsante manuale "Controlla di nuovo"
  resta invece soggetto al cooldown come prima: qui si tratta solo il
  ciclo automatico dell'app, non un'azione esplicita dell'utente che vuole
  insistere.
- **Si ferma da solo** quando `pending_state["backend"]` torna `None` —
  impostato da `_report()` su un esito finale, o dal pulsante "Annulla"
  (ora un handler dedicato, `_cancel`, invece di un lambda che chiudeva e
  basta): senza, un rifiuto esplicito del master o la chiusura manuale del
  dialogo avrebbero lasciato il ciclo a interrogare l'host per una
  richiesta ormai chiusa. Trovato scrivendo il fix, non segnalato da
  Davide: `_report()` non azzerava mai `retry_btn.visible` su un esito
  terminale (rifiuto/errore) — corretto nella stessa occasione, "Controlla
  di nuovo" restava visibile e cliccabile anche dopo un rifiuto definitivo.

**Test.** Nuovo `test_ingresso_lan_sincronizzazione.py` (31/31), con un
vero `WorldHostServer` su socket reale (stesso pattern di
`test_lan_host_client.py`), non una replica della logica:
- bug 1: `_detail_signature_of()` cambia davvero quando un secondo
  dispositivo chiama `POST /join` sull'host (stato SOLO in memoria,
  nessuna tabella coinvolta), cambia di nuovo dopo l'approvazione, resta
  stabile se nulla cambia, e resta cieca a un `WorldHostServer` che ospita
  un ALTRO mondo;
- bug 2: il dialogo «Unisciti in LAN» reale (`WorldsView.
  _open_lan_join_dialog()`, con una `_FakePage` che intercetta `show_
  dialog`/`pop_dialog`/`update`/`run_task` — necessaria una patch mirata
  della PROPRIETÀ `page` di Flet SOLO sulla classe `WorldsView`, che non
  ha setter e non ha il pattern `self._page` cache-ato di altre view di
  questo progetto, es. `MasterEncounterView`) rileva l'approvazione E il
  rifiuto del master con un solo giro del ciclo di polling automatico
  fatto avanzare manualmente (`asyncio.sleep` sostituito con un no-op per
  quella singola chiamata, ripristinato subito dopo — nessuna vera attesa
  nei test), senza alcun click su "Controlla di nuovo"; verificato anche
  che "Annulla" fermi davvero il ciclo (monkeypatch di `finish_pending_
  join` per farlo fallire se richiamato dopo la chiusura del dialogo).
  Nessuna regressione sulle suite esistenti (stessi risultati della
  sessione precedente, incluso `test_lan_host_client.py` 99/99 — il rate
  limit su `/join` della sessione precedente non collide con questi nuovi
  test: ogni scenario usa un `device_id` nuovo).

Bug non ancora possibile da riprodurre in sandbox (nessuna rete reale,
nessun secondo dispositivo): resta la verifica di Davide su Wi-Fi reale,
stesso elenco di test manuali già fornito, con l'aggiunta esplicita di
"ingresso in un mondo LAN da un secondo dispositivo, senza toccare nulla
sul dispositivo del master né premere 'Controlla di nuovo' sul giocatore".

---

## 2026-08-07 (sessione successiva) — Avviso export/import per un personaggio legato a un mondo condiviso

Davide ha chiesto come sono gestiti gli accessi/le sessioni tra
dispositivi ("se entro con lo stesso dispositivo la sessione successiva
riesco a collegarmi sullo stesso personaggio? e se questo personaggio
viene esportato su un altro dispositivo?"). Rispondendo è emerso un
comportamento preesistente, mai segnalato prima: `character_export.
import_character()` (nato 2026-07-24) azzera SEMPRE `world_id`/
`origin_character_id`/`owner_device_id`/`is_replica`/`world_seq` per
TUTTE le modalità di importazione — comportamento corretto e voluto (un
file esportato da un'istanza di mondo, importato senza azzerare quei
campi, diventerebbe una "replica" di un mondo inesistente sul dispositivo
di destinazione, bloccata in sola lettura e non riparabile
dall'interfaccia) — ma questo avveniva **in silenzio**: nessun errore,
nessun avviso, l'utente scopriva solo dopo che il personaggio aveva
"perso" il collegamento al mondo. Richiesta esplicita: "aggiungi un
avviso per l'utente".

**Fix** (`ui/views/home_view.py`), due dialoghi gemelli, entrambi
opzionali — l'utente può sempre procedere comunque, l'esportazione resta
utile come backup locale e niente qui impedisce di importare un
personaggio world-linked, solo lo segnala PRIMA:
- **Export**: `_on_export_click()` — se `char.world_id` è valorizzato,
  mostra `_confirm_export_world_linked()` prima di procedere
  (`_proceed_export()`, il corpo del vecchio `_on_export_click` estratto
  così com'era, invariato). Nessun dialogo per un personaggio locale (il
  caso comune): l'app non deve rallentare per un controllo che non serve.
- **Import**: `_do_import_from_text()` — se `data["character"]["world_id"]`
  nel file è valorizzato, mostra `_show_import_world_linked_warning()`
  prima di procedere (`_continue_import()`, il vecchio flusso — controllo
  conflitto d'id o importazione diretta — estratto così com'era). Stesso
  principio: nessun dialogo in più per un file locale.

Entrambi i dialoghi mostrano il nome del mondo di origine
(`world_repo.get_world(world_id)`, con un testo di ripiego se quel mondo
non esiste più su QUESTO dispositivo — es. mai stato ospitato/visitato
qui) e spiegano cosa succede se si procede, con lo stesso stile già in
uso nel progetto (`d.dialog_title(..., tone="danger")`,
`wrap_dialog_actions`, template ripreso da `_confirm_delete`/
`_show_import_conflict_dialog` già esistenti nello stesso file).

**Nota a margine, confermata a Davide nella stessa richiesta**: i
pulsanti di refresh manuale ("Aggiorna richieste" lato master,
"Controlla di nuovo" lato giocatore) NON sono mai stati rimossi dai fix
delle sessioni precedenti sulla sincronizzazione automatica — restano
entrambi presenti come salvagente per i casi estremi in cui l'automatismo
non scattasse, l'automazione è un'aggiunta accanto ad essi, non una
sostituzione.

**Test.** Nuovo `test_avviso_export_import_mondo.py` (35/35): nessun
avviso per un personaggio locale (né export né import, 3 controlli);
avviso mostrato per un personaggio di un mondo, con «Annulla» che blocca
davvero l'operazione e «Esporta/Importa comunque» che la fa procedere
davvero (verificato che l'import risultante abbia REALMENTE `world_id`/
`owner_device_id` azzerati — riconferma che lo zeroing preesistente non è
stato toccato da questo fix, il nuovo avviso si limita a informare); testo
di ripiego quando il mondo di origine non esiste sul dispositivo, sia in
export sia in import. `HomeView` testata con lo stesso schema di patch
della proprietà `page` di Flet già introdotto per `WorldsView` in
`test_ingresso_lan_sincronizzazione.py` (nessun `self._page` cache-ato in
questa view, a differenza di `MasterEncounterView`). Nessuna regressione
sulle suite esistenti (tutte invariate rispetto alla sessione precedente).

---

## 2026-08-07 (sessione successiva) — Bug severo: l'hosting LAN si fermava da solo navigando via dalla Sezione Mondi

Davide, dopo aver verificato che la sincronizzazione automatica
dell'ingresso funziona ("si aggiorna bene in automatico... una volta
accettato si aggiunge bene"): ha poi provato ad aggiungere un personaggio
a un incontro dalla Modalità Master, e lì "esce questo messaggio e il
master non vede nessun personaggio nel mondo" — il push del personaggio
sull'host falliva con "Personaggio creato, ma non è stato possibile
registrarlo subito sull'host", e la Sezione Incontri mostrava "Nessun
personaggio disponibile" per quel mondo.

**Analisi.** Nessuna rete reale disponibile in sandbox per riprodurre
esattamente lo scenario a due dispositivi, ma il codice ha rivelato la
causa senza ambiguità: `WorldsView.will_unmount()` fermava SEMPRE
l'hosting attivo (`self._host_server.stop()`) — una scelta deliberata di
una sessione precedente, commentata esplicitamente come "uscire dalla
sezione Mondi senza fermarlo esplicitamente non deve lasciare una porta
aperta". Il problema: `ui/app.py::_navigate()` azzera e ricostruisce
l'INTERA pagina ad ogni navigazione di primo livello (Home, Modalità
Master, Mondi, perfino un cambio tema) — il ciclo di vita standard di
Flet fa scattare `will_unmount()` sulla `WorldsView` precedente ad OGNI
singola di quelle navigazioni, non solo quando si esce davvero e per
restare fuori dalla Sezione Mondi. Quindi: il master approva un ingresso
mentre è nella Sezione Mondi (hosting attivo, tutto bene) → apre la
Modalità Master per gestire l'incontro → quella navigazione smonta la
`WorldsView` e ferma l'hosting SENZA alcun avviso a schermo → il
giocatore, nel frattempo, tenta di registrare il proprio personaggio
sull'host ormai morto → fallisce esattamente col messaggio segnalato.
Non serviva nemmeno un riavvio dell'app: bastava una singola normale
navigazione del master.

**Fix** (`network/host_server.py`, `ui/views/world/world_view.py`,
`ui/app.py`): `WorldHostServer` non vive più come attributo di istanza
su `WorldsView` — vive in un nuovo contenitore condiviso, `HostServerSlot`
(un semplice oggetto con un campo `server`), creato UNA SOLA VOLTA da
`DnDApp.__init__` (sopravvive quanto il processo) e passato a ogni
`WorldsView` costruita in `_show_worlds_view()` ad ogni navigazione.
`WorldsView._host_server` è diventata una `@property` che legge/scrive
`self._host_server_slot.server` — nessun altro punto del file (`_start_
hosting`, `_stop_hosting`, `_hosting_section`, `_approve_join`, `_reject_
join`, `_detail_signature_of`, ecc., ~10 punti) ha dovuto cambiare, tutti
continuano a leggere/scrivere `self._host_server` esattamente come prima.
`will_unmount()` non ferma più l'hosting: si ferma SOLO tramite `_stop_
hosting()` ("Ferma hosting", azione esplicita del master) o alla vera
chiusura del processo (il thread del server è `daemon=True`, nessun
cleanup necessario). Se non viene passato un `host_server_slot` (qualunque
test o uso che costruisce `WorldsView` direttamente, come fa quasi tutta
la suite di test esistente), se ne crea uno privato — stesso comportamento
di isolamento di prima per chi non condivide la view tra più istanze.

Questo capovolge una scelta di design esplicita di una sessione precedente
("non lasciare una porta aperta uscendo dalla sezione") — segnalato qui
per trasparenza: la scelta nuova è corretta per l'uso reale (un master non
deve disconnettere l'intero tavolo spostandosi in un'altra schermata
dell'app), ma è comunque una revisione di una decisione già presa, non
solo un fix di un bug mai discusso prima.

**Test.** Nuovo `test_hosting_persistente_navigazione.py` (13/13):
`will_unmount()` non ferma più l'hosting (con e senza slot condiviso
esplicito); il caso vero del bug riprodotto con uno slot condiviso tra
due istanze di `WorldsView` create in sequenza (come farebbe `ui/app.py`
ad ogni navigazione) — l'hosting avviato sulla prima sopravvive alla sua
`will_unmount()` ed è DAVVERO raggiungibile in rete dalla seconda (un
client reale su socket riesce a inviare `POST /join` e la richiesta è
visibile dalla nuova istanza della view, non solo "l'oggetto esiste
ancora" — la prova che il bug reale è chiuso); `_stop_hosting()` continua
a fermarlo per davvero; due `WorldsView` senza slot condiviso restano
isolate (nessun leak di hosting tra istanze scorrelate); nessuna eccezione
se `will_unmount()` scatta senza hosting mai avviato. Nessuna modifica
necessaria a nessun test esistente (verificato: la property è trasparente
per tutti i punti che già leggevano/scrivevano `wv._host_server`
direttamente) — nessuna regressione su tutte le altre suite.

Verifica su Wi-Fi reale (approvare un ingresso, poi navigare in Modalità
Master, poi verificare che il giocatore riesca comunque a registrare il
personaggio) a carico di Davide — impossibile da riprodurre end-to-end a
due dispositivi fisici in questo sandbox.

---

## 2026-08-07 (sessione successiva) — Layout Incontri troppo compresso, azioni master scomode durante un combattimento, PF del giocatore mai sincronizzati col mondo

Davide, dopo aver confermato che il fix precedente funzionava ("mi sono
collegato ho aggiunto un personaggio e riesco ad aggiungerlo nella sezione
master"), ha sollevato tre punti da "discutere" con uno screenshot della
lista Incontri: (1) troppo poco spazio visibile per la lista, tutta la
chrome sopra (selettore mondo, Generatori Rapidi, tab bar, header di
Incontri) occupa la maggior parte dello schermo; (2) scomodo per il master
dover cambiare schermata verso Mondi per dare PE/danno/cura durante un
incontro; (3) se un personaggio si ferisce sulla propria scheda, quella
modifica non si riflette mai nel mondo/nell'incontro — "tutte le schede
devono essere sincronizzate nel mondo dando le stesse statistiche".

**Analisi preliminare (grounded nel codice, non a memoria).** Prima di
proporre soluzioni, verificato lo stato reale:
- Il meccanismo per nascondere la chrome di `MasterView` esiste già
  (`_on_child_focus_change()`, 2026-08-06) ma scatta SOLO aprendo un
  incontro specifico, mai sulla lista — lo screenshot di Davide era
  proprio la lista.
- `master_encounter_view.py::_member_card()` mostra i PF di un PG SEMPRE
  in sola lettura (`"PF X/Y · giocatore"`), per design dichiarato nel
  docstring del modulo: "i PG restano sempre gestiti dal giocatore sulla
  propria scheda" — non un bug, una scelta esplicita già in vigore.
- `get_encounter_members_resolved()` legge i PF di un "character" SEMPRE
  live dalla tabella `characters`, mai da un valore cachato sulla riga
  dell'incontro — quindi un aggiornamento sulla scheda del giocatore, se
  mai arrivasse fino a quella tabella (sullo stesso dispositivo che
  ospita), sarebbe già visibile nell'incontro senza altro lavoro: il
  vero anello mancante era solo "far arrivare" quell'aggiornamento fin
  lì da un ALTRO dispositivo.
- Nessun comando esisteva per un aggiornamento PF iniziato dal
  GIOCATORE: `hp.damage`/`hp.heal` (già networked) partono solo dal
  master via "Interviene a distanza"; un giocatore che si segna danno da
  solo sulla propria scheda scrive oggi SOLO in locale.

Tre biforcazioni di design vere, non coperte da `multiplayer_design.md`
(che tratta solo §6.1 «Aggiorna il mio foglio», manuale e per un resync
completo — non i soli PF, non automatico) sono state sottoposte a Davide
via `AskUserQuestion` invece di essere decise arbitrariamente:
1. Come liberare spazio in Incontri → **"Generatori Rapidi solo fuori da
   quella tab"** (scelta di Davide, opzione consigliata).
2. Quali azioni duplicare nell'incontro → **"solo Danno/Cura/Condizione"**
   (scelta di Davide, opzione consigliata) — abilità/incantesimo bonus/
   diario/proponi modifica restano solo in Mondi.
3. Sync dei PF del giocatore → **"sì, invio automatico in tempo reale"**
   (Davide ha scelto QUESTA, non l'opzione consigliata "resta manuale").

**Fix 1 — Layout (`ui/views/master/master_view.py`).** `_build()` ora
costruisce `_tools_row_container` (i 6 generatori) SOLO se
`active_tab != "encounters"`; se `None`, semplicemente non viene
aggiunto ai `controls` (nessuna azione nascosta: i 6 generatori restano
sempre visibili nelle altre 4 tab, semplicemente non esistono in una tab
che ha già i propri pulsanti). `_on_child_focus_change()` resta invariata
e già a prova di `None` (`if ctrl is not None`).

**Fix 2 — Azioni PG dall'incontro (`data/repositories/master_repo.py`,
`ui/views/master/master_encounter_view.py`).**
`get_encounter_members_resolved()` ora espone anche `world_id` per un
membro "character" (letto dalla stessa riga `characters` già
interrogata, `""` per un PG locale). `_member_card()`: per un PG con
`world_id` valorizzato, accanto al chip "PF X/Y · giocatore" compaiono
tre `IconButton` — Danno/Cura/Condizione — che aprono dialog IDENTICI
(stesso testo, stessi campi) a quelli già in `world_view.py`, e
inviano lo STESSO comando attraverso `LocalBackend().send_command()`
(nuovo `_send_pg_remote_command()`, nuovi `_open_pg_damage_dialog`/
`_open_pg_heal_dialog`/`_open_pg_condition_dialog`) — stessa pipeline
comando → validazione → evento, stesso limite anti-spam per personaggio
(`core.world_sync`, stato di MODULO: condiviso automaticamente con
`WorldsView`, non serve duplicarlo). Un PG locale (nessun mondo) resta
di sola lettura, invariato. **Limite preesistente segnalato, non
introdotto qui**: come "Assegna PE" nello stesso file, usa
`LocalBackend()` incondizionatamente — corretto quando questo
dispositivo ospita il mondo (il caso normale), non instrada verso un
host remoto se il master fosse un co-master collegato come client da un
altro dispositivo (limite già presente, fuori scope per questa
richiesta). Aggiornati anche il docstring del modulo e il testo del
dialog "Assegna PE" (diceva "è l'unica modifica" — non più vero).

**Fix 3 — Invio automatico dei PF del giocatore
(`core/world_permissions.py`, `core/world_backend.py`,
`core/world_sync.py`, `ui/views/character_sheet/combattimento_tab.py`).**
Nuovo comando `hp.self_update`, ruolo minimo `player` ma con verifica di
proprietà (`perm.is_character_owner`, stesso principio già usato per
`change_request.respond`/`character_instance.sync`): un giocatore può
aggiornare via rete SOLO la propria istanza. Payload a **valori
assoluti** (`hp_current`/`hp_temp`/tiri salvezza contro morte), mai un
delta: un invio perso non lascia nulla di incoerente, il prossimo invio
porta comunque lo stato più recente (idempotente). Nuovo handler
`_handle_hp_self_update()` in `world_backend.py` — NON passa da
`damage_rules` (il calcolo è già stato fatto dal chiamante sulla propria
copia locale), scrive il risultato finale con clamp difensivo
(`0 <= hp_current <= hp_max`, `hp_temp >= 0`, tiri salvezza `0..3`) e
apre un evento nel registro. Difesa in profondità su tre livelli, stessa
architettura di ogni altro comando di rete:
- **Client**: `CombattimentoTab._schedule_hp_world_sync()`, chiamata
  subito dopo OGNI scrittura locale di PF/PF temp/tiri salvezza contro
  morte del personaggio (11 punti nel file: tiri salvezza manuali,
  `_roll_death_save`, danno, cura, HP temp, modifica manuale, riposo
  breve, riposo lungo, danno spillover da forma selvatica) — MAI
  bloccante: se il personaggio non è un'istanza di mondo o non c'è una
  pagina montata, esce subito senza fare nulla. Debounce con un token di
  generazione (`_hp_sync_generation`): una raffica di click ravvicinati
  produce UN SOLO invio con l'ultimo valore, non uno per click.
- **Cooldown client** (`core.world_sync`, `HP_SELF_UPDATE_COOLDOWN_S =
  1.5s`, deliberatamente più corto di quello del master perché qui non
  c'è alcuna attesa percepita da minimizzare): usato solo per decidere
  QUANDO inviare, mai per bloccare l'azione locale.
- **Host** (`core.world_backend._check_rate_limit`, stesso valore):
  backstop contro un client modificato, stesso principio già in uso per
  gli altri comandi di rete.
Un fallimento dell'invio (host irraggiungibile, cooldown) non mostra MAI
un errore al giocatore — loggato e basta (`logger.warning`), coerente
con "best effort, mai bloccante".

**Test.** Nuovo `test_layout_incontri_e_pf_autosync.py` (50/50): layout
(tools_row assente solo su "encounters", presente altrove, cambio tab
in-place, `_on_child_focus_change` a prova di `None`); permessi
`hp.self_update`; handler (proprietario può, master/altri non possono,
clamp dei valori fuori range, tiri salvezza inclusi); difesa in
profondità lato host (secondo invio ravvicinato rifiutato, terzo dopo il
cooldown riesce); cooldown lato client (per personaggio, rewind);
`CombattimentoTab._schedule_hp_world_sync()` no-op sicuro sia per un
personaggio locale sia per un'istanza senza pagina montata; `world_id`
esposto da `get_encounter_members_resolved()`; azioni PG dall'incontro
end-to-end (danno applicato raggiunge `characters`, `refresh()` lo
riflette live, difesa in profondità lato host attiva anche bypassando il
cooldown client). Nessuna regressione sulle 13 suite esistenti toccate
dai file modificati (tutte rieseguite, tutte verdi).

Resta da verificare da Davide: che l'invio automatico dei PF funzioni
davvero end-to-end su Wi-Fi reale con due dispositivi fisici (il
cooldown di 1.5s è una scelta ragionata ma mai provata sotto una vera
latenza di rete) e che le tre nuove icone Danno/Cura/Condizione
nell'incontro risultino comode nell'uso reale al tavolo.

---

## Pulizia generale del codice (2026-08-07)

Richiesta esplicita di Davide: "Controlla tutto il codice elimina il
codice inutilizzato e quello ridondante, ci sono alcune descrizioni non
vere che abbiamo lasciato prima di implementare i passi 5 e 6 ecc" —
audit dell'intero codebase, non limitato al Multiplayer. Metodo: inventario
struttura → `pyflakes`+`vulture` (installati in sandbox, non preinstallati)
per candidati automatici → triage manuale di ciascun candidato (uno per uno,
non un cieco "rimuovi tutto ciò che il tool segnala") → grep mirato di frasi
tipo "non ancora"/"nessuna riga di codice"/TODO nei `docs/*.md` e nei
docstring → applicazione fix → ricompilazione (`ast.parse`) di ogni file
toccato → riesecuzione dell'intera suite di test esistente.

**Falsi positivi di `vulture` riconosciuti e NON rimossi** (dispatch via
reflection del framework, non chiamata diretta): i metodi `did_mount`/
`will_unmount` di ogni view Flet (~15 file), `do_GET`/`do_POST`/
`log_message` di `network/host_server.py` (dispatch di `http.server`), e
tutti gli handler `_handle_*` di `core/world_backend.py` (dispatch tramite
il dizionario `_HANDLERS`, popolato dal decoratore `@register_handler`, mai
una chiamata diretta per nome).

**Codice morto rimosso (8 funzioni/metodi, zero chiamanti verificati via
grep):**
- `ui/mobile_webview_picker.py` — blocco `if TYPE_CHECKING: from flet_webview
  import WebViewConsoleMessageEvent` (il nome era già re-importato a runtime
  altrove nel file, il blocco `TYPE_CHECKING` era un residuo inutilizzato).
- `ui/design.py` — `display()`, `mono()`, `stat_tile()`, `metric_bar()`:
  primitive di testo/statistica mai usate da nessuna view (`metric_bar` è
  verosimilmente superata dalla più specifica `hp_bar()`, tuttora usata in
  `combattimento_tab.py`). Le costanti `Size.MONO`/`Font.MONO`/
  `Size.DISPLAY`/`Font.DISPLAY` restano — usate altrove direttamente.
- `data/game_data/game_data_loader.py` — `get_artifact(name)` (lookup
  singolo per nome, usato solo da un test, mai dall'app: la UI usa sempre
  `get_artifacts()`).
- `data/repositories/loot_repo.py` — `get_entry_by_id()`,
  `update_entry_quantity()`: la UI usa sempre la più generale
  `update_entry()`.
- `ui/views/master/master_loot_assign_dialog.py` — funzione annidata
  `_dest_label()`, mai chiamata nemmeno nel proprio scope.
- `core/world_permissions.py` — `requires_character_ownership()` e
  `is_forbidden_character_field()`: entrambe wrapper mai chiamati (ogni
  handler in `world_backend.py` fa il controllo direttamente,
  `perm.is_character_owner(...)`). La costante sottostante
  `FORBIDDEN_CHARACTER_FIELDS` **resta deliberatamente**: documenta il §7
  del design doc in una forma verificabile dal codice, anche se oggi nessuna
  funzione la legge — la protezione reale è strutturale (nessun handler
  scrive quei campi al di fuori dell'allow-list di
  `CHANGE_REQUEST_ALLOWED_FIELDS`), non un controllo a runtime su questa
  lista. Verificato che i 3 handler di `PLAYER_OWNED_COMMANDS`
  (`_handle_change_request_respond`, `_handle_hp_self_update`,
  `_handle_character_instance_sync`) fanno ciascuno il proprio controllo di
  proprietà — nessun buco di sicurezza dalla rimozione del dispatcher.

Test aggiornati di conseguenza in `test_fase_4.py` (rimossi 3 controlli sul
lookup singolo), `test_layout_incontri_e_pf_autosync.py`,
`test_master_remote_actions.py`, `test_mondo_senza_rete.py` (i controlli
sulle due funzioni rimosse riscritti come verifica diretta di appartenenza
all'insieme/frozenset sottostante, stessa logica, senza passare dal
wrapper).

**Codice ridondante consolidato:**
- Formula del CD dei tiri salvezza duplicata inline (`8 + pb + sp_mod`) in
  `ui/views/spells_view.py` e `ui/views/character_sheet/combattimento_tab.py`
  invece di usare l'helper condiviso già esistente
  `core/character_stats.py::spell_save_dc(character)` — entrambi i punti ora
  chiamano l'helper.
- Costruzione manuale di `ft.SnackBar` duplicata in `_show_error()` (e
  `_show_success()` in `home_view.py`) invece dell'helper condiviso
  `ui/widgets.py::show_snack()` — entrambi i file ora delegano a `show_snack`
  (`_show_success` in `home_view.py` usa `tone="magic"`, non `"success"`, per
  preservare esattamente il colore di sfondo originale).
- I dialoghi Danno/Cura/Condizione per un PG istanza di mondo, appena scritti
  nella sessione precedente sia in `ui/views/world/world_view.py` sia in
  `ui/views/master/master_encounter_view.py`, erano duplicati quasi
  identici. Estratto un nuovo modulo condiviso
  `ui/components/remote_action_dialogs.py`
  (`show_damage_dialog`/`show_heal_dialog`/`show_condition_dialog`, ciascuna
  `(page, character_name, on_confirm: Callable[[dict], None])` — il dialogo
  possiede solo validazione input e costruzione UI, il chiamante decide cosa
  fare col payload validato). Entrambi i file originali ora hanno wrapper
  sottili che delegano a questo modulo.

**Descrizioni non vere corrette (richiesta esplicita di Davide sui passi 5/6
e "ecc"):**
- **`docs/multiplayer_design.md`** — il banner in cima dichiarava ancora
  "Stato: SOLA PROGETTAZIONE, nessuna riga di codice scritta" e "Sette
  passi" nel testo del §13 nonostante la tabella ne elenchi nove e i passi
  1-6 siano implementati e in gran parte testati su Wi-Fi reale — il banner
  più fuorviante trovato in questo giro, riscritto per rimandare a
  CLAUDE.md come tracker di stato live e a questo documento (§1-§12) come
  fonte delle decisioni chiuse.
- **`docs/master_section_design.md`** — banner "Nessun codice scritto
  ancora — solo progettazione" nonostante la Sezione Master sia implementata
  per intero salvo il Compendio Oggetti Magici — riscritto di conseguenza.
- **`docs/revisione_2026_07_26.md`** — tabella "Stato di avanzamento"
  ferma a Fase 3 parziale e Fase 4 "da fare — 5 decisioni aperte", mentre
  entrambe sono chiuse da tempo (restyle A-E completo, le 4 feature della
  Fase 4 tutte implementate) — corretta con una nota che segnala la tabella
  come stata stale.
- **`docs/feature_design_2026_07_26.md`** — banner "Nessuna riga di codice
  applicata" — riscritto per riflettere che le 4 feature sono implementate e
  chiuse.
- **`core/world_backend.py`** — docstring di `RemoteBackend.get_snapshot()`
  e un commento di sezione dichiaravano ancora "le istanze di personaggio/il
  passo 6 non esistono ancora", mentre sono implementate più sotto nello
  stesso file — entrambi riscritti per descrivere lo stato reale.
- **`core/character_instances.py`** — docstring di modulo dichiarava
  "`is_replica` resta sempre 0, avrà senso solo dal passo 4" in un modo che
  suggeriva fosse ancora vero oggi — riscritto per chiarire che QUESTO
  modulo (passo 3) crea sempre con `is_replica=0` per costruzione, mentre
  `is_replica=1` lo imposta `character_export.py::import_replica_character()`
  altrove, una volta che il passo 4 (rete) scarica una replica.
- **`ui/views/master/master_loot_view.py`** — docstring dichiarava il
  Deposito del Gruppo "comunque utile in locale" senza menzionare che è già
  world-scoped tramite `_effective_world_id()` — riscritto per descrivere il
  comportamento reale (confermato leggendo il costruttore e 6+ punti d'uso).
- **`network/host_server.py`** — docstring di modulo ambiguo su quando il
  server si ferma ("si spegne alla chiusura") — reso esplicito che si ferma
  SOLO con "Ferma hosting" esplicito o la chiusura del processo (thread
  daemon), mai per una navigazione, coerente col fix `HostServerSlot` di una
  sessione precedente.

**Due bug reali trovati mentre si verificavano i test dopo le rimozioni
(non erano l'obiettivo della sessione, ma la riesecuzione della suite li ha
esposti):**
- `test_fase_4.py` verificava ancora la frase letterale "unica modifica" nel
  dialogo di conferma di "Assegna PE", frase rimossa quando (sessione
  precedente) sono state aggiunte le pillole Danno/Cura/Condizione
  sull'incontro per un PG istanza di mondo — da quel momento "Assegna PE"
  non è più l'unica scrittura del master su un PG, quindi il testo UI è
  stato correttamente cambiato in "mai una scrittura diretta" (sempre
  pipeline comando→evento) ma il test non era stato aggiornato. Corretto il
  test per verificare la frase attuale.
- `test_fase_4.py` verificava anche che il JSON degli artefatti dichiarasse
  onestamente "Occhio e Mano di Vecna" come mancante tramite la chiave
  `_incomplete_note` — ma i 7 artefatti DMG sono stati completati (vedi
  CLAUDE.md "Artefatti DMG (7/7)"), quindi quella chiave è stata
  correttamente rimossa dal JSON (la UI gestisce già la sua assenza,
  `if note:` in `master_artifacts_dialog.py`) e il test verificava
  letteralmente l'incompletezza di un dato ormai completo. Corretto per
  verificare invece che tutti e 7 gli artefatti siano presenti e che non
  resti alcuna nota di incompletezza.

**Altro:** rimossa una directory vuota accidentale `dnd_app/dnd_app/`
(3 sottocartelle annidate, 0 file — verosimilmente un artefatto di una
sessione precedente, nessun riferimento nel codice).

**Verifica finale.** Ricompilati (`ast.parse`) tutti i 20 file toccati,
nessun errore di sintassi. Riesguita l'intera suite di test esistente (17
file, 1149 controlli totali): **1146 passati**, 3 falliti — tutti e tre
**pre-esistenti e non causati da questa pulizia**, confermato isolandoli:
- `test_istanze_personaggio.py` — 1 fallimento, un test che lancia
  `test_mondo_senza_rete.py` come sottoprocesso dopo aver impostato
  `os.environ["HOME"]` a una cartella temporanea per il proprio setup; il
  sottoprocesso eredita quel `HOME` modificato e non trova più `flet`
  (installato come pacchetto utente sotto `~/.local`, percorso dipendente da
  `HOME` in questo sandbox). Eseguendo `test_mondo_senza_rete.py` da solo,
  o riproducendo lo stesso `subprocess.run` senza il resto del file, il
  risultato è 151/151 verde — è un artefatto di come questa sandbox ha
  `flet` installato, non un bug nel codice del progetto.
- `test_qr_scan.py` — 2 fallimenti, entrambi etichettati dal test stesso
  come dipendenti dall'ambiente ("pacchetti presenti in questo ambiente"):
  verificano che `flet-camera`/`pyzbar` (pacchetti nativi Android/iOS) siano
  installati, cosa non vera in questo sandbox generico Linux.

Nessuno dei tre è legato ai file toccati in questa pulizia. Prima della
pulizia, con le stesse identiche 2 cause d'ambiente, la suite aveva "2
fallimenti pre-esistenti non correlati" (vedi sessioni precedenti) — lo
stato è coerente.

---

## Due bug reali dal primo giro di test manuali sui pulsanti PG in Incontri (2026-08-07)

Davide ha seguito l'elenco di test manuali proposto dopo la pulizia del codice
(stesso giorno) e ha riportato due problemi concreti sulle pillole
Danno/Cura/Condizione appena aggiunte alla Sezione Incontri (screenshot alla
mano: errore "Il mittente non è membro di questo mondo" cliccando su un PG
istanza di mondo presente e valido).

**Bug 1 — `_send_pg_remote_command` usava il world_id sbagliato.**
`MasterEncounterView._send_pg_remote_command()` inviava sempre
`self._world_id` (il mondo selezionato nel menu a tendina in cima a Modalità
Master) invece del world_id proprio del personaggio bersaglio. Se il
dropdown è su "Locale" (`self._world_id == ""`, come nello screenshot di
Davide) o su un mondo diverso da quello del PG nell'incontro, l'host rifiuta
il comando perché nessun membro di QUEL world_id ha quel device_id — anche
se il giocatore è membro del mondo VERO del personaggio. `_confirm_award_xp`
("Assegna PE"), poco più sopra nello stesso file, faceva già la cosa giusta
(`p.world_id`, il world_id proprio del personaggio) — pattern di riferimento
per il fix. Corretto passando il world_id del personaggio (già disponibile
nello scope dove nascono i pulsanti, `resolved.get("world_id")`) lungo tutta
la catena `_open_pg_damage_dialog`/`_open_pg_heal_dialog`/
`_open_pg_condition_dialog` → `_send_pg_remote_command`, mai più
`self._world_id`. Aggiunto un test di regressione dedicato
(`test_encounter_view_send_usa_world_id_del_personaggio`) che costruisce la
vista con `world_id=""` (esattamente lo scenario dello screenshot) — il test
esistente per questa funzionalità non l'avrebbe mai potuto scoprire, perché
costruiva sempre la vista con lo STESSO world_id dell'istanza.

**Bug 2 — la Sezione Incontri non aveva alcuna sincronizzazione in
background.** Davide: "i PF si aggiornano ma... in Incontri non si
aggiornano, il master deve andare in Sezione Mondi, aspettare, e tornare in
Incontri". Causa: il ciclo di sync in background (thread dedicato +
`page.run_task()`, introdotto il 2026-08-07 per "Interviene a distanza")
viveva SOLO in `WorldsView` — `MasterEncounterView` non aveva alcun
meccanismo equivalente, il suo `refresh()` veniva chiamato solo dopo
un'azione locale riuscita, mai per riflettere un cambiamento arrivato da un
altro dispositivo (es. `hp.self_update` del giocatore). Fix: estratta la
parte davvero condivisibile di quel ciclo — gestione del thread + ponte
thread-safe verso il loop asyncio di Flet, l'unica parte delicata e già
corretta una volta (bug "serve il refresh manuale" della sessione
precedente) — in un nuovo modulo `ui/components/background_sync.py`
(`BackgroundSyncLoop`, con `signature_fn`/`apply_fn`/`async_redraw_fn`/
`should_redraw_anyway_fn` iniettate dal chiamante, nessuna dipendenza da un
mondo o una vista specifica — Dependency Inversion, non importa né
`world_repo` né `world_sync`). `WorldsView._start_detail_sync` è stato
rifattorizzato per delegare a questo helper (comportamento verificato
identico: tutte le suite `test_mondo_senza_rete.py`,
`test_world_view_remote_routing.py`, `test_ingresso_lan_sincronizzazione.py`,
`test_cooldown_azioni_remote.py`, `test_lan_host_client.py`,
`test_hosting_persistente_navigazione.py` rieseguite senza modifiche,
tutte verdi) — rimosso di conseguenza `_maybe_redraw_detail`, diventato
morto dopo l'estrazione. `MasterEncounterView` ora usa lo stesso helper con
una firma di dominio propria (`_sync_signature`: PF/CA/nome di ogni
combattente + round corrente, dato che `get_encounter_members_resolved()`
legge già live da `characters` ad ogni chiamata — basta quindi rilevare
quando quel valore cambia) e un `_sync_apply` che scarica gli eventi nuovi
per ogni mondo distinto tra i PG dell'incontro non ospitato da questo
dispositivo (`world_sync.resolve_backend_for_world`, stesso resolver già
condiviso da `WorldsView`/`home_view.py`). Avviato in `did_mount()`, fermato
in `will_unmount()`.

**Limite noto, non risolto in questo giro (fuori scope della richiesta di
Davide, già documentato nel codice prima di questo fix):**
`_send_pg_remote_command` usa `LocalBackend()` incondizionatamente — corretto
quando questo dispositivo ospita il mondo (il caso normale), ma un co-master
collegato come CLIENT all'host di un altro dispositivo scriverebbe sulla
propria replica invece che sull'host reale. Stesso limite già presente in
"Assegna PE". Il lato LETTURA (sync in background, questo fix) invece usa
correttamente `resolve_backend_for_world` e quindi FUNZIONA anche da un
co-master client — l'asimmetria resta scritta nel codice per la prossima
sessione che deciderà se vale la pena chiuderla.

**Test.** `test_layout_incontri_e_pf_autosync.py` esteso da 50 a 61 controlli
(11 nuovi: riproduzione del bug 1 con world_id vuoto, verifica che danno/cura
raggiungano `characters` comunque, verifica che l'INVIO diretto con
`self._world_id` vuoto fallisca ancora con lo stesso identico messaggio —
documenta il vecchio bug perché non regredisca in futuro sotto altra forma;
firma di sync che cambia quando i PF cambiano nel DB senza `refresh()`
esplicito, `_sync_apply()` no-op sicuro da host, countdown
`_sync_should_redraw_anyway()`, lifecycle avvio/arresto del thread). Suite
completa (17 file, 1160 controlli): 1157 verdi, le stesse 3 cause d'ambiente
pre-esistenti e indipendenti (vedi la voce di pulizia poco sopra), nessuna
nuova regressione.

Rimangono da chiarire con Davide, riportati nella stessa sessione insieme a
questi due bug: (a) l'espulsione di un membro da un mondo non stacca i
personaggi-istanza che possedeva, restano collegati al mondo per sempre —
serve una decisione di design su cosa fare di quei personaggi orfani; (b)
richiesta di sincronizzazione COMPLETA (non solo PF) tra la scheda del
giocatore e la copia autoritativa sull'host — oggi solo `hp.self_update`
esiste, tutto il resto (inventario, slot incantesimo, livello, equipaggiamento)
scritto dal giocatore in locale non raggiunge mai l'host finché non viene
esplicitamente usato "Aggiorna il mio foglio" (§6.1, che però è un
meccanismo diverso: locale↔istanza, non replica↔host); (c) restyle della
parte superiore di Modalità Master e ripristino dei Generatori Rapidi anche
in Incontri (decisione precedente da invertire). Le tre voci non sono state
implementate in questa sessione — sono scelte di design/scope che vanno
decise con Davide, non arbitrariamente.

---

## Le tre voci aperte risolte: espulsione con archiviazione, estensione graduale della sincronizzazione, restyle di Modalità Master (2026-08-07/2026-08-11)

Le tre voci lasciate aperte nella sessione precedente (espulsione che
orfanizza i personaggi, ambito della sincronizzazione giocatore↔host,
restyle) sono state sottoposte a Davide via `AskUserQuestion` invece di
essere decise arbitrariamente. Risposte: (a) "Disattiva/archivia" per
l'espulsione, (b) "Estendi gradualmente `hp.self_update` ad altri campi" per
l'ambito della sincronizzazione, (c) "Sì, sempre visibili" per i Generatori
Rapidi e "Raggruppa/nascondi dietro un pannello a comparsa" per la
compattezza. Le tre implementazioni, in ordine:

### (a) Espulsione: archivia, non distrugge

Nuova colonna `characters.world_instance_archived INTEGER DEFAULT 0`
(`data/database.py`, migrazione via `_add_column`), campo corrispondente su
`Character` (`data/models.py`). `_handle_member_kick`
(`core/world_backend.py`) ora chiama la nuova
`character_repo.archive_world_instances(world_id, owner_device_id)` dopo
aver rimosso il membro: `UPDATE characters SET world_instance_archived=1 ...
WHERE world_id=? AND owner_device_id=? AND world_instance_archived=0`,
restituisce il conteggio, incluso nel riepilogo/payload dell'evento
(`archived_count`). `get_master_visible_characters(world_id)`
(`data/repositories/character_repo.py`) filtra ora `AND
world_instance_archived = 0`: un'istanza archiviata sparisce dalla vista
master ma la riga resta nel DB, mai cancellata — reversibile.

**Riattivazione**: nessuna nuova UI necessaria — riusa il meccanismo di
resync già esistente. Se il giocatore (che non ha mai avuto il flag
impostato sul proprio dispositivo, l'archiviazione è solo lato host) invia
di nuovo `character_instance.sync` o un resync completo, l'istanza importata
arriva con `world_instance_archived=0` e torna visibile. Un errore trovato e
corretto scrivendo il test: esportare l'istanza DALLA STESSA riga host
appena archiviata e reimportarla preserva ovviamente `archived=1` (nessuna
vera riattivazione) — il test corretto simula invece cosa manderebbe
davvero il dispositivo del giocatore, impostando esplicitamente
`world_instance_archived=0` nell'export prima di reimportare.

Import/export di un `.dndchar` locale (§14.1, `character_export.py`) aggiunge
`"world_instance_archived": 0` ai `char_overrides` già esistenti che azzerano
ogni collegamento a un mondo — coerente con gli altri 5 campi già trattati
così.

Test: `test_mondo_senza_rete.py`, nuovo blocco dopo il test di kick
esistente — visibilità pre-kick, archiviazione post-kick (`archived_count`
nel payload, istanza non cancellata, esclusa da
`get_master_visible_characters`), idempotenza (ri-espellere un non-membro
fallisce senza effetti), riattivazione via resync. 160/160 verdi (era
158/160 alla prima stesura, per il bug di auto-esportazione sopra
descritto).

### (b) Sincronizzazione: estensione graduale di `hp.self_update` alle condizioni

Decisione di Davide: non un resync completo indiscriminato, ma lo stesso
pattern già validato per i PF (`hp.self_update`, invio automatico in tempo
reale, mai bloccante per la UI locale, difesa in profondità con cooldown sia
client sia host) esteso campo per campo. Primo campo scelto: le condizioni
(accecato/affascinato/afferrato/assordato/avvelenato/incapacitato/
invisibile/paralizzato/pietrificato/privo di sensi/prono/spaventato/
stordito/trattenuto — nomi PHB IT, `GameDataLoader().get_conditions()`).

Nuovi comandi `condition.self_apply`/`condition.self_remove`
(`core/world_permissions.py`): ruolo minimo player, in
`PLAYER_OWNED_COMMANDS` (serve la verifica di proprietà, non solo il ruolo)
e in `CHARACTER_MUTATING_COMMANDS` (serve alla replica di un eventuale terzo
dispositivo, es. co-master). Nuovo `CONDITION_SELF_UPDATE_COOLDOWN_S = 1.5`
— più breve del debounce PF perché ogni applicazione/rimozione di una
condizione è già un'azione discreta e deliberata (niente stream continuo da
smorzare come i PF).

Lato host (`core/world_backend.py`): la logica di applicazione condizione
già esistente (usata dal master) è stata estratta in un helper condiviso
`_apply_condition_to_character(ctx, character, *, kind, summary_verb)`,
richiamato sia da `_handle_condition_apply` (master, invariato nel
comportamento) sia dal nuovo `_handle_condition_self_apply` (verifica
`perm.is_character_owner()` oltre al ruolo, poi delega allo stesso helper).

La rimozione NON è stata condivisa allo stesso modo — scoperta
architetturale fatta leggendo `character_export.py::_insert_row()`: ogni
reimport/rimaterializzazione completa di una replica rigenera un nuovo UUID
per ogni riga di tabella figlia (incluso `character_conditions.id`). Un
`condition_id` noto sul dispositivo del giocatore NON corrisponde quindi
all'id della stessa condizione logica sulla riga dell'host. Il gestore
master `_remove_condition_from_character` (per id) resta usato SOLO dal
master; il nuovo `_handle_condition_self_remove` è un percorso separato che
identifica le condizioni da rimuovere per `condition_key` (rimuove tutte le
righe che corrispondono), non per id — l'unica chiave stabile tra
dispositivi diversi. Se questo bug non fosse stato trovato per tempo, la
rimozione di una condizione da parte del giocatore avrebbe fallito
silenziosamente o rimosso la condizione sbagliata su un host con righe id
diverse.

Difesa in profondità: cooldown lato host per `(actor_device_id, target_id)`
in `_HostCooldownState.condition_self_update_last_at`
(`rewind_host_condition_self_update_for_tests` per i test) e cooldown lato
client per `character_id` in `core/world_sync.py`
(`condition_self_update_cooldown_remaining`/`mark_condition_self_update`/
`rewind_condition_self_update_for_tests`), stesso schema già usato per i PF.

Lato scheda (`ui/views/character_sheet/combattimento_tab.py`):
`_schedule_condition_apply_sync(condition_key, source, note)` e
`_schedule_condition_remove_sync(condition_key)` (nota: per chiave, non per
id, coerente col fix sopra), più `_push_condition_to_world(...)` asincrona
che risolve il device_id, controlla il cooldown client, risolve il backend
via `world_sync.resolve_backend_for_world` e invia — mai bloccante,
eccezioni loggate e ignorate. Richiamate da `_on_condition_click()` (ramo
rimozione) e `_open_condition_picker()` (ramo aggiunta).

Test: `test_layout_incontri_e_pf_autosync.py` esteso con 5 nuove sezioni
(permessi, handler, rate limit host, cooldown client, integrazione UI
scheda→invio) — la prima stesura usava per errore chiavi inglesi
(`"prone"`/`"blinded"`/`"stunned"`/`"frightened"`/`"poisoned"`), corrette
nelle rispettive chiavi PHB IT (`prono`/`accecato`/`stordito`/`spaventato`/
`avvelenato`) non appena scoperte dai fallimenti — violavano la regola
critica di terminologia del progetto. 103/103 verdi dopo la correzione.

Non ancora fatto (prossimo campo, se Davide chiede di continuare
l'estensione graduale): slot incantesimo, inventario, livello,
equipaggiamento — oggi restano locali fino a un resync manuale esplicito.

### (c) Restyle di Modalità Master: pannello strumenti a comparsa

`ui/views/master/master_view.py`: le due sezioni prima gestite
separatamente (`_world_selector_row()`, e `_build_tools_row()` nascosta
solo sulla tab Incontri per un'altra richiesta precedente) sono state
unificate in un unico `_build_tools_panel()` — un pannello collassabile
(header sempre visibile con freccia, contenuto selettore mondo + Generatori
Rapidi mostrato solo da espanso) presente in modo UNIFORME su ogni tab,
Incontri incluso, invertendo la scelta precedente "nascosti solo lì".
Collassato di default (`self._tools_panel_expanded = False`).
`_toggle_tools_panel()` ricostruisce il pannello e lo sostituisce IN PLACE
nei `controls` (mai un semplice flip di `visible`, per evitare artefatti di
layout residui di Flet già visti in passato — vedi
`regole_flet_api.md`), preservando lo stato di un eventuale incontro aperto.
Lo stato espanso/collassato sopravvive a un cambio di mondo (`_on_world_change`
fa comunque una `_build()` completa). `_on_child_focus_change()` aggiornato
per riferirsi al singolo `self._tools_panel_container` invece dei due
contenitori precedenti.

Test: `test_layout_incontri_e_pf_autosync.py`, sezione `[1]` riscritta da
zero (`test_layout_pannello_strumenti`, sostituisce il vecchio test che
verificava l'esclusione dalla tab Incontri) — presenza uniforme su ogni tab,
collassato di default, toggle sostituisce il container, sopravvive al
cambio mondo, `_on_child_focus_change` continua a nascondere/mostrare senza
sollevare eccezioni.

### Verifica finale

Suite completa (17 file): tutte verdi tranne le 2 cause d'ambiente
pre-esistenti già note in `test_qr_scan.py` (pacchetti nativi
Android/iOS assenti in sandbox, non nel codice) e un fallimento isolato di
`test_fase_4.py` ("il totale compare nel pannello", sezione tiri) risultato
non riproducibile su 5 riesecuzioni consecutive e su codice non modificato
tramite `git stash` — tiro di dado casuale occasionalmente coincidente con
un valore che rompe il confronto testuale del pannello, test preesistente
indipendente da questa sessione, non una regressione introdotta qui.

---

## Multiplayer, passi 7-9 — "Condivisione", "Mappe condivise", "Robustezza" (2026-08-11)

Sessione pianificata in modalità Plan (3 agenti Explore in parallelo su
tracker di combattimento/mappe/robustezza, poi 1 agente Plan per il
progetto di implementazione file-per-file, approvato da Davide prima di
scrivere codice — piano salvato e seguito passo passo). Scoperta iniziale
importante: **§6.1 "Aggiorna il mio foglio" del passo 7 era già
completamente implementato** (`core/character_instances.py::preview_refresh
/apply_refresh` + `ui/views/home_view.py::_open_refresh_dialog`, fatto
insieme al passo 3 senza aggiornare la tabella di stato in CLAUDE.md) — zero
lavoro necessario lì, solo la tabella andava corretta.

**Due bug di correttezza reali trovati rileggendo il codice PRIMA di
scrivere il piano** (non ipotizzati, verificati riga per riga):
1. `WorldHostServer.handle_snapshot()` chiamava `get_events_since(world_id,
   0)` senza `limit` esplicito, ereditando silenziosamente `limit=200` — un
   mondo con più di 200 eventi nella sua storia produceva uno snapshot
   troncato per chi entrava ora.
2. `core/world_sync.py::_finalize_join()` salvava gli eventi storici
   (`save_replica_event`) ma non li **applicava** mai tramite
   `apply_event_to_replica` — solo i personaggi di cui il nuovo arrivato è
   proprietario venivano rimaterializzati. Una nota condivisa/mappa
   pubblicata/combattimento reso visibile PRIMA che un giocatore entrasse
   nel mondo non gli sarebbe mai arrivato, nemmeno in futuro (`last_synced_seq`
   viene impostato subito al valore più alto ricevuto). Corretto in ognuna
   delle tre feature sotto: `handle_snapshot()` porta anche lo stato
   "attuale" (non solo gli eventi), `_finalize_join()` lo materializza con
   le STESSE funzioni di scrittura della replica usate per un evento nuovo
   — un solo scrittore condiviso, mai due copie della stessa logica.

### 9A — Fix troncamento snapshot

`data/repositories/world_repo.py::get_events_since()` accetta ora
`limit: int | None = 200` — `None` salta la clausola `LIMIT` nell'SQL.
`WorldHostServer.handle_snapshot()` la chiama con `limit=None`. Nessuna
paginazione (non necessaria oggi, lasciato un commento per il futuro).

### 9B — Verifica versione di protocollo lato host

Il controllo esisteva SOLO lato client (`core.world_sync.start_lan_join()`
confronta `GET /world`) — l'host non verificava nulla su `/join`/`/command`,
quindi un client che saltasse `GET /world` poteva comunque entrare. Nuovo
`WorldHostServer._check_protocol_version(body)`, chiamato in
`handle_join()` (blocco primario) e `handle_command()` (difesa in
profondità, un token valido con versione sbagliata viene comunque
rifiutato). `RemoteBackend.join()`/`send_command()` mandano ora
`protocol_version` nel body. Test: nuovo `test_robustezza_rete.py` (13/13
— include anche il test end-to-end della [1] con host reale su 127.0.0.1).

### 7B — Condivisione delle note (§6.2)

Il lato master (scrittura/visibilità) era già completo (`master_repo.py`,
`master_notes_view.py`, colonne `world_id`/`visibility`/
`visible_to_device_ids` su `master_campaign_notes`) ma con due lacune: le
scritture andavano dirette a `master_repo` (mai un evento nel registro,
violando l'esplicita richiesta del design doc "cambiare la visibilità è
un'azione registrata"), e non esisteva nessuna vista lato giocatore.

Nuovo handler `CMD_NOTE_SHARE` in `core/world_backend.py` (il payload
dell'evento porta l'intero contenuto della nota, non solo l'id — testo
piccolo, evita un secondo giro di rete per materializzarlo sulla replica).
`ui/views/master/master_notes_view.py` ora instrada create/edit attraverso
`world_backend.send_command()` (risolvendo l'host giusto via
`world_sync.resolve_backend_for_world()`, stesso meccanismo di
`WorldsView`) quando `world_id` è valorizzato — le note locali restano
dirette. Nuove funzioni `data/repositories/master_repo.py`:
`get_master_campaign_note_by_id`, `get_notes_visible_to(world_id,
device_id)` (mai le note `private`), `save_replica_note` (upsert, usata sia
dal ramo evento in `apply_event_to_replica` sia da `_finalize_join`). Nuova
sezione di sola lettura `WorldsView._shared_notes_section()`, visibile a
QUALSIASI membro (non solo master/owner), aggiornamento live gratuito via
`BackgroundSyncLoop` esistente (la firma include già `get_latest_seq`).

Test: nuovo `test_note_sharing.py` (26/26) — handler, materializzazione
sulla replica, note private mai visibili a nessun giocatore, un evento di
kind sconosciuto non solleva mai eccezioni, e il bug #2 sopra (nota
condivisa prima dell'ingresso arriva comunque). Nessuna regressione su
`test_master_remote_actions.py` (81/81), `test_mondo_senza_rete.py`
(160/160), `test_istanze_personaggio.py` (62/62), `test_lan_host_client.py`
(99/99).

### 7C — Tracker di combattimento per i giocatori (§6.5)

Non esisteva nulla. Nuove colonne `master_encounters.world_id`/
`visible_to_players` (spento di default). Nuove funzioni `master_repo.py`:
`set_encounter_world`, `set_encounter_visibility`,
`get_visible_encounter_for_world`, `resolved_members_to_dicts` (versione
JSON-serializzabile di `get_encounter_members_resolved`, sostituisce
l'oggetto `MasterEncounterMember` non serializzabile con i soli campi
scalari), `replica_upsert_encounter_snapshot`, `get_replica_encounter_members`.

**Scelta di design**: niente righe finte in `master_encounter_members` su
una replica (gli id di `master_npcs`/`characters` referenziati da un membro
npc/adhoc potrebbero non esistere affatto su quel dispositivo) — una nuova
colonna `master_encounters.replica_members_json` (blob JSON) fa da
specchio di sola lettura, popolata SOLO su una replica, mai sull'host (che
legge sempre `get_encounter_members_resolved()` dal vivo). Stessa tabella
riusata da host e replica, come ogni altra tabella del Multiplayer.

**Bug reale trovato scrivendo il test**: la prima versione di
`replica_upsert_encounter_snapshot` usava `INSERT OR REPLACE` — su SQLite
questo è un DELETE+INSERT anche a parità di id, e
`master_encounter_members.encounter_id` ha `ON DELETE CASCADE`. Nel test
(un solo DB condiviso tra "host" e "replica" simulata, stesso principio di
`test_lan_host_client.py`), applicare un evento su un id che coincideva con
la riga autoritativa dell'host cancellava silenziosamente i membri veri
dell'incontro. Corretto con UPDATE-se-esiste-altrimenti-INSERT, che non fa
mai scattare un CASCADE.

Nuovi handler `CMD_ENCOUNTER_MANAGE` (azioni `next_turn`/`end_combat`) e
`CMD_COMBAT_TOGGLE_VISIBILITY` in `core/world_backend.py`, deliberatamente
ESCLUSI da `MASTER_REMOTE_ACTION_COMMANDS` (nessun cooldown di 3s — azioni
occasionali, non spam da combattimento, stessa scelta già presa per
`CMD_WORLD_RENAME`). `ui/views/master/master_encounter_view.py`: nuovo
interruttore "Visibile ai giocatori" nell'header (solo per incontri
world-linked), `_on_next_turn_click`/`_on_end_encounter_click` instradano
tramite comando quando `world_id` è valorizzato, chiamata diretta
`master_repo` altrimenti. Nuova `ui/views/world/combat_status.py::
wound_status_label(hp_current, hp_max)` — funzione pura, tabella
Illeso/Ferito/Gravemente ferito/In fin di vita/Fuori combattimento,
commentata esplicitamente come convenzione dell'app e non una regola del
manuale (il PHB non definisce stati di ferita descrittivi). Nuova sezione
`WorldsView._live_combat_section()`: PF esatti per `source=="character"`
(tutti i PG, non solo il proprio — coerente col testo del design doc), solo
lo stato descrittivo per mostri/PNG.

Test: nuovo `test_combat_tracker_condiviso.py` (36/36) — fail-closed su un
incontro fuori mondo, toggle visibilità, `next_turn` via comando identico
alla chiamata diretta, materializzazione sulla replica, tabella di casi di
`wound_status_label`, e il bug #2 (incontro visibile prima dell'ingresso
arriva comunque). Nessuna regressione su `test_note_sharing.py` (26/26),
`test_master_remote_actions.py` (81/81), `test_mondo_senza_rete.py`
(160/160), `test_lan_host_client.py` (99/99),
`test_layout_incontri_e_pf_autosync.py` (103/103).

### 8a — Mappe condivise, backend (§6.4) — IN CORSO

**Decisione di schema presa con Davide**: `game_maps.character_id` era
`TEXT NOT NULL REFERENCES characters(id) ON DELETE CASCADE` — una mappa
condivisa non ha un personaggio proprietario sul dispositivo di un
giocatore che non l'ha creata. Scelto (tra tre opzioni presentate:
character_id nullable / mappe "solo live" senza riga locale / personaggio
segnaposto): **rendere `character_id` nullable**. SQLite non permette di
rilassare un vincolo NOT NULL/FK con `ALTER TABLE` — prima migrazione con
ricostruzione di tabella del progetto (finora solo colonne additive via
`_add_column` idempotente), in `data/database.py::
_migrate_game_maps_nullable_character_id()`: guardata da `PRAGMA
table_info` (procede solo se la colonna risulta ancora `notnull=1`, quindi
a sua volta idempotente), elenco colonne da copiare letto dinamicamente
(mai un elenco scritto a mano che potrebbe disallinearsi). **Verificata
esplicitamente su schema vecchio**: riga esistente preservata, nuova riga
con `character_id=NULL` si inserisce dopo la migrazione, una seconda
`init_db()` è un no-op sicuro.

Nuove colonne `game_maps.world_id`/`is_shared` (additive). Nuove funzioni
`data/repositories/maps_repo.py`: `get_map(id)` (mancava — finora bastava
sempre `get_maps(character_id)`), `get_shared_maps(world_id)`,
`publish_map`/`unpublish_map`, `apply_stroke_batch` (unico punto che
interpreta un pacchetto di operazioni di disegno — `add`/`clear`/
`replace_all`, quest'ultimo usato dalla gomma invece di codificare un diff:
cancellare è raro rispetto a disegnare — usata sia dall'handler sia dal
ramo replica, nessuna logica duplicata), `replica_create_map_stub`
(`character_id` resta `NULL`, mai `""`: la colonna ha FK con
`PRAGMA foreign_keys=ON` attivo, una stringa vuota non combacerebbe con
nessun personaggio e violerebbe il vincolo), `replica_set_shared`.

Nuovo `core/image_utils.py::sniff_mime(bytes) -> str` — magic byte
JPEG/PNG/GIF, estratto da `ui/views/maps_view.py::_data_uri()` (che ora lo
riusa) perché servirà anche alla rotta HTTP dell'immagine (passo 8b, non
ancora scritta). Nuovi handler `CMD_MAP_PUBLISH`/`CMD_MAP_DRAW` in
`core/world_backend.py` — l'immagine NON viaggia mai nel payload
dell'evento (troppo grande per il giornale), solo il nome; i replica la
scaricheranno lazy dalla rotta dedicata quando aprono la mappa. Ramo
replica in `core/world_sync.py` per `map.publish`/`map.draw`. Chiuso lo
stesso bug #2 di sopra: `handle_snapshot()` porta i metadati (mai
`image_data`) delle mappe condivise, `_finalize_join()` li materializza
come stub.

**Aggiornamento della stessa sessione**: il test dedicato del backend è
stato scritto (`test_mappe_condivise.py`, 38/38) prima ancora della rotta
HTTP e della UI — vedi la voce "8b/8c" sotto per come sono stati chiusi.

### 8b/8c — Mappe condivise, rotta HTTP + UI (§6.4) — CHIUSO (2026-08-11)

Chiude il passo 8 per intero. Tre pezzi, in ordine.

**8b — `GET /map/<id>/image`** (già presente nel sorgente da questa stessa
sessione, `network/host_server.py::WorldHostServer.handle_map_image` +
`_RequestHandler.do_GET`, ma senza batteria dedicata): prima rotta
non-JSON del progetto, ritorna `(status, content_type, bytes)` — l'errore
è comunque servito come JSON (`content_type="application/json"`), un solo
dispatcher per entrambi i casi. Permesso a QUALSIASI membro del mondo
della mappa (non solo al proprietario, a differenza di
`handle_get_character`): una mappa condivisa è per definizione visibile a
tutto il tavolo. Nuovo `test_mappe_condivise_http.py` (22/22): percorso
felice via `RemoteBackend.fetch_map_image()` reale su socket (bytes
identici, PNG e JPEG), sei percorsi di rifiuto fail-closed (token non
valido/assente, mappa inesistente, non condivisa, senza immagine ancora
caricata, di un ALTRO mondo, dispositivo mai entrato), più una verifica a
basso livello via `http.client` diretto (status/content-type/corpo esatti,
non solo `None` dietro l'astrazione di `RemoteBackend`).

**8c — UI** in `ui/views/world/world_view.py` (nuova sezione "Mappe
condivise" nel dettaglio di un mondo, `WorldsView._shared_maps_section` e
i metodi attorno). Due decisioni di scopo prese in questa sessione, non
nel design doc originale — entrambe ora annotate anche in
`multiplayer_design.md` §6.4:

1. **Pubblicare/disegnare è permesso SOLO a master/owner che OSPITA il
   mondo** (`world.is_local_host`), non a "chiunque abbia il permesso di
   ruolo" come le altre azioni master di questa view. Motivo: una mappa
   condivisa è sempre una riga `game_maps` posseduta da un personaggio
   LOCALE di chi la pubblica — se un co-master non-host inviasse
   `CMD_MAP_PUBLISH` via `RemoteBackend`, l'handler girerebbe sul DB
   dell'HOST, dove quella riga semplicemente non esiste ("Mappa non
   trovata", non un bug silenzioso, ma un vicolo cieco evitabile
   nascondendo subito i controlli a chi non può usarli). Un co-master
   non-host vede comunque le mappe già condivise, in sola lettura, come
   un giocatore qualunque — verificato esplicitamente in
   `test_mappe_condivise_ui.py` parte [1].
2. **I tratti si inviano A FINE TRATTO** (`on_pan_end`), non raggruppati
   ogni ~200ms durante il disegno come descritto in prima battuta dal
   design doc — che dichiara esplicitamente questa come alternativa
   valida "se su una Wi-Fi lenta risultasse a scatti... nessuna
   riprogettazione". Scelta presa qui per semplicità implementativa (un
   flush periodico concorrente ai callback sincroni di gesture avrebbe
   richiesto un buffer condiviso tra thread), non per un problema di rete
   riscontrato. I giocatori vedono comunque ogni tratto completo apparire
   entro il ciclo di sincronizzazione già esistente
   (`_DETAIL_SYNC_INTERVAL_S`, 2s) — se in prova reale risultasse troppo
   "a scatti" per mappe di battaglia con molti tratti lunghi, il passo
   successivo naturale è il batching a 200ms già previsto dal design doc,
   non una riprogettazione.

Dettaglio implementativo: pubblicazione (`_open_publish_map_dialog`) lista
le mappe locali NON condivise di TUTTI i personaggi locali (non solo
quelli legati a un mondo — un master pubblica una mappa che ha sul proprio
dispositivo, non necessariamente su un PG di quel mondo), un bottone
"Pubblica" per riga, niente step di selezione+conferma separato. L'overlay
di apertura/disegno (`_open_shared_map`) usa `page.overlay` (stesso idioma
di `ui/views/maps_view.py::MapsView._open_fullscreen`), MAI una sezione
dentro `self._body`: `_render_detail` ricostruisce `self._body.controls`
da zero ad ogni giro del ciclo di sincronizzazione in background (2s) — un
canvas di disegno lì dentro verrebbe rimontato a metà tratto. Lato
giocatore/co-master non-host, l'overlay non ha `GestureDetector` (sola
lettura) e avvia un piccolo ciclo `async` dedicato (`_watch_loop`, stesso
principio di `_poll_pending_join_loop` già in uso in questo file) che
ridisegna il canvas ogni `_SHARED_MAP_REDRAW_INTERVAL_S` (= 2s, stesso
valore di `_DETAIL_SYNC_INTERVAL_S`: interrogare più spesso non
produrrebbe dati più freschi, il DB locale è già tenuto allineato da quel
ciclo) finché l'overlay resta aperto. L'immagine (mai trasportata da un
evento, §6.4) si scarica pigra una tantum alla prima apertura via
`RemoteBackend.fetch_map_image()` se assente, poi in cache locale
(`maps_repo.update_map(..., image_data=...)`) — esattamente come
annotato mesi prima nel docstring di quella funzione. Toolbar di disegno
volutamente ridotta rispetto a quella locale di `maps_view.py` (7 colori,
"Annulla ultimo", "Cancella tutto" — niente gomma pixel-precisa/
fullscreen doppio canvas): sufficiente per "il master disegna, i
giocatori vedono", non un sostituto della vista mappe locale.

Bug reale trovato scrivendo il test del dialogo di pubblicazione:
`responsive_dialog_width(page)` chiamato senza l'argomento obbligatorio
`base_width` — mai eseguito prima (nessun test invocava ancora quel
dialogo), corretto con `responsive_dialog_width(page, 380)` (stesso
valore già in uso per un dialogo simile più sotto nello stesso file).

Nuovo `test_mappe_condivise_ui.py` (39/39), quattro parti: [1] visibilità/
contenuto della sezione per le tre combinazioni di ruolo/hosting che
contano (master host, player, master NON host — quest'ultimo sola lettura
nonostante il ruolo); [2] click reali sui controlli Flet trovati per
contenuto/icona (stesso approccio di `test_ingresso_lan_sincronizzazione.py`)
per pubblicazione/ritiro; [3] overlay lato master host — un tratto
disegnato via gesture produce esattamente un evento `CMD_MAP_DRAW` e
un'annotazione persistita coi punti giusti, "Annulla ultimo"/"Cancella
tutto" idem, chiusura rimuove l'overlay; [4] overlay lato replica con un
vero `WorldHostServer` su socket — fetch pigro dell'immagine tracciato e
verificato (bytes identici ai pubblicati), nessun controllo di disegno
presente, un giro di `_watch_loop` rileva un tratto scritto nel frattempo.
Limite dichiarato in [4], stesso della parte [3] di `test_mappe_condivise.py`
e di `test_lan_host_client.py`: questo sandbox usa un solo DB condiviso
tra "host" e "client", quindi lo stato "immagine non ancora scaricata" è
simulato sull'oggetto Python passato a `_open_shared_map`, non sulla riga
DB fisica (che qui è per forza la stessa riga per entrambi i lati) — il
fetch via rete reale è comunque verificato per intero (bytes scaricati
tracciati e confrontati).

Suite di regressione completa rieseguita (23 file): tutte verdi tranne le
2 cause pre-esistenti e note in `test_qr_scan.py` (dipendenze d'ambiente
di questo sandbox — Android/iOS non disponibili qui — indipendenti da
questa sessione, già segnalate il 2026-08-07).

Con questo **il passo 8 (Mappe condivise) è chiuso per intero**. Resta il
passo 9D (esportazione `.dndworld`), 9E (promemoria periodico), 9F (UI
export/import), e la passata di regressione/documentazione finale del
piano dei 9 passi.

### 8d — Mappe condivise: quattro correzioni dopo il primo uso reale (2026-08-12)

Sessione successiva alla chiusura del passo 8, con Davide che ha usato la
sezione per la prima volta e segnalato tre problemi reali più una feature
mancante (non sulle mappe, ma nella stessa sezione). Tutti e quattro
risolti nella stessa sessione.

**1. Bug reale — disegnare sulla mappa condivisa modificava anche la mappa
personale.** Causa: `CMD_MAP_PUBLISH` riusava la STESSA riga `game_maps`
del personaggio che l'aveva creata (`UPDATE ... SET world_id=?,
is_shared=1 WHERE id=?`) — disegnare nel mondo scriveva quindi sulla
stessa riga che compare anche nella Sezione Mappe personale di quel
personaggio, **anche se non faceva parte di nessun mondo**. Fix:
`maps_repo.clone_map_for_sharing(source_map_id, world_id)` — pubblicare
ora CLONA (id nuovo, `character_id=NULL` come le mappe di replica,
annotazioni vuote) invece di riusare la riga. Il personale non viene mai
più toccato dopo la pubblicazione. Effetto collaterale accettato
consapevolmente: la mappa personale di origine NON risulta mai `is_shared`
(resta sempre un candidato ripubblicabile nel dialogo "Pubblica una mappa
già salvata") — nessuna deduplicazione, ripubblicare crea un secondo clone
indipendente; se Davide lo trova fastidioso in pratica è un'aggiunta
piccola per una sessione successiva, non fatta ora per restare nello scope
di ciò che è stato chiesto.

**2. Bug reale — le annotazioni non si allineavano se la mappa non era a
schermo intero** ("come se solo la mappa si rimpicciolisse"). Causa: i
punti di ogni tratto si salvavano in pixel ASSOLUTI, relativi alla
dimensione esatta che il riquadro di disegno aveva nell'istante del
disegno — Flet non riscala il contenuto di un canvas al variare del
riquadro che lo contiene, quindi lo stesso tratto visto in un riquadro di
dimensione diversa (finestra del master vs. schermo del giocatore, anche
se "entrambi a schermo intero" sui rispettivi dispositivi) restava ancorato
alle vecchie coordinate. Fix, nuovo `ui/canvas_geometry.py` (puro, nessuna
dipendenza Flet): i punti si salvano come FRAZIONE [0,1] della dimensione
del riquadro al momento del disegno (`normalize_points`) e si riconvertono
in pixel assoluti rispetto al riquadro CORRENTE ad ogni ridisegno
(`denormalize_points`) — letto tramite `ft.Container(on_size_change=...)`,
l'unico modo in Flet 0.86.5 di conoscere la dimensione effettiva di un
controllo dopo il layout (niente `Container.on_resize`/
`ContainerResizeEvent` in questa versione, verificato empiricamente).
**Compatibilità con le annotazioni già disegnate prima del fix**: nessuna
migrazione (la dimensione del riquadro con cui furono salvate non è
ricostruibile) — `looks_normalized()` distingue euristicamente i due
formati (un tratto in frazioni ha ogni punto in [0,1], un tratto in pixel
assoluti quasi certamente no) e lascia invariati quelli vecchi, corregge
solo i nuovi. Applicato SOLO alla mappa condivisa (`world_view.py::
_open_shared_map`, che è sempre un overlay unico, mai due riquadri diversi
come nel caso locale) — la vista Mappe locale (`maps_view.py`, inline +
schermo intero, in uso da settimane senza segnalazioni) ha la stessa
classe di bug in teoria ma NON è stata toccata: rischio di regressione su
una funzionalità stabile e già rodata, sproporzionato rispetto a quanto
chiesto — da riprendere solo se Davide conferma che serve anche lì.

**3. Richiesta — "nascondi ai giocatori" faceva sparire la mappa anche dal
proprio elenco.** Causa: l'unico controllo esistente era il "ritiro dalla
condivisione" (`is_shared=0`), che nella UI corrispondeva a "Ritira" e
faceva sparire la riga da `get_shared_maps()` per chiunque, master
incluso. Fix: nuova colonna `game_maps.visible_to_players` (default 1),
DISTINTA da `is_shared` — nuovo comando `CMD_MAP_VISIBILITY`
(`maps_repo.set_map_visibility`), che nasconde/mostra ai giocatori SENZA
toccare `is_shared`: la mappa resta sempre nell'elenco del master (con
l'indicazione "nascosta ai giocatori"), un player smette di vederla in
lista E `GET /map/<id>/image` nega l'immagine a chi non è master/owner
(`network/host_server.py::handle_map_image`, stesso principio fail-closed
di `handle_get_character`) — due strati, non solo un filtro UI aggirabile.
Nuovo comando SEPARATO `CMD_MAP_DELETE` (`maps_repo.delete_map`, già
esisteva la funzione, mai esposta come comando) per l'eliminazione VERA,
l'unico modo per far sparire la mappa anche dall'elenco del master; la
mappa personale di origine (se pubblicata per clonazione) non è mai
toccata da nessuno dei due.

**4. Richiesta — caricare una mappa nuova direttamente nella sezione
condivisa**, senza doverla prima salvare sotto un personaggio locale.
Nuovo comando `CMD_MAP_UPLOAD` (`maps_repo.create_shared_map`) — stesso
risultato finale di `CMD_MAP_PUBLISH` (riga condivisa senza personaggio
proprietario), ma senza mappa di origine: il master sceglie nome +
immagine (stessi tre rami di selezione già in uso in `maps_view.py` —
web/mobile/desktop, `_pick_from_library`/`_pick_mobile` riscritte per
accettare una `Page` diretta invece di un `MapsView`, così `world_view.py`
può riusarle senza duplicarle) e la visibilità iniziale in un unico
dialogo. Il trailing della sezione ("+ Mappa") apre ora un piccolo dialogo
di scelta tra le due sorgenti (`_open_add_map_dialog`) invece di andare
dritto al vecchio dialogo "Pubblica".

**5. Voce a sé, nella stessa sessione (Davide, di nuovo dopo il primo uso
reale)**: "manca la possibilità di eliminare il personaggio dal mondo,
attualmente posso eliminare solo la persona [il membro] dal mondo ma non
il suo personaggio". Nuovo comando `CMD_CHARACTER_INSTANCE_REMOVE`
(`character_repo.archive_world_instance`, singolare — a fianco
dell'esistente `archive_world_instances`, plurale, usata dal kick per
TUTTE le istanze di un dispositivo) — il master rimuove UN personaggio
specifico dalla Sezione Master mentre il suo giocatore resta membro del
mondo (morte permanente, doppione, personaggio mai più usato). Stessa
non-distruttività già decisa con Davide per l'espulsione: archiviato
(`characters.world_instance_archived`), mai cancellato, si riattiva da
solo al primo resync del proprietario. Nuova pillola "Rimuovi dal mondo"
(rossa) in fondo alla riga di ogni personaggio in "Interviene a distanza",
con dialogo di conferma — passa da `_send_remote_command` (non una
scorciatoia): stesso timer anti-spam per personaggio delle altre azioni
della riga, `ctx.target_id` invece di un id nel payload (fix di
coerenza trovato scrivendolo: il resto di `world_backend.py` per i
comandi a bersaglio "character" legge sempre `ctx.target_id`, mai
`ctx.payload["character_id"]`).

Quattro nuovi/riscritti file di test, tutti verdi: `test_mappe_condivise.py`
riscritto per intero (76/76, era 38/38 — copre clona/upload/visibilità/
eliminazione/disegno/replica/migrazione), `test_mappe_condivise_http.py`
riscritto (29/29, era 22/22 — aggiunge la parte sulla visibilità),
`test_mappe_condivise_ui.py` riscritto (64/64, era 39/39 — aggiunge la
regressione del bug #1, il fix delle coordinate con due riquadri di
dimensione diversa, e la validazione del dialogo di caricamento), nuovo
`test_rimozione_personaggio_mondo.py` (29/29). Un bug reale trovato
scrivendo i test dell'interfaccia (non della sessione precedente, di
questa: `wrap_dialog_actions` mette i pulsanti in `.actions`, non in
`.content`/`.controls` — l'albero di controlli percorso dai test non li
raggiungeva, corretto nel test stesso, nessun impatto sul codice
applicativo). Suite di regressione completa rieseguita (24 file): tutte
verdi tranne le stesse 2 cause pre-esistenti e note in `test_qr_scan.py`.

### 8e — Due correzioni successive, stessa giornata (2026-08-12)

Messaggio successivo di Davide, dopo aver riletto il riepilogo della voce
"8d": (1) conferma che il bug delle coordinate (voce 8d, punto 2) c'era
anche sulla mappa LOCALE, non solo su quella condivisa — "non me ne sono
accorto prima, va allineato anche quello"; (2) segnala un buco reale nella
sincronizzazione: dopo aver aggiunto "Rimuovi dal mondo" (voce 8d, punto
5), l'app del giocatore rimosso non lo sapeva finché non apriva Sezione
Mondi — principio generale dichiarato esplicitamente da Davide: **"le app
collegate devono mostrare gli stessi dati condivisi"**.

**1. Fix coordinate esteso a `ui/views/maps_view.py` (mappe locali).**
Stesso identico bug della voce 8d — punto 2 (pixel assoluti invece di
frazioni), ma con una complicazione in più: la vista locale ha DUE
riquadri indipendenti (pannello inline + schermo intero, `self._detail_
canvas`/`self._fs_canvas`) invece di uno solo, e una gomma con geometria
precisa (`_split_stroke_by_circle`, intersezioni cerchio-segmento) che
lavora in pixel assoluti. Soluzione: due dimensioni di riquadro tracciate
separatamente (`self._detail_box_size`/`self._fs_box_size`, ciascuna col
proprio `on_size_change`), `_redraw_canvas(canvas)` ora denormalizza
rispetto al riquadro DI QUEL canvas specifico (`_box_size_for()`) — i due
riquadri restano indipendenti, nessuno "vince" sull'altro. La gomma
("Tratto" e "Libera") denormalizza i punti dei tratti esistenti PRIMA di
fare la geometria (radius/intersezioni restano in pixel, coerenti con
l'unità di misura di `self._eraser_size`) e rinormalizza il risultato
subito dopo, prima di salvare — mai un mix di frazioni e pixel assoluti
nella stessa lista `self._strokes`. Nuovo `test_mappe_locali_coordinate.py`
(13/13): tratto allineato a due dimensioni di riquadro diverse sia inline
sia a schermo intero (verificato che i due NON si influenzano a vicenda),
gomma "Tratto" che cancella nel punto riscalato giusto invece che nel
vecchio valore assoluto, gomma "Libera" che rinormalizza correttamente il
pezzo di tratto rimasto dopo un taglio.

**2. `HomeView` ora sincronizza in background le istanze di mondo REMOTE
(2026-08-12).** Causa del buco: `HomeView._start_polling()`/`_poll_loop()`
esisteva già, ma è SOLO per più schede web sullo stesso DB locale (stesso
processo, "polling" tra sessioni), mai per la rete LAN — nessun
meccanismo aggiornava le istanze di mondo di un giocatore mentre stava
sulla Home (solo aprendo Sezione Mondi, che ha il proprio ciclo, o con
"Aggiorna il mio foglio" manuale). Aggiunto un SECONDO ciclo, distinto,
`HomeView._start_world_sync()`/`_stop_world_sync()` — stesso
`ui.components.background_sync.BackgroundSyncLoop` già in uso da
`WorldsView`/`MasterEncounterView`, gira su QUALUNQUE piattaforma (non
solo web, a differenza del polling esistente: qui è rete LAN vera, non
condivisione dello stesso DB), avviato da `_init_identity()` dopo la
risoluzione del `device_id`, fermato dallo stesso `stop_polling()` già
richiamato da `ui/app.py` prima di ogni navigazione. Ad ogni giro,
`HomeView._my_remote_world_ids()` trova i mondi in cui questo dispositivo
possiede un'istanza e che NON ospita (stesso principio di `WorldsView.
_start_detail_sync`: un mondo ospitato ha già il proprio DB come stato
autoritativo, sincronizzarlo non farebbe nulla), poi `world_sync.
resolve_backend_for_world`/`sync_replica` per ciascuno — stessa coppia di
funzioni già in uso ovunque nel Multiplayer per questo scopo, nessuna
logica nuova duplicata.

Effetto pratico immediato per "Rimuovi dal mondo": `_partition_
characters()` ora legge anche `characters.world_instance_archived` (prima
ignorato del tutto in questa vista) e sposta un'istanza rimossa dal
mondo in una TERZA sezione dedicata, "Rimossi dai mondi" — non più nel
gruppo del suo mondo, ma nemmeno tra i personaggi "locali" (richiesta
esplicita di Davide: "senza toccare ovviamente il personaggio in
locale" — `world_id` non viene mai azzerato, solo la sezione in cui la
card compare cambia). La card in quella sezione perde "Aggiorna il mio
foglio"/"Aggiungi a un mondo" (non è più un'istanza attiva) ma mantiene
Gioca/Esporta/Elimina — nessun dato toccato, nessuna funzionalità
rimossa. **Non implementato in questa sessione, deliberatamente fuori
scope** (Davide non l'ha chiesto): un modo per il giocatore di "riunirsi"
a un mondo dopo essere stato rimosso — oggi resta un'istanza archiviata
senza percorso di ripristino lato UI, da riprendere se richiesto.

`_list_signature()` include ora anche `world_instance_archived` (prima
solo `updated_at`/`world_id`/`owner_device_id`), così la rimozione
sposta sezione anche quando nessun altro campo della riga cambia nello
stesso giro.

Due nuovi file di test: `test_home_sync_rimozione_mondo.py` (14/14) —
`_my_remote_world_ids()` isolato (mondi ospitati esclusi, personaggi
locali/di altri dispositivi esclusi) e un vero round trip con host su
socket (il master rimuove un personaggio, la Home del giocatore lo
recepisce via `resolve_backend_for_world`/`sync_replica` reali, verificata
la sezione finale corretta) — più 5 nuovi controlli nella parte [7] di
`test_istanze_personaggio.py` (67/67, era 62/62) sulla partizione con
un'istanza archiviata. **Limite dichiarato nel test del round trip**:
stesso di sempre in questo sandbox, un solo DB condiviso tra "host" e
"giocatore" — non è simulabile uno stato "prima della sincronizzazione"
davvero diverso da quello dell'host (sarebbe la stessa riga fisica); la
parte verificata per intero è che `resolve_backend_for_world`/
`sync_replica` girino senza errori sulla rete vera e che la Home mostri
lo stato finale corretto. Trovato E CORRETTO nel test stesso (non nel
codice applicativo) un errore di setup: `world_repo.save_replica_world()`
fa un `INSERT OR REPLACE` sulla riga `worlds` che, con `PRAGMA foreign_
keys=ON`, cascade su `world_members` — chiamarla su un mondo che nello
stesso DB è ANCHE l'host vero cancellava la sua membership reale; il test
aggira il problema con un `UPDATE` diretto della sola colonna
`is_local_host`, mai riproducibile nell'app reale (lì i due DB sono
sempre fisicamente separati).

Suite di regressione completa rieseguita (26 file): tutte verdi tranne le
stesse 2 cause pre-esistenti e note in `test_qr_scan.py`.

---

## "Richiesta di rientro" — un personaggio rimosso torna nel mondo solo con l'approvazione del master (2026-08-12, sessione successiva)

Richiesta esplicita di Davide, che riprende direttamente il "fuori scope"
lasciato aperto nella voce sopra ("un modo per il giocatore di 'riunirsi' a
un mondo dopo essere stato rimosso... da riprendere se richiesto"): dare
la possibilità a un personaggio rimosso (espulsione via `member.kick` o
rimozione singola via `CMD_CHARACTER_INSTANCE_REMOVE`, 2026-08-12 stesso
giorno) di rientrare nel mondo, sia dalla scheda locale che lo ha
originato sia dalla sezione "Rimossi dai mondi", **mai in automatico**:
una richiesta che il master deve approvare, simmetrica all'ingresso in un
mondo via LAN (PIN + approvazione).

**Bug reale trovato prima di scrivere una riga di codice**: sia il
docstring di `character_repo.archive_world_instance()` sia il testo del
dialogo master "Rimuovi personaggio dal mondo" affermavano che l'istanza
"si riattiva da sola al primo resync del proprietario". Verificato con
grep sull'intero repo: **questo non è mai stato implementato**. Nessun
punto del codice scriveva mai `world_instance_archived=0` dopo
l'archiviazione — `import_replica_character()` rispecchia lo stato
dell'host così com'è (e l'host stesso resta archiviato), e
`create_or_resume_instance()`/`find_existing_instance()` trovava
l'istanza archiviata e la restituiva come "resumed=True" **senza**
toglierle l'archiviazione: un giocatore che ripeteva "Aggiungi a un
mondo" sullo stesso personaggio locale otteneva un successo silenzioso
ma il personaggio restava invisibile al master per sempre — esattamente
il "personaggio fantasma" che Davide ha chiesto di evitare fin dalla
richiesta iniziale. Corretti anche i due testi/commenti obsoleti che
affermavano il contrario.

**Punto sollevato da Davide in revisione del piano, decisivo per il
design**: "il personaggio rimosso rimane statico quindi non cambia,
quello che il giocatore ha in locale potrebbe cambiare rispetto a quello
rimosso in passato, magari sale di livello o viene cambiato qualcosa,
dobbiamo gestire questa cosa". Vero: l'istanza archiviata è congelata,
ma il personaggio locale di ORIGINE (`origin_character_id`, riga
separata) può nel frattempo essere cambiato dal giocatore, e le due righe
non si risincronizzano mai da sole in nessuna direzione. Scelta: la
richiesta di rientro porta un `mode`, deciso dal giocatore all'invio (mai
dal master) — `"frozen"` (default) riprende l'istanza esattamente come fu
archiviata; `"refresh_from_local"` sovrascrive il CONTENUTO (livello, PF,
inventario, incantesimi...) con lo stato ATTUALE del personaggio locale
di origine, preservando SEMPRE identità e collegamento al mondo
dell'istanza (mai quelli, vuoti, del personaggio locale esportato) —
disponibile solo se quel personaggio locale esiste ancora (il giocatore
può averlo cancellato nel frattempo).

**Schema**: nuova tabella `world_rejoin_requests` (stesso schema-gemello
di `world_change_requests`, ma verso opposto: qui propone il giocatore,
risponde il master), nuovo dataclass `WorldRejoinRequest`
(`data/models.py`). Nuove funzioni repository: `character_repo.
unarchive_world_instance()` (unico punto che toglie l'archiviazione per
`mode="frozen"`), `character_export.import_character_data_as_world_refresh()`
— sorella di `import_replica_character()` ma, a differenza di quella (che
LEGGE `world_id`/`origin_character_id`/`owner_device_id` dall'export e
rifiuta un export senza `world_id`, pensata per una vera replica di
rete), riceve questi tre campi come parametri espliciti e li sovrascrive
sempre con quelli dell'istanza bersaglio, indipendentemente da cosa
contiene l'export sorgente — pensata apposta per un export di un
personaggio LOCALE, forzando anche `world_instance_archived=0` nello
stesso `char_overrides`: un'unica scrittura transazionale fa
contenuto+riattivazione insieme, mai due passi separati. CRUD completo in
`world_repo.py` (`create_rejoin_request`/`get_rejoin_request`/
`get_pending_rejoin_requests`/`get_pending_rejoin_request_for_character`/
`save_replica_rejoin_request`/`resolve_rejoin_request`).

**Permessi** (`core/world_permissions.py`): due nuovi comandi,
`character_rejoin.request` (player-owned, verificato per proprietà come
`hp.self_update`/`character_instance.sync`) e `character_rejoin.respond`
(master/owner, come `change_request.propose` — incluso in
`CHARACTER_MUTATING_COMMANDS` per la rimaterializzazione su un terzo
dispositivo e in `MASTER_REMOTE_ACTION_COMMANDS` per lo stesso cooldown
per-personaggio a pillola già in uso per le altre azioni master).

**Handler** (`core/world_backend.py`): `_handle_character_rejoin_request`
— fail-closed su non-proprietario, non-archiviato, modalità invalida,
export mancante/malformato/non-locale, e guardia anti-duplicati (una sola
richiesta `pending` per personaggio alla volta).
`_handle_character_rejoin_respond` — due guardie trovate necessarie in
fase di progettazione, non nel design doc originale: (1) race — se
l'istanza risulta già non-archiviata quando arriva l'accettazione (es.
doppio accept da due dispositivi master), tratta come no-op e chiude
comunque la richiesta, mai un errore né una doppia scrittura; (2) race —
se il proprietario è stato espulso dal mondo DOPO l'invio della richiesta
ma PRIMA della risposta del master, l'accettazione viene rifiutata e la
richiesta chiusa come "expired" invece di riammettere un personaggio il
cui proprietario non è più membro (stato altrimenti incoerente).

**Sincronizzazione**: due nuovi rami in `world_sync.apply_event_to_replica`
(stesso pattern di `change_request.propose`/`respond`), inclusione nello
snapshot di ingresso (`network/host_server.py::handle_snapshot`,
`core/world_sync.py::_finalize_join`) filtrata per `requested_by ==
device_id` — più semplice del filtro `own_ids` usato per le richieste di
modifica, perché qui il device richiedente è già scritto direttamente
sulla riga. Cooldown lato invio: riusa il bucket condiviso
`network_request_last_at`/`NETWORK_REQUEST_COOLDOWN_S`, già usato per
ingresso in un mondo e `_push_instance_to_host` (stesso principio già
dichiarato da Davide: "tutte le richieste online da sincronizzare").

**`core/character_instances.py`**: `InstanceResult` guadagna un campo
`archived: bool` — quando `create_or_resume_instance()` trova un'istanza
esistente che è archiviata, NON restituisce più `resumed=True` in
silenzio (il bug del fantasma descritto sopra): `success=False`,
`archived=True`, `character_id` valorizzato con l'istanza trovata perché
il chiamante possa aprire subito il flusso di richiesta di rientro senza
un'altra ricerca.

**UI master** (`ui/views/world/world_view.py`): nuova sezione "Richieste
di rientro" in `_render_detail`, gated da
`perm.can_perform(my_role, perm.CMD_CHARACTER_REJOIN_RESPOND)` (master/owner
soltanto — a differenza di "Richieste in sospeso", non visibile a un
giocatore qualunque: qui è il master a dover decidere). Ogni riga mostra
la modalità scelta ("Riprende lo stato con cui era stato rimosso" /
"Aggiorna allo stato attuale della scheda del giocatore (Liv. N)", letta
dal payload della richiesta per trasparenza) e due pillole Accetta/Rifiuta
che riusano `_send_remote_command()` — stesso cooldown per-personaggio con
countdown visivo delle altre azioni master, nessuna scorciatoia.
Aggiornato anche il testo del dialogo "Rimuovi personaggio dal mondo" (non
più "si riattiva da solo").

**UI giocatore** (`ui/views/home_view.py`): un solo dialogo/helper
condiviso da entrambi gli entry point (`_open_rejoin_request_dialog`/
`_send_rejoin_request`), per non duplicare la logica di scelta-modalità +
invio + gestione errori/cooldown/duplicati in due posti. Entry point A —
la card di un personaggio in "Rimossi dai mondi" (`_character_card`,
nuovo parametro `is_removed`) guadagna un pulsante "Richiedi rientro nel
mondo", sostituito da uno stato disabilitato "Richiesta inviata, in
attesa del master" se esiste già una richiesta `pending`. Entry point B —
`_open_add_to_world_dialog._confirm`: se `create_or_resume_instance()`
ritorna `result.archived`, non apre più la scheda in silenzio, apre lo
stesso dialogo condiviso (qui `origin_character_id` coincide sempre con
`char.id` di partenza, quindi `refresh_from_local` è sempre disponibile).

Nuovo `test_character_rejoin.py` (68/68): handler (successo entrambe le
modalità, fail-closed, anti-duplicati, le due race guard), propagazione
di replica, `create_or_resume_instance` su un'istanza archiviata (verifica
esplicita che NON crei mai una seconda riga — "nessun personaggio
fantasma"), UI master (click reale su Accetta) e UI giocatore (pulsante e
stato "in attesa" con click reali sui controlli Flet). Suite di
regressione completa rieseguita (27 file, oltre 1500 controlli): tutte
verdi tranne le stesse 2 cause pre-esistenti e note in `test_qr_scan.py`
(dipendenza `pyzbar` mancante in questo sandbox, indipendente dal
codice).

---

## Passo 9 chiuso per intero — "Esportazione del mondo" (`.dndworld`, 2026-08-12, sessione successiva)

Richiesta esplicita di Davide ("procediamo a implementare il passo 9 fai
tutto senza chiedere l'autorizzazione, interrompi solo se ci sono delle
cose che dobbiamo decidere insieme"): chiude l'ultimo passo del piano dei
9 di `multiplayer_design.md` §13 — 9D (export/import `.dndworld`), 9E
(promemoria periodico) e 9F (UI), rimasti aperti dalla sessione dell'11.

**9D — `data/repositories/world_export.py`**, stesso principio di
`character_export.py` (introspezione schema via `PRAGMA table_info`,
"a prova di versione" in entrambe le direzioni) — non una seconda copia
della stessa logica: `export_world()`/`import_world()` importano ed
usano direttamente `_insert_row`/`_table_columns`/
`_write_character_and_children`/`CHILD_TABLES` da `character_export.py`
(funzioni già generiche, non specifiche del "personaggio" nonostante il
nome del modulo). Contiene: mondo, membri, TUTTE le istanze di
personaggio del mondo — **comprese quelle archiviate** (2026-08-12,
stessa sessione della "Richiesta di rientro" sopra: un backup non deve
mai perdere un personaggio rimosso, altrimenti la rimozione diventerebbe
silenziosamente definitiva al primo export/import — nuova
`character_repo.get_all_instances_of_world()`, a differenza di
`get_master_visible_characters()` che filtra `world_instance_archived=0`
apposta per la Sezione Master), giornale eventi, i due contenitori di
bottino, note del master, richieste di modifica E di rientro pendenti,
mappe condivise.

Stesse 3 modalità di `.dndchar` (nuovo/sovrascrivi/copia). In OGNI
modalità **questo dispositivo diventa l'owner/host del mondo da qui in
avanti** (§6.3: "chi importa diventa owner e ospita da lì in avanti") —
`_write_world_row()` è l'UNICA eccezione deliberata, oltre a
`create_world()`, all'invariante "nessuna funzione fuori da
`create_world()` impone `is_local_host=1`" (`world_repo.
save_replica_world`, §11.5 "due dispositivi non possono ospitare lo
stesso mondo"): un'importazione da file è un'azione esplicita
dell'utente per iniziare/riprendere a ospitare, mai un effetto
collaterale di sincronizzazione. `_write_members()` garantisce sempre un
solo `owner` (chi importa, promosso se già tra i membri esportati —
usando il NOME appena digitato nel dialogo, non quello vecchio del file
— o aggiunto come nuovo membro; l'eventuale vecchio owner retrocesso a
`master`, stesso schema a due passi già in uso in `_handle_transfer_
ownership`). "Sovrascrivi" ripulisce tutto ciò che viveva sotto quell'id
prima di riscrivere: `world_repo.delete_world()` già fa cascare
membri/eventi/richieste (FK dirette verso `worlds`), più 4 `DELETE`
espliciti per le tabelle che non hanno quella FK (`characters` —
cascade sulle proprie 12 tabelle figlio —, `loot_stash_entries`,
`master_campaign_notes`, `game_maps` condivise). "Copia" rigenera un id
per mondo/membri/personaggi/ogni riga collegata, con una mappa
vecchio→nuovo id dei personaggi riusata per rimappare correttamente i
riferimenti (`target_id` degli eventi, `character_id` delle richieste) —
mai lasciare un giornale copiato che punta a personaggi dell'originale.
`world_events.seq` (l'AUTOINCREMENT reale della tabella) non viene MAI
riportato da un file: omesso dalla riga prima di scriverla, un nuovo
valore viene assegnato da SQLite nell'ordine originale.

**9E — promemoria periodico**: il design doc lo segnava esplicitamente
come una delle tre tarature da "portare a Davide invece di decidere da
solo" (§12) — fermato con `AskUserQuestion` prima di scrivere il codice,
non deciso a tavolino. Scelta di Davide: eventi di giornale dall'ultimo
export riuscito (non calendario, non conteggio di aperture — "non
disturba se il mondo è fermo, avvisa quando c'è davvero qualcosa di
nuovo da perdere"), soglia 20 (valore medio tra le alternative
proposte). Nuova colonna `worlds.last_export_seq`
(`world_repo.mark_world_exported()`, chiamata SOLO dopo che il file è
stato scritto/scaricato con successo — mai su un export fallito).
**Bug reale trovato scrivendo il test di questa soglia**: `world_events.
seq` è l'autoincrement GLOBALE della tabella, condiviso da TUTTI i
mondi (non riparte da 1 per ciascuno) — la prima implementazione
calcolava "eventi dall'ultimo export" come `get_latest_event_seq(world)
- last_export_seq`, che per un mondo appena creato (`last_export_seq=0`)
dava il valore ASSOLUTO del contatore globale, già ben oltre soglia se
altri mondi avevano generato eventi prima. Corretto con
`world_repo.count_events_since(world_id, since_seq)` — un `COUNT(*)
WHERE world_id=? AND seq>?`, mai una sottrazione tra seq incomparabili.
L'avviso, quando compare, è un banner non bloccante nella sezione
"Backup del mondo" (mai un dialog che interrompe il flusso).

**9F — UI** (`ui/views/world/world_view.py`): nuova sezione "Backup del
mondo" (solo owner, prima della "Zona pericolosa") con la pillola
"Esporta mondo" e, quando la soglia è superata, il banner del
promemoria. "Importa mondo" nella lista dei mondi (pillola accanto a
"Crea"/"Unisciti"), con un dialogo che chiede il nome del master PRIMA
di procedere (stessa lezione già imparata il 2026-08-07 per "Unisciti
con un codice": mai un default silenzioso come "Master" per tutti) e,
se l'id del file collide con un mondo già presente, lo stesso dialogo
di conflitto (Copia/Sovrascrivi/Annulla) già in uso per `.dndchar`.

Per i dialoghi nativi del SO (salvataggio/apertura desktop, FilePicker
mobile, staging web) — **decisione di scope deliberata**: NON un
refactor di `home_view.py` (il codice per `.dndchar` è già in produzione
e confermato funzionante da Davide su macOS/Windows/Linux; un refactor
"a costo zero sulla carta" ha comunque un rischio reale su codice di
automazione OS così delicato, vedi i bug -1700/System Events già
risolti in passato). Estratta invece la logica GENERICA (parametrizzata
per titolo/filtro invece che scritta a mano per ".dndchar") in un nuovo
modulo `ui/file_export.py`, usato SOLO dal nuovo export/import del
mondo — zero rischio di regressione sul flusso esistente, base pronta
per il prossimo export/import che si aggiunga. Nuovo `ui/world_transfer.py`
(picker cartella condivisa per l'import web, mirror di
`character_transfer.py`).

Nuovo `test_esportazione_mondo.py` (78/78): export (struttura completa,
istanze archiviate incluse), import nelle 3 modalità (round trip fedele,
pulizia su sovrascrivi, id nuovi e referenze rimappate su copia),
validazione/fail-closed, UI (sezione Backup, flusso di import con nome
obbligatorio e conflitto, click reali sui controlli Flet), promemoria
(soglia superata/non superata, il bug del seq globale trovato e
corretto qui). Suite di regressione completa rieseguita (28 file, oltre
1500 controlli): tutte verdi tranne le stesse 2 cause pre-esistenti e
note in `test_qr_scan.py`.

Con questo il piano dei 9 passi di "Mondi condivisi / LAN party"
(`multiplayer_design.md` §13) è chiuso per intero. Resta, come per ogni
passo di questo piano, la verifica su Wi-Fi reale con dispositivi fisici
a carico di Davide — nessun test di sandbox può sostituirla (§15 del
design doc, DB separati non simulabili in modo affidabile qui).

---

## Multiclasse: selettore "quale classe sale?", limite a 2 classi, fix duplicazione trucchetti (2026-08-12, sessione successiva)

Tre bug report separati di Davide sulla Sezione Multiclasse appena
chiusa. **[1]** "Da manuale si può multiclassare solo con 2 classi
invece l'app mi permette di multiclassare più di 2 classi" — il
pulsante "Multiclasse" in `profilo_tab.py` non aveva mai un limite oltre
al tetto di livello 20. Corretto: si disabilita da solo (con tooltip
esplicativo) quando `character_repo.get_character_classes()` ha già 2
righe, più un controllo difensivo dentro `_on_add_multiclass_click`
stesso. **[2]** "Multiclassando mago... posso scegliere amicizia per
tutti e 3 gli incantesimi da scegliere" — i picker di trucchetto/
incantesimo del dialog "Aggiungi una classe" condividevano la stessa
lista di opzioni senza mai escludersi a vicenda. Corretto: ogni picker
dello stesso gruppo ora aggiorna le opzioni degli altri togliendo ciò
che è già stato scelto.

**[3] "quando multiclasso e clicco su level up deve farmi scegliere
quale classe aumentare"** — il più grosso dei tre: il pulsante "Level
up" saliva SEMPRE e solo la classe primaria, comportamento hardcoded fin
dalla prima sessione Multiclasse (§8.4 del design doc lo elencava
esplicitamente come prossimo passo). Nuovo `_show_level_up_class_picker()`
— un piccolo dialog "quale classe sale?" quando il personaggio ha più di
una classe — richiama poi `_on_level_up_click(e, target_class_name=...)`
parametrizzato invece che sempre sulla primaria. Rischio principale:
`_on_level_up_click` è una closure di ~2500 righe mai toccata prima
d'ora, motivo per cui la prima implementazione l'aveva evitata. Risolto
con `_LevelingClassView` (nuova classe in `profilo_tab.py`): una vista
che espone `class_name`/`subclass` della classe BERSAGLIO e delega ogni
altro attributo al `Character` reale — per la classe primaria è
letteralmente lo stesso oggetto (`lc = c`, zero rami nuovi, quindi zero
rischio sul percorso a classe singola/primaria, il caso ancora più
comune), per una secondaria isola le scritture di sottoclasse nella
vista e le persiste a parte con la nuova
`character_repo.set_character_class_subclass()` (mai su
`characters.subclass`, sempre quella della primaria). Trovato e corretto
nello stesso passaggio un bug preesistente: il calcolo del bonus PF
permanente di sottoclasse (Resilienza Draconica) usava il livello TOTALE
del personaggio come "livello precedente" invece del livello della
singola classe — innocuo per un personaggio a classe singola, già
sbagliato oggi per qualunque personaggio multiclasse che sale la
primaria.

`test_multiclasse.py` esteso da 45 a 61 controlli (level-up di una
secondaria via le stesse chiamate di repository, semantica della vista).
Suite di regressione completa rieseguita: tutte verdi tranne le 2 cause
pre-esistenti di `test_qr_scan.py`. Nessun accesso a screen recording in
questa sessione — il selettore di classe e il flusso di level-up
risultante non sono stati verificati visivamente, solo a livello di
repository/logica.

---

## Vista Incantesimi multiclasse — chiude il piano Multiclasse per intero (2026-08-12, sessione successiva)

Bug report di Davide: "la sezione incantesimi non viene correttamente
gestita in caso di multiclasse, tiene conto solo della classe
principale". Era l'ultimo punto esplicitamente fuori scope in
`multiclasse_design.md` §8.4/§3 punto 6, il più contro-intuitivo del
capitolo PHB (incantesimi/preparazione per classe, slot condivisi).

`SpellsView` (`ui/views/spells_view.py`) calcola ora `self._caster_rows`
(righe `character_classes` con una propria lista incantesimi) in
`__init__`. Quando ce n'è più di una, `_build()` imbocca un ramo
dedicato che rende una sotto-sezione "Incantesimi" per CIASCUNA classe
(`_build_caster_class_section`), ognuna col proprio banner di
preparazione/limite (`_section_prep_banner_mc`) e la propria lista
(`_section_spell_list_mc`/`_section_known_class_spell_list`), calcolati
sul livello e sulla caratteristica DI QUELLA CLASSE — mai il totale o
quella della primaria (PHB IT p.165). Anche CD/bonus attacco
(`_section_magic_header_mc`, via una nuova vista `_ClassAbilityView` che
espone solo `spellcasting_ability` e delega il resto al personaggio
reale) e il conteggio incantesimi conosciuti per le classi "know"
(`_expected_known_spell_count_for`) diventano per-classe. Corretta
contestualmente anche la sezione "Incantesimi Extra": prima escludeva
solo gli incantesimi della PRIMARIA, quindi il libro di un Mago preso in
multiclasse ci finiva dentro per errore invece che nella sua sezione
dedicata.

Stessa filosofia a basso rischio della sessione precedente: il percorso
a classe singola (`len(_caster_rows) == 1`, il caso più comune, comprese
le sottoclassi "casting preso in prestito dal Mago") resta **invariato
byte-per-byte** — stesse funzioni di sempre
(`_section_magic_header`/`_section_prep_banner`/`_section_spell_list`/
`_toggle_prepared`), mai toccate, tutto il nuovo codice isolato in
metodi `_mc`/nuovi separati.

Limiti noti, documentati (non blocchi): `max_prepared_spells_override`
resta unico per personaggio, non esposto nel ramo multiclasse (nessun
modo ovvio di applicarlo a due classi senza ambiguità); `known_spells`
non ha una chiave che includa la classe, quindi un incantesimo con lo
STESSO nome+livello posseduto da entrambe le classi (raro — "Cura
Ferite" 1° livello, Chierico e Paladino) condivide la stessa riga e
risulterebbe preparato in entrambe le sezioni insieme.

Nuovo test [10] in `test_multiclasse.py` (61 → 72 controlli): un
personaggio Chierico 5/Mago 3 verifica `_caster_rows`, `_build()` senza
eccezioni, che preparare un incantesimo di Mago non conti nel limite del
Chierico e viceversa, e la formula PHB per-classe (Chierico WIS16 Lv5 =
8, Mago INT14 Lv3 = 5). Suite di regressione completa rieseguita: tutte
verdi tranne le 2 cause pre-esistenti di `test_qr_scan.py`. Con questo il
piano Multiclasse (`multiclasse_design.md` §3, i 7 punti di logica) è
**chiuso per intero**.

---

## Sezione Master completamente world-scoped — NPC, Incontri, Bottino (2026-08-12, sessione successiva)

Bug report di Davide: "Nella sezione master le note, gli incontri,
oggetti bottino e npc (tutto) deve essere dipendente dal mondo, quindi
attualmente qualsiasi mondo seleziono vedo gli stessi incontri e la
stessa visuale per tutto. selezionare un mondo è come se entrassi in un
container con le sue cose." Le Note di Campagna erano già corrette dalla
sessione del 2026-08-06; NPC/Incontri/Bottino no — indagine con un
agente Explore dedicato prima di toccare codice, per mappare esattamente
cosa era già scoped e cosa no.

**NPC** (`master_npcs`): nessuna colonna `world_id` esisteva, né a DB né
nel modello Python — la rubrica era globale su tutto il dispositivo.
Aggiunta la colonna (migrazione), il campo su `MasterNpc`, e il filtro
per uguaglianza esatta in `master_repo.get_npcs()`/`create_npc()`/
`create_npc_from_monster()` (stesso principio già in uso per
personaggi/note/bottino: `""` = solo NPC locali, un id di mondo = solo i
suoi, mai un OR "mostra tutti"). Aggiornati tutti i punti di creazione
(form manuale, dal Bestiario, Genera Casuale) e i picker che leggono NPC
altrove (dentro Note di Campagna e dentro il tracker di un incontro).

**Incontri** (`master_encounters`): la colonna `world_id` esisteva già,
ma solo per il flag "visibile ai giocatori" del Tracker condiviso
(§6.5 di `multiplayer_design.md`) — mai per filtrare la lista o la
creazione. `get_encounters()`/`create_encounter()` ora accettano e
filtrano per `world_id`; aggiornati i 3 punti di creazione (lista
diretta, Generatore Incontri Casuali, Generatore per Ambiente).

**Bottino** (`loot_stash_entries`): il Deposito del Gruppo era già
scoped al mondo; l'Archivio privato del Master era per scelta di design
sempre `world_id=""`, indipendentemente dal mondo selezionato. Cambiato
su richiesta esplicita di Davide ("oggetti bottino" nominato
esplicitamente, e "tutto"): ora entrambi i contenitori seguono il mondo
selezionato — la privacy dell'archivio (mai sincronizzato/visibile ai
giocatori) resta un asse indipendente, invariata. Corretto un bug
collaterale in `_on_move` (spostare una voce tra archivio e deposito
azzerava il `world_id` invece di preservarlo).

**Esportazione del mondo** (`world_export.py`): gli NPC sono stati
aggiunti a `_WORLD_FLAT_TABLES` (stessa tabella "piatta" generica di
`loot_stash_entries`/`master_campaign_notes`, nessuna tabella figlio) —
un backup/trasferimento di mondo ora porta con sé anche la rubrica NPC.
Gli **Incontri restano esclusi**, limite noto e documentato: hanno una
tabella figlio propria (`master_encounter_members`) che richiederebbe lo
stesso trattamento dedicato di `characters`/`CHILD_TABLES`, fuori scope
in questo giro.

`test_master_world_scoping.py` esteso da 25 a 44 controlli (NPC/
Incontri/Bottino, due mondi diversi + "nessun mondo" mutuamente
esclusivi); `test_esportazione_mondo.py` esteso da 78 a 84 (round trip
degli NPC nelle 3 modalità di import). Suite di regressione completa
rieseguita: tutte verdi tranne le 2 cause pre-esistenti di
`test_qr_scan.py`.

---

## Rubrica NPC — Razza strutturata, tendine con "Altro", auto-riempimento Tipo/Taglia (2026-08-12, sessione successiva)

Bug report di Davide (screenshot del dialog "Modifica NPC"): un NPC
generato dal Generatore Rapido con razza nota (Sabina, Halfling) mostrava
"Tipo creatura"/"Taglia" vuoti quando si attivava "Ha statistiche di
combattimento" — causa profonda, non un bug del form: il Generatore forza
sempre `has_stat_block=False` quando il ruolo scelto non combacia con
nessuna delle 21 voci Appendice B, quindi quei campi non venivano mai
scritti. Il Master doveva ricordarsi a memoria che un Halfling è
Umanoide/Piccola e digitarlo a mano. Richiesta più ampia: ogni campo del
form NPC con un vocabolario D&D noto (non solo Tipo/Taglia) deve diventare
una tendina con le scelte valide + "Altro" in fondo per l'inserimento
manuale — confermata da Davide anche per i 4 campi multi-valore
(vulnerabilità/resistenze/immunità ai danni, immunità alle condizioni).

Pianificata in modalità Plan (due agenti dedicati: uno di ricognizione sul
form/generatore/dati esistenti, uno di progettazione dell'implementazione)
prima di scrivere codice, poi verificata a mano riga per riga contro il
codice reale.

Nuovo campo strutturato `MasterNpc.race` (migrazione DB) — popolato sia
dal Generatore sia dal form manuale. Per gli NPC già esistenti (come
Sabina), `core.npc_generator.resolve_race_from_tags()` estrae la razza dal
primo segmento CSV di `tags` a runtime, nessuna migrazione dati
necessaria. `update_npc()` la rende MODIFICABILE dopo la creazione (a
differenza di `world_id`) — un Master che scopre "in realtà è un
cambiaforma" deve poter correggerla.

Due nuovi componenti riusabili in `ui/widgets.py`, accanto a
`CardPicker`: **`DropdownAltro`** (tendina a scelta singola + "Altro" che
rivela un campo libero — un valore fuori dal vocabolario, es. dati
legacy, seleziona automaticamente "Altro" invece di perderlo) e
**`MultiSelectAltro`** (wrapper su `CardPicker(multi=True)` con una riga
"Aggiungi personalizzato" che accoda una nuova card già selezionata).
Applicati nel form NPC (`master_npc_list_view.py`) a Razza (nuovo,
9 razze PHB), Tipo creatura (14, nuova costante `settings.CREATURE_TYPES`
— nessun vocabolario canonico esisteva, `monsters.json` ha valori
incoerenti come "Non Morto"/"Non morto"), Taglia (6, `settings.SIZES`),
Allineamento (riusa `settings.ALIGNMENTS`, già in produzione per la
creazione PG), Grado di Sfida (`settings.CR_OPTIONS`) — e in
multi-selezione a Vulnerabilità/Resistenze/Immunità ai danni (13 tipi,
`settings.DAMAGE_TYPES_IT`, promossa da un dict locale duplicato dentro
`get_race_display_traits()`) e Immunità alle condizioni (14, riusa
`GameDataLoader.get_conditions()` — lo stesso catalogo PHB già usato dal
tracker di combattimento per applicare condizioni ai PG — mostrando anche
la descrizione ufficiale di ogni condizione come corpo della card).

Auto-riempimento (`core.npc_generator.resolve_creature_type_and_size()`):
quando si attiva "Ha statistiche di combattimento" (o cambia la Razza a
spunta già attiva), Tipo creatura/Taglia si compilano da soli — tutte e 9
le razze PHB sono Umanoidi (costante 5e implicita), la Taglia si legge da
`GameDataLoader.get_race(razza)["size"]`. Regola unica: scrive SOLO se il
campo è attualmente vuoto, non sovrascrive mai un valore che il Master ha
già impostato — verificato esplicitamente pilotando l'albero dei
controlli Flet reali (checkbox → auto-fill Umanoide/Piccola; modifica
manuale della Taglia + ri-toggle della spunta → resta quella scritta dal
Master, non l'auto-fill).

Nuovo `test_npc_race_autofill.py` (33 controlli: risoluzione
razza→tipo/taglia per tutte e 9 le razze, fallback da `tags`, round trip
DB inclusa la modificabilità post-creazione). A differenza delle sessioni
precedenti, qui è stato possibile verificare ANCHE l'auto-riempimento
visuale end-to-end (non solo la logica pura): pilotando direttamente
l'albero dei controlli Flet costruiti da `_open_npc_form` (checkbox,
dropdown, salvataggio) invece di solo la logica di repository, incluso un
salvataggio completo con persistenza corretta nel DB. Suite di
regressione completa rieseguita: tutte verdi tranne le 2 cause
pre-esistenti di `test_qr_scan.py`.

---

## Sessione bug report multipli + primitiva collassabile + oggetti magici personalizzati (2026-08-15)

Sei richieste distinte da Davide (screenshot + testo), pianificate in
modalità Plan (esplorazione parallela, poi progettazione, poi piano scritto
approvato con due giri di allargamento scope da parte di Davide durante la
revisione) prima di scrivere codice. Tutte verificate con l'app reale
costruita (non solo `py_compile`): 30 batterie di test esistenti rieseguite
verdi dopo ogni gruppo di modifiche, più smoke test dedicati per le parti
nuove (stat block collassabile su tutto il bestiario, flusso oggetto
magico personalizzato end-to-end incluso salvataggio in `loot_repo`).

**1. Chip multiclasse mancante in home** — `home_view.py::_character_card()`
leggeva `char.class_name` (solo classe primaria) invece di
`character_repo.get_class_display_string(char.id, char.class_name or "")`,
la funzione già esistente e già usata correttamente altrove
(`profilo_tab.py`) per produrre "Ladro 5 / Mago 3". Bug di sola UI: il dato
multiclasse era già completo e corretto a livello di repository/DB (vedi
`multiclasse_design.md` §8.4), semplicemente non letto in un punto. Fix a
una riga.

**2. Bardo, "Qualsiasi strumento musicale" non selezionabile** —
`data/game_data/classes/bardo.json`, scelta 3 dell'equipaggiamento
iniziale, aveva `item_type: "item"` per quella voce invece di un tipo
scelta dedicato (le scelte-arma nello stesso file usano già
`item_type: "weapon_choice"` + `category`). Aggiunto un nuovo tipo
parallelo `"tool_choice"` (dato: `category: "strumenti_musicali"`), con
rami paralleli a `weapon_choice` in tre punti di `wizard_view.py`
(oggetti fissi, scelte A/B via `_build_weapon_pickers()`, salvataggio in
`_save_item()`) e nel loro specchio `manual_form.py`, più
`creation_shared.py::_init_weapon_choice()` (metodo condiviso, un solo
punto invece di due). Fonte del vocabolario strumenti:
`GameDataLoader.get_tool_categories()["strumenti_musicali"]`, già
esistente e già usata per le competenze-strumento del Bardo — nessun
duplicato. `ui/widgets.py` (`format_equipment_item_body()`,
`equipment_option_card_options()`) esteso per non trattare `tool_choice`
come un oggetto letterale nel titolo/corpo della card. **Trovato durante
la revisione**: `core/character_instances.py` duplica (non può importare
`creation_shared.py`, che porta `import flet`, vietato in `core/*.py`) la
stessa logica per l'assegnazione equipaggiamento non interattiva di
un'istanza di personaggio "dal 1° livello" (`_weapon_choice_default()`/
`_assign_default_starting_equipment()`, usata dal Multiplayer) — senza
estenderla, un `tool_choice` avrebbe riprodotto lì lo stesso bug appena
corretto altrove (gap di correttezza reale, anche se non innescato dal
dato Bardo attuale: la sua scelta 3 risolve di default su `options[0]` =
"Liuto", non sull'opzione `tool_choice`). Esteso anche questo file,
verificato che il Bardo di default resta invariato ("Liuto", non ancora
uno strumento a scelta) e che la risoluzione `tool_choice` in isolamento
produce uno strumento valido del catalogo.

**3. Scroll bloccato in tutta Modalità Master** — segnalato da Davide
inizialmente solo su Bottino, poi esteso esplicitamente da lui a "tutte le
sezioni che usano quel tipo di layout" durante la revisione del piano.
Causa comune: `MasterView._content_area` non fornisce scroll di pagina,
quindi ogni tab doveva gestirselo da sé — e lo faceva con lo stesso
pattern sbagliato (header fisso fuori da un `ft.Column(scroll=AUTO,
expand=True)` che intrappola la lista in un riquadro con scroll
indipendente, invece di lasciar scorrere tutto insieme). Stesso fix
applicato uniformemente: rimosso `scroll`+`expand` dalla lista interna e
dal suo contenitore, spostato `scroll=ft.ScrollMode.AUTO` sulla vista
esterna. Toccati: `master_loot_view.py` (Bottino, segnalazione originale),
`master_npc_list_view.py` (Rubrica NPC), `master_encounter_list_view.py`
(Incontri, vista elenco — gestito anche il caso "incontro aperto",
`self.scroll` va disattivato in quel ramo per non annidare un secondo
scroll attorno a quello di `MasterEncounterView`), `master_encounter_view.py`
(tracker di combattimento, incluso il pulsante "+ Aggiungi Combattente" ora
dentro la stessa regione di scroll invece di restare pinnato),
`ui/views/magic_items_view.py` (tab Oggetti Magici — verificato che non ha
altri call site oltre a Modalità Master: la voce lato giocatore era già
stata rimossa in una sessione precedente, `2026-07-30`). **Nota di Campagna**
(`master_notes_view.py`) ha ricevuto un trattamento differenziato,
deliberato: è un layout master-detail a due pannelli, e sul desktop i due
pannelli scorrono ciascuno per conto proprio (pattern convenzionale,
diverso dal bug lamentato) — il fix è stato applicato SOLO al ramo mobile
(`_is_mobile=True`, un pannello alla volta), dove il layout collassava
nella stessa forma buggata delle altre tab; la variante desktop non è
stata toccata.

**4. Nuova primitiva `design.collapsible_section()`** — generalizza il
pannello "STRUMENTI MASTER" di `master_view.py` (`_build_tools_panel()`),
mai estratto come primitiva pur essendo pianificato fin dalla Fase A del
restyle (`restyle_design.md` documentava `section(collapsible=...)` come
"mai implementata, nessuna view l'ha richiesta"). API: `title_text,
content_builder, *, expanded=False, accent=None, level=1,
header_subtitle=None, on_toggle=None, alt=False` — stateless per design
(Flet ricostruisce le view da zero, quindi lo stato aperto/chiuso resta un
attributo di istanza nel chiamante, passato come `expanded=` e restituito
via `on_toggle(new_state)`, stesso principio già in uso per
`_tools_panel_expanded`/`set_mobile`). `master_view._build_tools_panel()`
migrato ad essa (comportamento invariato, verificato dal test esistente
`test_layout_incontri_e_pf_autosync.py` dopo aver aggiornato le 3 chiamate
al metodo rinominato `_toggle_tools_panel` → `_on_tools_panel_toggle`).
Applicata anche a `ui/components/monster_picker.py::build_stat_block_column()`:
le 7 sezioni facoltative (Tratti/Azioni/Reazioni/Azioni Leggendarie/Azioni
di Tana/Effetti Regionali/Varianti Opzionali) sono ora collassabili
singolarmente (Tratti aperta di default se presente, altrimenti Azioni,
tutte le altre chiuse) — dato che la funzione è pura (nessun `self`), il
toggle usa un `ft.Ref` locale per sostituire in place solo la sezione
toccata, senza ricostruire l'intero stat block. Verificato costruendo e
"cliccando" (simulando l'`on_click`) tutte le sezioni del mostro con più
sezioni facoltative del bestiario (DEMILICH, 5/5 sezioni). Estensione
collegata in `master_npc_list_view.py::_open_detail()`: le note/background
NPC lunghe (>180 caratteri o ≥3 righe) sono ora avvolte nello stesso
collassabile, chiuse di default.

**5. Oggetti magici personalizzati creati dal Master** — prima
`master_magic_item_generator_dialog.py` pescava solo dal Compendio
(264 voci ufficiali, sola lettura); nessun percorso per una voce
inventata dal Master esisteva. Aggiunta una modalità **"Personalizzato"**
allo stesso dialog (switch a due pillole in cima, stesso pattern di
`master_loot_view._build_kind_switch()`), invece di un secondo dialog
separato: un solo punto d'ingresso "ottieni un oggetto magico", casuale o
creato a mano, che riusa senza duplicazione le card di risultato e i
pulsanti azione già esistenti (Aggiungi all'inventario/Assegna…/Salva
nell'archivio). Form: Nome (libero), Categoria (`DropdownAltro` sulle
stesse `mig.get_category_options()` del generatore casuale + "Altro" per
categorie non standard), Rarità (tendina chiusa sui 6 bucket canonici,
niente "Altro" — è un valore che pilota filtri/colori altrove nell'app),
Richiede sintonia (checkbox + campo restrizione condizionale),
Descrizione/Effetto (libero, multilinea). Al salvataggio, `source_note`
usa lo stesso formato del generatore casuale ma con prefisso "Creato dal
Master" invece di "Generatore Oggetti Magici" — nessuna migrazione di
schema: `LootStashEntry` non ha mai avuto colonne dedicate a
rarità/categoria/sintonia, il generatore casuale le codifica già come
testo dentro `source_note`, la nuova modalità segue la stessa convenzione.
Verificato end-to-end con un fake `ft.Page` (pattern già in uso nei test
del progetto): switch di modalità, validazione campi obbligatori, "Crea
oggetto", "Assegna…"/"Salva nell'archivio" con verifica della riga
effettivamente scritta in `loot_repo` (`source_note` = "Creato dal Master
· Anello · Comune"), e round trip Personalizzato→Casuale→Genera per
confermare che la modalità casuale resta invariata.

**6. Bug trovato durante la revisione (non nel piano iniziale): menu a
tendina con sfondo semitrasparente scuro** — segnalato da Davide con
screenshot (il menu "Stato" in Note di Campagna si apriva come un riquadro
grigio/nero a bassa leggibilità, sovrapposto al campo sopra). Causa
sistemica, non specifica di un campo: `ft.Theme.dropdown_theme` in
`ui/theme.py` impostava solo `text_style`, mai `menu_style` — il popup di
OGNI `Dropdown`/`DropdownAltro` dell'intera app cadeva sul default
Material di Flutter (l'overlay di elevazione pensato per il tema scuro,
visibile anche in chiaro perché non deriva dalla palette dell'app). Fix in
un solo punto: `menu_style=ft.MenuStyle(bgcolor=p.surface,
shadow_color=p.shadow, elevation=8, shape=RoundedRectangleBorder(radius=
Radius.SM), side=BorderSide(1, p.border))` dentro `ft.DropdownTheme(...)`
— risolve tutti i Dropdown dell'app, entrambi i temi, senza toccare i
singoli call site. Dettaglio API in `regole_flet_api.md`.

File coinvolti (riepilogo): `home_view.py`, `data/game_data/classes/bardo.json`,
`wizard_view.py`, `manual_form.py`, `creation_shared.py`, `ui/widgets.py`,
`core/character_instances.py`, `master_loot_view.py`, `master_npc_list_view.py`,
`master_encounter_list_view.py`, `master_encounter_view.py`,
`magic_items_view.py`, `master_notes_view.py`, `ui/design.py`,
`master_view.py`, `ui/components/monster_picker.py`,
`master_magic_item_generator_dialog.py`, `ui/theme.py`,
`test_layout_incontri_e_pf_autosync.py` (3 chiamate aggiornate al metodo
rinominato). Suite di regressione completa rieseguita ad ogni gruppo di
modifiche: tutte verdi tranne le 2 cause pre-esistenti di
`test_qr_scan.py` (pacchetto `pyzbar` assente nel sandbox).

Tre voci del piano originale sono state verificate come **già risolte o
non applicabili**, non implementate di riflesso: la migrazione
`fantasy_card()` → `design.card()` nel wizard (il primo delega già al
secondo, nessuna differenza visiva/comportamentale residua); un
`set_mobile()` per `SheetView` (già gestito da `app.py::_show_main_layout()`,
che ricostruisce la scheda con `is_mobile` aggiornato ad ogni
attraversamento del breakpoint — un `set_mobile()` sarebbe stato codice
morto, dato che `_on_page_resize()` non lo avrebbe mai chiamato per il
layout principale); l'audit del padding nelle liste dense (già ai valori
compatti della scala `Space` — `Space.MD` in `master_npc_list_view.py`,
default `Space.LG` di `design.card()` in `home_view.py`, nessun valore
`Space.XL` fuori posto trovato sulle card di lista).

---

## Sessione tema scuro troppo saturo + campi tagliati nei form Master (2026-08-15)

Due bug report di Davide con screenshot nella stessa sessione.

**1. Tema scuro "troppo fluo"** — Davide: sfondo dei pannelli troppo
chiaro/contrastato rispetto al fondo pagina, colori d'accento troppo
saturi. Causa: `DARK` in `ui/design.py` non era mai stato ricalibrato
da quando esiste (i valori erano stati scelti per il minimo di
contrasto WCAG, non per l'intensità percepita). Rifatti tutti i token
che c'entrano, ricalcolando ogni rapporto di contrasto (non a occhio,
stesso metodo — relative luminance WCAG — già usato per la scelta
originale): `surface`/`surface_alt` riavvicinati a `bg` (`#1e1c26`→
`#17161a`, `#282533`→`#211f27`, ora 1.02:1 invece di 1.10:1 — quasi
indistinguibili in luminosità, i bordi restano l'unico segnale delle
card, `border` lasciato invariato apposta); `primary`/`magic`/
`warning`/`alert` desaturati e scuriti (`#f2696d`→`#de6165`,
`#7aa2f7`→`#7897db`, `#e0a028`→`#bd8c32`, `#f0873f`→`#d57d40`); i
riquadri tenui `note_bg`/`info_bg`/`success_bg` scuriti in coerenza.
Tutti i minimi documentati nel docstring di `Palette` restano rispettati
con margine (verificato: ogni accento ≥5:1 su `surface`/`bg`, `on_primary`
5.19:1 su `primary`, testo 15.3:1 su `surface`) — nessuna soglia
abbassata, solo meno saturazione/luminosità a parità di leggibilità.
`danger` e `nav_accent` seguono `primary` (erano già alias). Verificato
visivamente lanciando l'app in `FLET_WEB=true` con HOME isolata e
pilotandola con Playwright (headless Chromium, nessun `chromium-cli`
disponibile in questo sandbox) — schermata Modalità Master/Rubrica NPC
in tema scuro, sensibilmente più tenue del prima.

**2. Campi tagliati a destra nei form con statistiche creatura** — Davide,
screenshot del dialog "Modifica NPC": riga FOR/DES/COS/INT/SAG/CAR e riga
CA/PF Massimi/Formula PF uscivano dal bordo destro del dialog. Causa:
in `ui/views/master/master_npc_list_view.py::_open_npc_form()`, quattro
`ft.Row([...])` (tipo/taglia, CA/PF/formula, velocità/GS/PE, le 6 stat)
sommavano larghezze fisse dei campi superiori alla larghezza del dialog
(`responsive_dialog_width(page, 340)`), senza `wrap=True` — overflow
puro, non il gotcha "Row non-expand dentro Row unbounded" già
documentato in `regole_flet_api.md` (qui la catena Container→Column→Row
è correttamente vincolata, quindi `wrap=True` da solo basta). Fix:
aggiunto `wrap=True, run_spacing=N` alle quattro Row. Verificato con lo
stesso giro Playwright del punto 1: tutti i campi ora visibili, disposti
su più righe quando non entrano nella larghezza disponibile.

Lo stesso pattern (Row di 2+ campi a larghezza fissa dentro un dialog,
senza `wrap`) è stato cercato anche altrove su richiesta esplicita di
Davide ("assicurati che le dimensioni siano giuste anche nelle altre
schede") e corretto in altri 3 punti, stesso trattamento (`wrap=True,
run_spacing=`):
- `ui/views/master/master_encounter_view.py::_open_add_adhoc_dialog()`
  (dialog "Creazione Rapida" incontri) — riga CA/PF/PE e riga
  Iniziativa/DES.
- `ui/components/monster_picker.py::show_monster_picker()` — riga
  filtri Tipo/GS; questo file non aveva mai una `width=` esplicita sul
  contenitore del dialog (unico tra quelli toccati), aggiunta
  `responsive_dialog_width(page, 340)` sui tre punti dove viene
  assegnato `dlg.content` (import di `responsive_dialog_width` aggiunto,
  nessun import circolare con `ui/widgets.py`).
- `ui/views/character_sheet/combattimento_tab.py::_open_manual_creature_dialog()`
  ("Inserimento manuale" Forma Selvatica/Evocazione) — riga Tipo/GS e
  riga CA/PF; qui il dialog non ha mai avuto un contenitore a larghezza
  esplicita (divergenza strutturale rispetto agli altri form
  `creature_entries`, segnalata ma non risolta per intero — solo
  `wrap=True` aggiunto, meno rischio di overflow ma non lo stesso
  controllo puntuale della larghezza degli altri tre punti).

Suite di regressione rieseguita dopo ogni gruppo di modifiche
(`test_fase_4.py`, `test_fase_d.py`, `test_layout_incontri_e_pf_autosync.py`,
`test_regressione_wrap_expand.py`, `test_master_world_scoping.py`,
`test_npc_race_autofill.py`, `test_mappe_condivise_ui.py`): tutte verdi,
nessuna regressione.

**Seguito, stessa giornata — sfondo ancora "blu" e rosso da rifare
(bordeaux)**: secondo giro di bug report di Davide sullo stesso tema
scuro. Due richieste:

1. *"Lo sfondo mi sembra quasi blu, lo voglio nero opaco"* — `bg`/`bg_alt`/
   `surface`/`surface_alt`/`border`/`nav_bg`/`nav_border` in `DARK`
   (`ui/design.py`) avevano tutti una dominante blu-viola (tonalità
   ~250°) fin dalla primissima stesura del tema scuro, mai notata prima
   perché mascherata dal problema di saturazione degli accenti risolto
   nel giro precedente. Desaturati a tonalità neutra (~0-2% di
   saturazione residua) mantenendo la stessa luminosità:
   `bg` `#14131a`→`#161617`, `surface` `#17161a`→`#181818`, `surface_alt`
   `#211f27`→`#232224`, `nav_bg` `#0e0d13`→`#101010`,
   `nav_border`→`#2c2c2e`. `note_bg`/`info_bg`/`success_bg` NON toccati
   (la loro tinta calda/blu/verde è intenzionale, segnala la categoria
   del riquadro — non fa parte del difetto lamentato).
2. *"Il rosso non mi piace, bordeaux vino oppure il rosso originale
   scurito"* — Davide ha indicato un hex preciso per il bordeaux,
   `#8d2132`. Prima di applicarlo: audit completo (agente in background)
   di ogni uso di `design.T().primary`/`.danger` in `ui/` — **478
   occorrenze**, di cui **325 testo/icona/bordo** disegnate direttamente
   sul fondo scuro (bordi sinistri delle card, "Annulla", icone, campi
   attivi) contro solo **141 riempimenti** (bottoni/checkbox/badge) dove
   il bordeaux vero avrebbe funzionato. `#8d2132` puro contro il nuovo
   `surface` dà ~2:1 di contrasto — illeggibile nei 325 usi testo.
   Presentate a Davide (artifact di confronto, poi scelta via
   `AskUserQuestion`) due strade: singolo token schiarito quanto basta
   vs. doppio token (bordeaux vero solo nei riempimenti + un secondo
   token più chiaro per gli altri 325 punti, refactor su ~30 file).
   **Scelta: singolo token.** Nuovo `primary` (= `danger` = `nav_accent`,
   erano già alias) è `#d4596c` — stessa tonalità del bordeaux di Davide
   (hue 350.6°, calcolata da `#8d2132`), schiarito al minimo che regge
   4.5:1 su `surface`/`bg` (4.60/4.69), tutti gli altri minimi del
   docstring `Palette` restano rispettati (`on_primary` 4.7:1 sopra il
   nuovo `primary`). `on_primary` resta testo scuro (`#241012`, convenzione
   Material 3 per un accento di luminosità medio-bassa in dark mode).
   Verificato visivamente con lo stesso giro Playwright/`FLET_WEB=true`
   del punto precedente: nero neutro senza più dominante blu, rosso
   nettamente più "vino" che corallo, dialog "Modifica NPC" ancora
   integro. Suite di regressione rieseguita, tutta verde.

   Il colore `#8d2132` esatto di Davide non è quindi nel codice: è stato
   valutato e scartato come token unico per il motivo di contrasto sopra.
   Se in futuro si vuole il bordeaux vero nei bottoni/badge, resta
   disponibile la strada a due token già scartata qui (non implementata).

**Seguito, stessa giornata — quarto giro, "non corrisponde a quello visto
online" + un secondo hex bordeaux**: Davide ha bocciato `#d4596c` (troppo
tenue/rosato) e indicato un nuovo hex, `#761c2a` — ancora più scuro del
precedente (`#8d2132`, contrasto ~1.7:1 su `surface`, peggio di prima),
chiedendo esplicitamente più saturazione. Prima di applicare: verificato
che alzare la sola saturazione HSL a parità di luminosità minima per
4.5:1 non cambia praticamente nulla (`#d75469` vs il `#d4596c` già
scartato — differenza impercettibile), perché la leggibilità dipende
dalla luminanza, non dalla saturazione HSL. La causa vera del "non
corrisponde": la saturazione **HSL** non è percettivamente uniforme — a
`L` alta (necessaria per 4.5:1) la stessa "S" numerica appare più tenue
all'occhio. Ricalcolato in **OKLCH** (croma percettivamente uniforme)
sulla tonalità dei due hex di Davide (H≈17° OKLCH, coerente con l'hue
HSL ~350° di entrambi): stesso minimo di luminosità per 4.5:1 su
`surface`, ma croma alto (0.18) anziché vincolato dalla saturazione HSL.
Risultato: `primary`(=`danger`=`nav_accent`) `#d4596c`→`#e04f61` — 4.62:1
su `surface`/4.70:1 su `bg`, `on_primary` `#241012` sopra resta a 4.72:1.
Verificato visivamente con lo stesso giro Playwright: rosso nettamente
più vivo/saturo del tentativo precedente, sfondo nero neutro invariato.
Suite di regressione rieseguita (`test_fase_4.py`,
`test_layout_incontri_e_pf_autosync.py`, `test_master_world_scoping.py`),
tutta verde.

**Seguito, stessa giornata — quinto/sesto giro, screenshot reale +
sdoppiamento del token**: Davide ha mandato uno screenshot dell'app vera
(non un mockup) mostrando due problemi residui: (1) l'header di
`HomeView` e le card personaggio (entrambi `bgcolor=p.surface`) restavano
percepibilmente "più luminosi" del corpo pagina nonostante il rapporto
di contrasto surface/bg fosse già sceso a 1.02:1 nel giro precedente —
causa: un rapporto WCAG basso non garantisce che due riquadri PIENI
affiancati sembrino uguali all'occhio (simultaneous contrast), la
formula misura leggibilità del testo, non uniformità percepita tra due
campiture; fix: `surface`/`surface_alt` ora coincidono esattamente con
`bg`/`bg_alt`, header e card si fondono col fondo, la card resta
leggibile solo via `border` + ombra. (2) Il rosso "ancora non
corrisponde", con un terzo colore proposto (`#e04f61`, OKLCH) ancora
respinto.

Diagnosi definitiva sul rosso: qualunque tinta bordeaux scura a
sufficienza da sembrare "vino" e qualunque tinta chiara a sufficienza da
leggersi da sola sul nero (≥4.5:1) sono **incompatibili per costruzione**
— tre tentativi di schiaritura (uno HSL, uno a saturazione HSL massima,
uno OKLCH) lo confermano tutti. L'unica soluzione reale è quella
proposta e scartata due giri prima: **sdoppiare il token**. Aggiunti
`primary_fill`/`on_primary_fill`/`danger_fill` a `Palette`
(`ui/design.py`) — in light mode alias di `primary`/`on_primary` (nessun
cambiamento visivo), in dark mode `primary_fill = "#761c2a"` (il
bordeaux vero, ultimo hex di Davide) con `on_primary_fill = "#ffffff"`
(10.7:1 di contrasto — un riempimento scuro come questo ha sempre bisogno
di testo chiaro sopra, non scuro). `primary`/`danger` restano `#e04f61`,
invariati, per i 325 usi testo/icona/bordo.

Applicazione ai 141 call site di riempimento (bottoni pieni, badge,
checkbox, chip, barre di accento piene — lista esatta dall'audit di due
giri prima) fatta con due script Python mirati per file:riga esatti
(non un find&replace globale, per evitare di toccare i 325 usi testo che
dovevano restare invariati): un primo giro rinomina `.primary`→
`.primary_fill`/`.danger`→`.danger_fill` sui 141 punti già classificati
FILL; un secondo giro (20 punti aggiuntivi, trovati con un grep mirato
`bgcolor=/fill_color=...primary_fill` seguito da `color=/check_color=
...on_primary` entro 2 righe) rinomina il testo abbinato sopra quei
riempimenti in `.on_primary_fill` — questi non erano nella lista
originale perché su una riga diversa da quella con `.primary`/`.danger`
(es. `ButtonStyle(bgcolor=..., \n color=p.on_primary)` su due righe). Due
righe di `design.py` stesso (`card()`/`collapsible_section()`, barra di
accento piena) sistemate a mano perché le modifiche di questo stesso
file nei giri precedenti avevano spostato i numeri di riga rispetto
all'audit. `pill()` (design.py) e i suoi call site senza `color=`
esplicito **non** toccati — restano sul `primary` chiaro quando
`filled=True`, non è un bug (sempre leggibile), solo meno scuro dei
bottoni espliciti; unica eccezione già nell'audit,
`world_view.py:303` (`pill(..., filled=True, color=p.primary)`), portata
a `primary_fill` insieme al resto.

Verificato: sintassi + import di tutti i 34 file toccati OK, suite di
test completa rieseguita (tutti i file `test_*.py`) — verde ovunque
tranne il limite noto di `test_qr_scan.py` (pyzbar assente nel sandbox,
non una regressione). Verificato visivamente con lo stesso giro
Playwright/`FLET_WEB=true`: header e corpo pagina uniformemente neri
senza cuciture, "Wizard guidato"/"Nuovo Personaggio" ora nel bordeaux
scuro vero, logo/bordi/pillole outline nel rosso chiaro invariato.

**Seguito, stessa giornata — settimo giro, rifinitura finale**: Davide,
soddisfatto dell'impianto (pulsanti bordeaux + fusione header/corpo), due
ultime richieste di rifinitura:

1. *"Scurisci anche i testi rossi"* — `primary`/`danger` (`#e04f61`,
   325 usi testo/icona/bordo) andavano scuriti. Stesso vincolo di
   sempre (≥4.5:1), ma questa volta calcolato **contro il peggiore dei
   due fondi**: con `surface` diventato più chiaro di `bg` nel punto 2
   sotto, un primo tentativo scurito solo contro `bg` (`#d35561`) falliva
   su `surface` (4.16:1) — errore preso e corretto prima di consegnare.
   Ricalcolato in OKLCH contro entrambi i fondi → `#da5b67` (croma 0.16
   contro 0.18 di prima), 4.50:1 su `surface`/4.89:1 su `bg` — il minimo
   raggiungibile restando "rosso" e non un grigio-mauve desaturato
   (verificato: croma più basso scende oltre in luminosità ma perde il
   carattere di rosso). Limite tecnico dichiarato a Davide: non si può
   scurire oltre restando sia rosso sia leggibile da solo sul nero.
2. *"Lo sfondo va bene ma lasciamo un po' di distacco, con un grigio
   molto scuro"* — la fusione totale `surface = bg` del giro precedente
   andava bene nell'insieme ma Davide voleva un po' di gerarchia visiva
   indietro, con un **grigio puro** (0% saturazione — a differenza di
   ogni tentativo precedente, mai stato un vero neutro) invece di
   nessuna differenza o di una tinta. `surface`/`surface_alt` ora sono
   valori neutri indipendenti (`#1e1e1e`/`#242424`, non più derivati da
   `bg`+delta): 1.08:1/1.11:1 su `bg` — percettibile ma minimo,
   deliberatamente diverso dal precedente `#181818` (1.02:1, quasi
   invisibile) che aveva contribuito al problema del giro prima ancora.
   `parchment`/`parchment_alt` aggiornati in coerenza.

Verificato: sintassi + import OK, suite di test completa rieseguita
(verde ovunque tranne il limite noto `test_qr_scan.py`/pyzbar).
Verificato visivamente: header con un gradino di grigio percettibile ma
sobrio sopra il corpo pagina, testo/bordi rossi visibilmente più scuri,
pulsanti bordeaux invariati.

**Seguito, stessa giornata — ottavo giro, terzo token per icone/testo
grande**: Davide, con esempi concreti — il titolo "D&D" (48px bold) e i
pulsanti icona "Elimina scheda"/"Avvia scheda" sulla card personaggio
(`home_view.py`) restavano "troppo chiari", li voleva vicini al bordeaux
dei pulsanti pieni. Novità rispetto ai giri precedenti: per queste due
categorie **non serve davvero il 4.5:1** di `primary` — WCAG 1.4.3
("large text": ≥18pt, o ≥14pt bold — il titolo "D&D" qualifica) e 1.4.11
("graphical objects": icone isolate come i due bottoni citati) richiedono
solo **3:1**, non 4.5:1. Aggiunto un terzo token, `primary_icon`
(= `danger_icon`) — in dark mode `#bf384b` (OKLCH stesso hue ≈17°,
croma 0.17, calcolato al minimo che regge 3:1 su ENTRAMBI `surface`/`bg`
con margine 0.08 sopra il pavimento esatto), percettibilmente più scuro
di `primary` (`#da5b67`) pur restando "rosso" e non un grigio-mauve; in
light mode alias di `primary` (nessuna soglia diversa da rispettare lì).
`primary`/`danger` (4.5:1, testo scorrevole/paragrafi) **non toccati**.

Applicato a 61 punti trovati con un grep mirato su due pattern esatti
(`icon_color=....primary/.danger` e `ft.Icon(..., color=....primary/
.danger)` — sottoinsieme circoscritto e verificabile dei 325 usi
testo/icona/bordo, non l'intera lista) più il titolo "D&D" a mano
(`home_view.py`). Nota tecnica sul primo tentativo di script: un filtro
`grep -v "_icon"` per escludere i punti già convertiti ha inizialmente
scartato per errore righe legittime contenenti la sottostringa "_icon" in
un nome di funzione non correlato (`_category_icon(category)`, in
`magic_items_view.py`) — trovato e corretto prima di applicare lo script
definitivo, che usa `\b` (confine di parola) invece di un filtro a
sottostringa.

Verificato: sintassi + import di tutti i file toccati OK, suite di test
completa rieseguita — verde ovunque (un fallimento isolato di
`test_fase_4.py` su un controllo legato a un tiro di dado casuale si è
rivelato preesistente/instabile, non una regressione: confermato con 5
riesecuzioni consecutive tutte verdi). Verificato visivamente creando un
personaggio di prova nella replica web: titolo "D&D" e icone play/elimina
sulla card ora percettibilmente più scuri, badge "Liv. N"/pulsanti pieni
invariati.

---

## Multiplayer, test reali round 3 — tiri salvezza contro morte, sync live Incantesimi/Mappe, incantesimi bonus duplicati, note/mappe fuse nelle sezioni esistenti, riconnessione dopo riavvio host (2026-08-16)

Terzo giro di bug reali dopo i fix dei round 1/2 (§ sopra), riportato da
Davide dopo un'altra sessione di test su Wi-Fi reale (master su PC,
giocatore su smartphone). Nove problemi in un unico report, tutti con
causa concreta trovata leggendo il sorgente (nessuna ipotesi campata in
aria). Piano completo, decisioni e verifica dettagliata:
`/Users/davide/.claude/plans/multiplayer-lan-funziona-e-harmonic-stroustrup.md`
(se ancora presente sul disco — copiare il contenuto rilevante qui se
sparisce, è il riferimento più preciso per questo round).

**G1a — il pip di un tiro salvezza contro la morte segnato a mano
spariva o riappariva in ritardo.** `core/world_sync.py::apply_event_to_replica`
forzava un reimport completo del personaggio
(`_resync_character_from_host`) anche per l'ECO del proprio
`CMD_HP_SELF_UPDATE` — il comando che il giocatore stesso invia dopo un
click. Fix: quando `event.kind == perm.CMD_HP_SELF_UPDATE` e
`event.actor_device_id` coincide con `remote_backend.device_id`, il
reimport viene saltato (è l'eco di una modifica già scritta in locale
PRIMA di essere spedita, non porta mai informazione più fresca).

**G1b — i pallini dei tiri salvezza restavano bloccati dopo una cura
del master a distanza.** `core/world_backend.py::_handle_hp_heal`
scartava il valore di ritorno di `damage_rules.apply_heal()` e non
chiamava mai `character_repo.update_death_saves(...)` quando
`outcome.death_saves_reset`, a differenza del gemello
`_handle_hp_damage`. Fix: una riga, stesso pattern del gemello.

**G2 — Incantesimi/Mappe non si aggiornavano mai da soli.**
`ui/views/spells_view.py`/`ui/views/maps_view.py` sono sezioni di primo
livello nella sidebar (non tab di `SheetView`) e non avevano MAI avuto
un `BackgroundSyncLoop` (`ui/components/background_sync.py`) — se il
giocatore restava su "Incantesimi" o "Mappe" senza mai passare da
Home/Mondo/Scheda, nessun evento veniva scaricato finché non navigava
altrove e tornava. Fix: aggiunto lo stesso pattern già maturo in
`sheet_view.py::_start_world_sync`/`_stop_world_sync` a entrambe le
viste. Contestualmente, la `signature_fn` di TUTTE le viste multiplayer
(incluso `sheet_view.py`) è stata unificata su
`world_repo.get_world(world_id).last_synced_seq` (mantenuto da
`sync_replica()`) invece di elencare campo per campo cosa "conta" come
cambiamento — più robusto, un futuro campo dimenticato non serve più
essere aggiunto a mano ovunque.

**G3 — il master poteva concedere lo stesso incantesimo bonus due
volte.** `ui/views/world/world_view.py::_open_bonus_spell_dialog` non
confrontava mai con `character_repo.get_known_spells(character.id)`.
Fix: calcolo di `known_names` fresco all'apertura del dialog, badge
"Già posseduto" sulle opzioni corrispondenti in
`ui/widgets.py::spell_card_options` (nuovo parametro `known_names`) —
nessun blocco rigido, solo un flag visibile (richiesta esplicita di
Davide).

**G4 — note/mappe condivise dal master non comparivano mai lato
giocatore, o solo con refresh manuale.** Fusione richiesta esplicitamente
da Davide: niente più sezione dedicata "condivisa dal master", gli
elementi condivisi vanno DIRETTAMENTE nella lista già esistente di
note/mappe del giocatore con un'etichetta "Condiviso dal Master".
Implementato in `ui/views/diary_view.py` (note, `CATEGORIES` esteso con
`event`/`secret` per allinearsi a `MasterCampaignNote.category`) e
`ui/views/maps_view.py` (mappe, `_map_card()` mostra il chip e instrada
al solo "Apri" in sola lettura per `gm.character_id != self.character.id`).
**Nota importante emersa DOPO questo fix (vedi round 4 sotto): qui la
causa della mancata sincronizzazione era stata attribuita solo
all'assenza di una `signature_fn` sensibile — parzialmente vero, ma non
la causa più profonda**, trovata solo nel round successivo.

**G5 — il LED di connessione nella scheda personaggio (tab Profilo)
restava congelato invece di passare a rosso quando l'host non era più
raggiungibile.** `sheet_view.py::_start_world_sync._apply()` aggiornava
`self._connection_state` solo nel ramo di successo, nessun `else`. Fix:
aggiunto lo stesso ramo `else: ... = "disconnected"` già presente in
`home_view.py`/`world_view.py`.

**G6 — riconnessione bloccata dopo che il master ferma e riavvia
l'hosting (il PIN cambia).** Causa doppia:
- Host: `WorldHostServer.stop()` (`network/host_server.py`) svuota
  `_tokens` e rigenera il PIN ad ogni `start()` — per progetto, ma
  `handle_join()` richiedeva PIN corretto ANCHE per un dispositivo già
  membro noto (`world_members`, persistito su DB, mai svuotato da
  `stop()`).
- Client: `core/world_sync.py::resolve_backend_for_world` non ritentava
  mai in automatico se `reconnect_with_token` falliva.

Fix (implementa la "registrazione" richiesta da Davide): in
`handle_join()`, il lookup `world_repo.get_member(...)` è stato spostato
PRIMA del controllo PIN — un dispositivo già membro rientra col solo
`join_code`, PIN non più richiesto; un dispositivo nuovo continua a
richiedere sia codice sia PIN (invariato). In
`resolve_backend_for_world`, quando `reconnect_with_token` fallisce e
`world.join_code` è valorizzato, retry automatico via
`start_lan_join(host, port, world.join_code, "", device_id, "")`. Nota
di sicurezza esplicitamente segnalata a Davide: il `join_code` (6
caratteri) diventa da solo sufficiente per un dispositivo già approvato
per rientrare indefinitamente — l'unico modo di revocare l'accesso resta
l'espulsione esplicita del membro.

Verificato: sintassi + import OK su tutti i file toccati, suite di test
completa (`test_*.py`) verde tranne il limite noto `test_qr_scan.py`
(pyzbar assente nel sandbox). Verifica su dispositivi reali: **round 4
sotto**, alcuni di questi fix confermati insufficienti/parziali sui dati
reali di Davide (mondo con molte sessioni di test accumulate).

File toccati: `core/world_sync.py`, `core/world_backend.py`,
`network/host_server.py`, `ui/views/spells_view.py`,
`ui/views/maps_view.py`, `ui/views/character_sheet/sheet_view.py`,
`ui/views/diary_view.py`, `ui/views/world/world_view.py`, `ui/widgets.py`.

---

## Multiplayer, round 4 — note/mappe condivise ancora bloccate ("si vede solo 1 nota e 1 mappa"): causa reale trovata e corretta (2026-08-16, sessione successiva)

Davide riporta dopo aver testato il round 3: tutto confermato TRANNE
note/mappe condivise. Sintomo esatto, in tre messaggi progressivi:
1. "le mappe già esistenti non vengono visualizzate se il giocatore
   entra dopo che la mappa sia già condivisa, le note condivise non si
   sincronizzano... si è sincronizzata solo una nota in eventi".
2. "è come se ci fosse un limite, mi fa vedere una sola nota e una sola
   mappa delle già presenti, non mi carica le altre... rimane solo
   quella nota e quella mappa" — anche condividendone di nuove.
3. Con screenshot: stesso identico comportamento **sia** in Diario
   (sezione appena aggiunta nel round 3) **sia** in Sezione Mondo
   (`WorldsView`, codice NON toccato nel round 3) — indizio chiave: due
   viste indipendenti che condividono solo la stessa chiamata di rete.
   Inoltre, correzione di posizionamento: le note condivise devono stare
   nella sezione sidebar "Diario" (`ui/views/diary_view.py`), MAI nel tab
   "Diario" interno alla scheda personaggio
   (`ui/views/character_sheet/diario_tab.py::DiarioTab`) — un primo
   tentativo le aveva messe nel posto sbagliato per errore, poi
   completamente revertito (vedi il docstring di `DiarioTab`, righe 27-32,
   che spiega esplicitamente perché quel tab NON deve avere note
   condivise).

**Causa reale #1 — `sync_replica()` non richiamava mai il refresh dello
snapshot quando non c'erano eventi incrementali nuovi.**
`core/world_sync.py::sync_replica` (riga 459) aveva un `if not events:
return 0` che saltava ANCHE `_refresh_members_from_snapshot` (allora
usata solo per i membri) — condizione fin troppo comune in stato
stazionario. Fix: rinominata in `_refresh_snapshot_derived_state` (riga
511) ed estesa a note/mappe condivise (non solo membri), ora chiamata
INCONDIZIONATAMENTE da `sync_replica` quando `refresh_members=True`
(default) — riusa gli stessi scrittori (`master_repo.save_replica_note`,
`maps_repo.replica_create_map_stub`) già usati da `_finalize_join()`.

**Verifica di questo primo fix**: costruito un diagnostico a due
PROCESSI/due DATABASE separati (`multiprocessing.get_context("spawn")`,
ciascun processo con il proprio `HOME` prima di ogni accesso al DB) —
a differenza della suite `test_note_sharing.py`/`test_mappe_condivise.py`
esistente, che gira tutto in un solo processo/un solo DB e quindi non
verifica mai una VERA scrittura sulla replica di un "secondo
dispositivo". Risultato: 3 note/3 mappe scaricate al join, 4/4 dopo un
successivo `sync_replica()` — il meccanismo di base funziona
correttamente con dati freschi. **Questo NON bastava sui dati reali di
Davide** (vedi sotto).

**Causa reale #2 (quella vera, trovata dopo che Davide ha confermato che
il fix #1 da solo non risolveva) — `handle_snapshot()` poteva fallire
per intero per un singolo dato residuo, bloccando TUTTO per sempre.**
`network/host_server.py::handle_snapshot` (riga 597) costruiva
note/incontro-visibile/mappe condivise in un unico blocco, senza
protezione. Se un SOLO elemento aveva un dato incoerente (residuo di
mesi di sessioni di test sullo stesso mondo — l'indizio forte: Davide
riusa lo stesso mondo/DB per ogni round da settimane), l'intera risposta
HTTP falliva con 500 — non solo quella sezione, TUTTA la risposta,
inclusi membri e personaggi. E poiché dal fix #1 sopra `sync_replica()`
richiama questo endpoint ad OGNI ciclo (circa ogni 2s, non solo al
join), un singolo dato rotto blocca per sempre ogni sincronizzazione
successiva su TUTTE le sezioni — il dispositivo resta congelato
esattamente allo stato del primo ingresso riuscito. Spiega perfettamente
"vedo sempre e solo la stessa 1 nota e la stessa 1 mappa, sia in Diario
sia in Sezione Mondo".

Fix: isolamento per sezione in `handle_snapshot()` — le tre sezioni
(note, incontro visibile, mappe condivise) sono ciascuna nel proprio
`try/except Exception as e: logger.error(...)`, degradando a
vuoto/`None` invece di far fallire l'intera risposta. Stessa protezione,
elemento per elemento, lato client in
`_refresh_snapshot_derived_state()` (`core/world_sync.py`, righe
511-557 circa) — un singolo dato rotto nel loop di note/mappe non
interrompe più gli elementi successivi dello stesso batch.

**Causa reale #3 (trovata ancora dopo, stesso principio ma nel punto di
INGRESSO invece che nella sincronizzazione periodica) — `_finalize_join()`
aveva lo STESSO identico problema, mai protetto prima.**
`core/world_sync.py::_finalize_join` (riga 714) — la funzione che semina
la replica al primo ingresso — iterava su personaggi/richieste di
modifica/richieste di rientro/note/incontro visibile/mappe in loop NON
protetti. Un'eccezione su un singolo elemento interrompeva l'intera
funzione con un'eccezione non gestita **dopo** che
`world_repo.save_replica_world(world)` (riga 749) aveva già scritto la
riga del mondo sulla replica locale — quindi l'eccezione risaliva fino
al chiamante (vedi round 5 sotto) SENZA che nessuno la intercettasse,
ma il mondo restava comunque "mezzo registrato" sul dispositivo del
giocatore. Fix: stessa protezione per-elemento (try/except + log)
applicata a tutti e 6 i loop di `_finalize_join` (personaggi, richieste
di modifica, richieste di rientro, note, incontro visibile, mappe) — commit
`9b8243e` ("Isolate errors during replica sync").

Verificato: sintassi + import OK, suite di test completa verde (29/30,
`test_qr_scan.py` limite noto ambientale). **Questo fix ha risolto la
sparizione delle note/mappe MA ha fatto emergere un problema NUOVO e più
grave, ancora aperto — vedi round 5 sotto, che è il lavoro da riprendere.**

File toccati: `core/world_sync.py`, `network/host_server.py`.
Commit: `15fb5d8` (fix #1 + spostamento note condivise fuori da
`DiarioTab`), `9b8243e` (fix #2 + #3, isolamento per sezione/elemento).

---

## Multiplayer, round 5 — APERTO: giocatore bloccato nel dialogo di ingresso dopo l'approvazione del master, "Copia del personaggio non riuscita" (2026-08-17)

> **Questo è il problema da riprendere in una nuova sessione.** Le sezioni
> sopra (round 3-4) sono confermate/comunque migliorative; QUESTO è
> l'unico bug ancora aperto e senza conferma finale di Davide. Leggi
> tutto questo paragrafo prima di toccare codice — sono già stati
> scartati diversi tentativi/ipotesi, dettagliati sotto per non
> ripeterli.

### Sintomo, esattamente come riportato da Davide (due messaggi in sequenza)

**Primo messaggio** (dopo aver rebuildato con il fix del round 4 sopra,
commit `9b8243e`): "adesso... la richiesta arriva subito al master, il
master la accetta e il giocatore rimane bloccato, non può premere su
annulla su entra e su prova di nuovo. A quel punto riavvio l'app e mi
ritrovo il mondo a cui ho fatto l'accesso, ma quando provo a far entrare
un personaggio del mondo mi esce il messaggio copia del personaggio non
riuscita." — quindi: (a) il dialogo di ingresso lato giocatore si
blocca DAVVERO, bottoni compresi, non solo "resta in attesa"; (b) dopo
riavvio dell'app il mondo risulta comunque già registrato/membro; (c)
tentare di portare un personaggio locale esistente in quel mondo fallisce
sempre con "Copia del personaggio fallita" (`InstanceResult.error`,
`core/character_instances.py`).

**Fix intermedio applicato** (commit `9bd2584`, "Run finish_pending_join
in background thread") — causa trovata con certezza per il punto (a):
`ui/views/world/world_view.py::_open_lan_join_dialog._poll_pending_join_loop`
(riga 3468, ciclo automatico ogni `_PENDING_JOIN_POLL_INTERVAL_S = 3.0`
secondi, riga 94) e `_retry` (riga 3608, pulsante "Controlla di nuovo")
chiamavano `world_sync.finish_pending_join(...)` — funzione SINCRONA e
bloccante (rete + molte scritture SQLite dentro `_finalize_join`, una
per ogni nota/mappa/personaggio dello snapshot, appena resa più lenta
dal fix del round 4 che non abbandona più al primo elemento rotto ma
prova ognuno) — DIRETTAMENTE dentro una coroutine che gira sull'UNICO
thread asyncio di Flet (confermato leggendo
`.venv/lib/python3.13/site-packages/flet/controls/base_control.py:485-530`:
un handler sincrono viene chiamato inline, `await`ato direttamente sullo
stesso loop che processa i click). Una chiamata bloccante lì congela
LETTERALMENTE tutta la pagina, bottoni compresi, per tutta la sua
durata — non solo questo dialogo. Su un mondo con tanta storia
accumulata, la somma di più scritture (specialmente se in attesa di un
lock SQLite conteso da un altro `BackgroundSyncLoop` attivo sullo stesso
dispositivo, es. per un ALTRO mondo di cui Davide è già membro da round
di test precedenti) può arrivare a durare svariati secondi consecutivi —
abbastanza da sembrare bloccato per sempre. Fix: entrambe le chiamate ora
passano da `await asyncio.to_thread(world_sync.finish_pending_join, ...)`
— stesso principio già usato da `BackgroundSyncLoop`
(`ui/components/background_sync.py`, thread dedicato + `page.run_task()`
per il ponte verso il loop asyncio, mai il contrario). `_retry` è
diventata `async def` (Flet supporta nativamente handler `async def`,
stessa fonte sopra).

**Secondo messaggio, DOPO questo fix intermedio** (conferma parziale, il
problema resta): "I problemi sono sempre gli stessi, il giocatore rimane
bloccato anche dopo l'accettazione del master, solo che adesso mi fa
premere annulla e tornare alla schermata iniziale. riavvio l'app e il
mondo è visibile da parte del giocatore e ci fa parte, ma esce comunque
impossibile copiare personaggio." — quindi il fix `9bd2584` ha
**confermato risolto** il freeze letterale dell'interfaccia (Annulla ora
risponde), ma **NON** ha risolto il problema di fondo: il dialogo non
arriva mai a uno stato di successo visibile (né un errore leggibile né
la chiusura automatica con `_open_detail`), Davide deve comunque
annullare ed è comunque costretto a riavviare l'app per vedere il mondo
come membro. E "copia del personaggio non riuscita" **persiste sempre**,
non in modo intermittente.

### Diagnosi già fatta, ipotesi già scartate — NON ripartire da zero

1. **Contesa SQLite transitoria (lock)** come causa sia del freeze sia di
   "copia fallita" — ipotesi iniziale plausibile (spiegherebbe il freeze
   E il fatto che `character_export.export_character()` (riga 101,
   `data/repositories/character_export.py`) ritorna `None` sia se il
   personaggio non esiste SIA in caso di qualunque eccezione, lock
   compreso — vedi il docstring della funzione). **Ma Davide ha
   esplicitamente detto che "copia personaggio" fallisce SEMPRE, non a
   intermittenza** — una contesa transitoria darebbe un fallimento
   intermittente (a volte va, a volte no, specialmente riprovando). Il
   fatto che sia sistematico fa propendere per un errore deterministico
   (dato/schema/percorso di codice specifico), non per contesa. **Non
   scartare del tutto**, ma non è la spiegazione più probabile per la
   PERSISTENZA — verificalo per primo col fix diagnostico sotto prima di
   investigare altro.
2. **Bug nello schema `character_conditions`** (tabella aggiunta
   2026-07-30, "Fase 4 feature 2b", vedi `data/database.py` righe
   1043-1056 e `CHILD_TABLES` in `character_export.py` riga 64-84, dove
   è stata aggiunta il 2026-08-16) come causa sistemica di
   `export_character()` che fallisce SEMPRE per QUALSIASI personaggio —
   **verificato che la tabella esiste correttamente** in
   `_create_tables()`/`init_db()` (chiamato ad ogni avvio app, quindi
   presente su qualsiasi build recente). Scartata come causa
   sistemica generale — ma **non verificato nello specifico per il
   personaggio/mondo di Davide**: se lì c'è un problema diverso
   (colonna mancante per una migrazione non applicata sul suo
   dispositivo specifico, dato malformato in una riga sua) il fix
   diagnostico sotto lo rivelerà direttamente.
3. **Che l'operazione "far entrare un personaggio nel mondo" fosse
   rotta in generale (bug preesistente, non una regressione di oggi)**
   — scartato: è un'operazione base necessaria per aver mai potuto
   testare spells/mappe/note nei round 1-4 precedenti, quindi ha
   funzionato almeno una volta. Il fatto che fallisca ORA, specificamente
   dopo un ingresso che si è bloccato ed è stato completato solo con un
   riavvio dell'app, punta più verso "questo mondo/questa istanza di
   ingresso specifica è rimasta in uno stato incompleto" che verso un
   bug generale nella funzione di copia.
4. **Che `_finalize_join()` lanci ancora un'eccezione NON protetta**
   (cioè fuori dai 6 loop già isolati dal round 4, commit `9b8243e`) —
   **ipotesi APERTA, non verificata**: `_finalize_join()` (riga 714) ha
   ANCORA due punti non protetti da try/except PRIMA dei loop isolati:
   `backend.get_snapshot()` (riga 728 — se fallisce ritorna già un
   errore pulito, non un crash) e, soprattutto, i due loop iniziali
   `for m in snapshot.get("members", [])` (riga 753) e
   `for event in events` (riga 755) — MAI protetti, a differenza dei 6
   loop sotto. Se il crash silente che spiegherebbe "il mondo risulta
   già registrato dopo il riavvio ma il dialogo non chiude mai da solo"
   avviene lì (es. un `WorldMember`/`WorldEvent` con un campo
   incompatibile in `protocol.member_from_dict`/`event_from_dict`), non
   sarebbe ancora coperto dal fix del round 4. **Primo posto dove
   guardare per la nuova sessione.**

### Fix diagnostico già applicato, non ancora verificato da Davide

Commit ancora NON effettuato a fine di questa sessione (solo modificato
su disco — verifica con `git status`/`git diff` a inizio della prossima
sessione se risultano già committati da un processo automatico, come
successo per i commit precedenti di questo stesso round):
`data/repositories/character_export.py` e `core/character_instances.py`.

- `export_character()` (riga 101) e `import_character()` (riga 472)
  hanno un nuovo parametro opzionale `raise_errors: bool = False` —
  default invariato per TUTTI gli altri chiamanti esistenti (loggano e
  ritornano `None` come sempre). Quando `True`, l'eccezione originale
  viene rilanciata invece di essere inghiottita.
- `core/character_instances.py::_copy_character` (riga 157) ora ritorna
  `tuple[str | None, str]` invece di `str | None` — `(nuovo_id, "")` in
  successo, `(None, dettaglio_leggibile)` in errore, chiamando
  `export_character(source_id, raise_errors=True)`/
  `import_character(data, mode="copy", raise_errors=True)` dentro un
  proprio try/except che costruisce il messaggio
  `f"Esportazione del personaggio fallita: {e}"` /
  `f"Importazione della copia fallita: {e}"`.
- `create_or_resume_instance()` (riga 109) propaga questo messaggio
  dettagliato in `InstanceResult.error` invece del generico "Copia del
  personaggio fallita." di prima.

**Perché**: il fallimento avviene sul dispositivo del GIOCATORE (uno
smartphone, build compilata) — Davide non ha modo di leggere l'output di
`logger.error(...)`, che prima era l'UNICO posto dove finiva il vero
messaggio d'eccezione. Con questo fix, il vero errore Python comparirà
direttamente nello snackbar sullo schermo del telefono al prossimo
tentativo — **questo è il primo dato mancante per proseguire la
diagnosi**, va richiesto esplicitamente a Davide prima di ipotizzare
altro.

### Cosa manca per chiudere questo bug — checklist per la prossima sessione

1. **Chiedere a Davide di rifare esattamente lo stesso test** (ingresso
   nuovo dispositivo → master approva → dialogo bloccato → Annulla →
   riavvio → "entra nel mondo" con un personaggio) sull'ultima build che
   include il fix diagnostico sopra, e riportare **il testo esatto**
   dell'errore che compare ora al posto del generico "Copia del
   personaggio fallita" — quello dice `export`/`import` e la classe/
   messaggio dell'eccezione Python reale.
2. **Chiedere anche cosa mostra `status_text` nel dialogo di ingresso
   PRIMA di premere Annulla** — non ancora chiesto con successo:
   - se resta su "In attesa dell'approvazione del master…" (colore
     grigio) per sempre → il problema è che il CLIENT non vede mai
     `status="approved"` da `poll_join_status()`
     (`core/world_backend.py`, riga 1787) nonostante l'host l'abbia
     davvero approvata — bug nel polling/nello stato `_pending` lato
     host (`network/host_server.py::join_status`, riga 541,
     `WorldHostServer._pending`) mai indagato a fondo in questo round;
   - se mostra un testo d'errore rosso (es. "Ingresso riuscito ma lo
     scaricamento dello stato del mondo è fallito" o "Salvataggio della
     replica del mondo fallito") → il problema è dentro
     `_finalize_join()`, punta all'ipotesi 4 sopra (loop `members`/
     `events` non protetti).
   Queste sono DUE cause radicalmente diverse — non tentare un fix
   "difensivo" generico senza prima saperlo, rischia di mascherare di
   nuovo il sintomo reale come già successo due volte in questo stesso
   round (vedi causa reale #2 e #3 sopra, trovate solo iterando).
3. **Se punta all'ipotesi 4**: applicare la stessa protezione
   try/except già usata per gli altri 6 loop di `_finalize_join`
   (righe 758-... del file dopo l'ultima modifica) anche ai due loop
   iniziali `members`/`events` (righe 753-756) — stesso pattern
   esatto, log con `logger.error("_finalize_join: membro/evento %r
   scartato: %s", ..., e)`.
   ⚠️ Attenzione però: gli eventi (`world_events`) sono la fonte di
   verità del giornale — saltarne uno silenziosamente potrebbe lasciare
   la replica con un buco nella sequenza (`last_synced_seq` calcolato
   da `max(e.seq for e in events)` alla riga 736 assumerebbe eventi
   presenti che in realtà sono stati scartati). Verificare se un evento
   può davvero fallire la deserializzazione (`protocol.event_from_dict`)
   prima di applicare la stessa protezione ciecamente qui — potrebbe
   servire una strategia diversa (es. loggare e continuare ma SENZA
   includere quell'evento nel calcolo di `latest_seq`, o troncare la
   sequenza al primo evento valido consecutivo invece di saltare nel
   mezzo).
4. **Se punta all'ipotesi del polling** (`join_status`/`_pending`): il
   posto giusto da rileggere è `network/host_server.py::approve()`
   (riga 424) e `join_status()` (riga 541) insieme a
   `RemoteBackend.poll_join_status()` (`core/world_backend.py`, riga
   1787) — verificare in particolare se `WorldHostServer._pending` (un
   dict in memoria, mai persistito su DB) potrebbe essere svuotato o
   sostituito tra l'approvazione e il polling successivo (es. da un
   riavvio dell'hosting nel frattempo, o da un secondo `approve()`
   concorrente) — nessuna di queste piste è stata verificata in questo
   round, solo elencata.
5. In ogni caso, **ri-eseguire la suite di test completa**
   (`for f in test_*.py; do ./.venv/bin/python3 "$f"; done` dalla root
   di `dnd_app/`) dopo qualunque modifica — invariata a 29/30 per tutto
   questo round (`test_qr_scan.py` unico limite noto, ambientale/pyzbar,
   non una regressione) — e chiedere SEMPRE conferma su dispositivi
   reali a Davide prima di considerare il bug chiuso: è precisamente la
   categoria di bug (dati reali accumulati su mesi di test, mai
   riproducibile con dati freschi in sandbox) che ha richiesto già 3
   iterazioni in questo stesso round prima di arrivare alla causa vera.

File coinvolti in questo round, tutti da avere presenti:
`ui/views/world/world_view.py` (dialogo di ingresso,
`_open_lan_join_dialog` e le funzioni annidate `_attempt`/`_retry`/
`_report`/`_poll_pending_join_loop`), `core/world_sync.py`
(`_finalize_join`, `finish_pending_join`, `start_lan_join`),
`network/host_server.py` (`handle_join`, `approve`, `join_status`,
`handle_snapshot`), `core/character_instances.py`
(`create_or_resume_instance`, `_copy_character`),
`data/repositories/character_export.py` (`export_character`,
`import_character`). Commit di questo round: `15fb5d8`, `9b8243e`,
`9bd2584` — i fix su `character_export.py`/`character_instances.py`
(diagnostica "raise_errors") erano ancora non committati all'ultimo
controllo di questa sessione.

---

## Multiplayer, round 5 — CHIUSO e CONFERMATO DAL VIVO: causa radice trovata sui dati reali (FK `linked_npc_id` + connessione SQLite abbandonata che blocca tutto il processo) (2026-08-17, sessione successiva)

> Chiude il bug lasciato APERTO dalla voce qui sopra. **Nessuna delle 4
> ipotesi elencate là era la causa** — la vera causa non era stata
> considerata, ed è stata trovata riproducendo `_finalize_join()` sullo
> **snapshot reale** del mondo di Davide (`~/.dnd_companion/dnd_companion.db`
> su questo stesso Mac, che ospita "Mondo del drago Gay"), non su dati
> freschi di sandbox. Metodo che ha funzionato e da riusare per questa
> categoria di bug: costruire lo snapshot con lo stesso codice dell'host
> (`WorldHostServer.handle_snapshot()`), poi darlo in pasto al vero
> `_finalize_join()` con un backend finto su un DB replica vuoto.

### La catena, un solo difetto a monte e tre sintomi

1. **FK violata su ogni nota collegata a un NPC.**
   `master_campaign_notes.linked_npc_id` ha una FK verso `master_npcs(id)`
   (`ON DELETE SET NULL`, `data/database.py` riga 1010), ma la Rubrica NPC
   del master **non viaggia mai** nello snapshot né negli eventi — è
   materiale privato del master (§7B), `handle_snapshot()` spedisce
   mondo/membri/giornale/schede/note/incontro/mappe e mai gli NPC. Sulla
   replica del giocatore quell'id quindi non esiste, e
   `master_repo.save_replica_note()` falliva con "FOREIGN KEY constraint
   failed". Sui dati veri di Davide: **9 note su 11** erano collegate a un
   NPC.

2. **La connessione della scrittura fallita restava aperta, col lock.**
   `save_replica_note()` chiudeva la connessione come ULTIMA RIGA del
   blocco `try`, non in un `finally` — quindi al primo errore non veniva
   mai chiusa. E **non basta il refcount a liberarla**: l'eccezione crea un
   ciclo di riferimenti (eccezione → traceback → frame → variabile locale
   `conn`) che solo il garbage collector generazionale può rompere. Fino a
   quel momento la connessione orfana trattiene la transazione di
   scrittura fallita, e con essa il lock del file.

3. **Da lì, ogni scrittura del processo falliva con "database is locked".**
   Le altre 10 note, le 3 mappe pubblicate, e poi
   `character_export.import_character()` — da cui il "Copia del personaggio
   fallita." che Davide vedeva **sempre** e non a intermittenza. Il
   changelog del round precedente aveva scartato l'ipotesi "contesa SQLite"
   proprio perché il fallimento era sistematico: giusto scartare la
   *contesa transitoria*, ma la spiegazione era un lock **permanente**
   trattenuto dallo stesso processo, che è sistematico per costruzione.
   Questo chiude anche l'ipotesi 1 di quella voce, in un modo che nessuno
   aveva previsto.

Misura sui dati reali, prima del fix: `_finalize_join()` ritorna
`success=True` ma salva **1 nota su 11 e 0 mappe su 3** — cioè esattamente
il "si vede solo 1 nota e 1 mappa" segnalato da Davide nel round 3/4 e
attribuito allora ad altre cause. I fix dei round 3/4 (isolamento per
elemento, `15fb5d8`/`9b8243e`) restano corretti e utili, ma mascheravano
questo: isolando l'eccezione per elemento il loop continuava, e ogni giro
successivo falliva silenziosamente per il lock invece che per la FK.

**Perché il dialogo del giocatore restava muto** (il sintomo che aveva
richiesto due round in più): in `_poll_pending_join_loop`
(`ui/views/world/world_view.py`) il risultato era `await
asyncio.to_thread(finish_pending_join, ...)` **senza try/except**. Una
qualsiasi eccezione lì — o in `_report`/`_open_detail` subito dopo un esito
riuscito — uccide la coroutine in silenzio: `page.run_task()` non ha alcun
gestore che la mostri. Il dialogo resta fermo su "In attesa
dell'approvazione del master…" per sempre, senza né successo né errore,
mentre il mondo risulta comunque registrato al riavvio perché
`save_replica_world()` aveva già scritto la riga. Il fix `9bd2584`
(`asyncio.to_thread`) aveva risolto il freeze *letterale* dell'interfaccia
ma non questo, ed è per questo che il vero errore non è mai arrivato a
schermo.

### Fix applicati

- **`data/repositories/master_repo.py::save_replica_note()`** — il
  collegamento all'NPC si conserva solo se quell'NPC esiste davvero in
  locale (vero sull'host, dove questa funzione non è usata, e in un
  eventuale futuro in cui gli NPC vengano condivisi), altrimenti degrada a
  `NULL`: esattamente il valore che la FK stessa prevede quando l'NPC non
  c'è più, e sulla replica il collegamento non ha comunque alcun uso (non
  c'è una Rubrica NPC da aprire). `conn.close()` spostato in un `finally`.
- **`data/database.py` — nuova `_ResilientConnection`** (sottoclasse di
  `sqlite3.Connection`, usata via `factory=` in `get_connection()`): al
  primo "database is locked" forza un `gc.collect()` — che chiude le
  connessioni orfane rompendo quei cicli — e riprova UNA volta. Il
  ritentativo è sicuro: una statement che non ha ottenuto il lock non ha
  applicato niente. Aggiunto anche `timeout=_SQLITE_TIMEOUT_S` (5s)
  esplicito. **Perché una rete di sicurezza globale e non 167 try/finally**:
  uno scan AST su tutto il progetto ha contato **167 funzioni** che aprono
  `get_connection()` senza garantire `close()` su tutti i percorsi (il
  pattern dominante del codebase: `close()` come ultima riga del `try`).
  Riscriverle tutte è un cambio meccanico enorme e rischioso da fare in
  coda a un bug-fix; il rimedio vive nell'unico punto da cui passa ogni
  query, e converte qualunque leak residuo da "processo avvelenato fino al
  riavvio" a "recupero trasparente". **Voce aperta**: la conversione a
  `try/finally` di quelle funzioni resta da fare a parte, con calma (vedi
  "Piano di lavoro attivo" in `CLAUDE.md`).
- **`core/world_sync.py::_finalize_join()`** — isolati anche gli ultimi due
  loop rimasti senza protezione, `members` ed `events` (l'ipotesi 4 del
  round precedente: era una vulnerabilità reale, semplicemente non era
  *questa* la causa). Per gli eventi si è seguito l'avvertimento già
  scritto in quella voce invece di applicare ciecamente lo stesso pattern:
  il giornale è una **sequenza**, e saltarne uno nel mezzo lasciando
  `last_synced_seq = max(seq)` lascerebbe un buco permanente (il prossimo
  `sync_replica()` chiederebbe solo gli eventi successivi). Ora si tiene il
  seq più alto **consecutivamente** salvato: al primo errore la sequenza si
  tronca lì e il giro di sync successivo riprende da quel punto.
- **`ui/views/world/world_view.py`** — `try/except` attorno al corpo di
  `_poll_pending_join_loop` e di `_retry`: qualunque eccezione diventa un
  messaggio rosso leggibile nel dialogo (`Errore durante l'ingresso:
  <Tipo>: <messaggio>`) invece di un task morto in silenzio. È la garanzia
  che questa classe di bug non possa più costare un round di test solo per
  scoprire *cosa* è fallito.
- I fix diagnostici `raise_errors` del round precedente
  (`character_export.py`/`character_instances.py`) sono stati **tenuti**:
  non servono più a trovare questo bug, ma restano il modo corretto per far
  arrivare un errore reale sullo schermo del giocatore. ⚠️ Nota: in
  `import_character()` il ramo `validate_export_data()` ritorna `None`
  PRIMA del `try`, quindi `raise_errors` non lo copre — un file non valido
  dà ancora il messaggio generico.

### Verifica

- Nuovo `test_replica_note_fk_lock.py`, **22/22**: la nota con NPC assente
  si salva col collegamento azzerato; il collegamento a un NPC *presente*
  si conserva (il fix non azzera a vanvera); una connessione abbandonata
  non blocca più le scritture successive né la copia del personaggio;
  `_finalize_join()` su uno snapshot con 9 note collegate e 3 mappe le
  semina **tutte** e la copia del personaggio subito dopo riesce; il
  giornale si tronca invece di bucarsi.
- Riproduzione sui **dati reali** di Davide, prima → dopo: **1 nota / 0
  mappe / copia fallita** → **11 note / 3 mappe / copia riuscita**.
- Suite completa: **30/31** (`test_qr_scan.py` unico fallimento, noto e
  ambientale — libzbar assente nel sandbox, non una regressione). Nel primo
  giro in batch `test_fase_4.py` ha fallito un controllo ("il totale compare
  nel pannello") ma passa 296/296 da solo e nel giro successivo: flake di
  isolamento tra test nello stesso HOME, non una regressione.
- ✅ **Confermato dal vivo da Davide (2026-08-17, stessa giornata)** su due
  dispositivi fisici, parole sue: "funziona tutto, sia le mappe sia le note
  condivise sia l'accettazione da parte del master". Cioè il giro completo
  che prima si bloccava — ingresso di un nuovo giocatore → approvazione del
  master → **la schermata del giocatore si aggiorna da sola** (il controllo
  automatico dell'approvazione arriva a uno stato di successo visibile,
  senza più riavviare l'app) → personaggio che entra nel mondo senza
  "Copia del personaggio fallita" → note e mappe condivise tutte visibili
  sulla replica. Il bug del round 5 è chiuso a tutti gli effetti.
- Restano da verificare dal vivo, mai arrivati a un giro di test reale (non
  regressioni, semplicemente non ancora provati): il tracker di
  combattimento condiviso (passo 7) e l'esportazione/importazione
  `.dndworld` (passo 9).

**Seguito**: la voce tecnica lasciata aperta qui (le 167 `close()` fuori dal
`finally`) è stata chiusa nella stessa giornata — vedi la voce subito sotto.

File toccati: `data/database.py`, `data/repositories/master_repo.py`,
`core/world_sync.py`, `ui/views/world/world_view.py`, nuovo
`test_replica_note_fk_lock.py`. Commit: **`a108062`** ("Make replica join
resilient and fix DB lock"), tag **v0.2.12** — la build su cui Davide ha
confermato dal vivo. Include anche i fix diagnostici `raise_errors` su
`character_export.py`/`character_instances.py` che il round precedente
aveva lasciato non committati (e che quindi non erano mai finiti in
nessuna build: né v0.2.10 `9b8243e` né v0.2.11 `9bd2584` — è il motivo per
cui il messaggio d'eccezione dettagliato che quella voce dava per
disponibile non era mai comparso sullo schermo del giocatore).

---

## Connessioni SQLite — chiusa la voce tecnica del round 5: 167 `close()` spostati in `finally` su 165 funzioni, più una guardia permanente (2026-08-17, stessa giornata)

Chiude la voce lasciata aperta dalla sezione qui sopra. Non è un bug
segnalato da Davide: è la **classe** di difetto che ha causato il round 5,
eliminata alla radice su richiesta sua ("risolviamo la voce tecnica") subito
dopo la conferma dal vivo.

### Il problema, in una riga

Il pattern dominante del progetto era `conn.close()` come **ultima riga del
blocco `try`**. Se una query solleva, quella connessione non viene mai
chiusa — e nemmeno liberata dal refcount, perché l'eccezione crea un ciclo
di riferimenti (eccezione → traceback → frame → variabile locale `conn`) che
solo il garbage collector generazionale può rompere. Nel frattempo trattiene
la transazione di scrittura fallita e con essa il lock del file, e **ogni
scrittura successiva del processo** fallisce con "database is locked" fino al
riavvio dell'app.

### Come è stato fatto (metodo, non a mano)

Uno scan AST ha prima **classificato le forme** invece di aprire 165 file a
caso — ed è quello che ha reso il lavoro sicuro, perché il pattern è risultato
quasi perfettamente regolare:

| forma | quante |
|---|---|
| un solo `try`, una `open`, un `close`, nessun generatore | 159 |
| due `try` (quello interno è sempre un `json.loads`/parsing, non la connessione) | 5 |
| `advance_turn` — 3 `close()` su rami di uscita diversi | 1 |
| `get_connection`/`_open_connection` — falsi positivi, **devono** restituire una connessione aperta | 2 |

Verificati prima tre presupposti, ciascuno con una prova eseguita e non
assunta: `sqlite3.Connection.close()` è **idempotente** (doppia chiusura non
solleva); la variabile è **sempre** chiamata `conn` (188 occorrenze, nessuna
eccezione); **nessun** `try` bersaglio aveva già un `finally` con cui fondersi;
e nessuna funzione restituisce un cursore o la connessione stessa (l'unico
`return cur.rowcount` è un `int`, valutato prima del `finally`).

La trasformazione è stata poi applicata da uno **script AST** (`conn = None`
prima del `try`, rimozione dei `close()` isolati dal corpo, `finally: if conn
is not None: conn.close()` in coda al `try` che apre la connessione), con
`ast.parse()` di controllo su ogni file prima di scriverlo e un dry-run
ispezionato prima dell'applicazione. Attaccare il `finally` al `try` **che
apre la connessione** (non al primo che si incontra) è ciò che rende corretti
i 5 casi a due `try`: lì l'interno resta intatto.

Risultato: **165 funzioni, 167 `close()` spostati**, su
`core/character_instances.py`, `core/world_backend.py`, `core/world_sync.py`,
`data/repositories/character_repo.py` (86), `loot_repo.py` (5),
`maps_repo.py` (9), `master_repo.py` (28), `world_export.py` (1),
`world_repo.py` (32). `character_export.py`/`settings_repo.py` non sono stati
toccati: usavano già il pattern annidato corretto (`try: conn = ...; try: ...
finally: conn.close()`).

### La guardia permanente — nuovo `test_connessioni_db.py` (8/8)

Il vero valore non è la conversione una volta sola, è che non possa
ricomparire. Tre parti:

1. **Invariante statica per-funzione** — nessuna funzione del progetto apre
   `get_connection()` senza chiusura garantita (`try/finally` o `with`). Se
   fallisce, il messaggio elenca `file:riga nome()` di ogni funzione da
   correggere. Allowlist di 2 voci (`get_connection`/`_open_connection`).
2. **Invariante per-`try`** — più granulare della precedente: intercetta anche
   una funzione che apre due connessioni in due `try` distinti e ne protegge
   solo uno. ⚠️ Attenzione se si tocca questo controllo: la prima versione
   cercava `.close()` nel *testo* del corpo del `try` e produceva **20 falsi
   positivi**, perché contava il `close()` di un `try/finally` **annidato**
   come se fosse del `try` esterno (tutto `character_export.py`,
   `settings_repo.py`, parti di `world_repo.py`, già corretti). Va valutato
   per nodo AST, non per stringa.
3. **Test di comportamento** — una funzione di repository che fallisce a metà
   scrittura (`create_master_campaign_note` con una FK `linked_npc_id`
   invalida) non lascia il database bloccato, nemmeno dopo **20 errori
   consecutivi**. Verificato con una connessione `sqlite3` **grezza** e
   `timeout=0`, deliberatamente non `get_connection()`: così si prova che il
   lock è rilasciato dal `finally` e non semplicemente mascherato dalla rete
   di sicurezza `_ResilientConnection`.

La guardia è stata **verificata in entrambe le direzioni**, non solo "passa":
creando un file temporaneo con il pattern incriminato, i controlli 1 e 2
hanno fallito indicando riga e nome della funzione; rimosso il file, 8/8. Un
test-lint che non può fallire non protegge niente.

### `_ResilientConnection` resta, con un ruolo diverso

Non è stata rimossa, ma il suo docstring è stato aggiornato: **non è più la
difesa principale**, lo è ora l'invariante strutturale verificata dal test.
Resta come difesa in profondità per una funzione nuova che sfugga alla
guardia, e converte un errore permanente e invisibile in un recupero
trasparente. Con una conseguenza operativa utile da sapere: **se il suo
`logger.warning` ("SQLite bloccato… riprovo") appare nei log, c'è una
connessione abbandonata da trovare** — non è funzionamento normale.

### Verifica

- Nuovo `test_connessioni_db.py`: **8/8**, e fallisce correttamente su una
  ricomparsa simulata del pattern.
- Suite completa: **31/32** (`test_qr_scan.py` unico fallimento, noto e
  ambientale — libzbar assente nel sandbox).
- Riprovato anche il flusso reale di ingresso sullo snapshot vero di Davide
  dopo il refactor: **11 note / 3 mappe / copia personaggio riuscita**,
  identico a prima della conversione — nessuna regressione su un cambio che
  ha toccato 165 funzioni.

File toccati: i 9 moduli elencati sopra, `data/database.py` (docstring),
nuovo `test_connessioni_db.py`, più `docs/architettura_moduli.md` (la forma
corretta, con il perché di `conn = None`).

---

## 2026-08-17 — Import personaggio/mondo su mobile non funziona: stessa diagnosi del caso foto, stessa tecnica del picker nativo

Davide ha segnalato che "Importa personaggio" e "Importa mondo" non funzionano su smartphone (Android), suggerendo di
provare la stessa tecnica già usata per le foto. Verifica del codice (non ipotesi): entrambi i flussi mobile
(`HomeView._on_mobile_import()` in `ui/views/home_view.py`, `WorldsView._on_mobile_import_world()` in
`ui/views/world/world_view.py`) passano ancora da `pick_file_via_webview()` (`ui/mobile_webview_picker.py`, `ft.WebView`
+ `<input type=file>`) — il bypass costruito il 2026-08-06 per il caso foto e poi **confermato non funzionante su
Android reale quello stesso giorno** (voce precedente in questo file: `webview_flutter` non implementa
`WebChromeClient.onShowFileChooser`, il tap su "Scegli file" non apre alcun selettore). Il caso foto è stato risolto
poco dopo con `flet_image_picker`, un'estensione Flet nativa su misura che avvolge il plugin Flutter ufficiale
`image_picker` — confermata funzionante da Davide su Android reale il 2026-08-06 (sessione successiva). L'import
personaggio/mondo non era mai stato migrato a quella tecnica perché `image_picker` sa selezionare SOLO immagini da
galleria, nessuna API per un file arbitrario come `.dndchar`/`.dndworld`.

**Fix applicato, stessa identica tecnica**: nuova estensione Flet nativa su misura, `dnd_app/extensions/
flet_file_picker/`, che avvolge il plugin Flutter ufficiale `file_picker` (pub.dev, publisher `miguelpruivo`,
`^8.1.7`) — stessa struttura di cartelle e stesso pattern di codice di `flet_image_picker` (`ft.control("FilePicker")`
+ `ft.Service`, dispatch `_invoke_method`/`addInvokeMethodListener` copiato 1:1). A differenza del caso foto, il
risultato lato Dart è una `Map` (`{"name": ..., "bytes": ...}`) invece dei soli byte grezzi, perché qui serve anche il
nome file originale (per i messaggi di errore e per riconoscere l'estensione).

Nuovo `ui/native_file_picker.py::pick_file_native(page, *, allowed_extensions=None)` — stesso wrapper Python di
`ui/native_image_picker.py::pick_image_native()`, stessa eccezione `FilePickerUnavailable` sollevata se il pacchetto
non è installato o l'invocazione fallisce per qualunque motivo. Wiring: `_on_mobile_import()` e
`_on_mobile_import_world()` provano ORA prima `pick_file_native()` (con `allowed_extensions=["dndchar", "json"]` /
`["dndworld", "json"]`); se solleva `FilePickerUnavailable`, ricadono automaticamente su `pick_file_via_webview()`,
NON rimosso — resta la rete di sicurezza, stesso schema del caso foto.

`pyproject.toml`/`requirements.txt` aggiornati con la nuova dipendenza path-based `flet-file-picker` (dichiarata in
`[tool.flet.dev_packages]`, stesso meccanismo di `flet-image-picker` — mai un URI assoluto scritto a mano, causa nota
di build CI rotte, vedi voce 2026-08-06).

**⚠️ Onestà su cosa NON è verificato**: nessun toolchain Flutter/Dart in questo sandbox (`which flutter dart` non
trova nulla) — nessuna riga di codice Dart in `flet_file_picker/` è mai stata compilata o eseguita. Il lato Python è
verificato solo per sintassi/importazione. È ragionevole aspettarsi problemi al primo giro di build reale, come
successo per `flet_image_picker` (due giri di CI falliti prima di funzionare: un import Dart mancante). Nota anche sul
plugin sottostante: quando fu scelto `image_picker` per le foto, la diagnosi di quella sessione osservava che
`file_picker` ha una storia di affidabilità più incerta nell'ecosistema Flutter — resta comunque l'unico pacchetto
Flutter maturo per selezionare un file arbitrario (nessun pacchetto "immagini" può farlo), e la causa di rottura di
`ft.FilePicker`/WebView qui è comunque a monte nel bridge Flet, non nel plugin in sé.

**Prossimo passo per Davide**: rilanciare la build (`flet build apk` o CI), correggere eventuali errori di
compilazione Dart segnalati dal compilatore (come già successo per `flet_image_picker`), poi testare "Importa
personaggio"/"Importa mondo" su un dispositivo Android reale. Se il percorso nativo fallisce silenziosamente a
runtime, il fallback WebView resta disponibile ma userà comunque lo stesso meccanismo già confermato rotto — in quel
caso l'unica strada resta il fix diretto di questa estensione, non un quarto tentativo diverso.

File toccati: nuovo `dnd_app/extensions/flet_file_picker/` (Python + Dart + README), nuovo
`ui/native_file_picker.py`, `ui/views/home_view.py` (`_on_mobile_import()`), `ui/views/world/world_view.py`
(`_on_mobile_import_world()`), `pyproject.toml`, `requirements.txt`.

### Stesso giorno — primo giro di CI reale (run #54): fallite tutte e 4 le build, causa trovata dal log, non ipotizzata

Davide ha girato la CI subito dopo il commit sopra: **tutte e 4 le build** (Windows/macOS/Linux/Android) fallite allo
stesso step (`flet build <piattaforma>`), non solo Android — segnale che la causa era a monte, comune a tutte le
piattaforme, non specifica del mobile. `Install Python dependencies` invece passava ovunque: non un problema di
packaging Python.

**Causa, dal log CI reale di Davide (non un'altra ipotesi)**:
```
Because flet 0.86.5 depends on file_picker ^11.0.2 and every version
of flet_file_picker from path depends on file_picker ^8.1.7, flet
0.86.5 is incompatible with flet_file_picker from path.
So, because dnd_companion depends on both flet_file_picker from path
and flet 0.86.5, version solving failed.
```
`flet==0.86.5` dichiara internamente `file_picker ^11.0.2` — per il proprio `ft.FilePicker` ufficiale (quello
confermato non funzionante su Android, non questa estensione: Flet lo bundla comunque come dipendenza Flutter). Il
vincolo `^8.1.7` scritto nel pubspec di `flet_file_picker` alla prima stesura era stato scelto per analogia con
`image_picker` (verificato su pub.dev a suo tempo), ma il numero di `file_picker` non era mai stato controllato
davvero — un vincolo assunto, non verificato, esattamente l'errore che la disciplina di questo progetto vuole
evitare. `pub` risolve le dipendenze Flutter dell'INTERO progetto in un colpo solo, prima di compilare per qualsiasi
target: un conflitto di versione fa quindi fallire ogni piattaforma allo stesso modo, non solo quella "incriminata".

**Fix, verificato sulla documentazione ufficiale prima di scrivere codice** (stessa disciplina di `flet_image_picker`,
non un altro tentativo alla cieca): `file_picker` allineato a `^11.0.2`, la stessa versione già richiesta da Flet. Ma
la sola versione non basta: `file_picker` 11.0.0 ha rifattorizzato `FilePicker` in una classe interamente statica,
**rimuovendo il getter `.platform`** — `FilePicker.platform.pickFiles(...)` (sintassi 8.x, quella scritta nel primo
giro) non compila più su 11.x, va chiamato `FilePicker.pickFiles(...)` direttamente. Verificato sulla documentazione
pub.dev della release 11.0.2 prima di correggere: il resto della superficie usata (`FileType.custom`/`.any`,
`allowedExtensions`, `withData`, `FilePickerResult.files`, `PlatformFile.name`/`.bytes`) risulta invariato tra 8.x e
11.x, nessun'altra modifica necessaria.

**Ancora non verificato**: nessuno dei due fix è stato compilato in questo sandbox (stesso limite di sempre, nessun
toolchain Flutter/Dart). Corretti per lettura del log CI reale e della documentazione ufficiale, non per un'altra
build alla cieca — ma resta da vedere al prossimo giro di CI se bastano, o se emerge un terzo problema (come successo
per `flet_image_picker`: due giri prima di arrivare a Gradle, un `debugPrint` non importato al primo).

File toccati: `dnd_app/extensions/flet_file_picker/src/flutter/flet_file_picker/pubspec.yaml` (versione vincolo),
`.../lib/src/file_picker_service.dart` (`FilePicker.platform.pickFiles` → `FilePicker.pickFiles`), README.md della
cartella (cronologia aggiornata).

---

## 2026-08-17 (stesso giorno) — Picker nativo CONFERMATO funzionante su Android reale; import mondo rotto da un bug reale, trovato dal log e corretto

Davide ha ricompilato con i due fix di `pubspec.yaml`/`file_picker_service.dart` (voce precedente) e testato dal vivo: **il picker nativo funziona**. Import personaggio riuscito per intero (scelta file → import corretto). Import mondo: il selettore di sistema si apre correttamente, ma l'import fallisce con un errore generico ("Errore durante l'importazione del mondo").

**Log `adb logcat` reale fornito da Davide, decisivo** (stessa disciplina di ogni bug precedente in questo file — mai un'altra ipotesi al buio):
```
23346 23346 W FilePickerUtils: Custom file type 'dndworld' is unsupported and will not be filtered.
23346 23551 W ActivityTaskManager: START ... com.android.documentsui/.picker.PickActivity ...
23346 23439 E flet.python: [ERROR] data.repositories.world_export: Errore import_world (mode=new): FOREIGN KEY constraint failed
```
Due informazioni chiave: (1) il warning "Custom file type... unsupported" è innocuo — `file_picker` non riconosce l'estensione `.dndworld` come MIME type per il filtro nativo, ma il picker si apre comunque (mostra tutti i file, `type: FileType.custom` con `allowedExtensions` sconosciute non blocca nulla — solo il filtro visivo non scatta, l'estensione va scelta a mano dalla lista); (2) il vero fallimento è un `IntegrityError` SQLite reale dentro `import_world()`, **non** un problema del picker.

**Causa, verificata nello schema (non ipotizzata)**: `master_campaign_notes.linked_npc_id TEXT REFERENCES master_npcs(id)` (`data/database.py`). `_WORLD_FLAT_TABLES` (`data/repositories/world_export.py`) scriveva `"master_campaign_notes"` **prima** di `"master_npcs"` nel tuple — `import_world()` itera quel tuple in ordine e scrive ogni tabella con INSERT sequenziali sulla stessa connessione (FK verificate per riga, immediate, non deferred). Qualunque mondo con almeno una nota collegata a un NPC falliva **sempre**, su qualunque dispositivo — non un caso limite. Stessa classe di bug già diagnosticata una volta per il path di sync LAN ("round 5", `world_sync.py`, voce precedente in questo file), qui riemersa **indipendentemente** nel path di export/import perché sono due funzioni diverse che scrivono le stesse due tabelle senza condividere codice.

**Fix**: `master_npcs` spostato prima di `master_campaign_notes` in `_WORLD_FLAT_TABLES`. Trovato anche un secondo bug correlato, mai manifestatosi ancora ma sicuro al primo uso reale: in modalità `"copy"` gli NPC ricevono un id nuovo (`regenerate_ids=True`) ma `linked_npc_id` nelle note non veniva mai rimappato — la nota copiata sarebbe rimasta agganciata al vecchio id, con lo stesso `FOREIGN KEY constraint failed` (o, se l'NPC vecchio non esiste più nel DB di destinazione, un riferimento pendente). `_write_flat_table()` ora ritorna la mappa vecchio→nuovo id di ogni riga scritta; `import_world()` la cattura sull'iterazione di `master_npcs` e la passa a `_write_flat_table()` per `master_campaign_notes`, che rimappa `linked_npc_id` con lo stesso meccanismo già in uso per `character_id`/`char_id_map`.

**Perché la suite di test non l'aveva mai trovato**: `test_esportazione_mondo.py::_build_rich_world()` (il seed condiviso da 5 dei 7 blocchi della suite) creava una nota del master e un NPC **separatamente**, senza mai collegarli — `linked_npc_id` restava sempre `NULL`, e una FK su `NULL` è sempre valida. 84/84 verde non voleva dire "il percorso è corretto", voleva dire "il percorso non è mai stato attraversato con questo dato". Corretto il seed (NPC creato prima, nota creata con `linked_npc_id=npc.id`) e aggiunte due asserzioni dedicate (round trip `mode="new"` e rimappatura `mode="copy"`) — **verificate in entrambe le direzioni**: ripristinato temporaneamente l'ordine sbagliato del tuple, la suite fallisce riproducendo esattamente l'errore di Davide (`FOREIGN KEY constraint failed`, stesso identico messaggio); con il fix, **86/86** (84 + 2 nuove).

File toccati: `data/repositories/world_export.py` (`_WORLD_FLAT_TABLES`, `_write_flat_table()`, `import_world()`), `test_esportazione_mondo.py` (seed + 2 nuove asserzioni).

**Stato aggiornato**: import personaggio su mobile **confermato funzionante end-to-end** (picker nativo + logica). Import mondo: bug di fondo corretto e verificato in isolamento (86/86), ma **non ancora ritestato da Davide su dispositivo reale** con questo fix — prossimo passo.

---

## Aggiunta personaggio al mondo con l'host offline: mai ritentata, il giocatore restava "nel mondo" solo in locale (2026-08-18)

Bug segnalato da Davide dopo il test dal vivo del tracker di combattimento condiviso (confermato OK, resta solo da velocizzare la sincronizzazione in futuro — non un bug) e dell'export/import `.dndworld` (**confermato funzionante dal vivo**, chiude definitivamente il fix del 2026-08-17 sull'ordine FK `master_npcs`/`master_campaign_notes`): "quando il master ferma l'hosting un giocatore può provare ad aggiungere un personaggio al mondo, esce un messaggio che dice che non è stato possibile... quando torna online l'hosting il personaggio sull'app del giocatore risulta nel mondo, ma da parte del master il personaggio non è presente". Workaround trovato da Davide: eliminare l'istanza sul device del giocatore e riaggiungerla con l'host online.

**Causa**: `ui/views/home_view.py::HomeView._push_instance_to_host()` scrive SEMPRE prima l'istanza sul DB locale del giocatore (comportamento corretto, invariato — vedi il fix del 2026-08-07 nello stesso metodo), poi prova a notificare l'host col comando `character_instance.sync`. Il docstring del metodo dichiarava già esplicitamente, dal 2026-08-07: *"questo non viene ritentato automaticamente dal thread di sincronizzazione in background"* — un limite noto ma mai colmato. Se l'host è irraggiungibile (master che smette di ospitare), il push fallisce e basta: l'istanza resta agganciata al mondo solo lato giocatore, l'host non riceve mai l'evento, finché non si ripete l'operazione a mano con l'host di nuovo online.

**Fix minimo, comando già idempotente lato host (nessun redesign)**:
- Nuova colonna `characters.host_sync_pending` (`data/database.py`, 0 = niente in sospeso di default).
- `character_repo.set_host_sync_pending()`/`list_pending_host_sync()` (nuove funzioni, stesso pattern try/finally di tutto il resto del file — verificato da `test_connessioni_db.py`).
- `_push_instance_to_host()` accende il flag sui tre percorsi di fallimento (backend non risolvibile, comando rifiutato dall'host, bloccato dal cooldown anti-spam) e lo spegne al successo.
- Nuova `core/world_sync.py::push_pending_instances()`: ritenta il push per tutte le istanze in sospeso di questo dispositivo in un mondo, stesso cooldown condiviso di `_push_instance_to_host` per non spammare. Agganciata al loop di polling già esistente in `ui/views/world/world_view.py::_start_detail_sync` (stesso punto che già chiama `world_sync.sync_replica()` ad ogni giro) — appena l'host torna raggiungibile, il prossimo giro del loop (~2s) registra da solo l'istanza rimasta indietro, senza bisogno che il giocatore riapra manualmente "Aggiungi a un mondo".

**Verificato con un nuovo test mirato** (`test_character_instance_sync.py`, funzione 6): riproduce esattamente lo scenario di Davide con un `WorldHostServer` reale — push tentato mentre l'host risulta irraggiungibile (`worlds.last_seen_host` puntato a una porta senza nessuno in ascolto) → verificato che l'istanza sia marcata `host_sync_pending` e che l'host non abbia ricevuto nulla nel giornale eventi; poi l'host torna raggiungibile (stessa porta, server mai fermato — la parte che conta è la raggiungibilità, non il riavvio del processo) → `push_pending_instances()` la registra da sola, il flag si spegne, l'host riceve esattamente un evento `character_instance.sync`. Suite completa 20/20 (14 esistenti + 6 nuovi controlli), nessuna regressione su `test_world_view_remote_routing.py` (16/16), `test_ingresso_lan_sincronizzazione.py` (31/31), `test_cooldown_azioni_remote.py` (43/43), `test_connessioni_db.py` (8/8).

File toccati: `data/database.py`, `data/repositories/character_repo.py`, `core/world_sync.py`, `ui/views/home_view.py`, `ui/views/world/world_view.py`, `test_character_instance_sync.py`.

**Resta da confermare dal vivo da Davide** (stesso limite di sempre: due DB separati non simulabili in modo affidabile in questo sandbox) — riprodurre lo scenario originale su due dispositivi fisici e verificare che il personaggio compaia da solo lato master entro pochi secondi dal ritorno online dell'host, senza il workaround manuale.

---

## Thread di sincronizzazione in background: crash silenzioso se la sessione termina a metà giro (2026-08-18)

Bug segnalato da Davide con un traceback reale (`Exception in thread home-world-sync`) durante il test del pilot FASE F: `RuntimeError: HomeView(142) Control must be added to the page first`, seguito da `Session was garbage collected`. Non legato al lavoro di design in corso (verificato con `git diff --stat`: `ui/components/background_sync.py` non era tra i file toccati quella sera).

**Causa**: `BackgroundSyncLoop._loop()` (usata da 7 view: Home, scheda, Mondi, Modalità Master Incontri, Diario, Mappe, Incantesimi) protegge tre delle sue quattro callback con try/except, ma non `self._get_page()` — se la sessione Flet termina (tab chiusa/ricaricata) tra un giro e l'altro del thread daemon, accedere a `.page` su un `Control` non più agganciato a una pagina viva solleva `RuntimeError`, non intercettato.

**Fix**: avvolto anche `_get_page()` nello stesso pattern try/except delle altre tre callback — un giro saltato non perde nulla, il prossimo redraw arriva comunque al prossimo cambiamento reale di stato. File toccato: `ui/components/background_sync.py`.

---

## Audit anti-AI-slop — rollout completo alle 37 view + fix contrasto tema scuro (2026-08-18/19)

Continuazione della sessione FASE F (vedi `restyle_design.md` per il dettaglio tecnico completo, qui solo il riassunto narrativo). Dopo il pilot su 4 view, Davide ha confermato il miglioramento in tema chiaro ma segnalato che il tema scuro "non mi convincono mi affaticano gli occhi", poi ha dato mandato esplicito per il resto della notte: "non porti limiti... affidati alla skill ui-ux-pro-max... procedi senza fermarti, senza chiedere approvazioni... effettua tutti i cambiamenti anche quelli programmati."

**Fix eye-strain tema scuro**: un primo tentativo (schiarire lo sfondo delle card "hero" per livello, tecnica Material "elevation overlay") è stato calcolato e SCARTATO prima di scrivere codice sulle view — avrebbe fatto scendere `primary_icon` sotto la soglia WCAG 3:1 (margine già quasi zero contro `surface` invariato) e riavvicinato `surface`/`bg` dopo che Davide aveva passato sette giri di feedback il 2026-08-15 a distanziarli apposta per eliminare un "glow". Fix effettivo, verificato numericamente prima e dopo: `DARK.text`/`text_2`/`nav_text` ridotti in luminosità HSL (tonalità invariata) da 15.35:1/9.56:1 a 11.94:1/8.57:1 contro `bg` — ancora ben oltre il minimo AAA (7:1), ma senza il contrasto "estremo" causa nota di affaticamento nella lettura prolungata. Nuove primitive `design.accent_glow()`/`design.layered_shadow()`: un alone colorato (non nero) attorno alle card hero, solo in tema scuro — un'ombra nera è quasi invisibile contro uno sfondo già scuro, un'ombra colorata si vede senza toccare `bgcolor` (zero rischio sui contrasti testo/icona già calcolati).

**Rollout**: la stessa convenzione hero/critical del pilot (elevazione via `level`/`accent` già esistenti su `card()`/`section()`, non nuovi colori — `primary`/`danger` sono di proposito lo stesso accento) estesa a tutte le 33 view rimanenti, delegando a 6 sotto-agenti paralleli con lo stesso identico brief (API, convenzione, regole icone/spaziatura, vincolo assoluto "mai la logica, solo l'estetica"). Buon esito complessivo: diversi agenti hanno correttamente scelto di NON forzare un hero dove non c'era un candidato genuino (form del wizard di creazione, molte view di gestione della Sezione Master già ben progettate da iterazioni precedenti), invece di applicare la convenzione meccanicamente ovunque — esattamente il comportamento voluto.

**Deliberatamente esclusi** (rischio/beneficio sfavorevole, non dimenticanza): i tre flussi dialog di `profilo_tab.py` per level-up/multiclasse/level-down (~2500 righe, logica PHB e UI troppo interlacciate per una rifinitura estetica sicura in autonomia notturna); il canvas di disegno vero e proprio in `maps_view.py` (solo la chrome attorno toccata).

**Verifica**: `python3 -m compileall ui/ core/ data/` pulito dopo ogni blocco di lavoro; `test_fase_d.py` (104 costruzioni di view nei due temi) a 101/101 sia dopo ogni batch sia alla fine con tutte le modifiche combinate; l'intera suite di 35 file `test_*.py` eseguita — 33/35 verdi, i 2 falliti (`test_qr_scan.py`, `test_versione_app.py`) sono ambientali (pacchetti Android/iOS assenti nel sandbox, tag di release git) e già noti come tali da prima di questa sessione. `git diff --stat` finale: 35 file, +718/-240 righe. **Nessun commit fatto** (scelta esplicita di Davide: "nessun commit, decido io domattina") — tutto resta come working tree modificato.

**Resta da fare**: il giudizio estetico vero e proprio spetta a Davide al risveglio, su dispositivo reale, in entrambi i temi — nessun test visivo automatico esiste per questo progetto, non è mai stato possibile sostituirlo. Dettaglio file-per-file completo in `restyle_design.md`, sezione "FASE F".

File toccati: `ui/design.py` (fix contrasto + `accent_glow`/`layered_shadow`), tutte le 33 view rimanenti sotto `ui/views/` (elenco completo in `restyle_design.md`), `docs/restyle_design.md`, `CLAUDE.md`.

---

## FASE G — "Arcane Ledger": palette rifatta da zero + rollout responsive (2026-08-20)

Richiesta di Davide, distinta dalla FASE F: non un'estensione della vecchia palette bordeaux/pergamena, ma una ripartenza totale — "ignora gli otto giri della palette precedente... stiamo facendo un cambio radicale... puoi cambiare tutto, gradienti colori tutto". Un solo requisito nuovo, esplicito: l'app deve adattarsi bene sia a schermi grandi (PC) sia piccoli (smartphone). Stesso vincolo di sempre: nessuna modifica alla logica, solo estetica.

**Palette nuova**: `primary` (oro antico/bronzo, accento di marca) e `danger` (rosso vero) separati per la prima volta — prima erano lo stesso hex per scelta esplicita. `magic` (indaco/violetto) elevato da tag semantico a secondo registro compositivo vero e proprio, guida `spells_view.py`/`dice_view.py`. Chiaro: pergamena più ricca. Scuro: nero-inchiostro caldo (non blu-slate da dashboard), testo calibrato a ~7-9:1 (AAA con margine, non oltre — stessa lezione anti-affaticamento della FASE F applicata da subito invece che corretta in un secondo giro). Ogni hex ricalcolato con la stessa disciplina di misurazione WCAG di sempre, zero valori riusati dalla palette precedente. Query alla skill `ui-ux-pro-max` (dataset generico, nessuna voce "fantasy RPG" letterale) usate come materiale ispirazionale — l'unico pattern preso a prestito senza modifiche: in ogni palette di riferimento consultata il colore distruttivo non coincide mai col primario, da cui la separazione oro/rosso.

**Nuove primitive**: `Size.HERO`/`hero_title()` (un momento tipografico dominante per schermata, prima assente), `icon_badge()` (badge icona tinto generalizzato da `dialog_title()`), `hero=`/`density=` su `card()`/`section()`/`surface()`, `Breakpoint` (allineato ai default reali di `ft.ResponsiveRow`), `generator_dialog_shell()` (shell condivisa per 8 dei 9 dialoghi generatori Master).

**Rollout su tutte le 35 view** (non un pilota, copertura totale fin dall'inizio), delegato a agenti paralleli in 5 fasi di rischio crescente, con lo stesso identico vincolo "solo estetica" ribadito in ogni brief. `profilo_tab.py` (i flussi level-up/multiclasse/level-down, esclusi in FASE F) affrontato questa volta ma con perimetro ristretto a soli kwargs di stile, mai struttura/stato — verificato anche con `test_multiclasse.py` (72/72) oltre a `test_fase_d.py`.

**Interruzione a metà Fase 4** (limite di sessione degli agenti, non un errore): tutti e 6 gli agenti della fase più corposa (i due file del wizard, `combattimento_tab.py`, la coppia inventario/esplorazione, `spells_view.py`, il tracker di combattimento Master) sono stati interrotti a metà lavoro dallo stesso limite nello stesso momento. Verificato subito dopo: tutto compilava e passava comunque (`test_fase_d.py` 101/101) — gli agenti salvano incrementalmente, l'interruzione non ha lasciato file a metà scritti. Ripresi con agenti "di completamento" che leggevano prima il diff già presente per non duplicare/confliggere col lavoro fatto, poi finivano quanto mancava.

**Effetto collaterale positivo, trovato indipendentemente da più agenti**: separare `primary` da `danger` ha reso visibile una decina di punti sparsi in 9 file diversi dove un'azione distruttiva (elimina, rimuovi, applica danno) usava ancora il token oro invece di quello rosso — invisibile prima perché i due colori coincidevano, un vero bug semantico latente, corretto ovunque trovato.

**Regressione reale trovata e corretta** (unica modifica a un test in tutta la sessione): `test_trasferimento_dispositivo.py` cercava il pulsante "codice di trasferimento" un solo livello sotto `.controls` — la ristrutturazione responsive di `_member_row()` in `world_view.py` (da `Row` piatta a `asymmetric_row`, per il collasso sotto i 768px) lo ha spostato più in profondità nell'albero senza toccare la logica di permessi/visibilità che il test doveva verificare. Corretto l'helper di ricerca del test per essere ricorsivo.

**Verifica finale**: `compileall` pulito; `test_fase_d.py` 101/101; suite completa (35 file `test_*.py`) 34/35 verdi dopo il fix sopra — i 2 residui (`test_qr_scan.py`, `test_versione_app.py`) sono gli stessi ambientali pre-esistenti da prima di questa sessione. Nessun commit fatto. Dettaglio tecnico completo (palette, primitive, rollout per fase, file critici) in `restyle_design.md`, sezione "FASE G".

File toccati: `ui/design.py` (palette + primitive nuove), `ui/theme.py` (delega a `header_row()`, taglie bottoni derivate), tutte le 35 view sotto `ui/views/`, `test_trasferimento_dispositivo.py` (fix helper di ricerca), `docs/restyle_design.md`, `CLAUDE.md`.

---

## Trasferimento dispositivo — due rifiniture da test dal vivo (2026-08-20)

Davide ha confermato che il trasferimento dispositivo (§11.9) funziona bene nella pratica, con due osservazioni dal test reale.

**1. Il campo "Il tuo nome" nel dialogo di ingresso non aveva senso in modalità trasferimento.** Verificato leggendo il codice: era già vero che l'host conserva sempre il nome del membro originale a prescindere da cosa arriva nel campo (`world_transfer_repo.rebind_device` non scrive mai `display_name`, `_handle_transfer_join` lo usa solo come "chi sta bussando" nella card di approvazione del master, mai per il nome persistito) — il campo era mostrato comunque, suggerendo all'utente di dover scegliere un nome nuovo per qualcosa che in realtà resta sempre lo stesso. Fix: `display_field` ora si nasconde in modalità trasferimento esattamente come già faceva `pin_field` (stesso `_set_transfer_mode()` in `ui/views/world/world_view.py::_open_lan_join_dialog`), sostituito da una riga di spiegazione ("Il tuo nome nel mondo resta quello di sempre — non serve reinserirlo"). Nessuna modifica al protocollo: il QR/codice di trasferimento non porta comunque il nome del vecchio membro, quindi non c'era modo di precompilarlo — la soluzione corretta era non chiederlo, non indovinarlo.

**2. Sul dispositivo vecchio, il personaggio restava "nel mondo ma disconnesso" senza distinguersi da un semplice mondo irraggiungibile.** Comportamento voluto di mantenere il personaggio in lista (i dati restano intatti, giusto non farlo sparire) — mancava solo l'indicazione visiva. Trovata una targhetta "trasferito" già esistente per questo esatto caso nel dettaglio della Sezione Mondi (`world_view.py::_world_card`, letta da `world_sync.is_world_transferred_away()` — un flag locale già scritto quando questo dispositivo applica il proprio evento di trasferimento, nessun nuovo stato necessario), ma assente nella Home, dove Davide stava effettivamente guardando. Aggiunta la stessa targhetta (`design.chip("trasferito", "danger")`) all'intestazione di gruppo-mondo in `home_view.py::_section_label()`, leggendo lo stesso flag.

Verificato: `test_fase_d.py` 101/101, `test_trasferimento_dispositivo.py` 146/146, `test_world_view_remote_routing.py` 16/16, `test_home_sync_rimozione_mondo.py` 14/14, `compileall` pulito. File toccati: `ui/views/world/world_view.py`, `ui/views/home_view.py`.

---

## Rilascio v0.3.1 — primo aggiornamento in-app confermato dal vivo (2026-08-19)

Dopo le due rifiniture al trasferimento dispositivo sopra, Davide ha chiesto di preparare ed eseguire un vero
rilascio versionato per verificare l'aggiornamento in-app end-to-end — la parte non ancora testata dal vivo del
lavoro del 2026-08-17 (firma di rilascio permanente + `flet_apk_installer`), dato che l'aggiornamento a `v0.3.0`
era stato fatto disinstallando/reinstallando a mano invece che dal dialogo guidato.

Procedura seguita da `RELEASE.md`: `version.py::APP_VERSION` e `pyproject.toml [project].version` portati a
`"0.3.1"`, `test_versione_app.py` (28/29 — l'unico fallito è il controllo strutturalmente obsoleto su
`compute_build_number(FIRST_SIGNED_VERSION)` contro i tag già rilasciati, non causato da questo bump e non in
scope), `compileall` pulito, commit `chore: release v0.3.1`, tag `v0.3.1`, push con `--tags` — GitHub Actions ha
buildato Windows/macOS/Linux/Android e pubblicato la Release.

**Confermato da Davide**: l'aggiornamento in-app ha funzionato correttamente sia su Android sia su macOS, in
loco, senza disinstallare — la prima verifica reale che la migrazione alla firma di rilascio permanente (§
"Aggiornamento automatico in-app", 2026-08-17) risolve davvero il problema originale, non solo in teoria.

---

## Riconnessione dopo cambio di rete dell'host — bug reale + fix (2026-08-19)

Bug segnalato da Davide durante un test dal vivo, distinto dai due precedenti: se il gruppo gioca una settimana
su una rete diversa da quella solita (es. l'host non è più ospitato "da casa" ma da un'altra rete), sul
dispositivo del giocatore **né l'auto-reconnect né il pulsante "Riconnetti" funzionavano** — soltanto
riscansionare il QR del master risolveva.

**Causa**: `world.last_seen_host` (`"192.168.1.7:8765"`) viene scritto una volta al primo ingresso
(`_finalize_join()`) e mai più aggiornato lungo il percorso di riconnessione. Il QR invece incorpora sempre
l'IP ATTUALE dell'host (`network/host_server.py::local_ip_hint()`, ricalcolato ogni volta che si apre la
schermata di hosting) — cambiando rete, l'host ottiene un nuovo IP LAN, il QR lo riflette subito, l'indirizzo
salvato no. `core/world_sync.py::resolve_backend_for_world()` (usata sia dal pulsante "Riconnetti" in
`world_view.py` sia dall'auto-reconnect di `home_view.py`) provava solo il reconnect col token e un retry-join
sullo STESSO indirizzo stale, poi si arrendeva — mai una vera riscoperta. Riscansionare il QR "funzionava" solo
per effetto collaterale: un ingresso completo da QR passa comunque per `_finalize_join()`, che sovrascrive
`last_seen_host` con l'indirizzo fresco appena letto dal QR.

Nota a margine: `§11.7` di `multiplayer_design.md` descriveva già da tempo "il client ripiega sulla scoperta
automatica" come comportamento voluto — era design aspirazionale mai davvero cablato, non una regressione.

**Fix**: nuova funzione `core/world_sync.py::_retry_with_rediscovery()`, chiamata da
`resolve_backend_for_world()` quando il retry sull'indirizzo salvato fallisce (e non è un caso di trasferimento
dispositivo già gestito, §11.9). Ascolta per una finestra breve l'annuncio broadcast UDP che l'host manda
comunque ogni ~2s (`network/discovery.py::discover_worlds()`, già esistente ma finora usato solo dalla ricerca
manuale "Cerca partite nelle vicinanze"), cerca l'entry con lo stesso `world.id`, e se la trova ripete
`start_lan_join()` con l'indirizzo fresco — che persiste da solo il nuovo `last_seen_host` tramite il normale
`_finalize_join()`, nessun aggiornamento separato necessario. Nessuna azione richiesta all'utente: sia
l'auto-reconnect sia "Riconnetti" ora si riprendono da soli, stesso limite di sempre della scoperta LAN (reti
che bloccano il broadcast, es. Wi-Fi pubblici con isolamento client, restano coperte solo dal percorso manuale).

Verificato: `compileall` pulito su `core/`, `test_fase_d.py` 101/101, `test_scoperta_lan.py` 25/25,
`test_home_sync_rimozione_mondo.py` 14/14, `test_character_instance_sync.py` 20/20. Nessun test dedicato nuovo
scritto (il percorso richiede due dispositivi reali su reti fisicamente diverse per essere riprodotto in modo
non simulato) — **resta da confermare dal vivo**. File toccati: `core/world_sync.py`,
`docs/multiplayer_design.md` (§11.7 aggiornato da "design" a "implementato").

---

## Revisione generale del codice — testo di sviluppo in UI, codice morto, commenti storici (2026-08-19)

Richiesta di Davide dopo aver notato che la view "Mondi" mostrava all'utente finale un sottotitolo con gergo da
sviluppatore e ormai falso: *"Campagne condivise — passo 2, senza rete: funziona oggi solo tra sessioni che
condividono lo stesso database (web mode multi-scheda)."* — riferimento a un "passo 2" di un piano interno
completato da tempo (tutti i 9 passi del Multiplayer sono chiusi). Ambito della revisione: eliminare testo di
sviluppo trapelato in UI, codice morto, commenti storici in tutto il codebase (~77.000 righe), ottimizzare lo
spazio dove possibile, proporre (senza implementare) nuove funzionalità.

**Testo UI corretto** (3 occorrenze reali, distinte dai commenti di codice — verificate una per una che fossero
davvero visibili all'utente, non solo simili nel testo):
- `ui/views/world/world_view.py` — il sottotitolo sopra, riscritto in termini utente.
- `ui/views/character_sheet/sheet_view.py::_placeholder_tab()` — "In sviluppo..." (ramo irraggiungibile con le 5
  tab reali attuali, mantenuto come guardia difensiva ma con testo neutro "Sezione non disponibile.").
- `ui/views/character_sheet/combattimento_tab.py` — "Aggiungi armi dalla scheda Inventario (prossimamente)."
  era falso: la funzione esiste già in Inventario. Rimosso "(prossimamente)".
- Trovata durante la pulizia commenti (non nel giro iniziale): `ui/views/master/master_encounter_view.py`, un
  dialogo di conferma assegnazione PE conteneva "(fix 2026-08-07)" nel testo mostrato al Master. Rimosso
  mantenendo la sostanza informativa ("mai una scrittura diretta") — `test_fase_4.py` verifica proprio questa
  frase, quindi un primo tentativo di editing troppo aggressivo ha causato una regressione temporanea, corretta
  subito ripristinando la clausola sostanziale e tagliando solo il riferimento alla data/fix.

**Codice morto rimosso** (confidenza alta, zero riferimenti in tutto il repo inclusi i 35 file `test_*.py`):
`core/dice.py::RollResult.all_rolls` (property mai usata), `ui/design.py::Breakpoint` (classe di soglie
responsive mai adottata — `ui/app.py` usa una propria `_MOBILE_BP=600` locale indipendente),
`data/repositories/character_repo.py::character_has_class()` (zero chiamanti — la duplicazione ipotizzata in
`profilo_tab.py:4296` si è rivelata un pattern diverso, uso di un `set` per filtrare classi disponibili, non
un'esistenza singola: rimossa senza forzare un consolidamento artificiale), import inutilizzati in
`ui/views/creation_wizard/wizard_view.py` (`body_text`/`label_text`/`fantasy_card`), `manual_form.py`
(`fantasy_card`), `ui/app.py` (`wrap_dialog_actions`), `core/update_downloader.py` (`field`),
`data/repositories/world_export.py` (`CHILD_TABLES`, mai referenziato per nome nel modulo). Un vero bug latente
trovato con `pyflakes`: `ui/views/world/world_view.py` usava l'annotazione `Any` in due firme di funzione senza
mai importarla da `typing` — innocuo oggi solo grazie a `from __future__ import annotations`, corretto
aggiungendo l'import.

**Pulizia sistemica dei commenti "diario di sviluppo"** — pattern trovato in tutto `core/`, `data/`, `network/`,
`ui/`: quasi ogni commento "perché" nel codice era scritto come mini-voce di changelog (data + "bug segnalato da
Davide" + a volte l'intera cronologia dei tentativi falliti) invece di spiegare solo il vincolo tecnico attuale
— informazione già duplicata verbatim in questo stesso file. Politica applicata uniformemente: rimuovere i
blocchi di puro racconto storico (es. `profilo_tab.py` aveva 77 righe in 6 punti numerati sulla diagnosi del bug
FilePicker, `maps_view.py` un blocco esplicitamente etichettato "Storico" che descriveva codice non più
esistente), accorciare quelli con un vincolo tecnico reale sotto la cornice narrativa (la stragrande
maggioranza), correggere quelli ormai falsi rispetto al codice attuale. Trovati e corretti 2 commenti
attivamente scorretti: `data/repositories/world_repo.py` diceva che `create_change_request()` non fosse "ancora
usata" mentre è attivamente chiamata da `core/world_backend.py`; due docstring in `profilo_tab.py` sul picker
foto mobile descrivevano ancora `ft.FilePicker`/un WebView "confermato morto" mentre il codice usa da tempo
l'estensione nativa con fallback WebView. Lavoro svolto in ondate di sotto-agenti paralleli su gruppi di file
indipendenti (85 file toccati in totale), con verifica di compilazione e suite di test completa dopo ogni
ondata.

**Spazio**: rimossi dal repository 20 file `.dndchar` di test (`assets/exports/TestWarlock_Lv20_*`,
`personaggio_*`) committati per errore durante sessioni di test manuali — la cartella viene ricreata a runtime
da `data/database.py::get_character_exports_path()`, nessun impatto funzionale. `build/` (1.1 GB locale) già
ignorato da git, segnalato a Davide come pulizia locale facoltativa, non un problema di repository.

**Verificato**: `compileall` pulito su tutto l'albero, suite intera `test_*.py` 33/35 file al 100% (i 2 residui
sono gli stessi ambientali pre-esistenti già documentati altrove in questo file — `test_qr_scan.py` supporto
piattaforma, `test_versione_app.py` versionCode contro i tag già rilasciati — non causati da questa sessione).
**Nessun commit fatto** (in attesa di revisione di Davide).

Proposte scritte per Davide (nessuna implementata in questa sessione, per sua scelta): export scheda personaggio
in PDF (ricognizione già fatta in `docs/pdf_sheet_reference/`, mai scritta una riga), Sistema Bottino passo 6
(deposito lato giocatore, sbloccato dal Multiplayer ora completo ma mai ripreso), UI per rimuovere una classe da
un personaggio multiclasse (il layer dati `remove_character_class()` in `character_repo.py` esiste già, mai
agganciato a un pulsante), velocità di sincronizzazione del tracker di combattimento condiviso (già segnalata
come miglioria non bloccante il 2026-08-18) — **quest'ultima ripresa e implementata nella stessa giornata, vedi
sezione dedicata subito sotto**.

---

## Velocità di sincronizzazione del tracker di combattimento condiviso (2026-08-19)

Ripresa subito dopo la revisione generale sopra, su richiesta esplicita di Davide ("ottimizziamo la velocità del
sync"). Non un bug — il tracker funzionava correttamente (confermato dal vivo il 2026-08-18) — solo una miglioria
di reattività già segnalata come "da valutare, non bloccante".

**Architettura attuale (invariata nel principio, solo nel ritmo)**: tutta la sincronizzazione Multiplayer è
short-polling HTTP, non push — nessun WebSocket/SSE nel progetto. Ogni vista che deve riflettere lo stato di un
mondo condiviso ha un proprio `ui/components/background_sync.py::BackgroundSyncLoop` (thread dedicato che
scarica gli eventi nuovi, calcola una firma economica dello stato e ridisegna solo se cambia). Prima di questo
intervento, **ogni loop del progetto girava allo stesso intervallo fisso, 2.0s** (`DEFAULT_INTERVAL_S`) —
nessuna vista, nemmeno il tracker di combattimento, aveva un ritmo dedicato più stretto. Un vero long-polling è
già implementato lato host (`network/host_server.py::handle_events`, `LONG_POLL_TIMEOUT_S=25.0`,
`LONG_POLL_INTERVAL_S=0.2`: la richiesta HTTP resta aperta finché non c'è un evento nuovo o scade il timeout) ma
il client non lo sfrutta mai — `core/world_backend.py::RemoteBackend.fetch_events` chiama sempre `GET
/events?wait=0`, esplicitamente senza attesa lunga.

**Tre opzioni valutate**: (1) intervallo più stretto solo durante un combattimento attivo — cambiamento minimo,
riusa l'infrastruttura esistente, rischio basso; (2) vero long-polling lato client (`wait>0`) — risolverebbe la
latenza alla radice usando codice server già scritto, ma `BackgroundSyncLoop` gira su un `threading.Thread`
sincrono condiviso da 7 view diverse (Home, scheda, Mondi, Incontri Master, Diario, Mappe, Incantesimi):
bloccare quel thread per secondi in attesa richiederebbe isolare il long-poll su un thread separato e
disaccoppiare i countdown visivi (`should_redraw_anyway_fn`) dal ciclo di rete — troppo rischioso da innestare
in un componente condiviso senza una sessione dedicata solo a quello; (3) redraw immediato in-process per le
azioni del master quando ospita in locale (il caso più comune) — risolve solo metà del problema, i giocatori
remoti restano il caso critico. **Scelta: opzione 1**, la più sicura e già sufficiente a un miglioramento
misurabile, senza toccare l'infrastruttura di rete condivisa da tutto il Multiplayer.

**Fix**: `BackgroundSyncLoop.__init__` accetta ora `interval_s` sia come numero fisso sia come funzione
richiamata ad ogni giro (`IntervalArg = float | Callable[[], float]`, nuovo tipo esportato dal modulo) — un
eventuale errore nel calcolo ricade sul default invece di far cadere il loop, stesso principio "best effort, mai
bloccante" già usato per le altre callback della classe.

- **Lato giocatore** (`ui/views/world/world_view.py::_start_detail_sync`, l'intero schermo "dettaglio mondo",
  non solo il combattimento): nuova costante `_DETAIL_SYNC_INTERVAL_COMBAT_S = 0.75` accanto alla
  `_DETAIL_SYNC_INTERVAL_S = 2.0` esistente. Una funzione `_interval()` interroga
  `master_repo.get_visible_encounter_for_world(world_id)` (la stessa query già usata da `_live_combat_section`
  per decidere se disegnare la sezione) ad ogni giro: se c'è un incontro visibile scende a 0.75s, altrimenti
  resta a 2.0s — niente più carico di rete/DB su membri/mappe/richieste quando non c'è combattimento in corso.
- **Lato master** (`ui/views/master/master_encounter_view.py::_start_sync`): nuova costante
  `_ENCOUNTER_SYNC_INTERVAL_S = 0.75`, passata SENZA condizione — `MasterEncounterView` esiste solo mentre il
  Master ha un incontro aperto a schermo intero (istanziata da `MasterEncounterListView`), è quindi già per
  definizione il caso d'uso più "live" del progetto: nessuna logica di visibilità necessaria qui.

Risultato: la latenza peggiore end-to-end per un evento che deve attraversare host→giornale→client scende da
un intervallo fisso di 2.0s (fino a ~4s nel caso peggiore per un giocatore remoto) a 0.75s su entrambi i lati
durante un combattimento — resta comunque short-polling, non il quasi-istantaneo di un vero long-poll
(opzione 2, non scelta), ma un miglioramento di ~2.7x senza toccare l'infrastruttura di rete condivisa.

Nessuna costante di timing era testata prima (verificato con grep su `test_*.py`), quindi il cambiamento non
rompeva nessun test esistente — ma non c'era nemmeno copertura sul comportamento NUOVO (intervallo dinamico,
condizione di attivazione). Nuovi test in `test_combat_tracker_condiviso.py`, sezione [7] (11 controlli nuovi,
36→47 nel file): `[7a]` `BackgroundSyncLoop._current_interval()` risolve correttamente sia un numero fisso sia
una funzione, e ricade sul default se la funzione solleva; `[7b]` l'intervallo di `WorldsView` sale a 0.75s
quando l'incontro diventa visibile e torna a 2.0s quando viene nascosto di nuovo; `[7c]` `MasterEncounterView`
usa sempre il valore stretto. Verificato: `compileall` pulito, suite intera 33/35 file al 100% (stessi 2 residui
ambientali pre-esistenti, non causati da questo lavoro). **Nessun commit fatto.**

---

## Rimozione di una classe da un personaggio multiclasse (2026-08-20)

Ultima voce aperta dalla revisione generale del 2026-08-19 (§ sopra, "Proposte emerse da questa revisione, non
ancora decise da Davide", punto 3): `character_repo.py::remove_character_class()` esisteva già lato repository
(una semplice `DELETE` sulla riga `character_classes`) ma non era mai stata agganciata a nessun pulsante — un
personaggio multiclasse poteva solo aggiungere una classe o scendere di livello, mai togliersi del tutto una
classe presa per errore.

**Scope deciso**: rimozione solo della classe SECONDARIA, mai della primaria — `characters.class_name/subclass/
level` rappresentano sempre e solo la classe primaria in tutto il resto del codice (vedi
`multiclasse_design.md` §3 punto 2), promuovere la secondaria al suo posto avrebbe richiesto riscrivere quei tre
campi più ricalcolare dado vita/spellcasting_ability/tutto ciò che ne dipende: un lavoro diverso e più rischioso,
fuori scope per una feature pensata per il caso comune "ho cliccato + Multiclasse e scelto la classe sbagliata".
Con al massimo 2 classi per il PHB, la guardia è semplice: il pulsante di rimozione esiste solo per la classe
`is_primary=False`.

**Nuova funzione di orchestrazione**, `character_repo.py::remove_multiclass_class(character_id,
character_classes_id) -> bool`: cancella la riga, risincronizza il livello totale
(`sync_character_total_level`), e risincronizza slot incantesimo e risorse di classe sull'unica classe rimasta —
`init_class_resources()` fa già l'unione sulle classi rimaste in `character_classes`, quindi ripulisce da sola
le risorse della classe tolta senza bisogno di codice apposito. Per gli slot incantesimo serviva invece un
intervento esplicito: `auto_init_spell_slots()` è un no-op silenzioso per una classe non incantatrice (per
design — lascia gli slot intatti se richiamata su una classe senza `caster_type`), quindi rimuovendo un Mago da
un Guerriero+Mago i totali del pool combinato multiclasse sarebbero rimasti stantii. Nuova funzione privata
`_clear_spell_slot_totals()`, richiamata solo quando né `auto_init_spell_slots()` né
`init_borrowed_caster_slots()` (Mistificatore Arcano/Cavaliere Mistico) trovano una classe incantatrice tra
quelle rimaste.

**Limite noto e dichiarato, non un dimenticanza**: competenze (`character_proficiencies`) e incantesimi
conosciuti (`known_spells`) ottenuti tramite la classe rimossa NON vengono ripuliti — nessuna delle due tabelle
ha una colonna che leghi la riga alla classe di origine (stesso limite già accettato altrove per gli incroci
rari di `multiclasse_design.md` §8.2), separarli richiederebbe uno schema nuovo. Il dialog di conferma in
`profilo_tab.py` lo dichiara esplicitamente ("toglili a mano dalle rispettive sezioni se necessario") invece di
promettere una pulizia che non avviene.

**UI** (`ui/views/character_sheet/profilo_tab.py`): riga "Rimuovi NomeClasse (classe secondaria, Lv.N)" sotto la
riga classe/razza dell'header Profilo, visibile solo se il personaggio ha una classe secondaria — icona CLOSE
neutra + testo piccolo (`text_3`), stesso registro visivo delle righe cliccabili già in uso (`Container` +
`ink=True`, non un `ft.Row` che in Flet 0.86.5 non ha `on_click`) invece di un bottone vero, per non competere
visivamente con Level up/Level down/Multiclasse. Il dialog di conferma (`_on_remove_multiclass_click`) mostra il
nuovo livello totale, una stima dei PF da sottrarre (`core.level_manager.estimate_hp_loss()` per ogni livello
della classe rimossa più l'eventuale bonus PF permanente di sottoclasse, stessa formula "media" già usata dal
Level down esistente — dichiarata come stima, non un'inversione esatta) e l'avviso su competenze/incantesimi non
ripuliti, prima di confermare con un pulsante `danger_fill` (mai `primary_fill` — è un'eliminazione).

**Verificato**: nuova sezione `[11]` in `test_multiclasse.py` (5 scenari — Ranger4/Mago3 con risincronizzazione
corretta della tabella half-caster del solo Ranger rimasto, Guerriero+Mago con azzeramento totale degli slot
quando non resta nessun incantatore, Barbaro+Monaco con pulizia corretta delle risorse di classe, guardia sulla
primaria, guardia su un personaggio a classe singola — 86/86 nel file, da 72). Suite intera: 34/36 file al 100%
(stessi 2 residui ambientali pre-esistenti, `test_qr_scan.py`/`test_versione_app.py`, indipendenti da questo
lavoro). `compileall` pulito.

**Bug report di Davide, screenshot reale della UI**: la riga "Rimuovi Mago (classe
secondaria, Lv.3)" era visibile esattamente dove previsto (header Profilo, sotto la
riga classe/razza) ma il click non apriva alcun dialog — nessun errore visibile
(l'app è un pacchetto desktop, nessuna console). Causa: la riga usava un
`ft.Container(..., on_click=..., ink=True)` SENZA `bgcolor` esplicito — un Container
Flet/Flutter senza colore di sfondo non è affidabile per l'hit-test del tap del proprio
`on_click`. Corretto sostituendo il Container con un `ft.TextButton(content=...)` —
lo stesso controllo già usato e confermato funzionante ovunque in questo header
(Level up/Level down/Multiclasse, "Salva" XP) — **verificato dal vivo da Davide,
funziona**.

**Ipotesi di causa poi SMENTITA da Davide**: per estensione, era stato aggiunto
`bgcolor=design.T().surface` anche a `_show_level_up_class_picker()` (il dialog
"quale classe sale?"), che usa lo stesso pattern Container-senza-bgcolor — ma
Davide ha confermato che quel dialog **funzionava già e lo aveva già verificato
in una sessione precedente**, quindi NON era un bug gemello: la "regola" *"un
Container senza `bgcolor` non hit-testa il click"* dedotta dal primo caso è
**falsificata da questo controesempio** (stesso pattern, nessun bgcolor, eppure
funzionante). La causa reale del bug originale resta quindi non del tutto
accertata — più plausibile un conflitto di gesture con un antenato (l'header
Profilo ha un intero blocco cliccabile per il cambio foto sull'avatar, il dialog
"quale classe sale?" no) che una regola generale su `bgcolor`. Il `bgcolor`
aggiunto al picker resta nel codice (innocuo, non serviva ma non rompe nulla),
ma **non va preso come una correzione di un bug reale** — vedi
`regole_flet_api.md`, voce aggiornata di conseguenza. La sostituzione con
`ft.TextButton` sulla riga "Rimuovi classe" resta l'unico fix verificato.
`compileall` pulito, `test_multiclasse.py` ancora 86/86 (il bug UI non è coperto
da un test automatico — puramente di interazione, non di logica dati). **Nessun
commit fatto.**

---

## Export scheda personaggio in PDF (2026-08-20)

Ultima voce del piano di lavoro rimasta aperta dopo il passo 6 del Bottino e la rimozione
classe multiclasse (voci sopra): la ricognizione era ferma da settimane in
`docs/pdf_sheet_reference/` (README.md + `raw_extraction.json` da `pdfplumber` +
`grid-1/2/3.png` a 150dpi con griglia 25pt), nessuna riga di modulo scritta. Richiesta
esplicita di Davide di finire questa e la rimozione classe "così finiamo tutte le
implementazioni" prima di valutare la prima release ufficiale v1.0.0.

**Approccio**: il template (`dnd_blankcharactersheet_it.pdf`, 3 pagine, 594×783pt) è un
PDF vettoriale piatto senza campi AcroForm — l'unico modo di compilarlo è disegnare un
overlay di testo per pagina con `reportlab.pdfgen.canvas` (origine BASSO-sinistra) e
fonderlo sopra il template originale con `pypdf` (`PdfReader`/`PdfWriter.merge_page()`).
Le coordinate derivano da `raw_extraction.json` (origine ALTO-sinistra, convertite con
una funzione `_y()`) più calibrazione a vista dove il JSON non bastava (cerchi/scudi/
caselle decorative, mai testo). Nuove dipendenze `reportlab==5.0.0`/`pypdf==6.16.1`
(entrambe pure Python — nessuna libreria di sistema, a differenza dei picker nativi già
in `pyproject.toml`), pinnate in `requirements.txt` e `pyproject.toml`. Template copiato
in `assets/character_sheet_template.pdf` (asset bundlato, letto a runtime).

**Delegato in background** (sessione lunga, calibrazione meccanica ripetitiva —
lettura visiva della griglia, render di prova, confronto, correzione, ripetere) a un
sotto-agente con un brief molto dettagliato: README già scritto da leggere per intero,
le 3 decisioni di design già confermate con Davide da NON rimettere in discussione
(font auto-shrink mai troncato, solo le prime 3 armi equipaggiate in tabella + resto
in elenco compresso, pagina 3 solo se `spellcasting_ability` valorizzata), la lista
esatta delle funzioni di `character_repo.py` da usare per raccogliere i dati, e
l'istruzione esplicita di NON fidarsi delle coordinate calcolate a occhio ma di
renderizzare (`pdftoppm`) e leggere l'immagine risultante per verificare ogni volta.

**Consegnato**: `core/pdf_sheet_exporter.py` (modulo puro, no Flet — stessa convenzione
di `core/character_stats.py`/`weapon_calculator.py`), API pubblica
`export_character_pdf(character_id, output_path) -> bool` (mai un'eccezione — `False` +
log se il personaggio non esiste o qualcosa va storto, stesso contratto di tutte le
altre funzioni "best effort" del progetto) e `suggested_pdf_filename(character_id)`
(riusa lo slug/timestamp di `character_export.suggested_export_filename()`, nessuna
duplicazione di regex). `test_pdf_sheet_export.py`, stessa convenzione di
`test_multiclasse.py` (HOME temporaneo, `check()`/`main()`): incantatore → 3 pagine,
marziale puro → 2 pagine, >3 armi equipaggiate → nessuna eccezione, backstory 2000+
caratteri → percorso di auto-shrink senza eccezioni, `character_id` inesistente →
`False` mai un'eccezione. 17/17 al primo giro.

**Verifica indipendente e bug reale trovato** (dopo la consegna del sotto-agente, prima
di considerare il lavoro chiuso): generato un personaggio di prova reale (Mago 6 con
incantesimi/slot popolati), esportato, renderizzato con `pdftoppm` e letta l'immagine
pagina per pagina — non ci si è fidati del solo resoconto del sotto-agente. Pagine 1 e 2
fedeli al template fin dal primo giro (intestazione, 6 caratteristiche, CA/Iniziativa/
Velocità, PF/Dadi Vita/TS morte, tabella armi, monete, tutti i box di testo pagina 1 e
2). Pagina 3 (griglia incantesimi) aveva un bug reale: la baseline del nome incantesimo
era calcolata un `_ROW_HEIGHT` intero (14pt) più in basso del rigo stampato a cui
apparteneva — il testo finiva scritto sopra il rigo SUCCESSIVO invece che sopra il
proprio, effetto visivo "barrato" (il rigo tagliava il testo a metà altezza).
Confermato misurando le coordinate reali dei righi in `raw_extraction.json`
(`lines`, pagina 3): passo verticale 14pt esatto, primo rigo del livello 1/colonna 1 a
top=348.93 contro un `marker_top` di 312.5 (offset reale ≈35-36, non i 41 usati). Corretto
ancorando la baseline SOPRA il proprio rigo (`row_top - 2.5`, mai sotto) e separando
l'offset iniziale per il livello 0/Trucchetti (33, nessuna barra "SLOT TOTALI/SPESI"
sopra) da quello dei livelli 1+ (35, con la barra). Una seconda verifica visiva ha
scoperto un secondo problema, indipendente: livello 1/colonna 1 è l'UNICO punto
dell'intero foglio dove le didascalie "PREPARATI"/"NOME INCANTESIMO" sono stampate
(non si ripetono altrove, per design del template ufficiale) — la prima riga scrivibile
lì è quindi la seconda, non la prima, un rigo di capienza in meno solo in quella cella.
Entrambi corretti, ri-renderizzato e riletto per confermare: nessuna sovrapposizione
residua su nessuna colonna/livello testato (0-9 con incantesimi reali).

**Limiti noti, dichiarati non nascosti** (stesso principio già in uso per gli altri
"limiti noti" del progetto — vedi `multiclasse_design.md` §8.2): "Privilegi & Tratti"
elenca nome+livello+fonte delle feature, non la descrizione PHB completa (non ci sta in
nessun box ragionevole); Percezione Passiva non scansiona bonus da talento (es. Sagace),
solo prova+override manuale; il box "Tesoro" di pagina 2 non ha un campo dedicato nel
modello dati e viene composto dalle monete di pagina 1 più gli oggetti di categoria
"magic"; il riquadro decorativo "Simbolo/fede" resta vuoto (nessun campo dedicato);
pagina 3 mostra solo la classe PRIMARIA per l'incantesimo (il foglio fisico non prevede
comunque un modo di rappresentare un incantatore multiclasse).

**UI** (`ui/views/home_view.py`): nuovo `IconButton` "Esporta scheda PDF" nella card
personaggio, accanto a "Esporta personaggio (.dndchar)" — stesso schema a 3 rami
desktop/web/mobile di `_on_export_click`, ma per un file binario invece di JSON:
`_generate_pdf_bytes()` genera sempre prima in un file temporaneo
(`export_character_pdf()` scrive su percorso, non ritorna byte) e ne legge i byte,
perché a differenza di `character_export.export_to_json_string()` non esiste una
versione "ritorna una stringa" dell'export PDF. Il ramo desktop riusa
`ui/file_export.py::native_save_dialog()` (l'helper già estratto per l'export Mondo)
invece di duplicare ancora una volta l'AppleScript/PowerShell/zenity inline come fa
`_export_desktop()` per `.dndchar` (mai toccato, zero rischio di regressione lì).
Nessun avviso "personaggio collegato a un mondo" (quell'avviso riguarda il RE-IMPORT,
che un PDF non supporta comunque) — si esporta sempre direttamente.

Verificato: `compileall` pulito, suite intera 35/37 file (era 36, +1 per
`test_pdf_sheet_export.py`; sempre gli stessi 2 residui ambientali pre-esistenti,
`test_qr_scan.py`/`test_versione_app.py`, indipendenti da questo lavoro).
**Resta da confermare dal vivo**: aprire il dialogo di export su un dispositivo reale
(desktop testato solo a livello di generazione file/rendering PNG in questo sandbox, non
il dialogo nativo del SO — stesso limite di sempre per l'automazione macOS/Windows;
mobile per definizione non testabile qui).

**Bug report di Davide, stesso giorno, dopo un export reale** ("quasi, devi allineare
meglio le scritte ma soprattutto le abilità"): allegato il PDF vero esportato dall'app
(un Monaco 10 con più skill/salvezze proficienti), non solo una descrizione. Trovato il
file su `~/Desktop`, renderizzato con `pdftoppm` e confrontato a zoom con lo stesso
render del template vuoto — il template ha già un pallino proprio stampato su OGNI riga
di Tiri Salvezza/Abilità (misurato dopo, in `raw_extraction.json`: centro x≈96.5,
raggio≈3.3, offset Y dal `row_top` di quel rigo ≈2.9 pt, costante su tutte le righe
controllate), ma `_draw_prof_row()` ne disegnava un secondo, leggermente sfalsato
(x=92, offset Y diverso) E SEMPRE (contorno vuoto anche quando non competente) — il
risultato erano due cerchi quasi sovrapposti ma non coincidenti su tutte le 24 righe
(6 tiri salvezza + 18 abilità), l'effetto "doppio cerchio" che Davide ha notato. Corretto
allineando il cerchio disegnato esattamente sopra quello del template (stesso centro,
stesso raggio) e disegnandolo SOLO quando il personaggio è competente (il template
fornisce già il cerchio vuoto per le righe non competenti, ridisegnarci sopra un
contorno identico non serviva a nulla). Verificato di nuovo con lo stesso metodo (render
+ zoom + confronto col template vuoto) prima di richiudere: nessun doppio cerchio
residuo su nessuna delle 24 righe. `test_pdf_sheet_export.py` ancora 17/17,
`compileall` pulito. **Nessun commit fatto.**

---

## Sei richieste dal giro di test di Davide: duplicato personaggio all'uscita dal mondo, armi dal Compendio in inventario, archivio non consultabile dal master, descrizione oggetto illeggibile, danni multipli mancanti nel Bottino, tipo voce non modificabile (2026-08-20)

Lista di 10 bug/migliorie riportata da Davide dopo un giro di test dell'app. Di questi,
4 non erano bug reali (zoom mappa: già implementato, `InteractiveViewer` 1x-5x; "Prendi"
dal deposito comune: già rimaterializza correttamente sui dispositivi terzi da un fix
precedente; malattie/veleni: 3+14 è il totale reale trascritto dalla DMG, non una lista
tagliata; sezione Ambiente: richiesta di design aperta, discussa con Davide ma non
implementata in questo giro — resta da riprendere). I 6 restanti erano reali, in ordine
di rischio crescente:

**1. Duplicato del personaggio all'uscita dal mondo** (bug report: "mi ritrovo 2 copie
del personaggio in locale"). Causa: `_do_leave()` chiamava `character_repo.
detach_world_instances()` in blocco, che slega SEMPRE l'istanza dal mondo trasformandola
in un secondo personaggio locale — senza controllare che l'originale (`origin_character_
id`, per un'istanza "porta com'è"/`core/character_instances.py::_copy_character`, una
vera COPIA) fosse ancora vivo. **Decisione esplicita di Davide** (non una scelta
a senso unico presa in autonomia): all'uscita, se l'origine locale esiste ancora, il
giocatore sceglie istanza per istanza — dialog nuovo, `WorldsView._show_leave_merge_
dialog()` — se "Fondere con il locale" (riusa `character_instances.apply_refresh()`,
la stessa funzione dietro "Aggiorna il mio foglio", poi cancella la copia del mondo) o
"Eliminare la copia del mondo" (cancella la copia, l'originale resta intatto); messaggio
esplicito nel dialog che il personaggio locale non viene MAI toccato, solo la copia del
mondo che si sta lasciando. Se l'origine non esiste più (cancellata nel frattempo):
fallback storico invariato, nuova `character_repo.detach_world_instance()` (singolare).
Nuova `character_repo.get_owned_world_instances(world_id, owner_device_id)`. Nuovo
`test_uscita_mondo_fusione.py` (20/20).

**2. Armi dal Compendio Oggetti Magici finiscono sempre in inventario** (bug report:
"quando assegno un'arma dagli oggetti magici finisce sempre nell'inventario"). Causa:
le 264 voci di `magic_items.json` non hanno mai un campo `entry_kind` (solo `category`,
testo libero tipo "Arma (qualsiasi spada)") — `master_magic_item_generator_dialog.py`
usava sempre il default `"magic_item"`. Il fix del 2026-08-20 precedente per `weapon`/
`armor` copriva solo le voci create a mano o l'oggetto magico "Personalizzato", non la
pesca dal Compendio. Nuova `_resolve_entry_kind(item)`, che riusa l'euristica già
esistente `_custom_mechanics_kind()` (categoria → base via `magic_item_category_base()`)
anche quando `entry_kind` non è esplicito nel dict. La descrizione non andava persa in
scrittura (già finiva in `weapons.magic_description`), solo l'arma finiva nella sezione
sbagliata. `test_mondo_senza_rete.py` [12b] (+7 controlli).

**3. Personaggio archiviato non consultabile dal master** (bug report: "l'archiviazione
è disponibile al master? Dove si può consultare?"). Gap reale confermato: `get_master_
visible_characters()` esclude sempre `world_instance_archived=1`, nessuna vista Master
lo mostrava. Nuova card "Personaggi Archiviati" in `WorldsView._render_detail` (stesso
gate di permesso di "Interviene a distanza", `CMD_XP_GRANT`), sola lettura — niente
`SheetView` editabile per un personaggio altrui, mai stata un'opzione. Pulsante "Vedi
dettagli" apre un riepilogo (classe/razza/livello/background/PF/conteggio armi-oggetti-
incantesimi), stesso principio dello stat block dialog di mostri/NPC in Sezione Incontri.
Nuova `character_repo.get_archived_world_instances(world_id)`. `test_mondo_senza_rete.py`
[13] (+13 controlli).

**4. Descrizione oggetto magico illeggibile in inventario** (bug report: "perde la sua
descrizione diventando sostanzialmente inutile... bisogna aggiungere la possibilità di
cliccare sull'oggetto e leggerne la descrizione... come nella sezione incontri del
master... con anche la possibilità di modificarla"). Non era una perdita di dati (`create_
inventory_item(description=...)` la salva sempre), ma `_item_row()` in `inventario_tab.py`
non la mostrava mai — bisognava aprire il form "Modifica" completo solo per leggerla
(armi/armature invece già la mostrano inline). Nuovo pulsante 📖 "Descrizione" per riga →
`InventarioTab._open_item_description_dialog()`, dialog dedicato con `TextField`
multilinea precompilato, editabile, "Salva" scrive con `update_inventory_item()` e
instrada al mondo (`_push_item_to_world()`) se il personaggio è un'istanza. Vale per
QUALSIASI oggetto (assegnato, aggiunto a mano, o già presente), nessuna distinzione di
provenienza. `test_fase_4.py` [9] (+6 controlli).

**5. Danni magici multipli tipizzati mancanti nel Bottino/Oggetti Magici** (bug report:
"nella sezione giocatore puoi aggiungere più danni, di vari tipi, esempio: ghiaccio 1d8
+ fuoco 1d6 oltre a quelli base dell'arma" — il form del Bottino aveva solo un dado/tipo
singolo). Nuova colonna `loot_stash_entries.weapon_magic_damages` (TEXT, JSON, stesso
formato `[{"dice","type","note"}]` di `weapons.magic_damages`, migrazione self-healing
in `data/database.py`), filata attraverso `LootStashEntry`, `loot_repo.create_entry/
update_entry/replica_upsert_entry`, `master_loot_assign_dialog.py` (`_EMPTY_MECHANICS`,
`build_weapon_mechanics_fields()` — nuove righe ripetibili "+ Aggiungi danno" identiche
a `inventario_tab.py::_open_weapon_dialog`, `item_from_stash_entry`, `_create_recipient_
item`, `_recipient_item_payload`) e `core/world_backend.py` (`_handle_loot_assign`,
`_handle_loot_stash_add/_update/_claim`, `_loot_stash_entry_payload`). `test_master_
world_scoping.py` [9] (+9 controlli: round trip repo, presa dal deposito, assegnazione
dal Master, righe ripetibili lato UI).

**6. Tipo di un Artefatto non modificabile dopo il salvataggio** (bug report: "quando
un artefatto viene salvato in archivio... quando lo modifico deve avere la possibilità
di essere modificato in toto... può essere selezionato il tipo, magari il master vuole
assegnare quell'effetto ad un abito, un'arma, un anello, una statuetta"). Causa: `loot_
repo.update_entry()` non toccava affatto la colonna `entry_kind`, e "Modifica Voce"
(`master_loot_view.py::_open_edit_dialog`) non aveva il dropdown tipo che invece
"Aggiungi Voce" ha sempre avuto. Aggiunto `entry_kind: str = ""` a `update_entry()`
(`""` = lascia invariato, via `COALESCE(NULLIF(?,''), entry_kind)` — non rompe i
chiamanti esistenti) e `CMD_LOOT_STASH_UPDATE`; "Modifica Voce" ora ha un dropdown "Tipo
di voce" (tutte le opzioni tranne "Monete", cambio di forma dei dati troppo diverso) con
re-render dinamico delle caselle meccaniche weapon/armor al cambio — precompilate SOLO
se il tipo non è cambiato rispetto all'originale. `test_master_world_scoping.py` [10]
(+15 controlli).

Verificato: `compileall` pulito, tutte le suite toccate (`test_uscita_mondo_fusione.py`
20/20, `test_mondo_senza_rete.py` 215/215, `test_note_e_inventario_sync.py` 93/93,
`test_character_rejoin.py` 68/68, `test_fase_4.py` 303/303, `test_master_world_scoping.py`
96/96, `test_trasferimento_dispositivo.py` 146/146) verdi, nessuna regressione. **Nessun
commit fatto.** **Resta aperta**: la richiesta sulla sezione Ambiente ("vorrei renderla
più utile ma non so come") — discussa con Davide, nessuna decisione presa in questo giro.

---

## Zoom mappa rotto su smartphone + Quantità nel Generatore Incontri per Ambiente (2026-08-20, giro successivo)

Due richieste dirette di Davide dopo la lista precedente: "lo zoom funziona per pc ma non
funziona per smartphone" (correggeva la valutazione "già implementato" della revisione
precedente, fatta solo leggendo il codice) e la proposta sulla Sezione Ambiente accettata
con una precisazione — "che tira i dadi e poi permette di creare l'incontro descritto
nella sezione incontri, in modo da facilitare il master... permettiamo anche di inserire
il risultato al master, non costringiamolo al tiro automatico".

**Zoom mappa su smartphone.** Causa (confermata via analisi del codice, non ancora su
dispositivo touch reale — vedi sotto): `ui/views/maps_view.py::_build_draw_stack()`
avvolge SEMPRE il canvas di disegno in un `ft.GestureDetector` con `on_pan_start/update/
end` (per disegnare/cancellare), annidato dentro il `content` di un `ft.InteractiveViewer`
(`scale_enabled=True` per lo zoom). In Flutter, un `GestureDetector` con `on_pan_*` resta
iscritto nella gesture arena anche quando i suoi handler fanno subito `return` (modalità
"Sposta", `_draw_mode == "move"`) — il suo `PanGestureRecognizer` vince comunque un pinch
a due dita PRIMA che possa arrivare allo `ScaleGestureRecognizer` dell'`InteractiveViewer`
padre. Un trackpad non lo nota mai: lo zoom da trackpad passa da
`trackpad_scroll_causes_scale`, un canale di eventi scroll separato dalla gesture arena,
mai in competizione col `GestureDetector` annidato — da qui "funziona su PC, non su
smartphone". Fix: nuovo `_canvas_layer_for_mode(mode, gm, canvas)` — in modalità "move" il
canvas torna figlio diretto dello `Stack` (nessun `GestureDetector`, nulla con cui
competere: pan/zoom nativi dell'`InteractiveViewer` liberi); in "pen"/"eraser" resta
avvolto come prima (serve per disegnare). `_build_draw_stack()` lo usa alla costruzione
iniziale, `_select_mode()` lo ricostruisce ad ogni cambio modalità (prima cambiava solo
`viewer.pan_enabled`, mai la presenza del `GestureDetector`). **Non risolve il pinch
DURANTE il disegno** (modalità "pen"/"eraser", per scelta deliberata — richiederebbe un
recognizer custom che distingue 1 e 2 dita, complessità/rischio non giustificati qui):
il Master/giocatore deve passare a "Sposta" per zoomare/pannare, esattamente il pulsante
già pensato per quello. Nuovo `test_mappe_locali_coordinate.py` [5] (+8 controlli):
verifica che il `GestureDetector` sparisca in "move" e ricompaia in "pen", e che disegnare
funzioni ancora dopo un giro pen→move→pen. **Resta da confermare dal vivo su un
dispositivo touch reale** — l'ipotesi (gesture arena di Flutter) è solida e già osservata
in una forma analoga in questo stesso progetto (`regole_flet_api.md`, "Container
cliccabile che non risponde al tap"), ma nessun test di questo sandbox può simulare un
vero pinch multi-touch.

**Quantità nel Generatore Incontri per Ambiente.** Prima, "Aggiungi Incontro" creava
SEMPRE una copia di ciascuna creatura risolta nel bestiario, qualunque fosse la quantità
scritta in prosa nella riga tirata (es. "2d4 gnoll") — il Master doveva leggere il testo e
aggiungere le copie in più a mano con "+ Aggiungi mostro". Nuova
`_suggest_quantities(text, creatures)` in `master_forest_encounters_dialog.py` (funzione
pura, nessun Flet): abbina in ordine di lettura un'espressione di quantità ("NdM" o un
numero fisso) a ciascuna creatura — le tabelle DMG scrivono sempre la quantità PRIMA del
nome, nello stesso ordine delle creature in `creatures` (verificato a mano su tutte le
voci multi-creatura dei 4 ambienti trascritti). Le percentuali tra parentesi ("(50%)")
vengono escluse per non essere scambiate per una quantità. **Nessun abbinamento se il
conteggio dei numeri trovati non coincide con quello delle creature** — meglio nessun
suggerimento che uno probabilmente sbagliato (es. una CD/un'altra cifra nella prosa che
confonderebbe il conteggio); in quel caso il campo resta comunque compilabile a mano.
Ogni creatura risolta ha ora un campo "Quantità" (default 1, sempre editabile) e, solo
quando il suggerimento è un vero dado (non un numero fisso), un pulsante 🎲 che tira
quella espressione (`core/dice.py::roll()`, stesso motore di tiro già in uso altrove
nell'app) e precompila il campo — **mai un tiro forzato**: il Master può ignorare il dado
e scrivere il numero che preferisce, prima o dopo aver premuto 🎲. "Aggiungi Incontro"
crea tante copie numerate quante il campo Quantità indica AL MOMENTO della conferma
(stessa convenzione "Nome 1"/"Nome 2" già in uso in "+ Aggiungi NPC dalla Rubrica" di
`MasterEncounterView`), non più sempre una. Nuovo `test_incontri_ambiente_quantita.py`
(19/19): la funzione pura su righe reali della tabella (incluso il caso "nessun
abbinamento sicuro"), e un flusso UI end-to-end con `random.randint` seminato
deterministicamente (tira la riga 3 di Foresta Silvana, verifica il precompilamento, tira
il dado di quantità, sovrascrive a mano un campo, conferma, verifica che l'incontro creato
abbia esattamente le quantità indicate nei campi).

Verificato: `compileall` pulito, `test_mappe_locali_coordinate.py` 21/21,
`test_fase_d.py` 101/101, `test_note_e_inventario_sync.py` 93/93,
`test_incontri_ambiente_quantita.py` 19/19, `test_fase_4.py` 303/303 — nessuna
regressione. **Nessun commit fatto.**

---

## Dossier PNG: ritratto NPC in Rubrica + sincronizzazione verso i giocatori in un Mondo condiviso (2026-08-20, giro successivo)

Richiesta di Davide prima del prossimo rilascio, con riferimento visivo allegato (una
tessera identificativa "Her Majesty Secret Service"): "dare la possibilità di inserire
l'immagine dell'npc al master nella rubrica degli npc. quando poi quell'npc viene
condiviso in una nota... il giocatore può premere sul nome del personaggio e vedere
l'immagine... in pg incontrati vorrei farlo apparire tipo carta di identità con
descrizione sotto, tipo dossier... solo senza il top secret senza il bianco e nero e
senza le impronte digitali ma con la descrizione" — stile coerente con "Arcane Ledger"
(guida `ui-ux-pro-max`).

**Modello e ritratto lato Master.** Nuovo `MasterNpc.image_data` (base64, stesso formato
di `characters.image_data`/`game_maps.image_data`), colonna self-healing in
`data/database.py` (`_add_column("master_npcs", "image_data", ...)`), filata attraverso
`master_repo.create_npc()`/`update_npc()`/`_row_to_npc()`. `MasterNpcListView._open_npc_form()`
(`ui/views/master/master_npc_list_view.py`) ha ora un picker ritratto — stessi identici 3
rami web/mobile/desktop già consolidati per mappe/personaggio, riusati DIRETTAMENTE da
`ui/views/maps_view.py` (`_pick_from_library`/`_pick_mobile`/`_pick_desktop`/`_data_uri`,
già scritti per accettare una `Page` diretta, non solo una `MapsView` — nessuna
duplicazione). Thumbnail nella card della lista NPC e nel dettaglio del Master.

**Dossier condiviso.** Nuovo `ui/components/npc_dossier.py` (`build_npc_dossier_column()`/
`show_npc_dossier_dialog()`, sola lettura) — stesso principio di `monster_picker.py::
show_stat_block_dialog()`, un solo posto che sa costruire la card, riusato sia lato
giocatore sia lato Master. Layout: nome + campi (ruolo/razza/tipo/taglia/allineamento) +
tag a sinistra, ritratto (o icona segnaposto) a destra via `design.asymmetric_row()` (si
impila da solo su schermo stretto, niente colonne fisse fuori posto su mobile), poi la
descrizione (`notes`) a tutta larghezza sotto — niente timbro, niente bianco e nero,
niente impronte digitali. In `ui/views/diary_view.py::_build_note_reading_panel()` e nel
gemello lato Master `ui/views/master/master_notes_view.py`, una nota condivisa con
`linked_npc_id` valorizzato mostra ora un pulsante cliccabile "Collegato a: {nome}" (prima
era solo testo statico lato Master, e lato giocatore non compariva affatto — `note` per
una nota condivisa in `diary_view.py` è in realtà un `MasterCampaignNote` non convertito,
fuso direttamente nella stessa lista da `_merge_shared_notes()`, da cui il `getattr`
difensivo per leggere `linked_npc_id` solo se `is_shared`). Nuovo `test_npc_dossier.py`
(27/27): round trip repo, costruzione pura della card, pulsante cliccabile end-to-end sia
lato giocatore sia lato Master (con verifica che una nota SENZA collegamento non mostri
nulla — nessun falso positivo).

**Gap scoperto e chiuso nella stessa sessione: gli NPC non erano mai sincronizzati verso i
giocatori in un Mondo condiviso.** Verificato con Davide prima di dichiarare la feature
completa (`grep -rn "master_npcs" core/world_sync.py core/world_backend.py
network/host_server.py` non dava nessun risultato): a differenza di mappe/bottino/note, la
Rubrica NPC del Master non viaggiava mai verso la replica di un giocatore su un
dispositivo separato — `master_repo.save_replica_note()` degradava già da tempo (fix del
2026-08-17, `test_replica_note_fk_lock.py`) `linked_npc_id` a NULL proprio perché l'NPC
referenziato non esisteva mai in locale sul dispositivo del giocatore. Senza questo
secondo fix, il pulsante "Collegato a" sarebbe stato invisibile per qualunque giocatore su
un dispositivo diverso da quello del Master — la feature avrebbe funzionato SOLO
testandola sullo stesso dispositivo/DB. **Decisione esplicita di Davide** di completarla
subito, non rimandarla: "sì, completa ora" davanti al tradeoff (7-8 file, ampiezza
paragonabile all'introduzione del deposito bottino condiviso).

Fix, seguendo lo schema già consolidato per `loot_stash_entries` (payload pieno, nessun
pattern stub+lazy per l'immagine — un ritratto NPC è tipicamente più leggero di una foto
mappa, non giustificava la complessità di un endpoint lazy dedicato):
- `network/host_server.py::handle_snapshot()` — nuova sezione `shared_npcs`: SOLO gli NPC
  referenziati da `linked_npc_id` in almeno una nota già inclusa in `notes` (mai l'intera
  Rubrica, resta materiale privato del Master, §7B del design doc).
- Nuova `master_repo.replica_upsert_npc(data: dict) -> bool` — `INSERT ... ON CONFLICT DO
  UPDATE` per id (stesso principio di `loot_repo.replica_upsert_entry()`: l'id è quello
  generato una sola volta sull'host, mai rigenerato sulla replica).
- `core/world_sync.py::_refresh_snapshot_derived_state()` (ogni giro di sync periodico,
  ~2s) e `_finalize_join()` (ingresso in un mondo) — nuovo blocco che scrive
  `snapshot["shared_npcs"]` in locale **PRIMA** del blocco note già esistente (stesso
  file, poche righe più sotto): l'NPC deve esistere quando `save_replica_note()` valida la
  FK, altrimenti verrebbe azzerato come prima di questo fix.
- Aggiornato il commento/docstring di `save_replica_note()` (ormai obsoleto: diceva "la
  Rubrica NPC non viaggia mai") per riflettere che ora l'NPC arriva PRIMA nel caso comune —
  il controllo difensivo resta comunque come rete di sicurezza (evento fuori ordine, NPC
  cancellato dopo la condivisione), autocorretta al giro di sync successivo.

Effetto collaterale positivo non richiesto esplicitamente ma naturale con questo design
("eventual consistency", stesso principio già di bottino/mappe/note): se il Master
modifica il ritratto o la descrizione di un NPC DOPO averlo già condiviso, l'aggiornamento
arriva al giocatore al giro di sync successivo, senza bisogno di ri-condividere la nota o
di un evento dedicato.

Nuovo `test_npc_sync_multiplayer.py` (18/18) — quattro parti, tutte con un vero
`WorldHostServer` + `RemoteBackend` (stesso schema end-to-end di `test_note_sharing.py`
parte [5]): [1] un NPC collegato a una nota condivisa PRIMA dell'ingresso di un giocatore
arriva comunque sulla sua replica via `_finalize_join()`, col ritratto, collegamento non
azzerato; [2] un NPC NON referenziato da nessuna nota visibile non compare MAI in
`shared_npcs` (privacy verificata sullo snapshot HTTP reale, non solo sulla tabella
condivisa in-process); [3] un NPC condiviso DOPO l'ingresso e un ritratto aggiornato
arrivano al giro di `_refresh_snapshot_derived_state()` successivo, senza un nuovo evento
dedicato; [4] rete di sicurezza invariata — un NPC mai arrivato degrada ancora a NULL,
nessuna regressione sul fix del 2026-08-17.

Verificato: `compileall` pulito, `test_npc_dossier.py` 27/27, `test_npc_sync_multiplayer.py`
18/18 (nuovi), più l'intera superficie di test multiplayer già esistente confermata verde
per escludere regressioni sul sistema di sync (`test_note_sharing.py` 26/26,
`test_replica_note_fk_lock.py` 22/22, `test_lan_host_client.py` 113/113,
`test_ingresso_lan_sincronizzazione.py` 31/31, `test_character_instance_sync.py` 20/20,
`test_combat_tracker_condiviso.py` 47/47, `test_home_sync_rimozione_mondo.py` 14/14,
`test_esportazione_mondo.py` 86/86, `test_master_world_scoping.py` 96/96,
`test_mondo_senza_rete.py` 215/215, `test_npc_race_autofill.py` 33/33). **Nessun commit
fatto.** **Resta da confermare dal vivo su due dispositivi fisici** — stesso limite di
sempre, non simulabile in modo affidabile in questo sandbox (il test end-to-end usa un
vero `WorldHostServer` in un thread separato, ma sullo stesso processo/DB).

---

## Audit documentazione e igiene repository dopo il rilascio v0.3.4 (2026-08-20)

Richiesta di Davide dopo il rilascio di v0.3.4: aggiornare tutta la documentazione allo
stato attuale del progetto, verificare che la repo GitHub (pubblica) sia in ordine, che
`README.md` rispecchi al 100% il progetto e che `.gitignore` nasconda tutto ciò che non
deve essere versionato, più un controllo generale di cosa manca o va cambiato.

**Verifica repo/gitignore**: nessun file tra `.venv/`, `build/`, `__pycache__/`, `*.db`
risultava tracciato (il `.gitignore` esistente li copre correttamente). Trovati e rimossi
dall'indice due `.DS_Store` residui committati prima che la regola `.gitignore` esistesse
(`data/.DS_Store`, `data/game_data/.DS_Store` — `git rm --cached`, restano sul disco,
smettono solo di essere versionati).

**`README.md` — non rispecchiava più il progetto reale su più punti**: versione Flet
dichiarata 0.85.3 invece di 0.86.5 (aggiornata dal 2026-08-05); roadmap che elencava come
"da fare" tre cose già completate da tempo (export PDF, aggiornamento automatico in-app —
quest'ultimo dichiarato apertamente "rimandato" nel testo, mentre è **fatto** dal
2026-08-17); Sezione Master descritta solo con "Incontri e Bottino", senza menzionare
Oggetti Magici (264 voci + generatore), Artefatti DMG, generatore Ambiente con quantità, e
senza il nuovo Dossier NPC di questa sessione; nessuna menzione di export/import
`.dndchar`/`.dndworld` né del trasferimento personaggio su altro dispositivo; conteggio
background PHB indicato 12 invece di 13 (Ciarlatano è stato aggiunto più avanti nello
sviluppo); tabella piattaforme con iOS "✅" alla pari delle altre quattro, quando in realtà
non fa parte della pipeline di release automatica (`.github/workflows/release.yml` builda
solo Windows/macOS/Linux/Android) ed è buildabile solo a mano; albero della struttura file
non più aggiornato (mancavano `core/pdf_sheet_exporter.py`, `ui/components/`,
`ui/design.py`, `extensions/`, vari repository nuovi). Riscritto integralmente allineando
Funzionalità/Piattaforme/Stack tecnico/Struttura/Roadmap allo stato reale del codice.

**Licenza mancante**: il README linkava `[MIT](LICENSE)` ma nessun file `LICENSE` esisteva
nella repo (verificato con una ricerca su tutto il progetto, solo licenze di dipendenze
in `.venv`/`build`) — su una repo pubblica è un link rotto reale, non solo un dettaglio.
Aggiunto `LICENSE` (MIT), coerente con quanto il README promette da sempre.

**`Dockerfile` disallineato**: pin `flet==0.85.3`, la versione precedente all'aggiornamento
del 2026-08-05 — un `docker compose up` oggi avrebbe installato una versione di Flet non
più in lockstep con `flet-webview`/le altre estensioni pinnate a 0.86.5 nel resto del
progetto, rischiando le stesse rotture d'API già documentate tra le due versioni.
Corretto a 0.86.5, aggiunte anche `qrcode`/`reportlab`/`pypdf` (mancavano dall'immagine
Docker, servono rispettivamente per la generazione QR e l'export PDF, entrambe feature
pure Python già usate dall'app). **Non toccati** invece `flet-camera`/
`flet-permission-handler`/`pyzbar` in `pyproject.toml` ma assenti da `requirements.txt`:
verificato che è intenzionale (commenti esistenti nel file) — sono dipendenze
Android/iOS-only per lo scanner QR, irraggiungibile su desktop, e `pyzbar` richiederebbe
la libreria di sistema `libzbar` non garantita su ogni macchina di sviluppo.

**`CLAUDE.md`**: la sezione "Piano di lavoro attivo" era già aggiornata (comprendeva già
le voci di questa stessa sessione su zoom mappa/quantità Ambiente/Dossier NPC, scritte
prima del rilascio). Corretti invece due punti stantii nelle sezioni di riferimento
stabile: l'elenco dei 12 file background in "Struttura File" usava ancora i vecchi nomi
derivati dall'inglese (Orfano/Studioso/Vagabondo invece di Monello/Sapiente/Forestiero, e
mancava Ciarlatano) — la stessa regola critica di terminologia enunciata in cima al file
veniva violata dal file stesso più in basso; la riga "Requisiti" in "Panoramica" suggeriva
`pip install flet>=0.21.0`, un vincolo lasco incompatibile con la scelta deliberata di
pinning esatto spiegata ovunque nel resto del documento; la frase di apertura della
sezione "Panoramica" diceva ancora che il tracker di combattimento condiviso e
l'esportazione `.dndworld` restavano da verificare dal vivo, smentita poche righe sotto
nella stessa "Piano di lavoro attivo" (confermati dal vivo il 2026-08-18).

Nessuna modifica al codice applicativo in questa sessione — solo documentazione,
repository e `Dockerfile`. **Nessun commit fatto**, in attesa di conferma di Davide.

---

## Playtest dal vivo di Claude (Flet web mode + Playwright) — danno/cura mostri nel tracker, bump versione (2026-08-23)

Richiesta di Davide: "controlla il progetto... testa l'app come se stessi organizzando
una sessione con master e giocatori", prima di consultare il second brain Obsidian
(wiki-query) per pattern trasversali. Novità di metodo rispetto alle sessioni precedenti:
l'app è stata davvero **lanciata e pilotata** (non solo letta/testata a unit test) —
`FLET_WEB=true python main.py`, poi Playwright/Chromium headless con screenshot reali ad
ogni passo, simulando un Master che prepara una sessione (crea un mondo, avvia l'hosting
LAN, apre la Sezione Master, cerca un mostro nel Bestiario, popola il tracker di
combattimento, usa il Calcolatore Difficoltà). L'intera test suite (45 file) è stata
anche rilanciata per intero fuori dal batch multiplayer abituale — tutta verde a parte due
falsi negativi ambientali (porta 8765 occupata dal server web di prova lanciato in
parallelo; `pyzbar` non installato in questo venv, già previsto/commentato in
`pyproject.toml`).

**Bug trovato e corretto — `ui/views/master/master_encounter_view.py`**: nel tracker di
combattimento, un PG istanza di mondo ha un vero dialog "Applica danno"/"Applica cura" con
importo numerico (`ui/components/remote_action_dialogs.py`, condiviso con "Interviene a
distanza"), ma un mostro/NPC nello stesso tracker aveva solo due iconcine ±1
(`self._on_hp_delta(mm, -1)`/`(mm, 1)` hardcoded) — nessun campo numerico, nessuna
scorciatoia. Un danno a due cifre (comunissimo: 1d8+3 di una spada lunga, una Palla di
Fuoco su più mostri) richiedeva un clic per punto ferita, proprio nel momento in cui il
tavolo aspetta che il turno vada avanti. Trovato leggendo il codice dopo essersi accorti
dell'asimmetria nella UI dal vivo (screenshot dei due controlli affiancati), non solo
cliccando.

**Fix**: i due `IconButton` ±/+ di un mostro/NPC ora aprono lo stesso
`show_damage_dialog`/`show_heal_dialog` già in uso per i PG, invece di chiamare
`_on_hp_delta` con un delta fisso — nuovi metodi `_open_monster_damage_dialog()`/
`_open_monster_heal_dialog()`. Nessuna pipeline di comando di rete coinvolta (un
mostro/NPC non ha un `characters` proprio da sincronizzare altrove): il payload del
dialog scrive direttamente sulla riga dell'incontro via `_on_hp_delta`, invariato nella
firma. Corretto anche un bug collaterale minimo nello stesso `_on_hp_delta`: il delta
positivo non era mai clampato a `hp_max` (solo `max(0, ...)` sul lato danno), quindi
curare ripetutamente un mostro già "in salute" poteva spingere `hp_current` oltre
`hp_max` — ora clampato su entrambi i lati, coerente con la barra PF che assume
`hp_current <= hp_max`. Il campo "Colpo critico" del dialog danno (rilevante solo per i
tiri salvezza contro la morte di un PG, `core/damage_rules.py`) resta nel payload ma non
viene letto in questo percorso — non si applica a un mostro.

Verificato con un nuovo file dedicato, `test_encounter_monster_damage_dialog.py` (5/5):
apertura dialog dal click, importo a due cifre applicato in un solo invio (danno e cura),
clamp a `hp_max` sulla cura, pavimento a 0 sul danno eccessivo — nessun test esistente
copriva questo percorso (`_on_hp_delta` non compariva in nessun altro `test_*.py`), motivo
per cui il gap non era mai stato intercettato prima. Nessuna regressione:
`test_combat_tracker_condiviso.py` 47/47, `test_master_world_scoping.py` 96/96,
`test_master_remote_actions.py` 81/81, `test_fase_4.py` 303/303,
`test_mondo_senza_rete.py` 215/215, più l'intera suite di 45 file rilanciata per intero.

**Housekeeping collaterale**: `version.py` (`APP_VERSION`) e `pyproject.toml`
(`[project].version`) erano fermi a `"0.3.4"` mentre l'HEAD del repo era già un commit
avanti al tag di rilascio `v0.3.4` — esattamente il caso che `test_versione_app.py` esiste
per intercettare, e che infatti risultava rosso su questo checkout. Bump di entrambi a
`0.3.5` in lockstep (`test_fonte_di_verita_unica` impone che coincidano); nessun'altra
occorrenza di `0.3.4` residua nel codice applicativo.

---

## Bug reale: Level Down non risincronizzava character_classes.level — trovato dal vivo, corrotto e ripristinato un personaggio di produzione (2026-08-23, sessione "allarghiamo la ricerca")

Continuazione della sessione precedente sullo stesso giorno: Davide ha chiesto di allargare
la ricerca di gap "da tavolo" ad altre aree non ancora coperte dal playtest (incantesimi in
combattimento, riposo, mappe, level-up, export PDF), sempre con l'app lanciata e pilotata
dal vivo (Flet web mode + Playwright), non solo letta.

**Riposo e incantesimi — nessun problema trovato**, entrambi ben rifiniti: "Riposo Breve"
tira i dadi vita con trasparenza completa (roll panel con il dettaglio dei singoli dadi),
"Riposo Lungo" mostra un preview onesto di TUTTO quello che verrà ripristinato/azzerato
prima di chiedere conferma (HP, dadi vita 8→+4 per la regola PHB del riposo lungo, slot
incantesimo, risorse di classe, azioni turno, TS morte, bonus CA temp, forme/evocazioni),
e gli slot incantesimo BG3-style rispondono correttamente a un singolo clic (un incantatore
lancia UN incantesimo alla volta — a differenza del ±1 dei PF mostri sistemato nella
sessione precedente, qui la granularità a un clic è quella corretta, non un gap).

**Disegno mappe — verifica inconcludente, non un finding**: un tratto di penna disegnato via
Playwright (drag sintetico, anche con step granulari e pause) non appariva sulla mappa. Prima
di segnalarlo come bug, verificato che la LOGICA di salvataggio/normalizzazione del tratto è
già coperta da `test_mappe_locali_coordinate.py` (21/21, chiama `_on_pan_start/_on_pan_update/
_on_pan_end` direttamente) — quindi il problema, se esiste, è nel riconoscimento del gesto
Flutter (`GestureDetector` annidato dentro un `InteractiveViewer`, già oggetto di un gotcha
gesture-arena noto e documentato in `regole_flet_api.md`/vault, §"lo zoom funziona per pc ma
non per smartphone" del 2026-08-20), non nella logica applicativa. Stessa categoria del
falso positivo Ctrl+A trovato nella sessione precedente: un limite del driving automatico
via Playwright su un `GestureDetector` complesso, non necessariamente un bug reale — non
riportato come finding, segnalato solo come "andrebbe controllato a mano" se serve certezza.

**Level Up / Level Down — bug reale trovato, e un incidente durante la sua scoperta.**
Testando il ciclo su→giù sul personaggio reale "Thempest Zephyrion" (Paladino Lv.8),
un errore di sequenza nello script di test ha rieseguito "Level down" una seconda volta
su un personaggio già tornato a Lv.8 (invece di fermarsi lì), portandolo per errore a
Lv.7/FOR 18/PF 53 — un incidente della sessione di test, non un bug applicativo. Nel
diagnosticarlo però è emerso un problema reale: il dialog "Level Up" successivo proponeva
"Avanzamento a **Livello 10**" nonostante il personaggio fosse a Lv.7.

**Causa**: `ui/views/character_sheet/profilo_tab.py::do_level_up()` risincronizza SIA
`characters.level` SIA `character_classes.level` della classe primaria (commento
esplicito nel codice: "vanno risincronizzati PRIMA del salvataggio"), ma `do_level_down()`
aggiornava solo `characters.level` — mai la riga `character_classes`, che restava quindi
ferma al valore precedente più alto. Dato che `_on_level_up_click()` legge il livello
BERSAGLIO da `get_primary_character_class().level` (non da `character.level`), un solo
level-down su QUALSIASI personaggio (non solo multiclasse — ogni personaggio ha una riga
`character_classes` primaria dalla migrazione del 2026-08-12) lascia una bomba a
orologeria silente: il prossimo Level Up calcola il target dal valore stantio e propone
un livello sbagliato, senza alcun errore visibile finché non si guarda con attenzione il
numero nel dialog.

**Fix**: aggiunta la stessa chiamata `character_repo.set_character_class_level()` già
usata da `do_level_up()`, dentro `do_level_down()`, sulla classe primaria (level-down non
ha ancora un selettore "quale classe scende" come level-up in un multiclasse — assume
sempre la primaria, coerente con `new_level = c.level - 1` già esistente). Verificato con
un nuovo file dedicato, `test_level_down_class_sync.py` (9/9): un singolo level-down
sincronizza correttamente entrambe le tabelle, e — riproduzione esatta del bug osservato
dal vivo — un ciclo su→giù→su propone di nuovo il livello corretto (9, non 10). Test
verificato "a vuoto" contro il codice pre-fix (`git stash` del solo file toccato): fallisce
esattamente sui controlli attesi (5/9), confermando che il test intercetta davvero il bug.
Nessuna regressione: `test_multiclasse.py` 86/86, `test_fase_4.py` 303/303, intera suite
rilanciata.

**Query di controllo sui dati reali**: confrontato `characters.level` con la somma di
`character_classes.level` per OGNI personaggio del database di sviluppo — nessun altro
personaggio risultava disallineato, quindi il danno di questo bug (mai innescato prima
d'ora, dato che "Level down" è un'azione rara) era contenuto al solo personaggio toccato
durante il test.

**Ripristino dati**: il personaggio "Thempest Zephyrion" (id `2a4f364f-16b6-4f14-bf54-
a1ffa850d19b`) è stato riportato a Lv.8/FOR 20/PF 60 tramite `character_repo.update()` +
`set_character_class_level()` (stesse funzioni usate dall'app, nessun SQL diretto) — via
libera esplicito di Davide dopo essere stato informato dell'incidente prima di agire.
Valori di ripristino incrociati su due fonti indipendenti: una replica d'istanza di mondo
archiviata del 2026-08-20 (stesso Lv.8/FOR 20/PF 60) e la formula PF di level-up
(d10 massimo al Lv.1 + media per 7 livelli, +1 CON ciascuno = 11 + 7×7 = 60, verificata a
mano). Riposo lungo/breve e uso di slot incantesimo testati in precedenza sullo stesso
personaggio erano invece azioni di gioco legittime, non toccate dal ripristino.

**Bug gemello trovato subito dopo, controllando l'export PDF** (§ successiva) del
personaggio appena ripristinato: "Totale 7/9 d10" invece di "8/8" — stessa causa,
stessa asimmetria. `do_level_up()` fa sempre `c.hit_dice_total += 1` ("Dadi vita: +1
per ogni livello acquisito, PHB p.12"), ma `do_level_down()` non lo toglieva mai: un
dado vita fantasma permanente ad ogni level-down, non tappato da alcun clamp (a
differenza di `hit_dice_remaining`, che almeno restava ≤ `hit_dice_total`). Fix
simmetrico nello stesso file/funzione: `hit_dice_total - 1` (mai sotto 1), e
`hit_dice_remaining - 1` — non un semplice `min()` col nuovo totale, che avrebbe
comunque regalato un dado in più non guadagnato (il numero di dadi già SPESI deve
restare invariato attraverso il ciclo su/giù, esattamente come già fa `do_level_up()`
sul proprio lato). Verificato con un terzo test nello stesso file
(`test_level_down_class_sync.py`, ora 13/13): un ciclo su→giù riporta sia il totale sia
i rimanenti ai valori di partenza, a parità di dadi spesi. Anche questo campo del
personaggio di Davide era rimasto disallineato dal ripristino precedente (mancato in un
primo passaggio, notato solo grazie all'export PDF) — corretto con lo stesso metodo
sanzionato (`character_repo.update()`), stavolta senza dover richiedere di nuovo il via
libera: stessa restituzione già autorizzata, solo un campo dimenticato la prima volta.

---

## Bug reale: export/import .dndchar perdeva la classe secondaria di un personaggio multiclasse — trovato dal vivo, playtest lato giocatore e master (2026-08-24)

Proseguimento del giro di playtest della sessione precedente ("Guardiamo prima altre
aree"): su richiesta di Davide di coprire sistematicamente ogni zona dell'app non ancora
testata dal vivo, sia lato giocatore (Incantesimi, Combattimento, Importa personaggio)
sia lato master (Note di Campagna, Nuovo NPC, Mondi/hosting/join, Bottino dal lato
giocatore).

**Il bug**: esportato "Bambolo" (Monaco 6 / Ladro 4, personaggio reale di Davide) in un
file `.dndchar` e reimportato con l'opzione sicura "Crea copia" (per non rischiare
l'originale) offerta dal dialog "Personaggio già presente" — la copia risultante
mostrava solo "Monaco", la classe secondaria Ladro era sparita del tutto.

**Causa**: `data/repositories/character_export.py::CHILD_TABLES` — la lista delle
tabelle figlio con FK `character_id → characters(id) ON DELETE CASCADE` che export/
import copiano genericamente via introspezione dello schema — non includeva
`character_classes`. La tabella è stata introdotta il 2026-08-12 con lo schema
multiclasse (vedi `test_multiclasse.py`) ma non era mai stata aggiunta a questa lista,
nonostante abbia esattamente lo stesso FK CASCADE delle altre 13 tabelle già elencate.
L'export includeva quindi la riga `characters` (che porta ancora `class_name`/`level`
della sola classe primaria, per compatibilità con personaggi mono-classe) ma zero righe
`character_classes`.

**Impatto più ampio del previsto**: `core/character_instances.py::_copy_character()` —
usata ogni volta che un personaggio entra in un Mondo (per creare l'istanza di mondo) —
richiama la STESSA `export_character()`/`import_character()`. Il bug non riguardava
quindi solo il backup/trasferimento file `.dndchar`, ma anche "Crea copia" nel dialog di
conflitto import E l'ingresso di un personaggio multiclasse in un mondo condiviso: un
Paladino/Guerriero o qualsiasi altro multiclasse che si univa a una campagna perdeva
silenziosamente metà delle proprie classi nell'istanza di mondo.

**Fix**: aggiunta `"character_classes"` a `CHILD_TABLES`. Nessun'altra modifica
necessaria — `_write_character_and_children()` gestisce già genericamente qualunque
tabella della lista (nuovo `id` per riga, `character_id` riscritto al target), stesso
principio dichiarato nel docstring di modulo ("ogni colonna esistente viene sempre
inclusa"). Verificato con un nuovo file dedicato, `test_export_import_multiclasse.py`
(9/9): l'export include ora le righe `character_classes`, e una copia importata
mantiene entrambe le classi con la stringa di visualizzazione multiclasse corretta.
Verificato "a vuoto" contro il codice pre-fix (`git stash` del solo file toccato):
fallisce esattamente sui 7 controlli attesi (2/9), confermando che il test intercetta
davvero il bug. Nessuna regressione: intera suite di test rilanciata (unico fallimento,
`test_qr_scan.py` su disponibilità pacchetti Android/iOS in questo sandbox, preesistente
e confermato identico prima e dopo la modifica).

**Pulizia dati di test**: rimossi i file `.dndchar` di prova generati durante il test
(`~/dnd_character_exports/`) e la copia duplicata di "Bambolo" creata per verificare il
bug; il "Bambolo" originale di Davide non è mai stato toccato.

**Bug minore correlato, stessa causa di fondo trovato subito dopo controllando
"Personaggi Archiviati" (vista Mondi lato master)**: `ui/views/world/world_view.py::
_archived_character_row()` costruiva la riga di classe leggendo solo
`character.class_name`/`character.subclass` (i campi legacy mono-classe) invece di
`character_repo.get_class_display_string()` — stesso pattern già in uso ovunque nel
resto dell'app (card dei personaggi in home, ecc.). Un personaggio multiclasse
archiviato in un mondo mostrava quindi solo la classe primaria anche qui. Fix minimo:
sostituita la costruzione manuale con `get_class_display_string()`, mantenendo la
stessa forma "NomeClasse Livello" per un personaggio mono-classe (nessuna barra) e
omettendo il suffisso sottoclasse quando la stringa è già multiclasse (ambiguo altrimenti
— la sottoclasse riportata in `characters.subclass` appartiene solo alla classe
primaria). Solo verifica statica (sintassi + lettura del codice, stesso `get_class_
display_string()` già coperto da `test_multiclasse.py`): il flusso completo
"personaggio multiclasse → entra in un mondo → esce/viene espulso → master apre
Personaggi Archiviati" richiede una preparazione end-to-end (mondo + istanza + uscita)
sproporzionata rispetto alla severità cosmetica di questo secondo bug.

**Refuso grammaticale trovato esplorando le "Note di Campagna" (master) e la "Cronaca"
del personaggio (`ui/views/diary_view.py`, `ui/views/master/master_notes_view.py`)**: lo
stato vuoto "nessuna voce selezionata" di ogni sezione (PNG Incontrati, Luoghi, Missioni,
Fazioni, Eventi, Segreti, ecc.) veniva costruito con `f"Nessuna {meta['label'].lower()}
selezionata"` — un template che assume che l'etichetta della sezione sia sempre un
sostantivo singolare femminile, quando in realtà è quasi sempre un'etichetta PLURALE
(es. "Missioni", "Luoghi", "Eventi") e in metà dei casi maschile. Risultato dal vivo:
"Nessuna missioni selezionata", "Nessuna luoghi selezionata", ecc. su 8 sezioni del
master e 9 del personaggio (17 in totale, incluso "Cronaca" che per puro caso risultava
già corretto). Fix: aggiunto un campo esplicito `"none_selected_msg"` per ciascuna
categoria in entrambi i file, con la forma singolare e il genere corretti già scritti
(stesso principio già in uso per `"empty_msg"`, presente in ognuna delle stesse voci),
al posto della derivazione generica dall'etichetta plurale. Verificato dal vivo su due
sezioni di genere opposto ("Nessuna missione selezionata", "Nessun luogo selezionato").

**Resto del giro di copertura (nessun bug trovato)**: tab Incantesimi (preparazione/
rimozione incantesimi con conteggio slot, corretto blocco silenzioso al limite massimo —
comportamento voluto, non un bug), tab Combattimento (HP/CA/velocità, tiri salvezza morte,
slot incantesimo interattivi, risorse di classe — tutto corretto sul personaggio reale
Thempest Zephyrion), generazione NPC casuale nella Rubrica (tratti/ideale/legame/difetto,
salvataggio), creazione di un Mondo con hosting LAN attivo (QR d'ingresso, indirizzo IP e
PIN generati correttamente — la porta 8766 osservata anziché 8765 è il fallback
documentato in `network/host_server.py` per conflitto con la porta del server di sviluppo
usato per il test, non un bug), dialoghi "Unisciti con un codice"/"Unisciti in LAN"
(messaggi d'errore chiari per codice inesistente). Un vero test di join a due dispositivi
fisicamente separati resta il limite noto già documentato altrove nel progetto (due
database SEPARATI non simulabili in modo affidabile in un solo sandbox).

**Nota per Davide**: durante questo giro sono stati trovati, nel database di sviluppo, 13
copie duplicate del mondo "La Cripta di Ombrasole" più alcuni mondi "Verifica Quantità"/
"Verifica Combattimento"/"Tour Tabs" — chiaramente residui di sessioni di test precedenti
a questa (nomi di QA, non di campagna). Non rimossi senza conferma esplicita: erano
invisibili dalla UI di questa sessione di test (identità del dispositivo effimera in
modalità web, causa già nota) ma restano nel file `.db` reale. Da confermare se vanno
ripuliti.

---

> Questo file è stato estratto da `CLAUDE.md` il 2026-07-31 durante la riorganizzazione della documentazione del
> progetto (il file principale era cresciuto fino a superare 860 KB, causando compattazioni troppo frequenti della
> chat). Il contenuto è verbatim, nessuna informazione è stata riassunta o rimossa. Per la mappa completa dei
> documenti del progetto vedi `CLAUDE.md` alla radice.
