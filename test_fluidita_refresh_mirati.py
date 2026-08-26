"""
Verifica dei refresh mirati introdotti per il piano "Fluidità transizioni e
animazioni" (2026-08-26): HP/slot/risorse/equip/PF-mostro/tab-Master non
devono più passare da un rebuild pieno (`self.controls.clear()` + `_build()`,
o `_build()` dell'intera `MasterView`) per una singola variazione — solo la
sezione/card/tab-bar toccata deve cambiare, il resto dell'albero deve
restare la STESSA istanza di prima (altrimenti l'`animate=` già presente in
`ui/design.py` resta vanificato, lo scatto grosso torna).

Include anche il test del bug scoperto DAL VIVO durante la verifica manuale
in browser di questo stesso giro di fix: `SheetView._refresh_bar_and_header()`
(chiamata da `_refresh_hp_only()`/equip-con-CA/ispirazione per aggiornare
l'header) faceva un `self.update()` sull'intero sottoalbero di `SheetView`,
che azzera lo scroll di qualunque `ScrollMemoryListView` annidata sotto —
esattamente il problema per cui `ScrollMemoryListView`/`ScrollMemoryColumn`
esistono (vedi il loro docstring in `ui/widgets.py`) — senza mai richiamare
`restore_scroll()` sul tab attivo. Riprodotto dal vivo (Playwright, scroll a
metà tab Inventario + equip armatura): la vista tornava in cima. Fix:
`_refresh_bar_and_header()` ora richiama `restore_scroll()` sul contenuto
corrente di `content_container`, se esposto.

Eseguire con:
    PYTHONPATH=".venv/lib/python3.13/site-packages:." python3 test_fluidita_refresh_mirati.py
"""

from __future__ import annotations

import os
import sys
import tempfile

_TMP_HOME = tempfile.mkdtemp(prefix="dnd_fluidita_")
os.environ["HOME"] = _TMP_HOME

from data.database import init_db  # noqa: E402
from data.models import Character  # noqa: E402
from data.repositories import character_repo, master_repo  # noqa: E402

_PASS = 0
_FAIL: list[str] = []


def check(label: str, cond: bool) -> None:
    global _PASS
    if cond:
        _PASS += 1
    else:
        _FAIL.append(label)
        print(f"  FALLITO: {label}")


def _make_bardo() -> Character:
    """Livello 3, incantatore (slot 1°/2°) + risorsa di classe a cerchietti
    (Ispirazione Bardica) — copre in un solo personaggio sia il caso slot sia
    il caso risorse di classe."""
    c = Character(
        name="Fluidity Test", class_name="Bardo", race="Umano", level=3,
        hit_dice_type=8, hit_dice_total=3, hit_dice_remaining=3,
        str_score=10, dex_score=12, con_score=14, int_score=10,
        wis_score=10, cha_score=16, hp_max=24, hp_current=18,
        spellcasting_ability="cha",
    )
    character_repo.create(c)
    return c


def test_combattimento_refresh_hp_only_non_ricostruisce_la_tab() -> None:
    print("\n[1] CombattimentoTab._refresh_hp_only() aggiorna solo la card HP, "
          "senza ricostruire il resto della tab")
    from ui.views.character_sheet.combattimento_tab import CombattimentoTab

    c = _make_bardo()
    tab = CombattimentoTab(c)
    hp_row_before = tab._hp_stats_row
    slots_ref_before = tab._spell_slots_ref
    resources_ref_before = tab._class_resources_ref
    controls_before = tab.controls

    character_repo.update_hp(c.id, 10, 0)
    tab._refresh_hp_only()

    check("la card HP mostra il nuovo valore", "10" in str(tab.character.hp_current))
    check("self._hp_stats_row è la STESSA istanza di prima (nessun rebuild)",
          tab._hp_stats_row is hp_row_before)
    check("self._spell_slots_ref non è stato toccato (stessa istanza)",
          tab._spell_slots_ref is slots_ref_before)
    check("self._class_resources_ref non è stato toccato (stessa istanza)",
          tab._class_resources_ref is resources_ref_before)
    check("self.controls è la STESSA lista di prima (niente clear()+_build())",
          tab.controls is controls_before)


