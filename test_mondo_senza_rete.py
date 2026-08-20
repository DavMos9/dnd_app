"""
Batteria di verifica del passo 2 di dnd_app/docs/multiplayer_design.md —
"Modello mondo, senza rete" (2026-08-05).

Copre: schema (4 tabelle nuove + 5 colonne su characters), world_repo (CRUD,
giornale eventi, join idempotente), core/world_permissions (matrice per
ruolo), core/world_backend (LocalBackend end-to-end: comando -> validazione
-> evento -> stato, incluse le guardie sui casi limite), il fix del bug reale
in character_export.py (§14.1: colonne mondo azzerate in ogni modo di
import), ui/device_identity (identità stabile su desktop, ripiego di
sessione se SharedPreferences non risponde in web mode) e la view minimale
ui/views/world/world_view.py (costruzione, rendering nei due temi).

Nessuna rete qui: coerente con lo scope del passo 2, verificato girando tutto
nello stesso processo. Il comportamento su una vera LAN resta da verificare
da Davide quando si arriva al passo 4.

Usa SEMPRE un DB temporaneo isolato (tempfile.mkdtemp() + HOME separato):
il DB reale di Davide non viene mai toccato. Stesso pattern di test_fase_d.py.

Eseguire con:
    PYTHONPATH=".venv/lib/python3.13/site-packages:." python3 test_mondo_senza_rete.py
"""

from __future__ import annotations

import asyncio
import copy
import json
import os
import sys
import tempfile
import uuid
from typing import Any

_TMP_HOME = tempfile.mkdtemp(prefix="dnd_mondo_")
os.environ["HOME"] = _TMP_HOME

import flet as ft  # noqa: E402

from data.database import get_connection, init_db  # noqa: E402
from data.models import Character  # noqa: E402
from data.repositories import character_export, character_repo, world_repo  # noqa: E402
from core import world_permissions as perm  # noqa: E402
from core.world_backend import LocalBackend  # noqa: E402
from ui import design as d  # noqa: E402
from ui.device_identity import DEVICE_ID_SETTINGS_KEY, resolve_device_id  # noqa: E402
from data.repositories import settings_repo  # noqa: E402

_PASS = 0
_FAIL: list[str] = []


def check(label: str, cond: bool) -> None:
    global _PASS
    if cond:
        _PASS += 1
    else:
        _FAIL.append(label)
        print(f"  FALLITO: {label}")


def _texts(control: Any) -> list[str]:
    """Raccoglie ricorsivamente tutti i valori `ft.Text` sotto un controllo —
    usata per verificare CHE COSA verrebbe mostrato senza dover attaccare la
    view a una vera `ft.Page` (§ vedi `test_worlds_view`/
    `test_worlds_view_remote_actions`: `page` è una property di sola lettura
    in questa versione di Flet finché il controllo non è davvero montato,
    quindi qui si verifica solo la COSTRUZIONE dell'albero controlli, mai
    l'apertura di un dialogo)."""
    out: list[str] = []

    def _walk(c: Any, depth: int = 0) -> None:
        if c is None or depth > 40:
            return
        if isinstance(c, ft.Text) and isinstance(c.value, str):
            out.append(c.value)
        for attr in ("controls", "actions"):
            kids = getattr(c, attr, None)
            if isinstance(kids, (list, tuple)):
                for k in kids:
                    _walk(k, depth + 1)
        content = getattr(c, "content", None)
        if content is not None and not isinstance(content, str):
            _walk(content, depth + 1)

    _walk(control)
    return out


# ---------------------------------------------------------------------------
# 1 — Schema
# ---------------------------------------------------------------------------

def test_schema() -> None:
    print("\n[1] Schema — tabelle e colonne")
    init_db()
    conn = get_connection()
    try:
        for table in ("worlds", "world_members", "world_events", "world_change_requests"):
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
            check(f"tabella {table} creata", row is not None)

        char_cols = {r["name"] for r in conn.execute("PRAGMA table_info(characters)")}
        for col in ("world_id", "origin_character_id", "owner_device_id",
                    "is_replica", "world_seq"):
            check(f"characters.{col} presente", col in char_cols)

        fks = list(conn.execute("PRAGMA foreign_key_list(world_members)"))
        check("world_members ha FK verso worlds", any(fk["table"] == "worlds" for fk in fks))
        fks_ev = list(conn.execute("PRAGMA foreign_key_list(world_events)"))
        check("world_events ha FK verso worlds", any(fk["table"] == "worlds" for fk in fks_ev))

        # Idempotenza: richiamare init_db() due volte non deve sollevare.
        init_db()
        check("init_db() due volte non solleva", True)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 2 — world_repo: CRUD, membri, giornale
# ---------------------------------------------------------------------------

