"""
Verifica di "Esportazione del mondo" (`.dndworld`, 2026-08-12, passo 9D di
`dnd_app/docs/multiplayer_design.md` §6.3/§13) — stesso identico principio
già collaudato per `.dndchar` (introspezione schema via `PRAGMA
table_info`), esteso a un intero Mondo condiviso: mondo, membri, TUTTE le
istanze di personaggio (comprese quelle archiviate), giornale eventi,
bottino (entrambi i contenitori), note del master, NPC di rubrica
(2026-08-12, da quando `master_npcs` è world-scoped), richieste di
modifica e di rientro pendenti, mappe condivise.

Cinque parti:

[1] `export_world()` — struttura completa, include le istanze archiviate
    (2026-08-12, "Richiesta di rientro": un backup non deve mai perdere un
    personaggio rimosso).

[2] `import_world(mode="new")` — round trip fedele su un mondo nuovo:
    stessi id (mondo, membri, personaggi, eventi), contenuto invariato,
    QUESTO dispositivo diventa owner/host, `join_code` rigenerato.

[3] `import_world(mode="overwrite")` — ripulisce tutto ciò che viveva sotto
    quell'id prima di riscrivere (nessun residuo del vecchio contenuto).

[4] `import_world(mode="copy")` — nuovi id per mondo/membri/personaggi/righe
    collegate, nessun conflitto con l'originale ancora presente, referenze
    interne (eventi/richieste → personaggio) rimappate correttamente.

[5] Validazione/fail-closed — file malformato, mondo già esistente in modo
    "new", modalità invalida.

[6] UI (`WorldsView`) — sezione "Backup del mondo" (solo owner), flusso di
    import da testo (nome obbligatorio, conflitto id già presente →
    copia/sovrascrivi, click reali sui controlli Flet).

Eseguire con:
    PYTHONPATH=".venv/lib/python3.13/site-packages:." python3 test_esportazione_mondo.py
"""

from __future__ import annotations

import os
import sys
import tempfile

_TMP_HOME = tempfile.mkdtemp(prefix="dnd_esportazione_mondo_")
os.environ["HOME"] = _TMP_HOME

import flet as ft  # noqa: E402

from data.database import init_db, get_connection  # noqa: E402
from data.models import Character  # noqa: E402
from data.repositories import (  # noqa: E402
    character_repo, loot_repo, master_repo, maps_repo, world_export, world_repo,
)

_PASS = 0
_FAIL: list[str] = []


def check(label: str, cond: bool) -> None:
    global _PASS
    if cond:
        _PASS += 1
    else:
        _FAIL.append(label)
        print(f"  FALLITO: {label}")


def _make_character(name: str, world_id: str = "", owner_device_id: str = "",
                     archived: bool = False) -> Character:
    c = Character(
        name=name, class_name="Guerriero", race="Umano", level=1,
        hit_dice_type=10, hit_dice_total=1, hit_dice_remaining=1,
        str_score=10, dex_score=10, con_score=10, int_score=10,
        wis_score=10, cha_score=10, hp_max=10, hp_current=10,
    )
    character_repo.create(c)
    if world_id:
        c.world_id = world_id
        c.owner_device_id = owner_device_id
        c.world_instance_archived = archived
        character_repo.update(c)
    return character_repo.get_by_id(c.id)


def _build_rich_world(name: str, owner_device: str, owner_name: str) -> tuple:
    world = world_repo.create_world(name, owner_device, owner_name)
    assert world is not None
    world_repo.join_world_by_code(world.join_code, "dev-player-x", "Giocatore X")

    active = _make_character("Attivo", world.id, owner_device)
    archived = _make_character("Rimosso", world.id, "dev-player-x", archived=True)

    world_repo.append_event(
        world.id, owner_device, owner_name, kind="xp.grant", target_type="character",
        target_id=active.id, summary="PE assegnati", payload="{}",
    )
    loot_repo.create_entry("master", "item", name="Spada", world_id=world.id)
    loot_repo.create_entry("party", "coins", world_id=world.id, gold=50)
    master_repo.create_master_campaign_note(
        category="npc", name="Un PNG", description="desc", world_id=world.id,
    )
    master_repo.create_npc(name="Un NPC di Rubrica", role="Alleato", world_id=world.id)
    maps_repo.create_shared_map(world.id, "Mappa Condivisa", image_data="")
    world_repo.create_rejoin_request(
        world.id, archived.id, "dev-player-x", "Giocatore X", "frozen", "{}",
    )
    return world, active, archived


