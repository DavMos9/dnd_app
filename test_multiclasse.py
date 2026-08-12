"""
Verifica della progettazione Multiclasse (PHB IT cap.6, p.163-165) — 2026-08-12,
richiesta esplicita di Davide ("facciamo la sezione multiclasse adesso...
implementiamo quando ti do io il via"): schema/repository layer completo e
un fix di sicurezza sul level-up esistente, PRIMA della UI di livello
completo (esplicitamente fuori scope in questo giro — vedi
`docs/multiclasse_design.md` per lo stato esatto).

Sei parti:

[1] Migrazione — un personaggio pre-esistente (nessuna riga
    character_classes) viene backfillato correttamente e idempotentemente
    da init_db(); un personaggio creato con create() ha già la sua riga
    primaria.

[2] Prerequisiti (PHB IT p.163, tabella trascritta in multiclass_data.json)
    — verificati contro la tabella del manuale, incluso l'esempio letterale
    del PHB (Guerriero: Forza 13 OPPURE Destrezza 13).

[3] Competenze ridotte (PHB IT p.164) — applicate correttamente per una
    nuova classe, MAI quelle complete di apply_class_base_proficiencies();
    risoluzione delle entry "choice" (any_skill, own_class_skill_list,
    categoria strumento).

[4] Risorse di classe multiclasse — Furia (Barbaro) e Punti Ki (Monaco)
    coesistono sullo stesso personaggio senza cancellarsi a vicenda
    (init_class_resources() prima di questa sessione faceva un "replace
    totale" per nome, un bug reale se chiamato una volta per classe).

[5] Slot incantesimo multiclasse (PHB IT p.165) — riproduce ESATTAMENTE
    l'esempio numerico del manuale stesso: "ranger 4/mago 3... è
    considerato un personaggio di 5° livello... quattro slot di 1°
    livello, tre di 2°, due di 3°" — [4,3,2,0,0,0,0,0,0].

[6] Sicurezza del level-up esistente — un personaggio multiclasse che sale
    di livello nella classe PRIMARIA (via _on_level_up_click, non
    replicabile qui senza Flet in esecuzione: verificato indirettamente
    tramite le stesse funzioni di repository che quel metodo chiama in
    sequenza) non deve perdere i livelli delle altre classi dal totale.

Eseguire con:
    PYTHONPATH=".venv/lib/python3.13/site-packages:." python3 test_multiclasse.py
"""

from __future__ import annotations

import os
import sys
import tempfile

_TMP_HOME = tempfile.mkdtemp(prefix="dnd_multiclasse_")
os.environ["HOME"] = _TMP_HOME

from data.database import init_db, get_connection  # noqa: E402
from data.models import Character  # noqa: E402
from data.repositories import character_repo  # noqa: E402
from data.game_data.game_data_loader import game_data  # noqa: E402

_PASS = 0
_FAIL: list[str] = []


def check(label: str, cond: bool) -> None:
    global _PASS
    if cond:
        _PASS += 1
    else:
        _FAIL.append(label)
        print(f"  FALLITO: {label}")


_ABILITY_FIELD = {
    "forza": "str_score", "destrezza": "dex_score", "costituzione": "con_score",
    "intelligenza": "int_score", "saggezza": "wis_score", "carisma": "cha_score",
}


def _make_character(name: str, class_name: str, level: int, **scores) -> Character:
    defaults = dict(str_score=10, dex_score=10, con_score=10,
                     int_score=10, wis_score=10, cha_score=10)
    defaults.update({_ABILITY_FIELD[k]: v for k, v in scores.items()})
    c = Character(
        name=name, class_name=class_name, level=level,
        hit_dice_type=10, hit_dice_total=level, hit_dice_remaining=level,
        hp_max=10 * level, hp_current=10 * level,
        **defaults,
    )
    character_repo.create(c)
    return c