def test_world_repo() -> None:
    print("\n[2] world_repo — mondi, membri, giornale eventi")

    w = world_repo.create_world("La Costa di Smeraldo", "dev-owner", "Davide")
    check("create_world riuscito", w is not None)
    assert w is not None
    check("mondo ospitato localmente", w.is_local_host is True)
    check("join_code lungo 6", len(w.join_code) == 6)
    check("nome vuoto rifiutato", world_repo.create_world("  ", "dev-x", "X") is None)
    check("owner_device_id vuoto rifiutato",
          world_repo.create_world("Nome", "", "X") is None)

    members = world_repo.get_members(w.id)
    check("owner registrato automaticamente tra i membri", len(members) == 1)
    check("owner ha ruolo owner", members[0].role == "owner")

    events = world_repo.get_events_since(w.id, 0)
    check("evento world.created scritto alla creazione", len(events) == 1)
    check("evento world.created ha seq=1", events[0].seq == 1)

    # get_world / get_world_by_join_code
    check("get_world ritrova il mondo", world_repo.get_world(w.id).id == w.id)
    check("get_world su id inesistente ritorna None",
          world_repo.get_world("non-esiste") is None)
    check("get_world_by_join_code ritrova il mondo",
          world_repo.get_world_by_join_code(w.join_code).id == w.id)
    check("get_world_by_join_code case-insensitive",
          world_repo.get_world_by_join_code(w.join_code.lower()).id == w.id)
    check("get_world_by_join_code su codice inesistente ritorna None",
          world_repo.get_world_by_join_code("ZZZZZZ") is None)

    check("get_worlds_for_device trova il mondo per l'owner",
          any(x.id == w.id for x in world_repo.get_worlds_for_device("dev-owner")))
    check("get_worlds_for_device vuoto per un device estraneo",
          world_repo.get_worlds_for_device("dev-mai-visto") == [])

    # Join
    joined = world_repo.join_world_by_code(w.join_code, "dev-player", "Marco")
    check("join_world_by_code riuscito", joined is not None)
    assert joined is not None
    _w2, member = joined
    check("nuovo membro ha ruolo player", member.role == "player")
    check("evento member.joined scritto", any(
        e.kind == "member.joined" for e in world_repo.get_events_since(w.id, 0)
    ))
    check("un secondo join dello stesso device non duplica la riga",
          len(world_repo.get_members(w.id)) == 2)
    joined_again = world_repo.join_world_by_code(w.join_code, "dev-player", "Nome Ignorato")
    check("re-join ritorna lo stesso membro (nome NON sovrascritto)",
          joined_again is not None and joined_again[1].display_name == "Marco")
    check("join con codice inesistente ritorna None",
          world_repo.join_world_by_code("ZZZZZZ", "dev-x", "X") is None)

    # Giornale: ordine e sincronizzazione incrementale
    all_events = world_repo.get_events_since(w.id, 0)
    seqs = [e.seq for e in all_events]
    check("eventi in ordine di seq crescente", seqs == sorted(seqs))
    latest = world_repo.get_latest_seq(w.id)
    check("get_latest_seq coerente con l'ultimo evento", latest == seqs[-1])
    check("get_events_since(latest) non ritorna nulla di nuovo",
          world_repo.get_events_since(w.id, latest) == [])
    check("get_latest_seq su mondo senza eventi è 0",
          world_repo.get_latest_seq("mondo-inesistente") == 0)

    # Rinomina/regenerate diretti (bassi livello, senza permessi — li valida world_backend)
    check("rename_world riuscito", world_repo.rename_world(w.id, "Nuovo Nome"))
    check("rename_world con nome vuoto rifiutato", not world_repo.rename_world(w.id, "   "))
    old_code = world_repo.get_world(w.id).join_code
    new_code = world_repo.regenerate_join_code(w.id)
    check("regenerate_join_code cambia il codice", new_code is not None and new_code != old_code)

    # Ruoli/rimozione
    check("update_member_role riuscito", world_repo.update_member_role(w.id, "dev-player", "master"))
    check("nuovo ruolo persistito",
          world_repo.get_member(w.id, "dev-player").role == "master")
    check("update_member_role con ruolo non valido rifiutato",
          not world_repo.update_member_role(w.id, "dev-player", "dio"))
    check("remove_member riuscito", world_repo.remove_member(w.id, "dev-player"))
    check("membro rimosso non più presente",
          world_repo.get_member(w.id, "dev-player") is None)

    # Cascade alla cancellazione del mondo
    world_id = w.id
    check("delete_world riuscito", world_repo.delete_world(world_id))
    check("mondo eliminato non più presente", world_repo.get_world(world_id) is None)
    conn = get_connection()
    n_members = conn.execute(
        "SELECT COUNT(*) c FROM world_members WHERE world_id=?", (world_id,)
    ).fetchone()["c"]
    n_events = conn.execute(
        "SELECT COUNT(*) c FROM world_events WHERE world_id=?", (world_id,)
    ).fetchone()["c"]
    conn.close()
    check("CASCADE ha rimosso i membri", n_members == 0)
    check("CASCADE ha rimosso il giornale", n_events == 0)

    # world_change_requests — schema pronto, CRUD di base
    w3 = world_repo.create_world("Mondo Richieste", "dev-owner2", "Davide")
    req = world_repo.create_change_request(
        w3.id, "char-fittizio", "dev-owner2", '{"level": 5}', "Bonus narrativo",
    )
    check("create_change_request riuscito", req is not None)
    check("richiesta in stato pending", req.status == "pending")
    pending = world_repo.get_pending_change_requests(w3.id)
    check("get_pending_change_requests la trova", len(pending) == 1)
    check("resolve_change_request riuscito",
          world_repo.resolve_change_request(req.id, "accepted"))
    check("richiesta risolta non più tra le pending",
          world_repo.get_pending_change_requests(w3.id) == [])
    check("resolve_change_request con stato non valido rifiutato",
          not world_repo.resolve_change_request(req.id, "boh"))


# ---------------------------------------------------------------------------
# 3 — core/world_permissions
# ---------------------------------------------------------------------------

def test_permissions() -> None:
    print("\n[3] core/world_permissions — matrice per ruolo")

    check("owner può un comando owner-only", perm.can_perform("owner", perm.CMD_WORLD_RENAME))
    check("master NON può un comando owner-only",
          not perm.can_perform("master", perm.CMD_WORLD_RENAME))
    check("player NON può un comando owner-only",
          not perm.can_perform("player", perm.CMD_WORLD_RENAME))

    check("master può un comando master+owner", perm.can_perform("master", perm.CMD_XP_GRANT))
    check("owner può un comando master+owner (scala verso l'alto)",
          perm.can_perform("owner", perm.CMD_XP_GRANT))
    check("player NON può un comando master+owner",
          not perm.can_perform("player", perm.CMD_XP_GRANT))

    check("ruolo sconosciuto sempre rifiutato",
          not perm.can_perform("spettatore", perm.CMD_XP_GRANT))
    check("comando sconosciuto sempre rifiutato (fail-closed, anche per owner)",
          not perm.can_perform("owner", "comando.mai.registrato"))

    check("is_valid_role riconosce i tre ruoli",
          all(perm.is_valid_role(r) for r in ("owner", "master", "player")))
    check("is_valid_role rifiuta uno sconosciuto", not perm.is_valid_role("spettatore"))

    for field in ("name", "race", "class_name", "level", "str_score"):
        check(f"{field} è un campo vietato", field in perm.FORBIDDEN_CHARACTER_FIELDS)
    check("session_notes NON è un campo vietato",
          "session_notes" not in perm.FORBIDDEN_CHARACTER_FIELDS)

    check("str_score è ammesso in una richiesta di modifica",
          perm.is_change_request_field_allowed("str_score"))
    check("level è ammesso in una richiesta di modifica",
          perm.is_change_request_field_allowed("level"))
    check("name NON è ammesso in una richiesta di modifica (identità pura)",
          not perm.is_change_request_field_allowed("name"))
    check("class_name NON è ammesso in una richiesta di modifica",
          not perm.is_change_request_field_allowed("class_name"))


