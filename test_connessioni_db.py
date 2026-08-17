"""
Guardia permanente sulle connessioni SQLite (2026-08-17).

Nasce dalla causa radice del bug del round 5 del Multiplayer (vedi
`docs/changelog_storico.md`, "round 5 — CHIUSO"): il pattern dominante di
questo progetto era `conn.close()` come ULTIMA RIGA del blocco `try`, non in
un `finally`. Se una query solleva, quella connessione non viene mai chiusa —
e nemmeno liberata dal refcount, perché l'eccezione crea un ciclo di
riferimenti (eccezione → traceback → frame → variabile locale `conn`) che
solo il garbage collector generazionale può rompere. Nel frattempo la
connessione orfana trattiene la transazione di scrittura fallita, e con essa
il lock del file: **ogni scrittura successiva del processo** falliva con
"database is locked" fino al riavvio dell'app.

Erano **167 `close()` in 165 funzioni**, tutte convertite a `try/finally`
nella stessa sessione. Questo file esiste per impedire che il pattern
ricompaia: è un test **statico** (analisi AST di tutto il codebase), non un
test di comportamento, quindi non ha bisogno di eseguire quel codice per
coprirlo tutto — è l'unico modo pratico di tenere l'invariante su 165
funzioni sparse in 9 moduli.

Tre parti:

[1] Invariante statica — nessuna funzione del progetto apre
    `get_connection()` senza garantire la chiusura su TUTTI i percorsi
    (`try/finally` o `with`). Se questo test fallisce, il messaggio elenca
    esattamente le funzioni da correggere.

[2] Nessun `conn.close()` è rimasto come ultima riga di un `try` — la forma
    precisa che ha causato il bug, cercata a parte perché è quella che un
    copia-incolla da codice vecchio reintrodurrebbe.

[3] Comportamento reale — una funzione di repository che fallisce a metà
    scrittura NON lascia il database bloccato. Verificato con una
    connessione `sqlite3` GREZZA (non `get_connection()`), così da provare
    che il lock è davvero rilasciato dal `finally` e non solo mascherato
    dalla rete di sicurezza `_ResilientConnection`.

Eseguire con:
    PYTHONPATH=".venv/lib/python3.13/site-packages:." python3 test_connessioni_db.py
"""

from __future__ import annotations

import ast
import os
import pathlib
import sqlite3
import sys
import tempfile
import uuid

_TMP_HOME = tempfile.mkdtemp(prefix="dnd_connessioni_db_")
os.environ["HOME"] = _TMP_HOME

from data.database import get_db_path, init_db  # noqa: E402
from data.repositories import master_repo  # noqa: E402

_PASS = 0
_FAIL: list[str] = []

#: La factory DEVE restituire una connessione aperta: è l'unico punto del
#: progetto in cui non chiuderla è corretto.
_ALLOWLIST = {
    ("data/database.py", "get_connection"),
    ("data/database.py", "_open_connection"),
}

_ROOT = pathlib.Path(__file__).resolve().parent
_SKIP_DIRS = (".venv", "build", "__pycache__", "storage", "docs")


def check(label: str, cond: bool) -> None:
    global _PASS
    if cond:
        _PASS += 1
    else:
        _FAIL.append(label)
        print(f"  FALLITO: {label}")


def _project_files() -> list[pathlib.Path]:
    return [
        f for f in sorted(_ROOT.rglob("*.py"))
        if not any(p in f.parts for p in _SKIP_DIRS)
        and not f.name.startswith("test_")
    ]


def _guarantees_close(fn: ast.AST, src: str) -> bool:
    """La chiusura è garantita se un `finally` la contiene, oppure se la
    connessione è gestita da un `with` (che chiuderebbe da sé)."""
    for sub in ast.walk(fn):
        if isinstance(sub, ast.Try) and sub.finalbody:
            fin = "\n".join(ast.get_source_segment(src, s) or "" for s in sub.finalbody)
            if ".close()" in fin:
                return True
        if isinstance(sub, (ast.With, ast.AsyncWith)):
            if "get_connection()" in (ast.get_source_segment(src, sub) or ""):
                return True
    return False


# ---------------------------------------------------------------------------
# [1] Invariante statica su tutto il codebase
# ---------------------------------------------------------------------------

def test_ogni_connessione_ha_chiusura_garantita():
    print("\n[1] Ogni funzione che apre get_connection() garantisce conn.close()")
    offenders: list[str] = []
    n_funzioni = 0

    for path in _project_files():
        src = path.read_text(encoding="utf-8")
        if "get_connection" not in src:
            continue
        rel = str(path.relative_to(_ROOT))
        for fn in ast.walk(ast.parse(src)):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            seg = ast.get_source_segment(src, fn) or ""
            if "get_connection()" not in seg:
                continue
            if (rel, fn.name) in _ALLOWLIST:
                continue
            n_funzioni += 1
            if not _guarantees_close(fn, src):
                offenders.append(f"{rel}:{fn.lineno} {fn.name}()")

    check(f"almeno 100 funzioni analizzate (lo scan trova davvero il codice) — {n_funzioni}",
          n_funzioni >= 100)
    if offenders:
        print(f"  {len(offenders)} funzioni chiudono la connessione solo sul percorso "
              f"felice — spostare conn.close() in un finally:")
        for o in offenders:
            print(f"    - {o}")
    check(f"nessuna connessione senza chiusura garantita (trovate {len(offenders)})",
          not offenders)


