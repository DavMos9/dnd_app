"""
Verifica del bug del 2026-08-23, trovato dal vivo durante un playtest (non
da un test — nessuna batteria esistente esercitava mai `_on_level_down_click`):
`ui/views/character_sheet/profilo_tab.py::do_level_down()` decrementava
`characters.level` ma non `character_classes.level` della classe primaria,
a differenza di `do_level_up()` che li risincronizza entrambi (commento
gemello nello stesso file: "vanno risincronizzati PRIMA del salvataggio").

Riprodotto live su un personaggio REALE (Paladino a classe singola, non
multiclasse — il bug non è specifico al multiclasse, capita al primo
level-down di QUALSIASI personaggio, dato che ogni personaggio ha comunque
una riga `character_classes` primaria dalla migrazione del 2026-08-12):
Lv.8→9 (su, sincronizzato correttamente) →9→8 (giù, riga classe rimasta
a 9) → il successivo dialog "Level up" proponeva "Avanzamento a Livello 10"
invece di 9, perché `_on_level_up_click` legge il livello bersaglio da
`get_primary_character_class().level` (9, stantio), non da
`character.level` (8, corretto). Danno reale osservato sul personaggio di
produzione di Davide prima del fix e del ripristino manuale dei dati:
"Paladino 9" restava nel sottotitolo della scheda anche dopo essere
tornato a Lv.7/8.

Il fix aggiunge la stessa chiamata `character_repo.set_character_class_
level()` già usata da `do_level_up()`, dentro `do_level_down()`, sulla
classe primaria (level-down non ha ancora un selettore "quale classe
scende" come level-up — assume sempre la primaria, coerente con
`new_level = c.level - 1`).

Usa un `_FakePage` (stesso pattern già in uso in altre batterie di questo
progetto per verificare un dialog reale senza montare Flet) per guidare
`_on_level_down_click`/`_on_level_up_click` end-to-end attraverso
`ProfiloTab`, non solo le funzioni di repository in isolamento — a
differenza del gap che ha lasciato passare questo bug, qui il metodo
VERO viene eseguito.

Test [3]: bug gemello, stessa causa (asimmetria su/giù), trovato subito
dopo controllando l'export PDF del personaggio realmente corrotto:
`do_level_up()` fa sempre `hit_dice_total += 1` ("Dadi vita: +1 per ogni
livello acquisito, PHB p.12"), mai tolto da `do_level_down()` — un dado
vita fantasma permanente ad ogni level-down. Il fix decrementa
`hit_dice_total` di 1 e `hit_dice_remaining` mantenendo invariato il
numero di dadi già spesi (simmetrico all'incremento di do_level_up, non
un semplice `min()` col nuovo totale — quello regalerebbe comunque un
dado in più non guadagnato).

Eseguire con:
    PYTHONPATH=".venv/lib/python3.13/site-packages:." python3 test_level_down_class_sync.py
"""

from __future__ import annotations

import os
import sys
import tempfile

_TMP_HOME = tempfile.mkdtemp(prefix="dnd_level_down_sync_")
os.environ["HOME"] = _TMP_HOME

import flet as ft  # noqa: E402

from data.database import init_db  # noqa: E402
from data.models import Character  # noqa: E402
from data.repositories import character_repo  # noqa: E402

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


def _make_paladino(level: int) -> Character:
    c = Character(
        name="Test Livello", class_name="Paladino", subclass="Giuramento degli Antichi",
        level=level, hit_dice_type=10, hit_dice_total=level, hit_dice_remaining=level,
        str_score=18, dex_score=10, con_score=13, int_score=8, wis_score=12, cha_score=16,
        hp_max=10 * level, hp_current=10 * level,
    )
    character_repo.create(c)
    return c


def _profilo_tab(c: Character):
    from ui.views.character_sheet.profilo_tab import ProfiloTab
    tab = ProfiloTab(c, character_repo.get_proficiencies(c.id))
    fake_page = _FakePage()
    tab._page = fake_page
    return tab, fake_page


# ---------------------------------------------------------------------------
# [1] Un solo level-down: la riga character_classes deve seguire characters.level
# ---------------------------------------------------------------------------

def test_level_down_sincronizza_character_classes() -> None:
    print("\n[1] do_level_down() ora decrementa anche character_classes.level")

    c = _make_paladino(8)
    primary_before = character_repo.get_primary_character_class(c.id)
    check("riga classe primaria a Lv.8 prima del test", primary_before.level == 8)

    tab, fake_page = _profilo_tab(c)
    tab._on_level_down_click(None)
    dlg = fake_page.dialogs[-1]
    _find_button(dlg, "Scendi a Lv.7").on_click(None)

    refreshed = character_repo.get_by_id(c.id)
    check("characters.level sceso a 7", refreshed.level == 7)
    primary_after = character_repo.get_primary_character_class(c.id)
    check("character_classes.level sceso a 7 anch'esso (bug: restava a 8)",
          primary_after.level == 7)
    check("nessun disallineamento tra le due tabelle",
          refreshed.level == primary_after.level)


# ---------------------------------------------------------------------------
# [2] Riproduzione esatta del bug dal vivo: su -> giù -> il prossimo "Level
#     up" deve proporre il livello giusto, non uno sballato dalla riga
#     rimasta stantia.
# ---------------------------------------------------------------------------

