"""
Batteria di verifica dell'aggiornamento in-app (2026-08-17, richiesta di Davide:
"l'upgrade automatico dell'app con la barra del download e la scritta
aggiornamento completato, senza dover eliminare e reinstallare l'app ogni
volta").

Quattro parti, tutte eseguibili in questo sandbox — niente dispositivo, niente
rete verso GitHub:

[1] `core/update_checker.py`: individuazione dell'asset per piattaforma da una
    risposta reale di `releases/latest`, e la condizione che decide se
    l'aggiornamento attraversa la migrazione della firma (quella che richiede
    UNA disinstallazione manuale). Include il confronto fra i nomi degli asset
    attesi e quelli davvero pubblicati dal workflow della CI: è un contratto fra
    due file diversi, e un refuso significherebbe "nessun download disponibile"
    in silenzio.

[2] `core/update_downloader.py` contro un `http.server` locale su 127.0.0.1:
    download byte-per-byte, avanzamento, `.part` → rinomina atomica,
    verifica della dimensione, annullamento, assenza di `Content-Length`,
    pulizia.

[3] `core/update_state.py`: la tabella dei casi di "Aggiornamento completato",
    che è pura e quindi verificabile per intero.

[4] `data/database.py::get_updates_path()` e la formattazione delle etichette.

Ciò che questa batteria NON può verificare, e che resta a Davide su un
dispositivo reale (vedi RELEASE.md): che l'installer di sistema Android si apra
davvero, che il permesso "installa app sconosciute" si possa concedere, e che
l'APK firmato con la chiave di rilascio si installi sopra quello precedente
senza disinstallare.

Eseguire con:
    PYTHONPATH=".venv/lib/python3.13/site-packages:." python3 test_aggiornamento_app.py
"""

from __future__ import annotations

import http.server
import json
import os
import re
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

_TMP_HOME = tempfile.mkdtemp(prefix="dnd_aggiornamento_")
os.environ["HOME"] = _TMP_HOME

import version  # noqa: E402
from core import update_checker, update_downloader, update_state  # noqa: E402
from data.database import get_updates_path, init_db  # noqa: E402

_PASS = 0
_FAIL: list[str] = []

_ROOT = Path(__file__).resolve().parent


def check(label: str, cond: bool) -> None:
    global _PASS
    if cond:
        _PASS += 1
    else:
        _FAIL.append(label)
        print(f"  FALLITO: {label}")


# ---------------------------------------------------------------------------
# [1] update_checker
# ---------------------------------------------------------------------------

def _finta_risposta(tag: str, assets: list[dict]) -> bytes:
    """Forma reale di `GET /repos/:owner/:repo/releases/latest` — solo i campi
    che questo modulo legge."""
    return json.dumps({
        "tag_name": tag,
        "html_url": f"https://github.com/DavMos9/dnd_app/releases/tag/{tag}",
        "assets": assets,
    }).encode()


class _FintaRisposta:
    def __init__(self, payload: bytes, headers: dict | None = None):
        self._payload = payload
        self.headers = headers or {}

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            dati, self._payload = self._payload, b""
            return dati
        dati, self._payload = self._payload[:size], self._payload[size:]
        return dati

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _con_risposta(payload: bytes, platform_key: str, current_version: str):
    """Esegue `check_for_updates()` con urlopen, piattaforma e versione
    corrente sostituite. Ripristina tutto anche in caso di errore."""
    orig_urlopen = update_checker.urllib.request.urlopen
    orig_platform = update_checker.current_platform_key
    orig_version = update_checker.APP_VERSION
    orig_dev = update_checker.is_dev_checkout

    update_checker.urllib.request.urlopen = lambda *a, **k: _FintaRisposta(payload)
    update_checker.current_platform_key = lambda: platform_key
    update_checker.APP_VERSION = current_version
    # Questa batteria gira DAL repository, quindi `is_dev_checkout()` è True e
    # il controllo esce subito: va neutralizzata, altrimenti si verificherebbe
    # solo la guardia (che ha già il suo test in test_versione_app.py).
    update_checker.is_dev_checkout = lambda: False
    try:
        return update_checker.check_for_updates()
    finally:
        update_checker.urllib.request.urlopen = orig_urlopen
        update_checker.current_platform_key = orig_platform
        update_checker.APP_VERSION = orig_version
        update_checker.is_dev_checkout = orig_dev


