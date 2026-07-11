"""
Tema Dungeon Stone per Flet: palette pietra antica, stile fantasy adventurer.
"""

import flet as ft
from config.settings import *


def get_theme() -> ft.Theme:
    """Restituisce il tema Flet con la palette Marmo Classico (chiaro)."""
    return ft.Theme(
        color_scheme=ft.ColorScheme(
            primary=COLOR_ACCENT_CRIMSON,
            on_primary="#ffffff",
            secondary=COLOR_ACCENT_GOLD,
            on_secondary="#ffffff",
            surface=COLOR_BG_CARD,
            on_surface=COLOR_TEXT_PRIMARY,
            error=COLOR_ACCENT_CRIMSON,
        ),
        font_family=FONT_BODY,
    )


# ---------------------------------------------------------------------------
# Helper: testi
# ---------------------------------------------------------------------------

def title_text(text: str, size: int = 20) -> ft.Text:
    return ft.Text(
        text,
        size=size,
        weight=ft.FontWeight.BOLD,
        color=COLOR_TEXT_TITLE,
        font_family=FONT_TITLE,
    )


def body_text(text: str, size: int = 14, color: str = COLOR_TEXT_PRIMARY, weight=None) -> ft.Text:
    return ft.Text(text, size=size, color=color, font_family=FONT_BODY, weight=weight)


def muted_text(text: str, size: int = 12, text_align: ft.TextAlign | None = None, weight=None) -> ft.Text:
    return ft.Text(text, size=size, color=COLOR_TEXT_MUTED, font_family=FONT_BODY,
                   text_align=text_align or ft.TextAlign.LEFT, weight=weight)


def label_text(text: str, size: int = 10) -> ft.Text:
    return ft.Text(
        text.upper(),
        size=size,
        color=COLOR_TEXT_MUTED,          # grigio pietra – non giallo
        font_family=FONT_BODY,
        weight=ft.FontWeight.BOLD,
        style=ft.TextStyle(letter_spacing=1),
    )


# ---------------------------------------------------------------------------
# Helper: contenitori — stile lastra di pietra scolpita
# ---------------------------------------------------------------------------

def fantasy_card(content: ft.Control, padding: int = 16) -> ft.Container:
    """
    Card marmo bianco con bordo superiore rosso rubino.
    Sfondo bianco/carta, ombra leggera tramite bordo grigio.
    """
    return ft.Container(
        content=content,
        bgcolor=COLOR_BG_CARD,
        padding=padding,
        border=ft.Border(
            top=ft.BorderSide(3, COLOR_ACCENT_CRIMSON),
            left=ft.BorderSide(1, COLOR_BORDER),
            right=ft.BorderSide(1, COLOR_BORDER),
            bottom=ft.BorderSide(1, COLOR_BORDER),
        ),
        border_radius=6,
    )


def danger_card(content: ft.Control, padding: int = 16) -> ft.Container:
    """Card con bordo rosso pieno (HP critici, pericolo)."""
    return ft.Container(
        content=content,
        bgcolor=COLOR_BG_CARD,
        padding=padding,
        border=ft.Border.all(2, COLOR_ACCENT_CRIMSON),
        border_radius=6,
    )


