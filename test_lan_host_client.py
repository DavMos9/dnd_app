"""
Batteria di verifica del passo 4 di dnd_app/docs/multiplayer_design.md —
"Host + client in LAN" (2026-08-05).

Tre parti, per uno scopo dichiarato in ciascuna:

[1] Protocollo di rete reale (`network/host_server.py` + `RemoteBackend`)
    su socket veri via 127.0.0.1: join (codice/PIN corretti ed errati,
    dispositivo noto vs nuovo, approvazione/rifiuto del master), comandi
    sulla rete, attesa lunga di /events (con tempi misurati), invalidazione
    del token su /leave, riconnessione con token. Un solo DB condiviso qui:
    è accettabile perché nessuna funzione di questa parte scrive nella
    tabella `worlds` del "client" (vedi parte 3 per il motivo).

[2] Applicazione degli eventi sulla replica (`core/world_sync.py` lato
    scrittura) in isolamento puro: nessun server vivo, nessun thread,
    eventi costruiti a mano. Verifica che `apply_event_to_replica`/
    `save_replica_*` scrivano le righe corrette.

[3] Orchestrazione dell'ingresso LAN (`start_lan_join`/`finish_pending_join`/
    `_finalize_join`) con un finto backend (nessuna rete, risposte pre-
    confezionate): verifica la logica di branching (versione protocollo,
    pending/approvato) e che uno snapshot venga tradotto correttamente in
    righe locali — senza duplicare la verifica di rete già fatta in [1].

**Perché non un vero test a due database separati**: `get_connection()`
risolve il percorso del DB da `Path.home()` ad ogni chiamata, letto da
processi/thread diversi (il server host gira nel proprio thread daemon).
Scambiare `HOME` a runtime per simulare "due dispositivi" nello stesso
processo introdurrebbe una corsa reale tra il thread del server e il thread
di test — un test così potrebbe sembrare passare senza provare nulla di
vero, il che è peggio di non scriverlo (vedi CLAUDE.md, "non inventare
informazioni"). Il comportamento reale a due dispositivi/DB separati è
esattamente ciò che il design doc (§15) dichiara verificabile solo da
Davide su hardware vero.

Eseguire con:
    PYTHONPATH=".venv/lib/python3.13/site-packages:." python3 test_lan_host_client.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import time

_TMP_HOME = tempfile.mkdtemp(prefix="dnd_lan_")
os.environ["HOME"] = _TMP_HOME

from data.database import init_db  # noqa: E402
from data.models import World, WorldEvent, WorldMember  # noqa: E402
from data.repositories import world_repo  # noqa: E402
from core.world_backend import RemoteBackend  # noqa: E402
from core import world_permissions as perm  # noqa: E402
from core import world_sync  # noqa: E402
from network import protocol  # noqa: E402
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


# ---------------------------------------------------------------------------
# [1] Protocollo di rete reale
# ---------------------------------------------------------------------------

def test_network_protocol() -> None:
    print("\n[1] Protocollo di rete reale — host + RemoteBackend su 127.0.0.1")

    world = world_repo.create_world("Mondo LAN", "dev-owner", "Il Master")
    assert world is not None

    host = WorldHostServer(world.id, long_poll_timeout=2.0)
    port = host.start()
    check("il server si avvia e riporta una porta valida", isinstance(port, int) and port > 0)
    check("is_running è True dopo start()", host.is_running)
    check("il PIN generato ha 6 cifre numeriche", len(host.pin) == 6 and host.pin.isdigit())

    try:
        # -- GET /world ----------------------------------------------------
        client = RemoteBackend("127.0.0.1", port, "dev-player-1")
        info = client.check_world()
        check("GET /world risponde", info is not None)
        assert info is not None
        check("GET /world riporta la versione di protocollo corretta",
              info.get("protocol_version") == protocol.PROTOCOL_VERSION)
        check("GET /world riporta accepting=True", info.get("accepting") is True)
        check("GET /world riporta il nome del mondo", info.get("name") == "Mondo LAN")
        client.world_id = info.get("world_id", "")

        bad_host = RemoteBackend("127.0.0.1", port + 999, "dev-x")
        check("check_world su una porta senza server ritorna None",
              bad_host.check_world() is None)

        # -- POST /join: credenziali errate ---------------------------------
        wrong_code = client.join("ZZZZZZ", host.pin, "Giocatore 1")
        check("join con codice mondo errato viene rifiutato", wrong_code.status == "error")

        wrong_pin = client.join(world.join_code, "000000", "Giocatore 1")
        check("join con PIN errato viene rifiutato", wrong_pin.status == "error")

        # -- POST /join: dispositivo NUOVO -> pending -----------------------
        outcome = client.join(world.join_code, host.pin, "Giocatore 1")
        check("join di un dispositivo nuovo torna 'pending'", outcome.status == "pending")
        check("connection_state riflette 'pending'", client.connection_state() == "pending")
        check("un dispositivo nuovo compare tra le richieste in sospeso",
              any(r.device_id == "dev-player-1" for r in host.list_pending()))

        status = client.poll_join_status(outcome.request_id)
        check("prima dell'approvazione lo stato resta 'pending'", status.status == "pending")

        approved = host.approve(outcome.request_id)
        check("host.approve() riesce", approved)
        check("un id di richiesta già approvato non è più tra le pending",
              not any(r.id == outcome.request_id for r in host.list_pending()))

        status = client.poll_join_status(outcome.request_id)
        check("dopo l'approvazione lo stato è 'approved'", status.status == "approved")
        check("il client ha ricevuto un token", bool(client.token))
        check("connection_state è 'connected'", client.connection_state() == "connected")
        check("il nuovo membro è ora un player nel mondo",
              world_repo.get_member(world.id, "dev-player-1").role == "player")

        # -- rifiuto di un secondo dispositivo nuovo -------------------------
        client_rejected = RemoteBackend("127.0.0.1", port, "dev-player-2")
        client_rejected.world_id = client.world_id
        outcome2 = client_rejected.join(world.join_code, host.pin, "Giocatore 2")
        check("secondo dispositivo nuovo -> anch'esso pending", outcome2.status == "pending")
        check("host.reject() riesce", host.reject(outcome2.request_id))
        status2 = client_rejected.poll_join_status(outcome2.request_id)
        check("dopo il rifiuto lo stato è 'rejected'", status2.status == "rejected")
        check("un dispositivo rifiutato NON diventa membro",
              world_repo.get_member(world.id, "dev-player-2") is None)

        # -- dispositivo GIA' noto (l'owner stesso) -> approvazione immediata
        owner_client = RemoteBackend("127.0.0.1", port, "dev-owner")
        owner_client.world_id = client.world_id
        owner_outcome = owner_client.join(world.join_code, host.pin, "Il Master")
        check("un dispositivo già membro rientra senza approvazione",
              owner_outcome.status == "approved")
        check("nessuna richiesta in sospeso creata per un membro già noto",
              not any(r.device_id == "dev-owner" for r in host.list_pending()))

        # -- POST /command: rifiutato per ruolo insufficiente ----------------
        result = client.send_command(world.id, "dev-player-1", perm.CMD_WORLD_RENAME,
                                     {"name": "Hackerato"})
        check("un player non autorizzato a rinominare riceve un rifiuto via rete",
              not result.success)
        check("il mondo NON è stato rinominato", world_repo.get_world(world.id).name == "Mondo LAN")

        # -- POST /command: riuscito (owner via rete) -------------------------
        result = owner_client.send_command(world.id, "dev-owner", perm.CMD_WORLD_RENAME,
                                           {"name": "Rinominato via LAN"})
        check("l'owner rinomina con successo via rete", result.success)
        check("l'evento di ritorno ha il kind giusto",
              result.event is not None and result.event.kind == perm.CMD_WORLD_RENAME)
        check("il mondo è stato rinominato sul DB dell'host",
              world_repo.get_world(world.id).name == "Rinominato via LAN")

        # -- GET /events: senza attesa (wait=0) ------------------------------
        events = client.fetch_events(world.id, since_seq=0)
        check("fetch_events ritorna almeno gli eventi finora scritti", len(events) >= 3)
        check("gli eventi arrivano in ordine di seq crescente",
              [e.seq for e in events] == sorted(e.seq for e in events))
        kinds = {e.kind for e in events}
        check("il giornale ricevuto via rete contiene la rinomina",
              perm.CMD_WORLD_RENAME in kinds)

        latest_seq = max(e.seq for e in events)
        events_since_latest = client.fetch_events(world.id, since_seq=latest_seq)
        check("fetch_events da seq già visto ritorna vuoto", events_since_latest == [])

        # -- GET /events: attesa lunga misurata --------------------------------
        t0 = time.monotonic()
        status_code, payload = host.handle_events(client.token, latest_seq, wait=0.6)
        elapsed = time.monotonic() - t0
        check("handle_events con token valido risponde 200", status_code == 200)
        check("senza eventi nuovi, l'attesa dura circa il tempo richiesto",
              0.5 <= elapsed <= 1.2)
        check("dopo il timeout la lista di eventi è vuota", payload.get("events") == [])

        # -- GET /snapshot ------------------------------------------------------
        snapshot = owner_client.get_snapshot()
        check("get_snapshot ritorna un dizionario", snapshot is not None)
        assert snapshot is not None
        check("lo snapshot contiene il mondo", snapshot.get("world", {}).get("id") == world.id)
        check("lo snapshot contiene tutti i membri attuali",
              {m["device_id"] for m in snapshot.get("members", [])}
              == {"dev-owner", "dev-player-1"})
        check("lo snapshot contiene l'intero giornale",
              len(snapshot.get("events", [])) >= 3)

        # -- token non valido -----------------------------------------------------
        ghost = RemoteBackend("127.0.0.1", port, "dev-fantasma")
        ghost.token = "token-inventato-non-emesso-da-nessuno"
        result = ghost.send_command(world.id, "dev-fantasma", perm.CMD_WORLD_RENAME, {})
        check("un token mai emesso viene rifiutato (401)", not result.success)
        check("connection_state torna 'disconnected' dopo un 401",
              ghost.connection_state() == "disconnected")

        # -- POST /leave invalida il token ------------------------------------------
        valid_token = client.token
        client.leave()
        check("dopo leave() il client non ha più un token", client.token is None)
        check("connection_state è 'disconnected' dopo leave()",
              client.connection_state() == "disconnected")
        check("il membro risulta disconnesso lato host",
              not world_repo.get_member(world.id, "dev-player-1").is_connected)

        stale = RemoteBackend("127.0.0.1", port, "dev-player-1")
        stale.token = valid_token
        result = stale.send_command(world.id, "dev-player-1", perm.CMD_WORLD_RENAME, {})
        check("un token invalidato da leave() non funziona più per un comando",
              not result.success)

        # -- reconnect_with_token --------------------------------------------------
        reconnected = owner_client
        fresh_backend = RemoteBackend("127.0.0.1", port, "dev-owner")
        check("reconnect_with_token con un token ancora valido riesce",
              fresh_backend.reconnect_with_token(reconnected.token))
        check("connection_state è 'connected' dopo una riconnessione riuscita",
              fresh_backend.connection_state() == "connected")

        broken_backend = RemoteBackend("127.0.0.1", port, "dev-owner")
        check("reconnect_with_token con un token a caso fallisce",
              not broken_backend.reconnect_with_token("token-a-caso-mai-emesso"))
        check("connection_state torna 'disconnected' dopo una riconnessione fallita",
              broken_backend.connection_state() == "disconnected")

        # -- rotta sconosciuta -> 404, non un crash del server -----------------
        status_code, _payload = client._request("GET", "/rotta-inesistente")
        check("una rotta GET sconosciuta risponde 404", status_code == 404)
        status_code, _payload = client._request("POST", "/rotta-inesistente")
        check("una rotta POST sconosciuta risponde 404", status_code == 404)

        # Catturato PRIMA di stop() (che azzera self.pin) — serve dopo per
        # verificare che il riavvio generi davvero un PIN diverso.
        old_pin = host.pin
    finally:
        host.stop()

    check("is_running è False dopo stop()", not host.is_running)
    check("stop() azzera il PIN in memoria", host.pin == "")

    # Riavvio: nuovo PIN, nessun token residuo dalla sessione precedente.
    port2 = host.start()
    try:
        check("il riavvio genera un nuovo PIN", host.pin != "" and host.pin != old_pin)
        stale2 = RemoteBackend("127.0.0.1", port2, "dev-owner")
        check("un token della sessione precedente non è più valido dopo il riavvio",
              not stale2.reconnect_with_token(valid_token))
    finally:
        host.stop()


# ---------------------------------------------------------------------------
# [2] Applicazione degli eventi sulla replica — isolata, nessun server vivo
# ---------------------------------------------------------------------------

def test_apply_event_to_replica() -> None:
    print("\n[2] core.world_sync — applicazione eventi sulla replica (isolata)")

    # Un mondo "replica": stessa forma di riga di una copia locale creata da
    # save_replica_world, ma qui inserita direttamente per isolare il test
    # dalla parte [1] (nessun collegamento con l'host reale sopra).
    replica_id = "replica-mondo-test"
    world_repo.save_replica_world(World(
        id=replica_id, name="Nome Vecchio", owner_device_id="dev-owner-remoto",
        join_code="ABCDEF", last_seen_host="192.168.1.7:8765", last_synced_seq=0,
    ))
    check("save_replica_world crea la riga locale",
          world_repo.get_world(replica_id) is not None)
    check("la replica ha is_local_host=False",
          world_repo.get_world(replica_id).is_local_host is False)

    world_repo.save_replica_member(WorldMember(
        id="mem-1", world_id=replica_id, device_id="dev-owner-remoto",
        display_name="Master Remoto", role="owner",
    ))
    world_repo.save_replica_member(WorldMember(
        id="mem-2", world_id=replica_id, device_id="dev-io-stesso",
        display_name="Io", role="player",
    ))
    check("i membri della replica sono stati scritti",
          len(world_repo.get_members(replica_id)) == 2)

    # world.rename
    rename_event = WorldEvent(
        seq=1, id="ev-1", world_id=replica_id, actor_device_id="dev-owner-remoto",
        actor_name="Master Remoto", kind="world.rename",
        payload='{"name": "Nome Nuovo"}',
    )
    world_sync.apply_event_to_replica(replica_id, rename_event)
    check("world.rename aggiorna il nome sulla replica",
          world_repo.get_world(replica_id).name == "Nome Nuovo")

    # member.promote
    promote_event = WorldEvent(
        seq=2, id="ev-2", world_id=replica_id, actor_device_id="dev-owner-remoto",
        kind="member.promote", payload='{"device_id": "dev-io-stesso", "role": "master"}',
    )
    world_sync.apply_event_to_replica(replica_id, promote_event)
    check("member.promote aggiorna il ruolo sulla replica",
          world_repo.get_member(replica_id, "dev-io-stesso").role == "master")

    # member.demote
    demote_event = WorldEvent(
        seq=3, id="ev-3", world_id=replica_id, actor_device_id="dev-owner-remoto",
        kind="member.demote", payload='{"device_id": "dev-io-stesso", "role": "player"}',
    )
    world_sync.apply_event_to_replica(replica_id, demote_event)
    check("member.demote aggiorna il ruolo sulla replica",
          world_repo.get_member(replica_id, "dev-io-stesso").role == "player")

    # world.transfer_ownership
    transfer_event = WorldEvent(
        seq=4, id="ev-4", world_id=replica_id, actor_device_id="dev-owner-remoto",
        kind="world.transfer_ownership",
        payload='{"new_owner_device_id": "dev-io-stesso"}',
    )
    world_sync.apply_event_to_replica(replica_id, transfer_event)
    check("world.transfer_ownership promuove il nuovo owner sulla replica",
          world_repo.get_member(replica_id, "dev-io-stesso").role == "owner")
    check("world.transfer_ownership retrocede il vecchio owner sulla replica",
          world_repo.get_member(replica_id, "dev-owner-remoto").role == "master")
    check("worlds.owner_device_id aggiornato sulla replica",
          world_repo.get_world(replica_id).owner_device_id == "dev-io-stesso")

    # member.kick
    kick_event = WorldEvent(
        seq=5, id="ev-5", world_id=replica_id, actor_device_id="dev-io-stesso",
        kind="member.kick", payload='{"device_id": "dev-owner-remoto"}',
    )
    world_sync.apply_event_to_replica(replica_id, kick_event)
    check("member.kick rimuove il membro dalla replica",
          world_repo.get_member(replica_id, "dev-owner-remoto") is None)

    # evento di un tipo sconosciuto a questo passo: non deve sollevare.
    unknown_event = WorldEvent(
        seq=6, id="ev-6", world_id=replica_id, kind="xp.grant",
        payload='{"amount": 100}',
    )
    try:
        world_sync.apply_event_to_replica(replica_id, unknown_event)
        no_raise = True
    except Exception:
        no_raise = False
    check("un evento di un tipo non ancora gestito non solleva eccezioni", no_raise)

    # save_replica_event / update_last_synced_seq
    check("save_replica_event scrive la copia locale", world_repo.save_replica_event(rename_event))
    replica_events = world_repo.get_events_since(replica_id, 0)
    check("l'evento salvato è leggibile dal giornale locale",
          any(e.id == "ev-1" for e in replica_events))
    check("save_replica_event è idempotente (stesso seq/id, nessun duplicato)",
          world_repo.save_replica_event(rename_event) and
          len(world_repo.get_events_since(replica_id, 0)) == len(replica_events))

    check("update_last_synced_seq aggiorna il progresso di sincronizzazione",
          world_repo.update_last_synced_seq(replica_id, 5)
          and world_repo.get_world(replica_id).last_synced_seq == 5)
    check("update_last_seen_host aggiorna l'indirizzo di riconnessione",
          world_repo.update_last_seen_host(replica_id, "192.168.1.99:8766")
          and world_repo.get_world(replica_id).last_seen_host == "192.168.1.99:8766")


# ---------------------------------------------------------------------------
# [3] Orchestrazione dell'ingresso LAN — con un finto backend, nessuna rete
# ---------------------------------------------------------------------------

class _FakeRemoteBackend:
    """Sostituto di RemoteBackend con risposte pre-confezionate: isola la
    logica di `world_sync.start_lan_join`/`_finalize_join` dalla rete reale,
    già verificata a fondo nella parte [1]."""

    def __init__(self, world_info: dict, join_outcome, snapshot: dict | None):
        self._world_info = world_info
        self._join_outcome = join_outcome
        self._snapshot = snapshot
        self.world_id = ""
        self.token: str | None = None

    def check_world(self):
        return self._world_info

    def join(self, join_code, pin, display_name):
        return self._join_outcome

    def poll_join_status(self, request_id):
        return self._join_outcome

    def get_snapshot(self):
        return self._snapshot

    def fetch_events(self, world_id, since_seq=0):
        events = (self._snapshot or {}).get("events", [])
        return [protocol.event_from_dict(e) for e in events if e.get("seq", 0) > since_seq]


def test_lan_join_orchestration() -> None:
    print("\n[3] core.world_sync — orchestrazione dell'ingresso LAN (finto backend)")

    from core.world_backend import JoinOutcome

    # -- versione di protocollo incompatibile ---------------------------------
    import core.world_backend as wb_module

    def _fake_remote_backend_factory(*args, **kwargs):
        return _FakeRemoteBackend(
            {"protocol_version": 999, "accepting": True, "world_id": "w1", "name": "X"},
            JoinOutcome("approved"), None,
        )

    original_remote_backend = wb_module.RemoteBackend
    wb_module.RemoteBackend = _fake_remote_backend_factory
    try:
        result = world_sync.start_lan_join("1.2.3.4", 8765, "CODE01", "123456",
                                           "dev-x", "Test")
        check("versione di protocollo incompatibile viene rifiutata", not result.success)
        check("il messaggio menziona la versione", "versione" in result.error.lower())
    finally:
        wb_module.RemoteBackend = original_remote_backend

    # -- host non raggiungibile -------------------------------------------------
    def _unreachable_factory(*args, **kwargs):
        return _FakeRemoteBackend(None, JoinOutcome("error", error="n/d"), None)

    wb_module.RemoteBackend = _unreachable_factory
    try:
        result = world_sync.start_lan_join("1.2.3.4", 8765, "CODE01", "123456",
                                           "dev-x", "Test")
        check("host non raggiungibile viene segnalato chiaramente", not result.success)
        check("l'errore menziona la raggiungibilità", "raggiungibile" in result.error.lower())
    finally:
        wb_module.RemoteBackend = original_remote_backend

    # -- ingresso "pending" -----------------------------------------------------
    def _pending_factory(*args, **kwargs):
        return _FakeRemoteBackend(
            {"protocol_version": protocol.PROTOCOL_VERSION, "accepting": True,
             "world_id": "w-orch", "name": "Mondo Orchestrazione"},
            JoinOutcome("pending", request_id="req-1"), None,
        )

    wb_module.RemoteBackend = _pending_factory
    try:
        result = world_sync.start_lan_join("192.168.1.7", 8765, "CODE01", "123456",
                                           "dev-orch", "Giocatore Orch")
        check("ingresso di un dispositivo nuovo torna pending", not result.success)
        check("pending_request_id è valorizzato", result.pending_request_id == "req-1")
        check("il backend è restituito per un successivo poll", result.backend is not None)
    finally:
        wb_module.RemoteBackend = original_remote_backend

    # -- ingresso approvato: _finalize_join scrive la replica corretta ----------
    fake_snapshot = {
        "world": {"id": "w-orch-2", "name": "Mondo Approvato", "description": "",
                   "owner_device_id": "dev-master-remoto", "join_code": "APPROV"},
        "members": [
            {"id": "m1", "world_id": "w-orch-2", "device_id": "dev-master-remoto",
             "display_name": "Master", "role": "owner"},
            {"id": "m2", "world_id": "w-orch-2", "device_id": "dev-io-2",
             "display_name": "Io", "role": "player"},
        ],
        "events": [
            {"seq": 1, "id": "e1", "world_id": "w-orch-2", "actor_device_id": "dev-master-remoto",
             "actor_name": "Master", "kind": "world.created", "summary": "Mondo creato.",
             "payload": "{}", "before_state": "{}", "created_at": "2026-08-05T10:00:00"},
        ],
    }

    def _approved_factory(*args, **kwargs):
        return _FakeRemoteBackend(
            {"protocol_version": protocol.PROTOCOL_VERSION, "accepting": True,
             "world_id": "w-orch-2", "name": "Mondo Approvato"},
            JoinOutcome("approved"), fake_snapshot,
        )

    wb_module.RemoteBackend = _approved_factory
    try:
        result = world_sync.start_lan_join("192.168.1.7", 8765, "APPROV", "654321",
                                           "dev-io-2", "Io")
        check("ingresso approvato riesce", result.success)
        check("il mondo replicato ha l'id giusto",
              result.world is not None and result.world.id == "w-orch-2")
        check("il mondo replicato è marcato is_local_host=False",
              result.world is not None and result.world.is_local_host is False)
        check("il mondo replicato ricorda l'indirizzo dell'host",
              result.world is not None and result.world.last_seen_host == "192.168.1.7:8765")
        check("il mondo replicato è leggibile dal DB locale",
              world_repo.get_world("w-orch-2") is not None)
        check("i membri dello snapshot sono stati scritti localmente",
              {m.device_id for m in world_repo.get_members("w-orch-2")}
              == {"dev-master-remoto", "dev-io-2"})
        check("il giornale dello snapshot è stato scritto localmente",
              len(world_repo.get_events_since("w-orch-2", 0)) == 1)
        check("last_synced_seq riflette l'ultimo evento dello snapshot",
              world_repo.get_world("w-orch-2").last_synced_seq == 1)
    finally:
        wb_module.RemoteBackend = original_remote_backend

    # -- finish_pending_join: ancora in attesa, poi rifiutato --------------------
    still_pending = _FakeRemoteBackend(
        {"protocol_version": protocol.PROTOCOL_VERSION, "accepting": True},
        JoinOutcome("pending"), None,
    )
    result = world_sync.finish_pending_join(still_pending, "req-2", "192.168.1.7:8765")
    check("finish_pending_join ancora in attesa non ha successo", not result.success)
    check("finish_pending_join ancora in attesa preserva il request_id",
          result.pending_request_id == "req-2")

    rejected_backend = _FakeRemoteBackend(None, JoinOutcome("rejected"), None)
    result = world_sync.finish_pending_join(rejected_backend, "req-3", "192.168.1.7:8765")
    check("finish_pending_join rifiutato produce un messaggio chiaro",
          not result.success and "rifiutat" in result.error.lower())


def main() -> int:
    print("=" * 62)
    print("PASSO 4 — Host + client in LAN")
    print(f"HOME di test: {_TMP_HOME}")
    print("=" * 62)

    init_db()
    test_network_protocol()
    test_apply_event_to_replica()
    test_lan_join_orchestration()

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
