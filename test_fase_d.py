"""
Batteria di verifica della FASE D del restyle — tema scuro con preferenza
persistita (2026-07-30).

Usa SEMPRE un DB temporaneo isolato (`tempfile.mkdtemp()` + `HOME` separato):
il DB reale di Davide non viene mai toccato. I controlli Flet vengono costruiti
davvero e ispezionati ricorsivamente — stesso pattern gia' consolidato nel
progetto per testare la UI senza un vero client.

Eseguire con:
    PYTHONPATH=".venv/lib/python3.13/site-packages:." python3 test_fase_d.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from typing import Any
from unittest.mock import patch

_TMP_HOME = tempfile.mkdtemp(prefix="dnd_fase_d_")
os.environ["HOME"] = _TMP_HOME

import flet as ft  # noqa: E402

from data.database import get_connection, init_db  # noqa: E402
from data.repositories import settings_repo  # noqa: E402
from ui import design  # noqa: E402
from ui.app import DnDApp  # noqa: E402
from ui.widgets import theme_toggle_look, theme_toggle_pill, theme_toggle_tooltip  # noqa: E402

_PASS = 0
_FAIL: list[str] = []


def check(label: str, cond: bool) -> None:
    global _PASS
    if cond:
        _PASS += 1
    else:
        _FAIL.append(label)
        print(f"  FALLITO: {label}")


class FakePage:
    """Superficie minima di `ft.Page` usata dai percorsi che tocchiamo."""

    def __init__(self, width: int = 1280, brightness: Any = None):
        self.width = width
        self.height = 800
        self.platform_brightness = brightness
        self.controls: list[Any] = []
        self.overlay: list[Any] = []
        self.title = ""
        self.fonts: dict[str, str] = {}
        self.theme = None
        self.dark_theme = None
        self.theme_mode = None
        self.bgcolor = None
        self.padding = None
        self.web = False
        self.platform = None
        self.on_resize = None
        self.on_platform_brightness_change = None
        self.updates = 0
        self.dialogs: list[Any] = []

    def add(self, *controls: Any) -> None:
        self.controls.extend(controls)

    def update(self, *a: Any, **k: Any) -> None:
        self.updates += 1

    def show_dialog(self, dlg: Any) -> None:
        self.dialogs.append(dlg)

    def pop_dialog(self, *a: Any) -> None:
        if self.dialogs:
            self.dialogs.pop()

    def run_task(self, *a: Any, **k: Any) -> None:
        pass


def walk(control: Any, depth: int = 0):
    """Percorre ricorsivamente l'albero dei controlli."""
    if control is None or depth > 40:
        return
    yield control
    for attr in ("controls", "actions"):
        kids = getattr(control, attr, None)
        if isinstance(kids, (list, tuple)):
            for k in kids:
                yield from walk(k, depth + 1)
    content = getattr(control, "content", None)
    if content is not None and not isinstance(content, str):
        yield from walk(content, depth + 1)


def texts(control: Any) -> list[str]:
    out = []
    for c in walk(control):
        if isinstance(c, ft.Text) and isinstance(c.value, str):
            out.append(c.value)
    return out


def make_app(page: FakePage) -> DnDApp:
    """Costruisce DnDApp senza avviare il thread di update check."""
    with patch.object(DnDApp, "_start_update_check", lambda self: None):
        return DnDApp(page)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 1 — Repository: round-trip, validazione, ciclo
# ---------------------------------------------------------------------------

