"""
Picker "libreria file personaggio" — usato in modalità web (browser, deploy
Docker) per l'IMPORT di un personaggio esportato in precedenza, esattamente
con lo stesso principio già stabilito e validato da ui/image_library.py
(2026-07-12): ft.FilePicker è strutturalmente non utilizzabile in web mode
(bug upstream Flet confermato, vedi CLAUDE.md), quindi al posto di un vero
upload dal client, Davide copia il file .dndchar sul server via SSH
(scp/rsync) in una cartella dedicata — vedi
data/database.py → get_character_exports_path() — e questo modulo mostra un
picker con l'elenco dei file lì presenti, con un'anteprima di nome/classe/
livello letta dal contenuto del file prima di confermare la selezione.

L'EXPORT in modalità web non passa da questo modulo: scrive direttamente il
file nella stessa cartella (vedi home_view.py → _on_export_click), senza
bisogno di alcuna interazione — non c'è nulla da "scegliere" in export.

Usato SOLO quando page.web è True — su desktop nativo l'export/import
passano dai dialoghi nativi del SO (vedi home_view.py), che permettono di
scegliere liberamente qualsiasi percorso, non solo questa cartella fissa.
"""

import logging
import os
from typing import Callable

import flet as ft

from data.database import get_character_exports_path
from data.repositories.character_export import (
    load_json_string,
    peek_character_summary,
)
from ui import design

logger = logging.getLogger(__name__)

_ALLOWED_EXTENSIONS = {".dndchar", ".json"}


def _list_export_files() -> list[tuple[str, str]]:
    """
    Ritorna [(filename, full_path), ...] per tutti i file .dndchar/.json
    nella cartella di export, ordinati per data di modifica decrescente
    (i file appena copiati via scp compaiono per primi) — stesso identico
    pattern di image_library.py → _list_library_images().

    Non solleva mai eccezioni: un errore di lettura della cartella ritorna
    lista vuota, il chiamante mostra lo stato vuoto con il path esatto.
    """
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


def _peek_file(path: str) -> dict[str, str] | None:
    """
    Legge un file e ne estrae l'anteprima (nome/classe/livello) senza
    importarlo — None se il file non è un export leggibile/valido (mostrato
    come card "non valida" invece di essere escluso silenziosamente, così
    l'utente capisce che il file è lì ma illeggibile).
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError as exc:
        logger.warning("Impossibile leggere %s: %s", path, exc)
        return None
    data = load_json_string(text)
    if data is None:
        return None
    return peek_character_summary(data)


def show_character_import_picker(page: ft.Page, on_select: Callable[[str], None]):
    """
    Mostra un AlertDialog con l'elenco dei file .dndchar/.json presenti
    nella cartella di export, ciascuno con anteprima nome/classe/livello.
    Click su una card → on_select(path) e chiude il dialog.

    Include un bottone "Ricarica" per rileggere la cartella senza chiudere
    il dialog — utile se si copiano nuovi file via scp a dialog aperto.
    """
    exp_dir = get_character_exports_path()
    body = ft.Column(spacing=0, scroll=ft.ScrollMode.AUTO, tight=True)
    body_container = ft.Container(content=body, width=380, height=420)

    def _select(path: str):
        page.pop_dialog()
        on_select(path)

    def _card(name: str, path: str) -> ft.Container:
        info = _peek_file(path)
        if info:
            level_part = f" · Liv. {info['level']}" if info.get("level") else ""
            subtitle = f"{info.get('class_name', '')}{level_part}  ·  {info.get('race', '')}".strip(" ·")
            title_text = info.get("name") or name
            icon = ft.Icon(ft.Icons.PERSON, color=design.T().primary, size=24)
            clickable = True
        else:
            title_text = name
            subtitle = "File non riconosciuto come export personaggio"
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
                    icon_color=design.T().primary,
                    tooltip="Importa questo personaggio",
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
                    f"Copia il file .dndchar in questa cartella sul server:\n{exp_dir}",
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
        title=ft.Text("Importa Personaggio", size=14, weight=ft.FontWeight.BOLD,
                      color=design.T().text),
        bgcolor=design.T().surface,
        content=body_container,
        actions=[
            ft.TextButton("Ricarica", icon=ft.Icons.REFRESH, on_click=_refresh,
                          style=ft.ButtonStyle(color=design.T().text_2)),
            ft.TextButton("Chiudi", on_click=lambda e: page.pop_dialog(),
                          style=ft.ButtonStyle(color=design.T().primary)),
        ],
    ))