def test_update_checker() -> None:
    print("\n[1] update_checker — asset per piattaforma e soglia di reinstallazione")

    assets = [
        {"name": "dnd-companion-android.apk",
         "browser_download_url": "https://esempio/apk", "size": 50_000_000},
        {"name": "dnd-companion-windows.zip",
         "browser_download_url": "https://esempio/win", "size": 40_000_000},
        {"name": "dnd-companion-macos.zip",
         "browser_download_url": "https://esempio/mac", "size": 45_000_000},
        {"name": "dnd-companion-linux.tar.gz",
         "browser_download_url": "https://esempio/linux", "size": 42_000_000},
    ]
    payload = _finta_risposta("v0.2.16", assets)

    attesi = {
        "Android": ("https://esempio/apk", 50_000_000),
        "Windows": ("https://esempio/win", 40_000_000),
        "Darwin": ("https://esempio/mac", 45_000_000),
        "Linux": ("https://esempio/linux", 42_000_000),
    }
    for piattaforma, (url, size) in attesi.items():
        has, info = _con_risposta(payload, piattaforma, "0.2.15")
        check(f"{piattaforma}: aggiornamento rilevato", has and info is not None)
        if info:
            check(f"{piattaforma}: sceglie l'asset giusto ({info.asset_name})",
                  info.asset_url == url)
            check(f"{piattaforma}: legge la dimensione", info.asset_size == size)
            check(f"{piattaforma}: can_download è True", info.can_download)

    # Nessun aggiornamento quando la versione installata è uguale o più recente.
    has, info = _con_risposta(payload, "Android", "0.2.16")
    check("nessun aggiornamento a parità di versione", has is False and info is None)
    has, info = _con_risposta(payload, "Android", "0.3.0")
    check("nessun aggiornamento se l'installata è più recente",
          has is False and info is None)

    # Release senza asset per questa piattaforma: l'aggiornamento va comunque
    # annunciato, ma solo come link — non si può scaricare nulla in-app.
    solo_windows = _finta_risposta("v0.2.16", [assets[1]])
    has, info = _con_risposta(solo_windows, "Android", "0.2.15")
    check("release senza l'asset di questa piattaforma: aggiornamento annunciato",
          has is True and info is not None)
    check("...ma senza possibilità di scaricarlo in-app",
          info is not None and not info.can_download)
    check("...e con il link alla pagina della release",
          info is not None and "releases/tag" in info.release_url)

    # `assets` assente o vuoto: nessun crash.
    has, info = _con_risposta(_finta_risposta("v0.2.16", []), "Android", "0.2.15")
    check("assets vuoto non fa fallire il controllo", has is True and info is not None)
    has, info = _con_risposta(b'{"tag_name": "", "html_url": "x"}', "Android", "0.2.15")
    check("tag_name vuoto → nessun aggiornamento", has is False and info is None)
    has, info = _con_risposta(b"non-json", "Android", "0.2.15")
    check("risposta illeggibile → nessun aggiornamento, nessuna eccezione",
          has is False and info is None)

    # Piattaforma non riconosciuta (es. web): niente asset, ma nessun errore.
    has, info = _con_risposta(payload, "", "0.2.15")
    check("piattaforma non riconosciuta: annuncio sì, download no",
          has is True and info is not None and not info.can_download)

    # -- la soglia della migrazione della firma -------------------------------
    prima = "0.2.15"
    soglia = version.FIRST_SIGNED_VERSION  # "0.3.0"
    check(f"da {prima} a {soglia}: serve la reinstallazione",
          update_checker.crosses_signing_migration(prima, soglia))
    check(f"da {prima} a una versione oltre la soglia: serve la reinstallazione",
          update_checker.crosses_signing_migration(prima, "0.4.2"))
    check(f"da {soglia} in avanti: NON serve più (è il punto di tutto il lavoro)",
          not update_checker.crosses_signing_migration(soglia, "0.3.1"))
    check("fra due versioni entrambe successive alla soglia: non serve",
          not update_checker.crosses_signing_migration("0.4.0", "0.5.0"))
    check("fra due versioni entrambe precedenti alla soglia: non serve",
          not update_checker.crosses_signing_migration("0.2.14", "0.2.15"))

    has, info = _con_risposta(_finta_risposta("v0.3.0", assets), "Android", "0.2.15")
    check("check_for_updates segnala requires_reinstall attraversando la soglia",
          info is not None and info.requires_reinstall is True)
    has, info = _con_risposta(_finta_risposta("v0.3.1", assets), "Android", "0.3.0")
    check("...e non lo segnala per un aggiornamento normale",
          info is not None and info.requires_reinstall is False)


