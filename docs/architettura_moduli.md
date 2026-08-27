# Architettura e Moduli Implementati

> Riferimento dettagliato di ogni modulo/file del progetto: cosa fa, quali funzioni/metodi espone, dati e
> convenzioni usate. Consultare prima di modificare un modulo esistente per capirne le convenzioni già stabilite
> (pattern già in uso, colonne DB, nomi metodi) invece di reinventarle o duplicarle.

## Moduli Implementati ✅

### `config/settings.py`
Costanti globali:
- **Palette Pergamena & Avventura** (tema chiaro): `COLOR_BG_PRIMARY="#f5f0e8"` (pergamena),
  `COLOR_BG_CARD="#ffffff"` (bianco puro), `COLOR_ACCENT_CRIMSON="#c0182c"` (rosso D&D),
  `COLOR_ACCENT_BLUE="#1848a0"` (blu reale — nota: `COLOR_ACCENT_GOLD` è alias legacy per BLUE)
- Testo scuro su sfondo chiaro: `COLOR_TEXT_TITLE="#0a0c1c"`, `COLOR_TEXT_PRIMARY="#1c1e2c"`, `COLOR_TEXT_SECONDARY="#3c4060"` (blu-ardesia, più visibile), `COLOR_TEXT_MUTED="#7880a0"`
- Sidebar: `COLOR_NAV_BG="#1a0808"` (quasi nero-rosso), `COLOR_NAV_TEXT="#f0e8e0"`, `COLOR_NAV_MUTED`
- Tab: `COLOR_BG_TAB_ACTIVE="#ffffff"`, `COLOR_BG_TAB_INACTIVE="#e8e1d4"`
- **`ASI_LEVELS`**: dict `{classe: set[int]}` — livelli ASI per classe; `ASI_LEVELS_DEFAULT={4,8,12,16,19}`
- `COLOR_ACCENT_RED` = alias per `COLOR_ACCENT_CRIMSON` (retrocompatibilità)
- `LEVEL_PROGRESSION`: dict `{livello: (xp_soglia, proficiency_bonus)}` da 1 a 20
- `get_modifier(score)` → `(score-10)//2`
- `get_modifier_str(score)` → stringa con segno (`"+2"`, `"-1"`)
- `get_proficiency_bonus(level)`, `get_level_from_xp(xp)`
- `char_prof_bonus(character)` → usa `proficiency_bonus_override` se > 0, altrimenti `get_proficiency_bonus(level)` — **usare questo ovunque si calcola il bonus competenza di un Character**
- `ABILITY_SCORES` (nomi italiani), `ABILITY_KEYS` (chiavi snake_case), `ABILITY_ABBR`
- `SKILLS` dict: 18 abilità → chiave caratteristica (es. `"Atletica": "str"`)
- `ALIGNMENTS`, `RACES` (lista piatta legacy), `CLASSES`
- `STANDARD_ARRAY`, `POINT_BUY_COSTS`, `POINT_BUY_BUDGET`
- ~~`RACE_DATA`~~ — **rimosso (2026-07-09)**, vedi `GameDataLoader.get_resolved_race()` in "Note Importanti"
- **`RACES_BASE`**: `dict[str, list[str]]` — razza base → lista sottorazze (per wizard); Draconide ha lista vuota (usa `DRACONIDE_ANCESTRIES`)
- **`DRACONIDE_ANCESTRIES`**: lista 10 tipi di drago (Bianco, Blu, Verde, Nero, Rosso, Oro, Argento, Rame, Ottone,
  Bronzo) — riutilizzata anche per la scelta del drago antenato dello Stregone (Discendenza Draconica)
- ~~`CLASS_SAVING_THROWS`~~, ~~`FIGHTING_STYLES`~~, ~~`TOTEM_ANIMALS`~~, ~~`LAND_TERRAINS`~~, ~~`MAGO_CANTRIPS`~~,
  ~~`METAMAGIC_OPTIONS`~~, ~~`PACT_BOONS`~~ — **rimosse (2026-07-09)**, stesso refactor di `RACE_DATA`, vedi
  `GameDataLoader.get_class_saving_throws()` / `get_fighting_styles()` / `get_totem_animals()` /
  `get_land_terrains()` / `get_mago_cantrips()` / `get_metamagic_options()` / `get_pact_boons()` in "Note
  Importanti"
- **`WEAPONS_SEMPLICI_MISCHIA`**, **`WEAPONS_SEMPLICI_DISTANZA`**, **`WEAPONS_GUERRA_MISCHIA`**, **`WEAPONS_GUERRA_DISTANZA`**: liste armi PHB (tabella p.149 IT)
- **`WEAPONS_BY_CATEGORY`**: `dict[str, list[str]]` — `"semplice"` / `"semplice_mischia"` / `"guerra"` / `"guerra_mischia"` → lista armi; usato dal weapon picker nell'equipment phase
- **`LANGUAGES`**: lista 15 lingue D&D 5e (PHB)
- **`ARTISAN_TOOLS`**, **`MUSICAL_INSTRUMENTS`**, **`GAMING_SETS`**: liste strumenti per categoria
- **`TOOL_CATEGORIES`**: `dict[str, list[str]]` — chiave JSON `from` → lista opzioni (es. `"strumenti_artigiani"` → 18 tipi)
- **`TOOL_CATEGORY_LABEL`**: `dict[str, str]` — chiave → label singola (usata quando `from` è lista di chiavi in JSON background)
- **`get_race_resource_defaults(race_name, subrace, level)`** → lista dict `{name, max_value, current_value, reset_on, display_type}` per risorse razziali
- **`get_race_display_traits(race_name, subrace)`** → dict `{resistances, advantage_saves, passive_traits}` per UI combattimento
- **`EXHAUSTION_LEVELS`**: `dict[int, str]` — 6 livelli di Indebolimento (Exhaustion) cumulativi, PHB IT. Usata da
  feature come Frenesia (Barbaro) e da incantesimi come Guarigione (rimuove 1 livello). Aggiunta il 2026-07-03, NON
  ancora collegata a un tracker UI (vedi TODO)
- **`resolve_dragonide_trait_texts(subrace, level, character)`** (2026-08-27) → dict `{"Discendenza Draconica":
  str, "Resistenza ai Danni": str, "Arma a Soffio": str}` — incrocia `subrace` (la
  discendenza scelta, es. "Blu") con `dragonide.json → traits[].options[]` e calcola i numeri reali del
  personaggio (dado danno per livello, CD = 8 + `char_prof_bonus()` + `get_modifier(con_score)`). `{}` se la
  discendenza non è impostata/non riconosciuta — il chiamante mostra in quel caso il testo generico del JSON.
  Usata da `profilo_tab.py::_build_razza()` (Tratti Razziali) e da `get_race_resource_description()` sotto.
- **`get_race_resource_description(character, resource_name)`** (2026-08-27) → `str` (descrizione) o `""` — testo
  di consultazione per una risorsa RAZZIALE mostrata in "Risorse di Classe" (Combattimento): Dragonide (riusa
  la funzione sopra), Mezzorco (Tenacia Implacabile), Tiefling (Eredità Infernale, 2 incantesimi innati),
  Elfo → sottorazza Elfo Oscuro/Drow (Magia Drow, 2 incantesimi innati) — per un incantesimo innato calcola
  anche CD/bonus attacco reali. Ritorna `""` per qualunque risorsa di CLASSE (Furia, Ki, ecc. — quelle restano
  consultabili solo via "Abilità di Classe"). Usata da `combattimento_tab.py::_resource_name_control()`.

### `data/models.py`
Dataclass `Character` con tutti i campi (identità, 6 punteggi, HP, combattimento,
stato turno, incantesimi, fisico, personalità, timestamp).
- `ca_bonus: int = 0` — bonus CA temporaneo (incantesimi, reazioni, ecc.)
- `initiative_bonus: int = 0` — bonus iniziativa aggiuntivo (talenti: Allerta +5, ecc.)
- `session_notes: str = ""` — appunti di sessione (auto-saved da EsplorazioneTab)
- `dragon_ancestry: str = ""` — tipo drago antenato Stregone (Discendenza Draconica)
- `fighting_style: str = ""` — stile di combattimento scelto (Guerriero Lv1, Paladino Lv2, Ranger Lv2)
- `totem_animal: str = ""` — animale totem Barbaro Percorso del Totem (Orso/Aquila/Lupo)
- `land_terrain: str = ""` — terreno Druido Cerchio della Terra (8 opzioni)
- `pact_boon: str = ""` — Warlock Dono del Patto: "Patto della Catena/Lama/Tomo"
- `darkvision_override: float = -1.0` (2026-08-27) — override manuale della Scurovisione in metri: -1 = non
  impostato (usa `GameDataLoader.get_resolved_race().darkvision`), 0 = "Nessuna" esplicito (diverso dal
  sentinel). `character_repo.update_darkvision_override()`; UI in `esplorazione_tab.py::_on_edit_darkvision()`,
  letto anche da `profilo_tab.py::_build_razza()` — unici 2 render site, entrambi sincronizzati.

`Weapon`:
- `magic_damages: str = "[]"` — JSON array danni magici extra
- `weapon_category: str = ""`, `proficiency_override: bool = False`, `finesse_ability: str = ""`,
  `attack_total_override: bool = False`, `attack_override_value: int = 0` — calcolo automatico tiro per
  colpire/competenza (2026-07-17, vedi `core/weapon_calculator.py`)

`InventoryItem`:
- `ca_value: int = 0`, `armor_type: str = ""`, `effects: str = ""`

Entità correlate: `CharacterProficiency`, `Weapon`, `InventoryItem`, `Currency`,
`SpellSlot`, `KnownSpell`, `DiaryEntry`, `GameMap`.

### `data/database.py`
- DB path: `~/.dnd_companion/dnd_companion.db`
- `get_image_library_path()` → `~/dnd_image_library/` (picker foto in web mode, 2026-07-12)
- `get_character_exports_path()` → `~/dnd_character_exports/` (picker import in web mode, 2026-07-24 — vedi TODO "Import/Export personaggio")
- 11 tabelle: `characters`, `character_proficiencies`, `weapons`, `inventory_items`,
  `currencies`, `spell_slots`, `known_spells`, `diary_entries`, `game_maps`,
  `campaign_notes`, `creature_entries` (le ultime due mancavano da questa lista —
  vedi sezioni dedicate `DiaryView` e `CreatureEntry` più sotto)
- FK CASCADE su tutte le tabelle figlio
- WAL mode attivato
- `get_connection()` ritorna una **`_ResilientConnection`** (sottoclasse di `sqlite3.Connection`, passata via
  `factory=`) e apre con `timeout=_SQLITE_TIMEOUT_S` (5s) — 2026-08-17. `execute`/`executemany`/`commit` sono
  avvolte: al primo `"database is locked"` forzano un `gc.collect()` e riprovano **una** volta, poi propagano
  l'errore come prima. **Perché**: il pattern dominante di questo progetto è `conn.close()` come ultima riga del
  blocco `try`, non in un `finally` — **167 funzioni**, contate con uno scan AST. Se una query solleva, quella
  connessione non viene mai chiusa, e nemmeno liberata dal refcount: l'eccezione crea un ciclo
  (eccezione → traceback → frame → locale `conn`) che solo il gc generazionale rompe. Nel frattempo la
  connessione orfana trattiene la transazione di scrittura fallita e il lock del file, e **ogni scrittura
  successiva del processo** fallisce con "database is locked" fino al riavvio dell'app — è la causa radice del
  bug del round 5 del Multiplayer (vedi `changelog_storico.md`, "round 5 — CHIUSO"). Il ritentativo è sicuro:
  una statement che non ha ottenuto il lock non ha applicato niente.
  ⚠️ Questa è una **difesa in profondità, non la difesa principale**. Le 165 funzioni sono state tutte
  convertite a `try/finally` nella stessa giornata, quindi oggi non esiste più nessun punto noto che abbandoni
  una connessione e questo ritentativo non dovrebbe mai scattare — **se il suo `logger.warning` appare nei log,
  c'è una connessione abbandonata da trovare.**
- 🔒 **Invariante, verificata da `test_connessioni_db.py`** (2026-08-17): ogni funzione che apre
  `get_connection()` deve chiudere la connessione in un `finally` (o gestirla con un `with`), mai come ultima
  riga del blocco `try`. La forma corretta:
  ```python
  conn = None
  try:
      conn = get_connection()
      ...
      return risultato
  except Exception as e:
      logger.error(f"Errore f(): {e}")
      return fallback
  finally:
      if conn is not None:
          conn.close()
  ```
  `conn = None` prima del `try` non è decorativo: se `get_connection()` stessa solleva, senza quello il
  `finally` darebbe `NameError` mascherando l'errore vero. È corretto anche il pattern annidato già usato da
  `character_export.py`/`settings_repo.py` (`try: conn = ...; try: ... finally: conn.close()`).
  Il test analizza l'AST di **tutto** il codebase (per-funzione **e** per-`try`, così da intercettare anche una
  funzione che apre due connessioni e ne protegge una sola) e fallisce elencando le funzioni non conformi —
  ha una allowlist di due voci, `get_connection`/`_open_connection`, le sole a cui spetta restituire una
  connessione aperta.
- `_migrate(conn)` aggiunge via `ALTER TABLE` (idempotente):
  - `characters`: `image_data`, `ca_bonus`, `proficiency_bonus_override`, `session_notes`, `dragon_ancestry`,
    `fighting_style`, `totem_animal`, `land_terrain`, `pact_boon`, `initiative_bonus INTEGER DEFAULT 0`
  - `character_proficiencies`: `bonus_data TEXT DEFAULT NULL`, `level_obtained INTEGER DEFAULT 0`
  - `weapons.magic_damages TEXT`
  - `weapons`: `weapon_category`, `proficiency_override`, `finesse_ability`, `attack_total_override`, `attack_override_value` (2026-07-17)
  - `inventory_items`: `ca_value`, `armor_type`, `effects`
  - `game_maps`: `image_data`, `notes`

### `data/repositories/character_repo.py`
- `get_all()` → lista ordinata per `updated_at DESC`
- `get_by_id(id)` → `Character | None`
- `create(character)` → inserisce + inizializza currencies + 9 spell_slot (livelli 1-9)
- `update(character)` → aggiornamento completo (include `ca_bonus`, `session_notes`)
- `delete(character_id)` → CASCADE automatico
- `get_proficiencies(character_id)` → `list[CharacterProficiency]`
- `update_hp(character_id, hp_current, hp_temp=None)` → aggiornamento rapido
- `update_turn_state(character_id, action, bonus, reaction, movement, prev_state)`
- `update_ca_bonus(character_id, ca_bonus)` → aggiorna solo `ca_bonus` su characters
- `update_session_notes(character_id, notes)` → aggiorna solo `session_notes`
- `calculate_and_update_ca(character_id)` → legge oggetti equipaggiati categoria "armor",
  applica formula PHB (leggera=ca_value+DEX, media=ca_value+min(DEX,2), pesante=ca_value,
  scudo=somma ca_value), aggiorna `characters.ac`, ritorna nuovo valore
- `_save_single_proficiency(character_id, type, name, is_expert=False, bonus_data=None, level_obtained=0)` → per
  wizard/level-up; `bonus_data` è JSON stringa con i bonus applicati (usato per reversione), `level_obtained` è il
  livello a cui è stato acquisito
- `set_expertise(character_id, skill_names)` → imposta `is_expert=True` su competenze esistenti (Perizia Ladro/Bardo)
- `remove_feat_with_bonuses(character_id, feat_name)` → legge `bonus_data` del feat, inverte tutti i bonus
  applicati (ability scores, `initiative_bonus`, `speed`) in una transazione atomica, poi elimina la riga
- `undo_level(character_id, level_removed)` → trova tutti i `feat` e `asi_record` con `level_obtained ==
  level_removed`, inverte i loro `bonus_data` in un unico UPDATE, poi elimina le righe; usato dal level-down in
  ProfiloTab
- **Armi CRUD**: `get_weapons(id, equipped_only)`, `create_weapon(...)`, `update_weapon(...)`, `delete_weapon(id)`
  - Param aggiuntivo `magic_damages: str = "[]"` — JSON `[{"dice":"1d6","type":"Fuoco","note":""}]`
- **Inventario CRUD**: `get_inventory(id)`, `create_inventory_item(...)`, `update_inventory_item(...)`, `delete_inventory_item(id)`
  - Params aggiuntivi: `ca_value: int = 0`, `armor_type: str = ""`, `effects: str = ""`
- **Valute**: `get_currencies(id)`, `update_currencies(id, copper, silver, electrum, gold, platinum)`
  - ⚠️ Colonne DB: `copper/silver/electrum/gold/platinum` (NON `cp/sp/ep/gp/pp`)
- **Diario CRUD**: `get_diary_entries(id)`, `create_diary_entry(...)`, `update_diary_entry(...)`, `delete_diary_entry(id)`
  - ⚠️ sqlite3.Row NON ha `.get()` → usare sempre `r["column_name"]` diretto
- `update_exhaustion_level(character_id, value)` → clamp 0-6, aggiorna `characters.exhaustion_level` (2026-07-16)
- `update_frenzy_state(character_id, active)` / `end_frenzy_rage(character_id, current_exhaustion)` (2026-07-19) →
  Barbaro Cammino del Berserker: dichiara/annulla la Frenesia per l'ira in corso; `end_frenzy_rage` è atomica
  (unica connessione), azzera `frenzy_active` e applica +1 Indebolimento (clamp 6) nello stesso statement — vedi
  `Character.frenzy_active` e nota "Frenesia automatica" più sotto
- `apply_class_base_proficiencies(character_id, class_name)` (2026-07-16) → applica
  `armor_proficiencies`/`weapon_proficiencies` della CLASSE BASE (letti da `classes/*.json`, mai da sottoclasse)
  come `character_proficiencies` tipo `"armor"`/`"weapon"`; riusa `classify_bonus_proficiency_entries()` +
  `apply_subclass_bonus_proficiencies()` (dedup idempotente) invece di reimplementare la logica. Chiamata sia alla
  creazione (`wizard_view.py`/`manual_form.py`, subito dopo il salvataggio dei bonus di sottoclasse) sia come
  self-healing ad ogni apertura di `EsplorazioneTab` (backfilla i personaggi creati prima del fix)
- `_classify_bonus_proficiency_type(entry_name)` esteso (2026-07-16): un nome che risolve in
  `game_data.get_weapon(entry_name)` (arma specifica, es. "Stocco", non una categoria) è classificato `"weapon"`
  invece di ricadere su `"tool"` per default

**Multiclasse** (2026-08-12, backend — vedi `dnd_app/docs/multiclasse_design.md` §8 per lo stato esatto, NESSUNA
UI Flet scritta in questo giro):
- Nuova tabella `character_classes` (`data/database.py`) — una riga per classe posseduta, `is_primary=1` per
  quella di 1° livello. `characters.class_name`/`subclass`/`level` restano SEMPRE la classe primaria e il
  livello TOTALE, mai una stringa composita — invariati per un personaggio a classe singola.
- `get_character_classes`/`get_primary_character_class`/`character_has_class`/`get_class_display_string`/
  `add_character_class`/`set_character_class_level`/`remove_character_class`/`sync_character_total_level`
- `check_multiclass_prerequisites(character, new_class_name)` → advisory (mai un blocco duro), controlla sia le
  classi già possedute sia quella nuova contro `game_data.get_multiclass_prerequisites()`
- `apply_multiclass_proficiencies`/`resolve_multiclass_choice_options`/`apply_multiclass_proficiency_choices` →
  competenze RIDOTTE da multiclasse (PHB p.164), MAI quelle complete di `apply_class_base_proficiencies()`; riusa
  `classify_bonus_proficiency_entries()`/`apply_subclass_bonus_proficiencies()` esistenti
- `init_class_resources()` **modificata**: quando `get_character_classes()` ha più di una riga, i default sono
  l'UNIONE su tutte le classi possedute (ciascuna col proprio livello) invece della sola `class_name`/`level`
  passati — prima di questo fix, chiamarla una volta per classe avrebbe cancellato le risorse delle altre
  (strategia "replace totale per nome"). Risorse omonime tra classi diverse (es. Incanalare Divinità di
  Chierico/Paladino) tengono il valore più alto, non sommato (PHB: "non ottiene un utilizzo aggiuntivo").
