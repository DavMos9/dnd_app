# Multiclasse (PHB cap. 6) — progettazione preliminare

> Documento di **sola progettazione**, richiesto da Davide il 2026-07-26
> ("Sì, progettiamolo a parte"): non va implementato in questo ciclo.
> Serve a sapere in anticipo quanto costa e cosa romperebbe, così quando si
> deciderà di farlo non si parte da zero.
>
> **Nessun dato di regolamento è riportato qui.** Le due tabelle necessarie
> (prerequisiti di caratteristica per classe, e la tabella degli slot per
> incantatore multiclasse) vanno lette visivamente dalle pagine del PHB italiano
> prima di scrivere qualunque JSON — non tradotte, non ricostruite a memoria.

---

## 1. Perché è un intervento grosso

Oggi il personaggio ha **una** classe: `Character.class_name: str`,
`Character.subclass: str`, `Character.level: int`. Questi tre campi sono la base
di quasi tutta la logica di gioco dell'app. Una ricerca su `class_name` mostra che
viene letto in praticamente ogni modulo:

- `core/level_manager.py` — l'intero motore di level-up (`get_level_up_steps`)
- `core/wizard_engine.py` — creazione personaggio
- `data/repositories/character_repo.py` — `auto_init_spell_slots`,
  `init_class_resources`, `apply_class_base_proficiencies`,
  `sync_bonus_domain_spells`, `sync_borrowed_spellcasting_ability`,
  `calculate_and_update_ca`, `get_effective_speed`
- `config/settings.py` — `get_class_resource_defaults`, `get_permanent_class_hp_bonus`
- `ui/views/spells_view.py` — `_PREP_FULL`/`_PREP_HALF`/`_KNOW_CLASSES`, tetto
  dei preparati, CD e bonus di attacco
- i 5 tab della scheda + i 2 flussi di creazione

Non è quindi "aggiungere un campo": è **cambiare l'unità di ragionamento** da
"la classe del personaggio" a "le classi del personaggio, ciascuna con il suo
livello".

---

## 2. Modello dati proposto

Nuova tabella, **senza toccare le colonne esistenti** (retrocompatibilità totale:
un personaggio a classe singola continua a funzionare identico):

```sql
character_classes (
  id TEXT PK,
  character_id TEXT FK → characters(id) ON DELETE CASCADE,
  class_name TEXT NOT NULL,
  subclass   TEXT DEFAULT '',
  level      INTEGER NOT NULL,
  is_primary INTEGER DEFAULT 0,   -- la classe di 1° livello: decide competenze iniziali ed equipaggiamento
  order_index INTEGER DEFAULT 0,  -- ordine di acquisizione (serve al level-up)
  created_at, updated_at
)
```

`characters.class_name` / `subclass` / `level` **restano** e diventano *derivati*:
- `class_name` = descrizione compatta (`"Guerriero 3 / Ladro 2"`) usata per la
  visualizzazione — oppure resta la classe primaria e la stringa composita si
  calcola a runtime (da decidere: la prima opzione rompe i confronti tipo
  `class_name.lower() == "warlock"` sparsi nel codice, la seconda no).
- `level` = **livello totale del personaggio** = somma dei livelli di classe.
  Questo va mantenuto rigorosamente, perché bonus competenza, PE e molti effetti
  dipendono dal livello totale, non da quello di classe.

**Migrazione**: al primo avvio, per ogni personaggio esistente si crea una riga
`character_classes` da `class_name`/`subclass`/`level` con `is_primary=1`.
Idempotente, stesso pattern dei self-healing già presenti nel progetto.

---

## 3. I 7 punti di logica da riscrivere

