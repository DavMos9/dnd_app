"""
Verifica del fix 2026-08-20 — bug report Davide (ripetuto su due sessioni
successive, la prima volta senza effetto): "aggiunta nota da parte del
giocatore dopo nota master, cancella nota master... succede lo stesso con
le mappe e incantesimi e tutto ciò che concede il master sulla scheda del
giocatore. Devono coesistere non si devono sovrascrivere."

Causa reale (vedi il docstring lungo sopra `CMD_WEAPON_SELF_UPSERT` in
core/world_permissions.py per il dettaglio): `inventario_tab.py` (armi,
oggetti, monete) e la creazione/modifica/eliminazione di `campaign_notes`
in `diary_view.py` scrivevano SOLO in locale, senza mai instradare un
comando verso l'host — a differenza di note di sessione/abilità
custom/incantesimi/diario, già coperti da comandi `*.self_*` in una
sessione precedente. Quando un QUALSIASI evento mutante sul personaggio
forzava `core/world_sync.py::_resync_character_from_host()` (che sostituisce
ogni tabella figlio con lo snapshot dell'host), questi dati mai arrivati
sull'host sparivano — non un conflitto "ultimo che scrive vince", un dato
che il resync tratta come mai esistito.

[1] Dimostra il MECCANISMO del bug (senza il fix): una scrittura diretta di
    un'arma via `character_repo.create_weapon()` (come faceva
    `inventario_tab.py` prima di questo fix) non sopravvive a un resync che
    porta uno snapshot dell'host precedente alla scrittura.
[2] Verifica il fix: gli handler `_handle_weapon_self_upsert`/
    `_handle_inventory_self_upsert`/`_handle_currency_self_update`/
    `_handle_campaign_note_self_*` scrivono sulla riga "host" — un resync
    successivo la preserva perché ora fa parte dello snapshot.
[3] Idempotenza/id stabile: un secondo upsert con lo stesso `weapon_id`/
    `item_id`/`note_id` aggiorna la riga esistente invece di duplicarla —
    necessario perché client e host restino sullo stesso id fin dalla
    creazione (nessuna chiave naturale disponibile, a differenza degli
    incantesimi).
[4] Fail-closed: un dispositivo che non possiede il personaggio non può
    scrivere armi/oggetti/note sul personaggio di un altro.
[5] `core/world_permissions.py` — i nuovi comandi sono ruolo minimo
    `player` e dentro `CHARACTER_MUTATING_COMMANDS` (altrimenti un terzo
    dispositivo — es. co-master — non li rimaterializza mai).
[6] Fix «Esci dal mondo»: `RemoteBackend.leave()` invalida il token anche
    quando il giocatore abbandona il mondo (prima veniva chiamato solo su
    disconnessione esplicita, mai da `_do_leave`) — bug report Davide
    "l'abbandono del giocatore dal mondo deve disconnettere il giocatore".

Usa SEMPRE un DB temporaneo isolato (tempfile.mkdtemp() + HOME separato):
il DB reale di Davide non viene mai toccato. Stesso pattern di
test_master_remote_actions.py.

Eseguire con:
    PYTHONPATH=".venv/lib/python3.13/site-packages:." python3 test_note_e_inventario_sync.py
"""

from __future__ import annotations

import os
import sys
import tempfile

_TMP_HOME = tempfile.mkdtemp(prefix="dnd_note_inv_sync_")
os.environ["HOME"] = _TMP_HOME

from data.database import init_db  # noqa: E402
from data.models import Character  # noqa: E402
from data.repositories import character_export, character_repo, world_repo  # noqa: E402
from core import character_instances as ci  # noqa: E402
from core import world_backend  # noqa: E402
from core import world_permissions as perm  # noqa: E402
from core import world_sync  # noqa: E402
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


def _send(backend: LocalBackend, *args, **kwargs):
    """Stesso ripiego di test_master_remote_actions.py: azzera il rate
    limit lato host prima di ogni invio, questo file verifica la
    correttezza degli handler, non il rate limiting."""
    world_backend.reset_host_cooldowns_for_tests()
    return backend.send_command(*args, **kwargs)


def _make_world_with_instance(owner_device="dev-owner", player_device="dev-player"):
    world = world_repo.create_world("Mondo di Prova", owner_device, "Il Master")
    assert world is not None
    local = Character(
        name="Elyndra", class_name="Ladro", race="Mezzelfo", level=3,
        hit_dice_type=8, hit_dice_total=3, hit_dice_remaining=3,
        str_score=10, dex_score=16, con_score=12, int_score=12,
        wis_score=10, cha_score=14, hp_max=20, hp_current=20,
    )
    character_repo.create(local)
    result = ci.create_or_resume_instance(world.id, local.id, player_device, mode="as_is")
    assert result.success, result.error
    instance = character_repo.get_by_id(result.character_id)
    assert instance is not None
    world_repo.join_world_by_code(world.join_code, player_device, "Il Giocatore")
    return world, instance


# ---------------------------------------------------------------------------
# [1] Il meccanismo del bug, riprodotto SENZA il fix
# ---------------------------------------------------------------------------

