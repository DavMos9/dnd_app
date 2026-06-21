"""
Schermata Home: selezione, creazione ed eliminazione dei personaggi.
È la prima schermata che l'utente vede all'avvio.
"""

import flet as ft
from typing import cast
from config.settings import *
from data.models import Character
from data.repositories import character_repo
from ui.theme import (
    title_text, body_text, muted_text, label_text,
    fantasy_card, primary_button, ghost_button, danger_button,
)


def _data_uri(b64: str) -> str:
    """Data URI da base64 con rilevamento formato (Flet 0.85.3 non ha src_base64)."""
    try:
        import base64 as _b64
        h = _b64.b64decode(b64[:16] + "==")
        if h[:3] == b"\xff\xd8\xff":
            mime = "image/jpeg"
        elif h[:8] == b"\x89PNG\r\n\x1a\n":
            mime = "image/png"
        else:
            mime = "image/jpeg"
    except Exception:
        mime = "image/jpeg"
    return f"data:{mime};base64,{b64}"


class HomeView(ft.Column):
    """
    Lista dei personaggi esistenti con azioni di selezione, eliminazione
    e creazione (wizard o manuale).

    Callbacks:
        on_select(character_id: str)  → carica la scheda del personaggio
        on_create_wizard()            → avvia il wizard guidato
        on_create_manual()            → apre il form manuale
    """

    def __init__(self, on_select, on_create_wizard, on_create_manual):
        super().__init__(expand=True, spacing=0)
        self.on_select = on_select
        self.on_create_wizard = on_create_wizard
        self.on_create_manual = on_create_manual

        self._char_list_column = ft.Column(spacing=12, scroll=ft.ScrollMode.AUTO)
        self._build()
        self.refresh()

    # ------------------------------------------------------------------
    # Build layout
    # ------------------------------------------------------------------

    def _build(self):
        # Logo D&D come widget Flet — testo bold rosso, nessuna immagine
        logo_widget = ft.Text(
            "D&D",
            size=52,
            weight=ft.FontWeight.BOLD,
            color=COLOR_ACCENT_CRIMSON,
        )

        header = ft.Container(
            content=ft.Row(
                [
                    logo_widget,
                    ft.Container(width=16),
                    ft.Column(
                        [
                            title_text("D&D Companion", size=28),
                            muted_text("Seleziona un personaggio o creane uno nuovo", size=13),
                        ],
                        spacing=4,
                        expand=True,
                    ),
                    self._new_character_button(),
                ],
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=32, vertical=20),
            bgcolor=COLOR_BG_SECONDARY,
            border=ft.Border.only(bottom=ft.BorderSide(1, COLOR_BORDER)),
        )

        body = ft.Container(
            content=ft.Column(
                [self._char_list_column],
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            ),
            expand=True,
            padding=ft.Padding.all(32),
        )

        self.controls = [header, body]

    def _new_character_button(self) -> ft.Control:
        """Bottone '+' che apre il dialog per scegliere wizard o manuale."""
        return ft.ElevatedButton(
            "Nuovo Personaggio",
            icon=ft.Icons.ADD,
            on_click=self._on_new_click,
            style=ft.ButtonStyle(
                bgcolor=COLOR_ACCENT_GOLD,
                color=COLOR_BG_PRIMARY,
                shape=ft.RoundedRectangleBorder(radius=6),
            ),
        )

    # ------------------------------------------------------------------
    # Dati
    # ------------------------------------------------------------------

    def refresh(self):
        """Ricarica la lista personaggi dal database."""
        characters = character_repo.get_all()
        self._char_list_column.controls.clear()

        if not characters:
            self._char_list_column.controls.append(self._empty_state())
        else:
            for char in characters:
                self._char_list_column.controls.append(
                    self._character_card(char)
                )

        # update() è valido solo dopo il mount sulla page
        try:
            self._char_list_column.update()
        except RuntimeError:
            pass  # chiamata da __init__, il render avviene con page.add()

    # ------------------------------------------------------------------
    # Card personaggio
    # ------------------------------------------------------------------

    def _character_card(self, char: Character) -> ft.Container:
        """Card con info essenziali del personaggio e azioni."""

        # Foto o placeholder (priorità: base64 in DB > percorso file > icona)
        if char.image_data:
            avatar = ft.Container(
                content=ft.Image(
                    src=_data_uri(char.image_data),
                    width=72, height=72,
                    fit=ft.BoxFit.COVER,
                ),
                width=72, height=72,
                border_radius=6,
                clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            )
        elif char.image_path:
            avatar = ft.Image(
                src=char.image_path,
                width=72, height=72,
                fit=ft.BoxFit.COVER,
                border_radius=ft.BorderRadius.all(6),
            )
        else:
            avatar = ft.Container(
                width=72, height=72,
                bgcolor=COLOR_BG_SECONDARY,
                border_radius=6,
                border=ft.Border.all(1, COLOR_BORDER),
                content=ft.Icon(ft.Icons.PERSON, color=COLOR_TEXT_MUTED, size=36),
                alignment=ft.Alignment.CENTER,
            )

        # Badge livello
        level_badge = ft.Container(
            content=ft.Text(
                f"Liv. {char.level}",
                size=11,
                weight=ft.FontWeight.BOLD,
                color=COLOR_BG_PRIMARY,
            ),
            bgcolor=COLOR_ACCENT_GOLD,
            border_radius=4,
            padding=ft.Padding.symmetric(horizontal=6, vertical=2),
        )

        info = ft.Column(
            [
                ft.Row(
                    [
                        ft.Text(
                            char.name or "Senza nome",
                            size=18,
                            weight=ft.FontWeight.BOLD,
                            color=COLOR_TEXT_PRIMARY,
                        ),
                        level_badge,
                    ],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                body_text(
                    f"{char.class_name}  ·  {char.race}",
                    size=13,
                    color=COLOR_TEXT_SECONDARY,
                ),
                muted_text(
                    char.background or "Nessun background",
                    size=12,
                ),
            ],
            spacing=4,
            expand=True,
        )

        actions = ft.Row(
            [
                ft.IconButton(
                    icon=ft.Icons.PLAY_CIRCLE_OUTLINE,
                    icon_color=COLOR_ACCENT_GOLD,
                    tooltip="Gioca con questo personaggio",
                    on_click=lambda e, cid=char.id: self.on_select(cid),
                ),
                ft.IconButton(
                    icon=ft.Icons.DELETE_OUTLINE,
                    icon_color=COLOR_ACCENT_RED,
                    tooltip="Elimina personaggio",
                    on_click=lambda e, c=char: self._confirm_delete(c),
                ),
            ],
            spacing=0,
        )

        card_content = ft.Row(
            [avatar, ft.Container(width=16), info, actions],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        return ft.Container(
            content=card_content,
            padding=16,
            bgcolor=COLOR_BG_CARD,
            border=ft.Border.all(1, COLOR_BORDER),
            border_radius=8,
            on_click=lambda e, cid=char.id: self.on_select(cid),
            ink=True,
            animate=ft.Animation(150, ft.AnimationCurve.EASE_OUT),
        )

    # ------------------------------------------------------------------
    # Stato vuoto
    # ------------------------------------------------------------------

    def _empty_state(self) -> ft.Container:
        return ft.Container(
            content=ft.Column(
                [
                    ft.Icon(ft.Icons.SHIELD_OUTLINED, size=80, color=COLOR_BORDER),
                    ft.Container(height=16),
                    title_text("Nessun personaggio", size=20),
                    ft.Container(height=8),
                    muted_text(
                        "Crea il tuo primo personaggio per iniziare l'avventura.",
                        size=14,
                    ),
                    ft.Container(height=24),
                    ft.Row(
                        controls=cast(list[ft.Control], [
                            primary_button(
                                "Wizard guidato",
                                on_click=lambda e: self.on_create_wizard(),
                                icon=ft.Icons.AUTO_FIX_HIGH,
                            ),
                            ghost_button(
                                "Creazione manuale",
                                on_click=lambda e: self.on_create_manual(),
                            ),
                        ]),
                        alignment=ft.MainAxisAlignment.CENTER,
                        spacing=12,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            expand=True,
            alignment=ft.Alignment.CENTER,
            padding=64,
        )

    # ------------------------------------------------------------------
    # Dialogs
    # ------------------------------------------------------------------

    def _on_new_click(self, e):
        """Dialog per scegliere wizard o creazione manuale."""
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(
                "Nuovo Personaggio",
                color=COLOR_TEXT_TITLE,
                weight=ft.FontWeight.BOLD,
            ),
            bgcolor=COLOR_BG_CARD,
            content=ft.Column(
                [
                    muted_text(
                        "Come vuoi creare il tuo personaggio?",
                        size=14,
                    ),
                    ft.Container(height=16),
                    ft.Row(
                        [
                            ft.ElevatedButton(
                                "Wizard guidato",
                                icon=ft.Icons.AUTO_FIX_HIGH,
                                tooltip="Rispondi ad alcune domande e l'app crea il personaggio più adatto a te",
                                on_click=lambda e: self._close_and(self.on_create_wizard),
                                expand=True,
                                style=ft.ButtonStyle(
                                    bgcolor=COLOR_ACCENT_GOLD,
                                    color=COLOR_BG_PRIMARY,
                                    shape=ft.RoundedRectangleBorder(radius=6),
                                ),
                            ),
                        ],
                    ),
                    ft.Container(height=8),
                    ft.Row(
                        [
                            ft.OutlinedButton(
                                "Creazione manuale",
                                icon=ft.Icons.EDIT_NOTE,
                                tooltip="Compila direttamente tutti i campi della scheda",
                                on_click=lambda e: self._close_and(self.on_create_manual),
                                expand=True,
                                style=ft.ButtonStyle(
                                    color=COLOR_ACCENT_GOLD,
                                    side=ft.BorderSide(1, COLOR_ACCENT_GOLD),
                                    shape=ft.RoundedRectangleBorder(radius=6),
                                ),
                            ),
                        ],
                    ),
                ],
                tight=True,
                spacing=0,
            ),
            actions=[
                ft.TextButton(
                    "Annulla",
                    on_click=lambda e: self._close_dialog(),
                    style=ft.ButtonStyle(color=COLOR_TEXT_SECONDARY),
                ),
            ],
        )
        self.page.show_dialog(dlg)

    def _confirm_delete(self, char: Character):
        """Dialog di conferma eliminazione."""
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Elimina personaggio", color=COLOR_ACCENT_RED),
            bgcolor=COLOR_BG_CARD,
            content=ft.Text(
                f'Sei sicuro di voler eliminare "{char.name}"?\nQuesta azione non può essere annullata.',
                color=COLOR_TEXT_PRIMARY,
            ),
            actions=[
                ft.TextButton(
                    "Annulla",
                    on_click=lambda e: self._close_dialog(),
                    style=ft.ButtonStyle(color=COLOR_TEXT_SECONDARY),
                ),
                ft.ElevatedButton(
                    "Elimina",
                    icon=ft.Icons.DELETE,
                    on_click=lambda e: self._do_delete(dlg, char.id),
                    style=ft.ButtonStyle(
                        bgcolor=COLOR_ACCENT_RED,
                        color=COLOR_TEXT_PRIMARY,
                        shape=ft.RoundedRectangleBorder(radius=6),
                    ),
                ),
            ],
        )
        self.page.show_dialog(dlg)

    def _do_delete(self, dlg: ft.AlertDialog, character_id: str):
        self.page.pop_dialog()
        if character_repo.delete(character_id):
            self.refresh()
        else:
            self._show_error("Errore durante l'eliminazione del personaggio.")

    def _close_dialog(self):
        self.page.pop_dialog()

    def _close_and(self, callback):
        self.page.pop_dialog()
        callback()

    def _show_error(self, message: str):
        snack = ft.SnackBar(
            content=ft.Text(message, color=COLOR_TEXT_PRIMARY),
            bgcolor=COLOR_ACCENT_RED,
        )
        self.page.show_dialog(snack)