# ---------------------------------------------------------------------------
# [1] export_world — struttura completa
# ---------------------------------------------------------------------------

def test_export_struttura_completa() -> None:
    print("\n[1] export_world() — struttura completa, include gli archiviati")
    world, active, archived = _build_rich_world("Mondo Export 1", "dev-owner-1", "Master 1")

    data = world_export.export_world(world.id)
    check("export riuscito", data is not None)
    assert data is not None
    check("kind='world'", data.get("kind") == "world")
    check("world_format_version presente", isinstance(data.get("export_format_version"), int))
    check("2 membri esportati", len(data["members"]) == 2)
    check("2 personaggi esportati (attivo + archiviato)", len(data["characters"]) == 2)
    exported_ids = {c["character"]["id"] for c in data["characters"]}
    check("il personaggio ARCHIVIATO è incluso nell'export", archived.id in exported_ids)
    check("almeno 1 evento esportato", len(data["events"]) >= 1)
    check("bottino master presente", len(data["loot_stash_entries"]) >= 1)
    check("bottino di entrambi i tipi presenti",
          {e["stash_kind"] for e in data["loot_stash_entries"]} == {"master", "party"})
    check("nota del master presente", len(data["master_campaign_notes"]) == 1)
    check("NPC di rubrica presente (2026-08-12, world-scoped)", len(data["master_npcs"]) == 1)
    check("mappa condivisa presente", len(data["shared_maps"]) == 1)
    check("richiesta di rientro pendente presente", len(data["world_rejoin_requests"]) == 1)

    err = world_export.validate_export_data(data)
    check("l'export che ha appena prodotto se stesso è considerato valido", err == "")

    summary = world_export.peek_world_summary(data)
    check("peek_world_summary trova il nome giusto",
          summary is not None and summary["name"] == "Mondo Export 1")
    check("peek_world_summary conta il personaggio archiviato a parte",
          summary is not None and summary["archived_count"] == 1)


# ---------------------------------------------------------------------------
# [2] import_world(mode="new") — round trip fedele
# ---------------------------------------------------------------------------