# ---------------------------------------------------------------------------
# 4 — core/world_backend: LocalBackend end-to-end
# ---------------------------------------------------------------------------

def test_backend() -> None:
    print("\n[4] core/world_backend — LocalBackend end-to-end")

    backend = LocalBackend()
    check("connection_state di LocalBackend è 'local'", backend.connection_state() == "local")

    w = world_repo.create_world("Mondo Backend", "owner-1", "Owner")
    world_repo.join_world_by_code(w.join_code, "player-1", "Giocatore")
    world_repo.join_world_by_code(w.join_code, "player-2", "Giocatore 2")

    # Mittente non membro
    res = backend.send_command(w.id, "estraneo", perm.CMD_WORLD_RENAME, {"name": "X"})
    check("comando da un non-membro rifiutato", not res.success)

    # Player prova un comando owner-only -> rifiutato, nessun evento
    seq_before = world_repo.get_latest_seq(w.id)
    res = backend.send_command(w.id, "player-1", perm.CMD_WORLD_RENAME, {"name": "Hackerato"})
    check("player non autorizzato a rinominare", not res.success)
    check("nessun evento scritto per un comando rifiutato",
          world_repo.get_latest_seq(w.id) == seq_before)
    check("il mondo NON è stato rinominato", world_repo.get_world(w.id).name == "Mondo Backend")

    # Owner rinomina -> evento scritto, stato aggiornato
    res = backend.send_command(w.id, "owner-1", perm.CMD_WORLD_RENAME, {"name": "Rinominato"})
    check("owner autorizzato a rinominare", res.success)
    check("evento con kind corretto", res.event is not None and res.event.kind == perm.CMD_WORLD_RENAME)
    check("il mondo è stato rinominato", world_repo.get_world(w.id).name == "Rinominato")

    # Nome vuoto -> comando rifiutato dall'handler (non dai permessi)
    res = backend.send_command(w.id, "owner-1", perm.CMD_WORLD_RENAME, {"name": "  "})
    check("rename con nome vuoto rifiutato dall'handler", not res.success)

    # Rigenerazione codice
    old_code = world_repo.get_world(w.id).join_code
    res = backend.send_command(w.id, "owner-1", perm.CMD_WORLD_JOIN_CODE_REGENERATE, {})
    check("rigenerazione codice riuscita", res.success)
    check("codice cambiato", world_repo.get_world(w.id).join_code != old_code)

    # Promozione/retrocessione
    res = backend.send_command(w.id, "owner-1", perm.CMD_MEMBER_PROMOTE, {"device_id": "player-1"})
    check("promozione riuscita", res.success)
    check("ruolo aggiornato a master", world_repo.get_member(w.id, "player-1").role == "master")
    res = backend.send_command(w.id, "owner-1", perm.CMD_MEMBER_PROMOTE, {"device_id": "player-1"})
    check("promuovere un master (non player) fallisce", not res.success)
    res = backend.send_command(w.id, "owner-1", perm.CMD_MEMBER_DEMOTE, {"device_id": "player-1"})
    check("retrocessione riuscita", res.success)
    check("ruolo tornato a player", world_repo.get_member(w.id, "player-1").role == "player")
    res = backend.send_command(w.id, "owner-1", perm.CMD_MEMBER_DEMOTE, {"device_id": "player-1"})
    check("retrocedere un player (non master) fallisce", not res.success)

    # Co-master può eseguire comandi master+owner ma non owner-only
    backend.send_command(w.id, "owner-1", perm.CMD_MEMBER_PROMOTE, {"device_id": "player-1"})
    res = backend.send_command(w.id, "player-1", perm.CMD_MEMBER_KICK, {"device_id": "player-2"})
    check("co-master NON può espellere (owner-only)", not res.success)

    # Espulsione dell'owner vietata
    res = backend.send_command(w.id, "owner-1", perm.CMD_MEMBER_KICK, {"device_id": "owner-1"})
    check("l'owner non può essere espulso", not res.success)
    check("owner ancora membro", world_repo.get_member(w.id, "owner-1") is not None)

    # Espulsione di un giocatore CHE POSSIEDE un'istanza in questo mondo
    # (2026-08-07, bug segnalato da Davide: "posso espellere il proprietario
    # ma non il personaggio, che resta collegato per sempre" — l'istanza
    # deve essere archiviata, non lasciata agganciata per sempre).
    instance = Character(name="Fenwick", class_name="Chierico", race="Nano",
                          level=3, hp_max=24, hp_current=24)
    character_repo.create(instance)
    conn = get_connection()
    conn.execute(
        "UPDATE characters SET world_id=?, owner_device_id=? WHERE id=?",
        (w.id, "player-2", instance.id),
    )
    conn.commit()
    conn.close()
    check("prima dell'espulsione: l'istanza è visibile in Master",
          any(c.id == instance.id for c in character_repo.get_master_visible_characters(w.id)))

    res = backend.send_command(w.id, "owner-1", perm.CMD_MEMBER_KICK, {"device_id": "player-2"})
    check("espulsione di un giocatore riuscita", res.success)
    check("giocatore espulso non più membro", world_repo.get_member(w.id, "player-2") is None)
    check("l'evento riporta quante istanze sono state archiviate",
          res.event is not None and json.loads(res.event.payload).get("archived_instances") == 1)

    archived = character_repo.get_by_id(instance.id)
    check("l'istanza posseduta dal membro espulso è archiviata, non eliminata",
          archived is not None and archived.world_instance_archived is True)
    check("dopo l'espulsione: l'istanza NON è più visibile in Master "
          "(il bug segnalato da Davide: prima restava per sempre)",
          not any(c.id == instance.id
                  for c in character_repo.get_master_visible_characters(w.id)))
    check("l'istanza resta comunque nel DB (non distruttivo)",
          character_repo.get_by_id(instance.id) is not None)

    # Idempotenza: espellere di nuovo lo stesso device_id (già non più
    # membro) fallisce PRIMA di arrivare ad archiviare — nessun doppio conteggio.
    res_again = backend.send_command(w.id, "owner-1", perm.CMD_MEMBER_KICK, {"device_id": "player-2"})
    check("espellere un non-membro fallisce (membro non trovato)", not res_again.success)

    # Uscita volontaria (2026-08-19, bug segnalato da Davide: "il giocatore
    # non ha la possibilità di lasciare... il mondo") — controparte di
    # CMD_MEMBER_KICK sopra, ma auto-diretta: un membro fresco ("player-3",
    # mai toccato dai test di kick/promote sopra) esce da sé, con una
    # propria istanza da verificare archiviata come nel caso del kick.
    # `w.join_code` è ormai stale: `CMD_WORLD_JOIN_CODE_REGENERATE` più
    # sopra (riga ~321) l'ha rigenerato sul DB senza aggiornare l'oggetto
    # Python `w` in memoria — serve rileggerlo, altrimenti `join_world_by_code`
    # fallisce silenziosamente e "player-3" non diventa mai membro.
    fresh_join_code = world_repo.get_world(w.id).join_code
    world_repo.join_world_by_code(fresh_join_code, "player-3", "Terzo Giocatore")
    leave_instance = Character(name="Uscente", class_name="Ladro", race="Elfo",
                                level=2, hp_max=16, hp_current=16)
    character_repo.create(leave_instance)
    conn = get_connection()
    conn.execute(
        "UPDATE characters SET world_id=?, owner_device_id=? WHERE id=?",
        (w.id, "player-3", leave_instance.id),
    )
    conn.commit()
    conn.close()

    res = backend.send_command(w.id, "owner-1", perm.CMD_MEMBER_LEAVE, {})
    check("l'owner non può uscire (deve prima trasferire la proprietà)", not res.success)
    check("owner ancora membro dopo il tentativo di uscita", world_repo.get_member(w.id, "owner-1") is not None)

    res = backend.send_command(w.id, "player-3", perm.CMD_MEMBER_LEAVE, {})
    check("uscita volontaria riuscita", res.success)
    check("il membro uscito non è più tra i membri", world_repo.get_member(w.id, "player-3") is None)
    check("l'evento riporta quante istanze sono state archiviate",
          res.event is not None and json.loads(res.event.payload).get("archived_instances") == 1)
    archived_leave = character_repo.get_by_id(leave_instance.id)
    check("l'istanza del membro uscito è archiviata, non eliminata",
          archived_leave is not None and archived_leave.world_instance_archived is True)

    res_again_leave = backend.send_command(w.id, "player-3", perm.CMD_MEMBER_LEAVE, {})
    check("uscire di nuovo (già non più membro) fallisce", not res_again_leave.success)

    # Riattivazione (2026-08-07, scelta di Davide: "riattivabile"): la rotta
    # naturale è un nuovo `character_instance.sync` sullo stesso
    # character_id — riscrive l'intera riga per introspezione di schema,
    # azzerando anche `world_instance_archived` senza codice dedicato.
    # L'export qui simula quello che arriverebbe DAL GIOCATORE (sul suo
    # dispositivo `world_instance_archived` non è mai stato impostato,
    # l'archiviazione avviene SOLO sulla riga dell'host) — non un export
    # dell'istanza già archiviata su QUESTO stesso DB, che la
    # preserverebbe inalterata a 1.
    export_data = character_export.export_character(instance.id)
    assert export_data is not None
    export_data["character"]["world_instance_archived"] = 0
    result_id = character_export.import_replica_character(export_data, instance.id, world_seq=1)
    check("import_replica_character riesce", result_id == instance.id)
    reactivated = character_repo.get_by_id(instance.id)
    check("un nuovo character_instance.sync riattiva l'istanza da solo "
          "(nessuna UI dedicata necessaria)",
          reactivated is not None and reactivated.world_instance_archived is False)
    check("dopo la riattivazione l'istanza torna visibile in Master",
          any(c.id == instance.id for c in character_repo.get_master_visible_characters(w.id)))

    # Trasferimento di proprietà
    res = backend.send_command(w.id, "owner-1", perm.CMD_WORLD_TRANSFER_OWNERSHIP,
                                {"device_id": "player-1"})
    check("trasferimento di proprietà riuscito", res.success)
    check("nuovo owner ha ruolo owner", world_repo.get_member(w.id, "player-1").role == "owner")
    check("vecchio owner retrocesso a master", world_repo.get_member(w.id, "owner-1").role == "master")
    check("worlds.owner_device_id aggiornato", world_repo.get_world(w.id).owner_device_id == "player-1")
    res = backend.send_command(w.id, "player-1", perm.CMD_WORLD_TRANSFER_OWNERSHIP,
                                {"device_id": "player-1"})
    check("trasferire a se stessi viene rifiutato", not res.success)

    # Il vecchio owner (ora master) NON può più fare comandi owner-only
    res = backend.send_command(w.id, "owner-1", perm.CMD_WORLD_RENAME, {"name": "Non dovrebbe"})
    check("il master (ex-owner) non può più rinominare", not res.success)

    # Eliminazione: nessun evento sopravvive (CASCADE)
    world_id = w.id
    res = backend.send_command(w.id, "player-1", perm.CMD_WORLD_DELETE, {})
    check("eliminazione dal nuovo owner riuscita", res.success)
    check("mondo eliminato", world_repo.get_world(world_id) is None)
    check("nessun evento residuo", world_repo.get_events_since(world_id, 0) == [])

    # Registro non-handler: comando noto ai permessi ma senza handler in questo passo.
    # CMD_XP_GRANT era l'esempio originale (nessun handler esisteva prima del
    # passo 6) — dal 2026-08-06 ha un handler vero (core/world_backend.py);
    # CMD_LOOT_ASSIGN lo ha avuto a sua volta dal 2026-08-19 (bug segnalato
    # da Davide: assegnazione bottino restava locale-sola invece di
    # raggiungere l'host). La sonda usa ora CMD_DICE_REQUEST, deliberatamente
    # ancora senza handler (richiede un meccanismo di notifica lato
    # giocatore non ancora progettato — vedi i commenti in world_backend.py).
    w4 = world_repo.create_world("Mondo Senza Handler", "owner-2", "Owner2")
    res = backend.send_command(w4.id, "owner-2", perm.CMD_DICE_REQUEST, {})
    check("comando master+owner senza handler ancora registrato fallisce con errore chiaro",
          not res.success and "sconosciuto" in res.error.lower())


