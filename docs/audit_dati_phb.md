# Checklist Revisione Dati PHB (audit manuale con Davide)

> Registro dell'audit riga-per-riga di ogni file JSON di dati di gioco (classi, razze, background, incantesimi,
> talenti, mostri, equipaggiamento, ecc.) contro il manuale PHB italiano. **Consultare prima di ri-verificare un
> file dati già auditato** — la maggior parte dei file qui è già ✅ completata, con changelog delle correzioni
> applicate. Include anche il metodo di lettura (pdftoppm + lettura visiva, mai pdftotext/OCR) da riusare per
> qualunque nuova trascrizione dal manuale.

## Checklist Revisione Dati PHB (audit manuale con Davide)

> Processo: per ogni file, Claude legge il JSON e ne presenta la struttura/i
> contenuti in chat; Davide verifica riga per riga contro il PHB italiano
> cartaceo/PDF e segnala correzioni; Claude applica le modifiche al JSON;
> solo allora il file viene segnato ✅ e si passa al successivo. Aggiornare
> questa checklist ad ogni file completato — non spuntare in anticipo.

### Classi (`data/game_data/classes/`)
- [x] barbaro.json ✅ (2026-07-03 — nomi sottoclasse/feature corretti, descrizioni Frenesia/Ira
  Incontenibile/Presenza Intimidatoria/Ritorsione/Cercatore di Spiriti/Spirito Totemico/Aspetto della
  Bestia/Viandante Spirituale/Sintonia Totemica riscritte, Ira: aggiunta chiusura come azione bonus)
- [x] bardo.json ✅ (2026-07-03 — arma "Rapiera" → "Stocco" corretta in weapon_proficiencies e starting_equipment;
  Parole Taglienti, Segreti Magici Aggiuntivi, Ispirazione di Combattimento, Ispirazione Bardica, Controfascino:
  descrizioni complete riscritte; "Capacità Impareggiabile" → "Abilità Impareggiabile" con descrizione corretta;
  aggiunta feature mancante "Maestria" lv3; correzione trasversale "Rapiera"→"Stocco" applicata anche a ladro.json
  e tags.json — nessuna altra occorrenza nel progetto)
- [x] chierico.json ✅ (2026-07-03 — tutti e 7 i domini rivisti: Vita, Luce, Natura, Tempesta, Inganno, Guerra,
  Conoscenza. Rinominate/riscritte ~20 feature; corretti nomi incantesimi bonus di dominio; aggiunte le feature
  mancanti "Avatar della Battaglia" lv17 Guerra e "Nato dalla Tempesta" lv17 Tempesta; aggiunta "Incanalare
  Divinità: Charme su Animali e Vegetali" lv2 Natura, mancante del tutto; aggiunto bonus competenza abilità
  mancante su Dominio della Natura. "Allontanare Non Morti"→"Scacciare Non Morti". Note aggiunte su equipaggiamento
  condizionato da competenza (Martello da guerra, Cotta di maglia). Vedi "Note Importanti" per i problemi
  cross-file ancora aperti)
- [x] druido.json ✅ (2026-07-03 — armi specifiche corrette secondo il manuale, "Forniture erboristiche"→"Borsa da
  Erborista", "Cerchio"→"Circolo" ovunque; Circolo della Terra: trucchetto bonus convertito a
  bonus_cantrips_choice/options, aggiunta struttura completa `circle_spells` con le 8 liste di incantesimi per
  terreno (Artico/Costa/Deserto/Foresta/Montagna/Palude/Prateria/Underdark), aggiunta la feature di lv10
  "Interdizione della Natura" che mancava, feature riscritte; Circolo della Luna: aggiunte le 3 feature mancanti
  (Forme del Circolo lv2, Colpo Primordiale lv6, Forma Selvatica Elementale lv10, Mille Forme lv14) — ora completa
  con tutte e 5 le feature attese; feature base: aggiunta "Trucchetti" lv1 mancante, Forma Selvatica riscritta per
  intero, rimossa "Forma Selvatica Migliorata" come feature narrativa e sostituita con tabella dati separata
  `wild_shape_forms` {level, cr_max, limitation}, Corpo Senza Tempo/Incantesimi Bestiali/Arcidruido riscritte)
- [x] guerriero.json ✅ (2026-07-03 — riscrittura quasi completa: equip. Scelta 3 "Due giavellotti"→"Ascia" x2;
  Atleta Straordinario riscritta; "Cavaliere Arcano"→"Cavaliere Mistico" con Incantesimi riscritti per intero +
  aggiunta tabella `spell_progression` (lv3-20, trucchetti/incantesimi conosciuti/slot 1-4) + `cantrip_options` (16
  trucchetti mago); "Legame con l'Arma"→"Arma Vincolata", "Magia Bellica"→"Magia da Guerra", "Colpo di
  Incantesimo"→"Colpo Mistico" (mecc. corretta, prima era inventata), "Magia Bellica Migliorata"→"Magia da Guerra
  Migliorata"; **aggiunta la feature di lv15 "Carica Arcana" che mancava**; "Maestro delle Battaglie"→"Maestro di
  Battaglia" con tutte le feature riscritte, **aggiunta lista completa `maneuvers` (16 manovre)**, "Conoscenza del
  Terreno"(sbagliata)→"Conosci il Tuo Nemico", "Manovre Aggiuntive"→"Superiorità in Combattimento Migliorata";
  **Stili di Combattimento**: nuovo campo `fighting_style_details` (6 stili completi) — corretto un bug reale:
  "Combattimento con Arma a Due Mani" e "Grande Arma" avevano la stessa descrizione duplicata (il rientiro 1/2 sui
  danni), lo stile Combattere con Due Armi (bonus danno secondo attacco) mancava del tutto; nomi finali: Combattere
  con Armi Possenti, Combattere con Due Armi, Difesa, Duellare, Protezione, Tiro — propagati anche a
  `FIGHTING_STYLES` in config/settings.py (guerriero/paladino/ranger). "Secondo Fiato"→"Recupera Energie", "Impeto
  d'Azione"→"Azione Impetuosa", Indomito riscritta. ✅ `ranger.json` corretto il 2026-07-07 (vedi voce dedicata) —
  referenziava ancora i nomi vecchi degli stili di combattimento, ora risolto)
- [x] ladro.json ✅ (2026-07-03 — riscrittura completa: "Strumenti da ladro"→"Arnesi da Scasso" (tool_proficiencies
  + equip. fisso), rimosso il campo `expertise` top-level duplicato/morto (non letto da nessun codice Python, la
  meccanica è già coperta dalla feature "Maestria"); "Archetipo Furfantesco"→"Archetipo Ladresco"; sottoclasse
  "Ladro"→"Furfante" con **aggiunte le 3 feature mancanti** (Furtività Suprema lv9, Usare Oggetto Magico lv13,
  Riflessi da Furfante lv17) + "Scalatore Urbano"→"Lavoro al Secondo Piano" riscritta; Assassino:
  bonus_proficiencies corrette (Trucchi per il Camuffamento, Sostanze da Avvelenatore), "Capacità
  Infiltrazione"→"Maestro Infiltrato", "Colpi della Morte"→"Colpo Mortale" (meccanica corretta, era sbagliata),
  Impostore riscritta; "Canaglia Arcana"→"Mistificatore Arcano" con Incantesimi riscritta per intero +
  `spell_progression` (lv3-20) + `cantrip_options`, "Mano del Mago"→"Gioco di Prestigio della Mano Magica",
  **aggiunta la feature di lv9 "Imboscata Magica" che mancava**, aggiunta "Ingannatore Versatile" lv13, "Furto di
  Incantesimo"→"Ladro di Incantesimi" riscritta; feature base: Maestria/Attacco Furtivo riscritte (Attacco Furtivo
  ora richiede arma accurata/a distanza), Elusione con "ad area", **Inafferrabile corretta con la meccanica
  giusta** (vantaggio ai tiri contro di te, non "nessun colpo automatico" — errore reale, non solo un refuso),
  Colpo di Fortuna con l'opzione prova di caratteristica aggiunta. Corretti anche per coerenza:
  `core/level_manager.py` (etichette level-up Ladro allineate ai nuovi nomi) e `backgrounds/criminale.json`
  ("Strumenti da ladro"→"Arnesi da Scasso"))
