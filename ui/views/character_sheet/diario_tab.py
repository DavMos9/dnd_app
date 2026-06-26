"""
Tab Diario della scheda personaggio.

Struttura (ListView scrollabile):
  - Pulsante "Nuova Voce"  — apre dialog con titolo, data sessione, contenuto
  - Lista voci             — card per ogni voce con titolo, data, anteprima testo
                             click → espande/modifica, tasto elimina con conferma
"""

import flet as ft
import logging
from typing import Callable, cast
from config.settings import *
from data.models import Character, DiaryEntry
import data.repositories.character_repo as character_repo
from ui.theme import section_header, body_text, muted_text, label_text

logger = logging.getLogger(__name__)


class DiarioTab(ft.ListView):
    """
    Tab diario: voci di sessione con creazione, lettura, modifica, eliminazione.
    Eredita da ft.ListView per scroll corretto in Flet 0.85.3.
    """

    def __init__(self, character: Character, on_refresh: Callable[[], None] | None = None):
        super().__init__(expand=True, spacing=10, padding=16)
        self.character = character
        self._on_refresh = on_refresh
        self._page: ft.Page | None = None
        self._entries: list[DiaryEntry] = character_repo.get_diary_entries(character.id)
        self._build()

    def did_mount(self):
        self._page = cast(ft.Page, self.page)

    # ------------------------------------------------------------------
    # Build principale
    # ------------------------------------------------------------------

    def _build(self):
        header_row: list[ft.Control] = [
            ft.Text(
                "Diario di Avventura",
                size=16,
                weight=ft.FontWeight.BOLD,
                color=COLOR_TEXT_TITLE,
                expand=True,
            ),
            ft.ElevatedButton(
                "Nuova Voce",
                icon=ft.Icons.ADD,
                on_click=lambda e: self._on_new_entry(),
                style=ft.ButtonStyle(
                    bgcolor=COLOR_ACCENT_CRIMSON,
                    color="#ffffff",
                    shape=ft.RoundedRectangleBorder(radius=4),
                ),
            ),
        ]

        self.controls = [
            ft.Container(
                content=ft.Row(header_row, alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                padding=ft.Padding.only(bottom=4),
            ),
        ]

        if not self._entries:
            self.controls.append(self._empty_state())
        else:
            for entry in self._entries:
                self.controls.append(self._entry_card(entry))

    # ------------------------------------------------------------------
    # Stato vuoto
    # ------------------------------------------------------------------

    def _empty_state(self) -> ft.Container:
        return ft.Container(
            content=ft.Column(
                [
                    ft.Icon(ft.Icons.MENU_BOOK_OUTLINED, size=56, color=COLOR_BORDER),
                    ft.Container(height=12),
                    ft.Text("Nessuna voce nel diario", size=16,
                            weight=ft.FontWeight.BOLD, color=COLOR_TEXT_SECONDARY),
                    ft.Container(height=6),
                    muted_text("Premi «Nuova Voce» per iniziare a scrivere\nle tue avventure.", 13),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=0,
            ),
            expand=True,
            padding=ft.Padding.symmetric(horizontal=24, vertical=48),
            alignment=ft.Alignment.CENTER,
        )

    # ------------------------------------------------------------------
    # Card voce
    # ------------------------------------------------------------------

    def _entry_card(self, entry: DiaryEntry) -> ft.Container:
        # Anteprima: prime 2 righe di testo
        preview_lines = [l for l in (entry.content or "").split("\n") if l.strip()]
        preview = " · ".join(preview_lines[:2])
        if len(preview) > 120:
            preview = preview[:117] + "…"

        date_label = entry.session_date or entry.created_at[:10] if entry.created_at else ""

        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text(
                                        entry.title or "Senza titolo",
                                        size=14,
                                        weight=ft.FontWeight.BOLD,
                                        color=COLOR_TEXT_TITLE,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                    ),
                                    muted_text(date_label, 11),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            ft.Row(
                                [
                                    ft.IconButton(
                                        icon=ft.Icons.EDIT_OUTLINED,
                                        icon_size=16,
                                        icon_color=COLOR_TEXT_MUTED,
                                        tooltip="Modifica",
                                        on_click=lambda e, en=entry: self._on_edit_entry(en),
                                        padding=ft.Padding.all(4),
                                    ),
                                    ft.IconButton(
                                        icon=ft.Icons.DELETE_OUTLINE,
                                        icon_size=16,
                                        icon_color=COLOR_ACCENT_CRIMSON,
                                        tooltip="Elimina",
                                        on_click=lambda e, en=entry: self._on_delete_entry(en),
                                        padding=ft.Padding.all(4),
                                    ),
                                ],
                                spacing=0,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.START,
                    ),
                    *(
                        [
                            ft.Container(height=6),
                            ft.Text(
                                preview,
                                size=12,
                                color=COLOR_TEXT_SECONDARY,
                                max_lines=2,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                        ]
                        if preview else []
                    ),
                ],
                spacing=0,
            ),
            bgcolor=COLOR_BG_CARD,
            padding=ft.Padding.symmetric(horizontal=14, vertical=12),
            border=ft.Border(
                left=ft.BorderSide(3, COLOR_ACCENT_CRIMSON),
                top=ft.BorderSide(1, COLOR_BORDER),
                right=ft.BorderSide(1, COLOR_BORDER),
                bottom=ft.BorderSide(1, COLOR_BORDER),
            ),
            border_radius=6,
        )

    # ------------------------------------------------------------------
    # Dialog nuova voce
    # ------------------------------------------------------------------

    def _on_new_entry(self):
        page = self._page
        if page is None:
            return
        self._open_entry_dialog(page, entry=None)

    # ------------------------------------------------------------------
    # Dialog modifica voce
    # ------------------------------------------------------------------

    def _on_edit_entry(self, entry: DiaryEntry):
        page = self._page
        if page is None:
            return
        self._open_entry_dialog(page, entry=entry)

    # ------------------------------------------------------------------
    # Dialog condiviso (crea / modifica)
    # ------------------------------------------------------------------

    def _open_entry_dialog(self, page: ft.Page, entry: DiaryEntry | None):
        is_new = entry is None

        f_title = ft.TextField(
            label="Titolo",
            value="" if is_new else (entry.title or ""),
            autofocus=True,
            text_style=ft.TextStyle(size=13, color=COLOR_TEXT_PRIMARY),
            border_color=COLOR_BORDER,
            focused_border_color=COLOR_ACCENT_CRIMSON,
            bgcolor=COLOR_BG_CARD,
            label_style=ft.TextStyle(color=COLOR_TEXT_SECONDARY),
        )
        f_date = ft.TextField(
            label="Data / Sessione  (es. «Sessione 3», «15 Olarune 998»)",
            value="" if is_new else (entry.session_date or ""),
            text_style=ft.TextStyle(size=13, color=COLOR_TEXT_PRIMARY),
            border_color=COLOR_BORDER,
            focused_border_color=COLOR_ACCENT_CRIMSON,
            bgcolor=COLOR_BG_CARD,
            label_style=ft.TextStyle(color=COLOR_TEXT_SECONDARY),
        )
        f_content = ft.TextField(
            label="Contenuto",
            value="" if is_new else (entry.content or ""),
            multiline=True,
            min_lines=5,
            max_lines=12,
            text_style=ft.TextStyle(size=13, color=COLOR_TEXT_PRIMARY),
            border_color=COLOR_BORDER,
            focused_border_color=COLOR_ACCENT_CRIMSON,
            bgcolor=COLOR_BG_CARD,
            label_style=ft.TextStyle(color=COLOR_TEXT_SECONDARY),
        )

        def save(ev):
            if page is None:
                return
            title = (f_title.value or "").strip() or "Senza titolo"
            date = (f_date.value or "").strip()
            content = (f_content.value or "").strip()
            if is_new:
                character_repo.create_diary_entry(self.character.id, title, content, date)
            else:
                assert entry is not None
                character_repo.update_diary_entry(entry.id, title, content, date)
            page.pop_dialog()
            self._refresh()

        page.show_dialog(ft.AlertDialog(
            title=ft.Text(
                "Nuova Voce" if is_new else "Modifica Voce",
                size=14, weight=ft.FontWeight.BOLD, color=COLOR_TEXT_TITLE,
            ),
            content=ft.Column(
                [f_title, f_date, f_content],
                spacing=10,
                scroll=ft.ScrollMode.AUTO,
            ),
            actions=[
                ft.TextButton(
                    "Annulla",
                    on_click=lambda ev: page.pop_dialog() if page else None,
                ),
                ft.ElevatedButton(
                    "Salva",
                    icon=ft.Icons.SAVE_OUTLINED,
                    on_click=save,
                    style=ft.ButtonStyle(
                        bgcolor=COLOR_ACCENT_CRIMSON,
                        color="#ffffff",
                        shape=ft.RoundedRectangleBorder(radius=4),
                    ),
                ),
            ],
            bgcolor=COLOR_BG_CARD,
        ))

    # ------------------------------------------------------------------
    # Dialog conferma eliminazione
    # ------------------------------------------------------------------

    def _on_delete_entry(self, entry: DiaryEntry):
        page = self._page
        if page is None:
            return

        def do_delete(ev):
            if page is None:
                return
            character_repo.delete_diary_entry(entry.id)
            page.pop_dialog()
            self._refresh()

        page.show_dialog(ft.AlertDialog(
            title=ft.Text("Elimina voce", size=14,
                          weight=ft.FontWeight.BOLD, color=COLOR_TEXT_TITLE),
            content=ft.Text(
                f"Eliminare «{entry.title or 'Senza titolo'}»?\nL'operazione non è reversibile.",
                size=13, color=COLOR_TEXT_PRIMARY,
            ),
            actions=[
                ft.TextButton(
                    "Annulla",
                    on_click=lambda ev: page.pop_dialog() if page else None,
                ),
                ft.ElevatedButton(
                    "Elimina",
                    icon=ft.Icons.DELETE_OUTLINE,
                    on_click=do_delete,
                    style=ft.ButtonStyle(
                        bgcolor=COLOR_ACCENT_CRIMSON,
                        color="#ffffff",
                        shape=ft.RoundedRectangleBorder(radius=4),
                    ),
                ),
            ],
            bgcolor=COLOR_BG_CARD,
        ))

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    def _refresh(self):
        self._entries = character_repo.get_diary_entries(self.character.id)
        self.controls.clear()
        self._build()
        try:
            self.update()
        except RuntimeError:
            pass
        if self._on_refresh:
            self._on_refresh()
