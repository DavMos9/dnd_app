"""
Vista "Incontri" della Modalità Master — lista degli incontri di
combattimento (non archiviati) + creazione, e gestione della navigazione
verso il tracker a schermo intero di un singolo incontro
(`MasterEncounterView`). Vedi `dnd_app/docs/master_section_design.md` per il
design completo.

Questa vista è self-contained: gestisce da sola lo stato "lista" vs
"incontro aperto" al proprio interno (nessuna modifica al routing di
`master_view.py`, che la istanzia senza argomenti — stesso principio già
in uso per il cambio tab dentro `MasterView`).
"""

import logging
from typing import Any

import flet as ft

from data.models import MasterEncounter
from data.repositories import master_repo
from ui.theme import title_text, muted_text, primary_button
from ui.views.master.master_encounter_view import MasterEncounterView
from ui.widgets import wrap_dialog_actions
from ui import design

logger = logging.getLogger(__name__)


class MasterEncounterListView(ft.Column):
    """Lista incontri (non archiviati) + creazione. Innesta `MasterEncounterView`
    a schermo intero quando un incontro viene aperto."""

    def __init__(self):
        super().__init__(expand=True, spacing=0)
        self._page: ft.Page | None = None
        self._encounters: list[MasterEncounter] = []
        self._open_encounter_id: str | None = None
        self._list_col = ft.Column(spacing=10, scroll=ft.ScrollMode.AUTO, expand=True)
        self._body_area = ft.Container(expand=True)
        self._build()
        self.refresh()

    def did_mount(self):
        self._page = self.page

    # ------------------------------------------------------------------
    # Build / refresh
    # ------------------------------------------------------------------

    def _build(self):
        self.controls.clear()
        if self._open_encounter_id:
            self._body_area.content = MasterEncounterView(
                encounter_id=self._open_encounter_id,
                on_back_to_list=self._close_encounter,
            )
            self.controls.append(self._body_area)
            return

        header = ft.Container(
            content=ft.Column(
                [
                    title_text("Incontri", size=18),
                    # wrap=True: su schermi stretti (smartphone) i due pulsanti
                    # vanno a capo invece di traboccare — stessa convenzione
                    # ormai stabilita in tutta la Sezione Master.
                    ft.Row(
                        [
                            ft.OutlinedButton(
                                "Genera Incontro Casuale",
                                icon=ft.Icons.CASINO,
                                on_click=self._on_generate_click,
                                style=ft.ButtonStyle(
                                    color=design.T().magic,
                                    side=ft.BorderSide(1, design.T().magic),
                                ),
                            ),
                            primary_button("+ Nuovo Incontro", on_click=self._on_new_click),
                        ],
                        spacing=8, wrap=True,
                    ),
                ],
                spacing=8,
            ),
            padding=ft.Padding.all(16),
        )
        body = ft.Container(
            content=self._list_col, expand=True,
            padding=ft.Padding.only(left=16, right=16, bottom=16),
        )
        self.controls.append(header)
        self.controls.append(body)

    def refresh(self):
        self._encounters = master_repo.get_encounters(include_archived=False)
        self._populate_list()
        try:
            self.update()
        except RuntimeError:
            pass

    def _populate_list(self):
        self._list_col.controls.clear()
        if not self._encounters:
            self._list_col.controls.append(self._empty_state())
            return
        for enc in self._encounters:
            self._list_col.controls.append(self._encounter_card(enc))

    def _empty_state(self) -> ft.Control:
        return ft.Container(
            content=ft.Column(
                [
                    ft.Icon(ft.Icons.SHIELD_OUTLINED, size=48, color=design.T().border),
                    ft.Container(height=10),
                    muted_text(
                        "Nessun incontro attivo. Creane uno per iniziare a tracciare "
                        "iniziativa e PF dei combattenti.",
                        size=13, text_align=ft.TextAlign.CENTER,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.all(32),
            alignment=ft.Alignment.CENTER,
        )

    def _encounter_card(self, enc: MasterEncounter) -> ft.Control:
        members = master_repo.get_encounter_members(enc.id, active_only=True)
        count = len(members)
        subtitle = f"Round {enc.round_number} · {count} combattent{'e' if count == 1 else 'i'}"
        return ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.SHIELD, color=design.T().primary, size=22),
                    ft.Container(width=10),
                    ft.Column(
                        [
                            ft.Text(enc.name or "(senza nome)", size=14, weight=ft.FontWeight.BOLD,
                                     color=design.T().text),
                            ft.Text(subtitle, size=11, color=design.T().text_3),
                            ft.Text(enc.notes, size=11, color=design.T().text_2, italic=True)
                            if enc.notes else ft.Container(height=0),
                        ],
                        spacing=3, expand=True,
                    ),
                    ft.IconButton(
                        icon=ft.Icons.DELETE_OUTLINE, icon_color=design.T().text_3, icon_size=18,
                        tooltip="Elimina incontro",
                        on_click=lambda e, en=enc: self._confirm_delete(en),
                    ),
                    ft.Icon(ft.Icons.CHEVRON_RIGHT, color=design.T().text_3, size=18),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.all(12),
            bgcolor=design.T().surface,
            shadow=design.elevation(1),
            border_radius=8,
            on_click=lambda e, en=enc: self._open_encounter(en.id),
            ink=True,
        )

    def _confirm_delete(self, enc: MasterEncounter):
        if not self._page:
            return
        page = self._page

        def _do_delete(e: Any):
            master_repo.delete_encounter(enc.id)
            page.pop_dialog()
            self.refresh()

        dlg = ft.AlertDialog(
            title=ft.Text("Elimina incontro?", size=15, weight=ft.FontWeight.BOLD),
            content=ft.Text(
                f"\"{enc.name}\" e tutti i suoi combattenti verranno eliminati definitivamente.",
                size=12, color=design.T().text_2,
            ),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda e: page.pop_dialog()),
                ft.ElevatedButton(
                    "Elimina", icon=ft.Icons.DELETE_OUTLINE, on_click=_do_delete,
                    style=ft.ButtonStyle(bgcolor=design.T().danger, color=design.T().on_primary),
                ),
            ]),
        )
        page.show_dialog(dlg)

    def _on_generate_click(self, e: Any):
        if not self._page:
            return
        page = self._page
        from ui.views.master.master_encounter_generator_dialog import show_encounter_generator_dialog

        def _on_created(encounter_id: str):
            self.refresh()
            self._open_encounter(encounter_id)

        show_encounter_generator_dialog(page, _on_created)

    def _on_new_click(self, e: Any):
        if not self._page:
            return
        page = self._page
        name_tf = ft.TextField(label="Nome incontro", dense=True, border_radius=6, autofocus=True)
        notes_tf = ft.TextField(label="Note (opzionale)", multiline=True, min_lines=2, max_lines=4,
                                 dense=True, border_radius=6)

        def _do_create(_e: Any):
            name = (name_tf.value or "").strip() or "Nuovo Incontro"
            enc = master_repo.create_encounter(name=name, notes=notes_tf.value or "")
            page.pop_dialog()
            self.refresh()
            if enc:
                self._open_encounter(enc.id)

        dlg = ft.AlertDialog(
            title=ft.Text("Nuovo Incontro", size=16, weight=ft.FontWeight.BOLD),
            content=ft.Container(
                content=ft.Column([name_tf, notes_tf], spacing=8, tight=True),
                width=320,
            ),
            actions=wrap_dialog_actions([
                ft.TextButton("Annulla", on_click=lambda e: page.pop_dialog()),
                ft.ElevatedButton(
                    "Crea", icon=ft.Icons.ADD, on_click=_do_create,
                    style=ft.ButtonStyle(bgcolor=design.T().magic, color=design.T().on_accent),
                ),
            ]),
        )
        page.show_dialog(dlg)

    # ------------------------------------------------------------------
    # Navigazione lista ↔ tracker
    # ------------------------------------------------------------------

    def _open_encounter(self, encounter_id: str):
        self._open_encounter_id = encounter_id
        self._build()
        try:
            self.update()
        except RuntimeError:
            pass

    def _close_encounter(self):
        self._open_encounter_id = None
        self._build()
        self.refresh()
