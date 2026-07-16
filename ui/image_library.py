"""
Libreria immagini condivisa — picker per foto profilo e immagini mappa in
modalità web (browser, deploy Docker), dove ft.FilePicker è strutturalmente
non utilizzabile (bug upstream Flet confermato, vedi CLAUDE.md 2026-07-12,
issue flet-dev/flet#6040/#6250/#6251).

Al posto di un upload dal client, Davide carica le immagini a mano sul
server via SSH (scp/rsync) in una cartella dedicata — vedi
data/database.py → get_image_library_path() — e questo modulo mostra un
picker con le miniature di quella cartella. Selezionare un'immagine
richiama semplicemente il path locale, esattamente come già avviene per
mobile nativo/desktop (_load_photo() in profilo_tab.py,
_load_image_base64() in maps_view.py): nessun protocollo di controllo Flet
coinvolto, solo lettura diretta del filesystem del server.

Usato SOLO quando page.web è True — su mobile nativo/desktop il file
picker vero (ft.FilePicker / dialogo nativo del SO) funziona già
correttamente e non deve essere sostituito.
"""

import base64
import io
import logging
import os
from typing import Callable

import flet as ft

from config.settings import *
from data.database import get_image_library_path

logger = logging.getLogger(__name__)

_ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
_THUMB_MAX_SIZE = (160, 160)


def _data_uri(b64: str) -> str:
    """
    Rileva il mime dai magic bytes e costruisce il data URI — stesso
    identico pattern già duplicato in app.py/home_view.py/profilo_tab.py/
    maps_view.py (vedi CLAUDE.md), replicato qui per coerenza col resto
    del progetto piuttosto che introdurre una nuova astrazione condivisa
    non richiesta da questo task.
    """
    if not b64:
        return ""
    try:
        raw = base64.b64decode(b64[:16])
    except Exception:
        raw = b""
    if raw.startswith(b"\x89PNG"):
        mime = "image/png"
    elif raw.startswith(b"GIF8"):
        mime = "image/gif"
    elif raw[:4] == b"RIFF":
        mime = "image/webp"
    else:
        mime = "image/jpeg"
    return f"data:{mime};base64,{b64}"


def _make_thumbnail_b64(path: str) -> str:
    """
    Genera una miniatura JPEG ridotta (max 160x160) e la ritorna come
    base64 — la libreria può contenere foto a piena risoluzione, ridurle
    qui evita di appesantire il rendering della griglia.

    Non solleva mai eccezioni: un file non leggibile come immagine (es.
    corrotto, o un formato non supportato nonostante l'estensione)
    ritorna stringa vuota — il chiamante mostra un placeholder al suo
    posto invece di far fallire l'intero picker per un file solo.
    """
    try:
        from PIL import Image as PILImage  # type: ignore[import-untyped]
        with PILImage.open(path) as img:
            img = img.convert("RGB")
            img.thumbnail(_THUMB_MAX_SIZE)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=80)
            return base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception as exc:
        logger.warning("Impossibile generare miniatura per %s: %s", path, exc)
        return ""


def _list_library_images() -> list[tuple[str, str]]:
    """
    Ritorna [(filename, full_path), ...] per tutte le immagini nella
    cartella libreria, filtrate per estensione e ordinate per data di
    modifica decrescente (i file appena copiati via scp compaiono per
    primi, comodo per ritrovare subito l'ultimo caricato).

    Non solleva mai eccezioni: un errore di lettura della cartella (es.
    permessi) ritorna lista vuota — il chiamante mostra lo stato vuoto
    con il path esatto, così l'utente capisce dove copiare i file anche
    in caso di problema.
    """
    lib_dir = get_image_library_path()
    try:
        entries: list[tuple[str, str, float]] = []
        for name in os.listdir(lib_dir):
            full_path = os.path.join(lib_dir, name)
            if not os.path.isfile(full_path):
                continue
            ext = os.path.splitext(name)[1].lower()
            if ext not in _ALLOWED_EXTENSIONS:
                continue
            entries.append((name, full_path, os.path.getmtime(full_path)))
        entries.sort(key=lambda e: e[2], reverse=True)
        return [(name, path) for name, path, _ in entries]
    except OSError as exc:
        logger.error("Impossibile leggere la libreria immagini (%s): %s", lib_dir, exc)
        return []


