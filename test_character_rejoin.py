"""
Verifica di "Richiesta di rientro" (2026-08-12) — un personaggio archiviato
(espulso via `member.kick`, o rimosso singolarmente via
`CMD_CHARACTER_INSTANCE_REMOVE`) non torna mai visibile al master in
automatico: il proprietario deve chiedere il rientro
(`CMD_CHARACTER_REJOIN_REQUEST`), il master/owner deve accettare o
rifiutare (`CMD_CHARACTER_REJOIN_RESPOND`) — simmetrico all'ingresso in un
mondo via LAN (PIN + approvazione del master), richiesto esplicitamente da
Davide dopo aver notato che nessun punto del codice riattivava mai davvero
un'istanza archiviata nonostante alcuni testi/commenti lo dessero per
scontato (verificato con grep sull'intero repo prima di scrivere questa
feature).

Due modalità (Davide, in revisione: "il personaggio rimosso rimane statico
... quello che il giocatore ha in locale potrebbe cambiare... dobbiamo
gestire questa cosa"): `mode="frozen"` riprende l'istanza esattamente come
fu archiviata; `mode="refresh_from_local"` sovrascrive il CONTENUTO con lo
stato attuale del personaggio locale di origine, preservando identità e
collegamento al mondo dell'istanza.

Cinque parti:

[1] Handler `_handle_character_rejoin_request` — successo (entrambe le
    modalità), fail-closed (non proprietario, non archiviato, modalità
    invalida, export invalido/non locale, duplicato).

[2] Handler `_handle_character_rejoin_respond` — accetta (entrambe le
    modalità: l'istanza torna visibile al master, col contenuto giusto),
    rifiuta (resta archiviata), fail-closed (richiesta inesistente/già
    gestita, solo master/owner può rispondere), le due race guard (istanza
    già riattivata da un altro accept, proprietario non più membro).

[3] Propagazione di replica — `apply_event_to_replica` per entrambi gli
    eventi, nessun crash senza trasporto, scrive/risolve la richiesta sulla
    replica locale.

[4] `create_or_resume_instance` su un'istanza archiviata — MAI un "resume"
    silenzioso (il bug del "personaggio fantasma" trovato in fase di
    analisi): `archived=True`, `success=False`, nessuna nuova riga creata.

[5] UI — sezione master "Richieste di rientro" in `WorldsView` (click reale
    su Accetta/Rifiuta) e pulsante "Richiedi rientro" in `HomeView`
    ("Rimossi dai mondi").

Eseguire con:
    PYTHONPATH=".venv/lib/python3.13/site-packages:." python3 test_character_rejoin.py
"""

from __future__ import annotations

import os
import sys
import tempfile

_TMP_HOME = tempfile.mkdtemp(prefix="dnd_character_rejoin_")
os.environ["HOME"] = _TMP_HOME

import flet as ft  # noqa: E402

from data.database import init_db  # noqa: E402
from data.models import Character  # noqa: E402
from data.repositories import character_export, character_repo, world_repo  # noqa: E402
from core import character_instances as ci  # noqa: E402
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


def _make_character(name: str, level: int = 1) -> Character:
    c = Character(
        name=name, class_name="Guerriero", race="Umano", level=level,
        hit_dice_type=10, hit_dice_total=level, hit_dice_remaining=level,
        str_score=10, dex_score=10, con_score=10, int_score=10,
        wis_score=10, cha_score=10, hp_max=10, hp_current=10,
    )
    character_repo.create(c)
    return c


def _make_archived_instance(world_id: str, owner_device_id: str, *,
                             origin_id: str = "", name: str = "Rimosso") -> Character:
    """Fixture: un'istanza già archiviata in `world_id`, come se fosse
    stata espulsa/rimossa in passato — scrittura diretta minimale, stesso
    approccio già in uso nelle altre batterie di test di questo progetto."""
    c = _make_character(name)
    c.world_id = world_id
    c.origin_character_id = origin_id
    c.owner_device_id = owner_device_id
    c.world_instance_archived = True
    character_repo.update(c)
    return character_repo.get_by_id(c.id)