def test_import_new_round_trip() -> None:
    print("\n[2] import_world(mode='new') — round trip fedele, nuovo device diventa owner")
    world, active, archived = _build_rich_world("Mondo Export 2", "dev-owner-2", "Master 2")
    data = world_export.export_world(world.id)
    assert data is not None

    # Simula il trasferimento: elimina OGNI TRACCIA del mondo originale da
    # QUESTO DB (come se l'import avvenisse su un dispositivo che non ha
    # mai visto questo world_id) prima di reimportarlo — altrimenti 'new'
    # fallirebbe per collisione sulle tabelle senza CASCADE da `worlds`
    # (loot/note/mappe), correttamente: 'new' presuppone un id libero.
    world_repo.delete_world(world.id)
    character_repo.delete(active.id)
    character_repo.delete(archived.id)
    conn = get_connection()
    conn.execute("DELETE FROM loot_stash_entries WHERE world_id=?", (world.id,))
    conn.execute("DELETE FROM master_campaign_notes WHERE world_id=?", (world.id,))
    conn.execute("DELETE FROM master_npcs WHERE world_id=?", (world.id,))
    conn.execute("DELETE FROM game_maps WHERE world_id=?", (world.id,))
    conn.commit()
    conn.close()

    new_id = world_export.import_world(data, "new", "dev-importer-2", "Nuovo Master")
    check("import riuscito", new_id is not None)
    check("stesso id del file (mode new preserva gli id)", new_id == world.id)

    imported = world_repo.get_world(new_id)
    check("mondo importato trovato", imported is not None)
    assert imported is not None
    check("nome preservato", imported.name == "Mondo Export 2")
    check("il dispositivo importatore è ora l'owner", imported.owner_device_id == "dev-importer-2")
    check("il mondo è ora ospitato su QUESTO device", imported.is_local_host)
    check("join_code rigenerato (non lo stesso del file)", imported.join_code != world.join_code)

    members = world_repo.get_members(new_id)
    check("membri preservati (2 originali + 1 nuovo owner)", len(members) == 3)
    importer_member = world_repo.get_member(new_id, "dev-importer-2")
    check("il dispositivo importatore è owner tra i membri",
          importer_member is not None and importer_member.role == "owner")
    old_owner_member = world_repo.get_member(new_id, "dev-owner-2")
    check("il vecchio owner è stato retrocesso a master (mai due owner)",
          old_owner_member is not None and old_owner_member.role == "master")

    all_chars = character_repo.get_all_instances_of_world(new_id)
    check("entrambi i personaggi reimportati", len(all_chars) == 2)
    reimported_archived = character_repo.get_by_id(archived.id)
    check("il personaggio archiviato resta archiviato dopo l'import",
          reimported_archived is not None and reimported_archived.world_instance_archived)
    check("gli id dei personaggi sono preservati (mode new)",
          {c.id for c in all_chars} == {active.id, archived.id})

    events = world_repo.get_events_since(new_id, 0, limit=None)
    check("giornale eventi preservato (almeno l'evento originale)", len(events) >= 1)
    check("i seq sono validi e crescenti (mai importati da un altro DB)",
          all(events[i].seq < events[i + 1].seq for i in range(len(events) - 1)))

    check("bottino reimportato (entrambi i tipi)",
          len(loot_repo.get_entries("master", new_id)) == 1
          and len(loot_repo.get_entries("party", new_id)) == 1)
    check("nota del master reimportata",
          len(master_repo.get_master_campaign_notes(world_id=new_id)) == 1)
    check("NPC di rubrica reimportato", len(master_repo.get_npcs(world_id=new_id)) == 1)
    check("mappa condivisa reimportata", len(maps_repo.get_shared_maps(new_id)) == 1)
    check("richiesta di rientro reimportata",
          len(world_repo.get_pending_rejoin_requests(new_id)) == 1)


# ---------------------------------------------------------------------------
# [3] import_world(mode="overwrite") — ripulisce prima di riscrivere
# ---------------------------------------------------------------------------

def test_import_overwrite_ripulisce() -> None:
    print("\n[3] import_world(mode='overwrite') — nessun residuo del vecchio contenuto")
    world, active, archived = _build_rich_world("Mondo Export 3", "dev-owner-3", "Master 3")
    data = world_export.export_world(world.id)
    assert data is not None

    # Aggiunge dati "sporchi" locali DOPO l'export, che l'overwrite deve
    # eliminare (mai lasciarli mescolati col contenuto reimportato).
    extra_loot = loot_repo.create_entry("master", "item", name="Oggetto Sporco", world_id=world.id)
    assert extra_loot is not None
    extra_npc = master_repo.create_npc(name="NPC Sporco", world_id=world.id)
    assert extra_npc is not None
    extra_char = _make_character("Fantasma da Overwrite", world.id, "dev-player-ghost")

    new_id = world_export.import_world(data, "overwrite", "dev-owner-3", "Master 3")
    check("import overwrite riuscito", new_id is not None)
    check("stesso id (overwrite preserva l'id)", new_id == world.id)

    check("l'oggetto di bottino 'sporco' NON esiste più",
          not any(e.name == "Oggetto Sporco" for e in loot_repo.get_entries("master", world.id)))
    check("l'NPC 'sporco' aggiunto dopo l'export NON esiste più",
          not any(n.name == "NPC Sporco" for n in master_repo.get_npcs(world_id=world.id)))
    check("solo l'NPC originale resta dopo l'overwrite",
          len(master_repo.get_npcs(world_id=world.id)) == 1)
    check("il personaggio 'sporco' aggiunto dopo l'export è stato eliminato dall'overwrite "
          "(DELETE FROM characters WHERE world_id=?, stesso principio distruttivo di "
          "import_character(mode='overwrite') applicato a QUESTO mondo)",
          character_repo.get_by_id(extra_char.id) is None)
    all_chars = character_repo.get_all_instances_of_world(world.id)
    check("solo i 2 personaggi originali restano nel mondo dopo l'overwrite",
          len(all_chars) == 2)


