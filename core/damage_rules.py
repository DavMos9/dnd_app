"""
Regole PHB per applicare danno e cura a un personaggio — PHB p.197
("Punti Ferita", "Morte Istantanea", "Danni a 0 Punti Ferita") e p.203-204
("Concentrazione").

Modulo puro (nessuna dipendenza Flet, come tutto `core/*.py`) perché va
condiviso anche da `core/world_backend.py`, che non può importare Flet: la
UI locale e i comandi multiplayer (applicare danni/cure a un'istanza di
personaggio remota, `dnd_app/docs/multiplayer_design.md` §7) riusano la
stessa implementazione invece di duplicarla in due posti — duplicazione
che sarebbe la vera fonte di bug, con le due copie destinate a divergere.

Principio: queste funzioni mutano l'oggetto `Character` passato (in
memoria, stesso stile del chiamante originale in `combattimento_tab.py`)
ma NON scrivono mai sul DB e NON conoscono Flet — la persistenza
(`character_repo.update_hp()`, `update_death_saves()`, ecc.) resta
responsabilità del chiamante, che sa anche se serve mostrare un dialog di
conferma concentrazione (solo la UI locale) o scrivere un evento nel
giornale del mondo (solo il comando remoto).
"""

from __future__ import annotations

from dataclasses import dataclass

from data.models import Character


@dataclass
class DamageOutcome:
    """Esito dell'applicazione di un danno — quanto è stato assorbito dagli
    HP temporanei, se scatta la morte istantanea o un tiro salvezza contro
    morte, se la concentrazione va persa o va tirato un TS."""
    amount_requested: int
    amount_absorbed_by_temp: int
    amount_to_hp: int
    instant_death: bool = False
    death_saves_failure_added: int = 0
    death_note: str = ""
    concentration_broken: bool = False       # persa senza tiro (incapacitato a 0 PF)
    concentration_check_needed: bool = False  # va tirato un TS Costituzione
    concentration_spell: str = ""
    concentration_dc: int = 0                # max(10, metà del danno), solo se check_needed


@dataclass
class HealOutcome:
    amount_requested: int
    amount_applied: int
    death_saves_reset: bool = False


def apply_damage(character: Character, amount: int, is_critical: bool = False) -> DamageOutcome:
    """
    Applica danno a `character` (mutato in place) secondo PHB p.197 e
    p.203-204. `amount` deve già essere non negativo (il chiamante valida
    l'input dell'utente/del comando prima di arrivare qui).
    """
    amount = max(0, int(amount))
    requested = amount

    absorbed = 0
    if character.hp_temp and character.hp_temp > 0:
        absorbed = min(character.hp_temp, amount)
        character.hp_temp -= absorbed
        amount -= absorbed

    was_at_zero = character.hp_current <= 0
    # PHB p.197 "Morte Istantanea": danno residuo (quello che eccede gli HP
    # attuali) pari o superiore al massimo dei PF = morte immediata.
    residual = amount if was_at_zero else max(0, amount - max(0, character.hp_current))
    instant_death = amount > 0 and character.hp_max > 0 and residual >= character.hp_max

    character.hp_current = max(0, character.hp_current - amount)

    death_note = ""
    failure_added = 0
    if instant_death:
        character.death_saves_success = 0
        character.death_saves_failure = 3
        death_note = (
            f"Morte istantanea: i {residual} danni residui sono pari o "
            f"superiori al massimo dei punti ferita ({character.hp_max}).\n"
            "PHB p.197 — «Morte Istantanea»."
        )
    elif was_at_zero and amount > 0:
        # PHB p.197: danno subito a 0 PF = 1 TS contro morte fallito (2 se
        # da colpo critico).
        failure_added = 2 if is_critical else 1
        character.death_saves_failure = min(3, (character.death_saves_failure or 0) + failure_added)
        if character.death_saves_failure >= 3:
            death_note = (
                "Terzo tiro salvezza contro morte fallito: il personaggio "
                "muore.\nPHB p.197."
            )
        else:
            death_note = (
                f"Danno subito a 0 PF: {failure_added} tiro salvezza contro morte "
                f"fallito{'i' if failure_added > 1 else ''} "
                f"({character.death_saves_failure}/3).\nPHB p.197."
            )

    # Concentrazione (PHB p.203-204): a 0 PF il personaggio è incapacitato e
    # la perde comunque; altrimenti va tirato un TS di Costituzione con
    # CD = max(10, metà dei danni subiti).
    conc_spell = (character.concentrating_spell or "").strip()
    concentration_broken = False
    concentration_check_needed = False
    concentration_dc = 0
    if conc_spell and amount > 0:
        if character.hp_current <= 0:
            concentration_broken = True
            character.concentrating_spell = ""
            character.concentrating_since = ""
        else:
            concentration_check_needed = True
            concentration_dc = max(10, amount // 2)

    return DamageOutcome(
        amount_requested=requested,
        amount_absorbed_by_temp=absorbed,
        amount_to_hp=amount,
        instant_death=instant_death,
        death_saves_failure_added=failure_added,
        death_note=death_note,
        concentration_broken=concentration_broken,
        concentration_check_needed=concentration_check_needed,
        concentration_spell=conc_spell,
        concentration_dc=concentration_dc,
    )


def apply_heal(character: Character, amount: int) -> HealOutcome:
    """
    Applica cura a `character` (mutato in place). PHB p.197: i tiri
    salvezza contro morte tornano a zero quando il personaggio recupera un
    qualsiasi ammontare di punti ferita da 0 PF.
    """
    amount = max(0, int(amount))
    was_at_zero = character.hp_current <= 0
    character.hp_current = min(character.hp_max, character.hp_current + amount)

    reset = False
    if was_at_zero and amount > 0 and character.hp_current > 0:
        character.death_saves_success = 0
        character.death_saves_failure = 0
        reset = True

    return HealOutcome(amount_requested=amount, amount_applied=amount, death_saves_reset=reset)
