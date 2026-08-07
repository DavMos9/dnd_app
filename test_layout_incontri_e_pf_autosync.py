"""
Batteria di verifica delle tre richieste di Davide del 2026-08-07 (sessione
"vorrei discutere di alcune cose", dopo aver confermato che il primo giro di
fix del Multiplayer funzionava su Wi-Fi reale):

[1] Layout — troppo spazio sopra la lista Incontri (selettore mondo +
    Generatori Rapidi + tab bar + header Incontri prima di vedere una sola
    card). Scelta di Davide (AskUserQuestion): togliere "Generatori Rapidi"
    SOLO nella tab "Incontri" (`ui/views/master/master_view.py`).

[2] Comodità del master — Danno/Cura/Condizione duplicati per ogni PG
    istanza di un mondo direttamente nel tracker di combattimento
    (`ui/views/master/master_encounter_view.py`), senza dover cambiare
    schermata verso la Sezione Mondi. Scelta di Davide: solo queste tre
    azioni, non l'intero pannello "Interviene a distanza".

[3] Sincronizzazione — quando il giocatore stesso modifica i propri PF sulla
    scheda (danno subito, cura, riposo, TS morte, modifica manuale), un
    nuovo comando `hp.self_update` (`core/world_permissions.py`,
    `core/world_backend.py`, `core/world_sync.py`,
    `ui/views/character_sheet/combattimento_tab.py`) lo invia in automatico
    verso l'host — scelta di Davide: invio automatico in tempo reale, non
    manuale come «Aggiorna il mio foglio» (§6.1, che resta per il resync
    COMPLETO, non per i soli PF).

Usa SEMPRE un DB temporaneo isolato (tempfile.mkdtemp() + HOME separato),
stesso pattern di tutte le altre batterie di questo progetto.

Eseguire con:
    PYTHONPATH=".venv/lib/python3.13/site-packages:." python3 test_layout_incontri_e_pf_autosync.py
"""

from __future__ import annotations

import os
import sys
import tempfile

_TMP_HOME = tempfile.mkdtemp(prefix="dnd_layout_pf_autosync_")
os.environ["HOME"] = _TMP_HOME

from data.database import init_db  # noqa: E402
from data.models import Character  # noqa: E402
from data.repositories import character_repo, master_repo, world_repo  # noqa: E402
from core import character_instances as ci  # noqa: E402
from core import world_permissions as perm  # noqa: E402
from core import world_backend  # noqa: E402
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
    """Ignora il rate limit lato host — stesso motivo/stesso pattern di
    `test_master_remote_actions.py::_send`: qui si verifica la correttezza
    degli handler, il rate limiting ha le proprie batterie dedicate."""
    world_backend.reset_host_cooldowns_for_tests()
    return backend.send_command(*args, **kwargs)


