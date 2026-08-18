# Restyle — progettazione del sistema visivo (Fasi A · B · C · D · E)

> **STATO: A · B · C · E completate il 2026-07-30** (C assorbita dentro E).
> **Tutte le fasi sono completate (A · B · C · D · E) — il restyle è chiuso
> al 2026-07-30.** Ogni fase completata ha in testa un riquadro con gli
> scostamenti rispetto a quanto era stato progettato qui; il changelog
> dettagliato è in `CLAUDE.md`.
>
> Scostamenti della **FASE D** rispetto a quanto progettato più sotto:
> tre stati (Chiaro/Scuro/**Sistema**, default Sistema) invece di un
> interruttore a due — `page.platform_brightness` e
> `on_platform_brightness_change` sono stati verificati esistenti su
> `flet==0.85.3`, quindi "Sistema" segue il SO anche ad app aperta;
> **densità e dimensione testo NON incluse** (rimandate con Davide, la
> tabella chiave/valore le accoglierà senza migrazione); il pulsante vive in
> **tre** superfici (Home, sidebar/bottom nav, Sezione Master) e non in una
> sola, perché sidebar e bottom nav non esistono fuori dal layout della
> scheda; `page.theme_mode` riceve sempre un valore concreto e mai
> `ThemeMode.SYSTEM` (motivazione nel changelog).
>
> Documento nato come **progettazione** (nessuna riga di codice applicata).
> Scelte confermate da Davide il 2026-07-26: restyle completo **incluso dark mode**.
> Ordine di lavoro confermato: bug → pulizia → restyle → feature.
>
> **Ogni API Flet citata qui è stata verificata per introspezione sul pacchetto
> `flet==0.85.3` realmente installato in `.venv`** — nessuna API inventata.
> Verificate presenti: `Container.shadow/gradient/blur/animate/animate_opacity/
> animate_scale/offset/scale/ink_color`, `ft.BoxShadow` (campi:
> `spread_radius, blur_radius, color, offset, blur_style`), `ft.BlurStyle`,
> `ft.LinearGradient` (`colors, stops, begin, end, rotation, tile_mode`),
> `ft.AnimatedSwitcher`, `ft.Shimmer`, `ft.ShaderMask`, `ft.Page.fonts`,
> e i sotto-temi `ft.Theme.text_theme / card_theme / dialog_theme / button_theme /
> outlined_button_theme / text_button_theme / scrollbar_theme / visual_density /
> page_transitions` (58 campi totali in `ft.Theme`, oggi ne usiamo 2).

---

## Principio guida

Il fantasy sta nei **titoli, nelle texture e negli accenti**, non nel testo di
regolamento. Il testo di regolamento deve essere il più leggibile possibile:
è un manuale, non un poster. Questo evita l'effetto "font gotico illeggibile"
che fa sembrare amatoriali le app di settore.

Secondo principio, già stabilito come linea guida permanente del progetto:
**nulla di nascosto**. Il restyle non deve introdurre affordance ambigue —
ogni cosa cliccabile resta esplicitamente riconoscibile.

---

## FASE A — Fondazioni

Invisibile all'utente per il 70%, ma è ciò che rende economico tutto il resto.
Senza questa fase, cambiare un raggio o un colore significa modificare 25 file.

### A.1 — Design tokens in `ui/theme.py`

```
SPACING   XS=4  SM=8  MD=12  LG=16  XL=24  XXL=32       (niente più numeri a caso)
RADIUS    SM=8  MD=12  LG=16  XL=20  PILL=999
ELEV      ELEV_0 (nessuna)  ELEV_1 (riposo)  ELEV_2 (hover/attivo)  ELEV_3 (dialog)
TYPE      display / title / subtitle / body / body_sm / label / mono
DURATION  FAST=120ms  BASE=200ms  SLOW=320ms   curva standard EASE_OUT
```

Le elevazioni come `ft.BoxShadow` predefinite, due varianti per tema (le ombre in
dark mode vanno più diffuse e meno nere, altrimenti scompaiono):

```
ELEV_1  light: blur 8,  offset (0,2),  #1a1c24 @ 8%
        dark:  blur 12, offset (0,2),  #000000 @ 45%
ELEV_2  light: blur 16, offset (0,4),  #1a1c24 @ 12%
        dark:  blur 20, offset (0,4),  #000000 @ 55%
ELEV_3  light: blur 32, offset (0,8),  #1a1c24 @ 18%   (dialog)
        dark:  blur 40, offset (0,8),  #000000 @ 65%
```

### A.2 — Primitive riusabili (sostituiscono le 166 card scritte a mano)

| primitiva | sostituisce | note |
|---|---|---|
| `surface(content, level=1)` | i `Container(bgcolor=..., border=...)` generici | 3 livelli di profondità |
| `card(content, accent=None)` | `fantasy_card()` + le 166 varianti inline | accento opzionale come barra sottile a sinistra, non filetto in cima |
| `section(title, content, collapsible=False, key=None)` | `section_header()` + Column manuale | opzione comprimibile con memoria dello stato (serve al punto 4 della revisione) — **nota**: implementata poi come funzione a sé `collapsible_section()`, non come parametro di `section()`, vedi sotto |
| `collapsible_section(title, content_builder, expanded=False, on_toggle=None, ...)` | logica bespoke del pannello "STRUMENTI MASTER" | aggiunta 2026-08-15, fuori dalla Fase E — vedi nota sotto |
| `pill(icon, label, color, on_click)` | le 3 copie di `_tool_pill`/`_action_pill`/`_header_actions` in master_view / master_encounter_view / home_view | oggi lo stesso widget è duplicato in 3 file |
| `chip(text, tone)` | i ~40 chip/badge inline | toni: neutro/primario/magia/successo/attenzione/pericolo |
| `stat_tile(value, label, on_click=None)` | `stat_badge()` (dead) + i box caratteristica di `sheet_view` | tap-target ≥44px |
| `metric_bar(value, max, tone)` | le ProgressBar di HP/peso | animata (Fase C) |
| `empty_state(icon, title, hint, action)` | i ~12 stati vuoti scritti a mano | uniformi |

**Migrazione**: non tutto in un colpo. Le primitive nascono in Fase A, le view
migrano in Fase E, una per volta. Una view non migrata resta funzionante.

> Alla chiusura della Fase E le primitive effettivamente in uso sono 15, non 8:
> alle previste si sono aggiunte `hp_bar()` (barra PF a segmenti, per mostrare i
> temporanei), `slot_dots()`/`dot_button()` (gli slot erano caratteri di testo),
> `dialog_title()` e `field_style()` (allineamento delle 114 finestre),
> `difficulty_color()`, `CURRENCY_COLORS` e `CHROME` (chrome dell'editor mappe).
> `section(collapsible=…)` è invece rimasta **non implementata** per tutta la
> Fase E: nessuna view l'ha richiesta durante il restyle.
>
> **Implementata il 2026-08-15** (bug report/richiesta di Davide: "voglio
> usare di più la tendina che collassa"), non come parametro aggiuntivo di
> `section()` ma come funzione a sé, `design.collapsible_section(title_text,
> content_builder, *, expanded=False, accent=None, level=1,
> header_subtitle=None, on_toggle=None, alt=False)` — stateless (lo stato
> aperto/chiuso resta nel chiamante, stesso principio di `set_mobile`),
> `content_builder` invece di `content` già costruito per non pagare il
> costo di sezioni pesanti tenute chiuse. Sostituisce la logica bespoke del
> pannello "STRUMENTI MASTER" (`master_view.py`) e viene usata per le
> sezioni facoltative della scheda mostro (`ui/components/monster_picker.py`
> — Tratti/Azioni/Reazioni/ecc.) e per le note NPC lunghe
> (`master_npc_list_view.py`). Dettaglio completo in `changelog_storico.md`,
> voce "Sessione bug report multipli + primitiva collassabile + oggetti
> magici personalizzati (2026-08-15)".

### A.3 — `get_theme()` riscritta

Oggi passa solo `color_scheme` + `font_family`. La riscrittura sfrutta i
sotto-temi, con un effetto enorme a costo quasi zero:

- `dialog_theme`: `shape` (raggio 20), `elevation`, `bgcolor`, `title_text_style`,
  `content_text_style`, `inset_padding` → **restyla in un colpo solo tutti i ~60
  AlertDialog dell'app**, che oggi sono stilizzati a mano uno per uno.
- `card_theme`, `text_theme` (13 stili tipografici), `button_theme` /
  `outlined_button_theme` / `text_button_theme` (raggi e padding coerenti senza
  ripetere `ButtonStyle` in ogni chiamata), `scrollbar_theme` (le scrollbar di
  default sono uno dei dettagli che più "invecchiano" un'app), `divider_theme`,
  `tooltip_theme`, `visual_density`, `page_transitions`.
- `ColorScheme` completo (oggi 7 campi su 30+): serve per far comportare bene i
  controlli Material che non stiliamo a mano.

### A.4 — Wiring degli asset (prerequisito per i font)

Problema reale: `ft.run(run_app)` su desktop **non passa `assets_dir`**, e in web
mode `assets_dir` è già occupato da `get_character_exports_path()` (serve al
download degli export `.dndchar`).

Soluzione proposta: `assets_dir` punta sempre a `dnd_app/assets/`, e la cartella
degli export diventa una **sottocartella servita** (`assets/exports/`) oppure un
symlink/bind mount al suo interno. Va verificato che il bottone "Scarica" continui
a funzionare (l'URL diventerebbe `/exports/nome.dndchar`) — è l'unico punto di
attenzione di tutta la Fase A, perché tocca una feature già collaudata da Davide.

**Deliverable Fase A**: raggi/ombre/dialog/bottoni/scrollbar coerenti in tutta
l'app senza aver ancora toccato una singola view.

---

## FASE B — Identità visiva

> ✅ **COMPLETATA il 2026-07-30.** Changelog completo in `CLAUDE.md`
> ("FASE B COMPLETATA"). Scostamenti rispetto a quanto progettato qui:
> * i font installati sono le versioni **variable** (un file per famiglia):
>   `page.fonts` di Flet accetta un solo percorso per famiglia, quindi le
>   statiche non permetterebbero pesi reali;
> * i letterali di colore erano **321**, non 153 (la stima contava solo
>   `#ffffff`); ne restano 24, tutti in due blocchi dichiarati di
>   `maps_view.py` (colori del pennarello **persistiti** su DB + chrome
>   dell'editor, volutamente scura in entrambi i temi);
> * la palette ha **un accento in più del previsto**, `alert`: la scala di
>   difficoltà degli incontri ha 5 gradini e con soli 4 accenti "difficile" e
>   "letale" sarebbero diventati identici. Aggiunto anche `nav_accent`, perché
>   `primary` sul fondo scuro della nav dà 2.45:1.

### B.1 — Tipografia

Font self-hosted in `assets/fonts/` (nessuna richiesta di rete, funziona offline
— vincolo del progetto):

| ruolo | font | perché |
|---|---|---|
| display / titoli / nomi | **Cinzel** | capitali romane, evoca l'inciso su pietra; leggibile perché usata solo su testi brevi |
| corpo / regolamento | **Inter** | pensata per UI, altissima leggibilità a 12-14px, ottima resa su tablet |
| numeri / statistiche | **JetBrains Mono** | cifre tabellari (le colonne di numeri si allineano), a differenza di Courier New non sembra una macchina da scrivere |

Scala tipografica fissa (oggi: dimensioni da 9 a 52 scelte caso per caso):

```
display  32 / bold / Cinzel        titolo schermata
title    22 / bold / Cinzel        nome personaggio, titoli sezione grandi
subtitle 16 / semibold / Inter     intestazioni di card
body     14 / regular / Inter      testo di regolamento  ← minimo per il testo lungo
body_sm  13 / regular / Inter      descrizioni secondarie
label    11 / bold / Inter / +1 letter-spacing / MAIUSCOLO   etichette
mono     15 / medium / JetBrains   valori numerici
```

Regola: **niente testo sotto 11px** (oggi ci sono molti 9 e 10px).

### B.2 — Palette a due temi (valori verificati per contrasto WCAG)

Ho calcolato ogni rapporto di contrasto con uno script; sotto i valori misurati,
non stimati.

**Tema chiaro** (pergamena, evoluzione di quello attuale)

| token | hex | contrasto misurato |
|---|---|---|
| `bg` | `#f4efe6` | — |
| `surface` | `#fffdf9` | — |
| `surface_alt` | `#ece5d8` | — |
| `border` | `#d9d0bf` | — |
| `text` | `#1a1c24` | 16.7 su surface (AAA) |
| `text_2` | `#4a4f63` | 7.98 su surface (AAA) |
| `text_3` | `#5c6376` | 5.90 su surface / 4.79 su surface_alt (AA) |
| `primary` | `#a4161a` | 7.63 su surface — bianco sul pieno 7.75 |
| `magic` | `#2f4b8f` | 8.19 |
| `success` | `#1f6b3a` | 6.41 |
| `warning` | `#a35a00` | 5.14 |
| `danger` | `= primary` | 7.63 |

**Tema scuro** (rivisto due volte il 2026-08-15, vedi `changelog_storico.md` —
bug report Davide: pannelli troppo "accesi"/colori troppo fluo nel primo giro,
poi sfondo ancora percepito "blu" invece di nero opaco e rosso da rifare in
bordeaux nel secondo. I valori sotto sono quelli **attuali**, non quelli
originali della Fase B — la tabella storica con i numeri di allora è nel
changelog, non ripetuta qui)

| token | hex | contrasto misurato |
|---|---|---|
| `bg` | `#161617` | — (neutro, niente più dominante blu-viola) |
| `surface` | `#1e1e1e` | 1.08:1 su bg — grigio puro indipendente, non derivato da `bg` |
| `surface_alt` | `#242424` | 1.11:1 su bg |
| `border` | `#3e3d41` | 1.55:1 su surface — unico segnale dei bordi card |
| `text` | `#f0ece4` | 14.2 su surface (AAA) |
| `text_2` | `#c2bcae` | 8.88 (AAA) |
| `text_3` | `#9c94a8` | 5.14 (AA) |
| `primary` (= `danger` = `nav_accent`) | `#da5b67` | 4.50 su surface/4.89 su bg — testo scorrevole/paragrafi/etichette (soglia WCAG 1.4.3 normale, 4.5:1) |
| `primary_icon` (= `danger_icon`) | `#bf384b` | 3.08 su surface/3.34 su bg — SOLO icone isolate e testo grande/bold ≥18pt (soglia WCAG 1.4.11/1.4.3 "large text/graphical object", 3:1) — più scuro di `primary`, MAI per paragrafi |
| `primary_fill` (= `danger_fill`) | `#761c2a` | il bordeaux vero di Davide — SOLO riempimenti (bottoni/badge/checkbox), sempre con `on_primary_fill` (`#ffffff`, 10.7:1) sopra, mai da solo su `surface`/`bg` (~1.7:1, illeggibile) |
| `magic` | `#7897db` | 6.22 |
| `success` | `#4ec27f` | 7.48 |
| `warning` | `#bd8c32` | 5.97 |
| `alert` | `#d57d40` | 5.86 |

**`surface` un gradino sopra `bg`, grigio puro** (rifinito il 2026-08-15,
due volte): prima portato a coincidere esattamente con `bg` (un rapporto
WCAG basso tra due riquadri PIENI non garantisce che sembrino uguali
all'occhio — header/card restavano "più luminosi" anche a 1.02:1, la
fusione totale ha risolto), poi Davide ha chiesto un "leggero distacco"
con un grigio vero (0% saturazione, mai successo prima — ogni tentativo
precedente aveva sempre una tinta residua) invece di nessuna differenza.
`surface`/`surface_alt` sono ora valori neutri indipendenti, non derivati
da `bg` per formula.

**Due token per il rosso** (dal 2026-08-15): `primary` deve restare
leggibile da solo (325 usi testo/icona/bordo in `ui/`, audit completo in
`changelog_storico.md`) quindi non può essere scuro quanto un vero
bordeaux; `primary_fill` non ha questo vincolo perché è sempre
accompagnato da `on_primary_fill` sopra (141 usi, solo riempimenti). Le
due tinte sono deliberatamente diverse — non è un refuso.

Note importanti emerse dal calcolo:
- In dark mode i bottoni pieni devono usare un **foreground scuro** sull'accento
  chiaro (convenzione Material 3): bianco su un accento di luminosità
  medio-bassa scende sotto la soglia AA. Questa è la ragione per cui il
  `primary` scuro non può essere lo stesso `#a4161a` (o un bordeaux altrettanto
  scuro) del tema chiaro.
- `primary`/`danger` sono lo **stesso token**, usato in 478 punti di `ui/`
  (audit 2026-08-15): 325 come testo/icona/bordo diretto su `surface`/`bg`
  (serve ≥4.5:1), solo 141 come riempimento con `on_primary` sopra. Qualunque
  tonalità nuova va scelta pensando prima al vincolo testo, non al pulsante —
  un bordeaux scuro "vero" (tipo `#8d2132`, valutato e scartato) scende a
  ~2:1 e sparisce nei 325 usi non-riempimento.
- Per confronto, i valori **attuali**: `COLOR_TEXT_MUTED #7880a0` su bianco =
  **3.89** (sotto AA per testo piccolo, e viene usato proprio per i testi
  piccoli); `danger_button` testo `#1c1e2c` su `#c0182c` = **2.68** (illeggibile).

**Gerarchia d'uso** (questa è la parte che oggi manca del tutto): un solo accento
primario porta il peso visivo. Gli altri tre diventano **semantici**, usati solo
dove significano qualcosa:
`magic` = incantesimi/slot/effetti magici · `success` = valori positivi, HP alti,
risorse disponibili · `warning` = HP medi, Indebolimento, attenzione ·
`danger`/`primary` = HP bassi, azioni distruttive, accento del brand.
Vietato: 4 accenti pieni nella stessa card.

**Prerequisito tecnico obbligatorio**: i **153 `"#ffffff"` hardcoded** e i colori
fuori palette (`#7b1fa2`, `#d2691e`, 4 grigi diversi, `#9a8888`, `#3a2828`…)
vanno tutti sostituiti con token, altrimenti in dark mode restano bianchi/viola
sparati. È il lavoro più noioso della Fase B ed è ineliminabile.

### B.3 — Texture e superfici

- Sfondo pagina con `LinearGradient` a contrasto minimo (2 stop, ~2% di
  differenza di luminosità) → dà la sensazione della pergamena senza immagini,
  peso zero, funziona identico in dark.
- Le card passano da "bordo 1px + filetto colorato in cima" a "superficie
  elevata con ombra morbida + accento come barra sottile a sinistra": è il
  singolo cambiamento che sposta più percezione di modernità.
- Angoli: `RADIUS.MD=12` per le card, `LG=16` per i pannelli, `XL=20` per i
  dialog, `PILL` per chip/pillole.

---

## FASE C — Micro-interazioni

> ✅ **ASSORBITA NELLA FASE E il 2026-07-30** (scelta confermata da Davide: "sì,
> insieme"). Applicate: feedback di press su card/pillole/chip/riquadri
> caratteristica, transizione della tab bar (scheda e Master), barra HP animata,
> pallini degli slot animati, ombre e superfici con `animate`.
> **Non fatte, per scelta**: `ft.AnimatedSwitcher` sul cambio tab (il contenuto
> del tab viene ricostruito, un switcher animerebbe due alberi diversi) e
> `ft.Shimmer` come skeleton sulle liste lunghe — le liste si costruiscono da DB
> locale, il caricamento non è mai percepibile.

Serve **prima** aver risolto B10 (il rebuild totale ad ogni click): animare un
albero che viene ricostruito da zero produce sfarfallio, non fluidità.

| interazione | implementazione | dove |
|---|---|---|
| press feedback | `animate_scale=120ms` + `scale=0.97` | card, pillole, chip, stat tile |
| hover (desktop) | `animate=200ms` su `shadow` ELEV_1→ELEV_2 e `border` | card e righe cliccabili |
| cambio tab/sezione | `ft.AnimatedSwitcher` | scheda personaggio (5 tab), Modalità Master (5 tab), DiaryView |
| barra HP | `animate=320ms` sul valore + colore che transita | `_section_hp` |
| slot incantesimo | pop del cerchietto (`animate_scale`) quando si consuma | `_section_spell_slots` |
| caricamento liste | `ft.Shimmer` come skeleton | bestiario (444), incantesimi (361), oggetti magici (264) |
| dialog | `page_transitions` + `dialog_theme.elevation` | tutti |
| risultato del dado | scale-in + colore per critico/fallimento critico | `DiceView` (e la nuova feature dadi collegati) |

Regola: durate 120–320 ms, curva `EASE_OUT`. Niente animazioni sopra i 400 ms
(sembrano lente al secondo utilizzo) e niente animazioni su liste lunghe durante
lo scroll.

---

## FASE D — Dark mode + densità

- I token diventano una coppia `LIGHT`/`DARK` risolta da un unico
  `ThemeTokens.current()`; `get_theme()` produce sia `page.theme` sia
  `page.dark_theme`, e `page.theme_mode` diventa commutabile.
- Toggle in **un solo posto**, raggiungibile da tutte le schermate (candidato:
  accanto all'avatar nella sidebar / bottom nav, coerente con "nulla di
  nascosto": icona + etichetta, non un'icona muta).
- Persistenza della preferenza: nuova riga in una tabella `app_settings`
  (chiave/valore) — **non** sul personaggio, è una preferenza dell'installazione.
  Da valutare se includere anche "densità" (comoda/compatta) e "dimensione testo".
- `visual_density`: `COMFORTABLE` su tablet/mobile (tap-target ≥44px),
  `COMPACT` su desktop.

---

## FASE E — Restyle per superficie

> ✅ **COMPLETATA il 2026-07-30** (Fase C assorbita al suo interno: le
> micro-interazioni sono state aggiunte insieme al restyle, non in un giro a
> parte). Changelog completo in `CLAUDE.md` ("FASE E COMPLETATA").
>
> Scostamenti rispetto a quanto progettato qui:
> * l'ordine per superficie è stato **sostituito da due sweep globali** (token di
>   colore, poi superfici/raggi/ombre) seguiti dal restyle a mano dei soli
>   componenti nominati da Davide. Motivo: la maggior parte del "sembra vecchio"
>   veniva dalla vecchia palette e dal pattern card "filetto in cima + bordo
>   1px", entrambi presenti in modo identico in tutte le view — risolverli una
>   view alla volta avrebbe richiesto 11 passaggi per lo stesso risultato;
> * gli helper legacy di `ui/theme.py` **non sono stati lasciati invariati** come
>   previsto in Fase A: riscriverli sulle primitive ha restylato in un colpo solo
>   le 68 sezioni e i pulsanti delle view non ancora toccate a mano;
> * `config/settings.py` non ha più costanti di colore/font (rimosse, non
>   deprecate): erano l'ultimo ostacolo strutturale al tema scuro;
> * due primitive non previste qui si sono rivelate necessarie: `hp_bar()` a
>   segmenti (per mostrare i PF temporanei) e `slot_dots()`/`dot_button()` (gli
>   slot erano caratteri di testo "●"/"○", non forme).
>
> **Coda 2 (stesso giorno)**: allineate tutte le **114 finestre** dell'app
> (Master e giocatore) — titolo dalla primitiva condivisa, sfondo dal tema
> (i 76 `bgcolor` inline rimossi erano un ostacolo silenzioso al tema scuro),
> pulsanti sempre avvolti per andare a capo, larghezze responsive, campi con
> stile condiviso. Nota tecnica: `ft.Theme` **non ha** `input_decoration_theme`
> in Flet 0.85.3, quindi `TextField`/`Dropdown` sono l'unico controllo che va
> stilizzato sito per sito (`design.field_style()`); tutti gli altri controlli
> Material dei dialog sono ora uniformati dal tema.
>
> **Coda (stesso giorno)**: restylati anche l'editor di mappe e la Sezione
> Master. La chrome dell'editor resta scura in entrambi i temi — è un pannello
> sopra un'immagine — ma vive ora in `design.CHROME` invece che come dizionario
> di hex dentro la view; i colori del pennarello restano intoccabili perché
> **persistiti** in `game_maps.annotations`.
>
> **La Fase D è ora la sola cosa che separa l'app dal tema scuro**: nelle view non
> resta nessun colore statico, serve solo l'interruttore + persistenza.

---

## FASE F — Audit anti-AI-slop (pilot + rollout completo, 2026-08-18/19)

> ⏳ **Codice implementato su TUTTE le 37 view dell'app, in attesa di
> verifica visiva di Davide** (nessun test visivo automatico esiste per
> questo progetto — vedi "Rischi e punti di attenzione" più sotto — quindi
> questa fase non si considera chiusa finché non confermata su un avvio
> reale, in entrambi i temi. Verificato invece con certezza: `python3
> test_fase_d.py` — 104 costruzioni di view nei due temi, 101/101 controlli
> — e `python3 -m compileall ui/ core/ data/` puliti dopo OGNI blocco di
> lavoro, quindi zero rischio di crash strutturale; resta da confermare solo
> il giudizio ESTETICO).

Motivazione: nonostante il sistema di token della Fase E fosse solido, il
modo in cui viene usato nelle view produceva un risultato "meccanico" —
`card()`/`section()` riusate identiche per contenuti di importanza molto
diversa, nessun elemento focale per schermata, layout sempre a colonna
singola, icone decorative ridondanti. Pilot su 4 view (`home_view.py`,
`character_sheet/sheet_view.py`, `character_sheet/combattimento_tab.py`,
`world/world_view.py`), scelte perché coprono i 4 contesti strutturali
diversi dell'app (lista, scheda dati densa, combattimento con stato
dinamico, gestione entità con danger zone).

**Scoperta chiave**: `d.card()`/`d.section()` accettavano già `accent` e
`level` (elevazione 0-3) — non servivano nuove primitive "hero"/"critical",
solo un uso più intenzionale dei parametri esistenti (quasi ovunque
lasciati al default). Uniche due aggiunte di codice:

- **`design.asymmetric_row(major, minor, ratio=(7,5))`** — riga a due
  colonne di peso diverso via `ft.ResponsiveRow`/`col=`, MAI `expand=` su
  una `ft.Row` semplice (crash silenzioso Flutter dentro un `ft.ListView` —
  le tab della scheda personaggio ne sono sottoclassi, vedi
  `regole_flet_api.md`). Nato con un solo call site (`combattimento_tab.py`:
  HP affiancato alle statistiche di combattimento), poi riusato anche in
  `esplorazione_tab.py` (Percezione Passiva + Indagare Passivo) durante il
  rollout — incapsula una regola di sicurezza Flet non ovvia che vale la
  pena riusare invece di ricopiare a mano, non solo un caso singolo.
- Nessuna primitiva `stat_cell`/`hero_card`/`critical_section` a sé:
  valutate durante l'implementazione e scartate — i "riquadri statistica"
  di `combattimento_tab.py` (CA/velocità/iniziativa/ispirazione) sono già
  bespoke (bordi/icone diversi caso per caso), forzarli in un'astrazione
  comune con la stat bar di `sheet_view.py` (6 celle davvero identiche)
  avrebbe prodotto un'astrazione che calza male a entrambi i casi.

**Convenzioni d'uso** (nessun nuovo colore — `primary`/`danger` sono di
proposito lo stesso accento, vedi Palette in `ui/design.py`, quindi la
distinzione hero/critical passa per l'elevazione, non per il colore):
- **Hero (max 1 per schermata)**: `level=2` (invece del default 1),
  padding maggiorato. Esempio: `_section_hp` in `combattimento_tab.py`
  (bordo 3→4px, padding `Space.LG`→`Space.XL`, `elevation(1)`→`(2)`) e
  `_live_combat_section` in `world_view.py` (`accent=p.primary, level=2`,
  solo quando un combattimento è visibile).
- **Zona critica/pericolosa**: `level=0` (nessuna ombra — l'assenza è il
  segnale, non uno sfondo rosso pieno). Esempio: `_danger_zone_section` in
  `world_view.py`.
- **Emphasis locale, non tramite `card()`/`section()`**: la cella del
  punteggio più alto nella mini stat bar di `sheet_view.py` usa
  `bgcolor=p.surface` (invece di `p.surface_alt`) + `border=Border.all(1,
  p.primary_icon)` — un pattern troppo specifico per meritare una
  primitiva condivisa.
- **Icone decorative rimosse** dove il testo adiacente diceva già lo
  stesso concetto: `PUBLIC` accanto ai nomi dei gruppi-mondo in
  `home_view.py::_section_label` (era mostrata anche per "Non in un
  mondo"/"Rimossi dai mondi", semanticamente sbagliata lì);
  `CENTER_FOCUS_STRONG` accanto al nome incantesimo in
  `_section_concentration` (`combattimento_tab.py`, la sezione è già
  titolata "Concentrazione").

**Smoke test pilot** (2026-08-18): avvio in modalità web
(`FLET_WEB=true python main.py`), nessuna eccezione Python al boot,
migrazione DB ok, Home renderizzata correttamente con i personaggi reali
di Davide (screenshot preso una volta, poi il server è stato fermato per
non restare a interagire con la sessione browser reale dell'utente senza
autorizzazione esplicita).

### Fix contrasto/eye-strain tema scuro (2026-08-19)

Feedback di Davide dopo aver visto il pilot: "i colori in versione scura
non mi convincono mi affaticano gli occhi". Due interventi separati, in
ordine:

1. **Primo tentativo, scartato dopo verifica numerica**: schiarire
   `bgcolor` delle card "hero" per livello (tecnica Material "elevation
   overlay"). Calcolato PRIMA di applicarlo che avrebbe fatto scendere
   `primary_icon` (`#bf384b`) sotto soglia 3:1 contro un `surface`
   schiarito anche di poco (già 3.08:1 contro `surface` invariato, margine
   quasi zero), e avrebbe riavvicinato `surface`/`bg` dopo che Davide aveva
   passato SETTE giri di feedback (2026-08-15) a distanziarli il minimo
   indispensabile per evitare un "glow" diffuso. Scartato, mai committato
   sui file di vista.
2. **Fix effettivo**: `DARK.text` (`#f0ece4`→`#dbd1bd`), `DARK.text_2`
   (`#c2bcae`→`#b9b2a2`), `DARK.nav_text` (idem `text`) ridotti in
   luminosità HSL (tonalità/saturazione invariate) — erano a 15.35:1/
   9.56:1 contro `bg`, ben oltre il minimo AAA (7:1) e persino oltre la
   soglia ≥14:1 auto-imposta da questo file per `text`: un contrasto testo
   quasi-bianco/fondo quasi-nero così alto è causa nota di affaticamento
   ("halation") nella lettura prolungata. Ora 11.94:1/8.57:1 contro `bg` —
   ancora ben oltre AAA, meno "acceso". `bg`/`surface`/`text_3` NON
   toccati (voluti così da Davide, o margine già stretto). Nuova primitiva
   **`design.accent_glow(accent, level)`** + **`design.layered_shadow(level,
   accent)`**: un alone colorato (non nero) attorno alle card "hero" SOLO in
   tema scuro — un'ombra nera normale è quasi invisibile contro uno sfondo
   già scuro, un'ombra colorata a bassa opacità si vede senza toccare
   `bgcolor` (quindi senza rimettere in discussione nessun contrasto
   testo/icona già calcolato). `card()`/`section()` la usano automaticamente
   quando `level>=2` e un `accent` è passato — nessuna chiamata da
   aggiornare nei file di vista già scritti.

### Rollout completo alle 37 view (2026-08-19, stessa notte)

Con mandato esplicito di Davide ("non porti limiti... procedi senza
fermarti... effettua tutti i cambiamenti anche quelli programmati"), la
stessa convenzione del pilot è stata estesa a TUTTE le view rimanenti,
delegando a 6 sotto-agenti paralleli (ciascuno con lo stesso brief:
API disponibile, convenzione hero/critical, regole icone/spaziatura,
vincolo assoluto "mai la logica, solo l'estetica", compilazione +
`test_fase_d.py` dopo ogni file):

- Tab rimanenti della scheda personaggio (`profilo_tab.py`,
  `inventario_tab.py`, `esplorazione_tab.py`, `diario_tab.py`).
- Creazione personaggio (`wizard_view.py`, `manual_form.py` — hero sulla
  card "Riepilogo" finale in entrambi; `creation_shared.py` invariato,
  solo logica).
- View di primo livello (`spells_view.py`, `maps_view.py`, `diary_view.py`,
  `magic_items_view.py`, `dice_view.py`, `feats_view.py`).
- 9 dialog generatori della Sezione Master (artefatti, incontri, oggetti
  magici, NPC, incontri nella foresta, pericoli ambientali, trappole,
  tesori, assegnazione bottino) — hero quasi ovunque sul riquadro del
  risultato appena generato/tirato.
- 7 view di gestione/liste della Sezione Master — la maggior parte **già
  ben progettata** da iterazioni precedenti guidate da feedback reale di
  Davide (elevazione/accento già differenziati intenzionalmente): solo
  `master_view.py` modificato (placeholder "in costruzione" consolidato
  sulla primitiva `empty_state()`), gli altri 6 lasciati invariati per
  scelta esplicita, non per omissione.
- `world/qr_scanner_view.py` (mirino QR: alone "magic" sul viewfinder,
  testo centrato) — `world/combat_status.py` è pura logica, nessuna UI,
  invariato.

**Deliberatamente NON toccati** (rischio/beneficio giudicato sfavorevole,
non dimenticanza):
- I tre flussi dialog di `profilo_tab.py` per level-up/multiclasse/
  level-down (~2500 righe): logica di progressione PHB e costruzione UI
  troppo interlacciate per un lavoro di rifinitura estetica sicuro in
  autonomia notturna — vanno rivalutati a parte, con calma, se Davide lo
  richiede esplicitamente.
- L'editor di disegno mappe vero e proprio in `maps_view.py` (canvas,
  toolbar, gomma) — solo la chrome attorno (lista mappe, pannelli) è stata
  toccata.
- I 6 riquadri "risultato" pre-esistenti nei dialog generatori che restano
  visivamente vuoti (solo ombra/bordo) prima del primo tiro: comportamento
  già presente prima di stanotte (il contenuto si popola solo dopo il
  click "genera"), non introdotto ora — aggiungere un messaggio
  placeholder avrebbe richiesto toccare la logica di rendering condizionale
  di 9 file, fuori dal perimetro "solo estetica".

**Verifica finale** (2026-08-19): `python3 -m compileall ui/ core/ data/`
pulito; `test_fase_d.py` 101/101 (104 costruzioni di view, due temi);
l'intera suite di progetto (35 file `test_*.py`) eseguita — 33/35 verdi,
i 2 falliti (`test_qr_scan.py`, `test_versione_app.py`) sono ambientali
(pacchetti Android/iOS non installabili in questo sandbox, tag di release
git) e già noti come tali dal changelog precedente a stanotte, non causati
da queste modifiche. `git diff --stat`: 35 file, +718/-240 righe totali
(inclusi i due fix indipendenti della stessa notte — vedi
`changelog_storico.md` — non solo FASE F).

**Non ancora verificato**: il giudizio estetico vero e proprio, su
dispositivo reale, in entrambi i temi — Davide lo farà al risveglio.

---

Ordine proposto (dal più visibile al meno):
1. **Home** — è la prima impressione. Card personaggio con ritratto grande,
   ombre, chip di classe/livello.
2. **Scheda personaggio** — stat bar e header (il pezzo più guardato dell'app),
   poi i 5 tab uno per volta partendo da Combattimento.
3. **Incantesimi** — molto contenuto testuale: è dove la tipografia paga più.
4. **Modalità Master** — le pillole ci sono già, servono ombre/raggi/densità.
5. **Mappe / Dadi / Diario / Talenti**.

---

## Rischi e punti di attenzione

1. **`assets_dir` in web mode** (A.4): tocca l'export `.dndchar`, feature già
   testata da Davide su web. Va riverificata dopo la modifica.
2. **Font su build mobile**: `flet build apk/ipa` deve includere `assets/`.
   Va verificato su un vero dispositivo (Android/iOS restano non testati anche
   per Export/Import, come già documentato).
3. **Regressione dei 153 `#ffffff`**: sostituirli è meccanico ma va fatto con
   attenzione — alcuni sono legittimamente "bianco puro" (testo su bottone
   pieno), altri sono "colore della superficie". Sono due token diversi.
4. **Nessun test visivo automatico**: la verifica resta manuale (avvio da
   terminale + web). Proposta: uno screenshot di riferimento per view prima e
   dopo, da confrontare a occhio.
5. **Ordine**: la pulizia del codice duplicato (67% tra `wizard_view` e
   `manual_form`) va **prima** della Fase E, altrimenti si restyla due volte lo
   stesso codice.

---

## FASE G — "Arcane Ledger": rifacimento radicale della palette (2026-08-20)

Richiesta esplicita di Davide: ripartire da zero sull'estetica, ignorando gli
otto giri di calibrazione della vecchia palette bordeaux/pergamena (FASE
B-F), con un solo requisito nuovo — l'app deve restare davvero utilizzabile
sia su schermo desktop sia su smartphone. Vincolo tecnico invariato: nessuna
modifica alla logica di business, solo estetica/composizione.

### Direzione

Tre accenti distinti invece di uno (prima `primary`==`danger` per scelta
esplicita — qui separati, perché in ogni palette di riferimento consultata
via skill `ui-ux-pro-max` il colore distruttivo non coincide mai col
primario):
- **Oro antico/bronzo** (`primary`/`primary_fill`/`primary_icon`) — accento
  di marca, azioni primarie, elementi hero.
- **Indaco/violetto** (`magic`) — secondo registro compositivo per contenuto
  arcano (era solo un tag semantico prima, ora guida `spells_view.py` e
  `dice_view.py` in modo assertivo).
- **Rosso vero e isolato** (`danger`/`danger_fill`/`danger_icon`) — solo
  distruttivo, mai più alias del primario.

Chiaro: pergamena calda più ricca (`bg="#f0e8db"`). Scuro: inchiostro
nero-caldo (`bg="#17130f"`, hue 28° — non il blu-slate da dashboard SaaS
generica), testo `text="#c6b795"` calibrato a ~7.4-9.3:1 (AAA con margine,
deliberatamente NON spinto oltre ~9:1 per evitare l'affaticamento/halation
già diagnosticato in FASE F sulla vecchia palette scura). Ogni valore
ricalcolato da zero con la stessa disciplina di misurazione del contrasto
WCAG di sempre (script dedicato, non a occhio) — dettagli e soglie nei
commenti di `ui/design.py::LIGHT`/`DARK`.

Tipografia invariata (Cinzel/Inter/JetBrains Mono — nessuna alternativa nel
dataset della skill batte Cinzel per un'app fantasy). Nuova taglia
`Size.HERO=40` sopra `DISPLAY`, per avere un vero momento tipografico
dominante per schermata (prima la scala si fermava a 32px e nessun titolo
risultava davvero "hero").

### Nuove primitive in `ui/design.py`

- `hero_title(text, subtitle="", is_mobile=False)` — un solo uso per
  schermata.
- `icon_badge(icon, tone, size)` — badge icona circolare tinto, estratto da
  `dialog_title()` (era l'unico punto d'uso) e riusato ovunque un'icona fa
  lavoro di etichetta.
- `card()`/`section()`/`surface()` — nuovi parametri `hero: bool` (radius/
  livello/padding maggiori, bordo pieno nell'accento invece della sola
  barra sinistra) e `density: "relaxed"|"dense"` (per le tab dati-intensive).
- `Breakpoint` — soglie allineate ai default reali di `ft.ResponsiveRow`
  (576/768/992/1200), non una scala parallela inventata.
- `generator_dialog_shell()` — shell condivisa per il pattern "form → genera
  → risultato → assegna" dei dialoghi generatori Master, applicata a 8 dei
  9 dialoghi con questa forma (il nono, `master_loot_assign_dialog.py`, ha
  una forma diversa — allocazione/revisione, non generazione — lasciato
  fuori).
- `header_row()` — intestazione di sezione estratta da `section()` e
  condivisa con `ui/theme.py::section_header()`, così i call site ancora
  legacy (`wizard_view.py`/`manual_form.py`, 60+ punti) ricevono lo stile
  nuovo senza bisogno di migrare.

### Rollout — tutte le 35 view, in 5 fasi di rischio crescente

Stessa strategia di delega a più agenti in parallelo già rodata in FASE F,
estesa a copertura totale (non solo pilota):
1. Fondamenta (`design.py`/`theme.py`) — nessuna view toccata, verificata
   isolatamente prima di procedere.
2. Rischio basso: `world_view.py`, i 15 dialoghi generatori Master,
   `home_view.py`, `feats_view.py`, `magic_items_view.py`, `dice_view.py`.
3. Rischio medio: `sheet_view.py`, `diario_tab.py`, 5 view Master
   (`master_view.py`, `master_notes_view.py`, `master_encounter_list_view.py`,
   `master_loot_view.py`, `master_npc_list_view.py`), `maps_view.py` (solo
   chrome — il sistema `Chrome`/canvas del disegno mappe resta intoccato,
   volutamente scuro in entrambi i temi).
4. Rischio più alto: `wizard_view.py`, `manual_form.py`, `combattimento_tab.py`
   (prima passaggio meccanico `**design.field_style()` sui ~30 `TextField`
   scritti a mano, poi layout/hero), `inventario_tab.py`, `esplorazione_tab.py`,
   `spells_view.py`, `master_encounter_view.py`.
5. Massima cautela: `profilo_tab.py` (5110 righe — i flussi dialog di
   level-up/multiclasse/level-down toccati SOLO per kwargs di stile, mai
   struttura/stato, esattamente l'area esclusa in FASE F) e
   `master_loot_assign_dialog.py` (logica di assegnazione reale).

**Effetto collaterale positivo, trovato più volte in modo indipendente**:
separare `primary` da `danger` ha reso visibili diversi punti dove un'azione
distruttiva (elimina, rimuovi, applica danno) usava ancora `primary_fill`/
`primary_icon` — invisibile prima perché i due colori coincidevano, un vero
bug semantico corretto in `home_view.py`, `diario_tab.py`, `sheet_view.py`,
`inventario_tab.py`, `combattimento_tab.py` (5 punti), `maps_view.py`,
`profilo_tab.py`, `dice_view.py`, `spells_view.py`.

**Regressione reale trovata e corretta**: `test_trasferimento_dispositivo.py`
verificava la visibilità del pulsante "codice di trasferimento dispositivo"
cercando l'`IconButton` solo un livello sotto `riga.controls` — la
ristrutturazione di `_member_row()` in `world_view.py` (da `ft.Row` piatta a
`design.asymmetric_row`, per il collasso responsive) ha spostato il
pulsante più in profondità nell'albero dei controlli senza cambiare NULLA
della logica di permessi/visibilità. Il test cercava nel posto sbagliato, non
la funzione aveva un bug: corretto l'helper di ricerca del test per essere
ricorsivo invece di limitarlo a un solo livello — unica modifica a un file
`test_*.py` in tutta questa fase.

**Verifica finale** (2026-08-20): `python3 -m compileall ui/ core/ data/`
pulito; `test_fase_d.py` 101/101; l'intera suite di progetto (35 file
`test_*.py`) eseguita — 34/35 verdi dopo il fix del test sopra, i 2 fallimenti
residui (`test_qr_scan.py`, `test_versione_app.py`) sono gli stessi
ambientali pre-esistenti già documentati in FASE F (pacchetti Android/iOS
non installabili in questo sandbox, controllo tag di release git), non
causati da queste modifiche.

**Deliberatamente non toccato** (stesso perimetro di FASE F, confermato
ancora valido): il canvas di disegno di `maps_view.py`, la struttura interna
dei flussi level-up/multiclasse/level-down di `profilo_tab.py` oltre ai
kwargs di stile, la logica di allocazione di `master_loot_assign_dialog.py`.

**Non ancora verificato**: il giudizio estetico vero e proprio su dispositivo
reale, in entrambi i temi e a più larghezze (375/768/1024/1440px) — verifica
umana, non automatizzabile con l'infrastruttura di test esistente.
