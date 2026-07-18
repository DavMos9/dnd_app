"""
WeaponCalculator: calcolo del tiro per colpire, del tiro per i danni e della
competenza effettiva di un'arma equipaggiata.

Nessuna dipendenza da Flet: modulo puro, testabile in isolamento (stessa
convenzione di wizard_engine.py / level_manager.py / equipment_manager.py —
"Core: mai dipendenze da Flet").

Contesto (bug report Davide, 2026-07-17, punti 3+4): il campo `attack_bonus`
di `Weapon` esisteva già ma non veniva mai sommato a nulla — l'app mostrava
solo il numero grezzo inserito dal giocatore, senza calcolare il vero tiro
per colpire (modificatore caratteristica + bonus competenza se competente +
bonus magico dell'arma, che può essere negativo per un'arma maledetta). La
competenza stessa non veniva mai verificata contro le competenze arma
possedute dal personaggio.

Decisioni di design confermate da Davide (AskUserQuestion, 2026-07-17):
  - Calcolo automatico con possibilità di override manuale del TOTALE
    (Weapon.attack_total_override / attack_override_value).
  - Per le armi con proprietà "Accurata": automatico con il modificatore
    più alto tra Forza e Destrezza, ma sempre scegliibile a mano dal
    giocatore (Weapon.finesse_ability: "" | "str" | "dex").
  - Competenza determinata dal "tipo" dell'arma (Weapon.weapon_category:
    "semplice" | "guerra"), verificato anche per armi homebrew (che quindi
    devono sempre specificare una categoria in creazione), con possibilità
    di competenza manuale garantita da una specifica arma (es. arma magica
    che concede automaticamente competenza) via Weapon.proficiency_override.

Regola PHB per la caratteristica usata (Cap.9 "Combattimento", "Tiro per
Colpire in Mischia"/"Tiro per Colpire a Distanza", + Cap.5 proprietà
"Accurata"/"Lancio"):
  - Arma da mischia: modificatore di Forza.
  - Arma da distanza (proprietà "Munizioni", es. arco/balestra): modificatore
    di Destrezza.
  - Arma da mischia con la proprietà "Lancio" (es. ascia, giavellotto), se
    lanciata: usa lo STESSO modificatore che userebbe in mischia (quindi
    Forza, salvo sia anche Accurata) — il tipo di attacco (mischia vs
    lanciata) non è tracciato separatamente su Weapon in questo progetto,
    quindi "Lancio" da sola non cambia la caratteristica di default.
  - Proprietà "Accurata" (Finesse): il personaggio può scegliere Forza o
    Destrezza, la stessa per attacco e danno. Di default si usa la più
    alta tra le due (scelta comune, quasi sempre ottimale), sovrascrivibile
    dal giocatore.
"""

from dataclasses import dataclass


@dataclass
class AttackContext:
    """Vista minima di un'arma sufficiente al calcolo — disaccoppiata da
    data.models.Weapon per restare un modulo core senza dipendenze verso
    il resto del progetto."""
    properties: str
    range_normal: int
    weapon_category: str          # "semplice" | "guerra" | ""
    proficiency_override: bool
    finesse_ability: str          # "" | "str" | "dex"
    attack_bonus: int
    damage_bonus: int
    attack_total_override: bool
    attack_override_value: int


def _has_property(properties: str, needle: str) -> bool:
    props = (properties or "").lower()
    return needle in props


def is_ranged_weapon(ctx: AttackContext) -> bool:
    """Un'arma è "a distanza" ai fini del modificatore se ha la proprietà
    Munizioni (archi/balestre/fionde) — la mera presenza di una gittata
    (range_normal > 0) non basta da sola, dato che anche armi da mischia
    con "Lancio" hanno una gittata quando lanciate pur restando armi da
    mischia per il modificatore (vedi docstring di modulo)."""
    return _has_property(ctx.properties, "munizioni")


def is_finesse_weapon(ctx: AttackContext) -> bool:
    return _has_property(ctx.properties, "accurata")


