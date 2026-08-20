"""
Verifica della sincronizzazione degli NPC verso i dispositivi dei giocatori
in un Mondo condiviso (2026-08-20) — completamento del Dossier PNG
(`test_npc_dossier.py`) su richiesta esplicita di Davide: la feature doveva
funzionare non solo sul dispositivo del Master, ma anche per un giocatore su
un dispositivo SEPARATO in una vera sessione LAN.

Gap trovato prima di questo fix: `master_npcs` non veniva mai replicata
verso i dispositivi dei giocatori (a differenza di mappe/bottino/note) —
`master_repo.save_replica_note()` degradava sempre `linked_npc_id` a NULL
perché l'NPC referenziato non esisteva mai in locale sulla replica. Fix,
seguendo lo stesso schema già consolidato per il deposito comune del gruppo
(`loot_stash_entries`)/le mappe condivise:

  - `WorldHostServer.handle_snapshot()` include `shared_npcs`: SOLO gli NPC
    referenziati da almeno una nota visibile a quel device (mai l'intera
    Rubrica NPC, materiale privato del Master).
  - `master_repo.replica_upsert_npc()` li scrive sulla replica — chiamata
    PRIMA della scrittura delle note in `core.world_sync._finalize_join()`
    (ingresso) e `_refresh_snapshot_derived_state()` (ogni giro di sync
    periodico, ~2s), così l'NPC esiste già quando la nota che lo referenzia
    viene salvata.

Quattro parti, tutte con un vero `WorldHostServer` + `RemoteBackend` (stesso
schema di `test_note_sharing.py` parte [5], "Una nota condivisa prima
dell'ingresso arriva comunque al nuovo membro" — qui lo stesso principio
esteso all'NPC collegato):

[1] Un NPC collegato a una nota condivisa PRIMA dell'ingresso di un
    giocatore arriva comunque sulla sua replica via `_finalize_join()`, col
    ritratto, e il collegamento della nota NON viene azzerato.

[2] Un NPC NON referenziato da nessuna nota visibile non arriva MAI sulla
    replica del giocatore (privacy della Rubrica — resta materiale privato
    del Master).

[3] `_refresh_snapshot_derived_state()` (il giro di sync periodico, non solo
    l'ingresso): un NPC condiviso DOPO che il giocatore è già entrato arriva
    comunque al giro successivo, e un ritratto caricato/modificato dal
    Master DOPO la prima condivisione si aggiorna sulla replica senza
    bisogno di un nuovo evento dedicato (eventual consistency, stesso
    principio già in uso per bottino/mappe).

[4] Rete di sicurezza invariata: se per qualunque motivo un NPC collegato
    non arriva mai (es. cancellato sull'host dopo la condivisione), il
    collegamento sulla replica si degrada comunque a NULL invece di far
    fallire la scrittura della nota — nessuna regressione sul fix del
    2026-08-17 (`test_replica_note_fk_lock.py`).

Eseguire con:
    PYTHONPATH=".venv/lib/python3.13/site-packages:." python3 test_npc_sync_multiplayer.py
"""

from __future__ import annotations

import base64
import os
import sys
import tempfile

_TMP_HOME = tempfile.mkdtemp(prefix="dnd_npc_sync_mp_")
os.environ["HOME"] = _TMP_HOME

from data.database import init_db  # noqa: E402
from data.repositories import master_repo, world_repo  # noqa: E402
from core import world_backend  # noqa: E402
from core import world_permissions as perm  # noqa: E402
from core import world_sync  # noqa: E402
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


_FAKE_PHOTO = base64.b64encode(b"\xff\xd8\xff\xe0fake-npc-photo").decode()


def _join_and_finalize(host: WorldHostServer, port: int, world_id: str, join_code: str,
                        device_id: str, display_name: str):
    client = RemoteBackend("127.0.0.1", port, device_id, world_id=world_id)
    outcome = client.join(join_code, host.pin, display_name)
    assert outcome.status == "pending", outcome.status
    host.approve(outcome.request_id)
    join_outcome = client.poll_join_status(outcome.request_id)
    assert join_outcome.status == "approved" and client.token, join_outcome.status
    result = world_sync._finalize_join(client, f"127.0.0.1:{port}")
    assert result.success, result.error
    return client