def test_migrazione():
    print("\n[1] Migrazione — backfill legacy + create() già popolato")

    # Personaggio "legacy": inserito con SQL diretto, come un personaggio
    # esistente PRIMA di questa feature (nessuna riga character_classes).
    conn = get_connection()
    conn.execute("""
        INSERT INTO characters (id, name, class_name, subclass, level,
            str_score, dex_score, con_score, int_score, wis_score, cha_score,
            hp_max, hp_current, hit_dice_type, hit_dice_total, hit_dice_remaining)
        VALUES ('legacy-1', 'Legacy', 'Guerriero', '', 5,
            14,12,14,10,10,10, 44,44, 10,5,5)
    """)
    conn.commit()
    conn.close()

    check("legacy: nessuna riga PRIMA della migrazione",
          character_repo.get_character_classes("legacy-1") == [])

    init_db()  # ri-esegue _migrate() → backfill self-healing

    legacy_classes = character_repo.get_character_classes("legacy-1")
    check("legacy: una riga dopo init_db()", len(legacy_classes) == 1)
    check("legacy: classe/livello/is_primary corretti",
          legacy_classes and legacy_classes[0].class_name == "Guerriero"
          and legacy_classes[0].level == 5 and legacy_classes[0].is_primary)

    init_db()
    init_db()
    check("legacy: idempotente (ancora una sola riga dopo altri init_db())",
          len(character_repo.get_character_classes("legacy-1")) == 1)

    c = _make_character("Nuovo", "Ladro", 3, destrezza=16)
    fresh_classes = character_repo.get_character_classes(c.id)
    check("create(): riga primaria già presente", len(fresh_classes) == 1)
    check("create(): is_primary=True", fresh_classes[0].is_primary)
    check("create(): display string a classe singola",
          character_repo.get_class_display_string(c.id) == "Ladro 3")


def test_prerequisiti():
    print("\n[2] Prerequisiti di Multiclasse (PHB IT p.163)")

    # Esempio letterale del manuale: Guerriero = Forza 13 OPPURE Destrezza 13.
    prereq = game_data.get_multiclass_prerequisites("Guerriero")
    check("Guerriero: due opzioni in OR", len(prereq) == 2)
    check("Guerriero: opzione Forza 13", [["forza", 13]] in prereq)
    check("Guerriero: opzione Destrezza 13", [["destrezza", 13]] in prereq)

    # Monaco = Destrezza 13 E Saggezza 13 (AND, una sola opzione).
    monaco_prereq = game_data.get_multiclass_prerequisites("Monaco")
    check("Monaco: una sola opzione", len(monaco_prereq) == 1)
    check("Monaco: richiede DES 13 e SAG 13",
          set(tuple(r) for r in monaco_prereq[0]) == {("destrezza", 13), ("saggezza", 13)})

    c = _make_character("Prereq", "Barbaro", 3, forza=16, destrezza=10, saggezza=8)

    ok, failures = character_repo.check_multiclass_prerequisites(c, "Guerriero")
    check("Barbaro FOR16: qualifica per Guerriero (FOR13 soddisfatta)", ok and not failures)

    ok, failures = character_repo.check_multiclass_prerequisites(c, "Monaco")
    check("Barbaro SAG8: NON qualifica per Monaco (manca SAG13)", not ok and len(failures) == 1)

    # Deve controllare anche le classi GIA' possedute, non solo quella nuova.
    c2 = _make_character("Prereq2", "Barbaro", 3, forza=8)  # sotto la soglia della propria classe
    ok, failures = character_repo.check_multiclass_prerequisites(c2, "Ladro")
    check("Barbaro con FOR8 (sotto soglia della propria classe): fallisce anche sulla classe posseduta",
          not ok and any("Barbaro" in f for f in failures))


