"""
Batteria di verifica del passo 8b di dnd_app/docs/multiplayer_design.md —
"Mappe condivise" (§6.4), rotta HTTP `GET /map/<id>/image`
(`network/host_server.py::WorldHostServer.handle_map_image` +
`_RequestHandler.do_GET`). Il resto del passo 8 (schema, handler dei
comandi, replica, migrazione) ha la sua batteria a sé, `test_mappe_
condivise.py` — separata perché quella non serve un host reale su socket e
questa sì (prima rotta non-JSON del progetto: bytes grezzi, non un dict).

Aggiornata il 2026-08-12 insieme alla riscrittura di `CMD_MAP_PUBLISH`
(clona invece di riusare la riga — vedi il docstring di `test_mappe_
condivise.py` per il perché) e all'aggiunta di `CMD_MAP_VISIBILITY`
(nascondere ai giocatori, distinto dall'eliminazione): questa rotta ora
nega l'immagine anche a un membro regolare, se la mappa è nascosta.

Quattro parti:

[1] Percorso felice: pubblica (clona) una mappa con immagine, un membro
    del mondo la scarica via `RemoteBackend.fetch_map_image()` — bytes
    identici all'originale, content-type riconosciuto correttamente (PNG
    e JPEG).

[2] Percorsi di rifiuto, uno per condizione (token non valido, mappa
    inesistente, mappa di un altro mondo, mappa non condivisa, mappa senza
    immagine ancora caricata, mappa eliminata, dispositivo non membro del
    mondo) — tutti devono fallire "chiuso" (nessun byte trapela), mai un
    errore generico che nasconda quale sia stata la causa.

[3] Visibilità (`CMD_MAP_VISIBILITY`): un player non scarica l'immagine di
    una mappa nascosta ai giocatori, un master/owner sì — nascondere non è
    la stessa cosa di non essere condivisa (§6.4).

[4] Verifica a basso livello via `http.client` diretto (non solo
    `RemoteBackend`, che nasconde già status/corpo dietro `None`): la rotta
    risponde davvero un content-type immagine coi bytes attesi in caso di
    successo, e un corpo JSON con "application/json" in caso di errore —
    lo stesso dispatcher deve servire entrambe le forme (vedi il docstring
    di `handle_map_image`).

Eseguire con:
    PYTHONPATH=".venv/lib/python3.13/site-packages:." python3 test_mappe_condivise_http.py
"""

from __future__ import annotations

import base64
import http.client
import json
import os
import sys
import tempfile

_TMP_HOME = tempfile.mkdtemp(prefix="dnd_mappe_condivise_http_")
os.environ["HOME"] = _TMP_HOME

from data.database import init_db  # noqa: E402
from data.models import Character  # noqa: E402
from data.repositories import character_repo, maps_repo, world_repo  # noqa: E402
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


# Immagini minime valide, giusto per i primi byte che `sniff_mime` ispeziona
# — non serve un PNG/JPEG completo e decodificabile, la rotta si limita a
# leggere/ritrasmettere i bytes as-is.
_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
_JPEG_BYTES = b"\xff\xd8\xff" + b"\x00" * 32


def _send(backend: LocalBackend, *args, **kwargs):
    world_backend.reset_host_cooldowns_for_tests()
    return backend.send_command(*args, **kwargs)


def _make_world_and_owner_map(owner: str, image_bytes: bytes | None = _PNG_BYTES):
    world = world_repo.create_world("Mondo delle Mappe HTTP", owner, "Il Master")
    assert world is not None
    local = Character(
        name="Master Locale", class_name="Guerriero", race="Umano", level=1,
        hit_dice_type=10, hit_dice_total=1, hit_dice_remaining=1,
        str_score=10, dex_score=10, con_score=10, int_score=10,
        wis_score=10, cha_score=10, hp_max=10, hp_current=10,
    )
    character_repo.create(local)
    image_data = base64.b64encode(image_bytes).decode("ascii") if image_bytes else ""
    game_map = maps_repo.create_map(local.id, "Rovine del Tempio", image_data=image_data)
    assert game_map is not None
    return world, game_map.id


def _publish(backend: LocalBackend, world_id: str, owner: str, source_map_id: str) -> str:
    """Pubblica e ritorna l'id del CLONE condiviso — mai lo stesso di
    `source_map_id` da quando `CMD_MAP_PUBLISH` clona invece di riusare la
    riga (2026-08-12)."""
    result = _send(backend, world_id, owner, perm.CMD_MAP_PUBLISH, {"map_id": source_map_id})
    assert result.success, result.error
    assert result.event is not None
    return result.event.target_id


def _join_as_player(host: WorldHostServer, world_id: str, device_id: str) -> RemoteBackend:
    """Ingresso reale via rete (join → approvazione → token), stesso
    percorso di `test_lan_host_client.py` — un token emesso da `POST
    /join` è l'unico modo legittimo di ottenerne uno per questa batteria,
    niente scorciatoie che aggirerebbero ciò che la rotta sotto test
    controlla davvero."""
    client = RemoteBackend("127.0.0.1", host.port, device_id)
    client.world_id = world_id
    host.reset_join_rate_limit_for_tests()
    outcome = client.join(world_repo.get_world(world_id).join_code, host.pin, device_id)
    if outcome.status == "pending":
        host.approve(outcome.request_id)
        outcome = client.poll_join_status(outcome.request_id)
    assert outcome.status == "approved", f"join fallito: {outcome.status}"
    return client


