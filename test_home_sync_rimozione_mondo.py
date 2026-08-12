"""
Verifica del fix 2026-08-12 — sincronizzazione della Home del giocatore con
la rimozione di un personaggio dal mondo (richiesta esplicita di Davide,
subito dopo aver visto il pulsante "Rimuovi dal mondo" lato master): "come
tutta l'app deve essere sincronizzata, anche l'app del giocatore ospitato,
con la scomparsa dal mondo nella sua schermata Home, senza toccare
ovviamente il personaggio in locale" — principio generale: le app collegate
mostrano gli stessi dati condivisi.

Prima di questo fix, `HomeView` non aveva ALCUNA sincronizzazione con un
host remoto: il polling esistente (`_start_polling`/`_poll_loop`) è solo
per più schede web sullo stesso DB locale, mai per la rete LAN. Un
giocatore seduto sulla propria Home non avrebbe mai saputo di essere stato
rimosso finché non apriva "Sezione Mondi" (che ha il proprio ciclo di
sync) o non premeva manualmente "Aggiorna il mio foglio".

Due parti:

[1] `HomeView._my_remote_world_ids()` — trova i mondi remoti (non ospitati
    da questo dispositivo) in cui possiede almeno un'istanza, esclude i
    mondi ospitati (il proprio DB è già lo stato autoritativo, sincronizzarli
    non avrebbe alcun effetto — stesso principio di `WorldsView.
    _start_detail_sync`) e i personaggi locali/di altri dispositivi.

[2] Round trip reale (host + socket veri, stesso pattern di `test_world_
    view_remote_routing.py`): il master rimuove un personaggio dal mondo
    sull'host, la Home del GIOCATORE (dispositivo diverso, non ospita)
    applica la sincronizzazione in background esattamente come farebbe
    `_start_world_sync` (stessa `world_sync.resolve_backend_for_world` +
    `sync_replica` che il ciclo richiama ad ogni giro — testate qui senza
    aspettare un vero giro del thread, stesso principio già in uso per
    `WorldsView._detail_signature_of()` in `test_ingresso_lan_
    sincronizzazione.py`) e la ritrova nella sezione "Rimossi dai mondi",
    non più in quella del mondo.

Eseguire con:
    PYTHONPATH=".venv/lib/python3.13/site-packages:." python3 test_home_sync_rimozione_mondo.py
"""

from __future__ import annotations

import os
import sys
import tempfile

_TMP_HOME = tempfile.mkdtemp(prefix="dnd_home_sync_rimozione_")
os.environ["HOME"] = _TMP_HOME

from data.database import init_db  # noqa: E402
from data.models import Character, World  # noqa: E402
from data.repositories import character_repo, character_export, world_repo  # noqa: E402
from core import world_backend  # noqa: E402
from core import world_permissions as perm  # noqa: E402
from core.world_backend import LocalBackend, RemoteBackend  # noqa: E402
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


def _send(backend: LocalBackend, *args, **kwargs):
    world_backend.reset_host_cooldowns_for_tests()
    return backend.send_command(*args, **kwargs)


def _make_character(name: str) -> Character:
    c = Character(
        name=name, class_name="Guerriero", race="Umano", level=1,
        hit_dice_type=10, hit_dice_total=1, hit_dice_remaining=1,
        str_score=10, dex_score=10, con_score=10, int_score=10,
        wis_score=10, cha_score=10, hp_max=10, hp_current=10,
    )
    character_repo.create(c)
    return c


# ---------------------------------------------------------------------------
# [1] _my_remote_world_ids
# ---------------------------------------------------------------------------