def test_competenze():
    print("\n[3] Competenze dei Multiclasse (PHB IT p.164)")

    check("Mago: nessuna competenza da multiclasse",
          game_data.get_multiclass_proficiency_entries("Mago") == [])
    check("Barbaro: scudi + armi semplici/guerra",
          game_data.get_multiclass_proficiency_entries("Barbaro") == ["scudi", "semplice", "guerra"])

    c = _make_character("Comp", "Guerriero", 4, destrezza=14)
    character_repo.add_character_class(c.id, "Ladro", level=1)
    character_repo.apply_multiclass_proficiencies(c.id, "Ladro")

    conn = get_connection()
    rows = {(r["proficiency_type"], r["name"])
            for r in conn.execute(
                "SELECT proficiency_type, name FROM character_proficiencies WHERE character_id=?",
                (c.id,)).fetchall()}
    conn.close()
    check("Ladro multiclasse: armatura leggera applicata", ("armor", "leggere") in rows)
    check("Ladro multiclasse: Arnesi da Scasso applicati", ("tool", "Arnesi da Scasso") in rows)
    check("Ladro multiclasse: competenza COMPLETA (creazione) NON applicata — niente arnesi da ladro extra",
          ("skill", "Furtività") not in rows)  # non era tra le scelte fatte qui

    options = character_repo.resolve_multiclass_choice_options(
        {"from": "own_class_skill_list"}, "Ladro")
    check("own_class_skill_list risolve nella lista skill del Ladro (non vuota)", len(options) > 0)
    character_repo.apply_multiclass_proficiency_choices(c.id, "Ladro", [options[0]])
    conn = get_connection()
    saved = {r["name"] for r in conn.execute(
        "SELECT name FROM character_proficiencies WHERE character_id=? AND proficiency_type='skill'",
        (c.id,)).fetchall()}
    conn.close()
    check("scelta abilità multiclasse salvata", options[0] in saved)


def test_risorse_multiclasse():
    print("\n[4] Risorse di classe multiclasse (no cancellazione a vicenda)")

    c = _make_character("Risorse", "Barbaro", 5, forza=16, costituzione=14)
    furia = {r.name: r.max_value for r in character_repo.get_class_resources(c.id)}
    check("Barbaro Lv5: Furia=3", furia.get("Furia") == 3)

    character_repo.add_character_class(c.id, "Monaco", level=3)
    character_repo.sync_character_total_level(c.id)
    character_repo.init_class_resources(c.id, "Monaco", 3, c)

    resources = {r.name: r.max_value for r in character_repo.get_class_resources(c.id)}
    check("dopo Monaco: Furia ANCORA presente (non cancellata)", "Furia" in resources)
    check("dopo Monaco: Punti Ki presenti", resources.get("Punti Ki") == 3)

    # Level-up SOLO Barbaro: Ki non deve sparire né azzerarsi.
    barbaro_row = next(cc for cc in character_repo.get_character_classes(c.id)
                        if cc.class_name == "Barbaro")
    character_repo.set_character_class_level(barbaro_row.id, 6)
    character_repo.sync_character_total_level(c.id)
    character_repo.init_class_resources(c.id, "Barbaro", 6, c)
    resources = {r.name: r.max_value for r in character_repo.get_class_resources(c.id)}
    check("Barbaro Lv6: Furia sale a 4", resources.get("Furia") == 4)
    check("Punti Ki invariati dopo level-up del SOLO Barbaro", resources.get("Punti Ki") == 3)

    total_level = get_connection()
    lv = total_level.execute("SELECT level FROM characters WHERE id=?", (c.id,)).fetchone()[0]
    total_level.close()
    check("livello totale = 6 (Barbaro) + 3 (Monaco) = 9", lv == 9)