def show_image_library_picker(page: ft.Page, on_select: Callable[[str], None]):
    """
    Mostra un AlertDialog con le miniature delle immagini nella cartella
    libreria (get_image_library_path()). Click su una card → on_select(path)
    e chiude il dialog.

    Include un bottone "Ricarica" per rileggere la cartella senza dover
    chiudere e riaprire il dialog — utile se si caricano nuovi file via
    scp proprio mentre il dialog è aperto.
    """
    lib_dir = get_image_library_path()
    body = ft.Column(spacing=0, scroll=ft.ScrollMode.AUTO, tight=True)
    body_container = ft.Container(content=body, width=380, height=420)

    def _select(path: str):
        page.pop_dialog()
        on_select(path)

    def _card(name: str, path: str) -> ft.Container:
        b64 = _make_thumbnail_b64(path)
        if b64:
            thumb = ft.Container(
                content=ft.Image(src=_data_uri(b64), fit=ft.BoxFit.COVER),
                width=80, height=60, border_radius=4,
                clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                border=ft.Border.all(1, COLOR_BORDER),
            )
        else:
            thumb = ft.Container(
                content=ft.Icon(ft.Icons.BROKEN_IMAGE_OUTLINED, size=28,
                                color=COLOR_TEXT_MUTED),
                width=80, height=60, border_radius=4,
                bgcolor=COLOR_BG_SECONDARY,
                border=ft.Border.all(1, COLOR_BORDER),
                alignment=ft.Alignment.CENTER,
            )

        return ft.Container(
            content=ft.Row(
                [
                    thumb,
                    ft.Text(name, size=12, color=COLOR_TEXT_PRIMARY, expand=True,
                            max_lines=2, selectable=True),
                    ft.IconButton(
                        ft.Icons.CHECK_CIRCLE_OUTLINE, icon_size=22,
                        icon_color=COLOR_ACCENT_CRIMSON,
                        tooltip="Seleziona questa immagine",
                        on_click=lambda e, p=path: _select(p),
                    ),
                ],
                spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(vertical=6, horizontal=6),
            border=ft.Border.only(bottom=ft.BorderSide(1, COLOR_BORDER)),
            on_click=lambda e, p=path: _select(p),
            ink=True,
        )

    def _empty_state() -> ft.Column:
        return ft.Column(
            [
                ft.Icon(ft.Icons.PHOTO_LIBRARY_OUTLINED, size=40, color=COLOR_BORDER),
                ft.Container(height=8),
                ft.Text("Nessuna immagine trovata", size=13,
                        weight=ft.FontWeight.BOLD, color=COLOR_TEXT_MUTED),
                ft.Container(height=4),
                ft.Text(
                    f"Copia le immagini in questa cartella sul server:\n{lib_dir}",
                    size=11, color=COLOR_TEXT_MUTED,
                    text_align=ft.TextAlign.CENTER, selectable=True,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
            expand=True,
        )

    def _refresh(e=None):
        images = _list_library_images()
        body.controls.clear()
        if not images:
            body.controls.append(_empty_state())
        else:
            for name, path in images:
                body.controls.append(_card(name, path))
        try:
            body.update()
        except RuntimeError:
            pass

    _refresh()

    page.show_dialog(ft.AlertDialog(
        modal=True,
        title=ft.Text("Libreria immagini", size=14, weight=ft.FontWeight.BOLD,
                      color=COLOR_TEXT_TITLE),
        bgcolor=COLOR_BG_CARD,
        content=body_container,
        actions=[
            ft.TextButton("Ricarica", icon=ft.Icons.REFRESH, on_click=_refresh,
                          style=ft.ButtonStyle(color=COLOR_TEXT_SECONDARY)),
            ft.TextButton("Chiudi", on_click=lambda e: page.pop_dialog(),
                          style=ft.ButtonStyle(color=COLOR_ACCENT_CRIMSON)),
        ],
    ))