def test_contratto_nomi_asset() -> None:
    print("\n[1b] I nomi degli asset combaciano con quelli pubblicati dalla CI")

    workflow = (_ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    for piattaforma, nome in update_checker.ASSET_NAMES.items():
        # Il workflow deve caricare un file con ESATTAMENTE questo nome.
        check(f"{piattaforma}: la CI pubblica «{nome}»", nome in workflow)

    # E il contrario: ogni artefatto allegato alla release deve essere previsto
    # qui. Se la CI iniziasse a pubblicare un nome diverso, l'app cercherebbe
    # per sempre un asset inesistente senza dirlo a nessuno.
    allegati = set(re.findall(r"artifacts/\w+/(\S+)", workflow))
    check(f"nessun artefatto della CI è ignoto a update_checker ({sorted(allegati)})",
          allegati <= set(update_checker.ASSET_NAMES.values()))


# ---------------------------------------------------------------------------
# [2] update_downloader, contro un server HTTP reale
# ---------------------------------------------------------------------------

class _Handler(http.server.BaseHTTPRequestHandler):
    contenuto = b""
    manda_content_length = True
    tronca_a = 0        # >0: chiude la risposta dopo N byte (risposta troncata)
    rallenta = 0.0

    def do_GET(self):  # noqa: N802
        corpo = self.contenuto
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        if self.manda_content_length:
            self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        if self.tronca_a:
            corpo = corpo[: self.tronca_a]
        # A blocchi, così un annullamento a metà ha il tempo di intervenire.
        passo = max(1, len(corpo) // 8 or 1)
        for i in range(0, len(corpo), passo):
            try:
                self.wfile.write(corpo[i:i + passo])
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                return
            if self.rallenta:
                time.sleep(self.rallenta)

    def log_message(self, *args):  # silenzio nei log del test
        pass


def _avvia_server() -> tuple[http.server.ThreadingHTTPServer, int]:
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def test_downloader() -> None:
    print("\n[2] update_downloader — download reale su 127.0.0.1")

    contenuto = bytes(range(256)) * 4000   # ~1 MB, riconoscibile byte per byte
    _Handler.contenuto = contenuto
    _Handler.manda_content_length = True
    _Handler.tronca_a = 0
    _Handler.rallenta = 0.0

    srv, porta = _avvia_server()
    url = f"http://127.0.0.1:{porta}/pacchetto.bin"
    dest = tempfile.mkdtemp(prefix="dnd_dl_")

    try:
        # -- caso buono ------------------------------------------------------
        prog = update_downloader.DownloadProgress()
        percorso = update_downloader.download_asset(
            url, dest, "pacchetto.bin", expected_size=len(contenuto),
            progress=prog, chunk_size=8192,
        )
        check("il download riesce", Path(percorso).is_file())
        check("il contenuto è identico byte per byte",
              Path(percorso).read_bytes() == contenuto)
        check("lo stato finale è 'done'", prog.state == update_downloader.STATE_DONE)
        check("il totale arriva da Content-Length", prog.total == len(contenuto))
        check("i byte scaricati coincidono col totale",
              prog.downloaded == len(contenuto))
        check("la frazione è 1.0 alla fine", prog.fraction == 1.0)
        check("progress.path punta al file", prog.path == percorso)
        check("nessun file .part residuo",
              not list(Path(dest).glob("*" + update_downloader.PART_SUFFIX)))

        # -- avanzamento monotono e crescente --------------------------------
        _Handler.rallenta = 0.02
        prog2 = update_downloader.DownloadProgress()
        letture: list[int] = []
        stop = threading.Event()

        def _osserva():
            while not stop.is_set():
                letture.append(prog2.downloaded)
                time.sleep(0.005)

        osservatore = threading.Thread(target=_osserva, daemon=True)
        osservatore.start()
        update_downloader.download_asset(
            url, dest, "monotono.bin", expected_size=len(contenuto),
            progress=prog2, chunk_size=8192,
        )
        stop.set()
        osservatore.join(timeout=1)
        check("l'avanzamento non torna mai indietro",
              all(b >= a for a, b in zip(letture, letture[1:])))
        check("l'avanzamento è stato osservato mentre cresceva, non solo alla fine",
              len(set(letture)) > 2)
        _Handler.rallenta = 0.0

        # -- dimensione sbagliata: il file NON deve restare -------------------
        _Handler.tronca_a = len(contenuto) // 2
        prog3 = update_downloader.DownloadProgress()
        sollevato = False
        try:
            update_downloader.download_asset(
                url, dest, "troncato.bin", expected_size=len(contenuto),
                progress=prog3, chunk_size=8192,
            )
        except OSError:
            sollevato = True
        check("una risposta troncata solleva", sollevato)
        check("...lo stato è 'error'", prog3.state == update_downloader.STATE_ERROR)
        check("...non resta il file col nome definitivo",
              not (Path(dest) / "troncato.bin").exists())
        check("...non resta nemmeno il .part",
              not (Path(dest) / ("troncato.bin" + update_downloader.PART_SUFFIX)).exists())
        _Handler.tronca_a = 0

        # -- annullamento a metà ---------------------------------------------
        _Handler.rallenta = 0.05
        prog4 = update_downloader.DownloadProgress()
        cancel = threading.Event()
        esito: dict = {}

        def _scarica():
            try:
                update_downloader.download_asset(
                    url, dest, "annullato.bin", expected_size=len(contenuto),
                    progress=prog4, cancel=cancel, chunk_size=4096,
                )
            except update_downloader.DownloadCancelled:
                esito["annullato"] = True
            except Exception as ex:
                esito["errore"] = ex

        t = threading.Thread(target=_scarica, daemon=True)
        t.start()
        time.sleep(0.12)
        cancel.set()
        t.join(timeout=10)
        check("l'annullamento solleva DownloadCancelled", esito.get("annullato") is True)
        check("...lo stato è 'cancelled'",
              prog4.state == update_downloader.STATE_CANCELLED)
        check("...il file parziale è stato eliminato",
              not (Path(dest) / ("annullato.bin" + update_downloader.PART_SUFFIX)).exists())
        check("...e non è rimasto un file col nome definitivo",
              not (Path(dest) / "annullato.bin").exists())
        _Handler.rallenta = 0.0

        # -- senza Content-Length: barra indeterminata ------------------------
        _Handler.manda_content_length = False
        prog5 = update_downloader.DownloadProgress()
        percorso5 = update_downloader.download_asset(
            url, dest, "senza_lunghezza.bin", progress=prog5, chunk_size=8192,
        )
        check("il download riesce anche senza Content-Length",
              Path(percorso5).read_bytes() == contenuto)
        check("il totale resta 0 → fraction None → barra indeterminata",
              prog5.total == 0 and prog5.fraction is None)
        check("i byte scaricati sono comunque corretti",
              prog5.downloaded == len(contenuto))
        _Handler.manda_content_length = True

        # -- url vuoto ---------------------------------------------------------
        prog6 = update_downloader.DownloadProgress()
        errore = False
        try:
            update_downloader.download_asset("", dest, "x.bin", progress=prog6)
        except ValueError:
            errore = True
        check("un url vuoto solleva ValueError con un messaggio in italiano",
              errore and "piattaforma" in prog6.error)

        # -- riuso di un file già scaricato ------------------------------------
        check("find_downloaded trova un file della dimensione attesa",
              update_downloader.find_downloaded(dest, "pacchetto.bin",
                                                 len(contenuto)) is not None)
        check("find_downloaded rifiuta un file di dimensione sbagliata",
              update_downloader.find_downloaded(dest, "pacchetto.bin", 12345) is None)
        check("find_downloaded su un file assente ritorna None",
              update_downloader.find_downloaded(dest, "mai-esistito.bin") is None)

        # -- pulizia -----------------------------------------------------------
        (Path(dest) / ("orfano.bin" + update_downloader.PART_SUFFIX)).write_bytes(b"x")
        rimossi = update_downloader.cleanup_old_downloads(dest, keep_version="")
        check("cleanup_old_downloads elimina i file (nessuna versione da conservare)",
              rimossi >= 1)
        check("...compresi i .part orfani",
              not list(Path(dest).glob("*" + update_downloader.PART_SUFFIX)))
        check("...e la cartella resta vuota",
              not [f for f in Path(dest).iterdir() if f.is_file()])

        # Un pacchetto di una versione PIÙ RECENTE di quella in esecuzione va
        # conservato: è un aggiornamento scaricato e non ancora installato.
        (Path(dest) / "pacchetto.bin").write_bytes(b"nuovo")
        futura = f"{version.parse_version(version.APP_VERSION)[0] + 9}.0.0"
        rimossi = update_downloader.cleanup_old_downloads(dest, keep_version=futura)
        check("un pacchetto non ancora installato NON viene eliminato",
              (Path(dest) / "pacchetto.bin").exists() and rimossi == 0)
        rimossi = update_downloader.cleanup_old_downloads(
            dest, keep_version=version.APP_VERSION)
        check("un pacchetto della versione già in esecuzione viene eliminato",
              not (Path(dest) / "pacchetto.bin").exists() and rimossi == 1)
        check("cleanup su una cartella inesistente ritorna 0",
              update_downloader.cleanup_old_downloads(
                  str(Path(dest) / "non-esiste")) == 0)
    finally:
        srv.shutdown()
        srv.server_close()


# ---------------------------------------------------------------------------
# [3] update_state — la tabella dei casi
# ---------------------------------------------------------------------------

def test_update_state() -> None:
    print("\n[3] update_state — «Aggiornamento completato» dopo il riavvio")

    adesso = datetime(2026, 8, 17, 12, 0, 0)
    recente = (adesso - timedelta(hours=2)).isoformat()
    vecchio = (adesso - timedelta(days=30)).isoformat()

    casi = [
        # (installata, attesa, avvio, esito atteso, descrizione)
        ("0.3.0", "", "", "none",
         "nessun segnalibro: non mostrare nulla"),
        ("0.3.0", "0.3.0", recente, "completed",
         "la versione attesa è arrivata: aggiornamento completato"),
        ("0.3.1", "0.3.0", recente, "completed",
         "installata più recente dell'attesa: comunque completato"),
        ("0.2.15", "0.3.0", recente, "failed",
         "avviato di recente ma la versione non è cambiata: non completato"),
        ("0.2.15", "0.3.0", vecchio, "stale",
         "segnalibro vecchio di un mese: dimenticare in silenzio"),
        ("0.2.15", "0.3.0", "", "failed",
         "segnalibro senza istante: trattato come non completato"),
        ("0.2.15", "0.3.0", "non-una-data", "failed",
         "istante illeggibile: trattato come non completato, non nascosto"),
    ]
    for installata, attesa, avvio, atteso, descrizione in casi:
        got = update_state.classify_pending_update(installata, attesa, avvio, adesso)
        check(f"{descrizione} (atteso {atteso}, ottenuto {got})", got == atteso)

    # Il confine dei 7 giorni, da entrambi i lati.
    appena_dentro = (adesso - update_state.STALE_AFTER + timedelta(minutes=1)).isoformat()
    appena_fuori = (adesso - update_state.STALE_AFTER - timedelta(minutes=1)).isoformat()
    check("appena entro la scadenza: ancora 'failed'",
          update_state.classify_pending_update("0.2.15", "0.3.0", appena_dentro,
                                                adesso) == "failed")
    check("appena oltre la scadenza: 'stale'",
          update_state.classify_pending_update("0.2.15", "0.3.0", appena_fuori,
                                                adesso) == "stale")

    # Giro completo su DB reale.
    update_state.clear_pending_update()
    check("all'inizio non c'è nulla in sospeso",
          update_state.read_pending_update() == ("", ""))
    update_state.mark_update_started("9.9.9")
    attesa, avvio = update_state.read_pending_update()
    check("il segnalibro viene scritto", attesa == "9.9.9" and bool(avvio))
    check("...ed è leggibile come istante",
          isinstance(datetime.fromisoformat(avvio), datetime))
    check("con una versione attesa che non arriverà mai: 'failed'",
          update_state.classify_pending_update(version.APP_VERSION, attesa, avvio)
          == "failed")
    update_state.mark_update_started(version.APP_VERSION)
    attesa, avvio = update_state.read_pending_update()
    check("con la versione attesa uguale a quella in esecuzione: 'completed'",
          update_state.classify_pending_update(version.APP_VERSION, attesa, avvio)
          == "completed")
    update_state.clear_pending_update()
    check("la cancellazione funziona",
          update_state.read_pending_update() == ("", ""))


# ---------------------------------------------------------------------------
# [4] Percorsi ed etichette
# ---------------------------------------------------------------------------

def test_percorsi_ed_etichette() -> None:
    print("\n[4] Cartella di staging ed etichette dell'avanzamento")

    percorso = Path(get_updates_path())
    check("la cartella degli aggiornamenti viene creata", percorso.is_dir())
    check("è accanto al database, non nella cache",
          percorso.name == "updates" and "cache" not in str(percorso).lower())
    check("chiamarla due volte dà lo stesso percorso",
          get_updates_path() == str(percorso))

    check("48,1 MB", update_downloader.human_size(50_400_000) == "48,1 MB")
    check("byte sotto 1 KB", update_downloader.human_size(512) == "512 B")
    check("KB senza decimali", update_downloader.human_size(2048) == "2 KB")
    check("GB con la virgola",
          update_downloader.human_size(2 * 1024**3).endswith("GB"))

    prog = update_downloader.DownloadProgress(downloaded=13_000_000, total=50_400_000)
    etichetta = update_downloader.progress_label(prog)
    check(f"l'etichetta mostra scaricato, totale e percentuale ({etichetta})",
          "di" in etichetta and "%" in etichetta and "12,4 MB" in etichetta)
    prog_ignoto = update_downloader.DownloadProgress(downloaded=1024 * 1024, total=0)
    check("senza totale l'etichetta mostra solo i byte scaricati",
          "scaricati" in update_downloader.progress_label(prog_ignoto))
    check("is_finished è False mentre scarica",
          not update_downloader.DownloadProgress(
              state=update_downloader.STATE_RUNNING).is_finished)
    check("is_finished è True a scaricamento concluso",
          update_downloader.DownloadProgress(
              state=update_downloader.STATE_DONE).is_finished)


class _FakePage:
    """Doppio minimale della pagina Flet — stesso pattern di
    `test_ingresso_lan_sincronizzazione.py`: intercetta solo ciò che i dialoghi
    dell'aggiornamento chiamano davvero."""

    def __init__(self, platform=None):
        import flet as ft
        self.dialogs: list = []
        self.run_task_calls: list = []
        self.platform = platform
        self.web = False
        self.services: list = []

    def show_dialog(self, dlg) -> None:
        self.dialogs.append(dlg)

    def pop_dialog(self, *_a) -> None:
        if self.dialogs:
            self.dialogs.pop()

    def update(self, *_a, **_k) -> None:
        pass

    def run_task(self, coro_fn, *args, **kwargs) -> None:
        self.run_task_calls.append((coro_fn, args, kwargs))


def _tutti_i_testi(controllo) -> str:
    """
    Tutti i testi dell'albero di controlli, per verificare che un dialogo dica
    davvero ciò che deve dire.

    Deve seguire QUATTRO strade, e ognuna è stata necessaria:
      - `.controls` (Row/Column);
      - `.content` quando è un controllo (Container, AlertDialog, `d.section()`);
      - `.content` quando è una STRINGA — è così che i bottoni di questa versione
        di Flet (0.86.5) tengono la propria etichetta, non in un attributo
        `.text` (vedi `_find_by_text` in test_ingresso_lan_sincronizzazione.py);
      - `.title` dell'AlertDialog, che non è né in `controls` né in `content`.
    """
    import flet as ft
    out: list[str] = []

    def _visita(c):
        if isinstance(c, ft.Text) and c.value:
            out.append(str(c.value))
        for figlio in (getattr(c, "controls", None) or []):
            _visita(figlio)
        interno = getattr(c, "content", None)
        if isinstance(interno, str):
            out.append(interno)
        elif interno is not None:
            _visita(interno)
        titolo = getattr(c, "title", None)
        if isinstance(titolo, str):
            out.append(titolo)
        elif titolo is not None:
            _visita(titolo)
        etichetta = getattr(c, "label", None)
        if isinstance(etichetta, str):
            out.append(etichetta)
        for azione in (getattr(c, "actions", None) or []):
            _visita(azione)

    _visita(controllo)
    return " | ".join(out)


def test_dialoghi_si_costruiscono() -> None:
    """
    La UI non ha un driver headless in questo progetto: qui si verifica ciò che è
    verificabile onestamente — che i dialoghi si costruiscano senza sollevare, che
    il caso "serve reinstallare" imbocchi una strada DIVERSA da quella normale, e
    che la ProgressBar rispetti il vincolo documentato in regole_flet_api.md
    (dentro una Row con expand=True, altrimenti crash Flutter silenzioso).
    """
    print("\n[5] I dialoghi dell'aggiornamento si costruiscono")

    import flet as ft
    from core.update_checker import UpdateInfo
    from ui import update_dialogs

    normale = UpdateInfo(
        latest_version="0.3.1",
        release_url="https://github.com/DavMos9/dnd_app/releases/tag/v0.3.1",
        asset_name="dnd-companion-android.apk",
        asset_url="https://esempio/apk", asset_size=50_400_000,
        requires_reinstall=False,
    )
    migrazione = UpdateInfo(
        latest_version="0.3.0",
        release_url="https://github.com/DavMos9/dnd_app/releases/tag/v0.3.0",
        asset_name="dnd-companion-android.apk",
        asset_url="https://esempio/apk", asset_size=50_400_000,
        requires_reinstall=True,
    )
    senza_asset = UpdateInfo(latest_version="0.3.1",
                              release_url="https://esempio/release")

    # -- download normale --------------------------------------------------
    page = _FakePage(platform=ft.PagePlatform.ANDROID)
    update_dialogs.show_download_dialog(page, normale)
    check("il dialogo di download si apre", len(page.dialogs) == 1)
    dlg = page.dialogs[-1]
    testi = _tutti_i_testi(dlg)
    check(f"mostra la versione e la dimensione ({testi[:70]}…)",
          "0.3.1" in testi and "48,1 MB" in testi)

    barre = []

    def _cerca_barre(c, dentro_row_expand=False):
        if isinstance(c, ft.ProgressBar):
            barre.append((c, dentro_row_expand))
        for figlio in (getattr(c, "controls", None) or []):
            _cerca_barre(figlio, isinstance(c, ft.Row))
        interno = getattr(c, "content", None)
        if interno is not None and not isinstance(interno, str):
            _cerca_barre(interno, False)

    _cerca_barre(dlg.content)
    check("il dialogo contiene una ProgressBar", len(barre) == 1)
    if barre:
        barra, dentro_row = barre[0]
        check("la ProgressBar è dentro una ft.Row (regole_flet_api.md: PROGRESSBAR)",
              dentro_row)
        check("...con expand=True sulla barra", barra.expand is True)

    etichette_azioni = _tutti_i_testi(ft.Column(list(dlg.actions or [])))
    check("su Android l'azione finale è «Installa»", "Installa" in etichette_azioni)

    page_desktop = _FakePage(platform=ft.PagePlatform.MACOS)
    update_dialogs.show_download_dialog(page_desktop, normale)
    azioni_desktop = _tutti_i_testi(ft.Column(list(page_desktop.dialogs[-1].actions or [])))
    check("su desktop l'azione finale è «Mostra nella cartella»",
          "Mostra nella cartella" in azioni_desktop)

    # -- nessun asset scaricabile: solo il link ---------------------------
    page2 = _FakePage(platform=ft.PagePlatform.ANDROID)
    update_dialogs.show_download_dialog(page2, senza_asset)
    testi2 = _tutti_i_testi(page2.dialogs[-1])
    check("senza asset scaricabile non c'è barra di download",
          "non è scaricabile" in testi2)

    # -- migrazione della firma ------------------------------------------
    page3 = _FakePage(platform=ft.PagePlatform.ANDROID)
    update_dialogs.show_migration_dialog(page3, migrazione)
    dlg3 = page3.dialogs[-1]
    testi3 = _tutti_i_testi(dlg3)
    check("il dialogo di migrazione avverte della disinstallazione",
          "disinstallare e reinstallare" in testi3)
    check("...dice esplicitamente che i dati vengono cancellati",
          "cancella i dati" in testi3)
    check("...dice che è una volta sola", "VOLTA SOLA" in testi3)
    check("...spiega che serve il codice di trasferimento",
          "codice di trasferimento" in testi3)
    check("...e che il pacchetto va scaricato dal browser, non dall'app",
          "dal browser" in testi3)

    caselle = [c for c in dlg3.content.controls if isinstance(c, ft.Checkbox)]
    check("c'è una casella di conferma da spuntare", len(caselle) == 1)
    bottone_scarica = None
    for a in (dlg3.actions or []):
        for c in (getattr(a, "controls", None) or [a]):
            if getattr(c, "content", None) == "Vai alla pagina di download":
                bottone_scarica = c
    check("il pulsante di download esiste", bottone_scarica is not None)
    if bottone_scarica is not None and caselle:
        check("...ed è disabilitato finché la casella non è spuntata",
              bottone_scarica.disabled is True)
        caselle[0].value = True
        caselle[0].on_change(None)
        check("...e si abilita spuntandola", bottone_scarica.disabled is False)
        check("...e usa url=ft.Url (non webbrowser.open, morto su Android)",
              isinstance(bottone_scarica.url, ft.Url))

    # -- esito dell'aggiornamento -----------------------------------------
    page4 = _FakePage()
    update_dialogs.show_completion_dialog(page4, "0.3.0", "0.3.0", "completed")
    testi4 = _tutti_i_testi(page4.dialogs[-1])
    check("il dialogo di conferma dice «Aggiornamento completato»",
          "Aggiornamento completato" in testi4)
    check("...e nomina la versione in uso", "0.3.0" in testi4)

    page5 = _FakePage()
    update_dialogs.show_completion_dialog(page5, "0.2.15", "0.3.0", "failed")
    testi5 = _tutti_i_testi(page5.dialogs[-1])
    check("il dialogo di aggiornamento non completato lo dice",
          "non è stato completato" in testi5)
    check("...e nomina entrambe le versioni",
          "0.2.15" in testi5 and "0.3.0" in testi5)

    # -- istruzioni per sistema operativo ---------------------------------
    for sistema, atteso in (("Darwin", "Applicazioni"), ("Windows", "dnd_companion.exe"),
                             ("Linux", "eseguibile")):
        istruzioni = update_dialogs._desktop_instructions(sistema)
        check(f"le istruzioni per {sistema} sono specifiche", atteso in istruzioni)


def main() -> int:
    init_db()
    test_update_checker()
    test_contratto_nomi_asset()
    test_downloader()
    test_update_state()
    test_percorsi_ed_etichette()
    test_dialoghi_si_costruiscono()
    print("\n" + "=" * 70)
    print(f"Controlli passati: {_PASS} — falliti: {len(_FAIL)}")
    if _FAIL:
        for f in _FAIL:
            print(f"  - {f}")
        return 1
    print("Tutti i controlli passati.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
