"""
Verifica del fix 2026-08-20 (seconda revisione della sessione) — bug report
Davide: "quando un giocatore lascia il mondo si ritrova la copia del
personaggio in locale, il personaggio però già esiste in locale quindi me ne
trovo 2".

Causa: `ui/views/world/world_view.py::WorldsView._do_leave()` chiamava
`character_repo.detach_world_instances()` in blocco, che slega SEMPRE
l'istanza dal mondo trasformandola in un personaggio locale — senza mai
controllare che l'originale locale da cui l'istanza è nata
(`origin_character_id`) esistesse ancora. Con un'istanza "porta com'è"
(`core/character_instances.py::_copy_character`, una vera COPIA, l'originale
resta intatto) il risultato era sempre un secondo personaggio locale
accanto al primo.

Fix (su richiesta esplicita di Davide, non una scelta a senso unico):
`WorldsView` ora chiede al giocatore, istanza per istanza, cosa fare della
copia usata nel mondo — l'originale locale non viene MAI toccato in nessun
caso:
- "Fondi con il locale": `core/character_instances.py::apply_refresh()`
  (stessa funzione già dietro "Aggiorna il mio foglio") ricopia la
  progressione fatta nel mondo sull'originale, poi la copia del mondo viene
  cancellata (`character_repo.delete()`) — un solo personaggio locale,
  aggiornato, nessun duplicato.
- "Elimina copia del mondo": la copia viene cancellata SENZA toccare
  l'originale, che resta esattamente com'era prima di entrare nel mondo.
- Se l'originale non esiste più (cancellato nel frattempo): fallback
  storico, `character_repo.detach_world_instance()` (nuova variante
  SINGOLARE di `detach_world_instances()`, per una sola istanza — usata
  quando non c'è nulla con cui fondersi né confrontarsi), l'istanza diventa
  lei stessa il personaggio locale.

Questo file verifica la logica di repository/core dietro le tre scelte
(la UI del dialogo in `world_view.py` non è testabile qui, richiede una
`ft.Page` reale — stesso limite di sempre in questo sandbox).

Usa SEMPRE un DB temporaneo isolato (tempfile.mkdtemp() + HOME separato):
il DB reale di Davide non viene mai toccato. Stesso pattern di
test_note_e_inventario_sync.py.

Eseguire con:
    PYTHONPATH=".venv/lib/python3.13/site-packages:." python3 test_uscita_mondo_fusione.py
"""

from __future__ import annotations

import os
import tempfile

_TMP_HOME = tempfile.mkdtemp(prefix="dnd_uscita_mondo_")
os.environ["HOME"] = _TMP_HOME

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


def _make_local_character(name="Elyndra") -> Character:
    local = Character(
        name=name, class_name="Ladro", race="Mezzelfo", level=3,
        hit_dice_type=8, hit_dice_total=3, hit_dice_remaining=3,
        str_score=10, dex_score=16, con_score=12, int_score=12,
        wis_score=10, cha_score=14, hp_max=20, hp_current=20,
    )
    character_repo.create(local)
    return local


def _make_world_with_as_is_instance(local: Character, owner_device="dev-owner",
                                     player_device="dev-player"):
    world = world_repo.create_world("Mondo di Prova", owner_device, "Il Master")
    assert world is not None
    result = ci.create_or_resume_instance(world.id, local.id, player_device, mode="as_is")
    assert result.success, result.error
    instance = character_repo.get_by_id(result.character_id)
    assert instance is not None
    return world, instance


# ---------------------------------------------------------------------------
# [1] get_owned_world_instances — usata da _do_leave per capire cosa chiedere
# ---------------------------------------------------------------------------

def test_get_owned_world_instances() -> None:
    print("\n[1] get_owned_world_instances — trova esattamente le istanze "
          "non archiviate di questo dispositivo in questo mondo")
    local = _make_local_character()
    world, instance = _make_world_with_as_is_instance(local)

    owned = character_repo.get_owned_world_instances(world.id, "dev-player")
    check("trova l'istanza appena creata", any(c.id == instance.id for c in owned))
    check("esattamente una riga", len(owned) == 1)

    owned_other_device = character_repo.get_owned_world_instances(world.id, "dev-qualcunaltro")
    check("nessuna riga per un dispositivo diverso", owned_other_device == [])

    character_repo.archive_world_instance(world.id, instance.id)
    owned_after_archive = character_repo.get_owned_world_instances(world.id, "dev-player")
    check("un'istanza archiviata non compare più", owned_after_archive == [])


# ---------------------------------------------------------------------------
# [2] Scelta "Fondi con il locale" — nessun duplicato, progressione applicata
# ---------------------------------------------------------------------------