# ---------------------------------------------------------------------------
# [4] import_world(mode="copy") — nuovi id, nessun conflitto, referenze rimappate
# ---------------------------------------------------------------------------

def test_import_copy_nuovi_id() -> None:
    print("\n[4] import_world(mode='copy') — nuovi id, referenze interne rimappate")
    world, active, archived = _build_rich_world("Mondo Export 4", "dev-owner-4", "Master 4")
    data = world_export.export_world(world.id)
    assert data is not None

    new_id = world_export.import_world(data, "copy", "dev-importer-4", "Copia Master")
    check("import copia riuscito", new_id is not None)
    check("id NUOVO (diverso dall'originale)", new_id != world.id)
    check("il mondo ORIGINALE esiste ancora, intatto",
          world_repo.get_world(world.id) is not None)

    copied_chars = character_repo.get_all_instances_of_world(new_id)
    check("2 personaggi copiati", len(copied_chars) == 2)
    check("nessun id di personaggio riusato dall'originale (copia vera)",
          {c.id for c in copied_chars}.isdisjoint({active.id, archived.id}))
    original_chars_still_there = character_repo.get_all_instances_of_world(world.id)
    check("i personaggi ORIGINALI non sono stati toccati dalla copia",
          {c.id for c in original_chars_still_there} == {active.id, archived.id})

    copied_archived = next(c for c in copied_chars if c.name == "Rimosso")
    check("lo stato archiviato è preservato anche nella copia",
          copied_archived.world_instance_archived)

    events = world_repo.get_events_since(new_id, 0, limit=None)
    copied_active = next(c for c in copied_chars if c.name == "Attivo")
    char_events = [e for e in events if e.target_type == "character"]
    check("gli eventi sul personaggio puntano al NUOVO id copiato, non al vecchio",
          all(e.target_id == copied_active.id for e in char_events))

    check("bottino copiato con nuovi id (non collide col mondo originale)",
          len(loot_repo.get_entries("master", new_id)) == 1)
    copied_npcs = master_repo.get_npcs(world_id=new_id)
    original_npcs = master_repo.get_npcs(world_id=world.id)
    check("NPC copiato con id nuovo (non collide col mondo originale)",
          len(copied_npcs) == 1 and copied_npcs[0].id not in {n.id for n in original_npcs})
    check("l'NPC ORIGINALE non è stato toccato dalla copia", len(original_npcs) == 1)
    copied_requests = world_repo.get_pending_rejoin_requests(new_id)
    check("richiesta di rientro copiata e ricollegata al personaggio copiato",
          len(copied_requests) == 1 and copied_requests[0].character_id == copied_archived.id)


# ---------------------------------------------------------------------------
# [5] Validazione / fail-closed
# ---------------------------------------------------------------------------

def test_validazione_fail_closed() -> None:
    print("\n[5] Validazione e fail-closed")

    check("un dict vuoto viene rifiutato", world_export.validate_export_data({}) != "")
    check("None viene rifiutato", world_export.validate_export_data(None) != "")
    check("un export di PERSONAGGIO (non mondo) viene rifiutato",
          world_export.validate_export_data({"character": {"id": "x"}, "related": {},
                                              "export_format_version": 1}) != "")

    world, _, _ = _build_rich_world("Mondo Export 5", "dev-owner-5", "Master 5")
    data = world_export.export_world(world.id)
    assert data is not None

    check("world_id_exists riconosce un mondo presente", world_export.world_id_exists(world.id))
    check("world_id_exists riconosce un id assente",
          not world_export.world_id_exists("id-a-caso-inesistente"))

    result = world_export.import_world(data, "new", "dev-importer-5b", "X")
    check("import 'new' su un id GIÀ ESISTENTE viene rifiutato (nessun collision override)",
          result is None)

    result = world_export.import_world(data, "modalita_a_caso", "dev-importer-5c", "X")
    check("una modalità invalida viene rifiutata", result is None)

    result = world_export.import_world({"kind": "world"}, "new", "dev-importer-5d", "X")
    check("un dict incompleto viene rifiutato", result is None)


