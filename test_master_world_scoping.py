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
from core import world_permissions as perm  # noqa: E402
from core.world_backend import LocalBackend  # noqa: E402
from core import character_instances as ci  # noqa: E402

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


def test_loot_stash_move_handler_preserves_world_id() -> None:
    """
    Bug report Davide (2026-08-20): «sposta nell'archivio da bottino...
    archivio risulta sempre vuoto». A differenza del test sopra (che
    esercita `loot_repo.move_entry()` direttamente), questo passa dal
    VERO percorso usato da `master_loot_view.py` quando un mondo è
    selezionato: il comando di rete `CMD_LOOT_STASH_MOVE` gestito da
    `core/world_backend.py::_handle_loot_stash_move`. Quell'handler
    azzerava `new_world_id` a "" quando la destinazione era "master" —
    la voce restava tecnicamente spostata, ma spariva dalla vista
    Archivio (che filtra per il mondo correntemente selezionato in
    `MasterView`), esattamente il sintomo "salva ma risulta vuoto".
    """
    print("\n[7] core/world_backend._handle_loot_stash_move — CMD_LOOT_STASH_MOVE "
          "via rete preserva il world_id in ENTRAMBE le direzioni (2026-08-20)")

    world = world_repo.create_world("Mondo Loot Handler", "device-owner-7", "Owner")
    assert world is not None
    backend = LocalBackend()

    party_entry = loot_repo.create_entry("party", "item", name="Ascia del Deposito", world_id=world.id)
    assert party_entry is not None

    result = backend.send_command(
        world.id, "device-owner-7", perm.CMD_LOOT_STASH_MOVE,
        {"entry_id": party_entry.id, "new_stash_kind": "master"},
        target_type="loot_stash", target_id=party_entry.id,
    )
    check("CMD_LOOT_STASH_MOVE (deposito -> archivio) riesce", result.success)
    moved = loot_repo.get_entry(party_entry.id)
    check("la voce mantiene il world_id del mondo, non lo azzera",
          moved is not None and moved.world_id == world.id)
    check("la voce compare nell'archivio DI QUESTO mondo",
          any(e.id == party_entry.id for e in loot_repo.get_entries("master", world_id=world.id)))
    check("...e non nell'archivio 'locale' (world_id vuoto, il bug originale)",
          not any(e.id == party_entry.id for e in loot_repo.get_entries("master", world_id="")))

    # E la direzione opposta (archivio -> deposito) continuava già a
    # funzionare — verificarla comunque, per non ri-romperla in futuro.
    result_back = backend.send_command(
        world.id, "device-owner-7", perm.CMD_LOOT_STASH_MOVE,
        {"entry_id": party_entry.id, "new_stash_kind": "party"},
        target_type="loot_stash", target_id=party_entry.id,
    )
    check("CMD_LOOT_STASH_MOVE (archivio -> deposito) riesce", result_back.success)
    back = loot_repo.get_entry(party_entry.id)
    check("torna nel deposito dello stesso mondo",
          back is not None and back.world_id == world.id and back.stash_kind == "party")


