"""
Vista "Oggetti Magici" della Modalità Master — compendio sfogliabile del
Capitolo 7 "Tesori" (sezione "Oggetti Magici A-Z") della Guida del Dungeon
Master, 264 voci trascritte (vedi CLAUDE.md, TODO "Sezione Master (7) —
Compendio Oggetti Magici").

Sola consultazione: nessuna scrittura su nessuna tabella DB. I dati vivono
interamente in `data/game_data/magic_items.json` e sono letti via
`GameDataLoader.get_magic_items()`. Stesso principio già stabilito per
`FeatsView` (compendio talenti) — un browser di riferimento indipendente da
ogni personaggio/campagna, qui innestato come tab della Sezione Master
perché è il Master (non il giocatore) a consultarlo mentre distribuisce
tesori.

Esclusi da questo compendio (vedi nota `_source_note` in magic_items.json):
"Oggetti Magici Senzienti" (solo regole generali, nessuna scheda) e
"Artefatti" (formato diverso — tabelle di proprietà casuali d100, non uno
schema nome/categoria/rarità/descrizione — rimandati a un mini-task
futuro, vedi CLAUDE.md).
"""

import logging
from typing import Any

import flet as ft

from data.game_data.game_data_loader import (
    GameDataLoader,
    magic_item_category_base as _category_base,
    magic_item_rarity_bucket as _rarity_bucket,
)
from ui.theme import muted_text, title_text
from ui.widgets import responsive_dialog_width
from ui import design

logger = logging.getLogger(__name__)
_loader = GameDataLoader()

# Icone per categoria base (prima della parentesi, es. "Arma (qualsiasi
# spada)" -> "Arma") — riusa, dove possibile, le stesse icone già
# convenzionalmente associate a queste categorie altrove nell'app
# (es. "weapon"/"armor" in inventario_tab.py), per coerenza visiva.
_CATEGORY_ICONS: dict[str, str] = {
    "oggetto meraviglioso": ft.Icons.AUTO_AWESOME,
    "arma": ft.Icons.FLASH_ON,
    "armatura": ft.Icons.SHIELD,
    "anello": ft.Icons.RADIO_BUTTON_UNCHECKED,
    "pozione": ft.Icons.SCIENCE_OUTLINED,
    "bacchetta": ft.Icons.AUTO_FIX_HIGH,
    "bastone": ft.Icons.AUTO_FIX_HIGH,
    "verga": ft.Icons.AUTO_FIX_HIGH,
    "pergamena": ft.Icons.MENU_BOOK,
}
_DEFAULT_ICON = ft.Icons.AUTO_AWESOME_OUTLINED

_RARITY_ORDER = ("comune", "non comune", "raro", "molto raro", "leggendario", "variabile")
_RARITY_LABELS: dict[str, str] = {
    "comune": "Comune",
    "non comune": "Non Comune",
    "raro": "Raro",
    "molto raro": "Molto Raro",
    "leggendario": "Leggendario",
    "variabile": "Rarità Variabile",
}
# Rarità → NOME DI TOKEN, non colore: una costante di modulo è valutata a
# import-time e congelerebbe la palette chiara (Fase E.1 del restyle).
_RARITY_TONES: dict[str, str] = {
    "comune": "text_3",
    "non comune": "success",
    "raro": "magic",
    "molto raro": "warning",
    "leggendario": "primary",
    "variabile": "text_2",
}


def _rarity_color(bucket: str) -> str:
    return getattr(design.T(), _RARITY_TONES.get(bucket, "text_3"))


def _category_icon(category: str) -> str:
    return _CATEGORY_ICONS.get(_category_base(category).lower(), _DEFAULT_ICON)