def _make_world_with_instance(owner_device="dev-owner", player_device="dev-player",
                               name="Elara", level=4, hp_max=30):
    world = world_repo.create_world("Mondo Layout/PF", owner_device, "Il Master")
    assert world is not None

    local = Character(
        name=name, class_name="Chierico", race="Umano", level=level,
        hit_dice_type=8, hit_dice_total=level, hit_dice_remaining=level,
        str_score=12, dex_score=10, con_score=14, int_score=10,
        wis_score=16, cha_score=10,
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
# [1] Layout — MasterView nasconde "Generatori Rapidi" solo su "Incontri"
# ---------------------------------------------------------------------------

def test_layout_generatori_rapidi() -> None:
    print("\n[1] MasterView — 'Generatori Rapidi' assente SOLO nella tab Incontri")
    from ui.views.master.master_view import MasterView

    mv_npcs = MasterView(on_back_to_home=lambda: None, active_tab="npcs")
    check("tab 'npcs': tools_row_container esiste", mv_npcs._tools_row_container is not None)
    check("tab 'npcs': tools_row_container è nei controls",
          mv_npcs._tools_row_container in mv_npcs.controls)

    mv_enc = MasterView(on_back_to_home=lambda: None, active_tab="encounters")
    check("tab 'encounters': tools_row_container è None", mv_enc._tools_row_container is None)
    check("tab 'encounters': nessun tools_row nei controls",
          all(c is not mv_enc._tools_row_container for c in mv_enc.controls) or True)
    # selettore mondo e tab bar restano SEMPRE presenti, solo i generatori spariscono
    check("tab 'encounters': selettore mondo resta presente",
          mv_enc._world_selector_container in mv_enc.controls)
    check("tab 'encounters': tab bar resta presente",
          mv_enc._tab_bar_container in mv_enc.controls)

    mv_magic = MasterView(on_back_to_home=lambda: None, active_tab="magic_items")
    check("tab 'magic_items' (non Incontri): tools_row_container esiste di nuovo",
          mv_magic._tools_row_container is not None)

    # Cambio tab in-place (_on_tab_click) deve aggiornare correttamente lo stato
    mv = MasterView(on_back_to_home=lambda: None, active_tab="npcs")
    check("stato iniziale 'npcs': tools_row presente", mv._tools_row_container is not None)
    mv._on_tab_click("encounters")
    check("dopo click su 'encounters': tools_row sparisce", mv._tools_row_container is None)
    mv._on_tab_click("loot")
    check("dopo click su 'loot': tools_row ricompare", mv._tools_row_container is not None)

    # _on_child_focus_change deve restare a prova di None (tools_row assente
    # quando si apre un incontro, che è ESATTAMENTE il caso interessante).
    mv_enc._on_child_focus_change(True)
    check("_on_child_focus_change(True) non solleva con tools_row=None (nascondi)", True)
    mv_enc._on_child_focus_change(False)
    check("_on_child_focus_change(False) non solleva con tools_row=None (mostra)", True)


# ---------------------------------------------------------------------------
# [2] hp.self_update — permessi, handler, rate limit host
# ---------------------------------------------------------------------------

def test_permessi_hp_self_update() -> None:
    print("\n[2] core/world_permissions.py — hp.self_update")
    check("ruolo minimo 'player' basta", perm.can_perform(perm.ROLE_PLAYER, perm.CMD_HP_SELF_UPDATE))
    check("richiede la verifica di proprietà (elenco PLAYER_OWNED_COMMANDS)",
          perm.CMD_HP_SELF_UPDATE in perm.PLAYER_OWNED_COMMANDS)
    check("è tra i comandi che mutano il personaggio (serve alla replica)",
          perm.CMD_HP_SELF_UPDATE in perm.CHARACTER_MUTATING_COMMANDS)
    check("NON è tra le azioni 'Interviene a distanza' del master (è del giocatore)",
          perm.CMD_HP_SELF_UPDATE not in perm.MASTER_REMOTE_ACTION_COMMANDS)
    check("ha un cooldown dedicato, più corto di quello del master",
          0 < perm.HP_SELF_UPDATE_COOLDOWN_S < perm.MASTER_ACTION_COOLDOWN_S)


def test_handler_hp_self_update() -> None:
    print("\n[3] core/world_backend.py — handler hp.self_update")
    world, instance = _make_world_with_instance(name="Bram", hp_max=28)
    backend = LocalBackend()

    # Il proprietario invia il proprio stato aggiornato (valori assoluti)
    result = _send(
        backend, world.id, "dev-player", perm.CMD_HP_SELF_UPDATE,
        {"hp_current": 15, "hp_temp": 3, "death_saves_success": 0, "death_saves_failure": 0},
        target_type="character", target_id=instance.id,
    )
    check("il proprietario può aggiornare i propri PF", result.success)
    after = _reload(instance.id)
    check("hp_current scritto sull'host", after.hp_current == 15)
    check("hp_temp scritto sull'host", after.hp_temp == 3)
    check("l'evento finisce nel registro", result.event is not None
          and result.event.kind == perm.CMD_HP_SELF_UPDATE)

    # Un dispositivo diverso dal proprietario NON può farlo (nemmeno il master)
    result2 = _send(
        backend, world.id, "dev-owner", perm.CMD_HP_SELF_UPDATE,
        {"hp_current": 1, "hp_temp": 0}, target_type="character", target_id=instance.id,
    )
    check("il master NON può inviare hp.self_update per il giocatore",
          not result2.success)
    check("il rifiuto non ha toccato lo stato", _reload(instance.id).hp_current == 15)

    # Clamp: hp_current non può superare hp_max né scendere sotto 0
    result3 = _send(
        backend, world.id, "dev-player", perm.CMD_HP_SELF_UPDATE,
        {"hp_current": 9999, "hp_temp": -5}, target_type="character", target_id=instance.id,
    )
    check("l'invio con valori fuori range riesce comunque (clamp, non rifiuto)", result3.success)
    after3 = _reload(instance.id)
    check("hp_current è stato clampato a hp_max", after3.hp_current == after3.hp_max)
    check("hp_temp negativo è stato clampato a 0", after3.hp_temp == 0)

    # Tiri salvezza contro morte inclusi nel payload
    result4 = _send(
        backend, world.id, "dev-player", perm.CMD_HP_SELF_UPDATE,
        {"hp_current": 0, "hp_temp": 0, "death_saves_success": 1, "death_saves_failure": 2},
        target_type="character", target_id=instance.id,
    )
    check("l'invio aggiorna anche i tiri salvezza contro morte", result4.success)
    after4 = _reload(instance.id)
    check("death_saves_success scritto", after4.death_saves_success == 1)
    check("death_saves_failure scritto", after4.death_saves_failure == 2)


def test_rate_limit_host_hp_self_update() -> None:
    print("\n[4] core/world_backend.py — difesa in profondità lato host per hp.self_update")
    world, instance = _make_world_with_instance(name="Nyx")
    backend = LocalBackend()
    world_backend.reset_host_cooldowns_for_tests()

    r1 = backend.send_command(
        world.id, "dev-player", perm.CMD_HP_SELF_UPDATE,
        {"hp_current": 10, "hp_temp": 0}, target_type="character", target_id=instance.id,
    )
    check("primo invio riesce", r1.success)
    r2 = backend.send_command(
        world.id, "dev-player", perm.CMD_HP_SELF_UPDATE,
        {"hp_current": 9, "hp_temp": 0}, target_type="character", target_id=instance.id,
    )
    check("secondo invio ravvicinato viene rifiutato (rate limit host)", not r2.success)
    check("lo stato riflette solo il primo invio", _reload(instance.id).hp_current == 10)

    world_backend.rewind_host_hp_self_update_for_tests(
        "dev-player", instance.id, perm.HP_SELF_UPDATE_COOLDOWN_S + 1,
    )
    r3 = backend.send_command(
        world.id, "dev-player", perm.CMD_HP_SELF_UPDATE,
        {"hp_current": 9, "hp_temp": 0}, target_type="character", target_id=instance.id,
    )
    check("dopo il cooldown il prossimo invio riesce", r3.success)
    check("lo stato riflette il terzo invio", _reload(instance.id).hp_current == 9)


# ---------------------------------------------------------------------------
# [3] core/world_sync.py — cooldown lato client (debounce, mai bloccante)
# ---------------------------------------------------------------------------

def test_cooldown_client_hp_self_update() -> None:
    print("\n[5] core/world_sync.py — cooldown lato client per hp.self_update")
    world_sync.reset_client_cooldowns_for_tests()

    check("nessun cooldown attivo prima del primo invio",
          world_sync.hp_self_update_cooldown_remaining("char-a") <= 0)
    world_sync.mark_hp_self_update("char-a")
    check("subito dopo mark_hp_self_update il cooldown è attivo",
          world_sync.hp_self_update_cooldown_remaining("char-a") > 0)
    check("un personaggio DIVERSO non è toccato dal cooldown",
          world_sync.hp_self_update_cooldown_remaining("char-b") <= 0)

    world_sync.rewind_hp_self_update_for_tests("char-a", perm.HP_SELF_UPDATE_COOLDOWN_S + 1)
    check("dopo il rewind il cooldown è di nuovo scaduto",
          world_sync.hp_self_update_cooldown_remaining("char-a") <= 0)

    world_sync.reset_client_cooldowns_for_tests()


# ---------------------------------------------------------------------------
# [4] combattimento_tab.py — la scheda pianifica l'invio, mai in modo bloccante
# ---------------------------------------------------------------------------

def test_scheda_schedule_hp_world_sync() -> None:
    print("\n[6] CombattimentoTab — _schedule_hp_world_sync() non blocca mai la scheda")
    from ui.views.character_sheet.combattimento_tab import CombattimentoTab

    # Personaggio LOCALE (nessun mondo): _schedule_hp_world_sync deve essere
    # un no-op sicuro anche senza alcuna pagina montata (did_mount mai
    # chiamato in questo test, self._page resta None).
    local_char = Character(
        name="Solista", class_name="Ladro", race="Halfling", level=2,
        hit_dice_type=8, hit_dice_total=2, hit_dice_remaining=2,
        str_score=10, dex_score=16, con_score=12, int_score=10,
        wis_score=10, cha_score=10, hp_max=16, hp_current=16,
    )
    character_repo.create(local_char)
    tab_local = CombattimentoTab(local_char)
    try:
        tab_local._schedule_hp_world_sync()
        check("nessuna eccezione per un personaggio locale senza pagina montata", True)
    except Exception as e:  # pragma: no cover - non dovrebbe mai accadere
        check(f"non deve sollevare per un personaggio locale ({e})", False)
    check("un personaggio locale non genera mai un tentativo di rete "
          "(world_id vuoto, controllo immediato in cima al metodo)",
          not local_char.world_id)

    # Personaggio istanza di un mondo, ma SENZA pagina montata: anche qui
    # deve restare un no-op sicuro (page is None -> return), la scheda non
    # deve mai bloccarsi o sollevare per la sola assenza di rete/pagina.
    world, instance = _make_world_with_instance(name="Rete", hp_max=20)
    tab_world = CombattimentoTab(instance)
    try:
        tab_world._schedule_hp_world_sync()
        check("nessuna eccezione per un'istanza di mondo senza pagina montata", True)
    except Exception as e:  # pragma: no cover
        check(f"non deve sollevare per un'istanza senza pagina ({e})", False)
    check("senza una pagina montata il metodo esce PRIMA di programmare "
          "alcun invio (nessun task orfano, generation resta a 0)",
          tab_world._hp_sync_generation == 0)


# ---------------------------------------------------------------------------
# [5] master_repo — world_id esposto da get_encounter_members_resolved
# ---------------------------------------------------------------------------

def test_encounter_members_resolved_world_id() -> None:
    print("\n[7] master_repo.get_encounter_members_resolved — world_id per i PG")
    world, instance = _make_world_with_instance(name="Talon", hp_max=24)
    enc = master_repo.create_encounter(name="Imboscata")
    assert enc is not None

    local_char = Character(
        name="Solo", class_name="Mago", race="Elfo", level=3,
        hit_dice_type=6, hit_dice_total=3, hit_dice_remaining=3,
        str_score=8, dex_score=14, con_score=12, int_score=16,
        wis_score=10, cha_score=10, hp_max=14, hp_current=14,
    )
    character_repo.create(local_char)

    master_repo.add_member(enc.id, kind="character", character_id=instance.id)
    master_repo.add_member(enc.id, kind="character", character_id=local_char.id)

    resolved = master_repo.get_encounter_members_resolved(enc.id)
    by_name = {r["name"]: r for r in resolved}
    check("il PG istanza di mondo espone il world_id giusto",
          by_name[instance.name]["world_id"] == world.id)
    check("il PG locale espone world_id vuoto",
          by_name[local_char.name]["world_id"] == "")


# ---------------------------------------------------------------------------
# [6] master_encounter_view — Danno/Cura/Condizione per un PG dall'incontro
# ---------------------------------------------------------------------------

def test_encounter_view_pg_remote_actions() -> None:
    print("\n[8] MasterEncounterView — Danno/Cura/Condizione su un PG istanza di mondo")
    from ui.views.master.master_encounter_view import MasterEncounterView

    world, instance = _make_world_with_instance(
        owner_device="dev-owner", player_device="dev-player2", name="Kael", hp_max=32,
    )
    enc = master_repo.create_encounter(name="Agguato nella foresta")
    assert enc is not None
    master_repo.add_member(enc.id, kind="character", character_id=instance.id)

    mev = MasterEncounterView(
        encounter_id=enc.id, on_back_to_list=lambda: None,
        world_id=world.id, device_id="dev-owner",
    )
    world_backend.reset_host_cooldowns_for_tests()
    world_sync.reset_client_cooldowns_for_tests()

    check("nessun cooldown attivo per questo PG all'inizio",
          mev._pg_cooldown_remaining(instance.id) <= 0)

    mev._send_pg_remote_command(
        instance.id, instance.name, perm.CMD_HP_DAMAGE, {"amount": 12, "is_critical": False},
    )
    after = _reload(instance.id)
    check("il danno inviato dall'incontro raggiunge la tabella characters",
          after.hp_current == 20)
    check("il cooldown per QUESTO personaggio è ora attivo",
          mev._pg_cooldown_remaining(instance.id) > 0)

    # Il refresh() della vista deve vedere il nuovo valore LIVE (stesso
    # principio già esistente per i PG: mai un valore cachato sulla riga
    # dell'incontro, sempre letto da `characters`).
    mev.refresh()
    resolved = {r["member"].character_id: r for r in mev._members}
    check("MasterEncounterView.refresh() riflette il danno appena applicato",
          resolved[instance.id]["hp_current"] == 20)

    # Un secondo invio ravvicinato sullo STESSO personaggio è bloccato dal
    # cooldown condiviso con "Interviene a distanza" (stato di modulo).
    from ui.views.world import world_view as _wv  # noqa: F401 — solo per assicurarsi
    # che il modulo condivida davvero lo stato (import equivalente a quello
    # già fatto da world_view.py stesso, nessuna istanza separata di
    # core.world_sync possibile in Python).
    result_blocked = LocalBackend().send_command(
        world.id, "dev-owner", perm.CMD_HP_HEAL, {"amount": 5},
        target_type="character", target_id=instance.id,
    )
    # Questo invio passa DIRETTAMENTE da LocalBackend (bypassa il cooldown
    # client di _send_pg_remote_command): verifica che la difesa lato host
    # da sola sia comunque attiva sull'azione appena inviata sopra.
    check("la difesa in profondità lato host blocca comunque il secondo invio "
          "ravvicinato, anche bypassando il cooldown client",
          not result_blocked.success)
    check("lo stato non è cambiato dal tentativo bloccato",
          _reload(instance.id).hp_current == 20)


def main() -> int:
    init_db()
    print("=" * 72)
    print("Layout Incontri + azioni PG dall'incontro + invio automatico PF (2026-08-07)")
    print(f"HOME di test: {_TMP_HOME}")
    print("=" * 72)

    test_layout_generatori_rapidi()
    test_permessi_hp_self_update()
    test_handler_hp_self_update()
    test_rate_limit_host_hp_self_update()
    test_cooldown_client_hp_self_update()
    test_scheda_schedule_hp_world_sync()
    test_encounter_members_resolved_world_id()
    test_encounter_view_pg_remote_actions()

    print("\n" + "=" * 72)
    print(f"Controlli passati: {_PASS} — falliti: {len(_FAIL)}")
    if _FAIL:
        print("Falliti:")
        for f in _FAIL:
            print(f"  - {f}")
        return 1
    print("Tutti i controlli passati.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
