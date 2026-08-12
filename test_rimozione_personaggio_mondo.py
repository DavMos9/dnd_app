"""
Verifica di `CMD_CHARACTER_INSTANCE_REMOVE` (2026-08-12) — richiesta
esplicita di Davide dopo il primo uso reale della Sezione Mondi: "manca la
possibilità di eliminare il personaggio dal mondo, attualmente posso
eliminare solo la persona [il membro] dal mondo ma non il suo
personaggio".

Distinta da `CMD_MEMBER_KICK` (che espelle l'intero dispositivo e archivia
TUTTE le sue istanze, già coperto da `test_master_world_scoping.py`/
`test_mondo_senza_rete.py`): qui il master rimuove UN singolo personaggio
mentre il suo giocatore resta membro del mondo. Stessa non-distruttività
già decisa con Davide per l'espulsione — archiviato (`characters.
world_instance_archived`), mai cancellato, si riattiva da solo al primo
resync del proprietario.

Tre parti:

[1] Handler `_handle_character_instance_remove` — archivia SOLO il
    personaggio bersaglio (un secondo personaggio dello stesso proprietario
    resta intatto), il giocatore resta membro, fail-closed (personaggio di
    un altro mondo, personaggio inesistente, ruolo insufficiente).

[2] Effetto pratico: il personaggio rimosso sparisce da
    `get_master_visible_characters()` (quindi dalla Sezione Master/
    "Interviene a distanza") ma resta leggibile per id — mai cancellato.

[3] UI (`WorldsView._confirm_remove_character`/`_do_remove_character`) —
    click reale sul bottone di conferma, passa da `_send_remote_command`
    (stesso timer anti-spam per personaggio delle altre azioni della riga,
    non una scorciatoia).

Eseguire con:
    PYTHONPATH=".venv/lib/python3.13/site-packages:." python3 test_rimozione_personaggio_mondo.py
"""

from __future__ import annotations

import os
import sys
import tempfile

_TMP_HOME = tempfile.mkdtemp(prefix="dnd_rimozione_personaggio_")
os.environ["HOME"] = _TMP_HOME

import flet as ft  # noqa: E402

from data.database import init_db  # noqa: E402
from data.models import Character  # noqa: E402
from data.repositories import character_repo, world_repo  # noqa: E402
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


def _make_character(name: str) -> Character:
    c = Character(
        name=name, class_name="Guerriero", race="Umano", level=1,
        hit_dice_type=10, hit_dice_total=1, hit_dice_remaining=1,
        str_score=10, dex_score=10, con_score=10, int_score=10,
        wis_score=10, cha_score=10, hp_max=10, hp_current=10,
    )
    character_repo.create(c)
    return c


def _link_to_world(character: Character, world_id: str, owner_device_id: str) -> None:
    """Collega un personaggio locale a un mondo come istanza — scrittura
    diretta minimale (bastano le 3 colonne che l'handler legge/scrive),
    stesso approccio già in uso in altri test di questa batteria per non
    dover passare da `core.character_instances` per un fixture."""
    character.world_id = world_id
    character.owner_device_id = owner_device_id
    character_repo.update(character)


# ---------------------------------------------------------------------------
# [1] Handler — archivia SOLO il bersaglio, fail-closed
# ---------------------------------------------------------------------------

def test_handler_rimuove_solo_il_bersaglio() -> None:
    print("\n[1] CMD_CHARACTER_INSTANCE_REMOVE — archivia solo il personaggio scelto")

    world = world_repo.create_world("Mondo Rimozione", "dev-owner-1", "Il Master")
    assert world is not None
    world_repo.join_world_by_code(world.join_code, "dev-player-1", "Il Giocatore")

    target = _make_character("Bersaglio")
    _link_to_world(target, world.id, "dev-player-1")
    other = _make_character("Altro Personaggio Stesso Giocatore")
    _link_to_world(other, world.id, "dev-player-1")

    backend = LocalBackend()
    check("il bersaglio non è archiviato prima della rimozione",
          not character_repo.get_by_id(target.id).world_instance_archived)

    result = _send(backend, world.id, "dev-owner-1", perm.CMD_CHARACTER_INSTANCE_REMOVE,
                    {}, target_type="character", target_id=target.id)
    check("rimozione riuscita", result.success)
    check("produce un evento", result.event is not None)
    check("kind giusto", result.event.kind == perm.CMD_CHARACTER_INSTANCE_REMOVE)
    check("target_type character", result.event.target_type == "character")
    check("target_id il personaggio bersaglio", result.event.target_id == target.id)
    successful_event = result.event

    check("il bersaglio è ora archiviato", character_repo.get_by_id(target.id).world_instance_archived)
    check("l'ALTRO personaggio dello stesso giocatore NON è stato toccato",
          not character_repo.get_by_id(other.id).world_instance_archived)

    member = world_repo.get_member(world.id, "dev-player-1")
    check("il giocatore RESTA membro del mondo (distinto dall'espulsione)", member is not None)

    # -- Fail-closed --
    result = _send(backend, world.id, "dev-player-1", perm.CMD_CHARACTER_INSTANCE_REMOVE,
                    {}, target_type="character", target_id=other.id)
    check("un giocatore non può rimuovere personaggi (solo master/owner)", not result.success)

    result = _send(backend, world.id, "dev-owner-1", perm.CMD_CHARACTER_INSTANCE_REMOVE,
                    {}, target_type="character", target_id="id-inesistente")
    check("un personaggio inesistente viene rifiutato", not result.success)

    world2 = world_repo.create_world("Altro Mondo", "dev-owner-1b", "Master B")
    result = _send(backend, world2.id, "dev-owner-1b", perm.CMD_CHARACTER_INSTANCE_REMOVE,
                    {}, target_type="character", target_id=other.id)
    check("un personaggio di un ALTRO mondo viene rifiutato", not result.success)
    check("il personaggio non è stato archiviato dal tentativo respinto",
          not character_repo.get_by_id(other.id).world_instance_archived)

    local_character = _make_character("Mai stato in un mondo")
    result = _send(backend, world.id, "dev-owner-1", perm.CMD_CHARACTER_INSTANCE_REMOVE,
                    {}, target_type="character", target_id=local_character.id)
    check("un personaggio locale (mai in nessun mondo) viene rifiutato", not result.success)

    check("il comando è incluso nella matrice master/owner",
          perm.CMD_CHARACTER_INSTANCE_REMOVE in perm.MASTER_AND_OWNER_COMMANDS)
    check("il comando fa rimaterializzare la replica del proprietario (come le altre "
          "mutazioni di un personaggio)",
          perm.CMD_CHARACTER_INSTANCE_REMOVE in perm.CHARACTER_MUTATING_COMMANDS)

    # `apply_event_to_replica` con `remote_backend=None` non deve sollevare
    # (stesso principio già verificato per gli altri eventi che rientrano
    # in CHARACTER_MUTATING_COMMANDS — l'assenza di trasporto è il caso
    # normale quando questa funzione è chiamata in isolamento nei test:
    # `_resync_character_from_host` no-oppa senza un backend vero).
    try:
        world_sync.apply_event_to_replica(world.id, successful_event)
        no_crash = True
    except Exception:
        no_crash = False
    check("apply_event_to_replica gestisce l'evento senza sollevare (nessun trasporto)",
          no_crash)