# ---------------------------------------------------------------------------
# [2] La forma esatta che ha causato il bug non esiste più
# ---------------------------------------------------------------------------

def test_nessun_close_come_ultima_riga_del_try():
    print("\n[2] Ogni try che apre una connessione la chiude in un finally")
    offenders: list[str] = []
    n_try = 0

    for path in _project_files():
        src = path.read_text(encoding="utf-8")
        if "get_connection" not in src:
            continue
        rel = str(path.relative_to(_ROOT))
        for node in ast.walk(ast.parse(src)):
            if not isinstance(node, ast.Try):
                continue
            body = "\n".join(ast.get_source_segment(src, s) or "" for s in node.body)
            if "get_connection()" not in body:
                continue
            n_try += 1
            # Granularità per-`try`, non per-funzione come in [1]: intercetta
            # anche una funzione che apre DUE connessioni in due try distinti
            # e ne protegge solo uno. `_guarantees_close` sul nodo `try`
            # accetta sia il `finally` proprio sia quello di un try annidato
            # che avvolge l'uso della connessione — il pattern
            # `try: conn = ...; try: ... finally: conn.close()` di
            # `character_export.py`/`settings_repo.py` è già corretto e non
            # va segnalato.
            if not _guarantees_close(node, src):
                offenders.append(f"{rel}:{node.lineno}")

    check(f"almeno 100 try analizzati — {n_try}", n_try >= 100)
    if offenders:
        print("  try che aprono la connessione senza chiuderla in un finally:")
        for o in offenders:
            print(f"    - {o}")
    check(f"ogni try che apre una connessione la chiude in un finally "
          f"(non conformi: {len(offenders)})", not offenders)


# ---------------------------------------------------------------------------
# [3] Comportamento reale: un errore non lascia il DB bloccato
# ---------------------------------------------------------------------------

def _scrittura_con_connessione_grezza() -> tuple[bool, str]:
    """Prova a scrivere con una connessione `sqlite3` GREZZA — deliberatamente
    NON `get_connection()`, che avrebbe la rete di sicurezza
    `_ResilientConnection` (gc.collect() + un ritentativo) e potrebbe quindi
    mascherare un lock ancora trattenuto. `timeout=0` fa fallire subito
    invece di attendere."""
    raw = sqlite3.connect(get_db_path(), timeout=0)
    try:
        raw.execute(
            "INSERT INTO master_campaign_notes (id, category, name) VALUES (?, ?, ?)",
            (str(uuid.uuid4()), "npc", "Scrittura di controllo"),
        )
        raw.commit()
        return True, ""
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"
    finally:
        raw.close()


def test_errore_di_scrittura_non_blocca_il_database():
    print("\n[3] Una scrittura fallita in un repository non lascia il DB bloccato")

    ok, err = _scrittura_con_connessione_grezza()
    check(f"il database è scrivibile prima del test ({err})", ok)

    # Fallimento REALE dentro una funzione di repository: `linked_npc_id`
    # punta a un NPC inesistente, quindi la FK verso `master_npcs(id)` salta
    # e `conn.execute()` solleva a metà funzione — esattamente il percorso
    # che prima abbandonava la connessione col lock in mano.
    creata = master_repo.create_master_campaign_note(
        category="npc", name="Nota con FK rotta", world_id="w-test",
        linked_npc_id="npc-che-non-esiste",
    )
    check("la nota con FK invalida non viene creata (l'errore avviene davvero)",
          creata is None)

    ok, err = _scrittura_con_connessione_grezza()
    check(f"subito dopo, il database è ancora scrivibile con una connessione grezza — "
          f"il finally ha rilasciato il lock, non la rete di sicurezza ({err})", ok)

    # Ripetuto: nemmeno una raffica di errori accumula lock.
    for _ in range(20):
        master_repo.create_master_campaign_note(
            category="npc", name="Ancora rotta", world_id="w-test",
            linked_npc_id="npc-che-non-esiste",
        )
    ok, err = _scrittura_con_connessione_grezza()
    check(f"dopo 20 errori consecutivi il database è ancora scrivibile ({err})", ok)


def main() -> int:
    init_db()
    test_ogni_connessione_ha_chiusura_garantita()
    test_nessun_close_come_ultima_riga_del_try()
    test_errore_di_scrittura_non_blocca_il_database()
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
