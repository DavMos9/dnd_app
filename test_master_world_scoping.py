"""
Batteria di verifica — Modalità Master world-scoped (2026-08-06, estesa
2026-08-12).

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

2026-08-12 — bug report Davide ("nella sezione master le note, gli
incontri, oggetti bottino e npc... tutto deve essere dipendente dal
mondo... selezionare un mondo è come se entrassi in un container con le
sue cose"): le note (sopra) erano già corrette, NPC/incontri/bottino no —
completato qui:

  [4] master_repo — NPC di rubrica: `get_npcs()`/`create_npc()`/
      `create_npc_from_monster()` ora filtrano/impostano `world_id`
      (prima: nessuna colonna, nessun filtro, tutti gli NPC visibili in
      ogni mondo)
  [5] master_repo — Incontri: `get_encounters()`/`create_encounter()` ora
      filtrano/impostano `world_id` (la colonna esisteva già per il
      Tracker condiviso §6.5, ma non era mai usata per la lista/creazione)
  [6] loot_repo — Bottino: l'Archivio del Master (`stash_kind="master"`,
      prima sempre `world_id=""` per scelta di design) ora è scoped al
      mondo selezionato esattamente come il Deposito del Gruppo, più il
      fix collaterale di `move_entry()` tra i due contenitori

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
from data.repositories import character_repo, loot_repo, master_repo, world_repo  # noqa: E402
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


def test_npcs_world_scoped() -> None:
    print("\n[4] master_repo — NPC di rubrica world-scoped (bug report Davide, "
          "2026-08-12: \"in Master... npc... tutto deve essere dipendente dal mondo\")")

    world_a = world_repo.create_world("Mondo NPC A", "device-owner-4a", "Owner")
    world_b = world_repo.create_world("Mondo NPC B", "device-owner-4b", "Owner")
    assert world_a is not None and world_b is not None

    local_npc = master_repo.create_npc(name="Locandiere Locale")
    npc_a = master_repo.create_npc(name="Guardia A", world_id=world_a.id)
    npc_b = master_repo.create_npc(name="Guardia B", world_id=world_b.id)
    assert local_npc is not None and npc_a is not None and npc_b is not None

    check("NPC locale nasce con world_id vuoto", local_npc.world_id == "")
    check("NPC del mondo A porta il world_id corretto", npc_a.world_id == world_a.id)

    local_ctx = master_repo.get_npcs(world_id="")
    check("\"Nessun mondo\" mostra solo l'NPC locale",
          {n.id for n in local_ctx} == {local_npc.id})

    ctx_a = master_repo.get_npcs(world_id=world_a.id)
    check("il mondo A mostra SOLO il suo NPC, mai quello locale né quello di B",
          {n.id for n in ctx_a} == {npc_a.id})

    ctx_b = master_repo.get_npcs(world_id=world_b.id)
    check("il mondo B mostra SOLO il suo NPC",
          {n.id for n in ctx_b} == {npc_b.id})

    # create_npc_from_monster (percorso "Nuovo dal Bestiario") propaga world_id.
    npc_from_monster = master_repo.create_npc_from_monster(
        {"name": "Goblin", "type": "umanoide", "ac": 15}, world_id=world_a.id,
    )
    check("create_npc_from_monster propaga world_id",
          npc_from_monster is not None and npc_from_monster.world_id == world_a.id)


def test_encounters_world_scoped() -> None:
    print("\n[5] master_repo — Incontri world-scoped (stessa richiesta: "
          "\"in Master... incontri... tutto deve essere dipendente dal mondo\")")

    world_a = world_repo.create_world("Mondo Incontri A", "device-owner-5a", "Owner")
    world_b = world_repo.create_world("Mondo Incontri B", "device-owner-5b", "Owner")
    assert world_a is not None and world_b is not None

    local_enc = master_repo.create_encounter("Imboscata Locale")
    enc_a = master_repo.create_encounter("Imboscata A", world_id=world_a.id)
    enc_b = master_repo.create_encounter("Imboscata B", world_id=world_b.id)
    assert local_enc is not None and enc_a is not None and enc_b is not None

    check("incontro locale nasce con world_id vuoto", local_enc.world_id == "")
    check("incontro del mondo A porta il world_id corretto", enc_a.world_id == world_a.id)

    local_ctx = master_repo.get_encounters(include_archived=True, world_id="")
    check("\"Nessun mondo\" mostra solo l'incontro locale",
          {e.id for e in local_ctx} == {local_enc.id})

    ctx_a = master_repo.get_encounters(include_archived=True, world_id=world_a.id)
    check("il mondo A mostra SOLO il suo incontro, mai quello locale né quello di B",
          {e.id for e in ctx_a} == {enc_a.id})

    # `set_encounter_world`/`visible_to_players` restano il meccanismo
    # SEPARATO di condivisione (§6.5) — non toccato da questo fix, ma non
    # deve rompersi: un incontro già assegnato a un mondo può ancora essere
    # reso visibile ai giocatori.
    ok = master_repo.set_encounter_visibility(enc_a.id, True)
    check("set_encounter_visibility continua a funzionare su un incontro world-scoped", ok)
    visible = master_repo.get_visible_encounter_for_world(world_a.id)
    check("get_visible_encounter_for_world lo trova ancora", visible is not None and visible.id == enc_a.id)


def test_loot_world_scoped() -> None:
    print("\n[6] loot_repo — Bottino (archivio del Master + deposito del gruppo) "
          "world-scoped su ENTRAMBI gli stash_kind (2026-08-12)")

    world_a = world_repo.create_world("Mondo Loot A", "device-owner-6a", "Owner")
    world_b = world_repo.create_world("Mondo Loot B", "device-owner-6b", "Owner")
    assert world_a is not None and world_b is not None

    local_item = loot_repo.create_entry("master", "item", name="Spada locale")
    item_a = loot_repo.create_entry("master", "item", name="Spada A", world_id=world_a.id)
    item_b = loot_repo.create_entry("master", "item", name="Spada B", world_id=world_b.id)
    assert local_item is not None and item_a is not None and item_b is not None

    check("voce locale d'archivio nasce con world_id vuoto", local_item.world_id == "")
    check("voce d'archivio del mondo A porta il world_id corretto", item_a.world_id == world_a.id)

    local_ctx = loot_repo.get_entries("master", world_id="")
    check("\"Nessun mondo\": l'archivio mostra solo la voce locale",
          {i.id for i in local_ctx} == {local_item.id})

    ctx_a = loot_repo.get_entries("master", world_id=world_a.id)
    check("mondo A: l'archivio mostra SOLO la sua voce, mai quella locale né quella di B",
          {i.id for i in ctx_a} == {item_a.id})

    # Spostamento archivio -> deposito comune: deve restare nello stesso
    # mondo (bug fix collaterale, 2026-08-12 — prima azzerava world_id).
    ok = loot_repo.move_entry(item_a.id, "party", new_world_id=world_a.id)
    check("move_entry ha successo", ok)
    party_ctx_a = loot_repo.get_entries("party", world_id=world_a.id)
    check("dopo lo spostamento, la voce compare nel deposito comune DELLO STESSO mondo",
          any(i.id == item_a.id for i in party_ctx_a))
    archive_ctx_a = loot_repo.get_entries("master", world_id=world_a.id)
    check("...e non è più nell'archivio del mondo A",
          not any(i.id == item_a.id for i in archive_ctx_a))


def main() -> int:
    print("=" * 62)
    print("Modalità Master world-scoped — fix duplicazione + selettore mondo")
    print(f"HOME di test: {_TMP_HOME}")
    print("=" * 62)

    init_db()
    test_get_master_visible_characters()
    test_get_worlds_for_device_roles()
    test_master_campaign_notes_world_and_visibility()
    test_npcs_world_scoped()
    test_encounters_world_scoped()
    test_loot_world_scoped()

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
