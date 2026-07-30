# Revisione generale del progetto — 2026-07-26

## Stato di avanzamento

| fase | stato |
|---|---|
| 1 · Bug (B1–B12) | ✅ **completata** — vedi il changelog in `CLAUDE.md` → "Revisione 2026-07-26 · FASE 1 COMPLETATA" |
| 2 · Pulizia (codice morto/duplicato) | ✅ **completata** (con un residuo misurato e documentato: vedi `creation_shared.py`) |
| 3 · Restyle (`restyle_design.md`) | 🔄 **Fase A completata** (token, primitive, `ft.Theme` completo, `assets_dir`); B/C/D/E da fare |
| 4 · Feature (`feature_design_2026_07_26.md`) | ⏸ da fare — 5 decisioni aperte da chiedere a Davide |

> Il documento sotto è l'**analisi originale** che ha prodotto il piano: resta
> invariato come riferimento. Nessuna modifica al codice era stata applicata al
> momento della sua scrittura. Ogni affermazione qui sotto è stata verificata leggendo il codice reale
> o misurandola con uno script, non dedotta da CLAUDE.md.
>
> Metodo: `compileall` + `pyflakes` su tutte le 45.116 righe sorgente (esclusi
> `build/` e `.venv/`), `vulture` per il codice morto, lettura diretta dei file per
> ogni bug candidato, `difflib` per misurare la duplicazione.

---

## 1. Aspetto visivo — perché sembra un'app del 2018

### Diagnosi misurata (non impressioni)

| Misura | Valore reale | Cosa implica |
|---|---|---|
| `ft.BoxShadow` usati | **0** in 45k righe | zero profondità: tutto piatto con bordi 1px |
| Gradienti (`LinearGradient`/`RadialGradient`) | **0** | nessuna texture, nessun volume |
| Animazioni (`animate*=`) | **2** in tutta l'app | ogni transizione è uno scatto secco |
| Raggi angoli | 140× `radius=6`, 49× `radius=4` | spigoli duri; il linguaggio 2024-26 è 12–20 con gerarchia |
| Font | Georgia / Arial / Courier New | font di sistema, nessuna identità |
| `assets/fonts/` | **vuota** | e `assets_dir` non è nemmeno passato a `ft.run()` su desktop → oggi è tecnicamente impossibile caricare un font custom |
| `ft.Theme` | solo `color_scheme` + `font_family` | Flet 0.85.3 espone **58 sotto-temi** (`dialog_theme`, `card_theme`, `text_theme`, `button_theme`, `scrollbar_theme`, `visual_density`, `page_transitions`, …): nessuno usato |
| `fantasy_card()` | 18 chiamate, **solo** in wizard/manual_form | contro **166** `ft.Border(...)` scritti a mano nelle view |
| `"#ffffff"` hardcoded in `ui/` | **153** | + colori fuori palette (`#7b1fa2` viola, `#d2691e`, 4 grigi diversi) |
| Controlli Material moderni | 0 `ft.Card`, 0 `ft.Chip`, 0 `ft.Badge`, 0 `ExpansionTile` | tutto ricostruito a mano da `Container` |
| Temi | 1 solo (chiaro), `ThemeMode.LIGHT` fisso | nessun dark mode |

### I 7 punti critici, in ordine di impatto visivo

1. **Nessuna elevazione.** Le "card" sono rettangoli con bordo grigio 1px e un filetto
   colorato in cima. È esattamente l'estetica Bootstrap 3. Flet 0.85.3 supporta
   `shadow`, `gradient`, `blur`, `offset`, `scale`, `Shimmer`, `AnimatedSwitcher`,
   `ShaderMask` — verificato per introspezione sul pacchetto installato. Nessuna
   nuova dipendenza serve.
2. **Nessun movimento.** Niente hover, niente press feedback oltre all'`ink`
   di default, nessuna transizione tra tab/sezioni. Un'app moderna comunica lo
   stato con 150–250 ms di animazione, non con un ridisegno istantaneo.
3. **Il design system esiste ma è bypassato.** `ui/theme.py` ha
   `fantasy_card`/`section_header`/`stat_badge`, ma 23 view su 25 si costruiscono
   le proprie card inline. Conseguenza pratica: **un restyle oggi significa
   toccare 25 file a mano**. Va consolidato *prima* di cambiare l'aspetto,
   altrimenti la modernizzazione non è manutenibile.