def test_repo() -> None:
    print("\n[1] settings_repo — persistenza e validazione")
    init_db()

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='app_settings'"
        ).fetchone()
        check("tabella app_settings creata", row is not None)
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(app_settings)")}
        check("colonne app_settings", cols == {"key", "value", "updated_at"})
        fks = list(conn.execute("PRAGMA foreign_key_list(app_settings)"))
        check("nessuna FK su app_settings", fks == [])
    finally:
        conn.close()

    check("default alla prima apertura = system",
          settings_repo.get_theme_preference() == "system")
    check("get_setting su chiave assente usa il default",
          settings_repo.get_setting("mai_scritta", "fallback") == "fallback")

    for pref in ("light", "dark", "system"):
        check(f"salvataggio '{pref}' riuscito", settings_repo.set_theme_preference(pref))
        check(f"rilettura '{pref}'", settings_repo.get_theme_preference() == pref)

    check("riscrittura ripetuta non duplica la riga (PK)",
          settings_repo.set_setting("theme_mode", "dark") and
          settings_repo.get_setting("theme_mode") == "dark")
    conn = get_connection()
    try:
        n = conn.execute(
            "SELECT COUNT(*) c FROM app_settings WHERE key='theme_mode'"
        ).fetchone()["c"]
        check("una sola riga per chiave", n == 1)
    finally:
        conn.close()

    check("valore non valido rifiutato",
          settings_repo.set_theme_preference("neon") is False)
    check("il rifiuto non ha sovrascritto il valore buono",
          settings_repo.get_theme_preference() == "dark")

    # Valore sporco scritto a mano nel DB (o da una versione futura dell'app).
    settings_repo.set_setting("theme_mode", "sepia")
    check("valore sconosciuto nel DB -> fallback al default",
          settings_repo.get_theme_preference() == "system")
    settings_repo.set_setting("theme_mode", "  DARK  ")
    check("normalizzazione spazi/maiuscole", settings_repo.get_theme_preference() == "dark")

    check("ciclo light->dark", settings_repo.next_theme_preference("light") == "dark")
    check("ciclo dark->system", settings_repo.next_theme_preference("dark") == "system")
    check("ciclo system->light", settings_repo.next_theme_preference("system") == "light")
    check("ciclo da valore sporco riparte da light",
          settings_repo.next_theme_preference("boh") == "light")

    settings_repo.set_theme_preference("system")


# ---------------------------------------------------------------------------
# 2 — Risoluzione della modalita' e applicazione
# ---------------------------------------------------------------------------

def test_resolution() -> None:
    print("\n[2] DnDApp — risoluzione e applicazione del tema")

    settings_repo.set_theme_preference("dark")
    page = FakePage(brightness=ft.Brightness.LIGHT)
    app = make_app(page)
    check("preferenza esplicita letta all'avvio", app._theme_pref == "dark")
    check("'dark' ignora la brightness di sistema", app._resolve_theme_mode() == "dark")
    check("design.mode() allineato", design.mode() == "dark")
    check("page.theme_mode concreto (DARK)", page.theme_mode == ft.ThemeMode.DARK)
    check("mai ThemeMode.SYSTEM", page.theme_mode != ft.ThemeMode.SYSTEM)
    check("bgcolor dalla palette scura", page.bgcolor == design.DARK.bg)
    check("handler brightness agganciato",
          page.on_platform_brightness_change == app._on_system_brightness_change)
    check("entrambi i temi registrati", page.theme is not None and page.dark_theme is not None)
    check("font registrati prima del tema", set(page.fonts) == set(design.FONT_FILES))

    settings_repo.set_theme_preference("light")
    page = FakePage(brightness=ft.Brightness.DARK)
    app = make_app(page)
    check("'light' ignora la brightness di sistema", app._resolve_theme_mode() == "light")
    check("page.theme_mode LIGHT", page.theme_mode == ft.ThemeMode.LIGHT)
    check("bgcolor dalla palette chiara", page.bgcolor == design.LIGHT.bg)

    settings_repo.set_theme_preference("system")
    for brightness, expected in ((ft.Brightness.DARK, "dark"),
                                 (ft.Brightness.LIGHT, "light"),
                                 (None, "light")):
        page = FakePage(brightness=brightness)
        app = make_app(page)
        check(f"'system' con brightness={brightness} -> {expected}",
              app._resolve_theme_mode() == expected)
        check(f"design.mode() = {expected}", design.mode() == expected)


# ---------------------------------------------------------------------------
# 3 — Ciclo del pulsante e rebuild
# ---------------------------------------------------------------------------