- `sync_multiclass_spell_slots(character_id)` (nuova, usata solo se >1 classe — un personaggio a classe singola
  passa sempre da `auto_init_spell_slots()`, invariata): somma i livelli "full" per intero e "half" dimezzati
  (arrotondati per difetto) di tutte le classi (Warlock ESCLUSO), guarda `get_multiclass_spell_slot_table()`
  (= `full_caster`, confermato identico dal PHB). LIMITE NOTO: un personaggio con Warlock + un'altra classe da
  incantatore non ha ancora i suoi slot del Patto tracciati separatamente (schema `spell_slots` senza colonna
  pool) — logga un warning esplicito, non scrive un numero silenziosamente sbagliato.
- `data/game_data/multiclass_data.json` (nuovo) + `GameDataLoader.get_multiclass_prerequisites()`/
  `get_multiclass_proficiency_entries()`/`get_multiclass_spell_slot_table()` — le 2 tabelle PHB (prerequisiti
  p.163, competenze p.164) lette visivamente dal PDF italiano.
- `ui/views/character_sheet/profilo_tab.py::_on_level_up_click` — fix mirato (non un riscritto): `new_level`
  ora è esplicitamente il livello della classe PRIMARIA (da `character_classes`, non più `c.level+1` che per un
  multiclasse avrebbe sovrascritto il totale), `new_total_level` separato per il bonus competenza. A fine
  funzione risincronizza `character_classes`/`characters.level`. Zero comportamento diverso per un personaggio a
  classe singola (28 file di regressione pre-esistenti invariati).
- `update_darkvision_override(character_id, value)` (2026-08-27) — stesso pattern di
  `update_carry_capacity_override()`: `UPDATE characters SET darkvision_override=?`. -1 = non impostato (usa la
  razza), 0 = "Nessuna" esplicito. Vedi `Character.darkvision_override` sopra e `_add_column` in
  `data/database.py::_migrate()`.

### `core/wizard_engine.py`
- `WizardEngine`: accumula punteggi da risposte, calcola raccomandazione
- `record_answer(question_id, option_ids)` → aggiorna class_scores + bg_scores + alignment
- `undo_answer(question_id)` → sottrae il contributo (per tasto "indietro")
- `get_top_classes(n)`, `get_recommended_class()`, `get_recommended_background()`
- `get_recommended_race(class_name)`, `get_alignment_string()`
- `get_suggested_stat_assignment(class_name)` → distribuzione Standard Array per classe
- `build_character(...)` → costruisce `Character` Lv.1 con:
  - HP = max(dado vita) + mod CON (dopo bonus razziali)
  - Bonus razziali da `game_data.get_resolved_race(race, subrace)["ability_bonuses"]` applicati allo Standard Array (solo JSON, vedi "Note Importanti" 2026-07-09)
  - Velocità dalla razza (PHB, non sempre 9 m)

### `data/game_data/wizard_data.py`
- 9 domande (`WIZARD_QUESTIONS`) con sistema di scoring per 12 classi
- ~~13 background (`BACKGROUNDS`)~~ — **rimosso il 2026-07-10**, dataset divergente dal manuale eliminato durante
  l'audit background; unica fonte ora `data/game_data/backgrounds/*.json` via
  `GameDataLoader.get_background()`/`get_background_names()` (vedi Checklist Revisione Dati PHB → Background)
- `CLASS_PRIMARY_STATS`: mapping classe → stat primarie per assegnazione array
- `CLASS_SUGGESTED_RACES`: mapping classe → razze consigliate
- `CLASS_DESCRIPTIONS`: descrizione breve per schermata raccomandazione

### `ui/design.py` — Design system (Fase A/B/C del restyle)
Token e primitive riusabili — vedi `restyle_design.md` per il racconto completo
del restyle; qui solo un indice rapido delle primitive con firma stabile,
aggiornato quando se ne aggiunge una nuova (15 in uso a fine Fase E, +1 sotto).

- Scale: `Space` (XS4..XXL32), `Radius` (SM8..PILL999), `Duration`, `Font`, `Size`
- `Palette` (dataclass) con istanze `LIGHT`/`DARK`, contrasti WCAG calcolati — `T()` ritorna
  quella attiva (`set_mode("light"|"dark")`), non una costante: serve al tema scuro
- `surface()`, `card()`, `section()`, `pill()`, `chip()`, `hp_bar()`, `slot_dots()`/`dot_button()`,
  `dialog_title()`, `field_style()`, `empty_state()`, `difficulty_color()`, `CURRENCY_COLORS`, `Chrome`
- **`collapsible_section(title_text, content_builder, *, expanded=False, accent=None, level=1,
  header_subtitle=None, on_toggle=None, alt=False)`** (2026-08-15, richiesta Davide: "voglio usare
  di più la tendina che collassa... quando ci sono descrizioni lunghe") — sezione con header
  cliccabile (barra accento + label, chevron EXPAND_MORE/EXPAND_LESS) che mostra/nasconde
  `content_builder()`. **Stateless**: nessuno stato interno (le view Flet si ricostruiscono da
  zero), lo stato aperto/chiuso resta un attributo di istanza nel chiamante, passato con
  `expanded=` e restituito via `on_toggle(new_state)` — il chiamante decide se sostituire il
  controllo in place (`self.controls[idx] = ...`, come `master_view.py::_build_tools_panel()`) o
  aggiornare un `ft.Ref` locale (come `ui/components/monster_picker.py::build_stat_block_column()`,
  funzione pura senza `self`). `content_builder` è una funzione, non un controllo già costruito:
  se la sezione parte chiusa, il contenuto pesante non viene costruito finché non si apre.
  Sostituisce la logica bespoke del pannello "STRUMENTI MASTER"; usata anche per le sezioni
  facoltative della scheda mostro e le note NPC lunghe (`master_npc_list_view.py`). Dettaglio
  completo in `changelog_storico.md`.

### `ui/theme.py`
Helper Flet: `get_theme()`, `title_text()`, `body_text()`, `muted_text()`,
`label_text()`, `fantasy_card()`, `section_header()`, `primary_button()`,
`ghost_button()`, `danger_button()`.

### `ui/app.py` — `DnDApp`
Router principale. ThemeMode.LIGHT (tema marmo chiaro).
- `_show_home()` → `HomeView`
- `_show_wizard()` → `WizardView`
- `_show_manual_form()` → `ManualCreationForm`
- `_on_character_selected(id)` → `_show_main_layout()`
- `_show_main_layout()`: sidebar custom (`ft.Column` di `ft.Container`, NON `NavigationRail`) + area contenuto marmo
- Sidebar: avatar circolare del personaggio corrente (foto base64 o scudo con iniziali)
- Sezioni navbar: `sheet`, `spells`, `diary`, `maps`, `dice` — tutte attive ✅
- Tasto "Cambia personaggio" in fondo alla sidebar
- `_data_uri(b64)` helper: rileva mime dai magic bytes → `data:{mime};base64,{b64}`

### `ui/views/home_view.py` — `HomeView`
- Header: logo "D&D" come `ft.Text` bold rosso 52pt (NON immagine PNG — fragile)
- Card per ogni personaggio: avatar (foto via data URI o placeholder), nome, livello, classe, razza, background
- Avatar card: priorità `image_data` (base64 DB) > `image_path` (legacy) > icona placeholder
- Tasto play (→ `on_select`) e tasto elimina (con dialog di conferma)
- Stato vuoto con CTA wizard e manuale
- Dialog scelta creazione (wizard vs manuale)
- `refresh()`: ricarica dal DB
- `_data_uri(b64)` helper locale per display immagini
- **Export/Import personaggio** (2026-07-24, vedi TODO "Import/Export personaggio" per il changelog completo):
  pulsante "Esporta" (icona `IOS_SHARE`) su ogni card; pulsante "Importa" in header e stato vuoto; Desktop → dialog
  nativi (variante "save" del subprocess dialog, prima esisteva solo "open"); Web → export con download reale
  (`assets_dir` + bottone "Scarica" via `url=`, vedi TODO), import via `ui/character_transfer.py` (cartella
  `get_character_exports_path()`, popolata via SSH — resta bloccato dal bug upstream FilePicker/UrlLauncher in web
  mode, nessuna soluzione lato app possibile); Mobile → `await picker.save_file()`/`pick_files()` (API corretta, il
  vecchio `FilePicker.on_result` — inesistente in flet==0.85.3 — non viene più usato per questa feature; non ancora
  testato su un vero dispositivo, vedi TODO). Import mostra un dialog di conflitto a 3 scelte (Sovrascrivi/Crea
  copia/Annulla) quando l'id del personaggio nel file esiste già sul dispositivo.
- **Home raggruppata per mondo** (Multiplayer passo 3, 2026-08-05, vedi anche `core/character_instances.py` più
  sotto): `did_mount()` avvia `page.run_task(self._init_identity)` che risolve `self.device_id` via
  `ui/device_identity.py::resolve_device_id()` e forza un refresh appena pronto. `_partition_characters(characters)`
  separa i personaggi locali (`world_id == ""`) dalle istanze possedute da QUESTO dispositivo, raggruppate per
  `world_id` — filtro sempre su `owner_device_id == self.device_id`, mai solo su `world_id`, perché nello stesso
  DB (web mode multi-scheda) possono comparire istanze di ALTRI dispositivi che non devono mai apparire qui.
  `refresh()`: se non ci sono gruppi (nessuna istanza posseduta, o identità non ancora risolta) renderizza la
  lista piatta di sempre — zero cambiamento visivo per chi non usa il Multiplayer; altrimenti una sezione per
  mondo (ordine di `world_repo.get_worlds_for_device()`, il più recente per primo) più una sezione "Non in un
  mondo" per i locali, tramite l'helper `_section_label()`. `_character_card()` ora accetta
  `available_worlds`/`is_instance`: un personaggio locale con almeno un mondo disponibile mostra l'azione
  "Aggiungi a un mondo" (`_open_add_to_world_dialog`, dropdown mondo + porta com'è/ricomincia dal 1° livello →
  `core.character_instances.create_or_resume_instance()`); un'istanza mostra invece "Aggiorna il mio foglio"
  (`_open_refresh_dialog`, riepilogo diff via `ci.preview_refresh()` + conferma → `ci.apply_refresh()`) — mai
  entrambe sulla stessa card. `_list_signature()` include ora anche `world_id`/`owner_device_id`.
- **Sincronizzazione in background delle istanze remote** (2026-08-12, vedi `multiplayer_design.md` §9.5):
  `_start_world_sync()`/`_stop_world_sync()` — secondo `BackgroundSyncLoop` (il primo è `_start_polling()`/
  `_poll_loop()`, SOLO multi-scheda web sullo stesso DB, non toccato), gira su qualunque piattaforma. Ad ogni giro,
  `_my_remote_world_ids()` trova i mondi con un'istanza propria che questo dispositivo NON ospita, poi
  `world_sync.resolve_backend_for_world`/`sync_replica` per ciascuno. `self.backend`/`self._remote_backends` sono
  lo stesso stato persistente (cache di connessione) di `WorldsView`. `_list_signature()` include ora anche
  `world_instance_archived`. `_partition_characters()` ritorna una TERZA lista, `removed_from_world` (istanze con
  `world_instance_archived=True`, es. dopo "Rimuovi dal mondo" lato master) — sezione dedicata "Rimossi dai mondi"
  in `refresh()`, card senza "Aggiorna il mio foglio"/"Aggiungi a un mondo" (Gioca/Esporta/Elimina restano),
  `world_id` mai azzerato.

### `ui/views/creation_wizard/manual_form.py` — `ManualCreationForm` (RISCRITTO ✅)
**Flusso in 5 fasi** — shell identico al wizard (progress bar, `_set_content()`, `_on_back()`):
1. **Identità** — nome, giocatore, classe (Dropdown), razza, background, allineamento. Alla conferma: inizializza
   Standard Array ottimale per la classe via `_stat_engine.get_suggested_stat_assignment()`.
2. **Punteggi** — **Sottorazza / Discendenza Draconica** (dropdown, solo se la razza ne ha una — spostata qui da
   "Scelte" il 2026-07-10, vedi Note Importanti) + 6 Dropdown con valori Standard Array, riarrangiabili
   liberamente. Preview HP in tempo reale (dado vita + mod CON). Anteprima bonus razziali **dinamica**: si aggiorna
   subito quando si cambia sottorazza, PRIMA che il giocatore assegni i punteggi (applicati comunque solo al
   salvataggio).
3. **Scelte** — stesso sistema del wizard fase 3, MENO la sottorazza (ora in fase 2): sottoclasse lv1, tipo drago
   Stregone, stile combattimento Guerriero, extra razziali (Mezzelfo flex+abilità, Alto Elfo trucchetto, Umano
   lingua), abilità di classe (N checkbox), Perizia Ladro Lv1 (2 abilità), **Trucchetti e Incantesimi Iniziali** (N
   dropdown trucchetti + M dropdown incantesimi di 1° livello per le classi "know", + N dropdown incantesimi
   preparati iniziali per Chierico/Druido/Paladino, + 6 dropdown Libro degli Incantesimi per il Mago — vedi Note
   Importanti 2026-07-10 e 2026-07-11), lingue e strumenti background.
4. **Equipaggiamento** — oggetti fissi (checkbox), scelte A/B (RadioGroup), nota equipaggiamento background (auto-aggiunto).
5. **Conferma** — chip riepilogo (HP, CA, velocità, 6 stat derivati), tasto "Crea personaggio". Salvataggio con `_stat_engine.build_character()` + proficienze + inventario (stesso pattern del wizard).

**Valori derivati automaticamente**: HP max, CA, velocità, tiri salvezza di classe, abilità da background, tratti personalità casuali da PHB.
**Personalità e aspetto fisico**: compilabili dopo dalla scheda personaggio — non richiesti al momento della creazione.
**Dipendenze**: `WizardEngine` (singleton `_stat_engine`), `GameDataLoader` (singleton `_loader`), stesse costanti del wizard.

Salva via `character_repo.create()` + `_save_single_proficiency()` + `set_expertise()` + `upsert_known_spell()` + `create_inventory_item()`.

### `ui/views/feats_view.py` — `FeatsView`
**Eredita da `ft.ListView`** (expand=True). Sezione di riferimento indipendente dal personaggio.
- Lista scrollabile di tutti i 42 talenti PHB caricati da `feats.json`, ordinati alfabeticamente
- Ogni card mostra: nome, prerequisito (con 🔒), bonus caratteristica (se presente), prima frase della descrizione
- Click su card → `AlertDialog` con descrizione completa, prerequisito e bonus caratteristica
- Se `feats.json` vuoto → empty state con istruzione per popolarlo
- Accessibile dalla sidebar come 6° voce "Talenti" con icona `MILITARY_TECH`

### `ui/components/map_drawing_canvas.py` — `MapDrawingCanvas` (2026-08-25)
Componente condiviso che racchiude l'intera modalità di disegno mappe: area disegno,
toolbar, gomma, undo, storia. Estratto per unificare due implementazioni quasi-duplicate —
quella storica lato giocatore (`maps_view.py`) e la reimplementazione ridotta lato Master
(`world_view.py`, che non aveva la gomma "Libera"). Dettaglio completo del refactor e dei
bug corretti in `changelog_storico.md`, voce "Riprogettazione della modalità di disegno
mappe" (2026-08-25).

- **Costruttore**: `MapDrawingCanvas(gm, on_batch, can_manage, page=...)`. `on_batch`
  astrae la persistenza — il giocatore passa una closure verso il rewrite locale delle
  annotazioni, il Master verso `CMD_MAP_DRAW`. `can_manage=False` (giocatore in sola
  lettura su una mappa condivisa) non monta la toolbar e tratta ogni gesto come pan/zoom,
  mai disegno. `page` abilita `_safe_update()`, un fallback a `page.update()` se
  `ctrl.update()` solleva `RuntimeError`.
- **`build_draw_area(is_fs)`**: `ft.Stack([img_layer, canvas], expand=True,
  fit=ft.StackFit.EXPAND)` — il `fit=EXPAND` esplicito è **necessario**: `ft.Stack` di
  default usa `StackFit.LOOSE`, che non forza i figli `expand=True` a riempire lo Stack e
  causava disallineamento tra immagine e tratti disegnati (vedi changelog per l'analisi
  completa). Riquadro di disegno tracciato via `on_size_change`, SEPARATO per pannello
  inline e schermo intero (`self._box_size[is_fs]`), come nella vecchia implementazione.
- **Un solo `ft.InteractiveViewer` per pannello, montato una volta e mai più sostituito**
  (stato finale dopo QUATTRO giri di fix, l'ultimo il 2026-08-26 — dettaglio completo,
  incluso il perché dei primi tre tentativi sbagliati, in `changelog_storico.md`):
  `build_draw_area()` restituisce direttamente quell'`InteractiveViewer`, con
  `content=stack` e `scale_enabled=True` SEMPRE (il pizzico zoomma in ogni modalità);
  `pan_enabled` è l'unica proprietà che cambia con la modalità (`True` solo in "Sposta", o
  sempre in sola lettura). Non esiste più un `ft.GestureDetector` separato per
  disegno/gomma: quegli eventi arrivano da `on_interaction_start/update/end`, gli STESSI
  `onScaleStart/Update/End` che `InteractiveViewer` cabla comunque incondizionatamente
  (**causa REALE** del giro precedente, confermata leggendo il sorgente ufficiale di
  Flutter, `packages/flutter/lib/src/widgets/interactive_viewer.dart::build()`, non per
  analogia) — un solo `GestureRecognizer` per pannello, per costruzione nessuna gara
  nell'arena possibile con nient'altro. `_on_interaction_start()` decide, una volta sola
  per gesto, se si tratta di disegno/gomma (`pointer_count == 1`, modalità Penna/Gomma,
  riquadro noto) o di pan/zoom (tutto il resto, incluso qualunque gesto a 2+ dita, in
  QUALUNQUE modalità). Poiché Flet non espone la Matrix4 interna come proprietà leggibile,
  `_view_scale`/`_view_offset` ne tengono uno specchio Python, aggiornato con la STESSA
  formula di `interactive_viewer.dart::_onScaleUpdate` (il punto di contenuto sotto il
  fuoco del gesto resta fisso sotto il fuoco per tutta la sua durata) — usato SOLO per
  convertire un tocco singolo da coordinate di schermo a coordinate di contenuto
  (`_to_scene()`); il rendering resta comunque quello nativo di Flutter. Vedi
  `regole_flet_api.md` per la regola generale riusabile. Compromesso nuovo rispetto ai giri
  precedenti: lo zoom impostato in una modalità sopravvive al passaggio a un'altra (stesso
  widget, mai ricreato) e il pizzico funziona SEMPRE, anche mentre si disegna.
- **Cache dei tratti già salvati durante un trascinamento** (`_committed_shapes()`/
  `self._static_shapes[is_fs]`, 2026-08-26): `_redraw_canvas()` ricalcolava da zero TUTTI i
  tratti già salvati (denormalizzazione + `cv.Path`) ad ogni singolo
  `on_interaction_update`, costo O(punti totali sulla mappa) per fotogramma.
  `_committed_shapes(is_fs)` calcola quella lista una volta e la mette in cache;
  `_redraw_canvas()` la invalida sempre (usato ovunque i tratti POSSONO essere cambiati:
  resize, cambio modalità, fine tratto, gomma, annulla, cancella tutto),
  `_redraw_live_stroke()` (SOLO durante un trascinamento penna in corso) la riusa e
  ricalcola solo il tratto in corso — un miglioramento di prestazioni reale di per sé,
  anche se NON era la causa del ritardo di disegno touch (esclusa da Davide testando a
  mappa vuota; la causa reale era la gesture arena, vedi il punto sopra).