# ---------------------------------------------------------------------------
# 5 — character_export: fix §14.1
# ---------------------------------------------------------------------------

def test_export_fix() -> None:
    print("\n[5] character_export — colonne mondo azzerate all'import (§14.1)")

    char = Character(name="PG Istanza", class_name="Chierico", race="Nano",
                     level=4, hp_max=30, hp_current=30)
    character_repo.create(char)
    conn = get_connection()
    conn.execute(
        "UPDATE characters SET world_id=?, origin_character_id=?, owner_device_id=?, "
        "is_replica=1, world_seq=9 WHERE id=?",
        ("world-abc", "orig-def", "dev-owner", char.id),
    )
    conn.commit()
    conn.close()

    data = character_export.export_character(char.id)
    check("export cattura world_id (il bug è nell'import, non nell'export)",
          data["character"]["world_id"] == "world-abc")
    check("export cattura is_replica=1", data["character"]["is_replica"] == 1)

    def _world_cols(cid: str) -> dict[str, Any]:
        conn = get_connection()
        row = conn.execute(
            "SELECT world_id, origin_character_id, owner_device_id, is_replica, world_seq "
            "FROM characters WHERE id=?", (cid,),
        ).fetchone()
        conn.close()
        return dict(row) if row else {}

    zero = {"world_id": "", "origin_character_id": "", "owner_device_id": "",
            "is_replica": 0, "world_seq": 0}

    copy_id = character_export.import_character(data, mode="copy")
    check("import copy riuscito", copy_id is not None and copy_id != char.id)
    check("import copy azzera le colonne mondo", _world_cols(copy_id) == zero)

    data_new = copy.deepcopy(data)
    data_new["character"]["id"] = str(uuid.uuid4())
    new_id = character_export.import_character(data_new, mode="new")
    check("import new riuscito", new_id is not None)
    check("import new azzera le colonne mondo", _world_cols(new_id) == zero)

    overwrite_id = character_export.import_character(data, mode="overwrite")
    check("import overwrite riuscito con lo stesso id", overwrite_id == char.id)
    check("import overwrite azzera le colonne mondo", _world_cols(overwrite_id) == zero)

    # Regressione esplicita già presente in test_fase_d.py: app_settings resta escluso.
    check("app_settings NON è tra le tabelle esportate",
          "app_settings" not in character_export.CHILD_TABLES)
    check("worlds/world_members/world_events NON sono tra le CHILD_TABLES "
          "(un personaggio esportato non porta con sé l'intero mondo)",
          not ({"worlds", "world_members", "world_events"} & set(character_export.CHILD_TABLES)))