def test_loot_stash_claim() -> None:
    """
    Copre `CMD_LOOT_STASH_CLAIM` (decisione di design 2026-08-20, Davide:
    "i giocatori possono prendere da soli" — sostituisce la sola-lettura
    originale del Deposito del Gruppo). Un giocatore prende una voce DA
    SOLO: l'handler applica oggetto/monete E rimuove la voce nello stesso
    comando (`_handle_loot_stash_claim`), a differenza di `CMD_LOOT_ASSIGN`
    che lascia alla UI del Master un secondo comando di eliminazione.
    """
    print("\n[8] core/world_backend._handle_loot_stash_claim — auto-servizio "
          "dal deposito del gruppo (2026-08-20)")

    world = world_repo.create_world("Mondo Deposito Interattivo", "dev-owner-8", "Owner")
    assert world is not None
    local = Character(name="Bramwell", class_name="Ladro", race="Halfling", level=3)
    character_repo.create(local)
    result = ci.create_or_resume_instance(world.id, local.id, "dev-player-8", mode="as_is")
    assert result.success, result.error
    instance = character_repo.get_by_id(result.character_id)
    assert instance is not None
    world_repo.join_world_by_code(world.join_code, "dev-player-8", "Il Giocatore")
    world_repo.join_world_by_code(world.join_code, "dev-other-8", "Un altro giocatore")

    backend = LocalBackend()

    # Permesso: ruolo minimo player (non solo master/owner, a differenza
    # degli altri comandi loot_stash.*).
    check("ruolo minimo di loot_stash.claim è 'player'",
          perm.can_perform(ROLE_PLAYER, perm.CMD_LOOT_STASH_CLAIM))

    # -- Voce non monetaria -------------------------------------------------
    item_entry = loot_repo.create_entry("party", "item", name="Pugnale +1", world_id=world.id)
    assert item_entry is not None

    # Un altro dispositivo NON può prendere per conto del personaggio di
    # qualcun altro (stessa verifica di proprietà di hp.self_update).
    result_wrong_owner = backend.send_command(
        world.id, "dev-other-8", perm.CMD_LOOT_STASH_CLAIM,
        {"entry_id": item_entry.id}, target_type="character", target_id=instance.id,
    )
    check("un dispositivo che non possiede il personaggio non può reclamare in sua vece",
          not result_wrong_owner.success)
    check("la voce resta nel deposito dopo il tentativo rifiutato",
          loot_repo.get_entry(item_entry.id) is not None)

    result_claim = backend.send_command(
        world.id, "dev-player-8", perm.CMD_LOOT_STASH_CLAIM,
        {"entry_id": item_entry.id}, target_type="character", target_id=instance.id,
    )
    check("il proprietario del personaggio può reclamare la voce", result_claim.success)
    check("l'evento riguarda il personaggio (per far rimaterializzare le altre repliche)",
          result_claim.event is not None and result_claim.event.target_type == "character"
          and result_claim.event.target_id == instance.id)
    inv = character_repo.get_inventory(instance.id)
    check("l'oggetto è arrivato nell'inventario del personaggio",
          any(i.name == "Pugnale +1" for i in inv))
    check("la voce è sparita dal deposito del gruppo", loot_repo.get_entry(item_entry.id) is None)

    # Reclamare di nuovo la stessa voce (già consumata) fallisce senza eccezioni.
    result_again = backend.send_command(
        world.id, "dev-player-8", perm.CMD_LOOT_STASH_CLAIM,
        {"entry_id": item_entry.id}, target_type="character", target_id=instance.id,
    )
    check("reclamare due volte la stessa voce fallisce (già presa)", not result_again.success)

    # -- Monete ---------------------------------------------------------
    coins_entry = loot_repo.create_entry("party", "coins", world_id=world.id, gold=50, silver=3)
    assert coins_entry is not None
    before_currencies = character_repo.get_currencies(instance.id)
    before_gold = before_currencies.gold if before_currencies else 0

    result_coins = backend.send_command(
        world.id, "dev-player-8", perm.CMD_LOOT_STASH_CLAIM,
        {"entry_id": coins_entry.id}, target_type="character", target_id=instance.id,
    )
    check("reclamare le monete riesce", result_coins.success)
    after_currencies = character_repo.get_currencies(instance.id)
    check("le monete si sommano a quelle già presenti (mai sovrascritte)",
          after_currencies is not None and after_currencies.gold == before_gold + 50
          and after_currencies.silver == 3)
    check("la voce monete è sparita dal deposito", loot_repo.get_entry(coins_entry.id) is None)

    # -- Regressione: CMD_LOOT_ASSIGN/CMD_LOOT_STASH_CLAIM devono far
    # rimaterializzare la replica di un TERZO dispositivo (bug pre-esistente
    # trovato mentre si implementava questo comando: CMD_LOOT_ASSIGN non
    # era mai stato aggiunto a CHARACTER_MUTATING_COMMANDS).
    check("loot.assign è in CHARACTER_MUTATING_COMMANDS (bug fix 2026-08-20)",
          perm.CMD_LOOT_ASSIGN in perm.CHARACTER_MUTATING_COMMANDS)
    check("loot_stash.claim è in CHARACTER_MUTATING_COMMANDS",
          perm.CMD_LOOT_STASH_CLAIM in perm.CHARACTER_MUTATING_COMMANDS)


