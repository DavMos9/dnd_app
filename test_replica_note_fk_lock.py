"""
Regressione del bug del 2026-08-17 (Multiplayer, round 5): sul dispositivo
del GIOCATORE, dopo un ingresso in un mondo LAN, "impossibile copiare
personaggio" **sempre** (fino al riavvio dell'app), e nella replica si
vedeva solo 1 nota e nessuna mappa condivisa.

Causa unica, a monte di tutti e tre i sintomi (trovata riproducendo
`_finalize_join()` sullo snapshot REALE del mondo di Davide):

  1. `master_campaign_notes.linked_npc_id` ha una FK verso `master_npcs(id)`,
     ma la Rubrica NPC del master NON viaggia mai nello snapshot (è
     materiale privato del master). Sulla replica del giocatore quell'id
     non esiste, quindi `save_replica_note()` falliva con "FOREIGN KEY
     constraint failed" per OGNI nota collegata a un NPC — 9 note su 11 nei
     dati reali.

  2. `save_replica_note()` chiudeva la connessione come ultima riga del
     blocco `try`, non in un `finally`: al primo errore la connessione
     restava aperta con la transazione di scrittura fallita, e non veniva
     liberata dal refcount perché l'eccezione crea un ciclo di riferimenti
     (eccezione → traceback → frame → variabile locale `conn`) che solo il
     garbage collector generazionale può rompere.

  3. Quella connessione orfana trattiene il lock di scrittura del file:
     **ogni scrittura successiva del processo** falliva con "database is
     locked" — le altre 10 note, le 3 mappe, e poi la copia del personaggio
     (`character_export.import_character`, da cui il messaggio "Copia del
     personaggio fallita" che Davide vedeva SEMPRE e non a intermittenza).

Quattro parti:

[1] `save_replica_note` — NPC collegato assente in locale: la nota viene
    salvata comunque, col collegamento azzerato (mai più una FK violata);
    NPC presente: il collegamento si conserva.

[2] `data/database.py::_ResilientConnection` — una connessione abbandonata
    da una funzione che ha dimenticato `close()` non avvelena più le
    scritture successive del processo (167 funzioni scrivono `close()`
    dentro il `try`: la rete di sicurezza sta in `get_connection()`).

[3] `_finalize_join()` sullo snapshot di un mondo con note collegate a NPC
    e mappe pubblicate — TUTTE le note e TUTTE le mappe arrivano sulla
    replica, e la copia di un personaggio subito dopo riesce.

[4] `_finalize_join()` — il giornale eventi non resta mai con un buco: se
    un evento non si salva, `last_synced_seq` si tronca a quel punto invece
    di dichiarare "ho tutto" (il prossimo sync riprende da lì).

Eseguire con:
    PYTHONPATH=".venv/lib/python3.13/site-packages:." python3 test_replica_note_fk_lock.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import uuid

_TMP_HOME = tempfile.mkdtemp(prefix="dnd_replica_note_fk_")
os.environ["HOME"] = _TMP_HOME

from data.database import get_connection, init_db  # noqa: E402
from data.models import Character  # noqa: E402
from data.repositories import (  # noqa: E402
    character_repo, maps_repo, master_repo, world_repo,
)
from core import character_instances as ci  # noqa: E402
from core import world_sync  # noqa: E402
from network import protocol  # noqa: E402

_PASS = 0
_FAIL: list[str] = []


def check(label: str, cond: bool) -> None:
    global _PASS
    if cond:
        _PASS += 1
    else:
        _FAIL.append(label)
        print(f"  FALLITO: {label}")


def _note_payload(world_id: str, name: str, linked_npc_id: str = "",
                   note_id: str = "") -> dict:
    """Lo stesso dict che l'host spedisce nello snapshot (`asdict` di un
    `MasterCampaignNote`), ridotto ai campi che `save_replica_note` legge."""
    return {
        "id": note_id or str(uuid.uuid4()),
        "category": "npc",
        "name": name,
        "description": "",
        "status": "",
        "tags": "",
        "linked_npc_id": linked_npc_id,
        "world_id": world_id,
        "visibility": "all",
        "visible_to_device_ids": "[]",
        "updated_at": "",
    }


def _make_npc(name: str = "Ulfrik") -> str:
    """Una riga `master_npcs` minima, scritta diretta (il costruttore
    pubblico non serve: qui interessa solo che l'id esista per la FK)."""
    npc_id = str(uuid.uuid4())
    conn = get_connection()
    try:
        conn.execute("INSERT INTO master_npcs (id, name) VALUES (?, ?)", (npc_id, name))
        conn.commit()
    finally:
        conn.close()
    return npc_id


def _make_local_character(name: str = "Locale") -> Character:
    c = Character(
        name=name, class_name="Guerriero", race="Umano", level=3,
        hit_dice_type=10, hit_dice_total=3, hit_dice_remaining=3,
        str_score=10, dex_score=10, con_score=10, int_score=10,
        wis_score=10, cha_score=10, hp_max=10, hp_current=10,
    )
    character_repo.create(c)
    return c


# ---------------------------------------------------------------------------
# [1] save_replica_note e la FK verso master_npcs
# ---------------------------------------------------------------------------

def test_save_replica_note_npc_assente():
    print("\n[1] save_replica_note — NPC collegato assente in locale")
    world_id = str(uuid.uuid4())

    # Il caso reale: l'host manda una nota collegata a un suo NPC, che sulla
    # replica del giocatore non esiste (gli NPC non vengono mai condivisi).
    payload = _note_payload(world_id, "Nota collegata", linked_npc_id=str(uuid.uuid4()))
    check("la nota viene salvata comunque (prima: FOREIGN KEY constraint failed)",
          master_repo.save_replica_note(payload) is True)

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT name, linked_npc_id FROM master_campaign_notes WHERE id=?",
            (payload["id"],),
        ).fetchone()
    finally:
        conn.close()
    check("la nota è davvero sulla replica", row is not None)
    check("il nome è quello dell'host", row is not None and row["name"] == "Nota collegata")
    check("il collegamento all'NPC è azzerato (NULL), non inventato",
          row is not None and row["linked_npc_id"] is None)

    # Controprova: se l'NPC esiste in locale il collegamento si conserva —
    # il fix non è un azzeramento indiscriminato.
    npc_id = _make_npc()
    payload2 = _note_payload(world_id, "Nota con NPC presente", linked_npc_id=npc_id)
    check("nota con NPC presente salvata", master_repo.save_replica_note(payload2) is True)
    conn = get_connection()
    try:
        row2 = conn.execute(
            "SELECT linked_npc_id FROM master_campaign_notes WHERE id=?",
            (payload2["id"],),
        ).fetchone()
    finally:
        conn.close()
    check("il collegamento a un NPC PRESENTE viene conservato",
          row2 is not None and row2["linked_npc_id"] == npc_id)

    # Idempotenza (INSERT OR REPLACE): rispedire la stessa nota non duplica.
    master_repo.save_replica_note(payload)
    conn = get_connection()
    try:
        n = conn.execute(
            "SELECT COUNT(*) c FROM master_campaign_notes WHERE world_id=?", (world_id,)
        ).fetchone()["c"]
    finally:
        conn.close()
    check("rispedire la stessa nota non crea duplicati", n == 2)


