"""
Verifica dell'export scheda personaggio in PDF (`core/pdf_sheet_exporter.py`)
— 2026-08-20, feature pianificata da settimane (ricognizione completa in
`docs/pdf_sheet_reference/`), implementazione di questa sessione.

Stessa convenzione di `test_multiclasse.py`: HOME temporaneo prima di
importare `data.database`, `check()` accumula pass/fail, `main()` esegue i
test in sequenza e ritorna 1 se qualcosa fallisce. Non verifica il
posizionamento esatto del testo nel PDF (richiede lettura visiva, già fatta
manualmente durante la calibrazione) — solo che l'export non sollevi mai
un'eccezione e produca la struttura attesa (numero di pagine corretto nei
casi incantatore/non-incantatore, PDF valido anche con dati limite).

Cinque parti:

[1] Incantatore completo (Mago) → 3 pagine (include la pagina incantesimi).
[2] Marziale puro (Guerriero, nessuna spellcasting_ability) → 2 pagine.
[3] Più di 3 armi equipaggiate → decisione presa con Davide (solo le prime
    3 nella tabella Armi, le altre nell'elenco compresso di Equipaggiamento)
    — qui si verifica solo che non sollevi eccezioni e produca un PDF
    valido a 2 pagine.
[4] Campo di solo testo molto lungo (backstory 2000+ caratteri) — esercita
    il percorso di auto-shrink del font (decisione presa con Davide: mai
    troncare, mai pagina extra).
[5] `character_id` inesistente → `export_character_pdf` ritorna `False`,
    mai un'eccezione.

Eseguire con:
    .venv/bin/python3 test_pdf_sheet_export.py
"""

from __future__ import annotations

import os
import sys
import tempfile

_TMP_HOME = tempfile.mkdtemp(prefix="dnd_pdf_export_")
os.environ["HOME"] = _TMP_HOME

from data.database import init_db  # noqa: E402
from data.models import Character  # noqa: E402
from data.repositories import character_repo  # noqa: E402
from core.pdf_sheet_exporter import export_character_pdf  # noqa: E402

import pypdf  # noqa: E402

_PASS = 0
_FAIL: list[str] = []


def check(label: str, cond: bool) -> None:
    global _PASS
    if cond:
        _PASS += 1
    else:
        _FAIL.append(label)
        print(f"  FALLITO: {label}")


def _make_character(name: str, class_name: str, level: int,
                     spellcasting_ability: str = "", **overrides) -> Character:
    defaults = dict(
        str_score=12, dex_score=14, con_score=13, int_score=10, wis_score=11, cha_score=8,
        hp_max=10 * level, hp_current=10 * level, hit_dice_type=8,
        hit_dice_total=level, hit_dice_remaining=level,
        ac=12, speed=9.0,
    )
    defaults.update(overrides)
    c = Character(
        name=name, player_name="Tester", class_name=class_name, level=level,
        race="Umano", background="Eremita", alignment="Neutrale",
        spellcasting_ability=spellcasting_ability,
        **defaults,
    )
    character_repo.create(c)
    return c


def _page_count(path: str) -> int:
    return len(pypdf.PdfReader(path).pages)


def test_incantatore_completo() -> None:
    print("\n[1] Incantatore completo (Mago) — 3 pagine")
    c = _make_character("Test Mago", "Mago", 5, spellcasting_ability="int")
    character_repo.auto_init_spell_slots(c.id, "Mago", 5)
    character_repo.upsert_known_spell(c.id, "Raggio di Gelo", 0, True)
    character_repo.upsert_known_spell(c.id, "Dardo Incantato", 1, True)
    character_repo.create_weapon(c.id, "Pugnale", damage_dice="1d4",
                                  damage_type="perforante", is_equipped=True)

    out_path = os.path.join(_TMP_HOME, "mago.pdf")
    ok = export_character_pdf(c.id, out_path)
    check("export ritorna True", ok is True)
    check("file scritto su disco", os.path.isfile(out_path))
    check("3 pagine (con pagina incantesimi)", ok and _page_count(out_path) == 3)