# ---------------------------------------------------------------------------
# [2] Sparisce dalla Sezione Master, mai cancellato
# ---------------------------------------------------------------------------

def test_sparisce_da_sezione_master_non_cancellato() -> None:
    print("\n[2] Rimosso dalla Sezione Master (get_master_visible_characters), mai cancellato")

    world = world_repo.create_world("Mondo Visibilità", "dev-owner-2", "Il Master")
    assert world is not None
    world_repo.join_world_by_code(world.join_code, "dev-player-2", "Il Giocatore")

    target = _make_character("Da Rimuovere")
    _link_to_world(target, world.id, "dev-player-2")

    check("il personaggio è visibile al master PRIMA della rimozione",
          any(c.id == target.id
              for c in character_repo.get_master_visible_characters(world.id)))

    backend = LocalBackend()
    result = _send(backend, world.id, "dev-owner-2", perm.CMD_CHARACTER_INSTANCE_REMOVE,
                    {}, target_type="character", target_id=target.id)
    check("rimozione riuscita", result.success)

    check("il personaggio NON è più visibile al master dopo la rimozione",
          not any(c.id == target.id
                  for c in character_repo.get_master_visible_characters(world.id)))
    still_there = character_repo.get_by_id(target.id)
    check("il personaggio esiste ancora nel DB (mai cancellato)", still_there is not None)
    check("i suoi dati (es. il nome) sono intatti",
          still_there is not None and still_there.name == "Da Rimuovere")
    check("resta collegato al mondo (world_id invariato — si riattiva al resync, "
          "non serve un nuovo collegamento)",
          still_there is not None and still_there.world_id == world.id)


# ---------------------------------------------------------------------------
# [3] UI — click reale sul bottone di conferma
# ---------------------------------------------------------------------------

def _patch_worlds_view_page_property() -> None:
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


def test_ui_click_conferma() -> None:
    print("\n[3] UI — _confirm_remove_character/_do_remove_character, click reale")
    _patch_worlds_view_page_property()
    from ui.views.world.world_view import WorldsView

    world = world_repo.create_world("Mondo UI Rimozione", "dev-owner-3", "Il Master")
    assert world is not None
    world_repo.join_world_by_code(world.join_code, "dev-player-3", "Il Giocatore")
    target = _make_character("Personaggio UI")
    _link_to_world(target, world.id, "dev-player-3")

    wv = WorldsView(on_back_to_home=lambda: None)
    wv.device_id = "dev-owner-3"
    fake_page = _FakePage()
    wv._test_fake_page = fake_page

    row = wv._remote_character_row(world, target)
    remove_pill = _find(row, lambda n: getattr(n, "value", None) == "Rimuovi dal mondo")
    check("la pillola 'Rimuovi dal mondo' compare nella riga del personaggio",
          remove_pill is not None)

    wv._confirm_remove_character(world, target)
    check("il dialogo di conferma si apre", len(fake_page.dialogs) == 1)
    dlg = fake_page.dialogs[0]
    confirm_btn = _find(dlg, lambda n: isinstance(n, ft.ElevatedButton)
                         and n.content == "Rimuovi")
    check("il bottone 'Rimuovi' è presente nel dialogo", confirm_btn is not None)
    assert confirm_btn is not None

    confirm_btn.on_click(None)
    check("il dialogo si chiude dopo la conferma", len(fake_page.dialogs) == 0)
    check("il personaggio è stato archiviato (rimosso dalla Sezione Master)",
          character_repo.get_by_id(target.id).world_instance_archived)
    events = world_repo.get_events_since(world.id, 0)
    check("l'evento è nel giornale",
          any(e.kind == perm.CMD_CHARACTER_INSTANCE_REMOVE for e in events))


def main() -> int:
    print("=" * 62)
    print("CMD_CHARACTER_INSTANCE_REMOVE — rimozione di un personaggio dal mondo")
    print(f"HOME di test: {_TMP_HOME}")
    print("=" * 62)
    init_db()
    test_handler_rimuove_solo_il_bersaglio()
    test_sparisce_da_sezione_master_non_cancellato()
    test_ui_click_conferma()
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