def test_loot_weapon_armor_mechanics() -> None:
    """
    Copre le caselle meccaniche di `entry_kind` "weapon"/"armor"
    (bug report Davide 2026-08-20: "devono avere le stesse caselle di
    quando crei l'arma o l'armatura nella sezione giocatore, manca il
    danno il tipo di arma ecc."). Una voce "weapon" deve diventare una
    riga `weapons` (mai un `inventory_items` generico) quando presa/
    assegnata; una voce "armor" un `inventory_items` con
    `category="armor"` e i campi CA/tipo/effetti.
    """
    print("\n[9] Bottino — campi meccanici arma/armatura (2026-08-20)")
    from ui.views.master.master_loot_assign_dialog import _recipient_item_payload, simple_item

    world = world_repo.create_world("Mondo Armi e Armature", "dev-owner-9", "Owner")
    assert world is not None
    local = Character(name="Aldric", class_name="Guerriero", race="Umano", level=4)
    character_repo.create(local)
    result = ci.create_or_resume_instance(world.id, local.id, "dev-player-9", mode="as_is")
    assert result.success, result.error
    instance = character_repo.get_by_id(result.character_id)
    assert instance is not None
    world_repo.join_world_by_code(world.join_code, "dev-player-9", "Il Giocatore")

    backend = LocalBackend()

    # -- Round trip nel repository -------------------------------------
    import json as _json

    magic_dmgs_json = _json.dumps(
        [{"dice": "1d8", "type": "Freddo", "note": ""}, {"dice": "1d6", "type": "Fuoco", "note": ""}],
        ensure_ascii=False,
    )
    weapon_entry = loot_repo.create_entry(
        "party", "weapon", name="Spada Fiammeggiante", world_id=world.id,
        description="Una spada avvolta dalle fiamme.",
        weapon_damage_dice="1d8", weapon_damage_type="Fuoco", weapon_category="guerra",
        weapon_properties="Accurata, Leggera", weapon_attack_bonus=1, weapon_damage_bonus=1,
        weapon_magic_damages=magic_dmgs_json,
    )
    assert weapon_entry is not None
    reloaded = loot_repo.get_entry(weapon_entry.id)
    check("i campi meccanici dell'arma sopravvivono al round trip",
          reloaded is not None and reloaded.weapon_damage_dice == "1d8"
          and reloaded.weapon_damage_type == "Fuoco" and reloaded.weapon_category == "guerra"
          and reloaded.weapon_attack_bonus == 1 and reloaded.weapon_damage_bonus == 1)
    check("BUG FIX (2026-08-20): i danni magici multipli tipizzati sopravvivono al round trip",
          reloaded is not None and reloaded.weapon_magic_damages == magic_dmgs_json)

    armor_entry = loot_repo.create_entry(
        "party", "armor", name="Corazza di Mitril", world_id=world.id,
        description="Un'armatura leggerissima.",
        armor_ca_value=16, armor_type="media", armor_effects="Nessun malus a Furtività",
    )
    assert armor_entry is not None
    reloaded_armor = loot_repo.get_entry(armor_entry.id)
    check("i campi meccanici dell'armatura sopravvivono al round trip",
          reloaded_armor is not None and reloaded_armor.armor_ca_value == 16
          and reloaded_armor.armor_type == "media"
          and reloaded_armor.armor_effects == "Nessun malus a Furtività")

    # -- Presa dal deposito (CMD_LOOT_STASH_CLAIM) ----------------------
    before_weapons = {w.id for w in character_repo.get_weapons(instance.id, equipped_only=False)}
    result_claim = backend.send_command(
        world.id, "dev-player-9", perm.CMD_LOOT_STASH_CLAIM,
        {"entry_id": weapon_entry.id}, target_type="character", target_id=instance.id,
    )
    check("presa dell'arma riuscita", result_claim.success)
    new_weapons = [w for w in character_repo.get_weapons(instance.id, equipped_only=False)
                   if w.id not in before_weapons]
    check("è comparsa esattamente una nuova arma", len(new_weapons) == 1)
    if new_weapons:
        w = new_weapons[0]
        check("l'arma presa ha nome/dado danno/tipo/categoria/bonus corretti",
              w.name == "Spada Fiammeggiante" and w.damage_dice == "1d8"
              and w.damage_type == "Fuoco" and w.weapon_category == "guerra"
              and w.attack_bonus == 1 and w.damage_bonus == 1)
        check("BUG FIX: i danni magici multipli tipizzati (ghiaccio 1d8 + fuoco 1d6) "
              "sono arrivati sull'arma presa dal deposito",
              _json.loads(w.magic_damages or "[]") == _json.loads(magic_dmgs_json))
    check("l'arma presa NON è finita anche in inventory_items",
          not any(i.name == "Spada Fiammeggiante" for i in character_repo.get_inventory(instance.id)))

    result_claim_armor = backend.send_command(
        world.id, "dev-player-9", perm.CMD_LOOT_STASH_CLAIM,
        {"entry_id": armor_entry.id}, target_type="character", target_id=instance.id,
    )
    check("presa dell'armatura riuscita", result_claim_armor.success)
    armor_item = next((i for i in character_repo.get_inventory(instance.id)
                        if i.name == "Corazza di Mitril"), None)
    check("l'armatura presa è in inventory_items con CA/tipo/effetti corretti",
          armor_item is not None and armor_item.category == "armor"
          and armor_item.ca_value == 16 and armor_item.armor_type == "media"
          and armor_item.effects == "Nessun malus a Furtività")

    # -- Assegnazione dal Master (CMD_LOOT_ASSIGN) ----------------------
    assign_magic_dmgs = _json.dumps([{"dice": "1d6", "type": "Tuono", "note": "al colpo"}],
                                     ensure_ascii=False)
    weapon_item = simple_item(
        "weapon", "Ascia da Battaglia", description="Un'ascia pesante.",
        mechanics={"weapon_damage_dice": "1d10", "weapon_damage_type": "Taglio",
                   "weapon_category": "guerra", "weapon_attack_bonus": 0, "weapon_damage_bonus": 0,
                   "weapon_properties": "A due mani", "weapon_magic_damages": assign_magic_dmgs},
    )
    payload = _recipient_item_payload(weapon_item, instance.id, 1)
    check("il payload di rete porta con sé i danni magici multipli",
          payload.get("weapon_magic_damages") == assign_magic_dmgs)
    before_weapons_2 = {w.id for w in character_repo.get_weapons(instance.id, equipped_only=False)}
    result_assign = backend.send_command(
        world.id, "dev-owner-9", perm.CMD_LOOT_ASSIGN,
        {"items": [payload], "coins": []}, target_type="world", target_id=world.id,
    )
    check("l'assegnazione di un'arma dal Master riesce", result_assign.success)
    new_weapons_2 = [w for w in character_repo.get_weapons(instance.id, equipped_only=False)
                     if w.id not in before_weapons_2]
    check("è comparsa una nuova arma assegnata dal Master, con i campi giusti",
          len(new_weapons_2) == 1 and new_weapons_2[0].name == "Ascia da Battaglia"
          and new_weapons_2[0].damage_dice == "1d10" and new_weapons_2[0].weapon_category == "guerra")
    check("BUG FIX: i danni magici multipli sono arrivati sull'arma assegnata dal Master",
          bool(new_weapons_2) and _json.loads(new_weapons_2[0].magic_damages or "[]")
          == _json.loads(assign_magic_dmgs))

    # -- build_weapon_mechanics_fields(): righe ripetibili lato UI --------
    from ui.views.master.master_loot_assign_dialog import build_weapon_mechanics_fields

    _, read_empty = build_weapon_mechanics_fields()
    check("form vuoto -> nessun danno magico", read_empty()["weapon_magic_damages"] == "[]")

    control, read_fn = build_weapon_mechanics_fields()
    magic_section = control.controls[-1]
    add_btn = magic_section.controls[0].controls[1]
    magic_rows_col = magic_section.controls[1]
    add_btn.on_click(None)
    add_btn.on_click(None)
    check("«+ Aggiungi danno» aggiunge righe", len(magic_rows_col.controls) == 2)
    magic_rows_col.controls[0].controls[0].value = "1d8"
    magic_rows_col.controls[0].controls[1].value = "Freddo"
    magic_rows_col.controls[1].controls[0].value = "1d6"
    magic_rows_col.controls[1].controls[1].value = "Fuoco"
    result = read_fn()["weapon_magic_damages"]
    check("_read() raccoglie entrambe le righe compilate",
          _json.loads(result) == [{"dice": "1d8", "type": "Freddo", "note": ""},
                                   {"dice": "1d6", "type": "Fuoco", "note": ""}])

    remove_btn = magic_rows_col.controls[0].controls[3]
    remove_btn.on_click(None)
    check("il pulsante rimuovi toglie la riga", len(magic_rows_col.controls) == 1)

    _, read_prefill = build_weapon_mechanics_fields({"weapon_magic_damages": magic_dmgs_json})
    check("il prefill ricostruisce le righe esistenti in modifica",
          _json.loads(read_prefill()["weapon_magic_damages"]) == _json.loads(magic_dmgs_json))