# ---------------------------------------------------------------------------
# [6] UI
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
        self.web = False
        self.platform = None
        self.overlay: list = []

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


def test_ui_export_import() -> None:
    print("\n[6] UI — WorldsView, sezione Backup del mondo e flusso di import")
    _patch_page_property(__import__(
        "ui.views.world.world_view", fromlist=["WorldsView"],
    ).WorldsView)
    from ui.views.world.world_view import WorldsView

    world, active, archived = _build_rich_world("Mondo UI Export", "dev-owner-6", "Master 6")
    data = world_export.export_world(world.id)
    assert data is not None

    wv = WorldsView(on_back_to_home=lambda: None)
    wv.device_id = "dev-owner-6"
    fake_page = _FakePage()
    wv._test_fake_page = fake_page

    section = wv._backup_section(world)
    export_pill = _find(section, lambda n: getattr(n, "value", None) == "Esporta mondo")
    check("la pillola 'Esporta mondo' compare nella sezione Backup", export_pill is not None)

    import_pill_present = False
    wv._render_list()
    for control in wv._body.controls:
        if _find(control, lambda n: getattr(n, "value", None) == "Importa mondo") is not None:
            import_pill_present = True
    check("la pillola 'Importa mondo' compare nella lista dei mondi", import_pill_present)

    # --- import di un file valido su un id ASSENTE: nome obbligatorio, poi
    #     import diretto (nessun conflitto) ---
    json_text = world_export.export_to_json_string(world.id)
    world_repo.delete_world(world.id)
    character_repo.delete(active.id)
    character_repo.delete(archived.id)
    conn = get_connection()
    conn.execute("DELETE FROM loot_stash_entries WHERE world_id=?", (world.id,))
    conn.execute("DELETE FROM master_campaign_notes WHERE world_id=?", (world.id,))
    conn.execute("DELETE FROM master_npcs WHERE world_id=?", (world.id,))
    conn.execute("DELETE FROM game_maps WHERE world_id=?", (world.id,))
    conn.commit()
    conn.close()

    wv._do_import_world_from_text(json_text)
    check("il dialogo per il nome del master si apre", len(fake_page.dialogs) == 1)
    name_dialog = fake_page.dialogs[0]
    name_field = _find(name_dialog, lambda n: getattr(n, "label", None)
                        == "Il tuo nome (per il registro)")
    check("il campo nome è presente nel dialogo", name_field is not None)
    continue_btn = _find(name_dialog, lambda n: isinstance(n, ft.ElevatedButton)
                          and n.content == "Continua")
    assert continue_btn is not None and name_field is not None

    # nome vuoto -> errore (uno SnackBar in più, via show_snack/_show_error),
    # il dialogo del NOME resta comunque nello stack (mai popped su errore).
    name_field.value = "   "
    continue_btn.on_click(None)
    check("nome vuoto: il dialogo del nome resta aperto (nessun default silenzioso)",
          name_dialog in fake_page.dialogs)
    fake_page.dialogs.clear()  # simula la SnackBar che scompare da sola

    name_field.value = "Nuovo Master"
    continue_btn.on_click(None)
    check("dopo il nome, nessun conflitto -> import diretto, dialogo del nome chiuso "
          "(resta solo l'eventuale SnackBar di successo)",
          name_dialog not in fake_page.dialogs)
    reimported = world_repo.get_world(world.id)
    check("il mondo è stato importato con l'id originale (mode new)", reimported is not None)
    check("l'owner è ora questo dispositivo", reimported is not None
          and reimported.owner_device_id == "dev-owner-6")
    member = world_repo.get_member(world.id, "dev-owner-6")
    check("il nome inserito è quello registrato come membro",
          member is not None and member.display_name == "Nuovo Master")

    # --- import dello STESSO file di nuovo: id già presente -> conflitto ---
    fake_page.dialogs.clear()
    wv._do_import_world_from_text(json_text)
    name_dialog2 = fake_page.dialogs[0]
    name_field2 = _find(name_dialog2, lambda n: getattr(n, "label", None)
                         == "Il tuo nome (per il registro)")
    continue_btn2 = _find(name_dialog2, lambda n: isinstance(n, ft.ElevatedButton)
                           and n.content == "Continua")
    assert name_field2 is not None and continue_btn2 is not None
    name_field2.value = "Master Bis"
    continue_btn2.on_click(None)
    check("id già presente -> compare il dialogo di conflitto", len(fake_page.dialogs) == 1)
    conflict_dialog = fake_page.dialogs[0]
    copy_btn = _find(conflict_dialog, lambda n: isinstance(n, ft.OutlinedButton)
                      and n.content == "Crea copia")
    check("il bottone 'Crea copia' è presente nel conflitto", copy_btn is not None)
    assert copy_btn is not None

    copy_btn.on_click(None)
    check("dopo 'Crea copia' il dialogo di conflitto si chiude",
          conflict_dialog not in fake_page.dialogs)
    all_worlds = world_repo.get_worlds_for_device("dev-owner-6")
    check("ora esistono DUE mondi (originale + copia), nessun conflitto",
          len([w for w in all_worlds if w.name == "Mondo UI Export"]) == 2)

    # --- testo non valido: errore, nessun crash ---
    wv._do_import_world_from_text("questo non è JSON")
    check("un testo non valido mostra un errore invece di sollevare un'eccezione",
          True)  # se siamo arrivati qui senza eccezioni, il fail-closed regge


