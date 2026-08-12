"""
Verifica — Rubrica NPC, Razza strutturata e auto-riempimento (2026-08-12).

Bug report di Davide (screenshot del dialog "Modifica NPC"): un NPC
generato con razza nota (es. Sabina, Halfling) mostrava "Tipo creatura"/
"Taglia" vuoti quando si attivava "Ha statistiche di combattimento" — il
Master doveva ricordarsi a memoria che un Halfling è Umanoide/Piccola e
digitarlo a mano. Fix: `MasterNpc.race` (nuovo campo strutturato) +
`core.npc_generator.resolve_creature_type_and_size()`/
`resolve_race_from_tags()` (fallback per NPC generati prima di questo
campo, dove la razza viveva solo dentro `tags`).

Due parti:

[1] `core.npc_generator.resolve_creature_type_and_size()`/
    `resolve_race_from_tags()` — logica pura, nessuna dipendenza da
    Flet/DB.

[2] `master_repo.create_npc()`/`create_npc_from_monster()`/`update_npc()`
    — round trip di `race` nel DB, incluso che `update_npc()` non la
    dimentichi (a differenza di `world_id`, `race` è volutamente
    modificabile dopo la creazione).

Nessuna UI Flet toccata da queste funzioni — nessun bisogno di `import
flet`, stesso principio di `test_master_world_scoping.py`. Le due nuove
classi Flet (`DropdownAltro`/`MultiSelectAltro` in `ui/widgets.py`) e
l'auto-riempimento visuale nel form NPC non sono verificabili da uno
script standalone — richiedono un controllo manuale del dialog reale.

Usa SEMPRE un DB temporaneo isolato (tempfile.mkdtemp() + HOME separato):
il DB reale di Davide non viene mai toccato.

Eseguire con:
    PYTHONPATH="." python3 test_npc_race_autofill.py
"""

from __future__ import annotations

import os
import tempfile

_TMP_HOME = tempfile.mkdtemp(prefix="dnd_npc_race_")
os.environ["HOME"] = _TMP_HOME

from data.database import init_db  # noqa: E402
from data.repositories import master_repo  # noqa: E402
from core import npc_generator as ng  # noqa: E402

_PASS = 0
_FAIL: list[str] = []


def check(label: str, cond: bool) -> None:
    global _PASS
    if cond:
        _PASS += 1
    else:
        _FAIL.append(label)
        print(f"  FALLITO: {label}")


def test_resolve_creature_type_and_size() -> None:
    print("\n[1] core.npc_generator.resolve_creature_type_and_size()")

    small_races = {"Halfling", "Gnomo"}
    for race in ng.RACE_OPTIONS:
        ctype, size = ng.resolve_creature_type_and_size(race)
        check(f"{race}: tipo creatura = Umanoide", ctype == "Umanoide")
        expected_size = "Piccola" if race in small_races else "Media"
        check(f"{race}: taglia = {expected_size}", size == expected_size)

    check("razza vuota -> (\"\", \"\")", ng.resolve_creature_type_and_size("") == ("", ""))
    check("razza sconosciuta -> (\"\", \"\")",
          ng.resolve_creature_type_and_size("Non è una razza PHB") == ("", ""))


def test_resolve_race_from_tags() -> None:
    print("\n[2] core.npc_generator.resolve_race_from_tags()")

    check("match esatto", ng.resolve_race_from_tags("Halfling, Femmina") == "Halfling")
    check("case-insensitive", ng.resolve_race_from_tags("halfling, femmina") == "Halfling")
    check("spazi tollerati", ng.resolve_race_from_tags("  Elfo  , Maschio") == "Elfo")
    check("nessun match -> \"\"", ng.resolve_race_from_tags("Cattivo, Losco") == "")
    check("tags vuoto -> \"\"", ng.resolve_race_from_tags("") == "")
    check("un solo segmento senza virgola, match", ng.resolve_race_from_tags("Nano") == "Nano")


def test_npc_race_db_roundtrip() -> None:
    print("\n[3] master_repo — round trip di MasterNpc.race nel DB")

    npc = master_repo.create_npc(name="Sabina", role="Locandiera", race="Halfling")
    check("create_npc salva la razza", npc is not None and npc.race == "Halfling")
    assert npc is not None

    reloaded = master_repo.get_npc_by_id(npc.id)
    check("get_npc_by_id rilegge la razza", reloaded is not None and reloaded.race == "Halfling")
    assert reloaded is not None

    # A differenza di world_id, race è modificabile dopo la creazione —
    # il caso "in realtà è un cambiaforma".
    reloaded.race = "Dragonide"
    ok = master_repo.update_npc(reloaded)
    check("update_npc ha successo", ok)
    reloaded_again = master_repo.get_npc_by_id(npc.id)
    check("update_npc NON dimentica la colonna race",
          reloaded_again is not None and reloaded_again.race == "Dragonide")

    # create_npc_from_monster propaga race (percorso "Nuovo dal Bestiario"/
    # Generatore con stat block da mostro).
    npc_from_monster = master_repo.create_npc_from_monster(
        {"name": "Goblin", "type": "Umanoide", "ac": 15}, race="Gnomo",
    )
    check("create_npc_from_monster propaga race",
          npc_from_monster is not None and npc_from_monster.race == "Gnomo")

    # NPC senza razza (percorso "Nuovo Manuale" senza sceglierla) — mai
    # un'eccezione, resta semplicemente "".
    npc_no_race = master_repo.create_npc(name="Sconosciuto")
    check("NPC senza razza: campo vuoto, nessuna eccezione",
          npc_no_race is not None and npc_no_race.race == "")


def test_migrazione_idempotente() -> None:
    print("\n[4] Migrazione master_npcs.race — idempotente")
    init_db()
    init_db()
    check("init_db() chiamata due volte non solleva eccezioni", True)


def main() -> int:
    print("=" * 66)
    print("Rubrica NPC — Razza strutturata e auto-riempimento (2026-08-12)")
    print(f"HOME di test: {_TMP_HOME}")
    print("=" * 66)
    init_db()
    test_resolve_creature_type_and_size()
    test_resolve_race_from_tags()
    test_npc_race_db_roundtrip()
    test_migrazione_idempotente()
    print("\n" + "=" * 66)
    print(f"Controlli passati: {_PASS} — falliti: {len(_FAIL)}")
    if _FAIL:
        for f in _FAIL:
            print(f"  - {f}")
        return 1
    print("Tutti i controlli passati.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
