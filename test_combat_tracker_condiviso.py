"""
Batteria di verifica del passo 7C di dnd_app/docs/multiplayer_design.md —
"Tracker di combattimento condiviso" (§6.5).

Sei parti:

[1] L'handler `CMD_ENCOUNTER_MANAGE`/`CMD_COMBAT_TOGGLE_VISIBILITY`
    (`core/world_backend.py`): rifiuta un incontro che non appartiene al
    mondo del comando.

[2] `CMD_COMBAT_TOGGLE_VISIBILITY` cambia il flag e produce l'evento.

[3] `CMD_ENCOUNTER_MANAGE`/"next_turn" porta allo stesso stato
    (round/turno) di una chiamata diretta a `master_repo.advance_turn` —
    il wrapper non cambia il comportamento.

[4] Applicazione degli eventi sulla replica
    (`core/world_sync.py::apply_event_to_replica`): `get_visible_encounter_
    for_world` ritorna l'incontro corretto con round/turno/membri.

[5] `wound_status_label` — tabella di casi.

[6] Il bug di correttezza trovato in fase di revisione del piano: uno
    snapshot preso mentre un incontro è visibile porta, dopo
    `_finalize_join`, allo stesso risultato di [4] su un device che non ha
    mai ricevuto l'evento originale.

Eseguire con:
    PYTHONPATH=".venv/lib/python3.13/site-packages:." python3 test_combat_tracker_condiviso.py
"""

from __future__ import annotations

import os
import sys
import tempfile

_TMP_HOME = tempfile.mkdtemp(prefix="dnd_combat_tracker_")
os.environ["HOME"] = _TMP_HOME

from data.database import init_db  # noqa: E402
from data.models import Character, WorldEvent  # noqa: E402
from data.repositories import character_repo, master_repo, world_repo  # noqa: E402
from core import world_backend  # noqa: E402
from core import world_permissions as perm  # noqa: E402
from core import world_sync  # noqa: E402
from core.world_backend import LocalBackend  # noqa: E402
from ui.views.world.combat_status import wound_status_label  # noqa: E402

_PASS = 0
_FAIL: list[str] = []


def check(label: str, cond: bool) -> None:
    global _PASS
    if cond:
        _PASS += 1
    else:
        _FAIL.append(label)
        print(f"  FALLITO: {label}")


def _send(backend: LocalBackend, *args, **kwargs):
    world_backend.reset_host_cooldowns_for_tests()
    return backend.send_command(*args, **kwargs)


def _make_world_with_encounter(owner="dev-owner", player="dev-player"):
    world = world_repo.create_world("Mondo del Combattimento", owner, "Il Master")
    assert world is not None
    world_repo.join_world_by_code(world.join_code, player, "Il Giocatore")

    local = Character(
        name="Elyndra", class_name="Ladro", race="Elfo", level=3,
        hit_dice_type=8, hit_dice_total=3, hit_dice_remaining=3,
        str_score=10, dex_score=16, con_score=12, int_score=14,
        wis_score=10, cha_score=12, hp_max=20, hp_current=20,
    )
    character_repo.create(local)
    from core import character_instances as ci
    result = ci.create_or_resume_instance(world.id, local.id, player, mode="as_is")
    assert result.success, result.error
    pc = character_repo.get_by_id(result.character_id)
    assert pc is not None

    encounter = master_repo.create_encounter("Imboscata nel Bosco")
    assert encounter is not None
    master_repo.set_encounter_world(encounter.id, world.id)

    master_repo.add_member(encounter.id, "character", character_id=pc.id,
                            display_name=pc.name, initiative=15, order_index=0)
    master_repo.add_member(encounter.id, "adhoc", display_name="Lupo",
                            ac=13, hp_current=11, hp_max=11, xp=50,
                            initiative=10, order_index=1)
    return world, encounter.id, pc.id


# ---------------------------------------------------------------------------
# [1] Fail-closed su un incontro fuori mondo
# ---------------------------------------------------------------------------

def test_handler_fail_closed() -> None:
    print("\n[1] Handler: fail-closed su un incontro che non appartiene al mondo")

    world_a, encounter_id, _pc_id = _make_world_with_encounter(
        owner="dev-owner-1", player="dev-player-1",
    )
    world_b = world_repo.create_world("Un Altro Mondo", "dev-owner-1b", "Master B")
    assert world_b is not None

    backend = LocalBackend()
    result = _send(backend, world_b.id, "dev-owner-1b", perm.CMD_ENCOUNTER_MANAGE,
                    {"encounter_id": encounter_id, "action": "next_turn"})
    check("un incontro del mondo A non è raggiungibile da un comando sul mondo B",
          not result.success)

    result = _send(backend, world_a.id, "dev-owner-1", perm.CMD_ENCOUNTER_MANAGE,
                    {"encounter_id": "id-inesistente", "action": "next_turn"})
    check("un encounter_id inesistente viene rifiutato", not result.success)

    result = _send(backend, world_a.id, "dev-player-1", perm.CMD_ENCOUNTER_MANAGE,
                    {"encounter_id": encounter_id, "action": "next_turn"})
    check("un giocatore non può gestire il combattimento (solo master/owner)",
          not result.success)