# ---------------------------------------------------------------------------
# [2] Una connessione abbandonata non avvelena più il processo
# ---------------------------------------------------------------------------

def test_connessione_abbandonata_non_blocca_il_processo():
    print("\n[2] _ResilientConnection — una connessione orfana non blocca le scritture")

    def _abbandona_connessione_con_scrittura_fallita() -> None:
        """Riproduce ESATTAMENTE il pattern delle 167 funzioni dei
        repository: `conn.close()` come ultima riga del `try`, quindi mai
        eseguito se una query solleva. La connessione resta viva dentro il
        ciclo eccezione → traceback → frame, con il lock di scrittura preso."""
        try:
            conn = get_connection()
            conn.execute(
                "INSERT INTO master_campaign_notes (id, category, name, linked_npc_id) "
                "VALUES (?, ?, ?, ?)",
                (str(uuid.uuid4()), "npc", "Rotta", "npc-inesistente"),
            )
            conn.commit()
            conn.close()
        except Exception:
            pass  # esattamente come il `logger.error(...); return False` reale

    _abbandona_connessione_con_scrittura_fallita()

    # Prima del fix: da qui in poi OGNI scrittura del processo falliva con
    # "database is locked" fino al riavvio dell'app.
    world_id = str(uuid.uuid4())
    ok = master_repo.save_replica_note(_note_payload(world_id, "Dopo l'abbandono"))
    check("una scrittura successiva riesce comunque (prima: database is locked)", ok is True)

    local = _make_local_character("Copiabile")
    world_repo.create_world("Mondo prova", "dev-master", "Master", description="")
    worlds = world_repo.get_worlds_for_device("dev-master")
    check("mondo di prova creato", len(worlds) == 1)
    result = ci.create_or_resume_instance(worlds[0].id, local.id, "dev-player", mode="as_is")
    check("la copia del personaggio riesce dopo una connessione abbandonata "
          "(prima: 'Copia del personaggio fallita.' sempre)",
          result.success is True)
    check("nessun messaggio d'errore residuo", result.error == "")


# ---------------------------------------------------------------------------
# [3] _finalize_join end-to-end su uno snapshot realistico
# ---------------------------------------------------------------------------

