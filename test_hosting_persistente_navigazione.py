"""
Verifica del fix 2026-08-07 (sessione successiva) — bug reale segnalato da
Davide dopo un vero test su Wi-Fi con due dispositivi: ha approvato
l'ingresso di un giocatore (funzionante, fix della sessione precedente),
poi ha provato ad aggiungere il personaggio del giocatore a un incontro
dalla Modalità Master — e lì il push del personaggio sull'host falliva
("Personaggio creato, ma non è stato possibile registrarlo subito
sull'host"), il master non vedeva alcun personaggio nel mondo.

Causa reale, trovata analizzando il codice (non riproducibile in sandbox
con due dispositivi fisici separati, ma riproducibile a livello di singola
view/processo): `WorldsView.will_unmount()` fermava SEMPRE l'hosting
attivo (`self._host_server.stop()`) — scelta deliberata di una sessione
precedente ("non lasciare una porta aperta uscendo dalla Sezione Mondi").
Il problema è che `ui/app.py::_navigate()` ricostruisce l'intera pagina ad
OGNI navigazione di primo livello (Home, Modalità Master, Mondi, perfino
un cambio tema) — il ciclo di vita standard di Flet fa scattare
`will_unmount()` sulla `WorldsView` precedente ad ognuna di quelle azioni,
non solo quando si esce davvero dalla Sezione Mondi. Il master che ha
aperto la Modalità Master per gestire l'incontro ha quindi fermato
l'hosting SENZA volerlo e senza alcun avviso — l'host era già morto prima
ancora che il giocatore tentasse di registrare il personaggio.

Fix: l'hosting (`network.host_server.WorldHostServer`) non vive più come
attributo di istanza su `WorldsView` — vive in un contenitore condiviso
(`network.host_server.HostServerSlot`), creato UNA VOLTA da `ui/app.py::
DnDApp` e passato a ogni `WorldsView` costruita ad ogni navigazione nella
Sezione Mondi. `WorldsView._host_server` è ora una property che legge/
scrive quel contenitore condiviso — nessun altro punto del file ha dovuto
cambiare (tutti gli usi esistenti di `self._host_server` continuano a
funzionare identici). `will_unmount()` non ferma più l'hosting: si ferma
SOLO tramite `_stop_hosting()` ("Ferma hosting", azione esplicita del
master) o alla chiusura vera del processo (thread daemon).

Se non viene passato un `host_server_slot` (es. un test o un uso che
costruisce `WorldsView` direttamente, come quasi tutti gli altri file di
test di questa suite), se ne crea uno privato — stesso comportamento di
prima per chi non condivide la view tra più istanze: questo è ciò che
permette a TUTTI i test esistenti di restare invariati nonostante questo
fix (verificato: nessuna modifica è stata necessaria altrove).

Copre:
  1. Comportamento di default (nessuno slot passato): identico a prima,
     `will_unmount()` NON ferma più l'hosting nemmeno qui — cambiamento
     di comportamento intenzionale e globale, non solo per chi passa lo
     slot esplicitamente.
  2. Il caso vero del bug: uno slot CONDIVISO tra due istanze di
     `WorldsView` create in sequenza (come farebbe `ui/app.py` ad ogni
     navigazione) — l'hosting avviato sulla prima sopravvive alla sua
     `will_unmount()` ed è visibile, funzionante, DAVVERO raggiungibile
     in rete (join reale via socket) dalla seconda.
  3. `_stop_hosting()` (azione esplicita) ferma comunque l'hosting per
     davvero, sullo slot condiviso.
  4. Due `WorldsView` SENZA slot condiviso restano isolate (nessuna
     hosting-leak accidentale tra istanze scorrelate — il ripiego "slot
     privato" funziona).
  5. `will_unmount()` non solleva se non c'è alcun hosting attivo (nessuna
     regressione sul caso comune, nessun hosting mai avviato).

Eseguire con:
    PYTHONPATH=".venv/lib/python3.13/site-packages:." python3 test_hosting_persistente_navigazione.py
"""

from __future__ import annotations

import os
import sys
import tempfile

_TMP_HOME = tempfile.mkdtemp(prefix="dnd_hosting_persistente_")
os.environ["HOME"] = _TMP_HOME

from data.database import init_db  # noqa: E402
from data.repositories import world_repo  # noqa: E402
from core.world_backend import RemoteBackend  # noqa: E402
from network.host_server import HostServerSlot  # noqa: E402

_PASS = 0
_FAIL: list[str] = []


def check(label: str, cond: bool) -> None:
    global _PASS
    if cond:
        _PASS += 1
    else:
        _FAIL.append(label)
        print(f"  FALLITO: {label}")


def test_will_unmount_no_longer_stops_hosting_default_slot() -> None:
    print("\n[1] will_unmount() NON ferma più l'hosting, anche senza uno slot "
          "condiviso esplicito")
    from ui.views.world.world_view import WorldsView

    world = world_repo.create_world("Mondo Persistenza Default", "dev-master", "Il Master")
    assert world is not None

    wv = WorldsView(on_back_to_home=lambda: None)
    wv._start_hosting(world)
    check("l'hosting è partito", wv._host_server is not None and wv._host_server.is_running)

    wv.will_unmount()
    check("l'hosting resta attivo dopo will_unmount()",
          wv._host_server is not None and wv._host_server.is_running)

    # Pulizia esplicita — non c'è più nessuno che lo farebbe da solo.
    wv._host_server.stop()


