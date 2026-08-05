"""
Batteria di verifica del passo 3 di dnd_app/docs/multiplayer_design.md —
"Istanze di personaggio" (§6, 2026-08-05).

Copre: `core/character_instances.py` (porta com'è, ricomincia dal 1° livello
con reset completo via `undo_level`, ripresa idempotente, «Aggiorna il mio
foglio» con e senza origine ancora esistente), e la Home raggruppata per
mondo in `ui/views/home_view.py` (partizione locali/istanze, sezioni,
azioni contestuali sulla card).

Nessuna rete qui: un solo dispositivo/processo, come da scope del passo 3.
Il comportamento multi-dispositivo reale resta da verificare da Davide dal
passo 4 in poi.

Usa SEMPRE un DB temporaneo isolato (tempfile.mkdtemp() + HOME separato):
il DB reale di Davide non viene mai toccato. Stesso pattern di
test_mondo_senza_rete.py.

Eseguire con:
    PYTHONPATH=".venv/lib/python3.13/site-packages:." python3 test_istanze_personaggio.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from typing import Any

_TMP_HOME = tempfile.mkdtemp(prefix="dnd_istanze_")
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


def _make_guerriero(name: str, level: int = 7) -> Character:
    """
    Guerriero con la Forza spinta da un ASI (17 -> 18 preso al 4° livello):
    serve a verificare che `_reset_to_level_one` inverta davvero il bonus
    via `undo_level`, non solo che azzeri livello/PE. Stessa identica
    sequenza di scritture del flusso di level-up reale in
    `profilo_tab.py::do_level_up` (§3610-3624): applica il delta sul
    punteggio E salva la "ricevuta" in `character_proficiencies` con
    `proficiency_type="asi_record"` — il campo che `undo_level` filtra.
    """
    import json as _json

    char = Character(
        name=name, class_name="Guerriero", race="Umano", level=level,
        hit_dice_type=10, hit_dice_total=level, hit_dice_remaining=level,
        str_score=18, dex_score=14, con_score=14, int_score=10,
        wis_score=12, cha_score=8,
        hp_max=20 + (level - 1) * 6, hp_current=20 + (level - 1) * 6,
        xp=23000,
    )
    character_repo.create(char)
    character_repo._save_single_proficiency(
        char.id, "asi_record", "+1 str",
        bonus_data=_json.dumps({"ability": {"str": 1}}),
        level_obtained=4,
    )
    return character_repo.get_by_id(char.id)


def test_reset_fresh_undoes_asi_and_resets_state() -> None:
    """
    Verifica diretta di `_reset_to_level_one` isolata da `create_or_resume_
    instance`, per capire esattamente cosa fallisce se qualcosa si rompe.
    Usa `add_proficiency_with_bonus` se esiste nel repository (stesso
    meccanismo di `undo_level`); altrimenti verifica solo gli effetti che
    non dipendono da un bonus registrato (livello/PE/PF/inventario/diario),
    dichiarando esplicitamente il gap invece di fingere copertura.
    """
    print("\n[1] core/character_instances — _reset_to_level_one via create_or_resume_instance(fresh)")

    origin = _make_guerriero("Fresh Base")
    character_repo.create_diary_entry(origin.id, "Sessione 1", "Abbiamo esplorato la cripta.")
    check("diario scritto sull'origine", len(character_repo.get_diary_entries(origin.id)) == 1)

    w = world_repo.create_world("Mondo Fresh", "dev-fresh", "Tester")
    result = ci.create_or_resume_instance(w.id, origin.id, "dev-fresh", mode="fresh")
    check("create_or_resume_instance(fresh) riuscito", result.success)
    check("non è una ripresa (prima creazione)", not result.resumed)
    assert result.success

    inst = character_repo.get_by_id(result.character_id)
    check("istanza collegata al mondo giusto", inst.world_id == w.id)
    check("istanza collegata all'origine giusta", inst.origin_character_id == origin.id)
    check("istanza collegata al dispositivo giusto", inst.owner_device_id == "dev-fresh")
    check("istanza NON è una replica (nessuna rete al passo 3)", inst.is_replica is False)
    check("istanza ha un id diverso dall'origine", inst.id != origin.id)

    check("l'ASI preso al 4° livello viene invertito (Forza 18 -> 17)",
          inst.str_score == 17)
    check("livello riportato a 1", inst.level == 1)
    check("PE riportati a 0", inst.xp == 0)
    check("PF ricalcolati con la formula esatta di 1° livello (10 + mod_con)",
          inst.hp_max == 10 + 2)  # dado vita 10 (Guerriero) + mod CON (14 -> +2)
    check("PF correnti = PF massimi", inst.hp_current == inst.hp_max)
    check("dado vita totale riportato a 1", inst.hit_dice_total == 1)
    check("indebolimento azzerato", inst.exhaustion_level == 0)
    check("tiri salvezza contro la morte azzerati",
          inst.death_saves_success == 0 and inst.death_saves_failure == 0)

    check("diario dell'istanza vuoto (non copia gli eventi narrativi pregressi)",
          character_repo.get_diary_entries(inst.id) == [])
    check("diario dell'ORIGINE intatto (il reset non tocca il locale)",
          len(character_repo.get_diary_entries(origin.id)) == 1)

    check("l'origine resta al suo livello originale",
          character_repo.get_by_id(origin.id).level == 7)

    weapons = character_repo.get_weapons(inst.id, equipped_only=False)
    items = character_repo.get_inventory(inst.id)
    check("equipaggiamento iniziale assegnato automaticamente (armi e/o oggetti presenti)",
          len(weapons) + len(items) > 0)

    cur = character_repo.get_currencies(inst.id)
    check("monete azzerate (nessun oro portato dal 7° livello)",
          cur is not None and cur.gold == 0 and cur.copper == 0)


def test_as_is_copies_everything() -> None:
    print("\n[2] «Porta com'è» — copia integrale, nessun reset")

    origin = _make_guerriero("AsIs Base", level=5)
    character_repo.create_diary_entry(origin.id, "Diario", "Contenuto.")

    w = world_repo.create_world("Mondo AsIs", "dev-asis", "Tester")
    result = ci.create_or_resume_instance(w.id, origin.id, "dev-asis", mode="as_is")
    check("create_or_resume_instance(as_is) riuscito", result.success)
    inst = character_repo.get_by_id(result.character_id)

    check("livello identico all'origine", inst.level == origin.level)
    check("PE identici all'origine", inst.xp == origin.xp)
    check("PF massimi identici all'origine", inst.hp_max == origin.hp_max)
    check("diario copiato (porta com'è, non azzera nulla)",
          len(character_repo.get_diary_entries(inst.id)) == 1)


def test_resume_is_idempotent() -> None:
    print("\n[3] «Riprendi» — idempotenza, nessuna istanza duplicata")

    origin = _make_guerriero("Resume Base")
    w = world_repo.create_world("Mondo Resume", "dev-resume", "Tester")

    r1 = ci.create_or_resume_instance(w.id, origin.id, "dev-resume", mode="as_is")
    check("prima entrata riuscita", r1.success)
    check("prima entrata NON è una ripresa", not r1.resumed)

    r2 = ci.create_or_resume_instance(w.id, origin.id, "dev-resume", mode="fresh")
    check("seconda chiamata riuscita", r2.success)
    check("seconda chiamata è una ripresa (mode ignorato)", r2.resumed)
    check("stesso id di istanza, nessun duplicato", r2.character_id == r1.character_id)

    # Un secondo dispositivo che entra con lo STESSO personaggio locale
    # ottiene una propria istanza indipendente (owner_device_id diverso).
    r3 = ci.create_or_resume_instance(w.id, origin.id, "dev-resume-2", mode="as_is")
    check("un device diverso ottiene una nuova istanza", r3.success and not r3.resumed)
    check("le due istanze hanno id diversi", r3.character_id != r1.character_id)


def test_guard_no_instance_of_instance() -> None:
    print("\n[4] Guardia — non si crea mai l'istanza di un'istanza")

    origin = _make_guerriero("Guardia Base")
    w = world_repo.create_world("Mondo Guardia", "dev-guardia", "Tester")
    r1 = ci.create_or_resume_instance(w.id, origin.id, "dev-guardia", mode="as_is")
    check("prima istanza creata", r1.success)

    w2 = world_repo.create_world("Secondo Mondo", "dev-guardia", "Tester")
    r2 = ci.create_or_resume_instance(w2.id, r1.character_id, "dev-guardia", mode="as_is")
    check("creare l'istanza di un'istanza viene rifiutato", not r2.success)
    check("errore esplicito, non un fallimento silenzioso", bool(r2.error))

    r3 = ci.create_or_resume_instance(w.id, "id-inesistente", "dev-guardia", mode="as_is")
    check("personaggio locale inesistente viene rifiutato", not r3.success)


def test_refresh_preview_and_apply() -> None:
    print("\n[5] «Aggiorna il mio foglio» — anteprima e applicazione, origine esistente")

    origin = _make_guerriero("Refresh Base", level=3)
    w = world_repo.create_world("Mondo Refresh", "dev-refresh", "Tester")
    r = ci.create_or_resume_instance(w.id, origin.id, "dev-refresh", mode="as_is")
    check("istanza creata per il test di refresh", r.success)
    inst_id = r.character_id

    # Simula progressi fatti in gioco sull'istanza (PE guadagnati).
    character_repo.add_xp(inst_id, 5000)
    inst_after_play = character_repo.get_by_id(inst_id)

    preview = ci.preview_refresh(inst_id)
    check("preview_refresh non è None con origine esistente", preview is not None)
    assert preview is not None
    check("preview segnala origine esistente", preview.origin_exists)
    check("preview mostra i PE PRIMA (origine, non ancora aggiornata)",
          preview.xp_before == origin.xp)
    check("preview mostra i PE DOPO (istanza, con i progressi)",
          preview.xp_after == inst_after_play.xp)
    check("preview mostra il nome dell'origine", preview.origin_name == origin.name)

    result = ci.apply_refresh(inst_id)
    check("apply_refresh riuscito", result.success)
    check("apply_refresh scrive sullo STESSO id dell'origine (mai un nuovo personaggio)",
          result.character_id == origin.id)

    refreshed_origin = character_repo.get_by_id(origin.id)
    check("il personaggio locale ha ora i PE aggiornati dall'istanza",
          refreshed_origin.xp == inst_after_play.xp)
    check("il personaggio locale aggiornato resta locale (colonne mondo azzerate)",
          refreshed_origin.world_id == "" and not refreshed_origin.is_replica)

    # Anteprima su un personaggio senza origin_character_id (locale puro).
    check("preview_refresh su un personaggio locale ritorna None",
          ci.preview_refresh(origin.id) is None)


def test_refresh_when_origin_deleted() -> None:
    print("\n[6] «Aggiorna il mio foglio» — origine eliminata, crea un nuovo locale")

    origin = _make_guerriero("Refresh Orfano")
    w = world_repo.create_world("Mondo Refresh Orfano", "dev-orfano", "Tester")
    r = ci.create_or_resume_instance(w.id, origin.id, "dev-orfano", mode="as_is")
    inst_id = r.character_id
    origin_id = origin.id

    character_repo.delete(origin_id)
    check("origine eliminata", character_repo.get_by_id(origin_id) is None)

    preview = ci.preview_refresh(inst_id)
    check("preview segnala origine NON esistente", preview is not None and not preview.origin_exists)

    result = ci.apply_refresh(inst_id)
    check("apply_refresh riesce comunque (crea un nuovo locale)", result.success)
    check("il nuovo id è diverso da quello (ormai eliminato) dell'origine",
          result.character_id != origin_id)
    new_local = character_repo.get_by_id(result.character_id)
    check("il nuovo personaggio è locale", new_local is not None and new_local.world_id == "")


def test_home_grouping() -> None:
    print("\n[7] Home raggruppata per mondo — partizione e sezioni")

    from ui.views.home_view import HomeView

    home = HomeView(on_select=lambda i: None, on_create_wizard=lambda: None,
                    on_create_manual=lambda: None)

    local1 = _make_guerriero("Home Locale", level=2)
    w = world_repo.create_world("Mondo Home", "dev-home", "Tester")
    r = ci.create_or_resume_instance(w.id, local1.id, "dev-home", mode="as_is")
    inst = character_repo.get_by_id(r.character_id)

    home.device_id = "dev-home"
    all_chars = character_repo.get_all()
    locals_, by_world = home._partition_characters(all_chars)

    check("il personaggio locale finisce tra i locali", any(c.id == local1.id for c in locals_))
    check("l'istanza NON finisce tra i locali", not any(c.id == inst.id for c in locals_))
    check("l'istanza finisce nel gruppo del suo mondo", w.id in by_world)
    check("il gruppo del mondo contiene esattamente l'istanza attesa",
          [c.id for c in by_world[w.id]] == [inst.id])

    # Un'istanza posseduta da un ALTRO dispositivo (stesso DB, es. web mode
    # multi-scheda) non deve comparire nella Home di questo dispositivo.
    home_altro = HomeView(on_select=lambda i: None, on_create_wizard=lambda: None,
                          on_create_manual=lambda: None)
    home_altro.device_id = "dev-un-altro-dispositivo-mai-visto"
    locals_2, by_world_2 = home_altro._partition_characters(all_chars)
    check("un dispositivo estraneo non vede l'istanza altrui in nessun gruppo",
          not any(inst.id in [c.id for c in lst] for lst in by_world_2.values()))
    check("un dispositivo estraneo non vede l'istanza altrui nemmeno tra i locali "
          "(ha world_id valorizzato, non è locale)",
          not any(c.id == inst.id for c in locals_2))

    # refresh() end-to-end: non deve sollevare eccezioni con device_id
    # risolto, e deve produrre almeno una sezione per il mondo.
    home.refresh(force=True)
    check("refresh() con gruppi per mondo produce dei controlli",
          len(home._char_list_column.controls) > 0)

    # Senza device_id risolto (identità non ancora pronta): nessuna
    # eccezione, ricade sulla lista piatta.
    home_no_id = HomeView(on_select=lambda i: None, on_create_wizard=lambda: None,
                          on_create_manual=lambda: None)
    home_no_id.refresh(force=True)
    check("refresh() senza device_id non solleva eccezioni",
          len(home_no_id._char_list_column.controls) > 0)


def test_no_regression_existing_suites() -> None:
    """
    I moduli toccati in questo passo (`data/models.py`,
    `data/repositories/character_repo.py`,
    `data/repositories/character_export.py`) sono condivisi con tutto il
    resto dell'app: non basta testare le funzioni nuove, va verificato che
    le batterie preesistenti restino verdi nello stesso processo.
    """
    print("\n[8] Nessuna regressione — riesecuzione delle batterie esistenti")
    import subprocess
    import pathlib

    here = pathlib.Path(__file__).resolve().parent
    for script in ("test_mondo_senza_rete.py",):
        proc = subprocess.run(
            [sys.executable, str(here / script)],
            cwd=str(here), capture_output=True, text=True, timeout=180,
        )
        check(f"{script} termina con successo (exit 0)", proc.returncode == 0)
        if proc.returncode != 0:
            print(proc.stdout[-3000:])
            print(proc.stderr[-3000:])


def main() -> int:
    print("=" * 62)
    print("PASSO 3 — Istanze di personaggio")
    print(f"HOME di test: {_TMP_HOME}")
    print("=" * 62)

    init_db()
    test_reset_fresh_undoes_asi_and_resets_state()
    test_as_is_copies_everything()
    test_resume_is_idempotent()
    test_guard_no_instance_of_instance()
    test_refresh_preview_and_apply()
    test_refresh_when_origin_deleted()
    test_home_grouping()
    test_no_regression_existing_suites()

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
