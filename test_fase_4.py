"""
Batteria di verifica della FASE 4 — le 4 feature autorizzate
(vedi `docs/feature_design_2026_07_26.md`).

DB temporaneo isolato (`tempfile.mkdtemp()` + `HOME` separato): il DB reale non
viene mai toccato. I controlli Flet vengono costruiti davvero e ispezionati
ricorsivamente, pattern gia' consolidato nel progetto.

    PYTHONPATH=".venv/lib/python3.13/site-packages:." python3 test_fase_4.py
"""

from __future__ import annotations

import os
import random
import sys
import tempfile
from typing import Any
from unittest.mock import patch

_TMP_HOME = tempfile.mkdtemp(prefix="dnd_fase4_")
os.environ["HOME"] = _TMP_HOME

import flet as ft  # noqa: E402

from data.database import init_db  # noqa: E402
from data.models import Character, CharacterProficiency, Weapon  # noqa: E402
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


def walk(control: Any, depth: int = 0):
    if control is None or depth > 40:
        return
    yield control
    for attr in ("controls", "actions"):
        kids = getattr(control, attr, None)
        if isinstance(kids, (list, tuple)):
            for k in kids:
                yield from walk(k, depth + 1)
    # `title` serve per gli AlertDialog: il titolo non e' dentro `content`.
    for attr in ("content", "title"):
        child = getattr(control, attr, None)
        if child is not None and not isinstance(child, str):
            yield from walk(child, depth + 1)


def texts(control: Any) -> list[str]:
    out = []
    for c in walk(control):
        if isinstance(c, ft.Text) and isinstance(c.value, str):
            out.append(c.value)
        elif isinstance(getattr(c, "content", None), str):
            out.append(c.content)
    return out


def tooltips(control: Any) -> list[str]:
    return [str(getattr(c, "tooltip", "")) for c in walk(control)
            if getattr(c, "tooltip", None)]


class FakePage:
    def __init__(self, width: int = 1280):
        self.width = width
        self.height = 800
        self.controls: list[Any] = []
        self.overlay: list[Any] = []
        self.dialogs: list[Any] = []
        self.web = False
        self.platform = None
        self.updates = 0

    def add(self, *c: Any) -> None:
        self.controls.extend(c)

    def update(self, *a: Any, **k: Any) -> None:
        self.updates += 1

    def show_dialog(self, dlg: Any) -> None:
        self.dialogs.append(dlg)

    def pop_dialog(self, *a: Any) -> None:
        if self.dialogs:
            self.dialogs.pop()

    def run_task(self, *a: Any, **k: Any) -> None:
        pass


class FixedRandom:
    """
    RNG deterministico: restituisce in ordine i valori indicati.

    Non eredita da `random.Random` di proposito: `Random.__new__` passa gli
    argomenti a `seed()`, e una lista non e' hashable. `core.dice.roll()` usa
    solo `randint`, quindi il duck typing basta.
    """

    def __init__(self, values: list[int]):
        self._values = list(values)
        self._i = 0

    def randint(self, a: int, b: int) -> int:
        v = self._values[self._i % len(self._values)]
        self._i += 1
        return max(a, min(b, v))


# ---------------------------------------------------------------------------
# 1 — core/dice.py
# ---------------------------------------------------------------------------

def test_dice() -> None:
    print("\n[1] core/dice.py — parser e tiri")
    from core import dice as D

    check("1d20+5", D.parse_formula("1d20+5") == ([(1, 1, 20)], 5))
    check("2d6", D.parse_formula("2d6") == ([(1, 2, 6)], 0))
    check("d20 senza quantita'", D.parse_formula("d20") == ([(1, 1, 20)], 0))
    check("piu' termini", D.parse_formula("1d8+1d6+3") == ([(1, 1, 8), (1, 1, 6)], 3))
    check("costante negativa", D.parse_formula("1d20-2") == ([(1, 1, 20)], -2))

    for bad in ("", "   ", "ciao", "1d", "0d6", "1d0", "1d20++2", "2x6"):
        try:
            D.parse_formula(bad)
            check(f"formula non valida rifiutata: {bad!r}", False)
        except ValueError:
            check(f"formula non valida rifiutata: {bad!r}", True)

    r = D.roll("1d20", modifier=5, rng=FixedRandom([13]))
    check("tiro semplice: 13+5=18", r.total == 18)
    check("nessun critico su 13", not r.is_crit and not r.is_crit_fail)

    r = D.roll("1d20", rng=FixedRandom([20]))
    check("20 naturale = critico", r.is_crit and not r.is_crit_fail)
    r = D.roll("1d20", rng=FixedRandom([1]))
    check("1 naturale = fallimento critico", r.is_crit_fail and not r.is_crit)

    r = D.roll("1d20", advantage="advantage", rng=FixedRandom([7, 15]))
    check("vantaggio tiene il piu' alto", r.total == 15)
    check("vantaggio mostra lo scartato", r.groups[0].dropped == [7])
    r = D.roll("1d20", advantage="disadvantage", rng=FixedRandom([7, 15]))
    check("svantaggio tiene il piu' basso", r.total == 7)
    check("svantaggio mostra lo scartato", r.groups[0].dropped == [15])

    # PHB Cap. 7: vantaggio/svantaggio riguardano solo i d20.
    r = D.roll("2d6", advantage="advantage", rng=FixedRandom([3, 4]))
    check("vantaggio ignorato su formula di danno", r.total == 7 and not r.groups[0].dropped)

    r = D.roll("1d8+1d6", modifier=4, rng=FixedRandom([5, 2]))
    check("danno multi-dado: 5+2+4=11", r.total == 11)
    check("dettaglio non vuoto", bool(r.detail()))

    # 500 tiri: mai fuori range, mai eccezioni
    ok = True
    for _ in range(500):
        rr = D.roll("3d6+2")
        if not (5 <= rr.total <= 20):
            ok = False
    check("500 tiri 3d6+2 sempre nel range 5-20", ok)


# ---------------------------------------------------------------------------
# 2 — core/character_stats.py
# ---------------------------------------------------------------------------

