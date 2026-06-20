"""
Tema fantasy per Flet: colori, stili, helper per componenti comuni.
"""

import flet as ft
from config.settings import *


def get_theme() -> ft.Theme:
    """Restituisce il tema Flet con la palette fantasy."""
    return ft.Theme(
        color_scheme=ft.ColorScheme(
            primary=COLOR_ACCENT_GOLD,
            on_primary=COLOR_BG_PRIMARY,
            secondary=COLOR_ACCENT_BLUE,
            surface=COLOR_BG_CARD,
            on_surface=COLOR_TEXT_PRIMARY,
            error=COLOR_ACCENT_RED,
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


def muted_text(text: str, size: int = 12, text_align: ft.TextAlign = None, weight=None) -> ft.Text:
    return ft.Text(text, size=size, color=COLOR_TEXT_MUTED, font_family=FONT_BODY,
                   text_align=text_align, weight=weight)


def label_text(text: str, size: int = 10) -> ft.Text:
    return ft.Text(
        text.upper(),
        size=size,
        color=COLOR_TEXT_SECONDARY,
        font_family=FONT_BODY,
        weight=ft.FontWeight.BOLD,
    )


# ---------------------------------------------------------------------------
# Helper: contenitori
# ---------------------------------------------------------------------------

def fantasy_card(content: ft.Control, padding: int = 16) -> ft.Container:
    """Pannello con bordo dorato stile pergamena."""
    return ft.Container(
        content=content,
        padding=padding,
        bgcolor=COLOR_BG_CARD,
        border=ft.Border.all(1, COLOR_BORDER),
        border_radius=6,
    )


def section_header(text: str) -> ft.Container:
    """Intestazione di sezione con linea decorativa."""
    return ft.Container(
        content=ft.Row([
            ft.Container(width=20, height=1, bgcolor=COLOR_BORDER_ACCENT),
            ft.Container(width=4),
            title_text(text, size=13),
            ft.Container(width=4),
            ft.Container(expand=True, height=1, bgcolor=COLOR_BORDER_ACCENT),
        ]),
        margin=ft.Margin.only(bottom=8),
    )


def divider() -> ft.Divider:
    return ft.Divider(height=1, color=COLOR_BORDER)


# ---------------------------------------------------------------------------
# Helper: bottoni
# ---------------------------------------------------------------------------

def primary_button(text: str, on_click=None, icon: str = None) -> ft.ElevatedButton:
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
            color=COLOR_ACCENT_GOLD,
            side=ft.BorderSide(1, COLOR_ACCENT_GOLD),
            shape=ft.RoundedRectangleBorder(radius=4),
        ),
    )


def danger_button(text: str, on_click=None) -> ft.ElevatedButton:
    return ft.ElevatedButton(
        text,
        on_click=on_click,
        style=ft.ButtonStyle(
            bgcolor=COLOR_ACCENT_RED,
            color=COLOR_TEXT_PRIMARY,
            shape=ft.RoundedRectangleBorder(radius=4),
        ),
    )
