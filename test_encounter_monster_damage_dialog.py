"""
Verifica del fix del 2026-08-23 a `MasterEncounterView` (tracker di
combattimento della Modalità Master): applicare danno/cura a un mostro o
NPC non è più un clic ±1 per punto ferita
(`self._on_hp_delta(mm, -1)`/`(mm, 1)` incondizionato), ma apre lo stesso
dialog "Applica danno"/"Applica cura" con importo numerico già in uso per
un PG istanza di mondo (`ui/components/remote_action_dialogs.py`,
condiviso con "Interviene a distanza") — trovato durante un playtest reale
dal vivo (creazione mondo, hosting LAN, incontro dal Bestiario): un danno
a due cifre su un mostro richiedeva un clic per punto, inutilizzabile a
metà scontro.

Un mostro/NPC non ha un `characters` proprio da sincronizzare altrove (a
differenza di un PG), quindi qui il payload del dialog scrive DIRETTAMENTE
sulla riga dell'incontro (`master_repo.update_member_hp`), non tramite la
pipeline di comando di rete usata per i PG — nessun mondo necessario per
questo test.

Verifica anche una correzione collaterale minima nello stesso metodo
condiviso `_on_hp_delta`: prima del fix una cura poteva superare
`hp_max` (nessun clamp superiore, solo `max(0, ...)` sul minimo) — ora è
clampata su entrambi i lati, coerente con la barra PF che assume
`hp_current <= hp_max`.

Usa un DB temporaneo isolato (tempfile.mkdtemp() + HOME separato), stesso
pattern di tutte le altre batterie di questo progetto.

Eseguire con:
    PYTHONPATH=".venv/lib/python3.13/site-packages:." python3 test_encounter_monster_damage_dialog.py
"""

from __future__ import annotations

import os
import sys
import tempfile

_TMP_HOME = tempfile.mkdtemp(prefix="dnd_encounter_monster_dmg_")
os.environ["HOME"] = _TMP_HOME

import flet as ft  # noqa: E402

from data.database import init_db  # noqa: E402
from data.repositories import master_repo  # noqa: E402

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


def _confirm_button(dlg) -> ft.ElevatedButton:
    btn = next((c for c in _walk(dlg) if isinstance(c, ft.ElevatedButton)
                and str(getattr(c, "content", "")) == "Conferma"), None)
    assert btn is not None, "il dialog deve esporre un pulsante 'Conferma'"
    return btn


def _amount_field(dlg) -> ft.TextField:
    tf = next((c for c in _walk(dlg) if isinstance(c, ft.TextField)), None)
    assert tf is not None, "il dialog deve esporre un campo importo"
    return tf


def _make_encounter_with_monster(hp_current: int, hp_max: int):
    enc = master_repo.create_encounter(name="Imboscata di prova")
    assert enc is not None
    member = master_repo.add_member(
        enc.id, kind="npc", display_name="Goblin di prova",
        ac=15, hp_current=hp_current, hp_max=hp_max, xp=50,
    )
    assert member is not None
    return enc, member


# ---------------------------------------------------------------------------
# [1] Danno: il click apre un dialog con importo, non applica -1 fisso
# ---------------------------------------------------------------------------

def test_monster_damage_dialog_bulk_amount() -> None:
    print("\n[1] _open_monster_damage_dialog — importo a due cifre in un solo invio")
    from ui.views.master.master_encounter_view import MasterEncounterView

    enc, member = _make_encounter_with_monster(hp_current=30, hp_max=30)
    mev = MasterEncounterView(encounter_id=enc.id, on_back_to_list=lambda: None)
    fake_page = _FakePage()
    mev._page = fake_page

    mev._open_monster_damage_dialog(member, "Goblin di prova")
    check("il click ha aperto un dialog", len(fake_page.dialogs) == 1)
    dlg = fake_page.dialogs[-1]

    amount_tf = _amount_field(dlg)
    amount_tf.value = "14"
    _confirm_button(dlg).on_click(None)

    updated = next(m for m in master_repo.get_encounter_members(enc.id) if m.id == member.id)
    check("14 danni applicati in un solo invio (non serviva 1 clic a punto)",
          updated.hp_current == 16)


# ---------------------------------------------------------------------------
# [2] Cura: importo a due cifre, clampata a hp_max
# ---------------------------------------------------------------------------

def test_monster_heal_dialog_clamped_to_max() -> None:
    print("\n[2] _open_monster_heal_dialog — importo a due cifre, clamp su hp_max")
    from ui.views.master.master_encounter_view import MasterEncounterView

    enc, member = _make_encounter_with_monster(hp_current=5, hp_max=30)
    mev = MasterEncounterView(encounter_id=enc.id, on_back_to_list=lambda: None)
    fake_page = _FakePage()
    mev._page = fake_page

    mev._open_monster_heal_dialog(member, "Goblin di prova")
    dlg = fake_page.dialogs[-1]
    amount_tf = _amount_field(dlg)
    amount_tf.value = "12"
    _confirm_button(dlg).on_click(None)

    updated = next(m for m in master_repo.get_encounter_members(enc.id) if m.id == member.id)
    check("12 cura applicati in un solo invio", updated.hp_current == 17)

    # Un secondo invio che sfonderebbe hp_max deve fermarsi al tetto, non
    # sforare (bug collaterale pre-fix: _on_hp_delta clampava solo lo 0,
    # mai hp_max).
    mev._open_monster_heal_dialog(member, "Goblin di prova")
    dlg2 = fake_page.dialogs[-1]
    _amount_field(dlg2).value = "50"
    _confirm_button(dlg2).on_click(None)

    updated2 = next(m for m in master_repo.get_encounter_members(enc.id) if m.id == member.id)
    check("la cura non supera hp_max anche con un importo eccessivo",
          updated2.hp_current == 30)


# ---------------------------------------------------------------------------
# [3] Danno: non scende sotto zero con un importo eccessivo (invariato)
# ---------------------------------------------------------------------------

def test_monster_damage_dialog_floor_at_zero() -> None:
    print("\n[3] _open_monster_damage_dialog — non scende sotto zero PF")
    from ui.views.master.master_encounter_view import MasterEncounterView

    enc, member = _make_encounter_with_monster(hp_current=7, hp_max=13)
    mev = MasterEncounterView(encounter_id=enc.id, on_back_to_list=lambda: None)
    fake_page = _FakePage()
    mev._page = fake_page

    mev._open_monster_damage_dialog(member, "Goblin di prova")
    dlg = fake_page.dialogs[-1]
    _amount_field(dlg).value = "99"
    _confirm_button(dlg).on_click(None)

    updated = next(m for m in master_repo.get_encounter_members(enc.id) if m.id == member.id)
    check("il danno eccessivo ferma i PF a 0, non va in negativo",
          updated.hp_current == 0)


def main() -> int:
    init_db()
    print("=" * 72)
    print("Danno/Cura con importo per mostri/NPC nel tracker di combattimento (2026-08-23)")
    print(f"HOME di test: {_TMP_HOME}")
    print("=" * 72)

    test_monster_damage_dialog_bulk_amount()
    test_monster_heal_dialog_clamped_to_max()
    test_monster_damage_dialog_floor_at_zero()

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
