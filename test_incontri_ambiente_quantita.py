"""
Verifica della feature "Quantità" nel Generatore Incontri per Ambiente
(`ui/views/master/master_forest_encounters_dialog.py`) — bug report Davide
dopo aver visto la proposta di miglioria alla Sezione Ambiente: "magari che
tira i dadi e poi permette di creare l'incontro descritto nella sezione
incontri, in modo da facilitare il master... permettiamo anche di inserire
il risultato al master, non costringiamolo al tiro automatico".

Prima di questo fix, "Aggiungi Incontro" creava sempre UNA copia di ciascuna
creatura risolta nel bestiario, qualunque fosse la quantità scritta in prosa
nella riga tirata (es. "2d4 gnoll") — il Master doveva leggere il testo e
aggiungere le copie in più a mano con "+ Aggiungi mostro".

[1] `_suggest_quantities()` — funzione pura, nessun Flet: abbina in ordine
    di lettura un'espressione di quantità del testo a ciascuna creatura,
    sulle righe REALI di `forest_encounters.json` (non inventate), compreso
    il caso "nessun abbinamento sicuro" (conteggio non coincidente).

[2] Flusso UI end-to-end: tira la riga 3 di Foresta Silvana ("1 gnoll
    signore del branco e 2d4 gnoll", 2 creature) con `random.randint`
    seminato deterministicamente, verifica che il campo Quantità sia
    precompilato correttamente per ciascuna creatura e che il pulsante 🎲
    compaia SOLO dove c'è un vero dado da tirare; tira il dado di quantità
    per la seconda creatura; sovrascrive A MANO la quantità della prima
    creatura (il Master non è mai costretto al tiro automatico); conferma
    "Aggiungi Incontro" e verifica che l'incontro creato abbia esattamente
    le quantità indicate nei campi al momento della conferma, con la
    numerazione "Nome 1"/"Nome 2" già in uso altrove per qty>1.

Usa SEMPRE un DB temporaneo isolato (tempfile.mkdtemp() + HOME separato): il
DB reale di Davide non viene mai toccato.

Eseguire con:
    PYTHONPATH=".venv/lib/python3.13/site-packages:." python3 test_incontri_ambiente_quantita.py
"""

from __future__ import annotations

import os
import tempfile
from typing import Any
from unittest.mock import patch

_TMP_HOME = tempfile.mkdtemp(prefix="dnd_incontri_ambiente_")
os.environ["HOME"] = _TMP_HOME

import flet as ft  # noqa: E402

from data.database import init_db  # noqa: E402
from data.game_data.game_data_loader import game_data  # noqa: E402
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
    def __init__(self) -> None:
        self.dialogs: list = []

    def show_dialog(self, dlg) -> None:
        self.dialogs.append(dlg)

    def pop_dialog(self, *_a) -> None:
        if self.dialogs:
            self.dialogs.pop()

    def update(self, *_a, **_k) -> None:
        pass


def _walk(control, kind) -> list:
    """Raccoglie ricorsivamente tutti i controlli di tipo `kind` sotto
    `control` — stesso pattern di `_texts()`/`_find()` già in uso negli
    altri file di test del progetto."""
    out: list = []
    if control is None:
        return out
    if isinstance(control, kind):
        out.append(control)
    for attr in ("controls", "actions"):
        kids = getattr(control, attr, None)
        if isinstance(kids, (list, tuple)):
            for k in kids:
                out.extend(_walk(k, kind))
    content = getattr(control, "content", None)
    if content is not None and not isinstance(content, str):
        out.extend(_walk(content, kind))
    return out


def _find_button_by_text(control, text_substr: str):
    for cls in (ft.ElevatedButton, ft.OutlinedButton, ft.TextButton):
        for b in _walk(control, cls):
            label = b.content if isinstance(b.content, str) else getattr(b, "text", None)
            if label and text_substr in str(label):
                return b
    return None


def test_suggest_quantities_su_dati_reali() -> None:
    print("\n[1] _suggest_quantities() — abbinamento quantità/creatura su righe reali della DMG")
    from ui.views.master.master_forest_encounters_dialog import _suggest_quantities

    table = game_data.get_environment_table("foresta_silvana")
    entries = {e["roll"]: e for e in table["entries"]}

    r3 = entries[3]
    check("roll 3 (\"1 gnoll signore del branco e 2d4 gnoll\") -> ['1','2d4']",
          _suggest_quantities(r3["text"], r3["creatures"]) == ["1", "2d4"])

    r4 = entries[4]
    check("roll 4 (\"1d4 gnoll and 2d4 iene\") -> ['1d4','2d4']",
          _suggest_quantities(r4["text"], r4["creatures"]) == ["1d4", "2d4"])

    r8 = entries[8]
    check("roll 8 (\"1 driade (50%) o 1d4 satiri (50%)\") -> ['1','1d4'] (le percentuali non contano)",
          _suggest_quantities(r8["text"], r8["creatures"]) == ["1", "1d4"])

    r13 = entries[13]
    check("roll 13 (\"1d4 alci (75%) o 1 alce gigante (25%)\") -> ['1d4','1']",
          _suggest_quantities(r13["text"], r13["creatures"]) == ["1d4", "1"])

    r2 = entries[2]
    check("roll 2, una sola creatura, nessun dado -> ['1']",
          _suggest_quantities(r2["text"], r2["creatures"]) == ["1"])

    check("conteggio non coincidente -> nessun suggerimento (mai un abbinamento incerto)",
          _suggest_quantities("testo con 3 numeri: 1, 2, 3", ["Solo una creatura"]) == [""])
    check("nessuna creatura -> lista vuota", _suggest_quantities("qualunque testo", []) == [])