# ---------------------------------------------------------------------------
# [1] CMD_CHARACTER_REJOIN_REQUEST
# ---------------------------------------------------------------------------

def test_richiesta_di_rientro() -> None:
    print("\n[1] CMD_CHARACTER_REJOIN_REQUEST — creazione, fail-closed, anti-duplicati")

    world = world_repo.create_world("Mondo Rientro 1", "dev-owner-1", "Il Master")
    assert world is not None
    world_repo.join_world_by_code(world.join_code, "dev-player-1", "Il Giocatore")

    instance = _make_archived_instance(world.id, "dev-player-1")
    backend = LocalBackend()

    # -- successo, mode frozen (default) --
    result = _send(backend, world.id, "dev-player-1", perm.CMD_CHARACTER_REJOIN_REQUEST,
                    {}, target_type="character", target_id=instance.id)
    check("richiesta inviata con successo (mode frozen di default)", result.success)
    check("produce un evento", result.event is not None)
    check("kind giusto", result.event.kind == perm.CMD_CHARACTER_REJOIN_REQUEST)

    pending = world_repo.get_pending_rejoin_requests(world.id)
    check("una richiesta pending nel mondo", len(pending) == 1)
    check("mode frozen registrato", pending[0].mode == "frozen")
    check("character_id giusto", pending[0].character_id == instance.id)
    check("requested_by giusto", pending[0].requested_by == "dev-player-1")

    # -- anti-duplicati --
    dup = _send(backend, world.id, "dev-player-1", perm.CMD_CHARACTER_REJOIN_REQUEST,
                {}, target_type="character", target_id=instance.id)
    check("una seconda richiesta sullo stesso personaggio viene rifiutata", not dup.success)
    check("resta una sola richiesta pending",
          len(world_repo.get_pending_rejoin_requests(world.id)) == 1)

    # pulizia per i controlli successivi
    world_repo.resolve_rejoin_request(pending[0].id, "rejected")

    # -- non proprietario --
    result = _send(backend, world.id, "dev-player-2-non-owner", perm.CMD_CHARACTER_REJOIN_REQUEST,
                    {}, target_type="character", target_id=instance.id)
    check("un dispositivo diverso dal proprietario non può richiedere il rientro",
          not result.success)

    # -- non archiviato --
    active = _make_character("Attivo")
    active.world_id = world.id
    active.owner_device_id = "dev-player-1"
    character_repo.update(active)
    result = _send(backend, world.id, "dev-player-1", perm.CMD_CHARACTER_REJOIN_REQUEST,
                    {}, target_type="character", target_id=active.id)
    check("un personaggio NON archiviato viene rifiutato", not result.success)

    # -- modalità invalida --
    result = _send(backend, world.id, "dev-player-1", perm.CMD_CHARACTER_REJOIN_REQUEST,
                    {"mode": "qualcosa_a_caso"}, target_type="character", target_id=instance.id)
    check("una modalità invalida viene rifiutata", not result.success)

    # -- refresh_from_local: export mancante/malformato --
    result = _send(backend, world.id, "dev-player-1", perm.CMD_CHARACTER_REJOIN_REQUEST,
                    {"mode": "refresh_from_local"}, target_type="character", target_id=instance.id)
    check("refresh_from_local senza export viene rifiutato", not result.success)

    # -- refresh_from_local: export di un'ALTRA istanza di mondo (world_id valorizzato) --
    other_instance_export = character_export.export_character(active.id)
    result = _send(backend, world.id, "dev-player-1", perm.CMD_CHARACTER_REJOIN_REQUEST,
                    {"mode": "refresh_from_local", "export": other_instance_export},
                    target_type="character", target_id=instance.id)
    check("refresh_from_local con export NON locale (world_id valorizzato) viene rifiutato",
          not result.success)

    # -- refresh_from_local: successo con un vero export locale --
    origin = _make_character("Origine Locale", level=3)
    origin_export = character_export.export_character(origin.id)
    result = _send(backend, world.id, "dev-player-1", perm.CMD_CHARACTER_REJOIN_REQUEST,
                    {"mode": "refresh_from_local", "export": origin_export},
                    target_type="character", target_id=instance.id)
    check("refresh_from_local con export locale valido riesce", result.success)
    pending2 = world_repo.get_pending_rejoin_request_for_character(instance.id)
    check("la richiesta pending ha mode refresh_from_local",
          pending2 is not None and pending2.mode == "refresh_from_local")
    if pending2 is not None:
        world_repo.resolve_rejoin_request(pending2.id, "rejected")

    check("il comando è nella matrice player-owned",
          perm.CMD_CHARACTER_REJOIN_REQUEST in perm.PLAYER_OWNED_COMMANDS)
    check("il comando NON muta mai il personaggio direttamente",
          perm.CMD_CHARACTER_REJOIN_REQUEST not in perm.CHARACTER_MUTATING_COMMANDS)


