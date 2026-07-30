# Restyle — progettazione del sistema visivo (Fasi A · B · C · D)

> Documento di **progettazione**. Nessuna riga di codice applicata.
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
| `section(title, content, collapsible=False, key=None)` | `section_header()` + Column manuale | opzione comprimibile con memoria dello stato (serve al punto 4 della revisione) |
| `pill(icon, label, color, on_click)` | le 3 copie di `_tool_pill`/`_action_pill`/`_header_actions` in master_view / master_encounter_view / home_view | oggi lo stesso widget è duplicato in 3 file |
| `chip(text, tone)` | i ~40 chip/badge inline | toni: neutro/primario/magia/successo/attenzione/pericolo |
| `stat_tile(value, label, on_click=None)` | `stat_badge()` (dead) + i box caratteristica di `sheet_view` | tap-target ≥44px |
| `metric_bar(value, max, tone)` | le ProgressBar di HP/peso | animata (Fase C) |
| `empty_state(icon, title, hint, action)` | i ~12 stati vuoti scritti a mano | uniformi |

**Migrazione**: non tutto in un colpo. Le primitive nascono in Fase A, le view
migrano in Fase E, una per volta. Una view non migrata resta funzionante.

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

**Tema scuro** (nuovo)

| token | hex | contrasto misurato |
|---|---|---|
| `bg` | `#14131a` | — |
| `surface` | `#1e1c26` | — |
| `surface_alt` | `#282533` | — |
| `border` | `#3a3648` | — |
| `text` | `#f0ece4` | 14.3 su surface (AAA) |
| `text_2` | `#c2bcae` | 8.88 (AAA) |
| `text_3` | `#9c94a8` | 5.14 (AA) |
| `primary` | `#f2696d` | 5.62 su surface — foreground scuro `#241012` sul pieno 6.06 |
| `magic` | `#7aa2f7` | 6.67 |
| `success` | `#4ec27f` | 7.48 |
| `warning` | `#e0a028` | 7.39 |

Note importanti emerse dal calcolo:
- In dark mode i bottoni pieni devono usare un **foreground scuro** sull'accento
  chiaro (convenzione Material 3): bianco su `#f2696d` dà solo 3.91 → sotto la
  soglia AA. Questa è la ragione per cui il `primary` scuro non può essere lo
  stesso `#c0182c` del tema chiaro.
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
> **La Fase D è ora la sola cosa che separa l'app dal tema scuro**: nelle view non
> resta nessun colore statico, serve solo l'interruttore + persistenza.

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
