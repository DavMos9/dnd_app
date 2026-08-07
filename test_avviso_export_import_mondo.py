"""
Verifica del fix 2026-08-07 (sessione successiva) — Davide, dopo aver
chiesto come sono gestiti gli accessi/le sessioni tra dispositivi: "se
questo personaggio viene esportato su un altro dispositivo?" ha fatto
emergere che `character_export.import_character()` azzera SEMPRE
`world_id`/`origin_character_id`/`owner_device_id`/`is_replica`/
`world_seq` (comportamento preesistente, per design — un file esportato
da un'istanza di mondo diventerebbe altrimenti una "replica" di un mondo
inesistente sul dispositivo di destinazione, bloccata in sola lettura),
ma questo avveniva IN SILENZIO: nessun errore, nessun avviso, l'utente
scopriva solo dopo che il personaggio aveva "perso" il mondo. Richiesta
esplicita: "aggiungi un avviso per l'utente".

Fix: due dialoghi gemelli in `ui/views/home_view.py`, entrambi opzionali
(l'utente può procedere comunque — l'esportazione resta comunque utile
come backup locale, e niente qui impedisce di importare un personaggio
world-linked, solo lo segnala prima):
  - `_on_export_click()` → se `char.world_id` è valorizzato, mostra
    `_confirm_export_world_linked()` PRIMA di procedere
    (`_proceed_export()`, il corpo del vecchio `_on_export_click` estratto
    così com'era); altrimenti procede subito, nessun passaggio in più per
    il caso comune (personaggio locale).
  - `_do_import_from_text()` → se `data["character"]["world_id"]` è
    valorizzato, mostra `_show_import_world_linked_warning()` PRIMA di
    procedere (`_continue_import()`, il corpo del vecchio flusso —
    conflitto d'id o importazione diretta — estratto così com'era);
    altrimenti procede subito.

Copre:
  1-3. Personaggio LOCALE (`world_id == ""`): nessun avviso, né in export
       né in import — l'app non deve rallentare il caso comune.
  4-6. Personaggio legato a un mondo, in EXPORT: il dialogo compare,
       «Annulla» non esporta nulla, «Esporta comunque» procede davvero.
  7-9. Stesso file, in IMPORT su un altro "dispositivo" (stesso DB di
       test, ID diverso per evitare il conflitto): il dialogo compare,
       «Annulla» non importa nulla, «Importa comunque» importa DAVVERO e
       il personaggio risultante ha `world_id`/`owner_device_id` azzerati
       (riconferma, in corsa, che lo zeroing preesistente di
       `import_character()` non è stato toccato da questo fix — il
       nuovo avviso si limita a INFORMARE, mai a cambiare cosa succede
       dopo la conferma).
  10. Il mondo di origine può anche non esistere più sul dispositivo che
      importa (es. cancellato) — il messaggio deve comunque comparire,
      con un testo di ripiego invece di un errore.

Eseguire con:
    PYTHONPATH=".venv/lib/python3.13/site-packages:." python3 test_avviso_export_import_mondo.py
"""

from __future__ import annotations

import os
import sys
import tempfile

_TMP_HOME = tempfile.mkdtemp(prefix="dnd_avviso_export_import_")
os.environ["HOME"] = _TMP_HOME

import flet as ft  # noqa: E402

from data.database import get_connection, init_db  # noqa: E402
from data.models import Character  # noqa: E402
from data.repositories import character_export, character_repo, world_repo  # noqa: E402

_PASS = 0
_FAIL: list[str] = []


def check(label: str, cond: bool) -> None:
    global _PASS
    if cond:
        _PASS += 1
    else:
        _FAIL.append(label)
        print(f"  FALLITO: {label}")


def _patch_homeview_page_property() -> None:
    """Stesso principio (e stesso motivo) di `_patch_worlds_view_page_
    property()` in `test_ingresso_lan_sincronizzazione.py`: `HomeView` usa
    ovunque `self.page`, la proprietà vera di Flet (nessun `self._page`
    cache-ato come in `MasterEncounterView`), che non ha setter e richiede
    un controllo davvero agganciato a una `Page` — qui sostituita SOLO
    sulla classe `HomeView` con una che legge da un attributo d'istanza
    `_test_fake_page`."""
    from ui.views.home_view import HomeView

    if getattr(HomeView, "_test_page_patched", False):
        return
    original_page_property = HomeView.page

    def _page_getter(self):
        fake = getattr(self, "_test_fake_page", None)
        if fake is not None:
            return fake
        return original_page_property.fget(self)

    HomeView.page = property(_page_getter)
    HomeView._test_page_patched = True