# ---------------------------------------------------------------------------
# [2] CMD_CHARACTER_REJOIN_RESPOND
# ---------------------------------------------------------------------------

def test_risposta_master_frozen() -> None:
    print("\n[2a] CMD_CHARACTER_REJOIN_RESPOND — mode frozen, accetta")

    world = world_repo.create_world("Mondo Rientro 2a", "dev-owner-2a", "Il Master")
    assert world is not None
    world_repo.join_world_by_code(world.join_code, "dev-player-2a", "Il Giocatore")
    instance = _make_archived_instance(world.id, "dev-player-2a", name="Congelato")

    backend = LocalBackend()
    req = _send(backend, world.id, "dev-player-2a", perm.CMD_CHARACTER_REJOIN_REQUEST,
                {}, target_type="character", target_id=instance.id)
    assert req.success and req.event is not None
    import json
    request_id = json.loads(req.event.payload)["request_id"]

    check("non ancora visibile al master prima dell'accettazione",
          not any(c.id == instance.id
                  for c in character_repo.get_master_visible_characters(world.id)))

    result = _send(backend, world.id, "dev-owner-2a", perm.CMD_CHARACTER_REJOIN_RESPOND,
                    {"request_id": request_id, "accept": True},
                    target_type="character", target_id=instance.id)
    check("accettazione riuscita", result.success)
    check("produce un evento", result.event is not None)
    check("kind giusto", result.event is not None
          and result.event.kind == perm.CMD_CHARACTER_REJOIN_RESPOND)

    refreshed = character_repo.get_by_id(instance.id)
    check("l'istanza NON è più archiviata", not refreshed.world_instance_archived)
    check("il nome è rimasto quello con cui fu rimossa (frozen)", refreshed.name == "Congelato")
    check("ora è visibile al master",
          any(c.id == instance.id
              for c in character_repo.get_master_visible_characters(world.id)))

    resolved = world_repo.get_rejoin_request(request_id)
    check("la richiesta è ora 'accepted'", resolved is not None and resolved.status == "accepted")


