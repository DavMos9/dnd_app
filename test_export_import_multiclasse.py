"""
Verifica del fix 2026-08-24 — bug trovato dal vivo testando il flusso
"Importa personaggio" (.dndchar) su un personaggio multiclasse reale
(Bambolo, Monaco 6 / Ladro 4): la card del personaggio appena importato
mostrava solo "Monaco", la classe secondaria Ladro era sparita.

Causa: `data/repositories/character_export.py::CHILD_TABLES` elenca le 13
tabelle figlio con FK `character_id → characters(id) ON DELETE CASCADE` da
copiare in export/import — ma `character_classes` (introdotta il
2026-08-12 con lo schema multiclasse, vedi `test_multiclasse.py`) non era
mai stata aggiunta a questa lista. L'export di un personaggio multiclasse
include quindi la riga `characters` (che porta ancora `class_name`/`level`
della sola classe primaria, per compatibilità) ma NESSUNA riga
`character_classes`: dopo l'import il personaggio appare mono-classe,
perdendo silenziosamente ogni classe secondaria/terziaria.

Impatto più ampio del previsto: `core/character_instances.py::
_copy_character()` usa la STESSA `export_character()`/`import_character()`
— quindi non solo l'export/import di un file .dndchar (backup, cambio
dispositivo), ma anche "Crea copia" nel dialog di conflitto import E
l'ingresso di un personaggio multiclasse in un mondo (che duplica il
personaggio locale in un'istanza) perdevano la classe secondaria.

Fix: aggiunta "character_classes" a CHILD_TABLES. Nessun'altra modifica
necessaria — `_write_character_and_children()` gestisce già generica-
mente qualunque tabella della lista (nuovo id, character_id riscritto al
target), stesso principio dichiarato nel docstring di modulo.

Eseguire con:
    PYTHONPATH=".venv/lib/python3.13/site-packages:." python3 test_export_import_multiclasse.py
"""

from __future__ import annotations

import os
import sys
import tempfile

_TMP_HOME = tempfile.mkdtemp(prefix="dnd_export_import_multiclasse_")
os.environ["HOME"] = _TMP_HOME

from data.database import init_db  # noqa: E402
from data.models import Character  # noqa: E402
from data.repositories import character_export, character_repo  # noqa: E402

_PASS = 0
_FAIL: list[str] = []


def check(label: str, cond: bool) -> None:
    global _PASS
    if cond:
        _PASS += 1
    else:
        _FAIL.append(label)
        print(f"  FALLITO: {label}")


def _make_multiclass_character() -> Character:
    c = Character(
        name="Bambolo", class_name="Monaco", level=10,
        hit_dice_type=8, hit_dice_total=10, hit_dice_remaining=10,
        hp_max=80, hp_current=80,
        str_score=14, dex_score=20, con_score=13,
        int_score=11, wis_score=15, cha_score=9,
    )
    character_repo.create(c)
    character_repo.add_character_class(c.id, "Ladro", level=4, is_primary=False)
    return c


def test_export_include_character_classes():
    print("\n[1] export_character() include le righe character_classes")

    c = _make_multiclass_character()
    original = character_repo.get_character_classes(c.id)
    check("setup: 2 classi sul personaggio originale", len(original) == 2)

    data = character_export.export_character(c.id, raise_errors=True)
    check("export: sezione 'character_classes' presente in 'related'",
          "character_classes" in (data or {}).get("related", {}))
    rows = (data or {}).get("related", {}).get("character_classes", [])
    check("export: 2 righe character_classes esportate", len(rows) == 2)
    check("export: classe secondaria Ladro presente nel file",
          any(r.get("class_name") == "Ladro" for r in rows))


def test_import_copy_preserva_multiclasse():
    print("\n[2] import_character(mode='copy') preserva tutte le classi")

    c = _make_multiclass_character()
    data = character_export.export_character(c.id, raise_errors=True)

    new_id = character_export.import_character(data, mode="copy", raise_errors=True)
    check("import: nuovo id restituito", bool(new_id) and new_id != c.id)

    copied_classes = character_repo.get_character_classes(new_id) if new_id else []
    check("import: la copia ha 2 classi (non 1)", len(copied_classes) == 2)
    names = {cc.class_name for cc in copied_classes}
    check("import: la copia ha ancora Monaco", "Monaco" in names)
    check("import: la copia ha ancora Ladro (classe secondaria)", "Ladro" in names)

    display = character_repo.get_class_display_string(new_id) if new_id else ""
    check("import: display string multiclasse corretta",
          "Monaco" in display and "Ladro" in display)


def main() -> int:
    init_db()
    test_export_include_character_classes()
    test_import_copy_preserva_multiclasse()

    print(f"\n{_PASS} check superati, {len(_FAIL)} falliti.")
    if _FAIL:
        print("Falliti:")
        for f in _FAIL:
            print(f"  - {f}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