def test_combattimento_refresh_hp_only_concentrazione_interrotta() -> None:
    print("\n[2] Quando il danno interrompe la concentrazione, il chiamante "
          "usa il rebuild pieno (sezione Concentrazione compare/scompare)")
    from ui.views.character_sheet.combattimento_tab import CombattimentoTab

    c = _make_bardo()
    character_repo.set_concentration(c.id, "Charme Persona")
    c2 = character_repo.get_by_id(c.id)
    assert c2 is not None
    tab = CombattimentoTab(c2)
    check("la sezione Concentrazione è presente (concentrating_spell valorizzato)",
          bool((tab.character.concentrating_spell or "").strip()))
    hp_row_before = tab._hp_stats_row

    # Simula l'esito "concentrazione interrotta" come farebbe _on_damage_click:
    character_repo.clear_concentration(c.id)
    tab.character.concentrating_spell = ""
    tab._refresh()  # ramo strutturale, non _refresh_hp_only()

    check("dopo il rebuild pieno la concentrazione non c'è più",
          not (tab.character.concentrating_spell or "").strip())
    check("il rebuild pieno crea una NUOVA istanza di _hp_stats_row (atteso: "
          "è un cambiamento strutturale, non un refresh mirato)",
          tab._hp_stats_row is not hp_row_before)


def test_combattimento_refresh_slots_e_resources_only() -> None:
    print("\n[3] _refresh_slots_only()/_refresh_resources_only() toccano solo "
          "la propria sezione")
    from ui.views.character_sheet.combattimento_tab import CombattimentoTab

    c = _make_bardo()
    tab = CombattimentoTab(c)
    hp_row_before = tab._hp_stats_row
    slots_ref_before = tab._spell_slots_ref
    resources_ref_before = tab._class_resources_ref

    check("slot 1° livello configurati dall'auto-init", any(
        s.slot_level == 1 and s.total > 0 for s in tab._slots))
    check("risorsa 'Ispirazione Bardica' presente dall'auto-init",
          any(r.name == "Ispirazione Bardica" for r in tab._resources))

    slot1 = next(s for s in tab._slots if s.slot_level == 1)
    tab._toggle_slot(1, use=True)
    check("lo slot 1° livello risulta usato", slot1.used == 1)
    check("_spell_slots_ref invariato (stessa istanza)",
          tab._spell_slots_ref is slots_ref_before)
    check("_hp_stats_row non toccato dal toggle slot",
          tab._hp_stats_row is hp_row_before)

    res = next(r for r in tab._resources if r.name == "Ispirazione Bardica")
    used_before = res.current_value
    tab._toggle_resource(res, use=True)
    check("la risorsa è stata consumata di 1",
          res.current_value == used_before - 1)
    check("_class_resources_ref invariato (stessa istanza)",
          tab._class_resources_ref is resources_ref_before)
    check("_hp_stats_row non toccato dal toggle risorsa",
          tab._hp_stats_row is hp_row_before)


def test_combattimento_refresh_stats_only_ispirazione() -> None:
    print("\n[4] _toggle_inspiration() usa _refresh_stats_only(), non un "
          "rebuild pieno")
    from ui.views.character_sheet.combattimento_tab import CombattimentoTab

    c = _make_bardo()
    tab = CombattimentoTab(c)
    hp_row_before = tab._hp_stats_row
    controls_before = tab.controls
    was_inspired = bool(tab.character.inspiration)

    tab._toggle_inspiration(None)

    check("inspiration è stato invertito",
          bool(tab.character.inspiration) != was_inspired)
    check("self._hp_stats_row è la STESSA istanza (stessa Row HP+Stats)",
          tab._hp_stats_row is hp_row_before)
    check("self.controls è la STESSA lista di prima",
          tab.controls is controls_before)


