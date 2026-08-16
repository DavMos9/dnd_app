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
from data.models import Character, DiaryEntry, MasterCampaignNote
import data.repositories.character_repo as character_repo
from data.repositories import master_repo
from ui.device_identity import resolve_device_id
from ui.theme import muted_text
from ui.widgets import ScrollMemoryListView, wrap_dialog_actions
from ui import design

logger = logging.getLogger(__name__)


class DiarioTab(ScrollMemoryListView):
    """
    Tab diario: voci di sessione con creazione, lettura, modifica, eliminazione.
    Eredita da ft.ListView per scroll corretto in Flet 0.85.3.

    Note condivise dal Master (2026-08-16, richiesta di Davide: "la nota
    nella sezione diario/note del giocatore anche questa già esistente") —
    questo è il vero tab "Diario" che il giocatore usa dalla scheda
    (`SheetView`, tab "diario"): il feature di note condivise era stato
    costruito in un round precedente su `ui/views/diary_view.py::DiaryView`,
    una sezione SEPARATA raggiungibile dalla sidebar generale — non questo
    tab. Nessun bug di sincronizzazione dietro (`test_nota_arriva_a_chi_
    entra_dopo` in `test_note_sharing.py` conferma il meccanismo lato
    replica corretto): il posto sbagliato, semplicemente. Sola lettura qui
    — modificarle resta compito del Master. Si aggiornano da sole tramite
    `SheetView._soft_refresh()` (nessun ciclo di sync proprio: questo tab
    non è mai montato mentre l'utente guarda un altro tab, si affida al
    ridisegno del tab attivo quando `last_synced_seq` del mondo cambia).
    """

    def __init__(self, character: Character, on_refresh: Callable[[], None] | None = None):
        super().__init__(expand=True, spacing=10, padding=16)
        self.character = character
        self._on_refresh = on_refresh
        self._page: ft.Page | None = None
        self._entries: list[DiaryEntry] = character_repo.get_diary_entries(character.id)
        self.device_id: str | None = None
        self._shared_notes: list[MasterCampaignNote] = []
        self._build()

    def did_mount(self):
        self._page = cast(ft.Page, self.page)
        page = self.page
        if page is not None and self.character.world_id:
            page.run_task(self._init_shared_notes)

    async def _init_shared_notes(self) -> None:
        page = self.page
        if page is None:
            return
        self.device_id = await resolve_device_id(page)
        self._load_shared_notes()
        self._build()
        try:
            self.update()
        except RuntimeError:
            pass

    def _load_shared_notes(self) -> None:
        if not self.character.world_id or self.device_id is None:
            return
        self._shared_notes = master_repo.get_notes_visible_to(
            self.character.world_id, self.device_id,
        )

    # ------------------------------------------------------------------
    # Build principale
    # ------------------------------------------------------------------

    def _build(self):
        header_row: list[ft.Control] = [
            ft.Text(
                "Diario di Avventura",
                size=16,
                weight=ft.FontWeight.BOLD,
                color=design.T().text,
                expand=True,
            ),
            ft.ElevatedButton(
                "Nuova Voce",
                icon=ft.Icons.ADD,
                on_click=lambda e: self._on_new_entry(),
                style=ft.ButtonStyle(
                    bgcolor=design.T().primary_fill,
                    color=design.T().on_primary_fill,
                ),
            ),
        ]

        # IMPORTANTE: modificare self.controls IN-PLACE (mai self.controls = [...]).
        # In Flet 0.85.3 la riassegnazione diretta rimpiazza la ControlsList interna
        # che Flutter usa per il rendering → schermata bianca (vedi CLAUDE.md).
        self.controls.clear()
        self.controls.append(ft.Container(
            content=ft.Row(header_row, alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            padding=ft.Padding.only(bottom=4),
        ))

        if not self._entries:
            self.controls.append(self._empty_state())
        else:
            for entry in self._entries:
                self.controls.append(self._entry_card(entry))

        # Note condivise dal Master — in coda alla stessa lista (niente
        # riquadro separato, richiesta di Davide), con un'etichetta di
        # sezione se ce n'è almeno una.
        if self._shared_notes:
            self.controls.append(ft.Container(height=8))
            self.controls.append(ft.Text(
                "NOTE CONDIVISE DAL MASTER", size=10, weight=ft.FontWeight.BOLD,
                color=design.T().text_3, style=ft.TextStyle(letter_spacing=1.5),
            ))
            for note in self._shared_notes:
                self.controls.append(self._shared_note_card(note))

    # ------------------------------------------------------------------
    # Nota condivisa dal Master (sola lettura)
    # ------------------------------------------------------------------

    def _shared_note_card(self, note: MasterCampaignNote) -> ft.Container:
        preview_lines = [l for l in (note.description or "").split("\n") if l.strip()]
        preview = " · ".join(preview_lines[:2])
        if len(preview) > 120:
            preview = preview[:117] + "…"

        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text(
                                note.name or "Senza nome", size=14,
                                weight=ft.FontWeight.BOLD, color=design.T().text,
                                overflow=ft.TextOverflow.ELLIPSIS, expand=True,
                            ),
                            ft.Container(
                                content=ft.Row(
                                    [ft.Icon(ft.Icons.PUBLIC, size=11,
                                             color=design.T().on_primary),
                                     ft.Text("Condivisa dal Master", size=9,
                                             color=design.T().on_primary,
                                             weight=ft.FontWeight.BOLD)],
                                    spacing=3, tight=True,
                                ),
                                bgcolor=design.T().primary, border_radius=8,
                                padding=ft.Padding.symmetric(horizontal=6, vertical=2),
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.START,
                    ),
                    *([ft.Container(height=6),
                       ft.Text(preview, size=12, color=design.T().text_2,
                               max_lines=2, overflow=ft.TextOverflow.ELLIPSIS)]
                      if preview else []),
                ],
                spacing=0,
            ),
            bgcolor=design.T().surface,
            padding=ft.Padding.symmetric(horizontal=14, vertical=12),
            border=ft.Border(
                left=ft.BorderSide(3, design.T().primary),
                top=ft.BorderSide(1, design.T().border),
                right=ft.BorderSide(1, design.T().border),
                bottom=ft.BorderSide(1, design.T().border),
            ),
            border_radius=design.Radius.MD,
        )

    # ------------------------------------------------------------------
    # Stato vuoto
    # ------------------------------------------------------------------

    def _empty_state(self) -> ft.Container:
        return ft.Container(
            content=ft.Column(
                [
                    ft.Icon(ft.Icons.MENU_BOOK_OUTLINED, size=56, color=design.T().border),
                    ft.Container(height=12),
                    ft.Text("Nessuna voce nel diario", size=16,
                            weight=ft.FontWeight.BOLD, color=design.T().text_2),
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
                                        color=design.T().text,
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
                                        icon_color=design.T().text_3,
                                        tooltip="Modifica",
                                        on_click=lambda e, en=entry: self._on_edit_entry(en),
                                        padding=ft.Padding.all(4),
                                    ),
                                    ft.IconButton(
                                        icon=ft.Icons.DELETE_OUTLINE,
                                        icon_size=16,
                                        icon_color=design.T().primary_icon,
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
                                color=design.T().text_2,
                                max_lines=2,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                        ]
                        if preview else []
                    ),
                ],
                spacing=0,
            ),
            bgcolor=design.T().surface,
            padding=ft.Padding.symmetric(horizontal=14, vertical=12),
            border=ft.Border(
                left=ft.BorderSide(3, design.T().primary),
                top=ft.BorderSide(1, design.T().border),
                right=ft.BorderSide(1, design.T().border),
                bottom=ft.BorderSide(1, design.T().border),
            ),
            border_radius=design.Radius.MD,
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
            text_style=ft.TextStyle(size=13, color=design.T().text),
            border_color=design.T().border,
            focused_border_color=design.T().primary,
            bgcolor=design.T().surface,
            label_style=ft.TextStyle(color=design.T().text_2),
            border_radius=design.field_style()['border_radius'])
        f_date = ft.TextField(
            label="Data / Sessione  (es. «Sessione 3», «15 Olarune 998»)",
            value="" if is_new else (entry.session_date or ""),
            text_style=ft.TextStyle(size=13, color=design.T().text),
            border_color=design.T().border,
            focused_border_color=design.T().primary,
            bgcolor=design.T().surface,
            label_style=ft.TextStyle(color=design.T().text_2),
            border_radius=design.field_style()['border_radius'])
        f_content = ft.TextField(
            label="Contenuto",
            value="" if is_new else (entry.content or ""),
            multiline=True,
            min_lines=5,
            max_lines=12,
            text_style=ft.TextStyle(size=13, color=design.T().text),
            border_color=design.T().border,
            focused_border_color=design.T().primary,
            bgcolor=design.T().surface,
            label_style=ft.TextStyle(color=design.T().text_2),
            border_radius=design.field_style()['border_radius'])

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
            title=design.dialog_title("Nuova Voce" if is_new else "Modifica Voce"),
            content=ft.Column(
                [f_title, f_date, f_content],
                spacing=10,
                scroll=ft.ScrollMode.AUTO,
            ),
            actions=wrap_dialog_actions([
                ft.TextButton(
                    "Annulla",
                    on_click=lambda ev: page.pop_dialog() if page else None,
                ),
                ft.ElevatedButton(
                    "Salva",
                    icon=ft.Icons.SAVE_OUTLINED,
                    on_click=save,
                    style=ft.ButtonStyle(
                        bgcolor=design.T().primary_fill,
                        color=design.T().on_primary_fill,
                    ),
                ),
            ]),
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
            title=design.dialog_title("Elimina voce"),
            content=ft.Text(
                f"Eliminare «{entry.title or 'Senza titolo'}»?\nL'operazione non è reversibile.",
                size=13, color=design.T().text,
            ),
            actions=wrap_dialog_actions([
                ft.TextButton(
                    "Annulla",
                    on_click=lambda ev: page.pop_dialog() if page else None,
                ),
                ft.ElevatedButton(
                    "Elimina",
                    icon=ft.Icons.DELETE_OUTLINE,
                    on_click=do_delete,
                    style=ft.ButtonStyle(
                        bgcolor=design.T().primary_fill,
                        color=design.T().on_primary_fill,
                    ),
                ),
            ]),
        ))

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    def _refresh(self):
        self._entries = character_repo.get_diary_entries(self.character.id)
        self._load_shared_notes()
        self.controls.clear()
        self._build()
        try:
            self.update()
        except RuntimeError:
            pass
        # Ripristina la posizione di scroll: il rebuild sopra ricrea tutti i
        # controlli, quindi senza questo la vista tornerebbe in cima ad ogni
        # singola azione (bug B10, revisione 2026-07-26).
        self.restore_scroll()
        if self._on_refresh:
            self._on_refresh()