def section_header(text: str, accent: str = COLOR_ACCENT_CRIMSON) -> ft.Container:
    """
    Intestazione di sezione con stile runico:
    - piccolo blocco colorato a sinistra
    - testo maiuscolo in oro con spaziatura
    - linea decorativa sottile a destra
    """
    return ft.Container(
        content=ft.Row(
            [
                ft.Container(width=3, height=14, bgcolor=accent, border_radius=1),
                ft.Container(width=8),
                ft.Text(
                    text.upper(),
                    size=10,
                    color=COLOR_TEXT_SECONDARY,   # grigio pietra, non oro
                    weight=ft.FontWeight.BOLD,
                    font_family=FONT_BODY,
                    style=ft.TextStyle(letter_spacing=2),
                ),
                ft.Container(width=8),
                ft.Container(expand=True, height=1, bgcolor=COLOR_BORDER),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        margin=ft.Margin.only(bottom=10, top=4),
    )


def divider() -> ft.Divider:
    return ft.Divider(height=1, color=COLOR_BORDER)


def stat_badge(value: str, label: str, color: str = COLOR_TEXT_PRIMARY) -> ft.Container:
    """Badge compatto per visualizzare un valore numerico con etichetta."""
    return ft.Container(
        content=ft.Column(
            [
                ft.Text(value, size=20, weight=ft.FontWeight.BOLD, color=color,
                        font_family=FONT_MONO, text_align=ft.TextAlign.CENTER),
                ft.Text(label, size=9, color=COLOR_TEXT_SECONDARY,
                        text_align=ft.TextAlign.CENTER, weight=ft.FontWeight.BOLD,
                        style=ft.TextStyle(letter_spacing=1)),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=2,
        ),
        bgcolor=COLOR_BG_SECONDARY,
        border=ft.Border.all(1, COLOR_BORDER),
        border_radius=4,
        padding=ft.Padding.symmetric(horizontal=10, vertical=8),
    )


# ---------------------------------------------------------------------------
# Helper: bottoni
# ---------------------------------------------------------------------------

def primary_button(text: str, on_click=None, icon: ft.IconData | None = None) -> ft.ElevatedButton:
    return ft.ElevatedButton(
        text,
        icon=icon,
        on_click=on_click,
        style=ft.ButtonStyle(
            bgcolor=COLOR_ACCENT_CRIMSON,
            color="#ffffff",
            shape=ft.RoundedRectangleBorder(radius=4),
            side=ft.BorderSide(1, "#d0303e"),
        ),
    )


def gold_button(text: str, on_click=None, icon: ft.IconData | None = None) -> ft.ElevatedButton:
    """Bottone secondario in oro (per azioni importanti non distruttive)."""
    return ft.ElevatedButton(
        text,
        icon=icon,
        on_click=on_click,
        style=ft.ButtonStyle(
            bgcolor=COLOR_ACCENT_GOLD,
            color=COLOR_BG_PRIMARY,
            shape=ft.RoundedRectangleBorder(radius=4),
        ),
    )


def ghost_button(text: str, on_click=None) -> ft.OutlinedButton:
    return ft.OutlinedButton(
        text,
        on_click=on_click,
        style=ft.ButtonStyle(
            color=COLOR_TEXT_SECONDARY,
            side=ft.BorderSide(1, COLOR_BORDER),
            shape=ft.RoundedRectangleBorder(radius=4),
        ),
    )


def danger_button(text: str, on_click=None) -> ft.ElevatedButton:
    return ft.ElevatedButton(
        text,
        on_click=on_click,
        style=ft.ButtonStyle(
            bgcolor=COLOR_ACCENT_CRIMSON,
            color=COLOR_TEXT_PRIMARY,
            shape=ft.RoundedRectangleBorder(radius=4),
        ),
    )


def show_error_dialog(
    page: ft.Page | None,
    message: str = "Errore nel salvataggio. Riprova.",
    title: str = "Errore",
) -> None:
    """
    AlertDialog di errore standard, da usare ogni volta che una scrittura sul DB
    (es. character_repo.update()) fallisce e l'utente deve saperlo esplicitamente
    invece che vedere l'operazione fallire in silenzio.
    """
    if page is None:
        return
    page.show_dialog(ft.AlertDialog(
        title=ft.Text(title, size=14, weight=ft.FontWeight.BOLD, color=COLOR_ACCENT_CRIMSON),
        content=ft.Text(message, size=13, color=COLOR_TEXT_PRIMARY),
        actions=[
            ft.TextButton("OK", on_click=lambda e: page.pop_dialog()),
        ],
        bgcolor=COLOR_BG_CARD,
    ))
