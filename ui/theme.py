"""
Tema Flet dell'app + helper legacy.

**Riscritto nella Fase A del restyle (2026-07-26).** Prima usava 2 soli campi
di `ft.Theme` (`color_scheme` e `font_family`) su 58 disponibili: ogni dialog,
bottone e scrollbar era quindi stilizzato a mano, uno per uno, in 25 file.
Ora il tema configura i sotto-temi, e questo **restyla in un colpo solo tutti
i ~60 AlertDialog dell'app** senza toccarne nemmeno uno.

I valori vengono dai token in `ui/design.py` (palette doppia chiaro/scuro con
contrasti WCAG calcolati). Gli helper legacy in fondo al file
(`title_text`, `fantasy_card`, `section_header`, …) restano invariati e
funzionanti: le view migrano alle nuove primitive una superficie alla volta
nella Fase E, non tutte insieme.
"""

import flet as ft
from config.settings import *
from ui import design as d


def _build_theme(p: "d.Palette") -> ft.Theme:
    """Costruisce un `ft.Theme` completo a partire da una palette."""
    txt = lambda size, color, weight=None, family=d.Font.BODY: ft.TextStyle(  # noqa: E731
        size=size, color=color, weight=weight, font_family=family)

    return ft.Theme(
        font_family=d.Font.BODY,
        use_material3=True,
        color_scheme=ft.ColorScheme(
            primary=p.primary,
            on_primary=p.on_primary,
            secondary=p.magic,
            on_secondary=p.on_accent,
            tertiary=p.success,
            on_tertiary=p.on_accent,
            error=p.danger,
            on_error=p.on_primary,
            surface=p.surface,
            on_surface=p.text,
            on_surface_variant=p.text_2,
            outline=p.border,
            outline_variant=p.border,
            shadow=p.shadow,
            surface_container_lowest=p.surface,
            surface_container_low=p.surface,
            surface_container=p.surface_alt,
            surface_container_high=p.surface_alt,
            surface_dim=p.bg_alt,
            surface_bright=p.surface,
        ),
        # Un solo punto per raggio + ombra + tipografia di TUTTI i dialog.
        dialog_theme=ft.DialogTheme(
            bgcolor=p.surface,
            elevation=8,
            shadow_color=p.shadow,
            shape=ft.RoundedRectangleBorder(radius=d.Radius.XL),
            title_text_style=txt(d.Size.SUBTITLE, p.text, ft.FontWeight.BOLD,
                                 d.Font.DISPLAY),
            content_text_style=txt(d.Size.BODY, p.text),
            inset_padding=ft.Padding.symmetric(horizontal=d.Space.XL,
                                               vertical=d.Space.XXL),
        ),
        card_theme=ft.CardTheme(
            color=p.surface,
            shadow_color=p.shadow,
            elevation=2,
            shape=ft.RoundedRectangleBorder(radius=d.Radius.MD),
        ),
        text_theme=ft.TextTheme(
            display_small=txt(d.Size.DISPLAY, p.text, ft.FontWeight.BOLD, d.Font.DISPLAY),
            headline_medium=txt(d.Size.TITLE, p.text, ft.FontWeight.BOLD, d.Font.DISPLAY),
            title_medium=txt(d.Size.SUBTITLE, p.text, ft.FontWeight.W_600),
            body_large=txt(d.Size.BODY, p.text),
            body_medium=txt(d.Size.BODY_SM, p.text_2),
            body_small=txt(d.Size.LABEL, p.text_3),
            label_medium=txt(d.Size.LABEL, p.text_3, ft.FontWeight.BOLD),
        ),
        button_theme=ft.ButtonTheme(style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=d.Radius.SM),
            padding=ft.Padding.symmetric(horizontal=d.Space.LG, vertical=d.Space.MD),
        )),
        outlined_button_theme=ft.ButtonTheme(style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=d.Radius.SM),
            side=ft.BorderSide(1, p.border),
            color=p.text_2,
        )),
        text_button_theme=ft.ButtonTheme(style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=d.Radius.SM),
            color=p.primary,
        )),
        # Le scrollbar di default sono uno dei dettagli che più "invecchiano"
        # un'app: sottili, arrotondate e semitrasparenti.
        scrollbar_theme=ft.ScrollbarTheme(
            thickness=6,
            radius=d.Radius.SM,
            thumb_color=ft.Colors.with_opacity(0.35, p.text_3),
            track_color=ft.Colors.TRANSPARENT,
            track_border_color=ft.Colors.TRANSPARENT,
            main_axis_margin=2,
            cross_axis_margin=2,
            interactive=True,
        ),
        divider_theme=ft.DividerTheme(color=p.border, thickness=1, space=1),
        tooltip_theme=ft.TooltipTheme(
            text_style=txt(d.Size.LABEL, p.surface),
            padding=ft.Padding.symmetric(horizontal=d.Space.SM, vertical=d.Space.XS),
            wait_duration=ft.Duration(milliseconds=400),
        ),
        visual_density=ft.VisualDensity.COMFORTABLE,
    )


def get_theme() -> ft.Theme:
    """Tema chiaro (pergamena)."""
    return _build_theme(d.LIGHT)


def get_dark_theme() -> ft.Theme:
    """Tema scuro. Collegato al toggle nella Fase D del restyle."""
    return _build_theme(d.DARK)


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
            color=d.T().on_primary,
            shape=ft.RoundedRectangleBorder(radius=4),
            side=ft.BorderSide(1, d.T().primary),
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