# ---------------------------------------------------------------------------
# 6 — ui/device_identity
# ---------------------------------------------------------------------------

class _FakePageDesktop:
    web = False


class _FakePageWeb:
    def __init__(self):
        self.web = True
        self.overlay: list[Any] = []

    def update(self):
        pass


def test_device_identity() -> None:
    print("\n[6] ui/device_identity — identità desktop e ripiego web")

    settings_repo.set_setting(DEVICE_ID_SETTINGS_KEY, "")  # pulizia da run precedenti
    d1 = asyncio.run(resolve_device_id(_FakePageDesktop()))
    d2 = asyncio.run(resolve_device_id(_FakePageDesktop()))
    check("device_id desktop è un UUID non vuoto", bool(d1))
    check("device_id desktop stabile tra chiamate", d1 == d2)
    check("device_id desktop persistito in app_settings",
          settings_repo.get_setting(DEVICE_ID_SETTINGS_KEY) == d1)

    page_web = _FakePageWeb()
    w1 = asyncio.run(resolve_device_id(page_web))
    w2 = asyncio.run(resolve_device_id(page_web))
    check("device_id web (ripiego) è un UUID non vuoto", bool(w1))
    check("device_id web stabile sulla STESSA pagina/sessione", w1 == w2)

    page_web_2 = _FakePageWeb()
    w3 = asyncio.run(resolve_device_id(page_web_2))
    check("due pagine web diverse ottengono device_id diversi (il punto di tutto questo)",
          w3 != w1)

    check("desktop e web non producono lo stesso device_id",
          d1 != w1)


# ---------------------------------------------------------------------------
# 7 — ui/views/world/world_view: costruzione e rendering
# ---------------------------------------------------------------------------

def test_worlds_view() -> None:
    print("\n[7] WorldsView — costruzione e rendering nei due temi")

    from ui.views.world.world_view import WorldsView

    for mode in ("light", "dark"):
        d.set_mode(mode)

        wv = WorldsView(on_back_to_home=lambda: None)
        check(f"[{mode}] WorldsView si costruisce", len(wv.controls) == 2)
        check(f"[{mode}] stato iniziale = caricamento identità", len(wv._body.controls) == 1)

        wv.device_id = f"dev-view-{mode}"
        wv._render()
        check(f"[{mode}] lista vuota mostra le azioni + empty state",
              len(wv._body.controls) == 3)

        w = world_repo.create_world(f"Mondo Vista {mode}", wv.device_id, "Tester")
        wv._render()
        check(f"[{mode}] lista con un mondo si costruisce senza eccezioni",
              len(wv._body.controls) >= 3)

        wv._current_world = w
        wv._render()
        n_owner_sections = len(wv._body.controls)
        check(f"[{mode}] dettaglio (owner) mostra rinomina/codice/membri/registro/zona pericolosa",
              n_owner_sections >= 6)

        # Un membro non-owner non deve vedere rinomina/zona pericolosa (2 sezioni in meno).
        world_repo.join_world_by_code(w.join_code, "dev-guest", "Ospite")
        wv.device_id = "dev-guest"
        wv._render()
        n_player_sections = len(wv._body.controls)
        check(f"[{mode}] dettaglio (player) ha meno sezioni del dettaglio (owner)",
              n_player_sections < n_owner_sections)

    d.set_mode("light")

    # Pillola "Mondi" in Home: presente solo se on_open_worlds è passato.
    from ui.views.home_view import HomeView

    home_with = HomeView(on_select=lambda i: None, on_create_wizard=lambda: None,
                         on_create_manual=lambda: None, on_open_worlds=lambda: None)

    check("Home con on_open_worlds mostra la pillola 'Mondi'",
          "Mondi" in _texts(home_with))

    home_without = HomeView(on_select=lambda i: None, on_create_wizard=lambda: None,
                            on_create_manual=lambda: None)
    check("Home senza on_open_worlds NON mostra la pillola 'Mondi'",
          "Mondi" not in _texts(home_without))


# ---------------------------------------------------------------------------
# 8 — WorldsView: sezione "Interviene a distanza" (passo 6, 2026-08-06)
# ---------------------------------------------------------------------------