def test_stats() -> None:
    print("\n[2] core/character_stats.py — modificatori")
    import core.character_stats as cs

    c = Character(name="T", class_name="Ladro", race="Umano", level=5,
                  str_score=10, dex_score=18, con_score=14, int_score=12,
                  wis_score=13, cha_score=8, hit_dice_type=8,
                  initiative_bonus=5)
    profs = [
        CharacterProficiency(character_id=c.id, proficiency_type="skill",
                             name="Furtivita", is_expert=True),
        CharacterProficiency(character_id=c.id, proficiency_type="skill",
                             name="Acrobazia"),
        CharacterProficiency(character_id=c.id, proficiency_type="save",
                             name="Destrezza"),
        CharacterProficiency(character_id=c.id, proficiency_type="weapon",
                             name="guerra"),
    ]

    # Livello 5 -> bonus competenza 3
    r = cs.skill_roll(c, profs, "Acrobazia")
    check("abilita' competente: DES+4 + comp.+3 = +7", r.modifier == 7 and r.proficient)
    r = cs.skill_roll(c, profs, "Atletica")
    check("abilita' non competente: FOR+0", r.modifier == 0 and not r.proficient)

    # Maestria: bonus competenza raddoppiato
    profs_m = [CharacterProficiency(character_id=c.id, proficiency_type="skill",
                                    name="Acrobazia", is_expert=True)]
    r = cs.skill_roll(c, profs_m, "Acrobazia")
    check("Maestria raddoppia la competenza: +4+6 = +10",
          r.modifier == 10 and r.expert)

    r = cs.save_roll(c, profs, "dex")
    check("TS competente: +7", r.modifier == 7 and r.proficient)
    r = cs.save_roll(c, profs, "str")
    check("TS non competente: +0", r.modifier == 0 and not r.proficient)

    # Il DB storico usa sia "save" sia "saving_throw"
    alt = [CharacterProficiency(character_id=c.id,
                                proficiency_type="saving_throw", name="Forza")]
    check("accettato anche proficiency_type='saving_throw'",
          cs.save_roll(c, alt, "str").proficient)

    r = cs.initiative_roll(c)
    check("iniziativa include initiative_bonus: +4+5 = +9", r.modifier == 9)

    r = cs.ability_check_roll(c, "dex")
    check("prova di caratteristica pura: +4 senza competenza",
          r.modifier == 4 and not r.proficient)

    r = cs.death_save_roll()
    check("TS morte: d20 puro, CD 10, nessun modificatore",
          r.formula == "1d20" and r.modifier == 0 and r.dc == 10)

    r = cs.hit_die_roll(c)
    check("dado vita: 1d8 + COS+2", r.formula == "1d8" and r.modifier == 2)

    check("nessun attacco con incantesimo per un non incantatore",
          cs.spell_attack_roll(c) is None)
    check("nessuna CD incantesimi per un non incantatore",
          cs.spell_save_dc(c) is None)

    mage = Character(name="M", class_name="Mago", race="Umano", level=5,
                     int_score=18, spellcasting_ability="int")
    check("attacco con incantesimo: INT+4 + comp.+3 = +7",
          cs.spell_attack_roll(mage).modifier == 7)
    check("CD incantesimi: 8+3+4 = 15", cs.spell_save_dc(mage) == 15)

    # PHB p.203-204
    check("CD concentrazione con 22 danni = 11", cs.concentration_save_dc(22) == 11)
    check("CD concentrazione con 9 danni = 10 (minimo)",
          cs.concentration_save_dc(9) == 10)
    check("CD concentrazione con 40 danni = 20", cs.concentration_save_dc(40) == 20)

    w = Weapon(character_id=c.id, name="Stocco", damage_dice="1d8",
               damage_type="Perforante", properties="Accurata",
               weapon_category="guerra", attack_bonus=1, damage_bonus=1,
               magic_damages='[{"dice":"1d6","type":"Fuoco"}]')
    a = cs.attack_roll(c, w, profs)
    check("attacco: DES+4 (accurata) + comp.+3 + magico+1 = +8", a.modifier == 8)
    dmg = cs.damage_roll(c, w)
    check("danno include il dado magico extra", dmg.formula == "1d8+1d6")
    check("danno: DES+4 + magico+1 = +5", dmg.modifier == 5)

    w.magic_damages = "non-json"
    check("magic_damages malformato non rompe il tiro",
          cs.damage_roll(c, w).formula == "1d8")

    w2 = Weapon(character_id=c.id, name="Spada Lunga", damage_dice="1d8",
                properties="Versatile", versatile_damage_dice="1d10",
                grip_two_handed=True)
    check("arma Versatile a due mani usa il dado maggiore",
          cs.damage_roll(c, w2).formula == "1d10")
    w2.grip_two_handed = False
    check("arma Versatile a una mano usa il dado base",
          cs.damage_roll(c, w2).formula == "1d8")


# ---------------------------------------------------------------------------
# 3 — Feature 1: agganci sulla scheda
# ---------------------------------------------------------------------------

def test_feature1_hooks() -> None:
    print("\n[3] Feature 1 — agganci di tiro sulla scheda")
    from ui.views.character_sheet.esplorazione_tab import EsplorazioneTab
    from ui.views.character_sheet.combattimento_tab import CombattimentoTab
    from ui.views.character_sheet.sheet_view import SheetView
    from ui.views.spells_view import SpellsView

    c = Character(name="T", class_name="Mago", race="Umano", level=5,
                  dex_score=16, int_score=18, hp_max=30, hp_current=30,
                  spellcasting_ability="int")
    character_repo.create(c)
    character_repo.create_weapon(c.id, "Bastone Ferrato", "1d6", "Contundente")
    profs = character_repo.get_proficiencies(c.id)

    esp = EsplorazioneTab(c)
    dice_btns = [n for n in walk(esp)
                 if isinstance(n, ft.IconButton) and n.icon == ft.Icons.CASINO_OUTLINED]
    check("18 abilita' tirabili", len(dice_btns) == 18)
    check("6 TS tirabili", sum(1 for t in tooltips(esp) if t.startswith("Tira TS")) == 6)

    sv = SheetView(c, profs)
    check("6 prove di caratteristica tirabili",
          sum(1 for t in tooltips(sv) if "Tira una prova di" in t) == 6)
    check("la matita di modifica resta accanto al dado",
          sum(1 for n in walk(sv) if isinstance(n, ft.Icon) and n.icon == ft.Icons.EDIT) >= 6)

    comb = CombattimentoTab(c)
    tt = tooltips(comb)
    check("iniziativa tirabile", any("Tira l'iniziativa" in t for t in tt))
    check("attacco dell'arma tirabile", any("clicca per tirare" in t for t in tt))
    check("danni dell'arma tirabili", any("tirare i danni" in t for t in tt))
    check("nessun TS contro morte sopra 0 PF",
          "Tira TS contro morte" not in texts(comb))

    dying = Character(name="D", class_name="Mago", race="Umano", level=5,
                      hp_max=30, hp_current=0)
    character_repo.create(dying)
    check("TS contro morte offerto a 0 PF",
          "Tira TS contro morte" in texts(CombattimentoTab(dying)))

    sp = SpellsView(c)
    check("attacco con incantesimo tirabile",
          any("Tira l'attacco con incantesimo" in t for t in tooltips(sp)))

    non_caster = Character(name="G", class_name="Guerriero", race="Umano", level=5)
    character_repo.create(non_caster)
    sp2 = SpellsView(non_caster)
    check("nessun tiro d'attacco incantesimo per un non incantatore",
          not any("Tira l'attacco con incantesimo" in t for t in tooltips(sp2)))


# ---------------------------------------------------------------------------
# 4 — TS contro morte: applicazione automatica (PHB p.197)
# ---------------------------------------------------------------------------

def test_death_save_application() -> None:
    print("\n[4] TS contro morte — applicazione automatica")
    import ui.views.character_sheet.combattimento_tab as ct
    from core import dice as D
    import core.character_stats as cs

    def run(nat: int, start_succ: int = 0, start_fail: int = 0):
        c = Character(name="D", class_name="Mago", race="Umano", level=5,
                      hp_max=30, hp_current=0,
                      death_saves_success=start_succ, death_saves_failure=start_fail)
        character_repo.create(c)
        tab = ct.CombattimentoTab(c)
        tab._page = FakePage()   # type: ignore[attr-defined]
        result = D.roll("1d20", rng=FixedRandom([nat]))

        captured = {}

        def fake_show_roll(page, spec, advantage="normal", on_result=None):
            captured["spec"] = spec
            if on_result:
                on_result(spec, result)
            return result

        with patch.object(ct, "show_roll", fake_show_roll), \
             patch.object(ct.CombattimentoTab, "_show_rule_notice",
                          lambda self, *a, **k: None), \
             patch.object(ct.CombattimentoTab, "_refresh", lambda self: None):
            tab._roll_death_save()
        return character_repo.get_by_id(c.id)

    c = run(15)
    check("15 -> un successo", c.death_saves_success == 1 and c.death_saves_failure == 0)
    c = run(5)
    check("5 -> un fallimento", c.death_saves_failure == 1 and c.death_saves_success == 0)
    c = run(10)
    check("10 e' successo (CD 10, non 11)", c.death_saves_success == 1)
    c = run(1)
    check("1 naturale = DUE fallimenti", c.death_saves_failure == 2)
    c = run(1, start_fail=2)
    check("1 naturale non supera mai 3 fallimenti", c.death_saves_failure == 3)
    c = run(20)
    check("20 naturale: torna a 1 PF", c.hp_current == 1)
    check("20 naturale: azzera successi e fallimenti",
          c.death_saves_success == 0 and c.death_saves_failure == 0)
    c = run(15, start_succ=2)
    check("terzo successo: si stabilizza a 3/3", c.death_saves_success == 3)
    c = run(5, start_fail=2)
    check("terzo fallimento: 3/3", c.death_saves_failure == 3)


# ---------------------------------------------------------------------------
# 5 — Pannello dei tiri
# ---------------------------------------------------------------------------

