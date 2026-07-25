"""
Generatore di Incontri Casuali per la Modalità Master — logica pura (nessuna
dipendenza Flet/DB), stesso principio architetturale di
`core/encounter_calculator.py`/`core/treasure_generator.py`/
`core/trap_generator.py`: nessuna scrittura persistente, solo funzioni che
prendono dati (il bestiario già caricato via
`ui.components.monster_picker.load_monsters()`) e restituiscono una lista di
mostri (dict grezzi di `monsters.json`).

Due modalità, entrambe confermate da Davide (2026-07-25, via `AskUserQuestion`
— "Modalità di calcolo del grado di sfida per il Generatore Incontri
Casuali?" → "Entrambe le modalità (consigliato)"):

- **Diretta**: il Master fissa un intervallo di Grado di Sfida (GS) + un
  "tema" (il campo `type` del bestiario, es. "Non morto"/"Umanoide"/"Bestia")
  + un numero di mostri desiderato. Estrazione casuale CON ripetizione
  (`random.choices`) dal pool filtrato — le ripetizioni sono volute e
  realistiche (es. "4 goblin"), non un difetto; ad ogni chiamata il
  risultato cambia (nessun seed fisso), coerente con la richiesta esplicita
  di Davide ("la generazione... non deve generare sempre gli stessi...
  incontri").

- **Per Gruppo**: il Master fissa i livelli del gruppo (PG reali + eventuali
  "PG fantasma", stesso concetto già usato dal Calcolatore Difficoltà in
  `ui/views/master/master_encounter_view.py`) + una difficoltà bersaglio
  (facile/medio/difficile/letale) + un tema (+ opzionale intervallo GS) —
  l'algoritmo assembla un gruppo di mostri passo per passo, scegliendo ad
  ogni iterazione un candidato CASUALE tra quelli che rientrano nel budget
  PE residuo (ricalcolato ogni volta con
  `encounter_calculator.calculate_difficulty`, la stessa funzione già usata
  e verificata dal Calcolatore Difficoltà), fino a raggiungere la soglia PE
  della difficoltà scelta. Nessun ordine deterministico: la scelta del
  candidato ad ogni passo usa `random.choice`, quindi due generazioni con lo
  stesso identico bersaglio producono quasi sempre un incontro diverso.

Il tema è ricavato interamente dal campo `type` già presente e verificato in
`monsters.json` (444 mostri, interamente auditati) — nessuna nuova tabella di
classificazione da mantenere. Tre normalizzazioni deliberate (non modifiche
al dato, solo alla chiave usata per raggruppare in UI):
  - "Non Morto"/"Non morto" (incoerenza di maiuscole nel dato originale, 6
    voci contro 23) → un solo bucket "Non morto".
  - "Diavolo" (3 voci: ARCANALOTH/NYCALOTH/ULTROLOTH — in realtà Yugoloth,
    un mistag di trascrizione di una sessione precedente) → incluso nel
    bucket "Immondo" (gli Yugoloth sono concettualmente immondi).
  - "Mostruosità Mastodontica" (1 sola voce, TARRASQUE) → incluso nel bucket
    "Mostruosità" (nessun Master sceglierebbe un tema per un solo mostro).
"""

from __future__ import annotations

import random

from core.encounter_calculator import (
    DIFFICULTY_ORDER,
    calculate_difficulty,
    encounter_multiplier,
    get_pe_threshold,
)
from data.game_data.game_data_loader import cr_to_float, parse_monster_xp

# Tetto di sicurezza anti-loop per la modalità "Per Gruppo" — mai raggiunto
# in pratica per un incontro "letale" plausibile con un gruppo normale,
# previene comunque un ciclo infinito in casi limite (es. tema con un solo
# mostro fortissimo e gruppo di livello altissimo).
_MAX_MONSTERS_PER_GROUP_MODE = 15

_THEME_MERGE: dict[str, str] = {
    "non morto": "Non morto",
    "diavolo": "Immondo",
    "immondo": "Immondo",
    "mostruosità mastodontica": "Mostruosità",
    "mostruosità": "Mostruosità",
}


def _normalize_theme(raw_type: str) -> str:
    """Riduce il campo `type` grezzo di un mostro al bucket-tema usato per il
    filtro (vedi le 3 normalizzazioni nel docstring di modulo). Per i tipi
    che non necessitano merge (es. "Bestia", "Costrutto") ritorna il dato
    originale invariato."""
    key = (raw_type or "").strip().lower()
    return _THEME_MERGE.get(key, (raw_type or "").strip())


def get_theme_options(monsters: list[dict]) -> list[str]:
    """Elenco ordinato di temi disponibili nel pool fornito (dopo
    normalizzazione), per popolare il Dropdown "Tema" della UI. Non include
    mai una voce vuota — l'opzione "Qualsiasi" (nessun filtro tema) va
    aggiunta dal chiamante come prima voce del Dropdown."""
    themes = {_normalize_theme(m.get("type", "")) for m in monsters}
    themes.discard("")
    return sorted(themes)


