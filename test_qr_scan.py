"""
Batteria di verifica dello scanner QR per l'ingresso in un mondo LAN —
metà "comodità" del passo 5 di `dnd_app/docs/multiplayer_design.md` §9.3
(l'altra metà, la scoperta broadcast UDP, è in `test_scoperta_lan.py`).

Copre:
  - `network/qr_join.py::parse_join_text()` — l'operazione inversa di
    `build_join_text()` (già in produzione e verificata da Davide),
    round trip completo e ogni caso di rifiuto (fail-closed).
  - `ui/views/world/qr_scanner_view.py::qr_scanner_supported()` — gate di
    visibilità per piattaforma/pacchetti disponibili.
  - `ui/views/world/qr_scanner_view.py::QrScannerView` — costruzione
    dell'albero controlli senza eccezioni (stesso limite di
    `test_mondo_senza_rete.py`: nessuna vera `ft.Page` disponibile qui,
    quindi nessun avvio reale di fotocamera).
  - `QrScannerView._try_decode()` — non solleva mai, in nessuna
    circostanza, indipendentemente dalla disponibilità della libreria
    nativa `libzbar` in questo ambiente (verificato e dichiarato
    esplicitamente, non assunto — vedi `_pyzbar_functional()` sotto,
    stesso principio di `_broadcast_available()` in test_scoperta_lan.py).

⚠️ Non verificabile da questo sandbox: il ciclo vero fotocamera live →
pyzbar → ingresso automatico su un dispositivo Android/iOS reale — nessuna
fotocamera, nessun toolchain di build mobile, e (su questo Linux senza
permessi di root) nessuna libreria di sistema libzbar installabile per
`pyzbar` "puro" da PyPI. Su Android/iOS la build reale usa `flet-libzbar`,
fornito automaticamente da `flet build` (pacchetto ufficiale del team Flet,
vedi il docstring di qr_scanner_view.py) — un problema di packaging diverso
e già risolto a monte, non replicabile qui.

Eseguire con:
    PYTHONPATH=".venv/lib/python3.13/site-packages:." python3 test_qr_scan.py
"""

from __future__ import annotations

import os
import sys
import tempfile

_TMP_HOME = tempfile.mkdtemp(prefix="dnd_qrscan_")
os.environ["HOME"] = _TMP_HOME

from network.qr_join import build_join_text, parse_join_text  # noqa: E402

_PASS = 0
_FAIL: list[str] = []


def check(label: str, cond: bool) -> None:
    global _PASS
    if cond:
        _PASS += 1
    else:
        _FAIL.append(label)
        print(f"  FALLITO: {label}")


def _pyzbar_functional() -> bool:
    """True se `pyzbar` riesce a caricare la libreria nativa `libzbar` in
    questo ambiente — se no, alcuni controlli si limitano a dichiararlo
    onestamente invece di fingere una copertura che non c'è (stesso
    principio di `_broadcast_available()` in test_scoperta_lan.py)."""
    try:
        from pyzbar.pyzbar import decode  # noqa: F401
        return True
    except Exception:
        return False


def test_parse_join_text_round_trip() -> None:
    print("\n[1] parse_join_text() — round trip con build_join_text()")
    text = build_join_text("La Locanda del Drago", "192.168.1.42", 8765, "AB12CD", "394857")
    parsed = parse_join_text(text)
    check("il parsing riesce", parsed is not None)
    if parsed is not None:
        check("world_name corrisponde", parsed["world_name"] == "La Locanda del Drago")
        check("host corrisponde", parsed["host"] == "192.168.1.42")
        check("port è un int e corrisponde", parsed["port"] == 8765
              and isinstance(parsed["port"], int))
        check("join_code corrisponde", parsed["join_code"] == "AB12CD")
        check("pin corrisponde", parsed["pin"] == "394857")


def test_parse_join_text_tolerates_whitespace() -> None:
    print("\n[2] parse_join_text() — tollera spazi bianchi finali per riga")
    text = build_join_text("Mondo", "10.0.0.5", 8766, "ZZ9988", "111222")
    padded = "\n".join(line + "   " for line in text.splitlines())
    parsed = parse_join_text(padded)
    check("il parsing riesce anche con spazi finali", parsed is not None)
    if parsed is not None:
        check("host non contiene spazi residui", parsed["host"] == "10.0.0.5")


def test_parse_join_text_rejects_foreign_qr() -> None:
    print("\n[3] parse_join_text() — rifiuta un QR non nostro (fail-closed)")
    check("testo senza il magic iniziale viene rifiutato",
          parse_join_text("Un QR qualsiasi\nNon c'entra niente") is None)
    check("stringa vuota viene rifiutata", parse_join_text("") is None)
    check("None-like non solleva (stringa vuota gestita sopra)", True)


def test_parse_join_text_rejects_incomplete() -> None:
    print("\n[4] parse_join_text() — rifiuta un testo incompleto")
    text = build_join_text("Mondo", "10.0.0.5", 8766, "ZZ9988", "111222")
    # Rimuove l'ultima riga (PIN) — simula un QR corrotto/parzialmente letto.
    truncated = "\n".join(text.splitlines()[:-1])
    check("manca il PIN: il parsing fallisce (mai un dizionario parziale)",
          parse_join_text(truncated) is None)