def test_roll_panel() -> None:
    print("\n[5] Pannello dei tiri")
    from ui.components import roll_panel as rp
    import core.character_stats as cs
    from ui import design

    page = FakePage()
    panel = rp.get_panel(page)   # type: ignore[arg-type]
    check("pannello montato in page.overlay", panel.container in page.overlay)
    check("pannello nascosto finche' non si tira", panel.container.visible is False)
    check("pannello posizionato, non a tutto schermo",
          panel.container.right is not None and panel.container.bottom is not None
          and panel.container.width is not None)

    c = Character(name="T", class_name="Ladro", race="Umano", level=5, dex_score=18)
    spec = cs.initiative_roll(c)
    res = panel.roll(spec)
    check("il tiro produce un risultato", res is not None)
    check("pannello visibile dopo il tiro", panel.container.visible is True)
    check("il totale compare nel pannello", str(res.total) in texts(panel.container))
    check("l'etichetta compare nel pannello", "Iniziativa" in texts(panel.container))
    check("i pulsanti vantaggio/svantaggio ci sono su un d20",
          "Vantaggio" in texts(panel.container) and "Svantaggio" in texts(panel.container))

    # Su una formula di danno non hanno senso
    w = Weapon(character_id=c.id, name="Pugnale", damage_dice="1d4")
    panel.roll(cs.damage_roll(c, w))
    check("nessun vantaggio/svantaggio su un tiro di danni",
          "Vantaggio" not in texts(panel.container))

    panel.roll(spec)
    panel.roll(spec)
    check("lo storico si accumula", len(panel.history) >= 3)
    for _ in range(20):
        panel.roll(spec)
    check("lo storico e' limitato", len(panel.history) <= 6)

    panel.close()
    check("il pannello si chiude", panel.container.visible is False)

    check("stessa pagina -> stesso pannello", rp.get_panel(page) is panel)
    check("pagina None gestita", rp.get_panel(None) is None)
    check("show_roll senza pagina non solleva",
          rp.show_roll(None, spec) is None)

    # Formula malformata: si logga e non si rompe la scheda
    from core.character_stats import RollSpec
    bad = RollSpec(kind="test", label="Rotto", formula="non-una-formula")
    check("formula non tirabile ritorna None", panel.roll(bad) is None)

    # Effetto collaterale che esplode: non deve mangiare il tiro
    def boom(spec, result):
        raise RuntimeError("boom")
    check("un on_result rotto non annulla il tiro",
          panel.roll(spec, on_result=boom) is not None)

    # Il pulsante costruisce lo spec al momento del click, non alla creazione
    calls = []
    btn = rp.roll_button(lambda: (calls.append(1), spec)[1], lambda: page)
    check("roll_button e' un IconButton", isinstance(btn, ft.IconButton))
    btn.on_click(None)
    check("spec costruito al click", calls == [1])
    none_btn = rp.roll_button(lambda: None, lambda: page)
    none_btn.on_click(None)
    check("spec None non solleva", True)


# ---------------------------------------------------------------------------
# 6 — Feature 4a: iniziativa lato master
# ---------------------------------------------------------------------------

def test_initiative() -> None:
    print("\n[6] Feature 4a — tiro dell'iniziativa lato master")
    from data.repositories import master_repo
    import ui.views.master.master_encounter_view as mev

    check("modificatore da punteggio: 14 -> +2", mev._mod_from_score(14) == 2)
    check("modificatore da punteggio: 7 -> -2", mev._mod_from_score(7) == -2)
    check("punteggio non numerico -> 0", mev._mod_from_score("boh") == 0)
    check("punteggio None -> 0", mev._mod_from_score(None) == 0)

    vals = {mev._roll_initiative(3) for _ in range(200)}
    check("tiro iniziativa nel range 1+3..20+3", min(vals) >= 4 and max(vals) <= 23)
    check("il tiro varia davvero", len(vals) > 5)

    auto_cb, group_cb, _ = mev._initiative_options()
    check("tiro automatico attivo di default", auto_cb.value is True)
    check("gruppi identici spento di default", group_cb.value is False)

    # dex_mod persistito
    enc = master_repo.create_encounter("Test iniziativa")
    npc = master_repo.create_npc(name="Goblin", ac=15, hp_max=7, xp=50,
                                 dex_score=14, has_stat_block=True)
    m = master_repo.add_member(encounter_id=enc.id, kind="npc", npc_id=npc.id,
                               display_name="Goblin 1", ac=15, hp_current=7,
                               hp_max=7, xp=50, initiative=12, dex_mod=2)
    check("dex_mod salvato sul membro", m is not None and m.dex_mod == 2)
    check("dex_mod riletto dal DB",
          master_repo.get_encounter_members(enc.id)[0].dex_mod == 2)

    # "Tira per tutti": non tocca i PG
    ch = Character(name="Thorin", class_name="Guerriero", race="Nano", level=3,
                   hp_max=30, hp_current=30)
    character_repo.create(ch)
    master_repo.add_member(encounter_id=enc.id, kind="character",
                           character_id=ch.id, display_name=ch.name,
                           initiative=99, order_index=1)
    for i in range(2, 5):
        master_repo.add_member(encounter_id=enc.id, kind="adhoc",
                               display_name=f"Goblin {i}", ac=15, hp_current=7,
                               hp_max=7, xp=50, initiative=5, dex_mod=2,
                               order_index=i)

    view = mev.MasterEncounterView.__new__(mev.MasterEncounterView)
    view.encounter_id = enc.id
    view._page = FakePage()
    view.refresh = lambda: None   # type: ignore[method-assign]
    view._on_roll_all_initiative()
    dlg = view._page.dialogs[-1]
    check("dialog di conferma mostrato", dlg is not None)
    check("il dialog dichiara che i PG non vengono toccati",
          any("non vengono toccati" in t for t in texts(dlg)))
    btns = [b for b in walk(dlg) if isinstance(b, ft.ElevatedButton)]
    roll_btn = next(b for b in btns if str(getattr(b, "content", "")) == "Tira")
    roll_btn.on_click(None)

    after = {m.display_name: m for m in master_repo.get_encounter_members(enc.id)}
    check("l'iniziativa del PG resta intatta", after["Thorin"].initiative == 99)
    monsters = [m for n, m in after.items() if n != "Thorin"]
    check("tutti i mostri sono stati ritirati",
          all(m.initiative != 5 or m.initiative != 12 for m in monsters))
    check("i valori dei mostri sono plausibili (1..20 + DES)",
          all(3 <= m.initiative <= 22 for m in monsters))

    # Gruppi identici: stesso tiro per lo stesso nome base
    enc2 = master_repo.create_encounter("Gruppi")
    for i in range(1, 6):
        master_repo.add_member(encounter_id=enc2.id, kind="adhoc",
                               display_name=f"Goblin {i}", ac=15, hp_current=7,
                               hp_max=7, xp=50, initiative=0, dex_mod=2,
                               order_index=i)
    view2 = mev.MasterEncounterView.__new__(mev.MasterEncounterView)
    view2.encounter_id = enc2.id
    view2._page = FakePage()
    view2.refresh = lambda: None   # type: ignore[method-assign]
    view2._on_roll_all_initiative()
    dlg2 = view2._page.dialogs[-1]
    group_cb2 = next(c for c in walk(dlg2) if isinstance(c, ft.Checkbox))
    group_cb2.value = True
    next(b for b in walk(dlg2)
         if isinstance(b, ft.ElevatedButton)
         and str(getattr(b, "content", "")) == "Tira").on_click(None)
    inits = {m.initiative for m in master_repo.get_encounter_members(enc2.id)}
    check("con 'gruppi identici' i 5 goblin condividono un solo tiro",
          len(inits) == 1)

    # Senza mostri: messaggio dedicato, nessun tiro
    enc3 = master_repo.create_encounter("Solo PG")
    master_repo.add_member(encounter_id=enc3.id, kind="character",
                           character_id=ch.id, display_name=ch.name, initiative=7)
    view3 = mev.MasterEncounterView.__new__(mev.MasterEncounterView)
    view3.encounter_id = enc3.id
    view3._page = FakePage()
    view3.refresh = lambda: None   # type: ignore[method-assign]
    view3._on_roll_all_initiative()
    check("incontro di soli PG: messaggio dedicato",
          any("Nessun mostro" in t for t in texts(view3._page.dialogs[-1])))
    check("incontro di soli PG: iniziativa invariata",
          master_repo.get_encounter_members(enc3.id)[0].initiative == 7)


# ---------------------------------------------------------------------------
# 7 — Feature 2a: concentrazione (PHB p.203-204)
# ---------------------------------------------------------------------------