def test_my_remote_world_ids() -> None:
    print("\n[1] HomeView._my_remote_world_ids — solo mondi remoti con un'istanza propria")
    from ui.views.home_view import HomeView

    hosted = world_repo.create_world("Mondo Ospitato", "dev-me", "Io")
    # `create_world()` crea SEMPRE un mondo con `is_local_host=True` (è
    # l'unica funzione che può impostarlo, §11.5) — per simulare un mondo
    # REMOTO in questo stesso DB di test si passa da `save_replica_world()`,
    # che scrive sempre `is_local_host=False` (stessa riga che scriverebbe
    # una replica LAN reale dopo `_finalize_join()`).
    remote = world_repo.create_world("Mondo Remoto", "dev-altro-owner", "Un Altro")
    world_repo.save_replica_world(remote)
    remote = world_repo.get_world(remote.id)
    assert remote is not None and not remote.is_local_host

    mine_local = _make_character("Locale")
    mine_in_hosted = _make_character("Nel mio mondo ospitato")
    mine_in_hosted.world_id = hosted.id
    mine_in_hosted.owner_device_id = "dev-me"
    character_repo.update(mine_in_hosted)
    mine_in_remote = _make_character("In un mondo remoto")
    mine_in_remote.world_id = remote.id
    mine_in_remote.owner_device_id = "dev-me"
    character_repo.update(mine_in_remote)
    other_device_in_remote = _make_character("Di un altro giocatore")
    other_device_in_remote.world_id = remote.id
    other_device_in_remote.owner_device_id = "dev-un-altro-giocatore"
    character_repo.update(other_device_in_remote)

    home = HomeView(on_select=lambda i: None, on_create_wizard=lambda: None,
                    on_create_manual=lambda: None)
    home.device_id = "dev-me"

    ids = home._my_remote_world_ids()
    check("il mondo REMOTO con una mia istanza è incluso", remote.id in ids)
    check("il mondo che OSPITO non è incluso (il mio DB è già autoritativo)",
          hosted.id not in ids)
    check("nessun mondo in più/di meno", set(ids) == {remote.id})

    home_no_identity = HomeView(on_select=lambda i: None, on_create_wizard=lambda: None,
                                on_create_manual=lambda: None)
    check("senza device_id risolto, nessun mondo (mai bloccare/rompere la Home)",
          home_no_identity._my_remote_world_ids() == [])


# ---------------------------------------------------------------------------
# [2] Round trip reale — la Home riflette la rimozione decisa dal master
# ---------------------------------------------------------------------------

