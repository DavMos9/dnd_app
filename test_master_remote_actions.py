"""
Batteria di verifica del passo 6 di dnd_app/docs/multiplayer_design.md —
"Interventi del master a distanza" (§7, §7.1, 2026-08-06).

Tre parti:

[1] `core/damage_rules.py` in isolamento puro: nessun DB, nessun mondo —
    solo l'algoritmo PHB (assorbimento HP temporanei, morte istantanea, TS
    contro morte a 0 PF, concentrazione), estratto da
    `combattimento_tab.py` per essere riusato dagli handler qui sotto.

[2] Gli handler dei comandi master/owner sulle istanze di personaggio
    (`core/world_backend.py`, registrati per i comandi di `core/
    world_permissions.py` §7): PE, danno, cura, condizioni, risorse di
    classe, abilità custom, incantesimo bonus, voce di diario, proposta e
    risposta a una richiesta di modifica. Un solo DB (`LocalBackend` parla
    col proprio processo, come nel deploy web e come fa l'host reale in
    LAN — vedi la Parte [1] di `test_lan_host_client.py` per il perché il
    trasporto di rete non serve a testare la logica di dominio).

[3] Permessi: ruolo minimo per comando (`can_perform`), il caso speciale
    di `change_request.respond` (ruolo minimo `player`, ma con verifica
    aggiuntiva di proprietà del personaggio — nessun ruolo, nemmeno
    l'owner del mondo, può rispondere al posto del giocatore), e il
    fail-closed su un personaggio che non appartiene al mondo del comando.

Usa SEMPRE un DB temporaneo isolato (tempfile.mkdtemp() + HOME separato):
il DB reale di Davide non viene mai toccato. Stesso pattern di
test_istanze_personaggio.py/test_mondo_senza_rete.py.

Eseguire con:
    PYTHONPATH=".venv/lib/python3.13/site-packages:." python3 test_master_remote_actions.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

_TMP_HOME = tempfile.mkdtemp(prefix="dnd_master_remote_")
os.environ["HOME"] = _TMP_HOME

from data.database import init_db  # noqa: E402
from data.models import Character  # noqa: E402
from data.repositories import character_repo, world_repo  # noqa: E402
from core import character_instances as ci  # noqa: E402
from core import damage_rules  # noqa: E402
from core import world_permissions as perm  # noqa: E402
from core.world_backend import LocalBackend  # noqa: E402

_PASS = 0
_FAIL: list[str] = []


def check(label: str, cond: bool) -> None:
    global _PASS
    if cond:
        _PASS += 1
    else:
        _FAIL.append(label)
        print(f"  FALLITO: {label}")


# ---------------------------------------------------------------------------
# Fixture: un mondo con owner + un giocatore con un'istanza
# ---------------------------------------------------------------------------

def _make_world_with_instance(owner_device="dev-owner", player_device="dev-player",
                               name="Thorin", level=5, hp_max=40):
    world = world_repo.create_world("Mondo di Prova", owner_device, "Il Master")
    assert world is not None

    local = Character(
        name=name, class_name="Guerriero", race="Nano", level=level,
        hit_dice_type=10, hit_dice_total=level, hit_dice_remaining=level,
        str_score=16, dex_score=12, con_score=16, int_score=10,
        wis_score=10, cha_score=8,
        hp_max=hp_max, hp_current=hp_max,
    )
    character_repo.create(local)

    result = ci.create_or_resume_instance(world.id, local.id, player_device, mode="as_is")
    assert result.success, result.error
    instance = character_repo.get_by_id(result.character_id)
    assert instance is not None

    world_repo.join_world_by_code(world.join_code, player_device, "Il Giocatore")
    return world, instance


def _reload(character_id: str) -> Character:
    c = character_repo.get_by_id(character_id)
    assert c is not None
    return c


# ---------------------------------------------------------------------------
# [1] core/damage_rules.py
# ---------------------------------------------------------------------------

def test_damage_rules() -> None:
    print("\n[1] core/damage_rules.py — regole PHB in isolamento")

    # Assorbimento HP temporanei
    c = Character(hp_max=20, hp_current=20, hp_temp=5)
    outcome = damage_rules.apply_damage(c, 8)
    check("HP temp assorbono prima il danno", outcome.amount_absorbed_by_temp == 5)
    check("il danno residuo arriva ai PF attuali", outcome.amount_to_hp == 3 and c.hp_current == 17)
    check("gli HP temp si azzerano", c.hp_temp == 0)

    # Morte istantanea (PHB p.197): danno residuo >= hp_max
    c = Character(hp_max=10, hp_current=5, hp_temp=0)
    outcome = damage_rules.apply_damage(c, 20)
    check("morte istantanea quando il danno residuo >= hp_max", outcome.instant_death)
    check("morte istantanea porta i fallimenti TS a 3", c.death_saves_failure == 3)

    # Danno a 0 PF = TS contro morte fallito
    c = Character(hp_max=10, hp_current=0, hp_temp=0)
    outcome = damage_rules.apply_damage(c, 3)
    check("danno a 0 PF aggiunge 1 fallimento TS", outcome.death_saves_failure_added == 1
          and c.death_saves_failure == 1)
    check("nessuna morte istantanea per un danno piccolo a 0 PF", not outcome.instant_death)

    # Colpo critico a 0 PF = 2 fallimenti
    c = Character(hp_max=10, hp_current=0, hp_temp=0)
    outcome = damage_rules.apply_damage(c, 3, is_critical=True)
    check("colpo critico a 0 PF aggiunge 2 fallimenti TS", outcome.death_saves_failure_added == 2
          and c.death_saves_failure == 2)

    # Concentrazione: check richiesto se il personaggio resta sopra 0 PF
    c = Character(hp_max=30, hp_current=20, concentrating_spell="Scudo della Fede")
    outcome = damage_rules.apply_damage(c, 10)
    check("concentrazione: serve un TS se il personaggio resta vivo",
          outcome.concentration_check_needed and not outcome.concentration_broken)
    check("CD del TS di concentrazione = max(10, danno/2)", outcome.concentration_dc == 10)

    # Concentrazione persa senza tiro se il danno porta a 0 PF (incapacitato)
    c = Character(hp_max=10, hp_current=8, concentrating_spell="Scudo della Fede")
    outcome = damage_rules.apply_damage(c, 20)
    check("concentrazione persa senza TS se il personaggio va a 0 PF",
          outcome.concentration_broken and not outcome.concentration_check_needed)
    check("concentrating_spell azzerato", c.concentrating_spell == "")

    # Cura: azzera i TS contro morte se il personaggio era a 0 PF
    c = Character(hp_max=20, hp_current=0, death_saves_failure=2, death_saves_success=1)
    heal_outcome = damage_rules.apply_heal(c, 5)
    check("la cura riporta gli HP sopra zero", c.hp_current == 5)
    check("la cura da 0 PF azzera i TS contro morte", heal_outcome.death_saves_reset
          and c.death_saves_failure == 0 and c.death_saves_success == 0)

    # Cura non eccede hp_max
    c = Character(hp_max=10, hp_current=8)
    damage_rules.apply_heal(c, 100)
    check("la cura non eccede hp_max", c.hp_current == 10)


# ---------------------------------------------------------------------------
# [2] Handler dei comandi sulle istanze
# ---------------------------------------------------------------------------

def test_xp_grant() -> None:
    print("\n[2a] xp.grant")
    world, instance = _make_world_with_instance()
    backend = LocalBackend()

    before_xp = instance.xp
    result = backend.send_command(world.id, "dev-owner", perm.CMD_XP_GRANT,
                                   {"amount": 500}, target_type="character", target_id=instance.id)
    check("xp.grant riuscito", result.success)
    check("xp.grant scrive un evento", result.event is not None)
    updated = _reload(instance.id)
    check("i PE sono stati aggiunti", updated.xp == before_xp + 500)
    check("il livello NON viene toccato", updated.level == instance.level)
    if result.event:
        check("il summary è leggibile e nomina il personaggio", instance.name in result.event.summary)

    result0 = backend.send_command(world.id, "dev-owner", perm.CMD_XP_GRANT,
                                    {"amount": 0}, target_type="character", target_id=instance.id)
    check("xp.grant con quantità 0 viene rifiutato", not result0.success)

    result_bad = backend.send_command(world.id, "dev-owner", perm.CMD_XP_GRANT,
                                       {"amount": 100}, target_type="character",
                                       target_id="id-inesistente")
    check("xp.grant su un personaggio inesistente viene rifiutato", not result_bad.success)


def test_hp_damage_and_heal() -> None:
    print("\n[2b] hp.damage / hp.heal")
    world, instance = _make_world_with_instance(hp_max=30)
    backend = LocalBackend()

    result = backend.send_command(world.id, "dev-owner", perm.CMD_HP_DAMAGE,
                                   {"amount": 12}, target_type="character", target_id=instance.id)
    check("hp.damage riuscito", result.success)
    updated = _reload(instance.id)
    check("i PF sono scesi correttamente", updated.hp_current == 18)

    result_heal = backend.send_command(world.id, "dev-owner", perm.CMD_HP_HEAL,
                                        {"amount": 5}, target_type="character", target_id=instance.id)
    check("hp.heal riuscito", result_heal.success)
    updated2 = _reload(instance.id)
    check("i PF sono risaliti correttamente", updated2.hp_current == 23)

    result_neg = backend.send_command(world.id, "dev-owner", perm.CMD_HP_DAMAGE,
                                       {"amount": -5}, target_type="character", target_id=instance.id)
    check("hp.damage con quantità negativa viene rifiutato", not result_neg.success)


def test_conditions() -> None:
    print("\n[2c] condition.apply / condition.remove")
    world, instance = _make_world_with_instance()
    backend = LocalBackend()

    bad = backend.send_command(world.id, "dev-owner", perm.CMD_CONDITION_APPLY,
                                {"condition_key": "non-esiste"}, target_type="character",
                                target_id=instance.id)
    check("condition.apply con chiave sconosciuta viene rifiutato", not bad.success)

    conditions = character_repo.get_conditions(instance.id)
    check("nessuna condizione ancora attiva", len(conditions) == 0)

    # Usa la prima condizione realmente presente nei dati di gioco, non un
    # nome inventato (regola del progetto: mai dati non verificati).
    from data.game_data.game_data_loader import GameDataLoader
    all_conditions = GameDataLoader().get_conditions()
    check("il file dati delle condizioni PHB non è vuoto", len(all_conditions) > 0)
    if not all_conditions:
        return
    key = all_conditions[0]["key"]

    ok = backend.send_command(world.id, "dev-owner", perm.CMD_CONDITION_APPLY,
                               {"condition_key": key, "note": "colpito da una ragnatela"},
                               target_type="character", target_id=instance.id)
    check("condition.apply riuscito", ok.success)
    conditions = character_repo.get_conditions(instance.id)
    check("la condizione risulta applicata", len(conditions) == 1 and conditions[0].condition_key == key)

    remove_bad = backend.send_command(world.id, "dev-owner", perm.CMD_CONDITION_REMOVE,
                                       {"condition_id": "id-a-caso"}, target_type="character",
                                       target_id=instance.id)
    check("condition.remove con id inesistente viene rifiutato", not remove_bad.success)

    remove_ok = backend.send_command(world.id, "dev-owner", perm.CMD_CONDITION_REMOVE,
                                      {"condition_id": conditions[0].id}, target_type="character",
                                      target_id=instance.id)
    check("condition.remove riuscito", remove_ok.success)
    check("la condizione risulta rimossa", len(character_repo.get_conditions(instance.id)) == 0)


def test_resources() -> None:
    print("\n[2d] resource.consume / resource.restore")
    world, instance = _make_world_with_instance()
    backend = LocalBackend()

    character_repo.init_class_resources(instance.id, instance.class_name, instance.level, instance)
    resources = character_repo.get_class_resources(instance.id)
    check("il Guerriero ha almeno una risorsa di classe inizializzata", len(resources) > 0)
    if not resources:
        return
    resource = resources[0]
    full_value = resource.current_value

    consume = backend.send_command(world.id, "dev-owner", perm.CMD_RESOURCE_CONSUME,
                                    {"resource_id": resource.id, "amount": 1},
                                    target_type="character", target_id=instance.id)
    check("resource.consume riuscito", consume.success)
    after = [r for r in character_repo.get_class_resources(instance.id) if r.id == resource.id][0]
    check("il valore corrente è sceso di 1", after.current_value == max(0, full_value - 1))

    # Non scende sotto zero
    for _ in range(20):
        backend.send_command(world.id, "dev-owner", perm.CMD_RESOURCE_CONSUME,
                              {"resource_id": resource.id, "amount": 5},
                              target_type="character", target_id=instance.id)
    floor = [r for r in character_repo.get_class_resources(instance.id) if r.id == resource.id][0]
    check("resource.consume non scende mai sotto zero", floor.current_value == 0)

    restore = backend.send_command(world.id, "dev-owner", perm.CMD_RESOURCE_RESTORE,
                                    {"resource_id": resource.id, "amount": 999},
                                    target_type="character", target_id=instance.id)
    check("resource.restore riuscito", restore.success)
    ceiling = [r for r in character_repo.get_class_resources(instance.id) if r.id == resource.id][0]
    check("resource.restore non supera mai il massimo", ceiling.current_value == full_value)


def test_custom_ability_and_bonus_spell_and_diary() -> None:
    print("\n[2e] custom_ability.grant / bonus_spell.grant / diary.add_entry")
    world, instance = _make_world_with_instance()
    backend = LocalBackend()

    bad_cat = backend.send_command(world.id, "dev-owner", perm.CMD_CUSTOM_ABILITY_GRANT,
                                    {"category": "invalida", "name": "X"},
                                    target_type="character", target_id=instance.id)
    check("custom_ability.grant con categoria non valida viene rifiutato", not bad_cat.success)

    ok = backend.send_command(world.id, "dev-owner", perm.CMD_CUSTOM_ABILITY_GRANT,
                               {"category": "esplorazione", "name": "Vista nel Buio Estesa",
                                "description": "Concessa da un artefatto."},
                               target_type="character", target_id=instance.id)
    check("custom_ability.grant riuscito", ok.success)
    abilities = character_repo.get_custom_abilities(instance.id)
    check("l'abilità custom risulta presente", any(a.name == "Vista nel Buio Estesa" for a in abilities))

    bad_level = backend.send_command(world.id, "dev-owner", perm.CMD_BONUS_SPELL_GRANT,
                                      {"name": "Incantesimo Impossibile", "level": 99},
                                      target_type="character", target_id=instance.id)
    check("bonus_spell.grant con livello fuori intervallo viene rifiutato", not bad_level.success)

    ok_spell = backend.send_command(world.id, "dev-owner", perm.CMD_BONUS_SPELL_GRANT,
                                     {"name": "Luce", "level": 0}, target_type="character",
                                     target_id=instance.id)
    check("bonus_spell.grant riuscito", ok_spell.success)
    known = character_repo.get_known_spells(instance.id)
    granted = [s for s in known if s.name == "Luce"]
    check("l'incantesimo bonus risulta noto", len(granted) == 1)
    if granted:
        check("l'incantesimo bonus è marcato is_bonus", bool(granted[0].is_bonus))
        check("l'incantesimo bonus è preparato", bool(granted[0].is_prepared))

    bad_diary = backend.send_command(world.id, "dev-owner", perm.CMD_DIARY_ADD_ENTRY,
                                      {"title": "", "content": ""}, target_type="character",
                                      target_id=instance.id)
    check("diary.add_entry senza titolo/testo viene rifiutato", not bad_diary.success)

    ok_diary = backend.send_command(world.id, "dev-owner", perm.CMD_DIARY_ADD_ENTRY,
                                     {"title": "Una visione", "content": "Vedi un corvo nero."},
                                     target_type="character", target_id=instance.id)
    check("diary.add_entry riuscito", ok_diary.success)
    entries = character_repo.get_diary_entries(instance.id)
    check("la voce di diario risulta scritta", any(e.title == "Una visione" for e in entries))


def test_change_request_propose_and_respond() -> None:
    print("\n[2f] change_request.propose / change_request.respond")
    world, instance = _make_world_with_instance()
    backend = LocalBackend()

    forbidden = backend.send_command(
        world.id, "dev-owner", perm.CMD_CHANGE_REQUEST_PROPOSE,
        {"changes": {"name": "Nome Rubato"}, "reason": "house rule"},
        target_type="character", target_id=instance.id,
    )
    check("change_request.propose su un campo vietato (name) viene rifiutato", not forbidden.success)

    no_reason = backend.send_command(
        world.id, "dev-owner", perm.CMD_CHANGE_REQUEST_PROPOSE,
        {"changes": {"str_score": 18}}, target_type="character", target_id=instance.id,
    )
    check("change_request.propose senza motivazione viene rifiutato", not no_reason.success)

    proposal = backend.send_command(
        world.id, "dev-owner", perm.CMD_CHANGE_REQUEST_PROPOSE,
        {"changes": {"str_score": 18}, "reason": "Bevi una pozione di Forza da Gigante."},
        target_type="character", target_id=instance.id,
    )
    check("change_request.propose riuscito", proposal.success)
    pending = world_repo.get_pending_change_requests(world.id)
    check("la richiesta risulta in sospeso", len(pending) == 1)
    if not pending:
        return
    request_id = pending[0].id

    respond_wrong_owner = backend.send_command(
        world.id, "dev-owner", perm.CMD_CHANGE_REQUEST_RESPOND,
        {"request_id": request_id, "accept": True},
        target_type="character", target_id=instance.id,
    )
    check(
        "change_request.respond inviato dal master (non proprietario del "
        "personaggio) viene rifiutato",
        not respond_wrong_owner.success,
    )
    check("il personaggio NON è cambiato dopo il tentativo del master",
          _reload(instance.id).str_score == 16)

    respond_ok = backend.send_command(
        world.id, "dev-player", perm.CMD_CHANGE_REQUEST_RESPOND,
        {"request_id": request_id, "accept": True},
        target_type="character", target_id=instance.id,
    )
    check("change_request.respond inviato dal proprietario del personaggio riesce",
          respond_ok.success)
    check("la caratteristica è stata applicata", _reload(instance.id).str_score == 18)
    check("la richiesta risulta accettata",
          world_repo.get_change_request(request_id).status == "accepted")

    # Una seconda risposta alla stessa richiesta (già risolta) va rifiutata.
    respond_again = backend.send_command(
        world.id, "dev-player", perm.CMD_CHANGE_REQUEST_RESPOND,
        {"request_id": request_id, "accept": False},
        target_type="character", target_id=instance.id,
    )
    check("rispondere due volte alla stessa richiesta viene rifiutato", not respond_again.success)


def test_cross_world_targeting_rejected() -> None:
    print("\n[2g] fail-closed: un comando non può toccare un personaggio di un ALTRO mondo")
    world_a, instance_a = _make_world_with_instance(owner_device="dev-owner-a",
                                                      player_device="dev-player-a", name="Personaggio A")
    world_b, _instance_b = _make_world_with_instance(owner_device="dev-owner-b",
                                                       player_device="dev-player-b", name="Personaggio B")
    backend = LocalBackend()

    result = backend.send_command(world_b.id, "dev-owner-b", perm.CMD_XP_GRANT,
                                   {"amount": 500}, target_type="character",
                                   target_id=instance_a.id)
    check("xp.grant sul personaggio di un altro mondo viene rifiutato", not result.success)
    check("il personaggio del mondo A non è stato toccato",
          _reload(instance_a.id).xp == 0)


# ---------------------------------------------------------------------------
# [3] Permessi
# ---------------------------------------------------------------------------

def test_permissions() -> None:
    print("\n[3] core/world_permissions.py — ruolo minimo per comando")

    check("owner può xp.grant", perm.can_perform(perm.ROLE_OWNER, perm.CMD_XP_GRANT))
    check("master può xp.grant", perm.can_perform(perm.ROLE_MASTER, perm.CMD_XP_GRANT))
    check("player NON può xp.grant", not perm.can_perform(perm.ROLE_PLAYER, perm.CMD_XP_GRANT))

    check("player può change_request.respond (il ruolo da solo non è sufficiente:"
          " l'ownership è verificata dall'handler)",
          perm.can_perform(perm.ROLE_PLAYER, perm.CMD_CHANGE_REQUEST_RESPOND))
    check("requires_character_ownership è True per change_request.respond",
          perm.requires_character_ownership(perm.CMD_CHANGE_REQUEST_RESPOND))
    check("requires_character_ownership è False per xp.grant",
          not perm.requires_character_ownership(perm.CMD_XP_GRANT))

    check("is_character_owner: stesso device_id",
          perm.is_character_owner("dev-1", "dev-1"))
    check("is_character_owner: device_id diverso", not perm.is_character_owner("dev-1", "dev-2"))
    check("is_character_owner: device_id vuoto sempre False", not perm.is_character_owner("", ""))

    world, instance = _make_world_with_instance()
    backend = LocalBackend()
    denied = backend.send_command(world.id, "dev-player", perm.CMD_HP_DAMAGE,
                                   {"amount": 5}, target_type="character", target_id=instance.id)
    check("un giocatore non può inviare hp.damage (ruolo insufficiente)", not denied.success)

    outsider = backend.send_command(world.id, "dev-sconosciuto", perm.CMD_XP_GRANT,
                                     {"amount": 5}, target_type="character", target_id=instance.id)
    check("un dispositivo che non è membro del mondo viene rifiutato", not outsider.success)


# ---------------------------------------------------------------------------

def main() -> int:
    init_db()
    print("=" * 62)
    print("PASSO 6 — Interventi del master a distanza")
    print(f"HOME di test: {_TMP_HOME}")
    print("=" * 62)

    test_damage_rules()
    test_xp_grant()
    test_hp_damage_and_heal()
    test_conditions()
    test_resources()
    test_custom_ability_and_bonus_spell_and_diary()
    test_change_request_propose_and_respond()
    test_cross_world_targeting_rejected()
    test_permissions()

    print("\n" + "=" * 62)
    print(f"Controlli passati: {_PASS} — falliti: {len(_FAIL)}")
    if _FAIL:
        for f in _FAIL:
            print(f"  - {f}")
        return 1
    print("Tutti i controlli passati.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
