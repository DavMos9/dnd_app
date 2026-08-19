"""
Generatore Rapido NPC — Sezione Master. Ogni campo lasciato vuoto/"Qualsiasi"
viene risolto a caso, mai un default fisso: la generazione deve variare ad
ogni chiamata, non riproporre sempre lo stesso personaggio.

Logica pura (nessuna dipendenza Flet/DB, stesso principio di
`wizard_engine.py`/`level_manager.py`/`equipment_manager.py`/
`encounter_calculator.py`/`magic_item_generator.py`): il Master sceglie
razza/ruolo/allineamento/genere (ognuno anche lasciabile a "Qualsiasi"),
l'app genera:
  - un nome, da `data/game_data/npc_names.json` (liste inventate per questo
    progetto in stile fantasy generico, NON trascritte dal PHB — vedi la
    nota nel file stesso e il changelog CLAUDE.md);
  - tratti di personalità/ideale/legame/difetto presi da UN background PHB
    scelto a caso — stesso identico meccanismo già in uso in
    `wizard_engine.py.build_character()` per i personaggi giocanti
    (`personality_traits`/`ideals`/`bonds`/`flaws` di
    `data/game_data/backgrounds/*.json`, estratti con `random.choice`);
  - se il `role` scelto (case-insensitive, spazi normalizzati) combacia con
    una delle 21 voci dell'Appendice B "Personaggi Non Giocanti" del
    Manuale dei Mostri (Accolito/Arcimago/.../Veterano — già presenti in
    `monsters.json`), anche lo stat block di combattimento completo di
    quella voce (`GameDataLoader.get_appendix_b_stat_block()`, che verifica
    l'appartenenza alle 21 voci PRIMA di cercare in `monsters.json` — mai un
    lookup generico su tutti i 444 mostri: un ruolo come "Drago Rosso
    Antico" scritto a mano non deve mai agganciare uno stat block, solo le
    21 voci Appendice B lo fanno, per restare fedeli alla richiesta).
"""

from __future__ import annotations

import random
from typing import Any

from data.game_data.game_data_loader import GameDataLoader

_loader = GameDataLoader()

RACE_OPTIONS: tuple[str, ...] = (
    "Umano", "Elfo", "Nano", "Halfling", "Gnomo",
    "Mezzelfo", "Mezzorco", "Tiefling", "Dragonide",
)
GENDER_OPTIONS: tuple[str, ...] = ("male", "female")
GENDER_LABELS: dict[str, str] = {"male": "Maschio", "female": "Femmina"}
ALIGNMENT_OPTIONS: tuple[str, ...] = (
    "Legale Buono", "Neutrale Buono", "Caotico Buono",
    "Legale Neutrale", "Neutrale", "Caotico Neutrale",
    "Legale Malvagio", "Neutrale Malvagio", "Caotico Malvagio",
)


def get_race_options() -> list[str]:
    return list(RACE_OPTIONS)


def get_gender_options() -> list[tuple[str, str]]:
    """Lista di coppie (chiave interna, etichetta italiana) — es.
    `[("male", "Maschio"), ("female", "Femmina")]`."""
    return [(g, GENDER_LABELS[g]) for g in GENDER_OPTIONS]


def get_alignment_options() -> list[str]:
    return list(ALIGNMENT_OPTIONS)


def resolve_creature_type_and_size(race: str) -> tuple[str, str]:
    """
    Tipo creatura/Taglia "canonici" per una razza PHB — un NPC Halfling deve
    proporre Umanoide/Piccola senza che il Master debba ricordarselo a
    memoria.

    Tutte e 9 le razze di `RACE_OPTIONS` sono Umanoidi — costante 5e
    implicita, nessun JSON di razza porta una chiave `creature_type` — la
    Taglia viene invece letta da `GameDataLoader.get_race(race)["size"]`
    (fallback "Media" se la razza è risolvibile ma priva di quella chiave).

    Ritorna `("", "")` se `race` è vuota o non è una delle 9 razze PHB,
    così il chiamante (l'auto-riempimento nel form NPC) non scrive nulla
    invece di scrivere un valore inventato.
    """
    if race not in RACE_OPTIONS:
        return "", ""
    data = _loader.get_race(race)
    size = (data or {}).get("size") or "Media"
    return "Umanoide", size