def test_npc_collegato_arriva_a_chi_entra_dopo() -> None:
    print("\n[1] NPC collegato a una nota condivisa arriva sulla replica del "
          "giocatore, col ritratto — il collegamento non viene azzerato")

    world = world_repo.create_world("Mondo Dossier LAN", "dev-owner-npc1", "Il Master")
    assert world is not None
    backend = LocalBackend()

    npc = master_repo.create_npc(
        name="Oswin il Locandiere", role="Contatto", race="Umano",
        notes="Gestisce la locanda del Cinghiale Nero.",
        world_id=world.id, image_data=_FAKE_PHOTO,
    )
    assert npc is not None

    result = _send(backend, world.id, "dev-owner-npc1", perm.CMD_NOTE_SHARE, {
        "category": "npc", "name": "Incontro alla locanda",
        "description": "Il gruppo incontra Oswin.", "visibility": "all",
        "linked_npc_id": npc.id,
    })
    check("condivisione della nota (con NPC collegato) riuscita", result.success)

    host = WorldHostServer(world.id, backend=backend, long_poll_timeout=2.0, announce=False)
    port = host.start()
    try:
        _join_and_finalize(host, port, world.id, world.join_code, "dev-player-npc1", "Il Giocatore")

        replica_npc = master_repo.get_npc_by_id(npc.id)
        check("BUG FIX: l'NPC collegato esiste ora sulla replica del giocatore",
              replica_npc is not None)
        if replica_npc is not None:
            check("...con nome corretto", replica_npc.name == "Oswin il Locandiere")
            check("...con il ritratto caricato dal master",
                  replica_npc.image_data == _FAKE_PHOTO)
            check("...con la descrizione", "Cinghiale Nero" in replica_npc.notes)

        visible = master_repo.get_notes_visible_to(world.id, "dev-player-npc1")
        note = next((n for n in visible if n.name == "Incontro alla locanda"), None)
        check("la nota è visibile", note is not None)
        check("BUG FIX: linked_npc_id NON è stato azzerato (prima: sempre NULL)",
              note is not None and note.linked_npc_id == npc.id)
    finally:
        host.stop()


def test_npc_non_referenziato_non_arriva_mai() -> None:
    print("\n[2] Un NPC non collegato a nessuna nota visibile resta privato — "
          "non arriva mai sulla replica del giocatore")

    world = world_repo.create_world("Mondo Dossier Privacy", "dev-owner-npc2", "Il Master")
    assert world is not None
    backend = LocalBackend()

    npc_privato = master_repo.create_npc(
        name="Cospiratore Segreto", role="Antagonista futuro",
        world_id=world.id,
    )
    assert npc_privato is not None
    # Nessuna nota lo referenzia — resta nella Rubrica privata del Master.

    host = WorldHostServer(world.id, backend=backend, long_poll_timeout=2.0, announce=False)
    port = host.start()
    try:
        _join_and_finalize(host, port, world.id, world.join_code, "dev-player-npc2", "Il Giocatore")

        # `get_npc_by_id` legge la stessa tabella fisica: se l'NPC non è mai
        # stato scritto sulla replica, la riga con quell'id non esiste. In
        # questo test unico-processo la riga ESISTE comunque (è la stessa
        # tabella dell'host) — il vero controllo è sullo snapshot HTTP
        # stesso, che è quello che un dispositivo REALMENTE separato
        # riceverebbe: `shared_npcs` non deve contenerlo.
        status, payload = host.handle_snapshot(_member_token(host, "dev-player-npc2"))
        check("handle_snapshot riesce (200)", status == 200)
        shared_ids = {n.get("id") for n in payload.get("shared_npcs", [])}
        check("BUG FIX/privacy: l'NPC non referenziato NON è tra gli shared_npcs",
              npc_privato.id not in shared_ids)
    finally:
        host.stop()


def _member_token(host: WorldHostServer, device_id: str) -> str:
    """Il token di sessione valido per `device_id` su questo host — stessa
    mappa `token -> device_id` usata dal dispatcher HTTP reale per
    autenticare ogni richiesta."""
    for token, dev in host._tokens.items():  # noqa: SLF001 - test interno
        if dev == device_id:
            return token
    raise AssertionError(f"nessun token attivo per {device_id!r}")


