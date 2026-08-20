"""
Verifica della feature "Dossier PNG" (2026-08-20) — richiesta di Davide prima
del prossimo rilascio: "dare la possibilità di inserire l'immagine dell'npc
al master nella rubrica degli npc. quando poi quell'npc viene condiviso in
una nota... il giocatore può premere sul nome del personaggio e vedere
l'immagine che il master ha caricato... in pg incontrati vorrei farlo
apparire tipo carta di identità con descrizione sotto, tipo dossier".

Tre parti:

[1] `data/repositories/master_repo.py` — `MasterNpc.image_data` (nuova
    colonna, migrazione self-healing) sopravvive a create/update/round trip,
    come le altre colonne aggiunte dopo il rilascio iniziale (`race`,
    `world_id`).

[2] `ui/components/npc_dossier.py::build_npc_dossier_column()` — funzione
    pura di costruzione controlli: nome/ruolo/razza/descrizione compaiono,
    la foto compare solo se `image_data` è valorizzato (altrimenti
    un'icona segnaposto), nessuna cassetta impronte digitali/timbro
    (niente di quel genere nel codice, per costruzione).

[3] Flusso end-to-end lato giocatore (`ui/views/diary_view.py`) e lato
    master (`ui/views/master/master_notes_view.py`): una nota di campagna
    condivisa collegata a un NPC (`MasterCampaignNote.linked_npc_id`) mostra
    un pulsante "Collegato a: {nome}" cliccabile che apre il dossier — una
    nota SENZA collegamento non mostra alcun pulsante (nessun falso
    positivo).

Usa SEMPRE un DB temporaneo isolato (tempfile.mkdtemp() + HOME separato): il
DB reale di Davide non viene mai toccato.

Eseguire con:
    PYTHONPATH=".venv/lib/python3.13/site-packages:." python3 test_npc_dossier.py
"""

from __future__ import annotations

import base64
import os
import tempfile

_TMP_HOME = tempfile.mkdtemp(prefix="dnd_npc_dossier_")
os.environ["HOME"] = _TMP_HOME

import flet as ft  # noqa: E402

from data.database import init_db  # noqa: E402
from data.models import Character  # noqa: E402
from data.repositories import character_repo, master_repo, world_repo  # noqa: E402

_PASS = 0
_FAIL: list[str] = []


def check(label: str, cond: bool) -> None:
    global _PASS
    if cond:
        _PASS += 1
    else:
        _FAIL.append(label)
        print(f"  FALLITO: {label}")


class _FakePage:
    def __init__(self) -> None:
        self.dialogs: list = []

    def show_dialog(self, dlg) -> None:
        self.dialogs.append(dlg)

    def pop_dialog(self, *_a) -> None:
        if self.dialogs:
            self.dialogs.pop()

    def update(self, *_a, **_k) -> None:
        pass

    def run_task(self, *_a, **_k) -> None:
        pass


def _walk(control, kind) -> list:
    out: list = []
    if control is None:
        return out
    if isinstance(control, kind):
        out.append(control)
    for attr in ("controls", "actions"):
        kids = getattr(control, attr, None)
        if isinstance(kids, (list, tuple)):
            for k in kids:
                out.extend(_walk(k, kind))
    content = getattr(control, "content", None)
    if content is not None and not isinstance(content, str):
        out.extend(_walk(content, kind))
    return out


def _texts(control) -> list[str]:
    return [t.value for t in _walk(control, ft.Text) if isinstance(t.value, str)]


def _find_button_containing(control, substr: str):
    for b in _walk(control, ft.TextButton):
        if substr in " ".join(_texts(b.content if b.content is not None else b)):
            return b
    return None


_FAKE_JPEG_B64 = base64.b64encode(b"\xff\xd8\xff\xe0fake-jpeg-bytes").decode()