class _FakePage:
    def __init__(self):
        self.dialogs: list = []
        self.web = False
        self.platform = None  # non Android/iOS/web: qualunque export reale andrebbe sul ramo desktop

    def show_dialog(self, dlg) -> None:
        self.dialogs.append(dlg)

    def pop_dialog(self, *_a) -> None:
        if self.dialogs:
            self.dialogs.pop()

    def update(self, *_a, **_k) -> None:
        pass


def _find_by_content(controls: list, text: str):
    """`ElevatedButton`/`TextButton` in Flet 0.86.5 tengono l'etichetta in
    `.content` (una stringa passata così com'è), non in `.text` —
    verificato empiricamente, vedi `dnd_app/docs/regole_flet_api.md`."""
    for c in controls:
        if getattr(c, "content", None) == text:
            return c
    return None


def _make_home_view(device_id: str = "dev-test"):
    from ui.views.home_view import HomeView

    view = HomeView.__new__(HomeView)  # bypassa __init__: non serve l'intera UI per questi metodi
    view.device_id = device_id
    view.refresh = lambda force=True: None  # type: ignore[method-assign]
    page = _FakePage()
    view._test_fake_page = page  # type: ignore[attr-defined]
    errors: list[str] = []
    successes: list[str] = []
    view._show_error = lambda msg: errors.append(msg)  # type: ignore[method-assign]
    view._show_success = lambda msg: successes.append(msg)  # type: ignore[method-assign]
    return view, page, errors, successes


def _make_character(name: str, world_id: str = "", owner_device_id: str = "") -> Character:
    c = Character(name=name, class_name="Mago", race="Elfo", level=4,
                   hp_max=20, hp_current=20, xp=0)
    character_repo.create(c)
    if world_id:
        conn = get_connection()
        conn.execute(
            "UPDATE characters SET world_id=?, origin_character_id=?, owner_device_id=? "
            "WHERE id=?",
            (world_id, c.id, owner_device_id, c.id),
        )
        conn.commit()
        conn.close()
        c = character_repo.get_by_id(c.id)
    return c


# ---------------------------------------------------------------------------
# Personaggio locale: nessun avviso, né export né import
# ---------------------------------------------------------------------------

def test_export_local_character_no_warning() -> None:
    print("\n[1] Esportare un personaggio LOCALE non mostra alcun avviso")
    char = _make_character("Personaggio Locale Export")
    check("il personaggio è davvero locale (world_id vuoto)", not char.world_id)

    view, page, _errors, _successes = _make_home_view()
    proceeded: list[Character] = []
    view._proceed_export = lambda c: proceeded.append(c)  # type: ignore[method-assign]

    view._on_export_click(char)
    check("nessun dialogo mostrato per un personaggio locale", len(page.dialogs) == 0)
    check("l'esportazione procede subito", len(proceeded) == 1 and proceeded[0].id == char.id)


def test_import_local_character_no_warning() -> None:
    print("\n[2] Importare un file di un personaggio LOCALE non mostra alcun avviso")
    char = _make_character("Personaggio Locale Import")
    data = character_export.export_character(char.id)
    assert data is not None
    check("il file esportato ha world_id vuoto",
          not str(data["character"].get("world_id") or ""))
    character_repo.delete(char.id)  # simula "importato su un dispositivo che non lo ha ancora"

    view, page, errors, _successes = _make_home_view()
    import json
    text = json.dumps(data)

    view._do_import_from_text(text)
    check("nessun dialogo di avviso mondo mostrato", len(page.dialogs) == 0)
    check("nessun errore", not errors)
    check("il personaggio è stato importato davvero",
          character_repo.get_by_id(char.id) is not None)


def test_export_and_import_symmetry_no_warning_message() -> None:
    print("\n[3] La firma di `_do_import_from_text` non richiede alcuna modifica al "
          "chiamante per il caso comune (nessuna regressione sull'API)")
    char = _make_character("Personaggio Locale Simmetria")
    view, _page, errors, _successes = _make_home_view()
    view._continue_import_calls = 0  # type: ignore[attr-defined]
    original_continue = view._continue_import

    def _spy(data, summary):
        view._continue_import_calls += 1  # type: ignore[attr-defined]
        return original_continue(data, summary)

    view._continue_import = _spy  # type: ignore[method-assign]
    import json
    data = character_export.export_character(char.id)
    character_repo.delete(char.id)
    view._do_import_from_text(json.dumps(data))
    check("_continue_import viene chiamato direttamente (nessun avviso di mezzo)",
          view._continue_import_calls == 1)  # type: ignore[attr-defined]
    check("nessun errore", not errors)