# ---------------------------------------------------------------------------
# [1] Percorso felice
# ---------------------------------------------------------------------------

def test_download_felice() -> None:
    print("\n[1] Percorso felice — pubblica, scarica, bytes e content-type corretti")

    world, source_id = _make_world_and_owner_map("dev-owner-http1", image_bytes=_PNG_BYTES)
    host = WorldHostServer(world.id, long_poll_timeout=2.0, announce=False)
    host.start()
    try:
        backend = LocalBackend()
        clone_id = _publish(backend, world.id, "dev-owner-http1", source_id)

        player = _join_as_player(host, world.id, "dev-player-http1")
        raw = player.fetch_map_image(clone_id)
        check("il giocatore scarica l'immagine con successo", raw is not None)
        assert raw is not None
        check("i bytes ricevuti sono identici all'originale caricato", raw == _PNG_BYTES)

        # Il proprietario/master stesso può riscaricarla (non solo un
        # membro diverso da chi l'ha pubblicata) — la rotta è per
        # "chiunque sia membro del mondo", non solo per il destinatario.
        # L'owner è già membro locale (è l'host): usa un client remoto
        # verso se stesso solo per esercitare la rotta HTTP end-to-end.
        owner_remote = _join_as_player(host, world.id, "dev-owner-http1")
        raw_owner = owner_remote.fetch_map_image(clone_id)
        check("anche il master/owner scarica la propria mappa pubblicata via rete",
              raw_owner == _PNG_BYTES)

        # Una seconda mappa, JPEG — verifica che il riconoscimento del
        # content-type non sia un artefatto del solo caso PNG. Caricata
        # direttamente (CMD_MAP_UPLOAD), non clonata da una mappa personale.
        upload_result = _send(backend, world.id, "dev-owner-http1", perm.CMD_MAP_UPLOAD, {
            "name": "Accampamento", "image_data": base64.b64encode(_JPEG_BYTES).decode("ascii"),
        })
        check("caricamento della seconda mappa riuscito", upload_result.success)
        jpeg_map_id = upload_result.event.target_id
        raw_jpeg = player.fetch_map_image(jpeg_map_id)
        check("bytes JPEG identici all'originale", raw_jpeg == _JPEG_BYTES)
    finally:
        host.stop()


# ---------------------------------------------------------------------------
# [2] Percorsi di rifiuto
# ---------------------------------------------------------------------------

def test_percorsi_di_rifiuto() -> None:
    print("\n[2] Percorsi di rifiuto — fail-closed su ogni condizione")

    world, source_id = _make_world_and_owner_map("dev-owner-http2", image_bytes=_PNG_BYTES)
    other_world, other_source_id = _make_world_and_owner_map(
        "dev-owner-http2b", image_bytes=_PNG_BYTES)
    host = WorldHostServer(world.id, long_poll_timeout=2.0, announce=False)
    host.start()
    try:
        backend = LocalBackend()
        clone_id = _publish(backend, world.id, "dev-owner-http2", source_id)

        player = _join_as_player(host, world.id, "dev-player-http2")

        # Token non valido/inventato
        ghost = RemoteBackend("127.0.0.1", host.port, "dev-fantasma")
        ghost.token = "token-mai-emesso"
        check("token non valido → None", ghost.fetch_map_image(clone_id) is None)

        # Mappa inesistente
        check("id mappa inesistente → None", player.fetch_map_image("id-che-non-esiste") is None)

        # Mappa esistente ma non condivisa (mai pubblicata) — la mappa
        # personale di origine stessa, che dopo la clonazione resta locale.
        check("mappa non condivisa (l'originale personale) → None",
              player.fetch_map_image(source_id) is None)

        # Mappa condivisa ma senza immagine caricata
        stub_result = _send(backend, world.id, "dev-owner-http2", perm.CMD_MAP_UPLOAD,
                             {"name": "Solo abbozzo", "image_data": ""})
        check("caricamento dello stub riuscito", stub_result.success)
        stub_id = stub_result.event.target_id
        check("mappa condivisa senza immagine → None", player.fetch_map_image(stub_id) is None)

        # Mappa eliminata — l'unico modo per farla sparire anche dall'elenco
        # del master (distinto dal nasconderla ai giocatori, coperto in [3]).
        delete_result = _send(backend, world.id, "dev-owner-http2", perm.CMD_MAP_DELETE,
                               {"map_id": stub_id})
        check("eliminazione riuscita", delete_result.success)
        check("mappa eliminata → None", player.fetch_map_image(stub_id) is None)

        # Mappa condivisa in UN ALTRO mondo — un membro di `world` non deve
        # poter leggere l'immagine di una mappa di `other_world` nemmeno
        # conoscendone l'id per tentativi.
        other_backend = LocalBackend()
        other_clone_id = _publish(other_backend, other_world.id, "dev-owner-http2b",
                                   other_source_id)
        check("id di una mappa condivisa in un ALTRO mondo → None",
              player.fetch_map_image(other_clone_id) is None)

        # Dispositivo mai entrato in questo mondo (nessun token valido per QUESTO host)
        outsider = RemoteBackend("127.0.0.1", host.port, "dev-mai-entrato")
        check("dispositivo senza alcun token → None", outsider.fetch_map_image(clone_id) is None)
    finally:
        host.stop()