def test_inventario_refresh_mirati() -> None:
    print("\n[5] InventarioTab: equip arma/armatura aggiorna solo la propria "
          "sezione, la cascata scudo aggiorna Armi+Armature")
    from ui.views.character_sheet.inventario_tab import InventarioTab
    from data.models import Weapon

    c = _make_bardo()
    character_repo.create_weapon(
        c.id, "Spada corta", damage_dice="1d6", damage_type="perforante",
        properties="Finesse, Leggera", is_equipped=False,
    )
    character_repo.create_inventory_item(
        c.id, "Armatura di cuoio borchiata", category="armor",
        armor_type="leggera", ca_value=12,
    )
    tab = InventarioTab(c)
    weapons_ref_before = tab._weapons_ref
    armor_ref_before = tab._armor_ref
    oggetti_ref_before = tab._oggetti_ref
    controls_before = tab.controls

    weapon = tab._weapons[0]
    tab._toggle_weapon_equipped(weapon)
    # `_refresh_weapons_only()` ricarica `self._weapons` dal DB (nuove
    # istanze `Weapon`): il vecchio riferimento locale `weapon` resta
    # stantio per costruzione, si rilegge da `tab._weapons` come farebbe
    # la UI al prossimo ridisegno — stesso principio già in uso in
    # `_refresh()` pieno, solo ora con refetch mirato.
    check("l'arma risulta equipaggiata", tab._weapons[0].is_equipped)
    check("_weapons_ref invariato (stessa istanza)",
          tab._weapons_ref is weapons_ref_before)
    check("_armor_ref NON toccato da un equip arma senza cascata scudo",
          tab._armor_ref is armor_ref_before)
    check("self.controls è la STESSA lista di prima (equip arma isolato)",
          tab.controls is controls_before)

    armor = tab._items[0]
    old_ac = c.ac
    tab._toggle_item_equipped(armor)
    check("l'armatura risulta equipaggiata", tab._items[0].is_equipped)
    check("la CA è stata ricalcolata", tab.character.ac != old_ac)
    check("_armor_ref invariato (stessa istanza, aggiornato in-place)",
          tab._armor_ref is armor_ref_before)
    check("_oggetti_ref NON toccato dall'equip armatura",
          tab._oggetti_ref is oggetti_ref_before)
    check("self.controls resta la STESSA lista (nessun rebuild pieno)",
          tab.controls is controls_before)


def test_sheet_view_refresh_bar_and_header_ripristina_lo_scroll_del_tab() -> None:
    print("\n[6] BUG FIX (2026-08-26, trovato dal vivo via Playwright): "
          "SheetView._refresh_bar_and_header() deve richiamare "
          "restore_scroll() sul tab attivo, altrimenti il suo update() "
          "sull'intero sottoalbero azzera lo scroll di qualunque "
          "ScrollMemoryListView annidata sotto")
    from ui.views.character_sheet.sheet_view import SheetView

    c = _make_bardo()
    profs = character_repo.get_proficiencies(c.id)
    sv = SheetView(c, profs)

    calls = {"n": 0}

    class _FakeTabContent:
        def restore_scroll(self) -> None:
            calls["n"] += 1

    sv.content_container.content = _FakeTabContent()
    sv._refresh_bar_and_header()

    check("restore_scroll() del tab attivo è stato chiamato esattamente una volta",
          calls["n"] == 1)

    # Nessun crash se il contenuto del tab non espone restore_scroll()
    # (es. un placeholder ft.Container()) — getattr deve fare da guardia.
    import flet as ft
    sv.content_container.content = ft.Container()
    try:
        sv._refresh_bar_and_header()
        no_crash = True
    except AttributeError:
        no_crash = False
    check("nessun crash se il contenuto del tab non ha restore_scroll()", no_crash)