def test_risposta_master_refresh_from_local() -> None:
    print("\n[2b] CMD_CHARACTER_REJOIN_RESPOND — mode refresh_from_local, accetta")

    world = world_repo.create_world("Mondo Rientro 2b", "dev-owner-2b", "Il Master")
    assert world is not None
    world_repo.join_world_by_code(world.join_code, "dev-player-2b", "Il Giocatore")

    origin = _make_character("Origine 2b", level=1)
    instance = _make_archived_instance(world.id, "dev-player-2b", origin_id=origin.id,
                                        name="Vecchio Nome Istanza")

    # Il personaggio locale di origine è cambiato NEL FRATTEMPO (esattamente
    # lo scenario sollevato da Davide): livello 1 -> 5.
    origin.level = 5
    character_repo.update(origin)
    origin_export = character_export.export_character(origin.id)

    backend = LocalBackend()
    req = _send(backend, world.id, "dev-player-2b", perm.CMD_CHARACTER_REJOIN_REQUEST,
                {"mode": "refresh_from_local", "export": origin_export},
                target_type="character", target_id=instance.id)
    assert req.success and req.event is not None
    import json
    request_id = json.loads(req.event.payload)["request_id"]

    result = _send(backend, world.id, "dev-owner-2b", perm.CMD_CHARACTER_REJOIN_RESPOND,
                    {"request_id": request_id, "accept": True},
                    target_type="character", target_id=instance.id)
    check("accettazione riuscita", result.success)

    refreshed = character_repo.get_by_id(instance.id)
    check("l'istanza NON è più archiviata", not refreshed.world_instance_archived)
    check("il CONTENUTO riflette lo stato locale AGGIORNATO (livello 5, non 1)",
          refreshed.level == 5)
    check("il nome viene dall'export locale (Origine 2b), non dal vecchio nome dell'istanza",
          refreshed.name == "Origine 2b")
    check("l'id dell'istanza NON cambia (stesso record, nessun fantasma/duplicato)",
          refreshed.id == instance.id)
    check("world_id dell'istanza preservato (non quello, vuoto, dell'export locale)",
          refreshed.world_id == world.id)
    check("origin_character_id dell'istanza preservato",
          refreshed.origin_character_id == origin.id)
    check("owner_device_id dell'istanza preservato",
          refreshed.owner_device_id == "dev-player-2b")

    same_world_chars = [c for c in character_repo.get_master_visible_characters(world.id)]
    check("un solo personaggio visibile in questo mondo (nessun doppione creato)",
          len(same_world_chars) == 1)


def test_risposta_master_rifiuta() -> None:
    print("\n[2c] CMD_CHARACTER_REJOIN_RESPOND — rifiuta, resta archiviato")

    world = world_repo.create_world("Mondo Rientro 2c", "dev-owner-2c", "Il Master")
    assert world is not None
    world_repo.join_world_by_code(world.join_code, "dev-player-2c", "Il Giocatore")
    instance = _make_archived_instance(world.id, "dev-player-2c")

    backend = LocalBackend()
    req = _send(backend, world.id, "dev-player-2c", perm.CMD_CHARACTER_REJOIN_REQUEST,
                {}, target_type="character", target_id=instance.id)
    import json
    request_id = json.loads(req.event.payload)["request_id"]

    result = _send(backend, world.id, "dev-owner-2c", perm.CMD_CHARACTER_REJOIN_RESPOND,
                    {"request_id": request_id, "accept": False},
                    target_type="character", target_id=instance.id)
    check("rifiuto riuscito", result.success)
    check("l'istanza RESTA archiviata", character_repo.get_by_id(instance.id).world_instance_archived)
    resolved = world_repo.get_rejoin_request(request_id)
    check("la richiesta è ora 'rejected'", resolved is not None and resolved.status == "rejected")

    # Dopo un rifiuto il giocatore può richiedere di nuovo (nessun blocco permanente).
    req2 = _send(backend, world.id, "dev-player-2c", perm.CMD_CHARACTER_REJOIN_REQUEST,
                 {}, target_type="character", target_id=instance.id)
    check("dopo un rifiuto è possibile inviare una nuova richiesta", req2.success)