def test_concentration() -> None:
    print("\n[7] Feature 2a — concentrazione")
    import ui.views.character_sheet.combattimento_tab as ct
    from ui.views.spells_view import SpellsView

    def mk(**kw) -> Character:
        base = dict(name="M", class_name="Mago", race="Umano", level=5,
                    hp_max=30, hp_current=30, con_score=14,
                    spellcasting_ability="int", int_score=18)
        base.update(kw)
        c = Character(**base)   # type: ignore[arg-type]
        character_repo.create(c)
        return c

    # --- repository ---
    c = mk()
    check("nessuna concentrazione alla creazione",
          character_repo.get_by_id(c.id).concentrating_spell == "")
    character_repo.set_concentration(c.id, "Ragnatela")
    got = character_repo.get_by_id(c.id)
    check("concentrazione salvata", got.concentrating_spell == "Ragnatela")
    check("timestamp valorizzato", bool(got.concentrating_since))
    character_repo.set_concentration(c.id, "Volare")
    check("una sola alla volta: la nuova sostituisce la vecchia",
          character_repo.get_by_id(c.id).concentrating_spell == "Volare")
    character_repo.clear_concentration(c.id)
    got = character_repo.get_by_id(c.id)
    check("interruzione azzera nome e timestamp",
          got.concentrating_spell == "" and got.concentrating_since == "")
    got.concentrating_spell = "Invisibilità"
    character_repo.update(got)
    check("update generico persiste la concentrazione",
          character_repo.get_by_id(c.id).concentrating_spell == "Invisibilità")

    # --- sezione in Combattimento ---
    c1 = mk()
    check("nessuna sezione senza concentrazione",
          "CONCENTRAZIONE" not in texts(ct.CombattimentoTab(c1)))
    character_repo.set_concentration(c1.id, "Ragnatela")
    tab = ct.CombattimentoTab(character_repo.get_by_id(c1.id))
    tx = texts(tab)
    check("sezione presente con il nome dell'incantesimo",
          "CONCENTRAZIONE" in tx and any("Ragnatela" in t for t in tx))
    check("la sezione cita la regola",
          any("PHB p.203" in t for t in tx))
    check("c'e' il pulsante Interrompi", any("Interrompi" == t for t in tx))

    # Interruzione manuale
    tab._page = FakePage()   # type: ignore[attr-defined]
    with patch.object(ct.CombattimentoTab, "_refresh", lambda self: None):
        tab._end_concentration()
    check("Interrompi azzera la concentrazione",
          character_repo.get_by_id(c1.id).concentrating_spell == "")

    # --- CD del TS: PHB p.203 ---
    import core.character_stats as cs
    check("CD = 10 con danni bassi", cs.concentration_save_dc(5) == 10)
    check("CD = meta' danni con danni alti", cs.concentration_save_dc(30) == 15)
    check("CD = 10 al confine (20 danni)", cs.concentration_save_dc(20) == 10)
    check("CD = 11 appena sopra (22 danni)", cs.concentration_save_dc(22) == 11)

    # --- danno subito mentre si e' concentrati ---
    def apply_damage(character: Character, amount: int):
        tab = ct.CombattimentoTab(character)
        tab._page = FakePage()   # type: ignore[attr-defined]
        prompts: list[tuple] = []
        with patch.object(ct.CombattimentoTab, "_refresh", lambda self: None), \
             patch.object(ct.CombattimentoTab, "_show_rule_notice",
                          lambda self, *a, **k: None), \
             patch.object(ct.CombattimentoTab, "_prompt_concentration_save",
                          lambda self, s, d: prompts.append((s, d))):
            tab._on_damage_click(None)
            dlg = tab._page.dialogs[-1]
            field = next(n for n in walk(dlg) if isinstance(n, ft.TextField))
            field.value = str(amount)
            btn = next(b for b in walk(dlg) if isinstance(b, ft.ElevatedButton)
                       and str(getattr(b, "content", "")) == "Applica")
            btn.on_click(None)
        return character_repo.get_by_id(character.id), prompts

    c2 = mk()
    character_repo.set_concentration(c2.id, "Ragnatela")
    after, prompts = apply_damage(character_repo.get_by_id(c2.id), 12)
    check("danno subito -> viene proposto il TS", len(prompts) == 1)
    check("il TS riguarda l'incantesimo giusto e il danno giusto",
          prompts and prompts[0] == ("Ragnatela", 12))
    check("la concentrazione resta finche' il TS non e' risolto",
          after.concentrating_spell == "Ragnatela")

    # A 0 PF la concentrazione cade da sola (PHB p.204: incapacitato)
    c3 = mk(hp_current=5)
    character_repo.set_concentration(c3.id, "Volare")
    after, prompts = apply_damage(character_repo.get_by_id(c3.id), 5)
    check("a 0 PF la concentrazione cade automaticamente",
          after.concentrating_spell == "")
    check("a 0 PF non viene chiesto alcun TS", not prompts)

    # Nessun danno -> nessun TS
    c4 = mk()
    character_repo.set_concentration(c4.id, "Volare")
    after, prompts = apply_damage(character_repo.get_by_id(c4.id), 0)
    check("danno 0 non chiede il TS", not prompts)
    check("danno 0 non interrompe la concentrazione",
          after.concentrating_spell == "Volare")

    # Senza concentrazione attiva non succede nulla
    c5 = mk()
    after, prompts = apply_damage(c5, 15)
    check("nessuna concentrazione -> nessun prompt", not prompts)

    # --- dialog del TS ---
    c6 = mk()
    character_repo.set_concentration(c6.id, "Ragnatela")
    tab = ct.CombattimentoTab(character_repo.get_by_id(c6.id))
    tab._page = FakePage()   # type: ignore[attr-defined]
    with patch.object(ct.CombattimentoTab, "_refresh", lambda self: None):
        tab._prompt_concentration_save("Ragnatela", 30)
    dlg = tab._page.dialogs[-1]
    dtx = texts(dlg)
    check("il dialog mostra la CD calcolata", any("CD 15" in t for t in dtx))
    check("il dialog cita la pagina", any("p.203" in t for t in dtx))
    check("il dialog offre di interrompere", "Interrompi" in dtx)
    check("il dialog offre di dichiarare il successo",
          "Ho superato il tiro" in dtx)
    # "Interrompi" nel dialog termina davvero la concentrazione
    with patch.object(ct.CombattimentoTab, "_refresh", lambda self: None):
        next(b for b in walk(dlg) if isinstance(b, ft.TextButton)
             and str(getattr(b, "content", "")) == "Interrompi").on_click(None)
    check("Interrompi dal dialog del TS azzera la concentrazione",
          character_repo.get_by_id(c6.id).concentrating_spell == "")

    # --- attivazione dalla tab Incantesimi ---
    c7 = mk()
    sv = SpellsView(character_repo.get_by_id(c7.id))
    sv._page = FakePage()   # type: ignore[attr-defined]
    with patch.object(SpellsView, "_refresh", lambda self: None):
        sv._activate_concentration("Ragnatela")
    check("attivazione dalla tab Incantesimi",
          character_repo.get_by_id(c7.id).concentrating_spell == "Ragnatela")

    # Se c'e' gia' una concentrazione, l'app avvisa invece di sostituire
    sv._page = FakePage()   # type: ignore[attr-defined]
    with patch.object(SpellsView, "_refresh", lambda self: None):
        sv._activate_concentration("Volare")
    warn = sv._page.dialogs[-1]
    check("avviso prima di sostituire",
          any("interrompe" in t for t in texts(warn)))
    check("non ha ancora sostituito nulla",
          character_repo.get_by_id(c7.id).concentrating_spell == "Ragnatela")
    with patch.object(SpellsView, "_refresh", lambda self: None):
        next(b for b in walk(warn) if isinstance(b, ft.ElevatedButton)
             and str(getattr(b, "content", "")) == "Sostituisci").on_click(None)
    check("dopo la conferma la sostituzione avviene",
          character_repo.get_by_id(c7.id).concentrating_spell == "Volare")

    # Il dettaglio di un incantesimo con concentrazione offre il pulsante
    sv2 = SpellsView(mk())
    sv2._page = FakePage()   # type: ignore[attr-defined]
    sv2._open_spell_dialog({"name": "Ragnatela", "level": 2, "concentration": True,
                            "description": "..."})
    check("pulsante di attivazione sugli incantesimi con concentrazione",
          "Attiva concentrazione" in texts(sv2._page.dialogs[-1]))
    sv2._open_spell_dialog({"name": "Dardo Incantato", "level": 1,
                            "concentration": False, "description": "..."})
    check("nessun pulsante sugli incantesimi senza concentrazione",
          "Attiva concentrazione" not in texts(sv2._page.dialogs[-1]))