# ---------------------------------------------------------------------------
# Personaggio legato a un mondo — EXPORT
# ---------------------------------------------------------------------------

def test_export_world_linked_shows_warning_and_cancel_blocks() -> None:
    print("\n[4] Esportare un personaggio di un MONDO mostra l'avviso; «Annulla» non esporta")
    world = world_repo.create_world("Mondo Avviso Export", "dev-master", "Il Master")
    assert world is not None
    char = _make_character("Personaggio Del Mondo", world_id=world.id, owner_device_id="dev-test")
    check("il personaggio è davvero legato al mondo", bool(char.world_id))

    view, page, _errors, _successes = _make_home_view()
    proceeded: list[Character] = []
    view._proceed_export = lambda c: proceeded.append(c)  # type: ignore[method-assign]

    view._on_export_click(char)
    check("il dialogo di avviso compare", len(page.dialogs) == 1)
    check("l'esportazione NON è ancora avvenuta", not proceeded)

    dlg = page.dialogs[-1]
    check("il nome del mondo compare nel messaggio",
          any("Mondo Avviso Export" in t for t in _texts(dlg)))

    cancel_btn = _find_by_content(dlg.actions[0].controls, "Annulla")
    assert cancel_btn is not None
    cancel_btn.on_click(None)
    check("«Annulla» chiude il dialogo", len(page.dialogs) == 0)
    check("«Annulla» non esporta nulla", not proceeded)


def test_export_world_linked_proceed_anyway() -> None:
    print("\n[5] «Esporta comunque» procede davvero con l'esportazione")
    world = world_repo.create_world("Mondo Avviso Export 2", "dev-master", "Il Master")
    assert world is not None
    char = _make_character("Personaggio Del Mondo 2", world_id=world.id, owner_device_id="dev-test")

    view, page, _errors, _successes = _make_home_view()
    proceeded: list[Character] = []
    view._proceed_export = lambda c: proceeded.append(c)  # type: ignore[method-assign]

    view._on_export_click(char)
    dlg = page.dialogs[-1]
    proceed_btn = _find_by_content(dlg.actions[0].controls, "Esporta comunque")
    assert proceed_btn is not None
    proceed_btn.on_click(None)
    check("il dialogo si chiude", len(page.dialogs) == 0)
    check("l'esportazione procede davvero", len(proceeded) == 1 and proceeded[0].id == char.id)


def test_export_world_linked_missing_world_fallback_text() -> None:
    print("\n[6] Se il mondo non esiste più sul dispositivo, l'avviso compare comunque "
          "(testo di ripiego, non un errore)")
    char = _make_character("Personaggio Mondo Fantasma", world_id="mondo-inesistente-xyz",
                            owner_device_id="dev-test")

    view, page, errors, _successes = _make_home_view()
    view._proceed_export = lambda c: None  # type: ignore[method-assign]
    view._on_export_click(char)
    check("il dialogo compare comunque", len(page.dialogs) == 1)
    check("nessun errore sollevato per il mondo mancante", not errors)
    dlg = page.dialogs[-1]
    check("il messaggio usa il testo di ripiego",
          any("non più presente" in t for t in _texts(dlg)))


# ---------------------------------------------------------------------------
# Personaggio legato a un mondo — IMPORT
# ---------------------------------------------------------------------------

def test_import_world_linked_shows_warning_and_cancel_blocks() -> None:
    print("\n[7] Importare il file di un personaggio di un MONDO mostra l'avviso; "
          "«Annulla» non importa nulla")
    world = world_repo.create_world("Mondo Avviso Import", "dev-master", "Il Master")
    assert world is not None
    char = _make_character("Personaggio Da Importare", world_id=world.id, owner_device_id="dev-altro")
    data = character_export.export_character(char.id)
    assert data is not None
    check("il file ha world_id valorizzato", bool(data["character"].get("world_id")))
    character_repo.delete(char.id)  # "il dispositivo che importa non ce l'ha ancora"

    view, page, errors, _successes = _make_home_view()
    import json
    view._do_import_from_text(json.dumps(data))
    check("il dialogo di avviso compare", len(page.dialogs) == 1)
    check("nessun errore", not errors)
    check("il personaggio NON è stato importato", character_repo.get_by_id(char.id) is None)

    dlg = page.dialogs[-1]
    cancel_btn = _find_by_content(dlg.actions[0].controls, "Annulla")
    assert cancel_btn is not None
    cancel_btn.on_click(None)
    check("«Annulla» chiude il dialogo", len(page.dialogs) == 0)
    check("«Annulla» non importa nulla", character_repo.get_by_id(char.id) is None)


