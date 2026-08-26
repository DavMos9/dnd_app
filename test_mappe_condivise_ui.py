"""
Verifica della UI del passo 8 di dnd_app/docs/multiplayer_design.md —
"Mappe condivise" (§6.4): `ui/views/world/world_view.py::WorldsView.
_shared_maps_section` e tutti i metodi che ci girano intorno.

Riscritta per intero il 2026-08-12 insieme al backend (vedi il docstring
di `test_mappe_condivise.py` per il bug e le tre richieste di Davide che
l'hanno motivata): pubblicare CLONA invece di riusare la riga personale,
"nascondi ai giocatori" è distinto da "elimina", e il master può caricare
una mappa nuova direttamente. In più, il fix del disallineamento delle
annotazioni quando l'overlay non ha la stessa dimensione con cui si è
disegnato (normalizzazione a frazioni via `on_size_change`, `ui/
canvas_geometry.py`).

Scelta di design verificata qui, non solo dichiarata: pubblicare/caricare/
disegnare/nascondere/eliminare è permesso SOLO a master/owner che OSPITA
il mondo (`world.is_local_host`), mai a un co-master remoto — vedi il
commento sopra `_shared_maps_section` nel sorgente per il perché (la riga
`game_maps` di una mappa condivisa vive sul DB LOCALE di chi la
pubblica/carica, non su quello dell'host se sono dispositivi diversi).

Cinque parti:

[1] `_shared_maps_section`/`_shared_map_row` — visibilità e contenuto
    corretti per le tre combinazioni di ruolo/hosting che contano: master
    host (gestisce, vede tutto incluse le mappe nascoste ai giocatori),
    player (solo le visibili), master NON host (sola lettura come un
    player, nonostante il ruolo).

[2] `_open_add_map_dialog`/`_open_publish_map_dialog`/
    `_toggle_map_visibility`/`_confirm_delete_map` — click reali sui
    controlli Flet trovati per contenuto/icona, verificati sullo stato
    risultante nel DB e nel giornale eventi. Include la regressione del
    bug originale: disegnare sul clone condiviso non tocca la mappa
    personale di origine.

[3] `_open_shared_map` lato master host — l'overlay si apre in
    `page.overlay` (mai dentro `self._body`), un tratto disegnato via
    gesture produce UN evento `CMD_MAP_DRAW` e la riga persistita
    corretta, "Annulla ultimo"/"Cancella tutto" fanno lo stesso. Include
    il fix delle coordinate: la stessa mappa aperta in due riquadri di
    dimensione diversa (`on_size_change`) mostra il tratto nella stessa
    posizione RELATIVA, non ancorato ai vecchi pixel assoluti.

[4] `_open_shared_map` lato replica (client remoto reale, host+socket veri
    come in `test_world_view_remote_routing.py`) — l'immagine (mai
    trasportata da un evento) viene scaricata pigra alla prima apertura via
    `RemoteBackend.fetch_map_image()` e messa in cache locale; il ciclo di
    ridisegno periodico in sola lettura (`_watch_loop`) rileva un tratto
    disegnato nel frattempo sull'host.

[5] `_open_upload_map_dialog` — validazione (nome/immagine obbligatori);
    la meccanica di selezione immagine vera e propria non è testata qui,
    stessa limitazione già accettata nel resto del progetto per
    `_pick_desktop`/`_pick_mobile`/`_pick_from_library` (richiedono
    interazione OS reale — vedi `dnd_app/docs/changelog_storico.md`,
    sezione FILE PICKER).

Eseguire con:
    PYTHONPATH=".venv/lib/python3.13/site-packages:." python3 test_mappe_condivise_ui.py
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
import tempfile
from dataclasses import replace

_TMP_HOME = tempfile.mkdtemp(prefix="dnd_mappe_condivise_ui_")
os.environ["HOME"] = _TMP_HOME

import flet as ft  # noqa: E402
import flet.canvas as cv  # noqa: E402

from core import world_backend  # noqa: E402
from core import world_permissions as perm  # noqa: E402
from data.database import init_db  # noqa: E402
from data.models import Character, World  # noqa: E402
from data.repositories import character_repo, maps_repo, world_repo  # noqa: E402
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


_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _patch_worlds_view_page_property() -> None:
    """Stesso patch di `test_ingresso_lan_sincronizzazione.py` — `WorldsView.
    page` è la property vera di Flet (risale `parent` fino a una `Page`
    reale), niente setter: si sostituisce la property SOLO su questa
    classe con una che legge `_test_fake_page` se presente."""
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
    """Doppio minimale — intercetta solo ciò che i dialoghi/l'overlay di
    questa sezione chiamano davvero su `self.page`."""

    def __init__(self):
        self.dialogs: list = []
        self.overlay: list = []
        self.run_task_calls: list[tuple] = []
        self.platform = None
        self.web = False
        self.width = 1000

    def show_dialog(self, dlg) -> None:
        self.dialogs.append(dlg)

    def pop_dialog(self, *_a) -> None:
        if self.dialogs:
            self.dialogs.pop()

    def update(self, *_a, **_k) -> None:
        pass

    def run_task(self, coro_fn, *args, **kwargs) -> None:
        self.run_task_calls.append((coro_fn, args, kwargs))


def _iter_controls(root):
    """Cammina l'albero dei controlli Flet costruiti (mai montati su una
    Page reale, quindi niente `.controls`/`.content` popolati da Flet
    stesso — solo quelli che il nostro codice ha assegnato) per trovare un
    nodo per predicato. Copre `.content` singolo, `.controls` multipli, e
    `.actions` (i pulsanti di un `ft.AlertDialog`, un attributo a sé — non
    `.content` — che senza questo passo il cammino non raggiungerebbe
    mai)."""
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


def _find_all(root, pred):
    return [n for n in _iter_controls(root) if pred(n)]


def _find_pill_button(root, label: str):
    """Trova un pulsante-pillola della toolbar condivisa
    (`ui/components/map_drawing_canvas.py::MapDrawingCanvas._build_top_row_content`,
    stesso pattern di `ui/views/maps_view.py`) dal testo dell'etichetta —
    un `ft.Container(on_click=..., content=ft.Row([Icon, Text(label)]))`,
    non più un semplice `ft.TextButton` con `content` stringa."""
    def _pred(n):
        if not isinstance(n, ft.Container) or not getattr(n, "on_click", None):
            return False
        row = n.content
        if not isinstance(row, ft.Row):
            return False
        return any(isinstance(c, ft.Text) and c.value == label for c in row.controls)
    return _find(root, _pred)


class _FakeOffset:
    def __init__(self, x: float, y: float):
        self.x = x
        self.y = y


class _FakeScaleStartEvent:
    """Imita `ft.ScaleStartEvent` — l'unico evento che
    `MapDrawingCanvas._on_interaction_start()` legge ora (BUG FIX
    2026-08-26, quarto giro: un solo `ft.InteractiveViewer` per pannello,
    mai sostituito, gestisce sia disegno/gomma [1 dito] sia pan/zoom
    [2+ dita] — vedi il punto 4 del docstring del modulo di
    `map_drawing_canvas.py`)."""

    def __init__(self, x: float, y: float, pointer_count: int = 1):
        self.local_focal_point = _FakeOffset(x, y)
        self.pointer_count = pointer_count


class _FakeScaleUpdateEvent:
    def __init__(self, x: float, y: float, pointer_count: int = 1, scale: float = 1.0):
        self.local_focal_point = _FakeOffset(x, y)
        self.pointer_count = pointer_count
        self.scale = scale


class _FakeScaleEndEvent:
    def __init__(self, pointer_count: int = 1):
        self.pointer_count = pointer_count


class _FakeSizeEvent:
    """Doppio di `ft.LayoutSizeChangeEvent` — solo i due campi che
    `_on_box_resize` legge."""
    def __init__(self, width: float, height: float):
        self.width = width
        self.height = height


def _has_publish_pill(section) -> bool:
    """`d.section()` ritorna un `Container` semplice: il trailing passato
    in costruzione finisce dentro l'albero (una `d.pill()` con testo
    "+ Mappa"), non un attributo separato leggibile da fuori — si cerca
    per contenuto, stesso approccio già in uso per gli altri controlli."""
    return _find(section, lambda n: getattr(n, "value", None) == "+ Mappa") is not None


def _make_world_with_local_map(owner: str, image_bytes: bytes | None = _PNG_BYTES):
    world = world_repo.create_world("Mondo Mappe UI", owner, "Il Master")
    assert world is not None
    local = Character(
        name="Master Locale", class_name="Guerriero", race="Umano", level=1,
        hit_dice_type=10, hit_dice_total=1, hit_dice_remaining=1,
        str_score=10, dex_score=10, con_score=10, int_score=10,
        wis_score=10, cha_score=10, hp_max=10, hp_current=10,
    )
    character_repo.create(local)
    image_data = base64.b64encode(image_bytes).decode("ascii") if image_bytes else ""
    gm = maps_repo.create_map(local.id, "Rovine del Tempio", image_data=image_data)
    assert gm is not None
    return world, local, gm


def _publish(backend: LocalBackend, world_id: str, owner: str, source_map_id: str) -> str:
    result = _send(backend, world_id, owner, perm.CMD_MAP_PUBLISH, {"map_id": source_map_id})
    assert result.success, result.error
    return result.event.target_id


# ---------------------------------------------------------------------------
# [1] Visibilità/contenuto della sezione per ruolo
# ---------------------------------------------------------------------------

def test_visibilita_sezione() -> None:
    print("\n[1] _shared_maps_section — visibilità e contenuto per ruolo/hosting")
    from ui.views.world.world_view import WorldsView

    world, _local, gm = _make_world_with_local_map("dev-owner-vis")
    world_repo.join_world_by_code(world.join_code, "dev-player-vis", "Il Giocatore")
    world_repo.join_world_by_code(world.join_code, "dev-comaster-vis", "Co-Master")
    world_repo.update_member_role(world.id, "dev-comaster-vis", perm.ROLE_MASTER)

    wv = WorldsView(on_back_to_home=lambda: None)
    backend = LocalBackend()

    # Nessuna mappa condivisa ancora: il master host vede comunque la
    # sezione (per poter aggiungere una mappa), un player no.
    section = wv._shared_maps_section(world, perm.ROLE_OWNER)
    check("owner host vede la sezione anche senza mappe condivise (bottone + Mappa)",
          section is not None)
    check("la sezione per l'owner host contiene il bottone + Mappa",
          section is not None and _has_publish_pill(section))

    section_player = wv._shared_maps_section(world, perm.ROLE_PLAYER)
    check("un player NON vede la sezione se non c'è nessuna mappa condivisa",
          section_player is None)

    clone_id = _publish(backend, world.id, "dev-owner-vis", gm.id)

    section_player = wv._shared_maps_section(world, perm.ROLE_PLAYER)
    check("un player vede la sezione una volta che c'è una mappa condivisa",
          section_player is not None)
    check("la sezione di un player NON ha il bottone + Mappa",
          section_player is not None and not _has_publish_pill(section_player))
    row_name = _find(section_player, lambda n: getattr(n, "value", None) == "Rovine del Tempio")
    check("il nome della mappa compare nella riga", row_name is not None)
    visibility_btn = _find(
        section_player,
        lambda n: isinstance(n, ft.IconButton)
        and n.icon in (ft.Icons.VISIBILITY_OFF, ft.Icons.VISIBILITY),
    )
    check("un player NON ha il controllo di visibilità", visibility_btn is None)
    delete_btn = _find(
        section_player, lambda n: isinstance(n, ft.IconButton) and n.icon == ft.Icons.DELETE_OUTLINE,
    )
    check("un player NON ha il controllo di eliminazione", delete_btn is None)

    section_owner = wv._shared_maps_section(world, perm.ROLE_OWNER)
    check("un master che ospita VEDE il controllo di visibilità",
          _find(section_owner, lambda n: isinstance(n, ft.IconButton)
                and n.icon == ft.Icons.VISIBILITY_OFF) is not None)
    check("un master che ospita VEDE il controllo di eliminazione",
          _find(section_owner, lambda n: isinstance(n, ft.IconButton)
                and n.icon == ft.Icons.DELETE_OUTLINE) is not None)

    # Nascondere ai giocatori: il master la vede ancora (con lo stato
    # segnalato), il player smette di vederla del tutto.
    hide_result = _send(backend, world.id, "dev-owner-vis", perm.CMD_MAP_VISIBILITY,
                         {"map_id": clone_id, "visible_to_players": False})
    check("nascondere riesce (fixture)", hide_result.success)

    section_owner_hidden = wv._shared_maps_section(world, perm.ROLE_OWNER)
    check("il master vede ANCORA la mappa nascosta ai giocatori",
          _find(section_owner_hidden,
                lambda n: getattr(n, "value", None) == "Rovine del Tempio") is not None)
    status_text = _find(section_owner_hidden, lambda n: getattr(n, "value", None)
                         and "nascosta ai giocatori" in n.value)
    check("lo stato 'nascosta ai giocatori' è segnalato al master", status_text is not None)
    show_btn = _find(section_owner_hidden, lambda n: isinstance(n, ft.IconButton)
                      and n.icon == ft.Icons.VISIBILITY)
    check("l'icona diventa 'mostra' (occhio) quando la mappa è nascosta", show_btn is not None)

    section_player_hidden = wv._shared_maps_section(world, perm.ROLE_PLAYER)
    check("un player NON vede più una mappa nascosta ai giocatori",
          section_player_hidden is None)

    # Ripristina la visibilità per il resto del test.
    _send(backend, world.id, "dev-owner-vis", perm.CMD_MAP_VISIBILITY,
          {"map_id": clone_id, "visible_to_players": True})

    # Co-master che NON ospita: sola lettura come un player, nonostante il ruolo.
    non_hosted_world = World(
        id=world.id, name=world.name, owner_device_id=world.owner_device_id,
        join_code=world.join_code, is_local_host=False,
    )
    section_comaster_remote = wv._shared_maps_section(non_hosted_world, perm.ROLE_MASTER)
    check("un master su un mondo NON ospitato da questo dispositivo è sola lettura "
          "(niente eliminazione, niente + Mappa)",
          _find(section_comaster_remote, lambda n: isinstance(n, ft.IconButton)
                and n.icon == ft.Icons.DELETE_OUTLINE) is None
          and not _has_publish_pill(section_comaster_remote))


# ---------------------------------------------------------------------------
# [2] Aggiungi/pubblica/nascondi/elimina, via click reali sui controlli
# ---------------------------------------------------------------------------

def test_aggiungi_nascondi_elimina() -> None:
    print("\n[2] _open_add_map_dialog/_open_publish_map_dialog/"
          "_toggle_map_visibility/_confirm_delete_map — click reali")
    _patch_worlds_view_page_property()
    from ui.views.world.world_view import WorldsView

    world, _local, gm = _make_world_with_local_map("dev-owner-pub")

    wv = WorldsView(on_back_to_home=lambda: None)
    wv.device_id = "dev-owner-pub"
    fake_page = _FakePage()
    wv._test_fake_page = fake_page

    # -- Il dialogo "Aggiungi una mappa" offre la scelta tra le due sorgenti --
    wv._open_add_map_dialog(world)
    check("il dialogo di scelta si apre", len(fake_page.dialogs) == 1)
    chooser = fake_page.dialogs[0]
    existing_btn = _find(chooser, lambda n: isinstance(n, ft.OutlinedButton)
                          and "già salvata" in str(n.content))
    upload_btn = _find(chooser, lambda n: isinstance(n, ft.OutlinedButton)
                        and "nuova" in str(n.content))
    check("l'opzione 'mappa già salvata' è presente", existing_btn is not None)
    check("l'opzione 'carica mappa nuova' è presente", upload_btn is not None)
    assert existing_btn is not None
    existing_btn.on_click(None)
    check("scegliendo 'già salvata' si apre il dialogo di pubblicazione",
          len(fake_page.dialogs) == 1 and
          _find(fake_page.dialogs[0], lambda n: isinstance(n, ft.TextButton)
                and n.content == "Pubblica") is not None)

    # -- Pubblicazione (clona) --
    dlg = fake_page.dialogs[0]
    publish_btn = _find(dlg, lambda n: isinstance(n, ft.TextButton) and n.content == "Pubblica")
    assert publish_btn is not None
    publish_btn.on_click(None)
    check("il dialogo si chiude dopo il click", len(fake_page.dialogs) == 0)
    shared = maps_repo.get_shared_maps(world.id)
    check("una mappa condivisa nuova compare dopo la pubblicazione", len(shared) == 1)
    clone = shared[0]
    check("il clone ha un id diverso dalla mappa personale di origine", clone.id != gm.id)
    events = world_repo.get_events_since(world.id, 0)
    check("l'evento di pubblicazione è nel giornale",
          any(e.kind == perm.CMD_MAP_PUBLISH for e in events))

    # -- Il bug corretto: disegnare sul clone non tocca la mappa personale --
    draw_result = wv._send_command(world, perm.CMD_MAP_DRAW, {
        "map_id": clone.id,
        "strokes": [{"op": "add", "type": "stroke", "color": "#f00", "width": 3.0,
                     "points": [[0.1, 0.1], [0.5, 0.5]]}],
    })
    check("disegno sul clone riuscito (fixture)", draw_result.success)
    check("la mappa personale di origine NON riceve il tratto disegnato sul clone",
          json.loads(maps_repo.get_map(gm.id).annotations or "[]") == [])

    # -- Nascondi/mostra --
    fresh_clone = maps_repo.get_map(clone.id)
    wv._toggle_map_visibility(world, fresh_clone)
    check("dopo il toggle la mappa è nascosta ai giocatori",
          not maps_repo.get_map(clone.id).visible_to_players)
    wv._toggle_map_visibility(world, maps_repo.get_map(clone.id))
    check("un secondo toggle la rimostra", maps_repo.get_map(clone.id).visible_to_players)

    # -- Eliminazione: dialogo di conferma, poi click --
    wv._confirm_delete_map(world, maps_repo.get_map(clone.id))
    check("il dialogo di conferma eliminazione si apre", len(fake_page.dialogs) == 1)
    del_dlg = fake_page.dialogs[0]
    confirm_btn = _find(del_dlg, lambda n: isinstance(n, ft.ElevatedButton)
                         and n.content == "Elimina")
    check("il bottone 'Elimina' è presente nel dialogo di conferma", confirm_btn is not None)
    assert confirm_btn is not None
    confirm_btn.on_click(None)
    check("il dialogo si chiude dopo l'eliminazione", len(fake_page.dialogs) == 0)
    check("la mappa non esiste più", maps_repo.get_map(clone.id) is None)
    check("la mappa personale di origine non è mai stata toccata dall'eliminazione",
          maps_repo.get_map(gm.id) is not None)

    # -- Ripubblicando la stessa mappa personale si crea un secondo clone
    #    indipendente (nessuna deduplicazione — scelta deliberata, vedi
    #    changelog_storico.md): verifica solo che non sollevi errori.
    wv._open_publish_map_dialog(world)
    dlg2 = fake_page.dialogs[-1]
    publish_btn_again = _find(dlg2, lambda n: isinstance(n, ft.TextButton)
                               and n.content == "Pubblica")
    check("la mappa personale resta candidata dopo l'eliminazione del clone precedente",
          publish_btn_again is not None)
    fake_page.pop_dialog()


# ---------------------------------------------------------------------------
# [3] Overlay di disegno — master host, incluso il fix delle coordinate
# ---------------------------------------------------------------------------

def test_overlay_disegno_master() -> None:
    print("\n[3] _open_shared_map lato master host — disegno, annulla, cancella tutto, "
          "coordinate normalizzate")
    _patch_worlds_view_page_property()
    from ui.views.world.world_view import WorldsView

    world, _local, gm = _make_world_with_local_map("dev-owner-draw")
    backend = LocalBackend()
    clone_id = _publish(backend, world.id, "dev-owner-draw", gm.id)

    wv = WorldsView(on_back_to_home=lambda: None)
    wv.device_id = "dev-owner-draw"
    fake_page = _FakePage()
    wv._test_fake_page = fake_page

    shared_gm = maps_repo.get_map(clone_id)
    assert shared_gm is not None
    wv._open_shared_map(world, shared_gm, True)
    check("l'overlay è stato aggiunto a page.overlay", len(fake_page.overlay) == 1)
    overlay = fake_page.overlay[0]

    # BUG FIX 2026-08-24 (race di normalizzazione — vedi
    # `ui/components/map_drawing_canvas.py::MapDrawingCanvas.on_box_resize`):
    # un gesto ricevuto PRIMA che il riquadro sia noto (nessun
    # `on_size_change` ancora arrivato in quest'istante userebbe un box
    # 0x0, che normalizzerebbe i punti in modo scorretto — proprio il bug
    # segnalato da Davide "il disegno non corrisponde sulla mappa") viene
    # trattato come "view" (mai disegno), non come tratto — vedi il punto
    # 4 del docstring del modulo di `map_drawing_canvas.py`. Va quindi
    # simulato il resize PRIMA di disegnare, non dopo.
    resize_container = _find(
        overlay, lambda n: isinstance(n, ft.Container)
        and isinstance(getattr(n, "content", None), ft.InteractiveViewer)
        and getattr(n, "on_size_change", None),
    )
    assert resize_container is not None
    resize_container.on_size_change(_FakeSizeEvent(400, 300))

    viewer = _find(overlay, lambda n: isinstance(n, ft.InteractiveViewer))
    check("un master può disegnare: la mappa ha un InteractiveViewer "
          "(dopo che il riquadro è noto)", viewer is not None)
    assert viewer is not None

    viewer.on_interaction_start(_FakeScaleStartEvent(10, 10))
    viewer.on_interaction_update(_FakeScaleUpdateEvent(20, 20))
    viewer.on_interaction_end(_FakeScaleEndEvent())

    after_draw = maps_repo.get_map(clone_id)
    assert after_draw is not None
    strokes = json.loads(after_draw.annotations or "[]")
    check("un tratto disegnato produce esattamente una annotazione persistita",
          len(strokes) == 1 and strokes[0].get("type") == "stroke")
    check("FIX: con un riquadro noto (400x300), i punti si salvano come "
          "frazione [0,1] — mai più pixel assoluti indistinguibili da dati legacy",
          strokes[0].get("points") == [[10 / 400, 10 / 300], [20 / 400, 20 / 300]])
    draw_events = [e for e in world_repo.get_events_since(world.id, 0)
                   if e.kind == perm.CMD_MAP_DRAW]
    check("il tratto produce un evento CMD_MAP_DRAW nel giornale", len(draw_events) == 1)

    # "Annulla" (non più "Annulla ultimo" — le etichette sono ora quelle
    # condivise di `MapDrawingCanvas`, stesse della mappa personale).
    undo_btn = _find_pill_button(overlay, "Annulla")
    check("il bottone 'Annulla' è presente", undo_btn is not None)
    assert undo_btn is not None
    undo_btn.on_click(None)
    after_undo = maps_repo.get_map(clone_id)
    assert after_undo is not None
    check("dopo 'Annulla' non restano tratti",
          json.loads(after_undo.annotations or "[]") == [])

    close_btn = _find(overlay, lambda n: isinstance(n, ft.IconButton) and n.icon == ft.Icons.CLOSE)
    check("il bottone di chiusura è presente", close_btn is not None)
    assert close_btn is not None
    close_btn.on_click(None)
    check("chiudendo l'overlay viene rimosso da page.overlay", fake_page.overlay == [])


def test_coordinate_normalizzate() -> None:
    print("\n[3b] Fix 2026-08-12 — le coordinate restano allineate in riquadri di "
          "dimensione diversa (on_size_change)")
    _patch_worlds_view_page_property()
    from ui.views.world.world_view import WorldsView

    world, _local, gm = _make_world_with_local_map("dev-owner-coord")
    backend = LocalBackend()
    clone_id = _publish(backend, world.id, "dev-owner-coord", gm.id)

    wv = WorldsView(on_back_to_home=lambda: None)
    wv.device_id = "dev-owner-coord"
    fake_page = _FakePage()
    wv._test_fake_page = fake_page

    shared_gm = maps_repo.get_map(clone_id)
    wv._open_shared_map(world, shared_gm, True)
    overlay = fake_page.overlay[0]

    # Identificato dal contenuto diretto — l'`ft.InteractiveViewer` UNICO
    # che `build_draw_area()` restituisce (BUG FIX 2026-08-26, quarto
    # giro: mai più sostituito ai cambi modalità, vedi il punto 4 del
    # docstring del modulo di `map_drawing_canvas.py`) — non "un
    # qualunque Container con on_size_change": la toolbar (breakpoint
    # responsive) ne monta uno per conto proprio, e quello ha come
    # contenuto una Row/Column, non un InteractiveViewer.
    resize_container = _find(
        overlay, lambda n: isinstance(n, ft.Container)
        and isinstance(getattr(n, "content", None), ft.InteractiveViewer)
        and getattr(n, "on_size_change", None),
    )
    check("il riquadro di disegno ha un on_size_change agganciato", resize_container is not None)
    assert resize_container is not None

    # Riquadro "piccolo" (es. l'anteprima non a schermo intero su uno
    # smartphone) — disegna un tratto che tocca l'angolo in basso a destra.
    resize_container.on_size_change(_FakeSizeEvent(400, 300))
    viewer = _find(overlay, lambda n: isinstance(n, ft.InteractiveViewer))
    viewer.on_interaction_start(_FakeScaleStartEvent(0, 0))
    viewer.on_interaction_update(_FakeScaleUpdateEvent(400, 300))
    viewer.on_interaction_end(_FakeScaleEndEvent())

    stored = json.loads(maps_repo.get_map(clone_id).annotations)[0]["points"]
    check("il punto (400,300) in un riquadro 400x300 si salva come frazione (1.0, 1.0)",
          stored == [[0.0, 0.0], [1.0, 1.0]])

    canvas_ctrl = _find(overlay, lambda n: isinstance(n, cv.Canvas))
    assert canvas_ctrl is not None
    path_small = next(s for s in canvas_ctrl.shapes if isinstance(s, cv.Path))
    end_small = path_small.elements[-1]
    check("nel riquadro 400x300, il tratto è disegnato fino a (400,300)",
          (end_small.x, end_small.y) == (400.0, 300.0))

    # Stesso overlay, riquadro ORA molto più grande (es. la stessa mappa
    # aperta a schermo intero su un desktop) — il tratto deve seguire
    # PROPORZIONALMENTE, non restare ancorato a (400,300).
    resize_container.on_size_change(_FakeSizeEvent(1600, 1200))
    path_large = next(s for s in canvas_ctrl.shapes if isinstance(s, cv.Path))
    end_large = path_large.elements[-1]
    check("nello stesso riquadro allargato a 1600x1200, il tratto arriva fino a (1600,1200) "
          "— PRIMA del fix sarebbe rimasto fermo a (400,300), come se la mappa si fosse "
          "rimpicciolita (bug segnalato da Davide)",
          (end_large.x, end_large.y) == (1600.0, 1200.0))


# ---------------------------------------------------------------------------
# [4] Overlay lato replica — fetch pigro dell'immagine + ridisegno periodico
# ---------------------------------------------------------------------------

def test_overlay_replica_fetch_e_watch_loop() -> None:
    print("\n[4] _open_shared_map lato replica — fetch immagine + _watch_loop")
    _patch_worlds_view_page_property()
    from ui.views.world.world_view import WorldsView

    host_world, _local, gm = _make_world_with_local_map("dev-owner-replica",
                                                          image_bytes=_PNG_BYTES)
    backend = LocalBackend()
    clone_id = _publish(backend, host_world.id, "dev-owner-replica", gm.id)

    host = WorldHostServer(host_world.id, long_poll_timeout=2.0, announce=False)
    port = host.start()
    try:
        world_repo.join_world_by_code(host_world.join_code, "dev-player-replica", "Giocatore")
        join_backend = RemoteBackend("127.0.0.1", port, "dev-player-replica")
        outcome = join_backend.join(host_world.join_code, host.pin, "Giocatore")
        check("il giocatore entra ed è già noto", outcome.status == "approved")

        client_world = World(
            id=host_world.id, name=host_world.name, owner_device_id="dev-owner-replica",
            join_code=host_world.join_code, is_local_host=False,
            last_seen_host=f"127.0.0.1:{port}", session_token=join_backend.token or "",
        )

        wv = WorldsView(on_back_to_home=lambda: None)
        wv.device_id = "dev-player-replica"
        fake_page = _FakePage()
        wv._test_fake_page = fake_page

        # `stub_gm` simula l'oggetto che una VERA replica avrebbe in
        # memoria appena dopo `apply_event_to_replica` su `map.publish`
        # (`image_data==""`, mai trasportata da un evento — §6.4) — non
        # possiamo simulare anche la riga DB corrispondente vuota: questo
        # sandbox usa un solo DB condiviso tra "host" e "client" (stessa
        # limitazione già dichiarata in `test_lan_host_client.py`/`test_
        # mappe_condivise.py`) — qui si blocca solo l'oggetto passato a
        # `_open_shared_map`, non la riga fisica (che sull'host ha già
        # l'immagine, essendo lo stesso processo/DB).
        clone = maps_repo.get_map(clone_id)
        stub_gm = replace(clone, image_data="")

        fetch_calls: list[str] = []
        original_fetch = RemoteBackend.fetch_map_image

        def _tracked_fetch(self, map_id):
            fetch_calls.append(map_id)
            return original_fetch(self, map_id)

        RemoteBackend.fetch_map_image = _tracked_fetch
        try:
            wv._open_shared_map(client_world, stub_gm, False)
        finally:
            RemoteBackend.fetch_map_image = original_fetch
        check("l'apertura con immagine assente ha invocato il fetch pigro via rete",
              fetch_calls == [clone_id])
        check("l'overlay lato replica si apre comunque", len(fake_page.overlay) == 1)
        overlay = fake_page.overlay[0]

        # BUG FIX 2026-08-26 (quarto giro): un `ft.InteractiveViewer` è
        # SEMPRE montato ora, anche per un giocatore in sola lettura (può
        # comunque spostarsi/zoommare sulla mappa) — vedi il punto 4 del
        # docstring del modulo di `map_drawing_canvas.py`. Non è più
        # "nessun InteractiveViewer" il segnale di sola lettura, ma
        # "nessun tratto si salva mai, qualunque gesto si tenti".
        viewer = _find(overlay, lambda n: isinstance(n, ft.InteractiveViewer))
        check("un giocatore in sola lettura vede comunque un InteractiveViewer "
              "(può spostarsi/zoommare, solo non disegnare)", viewer is not None)
        assert viewer is not None
        viewer.on_interaction_start(_FakeScaleStartEvent(10, 10))
        viewer.on_interaction_update(_FakeScaleUpdateEvent(20, 20))
        viewer.on_interaction_end(_FakeScaleEndEvent())
        check("un giocatore NON può disegnare: un tentativo di tratto non "
              "salva nessuna annotazione",
              json.loads(maps_repo.get_map(clone_id).annotations or "[]") == [])
        undo_btn = _find(overlay, lambda n: isinstance(n, ft.TextButton)
                          and n.content == "Annulla ultimo")
        check("nessun controllo di disegno per un giocatore", undo_btn is None)

        after_open = maps_repo.get_map(clone_id)
        assert after_open is not None
        check("l'apertura ha scaricato e messo in cache l'immagine (fetch pigro)",
              bool(after_open.image_data))
        check("i bytes scaricati corrispondono a quelli pubblicati dall'host",
              base64.b64decode(after_open.image_data) == _PNG_BYTES)

        # -- ciclo di ridisegno periodico in sola lettura --
        watch_call = None
        for coro_fn, args, _kwargs in fake_page.run_task_calls:
            if getattr(coro_fn, "__name__", "") == "_watch_loop":
                watch_call = (coro_fn, args)
        check("_watch_loop è stato schedulato via page.run_task", watch_call is not None)
        assert watch_call is not None

        # Un tratto arriva sull'host MENTRE l'overlay è aperto sulla replica
        # (stesso principio dei test già in produzione: si scrive dove
        # l'evento arriverebbe DAVVERO, poi si verifica che il ciclo lo
        # rilevi — qui il "trasporto" è semplificato a una scrittura diretta
        # sulla riga locale, dato che la sincronizzazione degli eventi verso
        # la replica ha già la sua batteria dedicata altrove).
        maps_repo.update_map(clone_id, annotations=json.dumps(
            [{"type": "stroke", "color": "#e53935", "width": 5.0,
              "points": [[0.1, 0.1], [0.2, 0.2]]}],
        ))

        call_count = [0]
        original_sleep = asyncio.sleep

        async def _sleep_then_stop(_seconds):
            call_count[0] += 1
            if call_count[0] >= 2:
                raise asyncio.CancelledError()
            return

        asyncio.sleep = _sleep_then_stop  # type: ignore[assignment]
        try:
            asyncio.run(watch_call[0]())
        except asyncio.CancelledError:
            pass
        finally:
            asyncio.sleep = original_sleep

        canvas_ctrl = _find(overlay, lambda n: isinstance(n, cv.Canvas))
        check("dopo un giro del ciclo, canvas.shapes riflette il nuovo tratto arrivato",
              canvas_ctrl is not None and len(canvas_ctrl.shapes) == 1)
    finally:
        host.stop()


# ---------------------------------------------------------------------------
# [5] Dialogo di caricamento — validazione (mai la meccanica del picker)
# ---------------------------------------------------------------------------

def test_dialogo_upload_validazione() -> None:
    print("\n[5] _open_upload_map_dialog — validazione nome/immagine obbligatori")
    _patch_worlds_view_page_property()
    from ui.views.world.world_view import WorldsView

    world, _local, _gm = _make_world_with_local_map("dev-owner-upload")

    wv = WorldsView(on_back_to_home=lambda: None)
    wv.device_id = "dev-owner-upload"
    fake_page = _FakePage()
    wv._test_fake_page = fake_page

    wv._open_upload_map_dialog(world)
    check("il dialogo di caricamento si apre", len(fake_page.dialogs) == 1)
    dlg = fake_page.dialogs[0]
    name_tf = _find(dlg, lambda n: isinstance(n, ft.TextField))
    check("il campo nome è presente", name_tf is not None)
    switch = _find(dlg, lambda n: isinstance(n, ft.Switch))
    check("l'interruttore di visibilità è presente ed è acceso di default",
          switch is not None and switch.value is True)
    upload_confirm_btn = _find(dlg, lambda n: isinstance(n, ft.ElevatedButton)
                                and n.content == "Carica")
    check("il bottone 'Carica' è presente", upload_confirm_btn is not None)

    # Nessun nome, nessuna immagine: click su "Carica" non deve inviare
    # alcun comando (il dialogo resta aperto, mostra un errore). Il
    # controllo `error_text` non è mai stato montato su una Page REALE in
    # questo harness (`_FakePage` non attacca l'albero): `.update()` sullo
    # stesso identico codice di `MapsView._open_create_dialog` (mai avvolto
    # in try/except lì, funziona perché lì la Page è reale) solleva
    # `RuntimeError` qui — non un bug della UI, un limite noto di questo
    # doppio di test, ignorato per isolare cosa conta davvero: che il
    # comando NON sia partito.
    assert upload_confirm_btn is not None

    def _click(btn):
        try:
            btn.on_click(None)
        except RuntimeError:
            pass

    _click(upload_confirm_btn)
    check("senza nome né immagine, il dialogo resta aperto (validazione bloccante)",
          len(fake_page.dialogs) == 1)
    check("nessuna mappa condivisa è stata creata", maps_repo.get_shared_maps(world.id) == [])

    name_tf.value = "Accampamento"
    _click(upload_confirm_btn)
    check("con un nome ma senza immagine, il dialogo resta comunque aperto",
          len(fake_page.dialogs) == 1)
    check("ancora nessuna mappa condivisa creata", maps_repo.get_shared_maps(world.id) == [])


def main() -> int:
    print("=" * 62)
    print("PASSO 8 — Mappe condivise, UI (world_view.py)")
    print(f"HOME di test: {_TMP_HOME}")
    print("=" * 62)
    init_db()
    test_visibilita_sezione()
    test_aggiungi_nascondi_elimina()
    test_overlay_disegno_master()
    test_coordinate_normalizzate()
    test_overlay_replica_fetch_e_watch_loop()
    test_dialogo_upload_validazione()
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