def filter_by_theme(monsters: list[dict], theme: str) -> list[dict]:
    """Ritorna solo i mostri il cui tema normalizzato combacia con `theme`.
    `theme` vuoto/falsy → nessun filtro (l'intero pool)."""
    if not theme:
        return list(monsters)
    return [m for m in monsters if _normalize_theme(m.get("type", "")) == theme]


def filter_by_cr_range(monsters: list[dict], cr_min: float = 0.0, cr_max: float = 9999.0) -> list[dict]:
    """Ritorna solo i mostri con Grado di Sfida nell'intervallo [cr_min,
    cr_max] (inclusivo, con una piccola tolleranza in virgola mobile). Un
    mostro senza GS numerico parsabile (es. il caso speciale "DRAGO FATATO",
    GS testuale non numerico — vedi `cr_to_float`) viene escluso solo se
    `cr_max` è finito, incluso se non c'è alcun limite superiore esplicito
    (per non farlo sparire silenziosamente da una ricerca "senza filtri
    GS")."""
    out: list[dict] = []
    for m in monsters:
        v = cr_to_float(m.get("cr", ""))
        if v >= 9999.0:
            if cr_max >= 9999.0:
                out.append(m)
            continue
        if cr_min - 1e-9 <= v <= cr_max + 1e-9:
            out.append(m)
    return out


def generate_direct(
    monsters: list[dict],
    theme: str = "",
    cr_min: float = 0.0,
    cr_max: float = 9999.0,
    count: int = 4,
) -> list[dict]:
    """
    Modalità "Diretta": estrazione casuale CON ripetizione di `count` mostri
    dal pool filtrato per tema + intervallo GS. Ogni chiamata è indipendente
    (nessun seed fisso) — stesso bersaglio, risultati diversi ad ogni
    generazione. Lista vuota se il pool filtrato è vuoto (nessun mostro
    combacia con tema/GS scelti) o `count <= 0` — il chiamante mostra un
    messaggio informativo invece di un errore.
    """
    pool = filter_by_cr_range(filter_by_theme(monsters, theme), cr_min, cr_max)
    if not pool or count <= 0:
        return []
    return random.choices(pool, k=count)


def generate_for_party(
    monsters: list[dict],
    party_levels: list[int],
    difficulty: str,
    theme: str = "",
    cr_min: float = 0.0,
    cr_max: float = 9999.0,
) -> list[dict]:
    """
    Modalità "Per Gruppo": assembla un incontro CASUALE il cui PE modificato
    (calcolato con `calculate_difficulty`, la stessa funzione già in uso nel
    Calcolatore Difficoltà) raggiunge la soglia PE della difficoltà
    bersaglio per questo gruppo.

    Algoritmo goloso (greedy) con scelta casuale ad ogni passo: ricalcola il
    budget PE residuo (tenendo conto del moltiplicatore che risulterebbe
    aggiungendo un mostro in più — il moltiplicatore dipende dal numero
    totale di mostri, non solo dalla loro somma PE) e pesca un candidato A
    CASO tra quelli che stanno nel budget residuo (con una tolleranza del
    25%, per non restare sistematicamente sotto-soglia quando nessun mostro
    combacia perfetto); si ferma quando la soglia è raggiunta, quando nessun
    candidato regge più nel budget, o dopo un tetto di sicurezza di mostri.
    Non è un solutore esatto (il DMG stesso non ne prevede uno per questo
    problema) — è uno strumento di supporto: il Master può sempre
    rigenerare o aggiustare a mano nel tracker di combattimento dopo
    l'aggiunta.

    Lista vuota se `party_levels` è vuoto, `difficulty` non è una delle 4
    categorie PHB, o il pool filtrato è vuoto.
    """
    if not party_levels or difficulty not in DIFFICULTY_ORDER:
        return []
    pool = filter_by_cr_range(filter_by_theme(monsters, theme), cr_min, cr_max)
    if not pool:
        return []

    target_xp = sum(get_pe_threshold(lvl, difficulty) for lvl in party_levels)
    if target_xp <= 0:
        return []

    assembled: list[dict] = []
    xp_so_far: list[int] = []

    for _ in range(_MAX_MONSTERS_PER_GROUP_MODE):
        result = calculate_difficulty(xp_so_far, party_levels)
        if assembled and result["adjusted_xp"] >= target_xp:
            break

        tentative_count = len(assembled) + 1
        mult = encounter_multiplier(tentative_count, len(party_levels)) or 1.0
        raw_budget_left = max(0.0, (target_xp - result["adjusted_xp"]) / mult)

        eligible = [m for m in pool if parse_monster_xp(m.get("xp", 0)) <= raw_budget_left * 1.25]
        if not eligible:
            if not assembled:
                # Anche il mostro più debole del pool eccede il budget: lo
                # aggiungiamo comunque (un solo mostro) — meglio un incontro
                # sovradimensionato rispetto al bersaglio che un incontro
                # vuoto senza alcun mostro generato.
                weakest = min(pool, key=lambda m: parse_monster_xp(m.get("xp", 0)))
                assembled.append(weakest)
                xp_so_far.append(parse_monster_xp(weakest.get("xp", 0)))
            break

        choice = random.choice(eligible)
        assembled.append(choice)
        xp_so_far.append(parse_monster_xp(choice.get("xp", 0)))

    return assembled