def test_ciclo_su_giu_poi_level_up_propone_livello_corretto() -> None:
    print("\n[2] Ciclo su→giù→su: il dialog Level Up propone il livello giusto "
          "(riproduzione esatta del bug osservato dal vivo, Lv.8→9→8→ 'Level up' "
          "proponeva Livello 10 invece di 9)")

    c = _make_paladino(8)
    tab, fake_page = _profilo_tab(c)

    # Su: 8 -> 9
    tab._on_level_up_click(None)
    dlg_up1 = fake_page.dialogs[-1]
    check("primo Level Up propone Livello 9", "Avanzamento a Livello 9" in _dialog_title(dlg_up1))
    _find_button(dlg_up1, "Sali a Lv.9").on_click(None)
    c = character_repo.get_by_id(c.id)
    tab.character = c

    # Giù: 9 -> 8
    tab._on_level_down_click(None)
    dlg_down = fake_page.dialogs[-1]
    _find_button(dlg_down, "Scendi a Lv.8").on_click(None)
    c = character_repo.get_by_id(c.id)
    tab.character = c
    check("dopo su+giù characters.level è tornato a 8", c.level == 8)
    primary = character_repo.get_primary_character_class(c.id)
    check("dopo su+giù character_classes.level è tornato a 8 (non rimasto a 9)",
          primary.level == 8)

    # Il prossimo Level Up deve proporre 9, non 10 (il bug esatto osservato
    # dal vivo: la riga classe stantia a 9 faceva calcolare 9+1=10).
    tab._on_level_up_click(None)
    dlg_up2 = fake_page.dialogs[-1]
    title2 = _dialog_title(dlg_up2)
    check("secondo Level Up propone correttamente Livello 9, non 10 (bug fix)",
          "Avanzamento a Livello 9" in title2)
    check("NON propone Livello 10 (sintomo esatto del bug)",
          "Avanzamento a Livello 10" not in title2)


# ---------------------------------------------------------------------------
# [3] Dadi vita: do_level_up() fa sempre hit_dice_total += 1, ma
#     do_level_down() non lo toglieva mai — stesso bug, stessa causa
#     (asimmetria su/giù), trovato subito dopo il fix precedente
#     controllando l'export PDF del personaggio realmente corrotto
#     ("Totale 7/9 d10" invece di 8/8).
# ---------------------------------------------------------------------------

def test_level_down_simmetrico_su_dadi_vita() -> None:
    print("\n[3] do_level_down() ora toglie anche il dado vita guadagnato al level-up "
          "(bug gemello trovato nell'export PDF: 'Totale 7/9 d10' su un Lv.8)")

    c = _make_paladino(8)
    c.hit_dice_remaining = 6  # 2 già spesi, stato plausibile a metà avventura
    character_repo.update(c)

    tab, fake_page = _profilo_tab(c)

    # Su: 8 -> 9. do_level_up() esistente: total 8->9, remaining 6->7
    # (min(remaining+1, total) — il numero di dadi SPESI, 2, resta invariato).
    tab._on_level_up_click(None)
    dlg_up = fake_page.dialogs[-1]
    _find_button(dlg_up, "Sali a Lv.9").on_click(None)
    after_up = character_repo.get_by_id(c.id)
    check("level-up: dadi vita totali 8 -> 9", after_up.hit_dice_total == 9)
    check("level-up: rimanenti 6 -> 7 (2 spesi, invariato)", after_up.hit_dice_remaining == 7)
    tab.character = after_up

    # Giù: 9 -> 8. Simmetrico: total torna a 8, remaining torna a 6 (sempre
    # 2 spesi) — PRIMA del fix restava a 7 (un dado vita fantasma in più).
    tab._on_level_down_click(None)
    dlg_down = fake_page.dialogs[-1]
    _find_button(dlg_down, "Scendi a Lv.8").on_click(None)
    after_down = character_repo.get_by_id(c.id)
    check("level-down: dadi vita totali tornano a 8 (bug: restavano 9)",
          after_down.hit_dice_total == 8)
    check("level-down: rimanenti tornano a 6, stesso numero di spesi (bug: restava 7)",
          after_down.hit_dice_remaining == 6)


def _dialog_title(dlg: ft.AlertDialog) -> str:
    """L'intestazione "Avanzamento a Livello N" del dialog di Level Up non
    è il `title=` dell'AlertDialog (quello resta `None` per questo dialog
    specifico) ma il primo `ft.Text` dentro `content` — cerca in tutto il
    dialog per non dipendere da quale dei due sia usato."""
    texts = [c.value for c in _walk(dlg) if isinstance(c, ft.Text) and c.value]
    return " ".join(texts)


def main() -> int:
    init_db()
    print("=" * 72)
    print("Sync character_classes.level su level-down (bug 2026-08-23)")
    print(f"HOME di test: {_TMP_HOME}")
    print("=" * 72)

    test_level_down_sincronizza_character_classes()
    test_ciclo_su_giu_poi_level_up_propone_livello_corretto()
    test_level_down_simmetrico_su_dadi_vita()

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