# ---------------------------------------------------------------------------
# [2] Toggle visibilità
# ---------------------------------------------------------------------------

def test_toggle_visibility() -> None:
    print("\n[2] CMD_COMBAT_TOGGLE_VISIBILITY — flag ed evento")

    world, encounter_id, _pc_id = _make_world_with_encounter(
        owner="dev-owner-2", player="dev-player-2",
    )
    backend = LocalBackend()

    enc = master_repo.get_encounter_by_id(encounter_id)
    check("spento di default", enc is not None and not enc.visible_to_players)

    result = _send(backend, world.id, "dev-owner-2", perm.CMD_COMBAT_TOGGLE_VISIBILITY,
                    {"encounter_id": encounter_id, "visible": True})
    check("accensione riuscita", result.success)
    check("produce un evento", result.event is not None)
    check("kind giusto", result.event.kind == perm.CMD_COMBAT_TOGGLE_VISIBILITY)
    enc = master_repo.get_encounter_by_id(encounter_id)
    check("flag acceso sull'host", enc is not None and enc.visible_to_players)

    result = _send(backend, world.id, "dev-owner-2", perm.CMD_COMBAT_TOGGLE_VISIBILITY,
                    {"encounter_id": encounter_id, "visible": False})
    check("spegnimento riuscito", result.success)
    enc = master_repo.get_encounter_by_id(encounter_id)
    check("flag spento sull'host", enc is not None and not enc.visible_to_players)


# ---------------------------------------------------------------------------
# [3] next_turn — comportamento identico alla chiamata diretta
# ---------------------------------------------------------------------------

def test_next_turn_comportamento_invariato() -> None:
    print("\n[3] CMD_ENCOUNTER_MANAGE/next_turn — stesso esito di advance_turn diretto")

    world, encounter_id, _pc_id = _make_world_with_encounter(
        owner="dev-owner-3", player="dev-player-3",
    )
    backend = LocalBackend()

    # Applica un turno via comando.
    result = _send(backend, world.id, "dev-owner-3", perm.CMD_ENCOUNTER_MANAGE,
                    {"encounter_id": encounter_id, "action": "next_turn"})
    check("next_turn via comando riuscito", result.success)
    via_command = master_repo.get_encounter_by_id(encounter_id)

    # Crea un secondo incontro identico (due membri adhoc: qui conta solo
    # l'ordine per iniziativa, non la risoluzione di un personaggio vero)
    # e avanza con la chiamata diretta.
    encounter2 = master_repo.create_encounter("Imboscata Gemella")
    assert encounter2 is not None
    master_repo.add_member(encounter2.id, "adhoc", display_name="Copia",
                            hp_current=20, hp_max=20, initiative=15, order_index=0)
    master_repo.add_member(encounter2.id, "adhoc", display_name="Lupo Copia",
                            ac=13, hp_current=11, hp_max=11, initiative=10, order_index=1)
    master_repo.advance_turn(encounter2.id)
    via_direct = master_repo.get_encounter_by_id(encounter2.id)

    check("stesso round dopo un turno", via_command.round_number == via_direct.round_number)
    check("stesso indice di turno dopo un turno",
          via_command.current_turn_index == via_direct.current_turn_index)

    result = _send(backend, world.id, "dev-owner-3", perm.CMD_ENCOUNTER_MANAGE,
                    {"encounter_id": encounter_id, "action": "end_combat"})
    check("end_combat via comando riuscito", result.success)
    enc = master_repo.get_encounter_by_id(encounter_id)
    check("l'incontro risulta archiviato", enc is not None and enc.is_archived)


# ---------------------------------------------------------------------------
# [4] Applicazione sulla replica
# ---------------------------------------------------------------------------

