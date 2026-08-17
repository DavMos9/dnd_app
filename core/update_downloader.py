"""
Scaricamento in streaming dell'aggiornamento, con avanzamento reale
(2026-08-17, richiesta di Davide: "l'upgrade automatico dell'app con la barra
del download").

Nessun import di Flet: questo modulo espone uno stato mutabile
(`DownloadProgress`) che la UI legge a intervalli, e una funzione bloccante che
la UI esegue su un thread. Il ponte fra i due è documentato in
`ui/update_dialogs.py`, e riusa il pattern già in produzione in
`world_view.py::_start_network_cooldown_ticker` (un ciclo `async` schedulato con
`page.run_task` che legge uno stato condiviso e aggiorna i controlli) invece di
mutare controlli Flet da un thread — cosa che è una corsa, non un dettaglio.

Interamente verificabile senza dispositivo: `test_aggiornamento_app.py` lo
esercita contro un `http.server` locale.
"""

from __future__ import annotations

import logging
import os
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from version import APP_VERSION, parse_version

logger = logging.getLogger(__name__)

#: Dimensione del blocco letto per volta. 256 KB è un compromesso: abbastanza
#: grande da non fare migliaia di iterazioni su un APK da decine di MB,
#: abbastanza piccolo da aggiornare la barra con continuità e da accorgersi di
#: un annullamento entro una frazione di secondo.
DEFAULT_CHUNK_SIZE = 256 * 1024

#: Timeout della connessione, non del download complessivo: si applica alla
#: singola operazione di rete. Più generoso dei 5 s del controllo versione —
#: qui si scaricano decine di MB, possibilmente su un Wi-Fi lento.
DEFAULT_TIMEOUT_S = 30.0

#: Suffisso del file parziale. Il file col nome definitivo compare solo a
#: scaricamento completato e verificato (vedi `download_asset`).
PART_SUFFIX = ".part"

STATE_IDLE = "idle"
STATE_RUNNING = "running"
STATE_DONE = "done"
STATE_ERROR = "error"
STATE_CANCELLED = "cancelled"


class DownloadCancelled(Exception):
    """L'utente ha annullato: non è un errore, e la UI non deve trattarlo come
    tale (nessun messaggio rosso, nessuna proposta di riprovare)."""


@dataclass
class DownloadProgress:
    """
    Stato condiviso fra il thread che scarica e il ciclo della UI che lo mostra.

    Mutato in place dal thread, letto dalla UI: niente lock. È corretto perché
    ogni campo è un intero o una stringa, scritti con assegnazioni singole
    (atomiche sotto il GIL) e letti indipendentemente l'uno dall'altro — la UI
    che leggesse `downloaded` un istante prima dell'aggiornamento di `total`
    mostrerebbe una percentuale vecchia di 200 ms, non un valore corrotto. Un
    lock qui non comprerebbe nulla e andrebbe preso ad ogni blocco.
    """
    downloaded: int = 0
    total: int = 0
    state: str = STATE_IDLE
    error: str = ""
    path: str = ""

    @property
    def fraction(self) -> float | None:
        """
        Frazione completata fra 0 e 1, oppure `None` quando la dimensione totale
        non è nota — in quel caso la UI deve mostrare una barra INDETERMINATA
        (`ft.ProgressBar(value=None)`), non una barra a zero che sembra bloccata.
        Succede quando la risposta non porta `Content-Length`.
        """
        if self.total <= 0:
            return None
        return min(1.0, self.downloaded / self.total)

    @property
    def is_finished(self) -> bool:
        return self.state in (STATE_DONE, STATE_ERROR, STATE_CANCELLED)


def human_size(num_bytes: int) -> str:
    """
    "48,1 MB" — con la virgola decimale, come si scrive in italiano, e senza
    decimali per i byte e i KB, dove non aggiungono nulla.
    """
    if num_bytes < 1024:
        return f"{num_bytes} B"
    if num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.0f} KB"
    valore = num_bytes / (1024 * 1024)
    if valore >= 1024:
        return f"{valore / 1024:.1f} GB".replace(".", ",")
    return f"{valore:.1f} MB".replace(".", ",")


def progress_label(progress: DownloadProgress) -> str:
    """Etichetta sotto la barra: "12,4 MB di 48,1 MB — 26%", oppure la sola
    quantità scaricata quando il totale non è noto."""
    if progress.total <= 0:
        return f"{human_size(progress.downloaded)} scaricati"
    percento = int((progress.fraction or 0) * 100)
    return (
        f"{human_size(progress.downloaded)} di {human_size(progress.total)} "
        f"— {percento}%"
    )


