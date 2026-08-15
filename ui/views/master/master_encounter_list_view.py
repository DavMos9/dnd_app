"""
Vista "Incontri" della Modalità Master — lista degli incontri di
combattimento (attivi o archiviati, vedi sotto) + creazione, e gestione della
navigazione verso il tracker a schermo intero di un singolo incontro
(`MasterEncounterView`). Vedi `dnd_app/docs/master_section_design.md` per il
design completo.

Questa vista è self-contained: gestisce da sola lo stato "lista" vs
"incontro aperto" al proprio interno (nessuna modifica al routing di
`master_view.py`, che la istanzia senza argomenti — stesso principio già
in uso per il cambio tab dentro `MasterView`).

**Switch Attivi/Archiviati (2026-08-03, segnalazione di Davide)**: prima
l'archivio degli incontri ("Termina Incontro") non era consultabile da
nessuna parte dell'interfaccia — l'unico modo per vederlo era interrogare il
DB a mano. Stesso pattern del pill-switch già in uso in `MasterLootView`
(Archivio/Deposito): un solo elenco alla volta, filtrato client-side su
`MasterEncounter.is_archived` (nessuna nuova funzione di repository, dato che
`master_repo.get_encounters(include_archived=True)` già restituisce tutto).
In "Archiviati" la creazione è nascosta (non ha senso creare un incontro
dentro una vista di sola consultazione) e ogni riga offre "Riapri"
(`master_repo.archive_encounter(id, archived=False)`, già supportato come
"house rule" dal repository) oltre all'eliminazione definitiva.
"""

import logging
from typing import Any, Callable, Optional

import flet as ft

from data.models import MasterEncounter
from data.repositories import master_repo
from ui.theme import title_text, primary_button
from ui.views.master.master_encounter_view import MasterEncounterView
from ui.widgets import wrap_dialog_actions, responsive_dialog_width
from ui import design

logger = logging.getLogger(__name__)