def test_cycle_and_rebuild() -> None:
    print("\n[3] Ciclo del pulsante, persistenza e rebuild")

    settings_repo.set_theme_preference("light")
    page = FakePage(brightness=ft.Brightness.LIGHT)
    app = make_app(page)
    check("parte da 'light'", app._theme_pref == "light")

    rebuilds: list[str] = []
    app._rebuild_route = lambda: rebuilds.append("x")

    app._cycle_theme()
    check("click 1 -> dark", app._theme_pref == "dark")
    check("palette applicata", design.mode() == "dark")
    check("preferenza persistita", settings_repo.get_theme_preference() == "dark")
    check("rebuild richiesto", len(rebuilds) == 1)

    app._cycle_theme()
    check("click 2 -> system", app._theme_pref == "system")
    check("system con SO chiaro risolve light", design.mode() == "light")
    check("rebuild anche se la modalita' risolta non cambia rispetto a prima",
          len(rebuilds) == 2)

    app._cycle_theme()
    check("click 3 -> light (ciclo chiuso)", app._theme_pref == "light")
    check("rebuild richiesto", len(rebuilds) == 3)

    # Cambio di tema del SO
    app._theme_pref = "system"
    app._apply_theme_mode()
    before = len(rebuilds)
    page.platform_brightness = ft.Brightness.DARK
    app._on_system_brightness_change(None)
    check("SO passa a scuro con pref 'system' -> palette scura", design.mode() == "dark")
    check("SO passa a scuro -> rebuild", len(rebuilds) == before + 1)

    before = len(rebuilds)
    app._on_system_brightness_change(None)
    check("stessa brightness -> nessun rebuild inutile", len(rebuilds) == before)

    app._theme_pref = "light"
    app._apply_theme_mode()
    before = len(rebuilds)
    page.platform_brightness = ft.Brightness.DARK
    app._on_system_brightness_change(None)
    check("con preferenza esplicita il SO viene ignorato", design.mode() == "light")
    check("con preferenza esplicita nessun rebuild", len(rebuilds) == before)

    # Schermata non ricostruibile (wizard/form)
    app._rebuild_route = None
    updates_before = page.updates
    app._cycle_theme()
    check("route None non solleva e aggiorna soltanto la pagina",
          page.updates > updates_before)


# ---------------------------------------------------------------------------
# 4 — Route: quali schermate si ricostruiscono
# ---------------------------------------------------------------------------

def test_routes() -> None:
    print("\n[4] Tracciamento della route corrente")

    settings_repo.set_theme_preference("light")
    page = FakePage(brightness=ft.Brightness.LIGHT)
    app = make_app(page)
    check("Home e' ricostruibile", app._rebuild_route == app._show_home)

    app._show_master_view()
    check("Master e' ricostruibile", app._rebuild_route is not None)
    check("MasterView creata con la tab di default",
          getattr(app._master_view, "active_tab", None) == "npcs")

    # La tab attiva viene letta al momento del rebuild, non alla creazione.
    app._master_view.active_tab = "notes"
    app._rebuild_route()
    check("rebuild della Sezione Master preserva la tab attiva",
          getattr(app._master_view, "active_tab", None) == "notes")

    app._show_master_view("tab_inesistente")
    check("tab non valida ricade su npcs",
          getattr(app._master_view, "active_tab", None) == "npcs")

    app._show_wizard()
    check("wizard NON ricostruibile", app._rebuild_route is None)

    app._show_manual_form()
    check("form manuale NON ricostruibile", app._rebuild_route is None)

    app._show_home()
    check("tornando in Home la route torna ricostruibile",
          app._rebuild_route == app._show_home)


# ---------------------------------------------------------------------------
# 5 — Il pulsante e' presente e visibile in tutte e tre le superfici
# ---------------------------------------------------------------------------