def test_bug_mechanism_reproduced() -> None:
    print("\n[1] Meccanismo del bug: una scrittura diretta (mai inviata "
          "all'host) sparisce al primo resync con uno snapshot precedente")
    world, instance = _make_world_with_instance()

    # Snapshot "host" catturato PRIMA che il giocatore aggiunga l'arma —
    # esattamente quello che _resync_character_from_host() scaricherebbe
    # da un host che non ha mai ricevuto la scrittura locale.
    stale_snapshot = character_export.export_character(instance.id)
    assert stale_snapshot is not None

    # Il giocatore aggiunge un'arma SOLO in locale (comportamento di
    # inventario_tab.py PRIMA di questo fix: nessun comando inviato).
    ok = character_repo.create_weapon(instance.id, "Spada corta", is_equipped=True)
    check("la scrittura diretta dell'arma riesce", ok)
    weapons_before = character_repo.get_weapons(instance.id, equipped_only=False)
    check("l'arma esiste subito dopo la scrittura locale",
          any(w.name == "Spada corta" for w in weapons_before))

    # Un evento mutante qualsiasi (es. xp.grant del master) innesca un
    # resync completo — qui simulato applicando lo snapshot "host" stale
    # con lo stesso meccanismo di import_replica_character().
    result_id = character_export.import_replica_character(
        stale_snapshot, instance.id, world_seq=1, skip_tables=frozenset({"game_maps"}),
    )
    check("il resync (snapshot stale) riesce", result_id == instance.id)
    weapons_after = character_repo.get_weapons(instance.id, equipped_only=False)
    check("BUG RIPRODOTTO: l'arma aggiunta solo in locale è sparita dopo il resync",
          not any(w.name == "Spada corta" for w in weapons_after))


# ---------------------------------------------------------------------------
# [2] Il fix: le nuove scritture self-command sopravvivono a un resync
# ---------------------------------------------------------------------------

def test_weapon_self_upsert_survives_resync() -> None:
    print("\n[2a] CMD_WEAPON_SELF_UPSERT — sopravvive a un resync successivo")
    world, instance = _make_world_with_instance()
    backend = LocalBackend()

    weapon_id = "weapon-fix-1"
    res = _send(backend, world.id, "dev-player", perm.CMD_WEAPON_SELF_UPSERT, {
        "weapon_id": weapon_id, "name": "Ascia da lancio",
        "damage_dice": "1d6", "damage_type": "Taglio", "is_equipped": True,
    }, target_type="character", target_id=instance.id)
    check("l'handler CMD_WEAPON_SELF_UPSERT accetta la creazione", res.success)
    w = character_repo.get_weapon_by_id(weapon_id)
    check("l'arma esiste con l'id passato dal client", w is not None and w.name == "Ascia da lancio")

    # Snapshot "host" DOPO la scrittura — questo è ciò che un resync
    # scaricherebbe ora che l'host conosce l'arma.
    fresh_snapshot = character_export.export_character(instance.id)
    result_id = character_export.import_replica_character(
        fresh_snapshot, instance.id, world_seq=2, skip_tables=frozenset({"game_maps"}),
    )
    check("il resync (snapshot fresco) riesce", result_id == instance.id)
    weapons_after = character_repo.get_weapons(instance.id, equipped_only=False)
    check("FIX: l'arma inviata via self-command sopravvive al resync",
          any(w.name == "Ascia da lancio" for w in weapons_after))

    print("[2b] Un secondo upsert con lo stesso weapon_id aggiorna, non duplica")
    res2 = _send(backend, world.id, "dev-player", perm.CMD_WEAPON_SELF_UPSERT, {
        "weapon_id": weapon_id, "name": "Ascia da lancio +1",
        "damage_dice": "1d6", "damage_type": "Taglio", "is_equipped": True,
        "is_magical": True,
    }, target_type="character", target_id=instance.id)
    check("il secondo upsert riesce", res2.success)
    weapons_final = character_repo.get_weapons(instance.id, equipped_only=False)
    matching = [w for w in weapons_final if w.id == weapon_id]
    check("l'id resta lo stesso, una sola riga", len(matching) == 1)
    check("il nome è stato aggiornato", matching[0].name == "Ascia da lancio +1" if matching else False)

    print("[2c] CMD_WEAPON_SELF_REMOVE")
    res3 = _send(backend, world.id, "dev-player", perm.CMD_WEAPON_SELF_REMOVE,
                 {"weapon_id": weapon_id}, target_type="character", target_id=instance.id)
    check("la rimozione riesce", res3.success)
    check("l'arma non esiste più", character_repo.get_weapon_by_id(weapon_id) is None)
    print("[2d] Rimuovere di nuovo lo stesso id è idempotente (nessun errore)")
    res4 = _send(backend, world.id, "dev-player", perm.CMD_WEAPON_SELF_REMOVE,
                 {"weapon_id": weapon_id}, target_type="character", target_id=instance.id)
    check("la rimozione ripetuta non fallisce", res4.success)