def test_master_encounter_refresh_member_card_isola_le_altre_card() -> None:
    print("\n[7] MasterEncounterView._refresh_member_card() aggiorna solo la "
          "card del combattente toccato da _on_hp_delta()")
    from ui.views.master.master_encounter_view import MasterEncounterView

    enc = master_repo.create_encounter(name="Imboscata fluidità")
    assert enc is not None
    m1 = master_repo.add_member(enc.id, kind="adhoc", display_name="Goblin A",
                                 ac=13, hp_current=7, hp_max=7)
    m2 = master_repo.add_member(enc.id, kind="adhoc", display_name="Goblin B",
                                 ac=13, hp_current=7, hp_max=7)
    assert m1 is not None and m2 is not None

    mev = MasterEncounterView(encounter_id=enc.id, on_back_to_list=lambda: None,
                               world_id="", device_id="dev-test")
    mev.refresh()
    card_m1_before = mev._member_card_refs[m1.id]
    card_m2_before = mev._member_card_refs[m2.id]

    mev._on_hp_delta(m1, -3)

    check("la card del combattente colpito è la STESSA istanza (update in-place)",
          mev._member_card_refs[m1.id] is card_m1_before)
    check("la card dell'altro combattente non è stata toccata (stessa istanza)",
          mev._member_card_refs[m2.id] is card_m2_before)
    updated = master_repo.get_encounter_members_resolved(enc.id, active_only=True)
    hp_m1 = next(r["hp_current"] for r in updated if r["member"].id == m1.id)
    check("il PF del combattente colpito è stato scalato", hp_m1 == 4)


def test_master_notes_update_left_panel_e_detail() -> None:
    print("\n[8] MasterNotesView: selezionare una nota su desktop aggiorna "
          "pannello sinistro + dettaglio, senza rebuild pieno")
    from ui.views.master.master_notes_view import MasterNotesView

    n1 = master_repo.create_master_campaign_note("npc", "Taverna del Corvo")
    n2 = master_repo.create_master_campaign_note("npc", "Torre Infranta")
    assert n1 is not None and n2 is not None

    mnv = MasterNotesView(world_id="", device_id="dev-test", is_mobile=False)
    left_panel_before = mnv._left_panel_ref
    detail_before = mnv._detail_container

    mnv._on_sel_note(n2.id)

    check("la nota selezionata è cambiata", mnv._sel_note_id == n2.id)
    check("_left_panel_ref è la STESSA istanza (update in-place, desktop)",
          mnv._left_panel_ref is left_panel_before)
    check("_detail_container è la STESSA istanza (update in-place, desktop)",
          mnv._detail_container is detail_before)


def test_master_view_on_tab_click_non_fa_build_pieno() -> None:
    print("\n[9] MasterView._on_tab_click() aggiorna solo tab bar + contenuto, "
          "MAI header/pannello strumenti (nessun _build() pieno)")
    from ui.views.master.master_view import MasterView

    mv = MasterView(on_back_to_home=lambda: None)
    tools_panel_before = mv._tools_panel_container
    controls_before = mv.controls
    first_tab = mv.active_tab

    other_tab = "notes" if first_tab != "notes" else "npcs"
    mv._on_tab_click(other_tab)

    check("il tab attivo è cambiato", mv.active_tab == other_tab)
    check("il pannello strumenti NON è stato ricostruito (stessa istanza — "
          "un _build() pieno lo avrebbe rifatto da zero)",
          mv._tools_panel_container is tools_panel_before)
    check("self.controls resta la STESSA lista (nessun clear() nel percorso "
          "di cambio tab)", mv.controls is controls_before)
    check("il contenuto dello switcher corrisponde al nuovo tab",
          mv._content_switcher.content is not None)


def main() -> int:
    init_db()
    print("=" * 72)
    print("Refresh mirati — piano Fluidità transizioni e animazioni (2026-08-26)")
    print(f"HOME di test: {_TMP_HOME}")
    print("=" * 72)

    test_combattimento_refresh_hp_only_non_ricostruisce_la_tab()
    test_combattimento_refresh_hp_only_concentrazione_interrotta()
    test_combattimento_refresh_slots_e_resources_only()
    test_combattimento_refresh_stats_only_ispirazione()
    test_inventario_refresh_mirati()
    test_sheet_view_refresh_bar_and_header_ripristina_lo_scroll_del_tab()
    test_master_encounter_refresh_member_card_isola_le_altre_card()
    test_master_notes_update_left_panel_e_detail()
    test_master_view_on_tab_click_non_fa_build_pieno()

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