- **Pulsanti pillola** (`_mbtn` per Penna/Gomma/Sposta, `_esbtn` per le sotto-modalità
  gomma Tratto/Libera): usano `animate_scale=ft.Animation(...)` (`AnimatedScale`), MAI
  `animate=` (`AnimatedContainer`) — quest'ultimo, combinato con Icon+Text in una Row,
  taglia/sovrappone le lettere minuscole del testo. Colore impostato al costruttore, non
  mutato dopo.
- **Undo multi-azione**: `self._history: list[str]` — snapshot JSON dell'intera
  `self._strokes` (tetto 20 voci), presi prima di ogni azione distruttiva (fine tratto
  penna, un gesto di cancellazione gomma, cancella tutto, pulizia tratti legacy).
  `undo()` ripristina l'ultimo snapshot per intero — non un "pop" dell'ultimo tratto:
  copre anche il caso "ho cancellato per sbaglio con la gomma".
- **Responsive**: `_TOP_ROW_STACK_BP=950px` (sotto: i pallini colore scendono su riga
  propria) e `_TOP_ROW_COMPACT_BP=650px` (sotto: pulsanti modalità/Annulla/Cancella tutto
  passano a sola icona con tooltip). Mai `wrap=True` — vedi la regola generale
  "`wrap=True` con figlio `expand=True` crasha silenziosamente" in `regole_flet_api.md`.
- **Gomma** (`_eraser_sub: str = "stroke" | "pixel"`), ora paritaria su entrambi i
  chiamanti:
  - **Tratto** (`"stroke"`): rimuove interi stroke che il cursore tocca.
  - **Libera** (`"pixel"`): taglia geometricamente i segmenti — `_circle_segment_ts()`
    (intersezione linea-cerchio) + `_split_stroke_by_circle()`.
- **Regola critica — BlendMode.CLEAR non funziona**: Flutter `CustomPaint` senza
  `saveLayer` rende trasparente → nero. NON usare mai `BlendMode.CLEAR` per la gomma. La
  cancellazione avviene modificando `_strokes` in memoria, non ridisegnando pixel.
- **Fullscreen** (`page.overlay`): stack/toolbar proprio, canvas indipendente — stesso
  principio del riquadro separato di cui sopra. `_update_all_canvases()` ridisegna
  ENTRAMBI i canvas dalla stessa `self._strokes`, ciascuno scalato al proprio riquadro,
  non "sincronizzato" in pixel.
- **Persistenza**: `_strokes` serializzata come JSON in `game_maps.annotations` (colonna
  `TEXT`). Formato stroke: `{"type": "stroke", "color": "#hex", "width": float, "points":
  [[x,y], ...]}` — **`points` sono frazioni [0,1] del riquadro con cui si è disegnato**
  (2026-08-12, non più pixel assoluti). Normalizzazione/denormalizzazione in
  `ui/canvas_geometry.py` (puro, no Flet). `ui/canvas_geometry.py::looks_normalized()` usa
  un margine di tolleranza (`_NORM_MARGIN = 1.0`, aggiunto 2026-08-25) per riconoscere
  anche punti di lieve sconfinamento del letterbox durante il disegno freehand come già
  normalizzati, distinti dai tratti VERAMENTE legacy pre-2026-08-12 (pixel assoluti, mai
  migrati, riconosciuti/lasciati invariati per euristica).
- **`_PEN_COLORS`/`_data_uri()`**: qui, non più in `maps_view.py` — `world_view.py` e
  `ui/components/npc_dossier.py` li importano da questo modulo.
- **Strumenti rimossi**: testo sulla mappa (rimosso — non funzionava in modo
  soddisfacente con Flet 0.85.3).

### `ui/views/maps_view.py` — `MapsView`
**Eredita da `ft.Column`** (expand=True).

**Lista mappe**: card con miniatura base64 (o placeholder), nome, note, contatore annotazioni. CRUD tramite dialog
(crea/modifica/elimina). Upload immagine cross-platform: `ft.FilePicker` su mobile, subprocess nativo
(osascript/PowerShell/zenity) su desktop.

**Dettaglio mappa** (dopo click card o fullscreen): area di disegno e toolbar delegate a
`self._canvas: MapDrawingCanvas` (`ui/components/map_drawing_canvas.py`, vedi sopra) —
`_build_detail_panel()`/`_open_fullscreen()` mantengono solo header/note/layout esterno,
specifici di questa view.

**Type stub workaround** (Flet 0.85.3):
- `getattr(container.content, "controls", [])` invece di `container.content.controls` (Control non ha .controls)
- `cast(Any, fp).on_result = fn` + `cast(Any, fp).pick_files(...)` per FilePicker
- `def on_result(ev: Any):` — `ft.FilePickerResultEvent` non nei type stub

---

### `ui/views/character_sheet/diario_tab.py` — `DiarioTab`
**Eredita da `ft.ListView`**.
- Header con pulsante "Nuova Voce" (bottone rosso crimson)
- Lista voci: card con bordo sinistro rosso, titolo bold, data sessione, anteprima testo (prime 2 righe)
- Tasti modifica (matita) ed elimina (cestino) su ogni card
- Stato vuoto con icona MENU_BOOK_OUTLINED e CTA
- Dialog crea/modifica: titolo + data/sessione (testo libero, es. «Sessione 3») + contenuto multiline
- Dialog conferma eliminazione
- CRUD completo via `character_repo`: `get_diary_entries`, `create_diary_entry`, `update_diary_entry`, `delete_diary_entry`
- Pattern `did_mount` + `_page: ft.Page | None` per dialogs; guard `if page is None: return` in tutte le nested def

### `ui/views/diary_view.py` — `DiaryView` ("Codex di Campagna", sezione sidebar `key="diary"`)
**Non va confuso con `DiarioTab`** (sopra): sono due superfici diverse sullo stesso personaggio.
`DiarioTab` vive dentro i 5 tab della scheda (`sheet → diario`) ed è solo il diario/journal.
`DiaryView` è invece una sezione a sé nella sidebar principale, con un layout a due pannelli:
- **Pannello sinistro (200px)**: 7 categorie cliccabili — Cronaca, PNG Incontrati, PNG da Cercare,
  Luoghi Visitati, Da Esplorare, Missioni, Fazioni — e sotto la lista dei capitoli/voci della categoria attiva
- **Pannello destro**: per "Cronaca" una pagina di lettura stile pergamena + editor inline; per le altre 6
  categorie una card di dettaglio + form di modifica inline
- **Cronaca** usa la STESSA tabella/modello di `DiarioTab` (`diary_entries` / `DiaryEntry`) — è la stessa
  fonte dati, mostrata con un layout diverso, non una copia separata
- Le altre 6 categorie usano `campaign_notes` / `CampaignNote` (vedi schema DB e `data/models.py` sopra),
  CRUD via `character_repo`: `get_campaign_notes`, `create_campaign_note`, `update_campaign_note`, `delete_campaign_note`
- Flet 0.85.3: nessun `expand=True` su `Column` dentro `Row` dentro `ListView`; `cast(list[ft.Control], [...])`
  per `actions=`; `Any` per gli handler (stesse regole del resto del progetto)
- **Refresh mirati (2026-08-27)**: selezione/navigazione/salvataggio di una voce o nota NON ricostruiscono
  più l'intera vista — `_diary_list_item()`/`_note_list_item()` sono taggati `data=id`, e
  `_update_list_row_diary()`/`_update_list_row_note()` sostituiscono solo la riga coinvolta mentre
  `_update_detail()` (già esistente) sostituisce solo il pannello destro. Restano sul `_refresh()` completo
  SOLO le azioni che cambiano conteggio/ordine (elimina, crea, cambio categoria, toggle pannello). Stesso
  pattern applicato a `MasterNotesView` (`ui/views/master/master_notes_view.py`, layout gemello lato Master,
  che in più ha guadagnato una `ScrollMemoryColumn` — prima non ne aveva nessuna). Dettaglio completo in
  `changelog_storico.md`, voce "Refresh mirati invece di rebuild aggressivo... (2026-08-27, v0.3.19)".

### `ui/views/character_sheet/inventario_tab.py` — `InventarioTab` (RISCRITTO con CRUD completo)
**Eredita da `ft.ListView`**.
- **Monete**: 5 cerchi cliccabili (MR/MA/ME/MO/MP) → dialog con pulsanti −/+ (72px fissi) e
  numero corrente a 48pt; `_apply(delta)` aggiorna in-place senza ricaricare l'intero tab
- **Peso**: barra `ft.ProgressBar` colorata (verde/arancio/rosso) — capacità = FOR × 7.5 kg
- **Armi**: pulsante "Aggiungi Arma" + card per ogni arma con badge ATT/DANNO, tag magica, gittata
  - Tipo danno: `Dropdown` su `_DAMAGE_TYPES` (non TextField libero)
  - Proprietà: `Checkbox` multi-select da `_WEAPON_PROPERTIES` (12 proprietà PHB)
  - Sezione danni magici: righe ripetibili (dado+tipo+nota), pulsante "+Aggiungi" e "×" per rimozione
  - IconButton toggle equipaggiata (barra laterale cambia colore: rosso = eq, grigio = non eq)
  - IconButton elimina → dialog conferma
- **Oggetti**: pulsante "Aggiungi Oggetto" + lista per categoria (misc/armor/weapon/tool/magic)
  - Dialog oggetto: aggiunto `f_effects` TextField; se categoria=="armor" mostra `f_ca` (INT) + `armor_type_dd` Dropdown
  - `on_cat_select` toggl visibilità `armor_fields` dinamicamente
  - Save: se armor, chiama `calculate_and_update_ca()` per ricalcolare CA
  - IconButton elimina → dialog conferma
- `_toggle_weapon_equipped(weapon)` → aggiorna DB + refresh istantaneo
- `_refresh()` → ricarica tutto dal DB e ricostruisce i controlli
- Import necessari: `import json`, `from typing import Any, cast`

### `data/game_data/spell_slot_progressions.json` (nuovo, 2026-07-10)
Tabelle PHB slot incantesimo per livello (full/half/pact caster) + mappa `caster_type_by_class`, spostate da
`data/repositories/character_repo.py` (dove vivevano come dizionari Python
`_FULL_CASTER_SLOTS`/`_HALF_CASTER_SLOTS`/`_WARLOCK_SLOTS`/`_FULL_CASTERS`/`_HALF_CASTERS`/`_PACT_CASTERS`) su
segnalazione di Davide: i numeri erano già stati verificati contro il manuale in sessioni di audit precedenti, ma
restavano scritti a mano solo in Python invece che come dato JSON — stessa incoerenza architetturale già risolta
per RACE_DATA/CLASSES/tags.json. Nessun valore cambiato (diff automatico contro le vecchie tabelle prima della
rimozione, poi test di regressione end-to-end: 12 classi × 20 livelli, `auto_init_spell_slots()` produce totali
identici a prima).
`GameDataLoader` espone `get_caster_type(class_name)` → `"full"|"half"|"pact"|""` e
`get_spell_slot_table(caster_type)` → lista di 20 righe `[slot 1°...9°]`. `character_repo.auto_init_spell_slots()`
ora legge da qui invece che da tabelle locali.