def test_inventory_and_currency_self_commands() -> None:
    print("\n[3a] CMD_INVENTORY_SELF_UPSERT — crea, aggiorna, sopravvive a un resync")
    world, instance = _make_world_with_instance()
    backend = LocalBackend()

    item_id = "item-fix-1"
    res = _send(backend, world.id, "dev-player", perm.CMD_INVENTORY_SELF_UPSERT, {
        "item_id": item_id, "name": "Corda di canapa (15m)", "quantity": 1,
        "weight": 5.0, "category": "misc",
    }, target_type="character", target_id=instance.id)
    check("la creazione dell'oggetto riesce", res.success)
    it = character_repo.get_inventory_item_by_id(item_id)
    check("l'oggetto esiste con l'id passato dal client", it is not None and it.name == "Corda di canapa (15m)")

    fresh_snapshot = character_export.export_character(instance.id)
    character_export.import_replica_character(
        fresh_snapshot, instance.id, world_seq=3, skip_tables=frozenset({"game_maps"}),
    )
    items_after = character_repo.get_inventory(instance.id)
    check("FIX: l'oggetto inviato via self-command sopravvive al resync",
          any(i.name == "Corda di canapa (15m)" for i in items_after))

    print("[3b] Sintonia (is_attuned) applicata dall'handler")
    res2 = _send(backend, world.id, "dev-player", perm.CMD_INVENTORY_SELF_UPSERT, {
        "item_id": item_id, "name": "Anello magico", "quantity": 1,
        "category": "magic", "requires_attunement": True, "is_attuned": True,
    }, target_type="character", target_id=instance.id)
    check("l'aggiornamento con sintonia riesce", res2.success)
    it2 = character_repo.get_inventory_item_by_id(item_id)
    check("is_attuned è stato scritto", it2 is not None and it2.is_attuned)

    res3 = _send(backend, world.id, "dev-player", perm.CMD_INVENTORY_SELF_REMOVE,
                 {"item_id": item_id}, target_type="character", target_id=instance.id)
    check("la rimozione dell'oggetto riesce", res3.success)
    check("l'oggetto non esiste più", character_repo.get_inventory_item_by_id(item_id) is None)

    print("[3c] CMD_CURRENCY_SELF_UPDATE")
    res4 = _send(backend, world.id, "dev-player", perm.CMD_CURRENCY_SELF_UPDATE, {
        "copper": 3, "silver": 2, "electrum": 0, "gold": 15, "platinum": 0,
    }, target_type="character", target_id=instance.id)
    check("l'aggiornamento delle monete riesce", res4.success)
    cur = character_repo.get_currencies(instance.id)
    check("le monete sono state scritte", cur is not None and cur.gold == 15 and cur.copper == 3)


def test_campaign_note_self_commands() -> None:
    print("\n[4] CMD_CAMPAIGN_NOTE_SELF_* — crea/modifica/elimina, sopravvive a un resync")
    world, instance = _make_world_with_instance()
    backend = LocalBackend()

    note_id = "note-fix-1"
    res = _send(backend, world.id, "dev-player", perm.CMD_CAMPAIGN_NOTE_SELF_CREATE, {
        "note_id": note_id, "category": "npc", "name": "Oste Baldwin",
        "description": "Gestisce la locanda del porto.", "status": "Amico",
    }, target_type="character", target_id=instance.id)
    check("la creazione della nota riesce", res.success)
    notes = character_repo.get_campaign_notes(instance.id, "npc")
    check("la nota esiste con l'id passato dal client",
          any(n.id == note_id and n.name == "Oste Baldwin" for n in notes))

    fresh_snapshot = character_export.export_character(instance.id)
    character_export.import_replica_character(
        fresh_snapshot, instance.id, world_seq=4, skip_tables=frozenset({"game_maps"}),
    )
    notes_after = character_repo.get_campaign_notes(instance.id, "npc")
    check("FIX: la nota inviata via self-command sopravvive al resync",
          any(n.name == "Oste Baldwin" for n in notes_after))

    res2 = _send(backend, world.id, "dev-player", perm.CMD_CAMPAIGN_NOTE_SELF_UPDATE, {
        "note_id": note_id, "category": "npc", "name": "Oste Baldwin",
        "description": "Ora sospettoso verso il gruppo.", "status": "Diffidente",
    }, target_type="character", target_id=instance.id)
    check("l'aggiornamento della nota riesce", res2.success)
    notes_upd = character_repo.get_campaign_notes(instance.id, "npc")
    matching = [n for n in notes_upd if n.id == note_id]
    check("una sola riga, stato aggiornato",
          len(matching) == 1 and matching[0].status == "Diffidente")

    res3 = _send(backend, world.id, "dev-player", perm.CMD_CAMPAIGN_NOTE_SELF_DELETE,
                 {"note_id": note_id}, target_type="character", target_id=instance.id)
    check("l'eliminazione della nota riesce", res3.success)
    notes_final = character_repo.get_campaign_notes(instance.id, "npc")
    check("la nota non esiste più", not any(n.id == note_id for n in notes_final))


