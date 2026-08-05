"""
Regressione automatica per il bug "wrap=True + figlio expand=True" —
`dnd_app/docs/regole_flet_api.md`: produce un riquadro grigio vuoto lato
Flutter, SENZA alcun errore Python, quindi invisibile a qualunque test che
si limiti a costruire i controlli senza ispezionarne gli attributi.

Trovato per la prima volta il 2026-07-31 nel dialogo di assegnazione del
Bottino, **reintrodotto per errore il 2026-08-05** nella card personaggio di
`ui/views/home_view.py` durante l'aggiunta delle azioni contestuali dei
Mondi (passo 3 del Multiplayer) — segnalato da Davide con uno screenshot,
corretto subito dopo nella stessa sessione.

Questo file cammina l'albero dei controlli REALMENTE costruiti da alcune
view chiave (non il codice sorgente: i valori effettivi degli attributi
`wrap`/`expand` dopo la costruzione) e fallisce se trova una `Row`/`Column`
con `wrap=True` che ha un figlio diretto con `expand` "verita" (`True` o un
intero positivo — Flet accetta anche `expand=2` come peso flex).

Va esteso man mano che si aggiungono nuove view con liste/card, non solo
le due già colpite da questo bug — è un controllo strutturale, non
specifico di una schermata.

Eseguire con:
    PYTHONPATH=".venv/lib/python3.13/site-packages:." python3 test_regressione_wrap_expand.py
"""

from __future__ import annotations

import os
import sys
import tempfile

_TMP_HOME = tempfile.mkdtemp(prefix="dnd_wrapexpand_")
os.environ["HOME"] = _TMP_HOME

import flet as ft  # noqa: E402

from data.database import init_db  # noqa: E402
from data.models import Character  # noqa: E402
from data.repositories import character_repo, world_repo  # noqa: E402
from core import character_instances as ci  # noqa: E402
from ui import design as d  # noqa: E402

_PASS = 0
_FAIL: list[str] = []


def check(label: str, cond: bool) -> None:
    global _PASS
    if cond:
        _PASS += 1
    else:
        _FAIL.append(label)
        print(f"  FALLITO: {label}")


def _truthy_expand(value) -> bool:
    """`expand` in Flet è `bool | int | None`: sia `True` sia un intero
    positivo (peso flex) attivano `Expanded` lato Flutter."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value > 0
    return False


def find_wrap_expand_conflicts(control, path: str = "root", depth: int = 0,
                                results: list[str] | None = None) -> list[str]:
    """
    Cammina l'albero dei controlli (stesso pattern di `_texts()` già usato
    in `test_mondo_senza_rete.py::test_worlds_view`: `controls`/`actions`/
    `content`) e raccoglie i path di ogni `Row`/`Column` con `wrap=True`
    che ha un figlio diretto con `expand` "vero".
    """
    if results is None:
        results = []
    if control is None or depth > 60:
        return results

    if isinstance(control, (ft.Row, ft.Column)) and getattr(control, "wrap", False):
        children = getattr(control, "controls", None) or []
        for i, child in enumerate(children):
            if _truthy_expand(getattr(child, "expand", None)):
                child_kind = type(child).__name__
                results.append(
                    f"{path} [{type(control).__name__} wrap=True] -> "
                    f"figlio #{i} ({child_kind}) con expand={child.expand!r}"
                )

    children = getattr(control, "controls", None)
    if isinstance(children, (list, tuple)):
        for i, child in enumerate(children):
            find_wrap_expand_conflicts(child, f"{path}.controls[{i}]", depth + 1, results)

    actions = getattr(control, "actions", None)
    if isinstance(actions, (list, tuple)):
        for i, child in enumerate(actions):
            find_wrap_expand_conflicts(child, f"{path}.actions[{i}]", depth + 1, results)

    content = getattr(control, "content", None)
    if content is not None and not isinstance(content, str):
        find_wrap_expand_conflicts(content, f"{path}.content", depth + 1, results)

    return results


def _make_guerriero(name: str, level: int = 3) -> Character:
    char = Character(name=name, class_name="Guerriero", race="Umano", level=level,
                     hit_dice_type=10, hit_dice_total=level, hit_dice_remaining=level,
                     str_score=16, dex_score=14, con_score=14, int_score=10,
                     wis_score=12, cha_score=8, hp_max=20, hp_current=20, xp=900)
    character_repo.create(char)
    return character_repo.get_by_id(char.id)


def test_home_view() -> None:
    print("\n[1] HomeView — card locale e card istanza (raggruppata per mondo)")
    from ui.views.home_view import HomeView

    for mode in ("light", "dark"):
        d.set_mode(mode)

        home = HomeView(on_select=lambda i: None, on_create_wizard=lambda: None,
                        on_create_manual=lambda: None)
        home.device_id = "dev-wrapexpand"

        local_char = _make_guerriero(f"Locale {mode}")
        world = world_repo.create_world(f"Mondo WrapExpand {mode}", "dev-wrapexpand", "Tester")
        result = ci.create_or_resume_instance(world.id, local_char.id, "dev-wrapexpand",
                                              mode="as_is")
        check(f"[{mode}] istanza creata per il test", result.success)

        home.refresh(force=True)
        conflicts = find_wrap_expand_conflicts(home._char_list_column, path="HomeView")
        check(f"[{mode}] nessun conflitto wrap+expand nella lista personaggi "
              f"(locali + raggruppati per mondo): {conflicts}", conflicts == [])

    d.set_mode("light")


def test_worlds_view() -> None:
    print("\n[2] WorldsView — elenco, dettaglio, sezione hosting LAN")
    from ui.views.world.world_view import WorldsView

    for mode in ("light", "dark"):
        d.set_mode(mode)

        wv = WorldsView(on_back_to_home=lambda: None)
        wv.device_id = f"dev-wv-{mode}"
        wv._render()
        conflicts = find_wrap_expand_conflicts(wv._body, path="WorldsView.list.empty")
        check(f"[{mode}] elenco mondi vuoto senza conflitti: {conflicts}", conflicts == [])

        world = world_repo.create_world(f"Mondo WV {mode}", wv.device_id, "Tester")
        wv._render()
        conflicts = find_wrap_expand_conflicts(wv._body, path="WorldsView.list.non_vuoto")
        check(f"[{mode}] elenco mondi con una card senza conflitti: {conflicts}", conflicts == [])

        wv._current_world = world
        wv._render()
        conflicts = find_wrap_expand_conflicts(wv._body, path="WorldsView.detail.owner")
        check(f"[{mode}] dettaglio (owner, senza hosting attivo) senza conflitti: {conflicts}",
              conflicts == [])

        wv._start_hosting(world)
        try:
            wv._render()
            conflicts = find_wrap_expand_conflicts(wv._body, path="WorldsView.detail.hosting")
            check(f"[{mode}] sezione hosting LAN attiva senza conflitti: {conflicts}",
                  conflicts == [])
        finally:
            wv._stop_hosting(world)

    d.set_mode("light")


def main() -> int:
    print("=" * 62)
    print("Regressione — wrap=True + figlio expand=True (riquadro grigio)")
    print(f"HOME di test: {_TMP_HOME}")
    print("=" * 62)

    init_db()
    test_home_view()
    test_worlds_view()

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