def test_risposta_master_fail_closed_e_race() -> None:
    print("\n[2d] CMD_CHARACTER_REJOIN_RESPOND — fail-closed e race condition")

    world = world_repo.create_world("Mondo Rientro 2d", "dev-owner-2d", "Il Master")
    assert world is not None
    world_repo.join_world_by_code(world.join_code, "dev-player-2d", "Il Giocatore")
    instance = _make_archived_instance(world.id, "dev-player-2d")

    backend = LocalBackend()
    req = _send(backend, world.id, "dev-player-2d", perm.CMD_CHARACTER_REJOIN_REQUEST,
                {}, target_type="character", target_id=instance.id)
    import json
    request_id = json.loads(req.event.payload)["request_id"]

    # -- solo master/owner può rispondere --
    result = _send(backend, world.id, "dev-player-2d", perm.CMD_CHARACTER_REJOIN_RESPOND,
                    {"request_id": request_id, "accept": True},
                    target_type="character", target_id=instance.id)
    check("un giocatore (non master/owner) non può rispondere", not result.success)

    # -- richiesta inesistente --
    result = _send(backend, world.id, "dev-owner-2d", perm.CMD_CHARACTER_REJOIN_RESPOND,
                    {"request_id": "id-a-caso", "accept": True},
                    target_type="character", target_id=instance.id)
    check("una richiesta inesistente viene rifiutata", not result.success)

    # -- race: il richiedente non è più membro (espulso dopo l'invio) --
    world_repo.remove_member(world.id, "dev-player-2d")
    result = _send(backend, world.id, "dev-owner-2d", perm.CMD_CHARACTER_REJOIN_RESPOND,
                    {"request_id": request_id, "accept": True},
                    target_type="character", target_id=instance.id)
    check("accettare la richiesta di un proprietario non più membro viene rifiutato",
          not result.success)
    check("l'istanza RESTA archiviata (nessuna riammissione incoerente)",
          character_repo.get_by_id(instance.id).world_instance_archived)
    check("la richiesta è stata chiusa come 'expired', non resta pending per sempre",
          world_repo.get_rejoin_request(request_id).status == "expired")

    # -- richiesta già gestita --
    result = _send(backend, world.id, "dev-owner-2d", perm.CMD_CHARACTER_REJOIN_RESPOND,
                    {"request_id": request_id, "accept": True},
                    target_type="character", target_id=instance.id)
    check("rispondere di nuovo a una richiesta già chiusa viene rifiutato", not result.success)

    # -- race: doppio accept (istanza già riattivata) --
    world_repo.join_world_by_code(world.join_code, "dev-player-2d-bis", "Bis")
    instance2 = _make_archived_instance(world.id, "dev-player-2d-bis")
    req2 = _send(backend, world.id, "dev-player-2d-bis", perm.CMD_CHARACTER_REJOIN_REQUEST,
                 {}, target_type="character", target_id=instance2.id)
    request_id2 = json.loads(req2.event.payload)["request_id"]
    character_repo.unarchive_world_instance(instance2.id)  # simula un accept già avvenuto altrove
    result = _send(backend, world.id, "dev-owner-2d", perm.CMD_CHARACTER_REJOIN_RESPOND,
                    {"request_id": request_id2, "accept": True},
                    target_type="character", target_id=instance2.id)
    check("un secondo accept su un'istanza già riattivata non fallisce (no-op)", result.success)
    check("la richiesta duplicata viene comunque chiusa",
          world_repo.get_rejoin_request(request_id2).status != "pending")

    check("il comando è nella matrice master/owner",
          perm.CMD_CHARACTER_REJOIN_RESPOND in perm.MASTER_AND_OWNER_COMMANDS)
    check("il comando fa rimaterializzare la replica del proprietario",
          perm.CMD_CHARACTER_REJOIN_RESPOND in perm.CHARACTER_MUTATING_COMMANDS)
    check("il comando è protetto dal cooldown per-personaggio del master",
          perm.CMD_CHARACTER_REJOIN_RESPOND in perm.MASTER_REMOTE_ACTION_COMMANDS)


# ---------------------------------------------------------------------------
# [3] Propagazione di replica
# ---------------------------------------------------------------------------

def test_propagazione_replica() -> None:
    print("\n[3] apply_event_to_replica — entrambi gli eventi, nessun crash senza trasporto")

    world = world_repo.create_world("Mondo Rientro 3", "dev-owner-3", "Il Master")
    assert world is not None
    world_repo.join_world_by_code(world.join_code, "dev-player-3", "Il Giocatore")
    instance = _make_archived_instance(world.id, "dev-player-3")

    backend = LocalBackend()
    req = _send(backend, world.id, "dev-player-3", perm.CMD_CHARACTER_REJOIN_REQUEST,
                {}, target_type="character", target_id=instance.id)
    import json
    request_id = json.loads(req.event.payload)["request_id"]

    try:
        world_sync.apply_event_to_replica(world.id, req.event)
        no_crash_request = True
    except Exception:
        no_crash_request = False
    check("apply_event_to_replica gestisce l'evento di richiesta senza sollevare",
          no_crash_request)
    replica_req = world_repo.get_rejoin_request(request_id)
    check("la richiesta è salvata anche 'lato replica' (stesso DB nei test)",
          replica_req is not None and replica_req.status == "pending")

    result = _send(backend, world.id, "dev-owner-3", perm.CMD_CHARACTER_REJOIN_RESPOND,
                    {"request_id": request_id, "accept": True},
                    target_type="character", target_id=instance.id)
    try:
        world_sync.apply_event_to_replica(world.id, result.event)
        no_crash_respond = True
    except Exception:
        no_crash_respond = False
    check("apply_event_to_replica gestisce l'evento di risposta senza sollevare",
          no_crash_respond)
    check("la richiesta risulta risolta dopo l'evento di risposta",
          world_repo.get_rejoin_request(request_id).status == "accepted")