def resolve_weapon_ability(ctx: AttackContext, str_score: int, dex_score: int) -> str:
    """Determina quale caratteristica ("str" | "dex") usare per attacco e
    danno di quest'arma, rispettando un eventuale override esplicito del
    giocatore."""
    if ctx.finesse_ability in ("str", "dex"):
        return ctx.finesse_ability
    if is_finesse_weapon(ctx):
        return "str" if str_score >= dex_score else "dex"
    if is_ranged_weapon(ctx):
        return "dex"
    return "str"


def is_weapon_proficient(ctx: AttackContext, weapon_name: str, proficiency_names: set[str]) -> bool:
    """
    Vero se il personaggio è competente con quest'arma. `proficiency_names`
    è l'insieme (case-insensitive, già normalizzato in minuscolo) dei nomi
    presenti in character_proficiencies con proficiency_type="weapon" — può
    contenere sia token di categoria ("semplice"/"guerra") sia nomi di armi
    specifiche (es. "stocco").

    Un'arma è competente se una qualsiasi di queste è vera:
      - proficiency_override esplicito sull'arma stessa (es. arma magica
        che concede competenza automatica a chi la impugna);
      - il nome esatto dell'arma è tra le competenze possedute;
      - la categoria dell'arma ("semplice"/"guerra") è tra le competenze
        possedute.
    """
    if ctx.proficiency_override:
        return True
    name_l = (weapon_name or "").strip().lower()
    if name_l and name_l in proficiency_names:
        return True
    cat_l = (ctx.weapon_category or "").strip().lower()
    if cat_l and cat_l in proficiency_names:
        return True
    return False


def compute_attack_total(
    ctx: AttackContext,
    weapon_name: str,
    str_score: int,
    dex_score: int,
    prof_bonus: int,
    proficiency_names: set[str],
) -> tuple[int, bool, str, dict]:
    """
    Calcola il tiro per colpire totale.

    Ritorna (totale, is_proficient, ability_key, breakdown) dove `breakdown`
    è un dict {"ability_mod": int, "prof_bonus": int, "magic_bonus": int}
    coerente col totale calcolato automaticamente (anche quando il totale
    finale mostrato è un override manuale, il breakdown resta quello del
    calcolo automatico — utile per mostrarlo comunque nel tooltip).
    """
    ability_key = resolve_weapon_ability(ctx, str_score, dex_score)
    ability_score = str_score if ability_key == "str" else dex_score
    ability_mod = (ability_score - 10) // 2
    proficient = is_weapon_proficient(ctx, weapon_name, proficiency_names)
    prof_component = prof_bonus if proficient else 0
    breakdown = {
        "ability_mod": ability_mod,
        "prof_bonus": prof_component,
        "magic_bonus": ctx.attack_bonus,
    }
    if ctx.attack_total_override:
        return (ctx.attack_override_value, proficient, ability_key, breakdown)
    total = ability_mod + prof_component + ctx.attack_bonus
    return (total, proficient, ability_key, breakdown)


def compute_damage_formula(
    dice: str,
    damage_type: str,
    ctx: AttackContext,
    str_score: int,
    dex_score: int,
) -> str:
    """
    Costruisce la stringa del tiro per i danni completo: dado + modificatore
    caratteristica (stessa usata per l'attacco) + bonus danno magico
    dell'arma + tipo di danno. Solo i componenti non nulli sono mostrati.
    """
    ability_key = resolve_weapon_ability(ctx, str_score, dex_score)
    ability_score = str_score if ability_key == "str" else dex_score
    ability_mod = (ability_score - 10) // 2

    parts = (dice or "").strip()
    total_bonus = ability_mod + (ctx.damage_bonus or 0)
    if total_bonus > 0:
        parts += f"+{total_bonus}"
    elif total_bonus < 0:
        parts += f"{total_bonus}"
    if damage_type:
        parts += f" {damage_type}"
    return parts.strip()