def test_worlds_view_remote_actions() -> None:
    """
    Copre `WorldsView._remote_actions_section()`/`_remote_character_row()`
    (passo 6): costruzione dell'albero controlli senza eccezioni, visibilità
    per ruolo (master/owner sì, player no — stesso criterio già usato dal
    backend, `perm.can_perform(ruolo, perm.CMD_XP_GRANT)`, non una lista
    duplicata qui), stato vuoto, e presenza delle azioni/della condizione
    attiva nel testo reso. Non apre alcun dialogo (`_open_xp_dialog` e affini
    richiedono una vera `ft.Page` — `page` è di sola lettura finché il
    controllo non è montato, vedi `_texts()`), ma i dialoghi stessi non fanno
    altro che raccogliere un valore e chiamare `self.backend.send_command()`
    con lo stesso `kind`/payload già testato end-to-end in
    `test_master_remote_actions.py`.
    """
    print("\n[8] WorldsView — sezione «Interviene a distanza»")
    from ui.views.world.world_view import WorldsView

    world = world_repo.create_world("Mondo con Istanze", "dev-master", "Master")

    wv = WorldsView(on_back_to_home=lambda: None)
    wv.device_id = "dev-master"

    # Stato vuoto: nessun personaggio ancora nel mondo.
    empty_section = wv._remote_actions_section(world)
    check("stato vuoto: nessuna eccezione e messaggio esplicativo",
          "Nessun personaggio in questo mondo" in " ".join(_texts(empty_section)))

    # Un'istanza di personaggio in questo mondo (stesso pattern SQL di
    # test_export_fix: nessuna funzione dedicata "crea istanza" esposta da
    # world_repo/character_repo, la conversione è una UPDATE diretta delle
    # 5 colonne mondo su characters, qui replicata identica).
    char = Character(name="Elandor", class_name="Ranger", race="Elfo",
                      level=5, hp_max=42, hp_current=30, xp=6500)
    character_repo.create(char)
    conn = get_connection()
    conn.execute(
        "UPDATE characters SET world_id=?, origin_character_id=?, owner_device_id=? "
        "WHERE id=?",
        (world.id, char.id, "dev-player", char.id),
    )
    conn.commit()
    conn.close()
    character_repo.add_condition(char.id, "avvelenato", source="Trappola")

    section = wv._remote_actions_section(world)
    texts = " ".join(_texts(section))
    check("il nome del personaggio compare nella sezione", "Elandor" in texts)
    check("PF correnti/massimi mostrati", "30/42" in texts)
    check("azione PE presente", "PE" in texts)
    check("azione Danno presente", "Danno" in texts)
    check("azione Cura presente", "Cura" in texts)
    check("azione Condizione presente", "Condizione" in texts)
    check("il nome della condizione attiva compare come chip", "Avvelenato" in texts)

    # Visibilità per ruolo — un player semplice non deve vedere la sezione
    # nel dettaglio completo (stesso cancello di `_render_detail`:
    # `perm.can_perform(my_role, perm.CMD_XP_GRANT)`).
    world_repo.join_world_by_code(world.join_code, "dev-player-2", "Giocatore")
    wv._current_world = world
    wv.device_id = "dev-master"
    wv._render()
    # d.section() rende il titolo in maiuscolo (`title_text.upper()`).
    master_texts = " ".join(_texts(wv._body)).upper()
    check("il master vede «Interviene a distanza» nel dettaglio",
          "INTERVIENE A DISTANZA" in master_texts)

    wv.device_id = "dev-player-2"
    wv._render()
    player_texts = " ".join(_texts(wv._body)).upper()
    check("un giocatore semplice NON vede «Interviene a distanza»",
          "INTERVIENE A DISTANZA" not in player_texts)

    # Il comando dietro la dialog è lo stesso già coperto end-to-end in
    # test_master_remote_actions.py — qui si verifica solo che
    # _send_remote_command() lo invii con il target giusto.
    result_holder: dict[str, Any] = {}
    orig_send = wv.backend.send_command

    def _spy_send_command(*a, **k):
        res = orig_send(*a, **k)
        result_holder["result"] = res
        return res

    wv.backend.send_command = _spy_send_command  # type: ignore[method-assign]
    wv.device_id = "dev-master"
    wv._send_remote_command(world, char, perm.CMD_HP_HEAL, {"amount": 5})
    check("_send_remote_command invia il comando e riesce",
          result_holder.get("result") is not None and result_holder["result"].success)
    updated = character_repo.get_by_id(char.id)
    check("la cura è stata applicata davvero al personaggio (30 → 35 PF)",
          updated is not None and updated.hp_current == 35)


def test_worlds_view_shared_loot() -> None:
    """
    Copre `WorldsView._shared_loot_section()` (passo 6 di
    `dnd_app/docs/loot_design.md` §6, deposito del gruppo lato giocatore):
    sola lettura, visibile a QUALSIASI membro, mai l'archivio privato del
    Master (`stash_kind="master"`), nessuna azione di modifica/assegnazione
    esposta qui — l'assegnazione resta un privilegio della Sezione Master.
    """
    print("\n[9] WorldsView — sezione «Deposito del Gruppo» (bottino, passo 6)")
    from data.repositories import loot_repo
    from ui.views.world.world_view import WorldsView

    world = world_repo.create_world("Mondo con Bottino", "dev-master-loot", "Master")
    world_repo.join_world_by_code(world.join_code, "dev-player-loot", "Giocatore")

    wv = WorldsView(on_back_to_home=lambda: None)
    wv.device_id = "dev-master-loot"

    check("nessuna voce nel deposito → sezione assente",
          wv._shared_loot_section(world) is None)

    # Una voce nell'archivio PRIVATO del Master non deve mai comparire qui.
    loot_repo.create_entry("master", "item", name="Segreto del Master",
                            world_id=world.id)
    check("una voce nell'archivio del Master resta invisibile qui",
          wv._shared_loot_section(world) is None)

    loot_repo.create_entry("party", "magic_item", name="Ampolla di Ferro",
                            description="Un piccolo contenitore magico.",
                            world_id=world.id)
    loot_repo.create_entry("party", "coins", world_id=world.id,
                            gold=120, silver=7)

    section = wv._shared_loot_section(world)
    check("con voci nel deposito la sezione esiste", section is not None)
    texts = " ".join(_texts(section))
    check("il nome dell'oggetto compare", "Ampolla di Ferro" in texts)
    check("il riepilogo delle monete compare", "120 mo" in texts and "7 ma" in texts)
    check("l'archivio privato del Master resta fuori da questa sezione",
          "Segreto del Master" not in texts)
    check("nessuna azione di assegnazione/modifica/eliminazione esposta qui",
          "Assegna" not in texts and "Elimina" not in texts and "Sposta" not in texts)

    # Un giocatore semplice vede lo stesso deposito, sola lettura.
    wv.device_id = "dev-player-loot"
    player_section = wv._shared_loot_section(world)
    player_texts = " ".join(_texts(player_section))
    check("un giocatore vede lo stesso deposito del gruppo",
          "Ampolla di Ferro" in player_texts)

    # Compare anche nel dettaglio renderizzato per intero, per entrambi i ruoli.
    wv._current_world = world
    wv._render()
    check("«Deposito del Gruppo» compare nel dettaglio del giocatore",
          "DEPOSITO DEL GRUPPO" in " ".join(_texts(wv._body)).upper())
    wv.device_id = "dev-master-loot"
    wv._render()
    check("«Deposito del Gruppo» compare anche nel dettaglio del master",
          "DEPOSITO DEL GRUPPO" in " ".join(_texts(wv._body)).upper())