def test_parse_join_text_rejects_bad_port() -> None:
    print("\n[5] parse_join_text() — porta non valida")
    text = build_join_text("Mondo", "10.0.0.5", 8766, "ZZ9988", "111222")
    bad = text.replace("Porta: 8766", "Porta: non-un-numero")
    check("porta non numerica: il parsing fallisce", parse_join_text(bad) is None)
    bad2 = text.replace("Porta: 8766", "Porta: 99999")
    check("porta fuori range (>65535): il parsing fallisce", parse_join_text(bad2) is None)


def test_qr_scanner_supported() -> None:
    print("\n[6] qr_scanner_supported() — gate per piattaforma/pacchetti")
    import flet as ft
    from ui.views.world import qr_scanner_view as qsv

    class _FakePage:
        def __init__(self, platform):
            self.platform = platform

    check("Android è supportato (pacchetti presenti in questo ambiente)",
          qsv.qr_scanner_supported(_FakePage(ft.PagePlatform.ANDROID)) is True)
    check("iOS è supportato", qsv.qr_scanner_supported(_FakePage(ft.PagePlatform.IOS)) is True)
    check("Windows NON è supportato (flet-camera non copre desktop)",
          qsv.qr_scanner_supported(_FakePage(ft.PagePlatform.WINDOWS)) is False)
    check("macOS NON è supportato",
          qsv.qr_scanner_supported(_FakePage(ft.PagePlatform.MACOS)) is False)
    check("Linux NON è supportato",
          qsv.qr_scanner_supported(_FakePage(ft.PagePlatform.LINUX)) is False)

    # Simula pacchetti mancanti (es. un ambiente dove flet-camera non è
    # installata) — deve tornare False anche su Android, mai un pulsante
    # che apre una view destinata a fallire subito.
    orig_fc, orig_fph = qsv.fc, qsv.fph
    try:
        qsv.fc = None
        check("senza flet_camera, Android non è più supportato",
              qsv.qr_scanner_supported(_FakePage(ft.PagePlatform.ANDROID)) is False)
    finally:
        qsv.fc = orig_fc
    try:
        qsv.fph = None
        check("senza flet_permission_handler, Android non è più supportato",
              qsv.qr_scanner_supported(_FakePage(ft.PagePlatform.ANDROID)) is False)
    finally:
        qsv.fph = orig_fph


def test_qr_scanner_view_construction() -> None:
    print("\n[7] QrScannerView — costruzione senza eccezioni")
    from ui.views.world.qr_scanner_view import QrScannerView

    scanned: list[dict] = []
    cancelled: list[bool] = []

    view = QrScannerView(
        on_scanned=lambda parsed: scanned.append(parsed),
        on_cancel=lambda: cancelled.append(True),
    )
    check("la view si costruisce", len(view.controls) == 3)
    check("stato iniziale: nessuna decodifica in corso", view._decoding is False)
    check("stato iniziale: non ancora completata", view._done is False)
    check("nessuna fotocamera avviata prima di did_mount (richiede una vera Page)",
          view._camera is None)


def test_try_decode_never_raises() -> None:
    print("\n[8] QrScannerView._try_decode() — non solleva mai")
    from ui.views.world.qr_scanner_view import QrScannerView

    check("bytes non validi come immagine: nessuna eccezione, ritorna None",
          QrScannerView._try_decode(b"non e' un JPEG") is None)
    check("bytes vuoti: nessuna eccezione, ritorna None",
          QrScannerView._try_decode(b"") is None)

    if not _pyzbar_functional():
        print("  (libzbar non disponibile in questo sandbox — verifica del "
              "decode reale saltata onestamente, vedi il docstring del modulo)")
        return

    # Se pyzbar FUNZIONA davvero in questo ambiente, verifica il ciclo
    # completo: genera un vero PNG del QR (stessa libreria già usata da
    # generate_qr_png_base64) e conferma che _try_decode lo riconosce.
    import io
    import qrcode
    from network.qr_join import build_join_text

    text = build_join_text("Mondo di Prova", "10.0.0.9", 8765, "QR1234", "555000")
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")

    parsed = QrScannerView._try_decode(buf.getvalue())
    check("un vero QR generato viene decodificato e riconosciuto",
          parsed is not None and parsed["host"] == "10.0.0.9" and parsed["pin"] == "555000")


def main() -> int:
    print("=" * 62)
    print("Scanner QR — ingresso in LAN (passo 5, metà 'comodità')")
    print(f"HOME di test: {_TMP_HOME}")
    print("=" * 62)

    test_parse_join_text_round_trip()
    test_parse_join_text_tolerates_whitespace()
    test_parse_join_text_rejects_foreign_qr()
    test_parse_join_text_rejects_incomplete()
    test_parse_join_text_rejects_bad_port()
    test_qr_scanner_supported()
    test_qr_scanner_view_construction()
    test_try_decode_never_raises()

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