def test_import_world_linked_proceed_anyway_strips_world_link() -> None:
    print("\n[8] «Importa comunque» importa DAVVERO, e il personaggio risultante NON è "
          "più legato ad alcun mondo (lo zeroing preesistente non è stato toccato)")
    world = world_repo.create_world("Mondo Avviso Import 2", "dev-master", "Il Master")
    assert world is not None
    char = _make_character("Personaggio Da Importare 2", world_id=world.id,
                            owner_device_id="dev-altro")
    data = character_export.export_character(char.id)
    assert data is not None
    character_repo.delete(char.id)

    view, page, errors, successes = _make_home_view()
    import json
    view._do_import_from_text(json.dumps(data))
    dlg = page.dialogs[-1]
    proceed_btn = _find_by_content(dlg.actions[0].controls, "Importa comunque")
    assert proceed_btn is not None
    proceed_btn.on_click(None)

    check("il dialogo si chiude", len(page.dialogs) == 0)
    check("nessun errore", not errors)
    check("un messaggio di successo viene mostrato", len(successes) == 1)

    imported = character_repo.get_by_id(char.id)
    check("il personaggio è stato importato davvero", imported is not None)
    check("world_id è stato azzerato (comportamento preesistente, invariato)",
          imported is not None and imported.world_id == "")
    check("owner_device_id è stato azzerato",
          imported is not None and imported.owner_device_id == "")


def test_import_world_linked_missing_world_fallback_text() -> None:
    print("\n[9] Import: stesso testo di ripiego se il mondo di origine non esiste più "
          "sul dispositivo che importa")
    char = _make_character("Personaggio Import Mondo Fantasma", world_id="altro-mondo-inesistente",
                            owner_device_id="dev-altro")
    data = character_export.export_character(char.id)
    assert data is not None
    character_repo.delete(char.id)

    view, page, errors, _successes = _make_home_view()
    import json
    view._do_import_from_text(json.dumps(data))
    check("il dialogo compare comunque", len(page.dialogs) == 1)
    check("nessun errore", not errors)
    dlg = page.dialogs[-1]
    check("il messaggio usa il testo di ripiego",
          any("non più presente" in t for t in _texts(dlg)))


def _texts(control) -> list[str]:
    """Estrae ricorsivamente il testo (`.value`/`.content` se stringa) da
    un albero di controlli Flet — stesso principio del walker `texts()`
    già in uso in `test_fase_4.py`, riscritto qui in forma minima."""
    out: list[str] = []
    value = getattr(control, "value", None)
    if isinstance(value, str):
        out.append(value)
    content = getattr(control, "content", None)
    if isinstance(content, str):
        out.append(content)
    elif content is not None:
        out.extend(_texts(content))
    for attr in ("controls", "actions"):
        children = getattr(control, attr, None)
        if children:
            for c in children:
                out.extend(_texts(c))
    return out


def main() -> int:
    init_db()
    _patch_homeview_page_property()
    print("=" * 70)
    print("Avviso export/import per un personaggio legato a un mondo condiviso")
    print(f"HOME di test: {_TMP_HOME}")
    print("=" * 70)

    test_export_local_character_no_warning()
    test_import_local_character_no_warning()
    test_export_and_import_symmetry_no_warning_message()
    test_export_world_linked_shows_warning_and_cancel_blocks()
    test_export_world_linked_proceed_anyway()
    test_export_world_linked_missing_world_fallback_text()
    test_import_world_linked_shows_warning_and_cancel_blocks()
    test_import_world_linked_proceed_anyway_strips_world_link()
    test_import_world_linked_missing_world_fallback_text()

    print("\n" + "=" * 70)
    print(f"Controlli passati: {_PASS} — falliti: {len(_FAIL)}")
    if _FAIL:
        print("Falliti:")
        for f in _FAIL:
            print(f"  - {f}")
        return 1
    print("Tutti i controlli passati.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