def test_slot_incantesimo_multiclasse():
    print("\n[5] Slot incantesimo multiclasse — esempio letterale PHB IT p.164 (Ranger 4/Mago 3)")

    c = _make_character("Caster", "Ranger", 4, saggezza=14, intelligenza=8)
    character_repo.auto_init_spell_slots(c.id, "Ranger", 4)
    character_repo.add_character_class(c.id, "Mago", level=3)
    character_repo.sync_character_total_level(c.id)
    character_repo.sync_multiclass_spell_slots(c.id)

    slots = {s.slot_level: s.total for s in character_repo.get_spell_slots(c.id)}
    expected = {1: 4, 2: 3, 3: 2, 4: 0, 5: 0, 6: 0, 7: 0, 8: 0, 9: 0}
    check("Ranger4(half→2)+Mago3(full→3)=liv.5 incantatore → [4,3,2,0,...] (PHB, esempio testuale)",
          slots == expected)

    # Coerenza interna: get_multiclass_spell_slot_table() è identica a
    # full_caster (confermato in questa sessione leggendo il PDF, non
    # solo per coincidenza numerica).
    check("tabella multiclasse == tabella full_caster",
          game_data.get_multiclass_spell_slot_table() == game_data.get_spell_slot_table("full"))

    # Warlock combinato con un altro incantatore: limite noto e
    # documentato — il pool condiviso resta corretto per le classi non-Patto,
    # non deve sollevare eccezioni.
    c2 = _make_character("PattoMisto", "Warlock", 3, carisma=16)
    character_repo.add_character_class(c2.id, "Chierico", level=2)
    character_repo.sync_character_total_level(c2.id)
    ok = character_repo.sync_multiclass_spell_slots(c2.id)
    check("Warlock+Chierico: sync non solleva eccezioni, ritorna True", ok is True)
    slots2 = {s.slot_level: s.total for s in character_repo.get_spell_slots(c2.id)}
    check("Warlock+Chierico: pool condiviso riflette SOLO Chierico (full, lv2 → [3,0,...])",
          slots2[1] == 3 and slots2[2] == 0)


def test_sicurezza_level_up_esistente():
    print("\n[6] Sicurezza: level-up della classe primaria non deve corrompere il totale")

    c = _make_character("Multi", "Guerriero", 3, forza=16, destrezza=14)
    character_repo.add_character_class(c.id, "Ladro", level=1)
    total = character_repo.sync_character_total_level(c.id)
    check("totale iniziale Guerriero3/Ladro1 = 4", total == 4)

    # Simula esattamente la sequenza che _on_level_up_click esegue quando
    # sale la classe PRIMARIA (Guerriero 3 → 4): la stessa identica
    # sequenza di chiamate aggiunta in questa sessione.
    primary = character_repo.get_primary_character_class(c.id)
    check("classe primaria correttamente identificata come Guerriero", primary.class_name == "Guerriero")
    new_level = primary.level + 1  # 4
    character_repo.set_character_class_level(primary.id, new_level)
    is_multiclass = len(character_repo.get_character_classes(c.id)) > 1
    new_total = character_repo.sync_character_total_level(c.id)

    check("classe primaria ora a Lv4", new_level == 4)
    check("è ancora multiclasse", is_multiclass)
    check("totale corretto DOPO il level-up della primaria = 5 (4+1), non 4",
          new_total == 5)

    classes = {cc.class_name: cc.level for cc in character_repo.get_character_classes(c.id)}
    check("Ladro non toccato dal level-up del Guerriero", classes.get("Ladro") == 1)
    check("Guerriero aggiornato a 4", classes.get("Guerriero") == 4)
    check("display string coerente", character_repo.get_class_display_string(c.id) == "Guerriero 4 / Ladro 1")


def main() -> int:
    print("=" * 66)
    print("Multiclasse — schema/repository layer (PHB IT cap.6, p.163-165)")
    print(f"HOME di test: {_TMP_HOME}")
    print("=" * 66)
    init_db()
    test_migrazione()
    test_prerequisiti()
    test_competenze()
    test_risorse_multiclasse()
    test_slot_incantesimo_multiclasse()
    test_sicurezza_level_up_esistente()
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
