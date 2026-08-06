"""
QR d'ingresso per l'hosting LAN — generazione lato host (richiesta di Davide,
2026-08-06). Copre SOLO la generazione: nessun controllo camera/QR ufficiale
esiste in Flet (verificato prima di scrivere questo modulo — vedi
`dnd_app/docs/multiplayer_design.md` §9, nota sul passo 5 "Scoperta e
comodità"), quindi la scansione lato giocatore resta per ora un'azione
manuale: il giocatore continua a inserire indirizzo, codice e PIN nel
dialogo "Unisciti in LAN" di `ui/views/world/world_view.py`.

Il contenuto del QR è testo semplice leggibile, NON un URI/deep link:
qualunque fotocamera del telefono (non serve un'app dedicata) lo mostra come
testo che il giocatore può leggere o copiare a mano, riducendo gli errori di
trascrizione del PIN letto a distanza dallo schermo del master. Se in futuro
si costruirà uno scanner dentro l'app (passo 5, o l'opzione "WebView + jsQR"
valutata e rimandata insieme a questo lavoro), questo stesso formato può
essere riletto da un parser dedicato senza cambiare cosa genera l'host.

Nessuna dipendenza da Flet, come tutto `network/*.py` e `core/*.py`.
"""

from __future__ import annotations

import base64
import io
import logging

import qrcode

logger = logging.getLogger(__name__)


def build_join_text(world_name: str, host: str, port: int, join_code: str, pin: str) -> str:
    """
    Testo leggibile incorporato nel QR — gli stessi 4 dati richiesti dal
    dialogo "Unisciti in LAN" (indirizzo, porta, codice, PIN), più il nome
    del mondo per contesto quando in una stessa serata si ospitano più
    mondi in sequenza.
    """
    return (
        "D&D Companion — ingresso in LAN\n"
        f"Mondo: {world_name}\n"
        f"Host: {host}\n"
        f"Porta: {port}\n"
        f"Codice: {join_code}\n"
        f"PIN: {pin}"
    )


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
