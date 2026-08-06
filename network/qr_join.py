"""
QR d'ingresso per l'hosting LAN — generazione lato host (richiesta di Davide,
2026-08-06) e scansione lato giocatore (2026-08-06, sessione successiva:
`ui/views/world/qr_scanner_view.py`, passo 5 di
`dnd_app/docs/multiplayer_design.md` §9, "Scoperta e comodità").

Il contenuto del QR è testo semplice leggibile, NON un URI/deep link:
qualunque fotocamera del telefono (non serve un'app dedicata) lo mostra come
testo che il giocatore può leggere o copiare a mano — `parse_join_text()`
sotto è lo stesso formato riletto da uno scanner in-app, ma l'inserimento
manuale resta sempre possibile come ripiego (stessa filosofia della scoperta
automatica via broadcast UDP, passo 5).

Generazione e parsing vivono nello stesso modulo apposta: un solo posto dove
il formato del testo può cambiare, mai due copie che potrebbero disallinearsi.

Nessuna dipendenza da Flet, come tutto `network/*.py` e `core/*.py`.
"""

from __future__ import annotations

import base64
import io
import logging
import re

import qrcode

logger = logging.getLogger(__name__)

#: Prima riga del testo generato da `build_join_text()` — usata da
#: `parse_join_text()` per rifiutare subito un QR che non è dei nostri
#: (un codice sconosciuto inquadrato per sbaglio), stesso principio difensivo
#: di `network.protocol.DISCOVERY_MAGIC` per gli annunci broadcast.
_JOIN_TEXT_MAGIC = "D&D Companion — ingresso in LAN"


def build_join_text(world_name: str, host: str, port: int, join_code: str, pin: str) -> str:
    """
    Testo leggibile incorporato nel QR — gli stessi 4 dati richiesti dal
    dialogo "Unisciti in LAN" (indirizzo, porta, codice, PIN), più il nome
    del mondo per contesto quando in una stessa serata si ospitano più
    mondi in sequenza.
    """
    return (
        f"{_JOIN_TEXT_MAGIC}\n"
        f"Mondo: {world_name}\n"
        f"Host: {host}\n"
        f"Porta: {port}\n"
        f"Codice: {join_code}\n"
        f"PIN: {pin}"
    )


def parse_join_text(text: str) -> dict | None:
    """
    Legge il testo prodotto da `build_join_text()` — l'operazione inversa,
    usata da `ui/views/world/qr_scanner_view.py` dopo che uno scatto della
    fotocamera è stato decodificato come QR (`pyzbar`). Ritorna `None` se il
    testo non è nel formato atteso (non un QR nostro, o un QR corrotto/
    illeggibile parzialmente) — fail-closed, mai un dizionario parzialmente
    valorizzato: chi chiama deve poter assumere che un risultato non-`None`
    abbia TUTTI e 4 i campi.

    Tollerante a spazi bianchi finali per riga (alcuni lettori QR li
    aggiungono) ma non al resto del formato — non un parser permissivo:
    se qualcosa non torna è meglio dichiarare "QR non riconosciuto" e
    lasciare il giocatore inserire i dati a mano, piuttosto che tentare un
    ingresso con un indirizzo o una porta sbagliati.

    Ritorna un dizionario con chiavi `host: str`, `port: int`,
    `join_code: str`, `pin: str` (più `world_name: str`, solo per mostrare
    conferma in UI, non usato dal comando di ingresso).
    """
    if not text or not text.strip().startswith(_JOIN_TEXT_MAGIC):
        return None

    patterns = {
        "world_name": r"^Mondo:\s*(.+)$",
        "host": r"^Host:\s*(.+)$",
        "port": r"^Porta:\s*(\d+)$",
        "join_code": r"^Codice:\s*(\S+)$",
        "pin": r"^PIN:\s*(\d+)$",
    }
    found: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        for key, pattern in patterns.items():
            if key in found:
                continue
            m = re.match(pattern, line)
            if m:
                found[key] = m.group(1).strip()

    required = ("host", "port", "join_code", "pin")
    if not all(k in found for k in required):
        return None
    try:
        port = int(found["port"])
    except ValueError:
        return None
    if not (0 < port < 65536):
        return None

    return {
        "world_name": found.get("world_name", ""),
        "host": found["host"],
        "port": port,
        "join_code": found["join_code"],
        "pin": found["pin"],
    }


def generate_qr_png_base64(data: str, *, box_size: int = 8, border: int = 2) -> str:
    """
    Genera un QR per `data` e lo ritorna come PNG codificato in base64,
    pronto per un `ft.Image(src=f"data:image/png;base64,{...}")` (MAI
    `src_base64`: non esiste in questa versione di Flet, vedi
    `dnd_app/docs/regole_flet_api.md`).

    Solleva l'eccezione originale se la generazione fallisce (dipendenza
    mancante, dato troppo lungo per la versione massima del QR, ecc.) —
    nessun fallback silenzioso qui: è compito del chiamante (la UI) decidere
    come mostrare l'assenza del QR, loggando comunque l'errore.
    """
    qr = qrcode.QRCode(
        version=None,  # dimensione automatica (vedi fit=True sotto)
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(data)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")
