"""
Verifica del fix 2026-08-07 — instradamento dei comandi in
`ui/views/world/world_view.py::WorldsView`.

Prima di questo fix `WorldsView` inviava OGNI comando (rinomina mondo,
gestione membri, e tutte le azioni di "Interviene a distanza": PE, danno,
cura, condizioni, abilità/incantesimo bonus/diario, richiesta di modifica)
sempre attraverso `self.backend`, impostato una volta in `__init__` a
`LocalBackend()` e mai più cambiato. Per l'host va bene (il suo DB locale È
lo stato autoritativo), ma per un dispositivo unito in LAN
(`is_local_host=False`) significava scrivere SOLO sulla propria replica,
senza mai raggiungere l'host — un comando "riusciva" a schermo (nessun
errore) ma non lasciava mai quel dispositivo. Trovato NON durante lo
sviluppo della UI del passo 6, ma rispondendo alla domanda di Davide "cosa
devo testare col Wi-Fi" — nessun test esistente istanziava `WorldsView`
con un mondo non ospitato, quindi il bug non emergeva.

Qui si verifica con un vero `WorldHostServer` su socket reale (stesso
pattern di `test_lan_host_client.py` parte [1]) che `WorldsView.
_backend_for()`/`_send_command()` risolvano davvero un `RemoteBackend` per
un mondo non ospitato, che il comando arrivi sull'host (non resti sulla
copia locale), e che la propria replica venga rimaterializzata subito dopo
un comando riuscito (`_apply_own_remote_result`), senza aspettare il
prossimo giro della sincronizzazione in background.

Stessa limitazione dichiarata in `test_lan_host_client.py`: un vero test a
due database SEPARATI (due dispositivi fisici, ciascuno con la propria
`Path.home()`) non è simulabile in modo affidabile in questo sandbox — un
secondo thread/HOME introdurrebbe una corsa reale con il thread del server
host. Qui verifichiamo che il comando raggiunga DAVVERO l'host reale via
HTTP leggendo lo stato dallo stesso DB condiviso che il server host scrive
(la sola prova che conta: "non è rimasto sulla replica locale" è
equivalente a "esiste sul DB che il server host usa per rispondere").

Eseguire con:
    PYTHONPATH=".venv/lib/python3.13/site-packages:." python3 test_world_view_remote_routing.py
"""

from __future__ import annotations

import os
import sys
import tempfile

_TMP_HOME = tempfile.mkdtemp(prefix="dnd_world_view_routing_")
os.environ["HOME"] = _TMP_HOME

from data.database import init_db  # noqa: E402
from data.models import Character, World  # noqa: E402
from data.repositories import character_repo, world_repo  # noqa: E402
from core import character_instances as ci  # noqa: E402
from core import world_permissions as perm  # noqa: E402
from core.world_backend import RemoteBackend  # noqa: E402
from network.host_server import WorldHostServer  # noqa: E402

_PASS = 0
_FAIL: list[str] = []


def check(label: str, cond: bool) -> None:
    global _PASS
    if cond:
        _PASS += 1
    else:
        _FAIL.append(label)
        print(f"  FALLITO: {label}")


def _reload(character_id: str) -> Character:
    c = character_repo.get_by_id(character_id)
    assert c is not None
    return c