def test_replica_riceve_stato_incontro() -> None:
    print("\n[4] apply_event_to_replica — la replica riceve round/turno/membri")

    world, encounter_id, pc_id = _make_world_with_encounter(
        owner="dev-owner-4", player="dev-player-4",
    )
    backend = LocalBackend()

    result = _send(backend, world.id, "dev-owner-4", perm.CMD_COMBAT_TOGGLE_VISIBILITY,
                    {"encounter_id": encounter_id, "visible": True})
    check("accensione riuscita", result.success)
    world_sync.apply_event_to_replica(world.id, result.event)

    visible = master_repo.get_visible_encounter_for_world(world.id)
    check("get_visible_encounter_for_world lo trova dopo l'evento di accensione",
          visible is not None and visible.id == encounter_id)
    members = master_repo.get_replica_encounter_members(encounter_id)
    check("i membri sono stati materializzati sulla replica (2 membri)", len(members) == 2)
    check("un membro è il PG con i PF esatti",
          any(m.get("source") == "character" and m.get("hp_current") == 20 for m in members))

    result2 = _send(backend, world.id, "dev-owner-4", perm.CMD_ENCOUNTER_MANAGE,
                     {"encounter_id": encounter_id, "action": "next_turn"})
    check("next_turn riuscito", result2.success)
    world_sync.apply_event_to_replica(world.id, result2.event)
    visible2 = master_repo.get_visible_encounter_for_world(world.id)
    check("il turno avanzato si riflette sulla replica",
          visible2 is not None and visible2.current_turn_index == 1)


def test_wound_status_label() -> None:
    print("\n[5] wound_status_label — tabella di casi")

    check("100% -> Illeso", wound_status_label(20, 20) == "Illeso")
    check("99% -> Ferito", wound_status_label(19, 20) == "Ferito")
    check("50% -> Gravemente ferito", wound_status_label(10, 20) == "Gravemente ferito")
    check("51% -> Ferito (sopra la soglia del 50%)", wound_status_label(11, 20) == "Ferito")
    check("25% -> In fin di vita", wound_status_label(5, 20) == "In fin di vita")
    check("26% -> Gravemente ferito (sopra la soglia del 25%)",
          wound_status_label(6, 20) == "Gravemente ferito")
    check("0 -> Fuori combattimento", wound_status_label(0, 20) == "Fuori combattimento")
    check("hp_current negativo trattato come 0", wound_status_label(-5, 20) == "Fuori combattimento")
    check("hp_max=0 e hp_current=0 -> Fuori combattimento (mai una divisione per zero)",
          wound_status_label(0, 0) == "Fuori combattimento")
    check("hp_max=0 e hp_current>0 -> Illeso (dato malformato, mai un crash)",
          wound_status_label(5, 0) == "Illeso")


# ---------------------------------------------------------------------------
# [6] Bug di correttezza: incontro visibile PRIMA dell'ingresso di un giocatore
# ---------------------------------------------------------------------------

def test_incontro_arriva_a_chi_entra_dopo() -> None:
    print("\n[6] Un incontro reso visibile prima dell'ingresso arriva comunque al nuovo membro")

    from network.host_server import WorldHostServer
    from core.world_backend import RemoteBackend

    world, encounter_id, _pc_id = _make_world_with_encounter(
        owner="dev-owner-6", player="dev-player-6",
    )
    backend = LocalBackend()

    result = _send(backend, world.id, "dev-owner-6", perm.CMD_COMBAT_TOGGLE_VISIBILITY,
                    {"encounter_id": encounter_id, "visible": True})
    check("accensione (pre-ingresso) riuscita", result.success)

    host = WorldHostServer(world.id, backend=backend, long_poll_timeout=2.0, announce=False)
    port = host.start()
    try:
        client = RemoteBackend("127.0.0.1", port, "dev-player-tardivo", world_id=world.id)
        outcome = client.join(world.join_code, host.pin, "Arrivato Dopo")
        req_id = outcome.request_id
        host.approve(req_id)
        join_outcome = client.poll_join_status(req_id)
        check("ingresso approvato con token", join_outcome.status == "approved" and bool(client.token))

        finalize_result = world_sync._finalize_join(client, f"127.0.0.1:{port}")
        check("_finalize_join riesce", finalize_result.success)

        visible = master_repo.get_visible_encounter_for_world(world.id)
        check("l'incontro reso visibile PRIMA dell'ingresso è comunque visibile dopo "
              "_finalize_join (bug di correttezza corretto nel passo 9/7C)",
              visible is not None and visible.id == encounter_id)
        members = master_repo.get_replica_encounter_members(encounter_id)
        check("i membri sono arrivati insieme allo snapshot", len(members) == 2)
    finally:
        host.stop()


def main() -> int:
    print("=" * 62)
    print("PASSO 7C — Tracker di combattimento condiviso (§6.5)")
    print(f"HOME di test: {_TMP_HOME}")
    print("=" * 62)
    init_db()
    test_handler_fail_closed()
    test_toggle_visibility()
    test_next_turn_comportamento_invariato()
    test_replica_riceve_stato_incontro()
    test_wound_status_label()
    test_incontro_arriva_a_chi_entra_dopo()
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