def test_flusso_ui_quantita_end_to_end() -> None:
    print("\n[2] Flusso UI — quantità precompilata, tiro dado, override manuale, «Aggiungi Incontro»")
    from ui.views.master.master_forest_encounters_dialog import show_forest_encounters_dialog

    page = _FakePage()
    with patch("random.randint", side_effect=[1, 2]):  # d12=1, d8=2 -> roll=3
        show_forest_encounters_dialog(page, world_id="")
        dlg = page.dialogs[-1]
        roll_btn = _find_button_by_text(dlg.content, "Tira 1d12+1d8")
        check("il pulsante «Tira 1d12+1d8» esiste", roll_btn is not None)
        roll_btn.on_click(None)

    texts = [t.value for t in _walk(dlg.content, ft.Text) if isinstance(t.value, str)]
    check("il tiro mostrato è 3 (d12=1+d8=2)", any("Tiro: 3" in t for t in texts))
    check("il testo della riga (Gnoll Signore del Branco) compare",
          any("gnoll signore del branco" in t.lower() for t in texts))

    qty_fields = _walk(dlg.content, ft.TextField)
    qty_fields = [tf for tf in qty_fields if tf.label == "Quantità"]
    check("due campi Quantità (una per creatura risolta)", len(qty_fields) == 2)
    if len(qty_fields) == 2:
        check("prima creatura (\"1 gnoll signore del branco\") -> quantità precompilata a 1",
              qty_fields[0].value == "1")
        check("seconda creatura (\"2d4 gnoll\") -> default 1 finché non si tira il dado",
              qty_fields[1].value == "1")

    dice_btns = [b for b in _walk(dlg.content, ft.IconButton) if b.icon == ft.Icons.CASINO]
    check("un solo pulsante 🎲 (solo la creatura con un vero dado, non quella con quantità fissa '1')",
          len(dice_btns) == 1)
    if dice_btns:
        check("il tooltip indica la formula corretta (2d4)", "2d4" in (dice_btns[0].tooltip or ""))
        with patch("random.randint", side_effect=[1, 2, 3, 4]):  # 2d4 -> 1+2+3... in realtà 2 tiri
            dice_btns[0].on_click(None)
        check("dopo il tiro la quantità della seconda creatura è un numero valido (2d4 -> 2..8)",
              qty_fields[1].value.isdigit() and 2 <= int(qty_fields[1].value) <= 8)

    # Il Master non è mai costretto al tiro automatico: sovrascrive a mano
    # la quantità della PRIMA creatura (quella senza dado, fissa a "1" nel
    # testo — qui il Master decide comunque di metterne 2 sul tavolo).
    if len(qty_fields) == 2:
        qty_fields[0].value = "2"
        qty_fields[1].value = "3"  # override manuale anche su quella con dado

    add_btn = _find_button_by_text(dlg.content, "Aggiungi Incontro")
    check("il pulsante «Aggiungi Incontro» esiste", add_btn is not None)
    add_btn.on_click(None)

    encounters = master_repo.get_encounters(world_id="")
    enc = next((e for e in encounters if "Foresta" in e.name or "Incontro" in e.name), None)
    check("un nuovo incontro è stato creato", enc is not None)
    if enc is not None:
        members = master_repo.get_encounter_members(enc.id)
        names = sorted(m.display_name for m in members)
        # I nomi arrivano dalla riga del bestiario risolta (`m.get("name")`,
        # come già faceva "Vedi scheda" prima di questo fix), non dal testo
        # della tabella — `monsters.json` usa il MAIUSCOLO da manuale.
        check("BUG FIX: le quantità scritte nei campi al momento della conferma sono state rispettate "
              "(2 'Gnoll Signore del Branco' + 3 'Gnoll', non più 1 copia ciascuna)",
              names == ["GNOLL 1", "GNOLL 2", "GNOLL 3",
                        "GNOLL SIGNORE DEL BRANCO 1", "GNOLL SIGNORE DEL BRANCO 2"])


if __name__ == "__main__":
    init_db()
    test_suggest_quantities_su_dati_reali()
    test_flusso_ui_quantita_end_to_end()

    print("\n" + "=" * 70)
    print(f"Controlli passati: {_PASS} — falliti: {len(_FAIL)}")
    if _FAIL:
        print("\nControlli falliti:")
        for label in _FAIL:
            print(f"  - {label}")
        raise SystemExit(1)
    print("Tutti i controlli passati.")
