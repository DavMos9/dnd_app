"""
Il messaggio "Aggiornamento completato", e come sopravvive alla morte del
processo.

Il problema: su Android il processo dell'app viene UCCISO e sostituito durante
l'installazione del nuovo APK. Il messaggio di conferma non può quindi essere
mostrato dallo stesso processo che ha avviato l'aggiornamento — quel processo non
esiste più nel momento in cui l'aggiornamento riesce. (Su desktop non viene
ucciso, ma l'utente deve comunque chiudere l'app per sostituire i file, quindi
il problema è lo stesso.)

Soluzione: prima di passare il pacchetto all'installer si scrive un
"segnalibro" in `app_settings` (versione in installazione + istante), e al primo
avvio successivo si confronta la versione in esecuzione con quella attesa. Se è
arrivata, l'aggiornamento è riuscito e lo si dice; se non è arrivata, l'utente
ha annullato l'installazione e glielo si può ricordare; se il segnalibro è
vecchio di giorni, si cancella in silenzio invece di infastidire per sempre.

La decisione vive qui come funzione PURA (`classify_pending_update`) proprio per
poter essere testata senza Flet, senza DB e senza dispositivo: è una tabella di
casi, e le tabelle di casi sbagliano in silenzio.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Literal

from version import parse_version

logger = logging.getLogger(__name__)

#: Chiavi in `app_settings` (vedi `data/repositories/settings_repo.py`).
PENDING_VERSION_KEY = "update_pending_version"
PENDING_STARTED_AT_KEY = "update_pending_started_at"

#: Oltre questo tempo un aggiornamento avviato e mai completato viene
#: dimenticato in silenzio. Una settimana: abbastanza da coprire "l'ho avviato
#: venerdì e riapro l'app alla serata successiva", non abbastanza da trasformarsi
#: in un avviso permanente che nessuno sa più a cosa si riferisca.
STALE_AFTER = timedelta(days=7)

PendingOutcome = Literal["none", "completed", "failed", "stale"]


def classify_pending_update(
    current_version: str,
    pending_version: str,
    started_at: str,
    now: datetime | None = None,
) -> PendingOutcome:
    """
    Cosa fare all'avvio, dato il segnalibro lasciato dall'avvio precedente.

    - `"none"`      — nessun aggiornamento in sospeso: non mostrare nulla.
    - `"completed"` — la versione in esecuzione è quella attesa (o più recente):
                      mostra "Aggiornamento completato" e cancella il segnalibro.
    - `"failed"`    — l'aggiornamento era stato avviato di recente ma la versione
                      non è cambiata: l'utente non ha completato l'installazione.
                      Offri di riprovare.
    - `"stale"`     — segnalibro troppo vecchio: cancellalo senza dire nulla.

    Un `started_at` illeggibile è trattato come `"failed"`, non come `"stale"`:
    il segnalibro esiste, quindi un aggiornamento è stato davvero avviato, e
    perdere il timestamp non è una buona ragione per nascondere l'informazione.
    Il caso si autorisolve comunque, perché "failed" cancella il segnalibro
    appena l'utente risponde.
    """
    if not pending_version:
        return "none"

    if parse_version(current_version) >= parse_version(pending_version):
        return "completed"

    adesso = now or datetime.now()
    if not started_at:
        return "failed"
    try:
        avviato = datetime.fromisoformat(started_at)
    except ValueError:
        logger.debug(
            "classify_pending_update: istante di avvio illeggibile (%r)", started_at,
        )
        return "failed"

    return "stale" if adesso - avviato > STALE_AFTER else "failed"


def mark_update_started(version: str) -> None:
    """
    Scrive il segnalibro. Va chiamata IMMEDIATAMENTE PRIMA di passare il
    pacchetto all'installer di sistema: su Android, subito dopo, questo processo
    non esiste più e non avrebbe altra occasione per scriverlo.
    """
    from data.repositories import settings_repo

    settings_repo.set_setting(PENDING_VERSION_KEY, version)
    settings_repo.set_setting(PENDING_STARTED_AT_KEY, datetime.now().isoformat())
    logger.info("Aggiornamento a %s avviato: segnalibro scritto.", version)


def read_pending_update() -> tuple[str, str]:
    """`(versione_attesa, istante_di_avvio)`, entrambe stringhe vuote se non
    c'è nulla in sospeso."""
    from data.repositories import settings_repo

    return (
        settings_repo.get_setting(PENDING_VERSION_KEY, ""),
        settings_repo.get_setting(PENDING_STARTED_AT_KEY, ""),
    )


def clear_pending_update() -> None:
    """Cancella il segnalibro. Idempotente."""
    from data.repositories import settings_repo

    settings_repo.set_setting(PENDING_VERSION_KEY, "")
    settings_repo.set_setting(PENDING_STARTED_AT_KEY, "")
