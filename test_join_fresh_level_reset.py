"""
Verifica del bug del 2026-08-24, trovato dal vivo da Davide durante il primo
vero test multi-dispositivo: un Barbaro salvato in locale a Lv.11, fatto
entrare in un mondo condiviso con l'opzione "Ricomincia dal 1° livello"
(`mode="fresh"` in `core.character_instances.create_or_resume_instance()`),
mostrava correttamente "Lv.1" nella scheda — ma al primo level-up successivo
è saltato a Lv.12 invece che a Lv.2.

Causa: `core/character_instances.py::_reset_to_level_one()` scriveva
`characters.level = 1` ma non toccava la riga parallela `character_classes`
(ogni personaggio, anche single-class, ne ha una dalla migrazione del
2026-08-12 — vedi `docs/multiclasse_design.md` §2). Il level-up
(`profilo_tab.py::_on_level_up_click`) legge il livello di partenza da
`get_primary_character_class(...).level`, non da `characters.level` — quindi
restava a 11, e 11+1=12 veniva poi ripropagato su `characters.level` da
`sync_character_total_level()`, sovrascrivendo il 2 atteso.

Fix: `_reset_to_level_one()` ora azzera anche la riga `character_classes`
primaria a Lv.1, e rimuove eventuali classi secondarie (un'istanza "Lv.1" è,
per definizione, single-class — la creazione personaggio è sempre
single-class, vedi il flusso multiclasse).

Usa lo stesso pattern `ProfiloTab` + `_FakePage` già collaudato in
`test_level_down_class_sync.py` per guidare `_on_level_up_click` end-to-end,
non solo le funzioni di repository in isolamento.

Eseguire con:
    PYTHONPATH=".venv/lib/python3.13/site-packages:." python3 test_join_fresh_level_reset.py
"""

from __future__ import annotations

import os
import sys
import tempfile

_TMP_HOME = tempfile.mkdtemp(prefix="dnd_join_fresh_level_")
os.environ["HOME"] = _TMP_HOME

import flet as ft  # noqa: E402

from data.database import init_db  # noqa: E402
from data.models import Character  # noqa: E402
from data.repositories import character_repo, world_repo  # noqa: E402
from core import character_instances as ci  # noqa: E402

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
    def __init__(self):
        self.dialogs = []

    def show_dialog(self, dlg):
        self.dialogs.append(dlg)

    def pop_dialog(self):
        pass

    def update(self):
        pass


def _walk(ctrl):
    yield ctrl
    for attr in ("controls", "content", "actions"):
        v = getattr(ctrl, attr, None)
        if isinstance(v, list):
            for c in v:
                yield from _walk(c)
        elif v is not None and (hasattr(v, "controls") or hasattr(v, "content")):
            yield from _walk(v)


def _find_button(dlg, text_contains: str) -> ft.ElevatedButton:
    btn = next((c for c in _walk(dlg) if isinstance(c, ft.ElevatedButton)
                and text_contains in str(getattr(c, "content", "") or getattr(c, "text", ""))), None)
    assert btn is not None, f"nessun pulsante contenente {text_contains!r} nel dialog"
    return btn


def _dialog_title(dlg: ft.AlertDialog) -> str:
    texts = [c.value for c in _walk(dlg) if isinstance(c, ft.Text) and c.value]
    return " ".join(texts)


def _make_barbaro(level: int) -> Character:
    c = Character(
        name="Grondar", class_name="Barbaro", race="Mezzorco", level=level,
        hit_dice_type=12, hit_dice_total=level, hit_dice_remaining=level,
        str_score=18, dex_score=14, con_score=16, int_score=8,
        wis_score=10, cha_score=8, hp_max=12 * level, hp_current=12 * level,
    )
    character_repo.create(c)
    return c


def _profilo_tab(c: Character):
    from ui.views.character_sheet.profilo_tab import ProfiloTab
    tab = ProfiloTab(c, character_repo.get_proficiencies(c.id))
    fake_page = _FakePage()
    tab._page = fake_page
    return tab, fake_page


def test_reset_a_livello_uno_azzera_anche_character_classes() -> None:
    print("\n[1] mode='fresh' azzera characters.level E character_classes.level "
          "(bug: solo il primo veniva toccato)")

    local_char = _make_barbaro(11)
    primary_before = character_repo.get_primary_character_class(local_char.id)
    check("classe primaria a Lv.11 prima del join", primary_before.level == 11)

    world = world_repo.create_world("Mondo Reset Livello", "dev-owner", "Il Master")
    assert world is not None

    result = ci.create_or_resume_instance(world.id, local_char.id, "dev-owner", mode="fresh")
    check("l'istanza 'fresh' viene creata con successo", result.success)

    instance = character_repo.get_by_id(result.character_id)
    check("characters.level dell'istanza è 1", instance is not None and instance.level == 1)

    primary_after = character_repo.get_primary_character_class(result.character_id)
    check("character_classes.level dell'istanza è anch'esso 1 (bug: restava 11)",
          primary_after is not None and primary_after.level == 1)


def test_level_up_dopo_reset_propone_livello_2_non_12() -> None:
    print("\n[2] Riproduzione esatta del bug dal vivo: dopo il reset 'fresh', "
          "il primo Level Up deve proporre Livello 2, non 12")

    local_char = _make_barbaro(11)
    world = world_repo.create_world("Mondo Reset Livello 2", "dev-owner", "Il Master")
    assert world is not None

    result = ci.create_or_resume_instance(world.id, local_char.id, "dev-owner", mode="fresh")
    assert result.success, result.error
    instance = character_repo.get_by_id(result.character_id)
    assert instance is not None and instance.level == 1

    tab, fake_page = _profilo_tab(instance)
    tab._on_level_up_click(None)
    dlg = fake_page.dialogs[-1]
    title = _dialog_title(dlg)
    check("il dialog Level Up propone Livello 2 (bug: proponeva Livello 12)",
          "Avanzamento a Livello 2" in title)
    check("NON propone Livello 12 (sintomo esatto del bug)",
          "Avanzamento a Livello 12" not in title)

    _find_button(dlg, "Sali a Lv.2").on_click(None)
    after = character_repo.get_by_id(instance.id)
    check("dopo il level-up characters.level è 2 (bug: diventava 12)",
          after.level == 2)
    primary = character_repo.get_primary_character_class(instance.id)
    check("character_classes.level è anch'esso 2, nessun disallineamento",
          primary.level == 2 and primary.level == after.level)


def main() -> int:
    init_db()
    print("=" * 72)
    print("Reset character_classes.level su join 'fresh' (bug 2026-08-24)")
    print(f"HOME di test: {_TMP_HOME}")
    print("=" * 72)

    test_reset_a_livello_uno_azzera_anche_character_classes()
    test_level_up_dopo_reset_propone_livello_2_non_12()

    print("\n" + "=" * 72)
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