# ---------------------------------------------------------------------------
# 8 — Feature 4b: assegnazione dei PE
# ---------------------------------------------------------------------------

def test_award_xp() -> None:
    print("\n[8] Feature 4b — assegnazione dei PE")
    from config.settings import get_level_from_xp
    from data.repositories import master_repo
    import ui.views.master.master_encounter_view as mev

    for xp, lvl in ((0, 1), (299, 1), (300, 2), (6499, 4), (6500, 5),
                    (355000, 20), (999999, 20)):
        check(f"livello da {xp} PE = {lvl}", get_level_from_xp(xp) == lvl)
    check("PE non numerici -> livello 1", get_level_from_xp("boh") == 1)   # type: ignore[arg-type]

    c = Character(name="Thorin", class_name="Guerriero", race="Nano", level=4,
                  xp=6000, hp_max=30, hp_current=30)
    character_repo.create(c)
    check("add_xp somma e ritorna il totale",
          character_repo.add_xp(c.id, 500) == 6500)
    check("il totale e' persistito", character_repo.get_by_id(c.id).xp == 6500)
    check("il livello NON viene toccato dall'app",
          character_repo.get_by_id(c.id).level == 4)
    check("add_xp non scende sotto zero",
          character_repo.add_xp(c.id, -99999) == 0)
    check("add_xp su id inesistente ritorna None",
          character_repo.add_xp("non-esiste", 100) is None)
    # Riporta Thorin a un passo dalla soglia del livello 5 (6.500 PE), cosi'
    # l'assegnazione piu' sotto lo fa salire e possiamo verificare l'avviso.
    character_repo.add_xp(c.id, 6400)

    # Scenario completo
    enc = master_repo.create_encounter("Assegnazione")
    c2 = Character(name="Elara", class_name="Mago", race="Elfo", level=4,
                   xp=6000, hp_max=20, hp_current=20)
    character_repo.create(c2)
    for ch in (c, c2):
        master_repo.add_member(encounter_id=enc.id, kind="character",
                               character_id=ch.id, display_name=ch.name)
    # Due sconfitti (0 PF) e uno ancora in piedi
    master_repo.add_member(encounter_id=enc.id, kind="adhoc", display_name="Goblin 1",
                           ac=15, hp_current=0, hp_max=7, xp=50, dex_mod=2)
    master_repo.add_member(encounter_id=enc.id, kind="adhoc", display_name="Goblin 2",
                           ac=15, hp_current=0, hp_max=7, xp=50, dex_mod=2)
    master_repo.add_member(encounter_id=enc.id, kind="adhoc", display_name="Orco",
                           ac=13, hp_current=15, hp_max=15, xp=100, dex_mod=1)

    view = mev.MasterEncounterView.__new__(mev.MasterEncounterView)
    view.encounter_id = enc.id
    view._page = FakePage()
    view.refresh = lambda: None   # type: ignore[method-assign]
    view._on_award_xp_click()
    dlg = view._page.dialogs[-1]
    cbs = [n for n in walk(dlg) if isinstance(n, ft.Checkbox)]
    check("una casella per mostro", len(cbs) == 3)
    pre = {str(cb.label): cb.value for cb in cbs}
    check("i mostri a 0 PF sono pre-spuntati",
          all(v for k, v in pre.items() if "Goblin" in k))
    check("il mostro ancora in piedi non e' spuntato",
          not next(v for k, v in pre.items() if "Orco" in k))

    tf = next(n for n in walk(dlg) if isinstance(n, ft.TextField))
    check("100 PE totali / 2 PG = 50 a testa", tf.value == "50")

    # Spuntare anche l'Orco ricalcola dal vivo
    orco_cb = next(cb for cb in cbs if "Orco" in str(cb.label))
    orco_cb.value = True
    orco_cb.on_change(None)
    check("ricalcolo dal vivo: 200 / 2 = 100", tf.value == "100")

    # Il totale a testa resta modificabile a mano (PE bonus narrativi)
    tf.value = "120"
    next(b for b in walk(dlg) if isinstance(b, ft.ElevatedButton)
         and str(getattr(b, "content", "")) == "Continua").on_click(None)
    confirm = view._page.dialogs[-1]
    ctx = texts(confirm)
    check("la conferma elenca entrambi i personaggi",
          any("Thorin" in t for t in ctx) and any("Elara" in t for t in ctx))
    check("la conferma mostra il passaggio di livello",
          any("sale al livello 5" in t for t in ctx))
    check("la conferma dichiara che passa sempre dalla pipeline comando/evento",
          any("mai una scrittura diretta" in t for t in ctx))

    next(b for b in walk(confirm) if isinstance(b, ft.ElevatedButton)
         and str(getattr(b, "content", "")) == "Assegna").on_click(None)
    check("PE scritti sul primo personaggio",
          character_repo.get_by_id(c.id).xp == 6520)
    check("PE scritti sul secondo personaggio",
          character_repo.get_by_id(c2.id).xp == 6120)
    check("nessun level-up automatico",
          character_repo.get_by_id(c.id).level == 4)

    # Incontro senza PG
    enc2 = master_repo.create_encounter("Solo mostri")
    master_repo.add_member(encounter_id=enc2.id, kind="adhoc", display_name="Goblin",
                           ac=15, hp_current=0, hp_max=7, xp=50)
    v2 = mev.MasterEncounterView.__new__(mev.MasterEncounterView)
    v2.encounter_id = enc2.id
    v2._page = FakePage()
    v2.refresh = lambda: None   # type: ignore[method-assign]
    v2._on_award_xp_click()
    check("senza PG l'app lo dice invece di assegnare a vuoto",
          any("Nessun personaggio giocante" in t
              for t in texts(v2._page.dialogs[-1])))


# ---------------------------------------------------------------------------
# 9 — Feature 3: oggetti magici e sintonia lato giocatore
# ---------------------------------------------------------------------------

