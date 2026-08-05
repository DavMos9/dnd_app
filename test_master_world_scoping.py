"""
Batteria di verifica — Modalità Master world-scoped (2026-08-06).

Copre il fix dei due bug segnalati da Davide via screenshot ("il player
entrato in un mondo appare duplicato nei picker della Sezione Master" /
"in Master escono i personaggi di ogni mondo mescolati") più la scelta
esplicita di Davide di includere in questo stesso giro anche la visibilità
per-nota di `multiplayer_design.md` §7:

  [1] character_repo.get_master_visible_characters() — mutua esclusione
      locale/istanze, per mondo
  [2] world_repo.get_worlds_for_device(roles=...) — filtro ruolo
      (owner/master compaiono nel selettore "mondo da masterare",
      un semplice player no)
  [3] master_repo — CRUD master_campaign_notes con world_id/visibility/
      visible_to_device_ids, incluso il filtro per mondo di
      get_master_campaign_notes()

Nessuna UI Flet toccata da queste funzioni — nessun bisogno di `import flet`,
evita la classe di problemi (già nota, ambientale) delle batterie che
importano `flet` dopo aver spostato HOME su una cartella temporanea.

Usa SEMPRE un DB temporaneo isolato (tempfile.mkdtemp() + HOME separato): il
DB reale di Davide non viene mai toccato. Stesso pattern di
test_mondo_senza_rete.py/test_istanze_personaggio.py.

Eseguire con:
    PYTHONPATH="." python3 test_master_world_scoping.py
"""

from __future__ import annotations

import os
import tempfile

_TMP_HOME = tempfile.mkdtemp(prefix="dnd_master_world_")
os.environ["HOME"] = _TMP_HOME

from data.database import init_db  # noqa: E402
from data.models import Character  # noqa: E402
from data.repositories import character_repo, master_repo, world_repo  # noqa: E402
from core.world_permissions import ROLE_MASTER, ROLE_OWNER, ROLE_PLAYER  # noqa: E402

_PASS = 0
_FAIL: list[str] = []


def check(label: str, cond: bool) -> None:
    global _PASS
    if cond:
        _PASS += 1
    else:
        _FAIL.append(label)
        print(f"  FALLITO: {label}")


def _make_character(name: str) -> Character:
    c = Character(name=name, class_name="Guerriero", level=1)
    character_repo.create(c)
    return c


def test_get_master_visible_characters() -> None:
    print("\n[1] character_repo.get_master_visible_characters — mutua esclusione per mondo")

    local_a = _make_character("Locale A")
    local_b = _make_character("Locale B")

    world1 = world_repo.create_world("Mondo Uno", "device-master", "Master")
    world2 = world_repo.create_world("Mondo Due", "device-master", "Master")
    assert world1 is not None and world2 is not None

    # Simula un'istanza (senza passare da core/character_instances.py: qui
    # interessa solo il filtro, non la logica di creazione dell'istanza).
    inst1 = Character(name="Locale A", class_name="Guerriero", level=1,
                       world_id=world1.id, origin_character_id=local_a.id,
                       owner_device_id="device-player")
    character_repo.create(inst1)

    # "Nessun mondo" (modalità locale): solo i personaggi locali, MAI le
    # istanze — è il fix di "in Master escono i personaggi di ogni mondo
    # mescolati".
    local_ctx = character_repo.get_master_visible_characters("")
    local_ids = {c.id for c in local_ctx}
    check("modalità locale include Locale A", local_a.id in local_ids)
    check("modalità locale include Locale B", local_b.id in local_ids)
    check("modalità locale ESCLUDE l'istanza di Mondo Uno", inst1.id not in local_ids)

    # Mondo Uno: solo la sua istanza, MAI l'originale locale — è il fix di
    # "il player entrato in un mondo appare duplicato".
    world1_ctx = character_repo.get_master_visible_characters(world1.id)
    world1_ids = {c.id for c in world1_ctx}
    check("Mondo Uno include la propria istanza", inst1.id in world1_ids)
    check("Mondo Uno ESCLUDE l'originale locale (niente duplicato)", local_a.id not in world1_ids)
    check("Mondo Uno ESCLUDE Locale B (mai entrato in nessun mondo)", local_b.id not in world1_ids)

    # Mondo Due: nessuna istanza propria — nessuna "fuga" dell'istanza di
    # Mondo Uno in un mondo diverso.
    world2_ctx = character_repo.get_master_visible_characters(world2.id)
    check("Mondo Due non contiene l'istanza di Mondo Uno", inst1.id not in {c.id for c in world2_ctx})
    check("Mondo Due è vuoto (nessuna istanza propria)", len(world2_ctx) == 0)


