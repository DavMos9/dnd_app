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
        # Forma, padding e tipografia dei bottoni vivono QUI: nella Fase E.4 le
        # 81 `shape=RoundedRectangleBorder(radius=4|6|8)` inline sono state
        # rimosse dalle view, così ogni bottone dell'app prende questi valori.
        button_theme=ft.ButtonTheme(style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=d.Radius.SM),
            padding=ft.Padding.symmetric(horizontal=d.Space.LG, vertical=d.Space.MD),
            elevation=2,
            shadow_color=p.shadow,
            text_style=txt(13, None, ft.FontWeight.BOLD),
        )),
        outlined_button_theme=ft.ButtonTheme(style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=d.Radius.SM),
            padding=ft.Padding.symmetric(horizontal=d.Space.LG, vertical=d.Space.MD),
            side=ft.BorderSide(1, p.border),
            color=p.text_2,
            text_style=txt(13, None, ft.FontWeight.W_600),
        )),
        text_button_theme=ft.ButtonTheme(style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=d.Radius.SM),
            padding=ft.Padding.symmetric(horizontal=d.Space.MD, vertical=d.Space.SM),
            color=p.primary,
            text_style=txt(13, None, ft.FontWeight.W_600),
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
        # Controlli Material che l'app usa dentro i dialog: uniformati dal tema
        # (Fase E, coda 2026-07-30) invece che stilizzati caso per caso.
        #
        # `menu_style` (bug report Davide 2026-08-15, "Note di Campagna"):
        # senza uno sfondo esplicito, il menu a tendina di OGNI `Dropdown`
        # dell'app (non solo quello segnalato) cade sul default Material —
        # un riquadro semitrasparente scuro che si vede a malapena sul testo,
        # indipendentemente dal tema chiaro/scuro dell'app. Impostare
        # `bgcolor`/`shadow_color`/`shape` qui risolve tutti i Dropdown in un
        # colpo solo, stesso principio già applicato sopra a dialog/bottoni.
        dropdown_theme=ft.DropdownTheme(
            text_style=txt(d.Size.BODY_SM, p.text),
            menu_style=ft.MenuStyle(
                bgcolor=p.surface,
                shadow_color=p.shadow,
                elevation=8,
                shape=ft.RoundedRectangleBorder(radius=d.Radius.SM),
                side=ft.BorderSide(1, p.border),
            ),
        ),
        checkbox_theme=ft.CheckboxTheme(
            fill_color=p.primary,
            check_color=p.on_primary,
            shape=ft.RoundedRectangleBorder(radius=d.Radius.SM // 2),
            border_side=ft.BorderSide(1.5, p.border),
        ),
        radio_theme=ft.RadioTheme(fill_color=p.primary),
        slider_theme=ft.SliderTheme(
            active_track_color=p.primary,
            inactive_track_color=p.surface_alt,
            thumb_color=p.primary,
            value_indicator_color=p.primary,
        ),
        chip_theme=ft.ChipTheme(
            bgcolor=p.surface_alt,
            color=p.text_2,
            shape=ft.RoundedRectangleBorder(radius=d.Radius.PILL),
            label_text_style=txt(d.Size.LABEL, p.text_2, ft.FontWeight.BOLD),
        ),
        icon_theme=ft.IconTheme(color=p.text_2),
        snackbar_theme=ft.SnackBarTheme(
            bgcolor=p.surface,
            content_text_style=txt(d.Size.BODY_SM, p.text),
            shape=ft.RoundedRectangleBorder(radius=d.Radius.MD),
            elevation=4,
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
    return d.title(text, size=size)


def body_text(text: str, size: int = 14, color: str | None = None, weight=None) -> ft.Text:
    # `color` NON può avere `d.T()...` come default: sarebbe valutato una sola
    # volta all'import, congelando la palette chiara (Fase E.3).
    return d.body(text, size=size, color=color, weight=weight)


def muted_text(text: str, size: int = 12, text_align: ft.TextAlign | None = None,
               weight=None) -> ft.Text:
    t = d.muted(text, size=size)
    t.text_align = text_align or ft.TextAlign.LEFT
    t.weight = weight
    return t


def label_text(text: str, size: int = 10) -> ft.Text:
    t = d.label(text)
    t.size = max(size, d.Size.LABEL)   # mai sotto 11px (regola della Fase B)
    return t


# ---------------------------------------------------------------------------
# Helper: contenitori
# ---------------------------------------------------------------------------

def fantasy_card(content: ft.Control, padding: int = 16) -> ft.Container:
    """Card standard — delega alla primitiva `design.card()` (accento a sinistra)."""
    return d.card(content, accent=d.T().primary, padding=padding)


def section_header(text: str, accent: str | None = None) -> ft.Container:
    """
    Intestazione di sezione: barretta d'accento + etichetta maiuscola spaziata +
    filo di separazione. Riscritta sui token nella Fase E.3 — è chiamata da 68
    punti nelle view, quindi cambiarla qui restyla tutte le sezioni dell'app.
    """
    p = d.T()
    return ft.Container(
        content=ft.Row(
            [
                ft.Container(width=3, height=16, bgcolor=accent or p.primary,
                             border_radius=d.Radius.SM),
                ft.Container(width=d.Space.SM),
                ft.Text(
                    text.upper(),
                    size=d.Size.LABEL,
                    color=p.text_2,
                    weight=ft.FontWeight.BOLD,
                    font_family=d.Font.BODY,
                    style=ft.TextStyle(letter_spacing=1.5),
                ),
                ft.Container(width=d.Space.MD),
                ft.Container(expand=True, height=1,
                             bgcolor=ft.Colors.with_opacity(0.6, p.border)),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        margin=ft.Margin.only(bottom=d.Space.MD, top=d.Space.XS),
    )


# ---------------------------------------------------------------------------
# Helper: bottoni
# ---------------------------------------------------------------------------

def primary_button(text: str, on_click=None, icon: ft.IconData | None = None) -> ft.ElevatedButton:
    """Azione primaria: pieno, angoli morbidi, tap-target comodo anche su tablet."""
    p = d.T()
    return ft.ElevatedButton(
        text,
        icon=icon,
        on_click=on_click,
        style=ft.ButtonStyle(
            bgcolor=p.primary,
            color=p.on_primary,
            elevation=2,
            shadow_color=p.shadow,
            shape=ft.RoundedRectangleBorder(radius=d.Radius.SM),
            padding=ft.Padding.symmetric(horizontal=d.Space.LG, vertical=d.Space.MD),
            text_style=ft.TextStyle(size=13, weight=ft.FontWeight.BOLD,
                                    font_family=d.Font.BODY),
        ),
    )


def ghost_button(text: str, on_click=None) -> ft.OutlinedButton:
    """Azione secondaria: contorno sottile, stessa altezza del primario."""
    p = d.T()
    return ft.OutlinedButton(
        text,
        on_click=on_click,
        style=ft.ButtonStyle(
            color=p.text_2,
            side=ft.BorderSide(1, p.border),
            shape=ft.RoundedRectangleBorder(radius=d.Radius.SM),
            padding=ft.Padding.symmetric(horizontal=d.Space.LG, vertical=d.Space.MD),
            text_style=ft.TextStyle(size=13, weight=ft.FontWeight.W_600,
                                    font_family=d.Font.BODY),
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
        title=d.dialog_title(title),
        content=ft.Text(message, size=13, color=d.T().text),
        actions=[
            ft.TextButton("OK", on_click=lambda e: page.pop_dialog()),
        ],
    ))
