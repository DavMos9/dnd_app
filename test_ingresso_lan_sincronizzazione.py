"""
Verifica del fix 2026-08-07 (sessione successiva alla revisione dei timer
anti-spam) — bug reale segnalato da Davide dopo aver riletto in chat
l'elenco dei test manuali suggeriti, PRIMA ancora di arrivare a provarli
su Wi-Fi reale: "non si sincronizzano, al master non esce la richiesta a
meno di un aggiornamento manuale e al giocatore non esce l'approvazione
del master".

Due bug distinti, con la stessa causa di fondo — "questo pezzo di stato
non passa MAI dal ciclo di sincronizzazione in background già esistente":

1. **Il master non vede una nuova richiesta di ingresso in automatico.**
   `WorldsView._detail_signature_of()` (il "cosa è cambiato" del ciclo di
   sync ogni 2s, `_detail_sync_loop`) leggeva SOLO tabelle del DB
   (`world_events`, `world_members`, `world_change_requests`). Le
   richieste di ingresso in sospeso (`PendingJoinRequest`) però NON vivono
   nel DB — sono stato in memoria su `network.host_server.
   WorldHostServer._pending` (§9.4: sono per definizione una fase
   transitoria prima di diventare un vero membro). La firma non poteva
   quindi MAI cambiare all'arrivo di una nuova richiesta — invisibile al
   ciclo di sync, a differenza di ogni altra mutazione del mondo. Fix:
   `_detail_signature_of()` ora interroga anche `self._host_server.
   list_pending()` (stesso processo, nessuna rete) quando questo
   dispositivo ospita il mondo — stesso identico controllo già usato da
   `_hosting_section()` per decidere se mostrarle.

2. **Il giocatore non vede l'approvazione del master in automatico.**
   `core.world_sync.finish_pending_join()` era per design "azione manuale
   della UI, non un ciclo automatico" (docstring originale) — nessun
   polling automatico esisteva da nessuna parte, solo il pulsante
   "Controlla di nuovo". Fix:
   `WorldsView._open_lan_join_dialog()` avvia ora un ciclo `async`
   (`_poll_pending_join_loop`, `page.run_task()`) non appena il dialogo
   entra in stato "in attesa", che richiama `finish_pending_join()` ogni
   `_PENDING_JOIN_POLL_INTERVAL_S` (3s) finché non arriva un esito finale
   (approvato/rifiutato/errore) o l'utente chiude il dialogo — SENZA
   passare dal cancello anti-spam di rete (quello protegge i TENTATIVI di
   ingresso, non un polling passivo di stato, stessa scelta già presa per
   `WorldHostServer.join_status()` lato host, mai messo sotto rate limit
   perché economico e in sola lettura).

Entrambi i fix sono verificati qui con un vero `WorldHostServer` su socket
reale via 127.0.0.1 (stesso pattern di `test_lan_host_client.py`), non
con una replica della logica: la prova che conta è che
`WorldsView._detail_signature_of()`/`_open_lan_join_dialog()` REALI
rilevino un cambiamento avvenuto SOLO sull'host, esattamente come nello
scenario di Davide (due dispositivi, uno host uno client).

Per il polling automatico lato giocatore (bug 2), il ciclo `async` viene
fatto avanzare di UN giro manualmente in questi test (nessuna vera
`asyncio.sleep` da attendere: `asyncio.sleep` è temporaneamente sostituito
con un no-op per la durata di quella singola chiamata, ripristinato subito
dopo) — verifica che quel SINGOLO giro rilevi correttamente l'esito e
fermi il ciclo, non una simulazione di più giri nel tempo reale.

Eseguire con:
    PYTHONPATH=".venv/lib/python3.13/site-packages:." python3 test_ingresso_lan_sincronizzazione.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile

_TMP_HOME = tempfile.mkdtemp(prefix="dnd_ingresso_sync_")
os.environ["HOME"] = _TMP_HOME

import flet as ft  # noqa: E402

from data.database import init_db  # noqa: E402
from data.repositories import world_repo  # noqa: E402
from core import world_sync  # noqa: E402
from core.world_backend import RemoteBackend  # noqa: E402
from network.host_server import WorldHostServer  # noqa: E402

_PASS = 0
_FAIL: list[str] = []


def check(label: str, cond: bool) -> None:
    global _PASS
    if cond:
        _PASS += 1
    else:
        _FAIL.append(label)
        print(f"  FALLITO: {label}")


def _patch_worlds_view_page_property() -> None:
    """
    `WorldsView` (a differenza di altre view di questo progetto, es.
    `MasterEncounterView`, che cache-a `self._page` di suo) usa ovunque
    `self.page`, la PROPRIETÀ vera di Flet definita su `BaseControl`
    (`flet/controls/base_control.py`): risale la catena `parent` fino a
    trovare un'istanza di `Page`, e solleva `RuntimeError` se il controllo
    non è mai stato agganciato a una pagina reale — non esiste alcun
    setter, non si può semplicemente assegnare `wv.page = FakePage()`.

    Per questi test (che devono eseguire `_open_lan_join_dialog()` per
    intero, chiamate dirette a `self.page.show_dialog/pop_dialog/update/
    run_task` incluse) si sostituisce la proprietà `page` SOLO sulla
    classe `WorldsView` — non su `BaseControl`/`ft.Column` condivisi da
    tutto il resto dell'app — con una che legge da un attributo
    d'istanza `_test_fake_page` se presente, altrimenti ricade sul
    comportamento originale (utile per gli altri metodi chiamati sugli
    stessi oggetti che non hanno bisogno di una pagina finta). Va
    applicata una sola volta per processo di test.
    """
    from ui.views.world.world_view import WorldsView

    if getattr(WorldsView, "_test_page_patched", False):
        return
    original_page_property = WorldsView.page  # property ereditata da BaseControl

    def _page_getter(self):
        fake = getattr(self, "_test_fake_page", None)
        if fake is not None:
            return fake
        return original_page_property.fget(self)

    WorldsView.page = property(_page_getter)
    WorldsView._test_page_patched = True


class _FakePage:
    """Stesso pattern già in uso in `test_fase_4.py` (`FakePage`): un
    doppio minimale che intercetta le sole chiamate che `WorldsView` fa
    davvero su `self.page` durante questi scenari. `run_task` qui NON
    esegue subito la coroutine (a differenza del doppio di
    `test_fase_4.py`): la SALVA, così il test può farla avanzare di un
    giro alla volta in modo controllato — è proprio il compito di
    `run_task` che si sta verificando."""

    def __init__(self):
        self.dialogs: list = []
        self.run_task_calls: list[tuple] = []
        self.platform = None  # non Android/iOS: niente riga QR nel dialogo

    def show_dialog(self, dlg) -> None:
        self.dialogs.append(dlg)

    def pop_dialog(self, *_a) -> None:
        if self.dialogs:
            self.dialogs.pop()

    def update(self, *_a, **_k) -> None:
        pass

    def run_task(self, coro_fn, *args, **kwargs) -> None:
        self.run_task_calls.append((coro_fn, args, kwargs))


async def _instant_sleep(_seconds: float) -> None:
    """Sostituto di `asyncio.sleep` per far avanzare `_poll_pending_join_
    loop` di un giro senza attendere `_PENDING_JOIN_POLL_INTERVAL_S`
    secondi veri."""
    return


def _run_one_poll_iteration(coro_fn) -> None:
    """Esegue la coroutine catturata da `page.run_task()` con
    `asyncio.sleep` sostituito da un no-op — la coroutine termina da sola
    (vedi `_poll_pending_join_loop`) non appena `finish_pending_join()`
    ritorna un esito non più "pending", esattamente come nell'app reale
    dopo il primo risveglio successivo alla risoluzione."""
    original_sleep = asyncio.sleep
    asyncio.sleep = _instant_sleep  # type: ignore[assignment]
    try:
        asyncio.run(coro_fn())
    finally:
        asyncio.sleep = original_sleep


def _find_by_text(controls: list, text: str):
    """`ElevatedButton`/`TextButton` in questa versione di Flet
    (0.86.5) tengono l'etichetta in `.content` (una stringa semplice
    viene passata così com'è), non in un attributo `.text` — verificato
    empiricamente, vedi `dnd_app/docs/regole_flet_api.md`."""
    for c in controls:
        if getattr(c, "content", None) == text:
            return c
    return None


def _find_field(dlg, label: str):
    """
    Il `ft.TextField` del dialogo con questa etichetta esatta.

    Esiste per non dipendere dalla POSIZIONE dei controlli nella colonna del
    dialogo: quel dialogo cresce (scoperta automatica, QR, codice di
    trasferimento…) e un test agganciato agli indici si rompe ad ogni aggiunta,
    con un errore che punta altrove rispetto alla causa.
    """
    for c in dlg.content.controls:
        if isinstance(c, ft.TextField) and c.label == label:
            return c
    raise AssertionError(f"campo «{label}» non trovato nel dialogo")


def _find_status_and_retry(dlg) -> tuple:
    """
    `(status_text, retry_btn)`: la riga di stato è l'ultimo `ft.Text` della
    colonna, il pulsante è il `TextButton` "Controlla di nuovo".
    """
    status = None
    retry = None
    for c in dlg.content.controls:
        if isinstance(c, ft.Text) and not isinstance(c, ft.TextField):
            status = c
        if isinstance(c, ft.TextButton) and getattr(c, "content", None) == "Controlla di nuovo":
            retry = c
    assert status is not None, "riga di stato non trovata nel dialogo"
    assert retry is not None, "pulsante «Controlla di nuovo» non trovato nel dialogo"
    return status, retry


def _find_poll_loop_call(page: _FakePage) -> tuple | None:
    """Tra le chiamate a `page.run_task()` (che includono anche i cicli
    del countdown visivo sui pulsanti, avviati più volte con argomenti),
    isola quella del polling automatico — l'unica coroutine schedulata
    SENZA argomenti aggiuntivi e col nome giusto."""
    for call in page.run_task_calls:
        coro_fn, args, _kwargs = call
        if getattr(coro_fn, "__name__", "") == "_poll_pending_join_loop" and not args:
            return call
    return None


# ---------------------------------------------------------------------------
# [1] Il master vede una nuova richiesta di ingresso senza refresh manuale
# ---------------------------------------------------------------------------

def test_master_signature_includes_pending_join_requests() -> None:
    print("\n[1] _detail_signature_of() cambia quando arriva una NUOVA richiesta "
          "di ingresso, senza alcun refresh manuale")
    from ui.views.world.world_view import WorldsView

    world = world_repo.create_world("Mondo Sync Ingresso", "dev-master", "Il Master")
    assert world is not None

    host = WorldHostServer(world.id, long_poll_timeout=2.0, announce=False)
    port = host.start()
    try:
        wv = WorldsView(on_back_to_home=lambda: None)
        wv.device_id = "dev-master"
        wv._host_server = host  # simula "questo dispositivo sta ospitando", come _start_hosting()

        sig_before = wv._detail_signature_of(world)

        # Una nuova richiesta arriva SOLO sull'host (stato in memoria,
        # nessuna tabella DB coinvolta) — esattamente lo scenario reale:
        # un secondo dispositivo chiama POST /join.
        client = RemoteBackend("127.0.0.1", port, "dev-nuovo-giocatore")
        outcome = client.join(world.join_code, host.pin, "Nuovo Giocatore")
        check("il nuovo dispositivo risulta 'pending'", outcome.status == "pending")

        sig_after = wv._detail_signature_of(world)
        check("la firma cambia SOLO per l'arrivo della richiesta di ingresso "
              "(nessun'altra mutazione nel frattempo)", sig_after != sig_before)

        # Coerenza con quanto mostrato in `_hosting_section()`.
        pending = host.list_pending()
        check("la richiesta compare in list_pending() (la stessa fonte letta "
              "dalla firma)", len(pending) == 1 and pending[0].device_id == "dev-nuovo-giocatore")

        # Approvata: sparisce da list_pending() (diventa un membro vero),
        # la firma deve cambiare di nuovo.
        approved = host.approve(outcome.request_id)
        check("l'approvazione riesce", approved)
        sig_after_approve = wv._detail_signature_of(world)
        check("la firma cambia ANCHE dopo l'approvazione (sparisce dalle "
              "pending, compare tra i membri)", sig_after_approve != sig_after)

        # Nessun cambiamento nel frattempo -> firma stabile (non deve
        # ridisegnare a vuoto ad ogni giro del ciclo di sync).
        sig_stable = wv._detail_signature_of(world)
        check("la firma è stabile se non cambia nulla",
              sig_stable == sig_after_approve)
    finally:
        host.stop()


def test_master_signature_ignores_other_hosts_pending_requests() -> None:
    print("\n[2] _detail_signature_of() non guarda WorldHostServer.list_pending() "
          "se QUESTO dispositivo non ospita il mondo (nessun _host_server, o di un "
          "altro mondo)")
    from ui.views.world.world_view import WorldsView

    world = world_repo.create_world("Mondo Sync Ingresso B", "dev-owner", "Il Master")
    assert world is not None
    other_world = world_repo.create_world("Altro Mondo", "dev-owner", "Il Master")
    assert other_world is not None

    wv = WorldsView(on_back_to_home=lambda: None)
    wv.device_id = "dev-owner"
    check("nessun _host_server: nessun errore, la firma si calcola comunque",
          isinstance(wv._detail_signature_of(world), str))

    other_host = WorldHostServer(other_world.id, long_poll_timeout=2.0, announce=False)
    other_host.start()
    try:
        wv._host_server = other_host  # ospita un ALTRO mondo, non `world`
        sig = wv._detail_signature_of(world)
        client = RemoteBackend("127.0.0.1", other_host.port, "dev-x")
        client.join(other_world.join_code, other_host.pin, "Estraneo")
        sig_after = wv._detail_signature_of(world)
        check("una richiesta di ingresso su un ALTRO mondo non tocca la firma "
              "di `world`", sig == sig_after)
    finally:
        other_host.stop()


# ---------------------------------------------------------------------------
# [3] Il giocatore vede l'approvazione/il rifiuto del master senza cliccare
# manualmente "Controlla di nuovo"
# ---------------------------------------------------------------------------

def _reach_pending_state(host: WorldHostServer, port: int, device_id: str):
    """Apre il dialogo «Unisciti in LAN» con una FakePage, compila i campi
    e simula il click su «Entra» — riproduce esattamente il percorso reale
    dell'utente fino allo stato "in attesa dell'approvazione", punto in
    cui (dal fix) il polling automatico deve già essere stato schedulato.
    Ritorna `(wv, page, dlg, retry_btn, status_text)`."""
    from ui.views.world.world_view import WorldsView

    world_sync.reset_client_cooldowns_for_tests()

    wv = WorldsView(on_back_to_home=lambda: None)
    wv.device_id = device_id
    page = _FakePage()
    wv._test_fake_page = page  # type: ignore[attr-defined]

    wv._open_lan_join_dialog()
    check("il dialogo «Unisciti in LAN» si apre", len(page.dialogs) == 1)
    dlg = page.dialogs[-1]

    # Ricerca per ETICHETTA, non per posizione (corretto il 2026-08-17).
    # Prima questi sette controlli venivano presi per indice negativo
    # (`controls[-7]`…`controls[-1]`): aggiungere un campo al dialogo — come è
    # successo col codice di trasferimento, §11.9 — spostava tutti gli indici e
    # questo test riempiva i campi SBAGLIATI, fallendo con un `AssertionError`
    # a valle che non diceva nulla sulla causa vera.
    host_field = _find_field(dlg, "Indirizzo IP dell'host")
    port_field = _find_field(dlg, "Porta")
    code_field = _find_field(dlg, "Codice a 6 caratteri")
    pin_field = _find_field(dlg, "PIN a 6 cifre")
    display_field = _find_field(dlg, "Il tuo nome")
    status_text, retry_btn = _find_status_and_retry(dlg)
    enter_btn = _find_by_text(dlg.actions[0].controls, "Entra")
    assert enter_btn is not None, "pulsante «Entra» non trovato nel dialogo"

    host_field.value = "127.0.0.1"
    port_field.value = str(port)
    code_field.value = world_repo.get_world(host.world_id).join_code
    pin_field.value = host.pin
    display_field.value = "Giocatore Automatico"

    enter_btn.on_click(None)
    check("dopo «Entra», il dialogo mostra lo stato di attesa",
          "attesa" in (status_text.value or "").lower())
    check("il pulsante «Controlla di nuovo» diventa visibile", retry_btn.visible)

    poll_call = _find_poll_loop_call(page)
    check("il polling automatico viene schedulato SUBITO, senza bisogno di "
          "cliccare «Controlla di nuovo»", poll_call is not None)

    return wv, page, dlg, retry_btn, status_text, poll_call


def test_player_detects_approval_automatically() -> None:
    print("\n[3] Il polling automatico rileva l'approvazione del master senza "
          "alcun click manuale")

    world = world_repo.create_world("Mondo Approvazione Auto", "dev-master", "Il Master")
    assert world is not None
    host = WorldHostServer(world.id, long_poll_timeout=2.0, announce=False)
    port = host.start()
    try:
        wv, page, dlg, retry_btn, status_text, poll_call = _reach_pending_state(
            host, port, "dev-player-auto",
        )

        # Il master approva DALLA SUA parte — nessuna azione sul dialogo
        # del giocatore, che nel frattempo non sa ancora nulla.
        pending = host.list_pending()
        assert len(pending) == 1
        approved = host.approve(pending[0].id)
        check("il master approva la richiesta", approved)

        # Un giro del ciclo di polling automatico (nessun click utente).
        coro_fn, args, kwargs = poll_call
        _run_one_poll_iteration(lambda: coro_fn(*args, **kwargs))

        check("il dialogo si è chiuso da solo dopo l'approvazione",
              dlg not in page.dialogs)
        check("il giocatore è entrato nel mondo (nessun 'Controlla di nuovo' "
              "necessario)", wv._current_world is not None
              and wv._current_world.id == world.id)
        check("il dispositivo risulta membro vero del mondo",
              world_repo.get_member(world.id, "dev-player-auto") is not None)

        # Pulizia: `_open_detail` ha avviato un vero thread di sync in
        # background — da fermare esplicitamente, stesso principio di
        # `will_unmount()`.
        wv._stop_detail_sync()
    finally:
        host.stop()


def test_player_detects_rejection_automatically() -> None:
    print("\n[4] Il polling automatico rileva ANCHE il rifiuto del master, senza "
          "click manuale, e ferma se stesso")

    world = world_repo.create_world("Mondo Rifiuto Auto", "dev-master", "Il Master")
    assert world is not None
    host = WorldHostServer(world.id, long_poll_timeout=2.0, announce=False)
    port = host.start()
    try:
        wv, page, dlg, retry_btn, status_text, poll_call = _reach_pending_state(
            host, port, "dev-player-rifiutato",
        )

        pending = host.list_pending()
        assert len(pending) == 1
        rejected = host.reject(pending[0].id)
        check("il master rifiuta la richiesta", rejected)

        coro_fn, args, kwargs = poll_call
        _run_one_poll_iteration(lambda: coro_fn(*args, **kwargs))

        check("il dialogo resta aperto (il giocatore deve vedere il motivo)",
              dlg in page.dialogs)
        check("lo stato mostra il rifiuto, senza bisogno del pulsante manuale",
              "rifiutat" in (status_text.value or "").lower())
        check("«Controlla di nuovo» si nasconde (stato terminale, non ha più senso)",
              not retry_btn.visible)
        check("il dispositivo NON è diventato membro",
              world_repo.get_member(world.id, "dev-player-rifiutato") is None)
    finally:
        host.stop()


def test_cancel_stops_automatic_polling() -> None:
    print("\n[5] Chiudere il dialogo («Annulla») ferma il polling automatico — "
          "nessuna chiamata di rete residua al giro successivo")

    world = world_repo.create_world("Mondo Annulla Polling", "dev-master", "Il Master")
    assert world is not None
    host = WorldHostServer(world.id, long_poll_timeout=2.0, announce=False)
    port = host.start()
    try:
        wv, page, dlg, retry_btn, status_text, poll_call = _reach_pending_state(
            host, port, "dev-player-annulla",
        )

        cancel_btn = _find_by_text(dlg.actions[0].controls, "Annulla")
        assert cancel_btn is not None, "pulsante «Annulla» non trovato"
        cancel_btn.on_click(None)
        check("«Annulla» chiude il dialogo", dlg not in page.dialogs)

        # Il giro successivo del ciclo (quello già schedulato PRIMA di
        # Annulla) non deve più chiamare la rete: si accorge dello stato
        # azzerato e ritorna subito. Verificato monkeypatchando
        # `world_sync.finish_pending_join` per farlo fallire se mai
        # venisse chiamato.
        def _must_not_be_called(*_a, **_k):
            raise AssertionError("finish_pending_join() chiamato dopo Annulla")

        original = world_sync.finish_pending_join
        world_sync.finish_pending_join = _must_not_be_called
        try:
            coro_fn, args, kwargs = poll_call
            _run_one_poll_iteration(lambda: coro_fn(*args, **kwargs))
            check("il ciclo di polling si ferma da solo dopo Annulla, senza "
                  "generare traffico di rete", True)
        except AssertionError:
            check("il ciclo di polling si ferma da solo dopo Annulla, senza "
                  "generare traffico di rete", False)
        finally:
            world_sync.finish_pending_join = original
    finally:
        host.stop()


def main() -> int:
    init_db()
    _patch_worlds_view_page_property()
    print("=" * 70)
    print("Sincronizzazione automatica dell'ingresso in un mondo LAN")
    print(f"HOME di test: {_TMP_HOME}")
    print("=" * 70)

    test_master_signature_includes_pending_join_requests()
    test_master_signature_ignores_other_hosts_pending_requests()
    test_player_detects_approval_automatically()
    test_player_detects_rejection_automatically()
    test_cancel_stops_automatic_polling()

    print("\n" + "=" * 70)
    print(f"Controlli passati: {_PASS} — falliti: {len(_FAIL)}")
    if _FAIL:
        print("Falliti:")
        for f in _FAIL:
            print(f"  - {f}")
        return 1
    print("Tutti i controlli passati.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