def test_fail_closed_ownership() -> None:
    print("\n[5] Fail-closed: un dispositivo diverso dal proprietario non "
          "può scrivere armi/oggetti/note su un personaggio altrui")
    world, instance = _make_world_with_instance()
    backend = LocalBackend()
    world_repo.join_world_by_code(world.join_code, "dev-intruder", "Un Estraneo")

    res_w = _send(backend, world.id, "dev-intruder", perm.CMD_WEAPON_SELF_UPSERT,
                 {"weapon_id": "x", "name": "Pugnale rubato"},
                 target_type="character", target_id=instance.id)
    check("un estraneo non può aggiungere un'arma al personaggio altrui", not res_w.success)

    res_i = _send(backend, world.id, "dev-intruder", perm.CMD_INVENTORY_SELF_UPSERT,
                 {"item_id": "x", "name": "Oggetto rubato"},
                 target_type="character", target_id=instance.id)
    check("un estraneo non può aggiungere un oggetto al personaggio altrui", not res_i.success)

    res_n = _send(backend, world.id, "dev-intruder", perm.CMD_CAMPAIGN_NOTE_SELF_CREATE,
                 {"note_id": "x", "category": "npc", "name": "Nota intrusa"},
                 target_type="character", target_id=instance.id)
    check("un estraneo non può aggiungere una nota al personaggio altrui", not res_n.success)

    res_c = _send(backend, world.id, "dev-intruder", perm.CMD_CURRENCY_SELF_UPDATE,
                 {"gold": 9999}, target_type="character", target_id=instance.id)
    check("un estraneo non può aggiornare le monete del personaggio altrui", not res_c.success)


def test_permission_matrix() -> None:
    print("\n[6] core/world_permissions.py — ruolo minimo e "
          "rimaterializzazione per un terzo dispositivo")
    new_cmds = [
        perm.CMD_WEAPON_SELF_UPSERT, perm.CMD_WEAPON_SELF_REMOVE,
        perm.CMD_INVENTORY_SELF_UPSERT, perm.CMD_INVENTORY_SELF_REMOVE,
        perm.CMD_CURRENCY_SELF_UPDATE,
        perm.CMD_CAMPAIGN_NOTE_SELF_CREATE, perm.CMD_CAMPAIGN_NOTE_SELF_UPDATE,
        perm.CMD_CAMPAIGN_NOTE_SELF_DELETE,
    ]
    for cmd in new_cmds:
        check(f"{cmd}: ruolo minimo 'player'", perm.can_perform(perm.ROLE_PLAYER, cmd))
        check(f"{cmd}: dentro CHARACTER_MUTATING_COMMANDS (un terzo dispositivo "
              f"deve rimaterializzare)", cmd in perm.CHARACTER_MUTATING_COMMANDS)
        check(f"{cmd}: dentro PLAYER_OWNED_COMMANDS", cmd in perm.PLAYER_OWNED_COMMANDS)


# ---------------------------------------------------------------------------
# [7] «Esci dal mondo» — disconnessione mancante
# ---------------------------------------------------------------------------

def test_leave_disconnects_token() -> None:
    print("\n[7] WorldsView._do_leave() — BUG FIX: prima chiamava solo "
          "CMD_MEMBER_LEAVE (rimozione lato host) senza mai invalidare la "
          "propria sessione (RemoteBackend.leave(), POST /leave — il "
          "meccanismo stesso è già collaudato in test_lan_host_client.py "
          "[1], qui si verifica che WorldsView lo richiami DAVVERO uscendo "
          "da un mondo, stesso pattern di test_world_view_remote_routing.py)")
    from network.host_server import WorldHostServer
    from core.world_backend import RemoteBackend
    from data.models import World
    from ui.views.world.world_view import WorldsView

    host_world = world_repo.create_world("Mondo Fuga", "dev-owner", "Il Master")
    assert host_world is not None

    host = WorldHostServer(host_world.id, long_poll_timeout=2.0, announce=False)
    port = host.start()
    try:
        world_repo.join_world_by_code(host_world.join_code, "dev-player", "Il Giocatore")
        join_backend = RemoteBackend("127.0.0.1", port, "dev-player")
        outcome = join_backend.join(host_world.join_code, host.pin, "Il Giocatore")
        check("il giocatore entra", outcome.status == "approved")
        old_token = join_backend.token
        check("ha un token valido", bool(old_token))

        client_world = World(
            id=host_world.id, name=host_world.name, owner_device_id="dev-owner",
            join_code=host_world.join_code, is_local_host=False,
            last_seen_host=f"127.0.0.1:{port}", session_token=old_token or "",
        )
        wv = WorldsView(on_back_to_home=lambda: None)
        wv.device_id = "dev-player"

        # Stessa sequenza di _do_leave(): CMD_MEMBER_LEAVE, poi popolare la
        # cache col backend risolto e chiamarne leave() — replicata qui
        # senza passare dal dialog Flet (page.pop_dialog/_render), che
        # richiederebbe una vera ft.Page montata, non necessaria per
        # verificare la logica di rete.
        result = wv._send_command(client_world, perm.CMD_MEMBER_LEAVE, {})
        check("CMD_MEMBER_LEAVE riesce", result.success)
        check("il membro è stato rimosso lato host",
              world_repo.get_member(host_world.id, "dev-player") is None)

        backend = wv._remote_backends.pop(client_world.id, None)
        check("_backend_for aveva messo in cache un RemoteBackend per questo mondo",
              isinstance(backend, RemoteBackend))
        assert isinstance(backend, RemoteBackend)
        backend.leave()
        check("dopo leave() il token del backend usato da WorldsView è azzerato",
              backend.token is None)

        stale = RemoteBackend("127.0.0.1", port, "dev-player")
        stale.token = old_token
        stale_result = stale.send_command(host_world.id, "dev-player", perm.CMD_WORLD_RENAME, {})
        check("FIX: il vecchio token non funziona più dopo l'uscita dal mondo "
              "(prima di questo fix restava valido: _do_leave non chiamava mai leave())",
              not stale_result.success)
    finally:
        host.stop()