- [x] mago.json ✅ (2026-07-03 — "Bastone"→"Bastone Ferrato" (armi+equip.), "Sacca dei Componenti"→"Borsa per
  Componenti"; aggiunta a TUTTE le 8 scuole la feature lv2 mancante "[Scuola] Sapiente" (dimezza tempo/costo copia
  incantesimi della scuola); Abiurazione: Scudo Arcano→Interdizione Arcana, Abiurazione Proiettata→Interdizione
  Proiettata, Resistenza Migliorata→Abiurazione Migliorata, Negazione degli Incantesimi→Resistenza agli Incantesimi
  (tutte riscritte); Ammaliamento: **aggiunte le 3 feature mancanti** (Fascino Istintivo lv6, Ammaliamento
  Condiviso lv10, Alterare Ricordi lv14), Sguardo Ipnotico riscritta; Divinazione: Presagio→Portento (evita
  conflitto col nome dell'incantesimo "Presagio"), Oracolo Esperto→Divinazione Esperta, La Terza Vista→Terzo
  Occhio, tutte riscritte; Evocazione: Scolpire Incantesimi→Evocazione Minore, Potenza dei Trucchetti→Trasposizione
  Benevola, Evocazione Potenziata→Evocazione Focalizzata, Sovraccarico di Incantesimo→Evocazioni Perduranti (nomi
  completamente diversi, contenuto riscritto); Invocazione: **era completamente vuota (`features: []`), ora
  popolata con tutte e 5 le feature** (Invocatore Sapiente, Plasmare Incantesimi, Trucchetto Potente, Invocazione
  Potente, Saturazione Magica); Illusione: 4 feature riscritte; Necromanzia: **aggiunte le 2 feature mancanti**
  (Servitori Non Morti lv6, Impervio alla Non Morte lv10), Mietere la Vita→Raccolto Macabro, Comandante dei Non
  Morti→Comandare Non Morti; Trasmutazione: **aggiunta la feature mancante di lv6 "Pietra del Trasmutatore"**,
  corretta struttura lv10/lv14 (era tutto sbagliato: ora lv10 "Mutaforma", lv14 "Maestro Trasmutatore" sostituisce
  l'inventata "Padronanza della Trasmutazione"); feature base: **Incantesimi Personali (lv20) corretta
  radicalmente** — non trucchetti come nel JSON originale, ma 2 incantesimi di 3° livello dal libro. aggiunta anche
  la feature "Celebrare Rituale" (lv1) che mancava, più il paragrafo "Il Libro degli Incantesimi del Mago"
  (copiare/sostituire il libro, costi e tempi) integrato nella descrizione di "Incantesimi")
- [x] monaco.json ✅ (2026-07-07 — armi da monaco definite esplicitamente in "Arti Marziali" (spade corte o armi da
  mischia semplici senza proprietà a due mani/pesante); Ki: le 3 capacità base rinominate "Pioggia di
  Pugni"→"Raffica di Colpi" e "Pazienza del Torrente"→"Difesa Paziente" (Passo del Vento invariato), ora feature
  separate con descrizione propria; Deviare Proiettili riscritta con dettaglio gittata/attacco a distanza; Anima
  Adamantina **corretta con meccanica reale completamente diversa** (competenza in tutti i TS + reroll 1 TS fallito
  spendendo 1 ki — non più immunità charme/paura/sonno, errore reale non un refuso); Corpo Senza Tempo: aggiunto
  "non ha più bisogno di bere o mangiare"; Via della Mano Aperta: Tecnica della Mano Aperta/Integrità del
  Corpo/Tranquillità riscritte, "Palma Vibrante"→"Palmo Tremante" riscritta per intero; Via delle Quattro
  Elementali→**"Via dei Quattro Elementi"**: rimosse le 3 feature invented "Discipline Extra"/"Colpo degli
  Elementi"/"Maestria degli Elementi" (non esistono, la progressione è automatica via la lista discipline), tenuta
  solo "Discepolo degli Elementi" lv3 riscritta per intero, aggiunta struttura dati `disciplines` con tutte le 17
  discipline elementali PHB (nome, livello prerequisito, costo ki, descrizione) e tabella
  `max_ki_per_spell_by_level`; Via delle Ombre: "Arti delle Ombre"→"Arti dell'Ombra" (corretto anche il contenuto:
  Oscurità/Passare Senza Tracce/Scurovisione/Silenzio + trucchetto Illusione Minore, non più "Darkvision" non
  tradotto), "Passo delle Ombre"→"Passo dell'Ombra" riscritta, "Mantello dell'Ombra"→"Manto di Ombre" riscritta,
  **aggiunta la feature di lv17 "Opportunista" che mancava del tutto**. Oro 5d4×1 confermato corretto così com'è.)
- [x] paladino.json ✅ (2026-07-07 — Giuramento di Devozione: incantesimo bonus lv5 "Ripristino
  Inferiore"→"Ristorare Inferiore" (conferma il sospetto già annotato in "Note Importanti"); Arma Consacrata:
  aggiunto "o non trasporta più questa arma"; "Purità di Spirito"→**"Purezza di Spirito"**; Giuramento degli
  Antichi: "Scacciare Ali Infedeli"→**"Scacciare gli Infedeli"**, Campione degli Antichi arricchita con l'esempio
  di trasformazione (pelle/corteccia, corna di cervo, criniera di leone); Giuramento di Vendetta: nessuna modifica
  di contenuto, solo verifica; feature base: **Percezione del Divino corretta radicalmente** — rileva solo
  celestiale/immondo/non morto (non più "demone, elementale, essere fatato" che erano invenzioni), riconosce il
  tipo ma non l'identità, **aggiunta la rilevazione di luoghi sacri/sacrileghi (effetto Santificare) che mancava
  del tutto**; Imposizione delle Mani: aggiunte le clausole "cura più malattie/veleni con un solo utilizzo,
  spendendo PF separatamente" e "nessun effetto su costrutti e non morti"; Stile di Combattimento: rimossi i 4
  stili con nomi/testi vecchi e imprecisi, ora rimanda ai 4 stili canonici del Guerriero (Combattere con Armi
  Possenti, Difesa, Duellare, Protezione — confermato che il Paladino NON ha accesso a Tiro/Combattere con Due
  Armi, coerente con `FIGHTING_STYLES["paladino"]` già corretto in precedenza in config/settings.py); **Punizione
  Divina corretta**: richiede un attacco con **arma da mischia** (non genericamente "un'arma" — errore reale, i
  danni extra non si applicano alle armi a distanza); ~~rimossa interamente "Punizione Divina Migliorata" (lv11)"~~
  — **RIPRISTINATA il 2026-07-10** (task Audit Level-Up Phase 3, "Audit level-up: Paladino"): la rimozione del
  2026-07-07 era un ERRORE. Verificato con `pdftoppm` (non `pdftotext`, che aveva corrotto il testo in "----All'l
  r' livello") che la feature esiste eccome, con un paragrafo dedicato a pag.98: "All'11° livello, il paladino è
  talmente pervaso dalla potenza della giustizia che tutti i suoi colpi con le armi si caricano di potere divino.
  Ogni volta che il paladino colpisce una creatura con un'arma da mischia, quella creatura subisce 1d8 danni
  radiosi extra. Inoltre, se utilizza Punizione Divina con un attacco, aggiunge questi danni ai danni extra della
  sua Punizione Divina." — anche la tabella di classe a pag.96 la elenca esplicitamente come Privilegio del lv11.
  Il motivo della rimozione originale ("non presente nel testo del manuale fornito da Davide") era probabilmente
  dovuto a una ricerca incompleta nella sessione precedente. Ri-aggiunta a `paladino.json` con il testo esatto
  sopra; **"Aure Migliorate" (lv18) resta correttamente NON reintrodotta** — questa è l'unica delle due che è
  davvero solo un'espansione di raggio già scritta per esteso in ciascuna aura
  (Protezione/Coraggio/Devozione/Interdizione), diversamente da Punizione Divina Migliorata che ha un paragrafo
  dedicato con un meccanismo nuovo (danno passivo aggiuntivo). Corretto anche `core/level_manager.py` (etichette
  level-up Paladino allineate: "Individuazione del Male e del Bene"→"Percezione del Divino", "Combattere
  Divinamente"→"Punizione Divina", "Sanità Divina"→"Salute Divina", "Purificatore di Tocco"→"Tocco Purificatore";
  il lv11 ora mostra di nuovo "Punizione Divina Migliorata"). **Aggiunta la feature base mancante "Incanalare
  Divinità" (lv3)** con testo fornito da Davide (risorsa condivisa: 1 utilizzo, si rigenera con riposo breve o
  lungo, CD = CD incantesimi da paladino) — prima esisteva solo implicitamente tramite le opzioni di sottoclasse.
  Nota risolta: la frase ricostruita da Claude in "Incanalare Divinità: Giuramento di Inimicizia" ("il paladino può
  formulare un giuramento di inimicizia contro") è stata confermata testuale dal manuale cartaceo da Davide il
  2026-07-07 — nessuna modifica necessaria, il testo in paladino.json era già corretto.)
- [x] ranger.json ✅ (2026-07-07 — equip. Scelta 1 "Cotta di maglia"→"Corazza a scaglie" (OPPURE Armatura di cuoio);
  **Cacciatore: riscrittura quasi totale** — lv3 "Preda del Cacciatore" ora con opzioni Devastatore dell'Orda
  (nuova, attacco extra su bersaglio adiacente)/Sterminatore di Colossi (**meccanica corretta**: 1d8 extra se il
  bersaglio non è a PF massimi, non più legato alla taglia Grande+)/Uccisore di Giganti (nuova, reazione contro
  creature Grandi+ che colpiscono/mancano); lv7 "Tattiche Difensive" → Difesa dal Multiattacco/Sfuggire all'Orda
  (nuova)/Volontà d'Acciaio (nuova); lv11 "Attacco Multiplo"→**"Multiattacco"** → Attacco Turbinante/Raffica (nomi
  e testi completamente diversi da quelli inventati prima); lv15 "Sensi del Cacciatore Superiore"→**"Difesa del
  Cacciatore Superiore"** → Elusione (nuova)/Opporsi alla Marea (nuova)/Schivata Prodigiosa (nuova) — tutte e 4 le
  feature avevano nomi e/o meccaniche delle opzioni completamente inventati, ora sostituiti con `options` array per
  ciascuna; **"Maestro delle Bestie"→"Signore delle Bestie"**: lv3 "Compagno di Caccia"→**"Compagno del Ranger"**
  riscritta per intero con meccanica reale (CR ≤1/4, bonus competenza a CA/tiri/danni/TS, PF = max(scheda,
  4×livello ranger)), lv7 "Compagno Eccezionale"→**"Addestramento Straordinario"** riscritta, lv11 "Tattica della
  Bestia"→**"Furia Bestiale"** riscritta, lv15 "Condivisione degli Incantesimi" confermata/riscritta; feature base:
  Nemico Prescelto riscritta (lista tipi corretta: "celesti"→celestiali, "demoni"→rimosso/sostituito da "immondi",
  "fate"→"folletti", "piante"→"vegetali", aggiunta l'opzione 2 razze umanoidi e l'apprendimento di un linguaggio),
  Esploratore Nato riscritta (aggiunto terreno mancante "Underdark", nuova meccanica raddoppio bonus competenza,
  dettagli foraggiamento/tracce), **Stile di Combattimento**: confermati i 4 stili canonici (Combattere con Due
  Armi, Difesa, Duellare, Tiro) — corretta la discrepanza con `FIGHTING_STYLES["ranger"]` in config/settings.py che
  ne aveva solo 3 (mancava Duellare, ora aggiunto), **Incantesimi riscritta radicalmente**: il Ranger conosce un
  numero fisso di incantesimi (non li prepara come Paladino/Chierico), aggiunta formula CD/attacco; Consapevolezza
  Primordiale corretta (portata 9 km nel proprio terreno, non "6 km in pianura aperta"; lista creature corretta),
  Andatura sul Territorio (aggiunto vantaggio TS contro vegetazione magica), **Nascondersi in Piena Vista riscritta
  con meccanica reale diversa** (richiede materiali naturali per mimetizzarsi e appiattirsi contro una superficie,
  +10 Furtività da fermo — non più legata a "aree all'aperto/osservato entro 30m"), Svanire (aggiunta clausola "a
  meno che non scelga di lasciare una pista"), Sensi Ferini (aggiunta rilevazione invisibili entro 9 m, mancante
  del tutto), Sterminatore di Nemici (aggiunta clausola tempistica). Corretto anche `core/level_manager.py`
  (etichette level-up Ranger allineate: "Attacco Supplementare"→"Attacco Extra", "Passo della Terra"→"Andatura sul
  Territorio", "Scomparire"→"Svanire", "Cacciatore Supremo"→"Sterminatore di Nemici").)
- [x] stregone.json ✅ (2026-07-07 — arma "Bastone"→"Bastone Ferrato"; equip. "Sacca dei Componenti"→"Borsa per
  Componenti"; **Discendenza Draconiana**: aggiunta tabella dati `dragon_damage_types` (10 draghi→tipo di danno)
  mancante del tutto; Antenato Draconico/Resilienza Draconica/Affinità Elementale riscritte per intero; "Ali
  Draconiache"→**"Ali di Drago"** riscritta (velocità di volo = velocità attuale, non "velocità di terra"; vincolo
  armatura); Presenza Draconica riscritta (scelta soggezione/paura, richiede concentrazione, immunità 24h);
  **"Anima Selvaggia" era gravemente incompleta (1 sola feature su 5)** — aggiunte le 4 feature mancanti: "Onde di
  Caos" (lv1, vantaggio 1/riposo lungo), "Piegare la Fortuna" (lv6, reazione 2 pt stregoneria), "Caos Controllato"
  (lv14, doppio tiro sulla tabella impulsi), "Bombardamento Magico" (lv18); **aggiunta la tabella completa
  `wild_magic_surge_table` (50 voci, d100 Impulsi di Magia Selvaggia)**, dato mancante del tutto in precedenza;
  feature base: "Fonte di Magia" era una fusione errata di due feature distinte del manuale, **separata in "Fonte
  di Stregoneria" e "Incantesimi Flessibili"** (lv2 entrambe), aggiunta tabella dati `spell_slot_creation_cost`;
  **Metamagia corretta radicalmente**: l'elenco precedente aveva nomi sbagliati e mancava completamente
  "Incantesimo Raddoppiato" (Twinned Spell, una delle opzioni più importanti) — ora tutte e 8 le opzioni corrette
  con testo completo dal manuale (Incantesimo Celato, Distante, Esteso, Intensificato, Potenziato, Preciso,
  Raddoppiato, Rapido); propagata la correzione anche a `METAMAGIC_OPTIONS` in config/settings.py (nomi allineati)
  e a `core/level_manager.py` (etichette level-up Stregone corrette: "Magia Istintiva"→"Incantesimi/Origine
  Stregonesca", Metamagia spostata da lv2 a lv3 come da manuale, "Restaurazione Stregonica"→"Ripristino
  Stregonesco"). ⚠️ **Correzione terminologica ulteriore (2026-07-09)**: i nomi delle due sottoclassi stesse erano
  sbagliati — "Discendenza Draconiana"→**"Discendenza Draconica"** e "Anima Selvaggia"→**"Magia Selvaggia"** —
  confermato dal testo del manuale ("Il giocatore sceglie un'origine stregonesca... Discendenza Draconica o Magia
  Selvaggia", intestazioni di sezione "DISCENDENZA DRACONICA" e "MAGIA SELVAGGIA"). Errore sfuggito all'audit del
  2026-07-07 perché quella revisione aveva verificato il contenuto delle feature dentro le sottoclassi ma non il
  nome della sottoclasse stesso. Corretto in `stregone.json`, `data/game_data/races/dragonide.json` (stesso termine
  "Discendenza Draconica" usato anche per il tratto razziale del Dragonide — confermato dal manuale, non sono due
  nomi diversi), e in tutti i punti Python che confrontano la stringa: `config/settings.py`
  (`get_permanent_class_hp_bonus`, `calculate_and_update_ca`, commenti), `data/repositories/character_repo.py`,
  `data/models.py`, `ui/views/creation_wizard/wizard_view.py`, `ui/views/creation_wizard/manual_form.py`,
  `ui/views/character_sheet/profilo_tab.py`.)
- [x] warlock.json ✅ (2026-07-07 — equip. Scelta 2 "Sacca dei Componenti"→"Borsa per Componenti"; **aggiunta Scelta
  3 mancante** "Dotazione da Studioso OPPURE Dotazione da Avventuriero" (prima era fusa erroneamente nel blocco
  equip. fisso insieme ad armatura/arma/pugnali); **nomi dei 3 patroni corretti**: "L'Archefey"→**"Il Signore
  Fatato"**, "Il Signore degli Inferi"→**"L'Immondo"**, "Il Grande Antico" invariato — erano incoerenti anche al
  loro interno (la feature base "Patrono Ultraterreno" citava nomi diversi da quelli delle sottoclassi, bug reale
  confermato da Davide); tutte le feature di sottoclassi rinominate/riscritte per intero: Signore Fatato (Presenza
  Fatata, Fuga Velata, **aggiunta la feature di lv10 "Difese Seducenti" che mancava del tutto**, Delirio Oscuro),
  Immondo (Benedizione/Fortuna/Resilienza/Scagliare "dell'Oscuro"/"Immonda"/"all'Inferno"), Grande Antico (Mente
  Risvegliata, Interdizione Entropica, Scudo del Pensiero, Creare Servitore); liste incantesimi ampliati riscritte
  per tutti e 3 i patroni con i nomi esatti dal manuale; feature base riscritte per intero (Magia del Patto, Dono
  del Patto con i 3 testi completi Catena/Lama/Tomo, Arcanum Mistico, lv20 "Maestro Occulto"→**"Maestro
  dell'Occulto"**). **Correzione terminologica importante**: "Invocazioni Occulte" (nome che avevo proposto io
  basandomi su `invocations.json`) è SBAGLIATO — Davide conferma che il nome corretto da manuale è **"Suppliche
  Occulte"**. Corretto ovunque: `warlock.json`, `core/level_manager.py` (etichette level-up + logica di rilevamento
  step "invocazioni"→"supplic" + commenti enum), `ui/views/character_sheet/profilo_tab.py` (4 stringhe UI: sezione
  Talenti, dialog level-up, validazione errori), `data/game_data/invocations.json` (`_note` aggiornata). Non
  rinominati gli identificatori Python interni non visibili all'utente (`StepType.INVOCATION`,
  `proficiency_type="invocation"`, `get_invocations()`/`get_invocation_names()` in `game_data_loader.py`) per
  evitare refactoring rischioso non richiesto — sono solo nomi di variabili/metodi, non testo mostrato in UI. ⚠️
  **Nota critica**: Davide segnala che il contenuto di `invocations.json` (le 32 singole suppliche) NON è mai stato
  verificato riga per riga contro il manuale e va riaudit quando arriviamo alla sua revisione nella checklist
  "Altri file di riferimento" — la voce ✅ nel TODO storico si riferiva solo al fatto che il file fosse popolato,
  non che fosse corretto.)

### Razze (`data/game_data/races/`)
- [x] dragonide.json ✅ (2026-07-09 — verificato riga per riga contro il manuale, testo estratto direttamente dal
  PDF con `pdftotext`. Corretto il nome della sottorazza/tratto "Discendenza Draconiana"→**"Discendenza
  Draconica"** (stesso termine usato dalla sottoclasse Stregone, vedi nota nella sezione stregone.json — non sono
  due nomi diversi); il tratto "Soffio"→**"Arma a Soffio"** (nome completo confermato dall'intestazione del manuale
  e dall'indice analitico). Tutto il resto già corretto: bonus caratteristica (FOR+2, CAR+1), velocità 9m, nessuna
  scurovisione (il Dragonide non ne ha nel PHB, conferma assenza), taglia Media, lingue Comune+Draconico, tabella
  completa "Discendenza Draconica" con tutti e 10 i tipi di drago (tipo di danno, forma/area del soffio, tiro
  salvezza) verificata voce per voce contro la tabella del manuale — tutti i valori già corretti. Danno dell'Arma a
  Soffio verificato: 2d6 base, progressione a 3d6/4d6/5d6 ai livelli 6°/11°/16° — la formula compatta già presente
  nel JSON ("+1d6 ogni 5 livelli") produce esattamente questi valori.)
- [x] elfo.json ✅ (2026-07-09 — verificato riga per riga contro il manuale via `pdftotext -layout`. Corretti 8
  punti: tratto base "Discendenza Fatata"→**"Retaggio Fatato"** (nome sbagliato, contenuto confermato "vantaggio ai
  tiri salvezza per non essere affascinato e non può essere addormentato tramite la magia"); Elfo Alto ed Elfo dei
  Boschi condividevano lo stesso refuso "Addestramento con le Armi degli Elfi"→**"Addestramento nelle Armi
  Elfiche"** (nome esatto del manuale, corretto in entrambe le sottorazze); Elfo dei Boschi: velocità sottorazza
  corretta da 10 a **10,5 m** (manuale: "la velocità base... aumenta a 10,5 metri"), rimosso il tratto **"Passo
  della Foresta"** (attraversare vegetazione senza costo movimento) perché non esiste nel testo PHB 2014 di questa
  sottorazza — probabile invenzione di una versione precedente —, aggiunto al suo posto il tratto mancante **"Piede
  Lesto"** per il bonus di velocità (nome e meccanica dal manuale), "Nascondersi nella Natura"→**"Maschera della
  Selva"** (nome sbagliato); Elfo Oscuro (Drow): "Sensibilità alla Luce Solare"→**"Sensibilità alla Luce del
  Sole"** (nome sbagliato), "Addestramento con le Armi dei Drow"→**"Addestramento nelle Armi Drow"** + arma
  "rapiere"→**"stocchi"** (stesso refuso Rapiera→Stocco già noto nel progetto), **Magia Drow corretta nel
  contenuto**: l'incantesimo di 3° livello non è "Fuoco delle Fate" ma **"Luminescenza"** (confermato anche
  nell'indice degli incantesimi del manuale) — trucchetto Luci Danzanti e incantesimo di 5° livello Oscurità già
  corretti. Confermati invariati: bonus caratteristica base (DES+2) e delle 3 sottorazze (Alto INT+1, Boschi SAG+1,
  Oscuro CAR+1), velocità base 9m, scurovisione base 18m / Oscuro 36m, taglia Media, lingue Comune+Elfico,
  Trucchetto Alto Elfo, lingua extra Alto Elfo. Nessun codice Python referenziava le stringhe corrette (fix isolato
  al solo dato).)
- [x] gnomo.json ✅ (2026-07-09 — verificato riga per riga contro il manuale via `pdftotext -layout`/`-raw`, stessa
  sessione dell'audit razze. 5 correzioni totali, inclusa la riscrittura completa del tratto "Inventore" (Gnomo
  delle Rocce) con le 3 opzioni di congegno corrette dal manuale — dettaglio completo non trascritto voce per voce
  in questa riga al momento dell'audit, ma il conteggio e l'esito sono confermati dalla nota di chiusura "Razze —
  audit completo (9/9 file)" subito sotto. Nessuna correzione rimasta in sospeso.)
- [x] halfling.json ✅ (2026-07-09 — verificato riga per riga contro il manuale via `pdftotext -layout`. Corretti 4
  punti: velocità base corretta da 7 a **7,5 m** (manuale: "la velocità base sul terreno di un halfling è di 7,5
  metri"); tratto base "Agilità degli Halfling"→**"Agilità Halfling"** (nome esatto del manuale); Halfling
  Piedelesto: "Naturalmente Furtivo"→**"Furtività Innata"** (nome sbagliato, contenuto già corretto); Halfling
  Tozzo: "Resistenza dei Robusti"→**"Resilienza del Tozzi"** (nome sbagliato, contenuto già corretto). Confermati
  invariati: Destrezza +2 base, Carisma +1 Piedelesto, Costituzione +1 Tozzo, nessuna scurovisione, taglia Piccola,
  lingue Comune+Halfling, Fortunato e Coraggioso (nome e contenuto). Nessun codice Python referenziava le stringhe
  corrette (fix isolato al solo dato).)
- [x] mezzelf.json ✅ (2026-07-09 — verificato riga per riga contro il manuale via `pdftotext -layout`. Corretto 1
  punto: tratto "Discendenza Fatata"→**"Retaggio Fatato"** (stesso nome corretto già applicato in elfo.json,
  confermato testualmente anche qui: "Retaggio Fatato. Un mezzelfo dispone di vantaggio ai tiri salvezza per non
  essere affascinato e non può essere addormentato tramite la magia."). Confermati invariati: Carisma +2 + due
  caratteristiche a scelta +1 (escluso Carisma), velocità 9m, scurovisione 18m, taglia Media, lingue
  Comune+Elfico+1 a scelta, "Versatilità nelle Abilità" (nome e contenuto). Nessun codice Python referenziava la
  stringa corretta (fix isolato al solo dato).)
- [x] mezzorco.json ✅ (2026-07-09 — verificato riga per riga contro il manuale via `pdftotext -layout`. Corretti 2
  nomi: "Minacciante"→**"Minaccioso"** (manuale: "Minaccioso. Un mezzorco ha competenza nell'abilità Intimidire.");
  "Resistenza Implacabile"→**"Tenacia Implacabile"** (manuale: "Tenacia Implacabile. Quando un mezzorco scende a 0
  punti ferita ma non viene ucciso sul colpo, può decidere di rimanere a 1 punto ferita..."), contenuto già
  corretto in entrambi i casi. Confermati invariati: Forza +2 / Costituzione +1 (anche dalla tabella riepilogativa
  del capitolo), velocità 9m, scurovisione 18m, taglia Media, lingue Comune+Orchesco, "Attacchi Selvaggi" (nome e
  contenuto). Nessun codice Python del percorso dati attivo referenziava le stringhe corrette — i 3 hit trovati in
  `config/settings.py` appartengono al dataset parallelo `RACE_DATA`, già segnalato a Davide come problema
  architetturale a parte (duplicazione dati razza), da affrontare dopo il completamento dell'audit JSON.)
- [x] nano.json ✅ (2026-07-09 — verificato riga per riga contro il manuale usando `pdftotext -raw`, più affidabile
  di `-layout` su questa sezione a due colonne. Corretti 6 punti: velocità base corretta da 7 a **7,5 m** (manuale:
  "la velocità base sul terreno di un nano è di 7,5 metri. Tale velocità non viene ridotta se il nano indossa
  un'armatura pesante" — dettaglio quest'ultimo non tracciato meccanicamente nell'app, solo annotato); "Resistenza
  dei Nani"→**"Resilienza Nanica"** (nome sbagliato, contenuto già corretto); "Addestramento con le Armi dei
  Nani"→**"Addestramento da Combattimento Nanico"** (nome sbagliato, contenuto già corretto); "Competenza negli
  Strumenti": nome corretto ma **contenuto sbagliato** — "falegname" sostituito con **"strumenti da costruttore"**
  (manuale: "strumenti da fabbro, scorte da mescitore o strumenti da costruttore" — non c'è falegname tra le
  opzioni); "Senso della Pietra"→**"Esperto Minatore"** (nome sbagliato, confermato anche dall'indice analitico del
  manuale "Esperto Minatore (nano), 21"), aggiunta la clausola "anziché il tuo normale bonus di competenza"
  mancante nella descrizione; Nano della Montagna: "Addestramento con l'Armatura dei Nani"→**"Addestramento nelle
  Armature Naniche"** (nome sbagliato, contenuto già corretto); Nano delle Colline: "Durezza dei
  Nani"→**"Robustezza Nanica"** (nome sbagliato, contenuto già corretto). Confermati invariati: Costituzione +2
  base, Forza +2 Montagna, Saggezza +1 Colline, scurovisione 18m, taglia Media, lingue Comune+Nanico. Nessun codice
  Python referenziava le stringhe corrette (fix isolato al solo dato).)
- [x] tiefling.json ✅ (2026-07-09 — verificato riga per riga contro il manuale via `pdftotext -raw`. Corretti 2
  punti: "Taumateurgia"→**"Taumaturgia"** (refuso di battitura, confermato dall'indice del manuale); **incantesimo
  di 3° livello sbagliato**: "Infuriare"→**"Intimorire Infernale"** (lanciato come incantesimo di 2° livello) —
  confermato sia nel testo del tratto sia nell'indice incantesimi del manuale ("INTIMORIRE INFERNALE"); "Infuriare"
  non era nemmeno un incantesimo citato in questa sezione. Trucchetto e incantesimo di 5° livello (Oscurità) già
  corretti nella sostanza. Confermati invariati: Intelligenza +1, Carisma +2, velocità 9m, scurovisione 18m, taglia
  Media, lingue Comune+Infernale, "Resistenza Infernale" (nome e contenuto). Nessun codice Python referenziava le
  stringhe corrette (fix isolato al solo dato).)
- [x] umano.json ✅ (2026-07-09 — verificato riga per riga contro il manuale via `pdftotext -raw`. Dati già
  corretti: +1 a tutte e sei le caratteristiche, velocità 9m, nessuna scurovisione, taglia Media, lingue Comune+1 a
  scelta. Nota terminologica (non un errore): il tratto "Versatile" è un'etichetta UI, non un nome PHB — il manuale
  non nomina questo tratto, lo descrive solo tramite le sezioni standard "Incremento del Punteggio di
  Caratteristica"/"Linguaggi" comuni a tutte le razze. Confermato con Davide di tenere "Versatile" così com'è.
  **Aggiunto un nuovo campo dati `variant_human_optional_rule`** con la regola opzionale "Tratti Umani Alternativi"
  trascritta dal manuale (sostituisce l'incremento standard con: +1 a due caratteristiche a scelta, competenza in
  un'abilità a scelta, un talento a scelta) — dato presente solo a livello di JSON, non ancora selezionabile in UI.
  Vedi TODO "Selezione Umano Standard vs Variante nel wizard/form".)

**✅ Razze — audit completo (9/9 file, 2026-07-09).** Tutti i file razza sono stati verificati riga per riga contro
il PHB IT (`pdftotext -layout`/`-raw`). Correzioni totali: 8 in elfo.json, 5 in gnomo.json (incluso il tratto
"Inventore" completamente riscritto con le 3 opzioni di congegno), 4 in halfling.json, 1 in mezzelf.json, 2 in
mezzorco.json, 6 in nano.json, 2 in tiefling.json (incluso un incantesimo sbagliato), 2 in dragonide.json (già
chiuso in precedenza). Nessuna correzione necessaria in umano.json (solo nota terminologica). ⚠️ Durante l'audit è
emerso che `config/settings.py` contiene `RACE_DATA`, un secondo dataset razziale scritto a mano, completamente
indipendente dai JSON, usato per la UI di Combattimento (`get_race_display_traits()`) — con i suoi propri errori
(alcuni condivisi con quelli appena corretti, es. "Discendenza fatata", "Passo del bosco" inventato, "Fata Fuoco"
invece di "Luminescenza" con modificatore sbagliato; altri specifici come i tratti "Illusione
Artificiere"/"Comunicare con costrutti" del Gnomo delle Rocce che non esistono nel manuale). Davide ha messo in
discussione la necessità stessa di questa duplicazione dati scritta a mano, dato che i JSON esistono proprio per
evitarla. ✅ **Refactor completato lo stesso giorno** — vedi "Note Importanti" 2026-07-09 "Eliminazione di
RACE_DATA".

### Background (`data/game_data/backgrounds/`)
**✅ Audit completo (13/13 file, 2026-07-10)** — tutti i background verificati riga per riga contro il PHB IT
(pagine 127-141), letto tramite `pdftoppm` + lettura visiva delle immagini (non `pdftotext`, che su questa sezione
produce testo scorretto/scombinato per via del layout a due colonne). Ogni file ha ricevuto un campo `_source` con
la pagina del manuale. Changelog dettagliato per file:
- [x] acolito.json ✅ — riscrittura quasi completa. Nome corretto "Acolito"→**"Accolito"** (doppia C, come scritto
  ovunque nel manuale: "un accolito", "L'accolito..."). Contenuto precedente non era una trascrizione del manuale
  ma testo indipendente (probabile traduzione dall'inglese): equipaggiamento mancante di "Vesti" (fusa erroneamente
  con "Abito comune" in un solo oggetto "Abito"), ideale "Potere" con allineamento sbagliato Malvagio→**Legale**,
  ideale "Fede" Neutrale→**Legale**, 6° ideale rinominato "Aspirazione"→**"Ambizione"** con testo diverso. Tutti
  gli 8 tratti caratteriali riscritti per includere le clausole mancanti (es. "e al suo esempio", "riuscendo a
  fraternizzare con loro", "e del buon vino").
- [x] artigiano_gilda.json ✅ — riscrittura quasi completa, contenuto precedente indipendente dal manuale.
  Privilegio rinominato "Membro della Gilda"→**"Appartenenza alla Gilda"** con testo completo (inclusa la clausola
  della tariffa di 5 mo/mese, assente prima). Equipaggiamento: "Abiti da viaggio"(plurale, sbagliato)→**"Abito da
  viaggiatore"** (singolare), "Lettera d'introduzione"→**"Lettera di presentazione della gilda"**.
- [x] ciarlatano.json ✅ — già quasi interamente corretto (unico file, insieme a eroe_del_popolo.json e
  sapiente.json, già vicino al testo del manuale prima dell'audit). Corretta solo la `description` (paragrafo
  introduttivo incompleto, mancava la clausola "dopo alcune domande mirate, ogni interlocutore è per te un libro
  aperto").
- [x] criminale.json ✅ — riscrittura completa, contenuto precedente indipendente dal manuale (tratti caratteriali,
  legami, difetti tutti diversi da quelli del PHB). Privilegio rinominato "Contatti Criminali"→**"Contatto
  Criminale"** con testo corretto (messaggeri locali/mastri carovanieri corrotti/marinai poco raccomandabili, non
  "bande di contrabbandieri, gilde di ladri, assassini" inventati). Equipaggiamento: "Abiti scuri
  comuni"(inventato)→**"Abito comune comprensivo di cappuccio"**.
- [x] eremita.json ✅ — riscrittura completa, contenuto precedente indipendente dal manuale. Privilegio "Scoperta"
  riscritto per intero con tutte le clausole del manuale (inclusa quella sulle informazioni dannose per chi l'ha
  esiliato). Equipaggiamento: "Contenitore per erbe"(sbagliato)→**"Custodia per pergamene con appunti di studio o
  di preghiere"**, rimosso "Libro delle note" (non esiste nel manuale), aggiunta "Borsa da erborista" mancante come
  oggetto fisico distinto dalla competenza; competenza strumenti "Forniture erboristiche"→**"Borsa da Erborista"**
  (nome corretto già usato altrove nel progetto per lo stesso oggetto).
- [x] eroe_del_popolo.json ✅ — già quasi interamente corretto. Unica correzione: equipaggiamento "Pentola di ferro"→**"Vaso di ferro"** (nome esatto del manuale).
- [x] forestiero.json ✅ — quasi interamente corretto (tratti/ideali/legami/difetti già esatti). Espansa la
  `description`, che riportava solo metà del paragrafo introduttivo del manuale (mancava tutta la parte su
  solitudine/nomade/esploratore/maestro delle terre selvagge).
- [x] intrattenitore.json ✅ — riscrittura completa, contenuto precedente indipendente dal manuale. Privilegio
  rinominato "Per Amore del Palcoscenico"→**"A Grande Richiesta"** con testo corretto. Strumenti: "Kit del
  travestimento"→**"Trucchi per il Camuffamento"** (nome corretto, coerente con `equipment/tools.json`).
  Equipaggiamento: "Favore di un ammiratore (ciuffo di capelli, lettera d'amore, ecc.)"→**"Pegno di un ammiratore
  (lettera d'amore, ciocca di capelli o monile)"**.
- [x] marinaio.json ✅ — riscrittura completa (tratti/ideali/legami/difetti erano tutti inventati, non dal manuale).
  Equipaggiamento corretto radicalmente: mancavano del tutto la **"Galloccia da marinaio (randello)"** e l'**"Abito
  comune"**; "Fune 15 m"→**"Corda di seta di 15 metri"**; "Amuleto della fortuna"→**"Portafortuna (zampa di
  coniglio o piccola pietra forata)"**.
- [x] nobile.json ✅ — riscrittura completa (tratti/ideali/legami/difetti tutti inventati). Privilegio "Posizione di
  Privilegio"→**"Posizione Privilegiata"** (nome esatto) con testo riscritto. Equipaggiamento: "Abiti
  fini"→**"Abito pregiato"**, "Pergamena della propria stirpe"→**"Pergamena con albero genealogico"**.
- [x] monello.json ✅ — quasi interamente corretto (tratti/ideali/difetti già esatti). Corretti 2 legami: legame 1
  tempo/pronome ("la difenderò"→**"li difenderò"**, riferito a città+paese), legame 2 tempo verbale (condizionale
  "Finanzierei"→presente **"Finanzio"**, il manuale descrive un'azione già in corso). Fix minore refuso "ed sei"→"e
  sei".
- [x] sapiente.json ✅ — già interamente corretto, nessuna modifica di contenuto necessaria (solo aggiunto `_source`).
- [x] soldato.json ✅ — riscrittura completa (tratti/ideali/legami/difetti tutti inventati, non dal manuale).
  Equipaggiamento: "Grado militare (insegna o simbolo)"→**"Mostrina con i gradi"**, "Trofeo di un nemico
  sconfitto"→specificato **"(pugnale, lama spezzata o pezzo di bandiera)"**, "Osso con i dadi"→**"Dadi in osso o
  mazzo di carte"**.

**Fix architetturale collegato — eliminazione di `wizard_data.py → BACKGROUNDS` (2026-07-10, stessa sessione)**:
durante l'audit era già noto (vedi nota precedente in questo file) che `wizard_data.py` conteneva un secondo
dataset dei 13 background, usato attivamente da
`wizard_engine.py`/`wizard_view.py`/`manual_form.py`/`profilo_tab.py` in parallelo a `backgrounds/*.json` — stessa
duplicazione già eliminata per `RACE_DATA` e le costanti di classe. Confermato che il contenuto era **divergente**,
non solo diversamente formattato. **Bug reale scoperto**: la chiave del dizionario era `"Saggio"` invece di
**"Sapiente"** (il nome corretto, confermato dall'intestazione del manuale "SAPIENTE" p.139) — la domanda del
wizard `bg_academic` assegna 10 punti a `"Sapiente"` tramite `scores_bg`, ma `WizardEngine.__init__` inizializzava
`bg_scores` solo con le chiavi di `BACKGROUNDS` (quindi `"Saggio"`, mai `"Sapiente"`); il controllo `if bg in
self.bg_scores` falliva silenziosamente per `"Sapiente"`, azzerando l'effetto di quella risposta senza errori
visibili. **Fix**: rimosso l'intero dizionario `BACKGROUNDS` da `wizard_data.py` (sostituito da un commento
esplicativo, stesso stile delle rimozioni precedenti); `wizard_engine.py` ora inizializza `bg_scores` da
`game_data.get_background_names()` e `build_character()` legge `personality_traits`/`ideals`/`bonds`/`flaws` da
`game_data.get_background()` (i 4 campi `ideals` sono dict `{name, alignment, description}`, non più stringhe:
formattati a runtime in `"Nome. Descrizione (Allineamento)"` per preservare lo stesso formato mostrato finora);
`wizard_view.py`, `manual_form.py`, `profilo_tab.py` usano ora `_loader.get_background_names()` per le dropdown e
`_loader.get_background(x).get("skill_proficiencies", [])` per le abilità, senza più alcun fallback su
`BACKGROUNDS`. Verificato con test end-to-end: i 13 nomi risultano identici (a parte "Saggio"→"Sapiente"), la
risposta `bg_academic` ora assegna correttamente 10 punti a "Sapiente", e `build_character()` produce
trait/ideal/bond/flaw validi per tutti e 13 i background.

**Punti che Davide potrebbe voler verificare a mano** (non fonti dubbie, ma decisioni di trascrizione/scope prese senza poterle discutere prima):
1. **Persona grammaticale**: il manuale scrive tratti/ideali/legami/difetti in terza persona ("L'accolito
   venera..."). Ho scelto di convertirli in **prima persona** ("Venero...") per i campi
   `personality_traits`/`ideals`/`bonds`/`flaws`, e in **seconda persona** ("Hai trascorso...") per
   `description`/`feature.description` — scelta basata sul fatto che i file già corretti prima dell'audit
   (Ciarlatano, Eroe Popolare, Sapiente) usavano già questa convenzione mista. Il *contenuto* è verificato parola
   per parola contro il manuale; la *persona grammaticale* è una scelta di presentazione, non un fatto — se
   preferisci un'altra convenzione (es. tutto in terza persona, identico al manuale) è un cambio meccanico da
   rifare su tutti e 13 i file.
2. **Nobile, tratto caratteriale 8** — il manuale recita testualmente "Se qualcuno danneggia il nobile, questi lo
   distruggerà, getterà fango sul suo nome e sale sulle sue terre." Ho interpretato questo come un verbo condiviso
   su due oggetti ("getterà [fango sul nome] e [sale sulle terre]" — gettare sale sulle terre = distruggere/rendere
   sterili le terre di qualcuno, espressione idiomatica) anziché un verbo mancante. Ho ricontrollato l'immagine
   della pagina due volte con lo stesso risultato, ma segnalo l'interpretazione perché la frase è sintatticamente
   insolita.
3. **Tabelle di flavor non rappresentate nello schema JSON** — il manuale include tabelle opzionali per il tiro
   casuale di dettagli narrativi che NON hanno un campo dedicato in `backgrounds/*.json` e che quindi non sono
   stati trascritti: "Attività della Gilda" (d20, Artigiano di Gilda), "Truffe Preferite" (d6, Ciarlatano),
   "Specializzazione Criminale" (d8×2, Criminale), "Vita Solitaria" (d8, Eremita), "Evento Segnante" (d10, Eroe
   Popolare), "Origini" (d10, Forestiero), "Disciplina Artistica" (d10, Intrattenitore), "Specializzazione" (d8×2,
   Soldato). Nessuna di queste tabelle ha effetti meccanici, sono pura ambientazione. Se in futuro vuoi un
   generatore di dettagli narrativi alla creazione del personaggio, andrebbero aggiunte come nuovo campo (es.
   `flavor_tables`) — scelta di scope non affrontata in questa sessione per restare fedele al formato già stabilito
   dagli altri background.
4. **Background alternativi non rappresentati** — il manuale descrive 5 varianti opzionali in riquadri a parte, mai
   wired nel codice: "Mercante di Gilda" (alternativa ad Artigiano di Gilda), "Spia" (alternativa a Criminale),
   "Pirata" con privilegio alternativo "Pessima Fama" (alternativa a Marinaio), "Cavaliere" con privilegio
   alternativo "Servitù" (alternativa a Nobile), "Gladiatore" (alternativa a Intrattenitore). Nessuno di questi è
   mai stato implementato nemmeno prima dell'audit — segnalo solo perché durante la lettura delle pagine erano ben
   visibili e potrebbero essere un'estensione futura interessante.

- [ ] `data/game_data/wizard_data.py → BACKGROUNDS` — **rimosso interamente il 2026-07-10** (vedi sopra), non è più una voce di questa checklist.

### Incantesimi (`data/game_data/spells/`)

**✅ Riscrittura da zero completata (2026-07-10)** — su indicazione di Davide ("la maggior parte dei dati in questi
json sono sbagliati, ti conviene riscriverli da capo"), l'intera sezione incantesimi del PHB IT (Capitolo 11,
"Descrizione degli Incantesimi", pag. 211-289) è stata ritrascritta da zero leggendo visivamente le pagine del PDF
renderizzate come immagini (`pdftoppm -r 200`, mai `pdftotext` — inaffidabile su questo layout a due colonne),
invece di correggere i vecchi file per-classe (che contenevano nomi tradotti dall'inglese e contenuto sospettato di
contaminazione SRD 2024, vedi cronologia sotto).

**Nuova architettura**: un unico file master `data/game_data/spells/incantesimi_completi.json` contiene il testo
completo di tutti i **361 incantesimi univoci** del PHB IT (chiave = nome esatto da manuale), ognuno con
`name/level/school/casting_time/range/components/material/ritual/concentration/duration/description/higher_levels`.
Gli 8 file per-classe (`incantesimi_{bardo,chierico,druido,mago,paladino,ranger,stregone,warlock}.json`) contengono
ora **solo** `{"name","level"}` per ogni incantesimo conosciuto da quella classe (rispecchiano le liste del
Capitolo 11, non il testo) e vengono risolti contro il file master a runtime da
`GameDataLoader.get_spells(class_name)` (vedi `_ensure_spell_master()`/`get_spells()` in `game_data_loader.py`) —
un incantesimo condiviso tra più classi (es. "Cura Ferite") vive quindi in un solo posto invece che duplicato in
ogni file classe.

**Verifica di chiusura eseguita**: script Python di controllo incrociato tra il file master e tutti e 8 i file
per-classe — **0 nomi non risolti** su 843 riferimenti totali (120 Bardo, 106 Chierico, 110 Druido, 214 Mago, 45
Paladino, 46 Ranger, 128 Stregone, 74 Warlock); validazione JSON del file master (361/361 voci, tutti i campi
obbligatori presenti, nessuna voce vuota); copia sincronizzata e riverificata nel progetto reale a ogni batch di
scrittura durante la trascrizione.

**Correzioni terminologiche di rilievo emerse durante la trascrizione** (nomi ora confermati corretti, risolvono
sospetti aperti in sessioni precedenti): "Ristorare Inferiore"/"Ristorare Superiore" (non "Ripristino
Inferiore/Superiore"), "Traslazione Arborea" (non "Passo Arboreo", conferma il sospetto del Ranger), "Vita Falsata"
(non "Falsa Vita", conferma quanto emerso durante l'audit di `invocations.json`).

**✅ Verifica finale per-classe completata (2026-07-10, task #50-57)** — ogni file `incantesimi_{classe}.json` è
stato confrontato riga per riga contro le liste ufficiali del Capitolo 11 (pag. 207-211), lette visivamente dalle
immagini del PDF (non `pdftotext`, layout a 3-4 colonne per pagina in questa sezione). Metodologia: trascrizione
completa della lista di classe dal manuale, poi diff automatico contro il contenuto del file JSON.

Risultato per classe (nomi manuale = nomi JSON, dopo i fix sotto):
- Bardo: 120/120 ✅ nessuna discrepanza
- Chierico: 106/106 ✅ nessuna discrepanza
- Druido: 110/110 ✅ nessuna discrepanza
- Mago: 215/215 — **bug reale trovato e corretto**: mancava **"Scudo"** (1° livello) dalla lista, presente invece nel manuale (pag. 208-209) e già nel file master. Aggiunto.
- Paladino: 45/45 ✅ nessuna discrepanza
- Ranger: 46/46 ✅ nessuna discrepanza
- Stregone: 129/129 — **bug reale trovato e corretto**: mancava **"Ragnatela"** (2° livello) dalla lista, presente invece nel manuale (pag. 210) e già nel file master. Aggiunto.
- Warlock: 74/74 ✅ nessuna discrepanza

Totale: 845 riferimenti incantesimo su 8 classi, **0 non risolti** contro il file master dopo i 2 fix sopra
(verificato con script di cross-check `nome.lower() not in master`). Entrambi i bug erano probabilmente refusi di
trascrizione da una sessione precedente alla riscrittura del master (2026-07-10 stessa giornata, prima della
trascrizione completa) — non nuove voci mancanti dal master, che già le conteneva correttamente.

### Altri file di riferimento (`data/game_data/`)
- [x] feats.json (42 talenti) ✅ (2026-07-10 — riscritto interamente da zero, stesso processo del master
  incantesimi: lettura visiva delle pagine 165-170 del PDF via `pdftoppm` — mai `pdftotext` — invece di correggere
  il file precedente, che presentava la stessa contaminazione da traduzione inglese/SRD già trovata altrove nel
  progetto. **Unità di misura**: tutte le distanze in piedi sostituite con i valori in metri del manuale italiano
  (es. "1,5 metri" per la portata ravvicinata, "9 metri" per Condottiero Ispiratore, "3 metri" per
  Carica/Mobilità). **Rinominati 18 talenti** il cui nome non corrispondeva al manuale (nomi vecchio→corretto):
  Atletico→Atleta, Assalitore→Carica, Combattente con Doppia Arma→Combattente a Due Armi, Esploratore di
  Dungeon→Esperto di Dungeon, Gran Maestro delle Armi→Maestro d'Armi Possenti, Corazzato→Corazze Pesanti, Maestro
  dell'Armatura Pesante→Maestro delle Armature Pesanti, Ispiratore→Condottiero Ispiratore, Addestrato alle Armature
  Leggere→Corazze Leggere, Ammazzamaghi→Sterminatore di Maghi, Maestro dell'Armatura Media→Maestro delle Armature
  Medie, Mobile→Mobilità, Addestrato alle Armature Medie→Corazze Medie, Combattente Montato→Combattente in Sella,
  Maestro delle Armi ad Asta→Maestro delle Armi su Asta, Attaccante Brutale→Aggressore Selvaggio, Maestro dello
  Scudo→Maestro degli Scudi, Furtivo→Appostato, Cecchino degli Incantesimi→Cecchino Magico, Rissoso→Lottatore da
  Taverna, Duro→Robusto, Incantatore di Battaglia→Incantatore da Guerra, Maestro delle Armi→Maestro d'Armi. **2 bug
  meccanici reali trovati** (non solo di nome — contenuto scambiato/inventato): il vecchio "Tenace" (scegli una
  caratteristica, +1 e competenza al tiro salvezza) aveva in realtà la meccanica del talento reale
  **"Resiliente"**; il vecchio "Resistente" (COS+1, valore massimo dado vita a riposo breve — meccanica che non
  esiste nel manuale) è stato sostituito con il vero **"Tenace"** (COS+1, minimo di punti ferita recuperati per
  Dado Vita = 2× mod. COS, minimo 2) — la vecchia meccanica "valore massimo del Dado Vita a riposo breve" non
  corrisponde a nessun talento del PHB IT 2014, probabile contaminazione SRD 2024. Anche "Esperto" (competenza in 3
  abilità/strumenti + una clausola inventata di raddoppio del bonus di competenza) è stato ricondotto al vero
  **"Abile"** (solo le 3 competenze, nessun raddoppio — quella clausola non esiste nel manuale). **Verifica di
  chiusura**: mapping 1:1 dei 42 talenti vecchi confermato contro i 42 nomi reali letti dalle pagine del manuale
  (nessun talento mancante o di troppo); validazione JSON (42/42 voci, tutti i campi obbligatori presenti); grep su
  tutto l'albero `.py` per i 18 nomi vecchi — zero occorrenze, nessuna logica hardcoded per nome di talento in
  nessun punto del codice (tutto l'accesso passa da `get_feats()`/`get_feat_names()`/`get_feat(name)`), quindi la
  rinomina non ha richiesto modifiche altrove. Pagina 171 del PDF confermata come inizio del Capitolo 7 ("Le Regole
  dell'Avventura"), quindi i 42 talenti di pag. 165-170 sono la lista completa, nessuna voce oltre pag. 170.)
- [x] invocations.json ✅ (2026-07-09 — 32 Suppliche Occulte, tutte verificate riga per riga da Davide dal manuale
  cartaceo. **Rimossa "Esplosione Accecante"**: non esiste nel manuale, era una voce inventata nella versione
  precedente del file (il conteggio corretto è 32, non 33 come "corretto" erroneamente durante l'audit di stabilità
  dello stesso giorno). **Causa radice**: la versione precedente del file era stata scritta da Claude traducendo i
  nomi degli incantesimi dall'inglese invece di prenderli dal PHB italiano — violazione diretta della regola
  critica del progetto. Nomi corretti: "Esplosione Agonica"→"Deflagrazione Agonizzante", "Esplosione
  Repellente"→"Deflagrazione Respingente", "Lancia dell'Occulto"→"Lancia Occulta" (incantesimo bersaglio:
  "Esplosione dell'Occulto"→**"Deflagrazione Occulta"**, il trucchetto Eldritch Blast); "Armatura di
  Ombre"→"Armatura delle Ombre" (incantesimo: "Armatura del Mago"→"armatura magica"); "Libro dei Segreti
  Antichi"→"Libro degli Antichi Segreti" (testo espanso con dettagli mancanti: i 2 incantesimi rituali non devono
  appartenere alla stessa lista, non contano ai fini del numero di incantesimi conosciuti, regola per lanciare
  incantesimi da warlock rituali già conosciuti); "Catene di Carceri" **corretta radicalmente**: non è più
  Imprigionamento ma **Blocca Mostri** (bersaglio celestiale/immondo/elementale, non
  elementale/umanoide/nonmorto/fata/aberrazione), prerequisito Patto della Catena confermato; "Linguaggio delle
  Bestie"→"Lingue delle Bestie" (incantesimo: "Parlare con gli Animali", corretto un refuso di scansione "ali
  animali"); "Sussurri Ammalianti"→"Sussurri Stregati"; "Parola Terrificante"→"Parola Temibile"; "Vigore del
  Diavolo"→"Vigore Immondo" (incantesimo: "Falsa Vita"→**"vita falsata"**); "Maestro delle Miriadi di
  Forme"→"Maestro di Mille Forme" (incantesimo: "Alterazione dell'Aspetto"→**"alterare se stesso"**); "Maschera dei
  Mille Volti"→**"Maschera dei Molti Volti"** (incantesimo: "Travestimento"→**"camuffare se stesso"**); "Servitori
  del Caos" (incantesimo: "Convocare Elementale"→**"evoca elementale"**); "Mente Impantanata"→**"Fardello
  Mentale"** (incantesimo: "Rallentamento"→**"lentezza"**); "Visioni Nebbiose"→"Visioni Velate"; "Scultore di
  Carne"→"Scultore della Carne" (incantesimo: "Polimorfo"→**"metamorfosi"**); "Segno di Malaugurio"→**"Presagio di
  Sventura"** (incantesimo: "Maledizione del Sangue"→**"scagliare maledizione"**); "Ladro dei Cinque
  Destini"→**"Ladro dei Cinque Fati"** (incantesimo: "Destino"→**"anatema"**, nessun prerequisito di livello nel
  testo del manuale — voce distinta da Presagio di Sventura, non un duplicato); "Lama Assetata": **prerequisito di
  livello corretto da 12 a 5** (errore reale, non solo nome); "Visioni di Reami Lontani"→**"Visione dei Reami
  Lontani"** (singolare; incantesimo: "Occhio Arcano"→**"occhio arcano"**, corretto un refuso di scansione "occhi o
  arcano"); "Voce del Maestro della Catena"→**"Voce del Signore delle Catene"** (testo corretto: nessun limite di
  distanza esplicito, solo "stesso piano di esistenza"; corretto un refuso di scansione "famiglia"→**"famiglio"**,
  il termine PHB corretto per il familiare del Patto della Catena); "Sussurri della Tomba"→"Sussurri dalla Tomba";
  "Vista della Strega"→**"Vista Stregata"** (aggiunta clausola "ed entro linea di vista" mancante); "Vista
  dell'Occulto" (incantesimo: "Individuazione della Magia"→**"individuazione del magico"**); "Vista del Diavolo"
  (nome invariato, aggiunta distanza "36 metri" già in metri, non piedi). **Tutte le distanze in piedi della
  versione precedente corrette in metri** (120ft→36m, 300ft→90m, 100ft→"stesso piano" nessun limite, 30ft→9m,
  10ft→3m) usando la tabella di conversione già standard nel progetto. ⚠️ **Implicazione più ampia segnalata da
  Davide**: lo stesso errore (nomi incantesimo tradotti dall'inglese anziché presi dal manuale) è sospettato in
  TUTTI gli 8 file `incantesimi_*.json` (non solo in `incantesimi_chierico.json`, già segnalato come sospetto
  contaminato) — servirà un audit dedicato quando revisioneremo quei file, con particolare attenzione ai nomi già
  emersi qui come sbagliati: Deflagrazione Occulta (non "Esplosione dell'Occulto"), Blocca Mostri (non
  "Imprigionamento"), armatura magica (non "Armatura del Mago"), vita falsata (non "Falsa Vita"), alterare se
  stesso (non "Alterazione dell'Aspetto"), camuffare se stesso (non "Travestimento"), evoca elementale (non
  "Convocare Elementale"), lentezza (non "Rallentamento"), metamorfosi (non "Polimorfo"), scagliare maledizione
  (non "Maledizione del Sangue"), occhio arcano (nome confermato corretto), individuazione del magico (non
  "Individuazione della Magia").
- [x] **monsters.json (bestiario)** — ✅ **COMPLETO (2026-07-17): 444/444 blocchi statistici, riconciliato contro
  l'indice ufficiale del manuale** (batch 2026-07-11: Aarakocra, Aboleth, Deva/Planetar/Solar, Ankheg, Arpia,
  Artiglio Strisciante, Azer — pag. 12-22; batch B1 2026-07-16: Banshee, Basilisco, Behir, Beholder, Tiranno della
  Morte, Spectator, Belva Distorcente, Bugbear, Bugbear Capotribù, Bulette — pag. 23-33; batch B2 2026-07-16:
  Bullywug, Cacciatore Invisibile, Cambion, Cavaliere della Morte, Cavallo degli Incubi, Centauro, Chimera, Chuul,
  Ciclope, Coboldo Alato, Coboldo, Cockatrice — pag. 34-44; batch B3 2026-07-16: Couatl, Cumulo Strisciante,
  Cuspide Letale, Demilich (pag. 45-48) + l'intera famiglia dei 14 demoni "tipo" — Balor, Barlgura, Chasme, Demone
  d'Ombra, Dretch, Glabrezu, Goristro, Hezrou, Mane, Marilith, Nalfeshnee, Quasit, Vrock, Yochlol (pag. 53-65, con
  pag. 49-52 lore-only del capitolo Demone, nessuno stat block; batch B4 2026-07-16: l'intera famiglia degli 11
  diavoli "tipo" del capitolo Diavolo — Diavolo Barbuto, Diavolo Cornuto, Diavolo d'Ossa, Diavolo del Ghiaccio,
  Diavolo della Fossa, Diavolo delle Catene, Diavolo Spinato, Diavolo Uncinato, Erinni, Imp, Lemure (pag. 70-78,
  con pag. 66-69 lore-only del capitolo Diavolo — gerarchia infernale, tabella "Strati e Signori dei Nove Inferi" —
  nessuno stat block) + tutto il capitolo Dinosauro — Allosauro, Anchilosauro, Plesiosauro, Pteranodonte,
  Tirannosauro, Triceratopo (pag. 79-80) + Divoracervelli/Intellect Devourer (pag. 81); batch B5-B14 2026-07-16
  (sessione non interattiva, "vai" — vedi "Note Importanti" per il changelog completo): Doppelganger corretto (pag.
  82, punteggi COS/SAG/CAR erano OCR-corrotti a 4/2/11, ripristinati a 14/12/14; rimossi 2 tratti-lore inventati) +
  **capitolo completo dei Draghi Puri, tutti i 10 colori × 4 categorie d'età = 40 stat block**
  (Bianco/Nero/Blu/Verde/Rosso/D'Argento/Di Bronzo/Di Rame/D'Oro/D'Ottone, ciascuno Cucciolo/Giovane/Adulto/Antico,
  pag. 86-118) + Dracolich Blu Adulto corretto (pag. 83-84, il vecchio JSON aveva OCR corrotto — "Ciorno"→"Giorno",
  cifre confuse con lettere — e testo di lore sul Drago d'Ombra mescolato nella descrizione dell'azione Morso) +
  Drago d'Ombra Rosso Giovane aggiunto ex-novo (pag. 85, era assente); batch B15 2026-07-16 (stessa sessione non
  interattiva, continua senza interruzione): Drago Fatato (Faerie Dragon, pag. 119 — un solo stat block rappresenta
  più varianti colore/età con CD Sfida differenziato 1/2 e tabella di scala incantesimi innati per colore), Driade,
  Drider, Duergar (pag. 120-122) + tutto il capitolo Elementale — Elementale del Fuoco/dell'Acqua/dell'Aria/della
  Terra (pag. 123-125) + tutto il capitolo Elfo Drow — Drow, Drow Combattente Scelto, Drow Mago, Drow Sacerdotessa
  di Lolth (pag. 126-129) + Empireo, Ettercap, Ettin (pag. 130-132) + Fantasma, Fatale dell'Acqua, Fauce
  Gorgogliante, Flumph, Fomorian (pag. 133-137) + tutto il capitolo Fungo — Boleto Stridente, Fungo Viola, Spora
  Gassosa (pag. 138-139) + Fuoco Fatuo (pag. 140) — 24 stat block, vedi "Note Importanti" per il changelog
  completo); batch B16 2026-07-16: Fustigatore (pag. 141), Galeb Duhr, Gargoyle (pag. 142-143) + capitolo Genio
  (Dao, Djinni, Efreeti, Marid, pag. 146-149, con pag. 144-145 lore-only) + Ghast, Ghoul (pag. 150) + tutto il
  capitolo Gigante — Gigante del Fuoco, del Gelo, delle Colline, delle Nuvole, delle Pietre, delle Tempeste (pag.
  156-158, con pag. 151-155 lore-only) — 15 stat block; batch B17 2026-07-16/17 (stessa sessione non interattiva,
  continua senza interruzione): Githyanki Combattente, Githyanki Cavaliere (pag. 161), Githzerai Monaco, Githzerai
  Zerth (pag. 162, con pag. 163 lore-only del capitolo Gnoll, nessuno stat block), Gnoll Signore del Branco, Gnoll,
  Gnoll Zanna di Yeenoghu (pag. 164), Gnomo delle Profondità/Svirfneblin (pag. 165, con pag. 166/168/178 lore-only
  dei capitoli Goblin/Golem/Hobgoblin, nessuno stat block), Goblin, Goblin Capo (pag. 167) + tutto il capitolo
  Golem — Golem di Argilla, di Carne, di Ferro, di Pietra (pag. 169-171) + Gorgone (pag. 172), Grell (pag. 173),
  Grick, Grick Alfa (pag. 174), Grifone (pag. 175), Grimlock (pag. 176), Guardiano Protettore (pag. 177) +
  Hobgoblin, Hobgoblin Capitano (pag. 179), Hobgoblin Signore della Guerra (pag. 180) — 24 stat block; batch B18
  2026-07-17 (stessa sessione non interattiva, continua senza interruzione dopo "riprendi da dove hai lasciato"):
  Idra (pag. 181), Ippogrifo (pag. 182), Kenku (pag. 183), Kraken (pag. 185, con pag. 184 lore-only del capitolo
  Kraken ed Effetti Regionali/Azioni di Tana lette per intero ma non trascritte — nessun campo schema per lair
  actions, stesso precedente del Demilich), Kuo-toa, Kuo-toa Gran Sacerdote, Kuo-toa Esecutore (pag. 187-188),
  Kuo-toa Sovrintendente (variante pag. 186, stesse statistiche dell'Esecutore + mod. Saggezza alla CA, azioni
  proprie), Lamia (pag. 189) + tutto il capitolo Licantropo — Cinghiale Mannaro, Orso Mannaro, Lupo Mannaro, Tigre
  Mannara, Topo Mannaro (pag. 190-195, con pag. 190/191 lore-only, nessuno stat block) + Lich (pag. 196-197, con
  Azioni di Tana lette ma non trascritte, stesso principio del Kraken) + Lucertoloide, Lucertoloide Sciamano,
  Re/Regina Lucertola (pag. 198-199) + Magmin (pag. 200) — 19 stat block, vedi "Note Importanti" per il changelog
  completo); batch B19 2026-07-17 (stessa sessione non interattiva, continua senza interruzione): Ago Maligno,
  Arbusto Maligno, Rampicante Maligno (pag. 202, con pag. 201 lore-only del capitolo Maligno, nessuno stat block),
  Manticora (pag. 203), Manto Assassino (pag. 204), Mantoscuro (pag. 205), Marinide (pag. 206), Medusa (pag. 207),
  Megera Marina (pag. 209, con pag. 208 lore-only + sidebar meccanica "Congreghe di Megere" letta ma senza campo
  schema dedicato), Megera Notturna (pag. 210), Megera Verde (pag. 211, con sidebar oggetti magici da Megera
  Notturna sulla stessa pagina, letta ma non pertinente allo schema mostro), Ameba Paglierina (pag. 213, con pag.
  212 lore-only del capitolo Melma + sidebar "Variante: Melma Grigia Psichica" letta ma non incorporata nella voce
  base, stesso principio delle varianti opzionali già stabilito per l'Arma su Asta del Diavolo d'Ossa), Cubo
  Gelatinoso (pag. 214), Melma Grigia, Protoplasma Nero (pag. 215) + tutto il capitolo Mephit — del Fango, del Fumo
  (pag. 216), del Ghiaccio, del Magma (pag. 217), del Vapore, della Polvere (pag. 218, con sidebar "Variante:
  Evocare Mephit" letta ma deliberatamente non incorporata in nessuno dei 6 stat block base, nessuno dei quali la
  include nella propria lista Azioni) + Merrow (pag. 219) + Mezzodrago Rosso Veterano (esempio completo del
  template Mezzodrago/Half-Dragon, pag. 220 — le regole generiche del template sono prosa/tabella senza campo
  schema dedicato, ma questo esempio interamente statuito è stato trascritto come voce a sé, stesso principio già
  usato per i template Dracolich/Drago d'Ombra) — 23 stat block, vedi "Note Importanti" per il changelog completo);
  batch B20 2026-07-17 (stessa sessione non interattiva, continua senza interruzione): tutto il capitolo Miconide —
  Germoglio, Adulto, Sovrano (pag. 221-223) + Quaggoth Servitore delle Spore (esempio di archetipo "Servitore delle
  Spore" applicato, pag. 221 — le regole generiche dell'archetipo sono prosa senza campo schema dedicato, stesso
  principio del Mezzodrago) + Mimic (pag. 224) + Mind Flayer, Mind Flayer Arcanista (variante con incantesimi, pag.
  225-226, con pag. 225 lore-only) + Minotauro (pag. 227) + tutto il capitolo Modron — Monodrone, Duodrone,
  Tridrone, Quadrone, Pentadrone (pag. 228-230, con "Variante: Modron Fuori Controllo" letta ma senza campo schema,
  si applica a qualunque modron esistente) + Mummia, Signore delle Mummie (pag. 231-233, con Azioni di Tana/Effetti
  Regionali lette per intero ma non trascritte, stesso principio del Kraken/Lich) + tutto il capitolo Naga — Naga
  d'Ossa, Naga Spirituale, Naga Guardiana (pag. 234-235) + Nothic (pag. 236) + tutto il capitolo Oggetto Animato —
  Armatura Animata, Spada Volante, Tappeto Soffocante (pag. 237-238) + Ogre, Mezzogre/Ogrillon (pag. 239-240) — 24
  stat block); batch B21 2026-07-17 (stessa sessione non interattiva, continua senza interruzione dopo un secondo
  "riprendi da dove hai lasciato"): Ombra (pag. 241), Omuncolo (pag. 242), Oni (pag. 243), Orco, Orco Capotribù
  Guerriero (pag. 246, con pag. 244-245 lore-only del capitolo Orco — mitologia di Gruumsh, sidebar "Re Obould
  Molte-Frecce" — nessuno stat block), Orco Occhio di Gruumsh, Orog (pag. 247), Orrore Corazzato (pag. 248), Orrore
  Uncinato (pag. 249), Orsogufo (pag. 250), Otyugh (pag. 251), Pegaso (pag. 252), Peryton (pag. 253), Pixie (pag.
  254), Pseudodrago (pag. 255, con sidebar "Variante: Famiglio Pseudodrago" letta ma senza campo schema dedicato,
  si applica opzionalmente a qualunque pseudodrago esistente), Quaggoth, Quaggoth Thonot (variante con Incantesimi
  Innati Psionici e CR3 anziché CR2, trascritta come voce a sé stante — stesso principio delle varianti pienamente
  statuite già usato per Mezzodrago/Dracolich/Drago d'Ombra/Mind Flayer Arcanista — pag. 256), Rakshasa (pag. 257),
  Remorhaz Giovane, Remorhaz (pag. 258), Revenant (pag. 259, con sidebar "Variante: Revenant con Armi e
  Incantesimi" letta ma puramente narrativa, nessun dato meccanico da trascrivere), Roc (pag. 260) — 22 stat block;
  batch B22 2026-07-17 (stessa sessione non interattiva, continua senza interruzione dopo un terzo "riprendi da
  dove hai lasciato"): Rugginofago (pag. 261), Sahuagin, Sahuagin Sacerdotessa, Sahuagin Barone (pag. 262-263),
  Serpente di Fuoco (pag. 264), Salamandra (pag. 265), Satiro (pag. 266, con sidebar "Variante: Flauto del Satiro"
  letta ma senza campo schema dedicato, opzionale), Scheletro, Scheletro Minotauro, Scheletro Cavallo da Guerra
  (pag. 267-268), Sciacallo Mannaro (pag. 269), Segugio Infernale (pag. 270), Androsfinge, Ginosfinge (pag.
  272-273, con pag. 271 lore-only del capitolo Sfinge — "La Tana di una Sfinge"/Azioni di Tana lette per intero ma
  non trascritte, nessun campo schema per lair actions, stesso principio del Kraken/Lich/Signore delle Mummie),
  tutto il capitolo Slaad — Slaad Girino, Slaad Rosso, Slaad Blu (pag. 276), Slaad Verde, Slaad Grigio (pag. 277),
  Slaad della Morte (pag. 278, con pag. 274 lore-only + sidebar "Variante: Gemme del Controllo degli Slaadi" letta
  ma senza campo schema dedicato, opzionale), Spaventapasseri (pag. 279), Spettro e Poltergeist (variante con CR2
  anziché CR1, Invisibilità e azioni distinte — Schianto Violento/Spinta Telecinetica al posto di Risucchio di Vita
  — trascritta come voce a sé stante, stesso principio delle varianti pienamente statuite già usato per Quaggoth
  Thonot/Mezzodrago/Dracolich — pag. 280) — 23 stat block; batch B23 2026-07-17 (stessa sessione non interattiva,
  continua senza interruzione dopo un quarto "riprendi da dove hai lasciato"): Spiritello (pag. 281),
  Succube/Incubo (pag. 282), Tarrasque (pag. 283-284, con pag. 283 lore-only del capitolo Tarrasque, nessuno stat
  block — CR30, Resistenza Leggendaria, Presenza Terrificante, Inghiottire, 3 Azioni Leggendarie), Teschio
  Infuocato (pag. 285), Testuggine Dragona (pag. 286), Thri-kreen (pag. 287, con sidebar "Variante: Armi e Poteri
  Psionici dei Thri-kreen" letta ma senza campo schema dedicato, opzionale — gythka/chatkcha e incantesimi innati
  psionici), Treant (pag. 288), Troglodita (pag. 289), Troll (pag. 290, con sidebar "Variante: Arti Abominevoli"
  letta ma senza campo schema dedicato, meccanica opzionale di smembramento/rigenerazione), Uccello Stigeo (pag.
  291), Umber Hulk (pag. 292), Unicorno (pag. 293-294, con pag. 293 lore-only + "La Tana di un Unicorno"/Effetti
  Regionali letti per intero ma non trascritti, nessun campo schema per lair/regional effects, stesso principio del
  Kraken/Lich/Signore delle Mummie/Sfinge — stat block CR5 con Incantesimi Innati e 3 Azioni Leggendarie), Vampiro
  (pag. 295-297, con pag. 295-296 lore-only del capitolo Vampiro — "Personaggi Giocanti Come Vampiri" e "La Tana di
  un Vampiro"/Effetti Regionali letti ma non trascritti, stesso principio già consolidato — stat block CR13 con
  Mutaforma/Resistenza Leggendaria/Fuga Nebbiosa/3 Azioni Leggendarie; sidebar "Varianti: Vampiri Combattenti e
  Incantatori" pag. 298 letta ma NON incorporata come voce a sé, a differenza dei precedenti Mezzodrago/Quaggoth
  Thonot/Spettro-Poltergeist — qui il manuale presenta due modificatori generici applicabili al Vampiro base —
  CA18+spadone o casting da mago di 9° livello — non un singolo esempio pienamente statuito e autonomo, quindi
  trattata come le altre varianti opzionali non incorporate, es. Thri-kreen/Troll di questo stesso batch), Progenie
  Vampirica (pag. 298, CR5), Verme Purpureo (pag. 299, CR15, Mostruosità Mastodontica), Vermeiena (pag. 300, CR2) —
  16 stat block; batch B24 2026-07-17 (stessa sessione non interattiva, continua senza interruzione dopo un quinto
  "riprendi da dove hai lasciato"/"continua da dove hai lasciato", Davide ancora assente): **tutta l'Appendice A
  "Creature Varie"** (pag. 317-341, 101 mostri — bestie/animali reali e loro varianti gigante/velenosa: Albero
  Risvegliato, Alce, Alce Gigante, Aquila, Aquila Gigante, Avvoltoio, Avvoltoio Gigante, Babbuino, Beccoaguzzo,
  Cammello, Cane della Morte, Cane Intermittente, Capra, Capra Gigante, Cavallo da Galoppo, Cavallo da Guerra,
  Cavallo da Tiro, Cavalluccio Marino, Cavalluccio Marino Gigante, Cespuglio Risvegliato, Cinghiale, Cinghiale
  Gigante, Coccodrillo, Coccodrillo Gigante, Corvo, Daino, Elefante, Faina, Faina Gigante, Falco, Falco di Sangue,
  Gatto, Gorilla, Gorilla Gigante, Granchio, Granchio Gigante, Gufo, Gufo Gigante, Iena, Iena Gigante, Leone,
  Lucertola, Lucertola Gigante, Lupo, Lupo Feroce, Lupo Invernale, Mammut, Mastino, Millepiedi Gigante, Mulo, Orca
  Assassina, Orso Bruno, Orso Nero, Orso Polare, **Orso delle Caverne** (variante Orso Polare con scurovisione 18m,
  indice-confermata come voce a sé), Pantera, Piovra, Piovra Gigante, Pipistrello, Pipistrello Gigante, Pony,
  Quipper, Ragno, Ragno Gigante, Ragno Lupo Gigante, Ragno-Fase, Rana, Rana Gigante, Rinoceronte, Rospo Gigante,
  Scarabeo di Fuoco Gigante, Sciacallo, Sciame di Corvi, Sciame di Insetti, **Sciame di
  Millepiedi/Ragni/Scarabei/Vespe** (4 varianti di Sciame di Insetti, indice-confermate come voci a sé), Sciame di
  Pipistrelli, Sciame di Quipper, Sciame di Serpenti Velenosi, Sciame di Topi, Scorpione, Scorpione Gigante,
  Serpente Stritolatore, Serpente Stritolatore Gigante, Serpente Velenoso, Serpente Velenoso Gigante, Serpente
  Volante, Squalo Cacciatore, Squalo Gigante, Squalo Tropicale, Tasso, Tasso Gigante, Tigre, Tigre dai Denti a
  Sciabola, Topo, Topo Gigante, **Topi Giganti Contagiosi** (variante malattia di Topo Gigante, indice-confermata
  come voce a sé), Vespa Gigante, Worg) + **tutta l'Appendice B "Personaggi Non Giocanti"** (pag. 342-350, 21 NPC:
  Accolito, Arcimago, Assassino, Bandito, Berserker, Capo dei Banditi, Cavaliere, Combattente Tribale, Cultista,
  Cultista Fanatico, Druido, Esploratore, Gladiatore, Guardia, Mago, Malvivente, Nobile, Popolano, Sacerdote, Spia,
  Veterano — con blocchi incantesimi completi per Accolito/Arcimago/Cultista Fanatico/Druido/Mago/Sacerdote e i
  tratti risorsa "Autorità"/"Eminenza Divina" per Cavaliere/Sacerdote) — 122 stat block, **completando la lettura
  visiva pagina-per-pagina dell'intero manuale, pag. 12-350**; batch B25 2026-07-17 (stessa sessione, passo finale
  di chiusura): **ricognizione di controllo contro l'indice ufficiale del manuale** ("Indice delle Schede delle
  Statistiche", pag. 351-352) — l'intero indice alfabetico (444 nomi reali, escluse le righe "Vedi X" di puro
  rimando) è stato letto e confrontato programmaticamente contro i nomi presenti in `monsters.json`, per
  intercettare eventuali lacune sfuggite a tutti i batch precedenti (24+, su molte sessioni). Emersi 14 apparenti
  scostamenti, verificati singolarmente rileggendo l'immagine della pagina pertinente: 1 falso positivo (refuso
  dell'indice stesso, "Barigura" invece di "Barlgura" — il JSON aveva già il nome corretto, trascritto a suo tempo
  dall'intestazione reale dello stat block); 6 esclusioni deliberate già coerenti con la prassi consolidata del
  progetto (sezioni di regole generiche di archetipo/template senza un proprio blocco statistico indipendente:
  Acererak, Dracolich (Archetipo), Drago d'Ombra (Archetipo), Mezzodrago (Archetipo), Servitore delle Spore
  (Archetipo), Modron Fuori Controllo — per tutte queste il manuale fornisce SOLO l'esempio già trascritto come
  voce a sé, es. "Dracolich Blu Adulto"/"Quaggoth Servitore delle Spore"); 1 voce già presente ma con nome
  combinato diverso dall'indice (Succube/Incubo — confermato che il box del manuale stesso titola le due forme in
  un'unica scheda, coerente con quanto già in `monsters.json`); 1 verificata per continuità coi batch precedenti
  senza una nuova rilettura pagina in questa sessione (Gnomo delle Profondità, già presente come "Gnomo delle
  Profondità (Svirfneblin)" dal batch B17); **4 lacune reali confermate e colmate** (script `batch_b25_gaps.py`,
  stesso schema/pattern di merge dei batch precedenti): **Viverna** (pag. 301, CR6, Drago Grande — mai trascritta
  in nessun batch precedente, probabilmente caduta in un intervallo di pagine 301-316 non ancora coperto),
  **Yuan-ti Sanguepuro** (pag. 310, CR1, Umanoide con Incantesimi Innati — stessa causa), **Mezzoloth** (pag. 313,
  CR5, Immondo yugoloth con Incantesimi Innati — stessa causa, sulla stessa pagina dell'Arcanaloth già presente),
  **Melma Grigia Psichica** (pag. 212, CR1/2 — variante della Melma Grigia con INT elevata a 6 e una nuova azione
  "Stritolamento Psichico", già segnalata come sidebar letta-ma-non-incorporata nel batch B19 e ora effettivamente
  aggiunta come voce a sé, coerente con la prassi già stabilita per varianti con statistiche proprie
  indice-elencate separatamente). **Verifica di chiusura finale**: `monsters.json` conta ora **esattamente 444 voci
  uniche, zero duplicati**, che combaciano **esattamente** con le 444 voci reali dell'indice ufficiale del manuale
  (444 = 444, riconciliazione numerica diretta) — nessun nome dell'indice risulta più mancante dal file. `python3
  -m py_compile ui/views/character_sheet/combattimento_tab.py` (il consumer) pulito dopo l'ultima scrittura.
  **L'audit di `monsters.json` è considerato completo**: ogni pagina del manuale (12-350) è stata letta visivamente
  almeno una volta per la trascrizione, e la copertura è stata verificata in modo indipendente contro l'indice
  stampato del libro stesso, non solo contro la stima approssimativa iniziale (399, da un conteggio euristico `grep
  -c "Classe Armatura""`) — quella stima si è rivelata imprecisa di qualche unità rispetto al vero totale del libro
  (444), ma la riconciliazione finale contro l'indice ufficiale è una verifica più forte e definitiva. Restano solo
  due categorie di lavoro esplicitamente fuori scope, già segnalate nei rispettivi batch e non riconsiderate qui:
  (a) Azioni di Tana/Effetti Regionali (lair actions) di una decina di mostri con tana (Kraken/Lich/Signore delle
  Mummie/Sfinge/Unicorno/Vampiro/Demilich) — lette per intero ma mai trascritte, nessun campo schema dedicato
  esiste ancora in `monsters.json`/`creature_entries`; (b) le varianti opzionali "sidebar" non pienamente statuite
  (Arma su Asta del Diavolo d'Ossa, Lancia del Diavolo del Ghiaccio, Evocare Mephit, Flauto del Satiro, Gemme del
  Controllo degli Slaadi, Armi e Poteri Psionici dei Thri-kreen, Arti Abominevoli del Troll, Vampiri Combattenti e
  Incantatori, Famiglio Pseudodrago, Congreghe di Megere) — modificatori di regola applicabili a qualunque
  esemplare esistente, non nuovi stat block, deliberatamente non incorporati nelle voci base. Nessuna delle due
  categorie blocca l'uso pratico del bestiario per Forma Selvatica/Evoca Creatura in Combattimento, che richiede
  solo lo stat block base già completo per ciascuna. **✅ Entrambe le categorie sono state aggiunte il 2026-07-17**
  (vedi nota dedicata "Azioni di Tana / Effetti Regionali / Varianti Opzionali" più sotto in questa sezione) — il
  testo seguente resta come riferimento del processo di trascrizione usato, non più come TODO aperto. Procedura di
  riferimento (per un'eventuale futura estensione, es. se si decidesse di aggiungere le lair actions):
  1. **Fonte unica**: `ED 5.0 Manuale dei Mostri.pdf` (353 pagine), file già presente tra gli upload della
     sessione. Mai altre fonti (non il web, non l'edizione 2024, non l'inglese) — stessa regola critica di sempre.
  2. **Mai `pdftotext` su questo manuale, nemmeno con `-layout`/`-raw`** — confermato inaffidabile (2026-07-11): il
     layout a due colonne fa intercalare `pdftotext` le due colonne riga per riga in base alla posizione verticale,
     mescolando il contenuto di un mostro con l'inizio del successivo. L'unico metodo affidabile è la **lettura
     visiva delle pagine renderizzate come immagini**: `pdftoppm -r 150 -png "ED 5.0 Manuale dei Mostri.pdf"
     pagina` (alzare a `-r 200` se un blocco specifico risulta illeggibile a 150, stesso accorgimento già usato per
     il master incantesimi). Poi aprire ogni immagine con il tool di lettura immagini e trascrivere a mano quanto
     scritto — mai indovinare un valore poco leggibile: se un numero/nome resta ambiguo anche a risoluzione alta,
     segnalarlo a Davide invece di supporre.
  3. **Decidere il range della sessione PRIMA di iniziare a trascrivere**: scegliere un intervallo di pagine
     contiguo (es. "pag. 23-40") o una famiglia di mostri completa (es. "tutti i Draghi", "tutti i Giganti") — mai
     tentare l'intero manuale in un colpo solo. Stessa logica già adottata per `equipment/*.json` (un file alla
     volta) e per il primo batch di mostri (pag. 12-22, ~1 pagina/mostro a chiamata di lettura immagine).
  4. **Schema dati obbligatorio per ogni voce** (già verificato leggendo il codice consumer in
     `ui/views/character_sheet/combattimento_tab.py`, funzioni
     `_save_creature`/`_open_manual_creature_dialog`/`_show_creature_sheet` — non cambiare questo schema senza
     controllare anche quel codice): `name` (tutto MAIUSCOLO, come nel manuale — la conversione a title case per la
     UI è già gestita da `monster_display_name()`, non va fatta a mano nel JSON), `type` (tipo di creatura base in
     italiano, es. "Umanoide"/"Bestia"/"Non Morto" — attenzione: il Druido filtra la Forma Selvatica solo su
     `type=="Bestia"`, quindi questo campo va trascritto con precisione), `size`, `alignment`, `ac`+`ac_note` (nota
     tra parentesi tipo "(armatura naturale)"), `hp_max`+`hp_formula` (es. "8d8+16"), `speed`, i 6 punteggi
     caratteristica, `saving_throws`/`skills` (dict nome→valore, solo se il mostro li ha),
     `damage_vulnerabilities`/`damage_resistances`/`damage_immunities`/`condition_immunities` (stringhe, vuote se
     assenti), `senses`, `languages`, `cr`, `traits`/`actions`/`reactions`/`legendary_actions` (liste di
     `{"name","description"}`, testo integrale del manuale, non riassunto), `source_page` (numero di pagina del PDF
     — già previsto da `create_creature_entry()` ma quasi mai valorizzato nel file esistente, compilarlo sempre per
     i nuovi mostri: rende verificabile ogni singola voce in futuro).
  5. **Un piccolo script Python usa e getta per ogni batch** (stesso pattern di `build_monsters_batch_a1.py`, già
     usato e poi cancellato per il primo batch — questi script servono solo per scrivere/aggiornare il JSON in un
     colpo solo evitando errori di sintassi manuali, non fanno parte del codice dell'app e vanno rimossi dopo
     l'uso): costruire un dict Python con le voci trascritte in quella sessione, caricare
     `data/game_data/monsters.json` esistente, **sostituire** (per nome, case-insensitive) le voci già presenti ma
     contaminate/da questo batch, **aggiungere** quelle assenti, poi riscrivere il file con `json.dump(...,
     ensure_ascii=False, indent=2)`. Non toccare mai le voci di mostri non ancora trattati in questa sessione.
  6. **Verifica di chiusura ad ogni batch, sempre uguale**: validare che il JSON risultante sia sintatticamente
     corretto; controllare che ogni nuova voce abbia tutti i campi obbligatori del punto 4 (uno script di controllo
     automatico, non a occhio); confermare che le voci NON toccate in questo batch restino identiche a prima
     (nessuna regressione silenziosa sul resto del file); `py_compile` su `combattimento_tab.py` (il consumer) per
     assicurarsi che nessuna modifica di schema l'abbia rotto.
  7. **Aggiornare questa riga della checklist alla fine di ogni batch** con il nuovo conteggio (`N/399`), l'elenco
     dei mostri completati in quella sessione e il range di pagine coperto, più una nuova voce datata in "Note
     Importanti" con lo stesso livello di dettaglio già usato per il primo batch (2026-07-11) — così il progresso
     resta sempre tracciabile e verificabile a campione, invece di una trascrizione integrale mai controllabile
     pezzo per pezzo.
  8. **Se un batch rivela un problema strutturale** (es. un campo dello schema che non basta per una famiglia di
     mostri con una meccanica particolare, tipo i Draghi con più forme d'attacco, o i mostri con azioni
     leggendarie/di tana) — fermarsi e discuterne con Davide prima di proseguire, non improvvisare un'estensione
     dello schema a metà lavoro.
  9. **Sessione 2026-07-16 (batch B1, autonoma, "non fermarti finché non hai finito tutto il libro")**: Davide ha
     dato il via a una sessione di lavoro non interattiva (lui non poteva rispondere), chiedendo di proseguire il
     più possibile senza fermarsi. Procedura di ricognizione aggiunta: prima di ogni batch, usare `pdftotext
     -layout` sull'intero PDF **solo per localizzare** (mai per il contenuto) i punti dove inizia un nuovo blocco
     statistico — si cerca la stringa `"Classe Armatura"` pagina per pagina (split su `\f`) per ottenere una mappa
     approssimativa "pagina → nuovo blocco" e pianificare i batch senza procedere alla cieca. Confermato che le
     pagine 1-11 sono materiale introduttivo (regole generali sui blocchi statistici, nessun mostro), i mostri veri
     iniziano da pag. 12. Batch B1 completato: pag. 23-33, lettura visiva (`pdftoppm -r 150`) di ogni pagina, 10
     mostri (Banshee, Basilisco, Behir, Beholder, Tiranno della Morte, Spectator, Belva Distorcente, Bugbear,
     Bugbear Capotribù, Bulette). Confermata la stessa contaminazione OCR già nota (es. vecchio BEHIR aveva `"16dl2
     + 64"` invece di `"16d12 + 64"`, vecchio BUGBEAR `"5d8 + S"` invece di `"5d8 + 5"`, vecchio BULETTE assente
     del tutto) — tutti i nomi propri erano già corretti nel file esistente (nessuna traduzione dall'inglese
     trovata in questo batch), solo i valori numerici/testuali corrotti dall'OCR. **Nota su schema**: i mostri con
     "azioni leggendarie" (Beholder, Tiranno della Morte) seguono lo schema già in uso per altri multi-legendary
     monster già presenti nel file (es. ABOLETH, i draghi adulti, SOLAR) — `legendary_actions` è una lista piatta
     di `{"name","description"}`, il paragrafo introduttivo standard ("può effettuare 3 azioni leggendarie, una
     alla volta, solo alla fine del turno di un'altra creatura, le recupera a inizio turno") non viene salvato come
     voce separata negli esempi già presenti nel file, ma qui — a differenza di quegli esempi, che hanno più
     opzioni distinte — Beholder/Tiranno hanno **un'unica opzione ripetibile 3 volte** ("Raggio Oculare"), quindi
     il testo introduttivo è stato incluso nella descrizione di quell'unica voce per non perdere l'informazione "3
     volte per turno" (altrimenti l'unica voce sembrerebbe utilizzabile una sola volta). **ZOMBI BEHOLDER** (già
     presente nel file, cr 5) non è stato toccato in questo batch — non è comparso nelle pagine 23-33 lette,
     probabilmente vive altrove nel manuale (sezione Zombi, famiglia Z) e va verificato quando si arriverà a quella
     lettera. **Verifica di chiusura**: JSON validato (348 voci totali dopo il batch), `py_compile` su
     `combattimento_tab.py` pulito, nessuna voce fuori batch toccata (verificato per nome). Sessione proseguita
     subito dopo con il batch successivo (pag. 34+) senza fermarsi, come richiesto.
  **Batch B2 (2026-07-16, stessa sessione autonoma, pag. 34-44)**: 12 mostri — Bullywug, Cacciatore Invisibile,
  Cambion, Cavaliere della Morte, Cavallo degli Incubi, Centauro, Chimera, Chuul, Ciclope, Coboldo Alato, Coboldo,
  Cockatrice — letti visivamente pagina per pagina (`pdftoppm -r 150`), stessa disciplina del batch B1 (mai
  `pdftotext` per il contenuto). Nessun problema strutturale di schema incontrato (nessuna azione leggendaria/di
  tana in questo batch). **Verifica di chiusura**: JSON validato (350 voci totali dopo il batch), `py_compile` su
  `combattimento_tab.py` pulito, nessuna voce fuori batch toccata (verificato per nome).
  **Batch B3 (2026-07-16, stessa sessione autonoma, pag. 45-65)**: 18 mostri in due gruppi. Gruppo 1 — 4 mostri
  isolati non correlati tra loro: Couatl (pag. 45), Cumulo Strisciante/Shambling Mound (pag. 46), Cuspide
  Letale/Piercer (pag. 47), Demilich (pag. 48, incluso il proseguimento a pag. 49 con le regole di tana "La Tana di
  un Demilich"/"Tratti della Tana" e il riquadro "Acererak e i Suoi Discepoli" — quest'ultimo descrive solo una
  VARIANTE opzionale con un'azione leggendaria di tana aggiuntiva specifica per boss nominati come Acererak, non un
  dato del blocco statistico base del Demilich, quindi non riportata nel JSON). Gruppo 2 — l'intera famiglia dei 14
  demoni "tipo" del capitolo "Demone" (pag. 53-65): Balor, Barlgura, Chasme, Demone d'Ombra, Dretch, Glabrezu,
  Goristro, Hezrou, Mane, Marilith, Nalfeshnee, Quasit, Vrock, Yochlol. **Le pagine 50-52 sono risultate essere
  lore generale del capitolo Demone** (natura dei demoni, Signori dei Demoni —
  Baphomet/Demogorgon/Graz'zt/Juiblex/Lolth/Orcus/Yeenoghu — tabella "Tipi di Demoni" 1-6), **nessuno stat block**:
  nessuna voce JSON creata da queste 3 pagine, coerente con la regola del progetto di non inventare mai un blocco
  statistico per un demone signore/tipo generico non trattato con la sua scheda dedicata (i Signori dei Demoni con
  nome proprio, se hanno un blocco statistico proprio nel manuale, andranno cercati altrove — probabilmente in
  un'appendice, non verificato in questo batch). Pag. 54 include anche il riquadro "Variante: Evocazione dei
  Demoni" (tabelle di probabilità di evocazione reciproca tra demoni) — non uno stat block, non riportato nel JSON.
  **Schema**: nessun problema strutturale — Demilich è l'unico con azioni leggendarie in questo batch (4, "Costa
  2/3 Azioni" per due di esse — stesso schema già in uso per costi multipli, es. mostri con azioni leggendarie
  potenziate di altre edizioni/fonti già presenti nel file). **Verifica di chiusura**: JSON validato (354 voci
  totali dopo il batch: 336 preesistenti + 14 sostituite/aggiornate + 4 nuove nette), tutti i 18 nomi con tutti i
  campi obbligatori presenti (script di controllo automatico), `py_compile` su `combattimento_tab.py` pulito,
  nessuna voce fuori batch toccata (verificato per nome). Sessione proseguita subito dopo con il capitolo
  successivo (Diavolo, pag. 66+) senza fermarsi, come da istruzione di Davide.
  **Batch B4 (2026-07-16, stessa sessione autonoma, pag. 66-81)**: 18 mostri in tre gruppi. Gruppo 1 — l'intera
  famiglia degli 11 diavoli "tipo" del capitolo "Diavolo" (pag. 70-78): Diavolo Barbuto, Diavolo Cornuto, Diavolo
  d'Ossa, Diavolo del Ghiaccio, Diavolo della Fossa, Diavolo delle Catene, Diavolo Spinato, Diavolo Uncinato,
  Erinni, Imp, Lemure. **Le pagine 66-69 sono lore generale del capitolo Diavolo** (natura dei diavoli, gerarchia
  infernale con tabella "Gerarchia Infernale" 1-13, promozione/degradazione, tabella "Strati e Signori dei Nove
  Inferi" con i 9 arciduchi/arciduchesse — Zariel/Dispater/Mammon/Belial e
  Fierna/Levistus/Glasya/Belzebù/Mefistofele/Asmodeus — più 2 riquadri varianti "Evocazione dei Diavoli"/"Famiglio
  Imp"/"Veri Nomi dei Diavoli e Talismani"), **nessuno stat block**: nessuna voce JSON creata da queste pagine,
  stessa regola già applicata al capitolo Demone (nessun blocco statistico inventato per un arciduca/signore non
  trattato con una scheda dedicata). "Diavolo d'Ossa" e "Imp" erano assenti dal file esistente (aggiunti come voci
  nuove, non sostituzioni); gli altri 9 nomi erano già presenti (probabilmente con la stessa contaminazione
  OCR/traduzione già vista altrove) e sono stati sostituiti integralmente. Gruppo 2 — l'intero capitolo "Dinosauro"
  (pag. 79-80): Allosauro, Anchilosauro, Plesiosauro, Pteranodonte, Tirannosauro, Triceratopo — nessuna lore
  separata da saltare, la breve introduzione lore di ciascun dinosauro condivide la pagina con almeno uno stat
  block. Gruppo 3 — Divoracervelli/Intellect Devourer (pag. 81), voce isolata non correlata alle precedenti.
  **Schema**: nessun problema strutturale — nessuna azione leggendaria in questo batch; il Diavolo della Fossa (CR
  20) ha solo azioni normali + tratti (inclusi incantesimi innati), coerente con lo schema già in uso. Due varianti
  opzionali di sotto-riquadro non riportate come dati a sé (solo lette per completezza, non affiorano nello schema
  JSON): "Variante: Arma su Asta del Diavolo d'Ossa" (pag. 72, opzione di equipaggiamento alternativa) e "Variante:
  Lancia del Diavolo del Ghiaccio" (pag. 73, idem) — entrambe descrivono un set di azioni ALTERNATIVO che il DM può
  scegliere di dare invece delle azioni base, non azioni aggiuntive sempre presenti; il blocco statistico base (già
  trascritto) resta quello con artigli/coda/morso, coerente con la scelta di riportare solo il blocco "standard" di
  ciascun mostro salvo diversa indicazione futura di Davide. **Verifica di chiusura**: JSON validato (356 voci
  totali dopo il batch: 16 sostituite + 2 nuove nette), tutti i 18 nomi con tutti i campi obbligatori presenti
  (script di controllo automatico), `py_compile` su `combattimento_tab.py` pulito, nessuna voce fuori batch toccata
  (verificato per nome). Sessione proseguita subito dopo (pag. 82+) senza fermarsi, come da istruzione di Davide.
  **Azioni di Tana / Effetti Regionali / Varianti Opzionali — aggiunte per intero (2026-07-17)** — dopo la chiusura
  dell'audit (batch B25, 444/444), Davide ha chiesto chiarimento su cosa fosse rimasto fuori: la risposta ("nessun
  mostro mancante, solo Azioni di Tana/Effetti Regionali di 7 mostri con tana e ~10 varianti opzionali sidebar,
  escluse per mancanza di un campo schema, non per impossibilità di trascrizione") lo ha portato a chiedere
  esplicitamente di aggiungere anche questi dati ORA, per non dover mai più riaprire il manuale per questo lavoro
  ("conviene avere tutto per evitare che in futuro dobbiamo rifare questo lavoraccio"). Rilette le immagini delle
  pagine pertinenti (48-49, 72-74, 184, 197, 208, 218, 231-233, 255, 266, 271, 274, 287, 290, 293, 295-298) e
  trascritto tutto per intero, nessun riassunto.
  **Nuovo schema** (`data/models.py → CreatureEntry`, `data/database.py → _migrate()`,
  `data/repositories/character_repo.py`): 7 nuovi campi — `reactions` (bug pre-esistente scoperto in questo
  passaggio: la colonna non esisteva mai, quindi le Reazioni di un mostro, es. "Parata", sparivano silenziosamente
  ogni volta che un personaggio/master aggiungeva quel mostro a Forma Selvatica/Evocazione, nonostante il dato
  fosse già presente e corretto in `monsters.json` da tempo), `lair_actions_intro`/`lair_actions` (lista di
  stringhe), `regional_effects_label` (di norma "Effetti Regionali", ma "Tratti della Tana" per il Demilich — nome
  preso dal manuale, non generico), `regional_effects_intro`/`regional_effects` (lista di stringhe),
  `variant_rules` (lista di `{"name","description"}`). Migrazione via 7 nuove `_add_column()` idempotenti;
  `_row_to_creature()`/`create_creature_entry()` estesi coerentemente (colonne INSERT, placeholder `?`, tupla
  valori — verificato con uno script di conteggio dedicato dopo un refuso iniziale: 41 placeholder contro 42
  colonne/valori, corretto e riverificato 42/42/42).
  **Bug reale trovato e corretto nello stesso passaggio, non nella richiesta originale**: sia `_detail_content()`
  (anteprima bestiario) sia `_show_creature_sheet()` (scheda creatura salvata) in `combattimento_tab.py` leggevano
  la descrizione di ogni tratto/azione/azione leggendaria con `t.get("text", "")` — ma la chiave reale in
  `monsters.json` è `"description"`, mai stata `"text"` in nessun punto scrivente del codice (confermato via grep:
  zero occorrenze di un writer che produca `"text"`). Risultato pratico: **la descrizione di ogni
  tratto/azione/azione leggendaria di tutti i 444 mostri non è mai stata visibile nella UI**, dalla creazione della
  feature — comparivano solo i nomi in grassetto, con una riga vuota sotto. Corretto con un helper `_desc(d)` che
  legge `description` (con fallback `text` per sicurezza) in tutti e 6 i punti coinvolti (3 in `_detail_content`, 3
  in `_show_creature_sheet`), applicato automaticamente anche alle nuove sezioni Reazioni/Azioni di Tana/Effetti
  Regionali/Varianti appena aggiunte.
  **Dati trascritti** (nessun dato indovinato, tutto letto dalle immagini): Azioni di Tana e/o Effetti Regionali
  per **Demilich** (pag. 48-49, "Tratti della Tana"), **Kraken** (pag. 184, solo azioni di tana), **Lich** (pag.
  197, solo azioni di tana), **Signore delle Mummie** (pag. 231-233, entrambi), **Androsfinge/Ginosfinge** (pag.
  271, stessa tana condivisa, solo azioni di tana), **Unicorno** (pag. 293, solo effetti regionali), **Vampiro**
  (pag. 295-296, solo effetti regionali) — 8 voci JSON (Sfinge conta doppio: Androsfinge+Ginosfinge). Varianti
  opzionali applicate a 22 voci: "Arma su Asta del Diavolo d'Ossa" (Diavolo d'Ossa, pag. 72), "Lancia del Diavolo
  del Ghiaccio" (Diavolo del Ghiaccio, pag. 73), "Evoca Mephit" (tutti e 6 i Mephit, pag. 218), "Flauto del Satiro"
  (Satiro, pag. 266), "Gemma del Controllo degli Slaadi" (tutti e 6 gli Slaad, pag. 274), "Armi e Poteri Psionici
  dei Thri-kreen" (pag. 287), "Arti Abominevoli" (Troll, pag. 290), "Vampiri Combattenti e Incantatori" (Vampiro,
  pag. 298), "Famiglio Pseudodrago" (pag. 255), "Congreghe di Megere" (tutte e 3 le Megere, pag. 208).
  **UI** (`combattimento_tab.py`): nuove sezioni "Reazioni" (badge rosso, stesso stile di Azioni), "Azioni di Tana"
  ed "Effetti Regionali"/"Tratti della Tana" (intro in corsivo + elenco puntato, nessun tiro per colpire
  strutturato dato che il manuale le scrive come prosa), "Varianti Opzionali" (badge blu, stesso `feat_tile` di
  Tratti/Azioni) — mostrate solo se il mostro ha dati non vuoti in quei campi, sia nell'anteprima del bestiario
  picker sia nella scheda di una creatura già salvata. `_save_creature()` propaga tutti i nuovi campi a
  `create_creature_entry()`.
  **Verificato**: script di controllo (`monsters.json`, 444 voci totali, zero duplicati) — schema completo presente
  su tutte e 8 le voci lair/regional e su tutte e 22 le voci varianti (nessun campo obbligatorio mancante, ogni
  variante ha `name`+`description` non vuoti); `python3 -m py_compile` pulito su
  `combattimento_tab.py`/`character_repo.py`/`models.py`/`database.py`; test end-to-end con DB temporaneo isolato
  (mai quello reale): Vampiro creato come evocazione, riletto dal DB — `lair_actions_intro`, 4 `regional_effects`,
  1 `variant_rules` (con `description` non vuota) tutti persistiti e riletti correttamente; Cavaliere (mostro con
  una vera Reazione, "Parata" — il Vampiro stesso non ne ha, correttamente `[]` nel manuale) — round-trip di
  `reactions` confermato; un mostro senza alcun dato di tana/variante (Goblin) resta con campi vuoti, nessuna
  eccezione. File batch usa-e-getta rimosso dopo l'uso (richiesta permesso via `allow_cowork_file_delete`, come da
  convenzione del progetto per file scritti nella cartella di lavoro dell'utente).
- [x] ~~tags.json~~ — **rimosso il 2026-07-10** (non `[x]` audit completato, ma eliminazione: era dato morto — mai
  letto da nessun codice reale — e conteneva sia nomi inventati/tradotti dall'inglese sia un bug meccanico vero,
  Cotta di Maglia/Corazza ad Anelli classificate come armatura media anziché pesante. Vedi "Note Importanti" e la
  sezione `equipment/` sopra per il changelog completo)
- [x] equipment/weapons.json ✅ (2026-07-17 — verificato riga per riga con Davide contro il manuale, PHB IT
  p.146-149: proprietà delle armi, armi improvvisate/argentate/speciali, tutte le liste semplici mischia/distanza e
  guerra mischia/distanza. Nessuna correzione necessaria.)
- [x] equipment/armor.json ✅ (2026-07-17 — verificato riga per riga con Davide contro il manuale, PHB IT p.144-146:
  regole competenza/CA/Forza/Furtività/scudi, tutte le liste leggere/medie/pesanti/scudi, tabella
  indossare/togliere. Confermato esplicitamente il nome "Corazza di Piastre" (400 mo, CA 14+Des max2). Nessuna
  correzione necessaria.)
- [x] equipment/adventuring_gear.json ✅ (2026-07-17 — verificato con Davide contro il manuale, PHB IT p.150-153:
  catalogo 99 oggetti, 42 descrizioni con regole dedicate, capienza contenitori, tutte e 7 le dotazioni con
  `contents_items` espansi. Confermato che i 7 oggetti senza voce propria nel catalogo (Cassetta per le Offerte,
  Cubetto di Incenso, Incensiere, Spago, Sacchetto di Sabbia, Libro di Studio, Coltellino) sono corretti così —
  nessuna correzione necessaria.)
- [x] equipment/tools.json ✅ (2026-07-17 — verificato con Davide contro il manuale, PHB IT p.154:
  regole/descrizioni di tutte le categorie (Arnesi da Falsario/Scasso, Borsa da Erborista, Giochi, Sostanze da
  Avvelenatore, Strumenti da Artigiano, Strumenti da Navigatore, Strumenti Musicali, Trucchi per il Camuffamento),
  tutte le 6 voci "strumenti vari", 4 giochi, 17 strumenti da artigiano, 10 strumenti musicali. Nessuna correzione
  necessaria.)
- [x] equipment/mounts_and_vehicles.json ✅ (2026-07-17 — verificato con Davide contro il manuale, PHB IT p.155-157:
  regole capacità di trasporto/bardatura/sella/imbarcazioni a remi, tabelle Cavalcature e Altri Animali, Finimenti
  e Veicoli da Tiro, Imbarcazioni. Nessuna correzione necessaria.)
- [x] equipment/economy.json ✅ (2026-07-17 — verificato con Davide contro il manuale, PHB IT p.143 e 157-159:
  ricchezza di partenza per classe, valuta/tabella di cambio, merci, spese stile di vita, vitto e alloggio,
  servizi, servizi magici. Nessuna correzione necessaria.)

  **✅ Audit `equipment/*.json` completato (6/6 file, 2026-07-17).** Tutti e 6 i file (ex `equipment/equipment.json`
  unico, diviso il 2026-07-10) sono stati trascritti il 2026-07-10 leggendo visivamente le pagine 143-159 del PDF
  renderizzate come immagini (non tramite OCR/pdftotext, inaffidabile su queste tabelle) e sono stati verificati
  riga per riga con Davide in questa sessione — nessuna correzione necessaria in nessuno dei 6 file, solo la
  conferma esplicita del nome "Corazza di Piastre" in `armor.json`. Esclusa deliberatamente la tabella d100
  "Oggetti Insoliti" (p.160-161, vedi TODO dedicato).

---


---

> Questo file è stato estratto da `CLAUDE.md` il 2026-07-31 durante la riorganizzazione della documentazione del
> progetto (il file principale era cresciuto fino a superare 860 KB, causando compattazioni troppo frequenti della
> chat). Il contenuto è verbatim, nessuna informazione è stata riassunta o rimossa. Per la mappa completa dei
> documenti del progetto vedi `CLAUDE.md` alla radice.
