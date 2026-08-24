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
from data.models import Character, DiaryEntry
import data.repositories.character_repo as character_repo
from ui.theme import muted_text
from ui.widgets import ScrollMemoryListView, wrap_dialog_actions
from ui import design

logger = logging.getLogger(__name__)


class DiarioTab(ScrollMemoryListView):
    """
    Tab diario: voci di sessione con creazione, lettura, modifica, eliminazione.
    Eredita da ft.ListView per scroll corretto in Flet 0.85.3.

    NOTA: le note condivise dal Master NON vivono qui — vivono nella sezione
    "Diario" della barra laterale (`ui/views/diary_view.py::DiaryView`,
    insieme a Incantesimi/Mappe/Talenti), non in questo tab interno alla
    scheda. Le due viste si chiamano entrambe "Diario" ma sono sezioni
    diverse: non aggiungere qui le note del Master per errore.
    """

    def __init__(self, character: Character, on_refresh: Callable[[], None] | None = None):
        super().__init__(expand=True, spacing=10, padding=16)
        self.character = character
        self._on_refresh = on_refresh
        self._page: ft.Page | None = None
        self._entries: list[DiaryEntry] = character_repo.get_diary_entries(character.id)
        self._device_id_cache: dict = {}
        self._build()

    def did_mount(self):
        self._page = cast(ft.Page, self.page)

    def _push_diary_to_world(self, action: str, fields: dict) -> None:
        """Invia la voce di diario appena scritta/modificata verso l'host,
        best effort — no-op se il personaggio non è un'istanza di un mondo.
        Vedi `core.world_sync.push_character_self_command`."""
        if not self.character.world_id or self._page is None:
            return
        from core import world_permissions as perm
        from core import world_sync
        kind = (
            perm.CMD_DIARY_SELF_ADD_ENTRY if action == "add"
            else perm.CMD_DIARY_SELF_UPDATE_ENTRY
        )
        self._page.run_task(
            world_sync.push_character_self_command,
            self._page, self.character, self._device_id_cache, kind, fields,
        )

    # ------------------------------------------------------------------
    # Build principale
    # ------------------------------------------------------------------

    def _build(self):
        # Intestazione — momento tipografico dominante del tab (Arcane
        # Ledger, `hero_title()`): prima un semplice `ft.Text` in linea col
        # bottone, ora l'unica card "hero" della schermata (MAX una per
        # tab), stesso schema di `feats_view.py`/`magic_items_view.py` —
        # badge indaco/oro + titolo in `Font.DISPLAY` + sottotitolo con il
        # conteggio voci, pulsante "Nuova Voce" su una riga propria per non
        # combinare `wrap=True` e `expand=True` sulla stessa Row (vedi
        # `docs/regole_flet_api.md`).
        n = len(self._entries)
        subtitle = (
            f"{n} vo{'ce' if n == 1 else 'ci'} registrate"
            if n else "Le cronache delle tue avventure, sessione dopo sessione"
        )
        header = design.card(
            ft.Column(
                [
                    ft.Row(
                        [
                            design.icon_badge(ft.Icons.MENU_BOOK_OUTLINED, tone="primary"),
                            ft.Container(width=design.Space.MD),
                            design.hero_title("Diario di Avventura", subtitle),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        wrap=True,
                    ),
                    ft.Container(height=design.Space.MD),
                    ft.Row(
                        [
                            ft.ElevatedButton(
                                "Nuova Voce",
                                icon=ft.Icons.ADD,
                                on_click=lambda e: self._on_new_entry(),
                                style=ft.ButtonStyle(
                                    bgcolor=design.T().primary_fill,
                                    color=design.T().on_primary_fill,
                                ),
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.END,
                    ),
                ],
                spacing=0,
            ),
            hero=True,
        )

        # IMPORTANTE: modificare self.controls IN-PLACE (mai self.controls = [...]).
        # In Flet 0.85.3 la riassegnazione diretta rimpiazza la ControlsList interna
        # che Flutter usa per il rendering → schermata bianca (vedi CLAUDE.md).
        self.controls.clear()
        self.controls.append(header)
        self.controls.append(ft.Container(height=design.Space.XS))

        if not self._entries:
            self.controls.append(self._empty_state())
        else:
            for entry in self._entries:
                self.controls.append(self._entry_card(entry))

    # ------------------------------------------------------------------
    # Stato vuoto
    # ------------------------------------------------------------------

    def _empty_state(self) -> ft.Container:
        # Primitiva condivisa `design.empty_state()` (Arcane Ledger) al
        # posto della Column scritta a mano — stesso badge cerchiato tinto
        # usato per ogni altro stato vuoto dell'app.
        ctrl = design.empty_state(
            ft.Icons.MENU_BOOK_OUTLINED,
            "Nessuna voce nel diario",
            "Premi «Nuova Voce» per iniziare a scrivere le tue avventure.",
        )
        ctrl.expand = True  # centra verticalmente nell'area visibile, come prima
        return ctrl

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

        # Card standard (barra accento sinistra + ombra a livello, come le
        # altre viste) invece di un Container bordato a mano su 4 lati.
        return design.card(
            ft.Column(
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
                                        # `danger_icon`, non `primary_icon`: azione
                                        # distruttiva (vedi nota sul bottone
                                        # "Elimina" del dialog di conferma sotto).
                                        icon_color=design.T().danger_icon,
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
            accent=design.T().primary,
            padding=design.Space.MD,
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

        _saved = False

        def save(ev):
            # Guardia anti doppio-tap (BUG FIX 2026-08-24, bug report Davide:
            # "a volte premi conferma, salva la nota ma non sparisce la
            # finestra, si resettano solo vuoti i campi"): su smartphone un
            # tap può generare due eventi click ravvicinati sullo stesso
            # pulsante. Senza guardia, il secondo `on_click` in coda arriva
            # DOPO che `page.pop_dialog()`/`self._refresh()` del primo hanno
            # già ricostruito la scheda — ripete comunque `save()`
            # sull'AlertDialog ancora visibile lato client in quell'istante,
            # il cui secondo `page.pop_dialog()` non ha più nulla da
            # chiudere (il dialog è concettualmente già stato rimosso), da
            # cui la finestra che resta a schermo.
            nonlocal _saved
            if page is None or _saved:
                return
            _saved = True
            title = (f_title.value or "").strip() or "Senza titolo"
            date = (f_date.value or "").strip()
            content = (f_content.value or "").strip()
            if is_new:
                character_repo.create_diary_entry(self.character.id, title, content, date)
                self._push_diary_to_world(
                    "add", {"title": title, "content": content, "session_date": date},
                )
            else:
                assert entry is not None
                character_repo.update_diary_entry(entry.id, title, content, date)
                self._push_diary_to_world(
                    "update",
                    {"entry_id": entry.id, "title": title, "content": content,
                     "session_date": date},
                )
            page.pop_dialog()
            self._refresh()

        page.show_dialog(ft.AlertDialog(
            title=design.dialog_title(
                "Nuova Voce" if is_new else "Modifica Voce",
                ft.Icons.EDIT_NOTE if is_new else ft.Icons.EDIT_OUTLINED,
            ),
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
            title=design.dialog_title("Elimina voce", ft.Icons.DELETE_OUTLINE, tone="danger"),
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
                        # `danger_fill`, non `primary_fill`: azione distruttiva
                        # (Arcane Ledger separa i due accenti, vedi `ui/design.py`).
                        bgcolor=design.T().danger_fill,
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
        self.controls.clear()
        self._build()
        try:
            self.update()
        except RuntimeError:
            pass
        # Ripristina la posizione di scroll: il rebuild sopra ricrea tutti i
        # controlli, quindi senza questo la vista tornerebbe in cima ad ogni
        # singola azione.
        self.restore_scroll()
        if self._on_refresh:
            self._on_refresh()