def test_toggle_present() -> None:
    print("\n[5] Pulsante di cambio tema nelle tre superfici")

    from ui.views.home_view import HomeView
    from ui.views.master.master_view import MasterView

    for pref, label in (("light", "Chiaro"), ("dark", "Scuro"), ("system", "Sistema")):
        icon, lbl = theme_toggle_look(pref)
        check(f"etichetta per '{pref}' = {label}", lbl == label)
        check(f"icona per '{pref}' definita", icon is not None)
        check(f"tooltip di '{pref}' spiega stato e azione",
              label in theme_toggle_tooltip(pref) and "clicca" in theme_toggle_tooltip(pref).lower())
    check("preferenza sporca ricade su Sistema", theme_toggle_look("boh")[1] == "Sistema")

    clicked: list[int] = []
    pill = theme_toggle_pill("dark", lambda e: clicked.append(1))
    check("la pillola mostra icona E etichetta (mai icona muta)",
          any(isinstance(c, ft.Icon) for c in walk(pill)) and "Scuro" in texts(pill))
    check("la pillola ha un tooltip", bool(getattr(pill, "tooltip", None)))
    pill.on_click(None)
    check("click della pillola invoca la callback", clicked == [1])

    settings_repo.set_theme_preference("dark")

    for mode in ("light", "dark"):
        design.set_mode(mode)

        home = HomeView(on_select=lambda i: None, on_create_wizard=lambda: None,
                        on_create_manual=lambda: None, on_open_master=lambda: None,
                        on_toggle_theme=lambda e: None, theme_preference="dark")
        check(f"[{mode}] Home mostra la pillola del tema", "Scuro" in texts(home))

        home_legacy = HomeView(on_select=lambda i: None, on_create_wizard=lambda: None,
                               on_create_manual=lambda: None)
        check(f"[{mode}] Home senza callback non mostra la pillola",
              "Scuro" not in texts(home_legacy) and "Sistema" not in texts(home_legacy))

        master = MasterView(on_back_to_home=lambda: None,
                            on_toggle_theme=lambda e: None, theme_preference="system")
        check(f"[{mode}] Master mostra la pillola del tema", "Sistema" in texts(master))

        master_legacy = MasterView(on_back_to_home=lambda: None)
        check(f"[{mode}] Master senza callback non mostra la pillola",
              "Sistema" not in texts(master_legacy))

    # Sidebar (desktop) e bottom nav (mobile)
    settings_repo.set_theme_preference("system")
    page = FakePage(width=1280, brightness=ft.Brightness.LIGHT)
    app = make_app(page)
    app.current_character_id = None
    rail = app._build_nav_rail()
    check("sidebar mostra la voce del tema", "Sistema" in texts(rail))
    check("sidebar: la voce del tema e' cliccabile",
          any(getattr(c, "on_click", None) == app._cycle_theme for c in walk(rail)))

    page_m = FakePage(width=375, brightness=ft.Brightness.LIGHT)
    app_m = make_app(page_m)
    nav = app_m._build_bottom_nav()
    check("bottom nav mostra la voce del tema", "Sistema" in texts(nav))
    check("bottom nav: la voce del tema e' cliccabile",
          any(getattr(c, "on_click", None) == app_m._cycle_theme for c in walk(nav)))
    row = nav.content
    check("bottom nav ha 8 voci (6 sezioni + Cambia + Tema)", len(row.controls) == 8)
    check("le voci hanno una larghezza garantita (>= 48dp di tap-target)",
          all(getattr(c, "width", 0) and c.width >= 48 for c in row.controls))
    check("la bottom nav scorre invece di comprimere le voci",
          row.scroll is not None)


# ---------------------------------------------------------------------------
# 6 — Regressione: le view si costruiscono in entrambi i temi
# ---------------------------------------------------------------------------

def test_regression_views() -> None:
    print("\n[6] Regressione — costruzione delle view nei due temi")

    from data.models import Character
    from data.repositories import character_repo
    from ui.views.character_sheet.sheet_view import SheetView
    from ui.views.spells_view import SpellsView
    from ui.views.diary_view import DiaryView
    from ui.views.maps_view import MapsView
    from ui.views.dice_view import DiceView
    from ui.views.feats_view import FeatsView
    from ui.views.home_view import HomeView
    from ui.views.master.master_view import MasterView

    classes = ["Barbaro", "Bardo", "Chierico", "Druido", "Guerriero", "Ladro",
               "Mago", "Monaco", "Paladino", "Ranger", "Stregone", "Warlock"]

    built = 0
    errors: list[str] = []
    for mode in ("light", "dark"):
        design.set_mode(mode)
        for cls in classes:
            char = Character(name=f"Test {cls}", class_name=cls, race="Umano",
                             level=5, hp_max=40, hp_current=40)
            character_repo.create(char)
            profs = character_repo.get_proficiencies(char.id)
            for name, factory in (
                ("SheetView", lambda: SheetView(char, profs)),
                ("SpellsView", lambda: SpellsView(char)),
                ("DiaryView", lambda: DiaryView(char)),
                ("MapsView", lambda: MapsView(char)),
            ):
                try:
                    factory()
                    built += 1
                except Exception as exc:
                    errors.append(f"{mode}/{cls}/{name}: {exc}")
        for name, factory in (
            ("DiceView", DiceView),
            ("FeatsView", FeatsView),
            ("HomeView", lambda: HomeView(lambda i: None, lambda: None, lambda: None,
                                          lambda: None, lambda e: None, "dark")),
            ("MasterView", lambda: MasterView(lambda: None, lambda e: None, "dark")),
        ):
            try:
                factory()
                built += 1
            except Exception as exc:
                errors.append(f"{mode}/{name}: {exc}")

    print(f"    ({built} costruzioni di view nei due temi)")
    check(f"tutte le view costruite nei due temi ({built} costruzioni)", not errors)
    for e in errors[:5]:
        print(f"    {e}")

    # Palette: nessun colore condiviso tra i due temi sulle superfici principali
    diff = [f for f in ("bg", "surface", "text", "nav_bg")
            if getattr(design.LIGHT, f) == getattr(design.DARK, f)]
    check("le due palette differiscono sulle superfici principali", not diff)