class MasterEncounterListView(ft.Column):
    """Lista incontri (non archiviati) + creazione. Innesta `MasterEncounterView`
    a schermo intero quando un incontro viene aperto."""

    def __init__(self, world_id: str = "", device_id: str = "",
                 on_focus_change: Optional[Callable[[bool], None]] = None):
        super().__init__(expand=True, spacing=0)
        self._page: ft.Page | None = None
        #: Mondo correntemente selezionato in `MasterView` (2026-08-06) — ""
        #: per la modalità locale. Inoltrato al generatore di incontri e a
        #: `MasterEncounterView` (picker "Personaggio Giocante").
        self._world_id = world_id
        #: Identità di questo dispositivo (2026-08-06, passo 6) — inoltrata a
        #: `MasterEncounterView` per firmare i comandi remoti ("Assegna PE"
        #: su un'istanza di mondo).
        self._device_id = device_id
        #: Notifica a `MasterView` (2026-08-06) quando questa vista passa
        #: alla modalità "incontro aperto" (True) o torna alla lista (False)
        #: — permette a `MasterView` di nascondere la propria chrome
        #: (selettore mondo/Generatori Rapidi/tab bar) mentre il tracker di
        #: combattimento è a schermo intero, senza che questa vista debba
        #: sapere nulla di `MasterView`. `None` se instanziata fuori da
        #: `MasterView` (nessun comportamento diverso, solo nessuna notifica).
        self._on_focus_change = on_focus_change
        self._encounters: list[MasterEncounter] = []
        self._show_archived: bool = False
        self._open_encounter_id: str | None = None
        self._list_col = ft.Column(spacing=10)
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
            # `MasterEncounterView` gestisce da sé il proprio scroll (header +
            # lista combattenti scorrono insieme al suo interno) — qui il
            # contenitore esterno non deve scrollare, altrimenti si annida un
            # secondo scroll attorno a quello del tracker.
            self.scroll = None
            self._body_area.content = MasterEncounterView(
                encounter_id=self._open_encounter_id,
                on_back_to_list=self._close_encounter,
                world_id=self._world_id,
                device_id=self._device_id,
            )
            self.controls.append(self._body_area)
            return

        self.scroll = ft.ScrollMode.AUTO

        header_children: list[ft.Control] = [title_text("Incontri", size=18)]
        if not self._show_archived:
            # wrap=True: su schermi stretti (smartphone) i due pulsanti vanno
            # a capo invece di traboccare — stessa convenzione ormai
            # stabilita in tutta la Sezione Master. Nascosti in "Archiviati":
            # quella vista è di sola consultazione, creare un nuovo incontro
            # da lì lo farebbe comparire in una scheda diversa da quella
            # aperta, comportamento confuso.
            header_children.append(ft.Row(
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
            ))
        header_children.append(self._build_archive_switch())
        header = ft.Container(
            content=ft.Column(header_children, spacing=8),
            padding=ft.Padding.all(16),
        )
        body = ft.Container(
            content=self._list_col,
            padding=ft.Padding.only(left=16, right=16, bottom=16),
        )
        self.controls.append(header)
        self.controls.append(body)

    def _build_archive_switch(self) -> ft.Control:
        """Stesso pill-switch di `MasterLootView` (Archivio/Deposito) — un
        elenco alla volta, filtrato client-side su `is_archived`."""
        items = []
        for is_archived, label, icon in (
            (False, "Attivi", ft.Icons.SHIELD_OUTLINED),
            (True, "Archiviati", ft.Icons.ARCHIVE_OUTLINED),
        ):
            is_sel = is_archived == self._show_archived
            items.append(ft.Container(
                content=ft.Row(
                    [ft.Icon(icon, size=14, color=design.T().primary if is_sel else design.T().text_3),
                     ft.Container(width=6),
                     ft.Text(label, size=12, weight=ft.FontWeight.BOLD if is_sel else ft.FontWeight.W_500,
                             color=design.T().primary if is_sel else design.T().text_2)],
                    alignment=ft.MainAxisAlignment.CENTER, tight=True,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=ft.Padding.symmetric(horizontal=design.Space.MD, vertical=design.Space.SM),
                border_radius=design.Radius.PILL,
                bgcolor=design.T().surface_alt if is_sel else "transparent",
                shadow=design.elevation(1) if is_sel else None,
                on_click=lambda e, v=is_archived: self._on_archive_switch(v),
                ink=True, expand=True,
            ))
        return ft.Container(
            content=ft.Row(items, spacing=design.Space.XS),
            bgcolor=design.T().bg, border_radius=design.Radius.PILL, padding=design.Space.XS,
        )

    def _on_archive_switch(self, show_archived: bool) -> None:
        if show_archived == self._show_archived:
            return
        self._show_archived = show_archived
        self._build()
        self.refresh()

    def refresh(self):
        all_encounters = master_repo.get_encounters(include_archived=True, world_id=self._world_id)
        self._encounters = [e for e in all_encounters if e.is_archived == self._show_archived]
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
        if self._show_archived:
            return design.empty_state(
                ft.Icons.ARCHIVE_OUTLINED,
                "Nessun incontro archiviato",
                "Gli incontri terminati con «Termina Incontro» compaiono qui.",
            )
        return design.empty_state(
            ft.Icons.SHIELD_OUTLINED,
            "Nessun incontro attivo",
            "Creane uno per iniziare a tracciare iniziativa e PF dei combattenti.",
        )

    def _on_reopen(self, enc: MasterEncounter) -> None:
        master_repo.archive_encounter(enc.id, archived=False)
        self.refresh()

    def _encounter_card(self, enc: MasterEncounter) -> ft.Control:
        members = master_repo.get_encounter_members(enc.id, active_only=True)
        count = len(members)
        card_icon = ft.Icons.ARCHIVE if self._show_archived else ft.Icons.SHIELD
        reopen_btn: list[ft.Control] = []
        if self._show_archived:
            reopen_btn.append(ft.IconButton(
                icon=ft.Icons.UNARCHIVE_OUTLINED, icon_color=design.T().primary, icon_size=18,
                tooltip="Riapri incontro",
                on_click=lambda e, en=enc: self._on_reopen(en),
            ))
        return ft.Container(
            content=ft.Row(
                [
                    ft.Container(
                        content=ft.Icon(card_icon, color=design.T().primary, size=22),
                        width=44, height=44, alignment=ft.Alignment.CENTER,
                        bgcolor=ft.Colors.with_opacity(0.12, design.T().primary),
                        border_radius=design.Radius.PILL,
                    ),
                    ft.Container(width=design.Space.MD),
                    ft.Column(
                        [
                            ft.Text(enc.name or "(senza nome)", size=15,
                                     weight=ft.FontWeight.BOLD, color=design.T().text,
                                     font_family=design.Font.DISPLAY,
                                     no_wrap=True, max_lines=1,
                                     overflow=ft.TextOverflow.ELLIPSIS),
                            ft.Row([
                                design.chip(f"Round {enc.round_number}", "primary"),
                                design.chip(
                                    f"{count} combattent{'e' if count == 1 else 'i'}",
                                    "magic", icon=ft.Icons.GROUPS_OUTLINED),
                            ], spacing=design.Space.XS, wrap=True),
                            ft.Text(enc.notes, size=11, color=design.T().text_2, italic=True)
                            if enc.notes else ft.Container(height=0),
                        ],
                        spacing=3, expand=True,
                    ),
                    *reopen_btn,
                    ft.IconButton(
                        icon=ft.Icons.DELETE_OUTLINE, icon_color=design.T().text_3, icon_size=18,
                        tooltip="Elimina incontro",
                        on_click=lambda e, en=enc: self._confirm_delete(en),
                    ),
                    ft.Icon(ft.Icons.CHEVRON_RIGHT, color=design.T().text_3, size=18),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.all(design.Space.MD),
            bgcolor=design.T().surface,
            shadow=design.elevation(1),
            border_radius=design.Radius.MD,
            border=ft.Border.only(left=ft.BorderSide(3, design.T().primary)),
            on_click=lambda e, en=enc: self._open_encounter(en.id),
            ink=True,
            animate_scale=ft.Animation(design.Duration.FAST, design.CURVE),
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
            title=design.dialog_title("Elimina incontro?"),
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

        show_encounter_generator_dialog(page, _on_created, world_id=self._world_id)

    def _on_new_click(self, e: Any):
        if not self._page:
            return
        page = self._page
        name_tf = ft.TextField(label="Nome incontro", dense=True, border_radius=design.Radius.SM, autofocus=True, border_color=design.field_style()['border_color'], focused_border_color=design.field_style()['focused_border_color'], bgcolor=design.field_style()['bgcolor'], text_style=design.field_style()['text_style'])
        notes_tf = ft.TextField(label="Note (opzionale)", multiline=True, min_lines=2, max_lines=4,
                                 dense=True, border_radius=design.Radius.SM, border_color=design.field_style()['border_color'], focused_border_color=design.field_style()['focused_border_color'], bgcolor=design.field_style()['bgcolor'], text_style=design.field_style()['text_style'])

        def _do_create(_e: Any):
            name = (name_tf.value or "").strip() or "Nuovo Incontro"
            enc = master_repo.create_encounter(name=name, notes=notes_tf.value or "", world_id=self._world_id)
            page.pop_dialog()
            self.refresh()
            if enc:
                self._open_encounter(enc.id)

        dlg = ft.AlertDialog(
            title=design.dialog_title("Nuovo Incontro"),
            content=ft.Container(
                content=ft.Column([name_tf, notes_tf], spacing=8, tight=True),
                width=responsive_dialog_width(page, 320),
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
        if self._on_focus_change is not None:
            self._on_focus_change(True)
        try:
            self.update()
        except RuntimeError:
            pass

    def _close_encounter(self):
        self._open_encounter_id = None
        self._build()
        if self._on_focus_change is not None:
            self._on_focus_change(False)
        self.refresh()