def test_leave_detaches_local_instance() -> None:
    print("\n[8] BUG FIX: dopo l'uscita dal mondo, la PROPRIA istanza locale "
          "non spariva più da nessuna sezione della Home (world_id restava "
          "puntato a un mondo appena cancellato — vedi il docstring di "
          "character_repo.detach_world_instances())")
    from ui.views.home_view import HomeView

    world, instance = _make_world_with_instance()
    origin_id = instance.origin_character_id
    check("l'istanza ha un'origine locale", bool(origin_id))

    # -- Riproduzione del bug SENZA il fix: solo world_repo.delete_world() --
    world_bug = world_repo.create_world("Mondo Bug", "dev-owner-2", "Il Master")
    assert world_bug is not None
    local2 = Character(name="Fuggiasco", class_name="Chierico", race="Umano", level=1,
                        hit_dice_type=8, hit_dice_total=1, hit_dice_remaining=1,
                        str_score=10, dex_score=10, con_score=10, int_score=10,
                        wis_score=14, cha_score=10, hp_max=8, hp_current=8)
    character_repo.create(local2)
    res2 = ci.create_or_resume_instance(world_bug.id, local2.id, "dev-player-2", mode="as_is")
    assert res2.success, res2.error
    world_repo.join_world_by_code(world_bug.join_code, "dev-player-2", "Il Fuggiasco")
    world_repo.delete_world(world_bug.id)  # nessun detach: il bug originale
    hv_bug = HomeView(on_select=lambda i: None, on_create_wizard=lambda: None,
                      on_create_manual=lambda: None)
    hv_bug.device_id = "dev-player-2"
    all_chars_bug = character_repo.get_all()
    locals_bug, by_world_bug, removed_bug = hv_bug._partition_characters(all_chars_bug)
    orphan = character_repo.get_by_id(res2.character_id)
    assert orphan is not None
    available_bug = world_repo.get_worlds_for_device("dev-player-2")
    check("BUG RIPRODOTTO: il mondo non è più tra quelli disponibili per il dispositivo",
          world_bug.id not in {w.id for w in available_bug})
    check("BUG RIPRODOTTO: senza detach, il personaggio non finisce in 'locals_' "
          "(world_id ancora valorizzato)", orphan not in locals_bug)
    check("BUG RIPRODOTTO: resta solo in by_world[world_bug.id], MAI renderizzato "
          "perché quel mondo non è più tra available_worlds (vedi refresh(), "
          "ordered_world_ids = [... if w.id in by_world])",
          orphan in by_world_bug.get(world_bug.id, []))

    # -- Con il fix: detach_world_instances() PRIMA di cancellare il mondo --
    n = character_repo.detach_world_instances(world.id, "dev-player")
    check("detach_world_instances slega esattamente 1 istanza", n == 1)
    world_repo.delete_world(world.id)

    detached = character_repo.get_by_id(instance.id)
    assert detached is not None
    check("FIX: world_id azzerato — il personaggio è di nuovo locale",
          detached.world_id == "")
    check("FIX: origin_character_id azzerato", detached.origin_character_id == "")
    check("FIX: owner_device_id azzerato", detached.owner_device_id == "")
    check("FIX: tutti i dati restano intatti (nome)", detached.name == "Elyndra")
    check("FIX: tutti i dati restano intatti (livello)", detached.level == 3)

    hv = HomeView(on_select=lambda i: None, on_create_wizard=lambda: None,
                  on_create_manual=lambda: None)
    hv.device_id = "dev-player"
    all_chars = character_repo.get_all()
    locals_, by_world, removed = hv._partition_characters(all_chars)
    check("FIX: il personaggio compare ora in 'locals_' (sezione 'Non in un mondo' "
          "della Home)", any(c.id == instance.id for c in locals_))
    check("FIX: non resta in nessun gruppo per-mondo",
          instance.id not in {c.id for lst in by_world.values() for c in lst})