class _FakePage:
    """Sola `show_dialog`/`pop_dialog`/`update`/`run_task` — sufficiente
    per costruire un dialog di `MasterLootView` senza montarlo davvero."""

    def __init__(self) -> None:
        self.dialogs: list = []

    def show_dialog(self, dlg) -> None:
        self.dialogs.append(dlg)

    def pop_dialog(self, *_a) -> None:
        if self.dialogs:
            self.dialogs.pop()

    def update(self, *_a, **_k) -> None:
        pass

    def run_task(self, *_a, **_k) -> None:
        pass


def test_loot_entry_kind_editable() -> None:
    """
    Bug report Davide: "quando un artefatto viene salvato in archivio dopo
    che è stato generato... quando lo modifico deve avere la possibilità di
    essere modificato in toto, e cioè può essere selezionato il tipo, magari
    il master vuole assegnare quell'effetto ad un abito ad un'arma o ad un
    anello... e così via". Prima `loot_repo.update_entry()` non toccava
    affatto la colonna `entry_kind` e "Modifica Voce" non aveva alcun
    dropdown tipo (solo "Aggiungi Voce" lo aveva) — una volta salvata, una
    voce restava per sempre del tipo scelto alla creazione.
    """
    print("\n[10] Bottino — tipo di voce modificabile dopo il salvataggio (2026-08-20)")
    from ui.views.master.master_loot_view import MasterLootView

    # -- Livello repository: entry_kind ora è un campo scrivibile --------
    artifact_entry = loot_repo.create_entry(
        "master", "artifact", name="Lama del Vuoto",
        description="Un artefatto DMG che risucchia l'anima.",
    )
    assert artifact_entry is not None
    ok = loot_repo.update_entry(
        artifact_entry.id, name="Lama del Vuoto", description=artifact_entry.description,
        quantity=1, source_note="", entry_kind="weapon",
        weapon_damage_dice="2d6", weapon_damage_type="Necrotico", weapon_category="guerra",
    )
    check("update_entry con un nuovo entry_kind riesce", ok)
    reloaded_artifact = loot_repo.get_entry(artifact_entry.id)
    check("BUG FIX: il tipo è cambiato da 'artifact' a 'weapon'",
          reloaded_artifact is not None and reloaded_artifact.entry_kind == "weapon")
    check("...con i campi meccanici della nuova arma applicati",
          reloaded_artifact is not None and reloaded_artifact.weapon_damage_dice == "2d6"
          and reloaded_artifact.weapon_damage_type == "Necrotico")

    ok2 = loot_repo.update_entry(
        artifact_entry.id, name="Lama del Vuoto (rinominata)", description="",
        quantity=1, source_note="",  # entry_kind non passato -> default ""
    )
    check("update_entry senza entry_kind riesce", ok2)
    reloaded_again = loot_repo.get_entry(artifact_entry.id)
    check("entry_kind non passato ('') lascia il tipo invariato ('weapon')",
          reloaded_again is not None and reloaded_again.entry_kind == "weapon")

    # -- Livello UI: dropdown «Tipo di voce» in «Modifica Voce» ----------
    ring_entry = loot_repo.create_entry(
        "master", "artifact", name="Anello del Vuoto",
        description="Un artefatto minore, ancora senza meccaniche assegnate.",
    )
    assert ring_entry is not None
    view = MasterLootView(world_id="", device_id="dev-master-10")
    view._page = _FakePage()  # type: ignore[attr-defined]
    view._active_kind = "master"
    view._open_edit_dialog(ring_entry)
    check("«Modifica Voce» apre un dialog", bool(view._page.dialogs))
    dlg = view._page.dialogs[-1]

    def _find_kind_dd(control):
        if getattr(control, "label", None) == "Tipo di voce":
            return control
        for attr in ("controls",):
            kids = getattr(control, attr, None)
            if isinstance(kids, (list, tuple)):
                for k in kids:
                    found = _find_kind_dd(k)
                    if found is not None:
                        return found
        content = getattr(control, "content", None)
        if content is not None and not isinstance(content, str):
            return _find_kind_dd(content)
        return None

    kind_dd = _find_kind_dd(dlg.content)
    check("il dialog «Modifica Voce» ora ha un dropdown «Tipo di voce»", kind_dd is not None)
    check("il valore di partenza è il tipo corrente della voce ('artifact')",
          kind_dd is not None and kind_dd.value == "artifact")
    check("«Monete» non è tra le opzioni (cambio di forma dei dati, non di tipo)",
          kind_dd is not None and not any(o.key == "coins" for o in kind_dd.options))

    def _find_field(control, label_substr: str):
        if label_substr in str(getattr(control, "label", "")):
            return control
        for attr in ("controls",):
            kids = getattr(control, attr, None)
            if isinstance(kids, (list, tuple)):
                for k in kids:
                    found = _find_field(k, label_substr)
                    if found is not None:
                        return found
        content = getattr(control, "content", None)
        if content is not None and not isinstance(content, str):
            return _find_field(content, label_substr)
        return None

    check("nessuna sezione meccanica per 'artifact' inizialmente",
          _find_field(dlg.content, "Dado danno") is None)

    # Cambia il tipo in "weapon": deve comparire la sezione meccanica.
    kind_dd.value = "weapon"
    kind_dd.on_select(None)
    check("selezionare 'Arma' fa comparire le caselle meccaniche",
          _find_field(dlg.content, "Dado danno") is not None)

    # Compila il campo "Dado danno" appena comparso, poi salva.
    dice_field = _find_field(dlg.content, "Dado danno")
    if dice_field is not None:
        dice_field.value = "1d10"

    save_btn = dlg.actions[0].controls[1]
    check("il secondo pulsante è «Salva»",
          getattr(save_btn, "content", None) == "Salva")
    save_btn.on_click(None)

    reloaded_ring = loot_repo.get_entry(ring_entry.id)
    check("BUG FIX: la voce d'archivio è passata da 'artifact' ad 'weapon' via UI",
          reloaded_ring is not None and reloaded_ring.entry_kind == "weapon")
    if dice_field is not None:
        check("...con il dado danno compilato nel form applicato",
              reloaded_ring is not None and reloaded_ring.weapon_damage_dice == "1d10")


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
    test_loot_stash_move_handler_preserves_world_id()
    test_loot_stash_claim()
    test_loot_weapon_armor_mechanics()
    test_loot_entry_kind_editable()

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