def test_get_worlds_for_device_roles() -> None:
    print("\n[2] world_repo.get_worlds_for_device(roles=...) — filtro ruolo")

    owner_device = "device-owner-2"
    player_device = "device-player-2"

    world = world_repo.create_world("Mondo Ruoli", owner_device, "Owner")
    assert world is not None
    joined = world_repo.join_world_by_code(world.join_code, player_device, "Giocatore")
    assert joined is not None

    owner_masterable = world_repo.get_worlds_for_device(owner_device, roles=(ROLE_OWNER, ROLE_MASTER))
    check("l'owner vede il mondo tra i masterabili", any(w.id == world.id for w in owner_masterable))

    player_masterable = world_repo.get_worlds_for_device(player_device, roles=(ROLE_OWNER, ROLE_MASTER))
    check("un semplice player NON vede il mondo tra i masterabili",
          not any(w.id == world.id for w in player_masterable))

    player_all = world_repo.get_worlds_for_device(player_device)
    check("senza filtro roles il player vede comunque il mondo (compatibilità)",
          any(w.id == world.id for w in player_all))

    # Promozione a master: ora deve comparire anche nel selettore masterabile.
    world_repo.update_member_role(world.id, player_device, ROLE_MASTER)
    player_masterable_after = world_repo.get_worlds_for_device(player_device, roles=(ROLE_OWNER, ROLE_MASTER))
    check("dopo la promozione a master, il mondo compare tra i masterabili",
          any(w.id == world.id for w in player_masterable_after))


def test_master_campaign_notes_world_and_visibility() -> None:
    print("\n[3] master_repo — master_campaign_notes con world_id/visibility")

    world = world_repo.create_world("Mondo Note", "device-owner-3", "Owner")
    assert world is not None

    local_note = master_repo.create_master_campaign_note("quest", "Missione locale")
    world_note = master_repo.create_master_campaign_note(
        "quest", "Missione del mondo", world_id=world.id,
        visibility="all", visible_to_device_ids="[]",
    )
    assert local_note is not None and world_note is not None

    check("nota locale nasce con world_id vuoto", local_note.world_id == "")
    check("nota locale nasce 'private' di default", local_note.visibility == "private")
    check("nota di mondo porta il world_id corretto", world_note.world_id == world.id)
    check("nota di mondo porta la visibilità richiesta", world_note.visibility == "all")

    # Filtro per mondo: la vista "Nessun mondo" non deve mai mostrare le
    # note di un mondo, e viceversa.
    local_ctx_notes = master_repo.get_master_campaign_notes(world_id="")
    check("filtro locale include la nota locale", any(n.id == local_note.id for n in local_ctx_notes))
    check("filtro locale ESCLUDE la nota del mondo", not any(n.id == world_note.id for n in local_ctx_notes))

    world_ctx_notes = master_repo.get_master_campaign_notes(world_id=world.id)
    check("filtro per mondo include la nota del mondo", any(n.id == world_note.id for n in world_ctx_notes))
    check("filtro per mondo ESCLUDE la nota locale", not any(n.id == local_note.id for n in world_ctx_notes))

    # world_id=None (default): nessun filtro, compatibilità con la firma
    # precedente della funzione.
    unfiltered = master_repo.get_master_campaign_notes()
    check("senza filtro world_id, entrambe le note compaiono",
          {local_note.id, world_note.id}.issubset({n.id for n in unfiltered}))

    # Aggiornamento visibilità verso "selected" con destinatari espliciti.
    ok = master_repo.update_master_campaign_note(
        world_note.id, "Missione del mondo (rivista)", visibility="selected",
        visible_to_device_ids='["device-player-x"]',
    )
    check("update_master_campaign_note ha successo", ok)
    reloaded = [n for n in master_repo.get_master_campaign_notes(world_id=world.id) if n.id == world_note.id]
    check("la nota ricaricata ha la nuova visibilità", reloaded and reloaded[0].visibility == "selected")
    check("la nota ricaricata ha i destinatari salvati",
          reloaded and reloaded[0].visible_to_device_ids == '["device-player-x"]')
    check("world_id non è cambiato dopo l'update (non modificabile)",
          reloaded and reloaded[0].world_id == world.id)


def main() -> int:
    print("=" * 62)
    print("Modalità Master world-scoped — fix duplicazione + selettore mondo")
    print(f"HOME di test: {_TMP_HOME}")
    print("=" * 62)

    init_db()
    test_get_master_visible_characters()
    test_get_worlds_for_device_roles()
    test_master_campaign_notes_world_and_visibility()

    print("\n" + "=" * 62)
    print(f"Controlli passati: {_PASS} — falliti: {len(_FAIL)}")
    if _FAIL:
        print("Falliti:")
        for f in _FAIL:
            print(f"  - {f}")
        return 1
    print("Tutti i controlli passati.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