def test_marziale_senza_magia() -> None:
    print("\n[2] Marziale puro (Guerriero) — 2 pagine, nessuna pagina incantesimi")
    c = _make_character("Test Guerriero", "Guerriero", 4)
    check("spellcasting_ability vuota", not (c.spellcasting_ability or "").strip())

    out_path = os.path.join(_TMP_HOME, "guerriero.pdf")
    ok = export_character_pdf(c.id, out_path)
    check("export ritorna True", ok is True)
    check("2 pagine (nessuna pagina incantesimi)", ok and _page_count(out_path) == 2)


def test_piu_di_tre_armi() -> None:
    print("\n[3] Più di 3 armi equipaggiate — non solleva eccezioni, PDF valido")
    c = _make_character("Test Arsenale", "Guerriero", 6)
    for i in range(5):
        character_repo.create_weapon(
            c.id, f"Arma {i + 1}", damage_dice="1d8", damage_type="tagliente",
            is_equipped=True,
        )
    weapons = character_repo.get_weapons(c.id, equipped_only=True)
    check("5 armi equipaggiate in fixture", len(weapons) == 5)

    out_path = os.path.join(_TMP_HOME, "arsenale.pdf")
    try:
        ok = export_character_pdf(c.id, out_path)
        raised = False
    except Exception:
        ok = False
        raised = True
    check("nessuna eccezione sollevata", not raised)
    check("export ritorna True", ok is True)
    check("2 pagine, PDF valido", ok and _page_count(out_path) == 2)


def test_testo_lunghissimo_auto_shrink() -> None:
    print("\n[4] Backstory di 2000+ caratteri — percorso di auto-shrink, non solleva eccezioni")
    long_backstory = "Una storia lunghissima piena di dettagli epici e leggendari. " * 40
    check("backstory di test supera i 2000 caratteri", len(long_backstory) > 2000)
    c = _make_character("Test Verboso", "Bardo", 3, spellcasting_ability="cha",
                         backstory=long_backstory)
    character_repo.auto_init_spell_slots(c.id, "Bardo", 3)

    out_path = os.path.join(_TMP_HOME, "verboso.pdf")
    try:
        ok = export_character_pdf(c.id, out_path)
        raised = False
    except Exception:
        ok = False
        raised = True
    check("nessuna eccezione sollevata", not raised)
    check("export ritorna True", ok is True)
    check("PDF valido (3 pagine, incantatore)", ok and _page_count(out_path) == 3)


def test_personaggio_inesistente() -> None:
    print("\n[5] character_id inesistente — ritorna False, mai un'eccezione")
    out_path = os.path.join(_TMP_HOME, "fantasma.pdf")
    try:
        ok = export_character_pdf("id-che-non-esiste-affatto", out_path)
        raised = False
    except Exception:
        ok = True  # forza il check sotto a fallire se per errore solleva
        raised = True
    check("nessuna eccezione sollevata", not raised)
    check("ritorna False", ok is False)
    check("nessun file scritto", not os.path.isfile(out_path))


def main() -> int:
    print("=" * 66)
    print("Export scheda PDF (core/pdf_sheet_exporter.py)")
    print(f"HOME di test: {_TMP_HOME}")
    print("=" * 66)
    init_db()
    test_incantatore_completo()
    test_marziale_senza_magia()
    test_piu_di_tre_armi()
    test_testo_lunghissimo_auto_shrink()
    test_personaggio_inesistente()
    print("\n" + "=" * 66)
    print(f"Controlli passati: {_PASS} — falliti: {len(_FAIL)}")
    if _FAIL:
        for f in _FAIL:
            print(f"  - {f}")
        return 1
    print("Tutti i controlli passati.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
