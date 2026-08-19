"""
Unica fonte di verità per "quanto tira questo personaggio su X".

Modulo puro: nessuna dipendenza da Flet né dal DB (riceve il `Character` e le
sue competenze già caricati), stesso principio di `weapon_calculator.py` e
`level_manager.py`.

**Perché esiste** (Fase 4, feature 1 — vedi `docs/feature_design_2026_07_26.md`):
il calcolo di un modificatore era duplicato inline in almeno 6 punti della UI
(`esplorazione_tab`, `combattimento_tab` ×2, `sheet_view`, `profilo_tab`,
`spells_view` ×2), sempre nella forma `pb = char_prof_bonus(c)` seguita dalla
matematica per-abilità. Non esisteva un posto solo dove chiedere "quanto tira
questo personaggio su Atletica", e questo rendeva impossibile aggiungere il
tiro di dado senza replicare i conti una settima volta.

Ogni funzione restituisce un `RollSpec`: cosa si tira, con quale modificatore e
**perché** (il breakdown testuale mostrato all'utente). Il tiro vero e proprio è
di `core/dice.py`, che questo modulo non chiama: qui si descrive il tiro, là lo
si esegue. La separazione serve ai test — un `RollSpec` è deterministico e
confrontabile, un tiro no.

Regole PHB applicate:
  * modificatore di caratteristica = `(punteggio − 10) // 2` (Cap. 1);
  * bonus di competenza raddoppiato con la Maestria (`is_expert`), Cap. 4;
  * tiro salvezza contro morte: d20 puro, nessun modificatore, CD 10 (Cap. 9);
  * iniziativa = mod. Destrezza + eventuali bonus da talenti (`initiative_bonus`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from config.settings import (
    ABILITY_ABBR,
    ABILITY_KEYS,
    ABILITY_SCORES,
    SKILLS,
    char_prof_bonus,
    get_modifier,
)
from core.weapon_calculator import (
    AttackContext,
    compute_attack_total,
    resolve_weapon_ability,
)

#: Tipi di tiro. Servono alla UI per decidere icona e comportamento
#: (es. solo `death_save` scrive automaticamente sulla scheda).
RollKind = str

DEATH_SAVE_DC = 10


@dataclass(frozen=True)
class RollSpec:
    """
    Descrizione di un tiro: cosa, quanto e perché.

    `formula` è la parte in dadi (`"1d20"`, `"1d8"`, `"1d8+1d6"`), `modifier`
    la parte fissa. Tenerle separate permette alla UI di mostrare "1d20 +5"
    invece di una stringa già fusa, e a `core/dice.py` di applicare
    vantaggio/svantaggio al d20 giusto.
    """
    kind: RollKind
    label: str
    formula: str = "1d20"
    modifier: int = 0
    ability: str = ""
    proficient: bool = False
    expert: bool = False
    note: str = ""
    dc: int = 0
    damage_type: str = ""
    #: Componenti del modificatore, per il tooltip: {"Destrezza": 3, "Competenza": 2}
    breakdown: dict[str, int] = field(default_factory=dict)

    @property
    def modifier_str(self) -> str:
        return f"+{self.modifier}" if self.modifier >= 0 else f"−{abs(self.modifier)}"

    @property
    def is_d20(self) -> bool:
        """Vantaggio/svantaggio hanno senso solo su questi (PHB Cap. 7)."""
        return "d20" in self.formula


# ---------------------------------------------------------------------------
# Competenze
# ---------------------------------------------------------------------------


def skill_proficiencies(profs: Iterable[Any]) -> dict[str, bool]:
    """`{nome abilità: is_expert}` per le sole abilità in cui è competente."""
    return {
        p.name: bool(getattr(p, "is_expert", False))
        for p in profs
        if getattr(p, "proficiency_type", "") == "skill"
    }


def save_proficiencies(profs: Iterable[Any]) -> set[str]:
    """
    Nomi delle caratteristiche in cui il personaggio è competente nei TS.

    Accetta sia `"save"` sia `"saving_throw"`: entrambi i valori esistono nel
    DB per ragioni storiche (il wizard scrive `"save"`), e filtrarne uno solo
    farebbe sparire silenziosamente metà delle competenze.
    """
    return {
        p.name for p in profs
        if getattr(p, "proficiency_type", "") in ("save", "saving_throw")
    }


def weapon_proficiency_names(profs: Iterable[Any]) -> set[str]:
    return {
        (p.name or "").strip().lower() for p in profs
        if getattr(p, "proficiency_type", "") == "weapon"
    }


def ability_label(ability_key: str) -> str:
    """`"dex"` → `"Destrezza"`."""
    if ability_key in ABILITY_KEYS:
        return ABILITY_SCORES[ABILITY_KEYS.index(ability_key)]
    return ability_key


def ability_abbr(ability_key: str) -> str:
    """`"dex"` → `"DES"`."""
    if ability_key in ABILITY_KEYS:
        return ABILITY_ABBR[ABILITY_KEYS.index(ability_key)]
    return ability_key.upper()


def ability_score(character: Any, ability_key: str) -> int:
    return int(getattr(character, f"{ability_key}_score", 10) or 10)


def ability_modifier(character: Any, ability_key: str) -> int:
    return get_modifier(ability_score(character, ability_key))


# ---------------------------------------------------------------------------
# Prove, abilità, tiri salvezza
# ---------------------------------------------------------------------------


def ability_check_roll(character: Any, ability_key: str) -> RollSpec:
    """Prova di caratteristica pura (nessuna competenza applicabile)."""
    mod = ability_modifier(character, ability_key)
    return RollSpec(
        kind="ability",
        label=f"Prova di {ability_label(ability_key)}",
        modifier=mod,
        ability=ability_key,
        note=f"{ability_abbr(ability_key)} {_signed(mod)}",
        breakdown={ability_label(ability_key): mod},
    )


def skill_roll(character: Any, profs: Iterable[Any], skill_name: str) -> RollSpec:
    """Prova di abilità, con competenza e Maestria già applicate."""
    ability_key = SKILLS.get(skill_name, "")
    if not ability_key:
        raise ValueError(f"Abilità sconosciuta: {skill_name!r}")

    skills = skill_proficiencies(profs)
    proficient = skill_name in skills
    expert = skills.get(skill_name, False)

    pb = char_prof_bonus(character)
    ability_mod = ability_modifier(character, ability_key)
    prof_component = pb * (2 if expert else 1) if proficient else 0

    breakdown = {ability_label(ability_key): ability_mod}
    if prof_component:
        breakdown["Maestria" if expert else "Competenza"] = prof_component

    return RollSpec(
        kind="skill",
        label=skill_name,
        modifier=ability_mod + prof_component,
        ability=ability_key,
        proficient=proficient,
        expert=expert,
        note=_note_from(breakdown),
        breakdown=breakdown,
    )


def save_roll(character: Any, profs: Iterable[Any], ability_key: str) -> RollSpec:
    """Tiro salvezza di caratteristica."""
    name = ability_label(ability_key)
    proficient = name in save_proficiencies(profs)
    pb = char_prof_bonus(character)
    ability_mod = ability_modifier(character, ability_key)
    prof_component = pb if proficient else 0

    breakdown = {name: ability_mod}
    if prof_component:
        breakdown["Competenza"] = prof_component

    return RollSpec(
        kind="save",
        label=f"TS {name}",
        modifier=ability_mod + prof_component,
        ability=ability_key,
        proficient=proficient,
        note=_note_from(breakdown),
        breakdown=breakdown,
    )


def initiative_roll(character: Any) -> RollSpec:
    """
    Iniziativa: mod. Destrezza + `initiative_bonus` (talenti come Allerta +5).

    Stessa formula già usata da `combattimento_tab`, qui in un posto solo.
    """
    dex_mod = ability_modifier(character, "dex")
    extra = int(getattr(character, "initiative_bonus", 0) or 0)
    breakdown = {"Destrezza": dex_mod}
    if extra:
        breakdown["Bonus"] = extra
    return RollSpec(
        kind="initiative",
        label="Iniziativa",
        modifier=dex_mod + extra,
        ability="dex",
        note=_note_from(breakdown),
        breakdown=breakdown,
    )


def death_save_roll() -> RollSpec:
    """
    Tiro salvezza contro morte: d20 puro, nessun modificatore, CD 10.

    Non dipende dal personaggio (PHB Cap. 9: "il tiro non è legato ad alcuna
    caratteristica"), per questo non prende argomenti.
    """
    return RollSpec(
        kind="death_save",
        label="TS contro morte",
        dc=DEATH_SAVE_DC,
        note="d20 puro, CD 10 — nessun modificatore",
    )


def hit_die_roll(character: Any) -> RollSpec:
    """
    Un dado vita speso in un riposo breve: dado della classe + mod. Costituzione.

    Il minimo del recupero (0 sul totale, non per dado — PHB p.186) resta a
    carico di chi applica il risultato: qui si descrive solo il tiro.
    """
    die_value = getattr(character, "hit_dice_type", None) or 8
    die = f"d{int(die_value)}"
    con_mod = ability_modifier(character, "con")
    return RollSpec(
        kind="hit_die",
        label=f"Dado vita ({die})",
        formula=f"1{die}",
        modifier=con_mod,
        ability="con",
        note=_note_from({"Costituzione": con_mod}),
        breakdown={"Costituzione": con_mod},
    )


# ---------------------------------------------------------------------------
# Armi
# ---------------------------------------------------------------------------


def weapon_context(weapon: Any) -> AttackContext:
    """`Weapon` → `AttackContext`, l'adattatore già usato inline da combattimento_tab."""
    return AttackContext(
        properties=weapon.properties or "",
        range_normal=weapon.range_normal or 0,
        weapon_category=weapon.weapon_category or "",
        proficiency_override=weapon.proficiency_override,
        finesse_ability=weapon.finesse_ability or "",
        attack_bonus=weapon.attack_bonus or 0,
        damage_bonus=weapon.damage_bonus or 0,
        attack_total_override=weapon.attack_total_override,
        attack_override_value=weapon.attack_override_value or 0,
    )


def attack_roll(character: Any, weapon: Any, profs: Iterable[Any]) -> RollSpec:
    """Tiro per colpire con un'arma — riusa interamente `weapon_calculator`."""
    ctx = weapon_context(weapon)
    total, proficient, ability_key, bd = compute_attack_total(
        ctx, weapon.name, character.str_score, character.dex_score,
        char_prof_bonus(character), weapon_proficiency_names(profs),
    )

    if ctx.attack_total_override:
        note = f"Totale manuale: {_signed(total)} (override del giocatore)"
        breakdown = {"Override": total}
    else:
        breakdown = {ability_label(ability_key): bd["ability_mod"]}
        if bd["prof_bonus"]:
            breakdown["Competenza"] = bd["prof_bonus"]
        if bd["magic_bonus"]:
            breakdown["Magico"] = bd["magic_bonus"]
        note = _note_from(breakdown)
        if not proficient:
            note += " — non competente"

    return RollSpec(
        kind="attack",
        label=f"{weapon.name} — attacco",
        modifier=total,
        ability=ability_key,
        proficient=proficient,
        note=note,
        breakdown=breakdown,
    )


def damage_roll(character: Any, weapon: Any, *, two_handed: bool | None = None) -> RollSpec:
    """
    Tiro dei danni: dado dell'arma + mod. caratteristica + bonus magico, più
    gli eventuali dadi di danno magico extra (`magic_damages`) come termini
    aggiuntivi della stessa formula.

    `two_handed` forza l'impugnatura di un'arma Versatile; se `None` si usa
    quella attualmente salvata sull'arma (`grip_two_handed`).
    """
    import json

    ctx = weapon_context(weapon)
    ability_key = resolve_weapon_ability(ctx, character.str_score, character.dex_score)
    ability_mod = ability_modifier(character, ability_key)

    grip = weapon.grip_two_handed if two_handed is None else two_handed
    dice = (weapon.versatile_damage_dice or "").strip() if grip else ""
    if not dice:
        dice = (weapon.damage_dice or "").strip()
    if not dice:
        dice = "1d4"   # arma senza dado dichiarato (homebrew): colpo senz'armi

    formula = dice
    extra_labels: list[str] = []
    try:
        for extra in json.loads(weapon.magic_damages or "[]"):
            edice = str(extra.get("dice", "") or "").strip()
            if not edice:
                continue
            formula += f"+{edice}"
            etype = str(extra.get("type", "") or "").strip()
            extra_labels.append(f"{edice} {etype}".strip())
    except (ValueError, TypeError):
        pass   # JSON malformato sull'arma: si tira comunque il danno base

    breakdown = {ability_label(ability_key): ability_mod}
    if weapon.damage_bonus:
        breakdown["Magico"] = weapon.damage_bonus

    note = _note_from(breakdown)
    if extra_labels:
        note += " — extra: " + ", ".join(extra_labels)

    return RollSpec(
        kind="damage",
        label=f"{weapon.name} — danni",
        formula=formula,
        modifier=ability_mod + (weapon.damage_bonus or 0),
        ability=ability_key,
        note=note,
        damage_type=weapon.damage_type or "",
        breakdown=breakdown,
    )


# ---------------------------------------------------------------------------
# Incantesimi
# ---------------------------------------------------------------------------


def spell_attack_roll(character: Any) -> RollSpec | None:
    """
    Tiro per colpire con incantesimo = mod. caratteristica da incantatore +
    bonus di competenza (PHB Cap. 10).

    Ritorna `None` per un personaggio senza `spellcasting_ability` — nessun
    tiro da offrire, e la UI non deve mostrare il pulsante.
    """
    key = (getattr(character, "spellcasting_ability", "") or "").strip().lower()
    if key not in ABILITY_KEYS:
        return None
    mod = ability_modifier(character, key)
    pb = char_prof_bonus(character)
    breakdown = {ability_label(key): mod, "Competenza": pb}
    return RollSpec(
        kind="spell_attack",
        label="Attacco con incantesimo",
        modifier=mod + pb,
        ability=key,
        proficient=True,
        note=_note_from(breakdown),
        breakdown=breakdown,
    )


def spell_save_dc(character: Any) -> int | None:
    """CD dei tiri salvezza contro gli incantesimi: 8 + competenza + mod."""
    key = (getattr(character, "spellcasting_ability", "") or "").strip().lower()
    if key not in ABILITY_KEYS:
        return None
    return 8 + char_prof_bonus(character) + ability_modifier(character, key)


def concentration_save_dc(damage: int) -> int:
    """
    CD del TS di Costituzione per mantenere la concentrazione dopo un danno:
    **10 oppure metà del danno subito, il maggiore dei due** (PHB p.203-204).
    """
    return max(10, int(damage) // 2)


# ---------------------------------------------------------------------------
# Helper interni
# ---------------------------------------------------------------------------


def _signed(v: int) -> str:
    return f"+{v}" if v >= 0 else f"−{abs(v)}"


def _note_from(breakdown: dict[str, int]) -> str:
    """`{"Destrezza": 3, "Competenza": 2}` → `"Destrezza +3, Competenza +2"`."""
    return ", ".join(f"{k} {_signed(v)}" for k, v in breakdown.items())