def test_npc_image_data_round_trip() -> None:
    print("\n[1] master_repo — MasterNpc.image_data sopravvive a create/update/round trip")

    npc = master_repo.create_npc(name="Grondar Martelliferro", role="Fabbro",
                                  race="Nano", image_data=_FAKE_JPEG_B64)
    assert npc is not None
    check("create_npc salva image_data", npc.image_data == _FAKE_JPEG_B64)

    reloaded = master_repo.get_npc_by_id(npc.id)
    check("get_npc_by_id lo rilegge intatto",
          reloaded is not None and reloaded.image_data == _FAKE_JPEG_B64)

    npc_no_image = master_repo.create_npc(name="Sconosciuto")
    assert npc_no_image is not None
    check("un NPC senza ritratto ha image_data vuoto", npc_no_image.image_data == "")

    all_npcs = {n.id: n for n in master_repo.get_npcs()}
    check("get_npcs porta con sé image_data",
          all_npcs[npc.id].image_data == _FAKE_JPEG_B64)

    # Aggiorna il ritratto di un NPC esistente.
    reloaded.image_data = "nuovo-base64"
    ok = master_repo.update_npc(reloaded)
    check("update_npc riesce", ok)
    check("il nuovo ritratto è stato salvato",
          master_repo.get_npc_by_id(npc.id).image_data == "nuovo-base64")

    # Rimuove il ritratto (il Master cambia idea).
    reloaded2 = master_repo.get_npc_by_id(npc.id)
    reloaded2.image_data = ""
    master_repo.update_npc(reloaded2)
    check("il ritratto può anche essere rimosso",
          master_repo.get_npc_by_id(npc.id).image_data == "")


def test_build_npc_dossier_column() -> None:
    print("\n[2] ui/components/npc_dossier.py — build_npc_dossier_column()")
    from data.models import MasterNpc
    from ui.components.npc_dossier import build_npc_dossier_column

    npc_full = MasterNpc(
        name="Lyra Ombraverde", role="Alleata", race="Elfo",
        tags="taverna, guida, contatto",
        notes="Una guardaboschi taciturna che conosce ogni sentiero della foresta.",
        image_data=_FAKE_JPEG_B64,
    )
    col = build_npc_dossier_column(npc_full)
    texts = _texts(col)
    check("il nome compare", any("Lyra Ombraverde" in t for t in texts))
    check("il ruolo compare", any("Alleata" in t for t in texts))
    check("la razza compare", any("Elfo" in t for t in texts))
    check("la descrizione (notes) compare per esteso", any(
        "guardaboschi taciturna" in t for t in texts
    ))
    check("i tag compaiono come chip", any("taverna" in t for t in texts))
    images = _walk(col, ft.Image)
    check("con image_data valorizzato, un ft.Image è presente", len(images) == 1)

    npc_no_photo = MasterNpc(name="Anonimo", notes="")
    col2 = build_npc_dossier_column(npc_no_photo)
    check("senza image_data, nessun ft.Image (icona segnaposto invece)",
          len(_walk(col2, ft.Image)) == 0)
    check("nessuna icona/riferimento a impronte digitali o timbro top secret",
          not any("impronta" in t.lower() or "top secret" in t.lower()
                  for t in _texts(col2)))
    check("senza descrizione, un messaggio esplicito invece di una sezione vuota",
          any("Nessuna descrizione" in t for t in _texts(col2)))


def _make_world_and_shared_npc_note(with_link: bool):
    world = world_repo.create_world("Mondo Dossier", "dev-master-dossier", "Master")
    assert world is not None
    npc = master_repo.create_npc(name="Oswin il Locandiere", role="Contatto",
                                  race="Umano", notes="Gestisce la locanda del Cinghiale Nero.",
                                  world_id=world.id, image_data=_FAKE_JPEG_B64)
    assert npc is not None
    note = master_repo.create_master_campaign_note(
        category="npc", name="Incontro alla locanda",
        description="Il gruppo incontra Oswin al bancone.",
        world_id=world.id, visibility="all",
        linked_npc_id=npc.id if with_link else "",
    )
    assert note is not None
    return world, npc, note