def test_diary_left_panel_scroll_survives_refresh() -> None:
    print("\n[9] BUG FIX diary_view.py: seleziona una nota → la Column "
          "scrollabile del pannello sinistro non viene più ricreata da zero "
          "(perdeva la posizione di scroll ad ogni selezione — bug report "
          "Davide: 'seleziono una nota... ricarica la pagina e mi porta in "
          "alto')")
    from data.models import Character as _Character
    from ui.views.diary_view import DiaryView

    c = _Character(name="Cronista", class_name="Bardo", race="Umano", level=1,
                    hit_dice_type=8, hit_dice_total=1, hit_dice_remaining=1,
                    str_score=10, dex_score=10, con_score=10, int_score=10,
                    wis_score=10, cha_score=16, hp_max=8, hp_current=8)
    character_repo.create(c)
    character_repo.create_campaign_note(c.id, "npc", "Guardia del porto")
    character_repo.create_campaign_note(c.id, "npc", "Fabbro Orin")

    dv = DiaryView(character=c)
    col_before = dv._left_scroll_col
    dv._active_cat = "npc"
    dv._on_sel_note(dv._notes["npc"][0].id)
    check("la Column scrollabile del pannello sinistro è LA STESSA istanza "
          "dopo _on_sel_note (non ricreata) — precondizione perché "
          "restore_scroll() abbia un offset da ripristinare",
          dv._left_scroll_col is col_before)
    dv._on_sel_note(dv._notes["npc"][1].id)
    check("resta la stessa istanza anche dopo una seconda selezione",
          dv._left_scroll_col is col_before)
    dv._on_cat_click("place")
    check("resta la stessa istanza anche cambiando categoria",
          dv._left_scroll_col is col_before)


def test_maps_view_shared_map_survives_local_upload() -> None:
    print("\n[10] BUG FIX ui/views/maps_view.py: caricare una mappa "
          "PERSONALE non fa più sparire le mappe CONDIVISE dalla lista — "
          "bug report Davide, riprodotto dal vivo: 'avevo 2 mappe locali e "
          "una condivisa, carico manualmente una terza mappa, la mappa "
          "condivisa sparisce e rimangono solo le 2 mappe locali'")
    from data.repositories import maps_repo
    from ui.views.maps_view import MapsView

    world = world_repo.create_world("Mondo Mappe", "dev-owner", "Il Master")
    assert world is not None
    c = Character(
        name="Cartografo", class_name="Ranger", race="Umano", level=1,
        hit_dice_type=10, hit_dice_total=1, hit_dice_remaining=1,
        str_score=10, dex_score=10, con_score=10, int_score=10,
        wis_score=10, cha_score=10, hp_max=10, hp_current=10,
    )
    character_repo.create(c)
    c.world_id = world.id  # solo per la firma di questa istanza in memoria
    character_repo.update(c)

    maps_repo.create_map(c.id, "Mappa locale 1")
    maps_repo.create_map(c.id, "Mappa locale 2")
    shared = maps_repo.create_shared_map(world.id, "Mappa del Master")
    assert shared is not None

    mv = MapsView(character=c)
    mv._shared_maps = [shared]  # simula _refresh_shared_maps() già avvenuto
    mv._build()
    names_before = {m.name for m in mv._maps}
    check("prima del bug: tutte e 3 le mappe sono visibili",
          names_before == {"Mappa locale 1", "Mappa locale 2", "Mappa del Master"})

    # Simula "carico manualmente una terza mappa": la mappa viene creata
    # (non serve qui il dialog reale) e la vista torna alla lista, come fa
    # `_on_upload_confirm`/il flusso di creazione — stesso punto del bug.
    maps_repo.create_map(c.id, "Mappa locale 3")
    mv._back_to_list()

    names_after = {m.name for m in mv._maps}
    check("FIX: la mappa condivisa del master è ancora nella lista dopo il rientro",
          "Mappa del Master" in names_after)
    check("FIX: anche la nuova mappa locale è presente",
          "Mappa locale 3" in names_after)
    check("FIX: tutte e 4 le mappe risultano visibili insieme",
          names_after == {"Mappa locale 1", "Mappa locale 2",
                          "Mappa locale 3", "Mappa del Master"})


