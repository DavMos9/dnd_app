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

**Dal 2026-08-06 copre anche la sola COSTRUZIONE di `MasterView`** (senza
ancora aver aggiunto nulla al controllo wrap+expand): un secondo bug reale,
di natura diversa (`TypeError` Python puro alla creazione del controllo,
`Dropdown(prefix_icon=...)` — kwarg inesistente su `ft.Dropdown`, quello
corretto è `leading_icon`), sollevato dal nuovo selettore mondo
dell'header e segnalato da Davide sia su web sia in locale. `MasterView`
non aveva mai avuto un test di costruzione: costruire ogni tab (con e
senza mondo selezionato) in questo file la esercita comunque, quindi vale
la pena farlo qui piuttosto che aprire un quarto file di test per un
singolo `try/except`.

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


def test_master_view() -> None:
    """
    Costruzione di `MasterView` — aggiunta il 2026-08-06 dopo un bug reale
    segnalato da Davide (`Dropdown.__init__() got an unexpected keyword
    argument 'prefix_icon'` nel nuovo selettore mondo dell'header): a
    differenza del bug wrap+expand, quell'errore è un `TypeError` Python
    puro, sollevato già alla semplice costruzione del controllo — non
    serviva nemmeno ispezionare l'albero, bastava istanziare la vista una
    volta. `MasterView` non aveva MAI avuto un test di costruzione prima
    d'ora (a differenza di `HomeView`/`WorldsView` sopra): qui si copre lo
    stesso terreno per tutte e 5 le tab, con e senza un mondo selezionato
    (i due path di `_world_selector()` sono diversi: senza mondi
    masterabili disponibili same come con almeno uno).
    """
    print("\n[3] MasterView — costruzione di tutte le tab, con e senza mondo selezionato")
    from ui.views.master.master_view import MasterView, _TABS

    device_id = "dev-masterview"
    world = world_repo.create_world("Mondo MasterView", device_id, "Tester")
    check("mondo di test creato", world is not None)

    for mode in ("light", "dark"):
        d.set_mode(mode)
        for active_world_id in ("", world.id if world else ""):
            for tab in _TABS:
                key = tab["key"]
                try:
                    mv = MasterView(on_back_to_home=lambda: None, active_tab=key,
                                    active_world_id=active_world_id)
                    # Bypassa la risoluzione asincrona di did_mount() (stesso
                    # principio di wv.device_id sopra): imposta direttamente
                    # lo stato che _init_identity() avrebbe popolato, poi
                    # ricostruisce per esercitare _world_selector() con
                    # _masterable_worlds non vuoto.
                    mv.device_id = device_id
                    mv._masterable_worlds = [world] if world else []
                    mv._build()
                    conflicts = find_wrap_expand_conflicts(mv, path=f"MasterView.{key}")
                    check(f"[{mode}][mondo={'sì' if active_world_id else 'no'}] "
                          f"tab '{key}' costruita senza errori né conflitti wrap+expand: {conflicts}",
                          conflicts == [])
                except Exception as e:  # noqa: BLE001 — vogliamo il messaggio esatto nel report
                    check(f"[{mode}][mondo={'sì' if active_world_id else 'no'}] "
                          f"tab '{key}' costruita senza sollevare eccezioni: {type(e).__name__}: {e}",
                          False)

    d.set_mode("light")


def test_esplorazione_tab() -> None:
    """
    Costruzione di `EsplorazioneTab` — aggiunta il 2026-08-05 dopo la
    segnalazione di Davide "anche le abilità non si leggono bene da
    smartphone": la sezione Abilità era divisa in due colonne FISSE via
    slicing Python (`skill_items[:mid]`/`skill_items[mid:]`), col nome
    abilità `expand=True` ma senza `no_wrap`/`overflow`/`max_lines` — sullo
    stesso schema del bug del titolo "MODALITÀ MASTER" (Text espanso dentro
    un contenitore schiacciato, nessuna eccezione Python, solo un layout
    illeggibile). Fix: `ft.ResponsiveRow` con `col={"xs": 12, "sm": 6}` per
    riga abilità (una colonna sotto i 576px, due sopra — valutato lato
    client, non da `page.width` in Python) più la stessa protezione
    `no_wrap`/`overflow`/`max_lines` sul nome come rete di sicurezza.
    Questo test verifica solo che la costruzione non sollevi eccezioni
    (`ft.ResponsiveRow`/`col` sono API reali, verificate per introspezione
    prima dell'uso, ma un controllo end-to-end costa poco ed è la stessa
    disciplina già applicata a `MasterView` sopra).
    """
    print("\n[4] EsplorazioneTab — costruzione con la sezione Abilità responsive")
    from ui.views.character_sheet.esplorazione_tab import EsplorazioneTab

    char = _make_guerriero("Esplorazione WrapExpand")
    for mode in ("light", "dark"):
        d.set_mode(mode)
        try:
            tab = EsplorazioneTab(char)
            conflicts = find_wrap_expand_conflicts(tab, path="EsplorazioneTab")
            check(f"[{mode}] EsplorazioneTab costruita senza errori né conflitti "
                  f"wrap+expand: {conflicts}", conflicts == [])
        except Exception as e:  # noqa: BLE001
            check(f"[{mode}] EsplorazioneTab costruita senza sollevare eccezioni: "
                  f"{type(e).__name__}: {e}", False)

    d.set_mode("light")


def test_sheet_view() -> None:
    """
    Costruzione di `SheetView` — aggiunta il 2026-08-06 dopo la stessa
    segnalazione di Davide che ha portato al fix di `MasterView._build_tab_bar()`
    sopra: la tab bar a 5 pillole (Profilo/Combattimento/Esplorazione/
    Inventario/Diario) aveva lo stesso identico difetto — `expand=True` su
    ogni pillola dentro una Row a riga singola, con solo `no_wrap`+`ELLIPSIS`
    come argine — e su smartphone stretto troncava "Combattimento" a "Co...",
    "Esplorazione" a "Espl...". Fix: `wrap=True` sulla Row esterna, pillole
    senza `expand` (si dimensionano sul contenuto, come `design.pill()`).
    `SheetView` non aveva mai avuto un test di costruzione in questo file.
    """
    print("\n[5] SheetView — costruzione tab bar a 5 pillole")
    from ui.views.character_sheet.sheet_view import SheetView

    char = _make_guerriero("Sheet WrapExpand")
    profs = character_repo.get_proficiencies(char.id)

    for mode in ("light", "dark"):
        d.set_mode(mode)
        try:
            sheet = SheetView(char, profs)
            conflicts = find_wrap_expand_conflicts(sheet, path="SheetView")
            check(f"[{mode}] SheetView costruita senza errori né conflitti "
                  f"wrap+expand: {conflicts}", conflicts == [])
        except Exception as e:  # noqa: BLE001
            check(f"[{mode}] SheetView costruita senza sollevare eccezioni: "
                  f"{type(e).__name__}: {e}", False)

    d.set_mode("light")


def main() -> int:
    print("=" * 62)
    print("Regressione — wrap=True + figlio expand=True (riquadro grigio)")
    print(f"HOME di test: {_TMP_HOME}")
    print("=" * 62)

    init_db()
    test_home_view()
    test_worlds_view()
    test_master_view()
    test_esplorazione_tab()
    test_sheet_view()

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
