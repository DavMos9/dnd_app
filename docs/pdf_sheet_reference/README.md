# Export scheda PDF — materiale di ricognizione (2026-07-24)

Questa cartella (`docs/pdf_sheet_reference/`) contiene tutto il necessario per implementare
l'export della scheda personaggio nel PDF ufficiale D&D 5e italiano, senza dover ripetere
l'analisi del file sorgente.

## File presenti

- `dnd_blankcharactersheet_it.pdf` — il template originale caricato da Davide (3 pagine,
  594×783 pt ciascuna). **Nessun campo AcroForm** — è un PDF vettoriale piatto (testo/linee/
  curve), verificato con `pypdf.PdfReader.get_fields()` → `None`. L'unico modo per "compilarlo"
  è un overlay di testo a coordinate fisse, fuso poi con lo sfondo originale (`pypdf` per il
  merge, `reportlab` per disegnare l'overlay).
- `raw_extraction.json` — dump completo di `pdfplumber` per tutte e 3 le pagine: `words`
  (ogni parola con bounding box `x0/top/x1/bottom` in pt, origine in alto a sinistra),
  `rects` (rettangoli vettoriali), `lines` (segmenti), `curve_boxes` (bounding box dedupli-
  cati di ogni forma disegnata a curve di Bézier — cerchi/ovali/scudi decorativi; **non**
  sono cerchi già isolati, sono bbox aggregati di tutti i segmenti di una stessa forma,
  vanno letti insieme all'immagine per capire cosa rappresentano).
- `grid-1.png`, `grid-2.png`, `grid-3.png` — le 3 pagine renderizzate a 150dpi con una
  griglia sovrapposta ogni 25pt (etichette rosse = coordinata X in pt, blu = coordinata Y
  in pt, stesso sistema di origine di `raw_extraction.json`). Usarle per leggere a occhio
  la posizione di elementi grafici (cerchi, caselle) che non hanno testo associato.

## Convenzione di layout scoperta (vale per quasi tutti i campi)

La scheda ufficiale scrive l'etichetta ("CLASSE & LIVELLO", "FORZA", nomi delle abilità, ecc.)
in basso rispetto allo spazio bianco assegnato al valore. **Il valore va scritto SOPRA
l'etichetta**, non sotto — verificato sul box header di pagina 1 (Classe&Livello/Background/
Nome Giocatore sopra, Razza/Allineamento/Punti Esperienza sotto, ciascuna riga alta ~30pt
con la label ridotta in basso e lo spazio bianco sopra) e confermato coerente su tutte le
altre sezioni ispezionate (abilità, tiri salvezza, ecc.).

## Struttura Pagina 1 (scheda principale)

- Header in alto a destra (box `x=253.8..567.7, y=35.0..95.6`): 3 colonne × 2 righe
  (Classe&Livello | Background | Nome Giocatore // Razza | Allineamento | Punti Esperienza).
  Colonne separate approssimativamente a x≈376 e x≈473.
- "NOME PERSONAGGIO" è scritto sul nastro/banner decorativo a sinistra (circa
  `x=60..250, y=45..85`), il valore (nome vero) va sopra la label, centrato, font grande
  (14-16pt) vista la cornice ampia.
- 6 blocchi caratteristica (FORZA/DESTREZZA/COSTITUZIONE/INTELLIGENZA/SAGGEZZA/CARISMA),
  ciascuno alto ~71pt, impilati a sinistra (`x≈20..115`), y di partenza rispettivamente
  ≈125, ≈196, ≈267, ≈338, ≈409, ≈481 (label a inizio blocco, poi lo scudo con dentro il
  modificatore, poi un piccolo ovale in basso col punteggio grezzo — **posizione esatta
  di centro-cerchio e raggio non ancora calibrata pixel-per-pixel**, va rifinita a vista
  con `grid-1.png` prima di scrivere il modulo).
- CA / Iniziativa / Velocità: 3 scudi affiancati intorno a `x=216..400, y=125..180`
  (label "CA" / "INIZIATIVA" / "VELOCITÀ" a y≈166-169, valore sopra).
- Ispirazione (piccolo quadrato) e Bonus di Competenza (cerchio) subito sotto l'header,
  y≈125-175 — posizione esatta del cerchio competenza da rifinire a vista.
- Le 18 abilità e i 6 tiri salvezza: lista verticale a `x=123.2` (nome abilità), pallino
  di competenza a sinistra del nome (colonna x da confermare a vista, verosimilmente
  x≈108-113), il modificatore numerico va scritto sulla riga vuota fra pallino e nome.
  Posizioni Y di ogni abilità già note per intero in `raw_extraction.json` (word "Acrobazia"
  ha top=316.9, ecc. — tutte le 18 sono lì, in ordine alfabetico italiano).
- Percezione Passiva: box in basso a sinistra, label a y≈590.
- PF massimo / attuali / temporanei, Dadi Vita, TS contro morte (successi/fallimenti a
  cerchi): colonna centrale, y≈195-350 — coordinate label già note, cerchi da rifinire.
- Tabella Armi (NOME / BONUS ATT. / DANNI-TIPO): 3 righe visibili sul foglio, header a
  y≈378, righe sotto. **Decisione presa con Davide:** se il personaggio ha più di 3 armi,
  compilare solo le prime 3 nella tabella e aggiungere le rimanenti come elenco compresso
  nello spazio "EQUIPAGGIAMENTO".
- Monete (MR/MA/ME/MO/MP): 5 caselle in basso a sinistra, y≈598/624/650/676/702.
- Box grandi di solo testo (riempire con auto-shrink font se il contenuto eccede lo
  spazio — **decisione presa con Davide**): Tratti Caratteriali/Ideali/Legami/Difetti
  (colonna destra, y≈183-750), Altre Competenze & Linguaggi / Equipaggiamento /
  Privilegi & Tratti (fascia bassa, y≈751-900 area libera fino al bordo pagina).

## Struttura Pagina 2 (retro / background)

Campi semplici, tutti con label + valore sopra: Età/Altezza/Peso (y≈58), Nome
Personaggio/Occhi/Carnagione/Capelli (y≈85-92), poi grandi box di solo testo: Aspetto
(sinistra), Simbolo/fede + Alleati&Organizzazioni (destra, y≈137-350), Tratti&Privilegi
Aggiuntivi (y≈574), Storia (sinistra, y≈749) e Tesoro (destra, y≈749) — questi ultimi
due condividono la fascia finale della pagina.

## Struttura Pagina 3 (incantesimi) — la più complessa

- Header in alto (stesso box coordinate dell'header di pagina 1: `x=253.8..567.7,
  y=38.6..99.2`), diviso in 3 colonne da linee verticali a x≈337 e x≈477.8:
  Caratteristica da Incantatore | CD Tiro Salvezza Incantesimi | Bonus di Attacco
  Incantesimi. Valore sopra la label (label a y≈81-94), quindi scrivere intorno a
  y≈55-65.
- Corpo pagina: **griglia a 3 colonne**, ciascuna larga ~170pt:
  - Colonna 1: `x=24.3..195.7` → contiene i livelli **0 (trucchetti), 1, 2**
  - Colonna 2: `x=221.7..384.8` → contiene i livelli **3, 4, 5**
  - Colonna 3: `x=408.9..571.9` → contiene i livelli **6, 7, 8, 9**
  Ogni livello ha un marcatore esagonale col numero, poi una "pillola" (capsula divisa
  a metà da una piccola clessidra) per **Slot Totali** (metà sinistra) / **Slot Spesi**
  (metà destra) — tranne il livello 0 (trucchetti), che non ha slot e la pillola contiene
  solo la scritta "TRUCCHETTI". Sotto ogni livello: righe vuote con un pallino a sinistra
  (checkbox "preparato") + spazio per il nome dell'incantesimo.
  Coordinate Y del marcatore di ciascun livello (già estratte, in `raw_extraction.json`,
  pagina 3): 0→144.8, 1→312.5, 2→541.1 (colonna 1); 3→144.8, 4→370.4, 5→596.9 (colonna 2);
  6→144.8, 7→314.5, 8→484.3, 9→625.1 (colonna 3).
  Le didascalie "LIVELLO/INC.MO", "SLOT TOTALI", "SLOT SPESI", "PREPARATI",
  "NOME INCANTESIMO" compaiono **una sola volta nell'intero foglio** (accanto al livello 1,
  colonna 1) — è il template ufficiale, il resto dei livelli riusa lo stesso schema senza
  ripetere le etichette.
- **Decisione presa con Davide:** includere questa pagina nel PDF solo se
  `character.spellcasting_ability` è valorizzata (copre sia gli incantatori puri sia le
  sottoclassi "in prestito dal Mago" — Mistificatore Arcano/Cavaliere Mistico — grazie a
  `sync_borrowed_spellcasting_ability()` già esistente in `character_repo.py`). Nessuna
  pagina 3 per i personaggi non incantatori.

## Decisioni di design già confermate con Davide (non richiedono altre domande)

1. Testo che eccede lo spazio della casella → **riduci il font automaticamente**
   (non troncare, non aggiungere pagine extra) per restare fedeli al layout ufficiale.
2. Più di 3 armi → **le prime 3 equipaggiate nella tabella Armi**, le altre come elenco
   compresso nello spazio "Equipaggiamento".
3. Pagina 3 (incantesimi) → solo se il personaggio ha una `spellcasting_ability`.

## Cosa manca ancora prima di scrivere il modulo

1. Calibrare a vista (con `grid-1.png`/`grid-2.png`/`grid-3.png`) le coordinate esatte
   di: cerchi modificatore/punteggio delle 6 caratteristiche, cerchio Bonus di Competenza,
   cerchio Ispirazione, scudi CA/Iniziativa/Velocità, colonna X dei pallini competenza
   (abilità + tiri salvezza), box PF (max/attuali/temporanei), riquadro Dadi Vita, cerchi
   TS contro morte (successi/fallimenti), le 5 caselle moneta, la griglia armi (3 righe),
   i box grandi di solo testo (bounding box preciso per il word-wrap), pagina 2 per intero
   (Simbolo/fede, Aspetto, Alleati&Organizzazioni, Tratti Aggiuntivi, Storia, Tesoro),
   e su pagina 3 le righe vuote sotto ogni livello (per nome incantesimo + pallino
   preparato) e la larghezza esatta di ogni "pillola" slot totali/spesi.
2. Creare `core/pdf_sheet_exporter.py` (modulo puro, no Flet): costruisce un overlay
   per pagina con `reportlab.pdfgen.canvas`, poi fonde overlay+template con
   `pypdf.PdfWriter`/`PdfReader` (`page.merge_page()`).
3. Aggiungere `reportlab` e `pypdf` a `requirements.txt` (non ancora presenti — oggi il
   progetto ha solo `flet`/`Pillow`).
4. Copiare il template in `dnd_app/assets/character_sheet_template.pdf` (asset bundlato
   con l'app, letto a runtime — **non richiede internet né dati esterni**).
5. Wiring UI: bottone "Esporta Scheda PDF" (probabile posizione: header di `SheetView` o
   `ProfiloTab`, accanto alle altre azioni), riusando lo stesso pattern cross-platform
   già collaudato per l'export `.dndchar` in `home_view.py` (dialog nativo desktop via
   subprocess, download reale in web via `assets_dir`, `FilePicker.save_file()` su mobile).
6. Aggiornare `CLAUDE.md` a fine implementazione con lo stesso livello di dettaglio già
   usato per le altre feature del progetto (changelog, verifica, TODO chiusa).