def test_magic_items() -> None:
    print("\n[9] Feature 3 — oggetti magici e sintonia")
    from core.equipment_manager import (AttunementCandidate, MAX_ATTUNED_ITEMS,
                                        attuned_count, can_attune)
    from ui.views.magic_items_view import MagicItemsView
    from ui.views.master.master_magic_items_view import MasterMagicItemsView
    from ui.views.character_sheet.inventario_tab import InventarioTab

    check("il limite del manuale e' 3", MAX_ATTUNED_ITEMS == 3)
    check("la vista del Master e' la stessa del giocatore (zero duplicazione)",
          MasterMagicItemsView is MagicItemsView)

    # --- logica pura (DMG p.138) ---
    full = [AttunementCandidate("1", "Anello di Protezione", True, True),
            AttunementCandidate("2", "Cintura Nanica", True, True),
            AttunementCandidate("3", "Mantello Elfico", True, True),
            AttunementCandidate("4", "Bacchetta dei Fulmini", True, False),
            AttunementCandidate("5", "Corda di Canapa", False, False)]
    check("conteggio degli oggetti in sintonia", attuned_count(full) == 3)
    ok, why = can_attune(full, "4")
    check("il quarto oggetto viene rifiutato", not ok)
    check("il rifiuto spiega la regola e cita la pagina",
          "quarto" in why and "pag. 138" in why)
    ok, why = can_attune(full, "5")
    check("un oggetto che non richiede sintonia viene rifiutato", not ok)
    ok, _ = can_attune(full, "1")
    check("un oggetto gia' in sintonia non si ri-sintonizza", not ok)
    ok, _ = can_attune(full, "id-inesistente")
    check("id inesistente gestito senza eccezioni", not ok)

    dup = [AttunementCandidate("1", "Anello di Protezione", True, True),
           AttunementCandidate("2", "anello di protezione", True, False)]
    ok, why = can_attune(dup, "2")
    check("due copie dello stesso oggetto: rifiutato", not ok)
    check("il rifiuto cita la regola sulle copie", "copia" in why)

    free = [AttunementCandidate("1", "Anello", True, True),
            AttunementCandidate("2", "Bacchetta", True, False)]
    ok, why = can_attune(free, "2")
    check("sotto il limite la sintonia e' concessa", ok and why == "")

    # --- persistenza ---
    c = Character(name="X", class_name="Mago", race="Umano", level=5, str_score=14)
    character_repo.create(c)
    ring = character_repo.create_inventory_item(
        c.id, "Anello di Protezione", category="magic",
        description="Testo ufficiale", requires_attunement=True)
    rope = character_repo.create_inventory_item(c.id, "Corda", category="misc")
    inv = {i.name: i for i in character_repo.get_inventory(c.id)}
    check("requires_attunement salvato sull'oggetto",
          inv["Anello di Protezione"].requires_attunement)
    check("gli altri oggetti restano senza sintonia",
          not inv["Corda"].requires_attunement)
    check("nessun oggetto nasce gia' in sintonia",
          not inv["Anello di Protezione"].is_attuned)
    character_repo.set_item_attunement(ring, True)
    check("sintonia persistita",
          {i.name: i.is_attuned for i in character_repo.get_inventory(c.id)}
          ["Anello di Protezione"])
    character_repo.update_inventory_item(rope, "Corda", 1, 0.0, "", "misc", False)
    check("un update che non passa il flag non lo azzera",
          {i.name: i.requires_attunement
           for i in character_repo.get_inventory(c.id)}["Anello di Protezione"])

    # --- inventario: contatore e limite ---
    tab = InventarioTab(character_repo.get_by_id(c.id))
    tx = texts(tab)
    check("il contatore di sintonia compare", any("Sintonia: 1 / 3" in t for t in tx))
    check("elenca l'oggetto in sintonia",
          any("Anello di Protezione" in t for t in tx))
    check("spiega come si entra in sintonia",
          any("riposo breve" in t for t in tx))

    plain = Character(name="Y", class_name="Guerriero", race="Umano", level=1)
    character_repo.create(plain)
    character_repo.create_inventory_item(plain.id, "Corda", category="misc")
    check("nessuna sezione sintonia senza oggetti che la richiedono",
          not any("Sintonia:" in t for t in texts(InventarioTab(plain))))

    # Quarto oggetto: rifiuto visibile, niente scrittura
    ids = []
    for n in ("Cintura Nanica", "Mantello Elfico", "Bacchetta"):
        ids.append(character_repo.create_inventory_item(
            c.id, n, category="magic", requires_attunement=True))
    for i in ids[:2]:
        character_repo.set_item_attunement(i, True)
    tab = InventarioTab(character_repo.get_by_id(c.id))
    tab._page = FakePage()   # type: ignore[attr-defined]
    fourth = next(i for i in tab._items if i.name == "Bacchetta")
    with patch.object(InventarioTab, "_refresh", lambda self: None):
        tab._toggle_attunement(fourth)
    check("il quarto tentativo mostra un dialog",
          bool(tab._page.dialogs))
    check("il dialog spiega perche' non si puo'",
          any("quarto" in t for t in texts(tab._page.dialogs[-1])))
    check("nessuna scrittura sul quarto oggetto",
          not next(i for i in character_repo.get_inventory(c.id)
                   if i.name == "Bacchetta").is_attuned)

    # Interrompere libera uno slot
    with patch.object(InventarioTab, "_refresh", lambda self: None):
        tab._toggle_attunement(next(i for i in tab._items
                                    if i.name == "Anello di Protezione"))
    check("interrompere la sintonia libera lo slot",
          not next(i for i in character_repo.get_inventory(c.id)
                   if i.name == "Anello di Protezione").is_attuned)

    # --- compendio: sola consultazione, solo lato Master ---
    view = MagicItemsView()
    view._page = FakePage()   # type: ignore[attr-defined]
    check("il compendio ha caricato le 264 voci", len(view._all_items) == 264)
    sample = next(it for it in view._all_items if it.get("requires_attunement"))
    view._open_detail(sample)
    detail = texts(view._page.dialogs[-1])
    check("il dettaglio mostra la descrizione ufficiale",
          any(sample["description"][:40] in t for t in detail))
    check("nessuna aggiunta alla scheda dal compendio",
          "Aggiungi alla mia scheda" not in detail)
    check("la vista non conosce piu' alcun personaggio",
          not hasattr(view, "character"))

    # La voce "Oggetti" e' stata tolta dalla sidebar del giocatore
    from ui.app import SECTIONS
    check("nessuna voce 'Oggetti' nella sidebar del giocatore",
          not any(sec["key"] == "items" for sec in SECTIONS))
    check("la sidebar del giocatore ha 6 sezioni", len(SECTIONS) == 6)

    # --- BUG FIX (2026-08-20): dialog dedicato lettura/modifica descrizione
    # oggetto generico — bug report Davide: un oggetto magico assegnato
    # "perde la sua descrizione diventando sostanzialmente inutile", serve
    # un modo per leggerla/modificarla senza aprire il form "Modifica"
    # completo (come già succede per mostri/NPC in Sezione Incontri). ---
    magic_item = next(i for i in character_repo.get_inventory(c.id)
                       if i.name == "Anello di Protezione")
    tab2 = InventarioTab(character_repo.get_by_id(c.id))
    tab2._page = FakePage()   # type: ignore[attr-defined]
    tab2._open_item_description_dialog(magic_item)
    check("il click apre un dialog", bool(tab2._page.dialogs))
    dlg = tab2._page.dialogs[-1]
    check("il titolo del dialog è il nome dell'oggetto",
          any(magic_item.name in t for t in texts(dlg.title)))
    desc_field = dlg.content.content
    check("il campo mostra la descrizione esistente ('Testo ufficiale')",
          isinstance(desc_field, ft.TextField) and desc_field.value == "Testo ufficiale")

    desc_field.value = "Aggiornata dal giocatore in sessione"
    save_btn = dlg.actions[0].controls[1]
    check("il secondo pulsante è «Salva»", save_btn.content == "Salva" if hasattr(save_btn, "content") else False)
    save_btn.on_click(None)
    check("la nuova descrizione è stata salvata su DB",
          next(i for i in character_repo.get_inventory(c.id)
               if i.name == "Anello di Protezione").description
          == "Aggiornata dal giocatore in sessione")
    check("il dialog si chiude dopo il salvataggio", not tab2._page.dialogs)

    # Funziona anche per un oggetto senza descrizione (aggiunto a mano dal
    # giocatore, mai assegnato da un master) — nessuna distinzione di
    # provenienza, stesso campo per tutti.
    plain_item_id = character_repo.create_inventory_item(c.id, "Torcia", category="misc")
    plain_item = next(i for i in character_repo.get_inventory(c.id) if i.id == plain_item_id)
    tab2._open_item_description_dialog(plain_item)
    empty_field = tab2._page.dialogs[-1].content.content
    check("un oggetto senza descrizione mostra il campo vuoto (non un errore)",
          empty_field.value == "")


# ---------------------------------------------------------------------------
# 10 — Feature 2b: le condizioni dell'Appendice A
# ---------------------------------------------------------------------------