# ---------------------------------------------------------------------------
# [4] create_or_resume_instance su un'istanza archiviata — mai un fantasma
# ---------------------------------------------------------------------------

def test_create_or_resume_su_istanza_archiviata() -> None:
    print("\n[4] create_or_resume_instance — un'istanza archiviata non viene mai ripresa in silenzio")

    world = world_repo.create_world("Mondo Rientro 4", "dev-owner-4", "Il Master")
    assert world is not None
    world_repo.join_world_by_code(world.join_code, "dev-player-4", "Il Giocatore")

    origin = _make_character("Origine 4")
    result = ci.create_or_resume_instance(world.id, origin.id, "dev-player-4", mode="as_is")
    check("prima istanza creata con successo", result.success)
    instance_id = result.character_id

    character_repo.archive_world_instance(world.id, instance_id)
    check("istanza ora archiviata", character_repo.get_by_id(instance_id).world_instance_archived)

    before_count = len(character_repo.get_all())
    result2 = ci.create_or_resume_instance(world.id, origin.id, "dev-player-4", mode="as_is")
    check("su un'istanza archiviata, success è False (MAI un resume silenzioso)",
          not result2.success)
    check("il campo archived è True", result2.archived)
    check("character_id punta comunque all'istanza archiviata trovata",
          result2.character_id == instance_id)
    check("nessuna nuova riga creata (nessun personaggio fantasma/duplicato)",
          len(character_repo.get_all()) == before_count)
    check("l'istanza è ancora archiviata (create_or_resume non la riattiva mai)",
          character_repo.get_by_id(instance_id).world_instance_archived)


# ---------------------------------------------------------------------------
# [5] UI
# ---------------------------------------------------------------------------

def _patch_page_property(view_cls) -> None:
    if getattr(view_cls, "_test_page_patched", False):
        return
    original_page_property = view_cls.page

    def _page_getter(self):
        fake = getattr(self, "_test_fake_page", None)
        if fake is not None:
            return fake
        return original_page_property.fget(self)

    view_cls.page = property(_page_getter)
    view_cls._test_page_patched = True


class _FakePage:
    def __init__(self):
        self.dialogs: list = []

    def show_dialog(self, dlg) -> None:
        self.dialogs.append(dlg)

    def pop_dialog(self, *_a) -> None:
        if self.dialogs:
            self.dialogs.pop()

    def update(self, *_a, **_k) -> None:
        pass


def _iter_controls(root):
    stack = [root]
    while stack:
        node = stack.pop()
        if node is None:
            continue
        yield node
        content = getattr(node, "content", None)
        if content is not None:
            stack.append(content)
        controls = getattr(node, "controls", None)
        if controls:
            stack.extend(controls)
        actions = getattr(node, "actions", None)
        if actions:
            stack.extend(actions)


def _find(root, pred):
    for node in _iter_controls(root):
        if pred(node):
            return node
    return None


