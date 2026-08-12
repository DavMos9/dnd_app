"""
Picker "libreria file mondo" — usato in modalità web per l'IMPORT di un
mondo esportato in precedenza (`.dndworld`, passo 9D) — stesso identico
principio di `ui/character_transfer.py` (2026-07-24): `ft.FilePicker` è
strutturalmente non utilizzabile in web mode, quindi Davide copia il file
sul server via SSH/scp nella stessa cartella condivisa già usata per
`.dndchar` (`data/database.py::get_character_exports_path()` — nessuna
cartella nuova, riusa quella esistente) e questo modulo mostra un picker
con l'elenco dei file `.dndworld` lì presenti, con un'anteprima
nome/membri/personaggi letta dal contenuto del file prima di confermare.

L'EXPORT in modalità web non passa da questo modulo, stesso principio di
`character_transfer.py`: scrive direttamente il file nella stessa cartella
(vedi `ui/views/world/world_view.py`).
"""

import logging
import os
from typing import Callable

import flet as ft

from data.database import get_character_exports_path
from data.repositories.world_export import load_json_string, peek_world_summary
from ui import design
from ui.widgets import wrap_dialog_actions

logger = logging.getLogger(__name__)

_ALLOWED_EXTENSIONS = {".dndworld", ".json"}


def _list_export_files() -> list[tuple[str, str]]:
    """Stesso identico pattern di `character_transfer._list_export_files()`,
    filtrato per `.dndworld`/`.json` invece di `.dndchar`/`.json` — stessa
    cartella condivisa, i due tipi di file convivono lì senza conflitto
    (nomi generati con timestamp, mai identici)."""
    exp_dir = get_character_exports_path()
    try:
        entries: list[tuple[str, str, float]] = []
        for name in os.listdir(exp_dir):
            full_path = os.path.join(exp_dir, name)
            if not os.path.isfile(full_path):
                continue
            ext = os.path.splitext(name)[1].lower()
            if ext not in _ALLOWED_EXTENSIONS:
                continue
            entries.append((name, full_path, os.path.getmtime(full_path)))
        entries.sort(key=lambda e: e[2], reverse=True)
        return [(name, path) for name, path, _ in entries]
    except OSError as exc:
        logger.error("Impossibile leggere la cartella export (%s): %s", exp_dir, exc)
        return []


def _peek_file(path: str) -> dict | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError as exc:
        logger.warning("Impossibile leggere %s: %s", path, exc)
        return None
    data = load_json_string(text)
    if data is None:
        return None
    return peek_world_summary(data)


def show_world_import_picker(page: ft.Page, on_select: Callable[[str], None]):
    """Mostra un AlertDialog con l'elenco dei file `.dndworld`/`.json`
    presenti nella cartella di export, ciascuno con anteprima nome/membri/
    personaggi. Click su una card → `on_select(path)` e chiude il dialog."""
    exp_dir = get_character_exports_path()
    body = ft.Column(spacing=0, scroll=ft.ScrollMode.AUTO, tight=True)
    body_container = ft.Container(content=body, width=380, height=420)

    def _select(path: str):
        page.pop_dialog()
        on_select(path)

    def _card(name: str, path: str) -> ft.Container:
        info = _peek_file(path)
        if info:
            archived_part = f" · {info['archived_count']} rimossi" if info.get("archived_count") else ""
            subtitle = (f"{info['member_count']} membri · {info['character_count']} personaggi"
                        f"{archived_part}")
            title_text = info.get("name") or name
            icon = ft.Icon(ft.Icons.PUBLIC, color=design.T().magic, size=24)
            clickable = True
        else:
            title_text = name
            subtitle = "File non riconosciuto come export di un mondo"
            icon = ft.Icon(ft.Icons.ERROR_OUTLINE, color=design.T().text_3, size=24)
            clickable = False

        row_content = ft.Row(
            [
                ft.Container(
                    content=icon, width=40, height=40, border_radius=design.Radius.MD,
                    bgcolor=design.T().surface_alt, alignment=ft.Alignment.CENTER,
                    shadow=design.elevation(1),
                ),
                ft.Column(
                    [
                        ft.Text(title_text, size=13, weight=ft.FontWeight.BOLD,
                                color=design.T().text, max_lines=1),
                        ft.Text(subtitle, size=11, color=design.T().text_3, max_lines=1),
                    ],
                    spacing=2, expand=True, tight=True,
                ),
            ] + ([
                ft.IconButton(
                    ft.Icons.DOWNLOAD_OUTLINED, icon_size=22,
                    icon_color=design.T().magic,
                    tooltip="Importa questo mondo",
                    on_click=lambda e, p=path: _select(p),
                ),
            ] if clickable else []),
            spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        return ft.Container(
            content=row_content,
            padding=ft.Padding.symmetric(vertical=6, horizontal=6),
            border=ft.Border.only(bottom=ft.BorderSide(1, design.T().border)),
            on_click=(lambda e, p=path: _select(p)) if clickable else None,
            ink=clickable,
        )

    def _empty_state() -> ft.Column:
        return ft.Column(
            [
                ft.Icon(ft.Icons.FOLDER_OPEN_OUTLINED, size=40, color=design.T().border),
                ft.Container(height=8),
                ft.Text("Nessun file trovato", size=13,
                        weight=ft.FontWeight.BOLD, color=design.T().text_3),
                ft.Container(height=4),
                ft.Text(
                    f"Copia il file .dndworld in questa cartella sul server:\n{exp_dir}",
                    size=11, color=design.T().text_3,
                    text_align=ft.TextAlign.CENTER, selectable=True,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
            expand=True,
        )

    def _refresh(e=None):
        files = _list_export_files()
        body.controls.clear()
        if not files:
            body.controls.append(_empty_state())
        else:
            for name, path in files:
                body.controls.append(_card(name, path))
        try:
            body.update()
        except RuntimeError:
            pass

    _refresh()

    page.show_dialog(ft.AlertDialog(
        modal=True,
        title=design.dialog_title("Importa Mondo"),
        content=body_container,
        actions=wrap_dialog_actions([
            ft.TextButton("Ricarica", icon=ft.Icons.REFRESH, on_click=_refresh,
                          style=ft.ButtonStyle(color=design.T().text_2)),
            ft.TextButton("Chiudi", on_click=lambda e: page.pop_dialog(),
                          style=ft.ButtonStyle(color=design.T().primary)),
        ]),
    ))