class _FakePageDialogs:
    """Sola `show_dialog`/`pop_dialog` — sufficiente per una vista che apre
    un `ft.AlertDialog` senza montarla in un vero albero Flet."""

    def __init__(self) -> None:
        self.dialogs: list = []

    def show_dialog(self, dlg) -> None:
        self.dialogs.append(dlg)

    def pop_dialog(self, *_a) -> None:
        if self.dialogs:
            self.dialogs.pop()

    def update(self, *_a, **_k) -> None:
        pass


def _find_outlined_button(node, label: str):
    """Cerca un `ft.OutlinedButton` con questa etichetta (`.content`, non
    `.text` — vedi il commento in fondo alla funzione) in un (sotto)albero
    di controlli Flet. Accetta sia una lista di controlli (es.
    `dlg.actions`, o `wrap_dialog_actions()` che la avvolge in un'unica
    `ft.Row`) sia un singolo controllo con `.content` (es. `ft.Container`,
    come ritornato da `design.section()`/`design.card()`) — entrambe le
    forme compaiono nell'albero costruito da questa view."""
    if isinstance(node, list):
        for c in node:
            found = _find_outlined_button(c, label)
            if found is not None:
                return found
        return None
    if isinstance(node, ft.OutlinedButton) and node.content == label:
        return node
    inner = getattr(node, "controls", None)
    if inner:
        found = _find_outlined_button(inner, label)
        if found is not None:
            return found
    content = getattr(node, "content", None)
    if content is not None and not isinstance(content, str):
        found = _find_outlined_button(content, label)
        if found is not None:
            return found
    return None


def _patch_worlds_view_page_property() -> None:
    """Stesso identico pattern di `test_ingresso_lan_sincronizzazione.py`
    (vedi il suo docstring per il perché): `WorldsView.page` è la proprietà
    vera di Flet, senza setter — sostituita SOLO sulla classe `WorldsView`
    con una che legge da `_test_fake_page` se presente."""
    from ui.views.world.world_view import WorldsView

    if getattr(WorldsView, "_test_page_patched", False):
        return
    original_page_property = WorldsView.page

    def _page_getter(self):
        fake = getattr(self, "_test_fake_page", None)
        if fake is not None:
            return fake
        return original_page_property.fget(self)

    WorldsView.page = property(_page_getter)
    WorldsView._test_page_patched = True


def test_worlds_view_claim_loot() -> None:
    """
    Copre il pulsante «Prendi» di `WorldsView._shared_loot_section()`
    (decisione di design 2026-08-20, Davide: "i giocatori possono prendere
    da soli" — sostituisce la sola-lettura originale). La logica di rete
    (`CMD_LOOT_STASH_CLAIM`) è già coperta a fondo in
    `test_master_world_scoping.py`; qui si verifica solo il cablaggio UI:
    il pulsante compare/scompare in base al possesso di un personaggio in
    QUESTO mondo, e il click reale (dialog di conferma incluso) porta
    davvero all'effetto sul DB.
    """
    print("\n[11] WorldsView — pulsante «Prendi» del Deposito del Gruppo (2026-08-20)")
    from core import character_instances as ci
    from data.repositories import loot_repo
    from ui.views.world.world_view import WorldsView

    _patch_worlds_view_page_property()

    world = world_repo.create_world("Mondo Deposito Interattivo UI", "dev-master-claim", "Master")
    local = Character(name="Fenwick", class_name="Bardo", race="Gnomo", level=2)
    character_repo.create(local)
    result = ci.create_or_resume_instance(world.id, local.id, "dev-player-claim", mode="as_is")
    assert result.success, result.error
    instance = character_repo.get_by_id(result.character_id)
    assert instance is not None
    world_repo.join_world_by_code(world.join_code, "dev-player-claim", "Giocatore")

    entry = loot_repo.create_entry("party", "item", name="Corda di Seta", world_id=world.id)
    assert entry is not None

    wv = WorldsView(on_back_to_home=lambda: None)

    # Il master non ha un proprio personaggio in questo mondo: niente pulsante.
    # (`_texts()` raccoglie solo `ft.Text.value`, non l'etichetta di
    # `OutlinedButton.content` — una stringa semplice in questa versione di
    # Flet, vedi `_find_outlined_button` — quindi qui serve quest'ultima.)
    wv.device_id = "dev-master-claim"
    master_section = wv._shared_loot_section(world)
    check("il master (senza personaggio nel mondo) non vede «Prendi»",
          _find_outlined_button(master_section, "Prendi") is None)

    # Il giocatore, proprietario di un personaggio in questo mondo, lo vede.
    wv.device_id = "dev-player-claim"
    player_section = wv._shared_loot_section(world)
    check("il giocatore (con un personaggio nel mondo) vede «Prendi»",
          _find_outlined_button(player_section, "Prendi") is not None)

    # Click reale: apre il dialog di conferma, poi conferma davvero.
    wv._test_fake_page = _FakePageDialogs()
    prendi_btn = _find_outlined_button(player_section, "Prendi")
    check("il pulsante «Prendi» è raggiungibile nell'albero", prendi_btn is not None)
    prendi_btn.on_click(None)
    check("il click apre il dialog di conferma", len(wv._test_fake_page.dialogs) == 1)

    confirm_dlg = wv._test_fake_page.dialogs[-1]
    confirm_btn = None
    for c in confirm_dlg.actions:
        inner = getattr(c, "controls", None)
        if inner:
            for b in inner:
                if isinstance(b, ft.ElevatedButton) and b.content == "Prendi":
                    confirm_btn = b
    check("il dialog di conferma ha un pulsante «Prendi»", confirm_btn is not None)
    confirm_btn.on_click(None)

    inv = character_repo.get_inventory(instance.id)
    check("l'oggetto è arrivato davvero nell'inventario del personaggio",
          any(i.name == "Corda di Seta" for i in inv))
    check("la voce è sparita dal deposito del gruppo", loot_repo.get_entry(entry.id) is None)
    check("la sezione ora è vuota (nessuna voce residua) -> None",
          wv._shared_loot_section(world) is None)