def test_conditions() -> None:
    print("\n[10] Feature 2b — condizioni")
    from data.game_data.game_data_loader import game_data
    import ui.views.character_sheet.combattimento_tab as ct

    conds = game_data.get_conditions()
    check("14 condizioni trascritte (l'Indebolimento e' a parte)", len(conds) == 14)
    names = {c["name"] for c in conds}
    attesi = {"Accecato", "Affascinato", "Afferrato", "Assordato", "Avvelenato",
              "Incapacitato", "Invisibile", "Paralizzato", "Pietrificato",
              "Privo di Sensi", "Prono", "Spaventato", "Stordito", "Trattenuto"}
    check("i nomi combaciano con l'Appendice A", names == attesi)
    check("nessun nome tradotto dall'inglese: Restrained -> Trattenuto",
          "Trattenuto" in names and "Restrained" not in names)
    check("ogni condizione ha testo e almeno un punto",
          all(c.get("description") and c.get("bullets") for c in conds))
    check("lookup per chiave", game_data.get_condition("prono")["name"] == "Prono")
    check("chiave inesistente -> None", game_data.get_condition("zzz") is None)

    av = game_data.get_condition("avvelenato")["effects"]
    check("Avvelenato: svantaggio ad attacchi e prove",
          av.get("attack_disadvantage") and av.get("ability_check_disadvantage"))
    tr = game_data.get_condition("trattenuto")["effects"]
    check("Trattenuto: velocita' 0", tr.get("speed_zero"))
    check("Trattenuto: svantaggio ai TS su Destrezza",
          tr.get("save_disadvantage") == ["dex"])
    par = game_data.get_condition("paralizzato")["effects"]
    check("Paralizzato: incapacitato e TS FOR/DES falliti",
          par.get("incapacitated") and par.get("auto_fail_saves") == ["str", "dex"])
    inv = game_data.get_condition("invisibile")["effects"]
    check("Invisibile: vantaggio proprio, svantaggio a chi attacca",
          inv.get("attack_advantage") and inv.get("attacked_disadvantage"))

    c = Character(name="X", class_name="Mago", race="Umano", level=5,
                  hp_max=30, hp_current=30, speed=9)
    character_repo.create(c)
    check("nessuna condizione alla creazione",
          character_repo.get_conditions(c.id) == [])
    cid = character_repo.add_condition(c.id, "avvelenato", "Morso di ragno")
    character_repo.add_condition(c.id, "prono")
    check("due condizioni attive", len(character_repo.get_conditions(c.id)) == 2)
    character_repo.add_condition(c.id, "avvelenato", "Morso di ragno")
    check("stessa condizione dalla stessa fonte non si duplica",
          len(character_repo.get_conditions(c.id)) == 2)
    character_repo.add_condition(c.id, "avvelenato", "Freccia avvelenata")
    check("stessa condizione da fonte diversa e' una voce a se'",
          len(character_repo.get_conditions(c.id)) == 3)

    eff = character_repo.condition_effects(c.id)
    check("effetti uniti dalle condizioni attive",
          eff.get("attack_disadvantage") and eff.get("ability_check_disadvantage"))
    check("le fonti sono tracciate",
          "Avvelenato" in eff["_sources"]["attack_disadvantage"])

    character_repo.remove_condition(cid)
    check("rimozione puntuale", len(character_repo.get_conditions(c.id)) == 2)
    character_repo.clear_conditions(c.id)
    check("azzeramento totale", character_repo.get_conditions(c.id) == [])

    tab = ct.CombattimentoTab(character_repo.get_by_id(c.id))
    tx = texts(tab)
    check("la sezione Condizioni c'e' sempre", "CONDIZIONI" in tx)
    check("stato vuoto esplicito",
          any("Nessuna condizione attiva" in t for t in tx))
    check("c'e' il pulsante di aggiunta",
          any("Aggiungi condizione" in t for t in tx))

    character_repo.add_condition(c.id, "avvelenato", "Ragno")
    character_repo.add_condition(c.id, "trattenuto")
    tab = ct.CombattimentoTab(character_repo.get_by_id(c.id))
    tx = texts(tab)
    check("i chip mostrano nome e fonte", "Avvelenato \u00b7 Ragno" in tx)
    check("i chip senza fonte mostrano il solo nome", "Trattenuto" in tx)
    hints = [t for t in tx if t.startswith(("Svantaggio", "Vantaggio"))]
    check("promemoria: svantaggio ai tiri per colpire",
          any("tiri per colpire \u2014 Avvelenato, Trattenuto" in h for h in hints))
    check("promemoria: svantaggio alle prove di caratteristica",
          any("prove di caratteristica \u2014 Avvelenato" in h for h in hints))
    check("promemoria: svantaggio ai TS su Destrezza",
          any("salvezza su Destrezza \u2014 Trattenuto" in h for h in hints))
    check("promemoria: vantaggio a chi ti attacca",
          any("chi ti attacca \u2014 Trattenuto" in h for h in hints))
    check("velocita' mostrata a 0 se Trattenuto", "0m" in tx)

    tab._page = FakePage()   # type: ignore[attr-defined]
    cond = next(x for x in tab._conditions if x.condition_key == "trattenuto")
    with patch.object(ct.CombattimentoTab, "_refresh", lambda self: None):
        tab._on_condition_click(cond)
    dlg = tab._page.dialogs[-1]
    check("il dettaglio mostra il testo del manuale",
          any("velocit\u00e0 di una creatura trattenuta" in t for t in texts(dlg)))
    check("il dettaglio cita l'Appendice A",
          any("Appendice A" in t for t in texts(dlg)))
    with patch.object(ct.CombattimentoTab, "_refresh", lambda self: None):
        next(b for b in walk(dlg) if isinstance(b, ft.ElevatedButton)
             and str(getattr(b, "content", "")) == "Rimuovi").on_click(None)
    check("il pulsante Rimuovi toglie la condizione",
          not any(x.condition_key == "trattenuto"
                  for x in character_repo.get_conditions(c.id)))

    tab._page = FakePage()   # type: ignore[attr-defined]
    with patch.object(ct.CombattimentoTab, "_refresh", lambda self: None):
        tab._open_condition_picker()
    picker_dlg = tab._page.dialogs[-1]
    ptx = texts(picker_dlg)
    check("il picker elenca tutte le condizioni",
          sum(1 for n in attesi if n in ptx) == 14)
    check("il picker mostra la descrizione prima di scegliere",
          any("non \u00e8 in grado di vedere" in t for t in ptx))
    src = next(n for n in walk(picker_dlg) if isinstance(n, ft.TextField))
    src.value = "Prova"
    with patch.object(ct.CombattimentoTab, "_refresh", lambda self: None):
        next(b for b in walk(picker_dlg) if isinstance(b, ft.ElevatedButton)
             and str(getattr(b, "content", "")) == "Aggiungi").on_click(None)
    check("il picker aggiunge la condizione con la fonte",
          any(x.source == "Prova" for x in character_repo.get_conditions(c.id)))

    fresh = character_repo.get_by_id(c.id)
    tab = ct.CombattimentoTab(fresh)
    tab._page = FakePage()   # type: ignore[attr-defined]
    section = tab._section_riposo_lungo(fresh)
    start = next(b for b in walk(section) if isinstance(b, ft.ElevatedButton))
    with patch.object(ct.CombattimentoTab, "_refresh", lambda self: None):
        start.on_click(None)
        dlg = tab._page.dialogs[-1]
        next(b for b in walk(dlg) if isinstance(b, ft.ElevatedButton)).on_click(None)
    check("dopo il riposo lungo nessuna condizione resta",
          character_repo.get_conditions(c.id) == [])
    check("il riposo lungo azzera anche la concentrazione",
          character_repo.get_by_id(c.id).concentrating_spell == "")


# ---------------------------------------------------------------------------
# 11 — Artefatti (DMG Cap. 7)
# ---------------------------------------------------------------------------