class MasterMagicItemsView(ft.Column):
    """Browser compendio Oggetti Magici: ricerca + filtri + card cliccabili."""

    def __init__(self) -> None:
        super().__init__(expand=True, spacing=0)
        self._page: ft.Page | None = None
        self._all_items: list[dict[str, Any]] = sorted(
            _loader.get_magic_items(), key=lambda it: it.get("name", "")
        )
        self._categories: list[str] = sorted(
            {_category_base(it.get("category", "")) for it in self._all_items if it.get("category")}
        )
        self._query: str = ""
        self._rarity_filter: str = ""
        self._category_filter: str = ""
        self._list_col = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO, expand=True)
        self._build()

    def did_mount(self) -> None:
        self._page = self.page

    # ------------------------------------------------------------------
    # Build / filtri
    # ------------------------------------------------------------------

    def _build(self) -> None:
        self.controls.clear()

        search_tf = ft.TextField(
            hint_text="Cerca per nome...",
            prefix_icon=ft.Icons.SEARCH,
            dense=True, border_radius=8,
            on_change=self._on_search_change,
        )
        rarity_dd = ft.Dropdown(
            label="Rarità", dense=True, border_radius=6, width=160, value="",
            options=[ft.DropdownOption(key="", text="Tutte")]
            + [ft.DropdownOption(key=k, text=_RARITY_LABELS[k]) for k in _RARITY_ORDER],
            on_select=self._on_rarity_select,
        )
        category_dd = ft.Dropdown(
            label="Categoria", dense=True, border_radius=6, width=200, value="",
            options=[ft.DropdownOption(key="", text="Tutte")]
            + [ft.DropdownOption(key=c, text=c) for c in self._categories],
            on_select=self._on_category_select,
        )

        header = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.AUTO_AWESOME, color=design.T().primary, size=20),
                            ft.Container(width=8),
                            title_text("Oggetti Magici", size=18),
                            ft.Container(width=8),
                            muted_text(f"{len(self._all_items)} voci dalla Guida del Master", size=11),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        wrap=True,
                    ),
                    ft.Container(height=8),
                    search_tf,
                    ft.Row([rarity_dd, category_dd], spacing=10, wrap=True),
                ],
                spacing=4,
            ),
            padding=ft.Padding.all(16),
        )
        body = ft.Container(
            content=self._list_col, expand=True,
            padding=ft.Padding.only(left=16, right=16, bottom=16),
        )

        self.controls.append(header)
        self.controls.append(body)
        self._populate_list()

    def _on_search_change(self, e: Any) -> None:
        self._query = (e.control.value or "").strip()
        self._populate_list()
        self._refresh_list()

    def _on_rarity_select(self, e: Any) -> None:
        self._rarity_filter = e.control.value or ""
        self._populate_list()
        self._refresh_list()

    def _on_category_select(self, e: Any) -> None:
        self._category_filter = e.control.value or ""
        self._populate_list()
        self._refresh_list()

    def _refresh_list(self) -> None:
        try:
            self._list_col.update()
        except RuntimeError:
            pass

    def _filtered(self) -> list[dict[str, Any]]:
        q = self._query.lower()
        out: list[dict[str, Any]] = []
        for it in self._all_items:
            if q and q not in it.get("name", "").lower():
                continue
            if self._rarity_filter and _rarity_bucket(it.get("rarity", "")) != self._rarity_filter:
                continue
            if self._category_filter and _category_base(it.get("category", "")) != self._category_filter:
                continue
            out.append(it)
        return out

    def _populate_list(self) -> None:
        filtered = self._filtered()
        self._list_col.controls.clear()
        if not filtered:
            self._list_col.controls.append(self._empty_state())
            return
        for it in filtered:
            self._list_col.controls.append(self._item_card(it))

    def _empty_state(self) -> ft.Control:
        return ft.Container(
            content=ft.Column(
                [
                    ft.Icon(ft.Icons.AUTO_AWESOME, size=48, color=design.T().border),
                    ft.Container(height=10),
                    muted_text("Nessun oggetto trovato con questi filtri.", size=13,
                               text_align=ft.TextAlign.CENTER),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.all(32),
            alignment=ft.Alignment.CENTER,
        )

    # ------------------------------------------------------------------
    # Card + dettaglio
    # ------------------------------------------------------------------

    def _chip(self, text: str, color: str) -> ft.Container:
        return ft.Container(
            content=ft.Text(text, size=10, color=color, weight=ft.FontWeight.W_600),
            padding=ft.Padding.symmetric(horizontal=8, vertical=3),
            border=ft.Border.all(1, color),
            border_radius=10,
        )

    def _item_card(self, item: dict[str, Any]) -> ft.Control:
        name = item.get("name", "")
        category = item.get("category", "")
        rarity_raw = item.get("rarity", "")
        bucket = _rarity_bucket(rarity_raw)
        requires_att = bool(item.get("requires_attunement"))
        desc = item.get("description", "")
        preview = desc.split("\n")[0]
        if len(preview) > 130:
            preview = preview[:130].rstrip() + "…"

        chips: list[ft.Control] = [
            self._chip(_RARITY_LABELS.get(bucket, rarity_raw.strip().capitalize() or "—"),
                       _rarity_color(bucket))
        ]
        if category:
            chips.append(self._chip(category, design.T().text_3))
        if requires_att:
            chips.append(self._chip("Sintonia", design.T().warning))

        return ft.Container(
            content=ft.Row(
                [
                    ft.Icon(_category_icon(category), size=18, color=design.T().primary),
                    ft.Container(width=10),
                    ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Text(name, size=14, weight=ft.FontWeight.BOLD,
                                            color=design.T().text, expand=True),
                                    ft.Icon(ft.Icons.CHEVRON_RIGHT, size=16, color=design.T().text_3),
                                ],
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            ft.Row(chips, spacing=6, wrap=True),
                            ft.Text(preview, size=11, color=design.T().text_2),
                        ],
                        spacing=4, expand=True,
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            padding=ft.Padding.all(12),
            bgcolor=design.T().surface,
            shadow=design.elevation(1),
            border_radius=8,
            on_click=lambda e, it=item: self._open_detail(it),
            ink=True,
        )

    def _open_detail(self, item: dict[str, Any]) -> None:
        page = self._page
        if page is None:
            return

        name = item.get("name", "")
        category = item.get("category", "")
        rarity_raw = item.get("rarity", "").strip()
        requires_att = bool(item.get("requires_attunement"))
        att_restriction = item.get("attunement_restriction", "")
        desc = item.get("description", "")
        source_page = item.get("source_page")

        info_bits = [b for b in (category, rarity_raw.capitalize()) if b]
        att_text = ""
        if requires_att:
            att_text = "Richiede sintonia" + (f" ({att_restriction})" if att_restriction else "")

        dlg = ft.AlertDialog(
            title=ft.Row(
                [
                    ft.Icon(_category_icon(category), color=design.T().primary, size=18),
                    ft.Container(width=8),
                    ft.Text(name, size=15, weight=ft.FontWeight.BOLD, color=design.T().text, expand=True),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Text(", ".join(info_bits), size=12, color=design.T().text_2,
                                weight=ft.FontWeight.BOLD),
                        ft.Container(
                            content=ft.Row(
                                [
                                    ft.Icon(ft.Icons.HANDSHAKE, size=12, color=design.T().warning),
                                    ft.Container(width=4),
                                    ft.Text(att_text, size=11, color=design.T().warning),
                                ],
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            visible=bool(att_text),
                            padding=ft.Padding.only(top=4, bottom=6),
                        ),
                        ft.Divider(height=10, color=design.T().border),
                        ft.Text(desc, size=12, color=design.T().text, selectable=True),
                        ft.Container(
                            content=muted_text(f"Guida del Master, pag. {source_page}", size=10),
                            padding=ft.Padding.only(top=10),
                        ) if source_page else ft.Container(height=0),
                    ],
                    scroll=ft.ScrollMode.AUTO,
                    spacing=2,
                ),
                width=responsive_dialog_width(page, 420),
                height=460,
            ),
            actions=[ft.TextButton("Chiudi", on_click=lambda e: page.pop_dialog())],
            bgcolor=design.T().surface,
        )
        page.show_dialog(dlg)