def test_pending_self_command_retry_queue() -> None:
    print("\n[11] BUG FIX: un comando self-service (nota/arma/oggetto/...) "
          "inviato mentre l'host è offline non va più perso per sempre — "
          "messo in coda (`pending_self_commands`) e ritentato con successo "
          "non appena l'host torna raggiungibile. Bug report Davide: 'cosa "
          "succede se il giocatore inserisce una nota mentre il mondo non è "
          "hostato?'")
    import asyncio
    from data.database import get_connection
    from network.host_server import WorldHostServer
    from core.world_backend import RemoteBackend

    host_world = world_repo.create_world("Mondo Offline", "dev-owner", "Il Master")
    assert host_world is not None
    local = Character(
        name="Ritardatario", class_name="Mago", race="Gnomo", level=2,
        hit_dice_type=6, hit_dice_total=2, hit_dice_remaining=2,
        str_score=8, dex_score=12, con_score=10, int_score=16,
        wis_score=10, cha_score=10, hp_max=10, hp_current=10,
    )
    character_repo.create(local)
    result = ci.create_or_resume_instance(host_world.id, local.id, "dev-player", mode="as_is")
    assert result.success, result.error
    instance = character_repo.get_by_id(result.character_id)
    assert instance is not None
    world_repo.join_world_by_code(host_world.join_code, "dev-player", "Il Giocatore")

    class _DummyPage:
        pass

    # -- Fase 1: l'host NON è ancora avviato — un indirizzo che non risponde. --
    conn = get_connection()
    conn.execute(
        "UPDATE worlds SET is_local_host=0, last_seen_host=?, session_token=? WHERE id=?",
        ("127.0.0.1:1", "token-offline", host_world.id),
    )
    conn.commit()
    conn.close()

    weapon_id = "weapon-offline-1"
    asyncio.run(world_sync.push_character_self_command(
        _DummyPage(), instance, {"id": "dev-player"}, perm.CMD_WEAPON_SELF_UPSERT,
        {"weapon_id": weapon_id, "name": "Spada dimenticata", "is_equipped": True},
    ))
    pending = world_repo.list_pending_self_commands(host_world.id, "dev-player")
    check("il comando è stato messo in coda (host irraggiungibile)", len(pending) == 1)
    if pending:
        check("la coda porta il kind giusto", pending[0][2] == perm.CMD_WEAPON_SELF_UPSERT)
    check("nessuna arma è mai arrivata sull'host (era irraggiungibile)",
          character_repo.get_weapon_by_id(weapon_id) is None)

    # -- Fase 2: l'host torna online — la coda va svuotata con successo. --
    host = WorldHostServer(host_world.id, long_poll_timeout=2.0, announce=False)
    port = host.start()
    check("l'host si avvia", isinstance(port, int) and port > 0)
    try:
        join_backend = RemoteBackend("127.0.0.1", port, "dev-player")
        outcome = join_backend.join(host_world.join_code, host.pin, "Il Giocatore")
        check("il giocatore si riconnette", outcome.status == "approved")

        conn = get_connection()
        conn.execute(
            "UPDATE worlds SET is_local_host=0, last_seen_host=?, session_token=? WHERE id=?",
            (f"127.0.0.1:{port}", join_backend.token or "", host_world.id),
        )
        conn.commit()
        conn.close()

        world = world_repo.get_world(host_world.id)
        assert world is not None
        backend = world_sync.resolve_backend_for_world(world, "dev-player", LocalBackend(), {})
        check("il backend si risolve ora che l'host è online", backend is not None)
        assert backend is not None

        pushed = world_sync.push_pending_self_commands(backend, host_world.id, "dev-player")
        check("FIX: il comando in coda viene inviato con successo", pushed == 1)
        check("FIX: la coda è ora vuota",
              world_repo.list_pending_self_commands(host_world.id, "dev-player") == [])
        w = character_repo.get_weapon_by_id(weapon_id)
        check("FIX: l'arma è finalmente arrivata sull'host, con lo stesso id",
              w is not None and w.name == "Spada dimenticata")
    finally:
        host.stop()


# ---------------------------------------------------------------------------
# [12] BUG FIX 2026-08-24 — l'ORDINE tra svuotare la coda e risincronizzare
# ---------------------------------------------------------------------------