def test_round_trip_rimozione_riflessa_su_home() -> None:
    print("\n[2] Round trip — la Home del giocatore riflette la rimozione dal mondo")
    from ui.views.home_view import HomeView
    from core import world_sync

    world = world_repo.create_world("Mondo Round Trip", "dev-master-x", "Il Master")
    assert world is not None

    host = WorldHostServer(world.id, long_poll_timeout=2.0, announce=False)
    port = host.start()
    try:
        # -- Il giocatore entra ed registra la propria istanza sull'host --
        join_backend = RemoteBackend("127.0.0.1", port, "dev-player-x")
        outcome = join_backend.join(world.join_code, host.pin, "Il Giocatore")
        if outcome.status == "pending":
            host.approve(outcome.request_id)
            outcome = join_backend.poll_join_status(outcome.request_id)
        check("il giocatore entra nel mondo", outcome.status == "approved")

        player_character = _make_character("Personaggio Giocatore")
        player_character.world_id = world.id
        player_character.owner_device_id = "dev-player-x"
        character_repo.update(player_character)

        export_data = character_export.export_character(player_character.id)
        assert export_data is not None
        sync_result = join_backend.send_command(
            world.id, "dev-player-x", perm.CMD_CHARACTER_INSTANCE_SYNC,
            {"export": export_data}, target_type="character", target_id=player_character.id,
        )
        check("l'istanza è registrata sull'host", sync_result.success)

        # -- Il master rimuove il personaggio dal mondo (l'host è ancora
        # genuinamente `is_local_host=True` qui: nessun rischio di toccare
        # `world_members` prima di questo passo) --
        master_backend = LocalBackend()
        remove_result = _send(master_backend, world.id, "dev-master-x",
                               perm.CMD_CHARACTER_INSTANCE_REMOVE,
                               {}, target_type="character", target_id=player_character.id)
        check("la rimozione da parte del master riesce", remove_result.success)

        # -- La Home del GIOCATORE (non ospita) — NOTA sul limite di questo
        # sandbox (stesso già dichiarato in `test_lan_host_client.py`/
        # `test_mappe_condivise.py`): un solo DB condiviso tra "host" e
        # "giocatore". `world_repo.save_replica_world()` (il percorso reale
        # di `_finalize_join()`) fa un `INSERT OR REPLACE` sulla riga
        # `worlds`, che con `PRAGMA foreign_keys=ON` CASCADEREBBE su
        # `world_members` — cancellando la membership vera dell'host
        # condivisa con questo stesso DB. Qui si aggira SOLO per il test,
        # con un `UPDATE` diretto della singola colonna che conta per
        # `_my_remote_world_ids()`/`resolve_backend_for_world`
        # (`is_local_host`), senza toccare il resto della riga né i membri
        # — non replicabile così nell'app reale (lì i due DB sono sempre
        # fisicamente separati, `save_replica_world()` non tocca mai la
        # riga di un mondo che il dispositivo ospita davvero).
        from data.database import get_connection
        conn = get_connection()
        conn.execute("UPDATE worlds SET is_local_host=0, last_seen_host=?, "
                     "session_token=? WHERE id=?",
                     (f"127.0.0.1:{port}", join_backend.token or "", world.id))
        conn.commit()
        conn.close()

        home = HomeView(on_select=lambda i: None, on_create_wizard=lambda: None,
                        on_create_manual=lambda: None)
        home.device_id = "dev-player-x"

        remote_world_ids = home._my_remote_world_ids()
        check("_my_remote_world_ids trova il mondo remoto", world.id in remote_world_ids)

        client_world = world_repo.get_world(world.id)
        assert client_world is not None

        # -- Sincronizzazione in background — stessa `resolve_backend_for_
        # world`/`sync_replica` che `_start_world_sync()` richiama ad ogni
        # giro del ciclo, invocate qui direttamente invece di aspettare un
        # vero giro del thread (stesso principio già in uso per
        # `WorldsView._detail_signature_of()` in `test_ingresso_lan_
        # sincronizzazione.py`: si verifica la logica di dominio, non i
        # tempi del thread).
        backend = world_sync.resolve_backend_for_world(
            client_world, home.device_id, home.backend, home._remote_backends,
        )
        check("il backend per il mondo remoto si risolve", backend is not None)
        assert backend is not None
        world_sync.sync_replica(backend, world.id)

        # `refresh()` rilegge il DB e ricostruisce le sezioni — esattamente
        # ciò che il ciclo in background chiama dopo `apply_fn`.
        home.refresh(force=True)

        after_sync = character_repo.get_by_id(player_character.id)
        check("dopo la sincronizzazione, la replica locale del giocatore è archiviata",
              after_sync is not None and after_sync.world_instance_archived)

        all_chars = character_repo.get_all()
        locals_, by_world, removed_from_world = home._partition_characters(all_chars)
        check("il personaggio NON è più nel gruppo del mondo sulla Home del giocatore",
              not any(c.id == player_character.id for c in by_world.get(world.id, [])))
        check("il personaggio compare nella sezione 'Rimossi dai mondi' sulla Home",
              any(c.id == player_character.id for c in removed_from_world))
        check("il personaggio NON diventa locale (world_id resta quello del mondo)",
              not any(c.id == player_character.id for c in locals_))

        # I dati del personaggio (nome, ecc.) non sono stati toccati.
        check("i dati del personaggio restano intatti (nome invariato)",
              after_sync is not None and after_sync.name == "Personaggio Giocatore")
    finally:
        host.stop()


def main() -> int:
    print("=" * 62)
    print("Home sync — rimozione di un personaggio dal mondo riflessa lato giocatore")
    print(f"HOME di test: {_TMP_HOME}")
    print("=" * 62)
    init_db()
    test_my_remote_world_ids()
    test_round_trip_rimozione_riflessa_su_home()
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
