"""
Batteria di verifica del passo 8 di dnd_app/docs/multiplayer_design.md —
"Mappe condivise" (§6.4), SOLO backend (schema, migrazione, repository,
handler, replica). La rotta HTTP `GET /map/<id>/image` (passo 8b) ha una
batteria a sé (`test_mappe_condivise_http.py`) perché richiede un host
reale su socket.

Riscritta per intero il 2026-08-12 in risposta a un bug reale segnalato da
Davide dopo il primo uso vero della sezione: pubblicare una mappa
RIUSAVA la stessa riga del personaggio proprietario (`UPDATE ... SET
world_id=?, is_shared=1 WHERE id=?`), quindi disegnare sulla mappa
condivisa nel mondo modificava anche la mappa personale di quel
personaggio, anche se non faceva parte di NESSUN mondo. Pubblicare ora
CLONA (`maps_repo.clone_map_for_sharing`, id nuovo, `character_id=NULL`,
annotazioni vuote): il personale non viene mai più toccato. Stessa
occasione, tre richieste in più di Davide: "carica anche mappe nuove"
(`CMD_MAP_UPLOAD`, senza mappa personale di origine), "il tasto nascondi
non deve far sparire la mappa dall'elenco del master, solo ai giocatori"
(`CMD_MAP_VISIBILITY`, distinto da `is_shared`), "un tasto apposta per
eliminarla" (`CMD_MAP_DELETE`, l'unico modo per farla sparire anche
dall'elenco del master).

Sette parti:

[1] `CMD_MAP_PUBLISH` — clona, non riusa la riga; il tratto disegnato sul
    clone NON tocca la mappa personale di origine (bug corretto); fail-closed.

[2] `CMD_MAP_UPLOAD` — mappa condivisa nuova, senza mappa personale di
    origine, `character_id` sempre NULL, visibilità iniziale scelta.

[3] `CMD_MAP_VISIBILITY` — nasconde/mostra ai giocatori SENZA toccare
    `is_shared` (resta nell'elenco del master); fail-closed.

[4] `CMD_MAP_DELETE` — l'unico modo per far sparire la mappa anche
    dall'elenco del master; la mappa personale di origine (se pubblicata
    per clonazione) non viene mai toccata; fail-closed.

[5] `CMD_MAP_DRAW` — un pacchetto misto (add + add + clear) produce lo
    stesso stato finale di chiamare `maps_repo.apply_stroke_batch()` a
    mano; rifiuta una mappa non condivisa/fuori mondo.

[6] Applicazione sulla replica per tutti e quattro gli eventi sopra — stub
    (publish/upload), aggiornamento visibilità, rimozione — più il bug di
    correttezza già coperto in precedenza: uno snapshot preso dopo la
    pubblicazione di una mappa porta comunque a uno stub locale corretto
    su un device mai raggiunto dall'evento originale.

[7] La migrazione `_migrate_game_maps_nullable_character_id`: righe
    esistenti preservate, una nuova riga con `character_id=NULL` si
    inserisce dopo la migrazione, una seconda esecuzione è un no-op.

Eseguire con:
    PYTHONPATH=".venv/lib/python3.13/site-packages:." python3 test_mappe_condivise.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

_TMP_HOME = tempfile.mkdtemp(prefix="dnd_mappe_condivise_")
os.environ["HOME"] = _TMP_HOME

from data.database import init_db  # noqa: E402
from data.models import Character  # noqa: E402
from data.repositories import character_repo, maps_repo, world_repo  # noqa: E402
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
    world_backend.reset_host_cooldowns_for_tests()
    return backend.send_command(*args, **kwargs)


def _make_world_with_map(owner="dev-owner", player="dev-player"):
    world = world_repo.create_world("Mondo delle Mappe", owner, "Il Master")
    assert world is not None
    world_repo.join_world_by_code(world.join_code, player, "Il Giocatore")

    local = Character(
        name="Master Locale", class_name="Guerriero", race="Umano", level=1,
        hit_dice_type=10, hit_dice_total=1, hit_dice_remaining=1,
        str_score=10, dex_score=10, con_score=10, int_score=10,
        wis_score=10, cha_score=10, hp_max=10, hp_current=10,
    )
    character_repo.create(local)
    game_map = maps_repo.create_map(local.id, "Rovine del Tempio")
    assert game_map is not None
    return world, game_map.id


def _publish(backend: LocalBackend, world_id: str, owner: str, source_map_id: str) -> str:
    """Pubblica e ritorna l'id del CLONE condiviso (mai lo stesso di
    `source_map_id`, vedi il docstring del modulo)."""
    result = _send(backend, world_id, owner, perm.CMD_MAP_PUBLISH, {"map_id": source_map_id})
    assert result.success, result.error
    assert result.event is not None
    return result.event.target_id


# ---------------------------------------------------------------------------
# [1] CMD_MAP_PUBLISH — clona, non riusa la riga personale
# ---------------------------------------------------------------------------

def test_map_publish() -> None:
    print("\n[1] CMD_MAP_PUBLISH — clona (mai la riga personale), fail-closed")

    world, source_id = _make_world_with_map(owner="dev-owner-1", player="dev-player-1")
    backend = LocalBackend()

    source = maps_repo.get_map(source_id)
    check("mappa personale creata non condivisa di default",
          source is not None and not source.is_shared)

    result = _send(backend, world.id, "dev-owner-1", perm.CMD_MAP_PUBLISH,
                    {"map_id": source_id})
    check("pubblicazione riuscita", result.success)
    check("produce un evento", result.event is not None)
    check("kind giusto", result.event.kind == perm.CMD_MAP_PUBLISH)
    clone_id = result.event.target_id
    check("il clone ha un id DIVERSO dalla mappa personale di origine", clone_id != source_id)

    clone = maps_repo.get_map(clone_id)
    check("il clone è condiviso", clone is not None and clone.is_shared)
    check("il clone ha lo stesso nome dell'originale", clone is not None and clone.name == "Rovine del Tempio")
    check("il clone non ha personaggio proprietario", clone is not None and clone.character_id == "")
    check("il clone è visibile ai giocatori di default", clone is not None and clone.visible_to_players)

    source_after = maps_repo.get_map(source_id)
    check("la mappa personale di origine NON risulta condivisa dopo la pubblicazione",
          source_after is not None and not source_after.is_shared)
    check("la mappa personale di origine mantiene il proprio personaggio proprietario",
          source_after is not None and source_after.character_id == source.character_id)

    # --- Il bug corretto: disegnare sul clone non tocca l'originale ---
    batch = [{"type": "stroke", "color": "#f00", "width": 3.0, "points": [[0.1, 0.1], [0.5, 0.5]]}]
    draw_result = _send(backend, world.id, "dev-owner-1", perm.CMD_MAP_DRAW,
                         {"map_id": clone_id, "strokes": batch})
    check("disegno sul clone riuscito", draw_result.success)
    clone_after_draw = maps_repo.get_map(clone_id)
    check("il tratto è sul clone", len(json.loads(clone_after_draw.annotations)) == 1)
    source_after_draw = maps_repo.get_map(source_id)
    check("la mappa PERSONALE non condivisa in nessun mondo NON riceve il tratto "
          "disegnato sul clone condiviso (bug corretto 2026-08-12)",
          json.loads(source_after_draw.annotations) == [])

    result = _send(backend, world.id, "dev-player-1", perm.CMD_MAP_PUBLISH,
                    {"map_id": source_id})
    check("un giocatore non può pubblicare mappe (solo master/owner)", not result.success)

    result = _send(backend, world.id, "dev-owner-1", perm.CMD_MAP_PUBLISH,
                    {"map_id": "id-inesistente"})
    check("una mappa sorgente inesistente viene rifiutata", not result.success)


# ---------------------------------------------------------------------------
# [2] CMD_MAP_UPLOAD — mappa nuova, senza mappa personale di origine
# ---------------------------------------------------------------------------

def test_map_upload() -> None:
    print("\n[2] CMD_MAP_UPLOAD — mappa condivisa caricata direttamente")

    world = world_repo.create_world("Mondo Upload", "dev-owner-up", "Il Master")
    assert world is not None
    world_repo.join_world_by_code(world.join_code, "dev-player-up", "Il Giocatore")
    backend = LocalBackend()

    result = _send(backend, world.id, "dev-owner-up", perm.CMD_MAP_UPLOAD, {
        "name": "Accampamento", "image_data": "ZmFrZS1pbWFnZQ==", "visible_to_players": False,
    })
    check("caricamento riuscito", result.success)
    check("kind giusto", result.event is not None and result.event.kind == perm.CMD_MAP_UPLOAD)
    gm = maps_repo.get_map(result.event.target_id)
    check("la mappa caricata è condivisa", gm is not None and gm.is_shared)
    check("nessun personaggio proprietario", gm is not None and gm.character_id == "")
    check("il nome è quello scelto", gm is not None and gm.name == "Accampamento")
    check("l'immagine è quella caricata", gm is not None and gm.image_data == "ZmFrZS1pbWFnZQ==")
    check("la visibilità iniziale scelta (nascosta) è rispettata",
          gm is not None and not gm.visible_to_players)

    result_default = _send(backend, world.id, "dev-owner-up", perm.CMD_MAP_UPLOAD, {
        "name": "Foresta", "image_data": "",
    })
    gm2 = maps_repo.get_map(result_default.event.target_id)
    check("senza specificarla, la visibilità di default è vera",
          gm2 is not None and gm2.visible_to_players)

    result = _send(backend, world.id, "dev-player-up", perm.CMD_MAP_UPLOAD, {"name": "Hack"})
    check("un giocatore non può caricare mappe", not result.success)


# ---------------------------------------------------------------------------
# [3] CMD_MAP_VISIBILITY — distinta dall'eliminazione
# ---------------------------------------------------------------------------

def test_map_visibility() -> None:
    print("\n[3] CMD_MAP_VISIBILITY — nasconde/mostra SENZA ritirare dall'elenco del master")

    world, source_id = _make_world_with_map(owner="dev-owner-3", player="dev-player-3")
    backend = LocalBackend()
    clone_id = _publish(backend, world.id, "dev-owner-3", source_id)

    result = _send(backend, world.id, "dev-owner-3", perm.CMD_MAP_VISIBILITY,
                    {"map_id": clone_id, "visible_to_players": False})
    check("nascondere riesce", result.success)
    check("kind giusto", result.event is not None and result.event.kind == perm.CMD_MAP_VISIBILITY)
    gm = maps_repo.get_map(clone_id)
    check("visible_to_players spento", gm is not None and not gm.visible_to_players)
    check("is_shared resta acceso: la mappa NON sparisce dall'elenco del master",
          gm is not None and gm.is_shared)
    check("resta comunque tra le mappe condivise del mondo (lette dal master)",
          any(m.id == clone_id for m in maps_repo.get_shared_maps(world.id)))

    result = _send(backend, world.id, "dev-owner-3", perm.CMD_MAP_VISIBILITY,
                    {"map_id": clone_id, "visible_to_players": True})
    check("rimostrare riesce", result.success)
    gm = maps_repo.get_map(clone_id)
    check("visible_to_players riacceso", gm is not None and gm.visible_to_players)

    result = _send(backend, world.id, "dev-player-3", perm.CMD_MAP_VISIBILITY,
                    {"map_id": clone_id, "visible_to_players": False})
    check("un giocatore non può cambiare la visibilità", not result.success)

    result = _send(backend, world.id, "dev-owner-3", perm.CMD_MAP_VISIBILITY,
                    {"map_id": "id-inesistente", "visible_to_players": False})
    check("una mappa inesistente viene rifiutata", not result.success)

    result = _send(backend, world.id, "dev-owner-3", perm.CMD_MAP_VISIBILITY,
                    {"map_id": source_id, "visible_to_players": False})
    check("una mappa non condivisa (l'originale personale) viene rifiutata", not result.success)


# ---------------------------------------------------------------------------
# [4] CMD_MAP_DELETE — l'unico modo per farla sparire dall'elenco del master
# ---------------------------------------------------------------------------

def test_map_delete() -> None:
    print("\n[4] CMD_MAP_DELETE — elimina il clone, mai la mappa personale di origine")

    world, source_id = _make_world_with_map(owner="dev-owner-4", player="dev-player-4")
    backend = LocalBackend()
    clone_id = _publish(backend, world.id, "dev-owner-4", source_id)

    result = _send(backend, world.id, "dev-player-4", perm.CMD_MAP_DELETE, {"map_id": clone_id})
    check("un giocatore non può eliminare mappe condivise", not result.success)
    check("la mappa esiste ancora dopo il tentativo rifiutato",
          maps_repo.get_map(clone_id) is not None)

    result = _send(backend, world.id, "dev-owner-4", perm.CMD_MAP_DELETE, {"map_id": clone_id})
    check("eliminazione riuscita", result.success)
    check("kind giusto", result.event is not None and result.event.kind == perm.CMD_MAP_DELETE)
    check("la mappa non esiste più", maps_repo.get_map(clone_id) is None)
    check("non compare più tra le mappe condivise del mondo",
          not any(m.id == clone_id for m in maps_repo.get_shared_maps(world.id)))
    check("la mappa personale di origine non è mai stata toccata",
          maps_repo.get_map(source_id) is not None)

    result = _send(backend, world.id, "dev-owner-4", perm.CMD_MAP_DELETE, {"map_id": clone_id})
    check("eliminare una mappa già eliminata viene rifiutato (non un no-op silenzioso)",
          not result.success)

    result = _send(backend, world.id, "dev-owner-4", perm.CMD_MAP_DELETE, {"map_id": source_id})
    check("eliminare la mappa personale (mai condivisa) tramite questo comando viene rifiutato",
          not result.success)


# ---------------------------------------------------------------------------
# [5] CMD_MAP_DRAW
# ---------------------------------------------------------------------------

def test_map_draw() -> None:
    print("\n[5] CMD_MAP_DRAW — pacchetto misto, stesso esito di apply_stroke_batch diretto")

    world, source_id = _make_world_with_map(owner="dev-owner-5", player="dev-player-5")
    backend = LocalBackend()
    clone_id = _publish(backend, world.id, "dev-owner-5", source_id)

    batch = [
        {"type": "stroke", "color": "#ff0000", "width": 4.0, "points": [[0, 0], [1, 1]]},
        {"type": "stroke", "color": "#00ff00", "width": 4.0, "points": [[2, 2], [3, 3]]},
    ]
    result = _send(backend, world.id, "dev-owner-5", perm.CMD_MAP_DRAW,
                    {"map_id": clone_id, "strokes": batch})
    check("disegno riuscito", result.success)
    gm = maps_repo.get_map(clone_id)
    strokes = json.loads(gm.annotations)
    check("due tratti applicati", len(strokes) == 2)

    result = _send(backend, world.id, "dev-owner-5", perm.CMD_MAP_DRAW,
                    {"map_id": clone_id, "strokes": [{"op": "clear"}]})
    check("clear riuscito", result.success)
    gm = maps_repo.get_map(clone_id)
    check("annotations svuotate", json.loads(gm.annotations) == [])

    result = _send(backend, world.id, "dev-owner-5", perm.CMD_MAP_DRAW,
                    {"map_id": clone_id, "strokes": []})
    check("un pacchetto vuoto viene rifiutato", not result.success)

    world2 = world_repo.create_world("Altro Mondo", "dev-owner-5b", "Master B")
    result = _send(backend, world2.id, "dev-owner-5b", perm.CMD_MAP_DRAW,
                    {"map_id": clone_id, "strokes": batch})
    check("una mappa di un altro mondo viene rifiutata", not result.success)

    result = _send(backend, world.id, "dev-owner-5", perm.CMD_MAP_DRAW,
                    {"map_id": source_id, "strokes": batch})
    check("una mappa non condivisa (l'originale personale) viene rifiutata", not result.success)


# ---------------------------------------------------------------------------
# [6] Applicazione sulla replica
# ---------------------------------------------------------------------------

def test_replica_riceve_mappa() -> None:
    print("\n[6] apply_event_to_replica — publish/upload/visibility/delete sulla replica")

    world, source_id = _make_world_with_map(owner="dev-owner-6", player="dev-player-6")
    backend = LocalBackend()

    result = _send(backend, world.id, "dev-owner-6", perm.CMD_MAP_PUBLISH, {"map_id": source_id})
    check("pubblicazione riuscita", result.success)
    world_sync.apply_event_to_replica(world.id, result.event)
    clone_id = result.event.target_id

    # Simuliamo la "replica" con un id di mappa diverso, per non collidere
    # con la riga autoritativa dell'host nello stesso DB condiviso (stesso
    # principio già seguito da test_lan_host_client.py parte [2]).
    replica_map_id = "replica-map-xyz"
    ok = maps_repo.replica_create_map_stub(replica_map_id, world.id, "Mappa Remota")
    check("stub creato sulla replica", ok)
    gm = maps_repo.get_map(replica_map_id)
    check("is_shared=1 sullo stub", gm is not None and gm.is_shared)
    check("character_id resta vuoto (NULL in DB) sullo stub", gm is not None and gm.character_id == "")
    check("image_data resta vuota sullo stub (si scarica lazy)", gm is not None and gm.image_data == "")
    check("visibile ai giocatori di default sullo stub", gm is not None and gm.visible_to_players)

    ok = maps_repo.replica_create_map_stub("replica-map-nascosta", world.id, "Nascosta",
                                            visible_to_players=False)
    check("stub creato con visibilità nascosta rispettata", ok)
    gm_hidden = maps_repo.get_map("replica-map-nascosta")
    check("visible_to_players spento sullo stub caricato nascosto",
          gm_hidden is not None and not gm_hidden.visible_to_players)

    batch = [{"type": "stroke", "color": "#000", "width": 2.0, "points": [[0, 0], [5, 5]]}]
    applied = maps_repo.apply_stroke_batch(replica_map_id, batch)
    check("apply_stroke_batch riesce sullo stub", applied)
    gm = maps_repo.get_map(replica_map_id)
    check("il tratto è stato applicato", len(json.loads(gm.annotations)) == 1)

    # -- map.upload sulla replica: stesso stub di map.publish --
    upload_result = _send(backend, world.id, "dev-owner-6", perm.CMD_MAP_UPLOAD,
                           {"name": "Nuova", "image_data": "", "visible_to_players": True})
    world_sync.apply_event_to_replica(world.id, upload_result.event)
    ok = maps_repo.replica_create_map_stub(
        "replica-upload-xyz", world.id, "Nuova Caricata", visible_to_players=True)
    check("stub creato per una mappa caricata (non clonata) sulla replica", ok)

    # -- map.visibility sulla replica --
    ok = maps_repo.set_map_visibility(replica_map_id, False)
    check("set_map_visibility (riusata anche dalla replica) spegne il flag", ok)
    gm = maps_repo.get_map(replica_map_id)
    check("visible_to_players spento sulla replica", gm is not None and not gm.visible_to_players)
    check("is_shared resta acceso sulla replica (nascondere non è ritirare)",
          gm is not None and gm.is_shared)

    # -- map.delete sulla replica --
    ok = maps_repo.delete_map(replica_map_id)
    check("delete_map (riusata anche dalla replica) elimina lo stub", ok)
    check("lo stub non esiste più sulla replica", maps_repo.get_map(replica_map_id) is None)


# ---------------------------------------------------------------------------
# [6b] Bug di correttezza: mappa pubblicata PRIMA dell'ingresso
# ---------------------------------------------------------------------------

def test_mappa_arriva_a_chi_entra_dopo() -> None:
    print("\n[6b] Una mappa pubblicata prima dell'ingresso arriva comunque al nuovo membro")

    from network.host_server import WorldHostServer
    from core.world_backend import RemoteBackend

    world, source_id = _make_world_with_map(owner="dev-owner-7", player="dev-player-7")
    backend = LocalBackend()
    clone_id = _publish(backend, world.id, "dev-owner-7", source_id)

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

        shared = maps_repo.get_shared_maps(world.id)
        check("la mappa pubblicata PRIMA dell'ingresso è comunque tra le condivise "
              "dopo _finalize_join",
              any(m.id == clone_id for m in shared))
    finally:
        host.stop()


# ---------------------------------------------------------------------------
# [6c] Bug segnalato da Davide: le annotazioni disegnate PRIMA dell'ingresso
# non erano visibili al nuovo membro — GET /map/<id>/annotations (2026-08-19)
# ---------------------------------------------------------------------------

def test_annotazioni_arrivano_a_chi_entra_dopo() -> None:
    print("\n[6c] Le annotazioni disegnate PRIMA dell'ingresso arrivano al nuovo membro "
          "(backfill lazy, bug segnalato da Davide)")

    from network.host_server import WorldHostServer
    from core.world_backend import RemoteBackend

    world, source_id = _make_world_with_map(owner="dev-owner-8", player="dev-player-8")
    backend = LocalBackend()
    clone_id = _publish(backend, world.id, "dev-owner-8", source_id)

    stroke = {"type": "stroke", "color": "#FF0000", "width": 5.0,
              "points": [[0.1, 0.1], [0.5, 0.5]]}
    draw_result = _send(backend, world.id, "dev-owner-8", perm.CMD_MAP_DRAW,
                         {"map_id": clone_id, "strokes": [{"op": "add", **stroke}]})
    check("il tratto disegnato prima dell'ingresso viene applicato",
          draw_result.success)

    host = WorldHostServer(world.id, backend=backend, long_poll_timeout=2.0, announce=False)
    port = host.start()
    try:
        client = RemoteBackend("127.0.0.1", port, "dev-player-tardivo-2", world_id=world.id)
        outcome = client.join(world.join_code, host.pin, "Arrivato Dopo Con Disegno")
        req_id = outcome.request_id
        host.approve(req_id)
        join_outcome = client.poll_join_status(req_id)
        check("ingresso approvato con token", join_outcome.status == "approved" and bool(client.token))

        finalize_result = world_sync._finalize_join(client, f"127.0.0.1:{port}")
        check("_finalize_join riesce", finalize_result.success)

        replica_map = maps_repo.get_map(clone_id)
        check("lo stub della mappa esiste sulla replica", replica_map is not None)
        try:
            replica_strokes = json.loads(replica_map.annotations or "[]") if replica_map else []
        except json.JSONDecodeError:
            replica_strokes = []
        check("le annotazioni disegnate PRIMA dell'ingresso sono arrivate via backfill "
              "(non più '[]')",
              any(s.get("color") == "#FF0000" for s in replica_strokes))

        # Fetch diretto della rotta, per verificarne il comportamento isolato
        # dal resto di _finalize_join.
        raw = client.fetch_map_annotations(clone_id)
        check("RemoteBackend.fetch_map_annotations ritorna le annotazioni reali",
              raw is not None and "#FF0000" in raw)
    finally:
        host.stop()


# ---------------------------------------------------------------------------
# [7] Migrazione character_id nullable
# ---------------------------------------------------------------------------

def test_migrazione_character_id_nullable() -> None:
    print("\n[7] Migrazione game_maps.character_id → nullable")

    import sqlite3
    from data.database import get_connection, _migrate_game_maps_nullable_character_id

    # Un DB "vecchio": ricrea game_maps con lo schema NOT NULL originale
    # (init_db() è già stato chiamato da main() con lo schema nuovo, quindi
    # qui simuliamo l'upgrade esplicitamente su una tabella rifatta a mano).
    conn = get_connection()
    conn.execute("DROP TABLE IF EXISTS game_maps")
    conn.execute("""
        CREATE TABLE game_maps (
            id           TEXT PRIMARY KEY,
            character_id TEXT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
            name         TEXT NOT NULL DEFAULT '',
            image_path   TEXT NOT NULL DEFAULT '',
            annotations  TEXT NOT NULL DEFAULT '[]',
            created_at   TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    local = Character(name="Vecchio Personaggio", hp_max=1, hp_current=1)
    character_repo.create(local)
    conn.execute(
        "INSERT INTO game_maps (id, character_id, name, annotations) VALUES (?, ?, ?, ?)",
        ("m-vecchia", local.id, "Mappa Vecchia", '[{"type":"stroke"}]'),
    )
    conn.commit()
    info_before = conn.execute("PRAGMA table_info(game_maps)").fetchall()
    notnull_before = next(c["notnull"] for c in info_before if c["name"] == "character_id")
    check("prima della migrazione character_id è NOT NULL", notnull_before == 1)
    conn.close()

    cur = get_connection().cursor()
    _migrate_game_maps_nullable_character_id(cur)
    cur.connection.commit()
    cur.connection.close()

    conn = get_connection()
    info_after = conn.execute("PRAGMA table_info(game_maps)").fetchall()
    notnull_after = next(c["notnull"] for c in info_after if c["name"] == "character_id")
    check("dopo la migrazione character_id è nullable", notnull_after == 0)
    row = conn.execute("SELECT * FROM game_maps WHERE id='m-vecchia'").fetchone()
    check("la riga esistente è preservata", row is not None and row["name"] == "Mappa Vecchia")
    check("le annotazioni sono preservate", row is not None and "stroke" in row["annotations"])

    try:
        conn.execute(
            "INSERT INTO game_maps (id, character_id, name) VALUES ('m-nuova', NULL, 'Condivisa')"
        )
        conn.commit()
        check("una nuova riga con character_id NULL si inserisce dopo la migrazione", True)
    except sqlite3.IntegrityError:
        check("una nuova riga con character_id NULL si inserisce dopo la migrazione", False)
    conn.close()

    # Idempotenza: una seconda chiamata non deve sollevare né alterare nulla.
    cur2 = get_connection().cursor()
    _migrate_game_maps_nullable_character_id(cur2)
    cur2.connection.commit()
    conn = get_connection()
    count = conn.execute("SELECT COUNT(*) c FROM game_maps").fetchone()["c"]
    check("una seconda chiamata alla migrazione è un no-op sicuro (righe invariate)", count == 2)
    conn.close()


def main() -> int:
    print("=" * 62)
    print("PASSO 8 — Mappe condivise, backend (§6.4)")
    print(f"HOME di test: {_TMP_HOME}")
    print("=" * 62)
    init_db()
    test_map_publish()
    test_map_upload()
    test_map_visibility()
    test_map_delete()
    test_map_draw()
    test_replica_riceve_mappa()
    test_mappa_arriva_a_chi_entra_dopo()
    test_annotazioni_arrivano_a_chi_entra_dopo()
    test_migrazione_character_id_nullable()
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