def test_merge_choice_applies_progress_no_duplicate() -> None:
    print("\n[2] BUG FIX: 'Fondi con il locale' — l'originale assorbe la "
          "progressione fatta nel mondo, la copia sparisce, UN SOLO "
          "personaggio locale resta (prima: sempre 2)")
    local = _make_local_character("Grimlock")
    world, instance = _make_world_with_as_is_instance(local)

    # Progressione fatta SOLO nel mondo, mai sull'originale.
    instance.level = 5
    instance.xp = 6500
    check("l'aggiornamento del livello sull'istanza riesce", character_repo.update(instance))
    character_repo.create_weapon(instance.id, "Spada fiammeggiante", is_equipped=True)

    # Simula esattamente la sequenza di _finalize_leave() per choice="merge".
    result = ci.apply_refresh(instance.id)
    check("apply_refresh riesce", result.success)
    character_repo.delete(instance.id)

    all_local = [c for c in character_repo.get_all() if c.world_id == ""]
    matching = [c for c in all_local if c.name == "Grimlock"]
    check("BUG FIX: un solo personaggio locale 'Grimlock', non 2", len(matching) == 1)
    check("l'istanza del mondo è stata cancellata",
          character_repo.get_by_id(instance.id) is None)
    if matching:
        merged = matching[0]
        check("la progressione del mondo (livello 5) è stata applicata all'originale",
              merged.level == 5)
        weapons = character_repo.get_weapons(merged.id, equipped_only=False)
        check("l'arma raccolta nel mondo è arrivata sull'originale",
              any(w.name == "Spada fiammeggiante" for w in weapons))


# ---------------------------------------------------------------------------
# [3] Scelta "Elimina copia del mondo" — l'originale resta intatto
# ---------------------------------------------------------------------------

def test_discard_choice_keeps_original_untouched() -> None:
    print("\n[3] 'Elimina copia del mondo' — la copia sparisce, l'originale "
          "resta ESATTAMENTE com'era prima di entrare nel mondo")
    local = _make_local_character("Sarina")
    original_level = local.level
    world, instance = _make_world_with_as_is_instance(local)

    instance.level = 8
    check("l'aggiornamento del livello sull'istanza riesce", character_repo.update(instance))

    # Simula _finalize_leave() per choice="discard": solo delete, mai apply_refresh.
    character_repo.delete(instance.id)

    all_local = [c for c in character_repo.get_all() if c.world_id == ""]
    matching = [c for c in all_local if c.name == "Sarina"]
    check("un solo personaggio locale 'Sarina', non 2", len(matching) == 1)
    check("l'istanza del mondo è stata cancellata",
          character_repo.get_by_id(instance.id) is None)
    if matching:
        check("il livello dell'originale NON è cambiato (progressione del mondo scartata)",
              matching[0].level == original_level)


# ---------------------------------------------------------------------------
# [4] Fallback: origine locale cancellata → detach_world_instance (singolare)
# ---------------------------------------------------------------------------

def test_detach_single_instance_when_origin_gone() -> None:
    print("\n[4] Fallback: se l'originale locale non esiste più, "
          "detach_world_instance() converte l'istanza stessa in personaggio "
          "locale (comportamento storico, invariato in questo caso)")
    local = _make_local_character("Thoric")
    world, instance = _make_world_with_as_is_instance(local)

    # L'originale viene cancellato MENTRE il giocatore gioca l'istanza nel mondo.
    character_repo.delete(local.id)
    check("l'origine locale non esiste più", character_repo.get_by_id(local.id) is None)

    ok = character_repo.detach_world_instance(instance.id)
    check("detach_world_instance riesce", ok)
    detached = character_repo.get_by_id(instance.id)
    check("l'istanza esiste ancora", detached is not None)
    if detached is not None:
        check("è diventata un personaggio locale (world_id vuoto)", detached.world_id == "")
        check("origin_character_id azzerato", detached.origin_character_id == "")
        check("owner_device_id azzerato", detached.owner_device_id == "")


if __name__ == "__main__":
    init_db()
    test_get_owned_world_instances()
    test_merge_choice_applies_progress_no_duplicate()
    test_discard_choice_keeps_original_untouched()
    test_detach_single_instance_when_origin_gone()

    print("\n" + "=" * 70)
    print(f"Controlli passati: {_PASS} — falliti: {len(_FAIL)}")
    if _FAIL:
        print("\nControlli falliti:")
        for label in _FAIL:
            print(f"  - {label}")
        raise SystemExit(1)
    print("Tutti i controlli passati.")