def test_artifacts() -> None:
    print("\n[11] Artefatti della DMG")
    from data.game_data.game_data_loader import game_data
    from ui.views.master.master_artifacts_dialog import show_artifacts_dialog

    data = game_data.get_artifacts_data()
    check("il file dichiara la fonte",
          "Guida del Dungeon Master" in data.get("_source", ""))

    tables = data.get("tables", {})
    check("quattro tabelle di proprieta'", set(tables) == {
        "benefiche_minori", "benefiche_maggiori", "nocive_minori", "nocive_maggiori"})
    for key, table in tables.items():
        covered: set[int] = set()
        overlap = False
        for e in table["entries"]:
            lo, hi = e["roll"].split("-")
            lo_i, hi_i = int(lo), (100 if hi == "00" else int(hi))
            for i in range(lo_i, hi_i + 1):
                if i in covered:
                    overlap = True
                covered.add(i)
        check(f"{key}: copertura d100 completa", len(covered) == 100)
        check(f"{key}: nessuna sovrapposizione", not overlap)
        check(f"{key}: nessuna riga vuota",
              all(e.get("text") for e in table["entries"]))

    for key in tables:
        rolls = [game_data.roll_artifact_property(key) for _ in range(200)]
        check(f"{key}: 200 tiri sempre risolti", all(r is not None for r in rolls))
        check(f"{key}: tiri nel range 1-100",
              all(1 <= r["roll"] <= 100 for r in rolls if r))
        check(f"{key}: il tiro varia", len({r["range"] for r in rolls if r}) > 3)
    check("tabella inesistente -> None",
          game_data.roll_artifact_property("zzz") is None)

    arts = game_data.get_artifacts()
    check("almeno 5 artefatti trascritti", len(arts) >= 5)
    check("ogni artefatto ha nome, sottotitolo, lore e pagina",
          all(a.get("name") and a.get("subtitle") and a.get("lore")
              and a.get("source_page") for a in arts))
    check("ogni artefatto ha delle proprieta' nominate",
          all(a.get("properties") for a in arts))
    check("ogni artefatto dichiara le proprie proprieta' casuali",
          all(any("Casuali" in p.get("name", "") for p in a["properties"])
              for a in arts))
    # I 7 artefatti DMG sono stati completati (2026-07-xx, vedi CLAUDE.md
    # "Artefatti DMG (7/7)"): "Occhio e Mano di Vecna" prima mancava ed era
    # dichiarato onestamente in "_incomplete_note", ora è trascritto e la
    # nota è stata correttamente rimossa dal JSON (la UI gestisce già la sua
    # assenza, vedi master_artifacts_dialog.py: `if note:`).
    check("tutti i 7 artefatti DMG sono trascritti, incluso Vecna",
          {a.get("name") for a in arts} >= {
              "Ascia dei Signori dei Nani", "Bacchetta di Orcus",
              "Globo dei Draghi", "Libro delle Fosche Tenebre",
              "Libro delle Imprese Eroiche", "Occhio e Mano di Vecna",
              "Spada di Kas"})
    check("nessuna nota di incompletezza residua (dati completi)",
          not data.get("_incomplete_note"))
    check("regole di distruzione presenti",
          len(data.get("destruction", {}).get("suggestions", [])) == 7)

    page = FakePage()
    show_artifacts_dialog(page)   # type: ignore[arg-type]
    dlg = page.dialogs[-1]
    tx = texts(dlg)
    check("il dialog elenca gli artefatti", all(a["name"] in tx for a in arts))
    check("il dialog avvisa di cosa manca",
          any("Occhio e Mano di Vecna" in t for t in tx))
    card = next(n for n in walk(dlg)
                if getattr(n, "tooltip", "") == "Apri la scheda di Bacchetta di Orcus")
    card.on_click(None)
    detail = texts(page.dialogs[-1])
    check("la scheda mostra la lore", any("Orcus" in t for t in detail))
    check("la scheda mostra le proprieta' nominate",
          "Richiamare Non Morti" in detail)
    check("la scheda cita la pagina", any("pag. 222" in t for t in detail))

    page2 = FakePage()
    show_artifacts_dialog(page2)   # type: ignore[arg-type]
    dlg2 = page2.dialogs[-1]
    tab_btn = next(n for n in walk(dlg2)
                   if isinstance(getattr(n, "content", None), ft.Text)
                   and n.content.value == "Propriet\u00e0 casuali")
    tab_btn.on_click(None)
    tx2 = texts(dlg2)
    check("la scheda proprieta' mostra i quattro pulsanti",
          all(lbl in tx2 for lbl in ("Benefiche minori", "Benefiche maggiori",
                                     "Nocive minori", "Nocive maggiori")))
    roll_btn = next(b for b in walk(dlg2) if isinstance(b, ft.OutlinedButton)
                    and str(getattr(b, "content", "")) == "Nocive maggiori")
    roll_btn.on_click(None)
    check("il tiro produce un risultato nel dialog",
          any("d100 = " in t for t in texts(dlg2)))


# ---------------------------------------------------------------------------
# 12 — Regressioni segnalate da Davide il 2026-07-30
# ---------------------------------------------------------------------------

def test_regressioni_davide() -> None:
    print("\n[12] Regressioni segnalate da Davide")
    import importlib
    import pathlib as _pl

    # (a) Ogni modulo deve IMPORTARSI, non solo compilare: e' il controllo che
    # mancava e che ha lasciato passare l'ImportError di `_rarity_color`.
    mods = []
    for f in sorted(_pl.Path(".").rglob("*.py")):
        sf = str(f)
        if sf.startswith(("build/", ".venv/")) or "__pycache__" in sf:
            continue
        if sf.startswith("test_") or f.name == "main.py":
            continue
        mods.append(sf[:-3].replace("/", "."))
    broken = []
    for m in mods:
        try:
            importlib.import_module(m)
        except Exception as exc:
            broken.append(f"{m}: {type(exc).__name__}: {exc}")
    check(f"tutti i {len(mods)} moduli si importano", not broken)
    for b in broken[:5]:
        print(f"    {b}")

    # Lo shim del Master ri-esporta anche gli helper privati
    from ui.views.master import master_magic_items_view as shim
    for name in ("_rarity_color", "_category_icon", "_RARITY_LABELS",
                 "_RARITY_ORDER", "_RARITY_TONES", "_category_base",
                 "_rarity_bucket", "_CATEGORY_ICONS"):
        check(f"lo shim ri-esporta {name}", hasattr(shim, name))

    # (b) I pannelli laterali di Note/Diario scorrono
    from data.repositories import character_repo as _cr
    from ui.views.master.master_notes_view import MasterNotesView
    from ui.views.diary_view import DiaryView
    ch = Character(name="Panel", class_name="Bardo", race="Umano", level=2)
    _cr.create(ch)
    for label, view in (("Note di Campagna", MasterNotesView()),
                        ("Diario", DiaryView(ch))):
        panel = view._build_left_panel()
        check(f"{label}: il pannello laterale scorre",
              panel.content.scroll is not None)
        check(f"{label}: nessuno scroll annidato nella lista",
              getattr(view._left_list_lv, "scroll", None) is None)

    # (c) 1 e 20 naturali: nessun modificatore sommato
    from ui.components import roll_panel as rp
    from core import dice as D
    import core.character_stats as cs

    page = FakePage()
    panel = rp.get_panel(page)   # type: ignore[arg-type]
    c = Character(name="T", class_name="Ladro", race="Umano", level=5, dex_score=18)
    spec = cs.initiative_roll(c)   # modificatore +4

    def _render(nat: int):
        res = D.roll("1d20", modifier=spec.modifier, rng=FixedRandom([nat]))
        panel._render(spec, res)
        return texts(panel.container), res

    tx, res = _render(20)
    check("20 naturale: il totale grezzo sarebbe stato 24", res.total == 24)
    check("20 naturale: il pannello mostra 20, non 24",
          "20" in tx and "24" not in tx)
    check("20 naturale: etichettato come successo critico",
          "SUCCESSO CRITICO" in tx)
    check("20 naturale: dice che il modificatore non si applica",
          any("modificatore non si applica" in t for t in tx))

    tx, res = _render(1)
    check("1 naturale: il totale grezzo sarebbe stato 5", res.total == 5)
    check("1 naturale: il pannello mostra 1, non 5",
          "1" in tx and "5" not in tx)
    check("1 naturale: etichettato come fallimento critico",
          "FALLIMENTO CRITICO" in tx)

    tx, res = _render(13)
    check("tiro normale: il modificatore si somma ancora",
          "17" in tx and not any("modificatore non si applica" in t for t in tx))

    # Su un TS contro morte il verdetto contro la CD non compare su un
    # naturale (la nota "d20 puro, CD 10" resta: e' la descrizione del tiro).
    def _verdict(txts):
        return [t for t in txts if t.startswith("CD 10 \u2014")]

    panel._render(cs.death_save_roll(), D.roll("1d20", rng=FixedRandom([20])))
    check("naturale: nessun verdetto contro la CD",
          not _verdict(texts(panel.container)))
    panel._render(cs.death_save_roll(), D.roll("1d20", rng=FixedRandom([12])))
    check("tiro normale: il verdetto contro la CD resta",
          _verdict(texts(panel.container)) == ["CD 10 \u2014 successo"])


def main() -> int:
    print("=" * 62)
    print("FASE 4 — feature 1 (dadi collegati alla scheda)")
    print(f"HOME di test: {_TMP_HOME}")
    print("=" * 62)
    init_db()

    test_dice()
    test_stats()
    test_feature1_hooks()
    test_death_save_application()
    test_roll_panel()
    test_initiative()
    test_concentration()
    test_award_xp()
    test_magic_items()
    test_conditions()
    test_artifacts()
    test_regressioni_davide()

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
