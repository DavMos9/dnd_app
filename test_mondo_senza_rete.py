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
        check(f"{field} è un campo vietato", perm.is_forbidden_character_field(field))
    check("session_notes NON è un campo vietato",
          not perm.is_forbidden_character_field("session_notes"))

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

    # Espulsione di un giocatore
    res = backend.send_command(w.id, "owner-1", perm.CMD_MEMBER_KICK, {"device_id": "player-2"})
    check("espulsione di un giocatore riuscita", res.success)
    check("giocatore espulso non più membro", world_repo.get_member(w.id, "player-2") is None)

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
    # passo 6) — dal 2026-08-06 ha un handler vero (core/world_backend.py),
    # quindi la sonda usa CMD_LOOT_ASSIGN, deliberatamente ancora senza
    # handler (il Bottino resta locale finché non arriva il suo passo — vedi
    # "Piano di lavoro attivo" in CLAUDE.md e i commenti in world_backend.py).
    w4 = world_repo.create_world("Mondo Senza Handler", "owner-2", "Owner2")
    res = backend.send_command(w4.id, "owner-2", perm.CMD_LOOT_ASSIGN, {})
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