4. **La palette mente e non ha gerarchia.** `COLOR_ACCENT_GOLD` vale `#1848a0`
   (blu). Quattro accenti a saturazione piena (crimson, blu, ambra, verde)
   convivono sullo stesso schermo: nulla emerge, tutto grida. Serve **1 accento
   primario** + gli altri declassati a colori *semantici* (successo/attenzione/
   pericolo/magia) usati solo dove hanno un significato.
5. **Nessun dark mode.** Per un'app usata la sera al tavolo, su tablet, è la
   mancanza più sentita — e anche quella che fa sembrare "vecchia" un'app oggi.
6. **Tipografia senza scala.** Dimensioni sparse tra 9 e 52 px scelte caso per
   caso, mai una scala definita. Molti testi a 9-10px; `COLOR_TEXT_MUTED`
   (`#7880a0`) su bianco dà contrasto 3.6:1 → sotto la soglia AA per testo piccolo.
7. **Densità da desktop 2015.** Sidebar 82px con icone 22px ed etichette 10px;
   la tab Combattimento è **un unico scroll piatto con 21 sezioni**, senza
   raggruppamenti né sezioni comprimibili.

### Piano proposto (5 fasi, dalla più abilitante alla più visibile)

**Fase A — fondazioni** (invisibile all'utente, abilita tutto il resto)
- `ui/theme.py` → design tokens: scala di spaziatura (4/8/12/16/24/32),
  scala di raggi (`R_SM=8`, `R_MD=12`, `R_LG=16`, `R_PILL=999`), 3 livelli di
  elevazione (`ELEV_1/2/3` come `BoxShadow` predefinite), scala tipografica
  (`display/title/subtitle/body/label/mono`).
- Primitive riusabili: `surface()`, `card()`, `pill()`, `chip()`, `stat_tile()`,
  `section()` (con supporto comprimibile) — e migrazione progressiva delle 166
  card inline.
- `get_theme()` riscritta usando i sotto-temi Flet: `dialog_theme` (raggio +
  ombra su ~60 dialog **in un colpo solo**), `card_theme`, `text_theme`,
  `button_theme`/`outlined_button_theme`/`text_button_theme`, `scrollbar_theme`,
  `visual_density`, `page_transitions`.
- Wiring `assets_dir` su desktop/mobile (attenzione: in web mode è già occupato
  da `get_character_exports_path()` — va risolto, probabilmente spostando gli
  export in una sottocartella di `assets/`).

**Fase B — identità visiva**
- Font self-hosted in `assets/fonts/`: un serif display per titoli/nomi
  (Cinzel o Cormorant Garamond — leggibili, non "fantasy-parodia") + un sans
  moderno per il corpo (Inter) + un mono per i numeri (JetBrains Mono).
  Il fantasy sta nei titoli, non nel testo di regolamento.
- Palette a due livelli: superfici neutre calde (pergamena) con 3 gradini di
  profondità + **1 accento primario** (il rosso D&D) + semantici.
- Texture pergamena appena percettibile con un `LinearGradient` a bassissimo
  contrasto sullo sfondo (nessuna immagine, zero peso).
- Ombre soffuse a 2 livelli invece dei bordi 1px.

**Fase C — micro-interazioni**
- `animate=200ms` su card, pillole, chip, tab; `animate_scale` sul press.
- `AnimatedSwitcher` sui cambi di tab/sezione e sui contenuti dei dialog.
- Barra HP animata (transizione del valore, non salto).
- `Shimmer` come skeleton mentre si caricano bestiario/incantesimi/oggetti.

**Fase D — dark mode + densità**
- Doppia palette (token semantici, non colori hardcoded) + toggle unico.
  Prerequisito: eliminare i 153 `"#ffffff"` hardcoded, altrimenti il tema scuro
  è impossibile.
- `visual_density` e dimensioni tap-target differenziate desktop/tablet.

**Fase E — restyle per superficie**, una view alla volta: Home → Scheda
(5 tab) → Incantesimi → Master → Mappe/Dadi/Diario.

---

## 2. Bug ed errori logici individuati (nessuno corretto)

`compileall` e `pyflakes` sono **puliti** su tutte le 45k righe: nessun errore di
sintassi, import o nome. I problemi sono tutti semantici.

### Errori di regolamento

| # | Problema | Dove | Riferimento |
|---|---|---|---|
| **B1** | Curare un personaggio da 0 HP **non azzera i tiri salvezza contro morte**: i pallini restano segnati | `combattimento_tab.py` → `_on_heal_click` | PHB p.197 |
| **B2** | Subire danno a 0 HP **non aggiunge un fallimento** ai TS contro morte (2 se critico) | `_on_damage_click` | PHB p.197 |
| **B3** | **Morte istantanea per danno massiccio** (danno residuo ≥ HP max) non implementata | `_on_damage_click` | PHB p.197 |
| **B4** | Il **riposo lungo non riduce l'Indebolimento di 1** | `_section_riposo_lungo` → `do_rest` | PHB p.186 |
| **B5** | Il riposo lungo non azzera `ca_bonus` (un bonus CA temporaneo sopravvive alla notte) né `frenzy_active` (un'ira non può attraversare un riposo lungo) | `do_rest` | — |
| **B6** | Né riposo breve né lungo disattivano Forma Selvatica / evocazioni attive. La funzione corretta **esiste ma non è mai chiamata**: `deactivate_all_creatures()` | `character_repo.py:2909` | PHB (Forma Selvatica dura ore, non giorni) |
| **B7** | Riposo breve: `recovered = max(1, roll + con_mod*n)` applica il minimo **al totale** invece che **per dado** — sbagliato con CON negativa | `_on_short_rest_click` → `apply` | PHB p.186 |

### Errori tecnici

| # | Problema | Dove |
|---|---|---|
| **B8** | `HomeView._poll_loop`: thread ogni 5 s che chiama `self.refresh()` + `page.update()` **da un thread non-UI**, mutando l'albero dei controlli in concorrenza con la UI. Ricostruisce l'intera lista anche se nulla è cambiato (nessun confronto su `updated_at`). Su qualunque eccezione fa `break` → la sincronizzazione muore per sempre, in silenzio. Su desktop/mobile (sessione singola) è puro spreco. | `home_view.py:89` |
| **B9** | `_start_update_check`: thread che dopo 3 s apre un `AlertDialog` da un thread non-UI, potenzialmente sopra il wizard di creazione in corso. | `app.py:425` |
| **B10** | `_refresh()` di ogni tab = ~12 query + `controls.clear()` + rebuild totale **ad ogni singolo click** (anche −1 HP). Effetto visibile: **lo scroll torna in cima** dopo ogni azione, in un tab con 21 sezioni. È il difetto UX più fastidioso dell'app. | tutti i tab della scheda |
| **B11** | `danger_button()`: testo `COLOR_TEXT_PRIMARY` (`#1c1e2c`) su fondo crimson (`#c0182c`) → contrasto ~2.3:1, illeggibile. Oggi è dead code, ma va corretto prima di riusarlo nel restyle. | `theme.py:191` |
| **B12** | f-string senza placeholder (cosmetico, unico warning pyflakes dell'intero progetto) | `combattimento_tab.py:2989` |

---

## 3. Feature mancanti (rispetto ai manuali)

### Lato giocatore

1. **I dadi non parlano con la scheda.** `DiceView` è dichiaratamente standalone
   ("nessun DB, stato solo in sessione") e non conosce il personaggio. Nel
   frattempo la scheda calcola già *tutti* i modificatori (18 abilità, 6 TS,
   tiro per colpire e danno di ogni arma, iniziativa, CD incantesimi) e **nulla
   è cliccabile per tirare**. È la mancanza n.1 in termini di utilità reale al
   tavolo, e anche quella che più farebbe sembrare l'app "viva".
2. **Concentrazione**: mai tracciata, nonostante il campo `concentration` sia già
   presente in tutti i 361 incantesimi. Servirebbe: flag "concentrato su X",
   TS Costituzione (CD 10 o metà danno) quando si subisce danno, rottura
   automatica a 0 HP.
3. **Condizioni** (Appendice A PHB, 15 voci): tracciata solo l'Indebolimento.
   Mancano accecato, affascinato, afferrato, assordato, incapacitato, invisibile,
   paralizzato, pietrificato, prono, spaventato, stordito, trattenuto, avvelenato.
4. **Oggetti magici lato giocatore**: il compendio di 264 voci è visibile **solo
   al master**. Il giocatore non può sfogliarlo né aggiungere un oggetto alla
   propria scheda, e non esiste alcuna gestione della **sintonia** (massimo 3
   oggetti sintonizzati) nonostante `requires_attunement` sia già nel dato.
5. **Multiclasse** (PHB cap. 6): `class_name` è una stringa singola. Impatta HP,
   slot (tabella multiclasse dedicata), competenze, prerequisiti di caratteristica.
   Intervento grosso — da decidere se è in ambito o no.
6. **Recupero Arcano del Mago**: oggi è solo una nota testuale "aggiorna
   manualmente gli slot".
7. Trasporto/ingombro variante, spese di stile di vita e attività di inattività:
   i dati sono già in `economy.json`, nessuna UI li usa.

### Lato master

8. **Nessun tiro automatico dell'iniziativa** nel tracker: il default è 10 da
   digitare a mano per ogni combattente (aggiungi 5 goblin → 5 campi). Il
   modificatore di Destrezza è già nello stat block.
9. **Nessun tiro di attacco/danno dai mostri**: le azioni ci sono come testo,
   ma non c'è un pulsante per tirare.
10. **Condizioni e concentrazione per combattente** nel tracker d'incontro.
11. **Immagini di mostri/NPC** (già identificato come task futuro).
12. **PE non vengono distribuiti**: il calcolatore dice la difficoltà, ma dopo
    l'incontro non c'è modo di assegnare i PE ai personaggi giocanti. È l'anello
    mancante più evidente tra Modalità Master e schede dei giocatori.
13. Altro dal DMG mai affrontato: tabelle del tempo atmosferico, generatori di
    dungeon/insediamenti, tracciamento del tesoro assegnato per campagna.
14. **Artefatti** (13 voci, DMG) — esclusione già decisa e documentata.

---

## 4. Migliorie su ciò che è già implementato

- **Scroll che torna in cima** ad ogni azione (B10) → refresh chirurgico della
  sola sezione toccata invece del rebuild totale. Priorità alta: è percepito
  come "l'app è lenta/scatta".
- **Tab Combattimento: 21 sezioni in un unico scroll.** Sezioni comprimibili con
  memoria dello stato, e/o suddivisione in sotto-gruppi (Combattimento /
  Risorse / Abilità).
- **Indebolimento solo consultivo**: senza automatismi invasivi, si potrebbe
  almeno mostrare il promemoria dell'effetto *dove serve* (svantaggio accanto ai
  TS, velocità dimezzata accanto alla velocità) invece che in una sezione a parte.
- **Due diari diversi sulla stessa tabella**: `DiarioTab` dentro la scheda e
  `DiaryView` nella sidebar leggono entrambi `diary_entries` con layout diversi.
  Confonde: da unificare.
- **Peso trasportato incompleto**: `Weapon` non ha un campo peso, quindi le armi
  non contribuiscono al carico; costo/peso del catalogo sono solo una riga
  informativa.
- **Nessuna ricerca globale**: 361 incantesimi + 444 mostri + 264 oggetti magici
  + 42 talenti, ognuno in una lista separata, senza un punto di ricerca unico.
- **Creazione personaggio**: wizard e form manuale divergono in dettagli senza
  motivo (la sottorazza si scegli in fasi diverse) — vedi punto 5.
- **Accessibilità**: molti testi a 9–10 px, `COLOR_TEXT_MUTED` sotto la soglia
  di contrasto AA.
- **Nessun annulla** oltre ai dialog di conferma, nessuno storico delle modifiche.

---

## 5. Codice morto, ridondante, inutilizzato

### Ridondanza strutturale (la più costosa)

- **`wizard_view.py` (4.086 righe) + `manual_form.py` (3.616 righe)**:
  misurato con `difflib` → **83 funzioni con lo stesso nome** e **1.965 righe
  identiche = 67% del file più piccolo**. È la causa documentata di più bug del
  progetto: ogni correzione va applicata due volte, e in almeno un caso
  registrato in CLAUDE.md è stata applicata a uno solo dei due. → estrarre un
  modulo condiviso (`creation_shared.py`) con le 83 funzioni comuni.
- **`character_repo.py` (2.984 righe)**: god module — personaggi, armi,
  inventario, valute, slot, incantesimi, diario, note di campagna, creature,
  risorse di classe, competenze. Da spezzare per dominio.
- **`profilo_tab.py` (4.469)** e **`combattimento_tab.py` (3.860)**: il solo
  dialog di level-up è ~2.000 righe dentro un tab.

### Dead code confermato (verificato una funzione per volta: solo la definizione, zero chiamanti)

- `ui/widgets.py` — `dropdown_with_info`, `make_spell_describe`,
  `make_feat_describe`, `make_named_option_describe`, `make_invocation_describe`
  (~200 righe, superate dal `CardPicker`).
- `ui/theme.py` — `danger_card`, `divider`, `stat_badge`, `gold_button`,
  `danger_button`.
- `character_repo` — `deactivate_all_creatures` (⚠︎ **da collegare**, non da
  togliere: è esattamente il fix di B6), `update_creature_notes`.
- `master_repo` — `get_npc_by_id`, `update_encounter_notes`, `delete_member`,
  `get_master_campaign_note_by_id`.
- `maps_repo.get_map`; `wizard_engine.get_recommended_class` +
  `get_class_description`; `treasure_generator.format_coins` + `CR_BANDS`;
  `trap_generator.SEVERITY_LEVELS`; `profilo_tab._is_asi_level` + `_can_level_up`.
- `config/settings.py` — `get_xp_for_level`, `get_level_from_xp`,
  `POINT_BUY_COSTS`, `POINT_BUY_BUDGET`, `CURRENCIES`, `CURRENCY_NAMES`,
  `COLOR_BORDER_STRONG`, `COLOR_SLOT_USED`, `COLOR_NAV_TEXT`, `DB_NAME`.
- `game_data_loader` — 14 getter mai chiamati: `get_all_classes`, `get_all_races`,
  `get_race_names`, `get_all_backgrounds`, `get_mounts_and_vehicles`,
  `get_economy`, `get_equipment`, `get_trap_damage_dice`, `get_example_trap`,
  `get_disease`, `get_poison`, `get_madness_intro_text`, `get_magic_item`,
  `get_magic_item_names`, `get_npc_name_races`.
  ⚠︎ Alcuni sono "API pronta per una UI che non li usa": decidere caso per caso
  se **collegare** (es. `get_magic_item` serve al punto 3.4) o **togliere**.
- 8 variabili `ev_inner`/`ev2` non usate in `profilo_tab.py` (handler con
  parametro inutilizzato).

### File e asset morti

- **`mm_imgs/` = 306 MB, 152 PNG**: render di pagine del Manuale dei Mostri
  prodotti durante i batch di trascrizione del bestiario (`b12`…`b20`). Non
  servono più.
- `assets/fonts/` e `assets/backgrounds/` **vuote**;
  `assets/icons/dnd_logo.png` **mai referenziato** (l'header della Home usa un
  `ft.Text("D&D")`); `assets_dir` mai passato a `ft.run()` su desktop.
- `tools/parse_monsters.py`: estrattore basato su `pdfplumber`, metodo
  esplicitamente dichiarato inaffidabile per quel manuale e abbandonato in favore
  della lettura visiva delle pagine. Tenerlo è fuorviante per il futuro.
- **`CLAUDE.md`**: l'albero "Struttura File" è disallineato dalla realtà —
  mancano `core/update_checker.py`, `core/npc_generator.py`,
  `core/encounter_calculator.py`, `core/encounter_generator.py`,
  `core/trap_generator.py`, `core/treasure_generator.py`,
  `core/magic_item_generator.py`, `ui/widgets.py`, `ui/components/`, tutta
  `ui/views/master/`, la tabella `custom_abilities`, il polling di `HomeView`.

---

## Ordine di lavoro proposto

1. **Bug di regolamento B1–B7** — piccoli, isolati, alto valore percepito
   (l'app deve essere fedele al manuale).
2. **B10 (scroll/refresh) + B8/B9 (thread)** — sono i difetti che fanno sembrare
   l'app scattosa e fragile. B10 è anche prerequisito per godersi le animazioni
   della Fase C.
3. **Fase A del restyle** (tokens + primitive + `ft.Theme` completo) — abilita
   tutto il resto e riduce già di per sé l'aria "vecchia" (raggi, ombre, dialog).
4. **Pulizia dead code + `mm_imgs` + estrazione `creation_shared.py`** — da fare
   *prima* del restyle vero, così non si restyla due volte lo stesso codice
   duplicato.
5. **Fasi B–C–D del restyle**.
6. **Feature nuove**, in quest'ordine di rapporto valore/costo:
   dadi collegati alla scheda → iniziativa automatica lato master →
   concentrazione → condizioni → oggetti magici + sintonia lato giocatore →
   PE assegnati dopo l'incontro → (multiclasse, da valutare a parte).