def test_ui_master_richieste_di_rientro() -> None:
    print("\n[5a] UI master — sezione 'Richieste di rientro', click Accetta")
    _patch_page_property(__import__(
        "ui.views.world.world_view", fromlist=["WorldsView"],
    ).WorldsView)
    from ui.views.world.world_view import WorldsView

    world = world_repo.create_world("Mondo UI Rientro", "dev-owner-5a", "Il Master")
    assert world is not None
    world_repo.join_world_by_code(world.join_code, "dev-player-5a", "Il Giocatore")
    instance = _make_archived_instance(world.id, "dev-player-5a", name="PG UI")

    backend = LocalBackend()
    req = _send(backend, world.id, "dev-player-5a", perm.CMD_CHARACTER_REJOIN_REQUEST,
                {}, target_type="character", target_id=instance.id)
    assert req.success

    wv = WorldsView(on_back_to_home=lambda: None)
    wv.device_id = "dev-owner-5a"
    fake_page = _FakePage()
    wv._test_fake_page = fake_page

    section = wv._pending_rejoin_requests_section(world)
    check("la sezione 'Richieste di rientro' compare quando c'è una richiesta pending",
          section is not None)
    accept_pill = _find(section, lambda n: getattr(n, "value", None) == "Accetta")
    check("la pillola 'Accetta' compare nella riga della richiesta", accept_pill is not None)

    request = world_repo.get_pending_rejoin_requests(world.id)[0]
    wv._respond_rejoin_request(world, instance, request, True)
    check("l'istanza è stata riattivata dal click su Accetta",
          not character_repo.get_by_id(instance.id).world_instance_archived)

    section_after = wv._pending_rejoin_requests_section(world)
    check("la sezione sparisce quando non ci sono più richieste pending", section_after is None)


def test_ui_giocatore_richiedi_rientro() -> None:
    print("\n[5b] UI giocatore — pulsante 'Richiedi rientro' in HomeView")
    _patch_page_property(__import__(
        "ui.views.home_view", fromlist=["HomeView"],
    ).HomeView)
    from ui.views.home_view import HomeView

    world = world_repo.create_world("Mondo UI Rientro Player", "dev-owner-5b", "Il Master")
    assert world is not None
    world_repo.join_world_by_code(world.join_code, "dev-player-5b", "Il Giocatore")
    instance = _make_archived_instance(world.id, "dev-player-5b", name="PG Home")

    hv = HomeView.__new__(HomeView)  # bypassa __init__ (richiede una vera Page Flet)
    hv.device_id = "dev-player-5b"

    card = hv._character_card(instance, is_removed=True)
    rejoin_btn = _find(card, lambda n: isinstance(n, ft.IconButton)
                        and n.tooltip == "Richiedi rientro nel mondo")
    check("il pulsante 'Richiedi rientro nel mondo' compare sulla card di un personaggio rimosso",
          rejoin_btn is not None)

    backend = LocalBackend()
    req = _send(backend, world.id, "dev-player-5b", perm.CMD_CHARACTER_REJOIN_REQUEST,
                {}, target_type="character", target_id=instance.id)
    assert req.success

    card_pending = hv._character_card(instance, is_removed=True)
    pending_btn = _find(card_pending, lambda n: isinstance(n, ft.IconButton)
                         and n.tooltip == "Richiesta di rientro inviata — in attesa del master")
    check("con una richiesta già pending, il pulsante mostra lo stato di attesa",
          pending_btn is not None)
    rejoin_btn_gone = _find(card_pending, lambda n: isinstance(n, ft.IconButton)
                             and n.tooltip == "Richiedi rientro nel mondo")
    check("il pulsante di invio non è più cliccabile quando c'è già una richiesta pending",
          rejoin_btn_gone is None)


def main() -> int:
    print("=" * 62)
    print("Richiesta di rientro — CMD_CHARACTER_REJOIN_REQUEST/RESPOND")
    print(f"HOME di test: {_TMP_HOME}")
    print("=" * 62)
    init_db()
    test_richiesta_di_rientro()
    test_risposta_master_frozen()
    test_risposta_master_refresh_from_local()
    test_risposta_master_rifiuta()
    test_risposta_master_fail_closed_e_race()
    test_propagazione_replica()
    test_create_or_resume_su_istanza_archiviata()
    test_ui_master_richieste_di_rientro()
    test_ui_giocatore_richiedi_rientro()
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