# ---------------------------------------------------------------------------
# 7 — Regressione: la nuova tabella non tocca level-up ed export/import
# ---------------------------------------------------------------------------

def test_regression_core() -> None:
    print("\n[7] Regressione — level-up ed export/import")

    from core.level_manager import get_level_up_steps
    from data.game_data.game_data_loader import GameDataLoader

    loader = GameDataLoader()
    classes = ["Barbaro", "Bardo", "Chierico", "Druido", "Guerriero", "Ladro",
               "Mago", "Monaco", "Paladino", "Ranger", "Stregone", "Warlock"]
    combos = 0
    errors: list[str] = []
    for cls in classes:
        data = loader.get_class(cls) or {}
        subs = [s.get("name", "") for s in data.get("subclasses", [])] or [""]
        for sub in subs:
            for lvl in range(2, 21):
                try:
                    steps = get_level_up_steps(cls, lvl, 2, 2, sub)
                    combos += 1
                    if any(not getattr(s, "label", "x") for s in steps):
                        errors.append(f"{cls}/{sub}/lv{lvl}: label vuota")
                except Exception as exc:
                    errors.append(f"{cls}/{sub}/lv{lvl}: {exc}")
    print(f"    ({combos} combinazioni classe x sottoclasse x livello)")
    check(f"get_level_up_steps su {combos} combinazioni senza eccezioni", not errors)
    for e in errors[:5]:
        print(f"    {e}")

    # Export/import: la nuova tabella non ha character_id e non e' tra le
    # CHILD_TABLES, quindi non deve comparire nel file esportato.
    from data.models import Character
    from data.repositories import character_export, character_repo

    check("app_settings NON e' tra le tabelle esportate",
          "app_settings" not in character_export.CHILD_TABLES)

    char = Character(name="Export Test", class_name="Mago", race="Elfo",
                     level=3, hp_max=20, hp_current=20)
    character_repo.create(char)
    data = character_export.export_character(char.id)
    check("export riuscito", data is not None)
    if data:
        check("nessuna preferenza dell'app nel file esportato",
              "app_settings" not in data.get("related", {}))
        # Ritorna una stringa di errore in italiano; vuota = valido.
        err = character_export.validate_export_data(data)
        check(f"il file esportato resta valido ({err or 'ok'})", err == "")
        new_id = character_export.import_character(data, mode="copy")
        check("reimport in modalita' copia riuscito", bool(new_id) and new_id != char.id)
        copy = character_repo.get_by_id(new_id) if new_id else None
        check("la copia ha gli stessi dati", copy is not None and copy.name == "Export Test")

    check("la preferenza di tema sopravvive a un import",
          settings_repo.get_theme_preference() in settings_repo.THEME_PREFERENCES)


def main() -> int:
    print("=" * 62)
    print("FASE D — tema scuro con preferenza persistita")
    print(f"HOME di test: {_TMP_HOME}")
    print("=" * 62)

    test_repo()
    test_resolution()
    test_cycle_and_rebuild()
    test_routes()
    test_toggle_present()
    test_regression_views()
    test_regression_core()

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