def download_asset(
    url: str,
    dest_dir: str,
    filename: str,
    *,
    expected_size: int = 0,
    progress: DownloadProgress | None = None,
    cancel: threading.Event | None = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    timeout: float = DEFAULT_TIMEOUT_S,
) -> str:
    """
    Scarica `url` in `dest_dir/filename` mostrando l'avanzamento in `progress`.
    Restituisce il percorso del file scaricato.

    BLOCCANTE: va eseguita su un thread (`await asyncio.to_thread(...)` dalla
    UI), mai sul loop asyncio di Flet — una chiamata sincrona lì congela l'intera
    pagina, bottoni compresi. È lo stesso errore già corretto due volte nel
    dialogo d'ingresso LAN (vedi `world_view.py::_poll_pending_join_loop`).

    Garanzie:

    - **Mai un file parziale col nome definitivo.** Si scrive su
      `<filename>.part` e si chiude con `os.replace()`, che è atomico su tutti
      e tre i sistemi operativi e su Android. Serve perché il nome definitivo è
      anche il segnale "questo file è pronto da installare": un `.apk` troncato
      a metà, con il nome giusto, verrebbe passato all'installer di sistema.
    - **`expected_size` verificato alla fine**, quando fornito: una risposta
      troncata da un proxy o da una connessione caduta produce un file più
      corto senza alcun errore di rete. In caso di discrepanza il `.part` viene
      eliminato e si solleva.
    - **Nessun checksum.** L'API di GitHub Releases non pubblica un digest per
      gli asset (verificato leggendo la risposta reale di `releases/latest`):
      dichiararlo invece di simulare un controllo d'integrità che non esiste. Il
      controllo di dimensione più HTTPS sono ciò di cui disponiamo davvero.
    - **Annullamento entro un blocco**: `cancel.set()` fa eliminare il `.part`
      e sollevare `DownloadCancelled`.
    """
    progress = progress if progress is not None else DownloadProgress()
    cancel = cancel if cancel is not None else threading.Event()

    if not url:
        progress.state = STATE_ERROR
        progress.error = "Nessun file da scaricare per questa piattaforma."
        raise ValueError(progress.error)

    dest = Path(dest_dir) / filename
    part = dest.with_name(dest.name + PART_SUFFIX)

    progress.downloaded = 0
    progress.total = max(0, expected_size)
    progress.error = ""
    progress.path = ""
    progress.state = STATE_RUNNING

    def _pulisci_part() -> None:
        try:
            part.unlink(missing_ok=True)
        except OSError as e:
            logger.debug("Impossibile eliminare il file parziale %s: %s", part, e)

    try:
        Path(dest_dir).mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(
            url,
            headers={"User-Agent": f"DnDCompanion/{APP_VERSION}"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            # `Content-Length` è la fonte migliore: la dimensione dichiarata
            # dall'API può essere vecchia se l'asset è stato ricaricato.
            length = resp.headers.get("Content-Length")
            if length:
                try:
                    progress.total = int(length)
                except ValueError:
                    pass  # totale ignoto → barra indeterminata

            with open(part, "wb") as fh:
                while True:
                    if cancel.is_set():
                        raise DownloadCancelled()
                    blocco = resp.read(chunk_size)
                    if not blocco:
                        break
                    fh.write(blocco)
                    progress.downloaded += len(blocco)

        if expected_size > 0 and progress.downloaded != expected_size:
            raise OSError(
                f"scaricati {progress.downloaded} byte invece di {expected_size}: "
                f"il file è incompleto"
            )

        os.replace(part, dest)
        progress.path = str(dest)
        progress.state = STATE_DONE
        logger.info("Aggiornamento scaricato in %s (%s)", dest,
                    human_size(progress.downloaded))
        return str(dest)

    except DownloadCancelled:
        _pulisci_part()
        progress.state = STATE_CANCELLED
        logger.info("Scaricamento dell'aggiornamento annullato dall'utente.")
        raise
    except (urllib.error.URLError, OSError) as e:
        _pulisci_part()
        progress.state = STATE_ERROR
        progress.error = str(e)
        logger.warning("Scaricamento dell'aggiornamento fallito: %s", e)
        raise


def find_downloaded(dest_dir: str, filename: str,
                     expected_size: int = 0) -> str | None:
    """
    Percorso di un file già scaricato e integro, se c'è.

    Serve al pulsante «Riprova» dopo un aggiornamento non completato (l'utente
    ha scaricato ma non ha toccato "Installa"): non ha senso riscaricare decine
    di MB che sono già su disco. Ritorna `None` se il file manca o se la
    dimensione non combacia con quella attesa — in quel caso è più sicuro
    riscaricare che fidarsi.
    """
    candidato = Path(dest_dir) / filename
    try:
        if not candidato.is_file():
            return None
        if expected_size > 0 and candidato.stat().st_size != expected_size:
            logger.info(
                "Il file già presente %s ha dimensione %s invece di %s: verrà riscaricato",
                candidato, candidato.stat().st_size, expected_size,
            )
            return None
        return str(candidato)
    except OSError:
        return None


def cleanup_old_downloads(dest_dir: str, keep_version: str = "") -> int:
    """
    Elimina i file parziali orfani e i pacchetti di versioni diverse da
    `keep_version`, restituendo quanti file ha eliminato.

    Chiamata all'avvio dopo aver mostrato "Aggiornamento completato": senza,
    ogni aggiornamento lascerebbe per sempre decine di MB nello spazio privato
    dell'app — su un tablet, l'ultima cosa che si nota e la prima che dà
    fastidio.

    `keep_version` non viene confrontato col nome del file (che è fisso,
    `dnd-companion-android.apk`, senza numero di versione) ma serve a decidere
    se conservare il pacchetto corrente: se coincide con la versione in
    esecuzione l'installazione è avvenuta e il file non serve più. Un `.part`
    orfano viene sempre eliminato: nessun download è in corso all'avvio.
    """
    rimossi = 0
    cartella = Path(dest_dir)
    if not cartella.is_dir():
        return 0

    installata = parse_version(APP_VERSION)
    conserva = bool(keep_version) and parse_version(keep_version) > installata

    for file in cartella.iterdir():
        try:
            if not file.is_file():
                continue
            if file.name.endswith(PART_SUFFIX):
                file.unlink()
                rimossi += 1
                continue
            if not conserva:
                file.unlink()
                rimossi += 1
        except OSError as e:
            logger.debug("Impossibile eliminare %s: %s", file, e)

    if rimossi:
        logger.info("Pulizia aggiornamenti: %d file eliminati da %s", rimossi, dest_dir)
    return rimossi