# ---------------------------------------------------------------------------
# [3] Visibilità — nascondere non è la stessa cosa di non essere condivisa
# ---------------------------------------------------------------------------

def test_visibilita() -> None:
    print("\n[3] CMD_MAP_VISIBILITY — nasconde l'immagine ai player, mai a master/owner")

    world, source_id = _make_world_and_owner_map("dev-owner-http3v", image_bytes=_PNG_BYTES)
    host = WorldHostServer(world.id, long_poll_timeout=2.0, announce=False)
    host.start()
    try:
        backend = LocalBackend()
        clone_id = _publish(backend, world.id, "dev-owner-http3v", source_id)

        player = _join_as_player(host, world.id, "dev-player-http3v")
        check("visibile di default: il player scarica l'immagine",
              player.fetch_map_image(clone_id) is not None)

        hide_result = _send(backend, world.id, "dev-owner-http3v", perm.CMD_MAP_VISIBILITY,
                             {"map_id": clone_id, "visible_to_players": False})
        check("nascondere riesce", hide_result.success)
        check("nascosta ai giocatori → None per un player",
              player.fetch_map_image(clone_id) is None)

        # Un master (non owner, non host) resta comunque escluso dal filtro
        # visibilità — vede l'immagine anche se nascosta ai giocatori.
        world_repo.join_world_by_code(world.join_code, "dev-comaster-http3v", "Co-Master")
        world_repo.update_member_role(world.id, "dev-comaster-http3v", perm.ROLE_MASTER)
        comaster = _join_as_player(host, world.id, "dev-comaster-http3v")
        check("un master scarica comunque l'immagine di una mappa nascosta ai giocatori",
              comaster.fetch_map_image(clone_id) is not None)

        show_result = _send(backend, world.id, "dev-owner-http3v", perm.CMD_MAP_VISIBILITY,
                             {"map_id": clone_id, "visible_to_players": True})
        check("rimostrare riesce", show_result.success)
        check("rimostrata: il player torna a scaricarla",
              player.fetch_map_image(clone_id) is not None)
    finally:
        host.stop()


# ---------------------------------------------------------------------------
# [3] Verifica a basso livello via http.client diretto
# ---------------------------------------------------------------------------

def test_http_diretto() -> None:
    print("\n[4] http.client diretto — status/content-type/corpo esatti")

    world, source_id = _make_world_and_owner_map("dev-owner-http4", image_bytes=_PNG_BYTES)
    host = WorldHostServer(world.id, long_poll_timeout=2.0, announce=False)
    host.start()
    try:
        backend = LocalBackend()
        clone_id = _publish(backend, world.id, "dev-owner-http4", source_id)
        player = _join_as_player(host, world.id, "dev-player-http4")

        def _get(path: str, token: str | None) -> tuple[int, str, bytes]:
            conn = http.client.HTTPConnection("127.0.0.1", host.port, timeout=5)
            headers = {"Authorization": f"Bearer {token}"} if token else {}
            conn.request("GET", path, headers=headers)
            resp = conn.getresponse()
            body = resp.read()
            content_type = resp.getheader("Content-Type", "")
            conn.close()
            return resp.status, content_type, body

        status, ctype, body = _get(f"/map/{clone_id}/image", player.token)
        check("successo → status 200", status == 200)
        check("successo → content-type image/png", ctype == "image/png")
        check("successo → corpo = bytes originali", body == _PNG_BYTES)

        status, ctype, body = _get("/map/id-inventato/image", player.token)
        check("mappa inesistente → status 404", status == 404)
        check("mappa inesistente → content-type JSON", ctype == "application/json")
        check("mappa inesistente → corpo JSON con 'error'", "error" in json.loads(body))

        status, ctype, body = _get(f"/map/{clone_id}/image", None)
        check("token assente → status 401", status == 401)
        check("token assente → content-type JSON", ctype == "application/json")

        status, ctype, body = _get(f"/map/{clone_id}/image", "non-valido")
        check("token non valido → status 401", status == 401)
    finally:
        host.stop()


def main() -> int:
    print("=" * 62)
    print("PASSO 8b — Mappe condivise, rotta HTTP GET /map/<id>/image")
    print(f"HOME di test: {_TMP_HOME}")
    print("=" * 62)
    init_db()
    test_download_felice()
    test_percorsi_di_rifiuto()
    test_visibilita()
    test_http_diretto()
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