def test_custom_magic_item_weapon_armor_detection() -> None:
    """
    Copre `_custom_mechanics_kind()` in `master_magic_item_generator_dialog.py`
    — bug report Davide (2026-08-20): un oggetto magico personalizzato di
    categoria "Arma"/"Armatura" deve mostrare le caselle meccaniche dedicate
    invece di restare un oggetto magico generico. Verifica solo la funzione
    pura di categorizzazione (il resto del flusso — `simple_item()` con
    `mechanics=`, `_recipient_item_payload()`, gli handler di rete — è già
    coperto end-to-end in `test_master_world_scoping.py::
    test_loot_weapon_armor_mechanics()`, che passa dagli stessi identici
    costruttori).
    """
    print("\n[12] master_magic_item_generator_dialog — rilevamento arma/armatura "
          "personalizzata (2026-08-20)")
    from ui.views.master.master_magic_item_generator_dialog import _custom_mechanics_kind

    check("'Arma (qualsiasi spada)' -> weapon",
          _custom_mechanics_kind("Arma (qualsiasi spada)") == "weapon")
    check("'Arma (qualsiasi arma da mischia)' -> weapon",
          _custom_mechanics_kind("Arma (qualsiasi arma da mischia)") == "weapon")
    check("'Armatura' -> armor", _custom_mechanics_kind("Armatura") == "armor")
    check("'Oggetto meraviglioso' -> nessuna casella meccanica",
          _custom_mechanics_kind("Oggetto meraviglioso") == "")
    check("categoria vuota -> nessuna casella meccanica", _custom_mechanics_kind("") == "")


def test_magic_items_view_world_scoped_loot() -> None:
    """
    Copre il bug report di Davide (2026-08-20): «se provo ad assegnare un
    oggetto magico dalla sezione oggetti magici me li fa assegnare solo in
    locale». Causa: `MasterMagicItemsView()` (`ui/views/master/master_view.py`,
    tab «Oggetti Magici») era l'unica tab della Sezione Master istanziata
    SENZA `world_id`/`device_id` — a differenza di NPC/Incontri/
    Note/Bottino, tutte già world-scoped. `MagicItemsView` ora accetta
    entrambi i parametri e li inoltra sia a `show_loot_assign_dialog()`
    ("Assegna…") sia a `save_items_to_stash()` ("Salva nell'archivio").
    """
    print("\n[10] MagicItemsView — «Assegna…»/«Salva nell'archivio» "
          "confinati al mondo selezionato (bug report 2026-08-20)")
    from data.repositories import loot_repo
    from ui.views.magic_items_view import MagicItemsView
    import ui.views.master.master_loot_assign_dialog as loot_assign_dialog

    world = world_repo.create_world("Mondo Oggetti Magici", "dev-master-mi", "Master")

    mv = MagicItemsView(world_id=world.id, device_id="dev-master-mi")
    check("world_id/device_id memorizzati", mv._world_id == world.id and mv._device_id == "dev-master-mi")

    mv._page = _FakePageDialogs()
    item = mv._all_items[0]

    # "Salva nell'archivio" -> deve finire nell'archivio DI QUESTO mondo,
    # non in world_id="" (il bug originale: spariva perché la vista
    # Archivio filtra per il mondo selezionato).
    mv._open_detail(item)
    dlg = mv._page.dialogs[-1]
    save_btn = _find_outlined_button(dlg.actions, "Salva nell'archivio")
    check("dialog di dettaglio ha «Salva nell'archivio»", save_btn is not None)
    save_btn.on_click(None)

    archive_this_world = loot_repo.get_entries("master", world_id=world.id)
    archive_no_world = loot_repo.get_entries("master", world_id="")
    check("la voce salvata è nell'archivio del mondo selezionato",
          any(e.name == item.get("name", "") for e in archive_this_world))
    check("...e NON nell'archivio 'locale' (world_id vuoto, il bug originale)",
          not any(e.name == item.get("name", "") for e in archive_no_world))

    # "Assegna…" -> deve instradare world_id/device_id al dialog di
    # assegnazione (che decide da lì se passare dalla rete), non lasciarli
    # al default vuoto.
    captured: dict[str, Any] = {}
    orig_show = loot_assign_dialog.show_loot_assign_dialog

    def _spy_show_loot_assign_dialog(page, items, **kwargs):
        captured.update(kwargs)

    loot_assign_dialog.show_loot_assign_dialog = _spy_show_loot_assign_dialog
    try:
        mv._open_detail(item)
        dlg2 = mv._page.dialogs[-1]
        assign_btn = _find_outlined_button(dlg2.actions, "Assegna…")
        check("dialog di dettaglio ha «Assegna…»", assign_btn is not None)
        assign_btn.on_click(None)
    finally:
        loot_assign_dialog.show_loot_assign_dialog = orig_show

    check("«Assegna…» passa il world_id selezionato, non il default vuoto",
          captured.get("world_id") == world.id)
    check("«Assegna…» passa il device_id di questo dispositivo",
          captured.get("device_id") == "dev-master-mi")


def main() -> int:
    print("=" * 62)
    print("PASSO 2 — Modello mondo, senza rete")
    print(f"HOME di test: {_TMP_HOME}")
    print("=" * 62)

    test_schema()
    test_world_repo()
    test_permissions()
    test_backend()
    test_export_fix()
    test_device_identity()
    test_worlds_view()
    test_worlds_view_remote_actions()
    test_worlds_view_shared_loot()
    test_worlds_view_claim_loot()
    test_magic_items_view_world_scoped_loot()
    test_custom_magic_item_weapon_armor_detection()

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