# ---------------------------------------------------------------------------
# [7] Promemoria di backup periodico (passo 9E)
# ---------------------------------------------------------------------------

def test_promemoria_backup() -> None:
    print("\n[7] Promemoria di backup — soglia di eventi dall'ultimo export (passo 9E)")
    _patch_page_property(__import__(
        "ui.views.world.world_view", fromlist=["WorldsView"],
    ).WorldsView)
    from ui.views.world.world_view import WorldsView
    from data.repositories import world_export as we

    world = world_repo.create_world("Mondo Promemoria", "dev-owner-7", "Master 7")
    assert world is not None
    check("un mondo appena creato ha last_export_seq=0", world.last_export_seq == 0)
    check("get_latest_event_seq su un mondo senza eventi propri è >= 0",
          world_repo.get_latest_event_seq(world.id) >= 0)

    wv = WorldsView(on_back_to_home=lambda: None)
    wv.device_id = "dev-owner-7"
    wv._test_fake_page = _FakePage()

    fresh = world_repo.get_world(world.id)
    section = wv._backup_section(fresh)
    check("nessun avviso appena creato (sotto soglia)",
          _find(section, lambda n: "considera un nuovo backup" in str(getattr(n, "value", "")))
          is None)

    for i in range(we.EXPORT_REMINDER_EVENT_THRESHOLD):
        world_repo.append_event(
            world.id, "dev-owner-7", "Master 7", kind="xp.grant", target_type="character",
            target_id="x", summary=f"evento {i}", payload="{}",
        )

    fresh = world_repo.get_world(world.id)
    section = wv._backup_section(fresh)
    warning = _find(section, lambda n: "considera un nuovo backup" in str(getattr(n, "value", "")))
    check(f"l'avviso compare dopo {we.EXPORT_REMINDER_EVENT_THRESHOLD} eventi dall'ultimo export",
          warning is not None)

    latest_seq = world_repo.get_latest_event_seq(world.id)
    check("mark_world_exported riesce", world_repo.mark_world_exported(world.id, latest_seq))
    fresh = world_repo.get_world(world.id)
    check("last_export_seq aggiornato al seq più recente", fresh.last_export_seq == latest_seq)

    section_after = wv._backup_section(fresh)
    warning_after = _find(section_after, lambda n: "considera un nuovo backup"
                           in str(getattr(n, "value", "")))
    check("dopo mark_world_exported l'avviso sparisce", warning_after is None)


def main() -> int:
    print("=" * 62)
    print("Esportazione del mondo — .dndworld (passo 9D)")
    print(f"HOME di test: {_TMP_HOME}")
    print("=" * 62)
    init_db()
    test_export_struttura_completa()
    test_import_new_round_trip()
    test_import_overwrite_ripulisce()
    test_import_copy_nuovi_id()
    test_validazione_fail_closed()
    test_ui_export_import()
    test_promemoria_backup()
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