def resolve_race_from_tags(tags: str) -> str:
    """
    Fallback per NPC salvati prima dell'introduzione del campo
    `MasterNpc.race`, quando la razza era scritta solo come primo segmento
    CSV di `tags` (es. "Halfling, Femmina", scritto da
    `master_npc_generator_dialog.py::_do_save()`). Ritorna il valore
    CANONICO di `RACE_OPTIONS` se il primo segmento combacia
    case-insensitive, altrimenti stringa vuota (nessuna razza risolvibile
    — non blocca né inventa nulla, il Master può sempre scegliere "Altro").
    """
    first = (tags or "").split(",", 1)[0].strip()
    for r in RACE_OPTIONS:
        if r.lower() == first.lower():
            return r
    return ""


def get_appendix_b_role_options() -> list[str]:
    """Le 21 voci con scheda di combattimento pronta (Appendice B), in
    ordine e con la casistica italiana corretta — comode da offrire in un
    Dropdown, ma `generate_npc()` accetta comunque QUALSIASI stringa come
    `role`: solo se combacia (case-insensitive) con una di queste 21
    aggancia lo stat block, altrimenti resta solo l'etichetta di ruolo."""
    return _loader.get_appendix_b_role_names()


def generate_npc(
    race: str = "",
    role: str = "",
    alignment: str = "",
    gender: str = "",
) -> dict[str, Any]:
    """
    Genera un singolo NPC casuale.

    Ogni parametro vuoto o non riconosciuto viene risolto a caso (razza tra
    le 9 PHB, genere maschio/femmina, allineamento tra i 9) — `role` resta
    sempre libero (nessun fallback casuale: un ruolo vuoto produce
    semplicemente un NPC senza etichetta di ruolo né scheda di
    combattimento, esattamente come un NPC "puro ruolo" creato a mano nella
    Rubrica).

    Ritorna un dict con tutti i dati generati, pronto per essere passato a
    `master_repo.create_npc()` (NPC senza stat block) o
    `master_repo.create_npc_from_monster()` (NPC con stat block, quando
    `has_stat_block` è `True`) da parte del chiamante (la UI del dialog, che
    decide come persisterlo in Rubrica — questo modulo non scrive mai su
    nessun database).
    """
    resolved_race = race if race in RACE_OPTIONS else random.choice(RACE_OPTIONS)
    resolved_gender = gender if gender in GENDER_OPTIONS else random.choice(GENDER_OPTIONS)
    resolved_alignment = alignment if alignment in ALIGNMENT_OPTIONS else random.choice(ALIGNMENT_OPTIONS)

    names = _loader.get_npc_names(resolved_race, resolved_gender)
    if not names:
        # Difesa in profondità: non dovrebbe mai accadere (tutte e 9 le
        # razze hanno liste complete in npc_names.json), ma non deve mai
        # bloccare la generazione — ripiega sulla lista Umano.
        names = _loader.get_npc_names("Umano", resolved_gender) or ["Sconosciuto"]
    name = random.choice(names)

    bg_names = _loader.get_background_names()
    background_used = random.choice(bg_names) if bg_names else ""
    bg_data = (_loader.get_background(background_used) or {}) if background_used else {}
    traits_list = bg_data.get("personality_traits") or []
    ideals_list = bg_data.get("ideals") or []
    bonds_list = bg_data.get("bonds") or []
    flaws_list = bg_data.get("flaws") or []

    trait = random.choice(traits_list) if traits_list else ""
    if ideals_list:
        chosen_ideal = random.choice(ideals_list)
        ideal = (
            f"{chosen_ideal.get('name', '')}. {chosen_ideal.get('description', '')} "
            f"({chosen_ideal.get('alignment', '')})"
        ).strip()
    else:
        ideal = ""
    bond = random.choice(bonds_list) if bonds_list else ""
    flaw = random.choice(flaws_list) if flaws_list else ""

    role_clean = " ".join((role or "").strip().split())
    monster = _loader.get_appendix_b_stat_block(role_clean) if role_clean else None

    return {
        "name": name,
        "race": resolved_race,
        "gender": resolved_gender,
        "gender_label": GENDER_LABELS.get(resolved_gender, resolved_gender),
        "alignment": resolved_alignment,
        "role": role_clean,
        "personality_trait": trait,
        "ideal": ideal,
        "bond": bond,
        "flaw": flaw,
        "background_used": background_used,
        "has_stat_block": monster is not None,
        "monster": monster,
    }


def generate_npcs(
    count: int = 1,
    race: str = "",
    role: str = "",
    alignment: str = "",
    gender: str = "",
) -> list[dict[str, Any]]:
    """Genera `count` NPC indipendenti (ognuno con la propria risoluzione
    casuale di razza/genere/allineamento/nome/background — mai la stessa
    estrazione ripetuta N volte). `count` clampato a un minimo di 1."""
    n = max(1, count)
    return [generate_npc(race=race, role=role, alignment=alignment, gender=gender) for _ in range(n)]
