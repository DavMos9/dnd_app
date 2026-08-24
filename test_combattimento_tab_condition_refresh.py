"""
Verifica del bug del 2026-08-24, trovato dal vivo da Davide durante il primo
vero test multi-dispositivo LAN: quando il master infligge una condizione a
un giocatore, tutte le altre sincronizzazioni (PF, ecc.) arrivano subito sullo
schermo del giocatore, ma la condizione appena applicata compare solo dopo
aver cambiato tab e essere tornati indietro.

Causa: `ui/views/character_sheet/combattimento_tab.py::CombattimentoTab.
__init__()` carica le condizioni in due attributi cache, `self._conditions`
e `self._cond_effects` — ma `_refresh()` (chiamato dal poll periodico di
sincronizzazione, vedi `sheet_view.py::_soft_refresh()`) ricarica PF,
slot incantesimo, competenze, armi, ecc., MA NON quei due attributi. PF
funziona perché è letto live da `self.character.hp_current`/`hp_max` a ogni
build, e `self.character` viene correttamente riassegnato dentro
`_refresh()` — le condizioni, uniche, restano nella cache stantia
dell'`__init__` originale. Cambiare tab "ripara" il sintomo perché
`sheet_view.py::_get_tab_content()` ricrea un `CombattimentoTab` da zero,
rieseguendo `__init__`.

Fix: `_refresh()` ora ricarica anche `self._conditions`/`self._cond_effects`,
stessa fonte usata da `__init__`.

Eseguire con:
    PYTHONPATH=".venv/lib/python3.13/site-packages:." python3 test_combattimento_tab_condition_refresh.py
"""

from __future__ import annotations

import os
import sys
import tempfile

_TMP_HOME = tempfile.mkdtemp(prefix="dnd_cond_refresh_")
os.environ["HOME"] = _TMP_HOME

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


def _make_character() -> Character:
    c = Character(
        name="Sentinella", class_name="Guerriero", race="Umano", level=5,
        hit_dice_type=10, hit_dice_total=5, hit_dice_remaining=5,
        str_score=16, dex_score=12, con_score=14, int_score=10,
        wis_score=10, cha_score=8, hp_max=44, hp_current=44,
    )
    character_repo.create(c)
    return c


def test_refresh_ricarica_le_condizioni() -> None:
    print("\n[1] _refresh() deve ricaricare self._conditions/self._cond_effects "
          "(bug: restavano quelle dell'apertura tab, come su-schermo-vecchio)")
    from ui.views.character_sheet.combattimento_tab import CombattimentoTab

    c = _make_character()
    tab = CombattimentoTab(c)
    check("nessuna condizione all'apertura tab", tab._conditions == [])

    # Simula il master che infligge una condizione — stesso identico
    # percorso dati usato dal comando di rete lato client dopo un resync
    # (core/world_sync.py: condition.* -> _resync_character_from_host).
    character_repo.add_condition(c.id, "avvelenato", source="Morso di serpente")

    check("la cache NON è ancora aggiornata subito dopo l'INSERT diretto "
          "(prova che il test sta davvero esercitando la cache, non il DB)",
          tab._conditions == [])

    tab._refresh()

    check("dopo _refresh() la condizione appare nella cache (bug: restava vuota)",
          len(tab._conditions) == 1 and tab._conditions[0].condition_key == "avvelenato")
    check("anche _cond_effects è stato ricaricato",
          isinstance(tab._cond_effects, dict))


def test_refresh_toglie_una_condizione_rimossa() -> None:
    print("\n[2] Simmetria: _refresh() deve anche far sparire una condizione "
          "rimossa dal master, non solo mostrarne una nuova")
    from ui.views.character_sheet.combattimento_tab import CombattimentoTab

    c = _make_character()
    cond_id = character_repo.add_condition(c.id, "spaventato", source="Terrore Selvaggio")
    assert cond_id is not None

    tab = CombattimentoTab(c)
    check("la condizione è presente all'apertura tab (creata prima del costruttore)",
          len(tab._conditions) == 1)

    character_repo.remove_condition(cond_id)
    tab._refresh()

    check("dopo _refresh() la condizione rimossa non è più nella cache",
          tab._conditions == [])


def main() -> int:
    init_db()
    print("=" * 72)
    print("Refresh condizioni in CombattimentoTab (bug 2026-08-24)")
    print(f"HOME di test: {_TMP_HOME}")
    print("=" * 72)

    test_refresh_ricarica_le_condizioni()
    test_refresh_toglie_una_condizione_rimossa()

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