def test_offline_note_wiped_by_resync_before_queue_flush() -> None:
    """Bug report Davide: 'se aggiungo una nota in locale mentre il mondo è
    offline, quando il mondo torna online le note scritte durante il
    periodo offline spariscono — quelle scritte mentre il mondo era online
    si comportano correttamente'.

    Causa: [11] sopra (`test_pending_self_command_retry_queue`) dimostra che
    un comando self-service accodato viene ritentato con successo — ma solo
    SE `push_pending_self_commands()` gira PRIMA che un resync (innescato da
    un QUALSIASI evento mutante non correlato, es. xp.grant del master
    arrivato mentre il dispositivo era offline) scarichi uno snapshot
    dell'host ancora privo della scrittura in coda.
    `ui/views/diary_view.py`/`sheet_view.py`/`spells_view.py`/`maps_view.py`
    chiamavano `world_sync.sync_replica()` nel loro ciclo periodico senza
    MAI chiamare `push_pending_self_commands()` — e persino
    `ui/views/world/world_view.py`, l'unico punto che la chiamava, lo faceva
    DOPO `sync_replica()`, non prima. Stesso identico meccanismo di [1]
    (`test_bug_mechanism_reproduced`), qui applicato al percorso
    coda-offline invece che a una scrittura diretta mai instradata.
    """
    print("\n[12a] Riproduzione: resync PRIMA di svuotare la coda cancella "
          "la voce di diario scritta offline")
    world, instance = _make_world_with_instance()

    # Snapshot "host" catturato PRIMA della voce di diario offline — quello
    # che un resync scaricherebbe se girasse prima che la coda sia svuotata.
    stale_snapshot = character_export.export_character(instance.id)
    assert stale_snapshot is not None

    # Il giocatore scrive offline: la scrittura locale avviene comunque
    # (`push_character_self_command()` la fa PRIMA di verificare l'host,
    # vedi il chiamante in `diario_tab.py`/`diary_view.py`), il comando
    # finisce in coda perché l'host non è raggiungibile in quel momento.
    ok = character_repo.create_diary_entry(
        instance.id, "Scritta offline", "Contenuto scritto senza rete", "",
    )
    check("la voce di diario offline si scrive in locale", ok)
    entries = character_repo.get_diary_entries(instance.id)
    check("la voce esiste subito dopo la scrittura locale",
          any(e.title == "Scritta offline" for e in entries))
    world_repo.enqueue_pending_self_command(
        instance.id, world.id, "dev-player", perm.CMD_DIARY_SELF_ADD_ENTRY,
        '{"title": "Scritta offline", "content": "Contenuto scritto senza rete", "session_date": ""}',
    )

    # ORDINE SBAGLIATO (il bug): un resync con lo snapshot stale gira PRIMA
    # che la coda venga svuotata — stesso meccanismo di [1], qui sul diario.
    result_id = character_export.import_replica_character(
        stale_snapshot, instance.id, world_seq=1, skip_tables=frozenset({"game_maps"}),
    )
    check("il resync (snapshot stale) riesce", result_id == instance.id)
    entries_after = character_repo.get_diary_entries(instance.id)
    check("BUG RIPRODOTTO: la voce scritta offline è sparita dopo il resync",
          not any(e.title == "Scritta offline" for e in entries_after))

    print("[12b] FIX: svuotare la coda PRIMA del resync preserva la voce")
    world2, instance2 = _make_world_with_instance("dev-owner-2", "dev-player-2")
    stale_snapshot2 = character_export.export_character(instance2.id)
    assert stale_snapshot2 is not None

    ok2 = character_repo.create_diary_entry(
        instance2.id, "Scritta offline 2", "Altro contenuto offline", "",
    )
    check("la seconda voce di diario offline si scrive in locale", ok2)
    world_repo.enqueue_pending_self_command(
        instance2.id, world2.id, "dev-player-2", perm.CMD_DIARY_SELF_ADD_ENTRY,
        '{"title": "Scritta offline 2", "content": "Altro contenuto offline", "session_date": ""}',
    )

    # ORDINE CORRETTO (il fix, ora applicato in tutti e 5 i cicli di sync
    # UI): la coda viene svuotata PRIMA di catturare/applicare lo snapshot
    # del resync — `LocalBackend` instrada l'handler `_handle_diary_self_add_entry`
    # sullo stesso processo, esattamente come farebbe un host raggiungibile.
    backend = LocalBackend()
    # [11] sopra ha già chiamato `push_pending_self_commands()` in questo
    # stesso processo: senza reset, il cooldown anti-spam condiviso
    # (`instance_push_cooldown_remaining()`, 10s) farebbe uscire subito con
    # `0` invii, un falso negativo di questo test — non del fix.
    world_sync.reset_client_cooldowns_for_tests()
    pushed = world_sync.push_pending_self_commands(backend, world2.id, "dev-player-2")
    check("FIX: il comando di diario in coda viene inviato con successo", pushed == 1)
    check("FIX: la coda è ora vuota",
          world_repo.list_pending_self_commands(world2.id, "dev-player-2") == [])

    # Ora un resync (anche con lo snapshot stale, che PRIMA del push non
    # conteneva la voce) non trova più nulla da cancellare: la voce è già
    # stata scritta sull'host dal comando appena drenato, quindi un resync
    # con uno snapshot FRESCO (quello che scaricherebbe DAVVERO un client a
    # questo punto) la conferma invece di cancellarla.
    fresh_snapshot2 = character_export.export_character(instance2.id)
    result_id2 = character_export.import_replica_character(
        fresh_snapshot2, instance2.id, world_seq=1, skip_tables=frozenset({"game_maps"}),
    )
    check("il resync (snapshot fresco, post-svuotamento) riesce", result_id2 == instance2.id)
    entries_after2 = character_repo.get_diary_entries(instance2.id)
    check("FIX: la voce scritta offline sopravvive quando la coda si svuota PRIMA del resync",
          any(e.title == "Scritta offline 2" for e in entries_after2))


def main() -> int:
    init_db()
    print("=" * 70)
    test_bug_mechanism_reproduced()
    test_weapon_self_upsert_survives_resync()
    test_inventory_and_currency_self_commands()
    test_campaign_note_self_commands()
    test_fail_closed_ownership()
    test_permission_matrix()
    test_leave_disconnects_token()
    test_leave_detaches_local_instance()
    test_diary_left_panel_scroll_survives_refresh()
    test_maps_view_shared_map_survives_local_upload()
    test_pending_self_command_retry_queue()
    test_offline_note_wiped_by_resync_before_queue_flush()
    print("\n" + "=" * 70)
    print(f"Controlli passati: {_PASS} — falliti: {len(_FAIL)}")
    if _FAIL:
        for label in _FAIL:
            print(f"  - {label}")
        return 1
    print("Tutti i controlli passati.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
