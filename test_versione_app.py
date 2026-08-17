"""
Coerenza della versione dell'app e formula del versionCode Android (2026-08-17).

Nasce da tre problemi reali trovati indagando la richiesta di Davide
"aggiornamento automatico senza dover disinstallare e reinstallare l'app":

[1] `version.py` diceva `0.1.15` mentre l'ultimo tag git era `v0.2.15` — stale
    di un'intera minor. Non produceva un bug in release (la CI riscrive il file
    dal tag), ma l'esecuzione da sorgente dichiarava una versione più bassa di
    quella reale, quindi il controllo aggiornamenti annunciava un aggiornamento
    verso una versione già in esecuzione. Questo test asserisce che
    `version.APP_VERSION` e `pyproject.toml [project].version` coincidano, così
    un bump manuale non può più divergere in silenzio.

[2] `config/settings.py` conteneva un secondo `APP_VERSION = "0.1.0"` che
    nessuno importava. Non era inerte: `ui/app.py` fa
    `from config.settings import *`. Rimosso; questo test impedisce che
    ricompaia.

[3] `pyproject.toml` aveva `build_number = 1` HARDCODED e la CI non lo iniettava
    mai (riscriveva invece una chiave `app.version` che non esiste più dal
    2026-08-07 — una sostituzione a vuoto, silenziosa). Ogni APK mai rilasciato
    porta quindi versionCode 1. La formula ora vive in
    `version.compute_build_number()` invece che dentro il YAML della CI, proprio
    per poter essere coperta qui.

Eseguire con:
    PYTHONPATH=".venv/lib/python3.13/site-packages:." python3 test_versione_app.py
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys
import tomllib

import version
from core import update_checker

_PASS = 0
_FAIL: list[str] = []

_ROOT = pathlib.Path(__file__).resolve().parent


def check(label: str, cond: bool) -> None:
    global _PASS
    if cond:
        _PASS += 1
    else:
        _FAIL.append(label)
        print(f"  FALLITO: {label}")


def _pyproject() -> dict:
    with open(_ROOT / "pyproject.toml", "rb") as fh:
        return tomllib.load(fh)


# ---------------------------------------------------------------------------
# [1] Fonte di verità unica
# ---------------------------------------------------------------------------

def test_fonte_di_verita_unica() -> None:
    print("\n[1] Una sola versione, in un solo posto")

    data = _pyproject()
    pyproject_version = data["project"]["version"]
    check(
        f"version.APP_VERSION ({version.APP_VERSION}) == "
        f"pyproject [project].version ({pyproject_version})",
        version.APP_VERSION == pyproject_version,
    )

    settings_src = (_ROOT / "config" / "settings.py").read_text(encoding="utf-8")
    # Cerca un'ASSEGNAZIONE, non la parola: il file contiene di proposito un
    # commento che spiega perché la costante è stata rimossa.
    check(
        "config/settings.py non riassegna APP_VERSION (duplicato morto rimosso)",
        re.search(r"^APP_VERSION\s*=", settings_src, flags=re.MULTILINE) is None,
    )

    check(
        "version.FIRST_SIGNED_VERSION è una versione interpretabile",
        version.parse_version(version.FIRST_SIGNED_VERSION) != (0,),
    )


# ---------------------------------------------------------------------------
# [2] parse_version
# ---------------------------------------------------------------------------

def test_parse_version() -> None:
    print("\n[2] parse_version")

    casi = [
        ("1.2.3", (1, 2, 3)),
        ("v1.2.3", (1, 2, 3)),
        ("  v0.2.15 ", (0, 2, 15)),
        ("0.2.16-rc1", (0, 2, 16)),   # tag di prova per la firma di rilascio
        ("0.2.16+build7", (0, 2, 16)),
        ("", (0,)),
        ("non-una-versione", (0,)),
        ("1.2.x", (0,)),
    ]
    for testo, atteso in casi:
        got = version.parse_version(testo)
        check(f"parse_version({testo!r}) == {atteso} (ottenuto {got})", got == atteso)

    check(
        "l'ordinamento è ordinale, non lessicografico: 0.2.15 > 0.1.41",
        version.parse_version("0.2.15") > version.parse_version("0.1.41"),
    )
    check(
        "0.10.0 > 0.9.0 (il confronto fra stringhe direbbe il contrario)",
        version.parse_version("0.10.0") > version.parse_version("0.9.0"),
    )


# ---------------------------------------------------------------------------
# [3] compute_build_number — il versionCode Android
# ---------------------------------------------------------------------------

def test_compute_build_number() -> None:
    print("\n[3] compute_build_number (versionCode Android)")

    casi = [
        ("v0.1.15", 1_015),
        ("v0.1.41", 1_041),
        ("v0.2.15", 2_015),
        ("v0.3.0", 3_000),
        ("v1.0.0", 1_000_000),
        ("0.2.16-rc1", 2_016),
    ]
    for tag, atteso in casi:
        got = version.compute_build_number(tag)
        check(f"compute_build_number({tag!r}) == {atteso} (ottenuto {got})", got == atteso)

    check(
        "un tag malformato dà 0, così la CI si ferma invece di inventare un numero",
        version.compute_build_number("non-un-tag") == 0,
    )

    # Il valore committato in pyproject.toml resta il letterale che la CI
    # riscrive: se qualcuno lo alza a mano, il commento che lo spiega è sbagliato.
    check(
        "pyproject.toml build_number è ancora il segnaposto 1 (lo inietta la CI)",
        _pyproject()["tool"]["flet"]["build_number"] == 1,
    )

    # Monotonia su TUTTI i tag realmente rilasciati.
    #
    # L'ordine di confronto è quello SEMANTICO (per numero di versione), non
    # quello di creazione dei tag: `git tag --sort=creatordate` mostra che
    # `v0.1.10` è stato creato PRIMA di `v0.1.9`, quindi l'ordine di creazione
    # non è monotono nella storia reale di questo repository. È un fatto
    # storico, non un difetto della formula — e riguarda due versioni entrambe
    # precedenti alla firma di rilascio, quindi senza conseguenze pratiche.
    # L'invariante che conta per Android è: a versione più alta corrisponde
    # sempre un versionCode più alto.
    try:
        out = subprocess.run(
            ["git", "tag"],
            cwd=_ROOT, capture_output=True, text=True, timeout=15, check=True,
        ).stdout
    except (subprocess.SubprocessError, OSError, FileNotFoundError):
        print("  (git non disponibile: controllo sui tag reali saltato)")
        return

    tags = [t for t in out.split() if re.fullmatch(r"v\d+\.\d+\.\d+", t)]
    if not tags:
        print("  (nessun tag di versione trovato: controllo saltato)")
        return

    tags.sort(key=version.parse_version)
    numeri = [version.compute_build_number(t) for t in tags]
    check(
        f"il versionCode cresce strettamente con la versione su tutti i "
        f"{len(tags)} tag rilasciati ({tags[0]}→{numeri[0]} … {tags[-1]}→{numeri[-1]})",
        all(b > a for a, b in zip(numeri, numeri[1:])),
    )
    check(
        "nessuna collisione: due tag diversi non producono lo stesso versionCode",
        len(set(numeri)) == len(numeri),
    )
    check(
        "ogni versionCode è > 1, il valore di tutti gli APK già installati",
        all(n > 1 for n in numeri),
    )
    check(
        "il prossimo versionCode supera quello di ogni tag già rilasciato",
        version.compute_build_number(version.FIRST_SIGNED_VERSION) > max(numeri),
    )


# ---------------------------------------------------------------------------
# [4] La guardia sul checkout di sviluppo
# ---------------------------------------------------------------------------

def test_guardia_checkout_di_sviluppo() -> None:
    print("\n[4] Il controllo aggiornamenti è disattivato da sorgente")

    # Questo file gira dal repository, quindi `.git/` c'è: è il caso reale.
    in_checkout = update_checker.is_dev_checkout()
    check("is_dev_checkout() è True eseguendo dal repository", in_checkout)

    if in_checkout:
        # Nessuna rete: la guardia esce prima di qualunque urlopen. Se
        # regredisse, questa chiamata farebbe una richiesta HTTP reale.
        chiamate: list[str] = []
        original = update_checker.urllib.request.urlopen

        def _spia(*args, **kwargs):  # pragma: no cover - non deve mai eseguire
            chiamate.append("urlopen")
            return original(*args, **kwargs)

        update_checker.urllib.request.urlopen = _spia
        try:
            # Dal 2026-08-17 restituisce `(bool, UpdateInfo | None)` invece della
            # vecchia tripla `(bool, str, str)`: la UI ha bisogno anche dell'URL
            # dell'asset e della sua dimensione per la barra di download.
            has_update, info = update_checker.check_for_updates()
        finally:
            update_checker.urllib.request.urlopen = original

        check("check_for_updates() non annuncia aggiornamenti da sorgente", has_update is False)
        check("check_for_updates() non restituisce alcuna UpdateInfo da sorgente",
              info is None)
        check("check_for_updates() non fa alcuna richiesta HTTP da sorgente", not chiamate)


def main() -> int:
    test_fonte_di_verita_unica()
    test_parse_version()
    test_compute_build_number()
    test_guardia_checkout_di_sviluppo()
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