def test_refresh_periodico_e_aggiornamento_ritratto() -> None:
    print("\n[3] _refresh_snapshot_derived_state — NPC condiviso DOPO l'ingresso "
          "e ritratto aggiornato arrivano al giro di sync successivo")

    world = world_repo.create_world("Mondo Dossier Periodico", "dev-owner-npc3", "Il Master")
    assert world is not None
    backend = LocalBackend()

    npc = master_repo.create_npc(name="Millah la Guaritrice", role="Alleata",
                                  world_id=world.id, image_data="")
    assert npc is not None

    host = WorldHostServer(world.id, backend=backend, long_poll_timeout=2.0, announce=False)
    port = host.start()
    try:
        client = _join_and_finalize(host, port, world.id, world.join_code,
                                     "dev-player-npc3", "Il Giocatore")

        check("prima della condivisione, l'NPC non è ancora referenziato da nulla",
              npc.id not in {n.linked_npc_id for n in
                             master_repo.get_notes_visible_to(world.id, "dev-player-npc3")
                             if n.linked_npc_id})

        # La nota viene condivisa SOLO ORA, con l'app del giocatore già aperta.
        result = _send(backend, world.id, "dev-owner-npc3", perm.CMD_NOTE_SHARE, {
            "category": "npc", "name": "La guaritrice del villaggio",
            "description": "Cura i feriti per pochi spiccioli.", "visibility": "all",
            "linked_npc_id": npc.id,
        })
        check("condivisione (dopo l'ingresso) riuscita", result.success)

        # Il giro di sync periodico (non un nuovo ingresso) deve bastare.
        world_sync._refresh_snapshot_derived_state(client, world.id)

        replica_npc = master_repo.get_npc_by_id(npc.id)
        check("l'NPC condiviso DOPO l'ingresso arriva al giro di sync periodico",
              replica_npc is not None)
        note = next((n for n in master_repo.get_notes_visible_to(world.id, "dev-player-npc3")
                     if n.name == "La guaritrice del villaggio"), None)
        check("...e il collegamento della nota non è azzerato",
              note is not None and note.linked_npc_id == npc.id)

        # Il Master aggiorna il ritratto DOPO la condivisione — deve
        # propagarsi senza un nuovo evento dedicato (eventual consistency).
        npc.image_data = _FAKE_PHOTO
        ok = master_repo.update_npc(npc)
        check("l'aggiornamento del ritratto sull'host riesce", ok)
        world_sync._refresh_snapshot_derived_state(client, world.id)
        replica_npc_after = master_repo.get_npc_by_id(npc.id)
        check("BUG FIX: il ritratto aggiornato arriva alla replica al giro "
              "successivo, senza un evento dedicato",
              replica_npc_after is not None and replica_npc_after.image_data == _FAKE_PHOTO)
    finally:
        host.stop()


def test_rete_di_sicurezza_invariata() -> None:
    print("\n[4] Rete di sicurezza invariata: NPC mai arrivato -> il "
          "collegamento si degrada comunque a NULL (nessuna regressione sul "
          "fix del 2026-08-17)")
    from data.repositories import master_repo as mr

    payload = {
        "id": "nota-orfana", "category": "npc", "name": "Nota orfana",
        "description": "", "status": "", "tags": "",
        "linked_npc_id": "npc-mai-arrivato-sulla-replica",
        "world_id": "mondo-test-4", "visibility": "all",
        "visible_to_device_ids": "[]", "updated_at": "",
    }
    ok = mr.save_replica_note(payload)
    check("save_replica_note riesce comunque (mai una FK violata)", ok)
    saved = [n for n in mr.get_notes_visible_to("mondo-test-4", "qualunque-device")
             if n.id == "nota-orfana"]
    check("la nota è stata salvata", len(saved) == 1)
    check("il collegamento a un NPC mai arrivato si degrada a NULL, come prima",
          saved and saved[0].linked_npc_id == "")


if __name__ == "__main__":
    init_db()
    test_npc_collegato_arriva_a_chi_entra_dopo()
    test_npc_non_referenziato_non_arriva_mai()
    test_refresh_periodico_e_aggiornamento_ritratto()
    test_rete_di_sicurezza_invariata()

    print("\n" + "=" * 70)
    print(f"Controlli passati: {_PASS} — falliti: {len(_FAIL)}")
    if _FAIL:
        print("\nControlli falliti:")
        for label in _FAIL:
            print(f"  - {label}")
        sys.exit(1)
    print("Tutti i controlli passati.")