def test_hosting_survives_view_recreation_with_shared_slot() -> None:
    print("\n[2] Il caso vero del bug: hosting su uno slot CONDIVISO sopravvive alla "
          "ricreazione della view (simula la navigazione reale di ui/app.py) — e resta "
          "DAVVERO raggiungibile in rete")
    from ui.views.world.world_view import WorldsView

    world = world_repo.create_world("Mondo Persistenza Condivisa", "dev-master", "Il Master")
    assert world is not None
    slot = HostServerSlot()

    # Prima "istanza" della view — es. il master apre la Sezione Mondi e
    # avvia l'hosting.
    wv1 = WorldsView(on_back_to_home=lambda: None, host_server_slot=slot)
    wv1._start_hosting(world)
    server = wv1._host_server
    check("l'hosting è partito sulla prima istanza", server is not None and server.is_running)
    port = server.port
    assert port is not None

    # Il master naviga altrove (es. apre la Modalità Master) — `ui/app.py`
    # ricostruisce l'intera pagina, la vecchia `WorldsView` viene
    # smontata: è ESATTAMENTE lo scenario del bug.
    wv1.will_unmount()

    # Seconda "istanza" della view — es. il master torna nella Sezione
    # Mondi (o semplicemente il ciclo di navigazione dell'app ne crea
    # una nuova per un'altra ragione), con LO STESSO slot passato da
    # `DnDApp` (che vive quanto il processo, mai ricreato).
    wv2 = WorldsView(on_back_to_home=lambda: None, host_server_slot=slot)
    check("la nuova istanza vede lo STESSO WorldHostServer",
          wv2._host_server is server)
    check("l'hosting è ancora davvero in esecuzione", server.is_running)

    # La prova che conta: un giocatore riesce DAVVERO a entrare, via un
    # vero round-trip di rete — non solo "l'oggetto esiste ancora".
    client = RemoteBackend("127.0.0.1", port, "dev-player-persistenza")
    outcome = client.join(world.join_code, server.pin, "Giocatore Persistente")
    check("un giocatore riesce a entrare nell'hosting sopravvissuto alla "
          "navigazione (il bug reale: prima questo avrebbe fallito, host già morto)",
          outcome.status == "pending")

    # Anche la Sezione Mondi tornata a video (wv2) lo vede tra le
    # richieste in sospeso, esattamente come si aspetterebbe il master.
    pending = wv2._host_server.list_pending()
    check("la richiesta di ingresso è visibile dalla nuova istanza della view",
          len(pending) == 1 and pending[0].device_id == "dev-player-persistenza")

    server.stop()


def test_stop_hosting_still_stops_it_for_real() -> None:
    print("\n[3] _stop_hosting() (azione esplicita) ferma comunque l'hosting per davvero, "
          "anche su uno slot condiviso")
    from ui.views.world.world_view import WorldsView

    world = world_repo.create_world("Mondo Stop Esplicito", "dev-master", "Il Master")
    assert world is not None
    slot = HostServerSlot()

    wv = WorldsView(on_back_to_home=lambda: None, host_server_slot=slot)
    wv._start_hosting(world)
    server = wv._host_server
    check("l'hosting è partito", server is not None and server.is_running)

    wv._stop_hosting(world)
    check("_stop_hosting() lo ferma per davvero", not server.is_running)
    check("lo slot condiviso riflette l'arresto", slot.server is None)


def test_two_views_without_shared_slot_stay_isolated() -> None:
    print("\n[4] Due WorldsView SENZA slot condiviso restano isolate (nessun leak "
          "accidentale di hosting tra istanze scorrelate)")
    from ui.views.world.world_view import WorldsView

    world_a = world_repo.create_world("Mondo Isolamento A", "dev-master", "Il Master")
    world_b = world_repo.create_world("Mondo Isolamento B", "dev-master", "Il Master")
    assert world_a is not None and world_b is not None

    wv_a = WorldsView(on_back_to_home=lambda: None)
    wv_a._start_hosting(world_a)
    check("hosting A avviato", wv_a._host_server is not None)

    wv_b = WorldsView(on_back_to_home=lambda: None)
    check("una WorldsView B nuova, senza slot condiviso, NON vede l'hosting di A",
          wv_b._host_server is None)

    wv_a._host_server.stop()


def test_will_unmount_safe_with_no_hosting_active() -> None:
    print("\n[5] will_unmount() non solleva se non c'è alcun hosting attivo "
          "(caso comune: nessuna sessione di hosting mai avviata)")
    from ui.views.world.world_view import WorldsView

    wv = WorldsView(on_back_to_home=lambda: None)
    try:
        wv.will_unmount()
        check("will_unmount() non solleva eccezioni senza hosting attivo", True)
    except Exception as e:  # pragma: no cover - non dovrebbe mai accadere
        check(f"will_unmount() non deve sollevare ({e})", False)


def main() -> int:
    init_db()
    print("=" * 70)
    print("Hosting LAN persistente attraverso la navigazione (fix 2026-08-07)")
    print(f"HOME di test: {_TMP_HOME}")
    print("=" * 70)

    test_will_unmount_no_longer_stops_hosting_default_slot()
    test_hosting_survives_view_recreation_with_shared_slot()
    test_stop_hosting_still_stops_it_for_real()
    test_two_views_without_shared_slot_stay_isolated()
    test_will_unmount_safe_with_no_hosting_active()

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