def test_diary_view_linked_npc_button() -> None:
    print("\n[3a] ui/views/diary_view.py — pulsante «Collegato a» nella nota condivisa")
    from ui.views.diary_view import DiaryView

    world, npc, note = _make_world_and_shared_npc_note(with_link=True)
    c = Character(name="Investigatore", class_name="Ladro", race="Umano", level=1,
                  hit_dice_type=8, hit_dice_total=1, hit_dice_remaining=1,
                  str_score=10, dex_score=14, con_score=10, int_score=10,
                  wis_score=10, cha_score=10, hp_max=8, hp_current=8)
    character_repo.create(c)
    c.world_id = world.id
    character_repo.update(c)

    dv = DiaryView(character=c)
    dv._page = _FakePage()
    dv.device_id = "dev-player-dossier"
    dv._merge_shared_notes()

    shared_note = next((n for n in dv._notes.get("npc", []) if n.id == note.id), None)
    check("la nota condivisa è stata fusa nella categoria PNG", shared_note is not None)
    assert shared_note is not None
    check("è riconosciuta come condivisa", shared_note.id in dv._shared_note_ids)

    panel = dv._build_note_reading_panel(shared_note)
    link_btn = _find_button_containing(panel, "Collegato a: Oswin il Locandiere")
    check("il pulsante «Collegato a: Oswin il Locandiere» esiste", link_btn is not None)
    assert link_btn is not None
    link_btn.on_click(None)
    check("il click apre il dossier", bool(dv._page.dialogs))
    dossier_texts = _texts(dv._page.dialogs[-1].content)
    check("il dossier mostra il nome dell'NPC collegato",
          any("Oswin il Locandiere" in t for t in dossier_texts))
    check("...e il ritratto caricato dal master",
          len(_walk(dv._page.dialogs[-1].content, ft.Image)) == 1)

    # -- Nessun collegamento: nessun pulsante, nessun falso positivo. --
    world2, npc2, note2 = _make_world_and_shared_npc_note(with_link=False)
    c2 = Character(name="Secondo PG", class_name="Guerriero", race="Umano", level=1)
    character_repo.create(c2)
    c2.world_id = world2.id
    character_repo.update(c2)
    dv2 = DiaryView(character=c2)
    dv2._page = _FakePage()
    dv2.device_id = "dev-player-dossier-2"
    dv2._merge_shared_notes()
    shared_note2 = next((n for n in dv2._notes.get("npc", []) if n.id == note2.id), None)
    assert shared_note2 is not None
    panel2 = dv2._build_note_reading_panel(shared_note2)
    check("una nota SENZA linked_npc_id non mostra alcun pulsante «Collegato a»",
          _find_button_containing(panel2, "Collegato a") is None)

    # -- Una nota PROPRIA (non condivisa) non mostra mai il pulsante. --
    own_note = character_repo.create_campaign_note(c.id, "npc", "Nota personale")
    dv._notes["npc"] = [n for n in dv._notes["npc"] if n.id != shared_note.id]
    own = next(n for n in character_repo.get_campaign_notes(c.id, "npc") if n.id == own_note)
    dv._notes["npc"].append(own)
    panel3 = dv._build_note_reading_panel(own)
    check("una nota propria (non condivisa, niente linked_npc_id nel modello) "
          "non mostra il pulsante «Collegato a»",
          _find_button_containing(panel3, "Collegato a") is None)


def test_master_notes_view_linked_npc_button() -> None:
    print("\n[3b] ui/views/master/master_notes_view.py — stesso pulsante lato Master")
    from ui.views.master.master_notes_view import MasterNotesView

    world, npc, note = _make_world_and_shared_npc_note(with_link=True)

    view = MasterNotesView(world_id=world.id)
    view._page = _FakePage()
    view._load_all()

    panel = view._build_note_reading_panel(note)
    link_btn = _find_button_containing(panel, "PNG collegato: Oswin il Locandiere")
    check("il pulsante «PNG collegato: Oswin il Locandiere» esiste lato Master",
          link_btn is not None)
    assert link_btn is not None
    link_btn.on_click(None)
    check("il click apre lo stesso dossier", bool(view._page.dialogs))
    check("il dossier mostra il nome dell'NPC",
          any("Oswin il Locandiere" in t for t in _texts(view._page.dialogs[-1].content)))


if __name__ == "__main__":
    init_db()
    test_npc_image_data_round_trip()
    test_build_npc_dossier_column()
    test_diary_view_linked_npc_button()
    test_master_notes_view_linked_npc_button()

    print("\n" + "=" * 70)
    print(f"Controlli passati: {_PASS} — falliti: {len(_FAIL)}")
    if _FAIL:
        print("\nControlli falliti:")
        for label in _FAIL:
            print(f"  - {label}")
        raise SystemExit(1)
    print("Tutti i controlli passati.")