def _snapshot_realistico(world_id: str, n_note_con_npc: int, n_mappe: int) -> dict:
    """Uno snapshot nella forma esatta di `WorldHostServer.handle_snapshot()`
    — note collegate a NPC che sulla replica NON esistono (il caso reale) e
    mappe pubblicate."""
    notes = [_note_payload(world_id, "Nota libera")]
    notes += [
        _note_payload(world_id, f"Nota collegata {i}", linked_npc_id=str(uuid.uuid4()))
        for i in range(n_note_con_npc)
    ]
    return {
        "world": {
            "id": world_id, "name": "Mondo del test", "description": "",
            "owner_device_id": "dev-master", "join_code": "ABC123",
        },
        "members": [
            {"id": str(uuid.uuid4()), "world_id": world_id, "device_id": "dev-master",
             "display_name": "Master", "role": "owner", "is_connected": False,
             "last_seen_at": "", "created_at": "2026-08-17T10:00:00"},
            {"id": str(uuid.uuid4()), "world_id": world_id, "device_id": "dev-player",
             "display_name": "Giocatore", "role": "player", "is_connected": True,
             "last_seen_at": "", "created_at": "2026-08-17T10:00:00"},
        ],
        "events": [],
        "characters": [],
        "change_requests": [],
        "rejoin_requests": [],
        "notes": notes,
        "visible_encounter": None,
        "shared_maps": [
            {"id": str(uuid.uuid4()), "name": f"Mappa {i}"} for i in range(n_mappe)
        ],
    }


class _FakeBackend:
    """Sostituisce `RemoteBackend` per la sola parte usata da
    `_finalize_join()`: nessuna rete in questo test."""

    def __init__(self, snapshot: dict):
        self._snapshot = snapshot
        self.world_id = snapshot["world"]["id"]
        self.token = "token-di-test"

    def get_snapshot(self):
        return self._snapshot


def test_finalize_join_semina_tutto():
    print("\n[3] _finalize_join — tutte le note e tutte le mappe arrivano sulla replica")
    world_id = str(uuid.uuid4())
    snapshot = _snapshot_realistico(world_id, n_note_con_npc=8, n_mappe=3)

    result = world_sync._finalize_join(_FakeBackend(snapshot), "192.168.1.5:8765")
    check("_finalize_join riesce", result.success is True)
    check("il mondo è sulla replica", result.world is not None)
    check("la replica non è marcata come host locale",
          result.world is not None and not result.world.is_local_host)

    notes = master_repo.get_notes_visible_to(world_id, "dev-player")
    check(f"tutte le 9 note sono sulla replica (prima: 1) — trovate {len(notes)}",
          len(notes) == 9)
    maps = maps_repo.get_shared_maps(world_id)
    check(f"tutte le 3 mappe sono sulla replica (prima: 0) — trovate {len(maps)}",
          len(maps) == 3)
    check("i membri sono stati salvati", len(world_repo.get_members(world_id)) == 2)

    # Il sintomo che Davide vedeva subito dopo l'ingresso.
    local = _make_local_character("Entra nel mondo")
    result2 = ci.create_or_resume_instance(world_id, local.id, "dev-player", mode="as_is")
    check("subito dopo l'ingresso, far entrare un personaggio nel mondo riesce",
          result2.success is True)
    check("nessun 'Copia del personaggio fallita'", result2.error == "")


# ---------------------------------------------------------------------------
# [4] Il giornale eventi non resta mai con un buco
# ---------------------------------------------------------------------------

def test_giornale_troncato_non_bucato():
    print("\n[4] _finalize_join — un evento non salvato tronca la sequenza, non la buca")
    world_id = str(uuid.uuid4())
    snapshot = _snapshot_realistico(world_id, n_note_con_npc=0, n_mappe=0)
    snapshot["events"] = [
        {"id": str(uuid.uuid4()), "world_id": world_id, "seq": seq,
         "event_type": "note.share", "actor_device_id": "dev-master",
         "target_type": "note", "target_id": "n1", "payload": "{}",
         "created_at": "2026-08-17T10:00:00"}
        for seq in (1, 2, 3, 4)
    ]

    # Fa fallire il salvataggio dell'evento seq=3 e solo quello.
    originale = world_repo.save_replica_event
    def _save_con_guasto(event):
        if event.seq == 3:
            raise RuntimeError("guasto simulato sull'evento seq=3")
        return originale(event)
    world_repo.save_replica_event = _save_con_guasto
    try:
        result = world_sync._finalize_join(_FakeBackend(snapshot), "192.168.1.5:8765")
    finally:
        world_repo.save_replica_event = originale

    check("_finalize_join riesce comunque (l'ingresso non si perde per un evento)",
          result.success is True)
    saved = world_repo.get_events_since(world_id, 0, limit=None)
    check(f"gli eventi salvati si fermano prima del guasto — {len(saved)} su 4",
          [e.seq for e in saved] == [1, 2])
    world = world_repo.get_world(world_id)
    check("last_synced_seq è troncato all'ultimo evento davvero salvato, non a max(seq) "
          "(altrimenti gli eventi 3 e 4 non tornerebbero mai più)",
          world is not None and world.last_synced_seq == 2)


def main() -> int:
    init_db()
    test_save_replica_note_npc_assente()
    test_connessione_abbandonata_non_blocca_il_processo()
    test_finalize_join_semina_tutto()
    test_giornale_troncato_non_bucato()
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