| # | Cosa | Regola PHB coinvolta | Difficoltà |
|---|---|---|---|
| 1 | **Punti ferita** | il dado vita è quello della classe con cui si prende il livello; il massimo si applica solo al 1° livello della classe primaria | media |
| 2 | **Bonus competenza** | dipende dal livello **totale**, non di classe — già corretto se `level` resta la somma | bassa |
| 3 | **Competenze iniziali** | prendendo una nuova classe si ottiene solo un **sottoinsieme** delle sue competenze (tabella dedicata nel PHB, diversa dalla creazione) | media |
| 4 | **Slot incantesimo** | tabella **degli incantatori multiclasse** con un livello da incantatore calcolato (pieni contano tutto, metà contano metà arrotondata per difetto, un terzo un terzo) — è una tabella nuova, oggi in `spell_slot_progressions.json` ci sono solo `full_caster`/`half_caster`/`warlock` | **alta** |
| 5 | **Slot del Patto separati** | il Warlock non si fonde con gli altri: mantiene i suoi slot a parte | alta |
| 6 | **Incantesimi conosciuti/preparati** | si calcolano **per classe**, col livello di quella classe, mentre gli slot sono condivisi. È il punto più contro-intuitivo del capitolo | **alta** |
| 7 | **ASI, Attacco Extra, privilegi** | non si sommano tra classi (Attacco Extra di Guerriero e Ranger non cumulano); gli ASI arrivano ai livelli della singola classe | media |

Inoltre: **prerequisiti di caratteristica** (non puoi prendere una seconda classe
senza il punteggio minimo) — vanno letti dal manuale e verificati alla scelta,
con la possibilità di ignorarli per house rule (coerente con `proficiency_bonus_override`
e gli altri override già presenti nel progetto).

---

## 4. Impatto sulla UI

- **Creazione personaggio**: nessuna modifica. Si nasce sempre a classe singola,
  il multiclasse arriva col level-up (come nel manuale).
- **Level-up** (`profilo_tab.py`, il dialog da ~2000 righe): nuovo primo passo
  "in quale classe prendi questo livello?" con l'elenco delle classi possedute +
  "nuova classe" (filtrata sui prerequisiti). Tutti gli step successivi
  (`get_level_up_steps`) vanno calcolati **sulla classe scelta e sul suo livello**,
  non sul livello totale — è la modifica più delicata di tutto l'intervento.
- **Level-down**: deve sapere da quale classe togliere il livello.
- **Scheda**: header e stat bar mostrano `"Guerriero 3 / Ladro 2"`; le sezioni
  "Abilità di Classe" e "Risorse di Classe" uniscono le fonti di tutte le classi.
- **Incantesimi**: la vista deve gestire più liste di classe contemporaneamente
  (un Chierico/Mago prepara dalla lista del chierico *e* dal libro del mago, con
  regole diverse per ciascuna) — oggi `_PREP_FULL`/`_KNOW_CLASSES` presumono una
  sola classe.

---

## 5. Prerequisiti prima di iniziare

1. **Pulizia del codice duplicato**: farlo con `wizard_view.py`/`manual_form.py`
   ancora duplicati al 67% e con `profilo_tab.py` a 4.469 righe significa
   moltiplicare il lavoro. Il multiclasse va **dopo** la pulizia.
2. **Trascrizione dal manuale** delle 2 tabelle (prerequisiti, incantatore
   multiclasse) + del testo delle competenze concesse in multiclasse.
3. **Test di regressione esistenti**: va verificato che tutti i personaggi a
   classe singola continuino a comportarsi identici — la matrice già in uso nel
   progetto (12 classi × sottoclassi × livelli 1-20) è il punto di partenza.

---

## 6. Stima onesta

Non è un task da una sessione. Realisticamente:
- 1 sessione: trascrizione dati + schema DB + migrazione + repository
- 1-2 sessioni: riscrittura di `level_manager` e degli slot incantesimo multiclasse
- 1 sessione: UI del level-up
- 1 sessione: scheda + incantesimi
- 1 sessione: test di regressione

**Raccomandazione**: farlo solo dopo che restyle, pulizia e le 4 feature
autorizzate sono chiuse. È l'unico intervento del progetto che può far regredire
funzionalità già collaudate su tutte le 12 classi.
