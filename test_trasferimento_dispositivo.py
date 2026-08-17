"""
Batteria di verifica del trasferimento del personaggio su un altro dispositivo
(2026-08-17, §11.9 di `dnd_app/docs/multiplayer_design.md`).

Richiesta di Davide: "vorrei inserire un modo in cui un utente può accedere
anche con un dispositivo diverso al mondo, magari scaricando il proprio
personaggio dall'host, assegnando un codice univoco". Il problema di fondo è che
l'identità di un giocatore è il `device_id` (UUID per installazione) e le sue
istanze sono legate a quello: un dispositivo nuovo — o lo stesso dopo una
reinstallazione, che azzera `app_settings` — è per l'host uno sconosciuto senza
personaggi.

Cinque parti:

[1] Il codice: alfabeto, monouso, scadenza, revoca, unicità per mondo.

[2] I permessi: chi può emettere un codice e per chi. Include la verifica che il
    codice NON finisca mai nel payload dell'evento di giornale — il giornale è
    trasmesso a tutte le repliche, il codice è un segreto per un solo membro.

[3] `rebind_device`: la parte in cui un'implementazione distratta perde dati.
    Verifica sia ciò che DEVE spostarsi (appartenenza, istanze incluse quelle
    archiviate, visibilità delle note, richieste di rientro pendenti) sia ciò
    che deve restare fermo (giornale, provenienza del bottino, note di altri
    mondi, note condivise con altri). Più un'iniezione di fallimento a metà
    transazione, che è il test che dimostra che la transazione è reale.

[4] Il protocollo su socket veri: riscatto valido, i quattro modi di sbagliare
    il codice, il messaggio al vecchio dispositivo, la capability flag.

[5] Il ciclo completo su rete reale: emetti → riscatta → il master approva →
    il nuovo dispositivo scarica i propri personaggi da `/snapshot`, il vecchio
    token non vale più.

Nota sul DB unico condiviso: come `test_lan_host_client.py` (vedi il suo
docstring), qui host e client parlano allo stesso file SQLite. Scambiare `HOME`
a runtime per simulare due dispositivi introdurrebbe una corsa reale col thread
del server, e un test così potrebbe sembrare passare senza provare nulla. Il
comportamento a due dispositivi fisici separati resta verificabile solo da
Davide su hardware vero.

Eseguire con:
    PYTHONPATH=".venv/lib/python3.13/site-packages:." python3 test_trasferimento_dispositivo.py
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta

_TMP_HOME = tempfile.mkdtemp(prefix="dnd_trasferimento_")
os.environ["HOME"] = _TMP_HOME

from data.database import get_connection, init_db  # noqa: E402
from data.models import Character, WorldEvent  # noqa: E402
from data.repositories import (  # noqa: E402
    character_repo, loot_repo, master_repo, world_repo, world_transfer_repo,
)
from core import world_permissions as perm  # noqa: E402
from core import world_sync  # noqa: E402
from core.world_backend import LocalBackend, RemoteBackend  # noqa: E402
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
# Aiutanti
# ---------------------------------------------------------------------------

def _make_world(name: str, owner_device: str = "dev-master") -> object:
    world = world_repo.create_world(name, owner_device, "Il Master")
    assert world is not None
    return world


def _add_member(world_id: str, device_id: str, display_name: str,
                 role: str = "player"):
    joined = world_repo.join_world_by_code(
        world_repo.get_world(world_id).join_code, device_id, display_name,
    )
    assert joined is not None
    if role != "player":
        world_repo.update_member_role(world_id, device_id, role)
    return world_repo.get_member(world_id, device_id)


def _make_instance(world_id: str, owner_device: str, name: str,
                    archived: bool = False) -> Character:
    """Un'istanza di personaggio in un mondo, come la crea
    `core.character_instances` (qui scritta a mano: quel modulo non serve per
    ciò che questa batteria verifica)."""
    char = Character(
        name=name, class_name="Guerriero", race="Umano", level=3,
        hp_max=25, hp_current=25,
        world_id=world_id, owner_device_id=owner_device,
        origin_character_id=f"origin-{name}",
    )
    character_repo.create(char)
    if archived:
        character_repo.archive_world_instance(world_id, char.id)
    return character_repo.get_by_id(char.id)


def _note_ids(world_id: str, note_id: str) -> list:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT visible_to_device_ids FROM master_campaign_notes WHERE id=?",
            (note_id,),
        ).fetchone()
        return json.loads(row["visible_to_device_ids"] or "[]") if row else []
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# [1] Il codice
# ---------------------------------------------------------------------------

def test_codice() -> None:
    print("\n[1] Il codice di trasferimento")

    world = _make_world("Mondo Codici")
    _add_member(world.id, "dev-a", "Thorin")

    code = world_transfer_repo.generate_transfer_code()
    check(f"il codice ha {world_transfer_repo.TRANSFER_CODE_LENGTH} caratteri ({code})",
          len(code) == world_transfer_repo.TRANSFER_CODE_LENGTH)
    ambigui = set("0O1IL")
    check("il codice non usa caratteri ambigui (0/O/1/I/L)",
          not (set(code) & ambigui))
    check("l'alfabeto è quello condiviso con il codice d'ingresso",
          set(code) <= set(world_repo.JOIN_CODE_ALPHABET))

    t1 = world_transfer_repo.issue_transfer(world.id, "dev-a", "Thorin", "dev-a")
    check("l'emissione riesce", t1 is not None)
    assert t1 is not None
    check("il codice emesso è pending", t1.status == world_transfer_repo.STATUS_PENDING)
    check("il codice si ritrova per codice",
          world_transfer_repo.get_pending_transfer_by_code(world.id, t1.code) is not None)
    check("il codice si ritrova per membro",
          world_transfer_repo.get_pending_transfer_for_member(world.id, "dev-a") is not None)
    check("la ricerca per codice è insensibile al maiuscolo/minuscolo",
          world_transfer_repo.get_pending_transfer_by_code(world.id, t1.code.lower()) is not None)

    # Emettere di nuovo revoca il precedente: un membro ha sempre al massimo
    # un codice valido, così un codice letto ad alta voce per sbaglio muore
    # appena se ne genera un altro.
    t2 = world_transfer_repo.issue_transfer(world.id, "dev-a", "Thorin", "dev-a")
    assert t2 is not None
    check("una seconda emissione revoca la prima",
          world_transfer_repo.get_pending_transfer_by_code(world.id, t1.code) is None)
    check("il secondo codice è valido",
          world_transfer_repo.get_pending_transfer_by_code(world.id, t2.code) is not None)
    check("il primo codice risulta revocato",
          world_transfer_repo.get_transfer(t1.id).status == world_transfer_repo.STATUS_REVOKED)

    # Scadenza: retrodatata a mano, come farebbe il tempo.
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE world_device_transfers SET expires_at=? WHERE id=?",
            ((datetime.now() - timedelta(seconds=1)).isoformat(), t2.id),
        )
        conn.commit()
    finally:
        conn.close()
    check("un codice scaduto non è più valido",
          world_transfer_repo.get_pending_transfer_by_code(world.id, t2.code) is None)
    check("expire_stale_transfers marca il codice scaduto",
          world_transfer_repo.expire_stale_transfers(world.id) == 1)
    check("dopo la scadenza lo stato è 'expired'",
          world_transfer_repo.get_transfer(t2.id).status == world_transfer_repo.STATUS_EXPIRED)
    check("una seconda passata non marca nulla",
          world_transfer_repo.expire_stale_transfers(world.id) == 0)

    # `expires_at` illeggibile → trattato come scaduto (fail-closed): un codice
    # senza scadenza valida non deve diventare per sbaglio un codice eterno.
    t3 = world_transfer_repo.issue_transfer(world.id, "dev-a", "Thorin", "dev-a")
    assert t3 is not None
    conn = get_connection()
    try:
        conn.execute("UPDATE world_device_transfers SET expires_at='' WHERE id=?", (t3.id,))
        conn.commit()
    finally:
        conn.close()
    check("un codice senza scadenza è trattato come scaduto, non come eterno",
          world_transfer_repo.get_pending_transfer_by_code(world.id, t3.code) is None)

    # Monouso a livello di DB, non solo di controlli applicativi.
    t4 = world_transfer_repo.issue_transfer(world.id, "dev-a", "Thorin", "dev-a")
    assert t4 is not None
    check("il primo riscatto riesce",
          world_transfer_repo.mark_redeemed(t4.id, "dev-nuovo") is True)
    check("il secondo riscatto dello stesso codice fallisce",
          world_transfer_repo.mark_redeemed(t4.id, "dev-altro") is False)
    check("dopo il riscatto il codice non è più valido",
          world_transfer_repo.get_pending_transfer_by_code(world.id, t4.code) is None)
    check("was_transferred_away riconosce il vecchio dispositivo",
          world_transfer_repo.was_transferred_away(world.id, "dev-a") is not None)
    check("was_transferred_away non riporta nulla per un dispositivo estraneo",
          world_transfer_repo.was_transferred_away(world.id, "dev-mai-visto") is None)
    check("revocare un codice già riscattato non fa nulla",
          world_transfer_repo.revoke_transfer(t4.id) is False)

    # Lo stesso codice in due mondi diversi: l'indice UNIQUE è (world_id, code).
    world2 = _make_world("Mondo Parallelo")
    _add_member(world2.id, "dev-a", "Thorin")
    t5 = world_transfer_repo.issue_transfer(world2.id, "dev-a", "Thorin", "dev-a")
    assert t5 is not None
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE world_device_transfers SET code=? WHERE id=?", (t4.code, t5.id),
        )
        conn.commit()
        ok = True
    except sqlite3.IntegrityError:
        ok = False
    finally:
        conn.close()
    check("lo stesso codice è ammesso in due mondi diversi", ok)
    check("un codice di un altro mondo non è valido qui",
          world_transfer_repo.get_pending_transfer_by_code(world.id, t5.code) is None)


# ---------------------------------------------------------------------------
# [2] I permessi e il segreto
# ---------------------------------------------------------------------------

def test_permessi() -> None:
    print("\n[2] Chi può emettere un codice, e per chi")

    check("il comando di emissione è autorizzato dal ruolo player",
          perm.can_perform(perm.ROLE_PLAYER, perm.CMD_DEVICE_TRANSFER_ISSUE))
    check("il comando di revoca è autorizzato dal ruolo player",
          perm.can_perform(perm.ROLE_PLAYER, perm.CMD_DEVICE_TRANSFER_REVOKE))
    check("un ruolo vuoto non è autorizzato",
          not perm.can_perform("", perm.CMD_DEVICE_TRANSFER_ISSUE))
    check("il riscatto NON è inviabile come comando da nessuno, owner incluso",
          not perm.can_perform(perm.ROLE_OWNER, perm.DEVICE_TRANSFER_REDEEM_KIND))
    check("l'emissione non è fra i comandi che mutano un personaggio",
          perm.CMD_DEVICE_TRANSFER_ISSUE not in perm.CHARACTER_MUTATING_COMMANDS)

    world = _make_world("Mondo Permessi", owner_device="dev-owner")
    _add_member(world.id, "dev-master", "Il Co-Master", role="master")
    _add_member(world.id, "dev-p1", "Thorin")
    _add_member(world.id, "dev-p2", "Legolas")
    backend = LocalBackend()

    # Il giocatore per sé: la via del "sto cambiando telefono e ho ancora
    # quello vecchio in mano".
    res = backend.send_command(world.id, "dev-p1", perm.CMD_DEVICE_TRANSFER_ISSUE,
                                {"device_id": "dev-p1"})
    check("un giocatore può emettere un codice per sé stesso", res.success)
    check("il codice torna in CommandResult.data",
          bool(res.data and res.data.get("code")))
    check("data porta anche la scadenza", bool(res.data and res.data.get("expires_at")))

    # Il codice NON deve stare nel giornale: `world_events.payload` viaggia
    # verso OGNI replica via GET /events.
    codice = res.data["code"]
    check("il payload dell'evento non contiene il codice",
          codice not in (res.event.payload or ""))
    check("il payload dell'evento non contiene il codice nemmeno nel sommario",
          codice not in (res.event.summary or ""))
    check("il payload dell'evento porta transfer_id e device_id",
          json.loads(res.event.payload).get("transfer_id") is not None
          and json.loads(res.event.payload).get("device_id") == "dev-p1")

    # Un giocatore NON può emettere un codice per un altro giocatore.
    res = backend.send_command(world.id, "dev-p1", perm.CMD_DEVICE_TRANSFER_ISSUE,
                                {"device_id": "dev-p2"})
    check("un giocatore non può emettere un codice per un altro membro",
          not res.success)
    check("il rifiuto lo dice esplicitamente", "solo per il tuo" in res.error)

    # Il master sì: è il caso "telefono rotto", quello che rende utile la
    # funzione.
    res = backend.send_command(world.id, "dev-master", perm.CMD_DEVICE_TRANSFER_ISSUE,
                                {"device_id": "dev-p2"})
    check("un master può emettere un codice per un giocatore", res.success)

    res = backend.send_command(world.id, "dev-owner", perm.CMD_DEVICE_TRANSFER_ISSUE,
                                {"device_id": "dev-p2"})
    check("anche l'owner può emettere un codice per un giocatore", res.success)

    # Nessuno per l'owner: il suo device_id sta su `worlds.owner_device_id` e la
    # riassegnazione non lo tocca. La via corretta esiste già ed è l'export.
    for attore in ("dev-owner", "dev-master", "dev-p1"):
        res = backend.send_command(world.id, attore, perm.CMD_DEVICE_TRANSFER_ISSUE,
                                    {"device_id": "dev-owner"})
        check(f"nessun codice per l'owner (tentativo da {attore})", not res.success)
        check(f"il rifiuto indirizza su .dndworld (tentativo da {attore})",
              ".dndworld" in res.error)

    res = backend.send_command(world.id, "dev-master", perm.CMD_DEVICE_TRANSFER_ISSUE,
                                {"device_id": "dev-inesistente"})
    check("nessun codice per un dispositivo che non è membro", not res.success)

    res = backend.send_command(world.id, "dev-master", perm.CMD_DEVICE_TRANSFER_ISSUE, {})
    check("payload senza device_id viene rifiutato", not res.success)

    # Revoca
    res = backend.send_command(world.id, "dev-p1", perm.CMD_DEVICE_TRANSFER_REVOKE,
                                {"device_id": "dev-p1"})
    check("il giocatore può revocare il proprio codice", res.success)
    res = backend.send_command(world.id, "dev-p1", perm.CMD_DEVICE_TRANSFER_REVOKE,
                                {"device_id": "dev-p1"})
    check("revocare due volte segnala che non c'è nulla da revocare", not res.success)


# ---------------------------------------------------------------------------
# [3] La riassegnazione
# ---------------------------------------------------------------------------

def test_rebind() -> None:
    print("\n[3] rebind_device — cosa si sposta e cosa NON si sposta")

    old, new = "dev-vecchio", "dev-nuovo"
    world = _make_world("Mondo Rebind", owner_device="dev-owner")
    membro = _add_member(world.id, old, "Thorin")
    _add_member(world.id, "dev-altro", "Legolas")

    attiva1 = _make_instance(world.id, old, "Thorin Scudodiferro")
    attiva2 = _make_instance(world.id, old, "Thorin il Secondo")
    archiviata = _make_instance(world.id, old, "Thorin Caduto", archived=True)
    di_un_altro = _make_instance(world.id, "dev-altro", "Legolas Fogliaverde")

    nota_tutti = master_repo.create_master_campaign_note(
        category="npc", name="Nota per tutti", world_id=world.id, visibility="all",
    )
    nota_con = master_repo.create_master_campaign_note(
        category="npc", name="Nota per Thorin", world_id=world.id,
        visibility="selected",
        visible_to_device_ids=json.dumps([old, "dev-altro"]),
    )
    nota_senza = master_repo.create_master_campaign_note(
        category="npc", name="Nota per Legolas", world_id=world.id,
        visibility="selected", visible_to_device_ids=json.dumps(["dev-altro"]),
    )

    # Un secondo mondo che nomina lo STESSO device_id: non deve essere toccato,
    # quel dispositivo resta membro là.
    altro_mondo = _make_world("Mondo Estraneo", owner_device="dev-owner")
    _add_member(altro_mondo.id, old, "Thorin")
    nota_altro_mondo = master_repo.create_master_campaign_note(
        category="npc", name="Nota altrove", world_id=altro_mondo.id,
        visibility="selected", visible_to_device_ids=json.dumps([old]),
    )
    istanza_altro_mondo = _make_instance(altro_mondo.id, old, "Thorin Altrove")

    # Provenienza del bottino: dato storico, non si riscrive.
    bottino = loot_repo.create_entry(
        "party", "item", name="Spada del test", world_id=world.id,
        added_by_device_id=old,
    )

    # Richiesta di rientro pendente per l'istanza archiviata.
    richiesta = world_repo.create_rejoin_request(
        world.id, archiviata.id, old, "Thorin", "frozen", "{}",
    )
    assert richiesta is not None

    eventi_prima = world_repo.get_events_since(world.id, 0)
    attori_prima = [e.actor_device_id for e in eventi_prima]
    check("il mondo ha già eventi di giornale prima del rebind", len(eventi_prima) > 0)

    riepilogo = world_transfer_repo.rebind_device(world.id, old, new)
    check("rebind_device riesce", riepilogo is not None)
    assert riepilogo is not None

    # -- l'appartenenza --------------------------------------------------
    vecchio_membro = world_repo.get_member(world.id, old)
    nuovo_membro = world_repo.get_member(world.id, new)
    check("il vecchio device_id non è più membro", vecchio_membro is None)
    check("il nuovo device_id è membro", nuovo_membro is not None)
    assert nuovo_membro is not None
    check("la riga del membro mantiene lo STESSO id (le repliche fanno upsert per id)",
          nuovo_membro.id == membro.id)
    check("il ruolo è preservato", nuovo_membro.role == membro.role)
    check("il nome visualizzato è preservato",
          nuovo_membro.display_name == "Thorin")
    check("is_connected è azzerato", nuovo_membro.is_connected is False)
    check("il riepilogo riporta il nome per l'evento di giornale",
          riepilogo["display_name"] == "Thorin")

    # -- le istanze ------------------------------------------------------
    check("l'istanza attiva 1 ha il nuovo proprietario",
          character_repo.get_by_id(attiva1.id).owner_device_id == new)
    check("l'istanza attiva 2 ha il nuovo proprietario",
          character_repo.get_by_id(attiva2.id).owner_device_id == new)
    check("ANCHE l'istanza archiviata ha il nuovo proprietario",
          character_repo.get_by_id(archiviata.id).owner_device_id == new)
    check("l'istanza archiviata resta archiviata",
          character_repo.get_by_id(archiviata.id).world_instance_archived is True)
    check("il riepilogo conta tutte e 3 le istanze",
          riepilogo["characters"] == 3)
    check("l'istanza di un ALTRO membro non è toccata",
          character_repo.get_by_id(di_un_altro.id).owner_device_id == "dev-altro")
    check("l'istanza nell'altro mondo non è toccata",
          character_repo.get_by_id(istanza_altro_mondo.id).owner_device_id == old)

    # -- la visibilità delle note ----------------------------------------
    ids_con = _note_ids(world.id, nota_con.id)
    check("la nota condivisa col giocatore ora nomina il nuovo dispositivo",
          new in ids_con)
    check("...e non nomina più il vecchio", old not in ids_con)
    check("...e conserva gli altri destinatari", "dev-altro" in ids_con)
    check("...preservando l'ordine", ids_con == [new, "dev-altro"])
    check("la nota condivisa con un altro membro non è toccata",
          _note_ids(world.id, nota_senza.id) == ["dev-altro"])
    check("la nota visibile a tutti non è toccata",
          master_repo.get_master_campaign_note_by_id(nota_tutti.id).visibility == "all")
    check("la nota di un ALTRO mondo non è toccata",
          _note_ids(altro_mondo.id, nota_altro_mondo.id) == [old])
    check("il riepilogo conta una sola nota rimappata",
          riepilogo["notes_remapped"] == 1)

    # -- le richieste di rientro ------------------------------------------
    aggiornata = world_repo.get_rejoin_request(richiesta.id)
    check("la richiesta di rientro pendente segue il nuovo dispositivo",
          aggiornata.requested_by == new)
    check("il riepilogo conta la richiesta di rientro",
          riepilogo["rejoin_requests"] == 1)

    # -- ciò che NON si tocca ---------------------------------------------
    voci = [v for v in loot_repo.get_entries("party", world.id) if v.id == bottino.id]
    check("la provenienza del bottino resta il VECCHIO dispositivo (dato storico)",
          len(voci) == 1 and voci[0].added_by_device_id == old)

    eventi_dopo = world_repo.get_events_since(world.id, 0)
    attori_dopo = [e.actor_device_id for e in eventi_dopo[:len(eventi_prima)]]
    check("gli attori degli eventi già scritti non sono riscritti",
          attori_dopo == attori_prima)

    mondo = world_repo.get_world(world.id)
    check("worlds.owner_device_id non è toccato",
          mondo.owner_device_id == "dev-owner")

    # -- casi limite -------------------------------------------------------
    check("riassegnare un dispositivo non membro fallisce",
          world_transfer_repo.rebind_device(world.id, "dev-mai-visto", "dev-x") is None)
    check("riassegnare verso un dispositivo GIÀ membro fallisce",
          world_transfer_repo.rebind_device(world.id, new, "dev-altro") is None)
    check("vecchio e nuovo dispositivo coincidenti: rifiutato",
          world_transfer_repo.rebind_device(world.id, new, new) is None)
    check("il membro è ancora integro dopo i tre tentativi rifiutati",
          world_repo.get_member(world.id, new) is not None
          and world_repo.get_member(world.id, "dev-altro") is not None)


def test_rebind_atomico() -> None:
    print("\n[4] rebind_device è davvero una transazione")

    old, new = "dev-tx-vecchio", "dev-tx-nuovo"
    world = _make_world("Mondo Transazione", owner_device="dev-owner")
    _add_member(world.id, old, "Gimli")
    istanza = _make_instance(world.id, old, "Gimli Spaccateste")
    nota = master_repo.create_master_campaign_note(
        category="npc", name="Nota Gimli", world_id=world.id,
        visibility="selected", visible_to_device_ids=json.dumps([old]),
    )

    # Fallimento iniettato DOPO che i primi UPDATE della transazione sono già
    # passati: se il rollback non ci fosse, il membro risulterebbe spostato e
    # le note no.
    originale = world_transfer_repo._remap_note_visibility

    def _esplode(*args, **kwargs):
        raise sqlite3.OperationalError("fallimento iniettato dal test")

    world_transfer_repo._remap_note_visibility = _esplode
    try:
        esito = world_transfer_repo.rebind_device(world.id, old, new)
    finally:
        world_transfer_repo._remap_note_visibility = originale

    check("un fallimento a metà transazione restituisce None", esito is None)
    check("il membro NON è stato spostato", world_repo.get_member(world.id, old) is not None)
    check("il nuovo dispositivo NON è membro", world_repo.get_member(world.id, new) is None)
    check("l'istanza NON ha cambiato proprietario",
          character_repo.get_by_id(istanza.id).owner_device_id == old)
    check("la visibilità della nota è intatta",
          _note_ids(world.id, nota.id) == [old])

    # E dopo il ripristino funziona: la transazione fallita non ha lasciato
    # sporcizia né lock (l'invariante di test_connessioni_db.py).
    check("dopo il fallimento un rebind pulito riesce",
          world_transfer_repo.rebind_device(world.id, old, new) is not None)


# ---------------------------------------------------------------------------
# [5] Il protocollo, su socket veri
# ---------------------------------------------------------------------------

def test_protocollo() -> None:
    print("\n[5] POST /join con transfer_code — socket reali su 127.0.0.1")

    world = _make_world("Mondo Rete", owner_device="dev-host-owner")
    _add_member(world.id, "dev-telefono-vecchio", "Thorin")
    istanza_a = _make_instance(world.id, "dev-telefono-vecchio", "Thorin A")
    istanza_b = _make_instance(world.id, "dev-telefono-vecchio", "Thorin B")
    _make_instance(world.id, "dev-telefono-vecchio", "Thorin Archiviato", archived=True)

    host = WorldHostServer(world.id, long_poll_timeout=2.0, announce=False)
    port = host.start()
    try:
        client = RemoteBackend("127.0.0.1", port, "dev-telefono-nuovo")
        info = client.check_world()
        assert info is not None
        check("GET /world annuncia la capacità device_transfer",
              protocol.FEATURE_DEVICE_TRANSFER in (info.get("features") or []))
        check("GET /world NON alza la versione di protocollo",
              info.get("protocol_version") == 1)
        client.world_id = world.id

        # Codice inesistente, scaduto, revocato e già usato devono dare tutti lo
        # STESSO messaggio: chi prova codici non deve capire quale dei quattro.
        host.reset_join_rate_limit_for_tests()
        esito = client.join(world.join_code, "", "Thorin", transfer_code="AAAAAAAA")
        check("un codice inesistente è rifiutato", esito.status == "error")
        messaggio_generico = esito.error
        check("il messaggio non rivela il motivo",
              "non valido o scaduto" in messaggio_generico)

        t = world_transfer_repo.issue_transfer(
            world.id, "dev-telefono-vecchio", "Thorin", "dev-telefono-vecchio",
        )
        assert t is not None
        world_transfer_repo.revoke_transfer(t.id)
        host.reset_join_rate_limit_for_tests()
        esito = client.join(world.join_code, "", "Thorin", transfer_code=t.code)
        check("un codice revocato dà lo stesso messaggio di uno inesistente",
              esito.status == "error" and esito.error == messaggio_generico)

        # Lo stesso dispositivo del membro: non ha senso trasferire su sé stesso.
        t = world_transfer_repo.issue_transfer(
            world.id, "dev-telefono-vecchio", "Thorin", "dev-telefono-vecchio",
        )
        assert t is not None
        stesso = RemoteBackend("127.0.0.1", port, "dev-telefono-vecchio")
        stesso.world_id = world.id
        host.reset_join_rate_limit_for_tests()
        esito = stesso.join(world.join_code, "", "Thorin", transfer_code=t.code)
        check("riscattare dal dispositivo stesso è rifiutato", esito.status == "error")
        check("...con un messaggio che lo spiega",
              "già il dispositivo registrato" in esito.error)

        # Un dispositivo già membro con un'altra identità: UNIQUE(world_id,
        # device_id) impedisce di fondere due appartenenze.
        _add_member(world.id, "dev-gia-membro", "Legolas")
        gia_membro = RemoteBackend("127.0.0.1", port, "dev-gia-membro")
        gia_membro.world_id = world.id
        host.reset_join_rate_limit_for_tests()
        esito = gia_membro.join(world.join_code, "", "Legolas", transfer_code=t.code)
        check("un dispositivo già membro non può riscattare un codice",
              esito.status == "error")
        check("...con un messaggio che dice di uscire prima",
              "già membro" in esito.error)

        # Il caso buono: accodato, in attesa del master. Il codice NON basta.
        host.reset_join_rate_limit_for_tests()
        esito = client.join(world.join_code, "", "Thorin (tablet)", transfer_code=t.code)
        check("un codice valido mette la richiesta in attesa",
              esito.status == "pending")
        check("l'host dichiara che si tratta di un trasferimento",
              esito.kind == "transfer")
        check("il codice NON è ancora stato consumato: serve l'approvazione",
              world_transfer_repo.get_pending_transfer_by_code(world.id, t.code) is not None)
        check("il vecchio dispositivo è ancora membro finché il master non approva",
              world_repo.get_member(world.id, "dev-telefono-vecchio") is not None)

        in_attesa = host.list_pending()
        check("il master vede una richiesta in sospeso", len(in_attesa) == 1)
        check("la richiesta è marcata come trasferimento",
              bool(in_attesa[0].transfer_id))
        check("la richiesta porta il nome del membro da sostituire",
              in_attesa[0].transfer_member_name == "Thorin")

        # -- il master approva ------------------------------------------------
        check("l'approvazione riesce", host.approve(in_attesa[0].id) is True)
        check("il codice è stato consumato",
              world_transfer_repo.get_transfer(t.id).status
              == world_transfer_repo.STATUS_REDEEMED)
        check("il vecchio dispositivo non è più membro",
              world_repo.get_member(world.id, "dev-telefono-vecchio") is None)
        check("il nuovo dispositivo è membro",
              world_repo.get_member(world.id, "dev-telefono-nuovo") is not None)

        eventi = world_repo.get_events_since(world.id, 0)
        riscatti = [e for e in eventi if e.kind == perm.DEVICE_TRANSFER_REDEEM_KIND]
        check("è stato scritto esattamente un evento di riscatto", len(riscatti) == 1)
        payload = json.loads(riscatti[0].payload)
        check("l'evento porta il vecchio e il nuovo dispositivo",
              payload.get("old_device_id") == "dev-telefono-vecchio"
              and payload.get("new_device_id") == "dev-telefono-nuovo")
        check("l'evento conta i personaggi spostati (3, archiviato incluso)",
              payload.get("characters") == 3)
        check("l'evento NON contiene il codice", t.code not in riscatti[0].payload)

        # -- il nuovo dispositivo scarica i propri personaggi -----------------
        esito = client.poll_join_status(in_attesa[0].id)
        check("il nuovo dispositivo riceve l'approvazione", esito.status == "approved")
        snapshot = client.get_snapshot()
        check("lo snapshot risponde al nuovo dispositivo", snapshot is not None
              and isinstance(snapshot.get("characters"), list))
        nomi = sorted(
            c.get("character", {}).get("name", "")
            for c in (snapshot.get("characters") or [])
        )
        check(f"lo snapshot porta le 2 istanze ATTIVE del membro trasferito ({nomi})",
              nomi == ["Thorin A", "Thorin B"])

        # -- il vecchio dispositivo ------------------------------------------
        vecchio = RemoteBackend("127.0.0.1", port, "dev-telefono-vecchio")
        vecchio.world_id = world.id
        host.reset_join_rate_limit_for_tests()
        esito = vecchio.join(world.join_code, "", "Thorin")
        check("il vecchio dispositivo viene rifiutato", esito.status == "error")
        check("...con reason='transferred_away', non con 'PIN errato'",
              esito.reason == "transferred_away")
        check("...e un messaggio che spiega davvero cosa è successo",
              "trasferito su un altro dispositivo" in esito.error)
    finally:
        host.stop()

    # La replica del vecchio dispositivo si marca da sé quando vede l'evento.
    locale = world_repo.get_world(world.id)
    evento = WorldEvent(
        seq=999, world_id=locale.id, actor_device_id="dev-telefono-nuovo",
        kind=perm.DEVICE_TRANSFER_REDEEM_KIND, target_type="member",
        payload=json.dumps({"old_device_id": "dev-telefono-vecchio",
                            "new_device_id": "dev-telefono-nuovo"}),
    )

    class _FintoBackend:
        def __init__(self, device_id): self.device_id = device_id

    check("prima dell'evento il mondo non è marcato come trasferito",
          world_sync.is_world_transferred_away(locale.id) is False)
    world_sync.apply_event_to_replica(locale.id, evento, _FintoBackend("dev-un-terzo"))
    check("su un TERZO dispositivo l'evento non marca nulla",
          world_sync.is_world_transferred_away(locale.id) is False)
    world_sync.apply_event_to_replica(locale.id, evento,
                                       _FintoBackend("dev-telefono-vecchio"))
    check("sul VECCHIO dispositivo l'evento marca il mondo come trasferito",
          world_sync.is_world_transferred_away(locale.id) is True)
    check("il token di sessione della replica è stato azzerato",
          world_repo.get_world(locale.id).session_token == "")


def test_qr() -> None:
    print("\n[6] Il QR di trasferimento è un formato SEPARATO da quello d'ingresso")

    from network import qr_join

    testo = qr_join.build_transfer_text(
        "Mondo Rete", "192.168.1.7", 8765, "ABCDEF", "JKXCM8FX",
    )
    letto = qr_join.parse_transfer_text(testo)
    check("il QR di trasferimento si rilegge", letto is not None)
    assert letto is not None
    check("...con host e porta corretti",
          letto["host"] == "192.168.1.7" and letto["port"] == 8765)
    check("...con il codice del mondo", letto["join_code"] == "ABCDEF")
    check("...con il codice di trasferimento", letto["transfer_code"] == "JKXCM8FX")
    check("...e il nome del mondo per la conferma in UI",
          letto["world_name"] == "Mondo Rete")
    check("il QR di trasferimento NON contiene il PIN", "PIN" not in testo)

    # Il punto centrale della scelta di tenere due formati distinti: il parser
    # dell'ingresso non deve accettare un QR di trasferimento, e viceversa.
    check("parse_join_text rifiuta un QR di trasferimento",
          qr_join.parse_join_text(testo) is None)
    ingresso = qr_join.build_join_text("Mondo Rete", "192.168.1.7", 8765, "ABCDEF", "123456")
    check("parse_transfer_text rifiuta un QR d'ingresso",
          qr_join.parse_transfer_text(ingresso) is None)

    # Lo scanner in-app usa il riconoscitore combinato.
    check("parse_any_join_text riconosce l'ingresso e lo dichiara",
          (qr_join.parse_any_join_text(ingresso) or {}).get("kind") == "join")
    check("parse_any_join_text riconosce il trasferimento e lo dichiara",
          (qr_join.parse_any_join_text(testo) or {}).get("kind") == "transfer")
    check("parse_any_join_text rifiuta un QR estraneo",
          qr_join.parse_any_join_text("https://example.com") is None)
    check("parse_any_join_text rifiuta il testo vuoto",
          qr_join.parse_any_join_text("") is None)

    # Fail-closed: manca un campo obbligatorio → None, mai un dizionario a metà.
    troncato = "\n".join(testo.splitlines()[:-1])
    check("un QR di trasferimento senza il codice è rifiutato",
          qr_join.parse_transfer_text(troncato) is None)
    porta_rotta = testo.replace("Porta: 8765", "Porta: 99999")
    check("una porta fuori intervallo è rifiutata",
          qr_join.parse_transfer_text(porta_rotta) is None)


def test_ui_si_costruisce() -> None:
    """
    La UI di questo progetto non ha una batteria di test comportamentali (nessun
    driver Flet headless): qui si verifica ciò che è verificabile senza inventare
    garanzie — che i costruttori nuovi producano controlli senza sollevare, e che
    le decisioni di VISIBILITÀ (chi vede il pulsante del codice) siano quelle
    volute. Il resto — che il dialogo sia leggibile, che il QR si inquadri — lo
    verifica Davide sul dispositivo reale.
    """
    print("\n[7] La UI nuova si costruisce, e mostra i comandi a chi deve")

    from ui.views.world.world_view import WorldsView
    from data.models import WorldMember

    world = _make_world("Mondo UI", owner_device="dev-owner-ui")
    _add_member(world.id, "dev-master-ui", "Co-Master", role="master")
    _add_member(world.id, "dev-p-ui", "Thorin")

    vista = WorldsView(on_back_to_home=lambda: None)
    vista.device_id = "dev-master-ui"

    owner = world_repo.get_member(world.id, "dev-owner-ui")
    master = world_repo.get_member(world.id, "dev-master-ui")
    giocatore = world_repo.get_member(world.id, "dev-p-ui")

    def _ha_pulsante_trasferimento(riga) -> bool:
        import flet as ft
        for c in getattr(riga, "controls", []):
            if isinstance(c, ft.IconButton) and c.icon == ft.Icons.PHONELINK_SETUP:
                return True
        return False

    riga_giocatore = vista._member_row(world, giocatore, perm.ROLE_MASTER)
    check("il master vede il pulsante del codice sulla riga di un giocatore",
          _ha_pulsante_trasferimento(riga_giocatore))

    riga_owner = vista._member_row(world, owner, perm.ROLE_MASTER)
    check("nessun pulsante del codice sulla riga dell'OWNER",
          not _ha_pulsante_trasferimento(riga_owner))

    riga_se_stesso = vista._member_row(world, master, perm.ROLE_MASTER)
    check("il master vede il pulsante anche per sé stesso (cambio del proprio telefono)",
          _ha_pulsante_trasferimento(riga_se_stesso))

    # Un giocatore semplice: solo per sé, mai per un altro.
    vista.device_id = "dev-p-ui"
    check("un giocatore vede il pulsante sulla propria riga",
          _ha_pulsante_trasferimento(
              vista._member_row(world, giocatore, perm.ROLE_PLAYER)))
    check("un giocatore NON vede il pulsante sulla riga di un altro membro",
          not _ha_pulsante_trasferimento(
              vista._member_row(world, master, perm.ROLE_PLAYER)))

    # La riga di richiesta in sospeso deve distinguere un trasferimento.
    from network.host_server import PendingJoinRequest
    normale = PendingJoinRequest(id="r1", device_id="dev-x", display_name="Gimli")
    trasferimento = PendingJoinRequest(
        id="r2", device_id="dev-y", display_name="Thorin (tablet)",
        transfer_id="t1", transfer_member_name="Thorin",
    )
    riga_n = vista._pending_request_row(world, normale)
    riga_t = vista._pending_request_row(world, trasferimento)

    def _testi(controllo) -> str:
        """Tutti i testi dell'albero. Scende sia in `.controls` (Row/Column) sia
        in `.content` (Container/Card): `d.section()` avvolge in un Container,
        quindi seguire solo `.controls` non troverebbe nulla."""
        import flet as ft
        out: list[str] = []

        def _visita(c):
            if isinstance(c, ft.Text) and c.value:
                out.append(c.value)
            for figlio in (getattr(c, "controls", None) or []):
                _visita(figlio)
            interno = getattr(c, "content", None)
            if interno is not None and not isinstance(interno, str):
                _visita(interno)

        _visita(controllo)
        return " | ".join(out)

    check("la richiesta normale mostra solo il nome",
          "Gimli" in _testi(riga_n) and "spostare" not in _testi(riga_n))
    check("la richiesta di trasferimento spiega che è uno scambio di identità",
          "spostare il personaggio di Thorin" in _testi(riga_t))
    check("...e avverte che il vecchio dispositivo perderà l'accesso",
          "perderà l'accesso" in _testi(riga_t))

    # Il banner del dispositivo sostituito.
    banner = vista._transferred_away_banner(world)
    check("il banner del mondo trasferito si costruisce", banner is not None)
    check("...e dice che resta una copia di sola lettura",
          "sola lettura" in _testi(banner))


def main() -> int:
    init_db()
    test_codice()
    test_permessi()
    test_rebind()
    test_rebind_atomico()
    test_protocollo()
    test_qr()
    test_ui_si_costruisce()
    print("\n" + "=" * 70)
    print(f"Controlli passati: {_PASS} — falliti: {len(_FAIL)}")
    if _FAIL:
        for f in _FAIL:
            print(f"  - {f}")
        return 1
    print("Tutti i controlli passati.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