**ASI_LEVELS spostato in JSON (2026-07-10)** — stesso principio, con un bug di duplicazione reale trovato nel
percorso: `ASI_LEVELS`/`ASI_LEVELS_DEFAULT` esistevano sia in `config/settings.py` sia come copia locale
indipendente `_ASI_LEVELS`/`_ASI_DEFAULT` in `profilo_tab.py` (stesso identico contenuto, ma due dizionari Python
scritti a mano separatamente — se una futura correzione di uno dei due fosse stata dimenticata nell'altro, i due
punti dell'app si sarebbero disallineati silenziosamente). Fix: aggiunto il campo `"asi_levels"` a `guerriero.json`
(`[4,6,8,12,14,16,19]`) e `ladro.json` (`[4,8,10,12,16,19]`) — le uniche 2 progressioni non standard PHB; nuovo
`GameDataLoader.get_asi_levels(class_name)` legge quel campo se presente, altrimenti restituisce la progressione
standard `{4,8,12,16,19}` (costante universale, non scritta in tutti i 10 file classe standard per evitare di
duplicare lo stesso letterale dieci volte). Rimossi `ASI_LEVELS`/`ASI_LEVELS_DEFAULT` da `settings.py` e
`_ASI_LEVELS`/`_ASI_DEFAULT` da `profilo_tab.py`; `level_manager.py` e `profilo_tab.py` ora chiamano
`get_asi_levels()`. Verificato con test end-to-end: `get_level_up_steps()` su tutte le 12 classi × livelli 2-20
genera lo step ASI esattamente agli stessi livelli di prima della migrazione.

**Tabelle numeriche di `core/level_manager.py` spostate in JSON (2026-07-10)** — stesso principio, completando la
migrazione avviata con gli slot incantesimo e ASI_LEVELS. `_METAMAGIC_COUNT_BY_LEVEL` → `stregone.json →
"metamagic_count_by_level"`; `_INVOCATIONS_TOTAL_BY_LEVEL` → `warlock.json → "invocations_total_by_level"`;
`_SEGRETI_MAGICI_LEVELS` → `bardo.json → "segreti_magici_levels"`; `_EXPERTISE_LEVELS` → campo `"expertise_levels"`
in `ladro.json` (`[1,6]`) e `bardo.json` (`[3,10]`); `_SPELL_LEARN_DELTA` → campo `"spell_learn_delta"` in
`bardo.json`/`stregone.json`/`warlock.json`/`ranger.json` (le 4 classi "know"). Nuovi metodi `GameDataLoader`:
`get_metamagic_count_by_level()`, `get_invocations_total_by_level()`, `get_segreti_magici_levels()`,
`get_expertise_levels(class_name)`, `get_spell_learn_delta(class_name)` (le chiavi JSON sono stringhe, convertite
in int dal loader). Nessun valore cambiato — verificato sia confrontando le tabelle lette dal loader contro le
vecchie costanti Python, sia rieseguendo `get_level_up_steps()` su tutte le 12 classi × livelli 2-20 e controllando
che gli step METAMAGIC/INVOCATION/EXPERTISE/SPELL_LEARN vengano emessi esattamente agli stessi livelli e con gli
stessi conteggi di prima della migrazione (0 discrepanze). `level_manager.py` non contiene più nessuna tabella PHB
scritta a mano — tutti i numeri vengono ora da `data/game_data/classes/*.json`.

**Dado di Ispirazione Bardica calcolato a runtime (2026-07-10)** — `bardo.json` ha ora il campo
`"bardic_inspiration_die_by_level"` (`{"1":"d6","5":"d8","10":"d10","15":"d12"}`, dato già confermato dal testo
della feature "Ispirazione Bardica"). Nuovo `GameDataLoader.get_bardic_inspiration_die(level)` risolve il dado
corretto per il livello indicato. **Attenzione architetturale**: il dado NON viene incluso nel nome della risorsa
salvata su DB (`class_resources.name = "Ispirazione Bardica"`, invariato) — `character_repo.init_class_resources()`
fa il merge DB↔defaults confrontando i nomi per uguaglianza esatta, quindi un nome che cambiasse ad ogni soglia di
livello (es. "Ispirazione Bardica (d8)"→"(d10)") verrebbe trattato come una risorsa completamente diversa: la
vecchia riga sarebbe cancellata come "obsoleta" e la nuova ricreata con `current_value = max_value`, azzerando
silenziosamente gli utilizzi già spesi dal giocatore in quella sessione. Il dado viene invece calcolato e mostrato
solo a runtime in `combattimento_tab.py → _resource_circles_row()` (confrontando `res.name == "Ispirazione
Bardica"` e leggendo `self.character.level`), senza mai toccare il valore persistito. Verificato con test:
`get_class_resource_defaults("Bardo", lvl, c)` restituisce lo stesso nome esatto `"Ispirazione Bardica"` per tutti
i 20 livelli.

**Tabella Attacco Furtivo (Ladro) aggiunta e collegata alla UI (2026-07-10)** — dato mai trascritto in nessuna
sessione precedente (l'audit di `ladro.json` del 2026-07-03 aveva corretto solo il testo/meccanica della feature,
non la progressione numerica per livello). Davide ha fornito una foto della pagina "Ladro" del manuale con la
colonna "Attacco Furtivo" per intero. Aggiunto `ladro.json → "sneak_attack_dice_by_level"`
(`{"1":"1d6","3":"2d6","5":"3d6","7":"4d6","9":"5d6","11":"6d6","13":"7d6","15":"8d6","17":"9d6","19":"10d6"}` —
+1d6 ogni 2 livelli a partire dal 1°, fino a 10d6 dal 19° in poi). Nuovo
`GameDataLoader.get_sneak_attack_dice(level)`, stesso pattern di `get_bardic_inspiration_die()` (soglia più alta
raggiunta, fallback "1d6"). Collegato in `combattimento_tab.py → _section_class_features()`: quando la riga
cliccabile è "Attacco Furtivo" e la classe è Ladro, il nome mostrato diventa `"Attacco Furtivo (Nd6)"` con il dado
calcolato dal livello attuale — solo a runtime, nessun valore persistito (l'Attacco Furtivo non è una risorsa a
consumo con contatore, quindi qui non si pone nemmeno il problema di stabilità del nome già gestito per
l'Ispirazione Bardica). Verificato con test: `get_sneak_attack_dice(lv)` per tutti i 20 livelli combacia
esattamente con la tabella della foto fornita da Davide.

**Scelta Trucchetti/Incantesimi Iniziali a Lv.1 implementata (task #74, 2026-07-10)** — bug report di Davide:
mancava del tutto una UI per scegliere i trucchetti e (per le classi "know") gli incantesimi di 1° livello alla
creazione del personaggio; i personaggi nascevano senza nessun trucchetto/incantesimo conosciuto finché il
giocatore non li aggiungeva a mano dalla tab Incantesimi. **Origine dei dati** (Davide ha fatto notare che questi
numeri sono nelle stesse tabelle di classe del PHB già usate per altri dati, e in effetti erano già presenti nel
progetto sotto forma di testo delle feature, mai in un campo numerico dedicato):
  - Trucchetti @ Lv.1: confermati testualmente nella feature "Incantesimi"/"Trucchetti"/"Magia del Patto" di
    ciascun JSON classe — Bardo 2, Chierico 3, Druido 2, Mago 3, Stregone 4, Warlock 2 (Paladino/Ranger non hanno
    trucchetti nel PHB, correttamente 0).
  - Incantesimi conosciuti (non trucchetti) @ Lv.1 — solo le 3 classi "know" (Bardo/Stregone/Warlock, le uniche con
    una lista fissa di incantesimi scelta alla creazione anziché preparata ogni giorno): Stregone 2 e Warlock 2
    confermati testualmente ("conosce due incantesimi di 1° livello a sua scelta"); **Bardo 4 ricavato per
    calcolo** da due fatti già verificati contro il manuale in sessioni precedenti — `spell_learn_delta["Bardo"]`
    (verificata pag.53, somma dei delta dal Lv.2 al Lv.20 = 18) e il totale finale confermato a Lv.20 = 22 (vedi
    audit level-up Bardo) → 22 − 18 = 4. Chierico/Druido/Paladino non hanno una lista "conosciuta" fissa (preparano
    dal pool completo ogni giorno) — nessuna scelta necessaria oltre ai trucchetti. Il Mago non "conosce"
    incantesimi in questo senso: parte con un libro degli incantesimi (6 incantesimi di 1° livello, PHB p.82) —
    meccanica distinta, non affrontata da questo task.
  - **Dati aggiunti come nuovi campi JSON** (non tabelle Python scritte a mano, stesso principio architetturale di
    tutte le migrazioni precedenti): `"cantrips_known_at_1"` in bardo/chierico/druido/mago/stregone/warlock.json,
    `"spells_known_at_1"` in bardo/stregone/warlock.json. Nuovi metodi
    `GameDataLoader.get_cantrips_known_at_1(class_name)` / `get_spells_known_at_1(class_name)`.
  - **UI implementata identicamente in `wizard_view.py` (fase Revisione) e `manual_form.py` (fase Scelte)**: nuova
    sezione "Trucchetti e Incantesimi Iniziali" (`spells_init_col`, stesso pattern di visibilità dinamica delle
    altre sezioni extra — header dedicato, incluso in `extra_card_content`/`_update_extra_card`) con N dropdown
    trucchetti (opzioni da `get_spells_by_level(classe, 0)`) + M dropdown incantesimi di 1° livello
    (`get_spells_by_level(classe, 1)`), pre-popolati con i primi N/M nomi disponibili in ordine alfabetico e
    liberamente riassegnabili; nessuna sezione mostrata per classi senza trucchetti/incantesimi (Guerriero,
    Barbaro, ecc.) o per i soli preparatori senza trucchetti (nessuna in pratica, dato che tutti gli incantatori
    PHB hanno almeno i trucchetti).
  - **Caso limite Mago + Alto Elfo**: il trucchetto razziale dell'Alto Elfo (dropdown separato, sempre dalla lista
    Mago) e i trucchetti di classe condividono lo stesso pool SOLO quando il personaggio è effettivamente un Mago —
    in quel caso il trucchetto già scelto per il tratto razziale viene escluso dalle opzioni di classe (altrimenti
    lo stesso trucchetto occuperebbe "due slot" diversi, sprecandone uno). Per qualunque altra classe (es. un Ladro
    Alto Elfo) il trucchetto razziale non interagisce affatto con la sezione di classe, perché appartiene sempre
    alla lista Mago indipendentemente dalla classe del personaggio. Entrambi i file ricostruiscono la sezione
    "Trucchetti Iniziali" quando il dropdown del trucchetto Alto Elfo cambia (solo se la classe è Mago).
  - **Validazione**: il salvataggio è bloccato con messaggio d'errore se mancano scelte obbligatorie o se sono
    presenti duplicati tra i dropdown (stesso pattern delle altre validazioni già esistenti, es. Perizia Ladro).
  - **Salvataggio**: ogni trucchetto/incantesimo scelto viene risolto contro `_loader.get_spells(class_name)`
    (nuova funzione `_save_known_spell_by_name`, identica in entrambi i file, stesso pattern già usato in
    `profilo_tab.py` per gli step SPELL_LEARN del level-up) e salvato come `known_spell` con `is_prepared=True` —
    per le classi "know" questo rappresenta la lista fissa e permanente di incantesimi conosciuti (nessun limite di
    preparazione giornaliera, coerente con `spells_view.py → _KNOW_CLASSES`); per i trucchetti, `is_prepared=True`
    è la convenzione già usata ovunque nel progetto (i trucchetti non hanno mai un limite di preparazione).
  - **Verificato con test end-to-end** (DB temporaneo isolato) su entrambi i file, per
    Mago/Bardo/Stregone/Warlock/Chierico/Guerriero: numero di trucchetti/incantesimi salvati combacia esattamente
    con `get_cantrips_known_at_1()`/`get_spells_known_at_1()`, nessun duplicato; caso Mago+Alto Elfo verificato
    separatamente (3 trucchetti di classe + 1 trucchetto razziale, 4 nomi distinti, zero sovrapposizioni).

### `data/game_data/` — JSON dati di gioco (nuovi file)
Struttura gerarchica JSON per classi, razze e background PHB. Utilizzabile in futuro da wizard e level-up.

~~**`tags.json`** — espansione tag~~ — **rimosso il 2026-07-10**, vedi sezione `equipment/` più sotto per il changelog completo (dato morto, mai letto da nessun codice, e con errori reali).

**`classes/*.json`** — 12 classi PHB (barbaro, bardo, chierico, druido, guerriero, ladro, mago, monaco, paladino, ranger, stregone, warlock). Campi:
```json
{
  "name", "hit_die", "primary_ability", "saving_throws", "spellcasting_ability",
  "armor_proficiencies", "weapon_proficiencies", "tool_proficiencies",
  "skill_choices": {"count": N, "options": [...]},
  "starting_equipment": [{"type": "fixed|choice", ...}],
  "starting_gold_alternative": {"dice": "XdY", "multiplier": Z},
  "subclass_label", "subclass_choice_level",
  "subclasses": [{"name", "bonus_proficiencies", "features": [{"level", "name", "description"}]}]
}
```

**Schema `item_type` in `starting_equipment`:**
- `"weapon"` — arma specifica (nome esatto)
- `"armor"` — armatura specifica
- `"item"` — oggetto generico
- `"weapon_choice"` — scelta libera da categoria: campi `category` (`"semplice"`, `"semplice_mischia"`, `"guerra"`,
  `"guerra_mischia"`) e `count` (N armi da scegliere); la UI mostra N Dropdown popolati da
  `WEAPONS_BY_CATEGORY[category]`
- `"tool_choice"` (2026-08-15, bug report Davide: "qualsiasi strumento musicale" del Bardo
  non permetteva di scegliere) — stesso schema di `weapon_choice` ma per strumenti: campi
  `category` (chiave di `GameDataLoader.get_tool_categories()`, es. `"strumenti_musicali"`) e
  `count`; la UI mostra N Dropdown popolati da `_loader.get_tool_categories()[category]` invece
  di `WEAPONS_BY_CATEGORY`. Rami paralleli a `weapon_choice` in tutti e 3 i punti di
  `wizard_view.py`/`manual_form.py` (oggetti fissi, `_build_weapon_pickers()`, `_save_item()`) e
  in `CreationSharedMixin._init_weapon_choice()` (vedi sotto). Salva con `category="tool"` su
  `create_inventory_item()`, mai su `weapons`. **Terzo punto di sincronizzazione**, trovato
  durante la stessa sessione: `core/character_instances.py::_weapon_choice_default()`/
  `_assign_default_starting_equipment()` duplica (per lo stesso motivo di `import flet` vietato
  in `core/*.py`, vedi il commento lì) la risoluzione di `weapon_choice` per l'assegnazione
  equipaggiamento non interattiva di un'istanza di personaggio "dal 1° livello" — esteso con lo
  stesso ramo `tool_choice`, altrimenti un `tool_choice` come prima opzione di una scelta
  (non il caso di Bardo oggi, dove option[0] è "Liuto", ma un gap di correttezza reale per
  qualunque dato futuro) sarebbe silenziosamente salvato come oggetto generico col nome
  letterale del placeholder, riproducendo lì lo stesso bug appena corretto altrove.

**Schema `item_type` in `backgrounds/*.json → equipment`:**
- `"currency"` — monete: campi `currency_type` (`"gold"`, `"silver"`, `"copper"`, `"electrum"`, `"platinum"`) e `quantity`; al salvataggio → `update_currencies()`, NON `create_inventory_item()`
- `"item"` — oggetto generico → inventario

**Nomi dotazioni PHB italiano (corretti in tutti i JSON):**
- `"Dotazione da Esploratore"` (Explorer's Pack)
- `"Dotazione da Avventuriero"` (Dungeoneer's Pack)
- `"Dotazione da Sacerdote"` (Priest's Pack)
- `"Dotazione da Diplomatico"` (Diplomat's Pack)
- `"Dotazione da Intrattenitore"` (Entertainer's Pack)
- `"Dotazione da Scassinatore"` (Burglar's Pack)
- `"Dotazione da Studioso"` (Scholar's Pack)
- `"giavellotti"` (non "zagaglie" — arma da lancio semplice, PHB p.149)

**`races/*.json`** — 9 razze PHB (umano, elfo, nano, halfling, gnomo, mezzelfo, mezzorco, tiefling, draconide). Campi:
```json
{
  "name", "has_subrace", "ability_bonuses", "ability_bonuses_flex",
  "speed", "darkvision", "size", "languages", "traits",
  "subraces": [{"name", "ability_bonuses", "traits", ...}]
}
```

**`backgrounds/*.json`** — 12 background PHB. Campi:
```json
{
  "name", "description", "skill_proficiencies", "tool_proficiencies", "languages",
  "equipment", "feature": {"name", "description"},
  "personality_traits": [8 voci], "ideals": [6 voci], "bonds": [6 voci], "flaws": [6 voci]
}
```

**`spells/incantesimi_[classe].json`** — scritti manualmente dal giocatore. Struttura convenuta:
```json
{
  "class": "Chierico",
  "spells": [
    {
      "name", "level", "school", "casting_time", "range", "components",
      "duration", "ritual", "concentration", "description", "higher_levels"
    }
  ]
}
```

### `ui/views/character_sheet/combattimento_tab.py` — `CombattimentoTab` (aggiornato)
- Accetta `on_refresh: Callable[[], None] | None = None` → chiama `_on_refresh()` a fine `_refresh()` per aggiornare la top bar
- Box CA nella MiniStatBar è cliccabile: apre dialog per bonus CA temporaneo
  - Label diventa `"CA (+N)"` / `"CA (-N)"` con colore blu (positivo) o rosso (negativo)
  - `_on_ca_bonus_click`: mostra CA base, CA totale, TextField per nuovo bonus, pulsanti "Applica" e "Reset a 0"
  - Chiama `update_ca_bonus()` + `_refresh()`
- Iniziativa = `get_modifier(dex_score) + (character.initiative_bonus or 0)` — include talenti come Allerta
- **Sezione Abilità di Classe** (`_section_class_features`):
  - Righe cliccabili per ogni feature base della classe + sottoclasse (filtrate per `level <= c.level`)
  - Badge rosso = feature base classe, badge blu = feature sottoclasse
  - Click → `AlertDialog` con descrizione completa (scrollabile, width=340)
  - Separatori tra livelli diversi; legenda in fondo
  - Carica da JSON classe via `GameDataLoader`; `source` field per distinguere base vs sottoclasse
- **Sezione Tratti di Razza** (`_section_racial_traits`):
  - Chip resistenza (🛡 blu) e chip vantaggio TS (↑ amber)
  - Dati da `get_race_display_traits(race, subrace)` in `config/settings.py`
  - Solo mostrata se resistenze o advantage_saves presenti
- **Sezione Forme Selvatiche** (`_section_forme`, `entry_type="forma"`) e **Sezione Evocazioni**
  (`_section_evocazioni`, `entry_type="evocazione"`) — non documentate finché non trovate durante
  la code review del 2026-07-10, ma già implementate e funzionanti:
  - Backed da tabella `creature_entries` / modello `CreatureEntry` (vedi schema DB sopra)
  - Picker "Aggiungi Forma Selvatica" (solo creature `type == "Bestia"`, filtrate anche per CR massimo
    di `druido.json → wild_shape_forms`) / "Evoca Creatura" (nessun filtro di tipo) — legge da
    `data/game_data/monsters.json`, ricerca per nome + filtro CR/tipo, max 60 risultati mostrati
  - Card lista con nome (`monster_display_name()`, converte il MAIUSCOLO del bestiary in title case),
    GS, PF max; click → dialog dettaglio (stat block completo: CA, PF, caratteristiche, TS, abilità,
    resistenze/immunità, sensi, linguaggi, tratti, azioni, azioni leggendarie)
  - Tracker HP dedicato per ogni creatura attiva (`update_creature_hp`, indipendente dagli HP del PG)
  - CRUD via `character_repo`: `get_creature_entries(character_id, entry_type=...)`,
    `create_creature_entry(...)`, `update_creature_hp(creature_id, hp_current)`, `delete_creature_entry(creature_id)`
  - ⚠️ `monsters.json` (343 mostri) non ancora auditato riga per riga contro il Manuale dei Mostri —
    vedi checklist audit dati più sotto
- **Sezione Indebolimento** (`_section_exhaustion`, 2026-07-16 — **dal 2026-08-27 dentro la card di
  `_section_stats()`** invece che sezione a sé stante a piena larghezza, vedi sotto):
  - Counter −/+ per `character.exhaustion_level` (0-6), colore grigio→ambra→rosso
  - Lista effetti cumulativi da `EXHAUSTION_LEVELS` (config/settings.py) attivi al livello corrente
  - `_on_exhaustion_increment`/`_on_exhaustion_decrement` → `character_repo.update_exhaustion_level()` + `_refresh()`
  - Nessun enforcement automatico (non dimezza velocità/HP max da sola) — sezione di sola consultazione
  - **2026-08-27**: ritorna il contenuto interno (`ft.Column`, niente più `Container`/bordo/ombra propri, un
    `ft.Divider` al posto dell'header di sezione rimosso) — `_section_stats()` la aggiunge in coda alla propria
    `ft.Column`, dentro la stessa `design.card()` di CA/Velocità/Iniziativa/Ispirazione (`_build()` non la
    chiama più separatamente). Eredita così lo stesso comportamento responsive di `design.asymmetric_row()`
    (va a capo su smartphone insieme al resto invece di restare un blocco separato).
- **Risorse RAZZIALI cliccabili in "Risorse di Classe"** (2026-08-27) — nuovo
  `_resource_name_control(res, display_name=None)`, condiviso dalle 3 righe risorsa
  (`_resource_unlimited_row`/`_resource_circles_row`/`_resource_counter_row`): interroga
  `config/settings.py::get_race_resource_description(character, res.name)`; se non vuota, il nome diventa un
  `Container` cliccabile (icona ℹ) → `_show_resource_description()` (`AlertDialog` semplice). Copre solo le
  risorse di origine RAZZIALE (Soffio del Dragonide, Tenacia Implacabile, incantesimi innati Tiefling/Elfo
  Oscuro) — le risorse di CLASSE restano consultabili solo via "Abilità di Classe" (nessuna duplicazione,
  `get_race_resource_description()` ritorna `""` per quelle e la riga resta testo semplice non cliccabile).
- **Sezione Frenesia** (`_section_frenzy`, 2026-07-19, solo Barbaro Cammino del Berserker — dentro "Risorse di
  Classe", subito dopo Incantesimi Flessibili): chip "Dichiara Frenesia" (grigio) → "Termina Ira (+1
  Indebolimento)" (rosso) + link "Annulla dichiarazione (senza Indebolimento)";
  `_on_declare_frenzy`/`_on_cancel_frenzy` → `character_repo.update_frenzy_state()`; `_on_end_frenzy` →
  `character_repo.end_frenzy_rage()` (atomica: azzera `frenzy_active` + applica +1 Indebolimento clampato in
  un'unica scrittura) + `_refresh()`. Nessuna automazione più a monte (non rileva da sola l'uso di Furia/la fine
  del turno) — il giocatore dichiara/termina, l'incremento di Indebolimento è l'unica parte automatica.
- **Sezione Stile di Combattimento** (`_section_fighting_style`, 2026-07-19, sola lettura — visibile se
  `character.fighting_style` è valorizzato): riga cliccabile → `AlertDialog` con la descrizione completa risolta
  via `GameDataLoader.get_fighting_style_data(class_name)`. La scelta resta esclusivamente in Profilo (level-up);
  questa sezione non introduce un secondo punto di assegnazione.
- **Sezione Suppliche Occulte** (`_section_invocations`, 2026-07-19, sola lettura — visibile se il personaggio ha
  almeno una `proficiency_type="invocation"`): stessa logica, righe cliccabili risolte via il nuovo
  `GameDataLoader.get_invocation(name)`; nessuna nuova scelta possibile da qui, solo consultazione — stesso
  principio già stabilito per Abilità di Classe/Tratti di Razza.

### `ui/views/character_sheet/esplorazione_tab.py` — `EsplorazioneTab` (aggiornato)
- Accetta `on_refresh: Callable[[], None] | None = None` → chiama `_on_refresh()` a fine `_refresh()`
- Nuova sezione in fondo: **Appunti di Sessione**
  - `ft.TextField(multiline=True, min_lines=4, max_lines=12)` precompilato con `c.session_notes`
  - `on_blur` → `character_repo.update_session_notes()` se il testo è cambiato (auto-save)
- Import necessari: `from typing import Any, cast` (per `cast(Any, tf).error_text`)
- ~~Sezione Competenze Armatura e Armi~~ — **spostata in `profilo_tab.py` il 2026-07-16** (richiesta Davide: "le
  competenze non le dobbiamo lasciare in esplorazione ma andrebbero messe in profilo").
  `_section_armi_armature()`/`_ARMOR_TOKEN_LABELS`/`_WEAPON_TOKEN_LABELS` non esistono più in questo file — vedi
  `ProfiloTab` sotto per la stessa sezione nella nuova posizione.
- **Lingue/Strumenti (2026-08-27)** — ~~Lingue~~ **si è spostata sotto Competenze in `ProfiloTab`**
  (`_section_lingue_header()`/`_section_lingue()` NON esistono più qui, vedi `ProfiloTab::_section_lingue()`
  sotto). **Strumenti resta qui ma non è più sola lettura**: `_section_strumenti_header()` ha un pulsante
  "+ Aggiungi" (`_open_add_tool_dialog()`, tendina catalogo `game_data.get_all_tool_names()` + Veicoli
  terrestri/acquatici + "compila a mano" per uno strumento inventato) e ogni riga ha un ✕ rimuovi
  (`_on_delete_tool()`, query `DELETE FROM character_proficiencies` diretta — nessuna funzione dedicata nel
  repository, stesso pattern già in uso in `ProfiloTab::_on_delete_proficiency()`, duplicata qui non condivisa).
  Anche **Scurovisione** ha un override manuale ora (vedi `Character.darkvision_override` sopra):
  `_section_sensi()` → riga "Scurovisione" cliccabile (`_editable_info_row`, stesso pattern di "Camminata") →
  `_on_edit_darkvision()` (`RadioGroup` Sì/No + campo metri + "Usa valore di razza").

### `ui/views/character_sheet/inventario_tab.py` e `diario_tab.py`
- Entrambi accettano `on_refresh: Callable[[], None] | None = None` → chiamato a fine `_refresh()` per sincronizzare la top bar (es. dopo level-up che aggiorna l'inventario)

### `ui/views/character_sheet/sheet_view.py` — `SheetView`
Container principale della scheda personaggio (post-selezione):
- **MiniStatBar** fissa in cima: 6 box cliccabili (abbr/punteggio/modificatore) → click apre dialog modifica tutti e 6 i punteggi
  - Valori 1–30 (house rules), salva su DB e chiama `_refresh_all()` che aggiorna bar + tab corrente
- **Header personaggio**: nome, livello, classe (+sottoclasse), razza, bonus competenza
  - Bonus competenza cliccabile: dialog per override manuale (campo `proficiency_bonus_override` su Character)
  - Override visibile con colore blu e "✎"; lasciare vuoto per tornare a PHB standard
  - `char_prof_bonus(character)` in `config/settings.py` — usare ovunque al posto di `get_proficiency_bonus(level)`
- **`_refresh_bar_and_header()`**: aggiorna SOLO stat bar + header (senza ricreare il tab) — passata come
  `on_refresh` a tutti i tab. Usata dai tab quando modificano dati del personaggio (es. level-up, modifica stat)
  per sincronizzare la top bar senza rebuild completo
- **`_refresh_all()`**: ricarica Character dal DB, ricrea stat bar, header e tab corrente — usata internamente quando cambia tab
- **`_get_tab_content(key)`**: istanzia il tab passando `on_refresh=self._refresh_bar_and_header`
- **`did_mount()`**: salva `self._page` per i dialog
- **TabBar custom**: 5 tab (Profilo | Combattimento | Esplorazione | Inventario | Diario)
  - Tab attivo: sfondo bianco, bordo rosso sotto, testo bold rosso
  - Tab inattivo: sfondo marmo `COLOR_BG_TAB_INACTIVE`

### `ui/views/character_sheet/profilo_tab.py` — `ProfiloTab`
**Eredita da `ft.ListView`** (non Column scroll=AUTO) — necessario per layout corretto in Flet 0.85.3.
- Accetta `on_refresh: Callable[[], None] | None = None` → chiamato a fine `_refresh()` per aggiornare la top bar di SheetView
- **Header**: avatar cliccabile (dialog percorso file), nome, livello, classe, razza, XP inline + Salva, bottone "Sali di Livello" (visibile quando XP ≥ soglia prossimo livello)
- **Ogni sezione ha "✎ Modifica"** → `AlertDialog` con `TextField`:
  - Anagrafica, Tratti Razziali, Dettagli Fisici, Personalità, Storia
- **Tratti Razziali**: velocità, scurovisione (`c.darkvision_override if >= 0 else` valore razza, vedi
  `Character.darkvision_override` sopra), tratti speciali da `_loader.get_resolved_race(c.race, c.subrace)` (solo
  JSON). **Dragonide (2026-08-27)**: i 3 tratti legati alla discendenza scelta ("Discendenza Draconica",
  "Resistenza ai Danni", "Arma a Soffio") vengono risolti sui valori reali via
  `config/settings.py::resolve_dragonide_trait_texts(c.subrace, c.level, c)` invece di mostrare il testo generico
  del JSON (elenco di tutte le 10 discendenze) — solo se `c.race == "Dragonide"` e la discendenza (`c.subrace`,
  es. "Blu") è riconosciuta, altrimenti resta il testo generico.
- **Caratteristiche**: modificabili dalla MiniStatBar (non più sezione separata nel profilo tab)
- **Competenze**: TUTTE le 18 abilità (non solo competenti), su 2 colonne:
  - ● rosso = competente | ★ blu = maestria | ○ grigio = non competente
  - Tiri salvezza separati in blocco dedicato
  - "✎ Modifica" → dialog interattivo: tocca una riga per ciclare ○→●→★→○
  - Salva con `replace_proficiencies_by_types` per "save" e "skill" in transazione atomica
- **Level Up guidato** (`_on_level_up_click`):
  - Scelta HP: massimo / media / dado manuale (con calcolo CON)
  - ASI ai livelli appropriati per classe (default: 4,8,12,16,19; Guerriero/Ladro hanno livelli extra)
  - ASI: RadioGroup +2/+1+1/Talento; `+2` e `+1+1` salvati come `proficiency_type="asi_record"` con `bonus_data={"ability":{...}}` e `level_obtained=new_level` (per reversal in level-down).
    **2026-08-27**: `stat_options` (dropdown +2/+1+1) esclude le caratteristiche già a 20 — prima restavano
    selezionabili (l'applicazione le clampava comunque a `min(20,...)`, ma l'ASI veniva "consumata" senza alcun
    beneficio e senza avviso, bug report Davide)
  - Feat: `feat_bonus_dd` dropdown che appare solo per feat con `choose_one` — permette di scegliere quale stat
    aumentare; bonus applicato su `character.*_score` e salvato in `bonus_data={"ability":{stat:1}, "other":{...}}`
    del proficiency "feat"; `other_bonuses` supporta `initiative` e `speed`. Stesso filtro tetto-20 del punto sopra
    applicato anche qui (2026-08-27).
  - Notifica aumento Bonus Competenza
  - Salva e aggiorna scheda via `_refresh()`
  - **Validazione obbligatoria** (`do_level_up`): prima del salvataggio verifica tutti i campi obbligatori
    - dado manuale fuori range, ASI senza stat, feat non scelto, choose_one senza stat, dropdown incantesimi vuoti,
      Segreti Magici non completati, metamagia/invocazioni sotto il minimo
    - Se errori: `AlertDialog` con lista di campi mancanti, il dialog level-up rimane aperto
  - **Level Down** (`do_level_down`): chiama `undo_level(id, current_level)` che reversa tutti i bonus ASI/feat del
    livello; decrementa `character.level`, sottrae HP guadagnati al livello; usa `self.character` post-reload (non
    riassegnare `c`)
- **Sezione Talenti** (`_build_talenti`):
  - Bottone "✎ Modifica talenti" → `AlertDialog` con tutti i 42 feat da `feats.json` come Checkbox
  - Pre-spuntati se già posseduti; rimozione feat usa `remove_feat_with_bonuses()` (reversa i bonus) invece di bulk replace
  - Utile per house rules (aggiungere/rimuovere feat manualmente)
- **Sezione Competenze Armatura e Armi** (`_section_armi_armature`, sola lettura — **spostata qui da
  `EsplorazioneTab` il 2026-07-16**, vedi Note Importanti "Redesign selezione incantesimi/talenti (CardPicker)" per
  il changelog completo):
  - Mostra le competenze `proficiency_type in ("armor","weapon")` — popolate da
    `character_repo.apply_class_base_proficiencies()` (self-healing ad ogni apertura tab)
  - Token categoria (`"leggere"`/`"guerra"`/ecc.) mostrati con etichetta leggibile via
    `_ARMOR_TOKEN_LABELS`/`_WEAPON_TOKEN_LABELS`; nomi arma specifica (es. "Stocco") mostrati as-is
  - Nessun "+ Aggiungi" (derivate dalla classe, non scelte del giocatore) — rimovibili per house rule
  - `_on_delete_proficiency()` locale (stesso schema SQL già in uso in `esplorazione_tab.py`, non condiviso tra i due file)
- **Sezione Lingue** (`_section_lingue`, 2026-08-27 — spostata sotto "Competenze", subito prima di "Competenze
  Armatura e Armi") — sostituisce la vecchia "Altre Competenze" (Lingue+Strumenti insieme): ora filtra solo
  `proficiency_type == "language"`. Gli Strumenti si gestiscono invece direttamente in `EsplorazioneTab` (vedi
  sopra), non più da qui. `_open_add_competenza_dialog()` ha un nuovo parametro `lock_type: str | None = None`:
  quando chiamato da questa sezione (`lock_type="language"`) nasconde il selettore Tipo, fisso su "Lingua" —
  evita che una competenza aggiunta da qui venga salvata come Strumento/Arma/Armatura e sparisca dalla vista
  (bug potenziale, mai il comportamento voluto per questa sezione). Tendina catalogo invariata (`LANGUAGES`,
  15 lingue PHB) con "— nessuno, compila a mano —" per una lingua inventata dal giocatore.
- **Selezione incantesimi/trucchetti/talenti** (SPELL_LEARN, CANTRIP_LEARN, SPELL_SWAP, ARCANUM_SPELL,
  MONK_DISCIPLINE, BORROWED_*, talento ASI, Stile di Combattimento, scelte iniziali Warlock/Mago/Monaco) —
  **`CardPicker` invece di `Dropdown`+`dropdown_with_info()` dal 2026-07-16**, vedi Note Importanti per il
  changelog completo. Metamagia/Suppliche Occulte/Dono del Patto restano Checkbox/RadioGroup con icona ⓘ standalone
  (out of scope per questa redesign, la scelta lì è "tutto o niente" su poche opzioni sempre visibili, non un lungo
  elenco da scorrere). Il picker custom Segreti Magici (`_open_ms_picker`) resta invariato (mai usava
  `dropdown_with_info`).

**Import repo**: `import data.repositories.character_repo as character_repo` (modulo, NON classe).
**Formato competenze DB:** `proficiency_type="save"`, `name="Forza"` / `proficiency_type="skill"`, `name="Atletica"`.
**Tiri salvezza di classe**: assegnati automaticamente da `GameDataLoader.get_class_saving_throws()` in wizard e
manual_form (rimosso `CLASS_SAVING_THROWS` da settings.py il 2026-07-09, vedi "Note Importanti").
**Foto personaggio** — flusso completo:
1. Click avatar → `_pick_photo()` controlla `page.platform`
2. Android/iOS → `ft.FilePicker` nativo (funziona su mobile)
3. macOS → `osascript` in thread; Windows → PowerShell `OpenFileDialog`; Linux → `zenity` / `kdialog`
4. `_load_photo(path)` → PIL converte in JPEG (`convert("RGB")`) → base64 → salva in `character.image_data`
5. Display → `_data_uri(b64)` rileva mime dai magic bytes → `ft.Image(src=data_uri)`

`image_data TEXT` aggiunta via `ALTER TABLE` in `_migrate()`. `image_path` è campo legacy.
**IMPORTANTE**: `ft.Image(src_base64=...)` NON esiste in Flet 0.85.3 → usare sempre data URI.

### `data/database.py` — Migrazione
- `_migrate(conn)`: colonne aggiunte via `ALTER TABLE` (idempotenti): `image_data`, `ca_bonus`,
  `proficiency_bonus_override`, `session_notes`, `magic_damages`, `ca_value`, `armor_type`, `effects`,
  `initiative_bonus`, `exhaustion_level` (characters, 2026-07-16), `frenzy_active` (characters, 2026-07-19 —
  Barbaro Cammino del Berserker, vedi `data/models.py` sopra), `bonus_data` e `level_obtained`
  (character_proficiencies).
- Chiamata da `init_db()` dopo `_create_tables()`.

### `data/models.py` — Character
- `image_data: str = ""` — foto base64 (stringa, non bytes).
- `proficiency_bonus_override: int = 0` — se > 0 sovrascrive la tabella PHB (house rules).
- `initiative_bonus: int = 0` — bonus iniziativa aggiuntivo da talenti (es. Allerta +5).
- `exhaustion_level: int = 0` (0-6) — livello di Indebolimento (Exhaustion), aggiunto 2026-07-16. Nessun enforcement automatico delle regole (velocità/HP max non si dimezzano da soli).
- `frenzy_active: bool = False` — Barbaro Cammino del Berserker: Frenesia dichiarata per l'ira in corso, aggiunto
  2026-07-19. Traccia solo la dichiarazione; l'incremento di `exhaustion_level` scatta all'azione "Termina Ira"
  (vedi `character_repo.end_frenzy_rage()` e `combattimento_tab.py → _section_frenzy()` sotto), non alla sola
  presenza del flag.

### `ui/theme.py` — Tema Marmo Classico

> Voce storica, superata dal restyle Fase A (`ui/design.py`) per gran parte
> dei dettagli sotto (`fantasy_card()` oggi delega a `design.card()`,
> `danger_card()`/`stat_badge()`/`gold_button()` sono morte, vedi "Note
> Importanti") — non riscritta per intero qui, il contenuto attivo e
> verificato vive in `restyle_design.md`. L'unica voce ancora accurata e
> rilevante per `_build_theme()` (il vero `ft.Theme` passato a
> `page.theme`/`page.dark_theme`, non gli helper legacy sotto) è quella
> aggiunta il 2026-08-15:

- **`dropdown_theme=ft.DropdownTheme(text_style=..., menu_style=ft.MenuStyle(bgcolor=p.surface, shadow_color=p.shadow, elevation=8, shape=RoundedRectangleBorder(radius=Radius.SM), side=BorderSide(1, p.border)))`**
  (2026-08-15, bug report Davide) — `menu_style` mancava, quindi il popup di
  OGNI `Dropdown`/`DropdownAltro` dell'app cadeva sul default Material
  semitrasparente scuro di Flutter invece di ereditare la palette
  chiaro/scuro dell'app. Un solo punto di fix per tutti i Dropdown
  dell'app, entrambi i temi — vedi `regole_flet_api.md` per il dettaglio
  API e `changelog_storico.md` per il bug report completo.
- `fantasy_card()`: card bianca, bordo top rosso 3px, bordi laterali `COLOR_BORDER`
- `danger_card()`: bordo rosso pieno 2px
- `section_header()`: blocco rosso a sinistra + testo MAIUSCOLO grigio con letter-spacing
- `stat_badge()`: badge numerico per statistiche
- `gold_button()`: bottone blu cobalto (COLOR_ACCENT_BLUE — nome legacy "gold")
- `primary_button()`: rosso rubino COLOR_ACCENT_CRIMSON

### `ui/views/creation_wizard/wizard_view.py` — `WizardView`
**5 fasi** sequenziali con progress bar:
1. **Domande** (9 schermate): una domanda per volta, multi/singola selezione, Back annulla punteggio
2. **Raccomandazione**: top 3 classi **cliccabili** per selezionare la build di partenza; razza suggerita aggiornata dinamicamente in base alla classe selezionata
3. **Revisione** (espansa): dropdown classe/razza (base)/background/allineamento, Standard Array, **sezione extra dinamica**:
   - **Sottorazza** — dropdown se la razza ha sottorazze (Elfo/Gnomo/Halfling/Nano); per Draconide: dropdown discendenza draconica
   - **Sottoclasse lv1** — dropdown solo se `subclass_choice_level == 1` (Chierico, Stregone, Warlock)
   - **Abilità di classe** — checkbox: scegli N abilità dalla lista, escluse quelle già concesse dal background
   - **Lingue** — checkbox multi-select se il background ha lingue a scelta
   - **Strumenti** — dropdown per ogni scelta di strumenti del background
4. **Equipaggiamento** — oggetti fissi pre-selezionati (checkbox), scelte A/B (RadioGroup); equipaggiamento background mostrato come testo (auto-aggiunto)
5. **Conferma**: nome personaggio, riepilogo completo, salvataggio su DB

**State variabili review**: `_review_subrace`, `_review_subclass`, `_review_skills`, `_review_languages`, `_review_tools`, `_review_expertise`
**State variabili equipment**: `_equip_fixed` (lista dict con flag `selected`), `_equip_choices` (lista dict con `options` + `chosen_idx`)

**Salvataggio wizard (su Conferma)**:
- `character.subrace = _review_subrace` (se presente)
- `character.subclass = _review_subclass` (se lv1 subclass)
- Proficiencies: save da classe, skill da background + scelte classe, lingue, strumenti fissi background + scelti
- Inventario: oggetti fissi selezionati + pacchetto scelto A/B + oggetti background

**Dipendenze**: `GameDataLoader` (class/background JSON), `RACES_BASE`, `DRACONIDE_ANCESTRIES`, `LANGUAGES`,
`TOOL_CATEGORIES`, `TOOL_CATEGORY_LABEL`, `FIGHTING_STYLES`, `MAGO_CANTRIPS` da `config/settings.py`

**Scelte extra implementate nel wizard (fase Revisione)**:
- **Stregone + Discendenza Draconica** → dropdown tipo drago antenato (DRACONIDE_ANCESTRIES) → salvato in `character.dragon_ancestry`
- **Guerriero** → dropdown Stile di Combattimento (FIGHTING_STYLES["guerriero"]) → salvato in `character.fighting_style`
- **Mezzelfo** → 2 dropdown per +1 a 2 stat (escluso CHA) + 2 checkbox abilità razziali → bonus applicati ai
  punteggi, abilità salvate come proficiency "skill" (⚠️ bug corretto il 2026-07-09: la condizione di attivazione
  confrontava con "Mezzelf" invece di "Mezzelfo" e non scattava mai — vedi "Note Importanti")
- **Alto Elfo** → dropdown trucchetto Mago (MAGO_CANTRIPS) → salvato come `known_spell` level 0, is_prepared=True
- **Umano** → dropdown lingua aggiuntiva → salvata come proficiency "language"
- **Ladro Lv1** → sezione "Perizia (Ladro Lv.1)" con checkbox per 2 abilità dal pool (bg + classe), `set_expertise()` al salvataggio; validazione blocca se < 2 selezionate
- **Trucchetti e Incantesimi Iniziali** (task #74, 2026-07-10) → sezione con N dropdown trucchetti + M dropdown
  incantesimi di 1° livello, per tutte le classi incantatrici con `cantrips_known_at_1`/`spells_known_at_1` > 0
  (vedi Note Importanti per il dettaglio dati); salvati come `known_spell` (is_prepared=True) al salvataggio;
  validazione blocca se mancano scelte o ci sono duplicati

**Scelte extra implementate nel level-up (profilo_tab.py)**:
- **Paladino Lv2 / Ranger Lv2** → dropdown Stile di Combattimento (se `fighting_style` vuoto) → salvato in `character.fighting_style`
- **Barbaro + Percorso del Totem Guerriero, Lv3** → dropdown animale totem ("totem" in subclass lowercase) → salvato in `character.totem_animal`
- **Druido + Cerchio della Terra, Lv2** → dropdown terreno ("terra" in subclass lowercase) → salvato in `character.land_terrain`
- **Sottoclasse a Lv2-Lv3** → già gestita via features con "scegli" in `level_manager.py` → dropdown mostra tutte le sottoclassi della classe
- **Talento all'ASI** → terzo radio button nel dialog ASI → dropdown feat da `feats.json` → salvato come `proficiency_type="feat"`
- **Perizia (Expertise)** — Ladro Lv6, Bardo Lv3/Lv10 → checkbox su abilità competenti → `set_expertise()` → `is_expert=True`
- **Invocazioni Occulte Warlock** → checkbox filtrate per livello da `invocations.json` → `proficiency_type="invocation"`. Logica: `to_add = total_label - len(known_invocations)`
- **Metamagia Stregone** → checkbox da `METAMAGIC_OPTIONS` → `proficiency_type="metamagic"`. Lv2: 2 scelte, Lv10/Lv17: +1
- **Patto del Warlock Lv3** → RadioGroup Catena/Lama/Tomo → salvato in `character.pact_boon`

### `core/level_manager.py`
**Riscritto il 2026-07-10** — i nomi feature vengono ora letti SEMPRE da `data/game_data/classes/*.json` (via
`game_data.get_class()`), mai da una tabella Python. In precedenza esisteva `_CLASS_FEATURES`, una tabella
hardcoded 12 classi × 20 livelli rimasta ferma alle versioni pre-audit: bug reale confermato (non solo problema
architetturale) — ogni level-up mostrava al giocatore nomi feature superati (es. Guerriero lv1 "Secondo Respiro"
invece di "Recupera Energie", Mago lv20 "Firma degli Incantesimi" invece di "Incantesimi Personali", Barbaro lv3
"Percorso Primordiale" invece di "Cammino Primordiale"), anche se la sezione "Abilità di Classe" in Combattimento
(già JSON-based) mostrava i nomi corretti. Vedi "Note Importanti" per il changelog completo del fix.

`StepType` enum (tutti i tipi di step gestiti nel dialog level-up):
- `HP_GAIN` — sempre, scelta giocatore (max/media/manuale)
- `PROFICIENCY_BONUS_UP` — automatico, solo info
- `ASI` — ai livelli PHB; include opzione Talento dal Lv1 in poi
- `FEATURE_AUTO` — feature base o sottoclasse letta dal JSON per questo livello esatto, solo info
- `SUBCLASS_CHOICE` — rilevato da `cls_data["subclass_choice_level"] == new_level` (non più "scegli" in una stringa)
- `EXPERTISE` — Ladro (lv1/6) e Bardo (lv3/10), livelli in `_EXPERTISE_LEVELS`; nome feature ("Maestria") letto dal JSON via `_find_feature_name()`
- `INVOCATION` — Warlock, livelli/totali cumulativi in `_INVOCATIONS_TOTAL_BY_LEVEL` (2/3/4/5/6/7/8 a lv 2/5/7/9/12/15/17); `data["total"]`
- `METAMAGIC` — Stregone, conteggi in `_METAMAGIC_COUNT_BY_LEVEL` (2 a lv3, +1 a lv10/17); `data["count"]`
- `PACT_CHOICE` — rilevato da "dono del patto" nel nome JSON della feature base a questo livello
- `SPELL_LEARN` — emesso per Bardo/Stregone/Warlock/Ranger (delta da `_SPELL_LEARN_DELTA`, invariato) e per Bardo
  "Segreti Magici" (lv10/14/18, `_SEGRETI_MAGICI_LEVELS`, any_class=True); `data={"count", "max_level",
  "any_class"}`. Handler in profilo_tab: dropdown spell filtrate per max_level+already_known; Segreti Magici:
  picker (classe_dd→spell_dd reattivo). Salvataggio via `_save_known_spell()` → `upsert_known_spell()`

**Meccaniche ricorrenti registrate una sola volta nel JSON** (Metamagia, Suppliche Occulte, Segreti Magici,
Maestria): il nome/descrizione si legge comunque dal JSON tramite `_find_feature_name()` (cerca per substring nel
nome, base+sottoclasse), ma il livello di innesco e il conteggio sono piccole tabelle numeriche in
`level_manager.py` — stessa categoria di `ASI_LEVELS`/`_SPELL_LEARN_DELTA` (progressioni PHB universali e stabili,
non testo/nomi).

**Scelta di scope deliberata**: i promemoria puramente informativi che il vecchio `_CLASS_FEATURES` mostrava con un
numero crescente senza una vera scelta del giocatore (es. "Attacco Furtivo (Nd6)", "Ispirazione Bardica →
d8/d10/d12", "Distruggi Non Morti (CR N)", "Ki (punti = livello)") non sono stati ricostruiti: richiederebbero
altre tabelle numeriche per-livello mai verificate contro il manuale in questa sessione. Il level-up mostra quindi
meno testo puramente decorativo ma tutto tracciabile a una fonte verificata (JSON), invece di reintrodurre dati non
controllati. Nessuna feature con scelta reale del giocatore è stata rimossa.

**Miglioramento collaterale**: `get_level_up_steps()` ha un nuovo parametro opzionale `subclass: str = ""` (passato
da `profilo_tab.py` come `c.subclass`) che permette di includere le feature di sottoclasse nel punto esatto del
JSON in cui compaiono, con il nome reale (es. Barbaro Combattente Totemico lv6 → "Aspetto della Bestia"), invece
del vecchio placeholder generico sempre uguale ("Capacità del Percorso Primordiale") che appariva a prescindere
dalla sottoclasse scelta.

`get_level_up_steps(class_name, new_level, old_pb, new_pb, subclass="")` → `list[LevelStep]`

**Audit Phase 3 — bug reali trovati e corretti il 2026-07-10** (task "Audit level-up: Barbaro" e "Audit level-up:
Bardo", prima di procedere classe per classe — questi erano bug nella logica generica, non specifici di una singola
classe):
1. **Filtro "maestria"/"perizia" incondizionato**: escludeva dai `FEATURE_AUTO` qualunque feature con questi
   termini nel nome, per QUALSIASI classe/livello — ma "Maestria negli Incantesimi" del Mago (lv18, 2 incantesimi
   lanciabili gratis) non ha nulla a che vedere con l'Expertise di Ladro/Bardo e spariva silenziosamente dal
   level-up. Fix: il filtro ora si applica solo quando `new_level in _EXPERTISE_LEVELS.get(class_name, set())`.
2. **"Segreti Magici" rilevato con un set fisso di livelli** `{10,14,18}` valido solo per la progressione BASE del
   Bardo: la sottoclasse Collegio della Conoscenza concede la stessa meccanica ("Segreti Magici Aggiuntivi", 2
   incantesimi da qualsiasi classe) al lv6, che spariva senza essere sostituita da nessuno step. Fix: se il livello
   non è nel set fisso, si cerca dinamicamente una feature di sottoclasse con "segreti magici" nel nome a quel
   livello esatto.
3. **`_SPELL_LEARN_DELTA` errato per Bardo e Stregone** (Ranger e Warlock erano già corretti): verificato leggendo
   visivamente (pdftoppm, non pdftotext) la colonna "Incantesimi Conosciuti" delle tabelle di classe PHB IT —
   pag.53 Bardo, pag.103 Ranger, pag.108 Stregone, pag.114 Warlock.
   - Bardo: mancavano i salti di **+2** (non +1) ai livelli 10/14/18 (dove il manuale concede 2 Segreti Magici alla
     volta) e c'era un +1 di troppo al lv19 (il manuale non concede nulla quel livello). Il totale finale a lv20
     (19 invece di 22) nascondeva parzialmente l'errore, ma ogni livello da 10 a 19 mostrava il conteggio
     sbagliato.
   - Stregone: c'era un +1 di troppo al lv14 (il manuale non concede nulla quel livello) e mancava il +1 al lv17.
     Il totale finale a lv20 coincideva per compensazione (15=15) ma i livelli 14-17 erano sbagliati.
   - Tabelle corrette: `"Bardo": {2:1,3:1,4:1,5:1,6:1,7:1,8:1,9:1,10:2,11:1,13:1,14:2,15:1,17:1,18:2}`, `"Stregone": {2:1,3:1,4:1,5:1,6:1,7:1,8:1,9:1,10:1,11:1,13:1,15:1,17:1}`.
   - Verificate nella stessa sessione anche le tabelle di slot incantesimo
     (`_FULL_CASTER_SLOTS`/`_HALF_CASTER_SLOTS`/`_WARLOCK_SLOTS` in `character_repo.py`) e `_max_spell_level_for()`
     contro le stesse 4 pagine: tutte già corrette, nessuna modifica necessaria.

### Checklist Audit Level-Up (Phase 3, task per classe)
> Stesso processo di verifica delle Checklist precedenti: lettura di `classes/*.json`, esecuzione di
> `get_level_up_steps()` su tutti i livelli 1-20 e tutte le sottoclassi, confronto dei valori numerici (ASI, slot,
> risorse, progressioni "conosciuti") contro le pagine del manuale quando esiste una tabella dedicata.

- [x] Barbaro ✅ (2026-07-10 — nessun bug specifico di classe; struttura Furia/Difesa Senza Armatura/Movimento Veloce già corrette da audit precedenti, ASI standard 4/8/12/16/19 confermato)
- [x] Bardo ✅ (2026-07-10 — vedi i 3 bug generici sopra, trovati proprio durante questo task; tabella slot incantesimo e ASI standard confermate corrette contro pag.53)
- [x] Chierico ✅ (2026-07-10 — confrontato riga per riga contro la tabella di classe a pag.57: tutti e 7 i domini
  emettono le feature ai lv1/2/6/8/17 attesi, ASI standard confermato, i tre "aumenti" di Incanalare Divinità
  (1→2→3 riposi) e le soglie di Distruggere Non Morti restano correttamente solo in prosa nella feature che li
  descrive, senza step separati — stessa convenzione già documentata per Critico Brutale del Barbaro, non un bug)
- [x] Druido ✅ (2026-07-10 — **bug reale trovato e corretto**: "Forma Selvatica Migliorata", elencata
  esplicitamente come Privilegio ai lv4/8 nella tabella di classe a pag.65, non veniva mostrata nel level-up perché
  un audit precedente l'aveva rimossa come feature JSON in favore della sola tabella dati `wild_shape_forms` — il
  level-up di un Druido a quei livelli mostrava SOLO l'ASI. Aggiunto un nuovo step dedicato in
  `get_level_up_steps()` che legge `wild_shape_forms` e genera l'etichetta (es. "Forma Selvatica Migliorata (GS max
  1/2 — nessuna velocità di volare)") — nessun dato nuovo inventato, solo la tabella già verificata resa visibile
  al momento giusto. ASI standard e Circolo Druidico lv2/6/10/14 (entrambi i circoli) confermati corretti.)
- [x] Guerriero ✅ (2026-07-10 — ASI custom `{4,6,8,12,14,16,19}` confermato esatto contro pag.71; le 3 sottoclassi
  emettono le feature ai livelli attesi (Campione/Cavaliere Mistico: 3/7/10/15/18; Maestro di Battaglia: 3/7/10/15,
  senza feature al 18° — confermato che è corretto così anche nel manuale, il Maestro di Battaglia non ha un
  privilegio di livello 18); tabella `spell_progression` del Cavaliere Mistico riverificata riga per riga contro
  pag.75 ("Incantesimi del Cavaliere Mistico") — **100% corretta**, nessuna discrepanza. **Gap reale trovato, NON
  corretto in questa sessione** (fuori scope per un fix mordi-e-fuggi, richiede design UI dedicato):
  `spell_progression` esiste sia per Cavaliere Mistico (Guerriero) sia per Mistificatore Arcano (Ladro, vedi task
  Ladro) e contiene `spells_known`/`cantrips_known` per livello, ma **nessun codice in `level_manager.py` genera
  mai uno step SPELL_LEARN basato su questa tabella** — un personaggio con queste sottoclassi non viene mai
  invitato a scegliere nuovi incantesimi/trucchetti al level-up, nonostante il dato sia già verificato e pronto. Il
  fix richiederebbe: (1) rilevare il delta di `spells_known`/`cantrips_known` tra livello corrente e precedente
  nella sottoclasse attiva, (2) un nuovo modo di filtrare la lista incantesimi per "Mago" (non per la classe del
  personaggio, che è Guerriero/Ladro) con vincoli aggiuntivi per il Cavaliere Mistico (2 dei 3 incantesimi di 1°
  livello devono essere Abiurazione/Invocazione; quelli imparati a lv8/14/20 possono essere di qualsiasi scuola),
  (3) UI dedicata in `profilo_tab.py` per questo caso — nessuna delle strutture dati esistenti
  (`_SPELL_LEARN_DELTA`, gli handler in profilo_tab per Bardo/Stregone/Warlock/Ranger) è direttamente riusabile
  perché quelle presumono che la classe del personaggio SIA la classe incantatrice, mentre qui è la sottoclasse a
  portare la capacità. Segnalato come TODO dedicato più sotto.
- [x] Ladro ✅ (2026-07-10 — ASI custom `{4,8,10,12,16,19}` confermato esatto contro pag.77; le 3 sottoclassi
  (Furfante, Assassino, Mistificatore Arcano) emettono le feature ai livelli attesi (3/9/13/17), Maestria/Expertise
  ai lv1/6 confermata; stesso gap del Cavaliere Mistico per il level-up incantesimi del Mistificatore Arcano, vedi
  TODO dedicato — non duplicato qui)
- [x] Mago ✅ (2026-07-10 — confrontato riga per riga contro pag.82: ASI standard confermato, tutte e 8 le scuole
  emettono le feature ai lv2(x2)/6/10/14 attesi, "Maestria negli Incantesimi" (lv18) ora mostrata correttamente
  grazie al fix generico di questa sessione, "Incantesimi Personali" (lv20) presente per tutte le scuole)
- [x] Monaco ✅ (2026-07-10 — **2 bug reali trovati e corretti**, stesso pattern del Druido: (1) "Movimento Senza
  Armatura Migliorato" (lv9, capacità di muoversi su superfici verticali/acqua) era solo una frase incollata dentro
  la description della feature di lv2 invece di una feature JSON a sé — spostata in una nuova feature dedicata a
  `monaco.json` lv9 (testo riusato identico, nessuna invenzione), confermato contro pag.90; (2) Via dei Quattro
  Elementi non aveva MAI uno step ai lv6/11/17 nonostante il manuale (pag.93, "Discepolo degli Elementi") dica
  esplicitamente "Apprende una disciplina elementale aggiuntiva a sua scelta al 6°, 11° e 17° livello" — le altre
  due tradizioni (Mano Aperta, Ombra) hanno feature nominate a quei livelli, questa viveva solo nell'array
  `disciplines` mai controllato da `get_level_up_steps()`. Aggiunto un promemoria informativo (FEATURE_AUTO) ai
  lv6/11/17 per questa sottoclasse — **nota**: non è un picker interattivo per scegliere la disciplina specifica,
  richiederebbe una nuova UI dedicata; vedi TODO. ASI standard confermato, tutte e 3 le tradizioni verificate
  lv1-20.)
- [x] Paladino ✅ (2026-07-10 — **bug reale trovato e corretto, correzione di un errore di una sessione
  precedente**: "Punizione Divina Migliorata" (lv11) era stata rimossa il 2026-07-07 credendola inesistente nel
  manuale, ma la tabella di classe a pag.96 E un paragrafo dedicato a pag.98 (letti con `pdftoppm`, non `pdftotext`
  che corrompeva il testo) confermano che la feature è reale — ripristinata in `paladino.json` con il testo esatto
  del manuale. "Aure Migliorate" (lv18) correttamente confermata NON necessaria come feature separata (è solo
  l'espansione di raggio già scritta in ciascuna aura). ASI standard 4/8/12/16/19 confermato contro pag.96; tutti e
  3 i giuramenti verificati lv1-20, Incanalare Divinità/Salute Divina/subclass choice a lv3 confermati.)
- [x] Ranger ✅ (2026-07-10 — nessun bug trovato. Tabella pag.103 verificata riga per riga con `pdftoppm`: ASI
  standard 4/8/12/16/19, PB standard, `_SPELL_LEARN_DELTA["Ranger"]` (già corretto in questa sessione) confermato
  identico alla colonna "Incantesimi Conosciuti" (2/3/3/4/4/5/5/6/6/7/7/8/8/9/9/10/10/11/11), slot incantesimo già
  confermati corretti. Le voci di tabella "Nemico Prescelto Migliorato" (lv6/14) ed "Esploratore Nato Migliorato"
  (lv6/10) verificate a pag.104: sono solo promemoria della scelta aggiuntiva già descritta per intero nel testo
  delle feature base di lv1 — nessun paragrafo dedicato separato nel manuale, quindi correttamente NON generate
  come step distinti, stesso pattern di "Aure Migliorate" del Paladino. Sottoclassi Cacciatore/Signore delle Bestie
  confermate a lv3/7/11/15 con le opzioni corrette.)
- [x] Stregone ✅ (2026-07-10 — nessun bug specifico di classe trovato. Tabella pag.108 verificata riga per riga con
  `pdftoppm`: ASI standard 4/8/12/16/19, Metamagia a 3(x2)/10(+1)/17(+1) confermata, Punti Stregoneria (= livello
  personaggio da lv2 in poi) e slot incantesimo già confermati corretti in audit precedenti,
  `_SPELL_LEARN_DELTA["Stregone"]` (già corretto in questa sessione) riverificato cifra per cifra contro la colonna
  "Incantesimi Conosciuti" — cumulativo esatto a tutti i 20 livelli. Origine Stregonesca (Discendenza
  Draconica/Magia Selvaggia) confermata a lv1/6/14/18 per entrambe. **Trovato un gap architetturale cross-cutting
  (non specifico di questa classe)**: la crescita di "Trucchetti Conosciuti" non genera mai uno step al level-up
  per nessuna delle 4 classi che la usano — vedi nuovo TODO dedicato più sotto.)
- [x] Warlock ✅ (2026-07-10 — **bug reale trovato e corretto**: la tabella di classe a pag.114 elenca
  esplicitamente "Arcanum Mistico (6° livello)" al lv11, "(7° livello)" al lv13, "(8° livello)" al lv15, "(9°
  livello)" al lv17 come 4 righe Privilegi distinte — a differenza dei casi Ranger/Paladino (dove la voce di
  tabella era solo un promemoria di una scelta già interamente descritta altrove), qui ogni riga rappresenta una
  VERA nuova scelta (un incantesimo diverso per ciascun livello di slot sempre più alto). La feature JSON "Arcanum
  Mistico" esisteva solo al lv11 (prosa che descrive i 3 incrementi successivi, stessa convenzione di ASI_LEVELS) —
  il level-up ai lv13/15/17 non mostrava assolutamente nulla oltre ai PF. Aggiunto un promemoria informativo
  dedicato (FEATURE_AUTO) a questi 3 livelli — **nota**: non è un picker interattivo per scegliere l'incantesimo
  specifico, richiederebbe una nuova UI dedicata (filtro per livello ESATTO, non "livello massimo" come gli altri
  SPELL_LEARN); vedi TODO. ASI standard, PACT_CHOICE lv3, Suppliche Occulte 2/5/7/9/12/15/17 e
  `_SPELL_LEARN_DELTA["Warlock"]` (già corretto in questa sessione) tutti riverificati contro pag.114 — corretti.
  Regressione completa (12 classi × tutte le sottoclassi × lv1-20) rieseguita dopo il fix: zero eccezioni.)
- [x] **Risorse razziali per livello** ✅ (2026-07-10 — verificato `get_race_resource_defaults()` su tutte le 9
  razze/14 combinazioni razza-sottorazza: solo 4 tratti sono risorse a consumo limitato con soglie di livello —
  Dragonide "Arma a Soffio" (1/riposo breve, costante da lv1, solo il danno scala per livello — già confermato
  separatamente), Mezzorco "Tenacia Implacabile" (1/riposo lungo da lv1, nessuna scala), Elfo Oscuro (Drow) "Magia
  Drow" (Luminescenza da lv3, Oscurità da lv5, entrambe 1/riposo lungo), Tiefling "Eredità Infernale" (Intimorire
  Infernale da lv3, Oscurità da lv5, entrambe 1/riposo lungo) — tutte le soglie `min_level` testate con script
  automatizzato contro i valori attesi dal manuale (già confermati nei rispettivi audit JSON razza), nessuna
  discrepanza. Confermato che nessun'altra razza (Umano/Nano/Halfling/Gnomo/Mezzelfo) ha tratti che richiedano
  tracciamento a risorsa. Confermato che la sincronizzazione (`init_class_resources()`, che include sempre anche le
  risorse razziali) viene già chiamata sia ad ogni apertura della tab Combattimento sia a ogni level-up/level-down
  — nessun rischio di risorsa razziale "congelata" al vecchio livello, stesso fix già applicato l'8/9 luglio per le
  risorse di classe. **Trovato un gap reale ma non specifico della logica per-livello**: gli incantesimi di Magia
  Drow/Eredità Infernale (Luminescenza, Oscurità, Intimorire Infernale) non vengono mai aggiunti a `known_spells`
  né sono visualizzabili in `spells_view.py` per un personaggio di classe non incantatrice (la sezione Magia si
  nasconde interamente se `spellcasting_ability` è vuoto) — segnalato come nuovo TODO dedicato, richiede
  progettazione (incantesimi di razza indipendenti dalla classe), non un fix mordi-e-fuggi.)

### `data/game_data/feats.json` e `invocations.json`
File popolati completamente (42 feat, 32 invocazioni PHB). Schema `feats.json`:
- `ability_bonus`: `int` — bonus a una stat (es. +1 CHA) oppure `null`
- `choose_one`: `bool` — se `true`, il giocatore sceglie la stat al moment del level-up (dropdown `feat_bonus_dd`)
- `other_bonuses`: `dict` — bonus non-stat (es. `{"initiative": 5}` per Allerta, `{"speed": 3}` per Mobile);
  applicati su `character.initiative_bonus` / `character.speed`; sempre reversibili via `bonus_data` +
  `remove_feat_with_bonuses()`

`GameDataLoader` espone:
- `get_feats()` / `get_feat_names()` / `get_feat(name)` — caricamento lazy da `feats.json`
- `get_invocations(warlock_level)` / `get_invocation_names(warlock_level)` — filtrato per `prerequisite_level`

**`proficiency_type` valori DB estesi** (oltre ai precedenti):
- `"feat"` — talento scelto all'ASI
- `"metamagic"` — opzione metamagia Stregone
- `"invocation"` — invocazione occulta Warlock
- `"cantrip"` — trucchetto (es. Alto Elfo via wizard)

### `data/game_data/equipment/` — 6 file (nuovo, 2026-07-10; diviso in file separati lo stesso giorno)
Trascrizione integrale del Capitolo 5 "Equipaggiamento" del manuale italiano (PHB IT p.143-159), letta visivamente
dalle pagine del PDF renderizzate come immagini (`pdftoppm`) — **non** tramite `pdftotext`, risultato inaffidabile
su queste tabelle (OCR confondeva lettere/numeri: "5mo"→"Smo", "10mo"→"lOmo", "For 13"→"For13", ecc.). Nessun dato
è stato indovinato: ogni valore è stato letto direttamente dall'immagine della pagina corrispondente.

**Nato come un unico `equipment.json`, diviso in 6 file lo stesso giorno** su richiesta di Davide, per coerenza con
la granularità già usata altrove nel progetto (un file per classe/razza/background, non un unico blob) e per
rendere possibile spuntare l'audit riga-per-riga un file alla volta invece che tutto insieme:
- `weapons.json` — regole, proprietà, armi speciali/argentate/improvvisate, le 4 liste (`semplici_mischia`, `semplici_distanza`, `guerra_mischia`, `guerra_distanza`)
- `armor.json` — regole, `leggere`/`medie`/`pesanti`/`scudi`, tempi indossare/togliere
- `adventuring_gear.json` — 99 oggetti, 42 descrizioni con regole dedicate, capienza contenitori, contenuto esatto dei 7 pacchetti
- `tools.json` — 37 strumenti con campo `category`
- `mounts_and_vehicles.json` — cavalcature, finimenti/veicoli da tiro, imbarcazioni
- `economy.json` — ricchezza di partenza per classe, valuta, merci, stile di vita, vitto e alloggio, servizi

Ogni file ha un `_source_note` (stesso testo di provenienza in tutti e 6) e un `_source` per sezione che cita pagina/tabella del manuale.

**Ogni arma ha ora due campi espliciti `"category"` (`"semplice"`|`"guerra"`) e `"range_type"`
(`"mischia"`|`"distanza"`)** oltre a vivere nella lista annidata corrispondente — aggiunti su richiesta di Davide
per permettere filtri incrociati (es. "tutte le armi da mischia a prescindere da semplice/guerra", utile per regole
come lo stile di combattimento Duellare) senza dover attraversare le 4 liste a mano.

**Deliberatamente escluso da questa versione** (scelta esplicita di Davide, 2026-07-10): la tabella d100 "Oggetti
Insoliti" (100 cimeli di ambientazione, PHB IT p.160-161) — nessun effetto meccanico, solo flavor da tirare alla
creazione del personaggio. Vedi TODO per riprenderla in futuro.

**Convenzione costo**: `{"quantity": N, "currency_type": "gold"|"silver"|"copper"|"electrum"|"platinum"}`, stessa
convenzione già usata in `backgrounds/*.json → equipment` (`item_type: "currency"`). **Convenzione peso**:
`weight_kg` come float (`null` se il manuale non indica un peso, es. "Anello con Sigillo", "Fionda").

**`GameDataLoader` — metodi esposti** (uno o più per file, tutti lazy/cachati indipendentemente):
- `get_weapons()` → dict grezzo di `weapons.json`; `get_weapon(name)` → dict di una singola arma per nome esatto
  (case-insensitive); `get_weapon_names(category=None, range_type=None)` → nomi filtrabili per categoria e/o
  gittata
- `get_armor()`, `get_adventuring_gear()`, `get_tools()`, `get_mounts_and_vehicles()`, `get_economy()` → dict grezzo del rispettivo file
- `get_equipment()` → dict con tutte e 6 le sezioni unite sotto le chiavi
  `weapons`/`armor`/`adventuring_gear`/`tools`/`mounts_and_vehicles`/`economy` (comodo per ispezione, i getter
  specifici sono da preferire nell'uso normale perché caricano solo il file richiesto)
- `get_tool_names(category)`, `get_tool_categories()`, `get_tool_category_label(key)` — unica fonte per le scelte di strumenti (vedi sotto)

**Ancora non consumato dalla UI** — tutti i getter sopra sono pronti ma nessuna view li chiama ancora, salvo il
caso strumenti (sotto). `WEAPONS_BY_CATEGORY` in `config/settings.py` resta per ora la fonte usata da
wizard/form/level-up per i Dropdown arma (contiene solo nomi, non i dati completi costo/danni/proprietà già
disponibili in `weapons.json`).

**Correzione in due tempi di `ARTISAN_TOOLS`/`MUSICAL_INSTRUMENTS`/`GAMING_SETS` (2026-07-10)** — scoperte
confrontando queste tre liste in `config/settings.py` con la tabella "Strumenti" reale (p.154) durante la
trascrizione: contenevano nomi tradotti dall'inglese mai confrontati col manuale ("Strumenti da Birraio"→"Scorte da
Mescitore", "Strumenti da Muratore"→"Strumenti da Costruttore", "Strumenti da Cuoco"→"Utensili da Cuoco",
"Strumenti da Vetraio"→"Strumenti da Soffiatore", "Strumenti da Scalpellino"→"Strumenti da Intagliatore",
"Strumenti da Calligrafo"→"Scorte da Calligrafo"; 4 voci inesistenti nel manuale italiano rimosse: "Strumenti da
Fabbricante di Archi", "Strumenti da Sarto", "Strumenti da Calderaio", "Strumenti da Armaolo"; 3 voci reali
aggiunte: "Scorte da Alchimista", "Strumenti da Cartografo", "Strumenti da Inventore". Stesso tipo di correzione
per `MUSICAL_INSTRUMENTS` ("Batacchio"/"Piffero"/"Tamburello"/"Tromba"→"Ciaramella"/"Corno"/"Dulcimer"/"Flauto di
Pan"/"Tamburo") e `GAMING_SETS` ("Carte da Gioco"→"Mazzo di Carte", "Tre Draghi"→"Tre Draghi al Buio").

**Un primo passaggio ha corretto solo i nomi sul posto**, lasciando le 3 liste (+
`TOOL_CATEGORIES`/`TOOL_CATEGORY_LABEL`) come costanti Python parallele — Davide ha fatto notare che questo era
esattamente lo stesso errore di duplicazione già eliminato in questa sessione per `RACE_DATA` e le 7 costanti di
classe. **Fix definitivo**: le 5 costanti rimosse da `config/settings.py` (sostituite da un commento esplicativo);
`tools.json → items` ha un campo `"category"` per voce (`"strumenti_artigiano"` 17 voci, `"strumenti_musicali"` 10
voci, `"giochi"` 4 voci, `"strumenti_vari"` per arnesi/borse/strumenti da navigatore/trucchi camuffamento — nomi
senza più il prefisso di categoria inserito nella prima trascrizione, es. "Strumenti Musicali:
Ciaramella"→"Ciaramella"). Aggiornati i 2 call site reali (`wizard_view.py`/`manual_form.py → _bg_tool_choices()`).

**Eliminazione di `tags.json` (2026-07-10, stessa sessione)** — Davide ha chiesto se avesse ancora senso tenere
`tags.json` (espansione di tag tipo `#armi_semplici`/`#armature_leggere` in liste di nomi) ora che esiste
`equipment.json`. Verifica: `expand_tags()`/`get_tag()` (gli unici due metodi che leggevano `tags.json`) **non
erano mai chiamati da nessun codice reale**, solo nel docstring di esempio del modulo; i campi
`armor_proficiencies`/`weapon_proficiencies` nei 12 file classe che contenevano questi tag non erano a loro volta
mai letti da nessun modulo Python — dato morto collegato a codice morto. Il contenuto era anche **sbagliato**: nomi
mai verificati contro il manuale ("Clava", "Falce", "Bastone", "Lancia da guerra", "Flagello", "Sciabola",
"Martello" non esistono nel PHB italiano) e un **bug meccanico reale**, non solo di nome — `#armature_medie`
includeva "Cotta di maglia" e "Corazza ad anelli", che nella tabella verificata di `armor.json` sono invece
armature **pesanti**. Rimossi: `data/game_data/tags.json`, i metodi `expand_tags()`/`get_tag()`/`_ensure_tags()` da
`GameDataLoader` (mai usati). Nei 12 file classe, i valori `"#armi_semplici"`/`"#armi_da_guerra"` in
`weapon_proficiencies` sono stati sostituiti con `"semplice"`/`"guerra"` (stessi valori del campo `"category"` in
`weapons.json`), e `"#armature_leggere"`/`"#armature_medie"`/`"#armature_pesanti"`/`"#scudi"`/`"#armature_tutte"`
in `armor_proficiencies` con `"leggere"`/`"medie"`/`"pesanti"`/`"scudi"` (`#armature_tutte` espanso a
`["leggere","medie","pesanti"]`); corrette anche 8 voci con nome arma specifico ma case sbagliato (es. "Spada
corta"→"Spada Corta", "Balestra a mano"→"Balestra a Mano") in monaco/ladro/bardo/mago/stregone. **Nota (verificato in una revisione successiva)**: `bonus_proficiencies` delle sottoclassi in
`chierico.json`/`bardo.json`, segnalato qui come fuori scope con gli stessi tag `#...` mai letti da nessun
codice, non li contiene più — risolto in una sessione successiva non documentata qui. Verificato:
`py_compile` su tutto l'albero; tutti i 12 file classe restano JSON validi;
`get_weapon_names()`/`get_tool_categories()` testati end-to-end con gli stessi identici risultati di prima del
refactor.

---

### Multiplayer, passo 2 — "Modello mondo, senza rete" (2026-08-05)

Vedi `dnd_app/docs/multiplayer_design.md` per il progetto completo e
`dnd_app/docs/changelog_storico.md` per il changelog dettagliato di questo
passo. Qui solo l'elenco dei moduli e cosa espongono.

**`data/repositories/world_repo.py`** — CRUD `worlds`/`world_members` +
giornale eventi. `create_world(name, owner_device_id, owner_display_name,
description="")` crea il mondo E registra l'owner tra i membri in
un'unica transazione. `join_world_by_code(join_code, device_id,
display_name)` è idempotente: un secondo ingresso dello stesso `device_id`
ritorna il membro esistente, non ne crea uno nuovo. `append_event(...)` /
`get_events_since(world_id, since_seq, limit=200)` / `get_latest_seq(...)` —
la sincronizzazione incrementale che userà il passo 4. `generate_join_code()`
— 6 caratteri, alfabeto senza `0/O/1/I/L`. `rename_world`/`update_member_role`/
`remove_member` sono scritture dirette **non pensate per essere chiamate
dalla UI**: la validazione dei permessi vive solo in `core/world_backend.py`.

**`core/world_permissions.py`** — puro, no Flet, no DB. `can_perform(role,
command_kind) -> bool`, fail-closed per comandi sconosciuti (owner incluso).
`OWNER_ONLY_COMMANDS`/`MASTER_AND_OWNER_COMMANDS` codificano l'elenco chiuso
di §7 del design doc. `FORBIDDEN_CHARACTER_FIELDS`/
`CHANGE_REQUEST_ALLOWED_FIELDS` — campi di `characters` vietati a chiunque
non sia il giocatore, e il sottoinsieme negoziabile con una richiesta di
modifica (§7.1, non ancora usata: serve il passo 3).

**`core/world_backend.py`** — `WorldBackend` (ABC) + `LocalBackend` (unica
implementazione fino al passo 4). `LocalBackend.send_command(world_id,
actor_device_id, kind, payload, target_type="", target_id="") ->
CommandResult`: risolve SEMPRE il ruolo del mittente da `world_members` (mai
fidato dal chiamante), valida con `world_permissions.can_perform`, applica
via l'handler registrato, scrive l'evento. `register_handler(kind)` —
decoratore per aggiungere comandi senza toccare la classe (Open/Closed); i
passi successivi lo useranno per le azioni di §7 sulle istanze di
personaggio. Handler operativi oggi: `world.rename`,
`world.join_code.regenerate`, `member.promote`, `member.demote`,
`member.kick` (guardia: l'owner non si espelle), `world.transfer_ownership`,
`world.delete` (nessun evento scritto: CASCADE lo farebbe sparire subito).

**`ui/device_identity.py`** — `resolve_device_id(page) -> str` (async, va
chiamata via `page.run_task`). Desktop/mobile: `app_settings["device_id"]`,
stabile per installazione. Web: tenta `ft.SharedPreferences` (avvolto in
try/except — è un controllo `Service`, stessa categoria di `ft.FilePicker`
già documentato come rotto in web mode in `regole_flet_api.md`, **non ancora
verificato empiricamente per SharedPreferences**), ricade su un id tenuto
come attributo su `page` (sopravvive alla sessione, si perde al refresh).

**`ui/views/world/world_view.py`** — `WorldsView(on_back_to_home,
on_toggle_theme=None, theme_preference="system")`. Risolve l'identità in
`did_mount()` via `page.run_task`, poi elenco mondi (`_render_list`) o
dettaglio di uno (`_render_detail`) secondo `self._current_world`. Ogni
pulsante di azione (promuovi/retrocedi/espelli/rinomina/elimina) è mostrato
solo se `world_permissions.can_perform(my_role, ...)` è vero — mai un
controllo hardcoded sul ruolo. Tutte le mutazioni passano da
`self.backend.send_command(...)`, mai una scrittura diretta su `world_repo`.

**Refresh mirati per le 4 sezioni "calde" (2026-08-27)**: Membri/
Combattimento live/Note condivise/Bottino condiviso vivono ora in
`ft.Container` persistenti (`self._members_container`/
`_live_combat_container`/`_shared_notes_container`/`_shared_loot_container`),
sempre presenti nell'albero prodotto da `_render_detail()` (`.visible` ne
governa la presenza, mai più un append condizionale). Solo 2 azioni locali
rewired su ~15 punti di chiamata di `_refresh_detail()`:
`_member_command()` → `_update_members_section()`, `_do_claim_loot()` →
`_update_shared_loot_section()` — le restanti ~13 azioni (rinomina, mappe,
richieste, hosting, azioni remote...) restano sul rebuild completo. Il tick
di sync periodico (`_async_redraw_detail`) è **invariato**: ricostruisce
ancora tutto tramite `_render_detail()`. Stesso pattern in
`ui/views/master/master_encounter_view.py::MasterEncounterView`: nuovo
`_update_member_card(*, member_id=None, character_id=None)` per
danno/cura/condizione (rilegge sempre i dati freschi dal DB), MAI per
modifica iniziativa (riordina la lista) o rimozione membro (cambia la
lunghezza) — quelle restano su `refresh()` completo, così come il tick di
sync `_async_sync_redraw`. Dettaglio completo in `changelog_storico.md`,
voce "Refresh mirati invece di rebuild aggressivo... (2026-08-27, v0.3.19)".

**Refresh mirati, Fase 2 (2026-08-27/28, v0.3.20)**: altre 3 sezioni
containerizzate allo stesso modo — `_hosting_section`
(`_update_hosting_section()`), `_shared_maps_section`
(`_update_shared_maps_section()`), `_pending_change_requests_section`
(`_update_pending_requests_section()`). **Deliberatamente non toccate**:
`_remote_actions_section`/`_pending_rejoin_requests_section` condividono
lo stesso funnel `_send_remote_command()` (usato anche per PE/danno/cura/
condizione/proponi-modifica) — un'azione lì può toccare l'una o l'altra
sezione a seconda del comando, quindi ricablare solo a una avrebbe
rischiato dati vecchi nell'altra; restano sul `_refresh_detail()` completo.
Stesso giro: `ui/views/master/master_npc_list_view.py` (`MasterNpcListView`)
e `ui/views/master/master_encounter_list_view.py`
(`MasterEncounterListView`) hanno ora una `ScrollMemoryColumn` (prima
assente) + un helper di riga mirato (`_sync_npc_row()`/
`_remove_encounter_row()`, cerca per `data=<id>` taggato sul controllo
della riga); `ui/views/master/master_loot_view.py` (`MasterLootView`)
ha un nuovo `_update_entry_card()` per "Modifica Voce" non monetaria
(sicuro perché l'elenco è ordinato per data di creazione, mai toccata da
un aggiornamento in posto). Dettaglio completo in `changelog_storico.md`,
voce "Refresh mirati, Fase 2... (2026-08-27/28, v0.3.20)".

**`ui/views/master/master_treasure_dialog.py`** — dialog "Genera Tesoro"
(`show_treasure_generator_dialog(page, world_id="", device_id="")`), tira
tesoro individuale/cumulo per fascia di CR (`core/treasure_generator.py`) +
Cimelio (1d100). **Bug fix (2026-08-27, v0.3.21)**: "Aggiungi
all'inventario" scriveva sempre in locale via `character_repo` diretto,
anche con un `world_id` di mondo condiviso — a differenza di "Assegna…"
(instrada su `CMD_LOOT_ASSIGN`), quindi non generava l'evento che fa
arrivare l'aggiunta al tick di sync/a una scheda personaggio aperta su un
altro dispositivo. Ora `_on_add_to_inventory` instrada anch'esso su
`CMD_LOOT_ASSIGN` quando `world_id` è valorizzato (stesso
`_resolve_backend()` di `master_loot_assign_dialog.py`), scrittura diretta
solo in modalità locale. Dettaglio completo in `changelog_storico.md`.

**`core/character_instances.py`** (Multiplayer passo 3, 2026-08-05) — no
Flet, ma usa repository/DB direttamente (come `world_backend.py`).
`InstanceMode = Literal["as_is", "fresh"]`. `create_or_resume_instance(
world_id, local_character_id, owner_device_id, mode) -> InstanceResult`:
`find_existing_instance()` cerca prima una riga `characters` con la terna
esatta (mondo, origine, dispositivo) — se c'è, ritorna con `resumed=True`
senza copiare nulla (§6 "Riprendi" è automatico, `mode` viene ignorato in
quel caso). Altrimenti `_copy_character()` (riusa `character_export`,
introspezione di schema — stesso meccanismo di `.dndchar`) +
`_link_to_world()` (UPDATE diretto delle 3 colonne di collegamento) + se
`mode="fresh"`, `_reset_to_level_one()`. Guardia: `origin.world_id` già
valorizzato → rifiutato, non si crea mai l'istanza di un'istanza.

`_reset_to_level_one(character_id)` — reset completo (non solo la lista
minima del design doc), confermato da Davide: `character_repo.undo_level()`
chiamato una volta per livello da rimuovere (inverte ASI/talenti/competenze
bonus, legge `bonus_data`+`level_obtained` su `character_proficiencies`),
poi livello=1/PE=0/PF ricalcolati con la formula esatta di 1° livello (`max(1,
dado_vita + mod_costituzione)`), indebolimento e stato di sessione/
combattimento azzerati, `diary_entries` svuotate (le `campaign_notes`
restano intatte), inventario/armi/monete azzerati e riassegnati con
`_assign_default_starting_equipment()` (versione non interattiva
dell'assegnazione del wizard: ogni `"type": "choice"` risolve su
`options[0]`, le armi a scelta per categoria su `_weapon_choice_default()`
— piccola duplicazione voluta e commentata dell'algoritmo di
`CreationSharedMixin._init_weapon_choice()`, non importabile da `core/`
perché quel modulo porta `import flet`; i placeholder "(a scelta)" degli
strumenti si risolvono contro le competenze tool già registrate sul
personaggio). Risincronizza slot incantesimo/risorse di classe/CA con le
stesse funzioni di self-healing già usate dal level-up/level-down.

`preview_refresh(instance_id) -> RefreshPreview | None` / `apply_refresh(
instance_id) -> InstanceResult` (§6.1, "Aggiorna il mio foglio", sempre
manuale) — `preview_refresh` legge origine e istanza senza scrivere nulla
(riepilogo prima/dopo per la conferma); `apply_refresh` esporta l'istanza e
reimporta con `mode="overwrite", target_id=origin_id` (o `mode="copy"` se
l'origine è stata eliminata nel frattempo — comportamento esplicito, non un
fallback silenzioso). `import_character()` azzera sempre le colonne mondo
(§14.1), quindi il risultato è sempre un personaggio locale a tutti gli
effetti, mai un'altra istanza.

**`network/protocol.py`** (Multiplayer passo 4, 2026-08-05, prima cartella
popolata di `network/`) — nessuna logica, solo il formato condiviso tra
host e client: `PROTOCOL_VERSION`, `DEFAULT_PORT_RANGE` (8765-8770),
`LONG_POLL_TIMEOUT_S`/`LONG_POLL_INTERVAL_S`, `event_to_dict`/
`event_from_dict`/`world_to_dict`/`member_to_dict`/`member_from_dict`. Un
solo punto di verità per non disallineare host (`host_server.py`), client
(`world_backend.RemoteBackend`) e applicazione della replica
(`world_sync.py`).

**`network/host_server.py`** — `WorldHostServer(world_id, backend=None,
port_range=..., long_poll_timeout=...)`. `start()`/`stop()` gestiscono un
`http.server.ThreadingHTTPServer` (stdlib, `daemon_threads=True`,
`allow_reuse_address=True`) su un thread daemon dedicato; `start()`
genera un nuovo PIN a 6 cifre (`_generate_pin()`) e prova le porte
dell'intervallo in ordine. Stato in memoria, azzerato ad ogni `stop()`:
`self.pin`, `self._tokens` (token → device_id), `self._pending`
(`PendingJoinRequest` in attesa). `list_pending()`/`approve(request_id)`/
`reject(request_id)` sono chiamate dirette (NON rotte HTTP: girano nello
stesso processo della UI del master). Rotte HTTP gestite da
`_RequestHandler` (dispatcher puro, `do_GET`/`do_POST`) che delega alla
logica di dominio su `WorldHostServer` (`world_info`/`handle_join`/
`join_status`/`handle_events`/`handle_command`/`handle_snapshot`/
`handle_leave`) — separazione voluta: quei metodi sono testabili anche
senza socket, passando token/body a mano. `handle_events` implementa
l'attesa lunga con un ciclo che ripolla `world_repo.get_events_since`
ogni `LONG_POLL_INTERVAL_S` (200 ms) tenendo la connessione aperta fino a
un evento o al timeout — non una vera notifica push, nessuna dipendenza
nuova. `handle_join`: dispositivo già membro → token immediato; nuovo →
`PendingJoinRequest` in coda, nessuna riga in `world_members` finché il
master non chiama `approve()` (che a quel punto chiama
`world_repo.join_world_by_code()`, la stessa funzione usata per l'ingresso
locale/web — nessuna duplicazione della logica di ingresso). Anche
`local_ip_hint()` vive qui: apre una connessione UDP verso un indirizzo
pubblico solo per far scegliere al sistema operativo l'interfaccia di
uscita e leggerne l'IP locale, nessun pacchetto inviato davvero.

**`core/world_backend.py` — `RemoteBackend`** (Multiplayer passo 4,
aggiunta allo stesso file di `LocalBackend`/`WorldBackend`) — seconda
implementazione dell'interfaccia, parla HTTP con `http.client` (stdlib)
invece di scrivere sul proprio DB. `check_world()` (verifica
raggiungibilità + versione protocollo), `join()`/`poll_join_status()`
(il ciclo pending → approvato/rifiutato, `JoinOutcome`),
`reconnect_with_token()` (riprova un token esistente via `GET /snapshot`;
fallisce esplicitamente — mai un retry automatico con credenziali scadute
— se l'host è stato riavviato, dato che PIN/token vivono in memoria e si
azzerano a ogni `WorldHostServer.stop()`), `leave()`, `get_snapshot()`.
`send_command`/`fetch_events`/`connection_state` implementano
`WorldBackend` esattamente come `LocalBackend`: un 401 dall'host azzera
`self.token` e riporta `connection_state()` a `"disconnected"`, mai un
errore silenzioso.

**`core/world_sync.py`** (Multiplayer passo 4) — l'unico punto che
combina `RemoteBackend` (trasporto) e `world_repo` (scrittura della
replica): la UI non applica mai un evento da sola.
`apply_event_to_replica(local_world_id, event)` — uno switch su
`event.kind`, sei tipi gestiti (world.rename/member.promote/
member.demote/member.kick/world.transfer_ownership/world.created), un
`kind` sconosciuto viene loggato e ignorato (mai un'eccezione: un client
con versione più vecchia non deve bloccarsi). `sync_replica(remote_backend,
local_world_id, refresh_members=True)` — ciclo incrementale da
`last_synced_seq`, con un refresh completo dei membri via `/snapshot` di
default (più robusto di fidarsi solo degli eventi conosciuti).
`start_lan_join`/`finish_pending_join`/`_finalize_join` — orchestrazione
lato client dell'ingresso: `LanJoinResult` (dataclass di ritorno pensata
per la UI) porta `success`/`world`/`backend`/`pending_request_id`/`error`.
`_finalize_join` semina la replica locale con l'intero snapshot (mondo +
membri + giornale), non solo dal prossimo evento in poi — leggibile
offline fin dal primo momento (§6).

**`ui/views/world/world_view.py` — hosting LAN** (Multiplayer passo 4) —
`self._host_server: WorldHostServer | None`, un solo hosting attivo per
sessione della view. `_hosting_section(world)`: visibile solo se
`is_owner and world.is_local_host`; non avviato → pulsante "Avvia
hosting"; avviato → indirizzo (`local_ip_hint()`) + porta + PIN, elenco
`host.list_pending()` con approva/rifiuta per riga, "Aggiorna
richieste"/"Ferma hosting". `will_unmount()` ferma il server se l'utente
lascia la sezione senza fermarlo esplicitamente (§9.4: nessuna porta
aperta di default). `_open_lan_join_dialog()`: a differenza di "Unisciti
con un codice" (scrittura diretta sullo stesso DB, valida solo in web
mode multi-scheda) chiama `world_sync.start_lan_join()`; se l'esito è
`pending`, il dialogo NON si chiude — passa in uno stato di attesa con un
pulsante "Controlla di nuovo" che richiama `finish_pending_join()`,
riusando lo stesso `RemoteBackend` già connesso invece di far reinserire
tutti i campi.

**Mappe condivise, overlay di disegno** (2026-08-25): il metodo che apre
l'overlay di una mappa condivisa crea un `MapDrawingCanvas`
(`ui/components/map_drawing_canvas.py`) locale, passandogli `on_batch` verso
`CMD_MAP_DRAW` e `can_manage` in base al ruolo — sostituisce una closure di
~500 righe prima duplicata da `maps_view.py` (vedi la voce `MapDrawingCanvas`
sopra per i dettagli del componente e dei bug corretti in quel refactor).

**`ui/mobile_webview_picker.py`** (2026-08-06, import di `flet_webview`
corretto a import ritardato più sotto lo stesso giorno dopo un crash
desktop reale — vedi `changelog_storico.md`) — bypass di `ft.FilePicker`
per la selezione file su Android/iOS, dopo la diagnosi definitiva via log
`adb logcat` reale: `pick_files()`/`save_file()` arrivano al bridge Dart
ma vanno in `TimeoutException: Timeout waiting for invoke method
listener` — nessuna Activity nativa Android viene mai avviata, bug non
risolvibile lato applicazione (dettaglio completo in
`changelog_storico.md`). `async pick_file_via_webview(page, *,
accept="*/*", title="...") -> Optional[tuple[str, str]]` (nome file,
contenuto base64) o `None` se annullato/errore. Usa `flet_webview.WebView`
(pacchetto separato `flet-webview==0.86.5`, stesso lockstep di release del
core) per mostrare, dentro un `ft.AlertDialog`, una paginetta HTML
**locale** (mai rete: passata come `data:` URI via il parametro
costruttore `url=`, mai `load_html()` — evita la race "monta poi invoca"
dello stesso `BaseControl.page`/`_invoke_method` che affligge
`FilePicker`) con un `<input type=file>` che apre il selettore nativo di
sistema tramite l'infrastruttura WebView di Android (meccanismo maturo,
usato da milioni di app — non condivide il bug di `FilePicker`). **Import
di `flet_webview` volutamente RITARDATO dentro `pick_file_via_webview()`**,
non in cima al modulo: un import eager renderebbe il pacchetto un
requisito per l'avvio dell'app su QUALUNQUE piattaforma (questo modulo è
importato da `profilo_tab.py`/`maps_view.py`/`home_view.py`, tutti
caricati all'avvio), mentre serve solo sul ramo mobile — bug reale
riprodotto su desktop ("No module named 'flet_webview'"), corretto lo
stesso giorno. `from __future__ import annotations` + un blocco `if
TYPE_CHECKING:` permettono comunque di annotare i tipi senza un secondo
import eager. Il file scelto è letto in memoria con
`FileReader.readAsDataURL()` (JS standard, nessun upload) e rimandato a
Python tramite `WebView.on_console_message`
(evento di prima classe di `flet-webview`, non un URL-hack), con un
protocollo a prefisso di stringa (`FLET_PICKER_RESULT:`/
`FLET_PICKER_ERROR:` + JSON) e un `asyncio.Future` a fare da ponte
sincrono→asincrono. Copre solo la SELEZIONE (non il salvataggio: un
download via WebView è un meccanismo diverso, mai verificato — resta su
`ft.FilePicker.save_file()`, non ancora migrato). Usato da:
`profilo_tab.py::_pick_photo_mobile()` (`accept="image/*"` → `
_save_photo_bytes()`, nuova funzione estratta da `_load_photo()` per
condividere la normalizzazione PIL→JPEG→base64 tra path locale e bytes
diretti), `maps_view.py::_pick_mobile()` (stesso pattern,
`_normalize_image_bytes_to_base64()` estratta da `_load_image_base64()`),
`home_view.py::_on_mobile_import()` (`accept=".dndchar,.json,
application/json"`, decodifica UTF-8 e delega a `_do_import_from_text()`
— `_on_mobile_export()` resta su `FilePicker.save_file()`, non migrato,
probabilmente soggetto allo stesso bug ma non confermato con un log
dedicato).

**`ui/native_image_picker.py`** (2026-08-06) — terzo tentativo per la
selezione immagine su Android/iOS, dopo `ft.FilePicker` e il fallback
WebView sopra, entrambi confermati non funzionanti (vedi i due blocchi
precedenti e `changelog_storico.md`). Wrapper sottile attorno al
controllo Flet nativo scritto su misura `ImagePicker`
(`dnd_app/extensions/flet_image_picker/`, non SDK ufficiale Flet).
`async pick_image_native(page, *, image_quality=None, max_width=None,
max_height=None) -> Optional[bytes]` — bytes dell'immagine, o `None` se
l'utente ha annullato. Solleva `ImagePickerUnavailable` (non
`ImportError`/eccezione generica: distinzione voluta) se il pacchetto
`flet_image_picker` non è installato in questa build o se l'invocazione
fallisce per qualunque motivo — i chiamanti devono intercettarla e
ricadere su `pick_file_via_webview()` (`ui/mobile_webview_picker.py`,
sopra), non trattarla come "utente ha annullato". Import di
`flet_image_picker` volutamente ritardato dentro la funzione, stesso
motivo/stesso bug-pattern già corretto per `flet_webview`: un import
eager renderebbe il pacchetto un requisito anche per l'avvio desktop.
Costruzione del controllo verificata contro `flet==0.86.5` installato
(`ft.control`, `ft.Service`, `BaseControl._invoke_method`, tutti
confermati esistere con la firma usata); **nessuna invocazione reale né
compilazione del lato Dart è stata possibile da questo sandbox** — vedi
`dnd_app/extensions/flet_image_picker/README.md`. Nessuna registrazione
esplicita del controllo (niente `page.overlay`/`page.services.append`):
un `Service` Flet 0.86.5 si auto-registra nel proprio `init()`, chiamato
alla costruzione se `context.page` è già impostata — vedi il commento
esteso nel modulo e la voce corrispondente in `regole_flet_api.md`. Usato
da `profilo_tab.py::_pick_photo_mobile()` e `maps_view.py::_pick_mobile()`
come primo tentativo, con fallback automatico su
`pick_file_via_webview()` — `home_view.py::_on_mobile_import()` resta
volutamente solo sul fallback WebView (fuori scope di questo giro, l'uso
lì non è un'immagine).

**`dnd_app/extensions/flet_image_picker/`** (2026-08-06) — estensione
Flet completa (Python + Dart) scritta per questo progetto, non un
pacchetto di terze parti su PyPI. Controllo `ImagePicker` (categoria
`Service`), un solo metodo `pick_image()`, wrapper del plugin Flutter
ufficiale `image_picker`. Struttura e pattern di codice copiati dai
sorgenti reali di `flet-camera`/`flet-audio-recorder` (repository
ufficiale `flet-dev/flet`), non inventati — dettaglio completo delle
fonti verificate in `changelog_storico.md`. Consumata dall'app principale
come dipendenza path-based in `pyproject.toml`/`requirements.txt`. Lato
Python (`src/flet_image_picker/`) verificato per costruzione/importazione
in questo sandbox; lato Dart (`src/flutter/flet_image_picker/`) scritto
seguendo fedelmente i pattern reali ma **mai compilato né eseguito qui**
(nessun toolchain Flutter/Dart disponibile) — README.md della cartella
spiega cosa Davide deve verificare/eventualmente rigenerare
(`flet create --template extension`) prima di fidarsi che la build vada
a buon fine.

**`ui/native_file_picker.py`** (2026-08-17) — stesso identico pattern di
`native_image_picker.py` sopra, applicato all'import personaggio/mondo su
mobile dopo che Davide ha segnalato che anche il fallback WebView non
funziona per quel caso (stessa diagnosi già nota per le foto). Wrapper
sottile attorno al controllo Flet nativo scritto su misura `FilePicker`
(`dnd_app/extensions/flet_file_picker/`). `async pick_file_native(page, *,
allowed_extensions=None) -> Optional[tuple[str, bytes]]` — `(nome_file,
bytes)`, o `None` se l'utente ha annullato. Solleva `FilePickerUnavailable`
(stessa distinzione voluta di `ImagePickerUnavailable`) se il pacchetto
`flet_file_picker` non è installato in questa build o se l'invocazione
fallisce per qualunque motivo — i chiamanti devono intercettarla e ricadere
su `pick_file_via_webview()`. Import di `flet_file_picker` ritardato dentro
la funzione, stesso motivo di `native_image_picker.py`. **Nessuna
invocazione reale né compilazione del lato Dart è stata possibile da questo
sandbox** — vedi `dnd_app/extensions/flet_file_picker/README.md`. Usato da
`home_view.py::_on_mobile_import()` e
`world_view.py::_on_mobile_import_world()` come primo tentativo, con
fallback automatico su `pick_file_via_webview()`.

**`dnd_app/extensions/flet_file_picker/`** (2026-08-17) — estensione Flet
completa (Python + Dart) scritta per questo progetto, stessa struttura di
`flet_image_picker` sopra. Controllo `FilePicker` (categoria `Service`), un
solo metodo `pick_file(allowed_extensions=None)`, wrapper del plugin
Flutter ufficiale `file_picker` (diverso da `image_picker`: seleziona un
file arbitrario, non solo immagini da galleria — necessario per
`.dndchar`/`.dndworld`). A differenza di `flet_image_picker`, il lato Dart
restituisce una `Map` (`{"name": ..., "bytes": ...}`) invece dei soli byte
grezzi, perché qui serve anche il nome file originale. Consumata dall'app
principale come dipendenza path-based in
`pyproject.toml`/`requirements.txt`. Lato Python verificato solo per
sintassi/importazione; lato Dart scritto seguendo fedelmente i pattern
reali già usati da `flet_image_picker` ma **mai compilato né eseguito qui**
— README.md della cartella spiega cosa Davide deve verificare prima di
fidarsi che la build vada a buon fine.

---

### Aggiornamento in-app (2026-08-17)

**`core/update_checker.py`** (riscritto) — prima leggeva solo `tag_name` e
`html_url` della release: sapeva DIRE che c'era un aggiornamento ma non da dove
scaricarlo. Ora legge anche l'array `assets` e individua quello della
piattaforma corrente (`ASSET_NAMES`, i cui nomi sono un contratto col job
`release` del workflow — un test li confronta col YAML reale). Restituisce
`(bool, UpdateInfo | None)` invece della vecchia tripla. Due funzioni nuove
degne di nota: `is_dev_checkout()` (disattiva il controllo quando si gira dal
repository, dove `APP_VERSION` non è affidabile perché la CI lo riscrive dal tag
solo in build) e `crosses_signing_migration()` (pura: decide se l'aggiornamento
attraversa la soglia che richiede la disinstallazione manuale). Nessun import
Flet: la piattaforma si rileva da `ANDROID_DATA`/`platform.system()`, non da
`page.platform`.

**`core/update_downloader.py`** (nuovo) — download in streaming con avanzamento
reale. `DownloadProgress` è stato mutabile condiviso (nessun lock: interi e
stringhe, assegnazioni atomiche sotto il GIL, letti indipendentemente — un lock
non comprerebbe nulla e andrebbe preso ad ogni blocco). Scrive su `.part` e
chiude con `os.replace()` atomico: il nome definitivo è anche il segnale "questo
file è installabile", quindi un APK troncato col nome giusto verrebbe passato
all'installer. Verifica la dimensione attesa (una risposta troncata da un proxy
non produce alcun errore di rete); **nessun checksum**, perché l'API di GitHub
Releases non pubblica digest per gli asset — dichiarato invece di simulare un
controllo che non esiste. `find_downloaded()` evita di riscaricare decine di MB
già su disco; `cleanup_old_downloads()` libera lo spazio dopo l'installazione.

**`core/update_state.py`** (nuovo) — la scritta "Aggiornamento completato" non
può essere mostrata dal processo che ha avviato l'aggiornamento: su Android
l'installer lo uccide. Viaggia quindi in un segnalibro su `app_settings`
(versione attesa + istante), scritto prima della consegna e letto al primo avvio
successivo. `classify_pending_update()` è **pura** (`none`/`completed`/`failed`/
`stale`) proprio per essere testabile senza Flet, senza DB e senza dispositivo:
è una tabella di casi, e le tabelle di casi sbagliano in silenzio.

**`ui/update_dialogs.py`** (nuovo) — i tre dialoghi (migrazione della firma,
download, esito). Il ponte fra il thread che scarica e la barra che si muove
riusa il pattern già in produzione in
`world_view.py::_start_network_cooldown_ticker`: il download gira in
`asyncio.to_thread`, un ciclo `async` schedulato con `page.run_task` legge lo
stato ogni 200 ms e aggiorna i controlli. Zero mutazioni di controlli Flet fuori
dal thread della UI, nessuna `run_task` per blocco scaricato. `ui/app.py` resta
un router sottile: decide QUALE dialogo, non come.

**`ui/native_apk_installer.py`** + **`extensions/flet_apk_installer/`** (nuovi) —
l'ultimo passo su Android: consegnare l'APK all'installer di **sistema**. Non
ottenibile dal Python (serve un FileProvider per l'URI `content://` e un intent
nativo, e nessuna chiave di `pyproject.toml` letta da flet_cli permette di
aggiungere la risorsa XML che un FileProvider richiede). Terza estensione nativa
del progetto, ma la prima **senza una riga di Kotlin**: si appoggia al plugin
Flutter `open_filex`, che porta con sé il proprio FileProvider e il proprio
`filepaths.xml`, uniti ai nostri dal manifest merger di Gradle. Il wrapper
solleva `ApkInstallerUnavailable` se l'estensione non è compilata in questa
build, e il dialogo mostra allora il percorso del file già scaricato invece di
un pulsante inerte. ⚠️ Lato Dart **mai compilato né eseguito qui** — il README
della cartella elenca i quattro punti da verificare, in particolare i vincoli di
versione su pub.dev (c'è un precedente di CI rotta su tutte e 4 le piattaforme
per esattamente quel motivo con `flet_file_picker`).

**`data/database.py::get_updates_path()`** (nuovo) — cartella di staging,
ricavata dal parent di `get_db_path()` per non duplicare le tre strategie di
ripiego Android. Deliberatamente **non** la cache, che Android può svuotare a
metà scaricamento. ⚠️ Su Android è spazio privato e viene cancellata dalla
disinstallazione: per questo l'APK della migrazione alla firma deve scaricarlo il
browser, non l'app.

### Trasferimento del personaggio su un altro dispositivo (2026-08-17)

Design completo in `multiplayer_design.md` §11.9.

**`data/repositories/world_transfer_repo.py`** (nuovo) — le due metà: il codice
(8 caratteri, monouso, TTL 7 giorni, emetterne uno revoca il precedente) e
`rebind_device()`, la transazione che sposta appartenenza, istanze (anche
archiviate), visibilità delle note e richieste di rientro dal vecchio
`device_id` al nuovo. Il commento sopra `rebind_device` enumera **tutte** le
colonne del progetto che contengono un device_id, incluse quelle che si lasciano
deliberatamente ferme e perché — è la parte in cui un'implementazione distratta
perde dati in silenzio.

**`network/protocol.py::HOST_FEATURES`** (nuovo) — capacità opzionali annunciate
da `GET /world`, per non dover incrementare `PROTOCOL_VERSION` ad ogni aggiunta
retrocompatibile (quel numero è confrontato con un'uguaglianza stretta e
rifiuterebbe l'ingresso a tutti gli accoppiamenti esistenti).

**`core/world_backend.py`** — `CommandResult` guadagna un campo `data`: dati di
risposta destinati al SOLO mittente, perché `event.payload` finisce nel giornale
trasmesso a ogni replica e il codice di trasferimento è un segreto per un solo
membro. Attraversa la rete via `handle_command` → JSON → `RemoteBackend`.

**`core/world_sync.py`** — `is_world_transferred_away()` /
`_mark_world_transferred_away()`: la replica del vecchio dispositivo resta come
copia in sola lettura, marcata in `app_settings` (nessuna modifica di schema) e
con `session_token` azzerato, senza il quale `resolve_backend_for_world`
ritenterebbe un ingresso completo e mostrerebbe un errore sul PIN.

---


---

> Questo file è stato estratto da `CLAUDE.md` il 2026-07-31 durante la riorganizzazione della documentazione del
> progetto (il file principale era cresciuto fino a superare 860 KB, causando compattazioni troppo frequenti della
> chat). Il contenuto è verbatim, nessuna informazione è stata riassunta o rimossa. Per la mappa completa dei
> documenti del progetto vedi `CLAUDE.md` alla radice.