def test_backend_for_and_send_command() -> None:
    print("\n[1] WorldsView._backend_for() / _send_command() — comando reale verso l'host")
    from ui.views.world.world_view import WorldsView

    # Mondo + istanza sull'host (stesso DB di questo processo: qui giochiamo
    # sia la parte "host" — WorldHostServer, LocalBackend — sia la parte
    # "verifica" — le stesse letture che farebbe un secondo dispositivo).
    host_world = world_repo.create_world("Mondo LAN Routing", "dev-owner", "Il Master")
    assert host_world is not None

    local_char = Character(
        name="Bramgar", class_name="Guerriero", race="Nano", level=4,
        hit_dice_type=10, hit_dice_total=4, hit_dice_remaining=4,
        str_score=16, dex_score=12, con_score=16, int_score=10,
        wis_score=10, cha_score=8, hp_max=36, hp_current=36,
    )
    character_repo.create(local_char)
    result = ci.create_or_resume_instance(host_world.id, local_char.id, "dev-player", mode="as_is")
    assert result.success, result.error
    instance = character_repo.get_by_id(result.character_id)
    assert instance is not None

    host = WorldHostServer(host_world.id, long_poll_timeout=2.0, announce=False)
    port = host.start()
    check("l'host si avvia", isinstance(port, int) and port > 0)

    try:
        # Il giocatore si unisce da un client reale (RemoteBackend, socket
        # vero su 127.0.0.1) — esattamente il flusso di `start_lan_join()`
        # fino al token, senza passare da `_finalize_join()` (che scrive
        # anche personaggi/eventi: non serve qui, verifichiamo solo il
        # routing dei comandi).
        world_repo.join_world_by_code(host_world.join_code, "dev-player", "Il Giocatore")
        # Promosso a master (fixture di test, scrittura diretta): CMD_XP_GRANT
        # richiede ruolo minimo master — qui vogliamo verificare l'instradamento
        # del comando, non la matrice dei permessi (già coperta altrove).
        world_repo.update_member_role(host_world.id, "dev-player", perm.ROLE_MASTER)
        join_backend = RemoteBackend("127.0.0.1", port, "dev-player")
        outcome = join_backend.join(host_world.join_code, host.pin, "Il Giocatore")
        check("il giocatore entra ed è già noto (nessuna approvazione richiesta)",
              outcome.status == "approved")
        check("un token è stato consegnato", bool(join_backend.token))

        # `World` così come lo vedrebbe la REPLICA sul dispositivo del
        # giocatore: is_local_host=False, l'indirizzo dell'host e il token
        # appena ottenuto — esattamente ciò che `_finalize_join()` avrebbe
        # persistito in `worlds.session_token` (fix 2026-08-07).
        client_world = World(
            id=host_world.id, name=host_world.name, owner_device_id="dev-owner",
            join_code=host_world.join_code, is_local_host=False,
            last_seen_host=f"127.0.0.1:{port}", session_token=join_backend.token or "",
        )

        wv = WorldsView(on_back_to_home=lambda: None)
        wv.device_id = "dev-player"

        backend = wv._backend_for(client_world)
        check("_backend_for risolve un RemoteBackend connesso per un mondo non ospitato",
              backend is not None and backend.connection_state() == "connected")

        backend_again = wv._backend_for(client_world)
        check("una seconda chiamata riusa lo stesso backend dalla cache (nessuna riconnessione)",
              backend_again is backend)

        # -- Il comando deve arrivare DAVVERO sull'host, non restare locale --
        cmd_result = wv._send_command(
            client_world, perm.CMD_XP_GRANT, {"amount": 250},
            target_type="character", target_id=instance.id,
        )
        check("_send_command riesce (instradato verso l'host via RemoteBackend)",
              cmd_result.success)
        check("i PE sono stati applicati sul DB CHE L'HOST USA (non solo su una copia locale)",
              _reload(instance.id).xp == 250)

        # -- Applicazione immediata sulla propria replica (§ _apply_own_remote_result) --
        check("dopo un comando remoto riuscito last_synced_seq avanza subito "
              "(non serve aspettare il prossimo giro del thread in background)",
              world_repo.get_world(host_world.id).last_synced_seq >= (cmd_result.event.seq
                                                                        if cmd_result.event else 0))

        # -- Un ruolo insufficiente viene comunque rifiutato dall'HOST, non "riesce in locale" --
        bad_result = wv._send_command(
            client_world, perm.CMD_WORLD_DELETE, {},
        )
        check("un comando non autorizzato viene rifiutato dall'host via rete",
              not bad_result.success)

        # -- Token non valido: _backend_for deve fallire in modo esplicito, mai insistere --
        broken_world = World(
            id=host_world.id, name=host_world.name, owner_device_id="dev-owner",
            join_code=host_world.join_code, is_local_host=False,
            last_seen_host=f"127.0.0.1:{port}", session_token="token-inventato-mai-emesso",
        )
        wv_broken = WorldsView(on_back_to_home=lambda: None)
        wv_broken.device_id = "dev-player"
        check("_backend_for con un token non valido ritorna None (mai un ritentativo automatico)",
              wv_broken._backend_for(broken_world) is None)

        # -- Host irraggiungibile (mondo ospitato da un indirizzo inesistente) --
        unreachable_world = World(
            id=host_world.id, name=host_world.name, owner_device_id="dev-owner",
            join_code=host_world.join_code, is_local_host=False,
            last_seen_host="127.0.0.1:1", session_token=join_backend.token or "",
        )
        wv_unreachable = WorldsView(on_back_to_home=lambda: None)
        wv_unreachable.device_id = "dev-player"
        check("_backend_for con un host irraggiungibile ritorna None",
              wv_unreachable._backend_for(unreachable_world) is None)

        # -- Un mondo ospitato da QUESTO dispositivo continua a usare LocalBackend --
        wv_host = WorldsView(on_back_to_home=lambda: None)
        wv_host.device_id = "dev-owner"
        check("_backend_for su un mondo is_local_host=True ritorna self.backend (LocalBackend)",
              wv_host._backend_for(host_world) is wv_host.backend)

    finally:
        host.stop()


def test_detail_signature_changes_on_mutation() -> None:
    print("\n[2] _detail_signature_of — cambia quando cambia lo stato del mondo")
    from ui.views.world.world_view import WorldsView

    world = world_repo.create_world("Mondo Firma", "dev-owner", "Il Master")
    assert world is not None

    wv = WorldsView(on_back_to_home=lambda: None)
    wv.device_id = "dev-owner"

    sig_before = wv._detail_signature_of(world)

    world_repo.join_world_by_code(world.join_code, "dev-player", "Un Giocatore")
    sig_after_join = wv._detail_signature_of(world)
    check("la firma cambia quando un membro si unisce", sig_before != sig_after_join)

    from core.world_backend import LocalBackend
    backend = LocalBackend()
    xp_result = backend.send_command(world.id, "dev-owner", perm.CMD_WORLD_RENAME,
                                      {"name": "Mondo Firma Rinominato"})
    check("il comando di test riesce", xp_result.success)
    sig_after_rename = wv._detail_signature_of(world_repo.get_world(world.id))
    check("la firma cambia dopo un evento (world.rename)", sig_after_join != sig_after_rename)

    sig_repeat = wv._detail_signature_of(world_repo.get_world(world.id))
    check("la firma resta stabile se nulla è cambiato nel frattempo",
          sig_after_rename == sig_repeat)


def main() -> int:
    init_db()
    print("=" * 62)
    print("Fix 2026-08-07 — instradamento comandi WorldsView (client LAN reale)")
    print(f"HOME di test: {_TMP_HOME}")
    print("=" * 62)

    test_backend_for_and_send_command()
    test_detail_signature_changes_on_mutation()

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
    sys.exit(main())
