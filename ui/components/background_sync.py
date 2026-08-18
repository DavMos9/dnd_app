"""
Sincronizzazione in background per una vista Flet che deve riflettere da
sola i cambiamenti di un Mondo condiviso (Multiplayer), senza polling
manuale dell'utente — richiesta esplicita di Davide (2026-08-07): "l'utente
deve fare il meno possibile, la parte tecnica la deve gestire in automatico
l'app".

Nato in `ui/views/world/world_view.py::WorldsView` (2026-08-07, prima
sessione) e poi estratto qui (stessa giornata, bug segnalato da Davide: "in
Incontri i PF non si aggiornano da soli, il master deve prima andare in
Sezione Mondi e tornare indietro") per essere condiviso anche da
`ui/views/master/master_encounter_view.py::MasterEncounterView` — le due
viste hanno bisogno esattamente della stessa infrastruttura (thread
dedicato + ponte thread-safe verso il loop asyncio di Flet), ma logiche di
dominio diverse (cosa scaricare da un host remoto, cosa costituisce "uno
stato diverso"): quella parte resta iniettata da ciascun chiamante tramite
callback, per non accoppiare questo modulo a un mondo o a una vista
specifica (Dependency Inversion — questo modulo non importa né
`world_repo` né `world_sync`).

Il bug che ha reso necessaria questa attenzione al ponte thread-safe
(2026-08-07, verificato leggendo il sorgente di `flet==0.86.5`): l'UNICO
modo documentato per raggiungere in sicurezza il loop asyncio di una
sessione Flet da un `threading.Thread` estraneo è `page.run_task()`
(= `asyncio.run_coroutine_threadsafe(...)` sotto il cofano). Chiamare
`page.update()`/toccare i controlli direttamente da un thread qualunque
scrive lo stato giusto nel DB ma può lasciarlo invisibile a schermo finché
un'azione dell'utente non forza un giro sul thread giusto — esattamente il
sintomo "serve il refresh manuale" segnalato due volte da Davide su
funzionalità diverse (Sezione Mondi, poi Incontri).
"""

import logging
import threading
from typing import Awaitable, Callable, Optional

import flet as ft

logger = logging.getLogger(__name__)

#: Stesso ordine di grandezza già validato in `WorldsView` — abbastanza
#: reattivo per un tavolo di gioco, senza martellare rete/DB più volte al
#: secondo.
DEFAULT_INTERVAL_S = 2.0


class BackgroundSyncLoop:
    """
    Ciclo periodico su un thread dedicato (`daemon=True`, non blocca mai la
    chiusura del processo) che ad ogni giro:

    1. chiama `apply_fn()` — side-effect facoltativo, tipicamente "scarica
       gli eventi nuovi da un host remoto e applicali alla replica locale";
    2. chiama `signature_fn()` per ottenere una firma economica (stringa)
       dello stato rilevante;
    3. se la firma è cambiata rispetto al giro precedente — o se
       `should_redraw_anyway_fn()` lo richiede (es. un countdown visivo che
       deve scendere anche a stato invariato) — programma `async_redraw_fn()`
       sul loop asyncio della sessione tramite `page.run_task()`, MAI
       chiamato direttamente da questo thread.

    Ogni callback può sollevare eccezioni transitorie (rete, DB
    momentaneamente occupato): vengono loggate e SOLO quel giro viene
    saltato, il ciclo non si ferma mai per un errore isolato — coerente col
    resto del Multiplayer ("difesa in profondità", "best effort, mai
    bloccante").
    """

    def __init__(
        self,
        get_page: Callable[[], Optional[ft.Page]],
        signature_fn: Callable[[], Optional[str]],
        async_redraw_fn: Callable[[], Awaitable[None]],
        apply_fn: Optional[Callable[[], None]] = None,
        should_redraw_anyway_fn: Optional[Callable[[], bool]] = None,
        interval_s: float = DEFAULT_INTERVAL_S,
        thread_name: str = "background-sync",
    ):
        self._get_page = get_page
        self._signature_fn = signature_fn
        self._async_redraw_fn = async_redraw_fn
        self._apply_fn = apply_fn
        self._should_redraw_anyway_fn = should_redraw_anyway_fn
        self._interval_s = interval_s
        self._thread_name = thread_name
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._last_signature: Optional[str] = None

    def start(self) -> None:
        """Ferma un eventuale ciclo precedente e ne avvia uno nuovo — mai
        due thread attivi in parallelo su questa stessa istanza."""
        self.stop()
        self._last_signature = self._safe_signature()
        stop_event = threading.Event()
        self._stop_event = stop_event
        thread = threading.Thread(
            target=self._loop, args=(stop_event,),
            daemon=True, name=self._thread_name,
        )
        self._thread = thread
        thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._thread = None
        self._last_signature = None

    def _safe_signature(self) -> Optional[str]:
        try:
            return self._signature_fn()
        except Exception as e:
            logger.debug("BackgroundSyncLoop(%s): errore calcolo firma: %s",
                         self._thread_name, e)
            return self._last_signature

    def _loop(self, stop_event: threading.Event) -> None:
        while not stop_event.is_set():
            if self._apply_fn is not None:
                try:
                    self._apply_fn()
                except Exception as e:
                    logger.debug("BackgroundSyncLoop(%s): apply_fn fallita: %s",
                                 self._thread_name, e)

            signature = self._safe_signature()
            changed = signature != self._last_signature
            if changed:
                self._last_signature = signature

            redraw_anyway = False
            if not changed and self._should_redraw_anyway_fn is not None:
                try:
                    redraw_anyway = self._should_redraw_anyway_fn()
                except Exception as e:
                    logger.debug(
                        "BackgroundSyncLoop(%s): should_redraw_anyway_fn fallita: %s",
                        self._thread_name, e)

            if changed or redraw_anyway:
                try:
                    page = self._get_page()
                except Exception as e:
                    # Bug segnalato da Davide (2026-08-18): la sessione può
                    # terminare (tab chiusa/ricaricata) tra un giro e
                    # l'altro di questo thread — `self.page` su un Control
                    # non più agganciato a una pagina viva solleva
                    # RuntimeError ("Control must be added to the page
                    # first", stesso meccanismo già documentato in
                    # regole_flet_api.md per l'accesso PRIMA di page.add(),
                    # qui innescato DOPO che la sessione è stata smontata).
                    # `_get_page()` era l'unica delle callback di questo
                    # loop non protetta come le altre tre sopra — un giro
                    # saltato qui non perde nulla: il prossimo redraw
                    # arriverà comunque al prossimo cambiamento di firma.
                    logger.debug("BackgroundSyncLoop(%s): get_page fallita: %s",
                                 self._thread_name, e)
                    page = None
                if page is not None:
                    page.run_task(self._async_redraw_fn)

            if stop_event.wait(self._interval_s):
                return
